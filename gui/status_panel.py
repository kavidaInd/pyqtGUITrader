from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
    QScrollArea,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt
import threading
from typing import Optional, Any, Dict, List
import traceback

# ── Palette ───────────────────────────────────────────────────────────────────
BG_MAIN   = "#0d1117"
BG_PANEL  = "#161b22"
BG_ROW_A  = "#1c2128"
BG_ROW_B  = "#22272e"
BORDER    = "#30363d"
TEXT_MAIN = "#e6edf3"
TEXT_DIM  = "#8b949e"
GREEN     = "#3fb950"
RED       = "#f85149"
YELLOW    = "#d29922"
BLUE      = "#58a6ff"
ORANGE    = "#ffa657"
GREY_OFF  = "#484f58"



def _global_ss() -> str:
    return f"""
        QWidget, QFrame {{
            background: {BG_MAIN};
            color: {TEXT_MAIN};
            font-family: 'Segoe UI', sans-serif;
        }}
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
            padding: 6px 16px;
            font-size: 9pt;
            font-weight: bold;
        }}
        QTabBar::tab:selected {{
            background: {BG_PANEL};
            color: {TEXT_MAIN};
            border-bottom: 2px solid {BLUE};
        }}
        QTableWidget {{
            background: {BG_PANEL};
            gridline-color: {BORDER};
            border: none;
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
        QScrollArea {{ border: none; background: transparent; }}
        QLabel {{ color: {TEXT_MAIN}; }}
    """


# ─────────────────────────────────────────────────────────────────────────────
# StatusCard
# ─────────────────────────────────────────────────────────────────────────────

