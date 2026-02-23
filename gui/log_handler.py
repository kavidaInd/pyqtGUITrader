# PYQT: Qt-compatible log handler with color support
import logging
import logging.handlers
import traceback
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import QTextEdit, QPlainTextEdit

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class QtLogSignaller(QObject):
    """
    # PYQT: Signal must live on a QObject so it can cross thread boundaries safely
    """
    log_message = pyqtSignal(str, int)  # Now emits (message, levelno)
    log_batch = pyqtSignal(list)  # For batched messages with levels

    def __init__(self, parent=None):
        # Rule 2: Safe defaults
        try:
            super().__init__(parent)
        except Exception as e:
            logger.error(f"[QtLogSignaller.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)


class ColoredLogWidget(QTextEdit):
    """
    A QTextEdit widget specifically designed for colored log display.
    """

    # Define colors for different log levels (GitHub Dark theme)
    LEVEL_COLORS = {
        logging.DEBUG: QColor("#8b949e"),  # Gray
        logging.INFO: QColor("#e6edf3"),  # White
        logging.WARNING: QColor("#f0883e"),  # Orange
        logging.ERROR: QColor("#f85149"),  # Red
        logging.CRITICAL: QColor("#ff7b72"),  # Light Red
    }

    # Define level icons
    LEVEL_ICONS = {
        logging.DEBUG: "🔍",
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔥",
    }

    def __init__(self, parent=None, max_lines: int = 1000, show_icons: bool = True):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setReadOnly(True)
            self.max_lines = max_lines
            self.show_icons = show_icons

            # EXACT stylesheet preservation
            self.setStyleSheet("""
                QTextEdit {
                    background: #0d1117;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 10pt;
                }
            """)

            # Initialize document
            self._line_count = 0
            self._batch_update_in_progress = False

            logger.debug("ColoredLogWidget initialized")

        except Exception as e:
            logger.error(f"[ColoredLogWidget.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self.setReadOnly(True)
            self.max_lines = max_lines
            self.show_icons = show_icons

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.max_lines = 1000
        self.show_icons = True
        self._line_count = 0
        self._batch_update_in_progress = False

    def append_colored(self, text: str, level: int = logging.INFO):
        """
        Append colored text to the log widget with line limit.

        Args:
            text: The message to append
            level: Log level (determines color)
        """
        try:
            # Rule 6: Input validation
            if text is None:
                logger.warning("append_colored called with None text")
                text = ""

            if not isinstance(level, int):
                logger.warning(f"append_colored called with non-int level: {level}")
                level = logging.INFO

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
            color = self.LEVEL_COLORS.get(level, QColor("#e6edf3"))
            if color:
                format.setForeground(color)

            # Add level icon if enabled
            if self.show_icons:
                icon = self.LEVEL_ICONS.get(level, "")
                if icon:
                    display_text = f"{icon} {text}"
                else:
                    display_text = text
            else:
                display_text = text

            # Insert the text
            cursor.insertText(display_text + "\n", format)

            # Scroll to bottom
            self.ensureCursorVisible()

        except Exception as e:
            logger.error(f"[ColoredLogWidget.append_colored] Failed: {e}", exc_info=True)
            # Fallback to plain text
            try:
                super().append(str(text))
            except Exception:
                pass

    def append_batch(self, messages: List[Tuple[str, int]]):
        """
        Append multiple messages at once (more efficient for rate limiting).

        Args:
            messages: List of tuples (text, level)
        """
        try:
            # Rule 6: Input validation
            if not messages:
                return

            if not isinstance(messages, list):
                logger.warning(f"append_batch called with non-list: {type(messages)}")
                return

            self._batch_update_in_progress = True

            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.End)

            for text, level in messages:
                try:
                    # Validate message
                    if text is None:
                        continue

                    if not isinstance(level, int):
                        level = logging.INFO

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
                    color = self.LEVEL_COLORS.get(level, QColor("#e6edf3"))
                    if color:
                        format.setForeground(color)

                    if self.show_icons:
                        icon = self.LEVEL_ICONS.get(level, "")
                        if icon:
                            display_text = f"{icon} {text}"
                        else:
                            display_text = text
                    else:
                        display_text = text

                    cursor.insertText(display_text + "\n", format)

                except Exception as e:
                    logger.warning(f"Failed to append batch item: {e}")
                    continue

            self.ensureCursorVisible()

        except Exception as e:
            logger.error(f"[ColoredLogWidget.append_batch] Failed: {e}", exc_info=True)
        finally:
            self._batch_update_in_progress = False

    def clear(self):
        """Clear all text"""
        try:
            super().clear()
            self._line_count = 0
            logger.debug("Log widget cleared")
        except Exception as e:
            logger.error(f"[ColoredLogWidget.clear] Failed: {e}", exc_info=True)


class QtLogHandler(logging.Handler):
    """
    # PYQT: Replaces the Tkinter TextHandler with color support.
    # Emits log records as Qt signals so the main thread can append them to the log widget.
    """

    DEFAULT_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    def __init__(self, log_widget: Optional[ColoredLogWidget] = None,
                 level=logging.NOTSET,
                 rate_limit_ms: Optional[int] = None,
                 show_level_names: bool = True):
        """
        Initialize the handler.

        Args:
            log_widget: Optional ColoredLogWidget to connect to
            level: Logging level
            rate_limit_ms: Optional rate limiting in milliseconds
            show_level_names: Whether to include level names in the message
        """
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(level)

            self.show_level_names = show_level_names
            self.signaller = QtLogSignaller()

            # Set default formatter
            if not self.formatter:
                self.setFormatter(logging.Formatter(
                    self.DEFAULT_FORMAT,
                    self.DEFAULT_DATE_FORMAT
                ))

            # Connect to log widget if provided
            if log_widget:
                self.connect_log_widget(log_widget)

            # Rate limiting support
            self._rate_limit_ms = rate_limit_ms
            self._pending_messages: List[Tuple[str, int]] = []  # Now stores (message, level)
            self._timer = None
            self._setup_rate_limiting()

            logger.debug("QtLogHandler initialized")

        except Exception as e:
            logger.error(f"[QtLogHandler.__init__] Failed: {e}", exc_info=True)
            super().__init__(level)
            self.show_level_names = show_level_names
            self.signaller = QtLogSignaller()
            self._pending_messages = []

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.show_level_names = True
        self.signaller = None
        self._rate_limit_ms = None
        self._pending_messages = []
        self._timer = None
        self._closed = False

    def connect_log_widget(self, log_widget: ColoredLogWidget):
        """Connect this handler to a ColoredLogWidget"""
        try:
            if log_widget is None:
                logger.warning("connect_log_widget called with None widget")
                return

            if self.signaller:
                self.signaller.log_message.connect(log_widget.append_colored)
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

            if self._pending_messages and self.signaller:
                # Emit as batch
                self.signaller.log_batch.emit(self._pending_messages)
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

            # Emit with or without rate limiting
            if self._rate_limit_ms and self._timer and self._timer.isActive():
                # Rate limiting enabled - add to pending with level
                self._pending_messages.append((msg, record.levelno))

                # Prevent memory leak - limit pending queue size
                if len(self._pending_messages) > 1000:
                    logger.warning("Pending message queue too large, forcing flush")
                    self._flush_pending()
            else:
                # Direct emission with level
                if self.signaller:
                    self.signaller.log_message.emit(msg, record.levelno)

        except Exception as e:
            logger.error(f"[QtLogHandler.emit] Failed: {e}", exc_info=True)
            self.handleError(record)

    def close(self):
        """Clean up resources"""
        try:
            self._closed = True

            if self._timer:
                try:
                    self._timer.stop()
                    self._timer = None
                except Exception as e:
                    logger.warning(f"Error stopping timer: {e}")

            # Flush any pending messages
            self._flush_pending()

            super().close()
            logger.debug("QtLogHandler closed")

        except Exception as e:
            logger.error(f"[QtLogHandler.close] Failed: {e}", exc_info=True)

    def set_rate_limit(self, ms: Optional[int]):
        """Set or disable rate limiting"""
        try:
            self._rate_limit_ms = ms

            if ms and ms > 0:
                if not self._timer:
                    self._timer = QTimer()
                    self._timer.timeout.connect(self._flush_pending)
                    self._timer.start(ms)
                    logger.debug(f"Rate limit set to {ms}ms")
                else:
                    self._timer.setInterval(ms)
                    if not self._timer.isActive():
                        self._timer.start()
            elif not ms and self._timer:
                self._timer.stop()
                self._timer = None
                self._flush_pending()
                logger.debug("Rate limiting disabled")

        except Exception as e:
            logger.error(f"[QtLogHandler.set_rate_limit] Failed: {e}", exc_info=True)


class SimpleLogHandler(logging.Handler):
    """
    A simpler handler that just emits the message with level.
    Useful if you don't need the full ColoredLogWidget.
    """

    def __init__(self, log_widget, level=logging.NOTSET):
        # Rule 2: Safe defaults
        self._safe_defaults_init()

        try:
            super().__init__(level)
            self.log_widget = log_widget
            logger.debug("SimpleLogHandler initialized")
        except Exception as e:
            logger.error(f"[SimpleLogHandler.__init__] Failed: {e}", exc_info=True)
            super().__init__(level)
            self.log_widget = log_widget

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.log_widget = None

    def emit(self, record):
        try:
            if self.log_widget is None:
                logger.warning("SimpleLogHandler: log_widget is None")
                return

            if record is None:
                logger.warning("emit called with None record")
                return

            msg = self.format(record)
            self.log_widget.append_colored(msg, record.levelno)

        except Exception as e:
            logger.error(f"[SimpleLogHandler.emit] Failed: {e}", exc_info=True)
            self.handleError(record)


# Convenience function to set up logging
def setup_colored_logging(log_widget: ColoredLogWidget,
                          level=logging.INFO,
                          rate_limit_ms: Optional[int] = None,
                          clear_existing: bool = True) -> Optional[QtLogHandler]:
    """
    Set up colored logging with a log widget.

    Args:
        log_widget: ColoredLogWidget instance
        level: Logging level
        rate_limit_ms: Optional rate limiting
        clear_existing: Whether to remove existing handlers

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
            rate_limit_ms=rate_limit_ms
        )

        # Add to root logger
        logging.getLogger().addHandler(handler)

        logger.info("Colored logging setup completed")
        return handler

    except Exception as e:
        logger.error(f"[setup_colored_logging] Failed: {e}", exc_info=True)
        return None


class ColoredPlainTextWidget(QPlainTextEdit):
    """
    A QPlainTextEdit widget with color support (has setMaximumBlockCount).
    """

    LEVEL_COLORS = {
        logging.DEBUG: "#8b949e",  # Gray
        logging.INFO: "#e6edf3",  # White
        logging.WARNING: "#f0883e",  # Orange
        logging.ERROR: "#f85149",  # Red
        logging.CRITICAL: "#ff7b72",  # Light Red
    }

    LEVEL_ICONS = {
        logging.DEBUG: "🔍",
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔥",
    }

    def __init__(self, parent=None, max_lines: int = 1000, show_icons: bool = True):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setReadOnly(True)
            self.setMaximumBlockCount(max_lines)
            self.show_icons = show_icons

            # EXACT stylesheet preservation
            self.setStyleSheet("""
                QPlainTextEdit {
                    background: #0d1117;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 10pt;
                }
            """)

            logger.debug("ColoredPlainTextWidget initialized")

        except Exception as e:
            logger.error(f"[ColoredPlainTextWidget.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self.setReadOnly(True)
            self.setMaximumBlockCount(max_lines)
            self.show_icons = show_icons

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.show_icons = True

    def append_colored(self, text: str, level: int = logging.INFO):
        """Append colored text"""
        try:
            # Rule 6: Input validation
            if text is None:
                logger.warning("append_colored called with None text")
                text = ""

            if not isinstance(level, int):
                logger.warning(f"append_colored called with non-int level: {level}")
                level = logging.INFO

            color = self.LEVEL_COLORS.get(level, "#e6edf3")
            icon = self.LEVEL_ICONS.get(level, "") if self.show_icons else ""

            if icon:
                display_text = f"{icon} {text}"
            else:
                display_text = text

            # Escape HTML special characters to prevent injection
            import html
            safe_text = html.escape(display_text)

            # Use HTML for coloring
            html_text = f'<span style="color: {color};">{safe_text}</span><br>'
            self.appendHtml(html_text)

        except Exception as e:
            logger.error(f"[ColoredPlainTextWidget.append_colored] Failed: {e}", exc_info=True)
            # Fallback to plain text
            try:
                self.appendPlainText(str(text))
            except Exception:
                pass

    def append_batch(self, messages: List[Tuple[str, int]]):
        """Append multiple messages"""
        try:
            # Rule 6: Input validation
            if not messages:
                return

            if not isinstance(messages, list):
                logger.warning(f"append_batch called with non-list: {type(messages)}")
                return

            html = ""
            import html as html_escape

            for text, level in messages:
                try:
                    if text is None:
                        continue

                    if not isinstance(level, int):
                        level = logging.INFO

                    color = self.LEVEL_COLORS.get(level, "#e6edf3")
                    icon = self.LEVEL_ICONS.get(level, "") if self.show_icons else ""

                    if icon:
                        display_text = f"{icon} {text}"
                    else:
                        display_text = text

                    safe_text = html_escape.escape(display_text)
                    html += f'<span style="color: {color};">{safe_text}</span><br>'

                except Exception as e:
                    logger.warning(f"Failed to process batch item: {e}")
                    continue

            if html:
                self.appendHtml(html)

        except Exception as e:
            logger.error(f"[ColoredPlainTextWidget.append_batch] Failed: {e}", exc_info=True)