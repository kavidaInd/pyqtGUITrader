"""
strategy_editor_window.py
=========================
Redesigned Strategy Editor Window — Modern Professional UI with integrated Theme Manager.

Design Direction: "Refined Command Center"
  • Dark-first terminal aesthetic with amber accent
  • Monospace typography for data density
  • Left-border color coding for visual anchoring
  • Clinical grid layout — every pixel earns its place

Features:
  • Full Theme Manager panel (Dark / Light / High Contrast + 3 Density modes)
  • Strategy list sidebar with live search
  • Tabbed editor: Info | Signal Rules | Indicators | Help
  • Rule builder with LHS / Operator / RHS tri-panel cards
  • Confidence threshold, rule weighting, shift controls
  • Import / Export JSON dialog
  • Unsaved-changes tracking with visual indicator

Integration:
  - Fully compatible with existing theme_manager.py singleton
  - Connects to strategy_manager for CRUD operations
  - Emits strategy_activated(str) signal on activation
  - All colours sourced from theme_manager.palette tokens

Usage:
    from strategy.strategy_editor_window import StrategyEditorWindow
    win = StrategyEditorWindow(parent=main_window)
    win.show()
"""

from __future__ import annotations

import json
import logging
from strategy.strategy_presets import get_preset_names, get_preset_rules
from datetime import datetime
from typing import Dict, List, Optional, Any

from PyQt5.QtCore import (
    Qt, QTimer, pyqtSignal, pyqtSlot, QPoint
)
from PyQt5.QtGui import (
    QFont, QDoubleValidator
)
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QSpinBox,
    QStackedWidget, QTabWidget, QTextEdit, QVBoxLayout, QWidget
)

logger = logging.getLogger(__name__)

# ── Try to import project modules; fall back to stubs for standalone use ──────

try:
    from gui.theme_manager import theme_manager
except ImportError:
    class _FakePalette:
        BG_MAIN = "#0a0e17";
        BG_PANEL = "#0f1520";
        BG_CARD = "#141c2b"
        BG_HOVER = "#1a2438";
        BG_INPUT = "#0d1320";
        BG_SELECTED = "#1e3a5f"
        BORDER = "#1e2d45";
        BORDER_FOCUS = "#3b82f6";
        BORDER_STRONG = "#2d4068"
        TEXT_MAIN = "#e2e8f0";
        TEXT_DIM = "#64748b";
        TEXT_DISABLED = "#334155"
        TEXT_INVERSE = "#0a0e17";
        TEXT_LINK = "#3b82f6"
        ACCENT = "#f59e0b";
        ACCENT_DIM = "#92400e"
        GREEN = "#10b981";
        GREEN_BRIGHT = "#34d399"
        RED = "#ef4444";
        RED_BRIGHT = "#f87171"
        YELLOW = "#f59e0b";
        YELLOW_BRIGHT = "#fbbf24"
        BLUE = "#3b82f6";
        BLUE_DARK = "#1d4ed8"
        ORANGE = "#f97316";
        PURPLE = "#a78bfa";
        CYAN = "#06b6d4"
        BAR_BG = "#0f1520";
        BAR_BORDER = "#1e2d45"
        CHART_BG = "#0a0e17";
        CHART_GRID = "#1a2438"
        PNL_CARD_BG = "#141c2b";
        PNL_ACCENT = "#1d4ed8";
        PNL_DIVIDER = "#1e2d45"

        def get(self, name, default="#000000"): return getattr(self, name, default)


    class _FakeTypography:
        FONT_UI = "Segoe UI";
        FONT_MONO = "Consolas"
        SIZE_XS = 8;
        SIZE_SM = 9;
        SIZE_BODY = 10;
        SIZE_MD = 11
        SIZE_LG = 12;
        SIZE_XL = 14;
        SIZE_2XL = 16;
        SIZE_3XL = 20;
        SIZE_DISPLAY = 24
        SIZE_MONO = 10;
        SIZE_NUMERIC = 11
        WEIGHT_NORMAL = "normal";
        WEIGHT_MEDIUM = "500"
        WEIGHT_BOLD = "bold";
        WEIGHT_HEAVY = "800"
        LETTER_TIGHT = "-0.3px";
        LETTER_NORMAL = "0px";
        LETTER_WIDE = "0.5px"
        LINE_HEIGHT_TIGHT = 1.2;
        LINE_HEIGHT_NORMAL = 1.4
        LINE_HEIGHT_RELAXED = 1.6;
        LINE_HEIGHT_LOG = 1.3

        def get(self, name, default=None): return getattr(self, name, default)


    class _FakeSpacing:
        PAD_XS = 2;
        PAD_SM = 4;
        PAD_MD = 8;
        PAD_LG = 12;
        PAD_XL = 16;
        PAD_2XL = 24
        GAP_XS = 2;
        GAP_SM = 4;
        GAP_MD = 8;
        GAP_LG = 12;
        GAP_XL = 16
        RADIUS_SM = 3;
        RADIUS_MD = 5;
        RADIUS_LG = 8;
        RADIUS_XL = 12;
        RADIUS_PILL = 999
        ROW_HEIGHT = 24;
        BTN_HEIGHT_SM = 28;
        BTN_HEIGHT_MD = 36;
        BTN_HEIGHT_LG = 44
        INPUT_HEIGHT = 32;
        STATUS_BAR_H = 44;
        BUTTON_PANEL_H = 68;
        HEADER_H = 40
        TAB_H = 36;
        PNL_WIDGET_H = 100
        ICON_SM = 12;
        ICON_MD = 16;
        ICON_LG = 20;
        ICON_XL = 24
        SEPARATOR = 1;
        SPLITTER = 2;
        PROGRESS_SM = 4;
        PROGRESS_MD = 8;
        PROGRESS_LG = 12

        def get(self, name, default=0): return getattr(self, name, default)


    class _FakeThemeManager:
        palette = _FakePalette()
        typography = _FakeTypography()
        spacing = _FakeSpacing()
        _current_theme = "dark"
        _current_density = "normal"

        def is_dark(self): return True

        def is_compact(self): return False

        class _Signal:
            def connect(self, *a): pass

            def emit(self, *a): pass

            def disconnect(self, *a): pass

        theme_changed = _Signal()
        density_changed = _Signal()

        def set_theme(self, t): self._current_theme = t

        def set_density(self, d): self._current_density = d

        def toggle(self): pass

        def save_preference(self): pass


    theme_manager = _FakeThemeManager()

try:
    from strategy.strategy_manager import strategy_manager
except ImportError:
    class _FakeStrategyManager:
        def list_strategies(self):
            return [
                {"name": "EMA Crossover", "slug": "ema-cross", "is_active": True},
                {"name": "RSI Mean Revert", "slug": "rsi-strat", "is_active": False},
                {"name": "MACD Trend Follow", "slug": "macd-trend", "is_active": False},
                {"name": "Bollinger Squeeze", "slug": "bb-squeeze", "is_active": False},
            ]

        def get(self, slug):
            return {
                "name": "EMA Crossover", "slug": slug,
                "description": "Sample strategy using EMA crossover signals.",
                "created_at": "2025-01-15 10:00:00",
                "updated_at": "2025-06-20 14:30:00",
                "engine": {
                    "conflict_resolution": "WAIT",
                    "min_confidence": 0.6,
                    "BUY_CALL": {
                        "logic": "AND", "enabled": True,
                        "rules": [
                            {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                             "op": "<", "rhs": {"type": "scalar", "value": 30}, "weight": 2.0},
                            {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 20}},
                             "op": ">", "rhs": {"type": "column", "column": "close"}, "weight": 1.5},
                        ]
                    },
                    "BUY_PUT": {"logic": "AND", "enabled": True, "rules": []},
                    "EXIT_CALL": {"logic": "OR", "enabled": True, "rules": [
                        {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                         "op": ">", "rhs": {"type": "scalar", "value": 70}, "weight": 1.0},
                    ]},
                    "EXIT_PUT": {"logic": "AND", "enabled": False, "rules": []},
                    "HOLD": {"logic": "AND", "enabled": True, "rules": []},
                }
            }

        def get_active_slug(self): return "ema-cross"

        def create(self, name):
            import re
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            return True, slug

        def duplicate(self, slug, name):
            import re
            new_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            return True, new_slug

        def save(self, slug, data): return True

        def activate(self, slug): pass

        def delete(self, slug): return True, "deleted"


    strategy_manager = _FakeStrategyManager()

try:
    from strategy.indicator_registry import (
        ALL_INDICATORS, get_indicator_params, get_indicator_category,
        get_indicators_by_category, get_suggested_weight,
        get_indicator_sub_columns, get_rule_weight_range,
        get_param_type, get_param_description
    )
except ImportError:
    ALL_INDICATORS = [
        "rsi", "ema", "sma", "macd", "bb", "atr", "stoch", "adx",
        "obv", "vwap", "cci", "mfi", "psar", "kama", "dema", "tema",
        "wma", "hma", "zlema", "trix", "dpo", "williams_r", "ultimate_osc",
    ]


    def get_indicator_params(ind):
        defaults = {"rsi": {"length": 14}, "ema": {"length": 20}, "sma": {"length": 20},
                    "macd": {"fast": 12, "slow": 26, "signal": 9},
                    "bb": {"length": 20, "std": 2.0}, "atr": {"length": 14},
                    "stoch": {"k": 14, "d": 3}, "adx": {"length": 14}}
        return defaults.get(ind, {"length": 14})


    def get_indicator_category(ind):
        cats = {"rsi": "Momentum", "ema": "Trend", "sma": "Trend",
                "macd": "Momentum", "bb": "Volatility", "atr": "Volatility",
                "stoch": "Momentum", "adx": "Trend", "obv": "Volume",
                "vwap": "Volume", "cci": "Momentum", "mfi": "Volume"}
        return cats.get(ind, "Other")


    def get_indicators_by_category():
        cats: Dict[str, List[str]] = {}
        for ind in ALL_INDICATORS:
            c = get_indicator_category(ind)
            cats.setdefault(c, []).append(ind)
        return cats


    def get_suggested_weight(ind):
        weights = {"rsi": 2.0, "macd": 2.5, "ema": 1.5, "sma": 1.0,
                   "bb": 1.8, "atr": 1.2, "adx": 2.0, "stoch": 1.7}
        return weights.get(ind, 1.0)


    def get_indicator_sub_columns(ind):
        subs = {"macd": [("MACD", "MACD Line", "Main line"), ("SIGNAL", "Signal Line", "Signal"),
                         ("HIST", "Histogram", "Hist")],
                "bb": [("LOWER", "Lower Band", "Lower"), ("MID", "Middle Band", "Mid"),
                       ("UPPER", "Upper Band", "Upper")],
                "stoch": [("K", "Stoch %K", "%K"), ("D", "Stoch %D", "%D")]}
        return subs.get(ind, [])


    def get_rule_weight_range():
        return {"min": 0.1, "max": 5.0, "step": 0.1, "default": 1.0,
                "description": "Rule weight for confidence scoring (0.1–5.0)"}


    def get_param_type(param):
        _int = {"length", "fast", "slow", "signal", "k", "d", "smooth_k",
                "drift", "offset", "ddof", "atr_length"}
        _float = {"std", "multiplier", "scalar", "af0", "af", "max_af",
                  "bb_std", "kc_scalar", "q"}
        if param in _int:
            return "int"
        if param in _float:
            return "float"
        return "string"


    def get_param_description(param):
        _desc = {"length": "Number of periods", "fast": "Fast period",
                 "slow": "Slow period", "signal": "Signal period",
                 "std": "Std deviation multiplier", "multiplier": "ATR multiplier",
                 "drift": "Lookback for difference", "offset": "Period offset"}
        return _desc.get(param, "")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

OPERATORS = [">", "<", ">=", "<=", "==", "!=", "between"]
SIDE_TYPES = ["indicator", "scalar", "column"]
COLUMNS = ["close", "open", "high", "low", "volume", "hl2", "hlc3", "ohlc4"]
TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]

SIGNAL_GROUPS = [
    ("BUY_CALL", "📈 BUY CALL", "ACCENT"),
    ("BUY_PUT", "📉 BUY PUT", "BLUE"),
    ("EXIT_CALL", "🔴 EXIT CALL", "RED"),
    ("EXIT_PUT", "🟠 EXIT PUT", "ORANGE"),
    ("HOLD", "⏸  HOLD", "YELLOW"),
]

SIGNAL_COLOR_MAP = {
    "BUY_CALL": "GREEN",
    "BUY_PUT": "BLUE",
    "EXIT_CALL": "RED",
    "EXIT_PUT": "ORANGE",
    "HOLD": "YELLOW",
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def c() -> Any:
    """Shortcut to current palette."""
    return theme_manager.palette


def ty() -> Any:
    """Shortcut to current typography."""
    return theme_manager.typography


def sp() -> Any:
    """Shortcut to current spacing."""
    return theme_manager.spacing


def make_separator(horizontal: bool = True) -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine if horizontal else QFrame.VLine)
    sep.setStyleSheet(f"background: {c().BORDER}; max-height: 1px;" if horizontal
                      else f"background: {c().BORDER}; max-width: 1px;")
    return sep


def styled_button(text: str, bg: str, hover: str, fg: str = None,
                  min_w: int = 0, min_h: int = 0, bold: bool = True) -> QPushButton:
    """Create a fully styled button."""
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    fg = fg or c().TEXT_INVERSE
    h = min_h or sp().BTN_HEIGHT_MD
    style = f"""
        QPushButton {{
            background: {bg};
            color: {fg};
            border: none;
            border-radius: {sp().RADIUS_MD}px;
            padding: {sp().PAD_SM}px {sp().PAD_LG}px;
            font-size: {ty().SIZE_BODY}pt;
            font-weight: {"bold" if bold else "normal"};
            font-family: 'Segoe UI';
            {"min-width:" + str(min_w) + "px;" if min_w else ""}
            min-height: {h}px;
            letter-spacing: 0.3px;
        }}
        QPushButton:hover {{ background: {hover}; }}
        QPushButton:pressed {{ background: {hover}; border: 1px solid {c().BORDER_STRONG}; }}
        QPushButton:disabled {{
            background: {c().BG_HOVER};
            color: {c().TEXT_DISABLED};
        }}
    """
    btn.setStyleSheet(style)
    return btn


def ghost_button(text: str, color: str = None, min_w: int = 0) -> QPushButton:
    """Transparent border-only button."""
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    fg = color or c().TEXT_DIM
    style = f"""
        QPushButton {{
            background: transparent;
            color: {fg};
            border: 1px solid {fg}55;
            border-radius: {sp().RADIUS_MD}px;
            padding: {sp().PAD_SM}px {sp().PAD_MD}px;
            font-size: {ty().SIZE_BODY}pt;
            {"min-width:" + str(min_w) + "px;" if min_w else ""}
        }}
        QPushButton:hover {{
            background: {fg}22;
            border-color: {fg};
        }}
        QPushButton:pressed {{ background: {fg}33; }}
        QPushButton:disabled {{
            color: {c().TEXT_DISABLED};
            border-color: {c().BORDER};
        }}
    """
    btn.setStyleSheet(style)
    return btn


