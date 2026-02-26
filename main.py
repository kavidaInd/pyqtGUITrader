#!/usr/bin/env python3
"""
Algo Trading Dashboard - Main Application Entry Point
=====================================================
PyQt5-based graphical user interface for algorithmic trading operations.

This module serves as the primary entry point for the trading application,
providing comprehensive error handling, logging infrastructure, database
initialization, and graceful shutdown management.

Key Features:
    - Multi-level logging with rotation and separation by severity
    - Global exception handling to prevent crashes
    - Automatic database verification and initialization
    - High-DPI display support for modern monitors
    - Graceful shutdown with resource cleanup
    - User-friendly error dialogs for critical failures

Architecture:
    The application follows a robust initialization sequence:
    1. Logging system setup
    2. Global exception handler installation
    3. Database verification and seeding
    4. Qt application creation with high-DPI support
    5. Main window instantiation and display
    6. Event loop execution with error handling
    7. Cleanup on exit

Author: Development Team
Version: 1.0.0
"""

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

# Import database installer
from db.db_installer import run_startup_check

# Rule 4: Structured logging - setup at module level
logger = logging.getLogger(__name__)


def setup_logging():
    """
    Configure comprehensive logging infrastructure for the entire application.

    Rule 4: Structured logging implementation with multiple handlers for
    different log levels and destinations.

    Creates a rotating file log system with:
        - Main application log (DEBUG level): All application events
        - Error log (ERROR level): Only errors and critical issues
        - Console output (WARNING level): Important events for development
        - Crash log (CRITICAL level): Fatal errors requiring investigation

    Log Format:
        timestamp | log-level | module.function:line | message

    Example:
        2024-01-15 14:30:45 | INFO     | main.setup_logging:42 | Logging initialized

    Returns:
        bool: True if logging setup successful, False if fallback to basic logging

    Note:
        If directory creation or file handlers fail, falls back to basic console
        logging to ensure log visibility.
    """
    try:
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(log_dir, exist_ok=True)

        # Create formatter with detailed information for forensic analysis
        formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s.%(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Main application log - rotating file handler (10MB per file, keep 10 backups)
        # Captures all DEBUG and above events for comprehensive auditing
        main_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'trading_app.log'),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10,  # Keep 10 rotated files
            encoding='utf-8'
        )
        main_handler.setLevel(logging.DEBUG)
        main_handler.setFormatter(formatter)

        # Error log - separate file for errors only
        # Facilitates quick error investigation without wading through debug logs
        error_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'errors.log'),
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=5,  # Keep 5 rotated files
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)

        # Console handler for development (warnings and above)
        # Provides real-time feedback during development and debugging
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)

        # Crash log - for unhandled exceptions
        # Dedicated file for critical failures requiring immediate attention
        crash_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'crash.log'),
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,  # Keep 3 rotated files
            encoding='utf-8'
        )
        crash_handler.setLevel(logging.CRITICAL)
        crash_handler.setFormatter(formatter)

        # Get root logger and configure
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Remove any existing handlers to avoid duplicate logging
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Add our configured handlers
        root_logger.addHandler(main_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(crash_handler)

        # Log startup banner with system information
        logger.info("=" * 60)
        logger.info(f"Algo Trading Dashboard starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Log directory: {log_dir}")
        logger.info("=" * 60)

        return True

    except Exception as e:
        # Fallback to basic logging if setup fails
        # Ensures some logging capability even in degraded mode
        print(f"CRITICAL: Failed to setup logging: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

        # Basic console logging as fallback
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)s | %(message)s'
        )
        return False


