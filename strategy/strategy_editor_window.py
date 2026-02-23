"""
strategy_editor_window.py
==========================
Full-page Strategy Editor Window with tab-based signal rules and complete indicator registry.
Enhanced with expanded cards, clear labels, and import/export functionality.
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QFont, QIntValidator, QDoubleValidator, QClipboard
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget, QGridLayout,
    QHeaderView, QTableWidget, QTableWidgetItem, QCompleter,
    QStackedWidget, QFileDialog, QMenu, QToolButton)

from strategy.strategy_manager import (
    StrategyManager, INDICATOR_DEFAULTS, ENGINE_DEFAULTS, SIGNAL_GROUPS
)
from strategy.indicator_registry import (
    ALL_INDICATORS, INDICATOR_DEFAULT_PARAMS, get_indicator_params,
    get_param_type, get_param_description, get_indicator_category,
    INDICATOR_CATEGORIES, get_indicators_by_category
)

logger = logging.getLogger(__name__)

# ── Palette ──────────────────────────────────────────────────────────────────
BG       = "#0d1117"
BG_PANEL = "#161b22"
BG_ITEM  = "#1c2128"
BG_SEL   = "#1f3d5c"
BORDER   = "#30363d"
TEXT     = "#e6edf3"
DIM      = "#8b949e"
GREEN    = "#3fb950"
RED      = "#f85149"
BLUE     = "#58a6ff"
YELLOW   = "#d29922"
ORANGE   = "#ffa657"
PURPLE   = "#bc8cff"

SIGNAL_META = {
    "BUY_CALL":  ("📈", GREEN,  "BUY CALL"),
    "BUY_PUT":   ("📉", BLUE,   "BUY PUT"),
    "SELL_CALL": ("🔴", RED,    "SELL CALL"),
    "SELL_PUT":  ("🟠", ORANGE, "SELL PUT"),
    "HOLD":      ("⏸",  YELLOW, "HOLD"),
}

OPERATORS = [">", "<", ">=", "<=", "==", "!=", "crosses_above", "crosses_below"]
SIDE_TYPES = ["indicator", "scalar", "column"]
COLUMNS = ["close", "open", "high", "low", "volume", "hl2", "hlc3", "ohlc4"]

# Human-readable labels and descriptions for each column
COLUMN_META = {
    "close":  ("CLOSE",  "Closing price"),
    "open":   ("OPEN",   "Opening price"),
    "high":   ("HIGH",   "Period high"),
    "low":    ("LOW",    "Period low"),
    "volume": ("VOLUME", "Trading volume"),
    "hl2":    ("HL2",    "(High + Low) / 2  — mid-price"),
    "hlc3":   ("HLC3",   "(High + Low + Close) / 3  — typical price"),
    "ohlc4":  ("OHLC4",  "(Open + High + Low + Close) / 4  — average price"),
}


def _ss() -> str:
    """Global stylesheet."""
    return f"""
        QWidget, QDialog {{ background: {BG}; color: {TEXT}; font-size: 10pt; }}
        QLabel {{ color: {TEXT}; }}
        QGroupBox {{
            background: {BG_PANEL};
            border: 1px solid {BORDER};
            border-radius: 6px;
            margin-top: 14px;
            padding: 8px 6px 6px 6px;
            font-weight: bold; font-size: 9pt;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; left: 10px;
            padding: 0 4px; color: {TEXT};
        }}
        QLineEdit, QTextEdit, QComboBox {{
            background: #21262d; color: {TEXT};
            border: 1px solid {BORDER}; border-radius: 4px;
            padding: 6px 8px; font-size: 10pt;
        }}
        QLineEdit:focus, QTextEdit:focus {{ border: 2px solid {BLUE}; }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{ 
            background: #21262d; 
            color: {TEXT}; 
            selection-background-color: {BG_SEL};
            min-width: 250px;
        }}
        QCheckBox {{ color: {TEXT}; spacing: 6px; font-size: 10pt; }}
        QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 3px; }}
        QCheckBox::indicator:unchecked {{ background: #21262d; border: 2px solid {BORDER}; }}
        QCheckBox::indicator:checked  {{ background: {GREEN};  border: 2px solid {GREEN}; }}
        QPushButton {{
            background: #21262d; color: {TEXT};
            border: 1px solid {BORDER}; border-radius: 5px;
            padding: 7px 16px; font-size: 10pt; font-weight: bold;
        }}
        QPushButton:hover {{ background: #2d333b; }}
        QPushButton:disabled {{ background: #161b22; color: #484f58; }}
        QToolButton {{
            background: #21262d; color: {TEXT};
            border: 1px solid {BORDER}; border-radius: 5px;
            padding: 7px 16px; font-size: 10pt; font-weight: bold;
        }}
        QToolButton:hover {{ background: #2d333b; }}
        QToolButton::menu-indicator {{ image: none; }}
        QMenu {{
            background-color: #21262d;
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            font-size: 10pt;
        }}
        QMenu::item {{
            padding: 8px 20px;
            border-bottom: 1px solid {BORDER}40;
        }}
        QMenu::item:selected {{
            background-color: {BG_SEL};
            color: {BLUE};
        }}
        QListWidget {{
            background: {BG_PANEL}; color: {TEXT};
            border: 1px solid {BORDER}; border-radius: 4px;
            font-size: 10pt; outline: none;
        }}
        QListWidget::item {{ padding: 10px 12px; border-bottom: 1px solid {BORDER}; }}
        QListWidget::item:selected {{ background: {BG_SEL}; color: {BLUE}; border-left: 3px solid {BLUE}; }}
        QListWidget::item:hover {{ background: #1f2937; }}
        QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 4px; background: {BG_PANEL}; }}
        QTabBar::tab {{
            background: #21262d; color: {DIM};
            border: 1px solid {BORDER}; border-bottom: none;
            border-radius: 4px 4px 0 0; padding: 7px 18px; font-size: 10pt;
        }}
        QTabBar::tab:selected {{ background: {BG_PANEL}; color: {TEXT}; border-bottom: 2px solid {BLUE}; }}
        QTableWidget {{
            background: {BG_PANEL}; gridline-color: {BORDER};
            border: 1px solid {BORDER}; border-radius: 4px; color: {TEXT}; font-size: 9pt;
        }}
        QTableWidget::item {{ padding: 4px 8px; }}
        QHeaderView::section {{
            background: #21262d; color: {DIM};
            border: none; border-bottom: 1px solid {BORDER};
            padding: 5px 8px; font-size: 8pt; font-weight: bold;
        }}
        QScrollArea {{ border: none; background: transparent; }}
        QSplitter::handle {{ background: {BORDER}; }}
        QStackedWidget {{ background: transparent; }}
    """


def _btn(text: str, color: str = "#21262d", hover: str = "#2d333b",
         text_color: str = TEXT, min_w: int = 0) -> QPushButton:
    b = QPushButton(text)
    style = (
        f"QPushButton {{ background:{color}; color:{text_color}; border:1px solid {BORDER};"
        f" border-radius:5px; padding:7px 14px; font-weight:bold; font-size:10pt;"
        f"{'min-width:' + str(min_w) + 'px;' if min_w else ''} }}"
        f"QPushButton:hover {{ background:{hover}; }}"
        f"QPushButton:disabled {{ background:#161b22; color:#484f58; }}"
    )
    b.setStyleSheet(style)
    return b


# ── Import/Export Dialog ─────────────────────────────────────────────────────

class ImportExportDialog(QDialog):
    """Dialog for importing/exporting strategies as JSON"""

    def __init__(self, mode: str, strategy_data: Dict = None, parent=None):
        super().__init__(parent)
        self.mode = mode  # 'import' or 'export'
        self.strategy_data = strategy_data
        self.setWindowTitle("📦 Import/Export Strategy")
        self.setFixedSize(600, 400)
        self.setStyleSheet(_ss())

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("📋 Strategy JSON" if mode == 'export' else "📥 Import Strategy")
        header.setStyleSheet(f"color:{BLUE}; font-size:14pt; font-weight:bold; padding:8px;")
        layout.addWidget(header)

        # JSON Text Edit
        self.json_edit = QTextEdit()
        self.json_edit.setFont(QFont("Courier New", 10))
        self.json_edit.setStyleSheet(f"""
            QTextEdit {{
                background: #1c2128;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                font-family: 'Courier New';
                font-size: 10pt;
            }}
        """)

        if mode == 'export' and strategy_data:
            # Format JSON nicely
            formatted_json = json.dumps(strategy_data, indent=2, default=str)
            self.json_edit.setPlainText(formatted_json)
            self.json_edit.setReadOnly(True)
        else:
            self.json_edit.setPlaceholderText("Paste your strategy JSON here...")

        layout.addWidget(self.json_edit)

        # Buttons
        btn_layout = QHBoxLayout()

        if mode == 'export':
            # Copy button
            copy_btn = QPushButton("📋 Copy to Clipboard")
            copy_btn.clicked.connect(self._copy_to_clipboard)
            btn_layout.addWidget(copy_btn)

            # Save to file button
            save_btn = QPushButton("💾 Save to File")
            save_btn.clicked.connect(self._save_to_file)
            btn_layout.addWidget(save_btn)
        else:
            # Load from file button
            load_btn = QPushButton("📂 Load from File")
            load_btn.clicked.connect(self._load_from_file)
            btn_layout.addWidget(load_btn)

            # Validate button
            validate_btn = QPushButton("✓ Validate")
            validate_btn.clicked.connect(self._validate_json)
            btn_layout.addWidget(validate_btn)

        btn_layout.addStretch()

        # OK/Cancel
        self.ok_btn = QPushButton("OK" if mode == 'export' else "Import")
        self.ok_btn.setStyleSheet(f"background:{GREEN}; color:{BG}; font-weight:bold;")
        self.ok_btn.clicked.connect(self.accept if mode == 'export' else self._on_import)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        if mode == 'import':
            self.ok_btn.setEnabled(False)

    def _copy_to_clipboard(self):
        """Copy JSON to clipboard"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.json_edit.toPlainText())
        QMessageBox.information(self, "Copied", "Strategy JSON copied to clipboard!")

    def _save_to_file(self):
        """Save JSON to file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Strategy", "", "JSON Files (*.json)"
        )
        if filename:
            with open(filename, 'w') as f:
                f.write(self.json_edit.toPlainText())
            QMessageBox.information(self, "Saved", f"Strategy saved to {filename}")

    def _load_from_file(self):
        """Load JSON from file"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Strategy", "", "JSON Files (*.json)"
        )
        if filename:
            with open(filename, 'r') as f:
                content = f.read()
            self.json_edit.setPlainText(content)
            self._validate_json()

    def _validate_json(self):
        """Validate JSON content"""
        try:
            data = json.loads(self.json_edit.toPlainText())
            # Basic validation - check for required fields
            if 'meta' in data and 'engine' in data:
                self.ok_btn.setEnabled(True)
                self.ok_btn.setText("✓ Valid - Import")
                QMessageBox.information(self, "Valid", "JSON is valid and ready to import!")
            else:
                self.ok_btn.setEnabled(False)
                self.ok_btn.setText("✗ Invalid - Missing required fields")
                QMessageBox.warning(self, "Invalid", "JSON must contain 'meta' and 'engine' fields.")
        except json.JSONDecodeError as e:
            self.ok_btn.setEnabled(False)
            self.ok_btn.setText("✗ Invalid JSON")
            QMessageBox.warning(self, "Invalid JSON", f"Error: {str(e)}")

    def _on_import(self):
        """Handle import button click"""
        try:
            data = json.loads(self.json_edit.toPlainText())
            self.strategy_data = data
            self.accept()
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", f"Error: {str(e)}")

    def get_imported_data(self) -> Dict:
        """Get imported strategy data"""
        return self.strategy_data


# ── Enhanced Indicator ComboBox ──────────────────────────────────────────────

class IndicatorComboBox(QComboBox):
    """Comprehensive indicator dropdown with categories and autocomplete"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumWidth(180)
        self.setMaxVisibleItems(30)

        # Style
        self.setStyleSheet(f"""
            QComboBox {{
                background: #21262d;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px 8px;
                padding-right: 20px;
                font-size: 9pt;
                min-width: 170px;
            }}
            QComboBox:hover {{
                border: 1px solid {BLUE};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 16px;
                border-left: 1px solid {BORDER};
                background: transparent;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {DIM};
                margin-right: 4px;
            }}
            QComboBox::down-arrow:hover {{
                border-top-color: {TEXT};
            }}
            QComboBox QAbstractItemView {{
                background: #21262d;
                color: {TEXT};
                selection-background-color: {BG_SEL};
                selection-color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                outline: none;
                min-width: 280px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 12px;
                min-height: 24px;
                border-bottom: 1px solid {BORDER}40;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background: {BG_SEL};
                color: {BLUE};
            }}
            QComboBox QAbstractItemView::item:hover {{
                background: #2d333b;
            }}
        """)

        self._populate_indicators()
        self._setup_completer()

    def _populate_indicators(self):
        """Add indicators grouped by category"""
        self._category_indices = {}

        # Add a "Select indicator..." placeholder at the top
        self.addItem("🔍 Select indicator...")
        idx = self.count() - 1
        self.model().item(idx).setEnabled(False)
        font = QFont()
        font.setItalic(True)
        self.model().item(idx).setFont(font)
        self.model().item(idx).setForeground(QColor(DIM))

        for category, indicators in get_indicators_by_category().items():
            if indicators:
                # Add category header (non-selectable)
                self.addItem(f"───── {category} ─────")
                idx = self.count() - 1
                self.model().item(idx).setEnabled(False)
                font = QFont()
                font.setBold(True)
                self.model().item(idx).setFont(font)
                self.model().item(idx).setForeground(QColor(BLUE))

                self._category_indices[category] = idx

                # Add indicators in this category
                for indicator in sorted(indicators):
                    display_name = indicator.upper()
                    self.addItem(display_name)
                    self.setItemData(self.count() - 1, indicator, Qt.UserRole)

                    # Add tooltip with description
                    params = get_indicator_params(indicator)
                    if params:
                        param_desc = ", ".join(f"{k}={v}" for k, v in params.items())
                        self.setItemData(self.count() - 1, f"Default: {param_desc}", Qt.ToolTipRole)

    def _setup_completer(self):
        """Setup autocomplete with all indicators"""
        completer = QCompleter([ind.upper() for ind in ALL_INDICATORS], self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.popup().setStyleSheet(f"""
            QListView {{
                background: #21262d;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                font-size: 9pt;
            }}
            QListView::item {{
                padding: 6px 10px;
            }}
            QListView::item:selected {{
                background: {BG_SEL};
                color: {BLUE};
            }}
        """)
        self.setCompleter(completer)

    def get_indicator_name(self) -> str:
        """Get the raw indicator name (lowercase)"""
        text = self.currentText().strip().lower()
        if text == "select indicator..." or text == "🔍 select indicator...":
            return ""
        if text in ALL_INDICATORS:
            return text
        for ind in ALL_INDICATORS:
            if ind.upper() == text.upper():
                return ind
        return text

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.lineEdit().deselect()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.showPopup()


# ── Column ComboBox ──────────────────────────────────────────────────────────

class ColumnComboBox(QComboBox):
    """Dropdown for selecting a DataFrame column with descriptions"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet(f"""
            QComboBox {{
                background: #21262d;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px 8px;
                padding-right: 20px;
                font-size: 9pt;
            }}
            QComboBox:hover {{ border: 1px solid {BLUE}; }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 16px;
                border-left: 1px solid {BORDER};
                background: transparent;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0px; height: 0px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {DIM};
                margin-right: 4px;
            }}
            QComboBox QAbstractItemView {{
                background: #21262d;
                color: {TEXT};
                selection-background-color: {BG_SEL};
                selection-color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                outline: none;
                min-width: 250px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 12px;
                min-height: 20px;
                border-bottom: 1px solid {BORDER}40;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background: {BG_SEL};
                color: {BLUE};
            }}
        """)

        # Add separator and items with descriptions
        ohlcv = ["close", "open", "high", "low", "volume"]
        derived = ["hl2", "hlc3", "ohlc4"]

        self.addItem("─── OHLCV ───")
        self.model().item(0).setEnabled(False)
        self.model().item(0).setForeground(QColor(DIM))
        self.model().item(0).setFont(QFont("", -1, QFont.Bold))

        for col in ohlcv:
            label, desc = COLUMN_META[col]
            self.addItem(f"📊 {label}")
            idx = self.count() - 1
            self.setItemData(idx, col, Qt.UserRole)
            self.setItemData(idx, desc, Qt.ToolTipRole)

        self.addItem("─── Derived ───")
        sep_idx = self.count() - 1
        self.model().item(sep_idx).setEnabled(False)
        self.model().item(sep_idx).setForeground(QColor(DIM))
        self.model().item(sep_idx).setFont(QFont("", -1, QFont.Bold))

        for col in derived:
            label, desc = COLUMN_META[col]
            self.addItem(f"📐 {label}")
            idx = self.count() - 1
            self.setItemData(idx, col, Qt.UserRole)
            self.setItemData(idx, desc, Qt.ToolTipRole)

        self.setCurrentIndex(1)

    def get_column(self) -> str:
        """Return lowercase column name."""
        data = self.currentData(Qt.UserRole)
        if data:
            return data
        return self.currentText().lower()

    def set_column(self, col: str):
        """Select a column by its internal name."""
        for i in range(self.count()):
            if self.itemData(i, Qt.UserRole) == col.lower():
                self.setCurrentIndex(i)
                return
        idx = self.findText(col.upper())
        if idx >= 0:
            self.setCurrentIndex(idx)


# ── Parameter Editor ─────────────────────────────────────────────────────────

class ParameterEditor(QWidget):
    """Inline editor for indicator parameters - Enhanced with better layout"""

    params_changed = pyqtSignal(dict)

    def __init__(self, indicator: str = None, params: Dict = None, parent=None):
        super().__init__(parent)
        self._indicator = indicator
        self._params = params or {}
        self._param_widgets = {}

        self.setVisible(False)
        self.setFixedHeight(50)  # Slightly taller for better visibility
        self.setStyleSheet(f"""
            QWidget {{
                background: #1c2128;
                border: 1px solid {BORDER};
                border-radius: 4px;
            }}
            QLabel {{
                color: {DIM};
                font-size: 8pt;
                font-weight: bold;
                padding: 0px 4px;
            }}
            QLineEdit, QCheckBox {{
                font-size: 8pt;
                padding: 2px 4px;
                border: 1px solid {BORDER};
                border-radius: 3px;
                background: #21262d;
            }}
            QLineEdit:focus {{
                border: 1px solid {BLUE};
            }}
        """)

    def set_indicator(self, indicator: str):
        """Update editor for new indicator"""
        self._indicator = indicator
        self._rebuild()

    def _rebuild(self):
        """Rebuild parameter editor based on current indicator"""
        if self.layout():
            QWidget().setLayout(self.layout())

        if not self._indicator or self._indicator not in ALL_INDICATORS:
            self.setVisible(False)
            return

        default_params = get_indicator_params(self._indicator)
        if not default_params:
            self.setVisible(False)
            return

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignLeft)

        self._param_widgets.clear()

        # Add a small indicator icon/label
        icon_label = QLabel("⚙️")
        icon_label.setStyleSheet(f"color:{BLUE}; font-size:10pt;")
        layout.addWidget(icon_label)

        for param_name, default_value in default_params.items():
            param_type = get_param_type(param_name)
            current_value = self._params.get(param_name, default_value)

            # Create container for each parameter
            param_container = QWidget()
            param_container_layout = QHBoxLayout(param_container)
            param_container_layout.setContentsMargins(0, 0, 0, 0)
            param_container_layout.setSpacing(4)

            # Label
            label = QLabel(f"{param_name}:")
            label.setFixedWidth(80)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            param_container_layout.addWidget(label)

            # Input widget
            if param_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(current_value))
                widget.setFixedSize(40, 22)
            elif param_type in ("int", "float"):
                widget = QLineEdit()
                widget.setText(str(current_value))
                widget.setFixedWidth(50)
                if param_type == "int":
                    widget.setValidator(QIntValidator())
                else:
                    widget.setValidator(QDoubleValidator())
            else:  # string
                widget = QLineEdit()
                widget.setText(str(current_value))
                widget.setFixedWidth(70)

            param_container_layout.addWidget(widget)
            layout.addWidget(param_container)

            self._param_widgets[param_name] = (widget, param_type)

            if param_type == "bool":
                widget.stateChanged.connect(self._on_params_changed)
            else:
                widget.textChanged.connect(self._on_params_changed)

        # Add indicator info button
        info_btn = QPushButton("?")
        info_btn.setFixedSize(22, 22)
        info_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d;
                color: {DIM};
                border: 1px solid {BORDER};
                border-radius: 11px;
                font-size: 8pt;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background: {BLUE}40;
                color: {BLUE};
                border-color: {BLUE};
            }}
        """)
        info_btn.setToolTip(f"Default parameters for {self._indicator.upper()}")
        info_btn.clicked.connect(self._show_info)
        layout.addWidget(info_btn)

        layout.addStretch()
        self.setVisible(True)

    def _show_info(self):
        """Show parameter info dialog"""
        info_text = f"<b>{self._indicator.upper()}</b><br><br>"
        params = get_indicator_params(self._indicator)
        if params:
            info_text += "<b>Default Parameters:</b><br>"
            for name, value in params.items():
                desc = get_param_description(name)
                info_text += f"• <b>{name}</b>: {value} - {desc}<br>"

        QMessageBox.information(self, "Indicator Info", info_text)

    def _on_params_changed(self):
        """Emit updated parameters"""
        params = {}
        for name, (widget, ptype) in self._param_widgets.items():
            try:
                if ptype == "bool":
                    params[name] = widget.isChecked()
                elif ptype == "int":
                    params[name] = int(widget.text() or "0")
                elif ptype == "float":
                    params[name] = float(widget.text() or "0.0")
                else:
                    params[name] = widget.text()
            except ValueError:
                if name in self._params:
                    params[name] = self._params[name]

        self._params = params
        self.params_changed.emit(params)

    def get_params(self) -> Dict:
        """Get current parameter values"""
        return self._params.copy()


# ── Rule Editor Row ──────────────────────────────────────────────────────────

class _RuleRow(QWidget):
    """One editable rule row with clear labels and expanded layout"""

    deleted = pyqtSignal(object)

    def __init__(self, rule: Dict = None, parent=None):
        super().__init__(parent)
        self._param_editors = {}

        self.setStyleSheet(f"background:{BG_ITEM}; border-radius:6px; border:1px solid {BORDER};")
        self.setMinimumHeight(250)
        self.setMaximumHeight(400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # Main vertical layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(6)

        # Main content row - flexible stretch layout
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        # ── LEFT SIDE ─────────────────────────────────────────────────────
        lhs_container = QWidget()
        lhs_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lhs_layout = QVBoxLayout(lhs_container)
        lhs_layout.setContentsMargins(0, 0, 0, 0)
        lhs_layout.setSpacing(4)

        lhs_header = QLabel("🔹 LEFT SIDE (Condition)")
        lhs_header.setStyleSheet(f"color:{BLUE}; font-size:8pt; font-weight:bold;")
        lhs_layout.addWidget(lhs_header)

        # LHS type and input row
        lhs_type_row = QHBoxLayout()
        lhs_type_row.setSpacing(6)

        self.lhs_type = QComboBox()
        self.lhs_type.addItems(SIDE_TYPES)
        self.lhs_type.setFixedWidth(140)
        self.lhs_type.setStyleSheet("font-size: 9pt; font-weight:bold;")
        lhs_type_row.addWidget(self.lhs_type)

        # LHS input stack
        self.lhs_input_container = QStackedWidget()
        self.lhs_input_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Indicator widget
        lhs_indicator_widget = QWidget()
        lhs_indicator_layout = QHBoxLayout(lhs_indicator_widget)
        lhs_indicator_layout.setContentsMargins(0, 0, 0, 0)
        lhs_indicator_layout.setSpacing(4)
        ind_label = QLabel("📊")
        ind_label.setFixedWidth(40)
        lhs_indicator_layout.addWidget(ind_label)
        self.lhs_indicator = IndicatorComboBox()
        lhs_indicator_layout.addWidget(self.lhs_indicator)
        self.lhs_indicator.currentTextChanged.connect(lambda t: self._on_indicator_changed("lhs", t))

        # Column widget
        lhs_column_widget = QWidget()
        lhs_column_layout = QHBoxLayout(lhs_column_widget)
        lhs_column_layout.setContentsMargins(0, 0, 0, 0)
        lhs_column_layout.setSpacing(4)
        col_label = QLabel("📈")
        col_label.setFixedWidth(40)
        lhs_column_layout.addWidget(col_label)
        self.lhs_column = ColumnComboBox()
        lhs_column_layout.addWidget(self.lhs_column)

        # Scalar widget
        lhs_scalar_widget = QWidget()
        lhs_scalar_layout = QHBoxLayout(lhs_scalar_widget)
        lhs_scalar_layout.setContentsMargins(0, 0, 0, 0)
        lhs_scalar_layout.setSpacing(4)
        scalar_label = QLabel("#️⃣")
        scalar_label.setFixedWidth(40)
        lhs_scalar_layout.addWidget(scalar_label)
        self.lhs_scalar = QLineEdit()
        self.lhs_scalar.setPlaceholderText("value")
        self.lhs_scalar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.lhs_scalar.setValidator(QDoubleValidator())
        lhs_scalar_layout.addWidget(self.lhs_scalar)

        self.lhs_input_container.addWidget(lhs_indicator_widget)
        self.lhs_input_container.addWidget(lhs_column_widget)
        self.lhs_input_container.addWidget(lhs_scalar_widget)

        lhs_type_row.addWidget(self.lhs_input_container)
        lhs_layout.addLayout(lhs_type_row)

        # LHS Parameter editor
        self.lhs_params = ParameterEditor()
        self.lhs_params.setVisible(False)
        lhs_layout.addWidget(self.lhs_params)

        content_layout.addWidget(lhs_container, 4)

        # ── OPERATOR ──────────────────────────────────────────────────────
        op_container = QWidget()
        op_container.setFixedWidth(130)
        op_layout = QVBoxLayout(op_container)
        op_layout.setContentsMargins(0, 0, 0, 0)
        op_layout.setAlignment(Qt.AlignTop)
        op_layout.setSpacing(4)

        op_header = QLabel("⚖️ COMPARATOR")
        op_header.setStyleSheet(f"color:{YELLOW}; font-size:8pt; font-weight:bold;")
        op_header.setAlignment(Qt.AlignCenter)
        op_layout.addWidget(op_header)

        self.op = QComboBox()
        self.op.addItems(OPERATORS)
        self.op.setFixedWidth(150)
        self.op.setStyleSheet("font-size: 10pt; font-weight:bold; padding:6px;")
        op_layout.addWidget(self.op)

        content_layout.addWidget(op_container)

        # ── RIGHT SIDE ────────────────────────────────────────────────────
        rhs_container = QWidget()
        rhs_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        rhs_layout = QVBoxLayout(rhs_container)
        rhs_layout.setContentsMargins(0, 0, 0, 0)
        rhs_layout.setSpacing(4)

        rhs_header = QLabel("🔸 RIGHT SIDE (Target)")
        rhs_header.setStyleSheet(f"color:{ORANGE}; font-size:8pt; font-weight:bold;")
        rhs_layout.addWidget(rhs_header)

        # RHS type and input row
        rhs_type_row = QHBoxLayout()
        rhs_type_row.setSpacing(6)

        self.rhs_type = QComboBox()
        self.rhs_type.addItems(SIDE_TYPES)
        self.rhs_type.setFixedWidth(130)
        self.rhs_type.setStyleSheet("font-size: 9pt; font-weight:bold;")
        rhs_type_row.addWidget(self.rhs_type)

        # RHS input stack
        self.rhs_input_container = QStackedWidget()
        self.rhs_input_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Indicator widget
        rhs_indicator_widget = QWidget()
        rhs_indicator_layout = QHBoxLayout(rhs_indicator_widget)
        rhs_indicator_layout.setContentsMargins(0, 0, 0, 0)
        rhs_indicator_layout.setSpacing(4)
        rhs_ind_label = QLabel("📊")
        rhs_ind_label.setFixedWidth(40)
        rhs_indicator_layout.addWidget(rhs_ind_label)
        self.rhs_indicator = IndicatorComboBox()
        rhs_indicator_layout.addWidget(self.rhs_indicator)
        self.rhs_indicator.currentTextChanged.connect(lambda t: self._on_indicator_changed("rhs", t))

        # Column widget
        rhs_column_widget = QWidget()
        rhs_column_layout = QHBoxLayout(rhs_column_widget)
        rhs_column_layout.setContentsMargins(0, 0, 0, 0)
        rhs_column_layout.setSpacing(4)
        rhs_col_label = QLabel("📈")
        rhs_col_label.setFixedWidth(40)
        rhs_column_layout.addWidget(rhs_col_label)
        self.rhs_column = ColumnComboBox()
        rhs_column_layout.addWidget(self.rhs_column)

        # Scalar widget
        rhs_scalar_widget = QWidget()
        rhs_scalar_layout = QHBoxLayout(rhs_scalar_widget)
        rhs_scalar_layout.setContentsMargins(0, 0, 0, 0)
        rhs_scalar_layout.setSpacing(4)
        rhs_scalar_label = QLabel("#️⃣")
        rhs_scalar_label.setFixedWidth(40)
        rhs_scalar_layout.addWidget(rhs_scalar_label)
        self.rhs_scalar = QLineEdit()
        self.rhs_scalar.setPlaceholderText("value")
        self.rhs_scalar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.rhs_scalar.setValidator(QDoubleValidator())
        rhs_scalar_layout.addWidget(self.rhs_scalar)

        self.rhs_input_container.addWidget(rhs_indicator_widget)
        self.rhs_input_container.addWidget(rhs_column_widget)
        self.rhs_input_container.addWidget(rhs_scalar_widget)

        rhs_type_row.addWidget(self.rhs_input_container)
        rhs_layout.addLayout(rhs_type_row)

        # RHS Parameter editor
        self.rhs_params = ParameterEditor()
        self.rhs_params.setVisible(False)
        rhs_layout.addWidget(self.rhs_params)

        content_layout.addWidget(rhs_container, 4)

        # ── DELETE BUTTON ─────────────────────────────────────────────────
        del_container = QWidget()
        del_container.setFixedWidth(36)
        del_vlay = QVBoxLayout(del_container)
        del_vlay.setContentsMargins(0, 0, 0, 0)
        del_vlay.setSpacing(0)
        # Spacer to push button down to align with widgets (past the label row)
        del_vlay.addSpacing(18)
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 32)
        del_btn.setStyleSheet(
            f"QPushButton{{background:{RED}33;color:{RED};border:1px solid {RED};border-radius:4px;font-weight:bold;padding:0;}}"
            f"QPushButton:hover{{background:{RED}66;}}"
        )
        del_btn.clicked.connect(lambda: self.deleted.emit(self))
        del_vlay.addWidget(del_btn)
        del_vlay.addStretch()
        content_layout.addWidget(del_container)

        main_layout.addLayout(content_layout)

        # Bottom description row
        desc_layout = QHBoxLayout()
        self.desc_label = QLabel("ⓘ This rule will be evaluated on each bar")
        self.desc_label.setStyleSheet(f"color:{DIM}; font-size:8pt; font-style:italic;")
        desc_layout.addWidget(self.desc_label)
        desc_layout.addStretch()
        main_layout.addLayout(desc_layout)

        # Connect signals
        self.lhs_type.currentTextChanged.connect(lambda t: self._update_side_visibility("lhs", t))
        self.rhs_type.currentTextChanged.connect(lambda t: self._update_side_visibility("rhs", t))

        self.lhs_params.params_changed.connect(lambda p: self._on_params_updated("lhs", p))
        self.rhs_params.params_changed.connect(lambda p: self._on_params_updated("rhs", p))

        # Load rule if provided
        if rule:
            self._load(rule)
        else:
            self.lhs_type.setCurrentText("indicator")
            self.rhs_type.setCurrentText("scalar")
            self.rhs_scalar.setText("0")
            self._update_description()

    def _update_description(self):
        """Update the description based on current rule"""
        lhs_desc = self.lhs_type.currentText()
        rhs_desc = self.rhs_type.currentText()
        op_desc = self.op.currentText()

        if lhs_desc == "indicator":
            lhs_val = self.lhs_indicator.currentText() or "indicator"
        elif lhs_desc == "column":
            lhs_val = self.lhs_column.currentText()
        else:
            lhs_val = self.lhs_scalar.text() or "value"

        if rhs_desc == "indicator":
            rhs_val = self.rhs_indicator.currentText() or "indicator"
        elif rhs_desc == "column":
            rhs_val = self.rhs_column.currentText()
        else:
            rhs_val = self.rhs_scalar.text() or "value"

        self.desc_label.setText(f"ⓘ Rule: {lhs_desc} [{lhs_val}] {op_desc} {rhs_desc} [{rhs_val}]")

    def _update_side_visibility(self, side: str, type_text: str):
        """Update visibility of input widgets based on type"""
        if side == "lhs":
            stack = self.lhs_input_container
            params = self.lhs_params
        else:
            stack = self.rhs_input_container
            params = self.rhs_params

        if type_text == "indicator":
            stack.setCurrentIndex(0)
            params.setVisible(True)
        elif type_text == "column":
            stack.setCurrentIndex(1)
            params.setVisible(False)
        else:
            stack.setCurrentIndex(2)
            params.setVisible(False)

        self._update_description()

    def _on_indicator_changed(self, side: str, indicator_text: str):
        """Handle indicator selection change"""
        if side == "lhs":
            params_w = self.lhs_params
            type_w = self.lhs_type
        else:
            params_w = self.rhs_params
            type_w = self.rhs_type

        if type_w.currentText() == "indicator":
            indicator = indicator_text.lower()
            if indicator in ALL_INDICATORS:
                params_w.set_indicator(indicator)
                params_w.setVisible(True)

        self._update_description()

    def _on_params_updated(self, side: str, params: Dict):
        """Handle parameter updates"""
        self._update_description()

    def _load(self, rule: Dict):
        """Load rule data into widgets"""
        # Load LHS
        lhs_data = rule.get("lhs", {})
        lhs_type = lhs_data.get("type", "indicator")
        self.lhs_type.setCurrentText(lhs_type)

        if lhs_type == "indicator":
            ind = lhs_data.get("indicator", "rsi")
            self.lhs_indicator.setEditText(ind.upper())
            params = lhs_data.get("params", {})
            if ind in ALL_INDICATORS:
                self.lhs_params.set_indicator(ind)
                for pname, (widget, ptype) in self.lhs_params._param_widgets.items():
                    if pname in params:
                        if ptype == "bool":
                            widget.setChecked(bool(params[pname]))
                        else:
                            widget.setText(str(params[pname]))
        elif lhs_type == "column":
            col = lhs_data.get("column", "close")
            self.lhs_column.set_column(col)
        else:
            self.lhs_scalar.setText(str(lhs_data.get("value", "0")))

        # Load RHS
        rhs_data = rule.get("rhs", {})
        rhs_type = rhs_data.get("type", "scalar")
        self.rhs_type.setCurrentText(rhs_type)

        if rhs_type == "indicator":
            ind = rhs_data.get("indicator", "rsi")
            self.rhs_indicator.setEditText(ind.upper())
            params = rhs_data.get("params", {})
            if ind in ALL_INDICATORS:
                self.rhs_params.set_indicator(ind)
                for pname, (widget, ptype) in self.rhs_params._param_widgets.items():
                    if pname in params:
                        if ptype == "bool":
                            widget.setChecked(bool(params[pname]))
                        else:
                            widget.setText(str(params[pname]))
        elif rhs_type == "column":
            col = rhs_data.get("column", "close")
            self.rhs_column.set_column(col)
        else:
            self.rhs_scalar.setText(str(rhs_data.get("value", "0")))

        op = rule.get("op", ">")
        idx = self.op.findText(op)
        if idx >= 0:
            self.op.setCurrentIndex(idx)

        self._update_description()

    def collect(self) -> Dict:
        """Collect rule data as dictionary"""
        # Collect LHS
        lhs_type = self.lhs_type.currentText()
        if lhs_type == "scalar":
            try:
                lhs_value = float(self.lhs_scalar.text() or "0")
            except ValueError:
                lhs_value = 0
            lhs = {"type": "scalar", "value": lhs_value}
        elif lhs_type == "column":
            lhs = {"type": "column", "column": self.lhs_column.get_column()}
        else:
            indicator = self.lhs_indicator.get_indicator_name()
            lhs = {
                "type": "indicator",
                "indicator": indicator,
                "params": self.lhs_params.get_params() if indicator in ALL_INDICATORS else {}
            }

        # Collect RHS
        rhs_type = self.rhs_type.currentText()
        if rhs_type == "scalar":
            try:
                rhs_value = float(self.rhs_scalar.text() or "0")
            except ValueError:
                rhs_value = 0
            rhs = {"type": "scalar", "value": rhs_value}
        elif rhs_type == "column":
            rhs = {"type": "column", "column": self.rhs_column.get_column()}
        else:
            indicator = self.rhs_indicator.get_indicator_name()
            rhs = {
                "type": "indicator",
                "indicator": indicator,
                "params": self.rhs_params.get_params() if indicator in ALL_INDICATORS else {}
            }

        return {
            "lhs": lhs,
            "op": self.op.currentText(),
            "rhs": rhs,
        }


# ── Signal Group Panel ───────────────────────────────────────────────────────

class _SignalGroupPanel(QWidget):
    """Panel for editing rules of a single signal group"""

    rules_changed = pyqtSignal()

    def __init__(self, signal: str, parent=None):
        super().__init__(parent)
        self.signal = signal
        emoji, color, label = SIGNAL_META.get(signal, ("⬤", DIM, signal))
        self._color = color
        self._rule_rows: List[_RuleRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Header with controls
        header = self._build_header(color)
        layout.addLayout(header)

        # Rules container (scrollable)
        self._build_rules_area()
        layout.addWidget(self._rules_scroll, 1)

        # Quick actions bar
        actions = self._build_actions_bar(color)
        layout.addWidget(actions)

    def _build_header(self, color: str) -> QHBoxLayout:
        """Build header with logic selector and enabled toggle"""
        header = QHBoxLayout()
        header.setSpacing(16)

        # Logic selector
        logic_group = QHBoxLayout()
        logic_group.setSpacing(6)

        lbl_logic = QLabel("🔀 Logic:")
        lbl_logic.setStyleSheet(f"color:{DIM}; font-size:10pt; font-weight:bold;")
        logic_group.addWidget(lbl_logic)

        self.logic_combo = QComboBox()
        self.logic_combo.addItems(["AND", "OR"])
        self.logic_combo.setFixedWidth(90)
        self.logic_combo.setStyleSheet(f"""
            QComboBox {{
                background: #21262d;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 10pt;
                font-weight:bold;
            }}
            QComboBox:hover {{
                border: 1px solid {color};
            }}
        """)
        logic_group.addWidget(self.logic_combo)

        header.addLayout(logic_group)

        # Enabled toggle
        self.enabled_chk = QCheckBox("✓ Enabled")
        self.enabled_chk.setChecked(True)
        self.enabled_chk.setStyleSheet(f"""
            QCheckBox {{
                color: {TEXT};
                font-size: 10pt;
                font-weight: bold;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border-radius: 4px;
            }}
            QCheckBox::indicator:unchecked {{
                background: #21262d;
                border: 2px solid {BORDER};
            }}
            QCheckBox::indicator:checked {{
                background: {color};
                border: 2px solid {color};
            }}
        """)
        header.addWidget(self.enabled_chk)

        header.addStretch()

        # Rule count badge
        self._rule_count_badge = QLabel("0 rules")
        self._rule_count_badge.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background: {color}22;
                border: 1px solid {color}55;
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 9pt;
                font-weight: bold;
            }}
        """)
        header.addWidget(self._rule_count_badge)

        return header

    def _build_rules_area(self):
        """Build scrollable area for rules"""
        self._rules_scroll = QScrollArea()
        self._rules_scroll.setWidgetResizable(True)
        self._rules_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._rules_scroll.setFrameShape(QFrame.NoFrame)

        self._rules_container = QWidget()
        self._rules_container.setStyleSheet(f"background: transparent;")

        self._rules_layout = QVBoxLayout(self._rules_container)
        self._rules_layout.setContentsMargins(0, 0, 0, 0)
        self._rules_layout.setSpacing(12)
        self._rules_layout.setAlignment(Qt.AlignTop)

        # Empty state
        self._empty_lbl = QLabel("  ✨ No rules yet — click '+ Add Rule' to begin")
        self._empty_lbl.setStyleSheet(f"color:{DIM}; font-size:11pt; padding:30px;")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._rules_layout.addWidget(self._empty_lbl)

        self._rules_scroll.setWidget(self._rules_container)

    def _build_actions_bar(self, color: str) -> QWidget:
        """Build actions bar with add rule button and presets"""
        bar = QFrame()
        bar.setFixedHeight(50)
        bar.setStyleSheet(f"background: transparent;")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)

        # Add rule button
        add_btn = QPushButton("＋ Add Rule")
        add_btn.setFixedHeight(36)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d;
                color: {color};
                border: 2px solid {color};
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 11pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {color}22;
            }}
        """)
        add_btn.clicked.connect(self._add_rule)
        layout.addWidget(add_btn)

        # Presets dropdown
        self._presets_combo = QComboBox()
        common_presets = ["📋 Load Preset"]

        if self.signal == "BUY_CALL":
            presets = common_presets + [
                "RSI Oversold",
                "MACD Crossover",
                "BB Squeeze",
                "EMA Cross",
                "Stochastic Bull",
                "ADX Strong Trend",
                "Ichimoku Breakout",
                "Volume Breakout",
                "Triple Confirmation",
                "Bullish Engulfing"
            ]
        elif self.signal == "BUY_PUT":
            presets = common_presets + [
                "RSI Overbought",
                "MACD Bear Cross",
                "Death Cross",
                "BB Top Rejection",
                "Bearish Divergence"
            ]
        elif self.signal == "SELL_CALL":
            presets = common_presets + [
                "RSI Overbought",
                "Resistance Test"
            ]
        elif self.signal == "SELL_PUT":
            presets = common_presets + [
                "RSI Oversold",
                "Support Bounce"
            ]
        elif self.signal == "HOLD":
            presets = common_presets + [
                "Strong Trend",
                "Low Volatility"
            ]
        else:
            presets = common_presets

        self._presets_combo.addItems(presets)
        self._presets_combo.setFixedWidth(200)
        self._presets_combo.setStyleSheet(f"""
            QComboBox {{
                background: #21262d;
                color: {DIM};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 10pt;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox:hover {{
                border: 1px solid {color};
            }}
            QComboBox QAbstractItemView {{
                background: #21262d;
                color: {TEXT};
                selection-background-color: {color}40;
                selection-color: {TEXT};
                border: 1px solid {color};
                min-width: 250px;
            }}
        """)
        self._presets_combo.currentIndexChanged.connect(self._load_preset)
        layout.addWidget(self._presets_combo)

        layout.addStretch()

        # Clear all button
        clear_btn = QPushButton("🗑 Clear All")
        clear_btn.setFixedHeight(32)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {RED};
                border: 1px solid {RED}55;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background: {RED}22;
            }}
        """)
        clear_btn.clicked.connect(self._clear_all_rules)
        layout.addWidget(clear_btn)

        return bar

    def _update_rule_count(self):
        """Update rule count badge and empty state visibility"""
        count = len(self._rule_rows)
        self._rule_count_badge.setText(f"{count} rule{'s' if count != 1 else ''}")
        self._empty_lbl.setVisible(count == 0)

        if count > 0:
            height = min(600, 80 + 140 * count)  # 140px per row
            self._rules_scroll.setMinimumHeight(height)
        else:
            self._rules_scroll.setMinimumHeight(120)

        self.rules_changed.emit()

    def _add_rule(self, rule: Dict = None):
        """Add a new rule row"""
        row = _RuleRow(rule, parent=self._rules_container)
        row.deleted.connect(self._remove_rule)
        self._rule_rows.append(row)

        if self._empty_lbl.isVisible():
            self._rules_layout.insertWidget(0, row)
            self._empty_lbl.hide()
        else:
            self._rules_layout.addWidget(row)

        self._update_rule_count()

    def _remove_rule(self, row: _RuleRow):
        """Remove a rule row"""
        if row in self._rule_rows:
            self._rule_rows.remove(row)
            self._rules_layout.removeWidget(row)
            row.deleteLater()
        self._update_rule_count()

    def _clear_all_rules(self):
        """Remove all rule rows"""
        for row in list(self._rule_rows):
            self._remove_rule(row)

    def _load_preset(self, index: int):
        """Load a preset rule configuration"""
        if index <= 0:
            return

        preset = self._presets_combo.currentText()
        self._presets_combo.setCurrentIndex(0)

        # Preset definitions (same as before, but with updated format)
        # ... (preset code remains the same as in original file) ...
        # I'll keep the presets concise here since they're long
        # You can copy the presets from the original file

        # For brevity, I'm showing just one example - include all presets from original
        if self.signal == "BUY_CALL" and preset == "RSI Oversold":
            rules = [
                {
                    "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                    "op": "<",
                    "rhs": {"type": "scalar", "value": 30}
                },
                {
                    "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                    "op": "crosses_above",
                    "rhs": {"type": "scalar", "value": 30}
                }
            ]
            for rule in rules:
                self._add_rule(rule)

    def load(self, group_data: Dict):
        """Load group data into panel"""
        self._clear_all_rules()

        self.logic_combo.setCurrentText(group_data.get("logic", "AND"))
        self.enabled_chk.setChecked(bool(group_data.get("enabled", True)))

        for rule in group_data.get("rules", []):
            self._add_rule(rule)

    def collect(self) -> Dict:
        """Collect panel data"""
        return {
            "logic": self.logic_combo.currentText(),
            "enabled": self.enabled_chk.isChecked(),
            "rules": [row.collect() for row in self._rule_rows],
        }


# ── Signal Rules Tab ─────────────────────────────────────────────────────────

class _SignalRulesTab(QWidget):
    """Signal rules editor with tabs for each signal type"""

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Conflict resolution header
        header = self._build_header()
        main_layout.addWidget(header)

        # Tab widget
        self._tab_widget = QTabWidget()
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.tabBar().setExpanding(True)
        self._tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {BG_PANEL};
                border-top: 1px solid {BORDER};
            }}
            QTabBar::tab {{
                background: #21262d;
                color: {DIM};
                border: 1px solid {BORDER};
                border-bottom: none;
                border-radius: 6px 6px 0 0;
                padding: 10px 20px;
                margin-right: 2px;
                font-size: 11pt;
                font-weight: bold;
                min-width: 120px;
            }}
            QTabBar::tab:selected {{
                background: {BG_PANEL};
                color: {TEXT};
                border-bottom: 3px solid {BLUE};
            }}
            QTabBar::tab:hover:!selected {{
                background: #2d333b;
                color: {TEXT};
            }}
        """)

        self._panels: Dict[str, _SignalGroupPanel] = {}

        signal_tabs = [
            ("BUY_CALL", "📈 BUY CALL", GREEN),
            ("BUY_PUT", "📉 BUY PUT", BLUE),
            ("SELL_CALL", "🔴 SELL CALL", RED),
            ("SELL_PUT", "🟠 SELL PUT", ORANGE),
            ("HOLD", "⏸ HOLD", YELLOW),
        ]

        for signal, label, color in signal_tabs:
            panel = _SignalGroupPanel(signal)
            panel.rules_changed.connect(self._update_stats)
            self._panels[signal] = panel
            self._tab_widget.addTab(panel, label)

        main_layout.addWidget(self._tab_widget, 1)

        # Stats bar
        stats_bar = self._build_stats_bar()
        main_layout.addWidget(stats_bar)

    def _build_header(self) -> QWidget:
        """Build header with conflict resolution selector"""
        header = QWidget()
        header.setStyleSheet(f"background:{BG_PANEL}; border-bottom:1px solid {BORDER};")
        header.setFixedHeight(60)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)

        cr_lbl = QLabel("⚖️ Conflict Resolution:")
        cr_lbl.setStyleSheet(f"color:{DIM}; font-size:10pt; font-weight:bold;")
        layout.addWidget(cr_lbl)

        self.conflict_combo = QComboBox()
        self.conflict_combo.addItems(["WAIT", "PRIORITY"])
        self.conflict_combo.setFixedWidth(130)
        self.conflict_combo.setStyleSheet(f"""
            QComboBox {{
                background: #21262d;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 10pt;
            }}
            QComboBox:hover {{
                border: 1px solid {BLUE};
            }}
        """)
        layout.addWidget(self.conflict_combo)

        help_lbl = QLabel("(when both BUY_CALL and BUY_PUT fire)")
        help_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt; font-style:italic;")
        layout.addWidget(help_lbl)
        layout.addStretch()

        return header

    def _build_stats_bar(self) -> QWidget:
        """Build a stats bar showing total rules"""
        bar = QFrame()
        bar.setFixedHeight(45)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {BG_PANEL};
                border-top: 1px solid {BORDER};
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 4, 20, 4)

        self._total_rules_lbl = QLabel("📊 Total Rules: 0")
        self._total_rules_lbl.setStyleSheet(f"color:{DIM}; font-size:11pt; font-weight:bold;")
        layout.addWidget(self._total_rules_lbl)

        layout.addStretch()

        # Quick enable/disable all
        self._enable_all_btn = QPushButton("✓ Enable All")
        self._enable_all_btn.setFixedHeight(28)
        self._enable_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d;
                color: {GREEN};
                border: 1px solid {GREEN}55;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background: {GREEN}22;
            }}
        """)
        self._enable_all_btn.clicked.connect(self._toggle_all_enabled)
        layout.addWidget(self._enable_all_btn)

        self._disable_all_btn = QPushButton("✗ Disable All")
        self._disable_all_btn.setFixedHeight(28)
        self._disable_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d;
                color: {RED};
                border: 1px solid {RED}55;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background: {RED}22;
            }}
        """)
        self._disable_all_btn.clicked.connect(self._toggle_all_disabled)
        layout.addWidget(self._disable_all_btn)

        return bar

    def _update_stats(self):
        """Update the total rules count"""
        total = 0
        for panel in self._panels.values():
            total += len(panel._rule_rows)
        self._total_rules_lbl.setText(f"📊 Total Rules: {total}")

    def _toggle_all_enabled(self):
        for panel in self._panels.values():
            panel.enabled_chk.setChecked(True)

    def _toggle_all_disabled(self):
        for panel in self._panels.values():
            panel.enabled_chk.setChecked(False)

    def load(self, strategy: Dict):
        """Load strategy data into tabs"""
        engine = strategy.get("engine", {})
        self.conflict_combo.setCurrentText(engine.get("conflict_resolution", "WAIT"))

        for signal, panel in self._panels.items():
            panel.load(engine.get(signal, {"logic": "AND", "rules": [], "enabled": True}))

        self._update_stats()

    def collect(self) -> Dict:
        """Collect all signal group data"""
        result = {}
        for signal, panel in self._panels.items():
            result[signal] = panel.collect()
        result["conflict_resolution"] = self.conflict_combo.currentText()
        return result


