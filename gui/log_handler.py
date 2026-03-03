"""
log_handler.py
==============
Qt-compatible log handler with color support for the trading dashboard.

This module provides:
- Colored log display widgets (QTextEdit and QPlainTextEdit based)
- Thread-safe log emission via Qt signals
- Rate limiting support
- Multiple log level colors (themed)
- Integration with the application's logging infrastructure

UPDATED: Fully integrated with ThemeManager for dynamic theme switching.
"""

import logging
import logging.handlers
import traceback
import html
import weakref
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import QTextEdit, QPlainTextEdit, QApplication

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class QtLogSignaller(QObject):
    """
    # PYQT: Signal must live on a QObject so it can cross thread boundaries safely

    This class acts as a bridge between the logging thread and the Qt main thread.
    It emits signals that can be safely received by widgets in the GUI thread.

    FIXED: Added proper cleanup and weak references to prevent RuntimeError during shutdown.
    """

    # Enhanced signals with more metadata
    log_message = pyqtSignal(str, int, str)  # (message, levelno, source)
    log_batch = pyqtSignal(list)  # List of (message, levelno, source) tuples
    log_cleared = pyqtSignal()  # Signal when log is cleared
    error_occurred = pyqtSignal(str)  # Signal for logging errors

    def __init__(self, parent=None):
        # Rule 2: Safe defaults
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self._source_name = "QtLogSignaller"
            self._deleted = False
            logger.debug("QtLogSignaller initialized")
        except Exception as e:
            logger.error(f"[QtLogSignaller.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self._source_name = "QtLogSignaller"
            self._deleted = False

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._source_name = "QtLogSignaller"
        self._deleted = False

    def __del__(self):
        """Mark as deleted when garbage collected"""
        try:
            self._deleted = True
        except Exception:
            pass

    def safe_emit_log_message(self, msg: str, levelno: int, source: str) -> bool:
        """
        Safely emit log message signal with deletion check.

        Returns:
            bool: True if emitted successfully, False if object is deleted
        """
        try:
            if self._deleted:
                return False
            self.log_message.emit(msg, levelno, source)
            return True
        except RuntimeError as e:
            # Object has been deleted in C++ layer
            if "wrapped C/C++ object" in str(e):
                self._deleted = True
                return False
            raise
        except Exception:
            return False

    def safe_emit_log_batch(self, messages: list) -> bool:
        """
        Safely emit log batch signal with deletion check.

        Returns:
            bool: True if emitted successfully, False if object is deleted
        """
        try:
            if self._deleted:
                return False
            self.log_batch.emit(messages)
            return True
        except RuntimeError as e:
            # Object has been deleted in C++ layer
            if "wrapped C/C++ object" in str(e):
                self._deleted = True
                return False
            raise
        except Exception:
            return False


class ColoredLogWidget(QTextEdit):
    """
    A QTextEdit widget specifically designed for colored log display.

    Features:
    - Color-coded log levels (themed)
    - Level icons for visual identification
    - Line limit to prevent memory issues
    - Batch updates for performance
    - HTML-safe rendering
    - Theme-aware colors
    """

    # Define level icons (static - not theme dependent)
    LEVEL_ICONS = {
        logging.DEBUG: "🔍",
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔥",
    }

    # Source icons for different parts of the application
    SOURCE_ICONS = {
        "state_manager": "📊",
        "trading_app": "🤖",
        "websocket": "🌐",
        "executor": "💰",
        "signal_engine": "🎯",
        "risk_manager": "⚠️",
        "notifier": "📢",
        "gui": "🖥️",
        "default": "📝",
    }

    def __init__(self, parent=None, max_lines: int = 1000, show_icons: bool = True, show_sources: bool = True):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setReadOnly(True)
            self.max_lines = max_lines
            self.show_icons = show_icons
            self.show_sources = show_sources

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            # Initialize document
            self._line_count = 0
            self._batch_update_in_progress = False
            self._source_colors = {}  # Cache for source colors
            self._error_count = 0
            self._warning_count = 0
            self._closed = False

            # Apply theme initially
            self.apply_theme()

            # Enable context menu
            self.setContextMenuPolicy(Qt.CustomContextMenu)
            self.customContextMenuRequested.connect(self._show_context_menu)

            logger.debug("ColoredLogWidget initialized")

        except Exception as e:
            logger.error(f"[ColoredLogWidget.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self.setReadOnly(True)
            self.max_lines = max_lines
            self.show_icons = show_icons
            self.show_sources = show_sources

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.max_lines = 1000
        self.show_icons = True
        self.show_sources = True
        self._line_count = 0
        self._batch_update_in_progress = False
        self._source_colors = {}
        self._error_count = 0
        self._warning_count = 0
        self._closed = False

    # =========================================================================
    # Shorthand properties for theme tokens
    # =========================================================================
    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the log widget.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Update stylesheet with current theme tokens
            self.setStyleSheet(f"""
                QTextEdit {{
                    background: {c.BG_MAIN};
                    color: {c.TEXT_MAIN};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    font-family: '{ty.FONT_MONO}';
                    font-size: {ty.SIZE_MONO}pt;
                }}
            """)

            # Refresh level colors dictionary
            self._refresh_level_colors()

            # Clear source color cache (will regenerate with new theme)
            self._source_colors.clear()

            logger.debug("[ColoredLogWidget.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[ColoredLogWidget.apply_theme] Failed: {e}", exc_info=True)

    def _refresh_level_colors(self) -> None:
        """Refresh level colors based on current theme"""
        c = self._c
        self.LEVEL_COLORS = {
            logging.DEBUG: QColor(c.TEXT_DIM),
            logging.INFO: QColor(c.TEXT_MAIN),
            logging.WARNING: QColor(c.YELLOW_BRIGHT),
            logging.ERROR: QColor(c.RED_BRIGHT),
            logging.CRITICAL: QColor(c.RED),
        }

    def closeEvent(self, event):
        """Handle widget close event"""
        self._closed = True
        super().closeEvent(event)

    def _show_context_menu(self, pos):
        """Show context menu with additional options"""
        try:
            if self._closed:
                return

            menu = self.createStandardContextMenu()

            # Add custom actions
            menu.addSeparator()

            clear_action = menu.addAction("Clear Log")
            clear_action.triggered.connect(self.clear)

            copy_stats_action = menu.addAction("Copy Statistics")
            copy_stats_action.triggered.connect(self._copy_statistics)

            menu.exec_(self.mapToGlobal(pos))

        except Exception as e:
            logger.error(f"[ColoredLogWidget._show_context_menu] Failed: {e}", exc_info=True)

    def _copy_statistics(self):
        """Copy log statistics to clipboard"""
        try:
            if self._closed:
                return

            stats = f"Log Statistics:\n"
            stats += f"Errors: {self._error_count}\n"
            stats += f"Warnings: {self._warning_count}\n"
            stats += f"Total Lines: {self._line_count}\n"

            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(stats)

        except Exception as e:
            logger.error(f"[ColoredLogWidget._copy_statistics] Failed: {e}", exc_info=True)

    def _get_source_color(self, source: str) -> QColor:
        """Get or generate a color for a source"""
        try:
            if source in self._source_colors:
                return self._source_colors[source]

            # Generate consistent color from source name
            import hashlib
            hash_obj = hashlib.md5(source.encode())
            hash_hex = hash_obj.hexdigest()[:6]

            # Ensure color is readable on current theme background
            r = int(hash_hex[0:2], 16)
            g = int(hash_hex[2:4], 16)
            b = int(hash_hex[4:6], 16)

            # Adjust brightness if too dark for current theme
            if theme_manager.is_dark():
                # For dark theme, ensure colors are bright enough
                if r + g + b < 300:
                    r = min(255, r + 100)
                    g = min(255, g + 100)
                    b = min(255, b + 100)
            else:
                # For light theme, ensure colors are not too bright
                if r + g + b > 600:
                    r = max(0, r - 100)
                    g = max(0, g - 100)
                    b = max(0, b - 100)

            color = QColor(r, g, b)
            self._source_colors[source] = color
            return color

        except Exception as e:
            logger.debug(f"Failed to generate source color: {e}")
            return QColor(self._c.TEXT_DIM)  # Default to text dim color

    def _get_source_icon(self, source: str) -> str:
        """Get icon for source"""
        try:
            if not source:
                return ""

            source_lower = source.lower()
            for key, icon in self.SOURCE_ICONS.items():
                if key in source_lower:
                    return icon
            return self.SOURCE_ICONS["default"]

        except Exception:
            return "📝"

    def append_colored(self, text: str, level: int = logging.INFO, source: str = ""):
        """
        Append colored text to the log widget with line limit.

        Args:
            text: The message to append
            level: Log level (determines color)
            source: Source of the log message (e.g., 'state_manager', 'trading_app')
        """
        try:
            # Skip if widget is closed
            if self._closed:
                return

            # Rule 6: Input validation
            if text is None:
                logger.warning("append_colored called with None text")
                text = ""

            if not isinstance(level, int):
                logger.warning(f"append_colored called with non-int level: {level}")
                level = logging.INFO

            # Ensure level colors are fresh
            if not hasattr(self, 'LEVEL_COLORS'):
                self._refresh_level_colors()

            # Update counters
            if level == logging.ERROR or level == logging.CRITICAL:
                self._error_count += 1
            elif level == logging.WARNING:
                self._warning_count += 1

            # Check line limit
            if self.max_lines > 0:
                try:
                    doc = self.document()
                    if doc and doc.lineCount() >= self.max_lines:
                        # Remove first block (oldest line)
                        cursor = self.textCursor()
                        cursor.movePosition(QTextCursor.Start)
                        cursor.select(QTextCursor.LineUnderCursor)
                        cursor.removeSelectedText()
                        cursor.deleteChar()  # Remove the newline
                except Exception as e:
                    logger.warning(f"Failed to enforce line limit: {e}")

            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.End)

            # Create format for this message
            format = QTextCharFormat()
            color = self.LEVEL_COLORS.get(level, QColor(self._c.TEXT_MAIN))
            if color:
                format.setForeground(color)

            # Build display text
            display_text = ""

            # Add source icon if enabled
            if self.show_sources and source:
                source_icon = self._get_source_icon(source)
                display_text += f"{source_icon} "

            # Add level icon if enabled
            if self.show_icons:
                icon = self.LEVEL_ICONS.get(level, "")
                if icon:
                    display_text += f"{icon} "

            display_text += text

            # Insert the text
            cursor.insertText(display_text + "\n", format)

            # Scroll to bottom
            self.ensureCursorVisible()
            self._line_count += 1

        except RuntimeError as e:
            # Widget might be deleted
            if "wrapped C/C++ object" in str(e):
                self._closed = True
            else:
                logger.error(f"[ColoredLogWidget.append_colored] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[ColoredLogWidget.append_colored] Failed: {e}", exc_info=True)
            # Fallback to plain text
            try:
                if not self._closed:
                    super().append(str(text))
            except Exception:
                pass

    def append_batch(self, messages: List[Tuple[str, int, str]]):
        """
        Append multiple messages at once (more efficient for rate limiting).

        Args:
            messages: List of tuples (text, level, source)
        """
        try:
            # Skip if widget is closed
            if self._closed:
                return

            # Rule 6: Input validation
            if not messages:
                return

            if not isinstance(messages, list):
                logger.warning(f"append_batch called with non-list: {type(messages)}")
                return

            # Ensure level colors are fresh
            if not hasattr(self, 'LEVEL_COLORS'):
                self._refresh_level_colors()

            self._batch_update_in_progress = True

            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.End)

            for item in messages:
                try:
                    # Handle both 2-tuple and 3-tuple formats for backward compatibility
                    if len(item) == 3:
                        text, level, source = item
                    else:
                        text, level = item
                        source = ""

                    # Validate message
                    if text is None:
                        continue

                    if not isinstance(level, int):
                        level = logging.INFO

                    # Update counters
                    if level == logging.ERROR or level == logging.CRITICAL:
                        self._error_count += 1
                    elif level == logging.WARNING:
                        self._warning_count += 1

                    # Check line limit periodically
                    if self.max_lines > 0:
                        doc = self.document()
                        if doc and doc.lineCount() >= self.max_lines:
                            # Remove oldest line
                            remove_cursor = self.textCursor()
                            remove_cursor.movePosition(QTextCursor.Start)
                            remove_cursor.select(QTextCursor.LineUnderCursor)
                            remove_cursor.removeSelectedText()
                            remove_cursor.deleteChar()

                    format = QTextCharFormat()
                    color = self.LEVEL_COLORS.get(level, QColor(self._c.TEXT_MAIN))
                    if color:
                        format.setForeground(color)

                    # Build display text
                    display_text = ""

                    # Add source icon if enabled
                    if self.show_sources and source:
                        source_icon = self._get_source_icon(source)
                        display_text += f"{source_icon} "

                    # Add level icon if enabled
                    if self.show_icons:
                        icon = self.LEVEL_ICONS.get(level, "")
                        if icon:
                            display_text += f"{icon} "

                    display_text += text

                    cursor.insertText(display_text + "\n", format)
                    self._line_count += 1

                except Exception as e:
                    logger.warning(f"Failed to append batch item: {e}")
                    continue

            self.ensureCursorVisible()

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closed = True
            else:
                logger.error(f"[ColoredLogWidget.append_batch] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[ColoredLogWidget.append_batch] Failed: {e}", exc_info=True)
        finally:
            self._batch_update_in_progress = False

    def clear(self):
        """Clear all text"""
        try:
            if self._closed:
                return

            super().clear()
            self._line_count = 0
            self._error_count = 0
            self._warning_count = 0
            logger.debug("Log widget cleared")
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closed = True
            else:
                logger.error(f"[ColoredLogWidget.clear] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[ColoredLogWidget.clear] Failed: {e}", exc_info=True)

    def get_statistics(self) -> Dict[str, int]:
        """Get log statistics"""
        if self._closed:
            return {'lines': 0, 'errors': 0, 'warnings': 0}
        return {
            'lines': self._line_count,
            'errors': self._error_count,
            'warnings': self._warning_count,
        }

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            self._closed = True
            self._source_colors.clear()
        except Exception as e:
            logger.error(f"[ColoredLogWidget.cleanup] Error: {e}")


