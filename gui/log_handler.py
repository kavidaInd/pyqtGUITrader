# PYQT: Qt-compatible log handler with color support
import logging
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import QTextEdit, QPlainTextEdit
from typing import Optional, Dict
import traceback


class QtLogSignaller(QObject):
    """
    # PYQT: Signal must live on a QObject so it can cross thread boundaries safely
    """
    log_message = pyqtSignal(str, int)  # Now emits (message, levelno)
    log_batch = pyqtSignal(list)  # For batched messages with levels


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
        super().__init__(parent)
        self.setReadOnly(True)
        self.max_lines = max_lines
        self.show_icons = show_icons
        self.setStyleSheet("""
            QTextEdit {
                background: #0d1117;
                color: #e6edf3;
                border: 1px solid #30363d;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10pt;
            }
        """)

    def append_colored(self, text: str, level: int = logging.INFO):
        """
        Append colored text to the log widget with line limit.

        Args:
            text: The message to append
            level: Log level (determines color)
        """
        # Check line limit
        if self.max_lines > 0:
            doc = self.document()
            if doc.lineCount() >= self.max_lines:
                # Remove first block (oldest line)
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.Start)
                cursor.select(QTextCursor.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()  # Remove the newline

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        # Create format for this message
        format = QTextCharFormat()
        format.setForeground(self.LEVEL_COLORS.get(level, QColor("#e6edf3")))

        # Add level icon if enabled
        if self.show_icons and level in self.LEVEL_ICONS:
            display_text = f"{self.LEVEL_ICONS[level]} {text}"
        else:
            display_text = text

        # Insert the text
        cursor.insertText(display_text + "\n", format)

        # Scroll to bottom
        self.ensureCursorVisible()

    def append_batch(self, messages: list):
        """
        Append multiple messages at once (more efficient for rate limiting).

        Args:
            messages: List of tuples (text, level)
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        for text, level in messages:
            # Check line limit periodically
            if self.max_lines > 0:
                doc = self.document()
                if doc.lineCount() >= self.max_lines:
                    # Remove oldest line
                    remove_cursor = self.textCursor()
                    remove_cursor.movePosition(QTextCursor.Start)
                    remove_cursor.select(QTextCursor.LineUnderCursor)
                    remove_cursor.removeSelectedText()
                    remove_cursor.deleteChar()

            format = QTextCharFormat()
            format.setForeground(self.LEVEL_COLORS.get(level, QColor("#e6edf3")))

            if self.show_icons and level in self.LEVEL_ICONS:
                display_text = f"{self.LEVEL_ICONS[level]} {text}"
            else:
                display_text = text

            cursor.insertText(display_text + "\n", format)

        self.ensureCursorVisible()

    def clear(self):
        """Clear all text"""
        super().clear()


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
        self._pending_messages = []  # Now stores (message, level)
        self._timer = None
        self._setup_rate_limiting()

    def connect_log_widget(self, log_widget: ColoredLogWidget):
        """Connect this handler to a ColoredLogWidget"""
        self.signaller.log_message.connect(log_widget.append_colored)
        self.signaller.log_batch.connect(log_widget.append_batch)

    def _setup_rate_limiting(self):
        """Set up rate limiting timer if enabled"""
        if self._rate_limit_ms:
            self._timer = QTimer()
            self._timer.timeout.connect(self._flush_pending)
            self._timer.start(self._rate_limit_ms)

    def _flush_pending(self):
        """Flush pending messages (for rate limiting)"""
        if self._pending_messages:
            # Emit as batch
            self.signaller.log_batch.emit(self._pending_messages)
            self._pending_messages = []

    def emit(self, record):
        """
        Emit a log record with level information.

        Args:
            record: LogRecord to emit
        """
        try:
            # Format the message
            msg = self.format(record)

            # Optionally add level name
            if self.show_level_names and not msg.startswith(record.levelname):
                msg = f"{record.levelname}: {msg}"

            # Emit with or without rate limiting
            if self._rate_limit_ms and self._timer:
                # Rate limiting enabled - add to pending with level
                self._pending_messages.append((msg, record.levelno))
            else:
                # Direct emission with level
                self.signaller.log_message.emit(msg, record.levelno)

        except Exception:
            self.handleError(record)

    def close(self):
        """Clean up resources"""
        if self._timer:
            self._timer.stop()
            self._timer = None
        # Flush any pending messages
        self._flush_pending()
        super().close()

    def set_rate_limit(self, ms: Optional[int]):
        """Set or disable rate limiting"""
        self._rate_limit_ms = ms
        if ms and not self._timer:
            self._timer = QTimer()
            self._timer.timeout.connect(self._flush_pending)
            self._timer.start(ms)
        elif not ms and self._timer:
            self._timer.stop()
            self._timer = None
            self._flush_pending()
        elif ms and self._timer:
            self._timer.setInterval(ms)


class SimpleLogHandler(logging.Handler):
    """
    A simpler handler that just emits the message with level.
    Useful if you don't need the full ColoredLogWidget.
    """

    def __init__(self, log_widget, level=logging.NOTSET):
        super().__init__(level)
        self.log_widget = log_widget

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_widget.append_colored(msg, record.levelno)
        except Exception:
            self.handleError(record)


# Convenience function to set up logging
def setup_colored_logging(log_widget: ColoredLogWidget,
                          level=logging.INFO,
                          rate_limit_ms: Optional[int] = None,
                          clear_existing: bool = True) -> QtLogHandler:
    """
    Set up colored logging with a log widget.

    Args:
        log_widget: ColoredLogWidget instance
        level: Logging level
        rate_limit_ms: Optional rate limiting
        clear_existing: Whether to remove existing handlers

    Returns:
        The created QtLogHandler instance
    """
    # Clear existing handlers if requested
    if clear_existing:
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    # Create and configure handler
    handler = QtLogHandler(
        log_widget=log_widget,
        level=level,
        rate_limit_ms=rate_limit_ms
    )

    # Add to root logger
    logging.getLogger().addHandler(handler)

    return handler


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
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(max_lines)
        self.show_icons = show_icons
        self.setStyleSheet("""
            QPlainTextEdit {
                background: #0d1117;
                color: #e6edf3;
                border: 1px solid #30363d;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10pt;
            }
        """)

    def append_colored(self, text: str, level: int = logging.INFO):
        """Append colored text"""
        color = self.LEVEL_COLORS.get(level, "#e6edf3")
        icon = self.LEVEL_ICONS.get(level, "") if self.show_icons else ""

        if icon:
            display_text = f"{icon} {text}"
        else:
            display_text = text

        # Use HTML for coloring
        html = f'<span style="color: {color};">{display_text}</span><br>'
        self.appendHtml(html)

    def append_batch(self, messages: list):
        """Append multiple messages"""
        html = ""
        for text, level in messages:
            color = self.LEVEL_COLORS.get(level, "#e6edf3")
            icon = self.LEVEL_ICONS.get(level, "") if self.show_icons else ""

            if icon:
                display_text = f"{icon} {text}"
            else:
                display_text = text

            html += f'<span style="color: {color};">{display_text}</span><br>'

        self.appendHtml(html)