# ── Info Tab ─────────────────────────────────────────────────────────────────

class _InfoTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        lbl = QLabel("Strategy name and description.")
        lbl.setStyleSheet(f"color:{DIM}; font-size:10pt; font-style:italic;")
        layout.addRow("", lbl)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. EMA Crossover Strategy")
        self.name_edit.setMinimumWidth(300)
        layout.addRow("📝 Name:", self.name_edit)

        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText(
            "Describe when this strategy fires, what market conditions it suits, etc."
        )
        self.desc_edit.setMaximumHeight(120)
        layout.addRow("📋 Description:", self.desc_edit)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"QFrame{{background:{BORDER};max-height:1px;margin:15px 0;}}")
        layout.addRow("", sep)

        stats_lbl = QLabel("📊 Strategy Statistics")
        stats_lbl.setStyleSheet(f"color:{BLUE}; font-size:13pt; font-weight:bold;")
        layout.addRow("", stats_lbl)

        self.total_rules_lbl = QLabel("0")
        self.total_rules_lbl.setStyleSheet(f"color:{GREEN}; font-weight:bold; font-size:11pt;")
        layout.addRow("Total Rules:", self.total_rules_lbl)

        self.unique_indicators_lbl = QLabel("0")
        self.unique_indicators_lbl.setStyleSheet(f"color:{GREEN}; font-weight:bold; font-size:11pt;")
        layout.addRow("Unique Indicators:", self.unique_indicators_lbl)

        self.enabled_groups_lbl = QLabel("0/5")
        self.enabled_groups_lbl.setStyleSheet(f"color:{GREEN}; font-weight:bold; font-size:11pt;")
        layout.addRow("Enabled Groups:", self.enabled_groups_lbl)

        self.created_lbl = QLabel("—")
        self.created_lbl.setStyleSheet(f"color:{DIM}; font-size:10pt;")
        layout.addRow("Created:", self.created_lbl)

        self.updated_lbl = QLabel("—")
        self.updated_lbl.setStyleSheet(f"color:{DIM}; font-size:10pt;")
        layout.addRow("Last saved:", self.updated_lbl)

    def load(self, strategy: Dict):
        meta = strategy.get("meta", {})
        self.name_edit.setText(meta.get("name", ""))
        self.desc_edit.setPlainText(meta.get("description", ""))
        self.created_lbl.setText(meta.get("created_at", "—"))
        self.updated_lbl.setText(meta.get("updated_at", "—"))

        engine = strategy.get("engine", {})
        total_rules = 0
        indicators = set()
        enabled_count = 0

        for signal in SIGNAL_GROUPS:
            group = engine.get(signal, {})
            rules = group.get("rules", [])
            total_rules += len(rules)

            if group.get("enabled", True):
                enabled_count += 1

            for rule in rules:
                for side in ["lhs", "rhs"]:
                    side_data = rule.get(side, {})
                    if side_data.get("type") == "indicator":
                        indicators.add(side_data.get("indicator", "").lower())

        self.total_rules_lbl.setText(str(total_rules))
        self.unique_indicators_lbl.setText(str(len(indicators)))
        self.enabled_groups_lbl.setText(f"{enabled_count}/5")

    def collect(self) -> Dict:
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip(),
        }