class QtLogHandler(logging.Handler):
    """
    # PYQT: Replaces the Tkinter TextHandler with color support.
    # Emits log records as Qt signals so the main thread can append them to the log widget.

    Features:
    - Thread-safe signal emission
    - Rate limiting support
    - Source tracking for better organization
    - Batch processing for performance
    - Error recovery
    FIXED: Added safety checks for deleted Qt objects during shutdown.
    """

    DEFAULT_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    def __init__(self, log_widget: Optional[ColoredLogWidget] = None,
                 level=logging.NOTSET,
                 rate_limit_ms: Optional[int] = None,
                 show_level_names: bool = True,
                 track_source: bool = True):
        """
        Initialize the handler.

        Args:
            log_widget: Optional ColoredLogWidget to connect to
            level: Logging level
            rate_limit_ms: Optional rate limiting in milliseconds
            show_level_names: Whether to include level names in the message
            track_source: Whether to track source of log messages
        """
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(level)

            self.show_level_names = show_level_names
            self.track_source = track_source
            self.signaller = QtLogSignaller()

            # Set default formatter
            if not self.formatter:
                self.setFormatter(logging.Formatter(
                    self.DEFAULT_FORMAT,
                    self.DEFAULT_DATE_FORMAT
                ))

            # Connect to log widget if provided
            if log_widget is not None:
                self.connect_log_widget(log_widget)

            # Rate limiting support
            self._rate_limit_ms = rate_limit_ms
            self._pending_messages: List[Tuple[str, int, str]] = []  # (message, level, source)
            self._timer = None
            self._setup_rate_limiting()

            logger.debug("QtLogHandler initialized")

        except Exception as e:
            logger.error(f"[QtLogHandler.__init__] Failed: {e}", exc_info=True)
            super().__init__(level)
            self.show_level_names = show_level_names
            self.track_source = track_source
            self.signaller = QtLogSignaller()
            self._pending_messages = []

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.show_level_names = True
        self.track_source = True
        self.signaller = None
        self._rate_limit_ms = None
        self._pending_messages = []
        self._timer = None
        self._closed = False

    def connect_log_widget(self, log_widget):
        """Connect this handler to a log widget"""
        try:
            if log_widget is None:
                logger.warning("connect_log_widget called with None widget")
                return

            if self.signaller is not None:
                # Connect signals based on widget capabilities
                if hasattr(log_widget, 'append_colored'):
                    self.signaller.log_message.connect(log_widget.append_colored)

                if hasattr(log_widget, 'append_batch'):
                    self.signaller.log_batch.connect(log_widget.append_batch)

                logger.debug("Log widget connected")
            else:
                logger.error("Cannot connect: signaller is None")

        except Exception as e:
            logger.error(f"[QtLogHandler.connect_log_widget] Failed: {e}", exc_info=True)

    def _setup_rate_limiting(self):
        """Set up rate limiting timer if enabled"""
        try:
            if self._rate_limit_ms and self._rate_limit_ms > 0:
                self._timer = QTimer()
                self._timer.timeout.connect(self._flush_pending)
                self._timer.start(self._rate_limit_ms)
                logger.debug(f"Rate limiting enabled: {self._rate_limit_ms}ms")

        except Exception as e:
            logger.error(f"[QtLogHandler._setup_rate_limiting] Failed: {e}", exc_info=True)

    def _flush_pending(self):
        """Flush pending messages (for rate limiting)"""
        try:
            if self._closed:
                return

            if self._pending_messages and self.signaller is not None:
                # Emit as batch
                self.signaller.safe_emit_log_batch(self._pending_messages)
                self._pending_messages = []

        except Exception as e:
            logger.error(f"[QtLogHandler._flush_pending] Failed: {e}", exc_info=True)
            self._pending_messages = []  # Clear on error to prevent buildup

    def emit(self, record):
        """
        Emit a log record with level information.

        Args:
            record: LogRecord to emit
        """
        try:
            # Rule 6: Input validation
            if self._closed:
                return

            if record is None:
                logger.warning("emit called with None record")
                return

            # Format the message
            msg = self.format(record)

            # Optionally add level name
            if self.show_level_names and not msg.startswith(record.levelname):
                msg = f"{record.levelname}: {msg}"

            # Extract source information
            source = ""
            if self.track_source:
                # Try to get source from record
                if hasattr(record, 'source'):
                    source = record.source
                elif hasattr(record, 'name'):
                    source = record.name
                else:
                    # Parse from module name
                    module_parts = record.module.split('.')
                    if module_parts:
                        source = module_parts[0]

            # Emit with or without rate limiting
            if self._rate_limit_ms and self._timer and self._timer.isActive():
                # Rate limiting enabled - add to pending
                self._pending_messages.append((msg, record.levelno, source))

                # Prevent memory leak - limit pending queue size
                if len(self._pending_messages) > 1000:
                    logger.warning("Pending message queue too large, forcing flush")
                    self._flush_pending()
            else:
                # Direct emission with level and source
                if self.signaller is not None:
                    # Use safe emit method that checks for deleted objects
                    self.signaller.safe_emit_log_message(msg, record.levelno, source)

        except RuntimeError as e:
            # Check if it's the "deleted" error
            if "wrapped C/C++ object" in str(e):
                self._closed = True
                # Don't log this error as it's expected during shutdown
            else:
                logger.error(f"[QtLogHandler.emit] RuntimeError: {e}", exc_info=True)
                self.handleError(record)
        except Exception as e:
            logger.error(f"[QtLogHandler.emit] Failed: {e}", exc_info=True)
            self.handleError(record)

    def close(self):
        """Clean up resources - Rule 7"""
        try:
            self._closed = True

            if self._timer is not None:
                try:
                    self._timer.stop()
                    self._timer = None
                except Exception as e:
                    logger.warning(f"Error stopping timer: {e}")

            # Flush any pending messages
            self._flush_pending()

            # Disconnect signals
            if self.signaller is not None:
                try:
                    # Disconnect all signals to prevent further emissions
                    self.signaller.log_message.disconnect()
                    self.signaller.log_batch.disconnect()
                except Exception:
                    pass
                self.signaller = None

            super().close()
            logger.debug("QtLogHandler closed")

        except Exception as e:
            logger.error(f"[QtLogHandler.close] Failed: {e}", exc_info=True)

    def set_rate_limit(self, ms: Optional[int]):
        """Set or disable rate limiting"""
        try:
            if self._closed:
                return

            self._rate_limit_ms = ms

            if ms and ms > 0:
                if self._timer is None:
                    self._timer = QTimer()
                    self._timer.timeout.connect(self._flush_pending)
                    self._timer.start(ms)
                    logger.debug(f"Rate limit set to {ms}ms")
                else:
                    self._timer.setInterval(ms)
                    if not self._timer.isActive():
                        self._timer.start()
            elif not ms and self._timer is not None:
                self._timer.stop()
                self._timer = None
                self._flush_pending()
                logger.debug("Rate limiting disabled")

        except Exception as e:
            logger.error(f"[QtLogHandler.set_rate_limit] Failed: {e}", exc_info=True)


