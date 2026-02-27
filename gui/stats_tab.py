"""
stats_tab.py
============
Live-updating statistics tabs for the Trading Dashboard.

BUG #3 FIX: Proper label storage and live refresh implementation.
FEATURE 1: Risk management display
FEATURE 3: Signal confidence display
FEATURE 5: Daily P&L tracking
FEATURE 6: Multi-timeframe filter display
"""

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QGridLayout, QLabel, QTabWidget, QScrollArea,
                             QProgressBar, QFrame)
from PyQt5.QtGui import QFont, QColor
from datetime import datetime
import pandas as pd
import logging

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

# ── Dark theme colors ─────────────────────────────────────────────────────
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
PURPLE = "#bc8cff"
GREY_OFF = "#484f58"


class StatsTab(QWidget):
    """
    Live-updating statistics tabs with stored label references.

    BUG #3 FIX: All labels are stored in self._labels dict for live updates.
    """

    # Signals for external updates
    data_refreshed = pyqtSignal(dict)  # Emits snapshot data

    def __init__(self, state, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.state = state
            self._labels = {}  # BUG #3 FIX: Store all label references
            self._progress_bars = {}  # Store progress bars
            self._last_data = {}  # Cache for change detection

            # Apply dark theme
            self.setStyleSheet(self._get_style_sheet())

            # Build UI
            self.init_ui()

            logger.info("StatsTab initialized with live refresh support")

        except Exception as e:
            logger.critical(f"[StatsTab.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self.state = state
            self._labels = {}
            self._progress_bars = {}
            self._last_data = {}

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.state = None
        self._labels = {}
        self._progress_bars = {}
        self._last_data = {}
        self._tabs = None

    def _get_style_sheet(self) -> str:
        """Get dark theme stylesheet"""
        return f"""
            QWidget {{
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
                min-width: 100px;
            }}
            QTabBar::tab:selected {{
                background: {BG_PANEL};
                color: {TEXT_MAIN};
                border-bottom: 2px solid {BLUE};
            }}
            QTabBar::tab:hover:!selected {{
                background: #2d333b;
            }}
            QGroupBox {{
                border: 1px solid {BORDER};
                border-radius: 4px;
                margin-top: 8px;
                font-weight: bold;
                color: {TEXT_MAIN};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 5px;
                color: {BLUE};
            }}
            QLabel {{
                color: {TEXT_DIM};
                font-size: 9pt;
            }}
            QLabel#value {{
                color: {TEXT_MAIN};
                font-weight: bold;
            }}
            QLabel#positive {{
                color: {GREEN};
                font-weight: bold;
            }}
            QLabel#negative {{
                color: {RED};
                font-weight: bold;
            }}
            QLabel#warning {{
                color: {YELLOW};
                font-weight: bold;
            }}
            QProgressBar {{
                border: 1px solid {BORDER};
                border-radius: 4px;
                background: {BG_PANEL};
                text-align: center;
                color: {TEXT_MAIN};
                font-size: 8pt;
                min-height: 12px;
            }}
            QProgressBar::chunk {{
                background: {BLUE};
                border-radius: 4px;
            }}
            QFrame#card {{
                background: {BG_PANEL};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 8px;
            }}
        """

    def init_ui(self):
        """Initialize the UI with all tabs"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Create tab widget for organized categories
        self._tabs = QTabWidget()

        # 1. POSITION SUMMARY TAB (Most important for traders)
        self._tabs.addTab(self.create_position_tab(), "📊 Position")

        # 2. RISK METRICS TAB (FEATURE 1)
        self._tabs.addTab(self.create_risk_tab(), "⚠️ Risk")

        # 3. SIGNAL ENGINE TAB (FEATURE 3)
        self._tabs.addTab(self.create_signal_tab(), "🎯 Signal")

        # 4. PERFORMANCE TAB (FEATURE 5)
        self._tabs.addTab(self.create_performance_tab(), "📈 Performance")

        # 5. MARKET DATA TAB
        self._tabs.addTab(self.create_market_tab(), "📉 Market")

        # 6. MTF FILTER TAB (FEATURE 6)
        self._tabs.addTab(self.create_mtf_tab(), "📊 MTF Filter")

        # 7. RAW STATE TAB (for debugging)
        self._tabs.addTab(self.create_debug_tab(), "🔧 Debug")

        layout.addWidget(self._tabs)

    def _add_label(self, key: str, label: QLabel):
        """Store label reference for live updates"""
        self._labels[key] = label

    def _add_progress(self, key: str, progress: QProgressBar):
        """Store progress bar reference for live updates"""
        self._progress_bars[key] = progress

    def create_position_tab(self):
        """
        Current position details - most critical for active trader.
        BUG #3 FIX: All labels stored in self._labels dict.
        """
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setSpacing(8)

        row = 0

        # Card 1: Position Status
        pos_group = QGroupBox("Position Status")
        pos_layout = QGridLayout(pos_group)

        # Position
        pos_layout.addWidget(QLabel("Current Position:"), 0, 0)
        pos_label = QLabel("None")
        pos_label.setObjectName("value")
        pos_layout.addWidget(pos_label, 0, 1)
        self._add_label("current_position", pos_label)

        # Trade Confirmed
        pos_layout.addWidget(QLabel("Trade Confirmed:"), 1, 0)
        conf_label = QLabel("False")
        conf_label.setObjectName("value")
        pos_layout.addWidget(conf_label, 1, 1)
        self._add_label("current_trade_confirmed", conf_label)

        # Order Pending
        pos_layout.addWidget(QLabel("Order Pending:"), 2, 0)
        pending_label = QLabel("False")
        pending_label.setObjectName("value")
        pos_layout.addWidget(pending_label, 2, 1)
        self._add_label("order_pending", pending_label)

        # Position Size
        pos_layout.addWidget(QLabel("Positions Hold:"), 3, 0)
        size_label = QLabel("0")
        size_label.setObjectName("value")
        pos_layout.addWidget(size_label, 3, 1)
        self._add_label("positions_hold", size_label)

        layout.addWidget(pos_group, row, 0, 1, 2)
        row += 1

        # Card 2: Price Levels
        price_group = QGroupBox("Price Levels")
        price_layout = QGridLayout(price_group)

        # Entry Price
        price_layout.addWidget(QLabel("Entry Price:"), 0, 0)
        entry_label = QLabel("None")
        entry_label.setObjectName("value")
        price_layout.addWidget(entry_label, 0, 1)
        self._add_label("current_buy_price", entry_label)

        # Current Price
        price_layout.addWidget(QLabel("Current Price:"), 1, 0)
        current_label = QLabel("None")
        current_label.setObjectName("value")
        price_layout.addWidget(current_label, 1, 1)
        self._add_label("current_price", current_label)

        # Highest Price
        price_layout.addWidget(QLabel("Highest Price:"), 2, 0)
        high_label = QLabel("None")
        high_label.setObjectName("value")
        price_layout.addWidget(high_label, 2, 1)
        self._add_label("highest_current_price", high_label)

        layout.addWidget(price_group, row, 0, 1, 2)
        row += 1

        # Card 3: P&L
        pnl_group = QGroupBox("Profit & Loss")
        pnl_layout = QGridLayout(pnl_group)

        # Current P&L
        pnl_layout.addWidget(QLabel("Current P&L:"), 0, 0)
        pnl_label = QLabel("₹0.00")
        pnl_label.setObjectName("value")
        pnl_layout.addWidget(pnl_label, 0, 1)
        self._add_label("current_pnl", pnl_label)

        # Percentage Change
        pnl_layout.addWidget(QLabel("Change %:"), 1, 0)
        pct_label = QLabel("0.00%")
        pct_label.setObjectName("value")
        pnl_layout.addWidget(pct_label, 1, 1)
        self._add_label("percentage_change", pct_label)

        # Exit Reason
        pnl_layout.addWidget(QLabel("Exit Reason:"), 2, 0)
        reason_label = QLabel("None")
        reason_label.setWordWrap(True)
        reason_label.setObjectName("value")
        pnl_layout.addWidget(reason_label, 2, 1)
        self._add_label("reason_to_exit", reason_label)

        layout.addWidget(pnl_group, row, 0, 1, 2)

        return widget

    def create_risk_tab(self):
        """
        FEATURE 1: Stop loss, take profit, and risk parameters.
        BUG #3 FIX: All labels stored in self._labels dict.
        """
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setSpacing(8)

        row = 0

        # Card 1: Stop Loss Levels
        sl_group = QGroupBox("Stop Loss Levels")
        sl_layout = QGridLayout(sl_group)

        # Stop Loss
        sl_layout.addWidget(QLabel("Stop Loss:"), 0, 0)
        sl_label = QLabel("None")
        sl_label.setObjectName("value negative")
        sl_layout.addWidget(sl_label, 0, 1)
        self._add_label("stop_loss", sl_label)

        # Index Stop Loss
        sl_layout.addWidget(QLabel("Index Stop Loss:"), 1, 0)
        idx_sl_label = QLabel("None")
        idx_sl_label.setObjectName("value")
        sl_layout.addWidget(idx_sl_label, 1, 1)
        self._add_label("index_stop_loss", idx_sl_label)

        # Stop Loss Percentage
        sl_layout.addWidget(QLabel("SL %:"), 2, 0)
        sl_pct_label = QLabel("0.0%")
        sl_pct_label.setObjectName("value negative")
        sl_layout.addWidget(sl_pct_label, 2, 1)
        self._add_label("stoploss_percentage", sl_pct_label)

        layout.addWidget(sl_group, row, 0, 1, 2)
        row += 1

        # Card 2: Take Profit Levels
        tp_group = QGroupBox("Take Profit Levels")
        tp_layout = QGridLayout(tp_group)

        # Take Profit
        tp_layout.addWidget(QLabel("Take Profit:"), 0, 0)
        tp_label = QLabel("None")
        tp_label.setObjectName("value positive")
        tp_layout.addWidget(tp_label, 0, 1)
        self._add_label("tp_point", tp_label)

        # TP Percentage
        tp_layout.addWidget(QLabel("TP %:"), 1, 0)
        tp_pct_label = QLabel("0.0%")
        tp_pct_label.setObjectName("value positive")
        tp_layout.addWidget(tp_pct_label, 1, 1)
        self._add_label("tp_percentage", tp_pct_label)

        layout.addWidget(tp_group, row, 0, 1, 2)
        row += 1

        # Card 3: Trailing Settings
        trail_group = QGroupBox("Trailing Settings")
        trail_layout = QGridLayout(trail_group)

        # Trailing First Profit
        trail_layout.addWidget(QLabel("First Profit:"), 0, 0)
        first_label = QLabel("0.0%")
        first_label.setObjectName("value")
        trail_layout.addWidget(first_label, 0, 1)
        self._add_label("trailing_first_profit", first_label)

        # Max Profit
        trail_layout.addWidget(QLabel("Max Profit:"), 1, 0)
        max_label = QLabel("0.0%")
        max_label.setObjectName("value")
        trail_layout.addWidget(max_label, 1, 1)
        self._add_label("max_profit", max_label)

        # Profit Step
        trail_layout.addWidget(QLabel("Profit Step:"), 2, 0)
        step_label = QLabel("0.0%")
        step_label.setObjectName("value")
        trail_layout.addWidget(step_label, 2, 1)
        self._add_label("profit_step", step_label)

        # Loss Step
        trail_layout.addWidget(QLabel("Loss Step:"), 3, 0)
        loss_label = QLabel("0.0%")
        loss_label.setObjectName("value")
        trail_layout.addWidget(loss_label, 3, 1)
        self._add_label("loss_step", loss_label)

        # Profit Type
        trail_layout.addWidget(QLabel("Profit Type:"), 4, 0)
        type_label = QLabel("STOP")
        type_label.setObjectName("value")
        trail_layout.addWidget(type_label, 4, 1)
        self._add_label("take_profit_type", type_label)

        layout.addWidget(trail_group, row, 0, 1, 2)

        return widget

    def create_signal_tab(self):
        """
        FEATURE 3: Dynamic signal engine output with confidence.
        BUG #3 FIX: All labels stored in self._labels dict.
        """
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setSpacing(8)

        row = 0

        # Card 1: Current Signal
        signal_group = QGroupBox("Current Signal")
        signal_layout = QGridLayout(signal_group)

        # Signal Value
        signal_layout.addWidget(QLabel("Signal:"), 0, 0)
        signal_label = QLabel("WAIT")
        signal_label.setObjectName("value")
        signal_layout.addWidget(signal_label, 0, 1)
        self._add_label("option_signal", signal_label)

        # Signal Conflict
        signal_layout.addWidget(QLabel("Conflict:"), 1, 0)
        conflict_label = QLabel("False")
        conflict_label.setObjectName("value")
        signal_layout.addWidget(conflict_label, 1, 1)
        self._add_label("signal_conflict", conflict_label)

        # Signals Active
        signal_layout.addWidget(QLabel("Active:"), 2, 0)
        active_label = QLabel("False")
        active_label.setObjectName("value")
        signal_layout.addWidget(active_label, 2, 1)
        self._add_label("dynamic_signals_active", active_label)

        # Min Confidence
        signal_layout.addWidget(QLabel("Min Confidence:"), 3, 0)
        conf_label = QLabel("0.60")
        conf_label.setObjectName("value")
        signal_layout.addWidget(conf_label, 3, 1)
        self._add_label("min_confidence", conf_label)

        layout.addWidget(signal_group, row, 0, 1, 2)
        row += 1

        # Card 2: Fired Signals
        fired_group = QGroupBox("Fired Signals")
        fired_layout = QGridLayout(fired_group)

        signal_groups = ['BUY_CALL', 'BUY_PUT', 'EXIT_CALL', 'EXIT_PUT', 'HOLD']

        for i, sig in enumerate(signal_groups):
            fired_layout.addWidget(QLabel(f"{sig}:"), i, 0)
            label = QLabel("False")
            label.setObjectName("value")
            fired_layout.addWidget(label, i, 1)
            self._add_label(f"fired_{sig}", label)

        layout.addWidget(fired_group, row, 0, 1, 2)
        row += 1

        # Card 3: Signal Explanation
        exp_group = QGroupBox("Explanation")
        exp_layout = QVBoxLayout(exp_group)
        exp_label = QLabel("No signal evaluation yet")
        exp_label.setWordWrap(True)
        exp_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 8pt;")
        exp_layout.addWidget(exp_label)
        self._add_label("signal_explanation", exp_label)
        layout.addWidget(exp_group, row, 0, 1, 2)

        return widget

    def create_performance_tab(self):
        """
        FEATURE 5: Performance metrics and account stats.
        BUG #3 FIX: All labels stored in self._labels dict.
        """
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setSpacing(8)

        row = 0

        # Card 1: Account Info
        account_group = QGroupBox("Account Info")
        account_layout = QGridLayout(account_group)

        # Balance
        account_layout.addWidget(QLabel("Balance:"), 0, 0)
        balance_label = QLabel("₹0.00")
        balance_label.setObjectName("value")
        account_layout.addWidget(balance_label, 0, 1)
        self._add_label("account_balance", balance_label)

        # Lot Size
        account_layout.addWidget(QLabel("Lot Size:"), 1, 0)
        lot_label = QLabel("0")
        lot_label.setObjectName("value")
        account_layout.addWidget(lot_label, 1, 1)
        self._add_label("lot_size", lot_label)

        # Capital Reserve
        account_layout.addWidget(QLabel("Reserve:"), 2, 0)
        reserve_label = QLabel("₹0.00")
        reserve_label.setObjectName("value")
        account_layout.addWidget(reserve_label, 2, 1)
        self._add_label("capital_reserve", reserve_label)

        # Max Options
        account_layout.addWidget(QLabel("Max Options:"), 3, 0)
        max_label = QLabel("0")
        max_label.setObjectName("value")
        account_layout.addWidget(max_label, 3, 1)
        self._add_label("max_num_of_option", max_label)

        layout.addWidget(account_group, row, 0, 1, 2)
        row += 1

        # Card 3: Trade Timing
        timing_group = QGroupBox("Trade Timing")
        timing_layout = QGridLayout(timing_group)

        # Start Time
        timing_layout.addWidget(QLabel("Started:"), 0, 0)
        start_label = QLabel("None")
        start_label.setObjectName("value")
        timing_layout.addWidget(start_label, 0, 1)
        self._add_label("current_trade_started_time", start_label)

        # Duration
        timing_layout.addWidget(QLabel("Duration:"), 1, 0)
        duration_label = QLabel("0s")
        duration_label.setObjectName("value")
        timing_layout.addWidget(duration_label, 1, 1)
        self._add_label("trade_duration", duration_label)

        layout.addWidget(timing_group, row, 0, 1, 2)

        return widget

    def create_market_tab(self):
        """
        Market data and instrument info.
        BUG #3 FIX: All labels stored in self._labels dict.
        """
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setSpacing(8)

        row = 0

        # Card 1: Instruments
        inst_group = QGroupBox("Instruments")
        inst_layout = QGridLayout(inst_group)

        # Derivative
        inst_layout.addWidget(QLabel("Derivative:"), 0, 0)
        deriv_label = QLabel("N/A")
        deriv_label.setObjectName("value")
        inst_layout.addWidget(deriv_label, 0, 1)
        self._add_label("derivative", deriv_label)

        # Call Option
        inst_layout.addWidget(QLabel("Call Option:"), 1, 0)
        call_label = QLabel("None")
        call_label.setObjectName("value")
        inst_layout.addWidget(call_label, 1, 1)
        self._add_label("call_option", call_label)

        # Put Option
        inst_layout.addWidget(QLabel("Put Option:"), 2, 0)
        put_label = QLabel("None")
        put_label.setObjectName("value")
        inst_layout.addWidget(put_label, 2, 1)
        self._add_label("put_option", put_label)

        # Expiry
        inst_layout.addWidget(QLabel("Expiry:"), 3, 0)
        expiry_label = QLabel("0")
        expiry_label.setObjectName("value")
        inst_layout.addWidget(expiry_label, 3, 1)
        self._add_label("expiry", expiry_label)

        layout.addWidget(inst_group, row, 0, 1, 2)
        row += 1

        # Card 2: Prices
        price_group = QGroupBox("Prices")
        price_layout = QGridLayout(price_group)

        # Derivative Price
        price_layout.addWidget(QLabel("Derivative Price:"), 0, 0)
        deriv_price_label = QLabel("0.00")
        deriv_price_label.setObjectName("value")
        price_layout.addWidget(deriv_price_label, 0, 1)
        self._add_label("derivative_current_price", deriv_price_label)

        # Call Close
        price_layout.addWidget(QLabel("Call Close:"), 1, 0)
        call_close_label = QLabel("None")
        call_close_label.setObjectName("value")
        price_layout.addWidget(call_close_label, 1, 1)
        self._add_label("call_current_close", call_close_label)

        # Put Close
        price_layout.addWidget(QLabel("Put Close:"), 2, 0)
        put_close_label = QLabel("None")
        put_close_label.setObjectName("value")
        price_layout.addWidget(put_close_label, 2, 1)
        self._add_label("put_current_close", put_close_label)

        layout.addWidget(price_group, row, 0, 1, 2)
        row += 1

        # Card 3: Market Indicators
        ind_group = QGroupBox("Market Indicators")
        ind_layout = QGridLayout(ind_group)

        # PCR
        ind_layout.addWidget(QLabel("PCR:"), 0, 0)
        pcr_label = QLabel("0.000")
        pcr_label.setObjectName("value")
        ind_layout.addWidget(pcr_label, 0, 1)
        self._add_label("current_pcr", pcr_label)

        # PCR Vol
        ind_layout.addWidget(QLabel("PCR Vol:"), 1, 0)
        pcr_vol_label = QLabel("None")
        pcr_vol_label.setObjectName("value")
        ind_layout.addWidget(pcr_vol_label, 1, 1)
        self._add_label("current_pcr_vol", pcr_vol_label)

        # Market Trend
        ind_layout.addWidget(QLabel("Market Trend:"), 2, 0)
        trend_label = QLabel("None")
        trend_label.setObjectName("value")
        ind_layout.addWidget(trend_label, 2, 1)
        self._add_label("market_trend", trend_label)

        layout.addWidget(ind_group, row, 0, 1, 2)

        return widget

    def create_mtf_tab(self):
        """
        FEATURE 6: Multi-timeframe filter display.
        BUG #3 FIX: All labels stored in self._labels dict.
        """
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setSpacing(8)

        row = 0

        # Card 1: MTF Status
        status_group = QGroupBox("MTF Filter Status")
        status_layout = QGridLayout(status_group)

        # Enabled
        status_layout.addWidget(QLabel("Enabled:"), 0, 0)
        enabled_label = QLabel("No")
        enabled_label.setObjectName("value")
        status_layout.addWidget(enabled_label, 0, 1)
        self._add_label("mtf_enabled", enabled_label)

        # Allowed
        status_layout.addWidget(QLabel("Allowed:"), 1, 0)
        allowed_label = QLabel("Yes")
        allowed_label.setObjectName("value")
        status_layout.addWidget(allowed_label, 1, 1)
        self._add_label("mtf_allowed", allowed_label)

        layout.addWidget(status_group, row, 0, 1, 2)
        row += 1

        # Card 2: Timeframe Directions
        tf_group = QGroupBox("Timeframe Directions")
        tf_layout = QGridLayout(tf_group)

        timeframes = ['1m', '5m', '15m']
        tf_keys = ['1', '5', '15']

        for i, (tf, key) in enumerate(zip(timeframes, tf_keys)):
            tf_layout.addWidget(QLabel(f"{tf}:"), i, 0)
            label = QLabel("NEUTRAL")
            label.setObjectName("value")
            tf_layout.addWidget(label, i, 1)
            self._add_label(f"mtf_{key}", label)

        # Agreement
        tf_layout.addWidget(QLabel("Agreement:"), 3, 0)
        agree_label = QLabel("0/3")
        agree_label.setObjectName("value")
        tf_layout.addWidget(agree_label, 3, 1)
        self._add_label("mtf_agreement", agree_label)

        layout.addWidget(tf_group, row, 0, 1, 2)
        row += 1

        # Card 3: Last Decision
        decision_group = QGroupBox("Last Decision")
        decision_layout = QVBoxLayout(decision_group)

        summary_label = QLabel("No MTF evaluation yet")
        summary_label.setWordWrap(True)
        summary_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 8pt;")
        decision_layout.addWidget(summary_label)
        self._add_label("mtf_summary", summary_label)

        layout.addWidget(decision_group, row, 0, 1, 2)

        return widget

    def create_debug_tab(self):
        """
        Raw state snapshot for debugging.
        BUG #3 FIX: Dynamically created, not stored in _labels.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        snap = self.state.get_snapshot() if self.state else {}

        # Display all key-value pairs
        for key, value in sorted(snap.items()):
            if value is not None and not key.endswith('_df'):  # Skip DataFrame placeholders
                h_layout = QHBoxLayout()
                h_layout.addWidget(QLabel(f"{key}:"))

                value_str = str(value)
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."

                val_label = QLabel(value_str)
                val_label.setWordWrap(True)
                val_label.setObjectName("value")
                h_layout.addWidget(val_label)

                scroll_layout.addLayout(h_layout)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        return widget

    # ==================================================================
    # BUG #3 FIX: Live refresh implementation
    # ==================================================================

    def refresh(self):
        """
        BUG #3 FIX: Refresh all displayed stats with live data.
        Called by timer in parent widget.
        """
        try:
            if self.state is None:
                logger.debug("refresh called with None state")
                return

            # Get latest snapshot
            snap = self.state.get_snapshot()
            pos_snap = self.state.get_position_snapshot()
            signal_snap = self.state.get_option_signal_snapshot()

            # Update all labels with new values
            self._update_position_labels(pos_snap)
            self._update_risk_labels(snap, pos_snap)
            self._update_signal_labels(signal_snap, pos_snap)
            self._update_performance_labels(snap, pos_snap)
            self._update_market_labels(snap)
            self._update_mtf_labels(snap)

            # Emit signal with snapshot data
            self.data_refreshed.emit(snap)

        except Exception as e:
            logger.error(f"[StatsTab.refresh] Failed: {e}", exc_info=True)

    def _update_position_labels(self, snap: dict):
        """Update position tab labels"""
        try:
            # Position Status
            pos = snap.get('current_position', 'None')
            self._update_label("current_position", str(pos) if pos else "None")

            # Trade Confirmed
            confirmed = snap.get('current_trade_confirmed', False)
            self._update_label("current_trade_confirmed", str(confirmed))

            # Order Pending
            pending = snap.get('order_pending', False)
            self._update_label("order_pending", str(pending))

            # Positions Hold
            self._update_label("positions_hold", str(snap.get('positions_hold', 0)))

            # Entry Price
            entry = snap.get('current_buy_price')
            self._update_label("current_buy_price", f"{entry:.2f}" if entry else "None")

            # Current Price
            current = snap.get('current_price')
            self._update_label("current_price", f"{current:.2f}" if current else "None")

            # Highest Price
            high = snap.get('highest_current_price')
            self._update_label("highest_current_price", f"{high:.2f}" if high else "None")

            # P&L
            pnl = snap.get('current_pnl')
            if pnl is not None:
                pnl_str = f"₹{pnl:.2f}"
                pnl_color = "positive" if pnl > 0 else "negative" if pnl < 0 else "value"
                self._update_label("current_pnl", pnl_str, pnl_color)
            else:
                self._update_label("current_pnl", "None")

            # Percentage Change
            pct = snap.get('percentage_change')
            if pct is not None:
                pct_str = f"{pct:.2f}%"
                pct_color = "positive" if pct > 0 else "negative" if pct < 0 else "value"
                self._update_label("percentage_change", pct_str, pct_color)
            else:
                self._update_label("percentage_change", "None")

            # Exit Reason
            reason = snap.get('reason_to_exit', 'None')
            self._update_label("reason_to_exit", str(reason))

        except Exception as e:
            logger.error(f"[_update_position_labels] Failed: {e}", exc_info=True)

    def _update_risk_labels(self, snap: dict, pos_snap: dict):
        """Update risk tab labels"""
        try:
            # Stop Loss
            sl = pos_snap.get('stop_loss')
            self._update_label("stop_loss", f"{sl:.2f}" if sl else "None", "negative")

            # Index Stop Loss
            idx_sl = pos_snap.get('index_stop_loss')
            self._update_label("index_stop_loss", f"{idx_sl:.2f}" if idx_sl else "None")

            # Stop Loss Percentage
            sl_pct = snap.get('stoploss_percentage', 0)
            self._update_label("stoploss_percentage", f"{sl_pct:.1f}%", "negative")

            # Take Profit
            tp = pos_snap.get('tp_point')
            self._update_label("tp_point", f"{tp:.2f}" if tp else "None", "positive")

            # TP Percentage
            tp_pct = snap.get('tp_percentage', 0)
            self._update_label("tp_percentage", f"{tp_pct:.1f}%", "positive")

            # Trailing Settings
            self._update_label("trailing_first_profit", f"{snap.get('trailing_first_profit', 0):.1f}%")
            self._update_label("max_profit", f"{snap.get('max_profit', 0):.1f}%")
            self._update_label("profit_step", f"{snap.get('profit_step', 0):.1f}%")
            self._update_label("loss_step", f"{snap.get('loss_step', 0):.1f}%")
            self._update_label("take_profit_type", str(snap.get('take_profit_type', 'STOP')))

        except Exception as e:
            logger.error(f"[_update_risk_labels] Failed: {e}", exc_info=True)

    def _update_signal_labels(self, signal_snap: dict, pos_snap: dict):
        """Update signal tab labels"""
        try:
            # Signal Value
            signal = pos_snap.get('option_signal', 'WAIT')
            signal_color = "positive" if signal in ['BUY_CALL', 'BUY_PUT'] else \
                "negative" if signal in ['EXIT_CALL', 'EXIT_PUT'] else "value"
            self._update_label("option_signal", signal, signal_color)

            # Signal Conflict
            conflict = pos_snap.get('signal_conflict', False)
            self._update_label("signal_conflict", str(conflict), "negative" if conflict else "value")

            # Signals Active
            active = signal_snap.get('available', False)
            self._update_label("dynamic_signals_active", str(active), "positive" if active else "value")

            # Min Confidence
            min_conf = signal_snap.get('threshold', 0.6)
            self._update_label("min_confidence", f"{min_conf:.2f}")

            # Fired Signals
            fired = signal_snap.get('fired', {})
            for sig in ['BUY_CALL', 'BUY_PUT', 'EXIT_CALL', 'EXIT_PUT', 'HOLD']:
                is_fired = fired.get(sig, False)
                self._update_label(f"fired_{sig}", str(is_fired), "positive" if is_fired else "value")

            # Explanation
            explanation = signal_snap.get('explanation', 'No signal evaluation yet')
            self._update_label("signal_explanation", explanation)

        except Exception as e:
            logger.error(f"[_update_signal_labels] Failed: {e}", exc_info=True)

    def _update_performance_labels(self, snap: dict, pos_snap: dict):
        """Update performance tab labels"""
        try:
            # Account Info
            balance = snap.get('account_balance', 0)
            self._update_label("account_balance", f"₹{balance:,.2f}")

            lot_size = snap.get('lot_size', 0)
            self._update_label("lot_size", str(lot_size))

            reserve = snap.get('capital_reserve', 0)
            self._update_label("capital_reserve", f"₹{reserve:,.2f}")

            max_options = snap.get('max_num_of_option', 0)
            self._update_label("max_num_of_option", str(max_options))

            # Trade Timing
            start_time = snap.get('current_trade_started_time')
            if start_time:
                self._update_label("current_trade_started_time", start_time.strftime("%H:%M:%S"))

                # Calculate duration
                if snap.get('current_price'):
                    duration = datetime.now() - start_time
                    hours = duration.seconds // 3600
                    minutes = (duration.seconds % 3600) // 60
                    seconds = duration.seconds % 60
                    duration_str = f"{hours}h {minutes}m {seconds}s"
                    self._update_label("trade_duration", duration_str)
            else:
                self._update_label("current_trade_started_time", "None")
                self._update_label("trade_duration", "0s")

        except Exception as e:
            logger.error(f"[_update_performance_labels] Failed: {e}", exc_info=True)

    def _update_market_labels(self, snap: dict):
        """Update market tab labels"""
        try:
            # Instruments
            self._update_label("derivative", str(snap.get('derivative', 'N/A')))
            self._update_label("call_option", str(snap.get('call_option', 'None')))
            self._update_label("put_option", str(snap.get('put_option', 'None')))
            self._update_label("expiry", str(snap.get('expiry', 0)))

            # Prices
            deriv = snap.get('derivative_current_price', 0)
            self._update_label("derivative_current_price", f"{deriv:.2f}")

            call = snap.get('call_current_close')
            self._update_label("call_current_close", f"{call:.2f}" if call else "None")

            put = snap.get('put_current_close')
            self._update_label("put_current_close", f"{put:.2f}" if put else "None")

            # Market Indicators
            pcr = snap.get('current_pcr', 0)
            self._update_label("current_pcr", f"{pcr:.3f}")

            pcr_vol = snap.get('current_pcr_vol')
            self._update_label("current_pcr_vol", f"{pcr_vol:.3f}" if pcr_vol else "None")

            trend = snap.get('market_trend')
            if trend == 1:
                self._update_label("market_trend", "BULLISH", "positive")
            elif trend == -1:
                self._update_label("market_trend", "BEARISH", "negative")
            else:
                self._update_label("market_trend", "NEUTRAL")

        except Exception as e:
            logger.error(f"[_update_market_labels] Failed: {e}", exc_info=True)

    def _update_mtf_labels(self, snap: dict):
        """Update MTF filter tab labels"""
        try:
            # Enabled status
            mtf_enabled = snap.get('use_mtf_filter', False)
            self._update_label("mtf_enabled", "Yes" if mtf_enabled else "No",
                               "positive" if mtf_enabled else "value")

            # Allowed status
            mtf_allowed = snap.get('mtf_allowed', True)
            self._update_label("mtf_allowed", "Yes" if mtf_allowed else "No",
                               "positive" if mtf_allowed else "negative")

            # Timeframe directions
            mtf_results = snap.get('mtf_results', {})

            for tf, key in [('1m', '1'), ('5m', '5'), ('15m', '15')]:
                direction = mtf_results.get(key, 'NEUTRAL')
                color = "positive" if direction == 'BULLISH' else \
                    "negative" if direction == 'BEARISH' else "value"
                self._update_label(f"mtf_{key}", direction, color)

            # Agreement
            target = 'BULLISH' if snap.get('option_signal', '') == 'BUY_CALL' else 'BEARISH'
            matches = sum(1 for d in mtf_results.values() if d == target)
            self._update_label("mtf_agreement", f"{matches}/3")

            # Summary
            summary = snap.get('last_mtf_summary', 'No MTF evaluation yet')
            self._update_label("mtf_summary", summary)

        except Exception as e:
            logger.error(f"[_update_mtf_labels] Failed: {e}", exc_info=True)

    def _update_label(self, key: str, value: str, css_class: str = "value"):
        """
        Helper to update a label with error handling.

        Args:
            key: Label key in self._labels
            value: New text value
            css_class: CSS class to apply (value, positive, negative)
        """
        try:
            if key in self._labels and self._labels[key] is not None:
                label = self._labels[key]
                label.setText(value)
                label.setProperty("cssClass", css_class)
                # Force style refresh
                label.style().unpolish(label)
                label.style().polish(label)
        except Exception as e:
            logger.debug(f"Failed to update label {key}: {e}")

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown"""
        try:
            logger.info("[StatsTab] Starting cleanup")
            self._labels.clear()
            self._progress_bars.clear()
            self._last_data.clear()
            logger.info("[StatsTab] Cleanup completed")
        except Exception as e:
            logger.error(f"[StatsTab.cleanup] Error: {e}", exc_info=True)