"""
logs_popup.py
=============
High-performance log viewer popup with filtering, export, and syntax highlighting.
MODERN MINIMALIST DESIGN - Matches DailyTradeSettingGUI, BrokerageSettingGUI, etc.
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

import logging
import logging.handlers
import traceback
import re
from typing import Optional, Dict, Any, List
from collections import deque
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot

from Utils.time_utils import ist_now
from gui.dialog_base import ThemedDialog, ThemedMixin, ModernCard, make_separator, make_scrollbar_ss, create_section_header, create_modern_button, apply_tab_style, build_title_bar
from PyQt5.QtGui import QTextCharFormat, QColor, QFont, QTextCursor, QSyntaxHighlighter
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit, QPushButton, QLabel, QApplication,
    QHBoxLayout, QCheckBox, QSpinBox, QGroupBox, QComboBox, QLineEdit,
    QFileDialog, QWidget, QFrame
)

from Utils.safe_getattr import safe_hasattr
# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

class ThemedMixin:
    """Mixin class to provide theme token shortcuts."""

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

class ModernHeader(QLabel):
    """Modern header with underline accent."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("modernHeader")
        self._apply_style()

    def _apply_style(self):
        c = theme_manager.palette
        ty = theme_manager.typography
        sp = theme_manager.spacing

        self.setStyleSheet(f"""
            QLabel#modernHeader {{
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_XL}pt;
                font-weight: {ty.WEIGHT_BOLD};
                padding-bottom: {sp.PAD_SM}px;
                border-bottom: 2px solid {c.BLUE};
                margin-bottom: {sp.PAD_MD}px;
            }}
        """)

class StatusBadge(QLabel):
    """Status badge with color-coded background."""

    def __init__(self, text="", status="neutral"):
        super().__init__(text)
        self.setObjectName("statusBadge")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(60)
        self.set_status(status)

    def set_status(self, status):
        """Update badge color based on status."""
        c = theme_manager.palette
        sp = theme_manager.spacing
        ty = theme_manager.typography

        if status == "success":
            color = c.GREEN
            bg = c.GREEN + "20"
        elif status == "warning":
            color = c.ORANGE
            bg = c.ORANGE + "20"
        elif status == "error":
            color = c.RED
            bg = c.RED + "20"
        elif status == "info":
            color = c.BLUE
            bg = c.BLUE + "20"
        else:
            color = c.TEXT_DIM
            bg = c.BG_HOVER

        self.setStyleSheet(f"""
            QLabel#statusBadge {{
                color: {color};
                background: {bg};
                border: 1px solid {color};
                border-radius: {sp.RADIUS_PILL}px;
                padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                font-size: {ty.SIZE_XS}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
        """)