class SimpleLogHandler(logging.Handler):
    """
    A simpler handler that just emits the message with level.
    FIXED: Now properly handles ColoredLogWidget and ColoredPlainTextWidget.
    """

    def __init__(self, log_widget, level=logging.NOTSET):
        # Rule 2: Safe defaults
        self._safe_defaults_init()

        try:
            super().__init__(level)
            self.log_widget = log_widget
            self._closed = False
            logger.debug("SimpleLogHandler initialized")
        except Exception as e:
            logger.error(f"[SimpleLogHandler.__init__] Failed: {e}", exc_info=True)
            super().__init__(level)
            self.log_widget = log_widget
            self._closed = False

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.log_widget = None
        self._closed = False

    def emit(self, record):
        """Emit a log record to the widget"""
        try:
            # Rule 6: Input validation
            if self._closed or self.log_widget is None:
                return

            if record is None:
                logger.warning("emit called with None record")
                return

            msg = self.format(record)

            # FIXED: Check if widget has append_colored method and is not deleted
            if hasattr(self.log_widget, 'append_colored'):
                try:
                    self.log_widget.append_colored(msg, record.levelno)
                except RuntimeError as e:
                    if "wrapped C/C++ object" in str(e):
                        self._closed = True
                        self.log_widget = None
                    else:
                        raise
            else:
                # Fallback for widgets without color support
                try:
                    self.log_widget.appendPlainText(msg)
                except RuntimeError as e:
                    if "wrapped C/C++ object" in str(e):
                        self._closed = True
                        self.log_widget = None
                    else:
                        raise

        except Exception as e:
            logger.error(f"[SimpleLogHandler.emit] Failed: {e}", exc_info=True)
            self.handleError(record)

    def close(self):
        """Clean up resources - Rule 7"""
        try:
            self._closed = True
            self.log_widget = None
            super().close()
        except Exception as e:
            logger.error(f"[SimpleLogHandler.close] Failed: {e}", exc_info=True)