def section_label(text: str) -> QLabel:
    """Small uppercase section label."""
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        color: {c().TEXT_DIM};
        font-size: {ty().SIZE_XS}pt;
        font-weight: bold;
        letter-spacing: 0.8px;
        text-transform: uppercase;
    """)
    return lbl


def accent_label(text: str, color: str = None) -> QLabel:
    """Coloured bold label."""
    lbl = QLabel(text)
    col = color or c().BLUE
    lbl.setStyleSheet(f"""
        color: {col};
        font-size: {ty().SIZE_XS}pt;
        font-weight: bold;
        letter-spacing: 0.6px;
    """)
    return lbl


def pill_badge(text: str, color: str) -> QLabel:
    """Pill-shaped colored badge."""
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(f"""
        QLabel {{
            color: {color};
            background: {color}22;
            border: 1px solid {color}55;
            border-radius: 999px;
            padding: 1px 8px;
            font-size: {ty().SIZE_XS}pt;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
    """)
    return lbl


def styled_input(placeholder: str = "") -> QLineEdit:
    ed = QLineEdit()
    ed.setPlaceholderText(placeholder)
    ed.setStyleSheet(f"""
        QLineEdit {{
            background: {c().BG_INPUT};
            color: {c().TEXT_MAIN};
            border: 1px solid {c().BORDER};
            border-radius: {sp().RADIUS_MD}px;
            padding: {sp().PAD_SM}px {sp().PAD_MD}px;
            font-size: {ty().SIZE_BODY}pt;
            min-height: {sp().INPUT_HEIGHT}px;
            selection-background-color: {c().BG_SELECTED};
        }}
        QLineEdit:focus {{ border-color: {c().BORDER_FOCUS}; }}
        QLineEdit:disabled {{ color: {c().TEXT_DISABLED}; background: {c().BG_PANEL}; }}
    """)
    return ed


def styled_combo(items: List[str] = None, min_w: int = 0) -> QComboBox:
    cb = QComboBox()
    if items:
        cb.addItems(items)
    cb.setCursor(Qt.PointingHandCursor)
    cb.setStyleSheet(f"""
        QComboBox {{
            background: {c().BG_INPUT};
            color: {c().TEXT_MAIN};
            border: 1px solid {c().BORDER};
            border-radius: {sp().RADIUS_MD}px;
            padding: {sp().PAD_SM}px {sp().PAD_MD}px;
            font-size: {ty().SIZE_BODY}pt;
            min-height: {sp().INPUT_HEIGHT}px;
            {"min-width:" + str(min_w) + "px;" if min_w else ""}
        }}
        QComboBox:hover {{ border-color: {c().BORDER_FOCUS}; }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox QAbstractItemView {{
            background: {c().BG_PANEL};
            color: {c().TEXT_MAIN};
            border: 1px solid {c().BORDER};
            selection-background-color: {c().BG_SELECTED};
            outline: none;
        }}
        QComboBox QAbstractItemView::item {{
            padding: {sp().PAD_SM}px {sp().PAD_MD}px;
            min-height: 24px;
        }}
    """)
    return cb


def styled_spinbox(min_v: float, max_v: float, step: float = 1.0,
                   decimals: int = 0, val: float = 0) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(min_v, max_v)
    sb.setSingleStep(step)
    sb.setDecimals(decimals)
    sb.setValue(val)
    sb.setAlignment(Qt.AlignCenter)
    sb.setStyleSheet(f"""
        QDoubleSpinBox {{
            background: {c().BG_INPUT};
            color: {c().TEXT_MAIN};
            border: 1px solid {c().BORDER};
            border-radius: {sp().RADIUS_MD}px;
            padding: {sp().PAD_SM}px;
            font-size: {ty().SIZE_BODY}pt;
            min-height: {sp().INPUT_HEIGHT}px;
        }}
        QDoubleSpinBox:focus {{ border-color: {c().BORDER_FOCUS}; }}
    """)
    return sb


# ─────────────────────────────────────────────────────────────────────────────
# THEME MANAGER PANEL
# ─────────────────────────────────────────────────────────────────────────────

class ThemeManagerPanel(QFrame):
    """Floating panel for live theme / density switching."""

    theme_changed = pyqtSignal(str)
    density_changed = pyqtSignal(str)

    THEMES = [
        ("dark", "◐  Dark", "#0f1520"),
        ("light", "○  Light", "#f6f8fa"),
        ("contrast", "●  Contrast", "#000000"),
    ]
    DENSITIES = [
        ("compact", "Compact"),
        ("normal", "Normal"),
        ("relaxed", "Relaxed"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("themePanel")
        self.setFixedWidth(300)
        self._build_ui()
        self._apply_style()
        # auto-hide on focus loss
        self.setWindowFlags(Qt.Popup)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QFrame#themePanel {{
                background: {c().BG_PANEL};
                border: 1px solid {c().BORDER_FOCUS};
                border-radius: {sp().RADIUS_LG}px;
            }}
        """)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(sp().PAD_XL, sp().PAD_XL, sp().PAD_XL, sp().PAD_XL)
        root.setSpacing(sp().GAP_LG)

        # Header
        hdr = QLabel("⚙  Theme Manager")
        hdr.setStyleSheet(f"""
            color: {c().TEXT_MAIN};
            font-size: {ty().SIZE_LG}pt;
            font-weight: bold;
            padding-bottom: {sp().PAD_SM}px;
            border-bottom: 1px solid {c().BORDER};
        """)
        root.addWidget(hdr)

        # ── Color scheme ──────────────────────────────────────────────────────
        root.addWidget(section_label("COLOR SCHEME"))
        theme_row = QHBoxLayout()
        theme_row.setSpacing(sp().GAP_MD)
        self._theme_btns: Dict[str, QPushButton] = {}
        for key, label, preview_bg in self.THEMES:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setChecked(key == theme_manager._current_theme)
            btn.clicked.connect(lambda checked, k=key: self._on_theme(k))
            self._theme_btns[key] = btn
            theme_row.addWidget(btn)
        self._style_theme_buttons()
        root.addLayout(theme_row)

        # ── Density ───────────────────────────────────────────────────────────
        root.addWidget(section_label("UI DENSITY"))
        density_row = QHBoxLayout()
        density_row.setSpacing(sp().GAP_MD)
        self._density_btns: Dict[str, QPushButton] = {}
        for key, label in self.DENSITIES:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setChecked(key == theme_manager._current_density)
            btn.clicked.connect(lambda checked, k=key: self._on_density(k))
            self._density_btns[key] = btn
            density_row.addWidget(btn)
        self._style_density_buttons()
        root.addLayout(density_row)

        # ── Confidence threshold ──────────────────────────────────────────────
        root.addWidget(section_label("DEFAULT CONFIDENCE THRESHOLD"))
        conf_row = QHBoxLayout()
        conf_row.setSpacing(sp().GAP_MD)
        self.conf_slider = QSlider(Qt.Horizontal)
        self.conf_slider.setRange(0, 100)
        self.conf_slider.setValue(60)
        self.conf_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {c().BORDER};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {c().ACCENT if hasattr(c(), 'ACCENT') else c().BLUE};
                width: 14px;
                height: 14px;
                border-radius: 7px;
                margin: -5px 0;
            }}
            QSlider::sub-page:horizontal {{
                background: {c().ACCENT if hasattr(c(), 'ACCENT') else c().BLUE};
                height: 4px;
                border-radius: 2px;
            }}
        """)
        self.conf_value_lbl = QLabel("0.60")
        self.conf_value_lbl.setStyleSheet(f"""
            color: {c().ACCENT if hasattr(c(), 'ACCENT') else c().YELLOW};
            font-weight: bold;
            font-size: {ty().SIZE_LG}pt;
            min-width: 40px;
        """)
        self.conf_slider.valueChanged.connect(
            lambda v: self.conf_value_lbl.setText(f"{v / 100:.2f}")
        )
        conf_row.addWidget(self.conf_slider)
        conf_row.addWidget(self.conf_value_lbl)
        root.addLayout(conf_row)

        # ── Save ──────────────────────────────────────────────────────────────
        save_btn = styled_button(
            "💾  Save Preferences",
            c().GREEN, c().GREEN_BRIGHT, min_w=140
        )
        save_btn.clicked.connect(self._save_prefs)
        root.addWidget(save_btn)

    def _style_theme_buttons(self):
        active = theme_manager._current_theme
        accent = getattr(c(), "ACCENT", c().BLUE)
        for key, btn in self._theme_btns.items():
            if key == active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {accent}33;
                        color: {accent};
                        border: 1px solid {accent};
                        border-radius: {sp().RADIUS_MD}px;
                        padding: {sp().PAD_MD}px;
                        font-weight: bold;
                        font-size: {ty().SIZE_SM}pt;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {c().BG_HOVER};
                        color: {c().TEXT_DIM};
                        border: 1px solid {c().BORDER};
                        border-radius: {sp().RADIUS_MD}px;
                        padding: {sp().PAD_MD}px;
                        font-size: {ty().SIZE_SM}pt;
                    }}
                    QPushButton:hover {{ background: {c().BORDER}; color: {c().TEXT_MAIN}; }}
                """)

    def _style_density_buttons(self):
        active = theme_manager._current_density
        for key, btn in self._density_btns.items():
            if key == active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {c().BLUE}33;
                        color: {c().BLUE};
                        border: 1px solid {c().BLUE};
                        border-radius: {sp().RADIUS_MD}px;
                        padding: {sp().PAD_MD}px;
                        font-weight: bold;
                        font-size: {ty().SIZE_SM}pt;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {c().BG_HOVER};
                        color: {c().TEXT_DIM};
                        border: 1px solid {c().BORDER};
                        border-radius: {sp().RADIUS_MD}px;
                        padding: {sp().PAD_MD}px;
                        font-size: {ty().SIZE_SM}pt;
                    }}
                    QPushButton:hover {{ background: {c().BORDER}; color: {c().TEXT_MAIN}; }}
                """)

    def _on_theme(self, key: str):
        theme_manager.set_theme(key)
        self._style_theme_buttons()
        self.theme_changed.emit(key)

    def _on_density(self, key: str):
        theme_manager.set_density(key)
        self._style_density_buttons()
        self.density_changed.emit(key)

    def _save_prefs(self):
        theme_manager.save_preference()

    def get_confidence(self) -> float:
        return self.conf_slider.value() / 100.0


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY LIST SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

class StrategyListPanel(QWidget):
    """Left sidebar: searchable strategy list with CRUD actions."""

    strategy_selected = pyqtSignal(str)
    strategy_activated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_slug: Optional[str] = None
        self.setFixedWidth(270)
        self._build_ui()
        self._apply_style()
        self.refresh()
        try:
            theme_manager.theme_changed.connect(self._on_theme)
            theme_manager.density_changed.connect(self._on_theme)
        except Exception:
            pass

    def _apply_style(self):
        self.setStyleSheet(f"""
            QWidget {{
                background: {c().BG_PANEL};
                border-right: 1px solid {c().BORDER};
            }}
        """)

    def _on_theme(self, _=None):
        self._apply_style()
        self._restyle_list()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr_widget = QWidget()
        hdr_widget.setFixedHeight(40)
        hdr_widget.setStyleSheet(f"background: {c().BG_PANEL};")
        hdr_lay = QHBoxLayout(hdr_widget)
        hdr_lay.setContentsMargins(sp().PAD_LG, 0, sp().PAD_MD, 0)
        hdr_lay.setSpacing(sp().GAP_SM)

        # Amber accent stripe on left
        stripe = QFrame()
        stripe.setFixedWidth(3)
        stripe.setFixedHeight(18)
        accent = getattr(c(), "ACCENT", c().YELLOW)
        stripe.setStyleSheet(f"background: {accent}; border-radius: 2px;")
        hdr_lay.addWidget(stripe)

        title_lbl = QLabel("STRATEGIES")
        title_lbl.setStyleSheet(f"""
                    color: {c().TEXT_MAIN};
                    font-size: {ty().SIZE_SM}pt;
                    font-weight: bold;
                    letter-spacing: 1.2px;
                """)
        hdr_lay.addWidget(title_lbl)
        hdr_lay.addStretch()
        root.addWidget(hdr_widget)

        # ── Action buttons row ────────────────────────────────────────────────
        btn_widget = QWidget()
        btn_widget.setStyleSheet(f"""
                    background: {c().BG_PANEL};
                    border-bottom: 1px solid {c().BORDER};
                """)
        btn_lay = QHBoxLayout(btn_widget)
        btn_lay.setContentsMargins(sp().PAD_MD, sp().PAD_SM, sp().PAD_MD, sp().PAD_SM)
        btn_lay.setSpacing(sp().GAP_SM)

        self.new_btn = QPushButton("＋ New")
        self.new_btn.setFixedHeight(30)
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.setToolTip("Create a new strategy")
        self.new_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {c().GREEN};
                        color: #000000;
                        border: none;
                        border-radius: {sp().RADIUS_MD}px;
                        padding: 0px {sp().PAD_MD}px;
                        font-size: {ty().SIZE_SM}pt;
                        font-weight: bold;
                        letter-spacing: 0.3px;
                    }}
                    QPushButton:hover {{ background: {c().GREEN_BRIGHT}; }}
                    QPushButton:pressed {{ background: {c().GREEN}CC; }}
                """)
        self.new_btn.clicked.connect(self._on_new)
        btn_lay.addWidget(self.new_btn)

        self.dup_btn = QPushButton("⧉ Copy")
        self.dup_btn.setFixedHeight(30)
        self.dup_btn.setCursor(Qt.PointingHandCursor)
        self.dup_btn.setToolTip("Duplicate selected strategy")
        self.dup_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {c().BG_INPUT};
                        color: {c().TEXT_MAIN};
                        border: 1px solid {c().BORDER_STRONG};
                        border-radius: {sp().RADIUS_MD}px;
                        padding: 0px {sp().PAD_MD}px;
                        font-size: {ty().SIZE_SM}pt;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background: {c().BG_HOVER};
                        border-color: {c().ACCENT if hasattr(c(), "ACCENT") else c().YELLOW};
                        color: {c().ACCENT if hasattr(c(), "ACCENT") else c().YELLOW};
                    }}
                    QPushButton:pressed {{ background: {c().BORDER}; }}
                """)
        self.dup_btn.clicked.connect(self._on_dup)
        btn_lay.addWidget(self.dup_btn)
        btn_lay.addStretch()
        root.addWidget(btn_widget)

        # ── Search ────────────────────────────────────────────────────────────
        search_widget = QWidget()
        search_widget.setStyleSheet(f"background: {c().BG_PANEL};")
        search_lay = QHBoxLayout(search_widget)
        search_lay.setContentsMargins(sp().PAD_MD, sp().PAD_SM, sp().PAD_MD, sp().PAD_SM)

        search_icon = QLabel("⌕")
        search_icon.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_LG}pt; background: transparent;")
        search_lay.addWidget(search_icon)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search strategies...")
        self.search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {c().BG_INPUT};
                color: {c().TEXT_MAIN};
                border: 1px solid {c().BORDER};
                border-radius: {sp().RADIUS_MD}px;
                padding: {sp().PAD_SM}px {sp().PAD_MD}px;
                font-size: {ty().SIZE_SM}pt;
                min-height: 28px;
            }}
            QLineEdit:focus {{ border-color: {c().BORDER_FOCUS}; }}
        """)
        self.search_edit.textChanged.connect(self._filter_list)
        search_lay.addWidget(self.search_edit)
        root.addWidget(search_widget)
        root.addWidget(make_separator())

        # ── Strategy List ─────────────────────────────────────────────────────
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        self._restyle_list()
        root.addWidget(self.list_widget, 1)

        root.addWidget(make_separator())

        # ── Bottom Actions ────────────────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(f"background: {c().BG_PANEL};")
        footer_lay = QVBoxLayout(footer)
        footer_lay.setContentsMargins(sp().PAD_MD, sp().PAD_MD, sp().PAD_MD, sp().PAD_MD)
        footer_lay.setSpacing(sp().GAP_SM)

        self.activate_btn = styled_button(
            "⚡  Activate Strategy",
            c().BLUE, c().BLUE_DARK, min_w=200, min_h=40
        )
        self.activate_btn.clicked.connect(self._on_activate)
        footer_lay.addWidget(self.activate_btn)

        self.delete_btn = ghost_button("🗑  Delete", c().RED, min_w=100)
        self.delete_btn.clicked.connect(self._on_delete)
        footer_lay.addWidget(self.delete_btn)
        root.addWidget(footer)

    def _restyle_list(self):
        accent = getattr(c(), "ACCENT", c().YELLOW)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {c().BG_PANEL};
                color: {c().TEXT_MAIN};
                border: none;
                font-size: {ty().SIZE_BODY}pt;
                outline: none;
            }}
            QListWidget::item {{
                padding: {sp().PAD_MD}px {sp().PAD_LG}px;
                border-bottom: 1px solid {c().BORDER};
                border-left: 3px solid transparent;
            }}
            QListWidget::item:selected {{
                background: {c().BG_SELECTED};
                color: {c().TEXT_MAIN};
                border-left: 3px solid {accent};
            }}
            QListWidget::item:hover:!selected {{
                background: {c().BG_HOVER};
                border-left: 3px solid {c().BORDER_STRONG};
            }}
            QScrollBar:vertical {{
                background: {c().BG_PANEL};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {c().BORDER_STRONG};
                border-radius: 3px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def refresh(self):
        """Reload all strategies from manager."""
        try:
            self.list_widget.blockSignals(True)
            self.list_widget.clear()
            active_slug = strategy_manager.get_active_slug()
            accent = getattr(c(), "ACCENT", c().YELLOW)

            for s in strategy_manager.list_strategies():
                slug = s.get("slug", "")
                name = s.get("name", slug)
                is_active = s.get("is_active", False) or (slug == active_slug)

                item = QListWidgetItem()

                # Custom widget for richer display
                item_widget = self._make_list_item_widget(name, slug, is_active, accent)
                item.setSizeHint(item_widget.sizeHint())
                item.setData(Qt.UserRole, slug)

                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, item_widget)

                if slug == self._current_slug:
                    self.list_widget.setCurrentItem(item)

            self.list_widget.blockSignals(False)

            if self.list_widget.currentItem() is None and self.list_widget.count() > 0:
                self.list_widget.setCurrentRow(0)

        except Exception as e:
            logger.error(f"[StrategyListPanel.refresh] Failed: {e}", exc_info=True)

    def _make_list_item_widget(self, name: str, slug: str, is_active: bool, accent: str) -> QWidget:
        """Rich list item with name + metadata row."""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        if is_active:
            bolt = QLabel("⚡")
            bolt.setStyleSheet(f"color: {accent}; font-size: {ty().SIZE_BODY}pt; background: transparent;")
            name_row.addWidget(bolt)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"""
            color: {accent if is_active else c().TEXT_MAIN};
            font-weight: {"bold" if is_active else "normal"};
            font-size: {ty().SIZE_BODY}pt;
            background: transparent;
        """)
        name_row.addWidget(name_lbl)
        name_row.addStretch()
        lay.addLayout(name_row)

        sub_row = QHBoxLayout()
        sub_row.setSpacing(8)
        slug_lbl = QLabel(slug[:24])
        slug_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_XS}pt; background: transparent;")
        sub_row.addWidget(slug_lbl)
        if is_active:
            active_badge = QLabel("ACTIVE")
            active_badge.setStyleSheet(f"""
                color: {accent};
                background: {accent}22;
                border: 1px solid {accent}55;
                border-radius: 4px;
                padding: 0px 5px;
                font-size: {ty().SIZE_XS}pt;
                font-weight: bold;
            """)
            sub_row.addWidget(active_badge)
        sub_row.addStretch()
        lay.addLayout(sub_row)

        w.setMinimumHeight(48)
        return w

    def _filter_list(self, text: str):
        text = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            slug = item.data(Qt.UserRole) or ""
            hide = text and text not in slug.lower()
            item.setHidden(hide)

    def _on_item_changed(self, current, previous):
        try:
            if current:
                slug = current.data(Qt.UserRole)
                self._current_slug = slug
                self.strategy_selected.emit(slug)
        except Exception as e:
            logger.error(f"[StrategyListPanel._on_item_changed] {e}")

    def _on_double_click(self, item):
        slug = item.data(Qt.UserRole)
        if slug:
            self._activate_slug(slug)

    def _on_new(self):
        name, ok = QInputDialog.getText(self, "New Strategy", "Strategy name:", text="My Strategy")
        if ok and name.strip():
            ok2, slug = strategy_manager.create(name.strip())
            if ok2:
                self._current_slug = slug
                self.refresh()
                self.strategy_selected.emit(slug)

    def _on_dup(self):
        if not self._current_slug:
            return
        src = strategy_manager.get(self._current_slug)
        src_name = src.get("name", self._current_slug) if src else self._current_slug
        name, ok = QInputDialog.getText(self, "Duplicate Strategy", "New name:", text=f"{src_name} (copy)")
        if ok and name.strip():
            ok2, slug = strategy_manager.duplicate(self._current_slug, name.strip())
            if ok2:
                self._current_slug = slug
                self.refresh()
                self.strategy_selected.emit(slug)

    def _on_activate(self):
        if self._current_slug:
            self._activate_slug(self._current_slug)

    def _activate_slug(self, slug: str):
        strategy_manager.activate(slug)
        self.refresh()
        self.strategy_activated.emit(slug)

    def _on_delete(self):
        if not self._current_slug:
            return
        s = strategy_manager.get(self._current_slug)
        name = s.get("name", self._current_slug) if s else self._current_slug
        ans = QMessageBox.question(
            self, "Delete Strategy",
            f"Delete '{name}'?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if ans == QMessageBox.Yes:
            success, msg = strategy_manager.delete(self._current_slug)
            if not success:
                QMessageBox.warning(self, "Cannot Delete", msg)
            else:
                self._current_slug = strategy_manager.get_active_slug()
                self.refresh()
                if self._current_slug:
                    self.strategy_selected.emit(self._current_slug)


# ─────────────────────────────────────────────────────────────────────────────
# RULE ROW WIDGET
# ─────────────────────────────────────────────────────────────────────────────

class RuleRowWidget(QFrame):
    """
    Single editable rule row.
    Visual layout:  [## | LHS panel | OPERATOR | RHS panel | WEIGHT | ✕]
    Each side has: type-selector + shift + indicator/scalar/column input.
    """

    deleted = pyqtSignal(object)
    rule_changed = pyqtSignal()

    def __init__(self, rule: Dict = None, index: int = 0, parent=None):
        super().__init__(parent)
        self._index = index
        self._rule = rule or {}
        self._build_ui()
        self._load(self._rule)
        self._update_description()
        try:
            theme_manager.theme_changed.connect(self._apply_theme)
            theme_manager.density_changed.connect(self._apply_theme)
        except Exception:
            pass

    def _apply_theme(self, _=None):
        self._style_frame()

    def _style_frame(self):
        accent = getattr(c(), "ACCENT", c().YELLOW)
        self.setStyleSheet(f"""
            QFrame#ruleRow {{
                background: {c().BG_CARD if hasattr(c(), 'BG_CARD') else c().BG_HOVER};
                border: 1px solid {c().BORDER};
                border-left: 3px solid {c().BORDER};
                border-radius: {sp().RADIUS_MD}px;
            }}
            QFrame#ruleRow:hover {{
                border-left: 3px solid {accent};
            }}
        """)

    def _build_ui(self):
        self.setObjectName("ruleRow")
        self._style_frame()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(sp().PAD_SM, sp().PAD_SM, sp().PAD_SM, sp().PAD_SM)
        root.setSpacing(sp().GAP_SM)

        # ── Main row ──────────────────────────────────────────────────────────
        main_row = QHBoxLayout()
        main_row.setSpacing(sp().GAP_MD)

        # Index badge
        self.idx_lbl = QLabel(f"{self._index + 1:02d}")
        self.idx_lbl.setFixedWidth(28)
        self.idx_lbl.setAlignment(Qt.AlignCenter)
        self.idx_lbl.setStyleSheet(f"""
            color: {c().TEXT_DIM};
            font-size: {ty().SIZE_XS}pt;
            font-weight: bold;
            background: {c().BG_INPUT};
            border-radius: {sp().RADIUS_SM}px;
            padding: 2px;
        """)
        main_row.addWidget(self.idx_lbl)

        # ── LHS ──────────────────────────────────────────────────────────────
        lhs_card = self._make_side_card("lhs", "LEFT SIDE", c().BLUE)
        main_row.addWidget(lhs_card, 4)

        # ── Operator ──────────────────────────────────────────────────────────
        op_card = self._make_op_card()
        main_row.addWidget(op_card)

        # ── RHS ──────────────────────────────────────────────────────────────
        rhs_card = self._make_side_card("rhs", "RIGHT SIDE", c().ORANGE)
        main_row.addWidget(rhs_card, 4)

        # ── Weight ───────────────────────────────────────────────────────────
        weight_card = self._make_weight_card()
        main_row.addWidget(weight_card)

        # ── Delete ────────────────────────────────────────────────────────────
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(30, 30)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: {c().RED}22;
                color: {c().RED};
                border: 1px solid {c().RED}55;
                border-radius: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {c().RED}55; }}
        """)
        del_btn.clicked.connect(lambda: self.deleted.emit(self))
        main_row.addWidget(del_btn)

        root.addLayout(main_row)

        # ── Description bar ───────────────────────────────────────────────────
        self.desc_lbl = QLabel("ⓘ Rule will be evaluated on each bar")
        self.desc_lbl.setStyleSheet(f"""
            color: {c().TEXT_DIM};
            font-size: {ty().SIZE_XS}pt;
            font-style: italic;
            padding-left: 36px;
        """)
        root.addWidget(self.desc_lbl)

    def _make_side_card(self, side: str, header: str, header_color: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {c().BG_INPUT};
                border: 1px solid {c().BORDER};
                border-top: 2px solid {header_color};
                border-radius: {sp().RADIUS_MD}px;
                padding: {sp().PAD_SM}px;
            }}
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(sp().PAD_SM, sp().PAD_SM, sp().PAD_SM, sp().PAD_SM)
        lay.setSpacing(sp().GAP_SM)

        # Header label
        hdr = QLabel(header)
        hdr.setStyleSheet(f"""
            color: {header_color};
            font-size: {ty().SIZE_XS}pt;
            font-weight: bold;
            letter-spacing: 0.5px;
        """)
        lay.addWidget(hdr)

        # Type + shift row
        type_row = QHBoxLayout()
        type_row.setSpacing(sp().GAP_SM)

        type_cb = styled_combo(SIDE_TYPES)
        type_cb.setFixedWidth(100)
        type_row.addWidget(type_cb)

        shift_sb = QSpinBox()
        shift_sb.setRange(0, 100)
        shift_sb.setValue(0)
        shift_sb.setPrefix("  ⏱")
        shift_sb.setSuffix(" bars")
        shift_sb.setFixedWidth(90)
        shift_sb.setToolTip("Bars to look back (0 = current bar)")
        shift_sb.setStyleSheet(f"""
            QSpinBox {{
                background: {c().BG_INPUT};
                color: {c().TEXT_MAIN};
                border: 1px solid {c().BORDER};
                border-radius: {sp().RADIUS_SM}px;
                padding: {sp().PAD_XS}px;
                font-size: {ty().SIZE_XS}pt;
            }}
            QSpinBox:focus {{ border-color: {c().BORDER_FOCUS}; }}
        """)
        type_row.addWidget(shift_sb)
        type_row.addStretch()
        lay.addLayout(type_row)

        # Stacked input area
        stack = QStackedWidget()

        # Page 0: Indicator
        ind_page = QWidget()
        ind_lay = QVBoxLayout(ind_page)
        ind_lay.setContentsMargins(0, 0, 0, 0)
        ind_lay.setSpacing(sp().GAP_XS)
        ind_cb = QComboBox()
        ind_cb.setEditable(True)
        ind_cb.addItems([i.upper() for i in ALL_INDICATORS])
        ind_cb.setStyleSheet(f"""
                    QComboBox {{
                        background: {c().BG_INPUT};
                        color: {c().GREEN};
                        border: 1px solid {c().BORDER};
                        border-radius: {sp().RADIUS_SM}px;
                        padding: {sp().PAD_XS}px 28px {sp().PAD_XS}px {sp().PAD_SM}px;
                        font-size: {ty().SIZE_BODY}pt;
                        font-weight: bold;
                        min-height: 28px;
                    }}
                    QComboBox:hover {{
                        border-color: {c().GREEN};
                        background: {c().BG_HOVER};
                    }}
                    QComboBox::drop-down {{
                        subcontrol-origin: padding;
                        subcontrol-position: top right;
                        width: 26px;
                        border-left: 1px solid {c().BORDER};
                        border-top-right-radius: {sp().RADIUS_SM}px;
                        border-bottom-right-radius: {sp().RADIUS_SM}px;
                        background: {c().GREEN}22;
                    }}
                    QComboBox::drop-down:hover {{
                        background: {c().GREEN}44;
                    }}
                    QComboBox::down-arrow {{
                        image: none;
                        width: 0;
                        height: 0;
                        border-left: 4px solid transparent;
                        border-right: 4px solid transparent;
                        border-top: 6px solid {c().GREEN};
                    }}
                    QComboBox QAbstractItemView {{
                        background: {c().BG_PANEL};
                        color: {c().TEXT_MAIN};
                        border: 1px solid {c().BORDER};
                        selection-background-color: {c().BG_SELECTED};
                    }}
                """)
        ind_lay.addWidget(ind_cb)

        sub_col_cb = styled_combo()
        sub_col_cb.hide()
        ind_lay.addWidget(sub_col_cb)

        # ── Indicator Parameters Panel ────────────────────────────────────────
        # Shown below the indicator combo; rebuilt whenever the indicator changes.
        # Each parameter gets a compact labeled row: int → QSpinBox,
        # float → QDoubleSpinBox, others → QLineEdit.
        params_frame = QFrame()
        params_frame.setStyleSheet(f"""
            QFrame {{
                background: transparent;
                border: 1px solid {c().BORDER};
                border-radius: {sp().RADIUS_SM}px;
                padding: 2px;
            }}
        """)
        params_frame_lay = QVBoxLayout(params_frame)
        params_frame_lay.setContentsMargins(4, 4, 4, 4)
        params_frame_lay.setSpacing(2)

        params_header = QLabel("⚙ Parameters")
        params_header.setStyleSheet(f"""
            color: {c().TEXT_DIM};
            font-size: {ty().SIZE_XS}pt;
            font-weight: bold;
            letter-spacing: 0.3px;
            padding: 0px;
            border: none;
        """)
        params_frame_lay.addWidget(params_header)

        # Inner container — gets cleared & rebuilt on indicator change
        params_inner = QWidget()
        params_inner.setStyleSheet("background: transparent; border: none;")
        params_inner_lay = QGridLayout(params_inner)
        params_inner_lay.setContentsMargins(0, 0, 0, 0)
        params_inner_lay.setSpacing(3)
        params_frame_lay.addWidget(params_inner)

        ind_lay.addWidget(params_frame)

        # Dict that maps param_name → input widget (populated by _rebuild_params)
        params_widgets: Dict[str, QWidget] = {}
        setattr(self, f"{side}_params_widgets", params_widgets)
        setattr(self, f"{side}_params_inner", params_inner)
        setattr(self, f"{side}_params_frame", params_frame)

        def _rebuild_params(indicator_text: str, _inner=params_inner,
                            _lay=params_inner_lay, _widgets=params_widgets,
                            _frame=params_frame):
            """Clear and rebuild the params grid for the selected indicator."""
            # Clear old widgets
            _widgets.clear()
            while _lay.count():
                item = _lay.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            ind_key = indicator_text.strip().lower()
            defaults = get_indicator_params(ind_key)

            # Filter out params that are None or have None defaults (optional/advanced)
            # Also skip 'drift' and 'offset' as they're rarely changed
            SKIP_PARAMS = {"drift", "offset", "ddof", "scalar", "sort", "width", "weight"}
            visible = {k: v for k, v in defaults.items()
                       if v is not None and k not in SKIP_PARAMS}

            if not visible:
                _frame.hide()
                return

            _frame.show()
            _inner.show()

            row = 0
            col_pairs = list(visible.items())
            # Layout: 2 params per row (label + input | label + input)
            for i in range(0, len(col_pairs), 2):
                for j, (param, default) in enumerate(col_pairs[i:i+2]):
                    ptype = get_param_type(param)
                    desc = get_param_description(param)

                    lbl = QLabel(f"{param}:")
                    lbl.setToolTip(desc)
                    lbl.setStyleSheet(f"""
                        color: {c().TEXT_DIM};
                        font-size: {ty().SIZE_XS}pt;
                        border: none;
                        padding: 0px;
                        min-width: 52px;
                    """)

                    if ptype == "int":
                        w = QSpinBox()
                        w.setRange(1, 1000)
                        try:
                            w.setValue(int(default))
                        except (TypeError, ValueError):
                            w.setValue(14)
                        w.setFixedWidth(58)
                        w.setStyleSheet(f"""
                            QSpinBox {{
                                background: {c().BG_MAIN};
                                color: {c().TEXT_MAIN};
                                border: 1px solid {c().BORDER};
                                border-radius: {sp().RADIUS_SM}px;
                                padding: 1px 2px;
                                font-size: {ty().SIZE_XS}pt;
                            }}
                            QSpinBox:focus {{ border-color: {c().BORDER_FOCUS}; }}
                        """)
                        w.valueChanged.connect(lambda _: self.rule_changed.emit())
                    elif ptype == "float":
                        w = QDoubleSpinBox()
                        w.setRange(0.01, 100.0)
                        w.setDecimals(2)
                        w.setSingleStep(0.1)
                        try:
                            w.setValue(float(default))
                        except (TypeError, ValueError):
                            w.setValue(2.0)
                        w.setFixedWidth(68)
                        w.setStyleSheet(f"""
                            QDoubleSpinBox {{
                                background: {c().BG_MAIN};
                                color: {c().TEXT_MAIN};
                                border: 1px solid {c().BORDER};
                                border-radius: {sp().RADIUS_SM}px;
                                padding: 1px 2px;
                                font-size: {ty().SIZE_XS}pt;
                            }}
                            QDoubleSpinBox:focus {{ border-color: {c().BORDER_FOCUS}; }}
                        """)
                        w.valueChanged.connect(lambda _: self.rule_changed.emit())
                    else:
                        w = QLineEdit()
                        w.setText(str(default) if default is not None else "")
                        w.setFixedWidth(68)
                        w.setStyleSheet(f"""
                            QLineEdit {{
                                background: {c().BG_MAIN};
                                color: {c().TEXT_MAIN};
                                border: 1px solid {c().BORDER};
                                border-radius: {sp().RADIUS_SM}px;
                                padding: 1px 4px;
                                font-size: {ty().SIZE_XS}pt;
                            }}
                            QLineEdit:focus {{ border-color: {c().BORDER_FOCUS}; }}
                        """)
                        w.textChanged.connect(lambda _: self.rule_changed.emit())

                    w.setToolTip(f"{param}: {desc}")
                    _widgets[param] = w
                    col_base = j * 2
                    _lay.addWidget(lbl, row, col_base, Qt.AlignVCenter)
                    _lay.addWidget(w, row, col_base + 1, Qt.AlignVCenter)
                row += 1

        setattr(self, f"{side}_rebuild_params", _rebuild_params)

        # Initial build
        _rebuild_params(ind_cb.currentText())

        ind_cb.currentTextChanged.connect(
            lambda txt, cb=sub_col_cb: self._update_sub_cols(txt.lower(), cb)
        )
        ind_cb.currentTextChanged.connect(
            lambda txt, fn=_rebuild_params: fn(txt)
        )
        stack.addWidget(ind_page)
        scalar_page = QWidget()
        scalar_lay = QVBoxLayout(scalar_page)
        scalar_lay.setContentsMargins(0, 0, 0, 0)
        scalar_edit = styled_input("numeric value")
        scalar_edit.setValidator(QDoubleValidator())
        scalar_lay.addWidget(scalar_edit)
        stack.addWidget(scalar_page)

        # Page 2: Column
        col_page = QWidget()
        col_lay = QVBoxLayout(col_page)
        col_lay.setContentsMargins(0, 0, 0, 0)
        col_cb = QComboBox()
        col_cb.addItems(COLUMNS)
        col_cb.setStyleSheet(f"""
                    QComboBox {{
                        background: {c().BG_INPUT};
                        color: {c().CYAN if hasattr(c(), 'CYAN') else c().BLUE};
                        border: 1px solid {c().BORDER};
                        border-radius: {sp().RADIUS_SM}px;
                        padding: {sp().PAD_XS}px 28px {sp().PAD_XS}px {sp().PAD_SM}px;
                        font-size: {ty().SIZE_BODY}pt;
                        font-weight: bold;
                        min-height: 28px;
                    }}
                    QComboBox:hover {{
                        border-color: {c().CYAN if hasattr(c(), 'CYAN') else c().BLUE};
                        background: {c().BG_HOVER};
                    }}
                    QComboBox::drop-down {{
                        subcontrol-origin: padding;
                        subcontrol-position: top right;
                        width: 26px;
                        border-left: 1px solid {c().BORDER};
                        border-top-right-radius: {sp().RADIUS_SM}px;
                        border-bottom-right-radius: {sp().RADIUS_SM}px;
                        background: {(c().CYAN if hasattr(c(), 'CYAN') else c().BLUE)}22;
                    }}
                    QComboBox::drop-down:hover {{
                        background: {(c().CYAN if hasattr(c(), 'CYAN') else c().BLUE)}44;
                    }}
                    QComboBox::down-arrow {{
                        width: 0; height: 0;
                        border-left: 4px solid transparent;
                        border-right: 4px solid transparent;
                        border-top: 6px solid {c().CYAN if hasattr(c(), 'CYAN') else c().BLUE};
                    }}
                    QComboBox QAbstractItemView {{
                        background: {c().BG_PANEL};
                        color: {c().TEXT_MAIN};
                        border: 1px solid {c().BORDER};
                        selection-background-color: {c().BG_SELECTED};
                    }}
                """)
        col_lay.addWidget(col_cb)
        stack.addWidget(col_page)
        lay.addWidget(stack)

        # Wire type → stack
        def on_type(text, st=stack):
            idx = SIDE_TYPES.index(text) if text in SIDE_TYPES else 0
            st.setCurrentIndex(idx)
            shift_sb.setVisible(text != "scalar")
            self._update_description()

        type_cb.currentTextChanged.connect(on_type)
        type_cb.currentTextChanged.connect(lambda _: self.rule_changed.emit())

        # Store references
        setattr(self, f"{side}_type_cb", type_cb)
        setattr(self, f"{side}_shift_sb", shift_sb)
        setattr(self, f"{side}_stack", stack)
        setattr(self, f"{side}_ind_cb", ind_cb)
        setattr(self, f"{side}_sub_col_cb", sub_col_cb)
        setattr(self, f"{side}_col_cb", col_cb)
        setattr(self, f"{side}_scalar_edit", scalar_edit)

        return frame

    def _update_sub_cols(self, indicator: str, sub_cb: QComboBox):
        sub_cb.blockSignals(True)
        sub_cb.clear()
        subs = get_indicator_sub_columns(indicator)
        if subs:
            for key, label, _ in subs:
                sub_cb.addItem(f"↳ {label}")
                sub_cb.setItemData(sub_cb.count() - 1, key, Qt.UserRole)
            sub_cb.show()
        else:
            sub_cb.hide()
        sub_cb.blockSignals(False)

    def _make_op_card(self) -> QFrame:
        frame = QFrame()
        frame.setFixedWidth(110)
        frame.setStyleSheet(f"""
            QFrame {{
                background: {c().BG_INPUT};
                border: 1px solid {c().BORDER};
                border-top: 2px solid {c().YELLOW};
                border-radius: {sp().RADIUS_MD}px;
            }}
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(sp().PAD_SM, sp().PAD_SM, sp().PAD_SM, sp().PAD_SM)
        lay.setAlignment(Qt.AlignTop)

        hdr = QLabel("OPERATOR")
        hdr.setAlignment(Qt.AlignCenter)
        hdr.setStyleSheet(f"""
            color: {c().YELLOW};
            font-size: {ty().SIZE_XS}pt;
            font-weight: bold;
            letter-spacing: 0.5px;
        """)
        lay.addWidget(hdr)

        self.op_cb = styled_combo(OPERATORS)
        self.op_cb.setFixedWidth(90)
        self.op_cb.currentTextChanged.connect(lambda _: self._update_description())
        lay.addWidget(self.op_cb)
        lay.addStretch()
        return frame

    def _make_weight_card(self) -> QFrame:
        frame = QFrame()
        frame.setFixedWidth(100)
        frame.setStyleSheet(f"""
            QFrame {{
                background: {c().BG_INPUT};
                border: 1px solid {c().BORDER};
                border-top: 2px solid {c().PURPLE};
                border-radius: {sp().RADIUS_MD}px;
            }}
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(sp().PAD_SM, sp().PAD_SM, sp().PAD_SM, sp().PAD_SM)
        lay.setAlignment(Qt.AlignTop)

        hdr = QLabel("WEIGHT")
        hdr.setAlignment(Qt.AlignCenter)
        hdr.setStyleSheet(f"""
            color: {c().PURPLE};
            font-size: {ty().SIZE_XS}pt;
            font-weight: bold;
            letter-spacing: 0.5px;
        """)
        lay.addWidget(hdr)

        wr = get_rule_weight_range()
        self.weight_spin = styled_spinbox(wr["min"], wr["max"], wr["step"], 1, wr["default"])
        self.weight_spin.setFixedWidth(80)
        self.weight_spin.valueChanged.connect(lambda _: self._update_description())

        # Override color for weight
        self.weight_spin.setStyleSheet(f"""
            QDoubleSpinBox {{
                background: {c().BG_INPUT};
                color: {c().PURPLE};
                border: 1px solid {c().BORDER};
                border-radius: {sp().RADIUS_SM}px;
                padding: {sp().PAD_XS}px;
                font-size: {ty().SIZE_BODY}pt;
                font-weight: bold;
                text-align: center;
                min-height: 28px;
            }}
            QDoubleSpinBox:focus {{ border-color: {c().PURPLE}; }}
        """)
        lay.addWidget(self.weight_spin)

        self.suggest_lbl = QLabel("")
        self.suggest_lbl.setAlignment(Qt.AlignCenter)
        self.suggest_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_XS}pt;")
        lay.addWidget(self.suggest_lbl)
        lay.addStretch()
        return frame

    def _load(self, rule: Dict):
        """Populate widgets from rule dict."""
        if not rule:
            return
        try:
            for side in ("lhs", "rhs"):
                data = rule.get(side, {})
                t_cb = getattr(self, f"{side}_type_cb")
                sh_sb = getattr(self, f"{side}_shift_sb")
                ind_cb = getattr(self, f"{side}_ind_cb")
                col_cb = getattr(self, f"{side}_col_cb")
                sc_ed = getattr(self, f"{side}_scalar_edit")
                sub_cb = getattr(self, f"{side}_sub_col_cb")

                dtype = data.get("type", "indicator")
                t_cb.setCurrentText(dtype)

                sh_sb.setValue(int(data.get("shift", 0)))

                if dtype == "indicator":
                    ind = data.get("indicator", "rsi").upper()
                    idx = ind_cb.findText(ind, Qt.MatchFixedString | Qt.MatchCaseSensitive)
                    if idx < 0:
                        ind_cb.setEditText(ind)
                    else:
                        ind_cb.setCurrentIndex(idx)
                    self._update_sub_cols(ind.lower(), sub_cb)
                    saved_sub = data.get("sub_col", "")
                    if saved_sub:
                        for i in range(sub_cb.count()):
                            if sub_cb.itemData(i, Qt.UserRole) == saved_sub.upper():
                                sub_cb.setCurrentIndex(i)
                                break
                    # Restore saved parameter values into the dynamic params panel
                    saved_params = data.get("params", {})
                    if saved_params:
                        pw = getattr(self, f"{side}_params_widgets", {})
                        for pname, pval in saved_params.items():
                            w = pw.get(pname)
                            if w is None:
                                continue
                            try:
                                if isinstance(w, QSpinBox):
                                    w.setValue(int(pval))
                                elif isinstance(w, QDoubleSpinBox):
                                    w.setValue(float(pval))
                                elif isinstance(w, QLineEdit):
                                    w.setText(str(pval))
                            except Exception:
                                pass
                elif dtype == "column":
                    col = data.get("column", "close")
                    idx = col_cb.findText(col, Qt.MatchFixedString | Qt.MatchCaseSensitive)
                    if idx >= 0:
                        col_cb.setCurrentIndex(idx)
                else:
                    sc_ed.setText(str(data.get("value", "")))

            # operator
            op = rule.get("op", ">")
            idx = self.op_cb.findText(op)
            if idx >= 0:
                self.op_cb.setCurrentIndex(idx)

            # weight
            self.weight_spin.setValue(float(rule.get("weight", 1.0)))

        except Exception as e:
            logger.error(f"[RuleRowWidget._load] {e}", exc_info=True)

    def collect(self) -> Dict:
        """Read current widget state into a rule dict."""
        result = {}
        try:
            for side in ("lhs", "rhs"):
                dtype = getattr(self, f"{side}_type_cb").currentText()
                shift = getattr(self, f"{side}_shift_sb").value()
                ind_cb = getattr(self, f"{side}_ind_cb")
                col_cb = getattr(self, f"{side}_col_cb")
                sc_ed = getattr(self, f"{side}_scalar_edit")
                sub_cb = getattr(self, f"{side}_sub_col_cb")

                if dtype == "indicator":
                    ind = ind_cb.currentText().lower()
                    side_data = {"type": "indicator", "indicator": ind}
                    if shift:
                        side_data["shift"] = shift
                    # FIX: save sub_col whenever the combo has items (i.e. it is a
                    # multi-output indicator) regardless of its current visibility.
                    # The combo is temporarily hidden during _load() while items are
                    # being populated, so gating on isVisible() caused sub_col to be
                    # silently dropped on every save triggered during load.
                    sub_has_items = sub_cb.count() > 0
                    sub_data = sub_cb.currentData(Qt.UserRole) if sub_has_items else None
                    if sub_data:
                        side_data["sub_col"] = sub_data
                    # Collect indicator parameter values from the dynamic params panel
                    pw = getattr(self, f"{side}_params_widgets", {})
                    if pw:
                        collected_params = {}
                        for pname, widget in pw.items():
                            try:
                                if isinstance(widget, QSpinBox):
                                    collected_params[pname] = widget.value()
                                elif isinstance(widget, QDoubleSpinBox):
                                    collected_params[pname] = widget.value()
                                elif isinstance(widget, QLineEdit):
                                    collected_params[pname] = widget.text()
                            except Exception:
                                pass
                        if collected_params:
                            side_data["params"] = collected_params
                elif dtype == "column":
                    col = col_cb.currentText()
                    side_data = {"type": "column", "column": col}
                    if shift:
                        side_data["shift"] = shift
                else:
                    try:
                        val = float(sc_ed.text() or "0")
                    except ValueError:
                        val = 0.0
                    side_data = {"type": "scalar", "value": val}

                result[side] = side_data

            result["op"] = self.op_cb.currentText()
            result["weight"] = self.weight_spin.value()

        except Exception as e:
            logger.error(f"[RuleRowWidget.collect] {e}", exc_info=True)
            result = {"lhs": {"type": "scalar", "value": 0},
                      "op": ">",
                      "rhs": {"type": "scalar", "value": 0},
                      "weight": 1.0}
        return result

    def _update_description(self):
        try:
            lhs_type = self.lhs_type_cb.currentText()
            rhs_type = self.rhs_type_cb.currentText()
            op = self.op_cb.currentText()
            weight = self.weight_spin.value()
            lhs_shift = self.lhs_shift_sb.value()
            rhs_shift = self.rhs_shift_sb.value()

            lhs_val = (self.lhs_ind_cb.currentText() if lhs_type == "indicator"
                       else self.lhs_col_cb.currentText() if lhs_type == "column"
            else self.lhs_scalar_edit.text() or "?")
            rhs_val = (self.rhs_ind_cb.currentText() if rhs_type == "indicator"
                       else self.rhs_col_cb.currentText() if rhs_type == "column"
            else self.rhs_scalar_edit.text() or "?")

            lhs_shift_txt = f"[−{lhs_shift}]" if lhs_shift else ""
            rhs_shift_txt = f"[−{rhs_shift}]" if rhs_shift else ""

            self.desc_lbl.setText(
                f"ⓘ  {lhs_val}{lhs_shift_txt}  {op}  {rhs_val}{rhs_shift_txt}   │   weight: {weight:.1f}×"
            )
        except Exception:
            pass

    def set_index(self, i: int):
        self._index = i
        self.idx_lbl.setText(f"{i + 1:02d}")


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL GROUP PANEL
# ─────────────────────────────────────────────────────────────────────────────

class SignalGroupPanel(QWidget):
    """Scrollable panel of rules for one signal type."""

    rules_changed = pyqtSignal()

    def __init__(self, signal_key: str, signal_color: str, parent=None):
        super().__init__(parent)
        self._signal_key = signal_key
        self._signal_color = signal_color
        self._rule_rows: List[RuleRowWidget] = []
        self._build_ui()
        try:
            theme_manager.theme_changed.connect(self._apply_theme)
            theme_manager.density_changed.connect(self._apply_theme)
        except Exception:
            pass

    def _apply_theme(self, _=None):
        self._restyle_scroll()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Group header bar ──────────────────────────────────────────────────
        header_bar = QWidget()
        header_bar.setFixedHeight(52)
        header_bar.setStyleSheet(f"""
            background: {c().BG_PANEL};
            border-bottom: 1px solid {c().BORDER};
        """)
        hdr_lay = QHBoxLayout(header_bar)
        hdr_lay.setContentsMargins(sp().PAD_XL, 0, sp().PAD_XL, 0)
        hdr_lay.setSpacing(sp().GAP_LG)

        # Logic
        logic_lbl = QLabel("🔀 Logic:")
        logic_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_SM}pt; font-weight: bold;")
        hdr_lay.addWidget(logic_lbl)

        self.logic_cb = styled_combo(["AND", "OR"])
        self.logic_cb.setFixedWidth(80)
        hdr_lay.addWidget(self.logic_cb)

        # Enabled
        self.enabled_chk = QCheckBox("✓ Enabled")
        self.enabled_chk.setChecked(True)
        self.enabled_chk.setStyleSheet(f"""
            QCheckBox {{
                color: {c().TEXT_MAIN};
                font-size: {ty().SIZE_SM}pt;
                font-weight: bold;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 3px;
            }}
            QCheckBox::indicator:unchecked {{
                background: {c().BG_INPUT};
                border: 2px solid {c().BORDER};
            }}
            QCheckBox::indicator:checked {{
                background: {self._signal_color};
                border: 2px solid {self._signal_color};
            }}
        """)
        hdr_lay.addWidget(self.enabled_chk)

        hdr_lay.addStretch()

        self.rule_count_badge = QLabel("0 rules")
        self.rule_count_badge.setStyleSheet(f"""
            color: {self._signal_color};
            background: {self._signal_color}22;
            border: 1px solid {self._signal_color}55;
            border-radius: 999px;
            padding: 1px 10px;
            font-size: {ty().SIZE_XS}pt;
            font-weight: bold;
        """)
        hdr_lay.addWidget(self.rule_count_badge)

        root.addWidget(header_bar)

        # ── Scrollable rules area ─────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._restyle_scroll()

        self._rules_container = QWidget()
        self._rules_container.setStyleSheet("background: transparent;")
        self._rules_layout = QVBoxLayout(self._rules_container)
        self._rules_layout.setContentsMargins(sp().PAD_LG, sp().PAD_LG, sp().PAD_LG, sp().PAD_LG)
        self._rules_layout.setSpacing(sp().GAP_MD)
        self._rules_layout.setAlignment(Qt.AlignTop)

        self._empty_lbl = QLabel("✨  No rules yet — click  + Add Rule  to begin")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet(f"""
            color: {c().TEXT_DIM};
            font-size: {ty().SIZE_BODY}pt;
            padding: 40px;
            border: 2px dashed {c().BORDER};
            border-radius: {sp().RADIUS_LG}px;
            margin: 20px;
        """)
        self._rules_layout.addWidget(self._empty_lbl)
        self._rules_layout.addStretch()

        self._scroll.setWidget(self._rules_container)
        root.addWidget(self._scroll, 1)

        # ── Actions bar ───────────────────────────────────────────────────────
        actions_bar = QWidget()
        actions_bar.setFixedHeight(52)
        actions_bar.setStyleSheet(f"background: {c().BG_PANEL}; border-top: 1px solid {c().BORDER};")
        actions_lay = QHBoxLayout(actions_bar)
        actions_lay.setContentsMargins(sp().PAD_XL, 0, sp().PAD_XL, 0)
        actions_lay.setSpacing(sp().GAP_MD)

        add_btn = styled_button("＋  Add Rule", c().GREEN, c().GREEN_BRIGHT, min_w=120)
        add_btn.clicked.connect(lambda: self.add_rule())
        actions_lay.addWidget(add_btn)

        # Preset loader — populated from strategy_presets.PRESETS[signal_key]
        # BUG FIX: was hardcoded with 3 stub names and never connected to a
        # handler, so clicking did nothing and real preset names never showed.
        _preset_names = get_preset_names(self._signal_key)
        self.preset_cb = styled_combo(["📋 Load Preset…"] + _preset_names)
        self.preset_cb.setFixedWidth(220)
        self.preset_cb.setToolTip("Select a preset to append its rules")
        self.preset_cb.currentIndexChanged.connect(self._on_preset_selected)
        actions_lay.addWidget(self.preset_cb)

        actions_lay.addStretch()

        clear_btn = ghost_button("🗑  Clear All", c().RED, min_w=100)
        clear_btn.clicked.connect(self._clear_all)
        actions_lay.addWidget(clear_btn)

        root.addWidget(actions_bar)

    def _restyle_scroll(self):
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {c().BG_PANEL if hasattr(c(), 'BG_MAIN') else c().BG_PANEL};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {c().BG_PANEL};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {c().BORDER_STRONG};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{ height: 0; }}
        """)

    def _on_preset_selected(self, index: int):
        """
        BUG FIX: Previously missing — preset combobox had no connected handler.
        Appends all rules from the selected preset into this signal group.
        """
        if index <= 0:  # index 0 is the placeholder '📋 Load Preset…'
            return
        try:
            preset_name = self.preset_cb.currentText()
            rules = get_preset_rules(self._signal_key, preset_name)
            if not rules:
                logger.warning(
                    f"[SignalGroupPanel] Preset '{preset_name}' for "
                    f"'{self._signal_key}' returned no rules"
                )
                return
            for rule in rules:
                self.add_rule(rule)
            logger.info(
                f"[SignalGroupPanel] Preset '{preset_name}' inserted "
                f"{len(rules)} rule(s) into {self._signal_key}"
            )
        except Exception as e:
            logger.error(f"[SignalGroupPanel._on_preset_selected] {e}", exc_info=True)
        finally:
            # Reset dropdown back to placeholder so the same preset can be
            # selected again without needing to pick another item first.
            self.preset_cb.blockSignals(True)
            self.preset_cb.setCurrentIndex(0)
            self.preset_cb.blockSignals(False)

    def add_rule(self, rule: Dict = None):
        """Append a new rule row."""
        try:
            row = RuleRowWidget(rule, index=len(self._rule_rows), parent=self._rules_container)
            row.deleted.connect(self._remove_rule)
            row.rule_changed.connect(self.rules_changed)

            # Insert before stretch
            pos = max(0, self._rules_layout.count() - 1)
            self._rules_layout.insertWidget(pos, row)
            self._rule_rows.append(row)
            self._update_count()

            QTimer.singleShot(80, lambda: self._scroll.ensureWidgetVisible(row))
        except Exception as e:
            logger.error(f"[SignalGroupPanel.add_rule] {e}", exc_info=True)

    def _remove_rule(self, row: RuleRowWidget):
        try:
            if row in self._rule_rows:
                self._rule_rows.remove(row)
                self._rules_layout.removeWidget(row)
                row.deleteLater()
                for i, r in enumerate(self._rule_rows):
                    r.set_index(i)
                self._update_count()
        except Exception as e:
            logger.error(f"[SignalGroupPanel._remove_rule] {e}", exc_info=True)

    def _clear_all(self):
        for row in list(self._rule_rows):
            self._remove_rule(row)

    def _update_count(self):
        n = len(self._rule_rows)
        self.rule_count_badge.setText(f"{n} rule{'s' if n != 1 else ''}")
        self._empty_lbl.setVisible(n == 0)
        self.rules_changed.emit()

    def load(self, group_data: Dict):
        """Load from engine data."""
        self._clear_all()
        if not group_data:
            return
        self.logic_cb.setCurrentText(group_data.get("logic", "AND"))
        self.enabled_chk.setChecked(bool(group_data.get("enabled", True)))
        for rule in group_data.get("rules", []):
            self.add_rule(rule)

    def collect(self) -> Dict:
        return {
            "logic": self.logic_cb.currentText(),
            "enabled": self.enabled_chk.isChecked(),
            "rules": [r.collect() for r in self._rule_rows],
        }


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL RULES TAB
# ─────────────────────────────────────────────────────────────────────────────

