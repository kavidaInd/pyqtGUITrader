"""
strategy_editor_window.py
==========================
Full-page Strategy Editor Window.

Layout:
  ┌─────────────────────────────────────────────────────────────┐
  │  ▸ Strategy Editor                              [×  Close]  │
  ├───────────────┬─────────────────────────────────────────────┤
  │  STRATEGIES   │   EDITOR TABS                               │
  │  ──────────── │   ┌─────────┬──────────┬────────────────┐  │
  │  [+ New]      │   │ ⚙ Info  │📊 Indics │ 🔬 Sig Rules  │  │
  │  [⧉ Dup]      │   └─────────┴──────────┴────────────────┘  │
  │               │                                             │
  │  ● Strategy A │   (tab content)                             │
  │    Strategy B │                                             │
  │    Strategy C │                                             │
  │               │                                             │
  │  [🗑 Delete]  │   [💾 Save]  [↺ Revert]                    │
  └───────────────┴─────────────────────────────────────────────┘

Usage:
    mgr = StrategyManager()
    win = StrategyEditorWindow(mgr, parent=self)
    win.show()
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QFont, QIntValidator, QDoubleValidator
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget, QGridLayout,
    QHeaderView, QTableWidget, QTableWidgetItem,
)

from strategy.strategy_manager import (
    StrategyManager, INDICATOR_DEFAULTS, ENGINE_DEFAULTS, SIGNAL_GROUPS
)
# Add this import at the top
from strategy.indicator_registry import (
    ALL_INDICATORS, INDICATOR_DEFAULT_PARAMS, get_indicator_params,
    get_param_type, get_param_description, get_indicator_category, INDICATOR_CATEGORIES
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
    "BUY_CALL":  ("📈", "#3fb950", "Buy Call"),
    "BUY_PUT":   ("📉", "#58a6ff", "Buy Put"),
    "SELL_CALL": ("🔴", "#f85149", "Sell Call"),
    "SELL_PUT":  ("🟠", "#ffa657", "Sell Put"),
    "HOLD":      ("⏸",  "#d29922", "Hold"),
}

OPERATORS = [">", "<", ">=", "<=", "==", "!=", "crosses_above", "crosses_below"]
SIDE_TYPES = ["indicator", "scalar", "column"]
INDICATORS = [
    "rsi", "ema", "sma", "wma", "macd", "bbands", "atr", "adx", "cci",
    "stoch", "roc", "mom", "willr", "obv", "vwap", "supertrend",
    "kc", "donchian", "psar", "tema", "dema", "hma", "zlma", "slope", "linreg",
]
COLUMNS = ["open", "high", "low", "close", "volume"]

INDICATOR_PARAM_HINTS = {
    "rsi":        "length=14",
    "ema":        "length=20",
    "sma":        "length=20",
    "wma":        "length=20",
    "macd":       "fast=12, slow=26, signal=9",
    "bbands":     "length=20, std=2.0",
    "atr":        "length=14",
    "adx":        "length=14",
    "cci":        "length=20",
    "stoch":      "k=14, d=3, smooth_k=3",
    "roc":        "length=10",
    "mom":        "length=10",
    "willr":      "length=14",
    "supertrend": "length=7, multiplier=3.0",
    "kc":         "length=20, scalar=1.5",
    "donchian":   "lower_length=20, upper_length=20",
    "psar":       "af0=0.02, af=0.02, max_af=0.2",
    "slope":      "length=1",
    "linreg":     "length=14",
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
        QComboBox QAbstractItemView {{ background: #21262d; color: {TEXT}; selection-background-color: {BG_SEL}; }}
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

# ── Indicators Tab ────────────────────────────────────────────────────────────

class _IndicatorsTab(QScrollArea):
    """
    Dynamic Indicators Tab - Shows all indicators organized by category
    """

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

        # Category tabs
        self._category_widgets = {}

        for category in INDICATOR_CATEGORIES.keys():
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
            for indicator in sorted(INDICATOR_CATEGORIES[category]):
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
            }}
        """)
        card.setFixedSize(180, 70)

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
            param_text = ", ".join(f"{k}={v}" for k, v in list(params.items())[:2])
            if len(params) > 2:
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

# ── Rule Editor row ───────────────────────────────────────────────────────────

# Add this import at the top
from strategy.indicator_registry import (
    ALL_INDICATORS, INDICATOR_DEFAULT_PARAMS, get_indicator_params,
    get_param_type, get_param_description, get_indicator_category
)


