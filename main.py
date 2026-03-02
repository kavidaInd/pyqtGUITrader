# main.py (updated version with proper onboarding integration)
"""
Application entry point with splash screen and first-time onboarding.
"""

import logging
import logging.handlers
import os
import sys
import traceback
from typing import Optional

import PyQt5.QtCore
from PyQt5.QtWidgets import QMessageBox

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


# ── Deferred Qt import ──────────────────────────────────────────────────────
def _qt_app():
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
        dark.setColor(QPalette.Window, QColor("#0d1117"))
        dark.setColor(QPalette.WindowText, QColor("#e6edf3"))
        dark.setColor(QPalette.Base, QColor("#161b22"))
        dark.setColor(QPalette.AlternateBase, QColor("#21262d"))
        dark.setColor(QPalette.Text, QColor("#e6edf3"))
        dark.setColor(QPalette.Button, QColor("#21262d"))
        dark.setColor(QPalette.ButtonText, QColor("#e6edf3"))
        dark.setColor(QPalette.Highlight, QColor("#388bfd"))
        dark.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        app.setPalette(dark)
    except Exception as e:
        logger.warning(f"Could not apply dark palette: {e}")


# ── Splash Screen ──────────────────────────────────────────────────────────
def _show_splash():
    """Create and show the splash screen."""
    from gui.splash_screen import AnimatedSplashScreen
    splash = AnimatedSplashScreen("resources/logo.png")  # Update path as needed
    splash.show()
    splash.set_status("Initializing application...")
    splash.set_progress(0)
    return splash


def _update_splash(splash, status, progress):
    """Update splash screen status and progress."""
    if splash:
        splash.set_status(status)
        splash.set_progress(progress)
        # Process events to ensure UI updates
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()


# ── Database ───────────────────────────────────────────────────────────────
def _run_db_init(splash=None):
    """Initialise / migrate the SQLite database. Returns True on success."""
    try:
        _update_splash(splash, "Initializing database...", 10)
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


# ── State Manager ──────────────────────────────────────────────────────────
def _init_state_manager(splash=None):
    """
    Initialise the state manager and ensure the trade state singleton is ready.
    """
    try:
        _update_splash(splash, "Initializing state manager...", 20)
        from models.trade_state_manager import state_manager
        state = state_manager.get_state()
        logger.info(f"State manager initialised with state ID: {id(state)}")
        return True
    except Exception as e:
        logger.critical(f"State manager initialisation failed: {e}", exc_info=True)
        return False


# ── License Gate ───────────────────────────────────────────────────────────
def _run_license_gate(qt_app, splash=None):
    """
    Soft license check on startup.
    """
    _update_splash(splash, "Checking license...", 30)
    from license.license_manager import license_manager
    from license.activation_dialog import ActivationDialog
    from PyQt5.QtWidgets import QMessageBox, QDialog

    result = license_manager.verify_on_startup()
    logger.info(f"License check: {result}")

    if result.ok:
        if result.offline:
            logger.warning(f"Running in offline grace mode: {result.reason}")
        return True

    SOFT_REASONS = {"not_activated", "trial_expired", "expired"}
    if result.reason in SOFT_REASONS:
        logger.info(
            f"No active paid license ({result.reason!r}) — "
            "starting in free mode (paper/backtest only)"
        )
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


# ── Onboarding ─────────────────────────────────────────────────────────────
def _run_onboarding(splash=None):
    """
    Run the first-time setup wizard if this is the first launch.
    Returns True if onboarding was completed or skipped (not first time).
    """
    from gui.onboarding_popup import is_first_time, OnboardingWizard
    from PyQt5.QtWidgets import QDialog

    _update_splash(splash, "Checking first-time setup...", 35)

    # Check if this is first run
    if not is_first_time():
        logger.info("Not first time - skipping onboarding")
        return True

    logger.info("First-time launch detected - showing onboarding wizard")

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
        logger.info("Onboarding completed successfully")

        # Reload all settings to ensure they're fresh in memory
        _reload_all_settings()

        return True
    else:
        logger.warning("Onboarding cancelled by user")
        # Ask if user wants to exit or continue without setup
        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            None,
            "Continue without setup?",
            "You haven't completed the initial setup.\n\n"
            "You can continue with default settings, but some features may not work.\n\n"
            "Continue anyway?",
            QMessageBox.Yes | QMessageBox.No
        )
        return reply == QMessageBox.Yes