class LogHighlighter(QSyntaxHighlighter, ThemedMixin):
    """
    Syntax highlighter for log messages with level-based coloring.
    Theme-aware - colors update when theme changes.
    """

    def __init__(self, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals

            self._init_rules()
            self.apply_theme()
        except Exception as e:
            logger.error(f"[LogHighlighter.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.rules = []
        self.level_colors = {}
        self.source_colors = {}

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to highlighting rules"""
        try:
            c = self._c
            self.level_colors = {
                'DEBUG': QColor(c.TEXT_DIM),      # Gray
                'INFO': QColor(c.BLUE),            # Blue
                'WARNING': QColor(c.YELLOW),       # Yellow
                'ERROR': QColor(c.RED),            # Red
                'CRITICAL': QColor(c.RED_BRIGHT),  # Bright red
            }

            self.source_colors = {
                'state_manager': QColor(c.PURPLE),  # Purple
                'trading_app': QColor(c.GREEN),     # Green
                'websocket': QColor(c.ORANGE),      # Orange
                'executor': QColor(c.BLUE),         # Light blue (using BLUE)
                'signal_engine': QColor(c.RED_BRIGHT),  # Light red
                'risk_manager': QColor(c.YELLOW),   # Yellow
                'notifier': QColor(c.BLUE),         # Light blue
                'gui': QColor(c.TEXT_DIM),          # Light gray (using TEXT_DIM)
            }

            self._init_rules()

            # Rehighlight the document
            self.rehighlight()

        except Exception as e:
            logger.error(f"[LogHighlighter.apply_theme] Failed: {e}", exc_info=True)

    def _init_rules(self):
        """Initialize highlighting rules"""
        try:
            c = self._c
            self.rules = []

            # Timestamp pattern (YYYY-MM-DD HH:MM:SS,mmm)
            timestamp_format = QTextCharFormat()
            timestamp_format.setForeground(QColor(c.TEXT_DISABLED))
            timestamp_format.setFontWeight(QFont.Normal)
            self.rules.append((re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}'), timestamp_format))

            # Thread/Process ID pattern
            thread_format = QTextCharFormat()
            thread_format.setForeground(QColor(c.TEXT_DIM))
            thread_format.setFontWeight(QFont.Normal)
            self.rules.append((re.compile(r'\[.*?\]'), thread_format))

            # Level patterns
            for level, color in self.level_colors.items():
                level_format = QTextCharFormat()
                level_format.setForeground(color)
                level_format.setFontWeight(QFont.Bold)
                self.rules.append((re.compile(f'\\b{level}\\b'), level_format))
                self.rules.append((re.compile(f'\\| {level} \\|'), level_format))

            # Source patterns
            for source, color in self.source_colors.items():
                source_format = QTextCharFormat()
                source_format.setForeground(color)
                source_format.setFontWeight(QFont.Bold)
                self.rules.append((re.compile(f'\\b{source}\\b'), source_format))

            # Number patterns
            number_format = QTextCharFormat()
            number_format.setForeground(QColor(c.BLUE))
            self.rules.append((re.compile(r'\b\d+\.?\d*\b'), number_format))

            # Exception patterns
            exception_format = QTextCharFormat()
            exception_format.setForeground(QColor(c.RED))
            exception_format.setFontWeight(QFont.Bold)
            self.rules.append((re.compile(r'Traceback \(most recent call last\)'), exception_format))
            self.rules.append((re.compile(r'  File .*, line \d+, in .*'), exception_format))
            self.rules.append((re.compile(r'    .*'), exception_format))

        except Exception as e:
            logger.error(f"[LogHighlighter._init_rules] Failed: {e}", exc_info=True)

    def highlightBlock(self, text):
        """Apply highlighting to a block of text"""
        for pattern, format in self.rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, format)

class LogViewerWidget(QPlainTextEdit, ThemedMixin):
    """High-performance log viewer with virtual scrolling and filtering capabilities"""

    def __init__(self, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals

            self.setReadOnly(True)
            self.setMaximumBlockCount(20000)  # Increased from 10000
            self.setLineWrapMode(QPlainTextEdit.NoWrap)

            # Enable custom context menu
            self.setContextMenuPolicy(Qt.CustomContextMenu)

            # Add syntax highlighter
            self.highlighter = LogHighlighter(self.document())

            self.apply_theme()

        except Exception as e:
            logger.error(f"[LogViewerWidget.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.highlighter = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the widget"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Set monospace font for better log readability
            font = self.document().defaultFont()
            font.setFamily(ty.FONT_MONO)
            font.setPointSize(ty.SIZE_SM)
            self.document().setDefaultFont(font)

            self.setStyleSheet(f"""
                QPlainTextEdit {{ 
                    background: {c.BG_MAIN}; 
                    color: {c.TEXT_MAIN}; 
                    border: 1px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                    font-family: '{ty.FONT_MONO}';
                    font-size: {ty.SIZE_SM}pt;
                    selection-background-color: {c.BG_SELECTED};
                }}
            """)
        except Exception as e:
            logger.error(f"[LogViewerWidget.apply_theme] Failed: {e}", exc_info=True)

    def append_log_batch(self, messages: List[str]):
        """Append multiple messages efficiently"""
        if not messages:
            return

        cursor = self.textCursor()
        cursor.movePosition(cursor.End)

        for msg in messages:
            cursor.insertText(msg + '\n')

        # Update view
        self.ensureCursorVisible()

class LogPopup(ThemedDialog):
    """Popup window for displaying logs with enhanced features - Modern Design"""

    # Signal for filtered log messages
    log_filtered = pyqtSignal(str)

    # Signal for log statistics
    stats_updated = pyqtSignal(dict)

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent, title="LOG VIEWER", icon="LV", size=(1200, 800))

            # Rule 13.2: Connect to theme and density signals

            # Set window flags for modern look
            self.resize(1200, 800)
            self.setMinimumSize(900, 600)

            # Initialize components
            self._init_ui()
            self._init_timers()
            self._init_filters()

            self.apply_theme()

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
        self.main_card = None

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

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            super().__init__(parent)
            self.setMinimumSize(400, 300)

            # Set window flags for modern look
            root = QVBoxLayout(self)
            root.setContentsMargins(20, 20, 20, 20)

            main_card = ModernCard(self, elevated=True)
            layout = QVBoxLayout(main_card)
            layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL,
                                     self._sp.PAD_XL, self._sp.PAD_XL)

            error_label = QLabel("❌ Failed to initialize log viewer.\nPlease check the logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet(f"color: {self._c.RED_BRIGHT}; padding: {self._sp.PAD_XL}px; font-size: {self._ty.SIZE_MD}pt;")
            layout.addWidget(error_label)

            close_btn = self._create_modern_button("Close", primary=False)
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn, 0, Qt.AlignCenter)

            root.addWidget(main_card)

        except Exception as e:
            logger.error(f"[LogPopup._create_error_dialog] Failed: {e}", exc_info=True)

    def _create_modern_button(self, text, primary=False, icon=""):
        """Create a modern styled button."""
        btn = QPushButton(f"{icon} {text}" if icon else text)
        btn.setCursor(Qt.PointingHandCursor)

        if primary:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BLUE};
                    color: white;
                    border: none;
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    min-width: 120px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BLUE_DARK};
                }}
                QPushButton:disabled {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_DISABLED};
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    min-width: 100px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BORDER};
                    border-color: {self._c.BORDER_FOCUS};
                }}
            """)

        return btn

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the popup"""
        try:
            c = self._c
            sp = self._sp

            # Update main card style
            if self.main_card:
                self.main_card._apply_style()

            # Update filter edit style
            if self.filter_edit:
                self.filter_edit.setStyleSheet(self._get_lineedit_style())

            # Update status label
            if self.status_label:
                self.status_label.setStyleSheet(f"""
                    QLabel {{
                        color: {c.TEXT_DIM};
                        font-size: {self._ty.SIZE_SM}pt;
                        padding: {sp.PAD_SM}px;
                        background: {c.BG_HOVER};
                        border-radius: {sp.RADIUS_MD}px;
                    }}
                """)

            # Update log widget
            if self.log_widget and safe_hasattr(self.log_widget, 'apply_theme'):
                self.log_widget.apply_theme()

            # Update combobox styles
            for combo in [self.level_combo, self.source_combo]:
                if combo:
                    combo.setStyleSheet(self._get_combobox_style())

            # Update spinbox style
            if self.max_lines_spin:
                self.max_lines_spin.setStyleSheet(self._get_spinbox_style())

            # Update checkbox style
            for chk in [self.wrap_check, self.case_sensitive_check]:
                if chk:
                    chk.setStyleSheet(self._get_checkbox_style())

            logger.debug("[LogPopup.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[LogPopup.apply_theme] Failed: {e}", exc_info=True)

    def _get_lineedit_style(self) -> str:
        """Get styled lineedit"""
        c = self._c
        sp = self._sp
        ty = self._ty

        return f"""
            QLineEdit {{
                background: {c.BG_INPUT};
                color: {c.TEXT_MAIN};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                min-height: {sp.INPUT_HEIGHT}px;
                font-size: {ty.SIZE_BODY}pt;
            }}
            QLineEdit:focus {{
                border-color: {c.BORDER_FOCUS};
            }}
        """

    def _get_combobox_style(self) -> str:
        """Get consistent combobox styling."""
        return f"""
            QComboBox {{
                background: {self._c.BG_INPUT};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
                padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                min-height: {self._sp.INPUT_HEIGHT}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-width: 100px;
            }}
            QComboBox:hover {{
                border-color: {self._c.BORDER_FOCUS};
            }}
            QComboBox::drop-down {{
                border: none;
                width: {self._sp.ICON_LG}px;
            }}
            QComboBox QAbstractItemView {{
                background: {self._c.BG_PANEL};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                selection-background-color: {self._c.BG_SELECTED};
            }}
        """

    def _get_spinbox_style(self) -> str:
        """Get consistent spinbox styling."""
        return f"""
            QSpinBox {{
                background: {self._c.BG_INPUT};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
                padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                min-height: {self._sp.INPUT_HEIGHT}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-width: 80px;
            }}
            QSpinBox:focus {{
                border-color: {self._c.BORDER_FOCUS};
            }}
        """

    def _get_checkbox_style(self) -> str:
        """Get consistent checkbox styling."""
        return f"""
            QCheckBox {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_BODY}pt;
                spacing: {self._sp.GAP_SM}px;
            }}
            QCheckBox::indicator {{
                width: {self._sp.ICON_MD}px;
                height: {self._sp.ICON_MD}px;
                border: 2px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:checked {{
                background: {self._c.BLUE};
                border-color: {self._c.BLUE};
            }}
            QCheckBox::indicator:hover {{
                border-color: {self._c.BORDER_FOCUS};
            }}
        """

    def _init_ui(self):
        """Initialize UI components with modern design"""
        # Root layout with margins for shadow effect
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        # Main container card
        self.main_card = ModernCard(self, elevated=True)
        main_layout = QVBoxLayout(self.main_card)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Custom title bar
        title_bar = self._create_title_bar()
        main_layout.addWidget(title_bar)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"background: {self._c.BORDER}; max-height: 1px;")
        main_layout.addWidget(separator)

        # Content area
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL,
                                         self._sp.PAD_XL, self._sp.PAD_XL)
        content_layout.setSpacing(self._sp.GAP_LG)

        # Top toolbar
        toolbar = self._create_toolbar()
        content_layout.addLayout(toolbar)

        # Status bar
        self.status_label = QLabel("📋 Ready")
        self.status_label.setAlignment(Qt.AlignLeft)
        content_layout.addWidget(self.status_label)

        # Log widget
        self.log_widget = LogViewerWidget()
        content_layout.addWidget(self.log_widget, 1)  # Give it stretch factor

        # Bottom button bar
        button_bar = self._create_button_bar()
        content_layout.addLayout(button_bar)

        main_layout.addWidget(content)
        root.addWidget(self.main_card)

        self._initialized = True

    def _create_title_bar(self):
        """Build new-design title bar: monogram badge + CAPS title + ghost buttons."""
        return build_title_bar(
            self,
            title="LOG VIEWER",
            icon="LV",
            on_close=self.close,
        )

    def _create_toolbar(self):
        """Create top toolbar with filters and controls"""
        toolbar = QHBoxLayout()
        toolbar.setSpacing(self._sp.GAP_MD)

        # Filter input
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("🔍 Filter logs...")
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        self.filter_edit.setStyleSheet(self._get_lineedit_style())
        toolbar.addWidget(self.filter_edit, 2)  # Give more stretch

        # Level filter
        self.level_combo = QComboBox()
        self.level_combo.addItems(['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        self.level_combo.currentTextChanged.connect(self._on_filter_changed)
        self.level_combo.setStyleSheet(self._get_combobox_style())
        toolbar.addWidget(self.level_combo)

        # Source filter
        self.source_combo = QComboBox()
        self.source_combo.addItem('ALL')
        self.source_combo.currentTextChanged.connect(self._on_filter_changed)
        self.source_combo.setStyleSheet(self._get_combobox_style())
        toolbar.addWidget(self.source_combo)

        # Case sensitive checkbox
        self.case_sensitive_check = QCheckBox("Aa")
        self.case_sensitive_check.setToolTip("Case sensitive filter")
        self.case_sensitive_check.toggled.connect(self._on_case_sensitive_toggled)
        self.case_sensitive_check.setStyleSheet(self._get_checkbox_style())
        toolbar.addWidget(self.case_sensitive_check)

        # Max lines spinbox
        max_lines_layout = QHBoxLayout()
        max_lines_layout.addWidget(QLabel("Max:"))
        self.max_lines_spin = QSpinBox()
        self.max_lines_spin.setRange(1000, 50000)
        self.max_lines_spin.setValue(20000)
        self.max_lines_spin.setSingleStep(1000)
        self.max_lines_spin.valueChanged.connect(self._on_max_lines_changed)
        self.max_lines_spin.setStyleSheet(self._get_spinbox_style())
        max_lines_layout.addWidget(self.max_lines_spin)
        toolbar.addLayout(max_lines_layout)

        # Word wrap checkbox
        self.wrap_check = QCheckBox("Wrap")
        self.wrap_check.setToolTip("Wrap text")
        self.wrap_check.toggled.connect(self._on_wrap_toggled)
        self.wrap_check.setStyleSheet(self._get_checkbox_style())
        toolbar.addWidget(self.wrap_check)

        return toolbar

    def _create_button_bar(self):
        """Create bottom button bar"""
        button_bar = QHBoxLayout()
        button_bar.setSpacing(self._sp.GAP_MD)

        # Left side buttons
        left_layout = QHBoxLayout()

        self.clear_btn = self._create_modern_button("Clear", primary=False, icon="🗑️")
        self.clear_btn.clicked.connect(self.clear_logs)
        left_layout.addWidget(self.clear_btn)

        self.pause_btn = self._create_modern_button("Pause", primary=False, icon="⏸️")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._on_pause_toggled)
        left_layout.addWidget(self.pause_btn)

        button_bar.addLayout(left_layout)

        button_bar.addStretch()

        # Center buttons
        center_layout = QHBoxLayout()

        self.copy_btn = self._create_modern_button("Copy All", primary=False, icon="📋")
        self.copy_btn.clicked.connect(self.copy_all_logs)
        center_layout.addWidget(self.copy_btn)

        self.copy_filtered_btn = self._create_modern_button("Copy Filtered", primary=False, icon="🔍")
        self.copy_filtered_btn.clicked.connect(self.copy_filtered_logs)
        center_layout.addWidget(self.copy_filtered_btn)

        self.export_btn = self._create_modern_button("Export", primary=False, icon="💾")
        self.export_btn.clicked.connect(self.export_logs)
        center_layout.addWidget(self.export_btn)

        self.stats_btn = self._create_modern_button("Stats", primary=False, icon="📊")
        self.stats_btn.clicked.connect(self._show_statistics)
        center_layout.addWidget(self.stats_btn)

        button_bar.addLayout(center_layout)

        button_bar.addStretch()

        # Right side buttons
        right_layout = QHBoxLayout()

        close_btn = self._create_modern_button("Close", primary=True, icon="✕")
        close_btn.clicked.connect(self.accept)
        right_layout.addWidget(close_btn)

        button_bar.addLayout(right_layout)

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
                        if safe_hasattr(self.log_widget, 'appendPlainText'):
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
                except Exception:
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
        except Exception:
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
        except Exception:
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
                        if safe_hasattr(self.log_widget, 'appendPlainText'):
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

            status = f"📋 {block_count} messages"
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
                    self.status_label.setText("📋 Cleared")
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
                f"logs_export_{ist_now().strftime('%Y%m%d_%H%M%S')}.txt",
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
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout

            dialog = QDialog(self)
            dialog.setWindowTitle("Log Statistics")
            dialog.setMinimumSize(400, 500)

            # Set window flags for modern look
            dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            dialog.setAttribute(Qt.WA_TranslucentBackground)

            root = QVBoxLayout(dialog)
            root.setContentsMargins(20, 20, 20, 20)

            main_card = ModernCard(dialog, elevated=True)
            layout = QVBoxLayout(main_card)
            layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL,
                                     self._sp.PAD_XL, self._sp.PAD_XL)
            layout.setSpacing(self._sp.GAP_LG)

            # Title
            title = ModernHeader("Log Statistics")
            layout.addWidget(title)

            # Level statistics
            level_group = QLabel("Level Counts:")
            level_group.setStyleSheet(f"color: {self._c.TEXT_MAIN}; font-weight: {self._ty.WEIGHT_BOLD}; font-size: {self._ty.SIZE_MD}pt;")
            layout.addWidget(level_group)

            # Use theme colors for level labels
            c = self._c
            level_colors = {
                'DEBUG': c.TEXT_DIM,
                'INFO': c.BLUE,
                'WARNING': c.YELLOW,
                'ERROR': c.RED,
                'CRITICAL': c.RED_BRIGHT,
            }

            for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
                count = self._level_counts.get(level, 0)
                color = level_colors.get(level, c.TEXT_MAIN)

                level_layout = QHBoxLayout()
                level_layout.addWidget(QLabel(f"{level}:"))

                count_label = QLabel(str(count))
                count_label.setStyleSheet(f"color: {color}; font-weight: {self._ty.WEIGHT_BOLD};")
                level_layout.addWidget(count_label)
                level_layout.addStretch()

                layout.addLayout(level_layout)

            # Source statistics
            if self._source_counts:
                layout.addSpacing(self._sp.GAP_MD)
                source_group = QLabel("Source Counts:")
                source_group.setStyleSheet(f"color: {self._c.TEXT_MAIN}; font-weight: {self._ty.WEIGHT_BOLD}; font-size: {self._ty.SIZE_MD}pt;")
                layout.addWidget(source_group)

                for source, count in sorted(self._source_counts.items()):
                    source_layout = QHBoxLayout()
                    source_layout.addWidget(QLabel(f"{source}:"))

                    count_label = QLabel(str(count))
                    count_label.setStyleSheet(f"color: {self._c.TEXT_DIM};")
                    source_layout.addWidget(count_label)
                    source_layout.addStretch()

                    layout.addLayout(source_layout)

            # Total messages
            total = sum(self._level_counts.values())
            layout.addSpacing(self._sp.GAP_MD)
            total_layout = QHBoxLayout()
            total_layout.addWidget(QLabel("Total Messages:"))
            total_label = QLabel(str(total))
            total_label.setStyleSheet(f"color: {self._c.BLUE}; font-weight: {self._ty.WEIGHT_BOLD}; font-size: {self._ty.SIZE_MD}pt;")
            total_layout.addWidget(total_label)
            total_layout.addStretch()
            layout.addLayout(total_layout)

            layout.addStretch()

            # Close button
            close_btn = self._create_modern_button("Close", primary=True)
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn, 0, Qt.AlignCenter)

            root.addWidget(main_card)
            dialog.exec_()

        except Exception as e:
            logger.error(f"[LogPopup._show_statistics] Failed: {e}", exc_info=True)

    def _show_copy_feedback(self, message: str):
        """Show temporary feedback in status label"""
        try:
            if self.status_label is not None:
                old_text = self.status_label.text()
                self.status_label.setText(f"✅ {message}")
                self.status_label.setStyleSheet(f"""
                    QLabel {{
                        color: {self._c.GREEN};
                        font-size: {self._ty.SIZE_SM}pt;
                        font-weight: {self._ty.WEIGHT_BOLD};
                        padding: {self._sp.PAD_SM}px;
                        background: {self._c.BG_HOVER};
                        border-radius: {self._sp.RADIUS_MD}px;
                    }}
                """)
                QTimer.singleShot(2000, lambda: self._restore_status_label(old_text))
        except Exception as e:
            logger.error(f"[LogPopup._show_copy_feedback] Failed: {e}", exc_info=True)

    def _restore_status_label(self, old_text: str):
        """Restore status label after feedback"""
        try:
            if self.status_label is not None:
                self.status_label.setText(old_text)
                self.status_label.setStyleSheet(f"""
                    QLabel {{
                        color: {self._c.TEXT_DIM};
                        font-size: {self._ty.SIZE_SM}pt;
                        padding: {self._sp.PAD_SM}px;
                        background: {self._c.BG_HOVER};
                        border-radius: {self._sp.RADIUS_MD}px;
                    }}
                """)
        except Exception as e:
            logger.error(f"[LogPopup._restore_status_label] Failed: {e}", exc_info=True)

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
            self.main_card = None

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
                self.pause_btn.setText("⏸️ Pause")
            # Process any pending messages
            self._process_batch()
        except Exception as e:
            logger.error(f"[LogPopup.showEvent] Failed: {e}", exc_info=True)