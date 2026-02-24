import logging
import logging.handlers
import traceback
from typing import Optional
from collections import deque

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox, QPushButton, QLabel, QApplication, \
    QHBoxLayout

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
                    font-family: Consolas, 'Courier New', monospace;
                    font-size: 10pt;
                    selection-background-color: #264f78;
                }
                QPushButton {
                    background: #21262d;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    border-radius: 5px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
                QPushButton:hover { background: #30363d; }
                QPushButton:pressed { background: #3d444d; }
                QLabel#statusLabel {
                    color: #8b949e;
                    font-size: 9pt;
                    padding: 4px;
                }
            """)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(10)

            # Status label for showing log count
            self.status_label = QLabel("📋 Log Viewer - Ready")
            self.status_label.setObjectName("statusLabel")
            layout.addWidget(self.status_label)

            # Log widget
            self.log_widget = QPlainTextEdit()
            self.log_widget.setReadOnly(True)
            self.log_widget.setMaximumBlockCount(10000)  # Increased from 5000
            self.log_widget.setLineWrapMode(QPlainTextEdit.NoWrap)  # Better for logs
            layout.addWidget(self.log_widget)

            # Button row
            button_layout = QHBoxLayout()

            self.clear_btn = QPushButton("🗑️ Clear Logs")
            self.clear_btn.clicked.connect(self.clear_logs)

            self.copy_btn = QPushButton("📋 Copy All")
            self.copy_btn.clicked.connect(self.copy_all_logs)

            close_btn = QPushButton("✕ Close")
            close_btn.clicked.connect(self.accept)

            button_layout.addWidget(self.clear_btn)
            button_layout.addWidget(self.copy_btn)
            button_layout.addStretch()
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

            # Initialize pending messages queue
            self.pending_messages = deque(maxlen=1000)
            self._initialized = True

            # Process any pending messages
            QTimer.singleShot(100, self._process_pending_messages)

            logger.info("LogPopup initialized successfully")

        except Exception as e:
            logger.critical(f"[LogPopup.__init__] Failed: {e}", exc_info=True)
            self._initialized = False
            # Still try to create basic dialog
            super().__init__(parent)
            self.setWindowTitle("Log Viewer - ERROR")
            self.setMinimumSize(400, 300)

            layout = QVBoxLayout(self)
            error_label = QLabel(f"Failed to initialize log viewer:\n{e}")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #f85149; padding: 20px;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.log_widget = None
        self.status_label = None
        self.clear_btn = None
        self.copy_btn = None
        self.pending_messages = deque(maxlen=1000)
        self._initialized = False
        self._message_count = 0

    def append_log(self, message: str):
        """Append a log message to the widget with improved error handling"""
        try:
            # Rule 6: Input validation
            if message is None:
                logger.debug("append_log called with None message")
                return

            if not isinstance(message, str):
                logger.debug(f"append_log called with non-string message: {type(message)}")
                message = str(message)

            # Strip message to prevent excessive logging
            message = message.strip()
            if not message:
                return

            # If widget is not ready, queue the message
            if self.log_widget is None or not self._initialized:
                self.pending_messages.append(message)
                logger.debug(f"Log widget not ready, queued message (queue size: {len(self.pending_messages)})")
                return

            # Update message count
            self._message_count += 1

            # Append the message
            try:
                self.log_widget.appendPlainText(message)
            except RuntimeError as e:
                # Widget might have been deleted
                logger.debug(f"Failed to append text (widget deleted): {e}")
                self.pending_messages.append(message)
                return
            except Exception as e:
                logger.error(f"Failed to append text: {e}", exc_info=True)
                return

            # Update status label periodically
            if self._message_count % 100 == 0 and self.status_label is not None:
                try:
                    block_count = self.log_widget.blockCount()
                    self.status_label.setText(f"📋 Log Viewer - {block_count} messages")
                except:
                    pass

            # Auto-scroll to bottom (but not too frequently)
            if self._message_count % 10 == 0:
                try:
                    sb = self.log_widget.verticalScrollBar()
                    if sb:
                        sb.setValue(sb.maximum())
                except Exception as e:
                    logger.debug(f"Failed to scroll: {e}")

        except Exception as e:
            logger.error(f"[LogPopup.append_log] Failed: {e}", exc_info=True)

    def _process_pending_messages(self):
        """Process any messages that were queued before initialization"""
        try:
            if not self.pending_messages or self.log_widget is None:
                return

            logger.debug(f"Processing {len(self.pending_messages)} pending messages")

            # Temporarily block signals to prevent UI freeze
            self.log_widget.blockSignals(True)

            count = 0
            while self.pending_messages and count < 500:  # Process in batches
                message = self.pending_messages.popleft()
                try:
                    self.log_widget.appendPlainText(message)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to process pending message: {e}")
                    break

            self.log_widget.blockSignals(False)

            # Update status
            if self.status_label is not None:
                block_count = self.log_widget.blockCount()
                self.status_label.setText(f"📋 Log Viewer - {block_count} messages")

            # Scroll to bottom
            try:
                sb = self.log_widget.verticalScrollBar()
                if sb:
                    sb.setValue(sb.maximum())
            except:
                pass

            # Schedule next batch if needed
            if self.pending_messages:
                QTimer.singleShot(50, self._process_pending_messages)

        except Exception as e:
            logger.error(f"[LogPopup._process_pending_messages] Failed: {e}", exc_info=True)

    def clear_logs(self):
        """Clear all logs"""
        try:
            if self.log_widget is not None:
                self.log_widget.clear()
                self._message_count = 0
                if self.status_label is not None:
                    self.status_label.setText("📋 Log Viewer - Cleared")
                logger.debug("Logs cleared")
        except Exception as e:
            logger.error(f"[LogPopup.clear_logs] Failed: {e}", exc_info=True)

    def copy_all_logs(self):
        """Copy all logs to clipboard"""
        try:
            if self.log_widget is not None:
                clipboard = QApplication.clipboard()
                clipboard.setText(self.log_widget.toPlainText())

                # Show temporary feedback
                if self.status_label is not None:
                    old_text = self.status_label.text()
                    self.status_label.setText("📋 Copied to clipboard!")
                    QTimer.singleShot(2000, lambda: self.status_label.setText(old_text))

                logger.debug("Logs copied to clipboard")
        except Exception as e:
            logger.error(f"[LogPopup.copy_all_logs] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info("[LogPopup] Starting cleanup")

            # Mark as not initialized to prevent further append attempts
            self._initialized = False

            # Clear pending messages
            self.pending_messages.clear()

            # Clear log widget
            if self.log_widget is not None:
                try:
                    self.log_widget.clear()
                except Exception as e:
                    logger.warning(f"Failed to clear log widget: {e}")

            # Clear references
            self.log_widget = None
            self.status_label = None
            self.clear_btn = None
            self.copy_btn = None

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

    def showEvent(self, event):
        """Handle show event"""
        try:
            super().showEvent(event)
            # Process pending messages when shown
            QTimer.singleShot(100, self._process_pending_messages)
        except Exception as e:
            logger.error(f"[LogPopup.showEvent] Failed: {e}", exc_info=True)