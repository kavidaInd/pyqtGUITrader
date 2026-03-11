"""
broker/TokenExpiryHandler.py
============================
Centralized token expiry handling and recovery mechanism.
"""

import logging
import threading
import time
from typing import Optional, Callable, Any
from datetime import datetime, timedelta
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication

logger = logging.getLogger(__name__)


class TokenExpiryHandler(QObject):
    """
    Centralized handler for token expiry events.

    This singleton manages token expiry detection, re-authentication flow,
    and recovery of interrupted operations.

    Signals:
        token_expired: Emitted when token expiry is detected
        token_refreshed: Emitted after successful re-authentication
        recovery_completed: Emitted after state recovery is done
    """

    _instance = None
    _lock = threading.RLock()

    token_expired = pyqtSignal(str)  # message
    token_refreshed = pyqtSignal()  # token successfully refreshed
    recovery_completed = pyqtSignal(bool)  # success flag

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        super().__init__()
        self._initialized = True
        self._lock = threading.RLock()

        # State tracking
        self._is_expired = False
        self._expiry_time: Optional[datetime] = None
        self._recovery_in_progress = False
        self._pending_operations: list = []
        self._recovery_callbacks: list = []

        # Auto-refresh timer
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._check_token_expiry)
        self._refresh_interval = 300  # 5 minutes
        self._refresh_timer.start(self._refresh_interval * 1000)

        # Token check on startup
        self._check_token_expiry()

        logger.info("TokenExpiryHandler initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle_token_expired(self, source: str, error_msg: str,
                             recovery_callback: Optional[Callable] = None) -> None:
        """
        Handle token expiry from any component.

        Args:
            source: Component that detected the expiry
            error_msg: Error message
            recovery_callback: Optional callback to execute after recovery
        """
        with self._lock:
            if self._is_expired and not self._recovery_in_progress:
                logger.debug(f"Token already expired, ignoring duplicate from {source}")
                return

            logger.warning(f"Token expired detected by {source}: {error_msg}")
            self._is_expired = True
            self._expiry_time = datetime.now()

            if recovery_callback:
                self._recovery_callbacks.append(recovery_callback)

        # Emit signal outside lock
        self.token_expired.emit(error_msg)

        # Auto-start recovery after short delay
        QTimer.singleShot(100, self._start_recovery)

    def register_operation(self, operation_id: str, context: dict) -> None:
        """
        Register a pending operation that needs recovery after token refresh.

        Args:
            operation_id: Unique operation identifier
            context: Operation context (symbol, quantity, price, etc.)
        """
        with self._lock:
            self._pending_operations.append({
                'id': operation_id,
                'context': context,
                'timestamp': datetime.now()
            })
            logger.debug(f"Registered pending operation: {operation_id}")

    def is_token_valid(self) -> bool:
        """Check if token is currently considered valid."""
        with self._lock:
            return not self._is_expired

    def wait_for_recovery(self, timeout: float = 30.0) -> bool:
        """
        Wait for recovery to complete.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            True if recovery completed successfully
        """
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if not self._recovery_in_progress and not self._is_expired:
                    return True
            time.sleep(0.5)
        return False

    def reset(self) -> None:
        """Reset token expiry state (for testing)."""
        with self._lock:
            self._is_expired = False
            self._expiry_time = None
            self._recovery_in_progress = False
            self._pending_operations.clear()
            self._recovery_callbacks.clear()
        logger.info("Token expiry state reset")

    # ------------------------------------------------------------------
    # Internal Methods
    # ------------------------------------------------------------------

    def _check_token_expiry(self) -> None:
        """
        Periodic check for token expiry and broker configuration status.

        Detects:
          • Broker credentials deleted/cleared mid-session → triggers setup flow
          • Token expired → triggers re-authentication flow

        NOT_CONFIGURED is only reported after the application has been fully
        launched (i.e. the main window is visible), so we never interrupt
        onboarding or the startup splash with a spurious popup.
        """
        try:
            from broker.broker_config_guard import (
                detect_broker_config_state,
                BrokerConfigState,
            )

            state, bs = detect_broker_config_state()

            if state == BrokerConfigState.NOT_CONFIGURED:
                # Only trigger the setup flow if the main window is already open.
                # This prevents the periodic check from interrupting onboarding
                # or the startup token-gate before credentials have been saved.
                app = QApplication.instance()
                main_window_open = any(
                    w.isVisible() and w.windowTitle() == "Algo Trading Dashboard"
                    for w in (app.topLevelWidgets() if app else [])
                )
                if not main_window_open:
                    logger.debug(
                        "[TokenExpiryHandler] Broker not configured but main window "
                        "not yet open — skipping periodic NOT_CONFIGURED trigger"
                    )
                    return

                # Credentials were removed from the settings panel mid-session
                self.handle_token_expired(
                    source="periodic_check",
                    error_msg="Broker is not configured. Please set up your broker credentials."
                )

            elif state == BrokerConfigState.TOKEN_EXPIRED:
                self.handle_token_expired(
                    source="periodic_check",
                    error_msg="Broker access token has expired."
                )
            # CONFIGURED_NO_TOKEN is not an error during periodic checks

        except Exception as e:
            logger.debug(f"Token check failed: {e}")

    def _start_recovery(self) -> None:
        """Start the recovery process."""
        with self._lock:
            if self._recovery_in_progress:
                return
            self._recovery_in_progress = True

        logger.info("Starting token recovery process")

        # Show the appropriate dialog in the UI thread (must run on GUI thread)
        QTimer.singleShot(0, self._show_auth_dialog)

    def _show_auth_dialog(self) -> None:
        """
        Show the appropriate re-authentication dialog in the UI thread.

        Uses broker_config_guard to determine whether the broker is not
        configured at all (show settings dialog first), or simply needs
        a fresh login (show login popup directly).
        """
        try:
            from PyQt5.QtWidgets import QDialog
            from broker.broker_config_guard import (
                detect_broker_config_state,
                BrokerConfigState,
                _show_broker_settings_dialog,
                _show_broker_login_popup,
            )

            # Get main window
            app = QApplication.instance()
            main_window = None
            if app:
                for widget in app.topLevelWidgets():
                    if widget.windowTitle() == "Algo Trading Dashboard":
                        main_window = widget
                        break

            # Detect current state
            state, broker_setting = detect_broker_config_state()

            if state == BrokerConfigState.TOKEN_VALID:
                # Token became valid in between — nothing to do
                self._on_login_completed(True)
                return

            # ── Broker NOT configured at all ──────────────────────────────
            if state == BrokerConfigState.NOT_CONFIGURED:
                logger.info(
                    "[TokenExpiryHandler] Broker not configured — showing settings dialog"
                )
                saved = _show_broker_settings_dialog(main_window, broker_setting)
                if not saved:
                    self._on_login_cancelled()
                    return

                # Re-evaluate after settings saved
                from broker.broker_config_guard import detect_broker_config_state as _detect
                state, broker_setting = _detect()

                if state == BrokerConfigState.TOKEN_VALID:
                    self._on_login_completed(True)
                    return

                if state == BrokerConfigState.NOT_CONFIGURED:
                    # Still incomplete
                    self._on_login_cancelled()
                    return

                # Fall through: now need login

            # ── Need login (fresh or expired) ─────────────────────────────
            reason = (
                "Your broker session has expired. Please re-authenticate to resume trading."
                if state == BrokerConfigState.TOKEN_EXPIRED
                else None
            )

            from gui.brokerage_settings.Brokerloginpopup import BrokerLoginPopup

            dlg = BrokerLoginPopup(
                parent=main_window,
                brokerage_setting=broker_setting,
                reason=reason,
            )

            # Connect signals
            dlg.login_completed.connect(self._on_login_completed)
            dlg.rejected.connect(self._on_login_cancelled)

            # Show dialog (blocks until closed)
            result = dlg.exec_()

            if result != QDialog.Accepted:
                self._on_login_cancelled()

        except Exception as e:
            logger.error(f"Failed to show auth dialog: {e}", exc_info=True)
            self._complete_recovery(success=False)

    def _on_login_completed(self, success: bool) -> None:
        """Handle login completion."""
        if success:
            logger.info("Re-authentication successful")
            with self._lock:
                self._is_expired = False
                self._expiry_time = None

            # Notify listeners
            self.token_refreshed.emit()

            # Execute recovery callbacks
            self._execute_recovery_callbacks()

            # Complete recovery
            self._complete_recovery(success=True)
        else:
            logger.warning("Re-authentication failed")
            self._complete_recovery(success=False)

    def _on_login_cancelled(self) -> None:
        """Handle login cancellation."""
        logger.warning("Re-authentication cancelled by user")
        self._complete_recovery(success=False)

    def _execute_recovery_callbacks(self) -> None:
        """Execute all registered recovery callbacks."""
        with self._lock:
            callbacks = self._recovery_callbacks.copy()
            self._recovery_callbacks.clear()

        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Recovery callback failed: {e}", exc_info=True)

    def _complete_recovery(self, success: bool) -> None:
        """Complete the recovery process."""
        with self._lock:
            self._recovery_in_progress = False
            if success:
                self._is_expired = False

        self.recovery_completed.emit(success)
        logger.info(f"Recovery completed: {'success' if success else 'failed'}")

        # Clear pending operations if recovery failed
        if not success:
            with self._lock:
                self._pending_operations.clear()


# Global instance
token_expiry_handler = TokenExpiryHandler()