class StatusCard(QFrame):
    """Single status field with icon label + live value."""

    _BASE_SS = f"""
        QFrame {{
            background: {BG_PANEL};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 4px;
        }}
    """
    _DIM_SS = f"""
        QFrame {{
            background: #0f1318;
            border: 1px solid #1c2230;
            border-radius: 6px;
            padding: 4px;
        }}
    """

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self._dimmed = False
        self.setStyleSheet(self._BASE_SS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._title = QLabel(f"{icon}  {label}")
        self._title.setFont(QFont("Segoe UI", 8))
        self._title.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")

        self.value_label = QLabel("—")
        self.value_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.value_label.setStyleSheet(f"color: {TEXT_MAIN}; border: none; background: transparent;")

        self._last_value = None
        self._last_color = TEXT_MAIN

        layout.addWidget(self._title)
        layout.addWidget(self.value_label)

    def set_value(self, text: str, color: str = TEXT_MAIN):
        """Must be called on the main thread only."""
        if text == self._last_value and color == self._last_color:
            return
        self.value_label.setText(text)
        self.value_label.setStyleSheet(
            f"color: {color}; border: none; background: transparent;"
        )
        self._last_value = text
        self._last_color = color

    def set_dimmed(self, dimmed: bool):
        """Grey out card when it is irrelevant (no active trade)."""
        if dimmed == self._dimmed:
            return
        self._dimmed = dimmed
        self.setStyleSheet(self._DIM_SS if dimmed else self._BASE_SS)
        dim_col = GREY_OFF if dimmed else TEXT_DIM
        self._title.setStyleSheet(
            f"color: {dim_col}; border: none; background: transparent;"
        )
        if dimmed:
            self.value_label.setText("—")
            self.value_label.setStyleSheet(
                f"color: {GREY_OFF}; border: none; background: transparent;"
            )
            self._last_value = None   # force repaint when trade reopens


# ─────────────────────────────────────────────────────────────────────────────
# StatusPanel  (public API fully preserved)
# ─────────────────────────────────────────────────────────────────────────────

class StatusPanel(QWidget):
    """
    Single-tab panel showing live trade status.

    Trade Status tab
        Grid of StatusCards for position, balance, prices, PnL etc.
        Trade-specific cards (symbol, buy/current/target/stoploss price, PnL)
        are automatically greyed out and reset when no trade is active.

    Signal Data (moved to MultiChartWidget tab 3 — "🔬 Signal Data")
        Previously Tab 2 here; now lives in the chart area where there is
        sufficient horizontal space for the indicator and rule tables.

    Public API (unchanged):
        panel.refresh(state, config)
        panel.pause_refresh()
        panel.resume_refresh()
        panel.clear_cache()
    """

    # Cards that only make sense when a trade is open
    _TRADE_ONLY = frozenset({"symbol", "buy_price", "current_price",
                              "target_price", "stoploss_price", "pnl"})

    FIELDS = [
        # Always-visible
        ("position",       "🟢", "Position"),
        ("prev_position",  "🔄", "Previous Position"),
        ("balance",        "🏦", "Balance"),
        ("derivative",     "📈", "Derivative Price"),
        # Trade-specific (dimmed when no trade)
        ("symbol",         "💹", "Symbol"),
        ("buy_price",      "🛒", "Buy Price"),
        ("current_price",  "💰", "Current Price"),
        ("target_price",   "🎯", "Target Price"),
        ("stoploss_price", "🛑", "Stoploss Price"),
        ("pnl",            "💵", "PnL"),
    ]

    COLORS = {
        "positive": GREEN,
        "negative": RED,
        "neutral":  TEXT_DIM,
        "normal":   TEXT_MAIN,
        "accent":   BLUE,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_global_ss())

        self._lock            = threading.Lock()
        self._last_state: Dict = {}
        self._refresh_enabled = True
        self._trade_active    = False   # tracks last known trade state

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs)

        # ── Tab 1: Trade Status ────────────────────────────────────────────
        trade_tab   = QWidget()
        trade_layout = QVBoxLayout(trade_tab)
        trade_layout.setContentsMargins(6, 6, 6, 6)
        trade_layout.setSpacing(4)

        # No-trade notice (visible when no trade is open)
        self._no_trade_lbl = QLabel("⚪  No active trade — trade fields are greyed out")
        self._no_trade_lbl.setStyleSheet(
            f"color: {GREY_OFF}; font-size: 8pt; padding: 2px 4px;"
        )
        trade_layout.addWidget(self._no_trade_lbl)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)
        self.cards: Dict[str, StatusCard] = {}

        for i, (key, icon, label) in enumerate(self.FIELDS):
            card = StatusCard(icon, label)
            grid.addWidget(card, i // 2, i % 2)
            self.cards[key] = card

        trade_layout.addWidget(grid_widget)
        trade_layout.addStretch()

        # Start with trade-only cards dimmed
        for key in self._TRADE_ONLY:
            self.cards[key].set_dimmed(True)

        self._tabs.addTab(trade_tab, "📊  Trade Status   ")

    # ── Private helpers ───────────────────────────────────────────────────────

    def _safe_get(self, obj: Any, attr: str, default: Any = None) -> Any:
        try:
            return getattr(obj, attr) if hasattr(obj, attr) else default
        except Exception:
            return default

    def _fmt(self, value: Any, spec: str = ".2f") -> str:
        if value is None:
            return "—"
        try:
            return f"{float(value):{spec}}"
        except (ValueError, TypeError):
            return str(value)

    def _pnl_color(self, pnl) -> str:
        try:
            v = float(pnl)
            if v > 0: return self.COLORS["positive"]
            if v < 0: return self.COLORS["negative"]
        except (TypeError, ValueError):
            pass
        return self.COLORS["neutral"]

    def _pos_color(self, pos) -> str:
        if pos and str(pos).upper() in ("LONG", "SHORT"):
            return self.COLORS["positive"]
        return self.COLORS["neutral"]

    def _trade_open(self, state) -> bool:
        pos = self._safe_get(state, "current_position")
        if pos and str(pos).upper() not in ("NONE", "NO POSITION", ""):
            return True
        return bool(self._safe_get(state, "current_trading_symbol"))

    def _set_card(self, key: str, text: str, color: str):
        """Apply a card update only when the value actually changed."""
        ck, cc = f"{key}_v", f"{key}_c"
        with self._lock:
            if text != self._last_state.get(ck) or color != self._last_state.get(cc):
                self.cards[key].set_value(text, color)
                self._last_state[ck] = text
                self._last_state[cc] = color

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, state, config):
        """
        Called on the main thread by QTimer every second.
        Reads TradeState and updates both tabs.
        """
        if state is None or not self._refresh_enabled:
            return
        try:
            with self._lock:
                pos       = self._safe_get(state, "current_position")
                prev_pos  = self._safe_get(state, "previous_position")
                symbol    = self._safe_get(state, "current_trading_symbol")
                buy_price = self._safe_get(state, "current_buy_price")
                cur_price = self._safe_get(state, "current_price")
                tp        = self._safe_get(state, "tp_point")
                sl        = self._safe_get(state, "stop_loss")
                pnl       = self._safe_get(state, "percentage_change")
                balance   = self._safe_get(state, "account_balance")
                deriv     = self._safe_get(state, "derivative_current_price")
                pass  # derivative_trend is consumed by chart widget

            # ── Trade-active state: toggle dimming ─────────────────────────
            trade_active = self._trade_open(state)
            if trade_active != self._trade_active:
                self._trade_active = trade_active
                for key in self._TRADE_ONLY:
                    self.cards[key].set_dimmed(not trade_active)
                self._no_trade_lbl.setVisible(not trade_active)

            # ── Always-visible cards ───────────────────────────────────────
            self._set_card("position",
                           str(pos) if pos else "None", self._pos_color(pos))
            self._set_card("prev_position",
                           str(prev_pos) if prev_pos else "None", self.COLORS["normal"])
            self._set_card("balance",    self._fmt(balance),   self.COLORS["normal"])
            self._set_card("derivative", self._fmt(deriv),     self.COLORS["accent"])

            # ── Trade-specific cards (only update when trade is active) ────
            if trade_active:
                self._set_card("symbol",        str(symbol) if symbol else "—",  self.COLORS["normal"])
                self._set_card("buy_price",     self._fmt(buy_price),             self.COLORS["normal"])
                self._set_card("current_price", self._fmt(cur_price),             self.COLORS["normal"])
                self._set_card("target_price",  self._fmt(tp),                    self.COLORS["positive"])
                self._set_card("stoploss_price",self._fmt(sl),                    self.COLORS["negative"])
                try:
                    pnl_txt = f"{float(pnl):.2f}%" if pnl is not None else "—"
                except (ValueError, TypeError):
                    pnl_txt = str(pnl)
                self._set_card("pnl", pnl_txt, self._pnl_color(pnl))

            # Signal Data is refreshed by MultiChartWidget (chart tab 3)

        except Exception as e:
            print(f"StatusPanel.refresh error: {e}")
            traceback.print_exc()

    def pause_refresh(self):
        self._refresh_enabled = False

    def resume_refresh(self):
        self._refresh_enabled = True

    def clear_cache(self):
        with self._lock:
            self._last_state.clear()

    def closeEvent(self, event):
        self.pause_refresh()
        self.clear_cache()
        super().closeEvent(event)