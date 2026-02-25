#!/usr/bin/env python3
# PYQT: New entry point for PyQt5 application
import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

from TradingGUI import TradingGUI

# Rule 4: Structured logging - setup at module level
logger = logging.getLogger(__name__)


def setup_logging():
    """Rule 4: Configure comprehensive logging for the entire application"""
    try:
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(log_dir, exist_ok=True)

        # Create formatter with detailed information
        formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s.%(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Main application log - rotating file handler (10MB per file, keep 10 backups)
        main_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'trading_app.log'),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
        main_handler.setLevel(logging.DEBUG)
        main_handler.setFormatter(formatter)

        # Error log - separate file for errors only
        error_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'errors.log'),
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)

        # Console handler for development (warnings and above)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)

        # Crash log - for unhandled exceptions
        crash_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'crash.log'),
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        crash_handler.setLevel(logging.CRITICAL)
        crash_handler.setFormatter(formatter)

        # Get root logger and configure
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Remove any existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Add our handlers
        root_logger.addHandler(main_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(crash_handler)

        # Log startup
        logger.info("=" * 60)
        logger.info(f"Algo Trading Dashboard starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Log directory: {log_dir}")
        logger.info("=" * 60)

        return True

    except Exception as e:
        # Fallback to basic logging if setup fails
        print(f"CRITICAL: Failed to setup logging: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

        # Basic console logging as fallback
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)s | %(message)s'
        )
        return False


def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Rule 1: Global exception handler for unhandled exceptions.
    This prevents crashes and logs all unhandled exceptions.
    """
    # Ignore keyboard interrupt
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Log the exception
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

    # Also write to stderr
    print("FATAL: Unhandled exception occurred!", file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)

    # Show error dialog if QApplication exists
    try:
        app = QApplication.instance()
        if app and isinstance(app, QApplication):
            error_msg = f"Fatal Error: {exc_type.__name__}: {exc_value}\n\nCheck logs for details."
            QMessageBox.critical(None, "Application Error", error_msg)
    except Exception as e:
        logger.error(f"Failed to show error dialog: {e}", exc_info=True)


def main():
    """
    Main entry point with comprehensive error handling.
    """
    # Rule 1: Wrap entire main in try/except
    try:
        # Setup logging first
        setup_logging()

        # Rule 1: Set global exception hook
        sys.excepthook = handle_exception

        logger.info("Starting PyQt5 application...")

        # PYQT: High-DPI support - preserve exact attributes
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        # Create application
        app = QApplication(sys.argv)
        app.setApplicationName("Algo Trading Dashboard")

        # Rule 7: UI Responsiveness - ensure app processes events
        app.processEvents()

        logger.info("QApplication created successfully")

        # Create and show main window
        try:
            window = TradingGUI()
            window.show()
            logger.info("Main window created and shown")

            # Process events again to ensure window renders
            app.processEvents()

        except Exception as e:
            logger.critical(f"Failed to create main window: {e}", exc_info=True)
            QMessageBox.critical(
                None,
                "Initialization Error",
                f"Failed to create main window:\n{e}\n\nPlease check the logs for details."
            )
            return 1

        # Rule 8: Graceful shutdown handling
        exit_code = 0
        try:
            logger.info("Entering Qt event loop")
            exit_code = app.exec_()
            logger.info(f"Qt event loop exited with code {exit_code}")

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            # Allow Qt to handle cleanup
            app.quit()
            exit_code = 0

        except Exception as e:
            logger.critical(f"Error in event loop: {e}", exc_info=True)
            exit_code = 1

        finally:
            # Cleanup logging
            logger.info("Application shutting down")
            logging.shutdown()

        return exit_code

    except Exception as e:
        # Last resort error handling
        print(f"FATAL ERROR IN MAIN: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

        # Try to show error dialog if possible
        try:
            app = QApplication.instance()
            if app:
                QMessageBox.critical(
                    None,
                    "Fatal Error",
                    f"Fatal error during startup:\n{e}\n\nApplication will exit."
                )
        except:
            pass

        return 1


def cleanup():
    """
    Rule 8: Global cleanup function.
    Ensures resources are properly released on exit.
    """
    try:
        logger.info("Performing global cleanup...")

        # Get QApplication instance
        app = QApplication.instance()
        if app:
            # Process any pending events
            app.processEvents()

            # Close all windows
            for widget in app.topLevelWidgets():
                try:
                    widget.close()
                except Exception as e:
                    logger.warning(f"Error closing widget {widget}: {e}")

            # Process close events
            app.processEvents()

        logger.info("Global cleanup completed")

    except Exception as e:
        logger.error(f"Error during global cleanup: {e}", exc_info=True)


# Rule 8: Register cleanup on exit
import atexit

atexit.register(cleanup)

if __name__ == "__main__":
    """
    Entry point with minimal code to ensure errors are caught.
    """
    exit_code = 1
    try:
        exit_code = main()
    except Exception as e:
        # Absolute last resort error handling
        print(f"CRITICAL UNHANDLED EXCEPTION: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        exit_code = 1
    finally:
        sys.exit(exit_code)