def initialize_database():
    """
    Perform comprehensive database initialization and verification.

    Checks database integrity on application startup, creates required tables
    if missing, and seeds default configuration data. Provides detailed
    feedback about the database state and any issues encountered.

    The initialization process:
        1. Verifies database connection and accessibility
        2. Checks for existence of all required tables
        3. Validates table schemas (column presence)
        4. Creates missing tables automatically
        5. Seeds default configuration values
        6. Reports detailed status for troubleshooting

    Returns:
        bool: True if database is ready for use, False if critical errors exist

    Note:
        On failure, displays user-friendly error dialog with specific details
        about missing tables or columns to aid troubleshooting.

    See Also:
        db.db_installer.run_startup_check() for implementation details
    """
    try:
        logger.info("=" * 60)
        logger.info("Checking database installation...")

        # Run the database installer which performs comprehensive checks
        result = run_startup_check()

        if result.ok:
            logger.info("✅ Database check passed successfully")
            if result.db_created:
                logger.info("   New database created with all tables")
            if result.tables_created:
                logger.info(f"   Tables created: {', '.join(result.tables_created)}")
            if result.warnings:
                for warning in result.warnings:
                    logger.warning(f"   ⚠ {warning}")
            return True
        else:
            logger.error("❌ Database check FAILED")
            logger.error(f"   Errors: {result.errors}")
            logger.error(f"   Missing tables: {result.missing_tables}")
            if result.missing_columns:
                for table, cols in result.missing_columns.items():
                    logger.error(f"   Table '{table}' missing columns: {cols}")

            # Show user-friendly error dialog with actionable information
            error_msg = (
                f"Database initialization failed!\n\n"
                f"Missing tables: {', '.join(result.missing_tables) if result.missing_tables else 'None'}\n"
                f"Errors: {', '.join(result.errors) if result.errors else 'Unknown'}\n\n"
                f"Please check the logs and ensure the database is accessible."
            )
            QMessageBox.critical(None, "Database Error", error_msg)

            return False

    except Exception as e:
        logger.critical(f"Database initialization error: {e}", exc_info=True)
        QMessageBox.critical(
            None,
            "Database Error",
            f"Failed to initialize database:\n{e}\n\nApplication will exit."
        )
        return False