class ColoredPlainTextWidget(QPlainTextEdit):
    """
    A QPlainTextEdit widget with color support (has setMaximumBlockCount).

    Features:
    - HTML-based coloring
    - Maximum block count for memory management
    - Level icons and colors
    - Batch updates
    - Theme-aware colors
    """

    # Define level icons (static - not theme dependent)
    LEVEL_ICONS = {
        logging.DEBUG: "🔍",
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔥",
    }

    # Source icons for different parts of the application
    SOURCE_ICONS = {
        "state_manager": "📊",
        "trading_app": "🤖",
        "websocket": "🌐",
        "executor": "💰",
        "signal_engine": "🎯",
        "risk_manager": "⚠️",
        "notifier": "📢",
        "gui": "🖥️",
        "default": "📝",
    }

    def __init__(self, parent=None, max_lines: int = 1000, show_icons: bool = True, show_sources: bool = True):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setReadOnly(True)
            self.setMaximumBlockCount(max_lines)
            self.show_icons = show_icons
            self.show_sources = show_sources

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            # Statistics
            self._error_count = 0
            self._warning_count = 0
            self._closed = False

            # Apply theme initially
            self.apply_theme()

            # Enable context menu
            self.setContextMenuPolicy(Qt.CustomContextMenu)
            self.customContextMenuRequested.connect(self._show_context_menu)

            logger.debug("ColoredPlainTextWidget initialized")

        except Exception as e:
            logger.error(f"[ColoredPlainTextWidget.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self.setReadOnly(True)
            self.setMaximumBlockCount(max_lines)
            self.show_icons = show_icons
            self.show_sources = show_sources

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.show_icons = True
        self.show_sources = True
        self._error_count = 0
        self._warning_count = 0
        self._closed = False

    # =========================================================================
    # Shorthand properties for theme tokens
    # =========================================================================
    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the log widget.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Update stylesheet with current theme tokens
            self.setStyleSheet(f"""
                QPlainTextEdit {{
                    background: {c.BG_MAIN};
                    color: {c.TEXT_MAIN};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    font-family: '{ty.FONT_MONO}';
                    font-size: {ty.SIZE_MONO}pt;
                }}
            """)

            # Refresh level colors dictionary
            self._refresh_level_colors()

            logger.debug("[ColoredPlainTextWidget.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[ColoredPlainTextWidget.apply_theme] Failed: {e}", exc_info=True)

    def _refresh_level_colors(self) -> None:
        """Refresh level colors based on current theme"""
        c = self._c
        self.LEVEL_COLORS = {
            logging.DEBUG: c.TEXT_DIM,
            logging.INFO: c.TEXT_MAIN,
            logging.WARNING: c.YELLOW_BRIGHT,
            logging.ERROR: c.RED_BRIGHT,
            logging.CRITICAL: c.RED,
        }

    def closeEvent(self, event):
        """Handle widget close event"""
        self._closed = True
        super().closeEvent(event)

    def _show_context_menu(self, pos):
        """Show context menu with additional options"""
        try:
            if self._closed:
                return

            menu = self.createStandardContextMenu()

            menu.addSeparator()

            clear_action = menu.addAction("Clear Log")
            clear_action.triggered.connect(self.clear)

            copy_stats_action = menu.addAction("Copy Statistics")
            copy_stats_action.triggered.connect(self._copy_statistics)

            menu.exec_(self.mapToGlobal(pos))

        except Exception as e:
            logger.error(f"[ColoredPlainTextWidget._show_context_menu] Failed: {e}", exc_info=True)

    def _copy_statistics(self):
        """Copy log statistics to clipboard"""
        try:
            if self._closed:
                return

            stats = f"Log Statistics:\n"
            stats += f"Errors: {self._error_count}\n"
            stats += f"Warnings: {self._warning_count}\n"

            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(stats)

        except Exception as e:
            logger.error(f"[ColoredPlainTextWidget._copy_statistics] Failed: {e}", exc_info=True)

    def _get_source_icon(self, source: str) -> str:
        """Get icon for source"""
        try:
            if not source:
                return ""

            source_lower = source.lower()
            for key, icon in self.SOURCE_ICONS.items():
                if key in source_lower:
                    return icon
            return self.SOURCE_ICONS["default"]

        except Exception:
            return "📝"

    def append_colored(self, text: str, level: int = logging.INFO, source: str = ""):
        """Append colored text"""
        try:
            # Skip if widget is closed
            if self._closed:
                return

            # Rule 6: Input validation
            if text is None:
                logger.warning("append_colored called with None text")
                text = ""

            if not isinstance(level, int):
                logger.warning(f"append_colored called with non-int level: {level}")
                level = logging.INFO

            # Ensure level colors are fresh
            if not hasattr(self, 'LEVEL_COLORS'):
                self._refresh_level_colors()

            # Update counters
            if level == logging.ERROR or level == logging.CRITICAL:
                self._error_count += 1
            elif level == logging.WARNING:
                self._warning_count += 1

            color = self.LEVEL_COLORS.get(level, self._c.TEXT_MAIN)

            # Build display text
            display_text = ""

            # Add source icon if enabled
            if self.show_sources and source:
                source_icon = self._get_source_icon(source)
                display_text += f"{source_icon} "

            # Add level icon if enabled
            if self.show_icons:
                icon = self.LEVEL_ICONS.get(level, "")
                if icon:
                    display_text += f"{icon} "

            display_text += text

            # Escape HTML special characters to prevent injection
            safe_text = html.escape(display_text)

            # Use HTML for coloring
            html_text = f'<span style="color: {color};">{safe_text}</span><br>'
            self.appendHtml(html_text)

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closed = True
            else:
                logger.error(f"[ColoredPlainTextWidget.append_colored] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[ColoredPlainTextWidget.append_colored] Failed: {e}", exc_info=True)
            # Fallback to plain text
            try:
                if not self._closed:
                    self.appendPlainText(str(text))
            except Exception:
                pass

    def append_batch(self, messages: List[Tuple[str, int, str]]):
        """Append multiple messages"""
        try:
            # Skip if widget is closed
            if self._closed:
                return

            # Rule 6: Input validation
            if not messages:
                return

            if not isinstance(messages, list):
                logger.warning(f"append_batch called with non-list: {type(messages)}")
                return

            # Ensure level colors are fresh
            if not hasattr(self, 'LEVEL_COLORS'):
                self._refresh_level_colors()

            html_parts = []

            for item in messages:
                try:
                    # Handle both 2-tuple and 3-tuple formats
                    if len(item) == 3:
                        text, level, source = item
                    else:
                        text, level = item
                        source = ""

                    if text is None:
                        continue

                    if not isinstance(level, int):
                        level = logging.INFO

                    # Update counters
                    if level == logging.ERROR or level == logging.CRITICAL:
                        self._error_count += 1
                    elif level == logging.WARNING:
                        self._warning_count += 1

                    color = self.LEVEL_COLORS.get(level, self._c.TEXT_MAIN)

                    # Build display text
                    display_text = ""

                    # Add source icon if enabled
                    if self.show_sources and source:
                        source_icon = self._get_source_icon(source)
                        display_text += f"{source_icon} "

                    # Add level icon if enabled
                    if self.show_icons:
                        icon = self.LEVEL_ICONS.get(level, "")
                        if icon:
                            display_text += f"{icon} "

                    display_text += text

                    safe_text = html.escape(display_text)
                    html_parts.append(f'<span style="color: {color};">{safe_text}</span><br>')

                except Exception as e:
                    logger.warning(f"Failed to process batch item: {e}")
                    continue

            if html_parts:
                self.appendHtml("".join(html_parts))

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closed = True
            else:
                logger.error(f"[ColoredPlainTextWidget.append_batch] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[ColoredPlainTextWidget.append_batch] Failed: {e}", exc_info=True)

    def clear(self):
        """Clear all text"""
        try:
            if self._closed:
                return

            super().clear()
            self._error_count = 0
            self._warning_count = 0
            logger.debug("Plain text log widget cleared")
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closed = True
            else:
                logger.error(f"[ColoredPlainTextWidget.clear] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[ColoredPlainTextWidget.clear] Failed: {e}", exc_info=True)

    def get_statistics(self) -> Dict[str, int]:
        """Get log statistics"""
        if self._closed:
            return {'errors': 0, 'warnings': 0}
        return {
            'errors': self._error_count,
            'warnings': self._warning_count,
        }

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            self._closed = True
        except Exception as e:
            logger.error(f"[ColoredPlainTextWidget.cleanup] Error: {e}")


# Convenience function to set up logging
def setup_colored_logging(log_widget,
                          level=logging.INFO,
                          rate_limit_ms: Optional[int] = None,
                          clear_existing: bool = True,
                          track_source: bool = True) -> Optional[QtLogHandler]:
    """
    Set up colored logging with a log widget.

    Args:
        log_widget: ColoredLogWidget or ColoredPlainTextWidget instance
        level: Logging level
        rate_limit_ms: Optional rate limiting
        clear_existing: Whether to remove existing handlers
        track_source: Whether to track source of log messages

    Returns:
        The created QtLogHandler instance or None on failure
    """
    try:
        # Rule 6: Input validation
        if log_widget is None:
            logger.error("setup_colored_logging called with None log_widget")
            return None

        # Clear existing handlers if requested
        if clear_existing:
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                try:
                    root_logger.removeHandler(handler)
                    handler.close()
                except Exception as e:
                    logger.warning(f"Failed to remove handler: {e}")

        # Create and configure handler
        handler = QtLogHandler(
            log_widget=log_widget,
            level=level,
            rate_limit_ms=rate_limit_ms,
            track_source=track_source
        )

        # Add to root logger
        logging.getLogger().addHandler(handler)

        logger.info("Colored logging setup completed")
        return handler

    except Exception as e:
        logger.error(f"[setup_colored_logging] Failed: {e}", exc_info=True)
        return None