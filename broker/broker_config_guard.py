"""
broker/broker_config_guard.py
==============================
Central utility that checks whether the broker is fully configured before
attempting any token-related operation.

The guard covers three scenarios the original code did not distinguish:

    1. Broker NOT selected / credentials empty
       → Show BrokerageSettingDialog so the user can pick a broker and
         enter their API credentials.

    2. Broker selected but no login token yet  (first run after config)
       → Show BrokerLoginPopup so the user can authenticate.

    3. Broker configured AND token present but EXPIRED
       → Show BrokerLoginPopup with the "session expired" banner.

This module is imported by:
    • TokenExpiryHandler  (runtime token-expiry events)
    • main._run_token_gate (startup gate)
    • Any other component that previously showed a raw "token expired" error.
"""

import logging
from enum import Enum, auto
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class BrokerConfigState(Enum):
    """Possible states of broker configuration completeness."""
    NOT_CONFIGURED   = auto()   # No broker selected or credentials empty
    CONFIGURED_NO_TOKEN = auto()  # Creds present but no access token at all
    TOKEN_EXPIRED    = auto()   # Creds + old token, but token is expired/invalid
    TOKEN_VALID      = auto()   # Fully ready — no popup needed


def detect_broker_config_state() -> Tuple[BrokerConfigState, "BrokerageSetting"]:  # noqa: F821
    """
    Load BrokerageSetting from the database and classify the current state.

    Returns:
        (BrokerConfigState, BrokerageSetting instance)
    """
    try:
        from gui.brokerage_settings.BrokerageSetting import BrokerageSetting

        bs = BrokerageSetting()
        bs.load()
        bs._load_token_info()

        # ── Check 1: is the broker itself configured? ──────────────────────
        client_id   = (bs.client_id   or "").strip()
        secret_key  = (bs.secret_key  or "").strip()
        broker_type = (bs.broker_type or "").strip()

        if not broker_type or not client_id or not secret_key:
            logger.info(
                "[broker_config_guard] Broker NOT configured "
                f"(broker_type={broker_type!r}, client_id={'<empty>' if not client_id else '<set>'})"
            )
            return BrokerConfigState.NOT_CONFIGURED, bs

        # ── Check 2: is there a token at all? ─────────────────────────────
        token_info    = bs.get_token_info()
        access_token  = (token_info.get("access_token") or "").strip()

        if not access_token:
            logger.info(
                "[broker_config_guard] Broker configured but NO access token present"
            )
            return BrokerConfigState.CONFIGURED_NO_TOKEN, bs

        # ── Check 3: is the token still valid? ────────────────────────────
        if bs.has_valid_token:
            logger.info("[broker_config_guard] Token is valid — no popup required")
            return BrokerConfigState.TOKEN_VALID, bs

        logger.info("[broker_config_guard] Token exists but is EXPIRED")
        return BrokerConfigState.TOKEN_EXPIRED, bs

    except Exception as e:
        logger.error(f"[broker_config_guard.detect_broker_config_state] {e}", exc_info=True)
        # Fail-safe: treat as not configured so we don't silently block startup
        try:
            from gui.brokerage_settings.BrokerageSetting import BrokerageSetting
            return BrokerConfigState.NOT_CONFIGURED, BrokerageSetting()
        except Exception:
            return BrokerConfigState.NOT_CONFIGURED, None


