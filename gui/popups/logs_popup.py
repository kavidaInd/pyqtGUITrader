"""
logs_popup.py
=============
High-performance log viewer popup with filtering, export, and syntax highlighting.

UPDATED: Fixed AttributeError when source_combo is None during log appending.
"""

import logging
import logging.handlers
import traceback
import re
from typing import Optional, Dict, Any
from collections import deque
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QTextCharFormat, QColor, QFont, QTextCursor, QSyntaxHighlighter
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit, QPushButton, QLabel, QApplication,
    QHBoxLayout, QCheckBox, QSpinBox, QGroupBox, QComboBox, QLineEdit,
    QFileDialog
)

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class LogHighlighter(QSyntaxHighlighter):
    """
    Syntax highlighter for log messages with level-based coloring.
    """

    # Define colors for different log levels
    LEVEL_COLORS = {
        'DEBUG': QColor('#8b949e'),    # Gray
        'INFO': QColor('#58a6ff'),     # Blue
        'WARNING': QColor('#d29922'),  # Yellow
        'ERROR': QColor('#f85149'),    # Red
        'CRITICAL': QColor('#ff7b72')  # Bright red
    }

    # Source colors (for different application components)
    SOURCE_COLORS = {
        'state_manager': QColor('#bc8cff'),  # Purple
        'trading_app': QColor('#3fb950'),    # Green
        'websocket': QColor('#ffa657'),      # Orange
        'executor': QColor('#79c0ff'),       # Light blue
        'signal_engine': QColor('#ff7b72'),  # Light red
        'risk_manager': QColor('#d29922'),   # Yellow
        'notifier': QColor('#a5d6ff'),       # Light blue
        'gui': QColor('#c9d1d9'),            # Light gray
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_rules()

    def _init_rules(self):
        """Initialize highlighting rules"""
        self.rules = []

        # Timestamp pattern (YYYY-MM-DD HH:MM:SS,mmm)
        timestamp_format = QTextCharFormat()
        timestamp_format.setForeground(QColor('#6e7681'))
        timestamp_format.setFontWeight(QFont.Normal)
        self.rules.append((re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}'), timestamp_format))

        # Thread/Process ID pattern
        thread_format = QTextCharFormat()
        thread_format.setForeground(QColor('#8b949e'))
        thread_format.setFontWeight(QFont.Normal)
        self.rules.append((re.compile(r'\[.*?\]'), thread_format))

        # Level patterns
        for level, color in self.LEVEL_COLORS.items():
            level_format = QTextCharFormat()
            level_format.setForeground(color)
            level_format.setFontWeight(QFont.Bold)
            self.rules.append((re.compile(f'\\b{level}\\b'), level_format))
            self.rules.append((re.compile(f'\\| {level} \\|'), level_format))

        # Source patterns
        for source, color in self.SOURCE_COLORS.items():
            source_format = QTextCharFormat()
            source_format.setForeground(color)
            source_format.setFontWeight(QFont.Bold)
            self.rules.append((re.compile(f'\\b{source}\\b'), source_format))

        # Number patterns
        number_format = QTextCharFormat()
        number_format.setForeground(QColor('#79c0ff'))
        self.rules.append((re.compile(r'\b\d+\.?\d*\b'), number_format))

        # Exception patterns
        exception_format = QTextCharFormat()
        exception_format.setForeground(QColor('#f85149'))
        exception_format.setFontWeight(QFont.Bold)
        self.rules.append((re.compile(r'Traceback \(most recent call last\)'), exception_format))
        self.rules.append((re.compile(r'  File .*, line \d+, in .*'), exception_format))
        self.rules.append((re.compile(r'    .*'), exception_format))

    def highlightBlock(self, text):
        """Apply highlighting to a block of text"""
        for pattern, format in self.rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, format)


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

        # Add syntax highlighter
        self.highlighter = LogHighlighter(self.document())

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

    # Signal for log statistics
    stats_updated = pyqtSignal(dict)

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
                QSpinBox, QComboBox, QLineEdit {
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
                QLineEdit:focus {
                    border: 1px solid #58a6ff;
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
        self.source_combo = None
        self.wrap_check = None
        self.max_lines_spin = None
        self.copy_filtered_btn = None
        self.export_btn = None
        self.stats_btn = None
        self.case_sensitive_check = None

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
        self._filter_source = "ALL"
        self._filter_regex = False
        self._case_sensitive = False

        # Statistics
        self._level_counts = {
            'DEBUG': 0,
            'INFO': 0,
            'WARNING': 0,
            'ERROR': 0,
            'CRITICAL': 0
        }
        self._source_counts = {}
        self._source_set = set()  # Track unique sources

        # Timers
        self._batch_timer = None
        self._stats_timer = None

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
        self.level_combo.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.level_combo)

        # Source filter
        self.source_combo = QComboBox()
        self.source_combo.addItem('ALL')
        self.source_combo.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.source_combo)

        # Case sensitive checkbox
        self.case_sensitive_check = QCheckBox("Aa")
        self.case_sensitive_check.setToolTip("Case sensitive filter")
        self.case_sensitive_check.toggled.connect(self._on_case_sensitive_toggled)
        toolbar.addWidget(self.case_sensitive_check)

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

        # Stats button
        self.stats_btn = QPushButton("📊 Statistics")
        self.stats_btn.clicked.connect(self._show_statistics)
        button_bar.addWidget(self.stats_btn)

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
        self._filter_source = "ALL"
        self._case_sensitive = False

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        super().__init__(parent)
        self.setWindowTitle("Log Viewer - ERROR")
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)
        error_label = QLabel("Failed to initialize log viewer. Please check logs.")
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

            # Extract level for statistics
            level = self._extract_level(message)
            self._level_counts[level] = self._level_counts.get(level, 0) + 1

            # Extract source if present (format: [source] message or source: message)
            source = self._extract_source(message)
            if source:
                self._source_counts[source] = self._source_counts.get(source, 0) + 1

                # === FIX: Check if source_combo exists before updating it ===
                if source not in self._source_set:
                    self._source_set.add(source)
                    # Only update combo box if it exists and we're in the main thread
                    if self.source_combo is not None and self._initialized:
                        # Use QTimer to ensure this runs in the main thread
                        QTimer.singleShot(0, self._update_source_combo)

            # Add to queue
            self._message_queue.append((message, level, source))

            # Also add to filtered queue for filter operations
            self._filtered_queue.append((message, level, source))
            if len(self._filtered_queue) > 10000:
                self._filtered_queue.popleft()

        except Exception as e:
            logger.error(f"[LogPopup.append_log] Failed: {e}", exc_info=True)

    def _update_source_combo(self):
        """Update source combo box with new sources (runs in main thread)"""
        try:
            if self.source_combo is None or not self._initialized:
                return

            # Block signals to prevent filter triggers
            self.source_combo.blockSignals(True)

            # Get current selection
            current = self.source_combo.currentText()

            # Clear and rebuild
            self.source_combo.clear()
            self.source_combo.addItem('ALL')

            # Add all unique sources
            for source in sorted(self._source_set):
                self.source_combo.addItem(source)

            # Restore selection
            index = self.source_combo.findText(current)
            if index >= 0:
                self.source_combo.setCurrentIndex(index)

            self.source_combo.blockSignals(False)

        except Exception as e:
            logger.error(f"[LogPopup._update_source_combo] Failed: {e}", exc_info=True)

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
                msg, level, source = self._message_queue.popleft()

                # Apply filters
                if self._should_show_message(msg, level, source):
                    try:
                        # Use the log widget's append method
                        if hasattr(self.log_widget, 'appendPlainText'):
                            self.log_widget.appendPlainText(msg)
                        else:
                            self.log_widget.append(msg)
                        processed += 1

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

    def _should_show_message(self, message: str, level: str = None, source: str = None) -> bool:
        """Check if message should be shown based on filters"""
        try:
            # Level filter
            if self._filter_level != "ALL":
                if level is None:
                    level = self._extract_level(message)
                if level and level != self._filter_level:
                    return False

            # Source filter
            if self._filter_source != "ALL":
                if source is None:
                    source = self._extract_source(message)
                if source != self._filter_source:
                    return False

            # Text filter
            if self._filter_text:
                filter_text = self._filter_text.strip()
                if filter_text:
                    if self._case_sensitive:
                        return filter_text in message
                    else:
                        return filter_text.lower() in message.lower()

            return True

        except Exception as e:
            logger.error(f"[LogPopup._should_show_message] Failed: {e}", exc_info=True)
            return True

    def _extract_level(self, message: str) -> str:
        """Extract log level from message"""
        try:
            # Common log level patterns
            if '| DEBUG |' in message or '|DEBUG|' in message or ' DEBUG ' in message:
                return 'DEBUG'
            elif '| INFO |' in message or '|INFO|' in message or ' INFO ' in message:
                return 'INFO'
            elif '| WARNING |' in message or '|WARNING|' in message or ' WARNING ' in message:
                return 'WARNING'
            elif '| ERROR |' in message or '|ERROR|' in message or ' ERROR ' in message:
                return 'ERROR'
            elif '| CRITICAL |' in message or '|CRITICAL|' in message or ' CRITICAL ' in message:
                return 'CRITICAL'
            return 'INFO'
        except:
            return 'INFO'

    def _extract_source(self, message: str) -> str:
        """Extract source from message (format: [source] or source:)"""
        try:
            # Look for [source] pattern
            import re
            match = re.search(r'\[([^\]]+)\]', message)
            if match:
                return match.group(1)

            # Look for source: pattern
            match = re.search(r'^(\w+):', message)
            if match:
                return match.group(1)

            # Look for source in log format: "source - message"
            match = re.search(r'^([\w_]+) -', message)
            if match:
                return match.group(1)

            return ''
        except:
            return ''

    def _apply_filters_to_existing(self):
        """Re-apply filters to existing log content"""
        try:
            # Store current content from filtered queue (original messages)
            if not self._filtered_queue:
                return

            # Clear widget
            self.log_widget.clear()

            # Re-add filtered lines from the filtered queue
            messages_added = 0
            for msg, level, source in list(self._filtered_queue):  # Use a copy to avoid modification during iteration
                if msg and self._should_show_message(msg, level, source):
                    try:
                        if hasattr(self.log_widget, 'appendPlainText'):
                            self.log_widget.appendPlainText(msg)
                        else:
                            self.log_widget.append(msg)
                        messages_added += 1
                    except Exception as e:
                        logger.warning(f"Failed to add message during filter: {e}")

            logger.debug(f"Re-filtered {messages_added} messages")

        except Exception as e:
            logger.error(f"[LogPopup._apply_filters_to_existing] Failed: {e}", exc_info=True)

    def _on_filter_changed(self):
        """Handle filter changes"""
        try:
            self._filter_text = self.filter_edit.text() if self.filter_edit else ""
            self._filter_level = self.level_combo.currentText() if self.level_combo else "ALL"
            self._filter_source = self.source_combo.currentText() if self.source_combo else "ALL"

            # Clear and reapply filters to existing content
            self._apply_filters_to_existing()

        except Exception as e:
            logger.error(f"[LogPopup._on_filter_changed] Failed: {e}", exc_info=True)

    def _on_case_sensitive_toggled(self, checked: bool):
        """Handle case sensitive toggle"""
        try:
            self._case_sensitive = checked
            self._on_filter_changed()  # Re-apply filters
        except Exception as e:
            logger.error(f"[LogPopup._on_case_sensitive_toggled] Failed: {e}", exc_info=True)

    def _on_max_lines_changed(self, value: int):
        """Handle max lines change"""
        try:
            if self.log_widget:
                self.log_widget.setMaximumBlockCount(value)
            self._update_stats()
        except Exception as e:
            logger.error(f"[LogPopup._on_max_lines_changed] Failed: {e}", exc_info=True)

    def _on_wrap_toggled(self, checked: bool):
        """Handle word wrap toggle"""
        try:
            if self.log_widget:
                self.log_widget.setLineWrapMode(
                    QPlainTextEdit.WidgetWidth if checked else QPlainTextEdit.NoWrap
                )
        except Exception as e:
            logger.error(f"[LogPopup._on_wrap_toggled] Failed: {e}", exc_info=True)

    def _on_pause_toggled(self, checked: bool):
        """Handle pause button toggle"""
        try:
            self._paused = checked
            if self.pause_btn:
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

            block_count = self.log_widget.blockCount() if self.log_widget else 0
            queue_size = len(self._message_queue)

            status = f"📋 Log Viewer - {block_count} messages"
            if queue_size > 0:
                status += f" ({queue_size} queued)"
            if self._paused:
                status += " ⏸️ PAUSED"
            if self._filter_text or self._filter_level != "ALL" or self._filter_source != "ALL":
                status += " 🔍 Filtered"

            # Add level counts
            if any(self._level_counts.values()):
                counts = []
                for level in ['ERROR', 'WARNING', 'INFO', 'DEBUG']:
                    if self._level_counts.get(level, 0) > 0:
                        counts.append(f"{level}: {self._level_counts[level]}")
                if counts:
                    status += f" | {' | '.join(counts)}"

            self.status_label.setText(status)

            # Emit statistics
            self.stats_updated.emit({
                'total': block_count,
                'queued': queue_size,
                'levels': dict(self._level_counts),
                'sources': dict(self._source_counts)
            })

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
                self._level_counts = {k: 0 for k in self._level_counts}
                self._source_counts.clear()
                self._source_set.clear()

                # Clear source combo
                if self.source_combo:
                    self.source_combo.blockSignals(True)
                    self.source_combo.clear()
                    self.source_combo.addItem('ALL')
                    self.source_combo.blockSignals(False)

                if self.status_label:
                    self.status_label.setText("📋 Log Viewer - Cleared")
                logger.debug("Logs cleared")
        except Exception as e:
            logger.error(f"[LogPopup.clear_logs] Failed: {e}", exc_info=True)

    def copy_all_logs(self):
        """Copy all logs to clipboard"""
        try:
            if self.log_widget is not None:
                clipboard = QApplication.clipboard()
                if clipboard:
                    clipboard.setText(self.log_widget.toPlainText())

                # Show feedback
                self._show_copy_feedback("All logs copied to clipboard!")
                logger.debug("All logs copied to clipboard")
        except Exception as e:
            logger.error(f"[LogPopup.copy_all_logs] Failed: {e}", exc_info=True)

    def copy_filtered_logs(self):
        """Copy filtered logs to clipboard"""
        try:
            # Build filtered text from filtered_queue
            filtered_lines = []
            for msg, level, source in self._filtered_queue:
                if self._should_show_message(msg, level, source):
                    filtered_lines.append(msg)

            text = '\n'.join(filtered_lines)
            if text:
                clipboard = QApplication.clipboard()
                if clipboard:
                    clipboard.setText(text)
                self._show_copy_feedback(f"Copied {len(filtered_lines)} filtered messages!")
            else:
                self._show_copy_feedback("No filtered messages to copy")
        except Exception as e:
            logger.error(f"[LogPopup.copy_filtered_logs] Failed: {e}", exc_info=True)

    def export_logs(self):
        """Export logs to file"""
        try:
            # Get save filename
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Logs",
                f"logs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "Text Files (*.txt);;All Files (*)"
            )

            if filename and self.log_widget:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_widget.toPlainText())
                self._show_copy_feedback(f"Logs exported to {filename}")
                logger.info(f"Logs exported to {filename}")

        except Exception as e:
            logger.error(f"[LogPopup.export_logs] Failed: {e}", exc_info=True)
            self._show_copy_feedback(f"Export failed: {e}")

    def _show_statistics(self):
        """Show detailed statistics dialog"""
        try:
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton

            dialog = QDialog(self)
            dialog.setWindowTitle("Log Statistics")
            dialog.setMinimumSize(300, 400)
            dialog.setStyleSheet(self.styleSheet())

            layout = QVBoxLayout(dialog)

            # Level statistics
            layout.addWidget(QLabel("<b>Level Counts:</b>"))
            for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
                count = self._level_counts.get(level, 0)
                color = LogHighlighter.LEVEL_COLORS.get(level, QColor('#e6edf3'))
                label = QLabel(f"{level}: {count}")
                label.setStyleSheet(f"color: {color.name()};")
                layout.addWidget(label)

            # Source statistics
            if self._source_counts:
                layout.addWidget(QLabel("<br><b>Source Counts:</b>"))
                for source, count in sorted(self._source_counts.items()):
                    label = QLabel(f"{source}: {count}")
                    label.setStyleSheet("color: #8b949e;")
                    layout.addWidget(label)

            # Total messages
            total = sum(self._level_counts.values())
            layout.addWidget(QLabel(f"<br><b>Total Messages:</b> {total}"))

            # Close button
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)

            dialog.exec_()

        except Exception as e:
            logger.error(f"[LogPopup._show_statistics] Failed: {e}", exc_info=True)

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
            self._source_set.clear()

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
            self.source_combo = None
            self.case_sensitive_check = None
            self.wrap_check = None
            self.max_lines_spin = None
            self.export_btn = None
            self.stats_btn = None

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
            if self.pause_btn:
                self.pause_btn.setChecked(False)
            # Process any pending messages
            self._process_batch()
        except Exception as e:
            logger.error(f"[LogPopup.showEvent] Failed: {e}", exc_info=True)