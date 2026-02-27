"""
app_main.py
===========
Application entry point for the Algo Trading SaaS.

Replaces any existing main.py / run.py.  Every feature that must run
before the main window is shown is sequenced here:

  Step 1 — DB initialisation (schema + migrations)
  Step 2 — License verification (blocks if not activated / expired)
  Step 3 — Auto-update check (blocks on mandatory, optional banner otherwise)
  Step 4 — Main window launch

Activation gate
───────────────
  Free / unactivated users: app starts immediately.  No startup gate.
  Paper trading and historical backtesting are always available for free.
  The license gate fires only when a user attempts to start LIVE trading
  (handled inside TradingGUI._start_app via license_manager.is_live_trading_allowed()).

  If a stored paid license fails verification (revoked/expired/machine mismatch)
  the ActivationDialog is still shown on startup so the user can re-activate.

Auto-update gate
────────────────
  • OPTIONAL update → UpdateBanner is injected into TradingGUI's toolbar.
  • MANDATORY update → MandatoryUpdateDialog blocks the main window.
    - User clicks "Download & Install" → progress dialog, installer launched, app exits.
    - User clicks "Exit" → sys.exit(1).

Usage
─────
  python app_main.py
  # or as the entry_point in setup.cfg / pyproject.toml:
  #   algotrade = app_main:main
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import traceback
from typing import Optional

import PyQt5.QtCore
PyQt5.QtCore.QCoreApplication.setAttribute(PyQt5.QtCore.Qt.AA_ShareOpenGLContexts, True)

# ── Bootstrap logging before any other import ─────────────────────────────────
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

_log_file = os.path.join(LOG_DIR, "algotrade.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            _log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger(__name__)


# ── Deferred Qt import (so logging is set up before PyQt crashes) ─────────────
def _qt_app() -> "QApplication":
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Algo Trading Pro")
    app.setOrganizationName("YourCompany")
    return app


def _apply_dark_palette(app):
    """Apply a global dark palette before any window opens."""
    try:
        from PyQt5.QtGui import QPalette, QColor
        from PyQt5.QtCore import Qt
        dark = QPalette()
        dark.setColor(QPalette.Window,          QColor("#0d1117"))
        dark.setColor(QPalette.WindowText,      QColor("#e6edf3"))
        dark.setColor(QPalette.Base,            QColor("#161b22"))
        dark.setColor(QPalette.AlternateBase,   QColor("#21262d"))
        dark.setColor(QPalette.Text,            QColor("#e6edf3"))
        dark.setColor(QPalette.Button,          QColor("#21262d"))
        dark.setColor(QPalette.ButtonText,      QColor("#e6edf3"))
        dark.setColor(QPalette.Highlight,       QColor("#388bfd"))
        dark.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        app.setPalette(dark)
    except Exception as e:
        logger.warning(f"Could not apply dark palette: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Database
# ─────────────────────────────────────────────────────────────────────────────

def _run_db_init() -> bool:
    """Initialise / migrate the SQLite database. Returns True on success."""
    try:
        from db.db_installer import run_startup_check
        result = run_startup_check()
        if not result.ok:
            logger.critical(f"DB initialisation failed:\n{result.summary()}")
            return False
        logger.info("DB initialisation OK")
        return True
    except Exception:
        logger.critical("DB initialisation raised an exception", exc_info=True)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — License gate
# ─────────────────────────────────────────────────────────────────────────────

def _run_license_gate(qt_app) -> bool:
    """
    Soft license check on startup.

    - not_activated / trial_expired / expired → app starts freely.
      Free users land straight in the app; paper + backtest always work.
      The live-trading gate is enforced inside TradingGUI._start_app.

    - revoked / invalid_machine / order_cancelled → hard block.
      These indicate misuse or support issues that need resolving before
      the app should run at all.

    Returns True if the app should continue launching.
    """
    from license.license_manager import license_manager
    from license.activation_dialog import ActivationDialog
    from PyQt5.QtWidgets import QMessageBox, QDialog

    result = license_manager.verify_on_startup()
    logger.info(f"License check: {result}")

    # ── Happy path: valid paid/trial license ─────────────────────────────
    if result.ok:
        if result.offline:
            logger.warning(f"Running in offline grace mode: {result.reason}")
        return True

    # ── Soft failures: no license yet, or expired — let the user in freely ─
    SOFT_REASONS = {"not_activated", "trial_expired", "expired"}
    if result.reason in SOFT_REASONS:
        logger.info(
            f"No active paid license ({result.reason!r}) — "
            "starting in free mode (paper/backtest only)"
        )
        return True

    # ── Hard failures: revoke, machine mismatch, cancelled order ─────────
    reason_map = {
        "revoked":         "Your license has been deactivated. Please contact support.",
        "invalid_machine": (
            "This machine is not authorised for your license. "
            "Contact support to transfer your license to this machine."
        ),
        "order_cancelled": "Your order was cancelled or refunded.",
    }
    display_reason = reason_map.get(result.reason, result.reason)

    while True:
        dlg = ActivationDialog(
            parent=None,
            reason=display_reason,
            prefill_email=license_manager.get_cached_email(),
            start_on_tab="activate",
        )
        dlg_result = dlg.exec_()

        if dlg_result == QDialog.Accepted:
            logger.info("Re-activation accepted — proceeding")
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



# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Main window
# ─────────────────────────────────────────────────────────────────────────────

def _launch_main_window(qt_app, update_info=None) -> int:
    """Create TradingGUI, inject optional update banner, enter event loop."""
    from TradingGUI import TradingGUI
    from config import Config

    config = Config()
    window = TradingGUI()

    # Inject optional update banner into the main window
    if update_info and update_info.available:
        _inject_update_banner(window, update_info)

    # Inject trial expiry banner if the user is on a trial
    _inject_trial_banner(window)

    window.show()
    return qt_app.exec_()


def _inject_update_banner(window: "TradingGUI", update_info) -> None:
    """
    Prepend UpdateBanner to TradingGUI's central widget layout.
    Safe — does nothing if the window layout doesn't support it.
    """
    try:
        from license.activation_dialog import UpdateBanner
        from license.auto_updater import auto_updater
        from PyQt5.QtWidgets import QWidget, QVBoxLayout

        banner = UpdateBanner(
            version = update_info.latest_version,
            notes   = update_info.release_notes or "",
            parent  = window,
        )

        def _start_update():
            from license.activation_dialog import MandatoryUpdateDialog
            # Reuse the mandatory dialog for the optional flow
            dlg = MandatoryUpdateDialog(update_info, parent=window)
            dlg.update_requested.connect(lambda: _download_in_thread(dlg))
            dlg.exec_()

        def _download_in_thread(dlg):
            import threading
            from license.auto_updater import DownloadProgress

            def _run():
                def _cb(p: DownloadProgress):
                    # Qt signal proxy via QTimer
                    from PyQt5.QtCore import QMetaObject, Qt
                    pct = p.percent
                    msg = f"Downloading… {pct:.0f}%" if not p.done else "Installing…"
                    if p.error:
                        msg = f"Error: {p.error}"
                    QMetaObject.invokeMethod(
                        dlg, "set_progress",
                        Qt.QueuedConnection,
                    )

                auto_updater.download_and_install(update_info, _cb)

            threading.Thread(target=_run, daemon=True, name="OptionalUpdate").start()

        banner.update_requested.connect(_start_update)
        banner.dismissed.connect(banner.deleteLater)

        # Insert at top of central widget's layout
        central = window.centralWidget()
        if central:
            layout = central.layout()
            if layout:
                layout.insertWidget(0, banner)
                logger.info("Update banner injected into main window")

    except Exception as e:
        logger.warning(f"Could not inject update banner: {e}", exc_info=True)


def _inject_trial_banner(window: "TradingGUI") -> None:
    """
    If the active license is a trial, inject a TrialExpiryBanner at the top
    of the main window.  Clicking "Upgrade Now" opens the ActivationDialog
    directly on the "Activate License" tab.
    """
    try:
        from license.license_manager import license_manager, PLAN_TRIAL
        info = license_manager.get_local_info()
        if info.get("plan") != PLAN_TRIAL:
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
                # Reload the window title / status to reflect paid plan
                banner.hide()

        banner.upgrade_clicked.connect(_open_upgrade)
        banner.dismissed.connect(banner.deleteLater)

        central = window.centralWidget()
        if central and central.layout():
            central.layout().insertWidget(0, banner)
            logger.info(f"Trial expiry banner injected ({days} day(s) remaining)")

    except Exception as e:
        logger.warning(f"Could not inject trial banner: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    logger.info("=" * 60)
    logger.info("  Algo Trading Pro — starting up")
    logger.info("=" * 60)

    # ── Step 1: DB ────────────────────────────────────────────────────────────
    if not _run_db_init():
        from PyQt5.QtWidgets import QApplication, QMessageBox
        _app = _qt_app()
        QMessageBox.critical(
            None, "Database Error",
            "Database initialisation failed.\n"
            "Check the logs/ folder for details.\n\n"
            "The application will now exit."
        )
        return 1

    # ── Step 2: Qt app object ─────────────────────────────────────────────────
    qt_app = _qt_app()
    _apply_dark_palette(qt_app)

    # ── Step 3: License ───────────────────────────────────────────────────────
    if not _run_license_gate(qt_app):
        logger.info("License gate rejected — exiting")
        return 1

    # ── Step 5: Main window ───────────────────────────────────────────────────
    exit_code = _launch_main_window(qt_app)
    logger.info(f"Application exited with code {exit_code}")
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logger.critical("Unhandled exception at top level", exc_info=True)
        sys.exit(1)