"""
strategy_editor_window.py
==========================
Full-page Strategy Editor Window with tab-based signal rules and complete indicator registry.

Layout:
  ┌─────────────────────────────────────────────────────────────┐
  │  ▸ Strategy Editor                              [×  Close]  │
  ├───────────────┬─────────────────────────────────────────────┤
  │  STRATEGIES   │   EDITOR TABS                               │
  │  ──────────── │   ┌─────────┬──────────┬────────────────┐  │
  │  [+ New]      │   │ ⚙ Info  │📊 Indics │ 🔬 Sig Rules  │  │
  │  [⧉ Dup]      │   └─────────┴──────────┴────────────────┘  │
  │               │                                             │
  │  ● Strategy A │   ┌─────────────────────────────────────┐  │
  │    Strategy B │   │ 📈 BUY CALL  📉 BUY PUT  🔴 SELL ...│  │
  │    Strategy C │   ├─────────────────────────────────────┤  │
  │               │   │  Logic: [AND▼]  ✓ Enabled           │  │
  │  [🗑 Delete]  │   │  ┌─────────────────────────────────┐ │  │
  │               │   │  │ [RSI▼] [>] [30]           [✕]  │ │  │
  │               │   │  │ [MACD▼] [crosses_above] [0] [✕]│ │  │
  │               │   │  └─────────────────────────────────┘ │  │
  │               │   │  [＋ Add Rule]  [📋 Load Preset▼]    │  │
  │               │   └─────────────────────────────────────┘  │
  │               │   [💾 Save]  [↺ Revert]                    │
  └───────────────┴─────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QFont, QIntValidator, QDoubleValidator
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget, QGridLayout,
    QHeaderView, QTableWidget, QTableWidgetItem, QCompleter)

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
COLUMNS = ["open", "high", "low", "close", "volume"]


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


# ── Enhanced Indicator ComboBox ──────────────────────────────────────────────

# ── Enhanced Indicator ComboBox ──────────────────────────────────────────────

class IndicatorComboBox(QComboBox):
    """Comprehensive indicator dropdown with categories and autocomplete"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumWidth(160)
        self.setMaxVisibleItems(30)

        # Style - Fixed to show dropdown arrow
        self.setStyleSheet(f"""
            QComboBox {{
                background: #21262d;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 5px 8px;
                padding-right: 20px;  /* Make room for arrow */
                font-size: 9pt;
                min-width: 150px;
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
                min-width: 250px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 10px;
                min-height: 20px;
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
        # Store category indices for reference
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

                # Store category start index
                self._category_indices[category] = idx

                # Add indicators in this category
                for indicator in sorted(indicators):
                    display_name = indicator.upper()
                    self.addItem(display_name)
                    self.setItemData(self.count() - 1, indicator, Qt.UserRole)

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
                padding: 4px 8px;
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
        # Skip placeholder
        if text == "select indicator..." or text == "🔍 select indicator...":
            return ""
        # Check if it's a valid indicator
        if text in ALL_INDICATORS:
            return text
        # Try to find by display name
        for ind in ALL_INDICATORS:
            if ind.upper() == text.upper():
                return ind
        return text

    def focusInEvent(self, event):
        """Handle focus events to ensure dropdown works"""
        super().focusInEvent(event)
        # Clear selection when focusing
        self.lineEdit().deselect()

    def mousePressEvent(self, event):
        """Handle mouse press to show dropdown"""
        super().mousePressEvent(event)
        # Show dropdown on click
        self.showPopup()

# ── Parameter Editor ─────────────────────────────────────────────────────────

class ParameterEditor(QWidget):
    """Inline editor for indicator parameters"""

    params_changed = pyqtSignal(dict)

    def __init__(self, indicator: str = None, params: Dict = None, parent=None):
        super().__init__(parent)
        self._indicator = indicator
        self._params = params or {}
        self._param_widgets = {}

        self.setVisible(False)
        self.setStyleSheet(f"""
            QWidget {{
                background: #21262d;
                border: 1px solid {BORDER};
                border-radius: 4px;
            }}
            QLabel {{
                color: {DIM};
                font-size: 8pt;
            }}
        """)

    def set_indicator(self, indicator: str):
        """Update editor for new indicator"""
        self._indicator = indicator
        self._rebuild()

    def _rebuild(self):
        """Rebuild parameter editor based on current indicator"""
        # Clear existing layout
        if self.layout():
            QWidget().setLayout(self.layout())

        if not self._indicator or self._indicator not in ALL_INDICATORS:
            self.setVisible(False)
            return

        # Get default params for this indicator
        default_params = get_indicator_params(self._indicator)
        if not default_params:
            self.setVisible(False)
            return

        layout = QFormLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.setLabelAlignment(Qt.AlignRight)

        self._param_widgets.clear()

        for param_name, default_value in default_params.items():
            param_type = get_param_type(param_name)
            description = get_param_description(param_name)
            current_value = self._params.get(param_name, default_value)

            # Create appropriate input widget
            if param_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(current_value))
            elif param_type in ("int", "float"):
                widget = QLineEdit()
                widget.setText(str(current_value))
                if param_type == "int":
                    widget.setValidator(QIntValidator())
                else:
                    widget.setValidator(QDoubleValidator())
            else:  # string
                widget = QLineEdit()
                widget.setText(str(current_value))

            widget.setToolTip(description)
            widget.setStyleSheet(f"""
                QLineEdit, QCheckBox {{
                    font-size: 8pt;
                    padding: 2px 4px;
                }}
            """)

            if param_type != "bool":
                widget.setFixedWidth(80)

            layout.addRow(QLabel(f"{param_name}:"), widget)
            self._param_widgets[param_name] = (widget, param_type)

            # Connect change signal
            if param_type == "bool":
                widget.stateChanged.connect(self._on_params_changed)
            else:
                widget.textChanged.connect(self._on_params_changed)

        self.setVisible(True)
        self.adjustSize()

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
                # Keep previous value on error
                if name in self._params:
                    params[name] = self._params[name]

        self._params = params
        self.params_changed.emit(params)

    def get_params(self) -> Dict:
        """Get current parameter values"""
        return self._params.copy()


# ── Rule Editor Row ──────────────────────────────────────────────────────────

class _RuleRow(QWidget):
    """One editable rule row with complete indicator support"""

    deleted = pyqtSignal(object)

    def __init__(self, rule: Dict = None, parent=None):
        super().__init__(parent)
        self._param_editors = {}  # Store parameter editors for each side

        self.setStyleSheet(f"background:{BG_ITEM}; border-radius:5px; border:1px solid {BORDER};")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)

        # Left side container
        lhs_container = QWidget()
        lhs_layout = QVBoxLayout(lhs_container)
        lhs_layout.setContentsMargins(0, 0, 0, 0)
        lhs_layout.setSpacing(2)

        # LHS main row
        lhs_row = QHBoxLayout()
        lhs_row.setSpacing(4)

        self.lhs_type = QComboBox()
        self.lhs_type.addItems(SIDE_TYPES)
        self.lhs_type.setFixedWidth(85)
        self.lhs_type.setStyleSheet("font-size: 9pt;")
        lhs_row.addWidget(self.lhs_type)

        self.lhs_name = IndicatorComboBox()
        lhs_row.addWidget(self.lhs_name)

        self.lhs_val = QLineEdit()
        self.lhs_val.setPlaceholderText("value/params")
        self.lhs_val.setFixedWidth(120)
        lhs_row.addWidget(self.lhs_val)

        lhs_layout.addLayout(lhs_row)

        # LHS parameter editor (hidden by default)
        self.lhs_params = ParameterEditor()
        lhs_layout.addWidget(self.lhs_params)

        main_layout.addWidget(lhs_container)

        # Operator
        arrow = QLabel("→")
        arrow.setStyleSheet(f"color:{DIM}; font-size:11pt; padding:0 4px;")
        main_layout.addWidget(arrow)

        self.op = QComboBox()
        self.op.addItems(OPERATORS)
        self.op.setFixedWidth(110)
        self.op.setStyleSheet("font-size: 9pt;")
        main_layout.addWidget(self.op)

        arrow2 = QLabel("→")
        arrow2.setStyleSheet(f"color:{DIM}; font-size:11pt; padding:0 4px;")
        main_layout.addWidget(arrow2)

        # Right side container
        rhs_container = QWidget()
        rhs_layout = QVBoxLayout(rhs_container)
        rhs_layout.setContentsMargins(0, 0, 0, 0)
        rhs_layout.setSpacing(2)

        # RHS main row
        rhs_row = QHBoxLayout()
        rhs_row.setSpacing(4)

        self.rhs_type = QComboBox()
        self.rhs_type.addItems(SIDE_TYPES)
        self.rhs_type.setFixedWidth(85)
        self.rhs_type.setStyleSheet("font-size: 9pt;")
        rhs_row.addWidget(self.rhs_type)

        self.rhs_name = IndicatorComboBox()
        rhs_row.addWidget(self.rhs_name)

        self.rhs_val = QLineEdit()
        self.rhs_val.setPlaceholderText("value/params")
        self.rhs_val.setFixedWidth(120)
        rhs_row.addWidget(self.rhs_val)

        rhs_layout.addLayout(rhs_row)

        # RHS parameter editor (hidden by default)
        self.rhs_params = ParameterEditor()
        rhs_layout.addWidget(self.rhs_params)

        main_layout.addWidget(rhs_container)

        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(
            f"QPushButton{{background:{RED}33;color:{RED};border:1px solid {RED};border-radius:4px;font-weight:bold;padding:0;}}"
            f"QPushButton:hover{{background:{RED}66;}}"
        )
        del_btn.clicked.connect(lambda: self.deleted.emit(self))
        main_layout.addWidget(del_btn)

        # Connect signals
        self.lhs_type.currentTextChanged.connect(lambda t: self._update_side_visibility("lhs", t))
        self.rhs_type.currentTextChanged.connect(lambda t: self._update_side_visibility("rhs", t))

        self.lhs_name.currentTextChanged.connect(lambda t: self._on_indicator_changed("lhs", t))
        self.rhs_name.currentTextChanged.connect(lambda t: self._on_indicator_changed("rhs", t))

        self.lhs_params.params_changed.connect(lambda p: self._on_params_updated("lhs", p))
        self.rhs_params.params_changed.connect(lambda p: self._on_params_updated("rhs", p))

        # Load rule if provided
        if rule:
            self._load(rule)
        else:
            # Default: indicator > scalar
            self.lhs_type.setCurrentText("indicator")
            self.rhs_type.setCurrentText("scalar")
            self.rhs_val.setText("0")

    def _update_side_visibility(self, side: str, type_text: str):
        """Update visibility of name and value fields based on type"""
        if side == "lhs":
            name_w = self.lhs_name
            val_w = self.lhs_val
            params_w = self.lhs_params
        else:
            name_w = self.rhs_name
            val_w = self.rhs_val
            params_w = self.rhs_params

        if type_text == "scalar":
            name_w.setVisible(False)
            val_w.setVisible(True)
            params_w.setVisible(False)
            val_w.setPlaceholderText("numeric value")
        elif type_text == "column":
            name_w.setVisible(True)
            val_w.setVisible(False)
            params_w.setVisible(False)
        else:  # indicator
            name_w.setVisible(True)
            val_w.setVisible(False)
            params_w.setVisible(True)

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

    def _on_params_updated(self, side: str, params: Dict):
        """Handle parameter updates"""
        # Parameters are stored in the rule when collecting
        pass

    def _load(self, rule: Dict):
        """Load rule data into widgets"""
        for side, type_w, name_w, val_w, params_w in [
            ("lhs", self.lhs_type, self.lhs_name, self.lhs_val, self.lhs_params),
            ("rhs", self.rhs_type, self.rhs_name, self.rhs_val, self.rhs_params),
        ]:
            data = rule.get(side, {})
            t = data.get("type", "indicator")
            type_w.setCurrentText(t)

            if t == "scalar":
                val_w.setText(str(data.get("value", "0")))
            elif t == "column":
                col = data.get("column", "close")
                # Skip placeholder in IndicatorComboBox for column type
                if hasattr(name_w, 'model'):  # It's an IndicatorComboBox
                    name_w.setEditText(col.upper())
                else:
                    idx = name_w.findText(col.upper())
                    if idx >= 0:
                        name_w.setCurrentIndex(idx)
                    else:
                        name_w.setEditText(col)
            else:  # indicator
                ind = data.get("indicator", "rsi")
                # Skip placeholder for indicator
                if hasattr(name_w, 'model'):  # It's an IndicatorComboBox
                    name_w.setEditText(ind.upper())
                else:
                    idx = name_w.findText(ind.upper())
                    if idx >= 0:
                        name_w.setCurrentIndex(idx)
                    else:
                        name_w.setEditText(ind)

                # Load parameters
                params = data.get("params", {})
                if ind in ALL_INDICATORS:
                    params_w.set_indicator(ind)
                    # Update parameter editor with loaded params
                    for pname, pwidget in params_w._param_widgets.items():
                        if pname in params:
                            widget, ptype = pwidget
                            if ptype == "bool":
                                widget.setChecked(bool(params[pname]))
                            else:
                                widget.setText(str(params[pname]))

        # Operator
        op = rule.get("op", ">")
        idx = self.op.findText(op)
        if idx >= 0:
            self.op.setCurrentIndex(idx)

    def collect(self) -> Dict:
        """Collect rule data as dictionary"""
        def collect_side(type_w, name_w, val_w, params_w) -> Dict:
            t = type_w.currentText()
            if t == "scalar":
                try:
                    return {"type": "scalar", "value": float(val_w.text())}
                except:
                    return {"type": "scalar", "value": 0}
            elif t == "column":
                return {"type": "column", "column": name_w.currentText().lower()}
            else:  # indicator
                indicator = name_w.get_indicator_name()
                params = params_w.get_params() if params_w.isVisible() else {}
                return {
                    "type": "indicator",
                    "indicator": indicator,
                    "params": params
                }

        return {
            "lhs": collect_side(self.lhs_type, self.lhs_name, self.lhs_val, self.lhs_params),
            "op": self.op.currentText(),
            "rhs": collect_side(self.rhs_type, self.rhs_name, self.rhs_val, self.rhs_params),
        }


# ── Signal Group Panel ───────────────────────────────────────────────────────

class _SignalGroupPanel(QWidget):
    """Panel for editing rules of a single signal group (tab content)"""

    rules_changed = pyqtSignal()  # Emitted when rules are added/removed

    def __init__(self, signal: str, parent=None):
        super().__init__(parent)
        self.signal = signal
        emoji, color, label = SIGNAL_META.get(signal, ("⬤", DIM, signal))
        self._color = color
        self._rule_rows: List[_RuleRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

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
        lbl_logic.setStyleSheet(f"color:{DIM}; font-size:9pt; font-weight:bold;")
        logic_group.addWidget(lbl_logic)

        self.logic_combo = QComboBox()
        self.logic_combo.addItems(["AND", "OR"])
        self.logic_combo.setFixedWidth(80)
        self.logic_combo.setStyleSheet(f"""
            QComboBox {{
                background: #21262d;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
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
                font-size: 9pt;
                font-weight: bold;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
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
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 8pt;
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
        self._rules_layout.setSpacing(8)

        # Empty state
        self._empty_lbl = QLabel("  ✨ No rules yet — click '+ Add Rule' to begin")
        self._empty_lbl.setStyleSheet(f"color:{DIM}; font-size:10pt; padding:20px;")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._rules_layout.addWidget(self._empty_lbl)

        self._rules_layout.addStretch()
        self._rules_scroll.setWidget(self._rules_container)

    def _build_actions_bar(self, color: str) -> QWidget:
        """Build actions bar with add rule button and presets"""
        bar = QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet(f"background: transparent;")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)

        # Add rule button (prominent)
        add_btn = QPushButton("＋ Add Rule")
        add_btn.setFixedHeight(32)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d;
                color: {color};
                border: 1px solid {color};
                border-radius: 5px;
                padding: 6px 16px;
                font-size: 10pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {color}22;
            }}
        """)
        add_btn.clicked.connect(self._add_rule)
        layout.addWidget(add_btn)

        # Presets dropdown with comprehensive options
        self._presets_combo = QComboBox()

        # Common presets for all signals
        common_presets = ["📋 Load Preset"]

        # Signal-specific presets
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
        self._presets_combo.setFixedWidth(180)
        self._presets_combo.setStyleSheet(f"""
            QComboBox {{
                background: #21262d;
                color: {DIM};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
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
            }}
        """)
        self._presets_combo.currentIndexChanged.connect(self._load_preset)
        layout.addWidget(self._presets_combo)

        layout.addStretch()

        # Clear all button
        clear_btn = QPushButton("🗑 Clear All")
        clear_btn.setFixedHeight(28)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
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
        clear_btn.clicked.connect(self._clear_all_rules)
        layout.addWidget(clear_btn)

        return bar

    def _update_rule_count(self):
        """Update rule count badge and empty state visibility"""
        count = len(self._rule_rows)
        self._rule_count_badge.setText(f"{count} rule{'s' if count != 1 else ''}")
        self._empty_lbl.setVisible(count == 0)

        # Adjust scroll area height based on number of rules
        if count > 0:
            height = min(400, 60 + 70 * count)
            self._rules_scroll.setMinimumHeight(height)
        else:
            self._rules_scroll.setMinimumHeight(100)

        self.rules_changed.emit()

    def _add_rule(self, rule: Dict = None):
        """Add a new rule row"""
        row = _RuleRow(rule, parent=self._rules_container)
        row.deleted.connect(self._remove_rule)
        self._rule_rows.append(row)

        # Insert before the stretch
        insert_at = self._rules_layout.count() - 1
        self._rules_layout.insertWidget(insert_at, row)

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

        # ========== BUY CALL PRESETS (Bullish) ==========
        if self.signal == "BUY_CALL":

            # 1. RSI Oversold Bounce
            if preset == "RSI Oversold":
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

            # 2. MACD Bullish Crossover
            elif preset == "MACD Crossover":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "macd",
                                "params": {"fast": 12, "slow": 26, "signal": 9}},
                        "op": "crosses_above",
                        "rhs": {"type": "scalar", "value": 0}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "macd",
                                "params": {"fast": 12, "slow": 26, "signal": 9}},
                        "op": ">",
                        "rhs": {"type": "indicator", "indicator": "macd", "params": {"signal": 9}}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 3. Bollinger Band Squeeze Breakout (Bullish)
            elif preset == "BB Squeeze":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "bbands", "params": {"length": 20, "std": 2}},
                        "op": ">",
                        "rhs": {"type": "column", "column": "close"}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "bbands", "params": {"length": 20, "std": 2}},
                        "op": "crosses_above",
                        "rhs": {"type": "column", "column": "close"}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 4. EMA Golden Cross (9 above 21)
            elif preset == "EMA Cross":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}},
                        "op": "crosses_above",
                        "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}},
                        "op": ">",
                        "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 5. Stochastic Bullish Crossover
            elif preset == "Stochastic Bull":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "stoch", "params": {"k": 14, "d": 3, "smooth_k": 3}},
                        "op": "crosses_above",
                        "rhs": {"type": "scalar", "value": 20}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "stoch", "params": {"k": 14, "d": 3, "smooth_k": 3}},
                        "op": "<",
                        "rhs": {"type": "scalar", "value": 80}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 6. ADX Strong Trend + DI+ Cross
            elif preset == "ADX Strong Trend":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "adx", "params": {"length": 14}},
                        "op": ">",
                        "rhs": {"type": "scalar", "value": 25}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "dm", "params": {"length": 14}},
                        "op": "crosses_above",
                        "rhs": {"type": "indicator", "indicator": "dm", "params": {"length": 14}}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 7. Ichimoku Cloud Breakout
            elif preset == "Ichimoku Breakout":
                rules = [
                    {
                        "lhs": {"type": "column", "column": "close"},
                        "op": "crosses_above",
                        "rhs": {"type": "indicator", "indicator": "ichimoku",
                                "params": {"tenkan": 9, "kijun": 26, "senkou": 52}}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "ichimoku",
                                "params": {"tenkan": 9, "kijun": 26, "senkou": 52}},
                        "op": ">",
                        "rhs": {"type": "indicator", "indicator": "ichimoku",
                                "params": {"tenkan": 9, "kijun": 26, "senkou": 52}}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 8. Volume Surge + Price Breakout
            elif preset == "Volume Breakout":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "obv", "params": {}},
                        "op": "crosses_above",
                        "rhs": {"type": "indicator", "indicator": "sma", "params": {"length": 20}}
                    },
                    {
                        "lhs": {"type": "column", "column": "volume"},
                        "op": ">",
                        "rhs": {"type": "indicator", "indicator": "sma", "params": {"length": 20}}
                    },
                    {
                        "lhs": {"type": "column", "column": "close"},
                        "op": ">",
                        "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 50}}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 9. Triple Confirmation (RSI + MACD + EMA)
            elif preset == "Triple Confirmation":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                        "op": ">",
                        "rhs": {"type": "scalar", "value": 50}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "macd",
                                "params": {"fast": 12, "slow": 26, "signal": 9}},
                        "op": ">",
                        "rhs": {"type": "scalar", "value": 0}
                    },
                    {
                        "lhs": {"type": "column", "column": "close"},
                        "op": ">",
                        "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 200}}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 10. Bullish Engulfing Pattern
            elif preset == "Bullish Engulfing":
                rules = [
                    {
                        "lhs": {"type": "column", "column": "close"},
                        "op": ">",
                        "rhs": {"type": "column", "column": "open"}
                    },
                    {
                        "lhs": {"type": "column", "column": "open"},
                        "op": "<",
                        "rhs": {"type": "column", "column": "close", "shift": 1}
                    },
                    {
                        "lhs": {"type": "column", "column": "close"},
                        "op": ">",
                        "rhs": {"type": "column", "column": "open", "shift": 1}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

        # ========== BUY PUT PRESETS (Bearish) ==========
        elif self.signal == "BUY_PUT":

            # 11. RSI Overbought Reversal
            if preset == "RSI Overbought":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                        "op": ">",
                        "rhs": {"type": "scalar", "value": 70}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                        "op": "crosses_below",
                        "rhs": {"type": "scalar", "value": 70}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 12. MACD Bearish Crossover
            elif preset == "MACD Bear Cross":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "macd",
                                "params": {"fast": 12, "slow": 26, "signal": 9}},
                        "op": "crosses_below",
                        "rhs": {"type": "scalar", "value": 0}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "macd",
                                "params": {"fast": 12, "slow": 26, "signal": 9}},
                        "op": "<",
                        "rhs": {"type": "indicator", "indicator": "macd", "params": {"signal": 9}}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 13. Death Cross (50 below 200)
            elif preset == "Death Cross":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "sma", "params": {"length": 50}},
                        "op": "crosses_below",
                        "rhs": {"type": "indicator", "indicator": "sma", "params": {"length": 200}}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "sma", "params": {"length": 50}},
                        "op": "<",
                        "rhs": {"type": "indicator", "indicator": "sma", "params": {"length": 200}}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 14. Bollinger Band Top Rejection
            elif preset == "BB Top Rejection":
                rules = [
                    {
                        "lhs": {"type": "column", "column": "close"},
                        "op": ">",
                        "rhs": {"type": "indicator", "indicator": "bbands", "params": {"length": 20, "std": 2}}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                        "op": ">",
                        "rhs": {"type": "scalar", "value": 70}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 15. Bearish Divergence (Price up, RSI down)
            elif preset == "Bearish Divergence":
                rules = [
                    {
                        "lhs": {"type": "column", "column": "close"},
                        "op": ">",
                        "rhs": {"type": "column", "column": "close", "shift": 5}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                        "op": "<",
                        "rhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}, "shift": 5}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

        # ========== SELL CALL PRESETS (Bearish - for selling calls) ==========
        elif self.signal == "SELL_CALL":

            # 16. Overbought RSI for Call Selling
            if preset == "RSI Overbought":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                        "op": ">",
                        "rhs": {"type": "scalar", "value": 75}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                        "op": "crosses_below",
                        "rhs": {"type": "scalar", "value": 70}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 17. Resistance Level Test
            elif preset == "Resistance Test":
                rules = [
                    {
                        "lhs": {"type": "column", "column": "close"},
                        "op": ">",
                        "rhs": {"type": "indicator", "indicator": "kc", "params": {"length": 20, "scalar": 2}}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                        "op": ">",
                        "rhs": {"type": "scalar", "value": 70}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

        # ========== SELL PUT PRESETS (Bullish - for selling puts) ==========
        elif self.signal == "SELL_PUT":

            # 18. Oversold RSI for Put Selling
            if preset == "RSI Oversold":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                        "op": "<",
                        "rhs": {"type": "scalar", "value": 25}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                        "op": "crosses_above",
                        "rhs": {"type": "scalar", "value": 30}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 19. Support Level Bounce
            elif preset == "Support Bounce":
                rules = [
                    {
                        "lhs": {"type": "column", "column": "close"},
                        "op": "<",
                        "rhs": {"type": "indicator", "indicator": "bbands", "params": {"length": 20, "std": 2}}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "stoch", "params": {"k": 14, "d": 3, "smooth_k": 3}},
                        "op": "crosses_above",
                        "rhs": {"type": "scalar", "value": 20}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

        # ========== HOLD PRESETS ==========
        elif self.signal == "HOLD":

            # 20. Strong Trend (ADX > 25)
            if preset == "Strong Trend":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "adx", "params": {"length": 14}},
                        "op": ">",
                        "rhs": {"type": "scalar", "value": 25}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "adx", "params": {"length": 14}},
                        "op": ">",
                        "rhs": {"type": "indicator", "indicator": "adx", "params": {"length": 14}, "shift": 1}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

            # 21. Low Volatility Consolidation
            elif preset == "Low Volatility":
                rules = [
                    {
                        "lhs": {"type": "indicator", "indicator": "atr", "params": {"length": 14}},
                        "op": "<",
                        "rhs": {"type": "indicator", "indicator": "sma", "params": {"length": 20}}
                    },
                    {
                        "lhs": {"type": "indicator", "indicator": "bbands", "params": {"length": 20, "std": 2}},
                        "op": "<",
                        "rhs": {"type": "indicator", "indicator": "bbands", "params": {"length": 20, "std": 2}}
                    }
                ]
                for rule in rules:
                    self._add_rule(rule)

    def load(self, group_data: Dict):
        """Load group data into panel"""
        # Clear existing rules
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

        # Conflict resolution header (always visible)
        header = self._build_header()
        main_layout.addWidget(header)

        # Tab widget for signal groups
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
                border-radius: 4px 4px 0 0;
                padding: 8px 16px;
                margin-right: 2px;
                font-size: 10pt;
                font-weight: bold;
                min-width: 100px;
            }}
            QTabBar::tab:selected {{
                background: {BG_PANEL};
                color: {TEXT};
                border-bottom: 2px solid {BLUE};
            }}
            QTabBar::tab:hover:!selected {{
                background: #2d333b;
                color: {TEXT};
            }}
        """)

        # Create tabs for each signal type
        self._panels: Dict[str, _SignalGroupPanel] = {}

        # Define tab order with icons and colors
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

        # Quick stats bar at bottom
        stats_bar = self._build_stats_bar()
        main_layout.addWidget(stats_bar)

    def _build_header(self) -> QWidget:
        """Build header with conflict resolution selector"""
        header = QWidget()
        header.setStyleSheet(f"background:{BG_PANEL}; border-bottom:1px solid {BORDER};")
        header.setFixedHeight(50)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)

        cr_lbl = QLabel("⚖️ Conflict Resolution:")
        cr_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt; font-weight:bold;")
        layout.addWidget(cr_lbl)

        self.conflict_combo = QComboBox()
        self.conflict_combo.addItems(["WAIT", "PRIORITY"])
        self.conflict_combo.setFixedWidth(110)
        self.conflict_combo.setStyleSheet(f"""
            QComboBox {{
                background: #21262d;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }}
            QComboBox:hover {{
                border: 1px solid {BLUE};
            }}
        """)
        layout.addWidget(self.conflict_combo)

        help_lbl = QLabel("(when both BUY_CALL and BUY_PUT fire)")
        help_lbl.setStyleSheet(f"color:{DIM}; font-size:8pt;")
        layout.addWidget(help_lbl)
        layout.addStretch()

        return header

    def _build_stats_bar(self) -> QWidget:
        """Build a stats bar showing total rules across all signals"""
        bar = QFrame()
        bar.setFixedHeight(36)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {BG_PANEL};
                border-top: 1px solid {BORDER};
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 4, 16, 4)

        self._total_rules_lbl = QLabel("📊 Total Rules: 0")
        self._total_rules_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt;")
        layout.addWidget(self._total_rules_lbl)

        layout.addStretch()

        # Quick enable/disable all toggles
        self._enable_all_btn = QPushButton("✓ Enable All")
        self._enable_all_btn.setFixedHeight(24)
        self._enable_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d;
                color: {GREEN};
                border: 1px solid {GREEN}55;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 8pt;
            }}
            QPushButton:hover {{
                background: {GREEN}22;
            }}
        """)
        self._enable_all_btn.clicked.connect(self._toggle_all_enabled)
        layout.addWidget(self._enable_all_btn)

        self._disable_all_btn = QPushButton("✗ Disable All")
        self._disable_all_btn.setFixedHeight(24)
        self._disable_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d;
                color: {RED};
                border: 1px solid {RED}55;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 8pt;
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
        """Enable all signal groups"""
        for panel in self._panels.values():
            panel.enabled_chk.setChecked(True)

    def _toggle_all_disabled(self):
        """Disable all signal groups"""
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
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        lbl = QLabel("Strategy name and description.")
        lbl.setStyleSheet(f"color:{DIM}; font-size:9pt;")
        layout.addRow("", lbl)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. EMA Crossover")
        layout.addRow("Name:", self.name_edit)

        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText(
            "Describe when this strategy fires, what market conditions it suits, etc."
        )
        self.desc_edit.setMaximumHeight(100)
        layout.addRow("Description:", self.desc_edit)

        # Statistics section
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"QFrame{{background:{BORDER};max-height:1px;margin:10px 0;}}")
        layout.addRow("", sep)

        stats_lbl = QLabel("📊 Strategy Statistics")
        stats_lbl.setStyleSheet(f"color:{BLUE}; font-size:11pt; font-weight:bold;")
        layout.addRow("", stats_lbl)

        self.total_rules_lbl = QLabel("0")
        self.total_rules_lbl.setStyleSheet(f"color:{GREEN}; font-weight:bold;")
        layout.addRow("Total Rules:", self.total_rules_lbl)

        self.unique_indicators_lbl = QLabel("0")
        self.unique_indicators_lbl.setStyleSheet(f"color:{GREEN}; font-weight:bold;")
        layout.addRow("Unique Indicators:", self.unique_indicators_lbl)

        self.enabled_groups_lbl = QLabel("0/5")
        self.enabled_groups_lbl.setStyleSheet(f"color:{GREEN}; font-weight:bold;")
        layout.addRow("Enabled Groups:", self.enabled_groups_lbl)

        self.created_lbl = QLabel("—")
        self.created_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt;")
        layout.addRow("Created:", self.created_lbl)

        self.updated_lbl = QLabel("—")
        self.updated_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt;")
        layout.addRow("Last saved:", self.updated_lbl)

    def load(self, strategy: Dict):
        meta = strategy.get("meta", {})
        self.name_edit.setText(meta.get("name", ""))
        self.desc_edit.setPlainText(meta.get("description", ""))
        self.created_lbl.setText(meta.get("created_at", "—"))
        self.updated_lbl.setText(meta.get("updated_at", "—"))

        # Calculate statistics
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

            # Extract indicators from rules
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
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(14)

        # Info label
        info_lbl = QLabel(
            "📊 AVAILABLE INDICATORS (pandas_ta)\n"
            "The following indicators are available for your strategy rules."
        )
        info_lbl.setStyleSheet(f"color:{DIM}; font-size:10pt; padding:8px; background:{BG_ITEM}; border-radius:4px;")
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
        search_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt;")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter indicators...")
        self.search_edit.setFixedHeight(28)
        self.search_edit.textChanged.connect(self._filter_indicators)
        search_layout.addWidget(search_lbl)
        search_layout.addWidget(self.search_edit)
        self._layout.addLayout(search_layout)

        # Category sections
        self._category_widgets = {}

        for category, indicators in get_indicators_by_category().items():
            if not indicators:
                continue

            # Category header
            cat_header = QLabel(f"📁 {category.upper()}")
            cat_header.setStyleSheet(f"""
                color:{BLUE}; 
                font-size:11pt; 
                font-weight:bold; 
                padding:8px 0 4px 0;
                border-bottom:1px solid {BORDER};
            """)
            self._layout.addWidget(cat_header)

            # Grid for indicators in this category
            grid = QGridLayout()
            grid.setSpacing(8)

            row, col = 0, 0
            for indicator in sorted(indicators):
                card = self._create_indicator_card(indicator)
                grid.addWidget(card, row, col)

                col += 1
                if col >= 4:  # 4 columns per row
                    col = 0
                    row += 1

            container = QWidget()
            container.setLayout(grid)
            self._layout.addWidget(container)
            self._category_widgets[category] = container

    def _create_indicator_card(self, indicator_name: str) -> QWidget:
        """Create a compact card showing indicator info"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {BG_PANEL};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px;
            }}
            QFrame:hover {{
                border: 1px solid {BLUE};
                background: {BG_ITEM};
            }}
        """)
        card.setFixedSize(230, 150)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        # Indicator name
        name_lbl = QLabel(indicator_name.upper())
        name_lbl.setStyleSheet(f"color:{GREEN}; font-size:9pt; font-weight:bold;")
        layout.addWidget(name_lbl)

        # Default params preview
        params = get_indicator_params(indicator_name)
        if params:
            param_text = ", ".join(f"{k}={v}" for k, v in list(params.items())[:3])
            if len(params) > 3:
                param_text += "..."
            param_lbl = QLabel(param_text)
        else:
            param_lbl = QLabel("no params")
        param_lbl.setStyleSheet(f"color:{DIM}; font-size:7pt;")
        param_lbl.setWordWrap(True)
        layout.addWidget(param_lbl)

        # Category tag
        cat = get_indicator_category(indicator_name)
        cat_lbl = QLabel(cat)
        cat_lbl.setStyleSheet(f"color:{BLUE}99; font-size:7pt; border:none;")
        layout.addWidget(cat_lbl)

        return card

    def _filter_indicators(self, text: str):
        """Filter indicators by search text"""
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
        """No loading needed - this is a reference tab"""
        pass

    def collect(self) -> Dict:
        """Read-only tab"""
        return {}


# ── Strategy List Panel ──────────────────────────────────────────────────────

class _StrategyListPanel(QWidget):
    strategy_selected = pyqtSignal(str)   # slug
    strategy_activated = pyqtSignal(str)  # slug

    def __init__(self, manager: StrategyManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._current_slug: Optional[str] = None
        self.setFixedWidth(240)
        self.setStyleSheet(f"background:{BG_PANEL}; border-right:1px solid {BORDER};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QLabel("  STRATEGIES")
        hdr.setStyleSheet(f"color:{DIM}; font-size:8pt; font-weight:bold; padding:10px 12px 6px 12px; background:{BG_PANEL};")
        root.addWidget(hdr)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(8, 4, 8, 4)
        btn_row.setSpacing(6)
        self.new_btn = _btn("＋ New", "#238636", "#2ea043", min_w=70)
        self.new_btn.setFixedHeight(30)
        self.dup_btn = _btn("⧉ Dup", "#21262d", "#2d333b", min_w=60)
        self.dup_btn.setFixedHeight(30)
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

        # Bottom: activate + delete
        foot = QVBoxLayout()
        foot.setContentsMargins(8, 6, 8, 8)
        foot.setSpacing(6)
        self.activate_btn = _btn("⚡ Activate Strategy", "#1f6feb", "#388bfd")
        self.activate_btn.setFixedHeight(34)
        self.activate_btn.clicked.connect(self._on_activate)
        self.delete_btn = _btn("🗑 Delete", RED + "44", RED + "66", RED)
        self.delete_btn.setFixedHeight(30)
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
        # Select first if nothing selected
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
    Full-page strategy editor. Non-modal so trading can continue.
    Emits strategy_activated(slug) when the user activates a strategy.
    """
    strategy_activated = pyqtSignal(str)  # slug of newly activated strategy

    def __init__(self, manager: StrategyManager, parent=None):
        super().__init__(parent, Qt.Window)
        self.manager = manager
        self._current_slug: Optional[str] = None
        self._dirty = False

        self.setWindowTitle("📋 Strategy Editor")
        self.resize(1200, 780)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(_ss())

        self._build_ui()
        # Load active strategy by default
        active = manager.get_active_slug()
        if active:
            self._load_strategy(active)

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left: strategy list ───────────────────────────────────────────────
        self._list_panel = _StrategyListPanel(self.manager)
        self._list_panel.strategy_selected.connect(self._on_strategy_selected)
        self._list_panel.strategy_activated.connect(self._on_strategy_activated)
        root.addWidget(self._list_panel)

        # ── Right: editor ─────────────────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Title bar
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

        # Footer bar
        right_layout.addWidget(self._build_footer())

        root.addWidget(right, 1)

    def _build_title_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(f"QFrame{{background:{BG_PANEL}; border-bottom:1px solid {BORDER};}}")
        bar.setFixedHeight(50)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(12)

        self._title_lbl = QLabel("Select a strategy →")
        self._title_lbl.setStyleSheet(f"color:{TEXT}; font-size:12pt; font-weight:bold;")
        h.addWidget(self._title_lbl)

        self._active_badge = QLabel()
        self._active_badge.setFixedHeight(26)
        self._active_badge.hide()
        h.addWidget(self._active_badge)

        h.addStretch()

        self._dirty_lbl = QLabel("● Unsaved changes")
        self._dirty_lbl.setStyleSheet(f"color:{YELLOW}; font-size:9pt;")
        self._dirty_lbl.hide()
        h.addWidget(self._dirty_lbl)

        return bar

    def _build_footer(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"QFrame{{background:{BG_PANEL}; border-top:1px solid {BORDER};}}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(10)

        self.activate_btn = _btn("⚡ Activate This Strategy", "#1f6feb", "#388bfd", min_w=200)
        self.activate_btn.clicked.connect(self._on_activate)
        h.addWidget(self.activate_btn)

        h.addStretch()

        self.revert_btn = _btn("↺ Revert")
        self.revert_btn.clicked.connect(self._on_revert)
        h.addWidget(self.revert_btn)

        self.save_btn = _btn("💾 Save", "#238636", "#2ea043", min_w=100)
        self.save_btn.clicked.connect(self._on_save)
        h.addWidget(self.save_btn)

        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet(f"color:{GREEN}; font-size:9pt;")
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
                # Reselect old item in list
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
                f"color:{BLUE}; background:{BLUE}22; border:1px solid {BLUE};"
                f" border-radius:4px; font-size:9pt; font-weight:bold; padding:2px 6px;"
            )
            self._active_badge.show()
        else:
            self._active_badge.hide()

        self.status_lbl.clear()

        # Watch for edits to mark dirty
        self._connect_dirty_watchers()

    def _connect_dirty_watchers(self):
        """Connect change signals so we know when the user edits anything."""
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
        self._load_strategy(slug)  # refresh active badge

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
            f"color:{BLUE}; background:{BLUE}22; border:1px solid {BLUE};"
            f" border-radius:4px; font-size:9pt; font-weight:bold; padding:2px 6px;"
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
        # Validate name
        name = self._info_tab.collect()["name"]
        if not name:
            QMessageBox.warning(self, "Validation", "Strategy name cannot be empty.")
            return False

        strategy = self.manager.get(self._current_slug) or {}
        strategy["meta"] = strategy.get("meta", {})
        strategy["meta"]["name"] = name
        strategy["meta"]["description"] = self._info_tab.collect()["description"]
        strategy["indicators"] = self._ind_tab.collect()
        strategy["engine"] = self._rules_tab.collect()

        ok = self.manager.save(self._current_slug, strategy)
        if ok:
            self._set_dirty(False)
            self._title_lbl.setText(name)
            self._list_panel.refresh()
            self.status_lbl.setText("✓ Saved")
            self.status_lbl.setStyleSheet(f"color:{GREEN}; font-size:9pt;")
            QTimer.singleShot(2500, self.status_lbl.clear)
            return True
        else:
            self.status_lbl.setText("✗ Save failed")
            self.status_lbl.setStyleSheet(f"color:{RED}; font-size:9pt;")
            return False