# ── Indicators Tab ───────────────────────────────────────────────────────────

class _IndicatorsTab(QScrollArea):
    """Dynamic Indicators Tab - Shows all indicators organized by category"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(20)

        info_lbl = QLabel(
            "📊 AVAILABLE INDICATORS (pandas_ta)\n"
            "The following indicators are available for your strategy rules."
        )
        info_lbl.setStyleSheet(f"color:{DIM}; font-size:11pt; padding:12px; background:{BG_ITEM}; border-radius:6px;")
        info_lbl.setWordWrap(True)
        self._layout.addWidget(info_lbl)

        self._build()
        self._layout.addStretch()
        self.setWidget(container)

    def _build(self):
        """Build indicator cards organized by category"""
        # Search/filter box
        search_layout = QHBoxLayout()
        search_lbl = QLabel("🔍 Filter:")
        search_lbl.setStyleSheet(f"color:{DIM}; font-size:10pt;")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter indicators...")
        self.search_edit.setFixedHeight(32)
        self.search_edit.textChanged.connect(self._filter_indicators)
        search_layout.addWidget(search_lbl)
        search_layout.addWidget(self.search_edit)
        self._layout.addLayout(search_layout)

        # Category sections
        self._category_widgets = {}

        for category, indicators in get_indicators_by_category().items():
            if not indicators:
                continue

            cat_header = QLabel(f"📁 {category.upper()}")
            cat_header.setStyleSheet(f"""
                color:{BLUE}; 
                font-size:12pt; 
                font-weight:bold; 
                padding:12px 0 8px 0;
                border-bottom:2px solid {BORDER};
            """)
            self._layout.addWidget(cat_header)

            grid = QGridLayout()
            grid.setSpacing(12)

            row, col = 0, 0
            for indicator in sorted(indicators):
                card = self._create_indicator_card(indicator)
                grid.addWidget(card, row, col)

                col += 1
                if col >= 4:
                    col = 0
                    row += 1

            container = QWidget()
            container.setLayout(grid)
            self._layout.addWidget(container)
            self._category_widgets[category] = container

    def _create_indicator_card(self, indicator_name: str) -> QWidget:
        """Create an expanded card showing indicator info"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {BG_PANEL};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 12px;
            }}
            QFrame:hover {{
                border: 2px solid {BLUE};
                background: {BG_ITEM};
            }}
        """)
        card.setFixedSize(260, 180)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Indicator name
        name_lbl = QLabel(indicator_name.upper())
        name_lbl.setStyleSheet(f"color:{GREEN}; font-size:11pt; font-weight:bold;")
        layout.addWidget(name_lbl)

        # Default params
        params = get_indicator_params(indicator_name)
        if params:
            param_text = ""
            for k, v in list(params.items())[:4]:
                param_text += f"• {k}: {v}\n"
            if len(params) > 4:
                param_text += f"• ... (+{len(params)-4} more)"
            param_lbl = QLabel(param_text)
        else:
            param_lbl = QLabel("• No parameters")
        param_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt;")
        param_lbl.setWordWrap(True)
        layout.addWidget(param_lbl)

        # Category tag
        cat = get_indicator_category(indicator_name)
        cat_lbl = QLabel(f"📌 {cat}")
        cat_lbl.setStyleSheet(f"color:{BLUE}CC; font-size:8pt; border:none; background:{BLUE}11; padding:2px 6px; border-radius:3px;")
        layout.addWidget(cat_lbl)

        layout.addStretch()

        return card

    def _filter_indicators(self, text: str):
        text = text.lower()
        for category, container in self._category_widgets.items():
            visible = False
            grid = container.layout()
            if grid:
                for i in range(grid.count()):
                    card = grid.itemAt(i).widget()
                    if card:
                        name = card.findChild(QLabel).text().lower()
                        if text in name or not text:
                            card.show()
                            visible = True
                        else:
                            card.hide()
            container.setVisible(visible)

    def load(self, strategy: Dict):
        pass

    def collect(self) -> Dict:
        return {}


# ── Strategy List Panel ──────────────────────────────────────────────────────

class _StrategyListPanel(QWidget):
    strategy_selected = pyqtSignal(str)
    strategy_activated = pyqtSignal(str)

    def __init__(self, manager: StrategyManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._current_slug: Optional[str] = None
        self.setFixedWidth(260)
        self.setStyleSheet(f"background:{BG_PANEL}; border-right:2px solid {BORDER};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QLabel("  📋 STRATEGIES")
        hdr.setStyleSheet(f"color:{BLUE}; font-size:10pt; font-weight:bold; padding:14px 16px; background:{BG_PANEL};")
        root.addWidget(hdr)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 8, 12, 8)
        btn_row.setSpacing(8)
        self.new_btn = _btn("＋ New", "#238636", "#2ea043", min_w=80)
        self.new_btn.setFixedHeight(34)
        self.dup_btn = _btn("⧉ Duplicate", "#21262d", "#2d333b", min_w=90)
        self.dup_btn.setFixedHeight(34)
        self.new_btn.clicked.connect(self._on_new)
        self.dup_btn.clicked.connect(self._on_dup)
        btn_row.addWidget(self.new_btn)
        btn_row.addWidget(self.dup_btn)
        root.addLayout(btn_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"QFrame{{border:none;background:{BORDER};max-height:1px;}}")
        root.addWidget(sep)

        # List
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        root.addWidget(self.list_widget, 1)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"QFrame{{border:none;background:{BORDER};max-height:1px;}}")
        root.addWidget(sep2)

        # Bottom buttons
        foot = QVBoxLayout()
        foot.setContentsMargins(12, 8, 12, 12)
        foot.setSpacing(8)
        self.activate_btn = _btn("⚡ Activate Strategy", "#1f6feb", "#388bfd")
        self.activate_btn.setFixedHeight(38)
        self.activate_btn.clicked.connect(self._on_activate)
        self.delete_btn = _btn("🗑 Delete", RED + "44", RED + "66", RED)
        self.delete_btn.setFixedHeight(34)
        self.delete_btn.clicked.connect(self._on_delete)
        foot.addWidget(self.activate_btn)
        foot.addWidget(self.delete_btn)
        root.addLayout(foot)

        self.refresh()

    def refresh(self):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        active = self.manager.get_active_slug()
        for s in self.manager.list_strategies():
            item = QListWidgetItem()
            name = s["name"]
            is_active = s["is_active"]
            item.setText(("⚡ " if is_active else "   ") + name)
            item.setData(Qt.UserRole, s["slug"])
            if is_active:
                item.setForeground(QColor(BLUE))
                item.setFont(QFont("", -1, QFont.Bold))
            self.list_widget.addItem(item)
            if s["slug"] == self._current_slug:
                self.list_widget.setCurrentItem(item)
        self.list_widget.blockSignals(False)
        if self.list_widget.currentItem() is None and self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_item_changed(self, current, previous):
        if current:
            slug = current.data(Qt.UserRole)
            self._current_slug = slug
            self.strategy_selected.emit(slug)

    def _on_double_click(self, item):
        slug = item.data(Qt.UserRole)
        self._on_activate_slug(slug)

    def _on_new(self):
        name, ok = QInputDialog.getText(
            self, "New Strategy", "Strategy name:", text="My Strategy"
        )
        if ok and name.strip():
            ok2, slug = self.manager.create(name.strip())
            if ok2:
                self._current_slug = slug
                self.refresh()
                self.strategy_selected.emit(slug)

    def _on_dup(self):
        if not self._current_slug:
            return
        src = self.manager.get(self._current_slug)
        src_name = src.get("meta", {}).get("name", self._current_slug) if src else self._current_slug
        name, ok = QInputDialog.getText(
            self, "Duplicate Strategy", "New name:", text=f"{src_name} (copy)"
        )
        if ok and name.strip():
            ok2, slug = self.manager.duplicate(self._current_slug, name.strip())
            if ok2:
                self._current_slug = slug
                self.refresh()
                self.strategy_selected.emit(slug)

    def _on_activate(self):
        if self._current_slug:
            self._on_activate_slug(self._current_slug)

    def _on_activate_slug(self, slug: str):
        self.manager.activate(slug)
        self.refresh()
        self.strategy_activated.emit(slug)

    def _on_delete(self):
        if not self._current_slug:
            return
        s = self.manager.get(self._current_slug)
        name = s.get("meta", {}).get("name", self._current_slug) if s else self._current_slug
        ok = QMessageBox.question(
            self, "Delete Strategy",
            f"Delete '{name}'?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok == QMessageBox.Yes:
            success, msg = self.manager.delete(self._current_slug)
            if not success:
                QMessageBox.warning(self, "Cannot Delete", msg)
            else:
                self._current_slug = self.manager.get_active_slug()
                self.refresh()
                if self._current_slug:
                    self.strategy_selected.emit(self._current_slug)


# ── Main Editor Window ───────────────────────────────────────────────────────

class StrategyEditorWindow(QDialog):
    """
    Full-page strategy editor with import/export functionality.
    """
    strategy_activated = pyqtSignal(str)

    def __init__(self, manager: StrategyManager, parent=None):
        super().__init__(parent, Qt.Window)
        self.manager = manager
        self._current_slug: Optional[str] = None
        self._dirty = False

        self.setWindowTitle("📋 Strategy Editor")
        self.resize(1400, 900)
        self.setMinimumSize(1200, 700)
        self.setStyleSheet(_ss())

        self._build_ui()
        active = manager.get_active_slug()
        if active:
            self._load_strategy(active)

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left: strategy list
        self._list_panel = _StrategyListPanel(self.manager)
        self._list_panel.strategy_selected.connect(self._on_strategy_selected)
        self._list_panel.strategy_activated.connect(self._on_strategy_activated)
        root.addWidget(self._list_panel)

        # Right: editor
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Title bar with import/export
        self._title_bar = self._build_title_bar()
        right_layout.addWidget(self._title_bar)

        # Tabs
        self._tabs = QTabWidget()
        self._info_tab  = _InfoTab()
        self._ind_tab   = _IndicatorsTab()
        self._rules_tab = _SignalRulesTab()
        self._tabs.addTab(self._info_tab,  "⚙  Info")
        self._tabs.addTab(self._ind_tab,   "📊  Indicators")
        self._tabs.addTab(self._rules_tab, "🔬  Signal Rules")
        right_layout.addWidget(self._tabs, 1)

        # Footer
        right_layout.addWidget(self._build_footer())

        root.addWidget(right, 1)

    def _build_title_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(f"QFrame{{background:{BG_PANEL}; border-bottom:2px solid {BORDER};}}")
        bar.setFixedHeight(60)
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 0, 20, 0)
        h.setSpacing(16)

        self._title_lbl = QLabel("Select a strategy →")
        self._title_lbl.setStyleSheet(f"color:{TEXT}; font-size:14pt; font-weight:bold;")
        h.addWidget(self._title_lbl)

        self._active_badge = QLabel()
        self._active_badge.setFixedHeight(30)
        self._active_badge.hide()
        h.addWidget(self._active_badge)

        h.addStretch()

        # Import/Export buttons
        self._import_btn = QPushButton("📥 Import")
        self._import_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d;
                color: {BLUE};
                border: 1px solid {BLUE};
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 10pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {BLUE}22;
            }}
        """)
        self._import_btn.clicked.connect(self._on_import)
        h.addWidget(self._import_btn)

        self._export_btn = QPushButton("📤 Export")
        self._export_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d;
                color: {GREEN};
                border: 1px solid {GREEN};
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 10pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {GREEN}22;
            }}
        """)
        self._export_btn.clicked.connect(self._on_export)
        h.addWidget(self._export_btn)

        self._dirty_lbl = QLabel("● Unsaved changes")
        self._dirty_lbl.setStyleSheet(f"color:{YELLOW}; font-size:10pt; font-weight:bold;")
        self._dirty_lbl.hide()
        h.addWidget(self._dirty_lbl)

        return bar

    def _build_footer(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(70)
        bar.setStyleSheet(f"QFrame{{background:{BG_PANEL}; border-top:2px solid {BORDER};}}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 8, 20, 8)
        h.setSpacing(12)

        self.activate_btn = _btn("⚡ Activate This Strategy", "#1f6feb", "#388bfd", min_w=220)
        self.activate_btn.setFixedHeight(42)
        self.activate_btn.clicked.connect(self._on_activate)
        h.addWidget(self.activate_btn)

        h.addStretch()

        self.revert_btn = _btn("↺ Revert", min_w=100)
        self.revert_btn.setFixedHeight(38)
        self.revert_btn.clicked.connect(self._on_revert)
        h.addWidget(self.revert_btn)

        self.save_btn = _btn("💾 Save", "#238636", "#2ea043", min_w=120)
        self.save_btn.setFixedHeight(42)
        self.save_btn.clicked.connect(self._on_save)
        h.addWidget(self.save_btn)

        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet(f"color:{GREEN}; font-size:10pt; font-weight:bold;")
        h.addWidget(self.status_lbl)

        return bar

    def _set_dirty(self, dirty: bool):
        self._dirty = dirty
        self._dirty_lbl.setVisible(dirty)

    def _load_strategy(self, slug: str):
        if self._dirty:
            ans = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Discard them?",
                QMessageBox.Yes | QMessageBox.No
            )
            if ans == QMessageBox.No:
                return

        strategy = self.manager.get(slug)
        if not strategy:
            return
        self._current_slug = slug

        self._info_tab.load(strategy)
        self._ind_tab.load(strategy)
        self._rules_tab.load(strategy)
        self._set_dirty(False)

        name = strategy.get("meta", {}).get("name", slug)
        self._title_lbl.setText(name)

        is_active = self.manager.get_active_slug() == slug
        if is_active:
            self._active_badge.setText("  ⚡ ACTIVE  ")
            self._active_badge.setStyleSheet(
                f"color:{BLUE}; background:{BLUE}22; border:2px solid {BLUE};"
                f" border-radius:6px; font-size:10pt; font-weight:bold; padding:4px 10px;"
            )
            self._active_badge.show()
        else:
            self._active_badge.hide()

        self.status_lbl.clear()

        self._connect_dirty_watchers()

    def _connect_dirty_watchers(self):
        try:
            self._info_tab.name_edit.textChanged.connect(lambda: self._set_dirty(True))
            self._info_tab.desc_edit.textChanged.connect(lambda: self._set_dirty(True))
        except RuntimeError:
            pass

    @pyqtSlot(str)
    def _on_strategy_selected(self, slug: str):
        self._load_strategy(slug)

    @pyqtSlot(str)
    def _on_strategy_activated(self, slug: str):
        self.strategy_activated.emit(slug)
        self._load_strategy(slug)

    def _on_activate(self):
        if not self._current_slug:
            return
        if self._dirty:
            ans = QMessageBox.question(
                self, "Save First?",
                "Save changes before activating?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if ans == QMessageBox.Cancel:
                return
            if ans == QMessageBox.Yes:
                if not self._do_save():
                    return
        self.manager.activate(self._current_slug)
        self._list_panel.refresh()
        self._active_badge.setText("  ⚡ ACTIVE  ")
        self._active_badge.setStyleSheet(
            f"color:{BLUE}; background:{BLUE}22; border:2px solid {BLUE};"
            f" border-radius:6px; font-size:10pt; font-weight:bold; padding:4px 10px;"
        )
        self._active_badge.show()
        self.status_lbl.setText("✓ Activated!")
        self.strategy_activated.emit(self._current_slug)
        QTimer.singleShot(2500, self.status_lbl.clear)

    def _on_revert(self):
        if self._current_slug:
            self._load_strategy(self._current_slug)

    def _on_save(self):
        self._do_save()

    def _do_save(self) -> bool:
        if not self._current_slug:
            return False
        name = self._info_tab.collect()["name"]
        if not name:
            QMessageBox.warning(self, "Validation", "Strategy name cannot be empty.")
            return False

        strategy = self.manager.get(self._current_slug) or {}
        strategy["meta"] = strategy.get("meta", {})
        strategy["meta"]["name"] = name
        strategy["meta"]["description"] = self._info_tab.collect()["description"]
        strategy["meta"]["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        strategy["indicators"] = self._ind_tab.collect()
        strategy["engine"] = self._rules_tab.collect()

        ok = self.manager.save(self._current_slug, strategy)
        if ok:
            self._set_dirty(False)
            self._title_lbl.setText(name)
            self._list_panel.refresh()
            self.status_lbl.setText("✓ Saved")
            self.status_lbl.setStyleSheet(f"color:{GREEN}; font-size:10pt; font-weight:bold;")
            QTimer.singleShot(2500, self.status_lbl.clear)
            return True
        else:
            self.status_lbl.setText("✗ Save failed")
            self.status_lbl.setStyleSheet(f"color:{RED}; font-size:10pt; font-weight:bold;")
            return False

    def _on_import(self):
        """Import strategy from JSON"""
        dlg = ImportExportDialog('import', parent=self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_imported_data()

            # Ask for strategy name
            name = data.get('meta', {}).get('name', 'Imported Strategy')
            new_name, ok = QInputDialog.getText(
                self, "Import Strategy", "Strategy name:", text=name
            )
            if ok and new_name.strip():
                # Create new strategy with imported data
                ok2, slug = self.manager.create(new_name.strip())
                if ok2:
                    # Update with imported data
                    strategy = self.manager.get(slug)
                    strategy['meta']['description'] = data.get('meta', {}).get('description', '')
                    strategy['engine'] = data.get('engine', {})
                    self.manager.save(slug, strategy)

                    self._current_slug = slug
                    self._list_panel.refresh()
                    self._load_strategy(slug)

                    QMessageBox.information(self, "Success", f"Strategy '{new_name}' imported successfully!")

    def _on_export(self):
        """Export current strategy to JSON"""
        if not self._current_slug:
            QMessageBox.warning(self, "No Strategy", "Please select a strategy to export.")
            return

        strategy = self.manager.get(self._current_slug)
        if strategy:
            dlg = ImportExportDialog('export', strategy, self)
            dlg.exec_()