class SignalRulesTab(QWidget):
    """Main signal rules editor — sub-tabs per signal group."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._panels: Dict[str, SignalGroupPanel] = {}
        self._build_ui()
        try:
            theme_manager.theme_changed.connect(self._apply_theme)
            theme_manager.density_changed.connect(self._apply_theme)
        except Exception:
            pass

    def _apply_theme(self, _=None):
        self._restyle_tab_bar()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Conflict resolution bar ───────────────────────────────────────────
        cr_bar = QWidget()
        cr_bar.setFixedHeight(48)
        cr_bar.setStyleSheet(f"""
            background: {c().BG_PANEL};
            border-bottom: 1px solid {c().BORDER};
        """)
        cr_lay = QHBoxLayout(cr_bar)
        cr_lay.setContentsMargins(sp().PAD_XL, 0, sp().PAD_XL, 0)
        cr_lay.setSpacing(sp().GAP_LG)

        cr_lbl = QLabel("⚖  Conflict Resolution:")
        cr_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_SM}pt; font-weight: bold;")
        cr_lay.addWidget(cr_lbl)

        self.conflict_cb = styled_combo(["WAIT", "PRIORITY"])
        self.conflict_cb.setFixedWidth(130)
        cr_lay.addWidget(self.conflict_cb)

        hint = QLabel("  (applied when BUY_CALL & BUY_PUT both fire)")
        hint.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_XS}pt; font-style: italic;")
        cr_lay.addWidget(hint)
        cr_lay.addStretch()

        self.total_rules_lbl = QLabel("📊 Total: 0 rules")
        self.total_rules_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_SM}pt; font-weight: bold;")
        cr_lay.addWidget(self.total_rules_lbl)

        enable_all = ghost_button("✓ Enable All", c().GREEN, min_w=110)
        disable_all = ghost_button("✗ Disable All", c().RED, min_w=110)
        enable_all.clicked.connect(lambda: [p.enabled_chk.setChecked(True) for p in self._panels.values()])
        disable_all.clicked.connect(lambda: [p.enabled_chk.setChecked(False) for p in self._panels.values()])
        cr_lay.addWidget(enable_all)
        cr_lay.addWidget(disable_all)

        root.addWidget(cr_bar)

        # ── Signal sub-tabs ───────────────────────────────────────────────────
        self._tab_widget = QTabWidget()
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.tabBar().setExpanding(True)
        self._restyle_tab_bar()

        for key, label, color_token in SIGNAL_GROUPS:
            color = getattr(c(), color_token, c().BLUE)
            panel = SignalGroupPanel(key, color)
            panel.rules_changed.connect(self._update_total)
            self._panels[key] = panel
            self._tab_widget.addTab(panel, label)

        root.addWidget(self._tab_widget, 1)

    def _restyle_tab_bar(self):
        self._tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {c().BG_PANEL};
            }}
            QTabBar::tab {{
                background: {c().BG_HOVER};
                color: {c().TEXT_DIM};
                border: 1px solid {c().BORDER};
                border-bottom: none;
                border-top-left-radius: {sp().RADIUS_MD}px;
                border-top-right-radius: {sp().RADIUS_MD}px;
                padding: {sp().PAD_SM}px {sp().PAD_LG}px;
                margin-right: 2px;
                font-size: {ty().SIZE_SM}pt;
                min-width: 110px;
                min-height: {sp().TAB_H}px;
            }}
            QTabBar::tab:selected {{
                background: {c().BG_PANEL};
                color: {c().TEXT_MAIN};
                border-bottom: 2px solid {getattr(c(), "ACCENT", c().BLUE)};
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background: {c().BORDER};
                color: {c().TEXT_MAIN};
            }}
        """)

    def _update_total(self):
        total = sum(len(p._rule_rows) for p in self._panels.values())
        self.total_rules_lbl.setText(f"📊 Total: {total} rule{'s' if total != 1 else ''}")

    def load(self, strategy: Dict):
        engine = strategy.get("engine", {}) if strategy else {}
        self.conflict_cb.setCurrentText(engine.get("conflict_resolution", "WAIT"))
        for key, panel in self._panels.items():
            panel.load(engine.get(key, {"logic": "AND", "enabled": True, "rules": []}))
        self._update_total()

    def collect(self) -> Dict:
        result = {"conflict_resolution": self.conflict_cb.currentText()}
        for key, panel in self._panels.items():
            result[key] = panel.collect()
        return result