def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Global exception handler for all unhandled exceptions.

    Rule 1: Comprehensive error handling - intercepts any exception not caught
    elsewhere, logs it comprehensively, and optionally displays to user.

    This hook is installed via sys.excepthook and catches exceptions that would
    otherwise crash the application or be lost to stderr.

    Args:
        exc_type: Type of the exception (e.g., ValueError, TypeError)
        exc_value: The exception instance with details
        exc_traceback: Traceback object for stack trace

    Behavior:
        - KeyboardInterrupt is passed through to allow normal termination
        - All other exceptions are logged with full traceback
        - If Qt application exists, shows user-friendly error dialog
        - Ensures no exception goes unreported

    Note:
        This is the last line of defense - exceptions caught here indicate
        bugs that should be fixed in normal code paths.
    """
    # Ignore keyboard interrupt to allow clean termination with Ctrl+C
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Log the exception with full context for debugging
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

    # Also write to stderr for immediate visibility
    print("FATAL: Unhandled exception occurred!", file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)

    # Show error dialog if QApplication exists (user-friendly notification)
    try:
        app = QApplication.instance()
        if app and isinstance(app, QApplication):
            error_msg = f"Fatal Error: {exc_type.__name__}: {exc_value}\n\nCheck logs for details."
            QMessageBox.critical(None, "Application Error", error_msg)
    except Exception as e:
        logger.error(f"Failed to show error dialog: {e}", exc_info=True)


def main():
    """
    Primary application entry point with comprehensive lifecycle management.

    Orchestrates the entire application startup, execution, and shutdown sequence:

    Phase 1 - Initialization:
        - Configure logging infrastructure
        - Install global exception handler
        - Verify database integrity

    Phase 2 - Qt Setup:
        - Configure high-DPI support for modern displays
        - Create QApplication instance
        - Process initial events for responsiveness

    Phase 3 - UI Creation:
        - Instantiate main TradingGUI window
        - Display window and ensure rendering
        - Process events to prevent UI freezes

    Phase 4 - Event Loop:
        - Enter Qt event loop (app.exec_())
        - Handle keyboard interrupts gracefully
        - Catch and log loop errors

    Phase 5 - Cleanup:
        - Log shutdown information
        - Call registered cleanup handlers
        - Return appropriate exit code

    Returns:
        int: Exit code (0 for success, 1 for errors)

    Rule 1: Wrapped in comprehensive try/except to catch any startup failures.
    Rule 7: Processes events at key points to ensure UI responsiveness.
    Rule 8: Implements graceful shutdown with proper resource cleanup.
    """
    # Rule 1: Wrap entire main in try/except to catch any initialization errors
    try:
        # Phase 1: Setup logging first - critical for debugging any subsequent failures
        setup_logging()

        # Rule 1: Set global exception hook to catch unhandled exceptions
        sys.excepthook = handle_exception

        logger.info("Starting PyQt5 application...")

        # ==================================================================
        # DATABASE INITIALIZATION - Run before anything else
        # Ensures data layer is ready before UI attempts to access it
        # ==================================================================
        if not initialize_database():
            logger.critical("Database initialization failed - exiting")
            return 1  # Exit with error code

        # Phase 2: Qt Application Setup
        # PYQT: High-DPI support - preserve exact attributes for proper scaling
        # These attributes ensure crisp display on high-resolution monitors
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        # Create application instance (required before any widgets)
        app = QApplication(sys.argv)
        app.setApplicationName("Algo Trading Dashboard")

        # Rule 7: UI Responsiveness - ensure app processes events
        # Process any queued events to prevent UI freezes during startup
        app.processEvents()

        logger.info("QApplication created successfully")

        # Phase 3: Create and display main window
        try:
            window = TradingGUI()
            window.show()
            logger.info("Main window created and shown")

            # Rule 7: Process events again to ensure window renders completely
            # This prevents the "white window" syndrome during startup
            app.processEvents()

        except Exception as e:
            logger.critical(f"Failed to create main window: {e}", exc_info=True)
            QMessageBox.critical(
                None,
                "Initialization Error",
                f"Failed to create main window:\n{e}\n\nPlease check the logs for details."
            )
            return 1

        # Phase 4: Enter Qt event loop (blocks until application exits)
        exit_code = 0
        try:
            logger.info("Entering Qt event loop")
            exit_code = app.exec_()  # Blocks here until app.quit() is called
            logger.info(f"Qt event loop exited with code {exit_code}")

        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            logger.info("Received keyboard interrupt")
            # Allow Qt to handle cleanup by quitting normally
            app.quit()
            exit_code = 0

        except Exception as e:
            # Catch any unexpected exceptions in the event loop
            logger.critical(f"Error in event loop: {e}", exc_info=True)
            exit_code = 1

        finally:
            # Phase 5: Cleanup
            logger.info("Application shutting down")
            logging.shutdown()  # Ensure all log messages are flushed

        return exit_code

    except Exception as e:
        # Last resort error handling for catastrophic failures
        print(f"FATAL ERROR IN MAIN: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

        # Try to show error dialog if possible (Qt may not be initialized)
        try:
            app = QApplication.instance()
            if app:
                QMessageBox.critical(
                    None,
                    "Fatal Error",
                    f"Fatal error during startup:\n{e}\n\nApplication will exit."
                )
        except:
            pass  # Nothing more we can do if even error dialog fails

        return 1


def cleanup():
    """
    Global cleanup function for resource release on application exit.

    Rule 8: Ensures all resources are properly released when the application
    terminates, preventing memory leaks and file handle exhaustion.

    Registered via atexit to run regardless of how the application exits
    (normal termination, exception, or signal).

    Cleanup operations:
        1. Process any pending Qt events to ensure clean state
        2. Close all top-level windows gracefully
        3. Allow windows to perform their own cleanup
        4. Process close events to ensure they're handled
        5. Log completion status

    Note:
        This runs after the Qt event loop has exited but before the Python
        interpreter shuts down.
    """
    try:
        logger.info("Performing global cleanup...")

        # Get QApplication instance (may be None if never created)
        app = QApplication.instance()
        if app:
            # Process any pending events to ensure clean state
            app.processEvents()

            # Close all top-level windows gracefully
            # This allows each widget to perform its own cleanup
            for widget in app.topLevelWidgets():
                try:
                    widget.close()  # Triggers closeEvent which can be overridden
                except Exception as e:
                    logger.warning(f"Error closing widget {widget}: {e}")

            # Process close events to ensure they're handled
            app.processEvents()

        logger.info("Global cleanup completed")

    except Exception as e:
        logger.error(f"Error during global cleanup: {e}", exc_info=True)


# Rule 8: Register cleanup function to run on interpreter exit
# This ensures cleanup happens even if main() exits unexpectedly
import atexit

atexit.register(cleanup)

if __name__ == "__main__":
    """
    Script entry point with minimal error handling wrapper.

    This guard ensures the main() function is only called when the script is
    executed directly, not when imported as a module.

    The minimal wrapper provides:
        - Final exception barrier around main()
        - Consistent exit code propagation
        - Absolute last-resort error logging

    Returns:
        Exit code to the operating system (0 for success, non-zero for errors)
    """
    exit_code = 1
    try:
        exit_code = main()
    except Exception as e:
        # Absolute last resort error handling
        # This should theoretically never be reached due to handlers in main()
        print(f"CRITICAL UNHANDLED EXCEPTION: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        exit_code = 1
    finally:
        # Always exit with appropriate code
        sys.exit(exit_code)