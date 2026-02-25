import logging
import logging.handlers
import traceback
from typing import Optional
from collections import deque

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QPushButton, QLabel, QApplication, \
    QHBoxLayout, QCheckBox, QSpinBox, QGroupBox, QComboBox

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class LogViewerWidget(QPlainTextEdit):
    """High-performance log viewer with virtual scrolling and filtering capabilities"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(20000)  # Increased from 10000
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

        # Set monospace font for better log readability
        font = self.document().defaultFont()
        font.setFamily('Consolas, Courier New, monospace')
        font.setPointSize(9)
        self.document().setDefaultFont(font)

        # Enable custom context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def append_log_batch(self, messages):
        """Append multiple messages efficiently"""
        if not messages:
            return

        cursor = self.textCursor()
        cursor.movePosition(cursor.End)

        for msg in messages:
            cursor.insertText(msg + '\n')

        # Update view
        self.ensureCursorVisible()


class LogPopup(QDialog):
    """Popup window for displaying logs with enhanced features"""

    # Signal for filtered log messages
    log_filtered = pyqtSignal(str)

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setWindowTitle("Log Viewer")
            self.resize(1200, 800)
            self.setMinimumSize(800, 600)

            # Set window flags to make it a proper popup
            self.setWindowFlags(Qt.Window)

            # EXACT stylesheet preservation with enhancements
            self.setStyleSheet("""
                QDialog { 
                    background: #0d1117; 
                    color: #e6edf3; 
                }
                QPlainTextEdit { 
                    background: #0d1117; 
                    color: #e6edf3; 
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
                    min-width: 80px;
                }
                QPushButton:hover { 
                    background: #30363d; 
                }
                QPushButton:pressed { 
                    background: #3d444d; 
                }
                QPushButton:checked {
                    background: #1f6feb;
                    border: 1px solid #388bfd;
                }
                QPushButton#dangerBtn {
                    background: #da3633;
                }
                QPushButton#dangerBtn:hover {
                    background: #f85149;
                }
                QLabel#statusLabel {
                    color: #8b949e;
                    font-size: 9pt;
                    padding: 4px;
                    background: #161b22;
                    border-radius: 4px;
                }
                QGroupBox {
                    border: 1px solid #30363d;
                    border-radius: 5px;
                    margin-top: 10px;
                    font-weight: bold;
                    color: #e6edf3;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px 0 5px;
                }
                QCheckBox {
                    color: #e6edf3;
                    spacing: 5px;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                }
                QSpinBox, QComboBox {
                    background: #21262d;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    border-radius: 3px;
                    padding: 4px;
                    min-width: 60px;
                }
                QSpinBox::up-button, QSpinBox::down-button {
                    background: #30363d;
                    border: none;
                }
            """)

            # Initialize components
            self._init_ui()
            self._init_timers()
            self._init_filters()

            logger.info("LogPopup initialized successfully")

        except Exception as e:
            logger.critical(f"[LogPopup.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.log_widget = None
        self.status_label = None
        self.clear_btn = None
        self.copy_btn = None
        self.pause_btn = None
        self.filter_edit = None
        self.level_combo = None
        self.wrap_check = None
        self.max_lines_spin = None

        # Message handling
        self._message_queue = deque(maxlen=10000)
        self._filtered_queue = deque(maxlen=10000)
        self._initialized = False
        self._message_count = 0
        self._paused = False
        self._auto_scroll = True

        # Filtering
        self._filter_text = ""
        self._filter_level = "ALL"
        self._filter_regex = False
        self._case_sensitive = False

        # Timers
        self._batch_timer = None
        self._stats_timer = None

        # Level colors for syntax highlighting
        self._level_colors = {
            'DEBUG': '#8b949e',  # Gray
            'INFO': '#58a6ff',  # Blue
            'WARNING': '#d29922',  # Yellow
            'ERROR': '#f85149',  # Red
            'CRITICAL': '#ff7b72'  # Bright red
        }

    def _init_ui(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Top toolbar
        toolbar = self._create_toolbar()
        layout.addLayout(toolbar)

        # Status bar
        self.status_label = QLabel("📋 Log Viewer - Ready")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        # Log widget
        self.log_widget = LogViewerWidget()
        layout.addWidget(self.log_widget, 1)  # Give it stretch factor

        # Bottom button bar
        button_bar = self._create_button_bar()
        layout.addLayout(button_bar)

        self._initialized = True

    def _create_toolbar(self):
        """Create top toolbar with filters and controls"""
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        # Filter input
        from PyQt5.QtWidgets import QLineEdit
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("🔍 Filter logs...")
        self.filter_edit.setStyleSheet("""
            QLineEdit {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 6px;
                font-size: 10pt;
                min-width: 250px;
            }
            QLineEdit:focus {
                border: 1px solid #58a6ff;
            }
        """)
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.filter_edit)

        # Level filter
        self.level_combo = QComboBox()
        self.level_combo.addItems(['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        self.level_combo.setStyleSheet("""
            QComboBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 5px;
                min-width: 100px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #8b949e;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                selection-background-color: #1f6feb;
            }
        """)
        self.level_combo.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.level_combo)

        # Max lines spinbox
        toolbar.addWidget(QLabel("Max lines:"))
        self.max_lines_spin = QSpinBox()
        self.max_lines_spin.setRange(1000, 50000)
        self.max_lines_spin.setValue(20000)
        self.max_lines_spin.setSingleStep(1000)
        self.max_lines_spin.valueChanged.connect(self._on_max_lines_changed)
        toolbar.addWidget(self.max_lines_spin)

        # Word wrap checkbox
        self.wrap_check = QCheckBox("Wrap text")
        self.wrap_check.toggled.connect(self._on_wrap_toggled)
        toolbar.addWidget(self.wrap_check)

        toolbar.addStretch()

        return toolbar

    def _create_button_bar(self):
        """Create bottom button bar"""
        button_bar = QHBoxLayout()

        # Clear button
        self.clear_btn = QPushButton("🗑️ Clear")
        self.clear_btn.clicked.connect(self.clear_logs)
        button_bar.addWidget(self.clear_btn)

        # Pause/Resume button
        self.pause_btn = QPushButton("⏸️ Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._on_pause_toggled)
        button_bar.addWidget(self.pause_btn)

        # Copy buttons
        self.copy_btn = QPushButton("📋 Copy All")
        self.copy_btn.clicked.connect(self.copy_all_logs)
        button_bar.addWidget(self.copy_btn)

        self.copy_filtered_btn = QPushButton("🔍 Copy Filtered")
        self.copy_filtered_btn.clicked.connect(self.copy_filtered_logs)
        button_bar.addWidget(self.copy_filtered_btn)

        button_bar.addStretch()

        # Export button
        self.export_btn = QPushButton("💾 Export")
        self.export_btn.clicked.connect(self.export_logs)
        button_bar.addWidget(self.export_btn)

        # Close button
        close_btn = QPushButton("✕ Close")
        close_btn.setObjectName("dangerBtn")
        close_btn.clicked.connect(self.accept)
        button_bar.addWidget(close_btn)

        return button_bar

    def _init_timers(self):
        """Initialize timers for batch processing and stats updates"""
        # Batch processing timer (100ms for smooth UI)
        self._batch_timer = QTimer(self)
        self._batch_timer.setInterval(100)
        self._batch_timer.timeout.connect(self._process_batch)
        self._batch_timer.start()

        # Stats update timer (1 second)
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(1000)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start()

    def _init_filters(self):
        """Initialize filter settings"""
        self._filter_text = ""
        self._filter_level = "ALL"

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        super().__init__(parent)
        self.setWindowTitle("Log Viewer - ERROR")
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)
        error_label = QLabel(f"Failed to initialize log viewer. Please check logs.")
        error_label.setWordWrap(True)
        error_label.setStyleSheet("color: #f85149; padding: 20px; font-size: 12pt;")
        layout.addWidget(error_label)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 8px 16px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: #30363d;
            }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._initialized = False

    def append_log(self, message: str):
        """Queue log message for batch processing"""
        try:
            # Rule 6: Input validation
            if message is None:
                return

            if not isinstance(message, str):
                message = str(message)

            message = message.strip()
            if not message:
                return

            # Add to queue
            self._message_queue.append(message)

        except Exception as e:
            logger.error(f"[LogPopup.append_log] Failed: {e}", exc_info=True)

    def _process_batch(self):
        """Process queued messages in batches to prevent UI freeze"""
        try:
            if self._paused or not self._message_queue or self.log_widget is None:
                return

            # Block signals during batch update
            self.log_widget.blockSignals(True)

            processed = 0
            batch_size = 50  # Messages per batch

            while self._message_queue and processed < batch_size:
                msg = self._message_queue.popleft()

                # Apply filters
                if self._should_show_message(msg):
                    try:
                        # Apply syntax highlighting
                        formatted_msg = self._format_message(msg)
                        self.log_widget.appendPlainText(formatted_msg)
                        processed += 1

                        # Add to filtered queue for copy operations
                        self._filtered_queue.append(msg)
                        if len(self._filtered_queue) > 10000:
                            self._filtered_queue.popleft()

                    except RuntimeError:
                        # Widget was deleted
                        self._message_queue.clear()
                        break
                    except Exception as e:
                        logger.error(f"Failed to append message: {e}")
                        break

            self.log_widget.blockSignals(False)

            # Auto-scroll if enabled
            if processed > 0 and self._auto_scroll and not self._paused:
                try:
                    scrollbar = self.log_widget.verticalScrollBar()
                    scrollbar.setValue(scrollbar.maximum())
                except:
                    pass

            # Update message count
            self._message_count += processed

        except Exception as e:
            logger.error(f"[LogPopup._process_batch] Failed: {e}", exc_info=True)

    def _should_show_message(self, message: str) -> bool:
        """Check if message should be shown based on filters"""
        try:
            # Level filter
            if self._filter_level != "ALL":
                level = self._extract_level(message)
                if level and level != self._filter_level:
                    return False

            # Text filter
            if self._filter_text:
                if self._case_sensitive:
                    return self._filter_text in message
                else:
                    return self._filter_text.lower() in message.lower()

            return True

        except Exception as e:
            logger.error(f"[LogPopup._should_show_message] Failed: {e}", exc_info=True)
            return True

    def _extract_level(self, message: str) -> str:
        """Extract log level from message"""
        try:
            # Common log level patterns
            if '| DEBUG |' in message or '|DEBUG|' in message:
                return 'DEBUG'
            elif '| INFO |' in message or '|INFO|' in message:
                return 'INFO'
            elif '| WARNING |' in message or '|WARNING|' in message:
                return 'WARNING'
            elif '| ERROR |' in message or '|ERROR|' in message:
                return 'ERROR'
            elif '| CRITICAL |' in message or '|CRITICAL|' in message:
                return 'CRITICAL'
            return 'INFO'
        except:
            return 'INFO'

    def _format_message(self, message: str) -> str:
        """Apply syntax highlighting to message"""
        try:
            level = self._extract_level(message)
            color = self._level_colors.get(level, '#e6edf3')

            # Apply color using ANSI color codes (if supported)
            # For now, return as-is since QPlainTextEdit doesn't support colors per line easily
            # This could be extended with QSyntaxHighlighter
            return message
        except:
            return message

    def _on_filter_changed(self):
        """Handle filter changes"""
        try:
            self._filter_text = self.filter_edit.text()
            self._filter_level = self.level_combo.currentText()

            # Clear and reapply filters to existing content
            self._apply_filters_to_existing()

        except Exception as e:
            logger.error(f"[LogPopup._on_filter_changed] Failed: {e}", exc_info=True)

    def _apply_filters_to_existing(self):
        """Re-apply filters to existing log content"""
        try:
            # Store current content
            current_content = self.log_widget.toPlainText()
            if not current_content:
                return

            # Split into lines
            lines = current_content.split('\n')

            # Clear widget
            self.log_widget.clear()

            # Re-add filtered lines
            for line in lines:
                if line and self._should_show_message(line):
                    self.log_widget.appendPlainText(line)

        except Exception as e:
            logger.error(f"[LogPopup._apply_filters_to_existing] Failed: {e}", exc_info=True)

    def _on_max_lines_changed(self, value: int):
        """Handle max lines change"""
        try:
            self.log_widget.setMaximumBlockCount(value)
            self._update_stats()
        except Exception as e:
            logger.error(f"[LogPopup._on_max_lines_changed] Failed: {e}", exc_info=True)

    def _on_wrap_toggled(self, checked: bool):
        """Handle word wrap toggle"""
        try:
            self.log_widget.setLineWrapMode(
                QPlainTextEdit.WidgetWidth if checked else QPlainTextEdit.NoWrap
            )
        except Exception as e:
            logger.error(f"[LogPopup._on_wrap_toggled] Failed: {e}", exc_info=True)

    def _on_pause_toggled(self, checked: bool):
        """Handle pause button toggle"""
        try:
            self._paused = checked
            self.pause_btn.setText("▶️ Resume" if checked else "⏸️ Pause")

            if not checked:
                # Process any queued messages immediately
                self._process_batch()

        except Exception as e:
            logger.error(f"[LogPopup._on_pause_toggled] Failed: {e}", exc_info=True)

    def _update_stats(self):
        """Update status label with statistics"""
        try:
            if self.status_label is None:
                return

            block_count = self.log_widget.blockCount()
            queue_size = len(self._message_queue)

            status = f"📋 Log Viewer - {block_count} messages"
            if queue_size > 0:
                status += f" ({queue_size} queued)"
            if self._paused:
                status += " ⏸️ PAUSED"
            if self._filter_text or self._filter_level != "ALL":
                status += " 🔍 Filtered"

            self.status_label.setText(status)

        except Exception as e:
            logger.error(f"[LogPopup._update_stats] Failed: {e}", exc_info=True)

    def clear_logs(self):
        """Clear all logs"""
        try:
            if self.log_widget is not None:
                self.log_widget.clear()
                self._message_queue.clear()
                self._filtered_queue.clear()
                self._message_count = 0
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

                # Show feedback
                self._show_copy_feedback("All logs copied to clipboard!")
                logger.debug("All logs copied to clipboard")
        except Exception as e:
            logger.error(f"[LogPopup.copy_all_logs] Failed: {e}", exc_info=True)

    def copy_filtered_logs(self):
        """Copy filtered logs to clipboard"""
        try:
            text = '\n'.join(self._filtered_queue)
            if text:
                clipboard = QApplication.clipboard()
                clipboard.setText(text)
                self._show_copy_feedback(f"Copied {len(self._filtered_queue)} filtered messages!")
            else:
                self._show_copy_feedback("No filtered messages to copy")
        except Exception as e:
            logger.error(f"[LogPopup.copy_filtered_logs] Failed: {e}", exc_info=True)

    def export_logs(self):
        """Export logs to file"""
        try:
            from PyQt5.QtWidgets import QFileDialog

            # Get save filename
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Logs",
                f"logs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "Text Files (*.txt);;All Files (*)"
            )

            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_widget.toPlainText())
                self._show_copy_feedback(f"Logs exported to {filename}")
                logger.info(f"Logs exported to {filename}")

        except Exception as e:
            logger.error(f"[LogPopup.export_logs] Failed: {e}", exc_info=True)
            self._show_copy_feedback(f"Export failed: {e}")

    def _show_copy_feedback(self, message: str):
        """Show temporary feedback in status label"""
        try:
            if self.status_label is not None:
                old_text = self.status_label.text()
                self.status_label.setText(f"✅ {message}")
                QTimer.singleShot(2000, lambda: self.status_label.setText(old_text))
        except Exception as e:
            logger.error(f"[LogPopup._show_copy_feedback] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info(f"[LogPopup] Starting cleanup (ID: {id(self)})")

            # Mark as not initialized to prevent further append attempts
            self._initialized = False

            # Stop timers
            if self._batch_timer is not None:
                try:
                    self._batch_timer.stop()
                    self._batch_timer = None
                except Exception as e:
                    logger.warning(f"Failed to stop batch timer: {e}")

            if self._stats_timer is not None:
                try:
                    self._stats_timer.stop()
                    self._stats_timer = None
                except Exception as e:
                    logger.warning(f"Failed to stop stats timer: {e}")

            # Clear queues
            self._message_queue.clear()
            self._filtered_queue.clear()

            # Clear log widget
            if self.log_widget is not None:
                try:
                    self.log_widget.clear()
                    self.log_widget = None
                except Exception as e:
                    logger.warning(f"Failed to clear log widget: {e}")

            # Clear references
            self.status_label = None
            self.clear_btn = None
            self.copy_btn = None
            self.copy_filtered_btn = None
            self.pause_btn = None
            self.filter_edit = None
            self.level_combo = None
            self.wrap_check = None
            self.max_lines_spin = None
            self.export_btn = None

            logger.info(f"[LogPopup] Cleanup completed (ID: {id(self)})")

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
            # Reset pause state when shown
            self._paused = False
            self.pause_btn.setChecked(False)
            # Process any pending messages
            self._process_batch()
        except Exception as e:
            logger.error(f"[LogPopup.showEvent] Failed: {e}", exc_info=True)


# Import at bottom to avoid circular imports
from datetime import datetime