# ─────────────────────────────────────────────────────────────────────────────
# INFO TAB
# ─────────────────────────────────────────────────────────────────────────────

class InfoTab(QScrollArea):
    """Strategy name, description, and statistics."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self._build_ui()
        try:
            theme_manager.theme_changed.connect(self._apply_theme)
            theme_manager.density_changed.connect(self._apply_theme)
        except Exception:
            pass

    def _apply_theme(self, _=None):
        pass  # Handled by global stylesheet

    def _build_ui(self):
        container = QWidget()
        self.setWidget(container)
        root = QHBoxLayout(container)
        root.setContentsMargins(sp().PAD_2XL, sp().PAD_2XL, sp().PAD_2XL, sp().PAD_2XL)
        root.setSpacing(sp().GAP_XL)

        # ── Left: form ────────────────────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(sp().GAP_LG)

        details_card = self._make_card()
        details_lay = QVBoxLayout(details_card)
        details_lay.setSpacing(sp().GAP_LG)
        details_lay.addWidget(section_label("STRATEGY DETAILS"))

        details_lay.addWidget(accent_label("NAME", c().BLUE))
        self.name_edit = styled_input("e.g. EMA Crossover Strategy")
        self.name_edit.setMinimumWidth(380)
        self.name_edit.textChanged.connect(self.changed)
        details_lay.addWidget(self.name_edit)

        details_lay.addWidget(accent_label("DESCRIPTION", c().BLUE))
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("Describe when this strategy fires, market conditions, risk profile…")
        self.desc_edit.setMaximumHeight(110)
        self.desc_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {c().BG_INPUT};
                color: {c().TEXT_MAIN};
                border: 1px solid {c().BORDER};
                border-radius: {sp().RADIUS_MD}px;
                padding: {sp().PAD_SM}px;
                font-size: {ty().SIZE_BODY}pt;
            }}
            QTextEdit:focus {{ border-color: {c().BORDER_FOCUS}; }}
        """)
        self.desc_edit.textChanged.connect(self.changed)
        details_lay.addWidget(self.desc_edit)
        left.addWidget(details_card)

        # Engine settings card
        engine_card = self._make_card()
        engine_lay = QGridLayout(engine_card)
        engine_lay.setSpacing(sp().GAP_MD)
        engine_lay.addWidget(section_label("ENGINE SETTINGS"), 0, 0, 1, 4)

        engine_lay.addWidget(accent_label("Conflict Resolution"), 1, 0)
        self.conflict_cb = styled_combo(["WAIT", "PRIORITY"])
        self.conflict_cb.setFixedWidth(140)
        engine_lay.addWidget(self.conflict_cb, 1, 1)

        engine_lay.addWidget(accent_label("Min Confidence"), 1, 2)
        self.conf_spin = styled_spinbox(0.0, 1.0, 0.05, 2, 0.6)
        self.conf_spin.setFixedWidth(80)
        engine_lay.addWidget(self.conf_spin, 1, 3)
        left.addWidget(engine_card)
        left.addStretch()

        # ── Right: stats ──────────────────────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(sp().GAP_LG)

        stats_card = self._make_card()
        stats_lay = QVBoxLayout(stats_card)
        stats_lay.addWidget(section_label("STATISTICS"))
        stats_lay.addSpacing(sp().GAP_MD)

        self._stat_labels: Dict[str, QLabel] = {}
        stats = [
            ("Total Rules", "BLUE"),
            ("Unique Indicators", "PURPLE"),
            ("Enabled Groups", "GREEN"),
            ("Avg Rule Weight", "ACCENT" if hasattr(c(), "ACCENT") else "YELLOW"),
        ]
        for stat_name, color_token in stats:
            row = QHBoxLayout()
            row.setSpacing(sp().GAP_MD)
            name_lbl = QLabel(stat_name)
            name_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_SM}pt;")
            row.addWidget(name_lbl)
            row.addStretch()
            val_lbl = QLabel("—")
            col = getattr(c(), color_token, c().BLUE)
            val_lbl.setStyleSheet(f"""
                color: {col};
                font-size: {ty().SIZE_LG}pt;
                font-weight: bold;
                background: {col}11;
                border-radius: {sp().RADIUS_SM}px;
                padding: 1px 8px;
            """)
            row.addWidget(val_lbl)
            self._stat_labels[stat_name] = val_lbl
            stats_lay.addLayout(row)
            stats_lay.addWidget(make_separator())

        right.addWidget(stats_card)

        meta_card = self._make_card()
        meta_lay = QVBoxLayout(meta_card)
        meta_lay.addWidget(section_label("METADATA"))
        meta_lay.addSpacing(sp().GAP_SM)

        self.created_lbl = self._meta_row(meta_lay, "Created")
        self.updated_lbl = self._meta_row(meta_lay, "Last Saved")
        self.slug_lbl = self._meta_row(meta_lay, "Slug / ID")
        right.addWidget(meta_card)
        right.addStretch()

        root.addLayout(left, 3)
        root.addLayout(right, 2)

    def _make_card(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"""
            QFrame {{
                background: {c().BG_PANEL if hasattr(c(), 'BG_CARD') else c().BG_HOVER};
                border: 1px solid {c().BORDER};
                border-radius: {sp().RADIUS_LG}px;
                padding: {sp().PAD_LG}px;
            }}
        """)
        return f

    def _meta_row(self, layout: QVBoxLayout, label: str) -> QLabel:
        row = QHBoxLayout()
        lbl = QLabel(label + ":")
        lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_XS}pt;")
        val = QLabel("—")
        val.setStyleSheet(f"color: {c().TEXT_MAIN}; font-size: {ty().SIZE_XS}pt; font-family: monospace;")
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(val)
        layout.addLayout(row)
        return val

    def load(self, strategy: Dict):
        if not strategy:
            return
        self.name_edit.setText(strategy.get("name", ""))
        self.desc_edit.setPlainText(strategy.get("description", ""))
        engine = strategy.get("engine", {})
        self.conflict_cb.setCurrentText(engine.get("conflict_resolution", "WAIT"))
        self.conf_spin.setValue(float(engine.get("min_confidence", 0.6)))
        self.created_lbl.setText(str(strategy.get("created_at", "—")))
        self.updated_lbl.setText(str(strategy.get("updated_at", "—")))
        self.slug_lbl.setText(str(strategy.get("slug", "—")))
        self._recalculate_stats(strategy)

    def _recalculate_stats(self, strategy: Dict):
        try:
            engine = strategy.get("engine", {})
            total_rules = 0
            indicators = set()
            enabled_count = 0
            weights = []

            for sig_key, _, _ in SIGNAL_GROUPS:
                group = engine.get(sig_key, {})
                rules = group.get("rules", [])
                total_rules += len(rules)
                if group.get("enabled", True):
                    enabled_count += 1
                for rule in rules:
                    weights.append(float(rule.get("weight", 1.0)))
                    for side in ("lhs", "rhs"):
                        sd = rule.get(side, {})
                        if sd.get("type") == "indicator":
                            indicators.add(sd.get("indicator", "").lower())

            avg_w = sum(weights) / len(weights) if weights else 0.0
            self._stat_labels["Total Rules"].setText(str(total_rules))
            self._stat_labels["Unique Indicators"].setText(str(len(indicators)))
            self._stat_labels["Enabled Groups"].setText(f"{enabled_count} / 5")
            self._stat_labels["Avg Rule Weight"].setText(f"{avg_w:.1f}")
        except Exception as e:
            logger.error(f"[InfoTab._recalculate_stats] {e}", exc_info=True)

    def collect(self) -> Dict:
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip(),
            "conflict_resolution": self.conflict_cb.currentText(),
            "min_confidence": self.conf_spin.value(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# INDICATORS TAB
# ─────────────────────────────────────────────────────────────────────────────

class IndicatorsTab(QScrollArea):
    """Visual catalogue of all available indicators."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self._build_ui()

    def _build_ui(self):
        container = QWidget()
        self.setWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(sp().PAD_XL, sp().PAD_XL, sp().PAD_XL, sp().PAD_XL)
        root.setSpacing(sp().GAP_LG)

        # Filter bar
        filter_bar = QHBoxLayout()
        filter_lbl = QLabel("⌕ Filter:")
        filter_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_BODY}pt;")
        filter_bar.addWidget(filter_lbl)

        self.filter_edit = styled_input("Type to filter indicators…")
        self.filter_edit.setMaximumWidth(400)
        self.filter_edit.textChanged.connect(self._filter)
        filter_bar.addWidget(self.filter_edit)
        filter_bar.addStretch()
        root.addLayout(filter_bar)

        # Category sections
        self._cards: List[QFrame] = []
        self._cat_sections: List[QWidget] = []

        for category, indicators in get_indicators_by_category().items():
            if not indicators:
                continue

            cat_header = QLabel(f"📁  {category.upper()}")
            cat_header.setStyleSheet(f"""
                color: {c().BLUE};
                font-size: {ty().SIZE_BODY}pt;
                font-weight: bold;
                letter-spacing: 0.8px;
                padding: {sp().PAD_SM}px 0;
                border-bottom: 1px solid {c().BORDER};
            """)
            root.addWidget(cat_header)

            grid_widget = QWidget()
            grid = QGridLayout(grid_widget)
            grid.setSpacing(sp().GAP_MD)

            row_idx, col_idx = 0, 0
            for indicator in sorted(indicators):
                card = self._make_indicator_card(indicator)
                grid.addWidget(card, row_idx, col_idx)
                self._cards.append((card, indicator))
                col_idx += 1
                if col_idx >= 4:
                    col_idx = 0
                    row_idx += 1

            section = QWidget()
            sec_lay = QVBoxLayout(section)
            sec_lay.setContentsMargins(0, 0, 0, 0)
            sec_lay.addWidget(cat_header)
            sec_lay.addWidget(grid_widget)
            self._cat_sections.append((section, category))
            root.addWidget(section)

        root.addStretch()

    def _make_indicator_card(self, name: str) -> QFrame:
        card = QFrame()
        card.setFixedSize(220, 190)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(f"""
            QFrame {{
                background: {c().BG_PANEL};
                border: 1px solid {c().BORDER};
                border-top: 2px solid {c().GREEN}44;
                border-radius: {sp().RADIUS_MD}px;
            }}
            QFrame:hover {{
                border-top: 2px solid {c().GREEN};
                background: {c().BG_HOVER};
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(sp().PAD_MD, sp().PAD_MD, sp().PAD_MD, sp().PAD_MD)
        lay.setSpacing(sp().GAP_SM)

        name_lbl = QLabel(name.upper())
        name_lbl.setStyleSheet(f"color: {c().GREEN}; font-weight: bold; font-size: {ty().SIZE_BODY}pt;")
        lay.addWidget(name_lbl)

        # Category
        cat = get_indicator_category(name)
        cat_lbl = QLabel(f"📌 {cat}")
        cat_lbl.setStyleSheet(f"""
            color: {c().BLUE}CC;
            font-size: {ty().SIZE_XS}pt;
            background: {c().BLUE}11;
            border-radius: {sp().RADIUS_SM}px;
            padding: 1px 5px;
        """)
        lay.addWidget(cat_lbl)

        # Params
        params = get_indicator_params(name)
        if params:
            param_text = "\n".join(f"• {k}: {v}" for k, v in list(params.items())[:4])
            if len(params) > 4:
                param_text += f"\n• … (+{len(params) - 4} more)"
        else:
            param_text = "• No parameters"
        param_lbl = QLabel(param_text)
        param_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_XS}pt;")
        param_lbl.setWordWrap(True)
        lay.addWidget(param_lbl)

        # Sub-columns
        subs = get_indicator_sub_columns(name)
        if subs:
            sub_text = "  ".join(f"[{k}]" for k, _, _ in subs)
            sub_lbl = QLabel(f"↳ {sub_text}")
            sub_lbl.setStyleSheet(f"color: {c().PURPLE}; font-size: {ty().SIZE_XS}pt;")
            lay.addWidget(sub_lbl)

        # Weight
        w = get_suggested_weight(name)
        w_lbl = QLabel(f"⚖ suggested weight: {w:.1f}")
        w_lbl.setStyleSheet(f"color: {c().PURPLE}; font-size: {ty().SIZE_XS}pt; font-weight: bold;")
        lay.addWidget(w_lbl)

        lay.addStretch()
        return card

    def _filter(self, text: str):
        text = text.lower()
        for card, name in self._cards:
            card.setVisible(not text or text in name.lower())

    def load(self, strategy: Dict):
        pass

    def collect(self) -> Dict:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# HELP TAB
# ─────────────────────────────────────────────────────────────────────────────

class HelpTab(QScrollArea):
    """Reference documentation panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self._build_ui()

    def _build_ui(self):
        container = QWidget()
        self.setWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(sp().PAD_2XL, sp().PAD_2XL, sp().PAD_2XL, sp().PAD_2XL)
        root.setSpacing(sp().GAP_LG)

        sections = [
            ("📘 How Rules Work",
             "Each rule compares a LEFT SIDE value against a RIGHT SIDE value using a comparison OPERATOR.\n\n"
             "Rules within a group are combined using the group's logic (AND requires ALL rules to pass; "
             "OR requires at least ONE to pass). If the group's combined condition evaluates true, the signal fires."),
            ("⚖  Rule Weights & Confidence",
             "Every rule carries a weight (0.1 – 5.0) that scales its contribution to the group's confidence score.\n\n"
             "Confidence = Σ(matching rule weights) / Σ(all rule weights)\n\n"
             "A signal only fires when confidence ≥ the configured Min Confidence threshold."),
            ("⏱  Bar Shifts",
             "Shift = 0 reads the current bar.\n"
             "Shift = 1 reads the previous bar.\n"
             "Shift = N reads N bars back.\n\n"
             "Use shifts to compare current vs. historical values:\n"
             "  RSI[0] > RSI[1]  →  RSI is rising right now"),
            ("⚡  Conflict Resolution",
             "WAIT   — if both BUY_CALL and BUY_PUT fire simultaneously, take no action until one clears.\n"
             "PRIORITY — if both fire simultaneously, always prefer BUY_CALL."),
            ("📋  Multi-Output Indicators",
             "Some indicators (MACD, Bollinger Bands, Stochastic) produce multiple output columns.\n"
             "Use the ↳ Output Column selector that appears after choosing such an indicator to specify "
             "which column to compare:\n\n"
             "  MACD → [MACD Line | Signal Line | Histogram]\n"
             "  BB   → [Lower Band | Middle Band | Upper Band]\n"
             "  STOCH → [%K | %D]"),
        ]

        for title, body in sections:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {c().BG_PANEL};
                    border: 1px solid {c().BORDER};
                    border-left: 3px solid {getattr(c(), "ACCENT", c().BLUE)};
                    border-radius: {sp().RADIUS_MD}px;
                    padding: {sp().PAD_LG}px;
                }}
            """)
            lay = QVBoxLayout(card)
            lay.setSpacing(sp().GAP_MD)

            title_lbl = QLabel(title)
            title_lbl.setStyleSheet(f"""
                color: {c().TEXT_MAIN};
                font-size: {ty().SIZE_LG}pt;
                font-weight: bold;
            """)
            lay.addWidget(title_lbl)

            body_lbl = QLabel(body)
            body_lbl.setWordWrap(True)
            body_lbl.setStyleSheet(f"""
                color: {c().TEXT_DIM};
                font-size: {ty().SIZE_BODY}pt;
                line-height: 1.6;
            """)
            lay.addWidget(body_lbl)
            root.addWidget(card)

        # Code example
        example_card = QFrame()
        example_card.setStyleSheet(f"""
            QFrame {{
                background: {c().BG_PANEL};
                border: 1px solid {c().BORDER};
                border-top: 2px solid {c().BLUE};
                border-radius: {sp().RADIUS_MD}px;
                padding: {sp().PAD_LG}px;
            }}
        """)
        ex_lay = QVBoxLayout(example_card)
        ex_hdr = QLabel("🔗 Example Rule")
        ex_hdr.setStyleSheet(f"color: {c().BLUE}; font-size: {ty().SIZE_LG}pt; font-weight: bold;")
        ex_lay.addWidget(ex_hdr)

        code_lbl = QLabel('  RSI(length=14)[shift=0]   <   30   →   weight: 2.5')
        code_lbl.setStyleSheet(f"""
            background: {c().BG_INPUT};
            color: {c().GREEN};
            font-family: 'Consolas', monospace;
            font-size: {ty().SIZE_BODY}pt;
            border-radius: {sp().RADIUS_MD}px;
            padding: {sp().PAD_MD}px;
        """)
        ex_lay.addWidget(code_lbl)

        desc_lbl = QLabel(
            '"If RSI with period 14 on the current bar is below 30, '
            'contribute 2.5× to the BUY_CALL confidence score."'
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_SM}pt; font-style: italic;")
        ex_lay.addWidget(desc_lbl)
        root.addWidget(example_card)
        root.addStretch()

    def load(self, strategy: Dict): pass

    def collect(self) -> Dict: return {}


# ─────────────────────────────────────────────────────────────────────────────
# IMPORT / EXPORT DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class ImportExportDialog(QDialog):
    """Frameless JSON import/export dialog."""

    def __init__(self, mode: str, strategy_data: Dict = None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.strategy_data = strategy_data
        self._imported_data: Dict = {}
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(720, 540)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        card = QFrame()
        card.setObjectName("ioCard")
        card.setStyleSheet(f"""
            QFrame#ioCard {{
                background: {c().BG_PANEL};
                border: 1px solid {c().BORDER_FOCUS};
                border-top: 3px solid {c().GREEN if self.mode == "export" else c().CYAN if hasattr(c(), "CYAN") else c().BLUE};
                border-radius: {sp().RADIUS_LG}px;
            }}
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(sp().PAD_XL, 0, sp().PAD_XL, sp().PAD_XL)
        card_lay.setSpacing(sp().GAP_LG)

        # Title bar
        tbar = QHBoxLayout()
        tbar.setContentsMargins(0, sp().PAD_MD, 0, sp().PAD_MD)
        icon = "↑" if self.mode == "export" else "↓"
        label_text = f"{icon}  {'Export' if self.mode == 'export' else 'Import'} Strategy"
        title = QLabel(label_text)
        title.setStyleSheet(f"""
            color: {c().GREEN if self.mode == "export" else c().CYAN if hasattr(c(), "CYAN") else c().BLUE};
            font-size: {ty().SIZE_XL}pt;
            font-weight: bold;
        """)
        tbar.addWidget(title)
        tbar.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {c().BG_HOVER};
                color: {c().TEXT_DIM};
                border: none;
                border-radius: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {c().RED}; color: white; }}
        """)
        close_btn.clicked.connect(self.reject)
        tbar.addWidget(close_btn)
        card_lay.addLayout(tbar)
        card_lay.addWidget(make_separator())

        # JSON editor
        self.json_edit = QTextEdit()
        self.json_edit.setFont(QFont("Consolas", ty().SIZE_SM))
        self.json_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {c().BG_INPUT};
                color: {c().TEXT_MAIN};
                border: 1px solid {c().BORDER};
                border-radius: {sp().RADIUS_MD}px;
                font-family: 'Consolas', monospace;
                font-size: {ty().SIZE_SM}pt;
                padding: {sp().PAD_MD}px;
            }}
            QTextEdit:focus {{ border-color: {c().BORDER_FOCUS}; }}
        """)
        if self.mode == "export" and self.strategy_data:
            try:
                self.json_edit.setPlainText(json.dumps(self.strategy_data, indent=2, default=str))
                self.json_edit.setReadOnly(True)
            except Exception:
                self.json_edit.setPlainText("Error formatting JSON")
        else:
            self.json_edit.setPlaceholderText("Paste strategy JSON here…")
        card_lay.addWidget(self.json_edit)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(sp().GAP_MD)

        if self.mode == "export":
            copy_btn = ghost_button("📋 Copy", c().TEXT_MAIN, 120)
            copy_btn.clicked.connect(self._copy)
            btn_row.addWidget(copy_btn)

            save_btn = styled_button("💾 Save to File", c().GREEN, c().GREEN_BRIGHT, min_w=140)
            save_btn.clicked.connect(self._save_file)
            btn_row.addWidget(save_btn)
            btn_row.addStretch()

            ok_btn = styled_button("OK", c().BLUE, c().BLUE_DARK, min_w=80)
            ok_btn.clicked.connect(self.accept)
            btn_row.addWidget(ok_btn)
        else:
            load_btn = ghost_button("📂 Load from File", c().TEXT_MAIN, 140)
            load_btn.clicked.connect(self._load_file)
            btn_row.addWidget(load_btn)

            validate_btn = ghost_button("✓ Validate", c().GREEN, 100)
            validate_btn.clicked.connect(self._validate)
            btn_row.addWidget(validate_btn)
            btn_row.addStretch()

            self.import_btn = styled_button("↓ Import", c().BLUE, c().BLUE_DARK, min_w=100)
            self.import_btn.setEnabled(False)
            self.import_btn.clicked.connect(self._do_import)
            btn_row.addWidget(self.import_btn)

            cancel_btn = ghost_button("Cancel", c().TEXT_DIM, 80)
            cancel_btn.clicked.connect(self.reject)
            btn_row.addWidget(cancel_btn)

        card_lay.addLayout(btn_row)
        root.addWidget(card)

    def _copy(self):
        QApplication.clipboard().setText(self.json_edit.toPlainText())
        QMessageBox.information(self, "Copied", "JSON copied to clipboard!")

    def _save_file(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Save Strategy", "", "JSON Files (*.json)")
        if fn:
            try:
                with open(fn, "w", encoding="utf-8") as f:
                    f.write(self.json_edit.toPlainText())
                QMessageBox.information(self, "Saved", f"Strategy saved to {fn}")
            except IOError as e:
                QMessageBox.critical(self, "Error", str(e))

    def _load_file(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Load Strategy", "", "JSON Files (*.json)")
        if fn:
            try:
                with open(fn, "r", encoding="utf-8") as f:
                    self.json_edit.setPlainText(f.read())
                self._validate()
            except IOError as e:
                QMessageBox.critical(self, "Error", str(e))

    def _validate(self):
        try:
            data = json.loads(self.json_edit.toPlainText())
            if "name" in data and "engine" in data:
                self.import_btn.setEnabled(True)
                self.import_btn.setText("✓ Valid — Import")
                QMessageBox.information(self, "Valid", "JSON is valid and ready to import!")
            else:
                self.import_btn.setEnabled(False)
                QMessageBox.warning(self, "Invalid", "JSON must contain 'name' and 'engine' fields.")
        except json.JSONDecodeError as e:
            self.import_btn.setEnabled(False)
            QMessageBox.warning(self, "Invalid JSON", str(e))

    def _do_import(self):
        try:
            self._imported_data = json.loads(self.json_edit.toPlainText())
            self.accept()
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", str(e))

    def get_imported_data(self) -> Dict:
        return self._imported_data


# ─────────────────────────────────────────────────────────────────────────────
# MAIN STRATEGY EDITOR WINDOW
# ─────────────────────────────────────────────────────────────────────────────

class StrategyEditorWindow(QDialog):
    """
    Full-page Strategy Editor with Theme Manager integration.

    Signals:
        strategy_activated(str) — emitted when user activates a strategy
        strategy_saved(str)     — emitted when any strategy is saved; slug is
                                  the saved strategy's slug.  TradingGUI listens
                                  to this and calls reload_signal_engine() when
                                  the saved slug matches the active strategy so
                                  evaluation updates immediately without needing
                                  to re-activate or restart.
    """

    strategy_activated = pyqtSignal(str)
    strategy_saved     = pyqtSignal(str)   # NEW: fires on every successful save

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self._current_slug: Optional[str] = None
        self._dirty = False
        self._theme_panel: Optional[ThemeManagerPanel] = None

        # Frameless window for full custom chrome
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1560, 940)
        self.setMinimumSize(1280, 720)

        self._build_ui()
        self._apply_global_style()

        # Connect theme signals
        try:
            theme_manager.theme_changed.connect(self._on_theme)
            theme_manager.density_changed.connect(self._on_theme)
        except Exception:
            pass

        # Load active strategy
        active = strategy_manager.get_active_slug()
        if active:
            self._load_strategy(active)

    # ── Global style (applied to root) ────────────────────────────────────────

    def _apply_global_style(self):
        """Push full-window stylesheet."""
        self.setStyleSheet(f"""
            QDialog {{
                background: {c().BG_PANEL};
                color: {c().TEXT_MAIN};
                font-family: 'Segoe UI', 'Arial', sans-serif;
                font-size: {ty().SIZE_BODY}pt;
            }}
        """)

    def _on_theme(self, _=None):
        self._apply_global_style()

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)

        # Outer card (gives drop-shadow area)
        outer = QFrame()
        outer.setObjectName("outerCard")
        outer.setStyleSheet(f"""
            QFrame#outerCard {{
                background: {c().BG_PANEL};
                border: 1px solid {c().BORDER};
                border-radius: {sp().RADIUS_LG}px;
            }}
        """)
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        # ── Custom title bar ──────────────────────────────────────────────────
        outer_lay.addWidget(self._build_title_bar())
        outer_lay.addWidget(make_separator())

        # ── Body: sidebar + editor ────────────────────────────────────────────
        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        self._list_panel = StrategyListPanel()
        self._list_panel.strategy_selected.connect(self._on_strategy_selected)
        self._list_panel.strategy_activated.connect(self._on_strategy_activated)
        body_lay.addWidget(self._list_panel)

        # Right editor area
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        right_lay.addWidget(self._build_editor_header())
        right_lay.addWidget(make_separator())
        right_lay.addWidget(self._build_tabs(), 1)
        right_lay.addWidget(make_separator())
        right_lay.addWidget(self._build_footer())

        body_lay.addWidget(right, 1)
        outer_lay.addWidget(body, 1)

        root.addWidget(outer)

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"""
            background: {c().BG_PANEL};
            border-top-left-radius: {sp().RADIUS_LG}px;
            border-top-right-radius: {sp().RADIUS_LG}px;
        """)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(sp().PAD_LG, 0, sp().PAD_MD, 0)
        lay.setSpacing(sp().GAP_MD)

        # Amber logo badge
        accent = getattr(c(), "ACCENT", c().YELLOW)
        logo_badge = QLabel("S")
        logo_badge.setFixedSize(32, 32)
        logo_badge.setAlignment(Qt.AlignCenter)
        logo_badge.setStyleSheet(f"""
            color: #000;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {accent}, stop:1 {c().ORANGE});
            border-radius: 8px;
            font-size: {ty().SIZE_LG}pt;
            font-weight: 900;
        """)
        lay.addWidget(logo_badge)

        title_lbl = QLabel("STRATEGY EDITOR")
        title_lbl.setStyleSheet(f"""
            color: {c().TEXT_MAIN};
            font-size: {ty().SIZE_LG}pt;
            font-weight: bold;
            letter-spacing: 1.5px;
        """)
        lay.addWidget(title_lbl)

        ver_lbl = QLabel("v2.0")
        ver_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_XS}pt;")
        lay.addWidget(ver_lbl)

        lay.addStretch()

        # Import / Export
        self._import_btn = ghost_button("↓ Import", c().CYAN if hasattr(c(), "CYAN") else c().BLUE, 90)
        self._import_btn.clicked.connect(self._on_import)
        lay.addWidget(self._import_btn)

        self._export_btn = ghost_button("↑ Export", c().GREEN, 90)
        self._export_btn.clicked.connect(self._on_export)
        lay.addWidget(self._export_btn)

        # Theme Manager button
        theme_btn = QPushButton("⚙  Theme")
        theme_btn.setCursor(Qt.PointingHandCursor)
        theme_btn.setStyleSheet(f"""
            QPushButton {{
                background: {accent}22;
                color: {accent};
                border: 1px solid {accent}55;
                border-radius: {sp().RADIUS_MD}px;
                padding: {sp().PAD_SM}px {sp().PAD_MD}px;
                font-size: {ty().SIZE_SM}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {accent}44; border-color: {accent}; }}
        """)
        theme_btn.clicked.connect(self._toggle_theme_panel)
        lay.addWidget(theme_btn)

        # Close
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {c().BG_HOVER};
                color: {c().TEXT_DIM};
                border: none;
                border-radius: 16px;
                font-size: {ty().SIZE_BODY}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {c().RED}; color: white; }}
        """)
        close_btn.clicked.connect(self.close)
        lay.addWidget(close_btn)

        # Make title bar draggable
        bar.mousePressEvent = self._drag_start
        bar.mouseMoveEvent = self._drag_move
        bar.mouseReleaseEvent = self._drag_end
        self._drag_pos: Optional[QPoint] = None

        return bar

    def _drag_start(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def _drag_move(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(e.globalPos() - self._drag_pos)

    def _drag_end(self, e):
        self._drag_pos = None

    def _toggle_theme_panel(self):
        if self._theme_panel and self._theme_panel.isVisible():
            self._theme_panel.hide()
            return
        if not self._theme_panel:
            self._theme_panel = ThemeManagerPanel(self)
        # Position near the top-right
        geo = self.geometry()
        self._theme_panel.move(geo.right() - self._theme_panel.width() - 30, geo.top() + 70)
        self._theme_panel.show()

    def _build_editor_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(60)
        bar.setStyleSheet(f"background: {c().BG_PANEL};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(sp().PAD_XL, 0, sp().PAD_XL, 0)
        lay.setSpacing(sp().GAP_MD)

        self._strategy_name_lbl = QLabel("Select a strategy →")
        self._strategy_name_lbl.setStyleSheet(f"""
            color: {c().TEXT_DIM};
            font-size: {ty().SIZE_XL}pt;
            font-weight: bold;
        """)
        lay.addWidget(self._strategy_name_lbl)

        self._active_badge = QLabel()
        self._active_badge.hide()
        accent = getattr(c(), "ACCENT", c().YELLOW)
        self._active_badge.setStyleSheet(f"""
            color: {accent};
            background: {accent}22;
            border: 1px solid {accent}55;
            border-radius: 999px;
            padding: 2px 12px;
            font-size: {ty().SIZE_XS}pt;
            font-weight: bold;
        """)
        lay.addWidget(self._active_badge)

        self._dirty_lbl = QLabel("● unsaved changes")
        self._dirty_lbl.hide()
        self._dirty_lbl.setStyleSheet(f"color: {c().YELLOW}; font-size: {ty().SIZE_SM}pt; font-weight: bold;")
        lay.addWidget(self._dirty_lbl)

        lay.addStretch()

        # Confidence threshold
        conf_lbl = QLabel("🎯 Min Confidence:")
        conf_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_SM}pt; font-weight: bold;")
        lay.addWidget(conf_lbl)

        self.confidence_spin = styled_spinbox(0.0, 1.0, 0.05, 2, 0.6)
        self.confidence_spin.setFixedWidth(90)
        self.confidence_spin.valueChanged.connect(lambda: self._mark_dirty())
        lay.addWidget(self.confidence_spin)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"background: {c().BORDER}; max-width: 1px; margin: 10px 4px;")
        lay.addWidget(sep)

        # Timeframe
        tf_lbl = QLabel("⏱ Timeframe:")
        tf_lbl.setStyleSheet(f"color: {c().TEXT_DIM}; font-size: {ty().SIZE_SM}pt; font-weight: bold;")
        lay.addWidget(tf_lbl)

        self.timeframe_cb = QComboBox()
        self.timeframe_cb.addItems(TIMEFRAMES)
        self.timeframe_cb.setCurrentText("1h")
        self.timeframe_cb.setFixedWidth(100)
        self.timeframe_cb.setCursor(Qt.PointingHandCursor)
        self.timeframe_cb.currentTextChanged.connect(lambda: self._mark_dirty())
        self.timeframe_cb.setStyleSheet(f"""
                    QComboBox {{
                        background: {c().BG_INPUT};
                        color: {c().PURPLE};
                        border: 1px solid {c().BORDER};
                        border-radius: {sp().RADIUS_MD}px;
                        padding: {sp().PAD_SM}px 28px {sp().PAD_SM}px {sp().PAD_MD}px;
                        font-size: {ty().SIZE_BODY}pt;
                        font-weight: bold;
                        min-height: {sp().INPUT_HEIGHT}px;
                    }}
                    QComboBox:hover {{
                        border-color: {c().PURPLE};
                        background: {c().BG_HOVER};
                    }}
                    QComboBox::drop-down {{
                        subcontrol-origin: padding;
                        subcontrol-position: top right;
                        width: 26px;
                        border-left: 1px solid {c().BORDER};
                        border-top-right-radius: {sp().RADIUS_MD}px;
                        border-bottom-right-radius: {sp().RADIUS_MD}px;
                        background: {c().PURPLE}22;
                    }}
                    QComboBox::drop-down:hover {{
                        background: {c().PURPLE}44;
                    }}
                    QComboBox::down-arrow {{
                        width: 0; height: 0;
                        border-left: 4px solid transparent;
                        border-right: 4px solid transparent;
                        border-top: 6px solid {c().PURPLE};
                    }}
                    QComboBox QAbstractItemView {{
                        background: {c().BG_PANEL};
                        color: {c().TEXT_MAIN};
                        border: 1px solid {c().BORDER};
                        selection-background-color: {c().BG_SELECTED};
                        outline: none;
                    }}
                    QComboBox QAbstractItemView::item {{
                        padding: {sp().PAD_SM}px {sp().PAD_MD}px;
                        min-height: 24px;
                    }}
                """)
        lay.addWidget(self.timeframe_cb)

        return bar

        return bar

    def _build_tabs(self) -> QTabWidget:
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.tabBar().setExpanding(True)
        accent = getattr(c(), "ACCENT", c().BLUE)
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {c().BG_PANEL};
            }}
            QTabBar::tab {{
                background: {c().BG_HOVER};
                color: {c().TEXT_DIM};
                border: none;
                border-right: 1px solid {c().BORDER};
                padding: {sp().PAD_SM}px {sp().PAD_XL}px;
                font-size: {ty().SIZE_SM}pt;
                min-width: 100px;
                min-height: {sp().TAB_H}px;
            }}
            QTabBar::tab:selected {{
                background: {c().BG_PANEL};
                color: {c().TEXT_MAIN};
                border-bottom: 2px solid {accent};
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background: {c().BORDER};
                color: {c().TEXT_MAIN};
            }}
        """)

        self._info_tab = InfoTab()
        self._rules_tab = SignalRulesTab()
        self._ind_tab = IndicatorsTab()
        self._help_tab = HelpTab()

        self._tabs.addTab(self._info_tab, "⚙  Info")
        self._tabs.addTab(self._rules_tab, "⊕  Signal Rules")
        self._tabs.addTab(self._ind_tab, "◈  Indicators")
        self._tabs.addTab(self._help_tab, "?  Help")

        self._info_tab.changed.connect(self._mark_dirty)

        return self._tabs

    def _build_footer(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(68)
        bar.setStyleSheet(f"background: {c().BG_PANEL};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(sp().PAD_XL, sp().PAD_SM, sp().PAD_XL, sp().PAD_SM)
        lay.setSpacing(sp().GAP_MD)

        self.activate_btn = styled_button(
            "⚡  Activate This Strategy",
            c().BLUE, c().BLUE_DARK, min_w=220, min_h=44
        )
        self.activate_btn.clicked.connect(self._on_activate)
        lay.addWidget(self.activate_btn)

        lay.addStretch()

        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet(f"color: {c().GREEN}; font-size: {ty().SIZE_BODY}pt; font-weight: bold;")
        lay.addWidget(self.status_lbl)

        self.revert_btn = ghost_button("↺ Revert", c().TEXT_DIM, 100)
        self.revert_btn.setMinimumHeight(40)
        self.revert_btn.clicked.connect(self._on_revert)
        lay.addWidget(self.revert_btn)

        accent = getattr(c(), "ACCENT", c().YELLOW)
        self.save_btn = styled_button("💾  Save", accent, accent, "#000", min_w=120, min_h=44)
        self.save_btn.clicked.connect(self._on_save)
        lay.addWidget(self.save_btn)

        return bar

    # ── Strategy Loading ──────────────────────────────────────────────────────

    def _load_strategy(self, slug: str):
        try:
            if self._dirty:
                ans = QMessageBox.question(
                    self, "Unsaved Changes",
                    "You have unsaved changes. Discard them?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if ans == QMessageBox.No:
                    return

            strategy = strategy_manager.get(slug)
            if strategy is None:
                return

            self._current_slug = slug
            self._info_tab.load(strategy)
            self._rules_tab.load(strategy)
            self._ind_tab.load(strategy)
            self._help_tab.load(strategy)

            engine = strategy.get("engine", {})
            self.confidence_spin.setValue(float(engine.get("min_confidence", 0.6)))
            saved_tf = strategy.get("timeframe", "1h")
            idx = self.timeframe_cb.findText(saved_tf)
            self.timeframe_cb.setCurrentIndex(idx if idx >= 0 else self.timeframe_cb.findText("1h"))
            print(engine)
            self._mark_dirty(False)

            name = strategy.get("name", slug)
            self._strategy_name_lbl.setText(name)
            self._strategy_name_lbl.setStyleSheet(f"""
                color: {c().TEXT_MAIN};
                font-size: {ty().SIZE_XL}pt;
                font-weight: bold;
            """)

            is_active = strategy_manager.get_active_slug() == slug
            if is_active:
                self._active_badge.setText("⚡ ACTIVE")
                self._active_badge.show()
            else:
                self._active_badge.hide()

            self.status_lbl.clear()

        except Exception as e:
            logger.error(f"[StrategyEditorWindow._load_strategy] {e}", exc_info=True)

    # ── Dirty State ───────────────────────────────────────────────────────────

    def _mark_dirty(self, dirty: bool = True):
        self._dirty = dirty
        self._dirty_lbl.setVisible(dirty)

    # ── Slots ─────────────────────────────────────────────────────────────────

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
            if ans == QMessageBox.Yes and not self._do_save():
                return

        strategy_manager.activate(self._current_slug)
        self._list_panel.refresh()
        self._active_badge.setText("⚡ ACTIVE")
        self._active_badge.show()
        self._flash_status("⚡ Strategy activated!")
        self.strategy_activated.emit(self._current_slug)

    def _on_revert(self):
        if self._current_slug:
            self._load_strategy(self._current_slug)

    def _on_save(self):
        self._do_save()

    def _do_save(self) -> bool:
        try:
            if not self._current_slug:
                return False

            info = self._info_tab.collect()
            name = info["name"]
            if not name:
                QMessageBox.warning(self, "Validation", "Strategy name cannot be empty.")
                return False

            strategy = strategy_manager.get(self._current_slug) or {}
            strategy["name"] = name
            strategy["description"] = info["description"]
            strategy["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            engine = self._rules_tab.collect()
            engine["conflict_resolution"] = info.get("conflict_resolution", "WAIT")
            engine["min_confidence"] = self.confidence_spin.value()
            strategy["engine"] = engine
            strategy["timeframe"] = self.timeframe_cb.currentText()

            ok = strategy_manager.save(self._current_slug, strategy)
            if ok:
                self._mark_dirty(False)
                self._strategy_name_lbl.setText(name)
                self._list_panel.refresh()
                self._flash_status("✓ Saved")
                # Notify TradingGUI so it can hot-reload the signal engine when
                # this slug is the currently active strategy.
                self.strategy_saved.emit(self._current_slug)
                return True
            else:
                self._flash_status("✗ Save failed")
                return False

        except Exception as e:
            logger.error(f"[StrategyEditorWindow._do_save] {e}", exc_info=True)
            self._flash_status("✗ Save error")
            return False

    def _on_import(self):
        dlg = ImportExportDialog("import", parent=self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_imported_data()
            name, ok = QInputDialog.getText(
                self, "Import Strategy", "Strategy name:",
                text=data.get("name", "Imported Strategy")
            )
            if ok and name.strip():
                ok2, slug = strategy_manager.create(name.strip())
                if ok2:
                    s = strategy_manager.get(slug) or {}
                    s["description"] = data.get("description", "")
                    s["engine"] = data.get("engine", {})
                    strategy_manager.save(slug, s)
                    self._current_slug = slug
                    self._list_panel.refresh()
                    self._load_strategy(slug)
                    QMessageBox.information(self, "Success", f"'{name}' imported successfully!")

    def _on_export(self):
        if not self._current_slug:
            QMessageBox.warning(self, "No Strategy", "Please select a strategy to export.")
            return
        strategy = strategy_manager.get(self._current_slug)
        if strategy:
            dlg = ImportExportDialog("export", strategy, self)
            dlg.exec_()

    def _flash_status(self, msg: str, ms: int = 2500):
        self.status_lbl.setText(msg)
        QTimer.singleShot(ms, self.status_lbl.clear)

    # ── Close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._dirty:
            ans = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Close anyway?",
                QMessageBox.Yes | QMessageBox.No
            )
            if ans == QMessageBox.No:
                event.ignore()
                return
        super().closeEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE TEST RUNNER
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    app.setApplicationName("Strategy Editor")

    # Apply global base style
    app.setStyleSheet(f"""
        QWidget {{
            background: {c().BG_PANEL};
            color: {c().TEXT_MAIN};
            font-family: 'Segoe UI', 'Arial', sans-serif;
            font-size: {ty().SIZE_BODY}pt;
        }}
        QScrollBar:vertical {{
            background: {c().BG_PANEL};
            width: 6px;
            border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{
            background: {c().BORDER_STRONG};
            border-radius: 3px;
            min-height: 20px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{ height: 0; }}
        QToolTip {{
            background: {c().BG_PANEL};
            color: {c().TEXT_MAIN};
            border: 1px solid {c().BORDER};
            padding: 4px 8px;
            border-radius: 4px;
            font-size: {ty().SIZE_SM}pt;
        }}
    """)

    win = StrategyEditorWindow()
    win.show()

    sys.exit(app.exec_())