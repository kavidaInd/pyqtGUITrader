# main.py (updated version with global exception handler)
"""
Application entry point with splash screen and first-time onboarding.
FIXED: Added global exception handler for uncaught exceptions.
"""

import logging.handlers
import os
import sys
import threading
import traceback
from datetime import datetime
from typing import Optional

import PyQt5.QtCore
from PyQt5.QtWidgets import QMessageBox

from Utils.safe_getattr import safe_hasattr
from Utils.session_utils import generate_session_id
from data.trade_state_manager import state_manager
from gui.theme_manager import show_themed_message_box

PyQt5.QtCore.QCoreApplication.setAttribute(PyQt5.QtCore.Qt.AA_ShareOpenGLContexts, True)

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

_log_file = os.path.join(LOG_DIR, "algotrade.log")


class _FlushingRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Bug #8 fix: flush after every emit so crash logs are never truncated."""

    def emit(self, record):
        super().emit(record)
        self.flush()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        _FlushingRotatingFileHandler(
            _log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger(__name__)


# ── Global exception handler ──────────────────────────────────────────────────

def global_exception_handler(exc_type, exc_value, exc_traceback):
    """
    Global exception handler for all uncaught exceptions.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        # Let KeyboardInterrupt through
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    # Try to show error dialog if GUI is running
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            msg_box = QMessageBox()
            msg_box.setWindowTitle("Fatal Error")
            msg_box.setText(f"An unhandled exception occurred:\n\n{exc_type.__name__}: {exc_value}")
            msg_box.setInformativeText("Check logs for details.\n\nThe application will now exit.")
            msg_box.setDetailedText(error_msg)
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.exec_()
    except:
        pass

    # Exit with error code
    sys.exit(1)


def thread_exception_handler(args):
    """
    Handler for uncaught exceptions in threads.
    """
    logger.critical(f"Unhandled exception in thread {args.thread.name}: {args.exc_value}",
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


# Install global exception handlers
sys.excepthook = global_exception_handler
threading.excepthook = thread_exception_handler


# ── Deferred Qt import ──────────────────────────────────────────────────────
def _qt_app():
    """Create or get the QApplication instance."""
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt

        app = QApplication.instance() or QApplication(sys.argv)
        app.setApplicationName("Algo Trading Pro")
        app.setOrganizationName("YourCompany")
        app.setOrganizationDomain("yourcompany.com")

        return app
    except Exception as e:
        logger.error(f"[main._qt_app] Failed: {e}", exc_info=True)
        raise


def _apply_saved_theme(app):
    """
    Rule 13.2: Load saved theme preference and apply it before any window opens.
    """
    try:
        from gui.theme_manager import theme_manager

        # Load saved preference (doesn't apply yet)
        theme_manager.load_preference()

        # Apply the theme's palette to QApplication
        _apply_theme_palette(app, theme_manager.current_theme)

        logger.info(f"[main._apply_saved_theme] Loaded theme: {theme_manager.current_theme}")

    except Exception as e:
        logger.error(f"[main._apply_saved_theme] Failed: {e}", exc_info=True)
        # Fallback to dark theme
        _apply_theme_palette(app, "dark")


def _apply_theme_palette(app, theme: str):
    """Apply a global palette based on theme."""
    try:
        from PyQt5.QtGui import QPalette, QColor
        from PyQt5.QtCore import Qt

        if theme == "dark":
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor("#0d1117"))
            palette.setColor(QPalette.WindowText, QColor("#e6edf3"))
            palette.setColor(QPalette.Base, QColor("#161b22"))
            palette.setColor(QPalette.AlternateBase, QColor("#21262d"))
            palette.setColor(QPalette.Text, QColor("#e6edf3"))
            palette.setColor(QPalette.Button, QColor("#21262d"))
            palette.setColor(QPalette.ButtonText, QColor("#e6edf3"))
            palette.setColor(QPalette.Highlight, QColor("#388bfd"))
            palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
            palette.setColor(QPalette.ToolTipBase, QColor("#161b22"))
            palette.setColor(QPalette.ToolTipText, QColor("#e6edf3"))
            palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#484f58"))
            palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#484f58"))
        else:  # light theme
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor("#ffffff"))
            palette.setColor(QPalette.WindowText, QColor("#1f2328"))
            palette.setColor(QPalette.Base, QColor("#f6f8fa"))
            palette.setColor(QPalette.AlternateBase, QColor("#eaeef2"))
            palette.setColor(QPalette.Text, QColor("#1f2328"))
            palette.setColor(QPalette.Button, QColor("#eaeef2"))
            palette.setColor(QPalette.ButtonText, QColor("#1f2328"))
            palette.setColor(QPalette.Highlight, QColor("#0969da"))
            palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
            palette.setColor(QPalette.ToolTipBase, QColor("#f6f8fa"))
            palette.setColor(QPalette.ToolTipText, QColor("#1f2328"))
            palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#afb8c1"))
            palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#afb8c1"))

        app.setPalette(palette)

    except Exception as e:
        logger.warning(f"[main._apply_theme_palette] Could not apply palette: {e}")


# ── Splash Screen ──────────────────────────────────────────────────────────
def _show_splash():
    """Create and show the splash screen."""
    try:
        from gui.splash_screen import AnimatedSplashScreen

        # Check if logo exists, use default if not
        logo_path = "assets/logo.png"
        if not os.path.exists(logo_path):
            logo_path = None
            logger.warning("[main._show_splash] Logo file not found, using default")

        splash = AnimatedSplashScreen(logo_path)
        splash.show()
        splash.set_status("Initializing application...")
        splash.set_progress(0)

        # Process events to ensure splash displays
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        return splash
    except Exception as e:
        logger.error(f"[main._show_splash] Failed: {e}", exc_info=True)
        return None


def _update_splash(splash, status, progress):
    """Update splash screen status and progress."""
    try:
        if splash:
            splash.set_status(status)
            splash.set_progress(progress)
            # Process events to ensure UI updates
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
    except Exception as e:
        logger.warning(f"[main._update_splash] Failed: {e}")


# ── Database ───────────────────────────────────────────────────────────────
def _run_db_init(splash=None) -> bool:
    """Initialise / migrate the SQLite database. Returns True on success."""
    try:
        _update_splash(splash, "Initializing database...", 10)
        from db.db_installer import run_startup_check
        result = run_startup_check()
        if not result.ok:
            logger.critical(f"[main._run_db_init] DB initialisation failed:\n{result.summary()}")
            return False
        logger.info("[main._run_db_init] DB initialisation OK")
        return True
    except Exception as e:
        logger.critical(f"[main._run_db_init] DB initialisation raised an exception: {e}", exc_info=True)
        return False


# ── State Manager ──────────────────────────────────────────────────────────
def _init_state_manager(splash=None) -> bool:
    """Initialise the state manager and ensure the trade state singleton is ready."""
    try:
        _update_splash(splash, "Initializing state manager...", 20)
        from data.trade_state_manager import state_manager
        state = state_manager.get_state()
        logger.info(f"[main._init_state_manager] State manager initialised with state ID: {id(state)}")
        return True
    except Exception as e:
        logger.critical(f"[main._init_state_manager] State manager initialisation failed: {e}", exc_info=True)
        return False


# ── Session Initialization (Database Session) ─────────────────────────────
def _init_db_session(splash=None) -> Optional[int]:
    """
    Create a database session record and store the session ID in state manager.

    Args:
        splash: Optional splash screen for status updates

    Returns:
        Optional[int]: Database session ID if successful, None otherwise
    """
    try:
        _update_splash(splash, "Creating trading session...", 25)

        from db.crud import sessions, daily_trade, trading_mode, strategies

        # Get current settings for session creation
        daily_settings = daily_trade.get()
        mode_settings = trading_mode.get()
        active_strategy = strategies.get_active_slug()

        # Create database session
        session_id = sessions.create(
            mode=mode_settings.get("mode", "PAPER"),
            exchange=daily_settings.get("exchange", "NSE"),
            derivative=daily_settings.get("derivative", "NIFTY"),
            lot_size=daily_settings.get("lot_size", 65),
            interval=daily_settings.get("history_interval", "1m"),  # Always 1m; candles are resampled by candle manager
            strategy_slug=active_strategy
        )

        if session_id > 0:
            logger.info(f"[main._init_db_session] Database session created with ID: {session_id}")

            # Store in state manager for global access
            state = state_manager.get_state()
            state.session_id = session_id

            return session_id
        else:
            logger.error("[main._init_db_session] Failed to create database session")
            return None

    except Exception as e:
        logger.error(f"[main._init_db_session] Failed: {e}", exc_info=True)
        return None


def _init_app_session(splash=None) -> bool:
    """
    Initialize application session ID and update it to trade state.

    Args:
        splash: Optional splash screen for status updates

    Returns:
        bool: True if successful
    """
    try:
        _update_splash(splash, "Initializing application session...", 15)

        # Generate application session ID
        app_session_id = generate_session_id()
        session_start_time = datetime.now()

        # Get trade state and update session info
        state = state_manager.get_state()
        state.app_session_id = app_session_id
        state.session_start_time = session_start_time

        logger.info(f"[main._init_app_session] Application session initialized: {app_session_id}")
        logger.info(f"[main._init_app_session] Session start time: {session_start_time}")

        return True

    except Exception as e:
        logger.error(f"[main._init_app_session] Failed to initialize application session: {e}", exc_info=True)
        return False


# ── License Gate ───────────────────────────────────────────────────────────
def _run_license_gate(qt_app, splash=None) -> bool:
    """Soft license check on startup."""
    try:
        _update_splash(splash, "Checking license...", 30)
        from license.license_manager import license_manager
        from license.activation_dialog import ActivationDialog
        from PyQt5.QtWidgets import QMessageBox, QDialog

        result = license_manager.verify_on_startup()
        logger.info(f"[main._run_license_gate] License check: {result}")

        if result.ok:
            if result.offline:
                logger.warning(f"[main._run_license_gate] Running in offline grace mode: {result.reason}")
            return True

        # not_activated  → first run with no license at all: pass through to app
        #                  ActivationDialog will be shown by the app itself on first-run
        # expired         → paid license expired: pass through, live trading gate
        #                  will block them and prompt upgrade
        # trial_expired   → 7-day trial over: show upgrade dialog before entering app
        if result.reason == "not_activated":
            logger.info("[main._run_license_gate] No license — opening activation dialog")
            from license.activation_dialog import ActivationDialog
            from PyQt5.QtWidgets import QDialog
            dlg = ActivationDialog(
                parent=None,
                reason="",
                prefill_email=license_manager.get_cached_email(),
                start_on_tab="trial",
            )
            dlg_result = dlg.exec_()
            # Whether they activated or not, let them in — live gate will block if needed
            return True

        if result.reason == "trial_expired":
            logger.info("[main._run_license_gate] Trial expired — showing upgrade dialog")
            from license.activation_dialog import ActivationDialog
            from PyQt5.QtWidgets import QDialog
            dlg = ActivationDialog(
                parent=None,
                reason=(
                    f"Your 7-day free trial has ended."
                    "Subscribe for ₹4,999/month to continue live trading. "
                    "Paper trading and backtesting remain free."
                ),
                prefill_email=license_manager.get_cached_email(),
                start_on_tab="activate",
            )
            dlg.exec_()
            # Let them into the app — live trading gate blocks if not activated
            return True

        if result.reason == "expired":
            logger.info("[main._run_license_gate] Paid license expired — continuing in paper mode")
            return True

        # Hard failures
        reason_map = {
            "revoked": "Your license has been deactivated. Please contact support.",
            "invalid_machine": (
                "This machine is not authorised for your license. "
                "Contact support to transfer your license to this machine."
            ),
            "order_cancelled": "Your order was cancelled or refunded.",
        }
        display_reason = reason_map.get(result.reason, result.reason)

        _max_activation_attempts = 3
        for _attempt in range(_max_activation_attempts):
            dlg = ActivationDialog(
                parent=None,
                reason=display_reason,
                prefill_email=license_manager.get_cached_email(),
                start_on_tab="activate",
            )
            dlg_result = dlg.exec_()

            if dlg_result == QDialog.Accepted:
                logger.info("[main._run_license_gate] Re-activation accepted — proceeding")
                return True
            else:
                reply = QMessageBox.question(
                    None,
                    "Exit?",
                    "Your license could not be verified.\n\nExit the application?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    return False
        # Bug #7 fix: exhausted max activation attempts
        logger.warning("[main._run_license_gate] Max activation attempts reached — exiting")
        return False
    except Exception as e:
        logger.error(f"[main._run_license_gate] Unexpected error — continuing in free mode: {e}", exc_info=True)
        return True


# ── Onboarding ─────────────────────────────────────────────────────────────
def _run_onboarding(splash=None) -> bool:
    """Run the first-time setup wizard if this is the first launch."""
    try:
        from gui.onboarding_popup import is_first_time, OnboardingWizard
        from PyQt5.QtWidgets import QDialog, QMessageBox

        _update_splash(splash, "Checking first-time setup...", 35)

        # Check if this is first run
        if not is_first_time():
            logger.info("[main._run_onboarding] Not first time - skipping onboarding")
            return True

        logger.info("[main._run_onboarding] First-time launch detected - showing onboarding wizard")

        # Hide splash while showing wizard
        if splash:
            splash.hide()

        # Create and show wizard
        wizard = OnboardingWizard()
        result = wizard.exec_()

        # Show splash again
        if splash:
            splash.show()

        if result == QDialog.Accepted:
            logger.info("[main._run_onboarding] Onboarding completed successfully")

            _reload_all_settings()

            return True
        else:
            logger.warning("[main._run_onboarding] Onboarding cancelled by user")
            reply = show_themed_message_box(
                None,
                "Continue without setup?",
                "You haven't completed the initial setup.\n\n"
                "You can continue with default settings, but some features may not work.\n\n"
                "Continue anyway?",
                QMessageBox.Yes | QMessageBox.No
            )
            return reply == QMessageBox.Yes
    except Exception as e:
        logger.error(f"[main._run_onboarding] Failed — skipping onboarding: {e}", exc_info=True)
        return True


def _reload_all_settings():
    try:
        from gui.brokerage_settings.BrokerageSetting import BrokerageSetting
        from gui.daily_trade.DailyTradeSetting import DailyTradeSetting
        from gui.profit_loss.ProfitStoplossSetting import ProfitStoplossSetting
        from gui.trading_mode.TradingModeSetting import TradingModeSetting

        _bs = BrokerageSetting()
        _bs.load()
        _dt = DailyTradeSetting()
        _dt.load()
        _pl = ProfitStoplossSetting()
        _pl.load()
        _tm = TradingModeSetting()
        _tm.load()

        logger.info("[main._reload_all_settings] All settings reloaded from database after onboarding")
    except Exception as e:
        logger.error(f"[main._reload_all_settings] Failed to reload settings: {e}", exc_info=True)


# ── Token Gate ─────────────────────────────────────────────────────────────

def _run_token_gate(qt_app, splash=None) -> bool:
    """
    Verify broker configuration and token before opening the main window.

    Uses broker_config_guard to detect the exact state and show the
    right dialog:

        • Broker not configured (skipped setup or credentials deleted)
          → BrokerageSettingDialog  so the user can pick a broker + enter creds
          → Followed by BrokerLoginPopup if a login step is needed

        • Broker configured but no token yet (first run after setup)
          → BrokerLoginPopup  (no expiry banner)

        • Broker configured, token present but expired
          → BrokerLoginPopup  (with "session expired" banner)

        • Valid token
          → Nothing shown; returns True immediately.

    Returns True only when the app can safely proceed.
    """
    try:
        from broker.broker_config_guard import (
            detect_broker_config_state,
            BrokerConfigState,
            show_broker_setup_flow,
        )
        from PyQt5.QtWidgets import QMessageBox

        # ── Fast path: valid token ─────────────────────────────────────────
        state, _ = detect_broker_config_state()
        if state == BrokerConfigState.TOKEN_VALID:
            logger.info("[main._run_token_gate] Token valid — proceeding to main window")
            return True

        # ── Need interaction — close splash first ──────────────────────────
        if splash:
            try:
                splash.close()
            except Exception:
                pass

        # ── Determine user-friendly reason string ─────────────────────────
        if state == BrokerConfigState.NOT_CONFIGURED:
            reason = None   # settings dialog shown first; no "expired" banner
        elif state == BrokerConfigState.TOKEN_EXPIRED:
            reason = (
                "Your broker access token has expired or has not been generated yet. "
                "Please login to continue."
            )
        else:
            reason = None   # CONFIGURED_NO_TOKEN — fresh login, no banner

        logger.warning(
            f"[main._run_token_gate] Broker state={state.name} — showing setup flow"
        )

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            success = show_broker_setup_flow(parent=None, reason=reason)

            if success:
                logger.info(
                    f"[main._run_token_gate] Setup flow completed on attempt {attempt}"
                )
                return True

            # User cancelled
            if attempt < max_attempts:
                reply = QMessageBox.question(
                    None,
                    "Broker Setup Required",
                    "A valid broker configuration and access token are required to use this application.\n\n"
                    "Would you like to try again?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply != QMessageBox.Yes:
                    logger.info("[main._run_token_gate] User chose not to retry — exiting")
                    return False
            else:
                QMessageBox.critical(
                    None,
                    "Broker Setup Required",
                    "Broker setup was not completed.\n"
                    "The application cannot start without a valid broker configuration.",
                )
                logger.warning("[main._run_token_gate] Max attempts reached — exiting")
                return False

        return False

    except Exception as e:
        logger.error(f"[main._run_token_gate] Unexpected error: {e}", exc_info=True)
        # Don't block startup on unexpected error — let TradingGUI handle it
        return True



# ── Main Window ────────────────────────────────────────────────────────────
def _launch_main_window(qt_app, splash=None, update_info=None) -> int:
    """Create TradingGUI, inject optional update banner, enter event loop."""
    try:
        _update_splash(splash, "Loading main window...", 80)

        from TradingGUI import TradingGUI

        # Create the main window
        window = TradingGUI()

        # Inject optional update banner
        if update_info and safe_hasattr(update_info, 'available') and update_info.available:
            _inject_update_banner(window, update_info)

        _inject_trial_banner(window)

        # Update splash to ready
        _update_splash(splash, "Ready!", 100)

        # Process events to ensure splash updates
        qt_app.processEvents()

        window.show()
        window.raise_()  # Bring to front
        window.activateWindow()  # Activate window

        # Now finish the splash screen (this will close it)
        if splash:
            # Small delay to ensure window is fully rendered
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, lambda: splash.finish(window))

        # Enter event loop
        return qt_app.exec_()

    except Exception as e:
        logger.critical(f"[main._launch_main_window] Failed to launch main window: {e}", exc_info=True)
        if splash:
            splash.close()
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(
            None,
            "Launch Error",
            f"Failed to launch main window:\n{e}\n\nPlease check the logs for details."
        )
        return 1


def _inject_update_banner(window, update_info):
    """Inject update banner into main window."""
    try:
        from license.activation_dialog import UpdateBanner
        from license.auto_updater import auto_updater
        from PyQt5.QtWidgets import QWidget, QVBoxLayout

        banner = UpdateBanner(
            version=update_info.latest_version,
            notes=update_info.release_notes or "",
            parent=window,
        )

        def _start_update():
            from license.activation_dialog import MandatoryUpdateDialog
            dlg = MandatoryUpdateDialog(update_info, parent=window)
            dlg.update_requested.connect(lambda: _download_in_thread(dlg))
            dlg.exec_()

        def _download_in_thread(dlg):
            import threading
            from license.auto_updater import DownloadProgress
            from PyQt5.QtCore import pyqtSignal, QObject

            class _ProgressRelay(QObject):
                progress = pyqtSignal(int, str)  # (percent, message)

            relay = _ProgressRelay()
            relay.progress.connect(dlg.set_progress)

            def _run():
                def _cb(p: DownloadProgress):
                    pct = int(p.percent)
                    if p.error:
                        msg = f"Error: {p.error}"
                    elif p.done:
                        msg = "Installing…"
                    else:
                        msg = f"Downloading… {pct:.0f}%"
                    relay.progress.emit(pct, msg)

                auto_updater.download_and_install(update_info, _cb)

            threading.Thread(target=_run, daemon=True, name="OptionalUpdate").start()

        banner.update_requested.connect(_start_update)
        banner.dismissed.connect(banner.deleteLater)

        central = window.centralWidget()
        if central and central.layout():
            central.layout().insertWidget(0, banner)
            logger.info("[main._inject_update_banner] Update banner injected into main window")

    except Exception as e:
        logger.warning(f"[main._inject_update_banner] Could not inject update banner: {e}", exc_info=True)


def _inject_trial_banner(window):
    """Inject trial countdown banner for active trial users."""
    try:
        from license.license_manager import license_manager, PLAN_TRIAL
        info = license_manager.get_local_info()
        # Only show banner while trial is still active (plan == "trial" + key present)
        # Expired trials are handled at startup in _run_license_gate
        if info.get("plan") != PLAN_TRIAL or not info.get("license_key" if "license_key" in info else "order_id"):
            return

        days = int(info.get("days_remaining", 0))

        from license.activation_dialog import TrialExpiryBanner, ActivationDialog
        banner = TrialExpiryBanner(days_remaining=days, parent=window)

        def _open_upgrade():
            dlg = ActivationDialog(
                parent=window,
                reason="",
                prefill_email=info.get("email", ""),
                start_on_tab="activate",
            )
            from PyQt5.QtWidgets import QDialog
            if dlg.exec_() == QDialog.Accepted:
                banner.hide()

        banner.upgrade_clicked.connect(_open_upgrade)
        banner.dismissed.connect(banner.deleteLater)

        central = window.centralWidget()
        if central and central.layout():
            central.layout().insertWidget(0, banner)
            logger.info(f"[main._inject_trial_banner] Trial expiry banner injected ({days} day(s) remaining)")

    except Exception as e:
        logger.warning(f"[main._inject_trial_banner] Could not inject trial banner: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    """Main application entry point."""
    logger.info("=" * 60)
    logger.info("  Algo Trading Pro — starting up")
    logger.info("=" * 60)

    # Global variable to store database session ID for use throughout the app
    global session_id

    try:
        # ── Step 1: Create Qt app ──────────────────────────────────────────────
        qt_app = _qt_app()

        # ── Step 2: Apply saved theme preference ───────────────────────────────
        # This ensures the application starts with the user's preferred theme
        _apply_saved_theme(qt_app)

        # ── Step 3: Show splash screen ─────────────────────────────────────────
        splash = _show_splash()
        qt_app.processEvents()

        def _exit(code: int, msg_title: str = "", msg_body: str = "") -> int:
            """Bug #6 fix: always close the splash before an early exit."""
            if splash:
                try:
                    splash.close()
                except Exception:
                    pass
            if msg_title and msg_body:
                show_themed_message_box(None, msg_title, msg_body, QMessageBox.Ok)
            return code

        # ── Step 4: DB ─────────────────────────────────────────────────────────
        if not _run_db_init(splash):
            return _exit(
                1,
                "Database Error",
                "Database initialisation failed.\n"
                "Check the logs/ folder for details.\n\n"
                "The application will now exit.",
            )

        # ── Step 5: State manager ───────────────────────────────────────────────
        if not _init_state_manager(splash):
            return _exit(
                1,
                "State Manager Error",
                "State manager initialisation failed.\n"
                "Check the logs/ folder for details.\n\n"
                "The application will now exit.",
            )

        # ── Step 6: Application Session (string ID) ────────────────────────────
        if not _init_app_session(splash):
            logger.warning("[main.main] Application session initialization failed, continuing anyway")
            # Not critical, continue

        # ── Step 7: License ─────────────────────────────────────────────────────
        if not _run_license_gate(qt_app, splash):
            logger.info("[main.main] License gate rejected — exiting")
            return _exit(1)

        # ── Step 8: Onboarding (first-time setup) ───────────────────────────────
        if not _run_onboarding(splash):
            logger.info("[main.main] User chose to exit after onboarding")
            return _exit(1)

        # ── Step 9: Database Session (integer ID for foreign keys) ─────────────
        # This MUST happen after onboarding because onboarding might change settings
        session_id = _init_db_session(splash)
        if session_id is None:
            logger.warning("[main.main] Database session creation failed, continuing with limited functionality")
            # Not critical for UI, but orders won't work

        # ── Step 10: Token gate ─────────────────────────────────────────────────
        # Verify broker token before opening the main window.  If expired, the
        # user must complete login now so the main window always opens with a
        # live session and can load chart data immediately.
        if not _run_token_gate(qt_app, splash):
            logger.info("[main.main] Token gate rejected — exiting")
            return _exit(1)

        # ── Step 11: Main window ────────────────────────────────────────────────
        exit_code = _launch_main_window(qt_app, splash)
        logger.info(f"[main.main] Application exited with code {exit_code}")
        return exit_code

    except Exception as e:
        logger.critical(f"[main.main] Unhandled exception: {e}", exc_info=True)
        # Try to show error message if possible
        try:
            show_themed_message_box(
                None, "Startup Error",
                f"An unexpected error occurred during startup:\n{e}\n\nPlease check the logs for details."
            )
        except:
            pass
        return 1


# Global variable to store database session ID for use throughout the app
session_id = None


def get_session_id() -> Optional[int]:
    """
    Get the current database session ID.

    Returns:
        Optional[int]: Database session ID or None if not initialized
    """
    return session_id


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        logger.critical(f"[main] Unhandled exception at top level: {e}", exc_info=True)
        sys.exit(1)