def _reload_all_settings():
    """Reload all settings from database after onboarding."""
    try:
        from gui.brokerage_settings.BrokerageSetting import BrokerageSetting
        from gui.daily_trade.DailyTradeSetting import DailyTradeSetting
        from gui.profit_loss.ProfitStoplossSetting import ProfitStoplossSetting
        from gui.trading_mode.TradingModeSetting import TradingModeSetting

        # Force reload all settings from database
        BrokerageSetting().load()
        DailyTradeSetting().load()
        ProfitStoplossSetting().load()
        TradingModeSetting().load()

        logger.info("All settings reloaded from database after onboarding")
    except Exception as e:
        logger.error(f"Failed to reload settings: {e}", exc_info=True)


# ── Main Window ────────────────────────────────────────────────────────────
# main.py (updated _launch_main_window function)

def _launch_main_window(qt_app, splash=None, update_info=None) -> int:
    """Create TradingGUI, inject optional update banner, enter event loop."""
    _update_splash(splash, "Loading main window...", 80)

    try:
        from TradingGUI import TradingGUI

        # Create the main window
        window = TradingGUI()

        # Inject optional update banner
        if update_info and update_info.available:
            _inject_update_banner(window, update_info)

        # Inject trial expiry banner
        _inject_trial_banner(window)

        # Update splash to ready
        _update_splash(splash, "Ready!", 100)

        # Process events to ensure splash updates
        qt_app.processEvents()

        # IMPORTANT: First show the main window, THEN finish the splash
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
        logger.critical(f"Failed to launch main window: {e}", exc_info=True)
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

            def _run():
                def _cb(p: DownloadProgress):
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

        central = window.centralWidget()
        if central:
            layout = central.layout()
            if layout:
                layout.insertWidget(0, banner)
                logger.info("Update banner injected into main window")

    except Exception as e:
        logger.warning(f"Could not inject update banner: {e}", exc_info=True)


def _inject_trial_banner(window):
    """Inject trial expiry banner if user is on trial."""
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

    try:
        # ── Step 1: Create Qt app and splash screen ──────────────────────────────
        qt_app = _qt_app()
        _apply_dark_palette(qt_app)

        splash = _show_splash()
        qt_app.processEvents()

        # ── Step 2: DB ───────────────────────────────────────────────────────────
        if not _run_db_init(splash):
            QMessageBox.critical(
                None, "Database Error",
                "Database initialisation failed.\n"
                "Check the logs/ folder for details.\n\n"
                "The application will now exit."
            )
            return 1

        # ── Step 3: State manager ─────────────────────────────────────────────────
        if not _init_state_manager(splash):
            QMessageBox.critical(
                None, "State Manager Error",
                "State manager initialisation failed.\n"
                "Check the logs/ folder for details.\n\n"
                "The application will now exit."
            )
            return 1

        # ── Step 4: License ───────────────────────────────────────────────────────
        if not _run_license_gate(qt_app, splash):
            logger.info("License gate rejected — exiting")
            return 1

        # ── Step 5: Onboarding (first-time setup) ─────────────────────────────────
        if not _run_onboarding(splash):
            logger.info("User chose to exit after onboarding")
            return 1

        # ── Step 6: Main window ───────────────────────────────────────────────────
        exit_code = _launch_main_window(qt_app, splash)
        logger.info(f"Application exited with code {exit_code}")
        return exit_code

    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        # Try to show error message if possible
        try:
            QMessageBox.critical(
                None,
                "Startup Error",
                f"An unexpected error occurred during startup:\n{e}\n\nPlease check the logs for details."
            )
        except:
            pass
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logger.critical("Unhandled exception at top level", exc_info=True)
        sys.exit(1)