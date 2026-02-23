import logging
import logging.handlers
import traceback
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox, QPushButton

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class LogPopup(QDialog):
    """Popup window for displaying logs"""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setWindowTitle("Log Viewer")
            self.resize(1000, 700)
            self.setMinimumSize(800, 500)

            # Set window flags to make it a proper popup
            self.setWindowFlags(Qt.Window)

            # EXACT stylesheet preservation
            self.setStyleSheet("""
                QDialog { background: #0d1117; color: #e6edf3; }
                QPlainTextEdit { 
                    background: #0d1117; 
                    color: #58a6ff; 
                    border: 1px solid #30363d;
                    font-family: Consolas;
                    font-size: 10pt;
                }
                QPushButton {
                    background: #21262d;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    border-radius: 5px;
                    padding: 8px 16px;
                }
                QPushButton:hover { background: #30363d; }
            """)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(10)

            # Log widget
            self.log_widget = QPlainTextEdit()
            self.log_widget.setReadOnly(True)
            self.log_widget.setMaximumBlockCount(5000)
            layout.addWidget(self.log_widget)

            # Button row
            button_box = QDialogButtonBox()
            clear_btn = QPushButton("Clear Logs")
            clear_btn.clicked.connect(self.clear_logs)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)

            button_box.addButton(clear_btn, QDialogButtonBox.ActionRole)
            button_box.addButton(close_btn, QDialogButtonBox.AcceptRole)
            layout.addWidget(button_box)

            logger.info("LogPopup initialized")

        except Exception as e:
            logger.critical(f"[LogPopup.__init__] Failed: {e}", exc_info=True)
            # Still try to create basic dialog
            super().__init__(parent)
            self.setWindowTitle("Log Viewer - ERROR")
            self.setMinimumSize(400, 300)

            layout = QVBoxLayout(self)
            error_label = QPushButton(f"Failed to initialize log viewer:\n{e}")
            error_label.setEnabled(False)
            error_label.setStyleSheet("color: #f85149; padding: 20px;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.log_widget = None

    def append_log(self, message: str):
        """Append a log message to the widget"""
        try:
            # Rule 6: Input validation
            if message is None:
                logger.warning("append_log called with None message")
                return

            if not isinstance(message, str):
                logger.warning(f"append_log called with non-string message: {type(message)}")
                message = str(message)

            if self.log_widget is None:
                logger.warning("append_log called with None log_widget")
                return

            # Debug logging (commented out in original)
            # print(f"🟣 Popup.append_log: {message[:50]}...")  # Debug

            # Get current text count before adding
            try:
                before_count = self.log_widget.blockCount()
                # print(f"Before: {before_count} blocks")
            except Exception as e:
                logger.debug(f"Failed to get block count: {e}")
                before_count = 0

            # Append the message
            try:
                self.log_widget.appendPlainText(message)
            except Exception as e:
                logger.error(f"Failed to append text: {e}", exc_info=True)
                return

            # Check if it was added
            try:
                after_count = self.log_widget.blockCount()
                # print(f"After: {after_count} blocks, Added: {after_count - before_count}")
            except Exception as e:
                logger.debug(f"Failed to get after block count: {e}")

            # Force update
            try:
                self.log_widget.repaint()
            except Exception as e:
                logger.debug(f"Failed to repaint: {e}")

            # Auto-scroll to bottom
            try:
                sb = self.log_widget.verticalScrollBar()
                if sb:
                    sb.setValue(sb.maximum())
            except Exception as e:
                logger.debug(f"Failed to scroll: {e}")

        except Exception as e:
            logger.error(f"[LogPopup.append_log] Failed: {e}", exc_info=True)

    def clear_logs(self):
        """Clear all logs"""
        try:
            if self.log_widget:
                self.log_widget.clear()
                logger.debug("Logs cleared")
        except Exception as e:
            logger.error(f"[LogPopup.clear_logs] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info("[LogPopup] Starting cleanup")

            # Clear log widget
            if self.log_widget:
                try:
                    self.log_widget.clear()
                except Exception as e:
                    logger.warning(f"Failed to clear log widget: {e}")

            # Clear references
            self.log_widget = None

            logger.info("[LogPopup] Cleanup completed")

        except Exception as e:
            logger.error(f"[LogPopup.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup"""
        try:
            self.cleanup()
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[LogPopup.closeEvent] Failed: {e}", exc_info=True)
            super().closeEvent(event)

    def accept(self):
        """Handle accept (close button) with cleanup"""
        try:
            self.cleanup()
            super().accept()
        except Exception as e:
            logger.error(f"[LogPopup.accept] Failed: {e}", exc_info=True)
            super().accept()