# Update the _RuleRow class to use dynamic indicators
class _RuleRow(QWidget):
    """One editable rule row with all pandas_ta indicators"""
    deleted = pyqtSignal(object)

    def __init__(self, rule: Dict = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{BG_ITEM}; border-radius:5px; border:1px solid {BORDER};")
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(6)

        # LHS
        self.lhs_type = QComboBox();
        self.lhs_type.addItems(SIDE_TYPES);
        self.lhs_type.setFixedWidth(95)
        self.lhs_name = QComboBox();
        self.lhs_name.addItems(ALL_INDICATORS + COLUMNS)
        self.lhs_name.setEditable(True)
        self.lhs_name.setFixedWidth(130)
        self.lhs_name.setInsertPolicy(QComboBox.InsertAlphabetically)

        self.lhs_val = QLineEdit();
        self.lhs_val.setPlaceholderText("params e.g. length=14")
        self.lhs_val.setFixedWidth(150)

        h.addWidget(self.lhs_type);
        h.addWidget(self.lhs_name);
        h.addWidget(self.lhs_val)

        # Operator
        arrow = QLabel("→");
        arrow.setStyleSheet(f"color:{DIM}; font-size:11pt;")
        h.addWidget(arrow)
        self.op = QComboBox();
        self.op.addItems(OPERATORS);
        self.op.setFixedWidth(120)
        h.addWidget(self.op)

        arrow2 = QLabel("→");
        arrow2.setStyleSheet(f"color:{DIM}; font-size:11pt;")
        h.addWidget(arrow2)

        # RHS
        self.rhs_type = QComboBox();
        self.rhs_type.addItems(SIDE_TYPES);
        self.rhs_type.setFixedWidth(95)
        self.rhs_name = QComboBox();
        self.rhs_name.addItems(ALL_INDICATORS + COLUMNS)
        self.rhs_name.setEditable(True)
        self.rhs_name.setFixedWidth(130)
        self.rhs_name.setInsertPolicy(QComboBox.InsertAlphabetically)

        self.rhs_val = QLineEdit();
        self.rhs_val.setPlaceholderText("params e.g. length=14")
        self.rhs_val.setFixedWidth(150)

        h.addWidget(self.rhs_type);
        h.addWidget(self.rhs_name);
        h.addWidget(self.rhs_val)

        h.addStretch()

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(
            f"QPushButton{{background:{RED}33;color:{RED};border:1px solid {RED};border-radius:4px;font-weight:bold;padding:0;}}"
            f"QPushButton:hover{{background:{RED}66;}}")
        del_btn.clicked.connect(lambda: self.deleted.emit(self))
        h.addWidget(del_btn)

        # Connect type and name changes
        self.lhs_type.currentTextChanged.connect(self._update_lhs_visibility)
        self.rhs_type.currentTextChanged.connect(self._update_rhs_visibility)
        self.lhs_name.currentTextChanged.connect(lambda t: self._update_param_hint("lhs", t))
        self.rhs_name.currentTextChanged.connect(lambda t: self._update_param_hint("rhs", t))

        # Load rule if provided
        if rule:
            self._load(rule)
        else:
            self._update_lhs_visibility("indicator")
            self._update_rhs_visibility("scalar")
            self.rhs_type.setCurrentText("scalar")

    def _update_param_hint(self, side: str, indicator: str):
        """Update parameter placeholder with default params for selected indicator"""
        if side == "lhs":
            type_w = self.lhs_type
            val_w = self.lhs_val
        else:
            type_w = self.rhs_type
            val_w = self.rhs_val

        if type_w.currentText() == "indicator" and indicator in ALL_INDICATORS:
            params = get_indicator_params(indicator)
            if params:
                hint = ", ".join(f"{k}={v}" for k, v in params.items())
                val_w.setPlaceholderText(hint)
            else:
                val_w.setPlaceholderText("params e.g. length=14")
        elif type_w.currentText() == "scalar":
            val_w.setPlaceholderText("numeric value")

    def _update_lhs_visibility(self, t: str):
        self.lhs_name.setVisible(t in ("indicator", "column"))
        self.lhs_val.setVisible(t in ("indicator", "scalar"))
        if t == "indicator":
            current_ind = self.lhs_name.currentText()
            self._update_param_hint("lhs", current_ind)
        elif t == "scalar":
            self.lhs_val.setPlaceholderText("numeric value")
        elif t == "column":
            self.lhs_val.setVisible(False)

    def _update_rhs_visibility(self, t: str):
        self.rhs_name.setVisible(t in ("indicator", "column"))
        self.rhs_val.setVisible(t in ("indicator", "scalar"))
        if t == "indicator":
            current_ind = self.rhs_name.currentText()
            self._update_param_hint("rhs", current_ind)
        elif t == "scalar":
            self.rhs_val.setPlaceholderText("numeric value")
        elif t == "column":
            self.rhs_val.setVisible(False)

    def _load(self, rule: Dict):
        for side, type_w, name_w, val_w in [
            ("lhs", self.lhs_type, self.lhs_name, self.lhs_val),
            ("rhs", self.rhs_type, self.rhs_name, self.rhs_val),
        ]:
            d = rule.get(side, {})
            t = d.get("type", "indicator")
            type_w.setCurrentText(t)
            if t == "scalar":
                val_w.setText(str(d.get("value", "")))
            elif t == "column":
                idx = name_w.findText(d.get("column", "close"))
                if idx >= 0: name_w.setCurrentIndex(idx)
            else:  # indicator
                ind = d.get("indicator", "rsi")
                idx = name_w.findText(ind)
                if idx >= 0:
                    name_w.setCurrentIndex(idx)
                else:
                    name_w.setEditText(ind)
                params = d.get("params", {})
                val_w.setText(", ".join(f"{k}={v}" for k, v in params.items()))

        op = rule.get("op", ">")
        idx = self.op.findText(op)
        if idx >= 0: self.op.setCurrentIndex(idx)

    def _parse_params(self, raw: str, indicator: str = None) -> Dict:
        """Parse parameters with type conversion based on indicator defaults"""
        params = {}
        default_params = get_indicator_params(indicator) if indicator else {}

        for part in raw.split(","):
            part = part.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                k = k.strip();
                v = v.strip()

                # Get expected type from defaults
                param_type = get_param_type(k)

                try:
                    if param_type == "int":
                        params[k] = int(v)
                    elif param_type == "float":
                        params[k] = float(v)
                    elif param_type == "bool":
                        params[k] = v.lower() in ("true", "yes", "1")
                    else:
                        params[k] = v
                except ValueError:
                    params[k] = v  # keep as string if conversion fails

        # Merge with defaults for missing params
        for k, default_v in default_params.items():
            if k not in params:
                params[k] = default_v

        return params

    def _collect_side(self, type_w, name_w, val_w) -> Dict:
        t = type_w.currentText()
        if t == "scalar":
            try:
                return {"type": "scalar", "value": float(val_w.text())}
            except:
                return {"type": "scalar", "value": 0}
        elif t == "column":
            return {"type": "column", "column": name_w.currentText()}
        else:
            indicator = name_w.currentText()
            params = self._parse_params(val_w.text(), indicator)
            return {"type": "indicator", "indicator": indicator, "params": params}

    def collect(self) -> Dict:
        return {
            "lhs": self._collect_side(self.lhs_type, self.lhs_name, self.lhs_val),
            "op": self.op.currentText(),
            "rhs": self._collect_side(self.rhs_type, self.rhs_name, self.rhs_val),
        }

# ── Signal Group Panel ────────────────────────────────────────────────────────

class _SignalGroupPanel(QGroupBox):
    def __init__(self, signal: str, parent=None):
        emoji, color, label = SIGNAL_META.get(signal, ("⬤", DIM, signal))
        super().__init__(f" {emoji} {label} ", parent)
        self.signal = signal
        self._color = color
        self._rule_rows: List[_RuleRow] = []

        self.setStyleSheet(f"""
            QGroupBox {{
                background: {BG_PANEL};
                border: 1px solid {color}55;
                border-radius: 6px;
                margin-top: 14px;
                padding: 8px;
                font-weight: bold;
            }}
            QGroupBox::title {{ color: {color}; subcontrol-origin: margin; left:10px; padding:0 4px; }}
        """)

        root = QVBoxLayout(self)
        root.setSpacing(6)

        # Header: logic + enabled
        header = QHBoxLayout()
        lbl_logic = QLabel("Logic:")
        lbl_logic.setStyleSheet(f"color:{DIM}; font-size:9pt;")
        header.addWidget(lbl_logic)
        self.logic_combo = QComboBox()
        self.logic_combo.addItems(["AND", "OR"])
        self.logic_combo.setFixedWidth(80)
        header.addWidget(self.logic_combo)
        header.addSpacing(16)
        self.enabled_chk = QCheckBox("Enabled")
        self.enabled_chk.setChecked(True)
        header.addWidget(self.enabled_chk)
        header.addStretch()
        add_btn = _btn(f"+ Add Rule", color="#21262d")
        add_btn.setFixedHeight(28)
        add_btn.clicked.connect(self._add_rule)
        header.addWidget(add_btn)
        root.addLayout(header)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"QFrame{{border:none; background:{BORDER}; max-height:1px;}}")
        root.addWidget(sep)

        # Rules container (scrollable)
        self._rules_scroll = QScrollArea()
        self._rules_scroll.setWidgetResizable(True)
        self._rules_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._rules_scroll.setMaximumHeight(220)

        self._rules_container = QWidget()
        self._rules_container.setStyleSheet(f"background: transparent;")
        self._rules_vbox = QVBoxLayout(self._rules_container)
        self._rules_vbox.setContentsMargins(0, 0, 0, 0)
        self._rules_vbox.setSpacing(5)

        self._empty_lbl = QLabel("  No rules — click '+ Add Rule' to begin.")
        self._empty_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt; padding:10px;")
        self._rules_vbox.addWidget(self._empty_lbl)
        self._rules_vbox.addStretch()

        self._rules_scroll.setWidget(self._rules_container)
        root.addWidget(self._rules_scroll)

    def _add_rule(self, rule: Dict = None):
        row = _RuleRow(rule, parent=self._rules_container)
        row.deleted.connect(self._remove_rule)
        self._rule_rows.append(row)
        # Insert before the stretch
        insert_at = self._rules_vbox.count() - 1
        self._rules_vbox.insertWidget(insert_at, row)
        self._empty_lbl.setVisible(False)
        # Auto-expand height
        self._rules_scroll.setMaximumHeight(min(220, 50 + 56 * len(self._rule_rows)))

    def _remove_rule(self, row: _RuleRow):
        if row in self._rule_rows:
            self._rule_rows.remove(row)
            self._rules_vbox.removeWidget(row)
            row.deleteLater()
        self._empty_lbl.setVisible(len(self._rule_rows) == 0)

    def load(self, group_data: Dict):
        # Clear existing
        for row in list(self._rule_rows):
            self._remove_rule(row)
        self.logic_combo.setCurrentText(group_data.get("logic", "AND"))
        self.enabled_chk.setChecked(bool(group_data.get("enabled", True)))
        for rule in group_data.get("rules", []):
            self._add_rule(rule)

    def collect(self) -> Dict:
        return {
            "logic":   self.logic_combo.currentText(),
            "enabled": self.enabled_chk.isChecked(),
            "rules":   [row.collect() for row in self._rule_rows],
        }