def show_broker_setup_flow(
    parent=None,
    reason: Optional[str] = None,
    notifier=None,
    force_state: Optional[BrokerConfigState] = None,
) -> bool:
    """
    Show the appropriate dialog(s) based on the current broker config state.

    Flow:
        NOT_CONFIGURED       → BrokerageSettingDialog  (step 1)
                               If user saves, re-evaluate → may show login popup next
        CONFIGURED_NO_TOKEN  → BrokerLoginPopup  (no expiry banner)
        TOKEN_EXPIRED        → BrokerLoginPopup  (with expiry banner)
        TOKEN_VALID          → nothing shown, returns True immediately

    Args:
        parent:      Qt parent widget (can be None)
        reason:      Human-readable reason string (shown in banner for expiry)
        notifier:    Optional Telegram notifier instance
        force_state: Override auto-detection (used for testing)

    Returns:
        True  → user completed setup / token is now valid
        False → user cancelled, app should not proceed
    """
    try:
        from PyQt5.QtWidgets import QDialog, QMessageBox

        state, bs = detect_broker_config_state()
        if force_state is not None:
            state = force_state

        # ── Fully ready ────────────────────────────────────────────────────
        if state == BrokerConfigState.TOKEN_VALID:
            return True

        # ── No broker configured at all ────────────────────────────────────
        if state == BrokerConfigState.NOT_CONFIGURED:
            logger.info("[broker_config_guard] Showing BrokerageSettingDialog (no broker configured)")
            result = _show_broker_settings_dialog(parent, bs)

            if not result:
                # User dismissed settings without saving
                return False

            # Re-evaluate state after settings were saved
            new_state, bs = detect_broker_config_state()

            if new_state == BrokerConfigState.TOKEN_VALID:
                return True

            if new_state == BrokerConfigState.NOT_CONFIGURED:
                # Still not configured — user likely saved partial data
                QMessageBox.warning(
                    parent,
                    "Broker Not Configured",
                    "Broker configuration is still incomplete.\n\n"
                    "Please enter your Client ID and Secret Key, then try again."
                )
                return False

            # Settings saved — now need login
            state = new_state   # fall through to login popup below

        # ── Broker configured but needs login ──────────────────────────────
        if state in (BrokerConfigState.CONFIGURED_NO_TOKEN, BrokerConfigState.TOKEN_EXPIRED):
            popup_reason = reason
            if state == BrokerConfigState.TOKEN_EXPIRED and not popup_reason:
                popup_reason = (
                    "Your broker access token has expired or is no longer valid. "
                    "Please re-authenticate to continue."
                )
            elif state == BrokerConfigState.CONFIGURED_NO_TOKEN and not popup_reason:
                popup_reason = None  # fresh login — no expiry banner

            logger.info(
                f"[broker_config_guard] Showing BrokerLoginPopup (state={state.name})"
            )
            result = _show_broker_login_popup(parent, bs, popup_reason, notifier)
            return result

        return False

    except Exception as e:
        logger.error(f"[broker_config_guard.show_broker_setup_flow] {e}", exc_info=True)
        return False


# ── Internal helpers ──────────────────────────────────────────────────────────

def _show_broker_settings_dialog(parent, bs) -> bool:
    """
    Show BrokerageSettingDialog.

    Returns True if the dialog was accepted (settings saved).
    """
    try:
        from PyQt5.QtWidgets import QDialog
        from gui.brokerage_settings.BrokerageSettingGUI import BrokerageSettingDialog

        dlg = BrokerageSettingDialog(broker_setting=bs, parent=parent)

        # Customise title to make the intent clear
        try:
            dlg.setWindowTitle("⚙️ Broker Setup Required")
        except Exception:
            pass

        result = dlg.exec_()
        return result == QDialog.Accepted

    except Exception as e:
        logger.error(f"[broker_config_guard._show_broker_settings_dialog] {e}", exc_info=True)
        return False


def _show_broker_login_popup(parent, bs, reason: Optional[str], notifier) -> bool:
    """
    Show BrokerLoginPopup.

    Returns True if login completed successfully.
    """
    try:
        from PyQt5.QtWidgets import QDialog
        from gui.brokerage_settings.Brokerloginpopup import BrokerLoginPopup

        dlg = BrokerLoginPopup(
            parent=parent,
            brokerage_setting=bs,
            reason=reason,
            notifier=notifier,
        )
        result = dlg.exec_()
        return result == QDialog.Accepted

    except Exception as e:
        logger.error(f"[broker_config_guard._show_broker_login_popup] {e}", exc_info=True)
        return False