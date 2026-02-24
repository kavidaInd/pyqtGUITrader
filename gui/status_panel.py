from __future__ import annotations

import logging.handlers
import threading
from typing import Any, Dict, Set

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QLabel, QFrame, QVBoxLayout, QTabWidget, )

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

# ── Palette ───────────────────────────────────────────────────────────────────
BG_MAIN = "#0d1117"
BG_PANEL = "#161b22"
BG_ROW_A = "#1c2128"
BG_ROW_B = "#22272e"
BORDER = "#30363d"
TEXT_MAIN = "#e6edf3"
TEXT_DIM = "#8b949e"
GREEN = "#3fb950"
RED = "#f85149"
YELLOW = "#d29922"
BLUE = "#58a6ff"
ORANGE = "#ffa657"
GREY_OFF = "#484f58"


def _global_ss() -> str:
    """Return global stylesheet string."""
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
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
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

            logger.debug(f"StatusCard created: {icon} {label}")

        except Exception as e:
            logger.error(f"[StatusCard.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self._safe_defaults_init()

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._dimmed = False
        self._title = None
        self.value_label = None
        self._last_value = None
        self._last_color = TEXT_MAIN

    def set_value(self, text: str, color: str = TEXT_MAIN):
        """Must be called on the main thread only."""
        try:
            # Rule 6: Input validation
            if text is None:
                logger.warning("set_value called with None text")
                text = "—"

            if not isinstance(color, str):
                logger.warning(f"set_value called with non-string color: {color}")
                color = TEXT_MAIN

            # FIXED: Use explicit None check
            if self.value_label is None:
                logger.warning("set_value called with None value_label")
                return

            # Check if value changed
            if text == self._last_value and color == self._last_color:
                return

            self.value_label.setText(text)
            self.value_label.setStyleSheet(
                f"color: {color}; border: none; background: transparent;"
            )
            self._last_value = text
            self._last_color = color

        except Exception as e:
            logger.error(f"[StatusCard.set_value] Failed: {e}", exc_info=True)

    def set_dimmed(self, dimmed: bool):
        """Grey out card when it is irrelevant (no active trade)."""
        try:
            # Rule 6: Input validation
            if not isinstance(dimmed, bool):
                logger.warning(f"set_dimmed called with non-bool: {dimmed}")
                dimmed = bool(dimmed)

            if dimmed == self._dimmed:
                return

            self._dimmed = dimmed
            self.setStyleSheet(self._DIM_SS if dimmed else self._BASE_SS)
            dim_col = GREY_OFF if dimmed else TEXT_DIM

            # FIXED: Use explicit None check
            if self._title is not None:
                self._title.setStyleSheet(
                    f"color: {dim_col}; border: none; background: transparent;"
                )

            # FIXED: Use explicit None check
            if dimmed:
                if self.value_label is not None:
                    self.value_label.setText("—")
                    self.value_label.setStyleSheet(
                        f"color: {GREY_OFF}; border: none; background: transparent;"
                    )
                self._last_value = None  # force repaint when trade reopens

        except Exception as e:
            logger.error(f"[StatusCard.set_dimmed] Failed: {e}", exc_info=True)


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
    _TRADE_ONLY: Set[str] = frozenset({"symbol", "buy_price", "current_price",
                                       "target_price", "stoploss_price", "pnl"})

    FIELDS = [
        # Always-visible
        ("position", "🟢", "Position"),
        ("prev_position", "🔄", "Previous Position"),
        ("balance", "🏦", "Balance"),
        ("derivative", "📈", "Derivative Price"),
        # Trade-specific (dimmed when no trade)
        ("symbol", "💹", "Symbol"),
        ("buy_price", "🛒", "Buy Price"),
        ("current_price", "💰", "Current Price"),
        ("target_price", "🎯", "Target Price"),
        ("stoploss_price", "🛑", "Stoploss Price"),
        ("pnl", "💵", "PnL"),
    ]

    COLORS = {
        "positive": GREEN,
        "negative": RED,
        "neutral": TEXT_DIM,
        "normal": TEXT_MAIN,
        "accent": BLUE,
    }

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setStyleSheet(_global_ss())

            self._lock = threading.RLock()  # Use RLock for reentrant locking
            self._last_state: Dict[str, str] = {}
            self._refresh_enabled = True
            self._trade_active = False  # tracks last known trade state
            self._closing = False

            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            self._tabs = QTabWidget()
            root.addWidget(self._tabs)

            # ── Tab 1: Trade Status ────────────────────────────────────────────
            trade_tab = QWidget()
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
                try:
                    card = StatusCard(icon, label)
                    grid.addWidget(card, i // 2, i % 2)
                    self.cards[key] = card
                except Exception as e:
                    logger.error(f"Failed to create card for {key}: {e}", exc_info=True)

            trade_layout.addWidget(grid_widget)
            trade_layout.addStretch()

            # Start with trade-only cards dimmed
            for key in self._TRADE_ONLY:
                if key in self.cards:
                    self.cards[key].set_dimmed(True)

            self._tabs.addTab(trade_tab, "📊  Trade Status   ")

            logger.info("StatusPanel initialized")

        except Exception as e:
            logger.critical(f"[StatusPanel.__init__] Failed: {e}", exc_info=True)
            # Still create basic widget
            super().__init__(parent)
            self._safe_defaults_init()

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._lock = threading.RLock()
        self._last_state = {}
        self._refresh_enabled = True
        self._trade_active = False
        self._closing = False
        self._tabs = None
        self._no_trade_lbl = None
        self.cards = {}

    # ── Private helpers ───────────────────────────────────────────────────────

    def _safe_get(self, obj: Any, attr: str, default: Any = None) -> Any:
        """Safely get attribute from object with error handling"""
        try:
            # Rule 6: Input validation
            if obj is None:
                return default

            if not isinstance(attr, str):
                logger.warning(f"_safe_get called with non-string attr: {attr}")
                return default

            return getattr(obj, attr) if hasattr(obj, attr) else default

        except Exception as e:
            logger.debug(f"Failed to get attribute {attr}: {e}")
            return default

    def _fmt(self, value: Any, spec: str = ".2f") -> str:
        """Format value for display"""
        try:
            if value is None:
                return "—"

            try:
                return f"{float(value):{spec}}"
            except (ValueError, TypeError):
                return str(value)

        except Exception as e:
            logger.error(f"[_fmt] Failed: {e}", exc_info=True)
            return "—"

    def _pnl_color(self, pnl) -> str:
        """Get color for PnL value"""
        try:
            if pnl is None:
                return self.COLORS["neutral"]

            v = float(pnl)
            if v > 0:
                return self.COLORS["positive"]
            if v < 0:
                return self.COLORS["negative"]
            return self.COLORS["neutral"]

        except (TypeError, ValueError) as e:
            logger.debug(f"Failed to parse PnL {pnl}: {e}")
            return self.COLORS["neutral"]
        except Exception as e:
            logger.error(f"[_pnl_color] Failed: {e}", exc_info=True)
            return self.COLORS["neutral"]

    def _pos_color(self, pos) -> str:
        """Get color for position value"""
        try:
            if pos and str(pos).upper() in ("LONG", "SHORT", "CALL", "PUT"):
                return self.COLORS["positive"]
            return self.COLORS["neutral"]
        except Exception as e:
            logger.error(f"[_pos_color] Failed: {e}", exc_info=True)
            return self.COLORS["neutral"]

    def _trade_open(self, state) -> bool:
        """Check if trade is currently open"""
        try:
            if state is None:
                return False

            pos = self._safe_get(state, "current_position")
            if pos and str(pos).upper() not in ("NONE", "NO POSITION", "", "NONE"):
                return True

            symbol = self._safe_get(state, "current_trading_symbol")
            return bool(symbol)

        except Exception as e:
            logger.error(f"[_trade_open] Failed: {e}", exc_info=True)
            return False

    def _set_card(self, key: str, text: str, color: str):
        """Apply a card update only when the value actually changed."""
        try:
            # Rule 6: Input validation
            if key not in self.cards:
                logger.warning(f"Card {key} not found")
                return

            if text is None:
                text = "—"

            if not isinstance(color, str):
                color = self.COLORS["normal"]

            ck, cc = f"{key}_v", f"{key}_c"
            with self._lock:
                if text != self._last_state.get(ck) or color != self._last_state.get(cc):
                    self.cards[key].set_value(text, color)
                    self._last_state[ck] = text
                    self._last_state[cc] = color

        except Exception as e:
            logger.error(f"[_set_card] Failed for key {key}: {e}", exc_info=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, state, config):
        """
        Called on the main thread by QTimer every second.
        Reads TradeState and updates both tabs.
        """
        # Rule 6: Check if refresh should proceed
        if self._closing:
            return

        if state is None:
            logger.debug("refresh called with None state")
            return

        if not self._refresh_enabled:
            logger.debug("refresh disabled")
            return

        try:
            # Get values with thread safety
            with self._lock:
                pos = self._safe_get(state, "current_position")
                prev_pos = self._safe_get(state, "previous_position")
                symbol = self._safe_get(state, "current_trading_symbol")
                buy_price = self._safe_get(state, "current_buy_price")
                cur_price = self._safe_get(state, "current_price")
                tp = self._safe_get(state, "tp_point")
                sl = self._safe_get(state, "stop_loss")
                pnl = self._safe_get(state, "percentage_change")
                balance = self._safe_get(state, "account_balance")
                deriv = self._safe_get(state, "derivative_current_price")

            # ── Trade-active state: toggle dimming ─────────────────────────
            trade_active = self._trade_open(state)
            if trade_active != self._trade_active:
                self._trade_active = trade_active
                for key in self._TRADE_ONLY:
                    if key in self.cards:
                        self.cards[key].set_dimmed(not trade_active)
                # FIXED: Use explicit None check
                if self._no_trade_lbl is not None:
                    self._no_trade_lbl.setVisible(not trade_active)

            # ── Always-visible cards ───────────────────────────────────────
            self._set_card("position",
                           str(pos) if pos is not None else "None",
                           self._pos_color(pos))
            self._set_card("prev_position",
                           str(prev_pos) if prev_pos is not None else "None",
                           self.COLORS["normal"])
            self._set_card("balance", self._fmt(balance), self.COLORS["normal"])
            self._set_card("derivative", self._fmt(deriv), self.COLORS["accent"])

            # ── Trade-specific cards (only update when trade is active) ────
            if trade_active:
                self._set_card("symbol", str(symbol) if symbol else "—", self.COLORS["normal"])
                self._set_card("buy_price", self._fmt(buy_price), self.COLORS["normal"])
                self._set_card("current_price", self._fmt(cur_price), self.COLORS["normal"])
                self._set_card("target_price", self._fmt(tp), self.COLORS["positive"])
                self._set_card("stoploss_price", self._fmt(sl), self.COLORS["negative"])

                try:
                    if pnl is not None:
                        pnl_txt = f"{float(pnl):.2f}%"
                    else:
                        pnl_txt = "—"
                except (ValueError, TypeError):
                    pnl_txt = str(pnl) if pnl is not None else "—"

                self._set_card("pnl", pnl_txt, self._pnl_color(pnl))

            # Signal Data is refreshed by MultiChartWidget (chart tab 3)

        except Exception as e:
            logger.error(f"StatusPanel.refresh error: {e}", exc_info=True)

    def pause_refresh(self):
        """Pause automatic refresh"""
        try:
            self._refresh_enabled = False
            logger.debug("Refresh paused")
        except Exception as e:
            logger.error(f"[StatusPanel.pause_refresh] Failed: {e}", exc_info=True)

    def resume_refresh(self):
        """Resume automatic refresh"""
        try:
            self._refresh_enabled = True
            logger.debug("Refresh resumed")
        except Exception as e:
            logger.error(f"[StatusPanel.resume_refresh] Failed: {e}", exc_info=True)

    def clear_cache(self):
        """Clear internal state cache"""
        try:
            with self._lock:
                self._last_state.clear()
                logger.debug("Cache cleared")
        except Exception as e:
            logger.error(f"[StatusPanel.clear_cache] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown"""
        try:
            logger.info("[StatusPanel] Starting cleanup")
            self._closing = True
            self.pause_refresh()
            self.clear_cache()

            # Clear cards
            self.cards.clear()

            logger.info("[StatusPanel] Cleanup completed")

        except Exception as e:
            logger.error(f"[StatusPanel.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup"""
        try:
            self.cleanup()
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[StatusPanel.closeEvent] Failed: {e}", exc_info=True)
            super().closeEvent(event)