# ── Signal Rules Tab ──────────────────────────────────────────────────────────

class _SignalRulesTab(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Conflict resolution
        cr_row = QHBoxLayout()
        cr_lbl = QLabel("Conflict Resolution:")
        cr_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt;")
        cr_row.addWidget(cr_lbl)
        self.conflict_combo = QComboBox()
        self.conflict_combo.addItems(["WAIT", "PRIORITY"])
        self.conflict_combo.setFixedWidth(110)
        cr_row.addWidget(self.conflict_combo)
        help_lbl = QLabel("  (when BUY_CALL and BUY_PUT both fire)")
        help_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt;")
        cr_row.addWidget(help_lbl)
        cr_row.addStretch()
        layout.addLayout(cr_row)

        # Signal group panels
        self._panels: Dict[str, _SignalGroupPanel] = {}
        for sig in SIGNAL_GROUPS:
            panel = _SignalGroupPanel(sig)
            self._panels[sig] = panel
            layout.addWidget(panel)

        layout.addStretch()
        self.setWidget(container)

    def load(self, strategy: Dict):
        engine = strategy.get("engine", {})
        self.conflict_combo.setCurrentText(engine.get("conflict_resolution", "WAIT"))
        for sig in SIGNAL_GROUPS:
            self._panels[sig].load(engine.get(sig, {"logic": "AND", "rules": [], "enabled": True}))

    def collect(self) -> Dict:
        result = {}
        for sig in SIGNAL_GROUPS:
            result[sig] = self._panels[sig].collect()
        result["conflict_resolution"] = self.conflict_combo.currentText()
        return result


# ── Strategy List Panel ───────────────────────────────────────────────────────

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

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"QFrame{{border:none;background:{BORDER};max-height:1px;}}")
        root.addWidget(sep)

        # List
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        root.addWidget(self.list_widget, 1)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
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


# ── Main Editor Window ────────────────────────────────────────────────────────

class StrategyEditorWindow(QDialog):
    """
    Full-page strategy editor. Non-modal so trading can continue.
    Emits  strategy_activated(slug)  when the user activates a strategy.
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