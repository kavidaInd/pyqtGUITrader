"""
DynamicSignalDebugPopup
=======================
A live-updating popup that shows every detail of the DynamicSignalEngine
evaluation: indicator values, rule-by-rule results, group fired/not-fired
status, conflict detection, and the final resolved signal.

Usage (from TradingGUI.py):
    # In __init__:
    self.signal_debug_popup = None

    # In _create_menu (under the View menu):
    sig_act = QAction("🔬 Dynamic Signal Debug", self)
    sig_act.triggered.connect(self._show_signal_debug_popup)
    view_menu.addAction(sig_act)

    # New method:
    def _show_signal_debug_popup(self):
        if not self.trading_app:
            QMessageBox.information(self, "Not Ready", "Trading app not initialized yet.")
            return
        if not self.signal_debug_popup:
            self.signal_debug_popup = DynamicSignalDebugPopup(self.trading_app, self)
        self.signal_debug_popup.show()
        self.signal_debug_popup.raise_()
        self.signal_debug_popup.activateWindow()

    # In _tick_fast, add:
    if self.signal_debug_popup and self.signal_debug_popup.isVisible():
        self.signal_debug_popup.refresh()

    # In _close_all_popups, add:
    if self.signal_debug_popup:
        self.signal_debug_popup.close()
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QGroupBox,
    QGridLayout, QTabWidget, QTextEdit,
)

logger = logging.getLogger(__name__)

# ── Colours matching the dark theme ─────────────────────────────────────────
BG_MAIN   = "#0d1117"
BG_PANEL  = "#161b22"
BG_ROW_A  = "#1c2128"
BG_ROW_B  = "#22272e"
BORDER    = "#30363d"
TEXT_DIM  = "#8b949e"
TEXT_MAIN = "#e6edf3"
GREEN     = "#3fb950"
RED       = "#f85149"
YELLOW    = "#d29922"
BLUE      = "#58a6ff"
PURPLE    = "#bc8cff"
ORANGE    = "#ffa657"
GREY_OFF  = "#484f58"

SIGNAL_COLORS = {
    "BUY_CALL":  "#3fb950",
    "BUY_PUT":   "#58a6ff",
    "SELL_CALL": "#f85149",
    "SELL_PUT":  "#ffa657",
    "HOLD":      "#d29922",
    "WAIT":      "#484f58",
}

SIGNAL_LABELS = {
    "BUY_CALL":  "📈  Buy Call",
    "BUY_PUT":   "📉  Buy Put",
    "SELL_CALL": "🔴  Sell Call",
    "SELL_PUT":  "🟠  Sell Put",
    "HOLD":      "⏸   Hold",
    "WAIT":      "⏳  Wait",
}

SIGNAL_GROUPS = ["BUY_CALL", "BUY_PUT", "SELL_CALL", "SELL_PUT", "HOLD"]


def _style_sheet() -> str:
    return f"""
        QDialog, QWidget {{
            background: {BG_MAIN};
            color: {TEXT_MAIN};
            font-family: 'Consolas', 'Menlo', monospace;
        }}
        QLabel {{ color: {TEXT_MAIN}; }}
        QGroupBox {{
            background: {BG_PANEL};
            border: 1px solid {BORDER};
            border-radius: 6px;
            margin-top: 12px;
            padding: 6px;
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: {TEXT_MAIN};
            font-size: 9pt;
        }}
        QTableWidget {{
            background: {BG_PANEL};
            gridline-color: {BORDER};
            border: 1px solid {BORDER};
            border-radius: 4px;
            color: {TEXT_MAIN};
            font-size: 9pt;
        }}
        QTableWidget::item {{ padding: 4px 8px; }}
        QHeaderView::section {{
            background: #21262d;
            color: {TEXT_DIM};
            border: none;
            border-bottom: 1px solid {BORDER};
            padding: 4px 8px;
            font-size: 8pt;
            font-weight: bold;
        }}
        QPushButton {{
            background: #21262d;
            color: {TEXT_MAIN};
            border: 1px solid {BORDER};
            border-radius: 5px;
            padding: 6px 16px;
            font-size: 9pt;
        }}
        QPushButton:hover {{ background: #2d333b; }}
        QTabWidget::pane {{
            border: 1px solid {BORDER};
            border-radius: 4px;
            background: {BG_PANEL};
        }}
        QTabBar::tab {{
            background: #21262d;
            color: {TEXT_DIM};
            border: 1px solid {BORDER};
            border-bottom: none;
            border-radius: 4px 4px 0 0;
            padding: 5px 14px;
            font-size: 9pt;
        }}
        QTabBar::tab:selected {{
            background: {BG_PANEL};
            color: {TEXT_MAIN};
            border-bottom: 2px solid {BLUE};
        }}
        QScrollArea {{ border: none; background: transparent; }}
        QCheckBox {{ color: {TEXT_DIM}; font-size: 9pt; spacing: 5px; }}
        QTextEdit {{
            background: {BG_PANEL};
            color: {TEXT_MAIN};
            border: 1px solid {BORDER};
            border-radius: 4px;
            font-family: 'Consolas', 'Menlo', monospace;
            font-size: 9pt;
        }}
    """


def _header_label(text: str, color: str = TEXT_DIM, size: int = 8) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {color}; font-size: {size}pt; font-weight: bold;")
    return lbl


def _value_label(text: str, color: str = TEXT_MAIN, size: int = 9) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {color}; font-size: {size}pt; font-weight: bold;")
    return lbl


class _SignalBadge(QLabel):
    """Pill-shaped label showing a signal value."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(130)
        self.setFixedHeight(36)
        self._set("WAIT")

    def _set(self, signal_value: str):
        color = SIGNAL_COLORS.get(signal_value, SIGNAL_COLORS["WAIT"])
        label = SIGNAL_LABELS.get(signal_value, signal_value)
        self.setText(label)
        self.setStyleSheet(f"""
            QLabel {{
                background: {color}22;
                color: {color};
                border: 2px solid {color};
                border-radius: 6px;
                font-size: 13pt;
                font-weight: bold;
                padding: 2px 12px;
            }}
        """)

    def update_signal(self, signal_value: str):
        self._set(signal_value)


class _RuleRow:
    """One row in a rule table: rule expression | current values | result."""
    def __init__(self, table: QTableWidget, row: int):
        self.table = table
        self.row = row

    def set(self, rule_str: str, lhs_val: str, op: str, rhs_val: str, result: bool, error: str = ""):
        items = [
            (rule_str, TEXT_MAIN),
            (lhs_val, BLUE),
            (op, YELLOW),
            (rhs_val, ORANGE),
            ("✅  TRUE" if result else "❌  FALSE", GREEN if result else RED),
        ]
        if error:
            items[-1] = (f"⚠ {error[:40]}", YELLOW)

        for col, (text, color) in enumerate(items):
            item = QTableWidgetItem(text)
            item.setForeground(QColor(color))
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.setItem(self.row, col, item)


class _GroupPanel(QGroupBox):
    """
    Panel for one signal group (BUY_CALL, BUY_PUT, etc.).
    Shows logic mode, fired status, and a per-rule table.
    """
    def __init__(self, signal: str, parent=None):
        label = SIGNAL_LABELS.get(signal, signal)
        color = SIGNAL_COLORS.get(signal, GREY_OFF)
        super().__init__(f" {label} ", parent)
        self.signal = signal
        self._color = color
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 12, 8, 8)
        root.setSpacing(6)

        # Top row: logic + fired indicator
        top = QHBoxLayout()
        top.setSpacing(10)

        self._logic_lbl = _header_label("Logic: AND", TEXT_DIM)
        top.addWidget(self._logic_lbl)
        top.addStretch()

        self._fired_lbl = QLabel("⬤  NOT FIRED")
        self._fired_lbl.setStyleSheet(f"color: {GREY_OFF}; font-size: 9pt; font-weight: bold;")
        top.addWidget(self._fired_lbl)

        self._enabled_lbl = QLabel("enabled")
        self._enabled_lbl.setStyleSheet(f"color: {GREY_OFF}; font-size: 8pt;")
        top.addWidget(self._enabled_lbl)

        root.addLayout(top)

        # Rule table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Rule Expression", "LHS Value", "Op", "RHS Value", "Result"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 5):
            self._table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(f"""
            QTableWidget {{ alternate-background-color: {BG_ROW_B}; background: {BG_ROW_A}; }}
        """)
        self._table.setMinimumHeight(80)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        root.addWidget(self._table)

        self._no_rules_lbl = QLabel("  ⚪ No rules configured for this signal.")
        self._no_rules_lbl.setStyleSheet(f"color: {GREY_OFF}; font-size: 9pt; padding: 8px;")
        root.addWidget(self._no_rules_lbl)
        self._no_rules_lbl.hide()

    def update(self, rule_results: List[Dict], fired: bool, logic: str, enabled: bool,
               indicator_cache: Dict = None):
        # Logic label
        self._logic_lbl.setText(f"Logic: {logic}")

        # Enabled
        if enabled:
            self._enabled_lbl.setText("✓ enabled")
            self._enabled_lbl.setStyleSheet(f"color: {GREEN}; font-size: 8pt;")
        else:
            self._enabled_lbl.setText("✗ disabled")
            self._enabled_lbl.setStyleSheet(f"color: {RED}; font-size: 8pt;")

        # Fired
        if fired:
            self._fired_lbl.setText("⬤  FIRED")
            self._fired_lbl.setStyleSheet(f"color: {self._color}; font-size: 9pt; font-weight: bold;")
        else:
            self._fired_lbl.setText("⬤  NOT FIRED")
            self._fired_lbl.setStyleSheet(f"color: {GREY_OFF}; font-size: 9pt; font-weight: bold;")

        if not rule_results:
            self._table.hide()
            self._no_rules_lbl.show()
            self._table.setRowCount(0)
            return

        self._no_rules_lbl.hide()
        self._table.show()
        self._table.setRowCount(len(rule_results))

        for i, entry in enumerate(rule_results):
            rule_str = entry.get("rule", "?")
            result   = entry.get("result", False)
            error    = entry.get("error", "")

            # Try to extract LHS/op/RHS from rule string for display
            lhs_val, op, rhs_val = _parse_rule_display(rule_str, indicator_cache)
            _RuleRow(self._table, i).set(rule_str, lhs_val, op, rhs_val, result, error)

        self._table.setFixedHeight(30 * len(rule_results) + 30)


def _parse_rule_display(rule_str: str, cache: Dict = None):
    """
    Split rule string like 'RSI(14) > 55' into lhs/op/rhs.
    If indicator_cache has the computed value, show it.
    """
    OPERATORS = ["crosses_above", "crosses_below", ">=", "<=", "!=", "==", ">", "<"]
    for op in OPERATORS:
        if f" {op} " in rule_str:
            parts = rule_str.split(f" {op} ", 1)
            lhs_name = parts[0].strip()
            rhs_name = parts[1].strip() if len(parts) > 1 else "?"

            # Look up current value from indicator cache
            lhs_val = _lookup_cache(lhs_name, cache)
            rhs_val = _lookup_cache(rhs_name, cache)
            return lhs_val, op, rhs_val

    return "?", "?", "?"


def _lookup_cache(name: str, cache: Dict = None) -> str:
    """Try to find a computed indicator value from the engine cache."""
    if cache is None:
        return name
    # Cache key format: "rsi_{"length": 14}"
    name_lower = name.lower().split("(")[0].strip()
    for key, series in cache.items():
        if key.startswith(name_lower + "_"):
            try:
                import pandas as pd
                if isinstance(series, pd.Series) and len(series) > 0:
                    val = series.iloc[-1]
                    if val is not None:
                        import math
                        if not math.isnan(float(val)):
                            return f"{name}  [{float(val):.4f}]"
            except Exception:
                pass
    return name


class _IndicatorCachePanel(QWidget):
    """Tab showing raw computed indicator values from the engine cache."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        lbl = _header_label("All computed indicator values during last evaluation:", TEXT_DIM)
        layout.addWidget(lbl)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Indicator (cache key)", "Latest Value", "Prev Value"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(f"""
            QTableWidget {{ alternate-background-color: {BG_ROW_B}; background: {BG_ROW_A}; }}
        """)
        layout.addWidget(self._table)

    def update_cache(self, cache: Dict):
        import pandas as pd
        rows = []
        for key, series in cache.items():
            try:
                if isinstance(series, pd.Series) and len(series) > 0:
                    latest = series.iloc[-1]
                    prev   = series.iloc[-2] if len(series) >= 2 else None
                    latest_str = f"{float(latest):.6f}" if latest is not None else "N/A"
                    prev_str   = f"{float(prev):.6f}"   if prev   is not None else "N/A"
                else:
                    latest_str = prev_str = "N/A"
            except Exception:
                latest_str = prev_str = "err"
            rows.append((key, latest_str, prev_str))

        self._table.setRowCount(len(rows))
        for i, (key, latest, prev) in enumerate(rows):
            for j, (text, color) in enumerate([(key, TEXT_DIM), (latest, BLUE), (prev, TEXT_DIM)]):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(color))
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self._table.setItem(i, j, item)


class _RawJsonPanel(QTextEdit):
    """Tab showing the raw evaluate() result dict as JSON."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

    def update_result(self, result: Dict):
        import json

        def _default(obj):
            return str(obj)

        try:
            text = json.dumps(result, indent=2, default=_default)
        except Exception as e:
            text = f"Serialisation error: {e}"
        self.setPlainText(text)


class DynamicSignalDebugPopup(QDialog):
    """
    Non-modal popup that lives alongside the main TradingGUI window.
    Call  refresh()  every second (or from _tick_fast) to keep it live.
    """

    def __init__(self, trading_app, parent=None):
        super().__init__(parent, Qt.Window)
        self.trading_app = trading_app
        self.setWindowTitle("🔬 Dynamic Signal Engine — Live Debug")
        self.resize(980, 750)
        self.setMinimumSize(700, 500)
        self.setStyleSheet(_style_sheet())

        # Internal state
        self._last_signal_value: str = ""
        self._auto_refresh = True
        self._indicator_cache: Dict = {}

        self._build_ui()

        # Auto-refresh every second when visible
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._maybe_refresh)
        self._timer.start(1000)

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────────
        header = self._build_header()
        root.addWidget(header)

        # ── Tabs ─────────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        root.addWidget(self._tabs, 1)

        # Tab 1: Group panels
        groups_widget = self._build_groups_tab()
        self._tabs.addTab(groups_widget, "📋  Signal Groups")

        # Tab 2: Indicator cache
        self._cache_panel = _IndicatorCachePanel()
        self._tabs.addTab(self._cache_panel, "📊  Indicator Values")

        # Tab 3: Raw JSON
        self._json_panel = _RawJsonPanel()
        self._tabs.addTab(self._json_panel, "{}  Raw JSON")

        # ── Footer ───────────────────────────────────────────────────────────
        footer = self._build_footer()
        root.addWidget(footer)

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 6px; }}")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(20)

        # Signal badge (large)
        sig_col = QVBoxLayout()
        sig_col.addWidget(_header_label("FINAL SIGNAL", TEXT_DIM, 8))
        self._signal_badge = _SignalBadge()
        sig_col.addWidget(self._signal_badge)
        layout.addLayout(sig_col)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"QFrame {{ border: 1px solid {BORDER}; }}")
        layout.addWidget(sep)

        # Grid of quick-status labels
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(4)

        self._lbl_conflict   = self._make_status_pair(grid, 0, 0, "CONFLICT")
        self._lbl_available  = self._make_status_pair(grid, 0, 2, "RULES AVAILABLE")
        self._lbl_symbol     = self._make_status_pair(grid, 1, 0, "SYMBOL")
        self._lbl_last_close = self._make_status_pair(grid, 1, 2, "LAST CLOSE")
        self._lbl_bars       = self._make_status_pair(grid, 2, 0, "BARS IN DF")
        self._lbl_timestamp  = self._make_status_pair(grid, 2, 2, "LAST REFRESH")

        layout.addLayout(grid, 1)
        layout.addStretch()

        # Fired group indicators (5 small pills)
        fired_col = QVBoxLayout()
        fired_col.addWidget(_header_label("GROUP FIRED", TEXT_DIM, 8))
        fired_inner = QHBoxLayout()
        self._fired_pills: Dict[str, QLabel] = {}
        for sig in SIGNAL_GROUPS:
            lbl = QLabel(sig.replace("_", "\n"))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedSize(64, 42)
            lbl.setStyleSheet(f"""
                QLabel {{
                    background: {GREY_OFF}33;
                    color: {GREY_OFF};
                    border: 1px solid {GREY_OFF};
                    border-radius: 5px;
                    font-size: 7pt;
                    font-weight: bold;
                }}
            """)
            self._fired_pills[sig] = lbl
            fired_inner.addWidget(lbl)
        fired_col.addLayout(fired_inner)
        layout.addLayout(fired_col)

        return frame

    def _make_status_pair(self, grid: QGridLayout, row: int, col: int, title: str) -> QLabel:
        grid.addWidget(_header_label(title, TEXT_DIM, 7), row, col)
        val_lbl = _value_label("—", TEXT_MAIN, 9)
        grid.addWidget(val_lbl, row, col + 1)
        return val_lbl

    def _build_groups_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self._groups_layout = QVBoxLayout(container)
        self._groups_layout.setContentsMargins(4, 4, 4, 4)
        self._groups_layout.setSpacing(8)

        self._group_panels: Dict[str, _GroupPanel] = {}
        for sig in SIGNAL_GROUPS:
            panel = _GroupPanel(sig)
            self._group_panels[sig] = panel
            self._groups_layout.addWidget(panel)

        self._groups_layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _build_footer(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 4px; }}")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        self._auto_chk = QCheckBox("Auto-refresh (1 s)")
        self._auto_chk.setChecked(True)
        self._auto_chk.toggled.connect(self._on_auto_toggle)
        layout.addWidget(self._auto_chk)

        layout.addStretch()

        self._status_lbl = QLabel("Waiting for data…")
        self._status_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 8pt;")
        layout.addWidget(self._status_lbl)

        layout.addStretch()

        refresh_btn = QPushButton("⟳  Refresh Now")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)

        close_btn = QPushButton("✕  Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        return frame

    # ── Refresh logic ────────────────────────────────────────────────────────

    @pyqtSlot()
    def _maybe_refresh(self):
        if self._auto_refresh and self.isVisible():
            self.refresh()

    def _on_auto_toggle(self, checked: bool):
        self._auto_refresh = checked

    @pyqtSlot()
    def refresh(self):
        """Pull the latest option_signal from trading_app.state and update UI."""
        try:
            state = getattr(self.trading_app, "state", None)
            if state is None:
                self._status_lbl.setText("⚠  trading_app.state is None")
                return

            # Get trend data (derivative_trend holds the last detect() result)
            trend_data = getattr(state, "derivative_trend", None) or {}
            option_signal = trend_data.get("option_signal")

            if option_signal is None:
                self._status_lbl.setText("⚠  No option_signal in state.derivative_trend yet.")
                return

            if not option_signal.get("available", False):
                if not option_signal.get("fired"):
                    self._status_lbl.setText("ℹ  Engine available but no rules configured.")
                else:
                    self._status_lbl.setText("ℹ  DynamicSignalEngine not available.")
                return

            # ── Update header ────────────────────────────────────────────────
            signal_val = option_signal.get("signal_value", "WAIT")
            self._signal_badge.update_signal(signal_val)

            conflict = option_signal.get("conflict", False)
            self._lbl_conflict.setText("⚠ YES" if conflict else "No")
            self._lbl_conflict.setStyleSheet(f"color: {RED if conflict else GREEN}; font-weight: bold; font-size: 9pt;")

            self._lbl_available.setText("Yes")
            self._lbl_available.setStyleSheet(f"color: {GREEN}; font-weight: bold; font-size: 9pt;")

            # Symbol & price from trend_data
            symbol = trend_data.get("name", "—")
            close_list = trend_data.get("close") or []
            last_close = close_list[-1] if close_list else "—"
            self._lbl_symbol.setText(str(symbol))
            self._lbl_last_close.setText(str(last_close))

            # Bars
            self._lbl_bars.setText(str(len(close_list)))

            # Timestamp
            from datetime import datetime
            self._lbl_timestamp.setText(datetime.now().strftime("%H:%M:%S"))

            # ── Fired pills ──────────────────────────────────────────────────
            fired_map = option_signal.get("fired", {})
            for sig, pill in self._fired_pills.items():
                is_fired = fired_map.get(sig, False)
                color = SIGNAL_COLORS.get(sig, GREY_OFF) if is_fired else GREY_OFF
                pill.setStyleSheet(f"""
                    QLabel {{
                        background: {color}33;
                        color: {color};
                        border: 2px solid {color};
                        border-radius: 5px;
                        font-size: 7pt;
                        font-weight: bold;
                    }}
                """)

            # ── Group panels ─────────────────────────────────────────────────
            rule_results = option_signal.get("rule_results", {})

            # Try to get engine's indicator cache for richer display
            indicator_cache = {}
            if hasattr(self.trading_app, "trend_detector") and \
               hasattr(self.trading_app.trend_detector, "signal_engine") and \
               self.trading_app.trend_detector.signal_engine is not None:
                engine = self.trading_app.trend_detector.signal_engine
                # Access last cache if stored (see note below)
                indicator_cache = getattr(engine, "_last_cache", {})

            for sig in SIGNAL_GROUPS:
                panel = self._group_panels[sig]
                rules_for_sig = rule_results.get(sig, [])
                is_fired = fired_map.get(sig, False)
                logic = "AND"
                enabled = True
                engine = getattr(
                    getattr(self.trading_app, "trend_detector", None),
                    "signal_engine", None
                )
                if engine:
                    logic   = engine.get_logic(sig)
                    enabled = engine.is_enabled(sig)

                panel.update(rules_for_sig, is_fired, logic, enabled, indicator_cache)

            # ── Indicator values tab ─────────────────────────────────────────
            self._cache_panel.update_cache(indicator_cache)

            # ── Raw JSON tab ─────────────────────────────────────────────────
            self._json_panel.update_result(option_signal)

            self._status_lbl.setText(f"✓  Last update: {datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            logger.error(f"DynamicSignalDebugPopup.refresh error: {e}", exc_info=True)
            self._status_lbl.setText(f"⚠  Refresh error: {e}")

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)