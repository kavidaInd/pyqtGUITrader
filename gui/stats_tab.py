# gui/stats_tab.py
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QGridLayout, QLabel, QTabWidget, QScrollArea)
from datetime import datetime
import pandas as pd


class StatsTab(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Create tab widget for organized categories
        tabs = QTabWidget()

        # 1. POSITION SUMMARY TAB (Most important for traders)
        tabs.addTab(self.create_position_tab(), "Position Summary")

        # 2. RISK METRICS TAB
        tabs.addTab(self.create_risk_tab(), "Risk Management")

        # 3. SIGNAL ENGINE TAB
        tabs.addTab(self.create_signal_tab(), "Signal Engine")

        # 4. PERFORMANCE METRICS TAB
        tabs.addTab(self.create_performance_tab(), "Performance")

        # 5. MARKET DATA TAB
        tabs.addTab(self.create_market_tab(), "Market Data")

        # 6. RAW STATE TAB (for debugging)
        tabs.addTab(self.create_debug_tab(), "Debug View")

        layout.addWidget(tabs)

    def create_position_tab(self):
        """Current position details - most critical for active trader"""
        widget = QWidget()
        layout = QGridLayout(widget)

        snap = self.state.get_position_snapshot()

        row = 0

        # Position Status
        layout.addWidget(QLabel("Current Position:"), row, 0)
        pos_label = QLabel(str(snap.get('current_position', 'None')))
        pos_label.setProperty("cssClass", "value")
        if snap.get('current_position') == 'CALL':
            pos_label.setProperty("cssClass", "positive")
        elif snap.get('current_position') == 'PUT':
            pos_label.setProperty("cssClass", "negative")
        layout.addWidget(pos_label, row, 1)
        row += 1

        # Trade Confirmed
        layout.addWidget(QLabel("Trade Confirmed:"), row, 0)
        conf_label = QLabel(str(snap.get('current_trade_confirmed', False)))
        conf_label.setProperty("cssClass", "value")
        layout.addWidget(conf_label, row, 1)
        row += 1

        # Order Pending
        layout.addWidget(QLabel("Order Pending:"), row, 0)
        pending_label = QLabel(str(snap.get('order_pending', False)))
        pending_label.setProperty("cssClass", "value")
        layout.addWidget(pending_label, row, 1)
        row += 1

        # Position Size
        layout.addWidget(QLabel("Positions Hold:"), row, 0)
        layout.addWidget(QLabel(str(snap.get('positions_hold', 0))), row, 1)
        row += 1

        # Entry Price
        layout.addWidget(QLabel("Entry Price:"), row, 0)
        entry = snap.get('current_buy_price')
        entry_label = QLabel(f"{entry:.2f}" if entry else "None")
        entry_label.setProperty("cssClass", "value")
        layout.addWidget(entry_label, row, 1)
        row += 1

        # Current Price
        layout.addWidget(QLabel("Current Price:"), row, 0)
        current = snap.get('current_price')
        current_label = QLabel(f"{current:.2f}" if current else "None")
        current_label.setProperty("cssClass", "value")
        layout.addWidget(current_label, row, 1)
        row += 1

        # Highest Price
        layout.addWidget(QLabel("Highest Price:"), row, 0)
        high = snap.get('highest_current_price')
        high_label = QLabel(f"{high:.2f}" if high else "None")
        high_label.setProperty("cssClass", "value")
        layout.addWidget(high_label, row, 1)
        row += 1

        # P&L
        layout.addWidget(QLabel("Current P&L:"), row, 0)
        pnl = snap.get('current_pnl')
        pnl_label = QLabel(f"₹{pnl:.2f}" if pnl else "None")
        pnl_label.setProperty("cssClass", "value")
        if pnl and pnl > 0:
            pnl_label.setProperty("cssClass", "positive")
        elif pnl and pnl < 0:
            pnl_label.setProperty("cssClass", "negative")
        layout.addWidget(pnl_label, row, 1)
        row += 1

        # Percentage Change
        layout.addWidget(QLabel("Change %:"), row, 0)
        pct = snap.get('percentage_change')
        pct_label = QLabel(f"{pct:.2f}%" if pct else "None")
        pct_label.setProperty("cssClass", "value")
        if pct and pct > 0:
            pct_label.setProperty("cssClass", "positive")
        elif pct and pct < 0:
            pct_label.setProperty("cssClass", "negative")
        layout.addWidget(pct_label, row, 1)
        row += 1

        # Exit Reason
        layout.addWidget(QLabel("Exit Reason:"), row, 0)
        reason = snap.get('reason_to_exit', 'None')
        layout.addWidget(QLabel(str(reason)), row, 1)
        row += 1

        return widget

    def create_risk_tab(self):
        """Stop loss, take profit, and risk parameters"""
        widget = QWidget()
        layout = QGridLayout(widget)

        snap = self.state.get_position_snapshot()

        row = 0

        # Stop Loss
        layout.addWidget(QLabel("Stop Loss:"), row, 0)
        sl = snap.get('stop_loss')
        sl_label = QLabel(f"{sl:.2f}" if sl else "None")
        sl_label.setProperty("cssClass", "value negative")
        layout.addWidget(sl_label, row, 1)
        row += 1

        # Index Stop Loss
        layout.addWidget(QLabel("Index Stop Loss:"), row, 0)
        idx_sl = snap.get('index_stop_loss')
        idx_sl_label = QLabel(f"{idx_sl:.2f}" if idx_sl else "None")
        idx_sl_label.setProperty("cssClass", "value")
        layout.addWidget(idx_sl_label, row, 1)
        row += 1

        # Take Profit
        layout.addWidget(QLabel("Take Profit:"), row, 0)
        tp = snap.get('tp_point')
        tp_label = QLabel(f"{tp:.2f}" if tp else "None")
        tp_label.setProperty("cssClass", "value positive")
        layout.addWidget(tp_label, row, 1)
        row += 1

        # Risk Percentages
        layout.addWidget(QLabel("TP %:"), row, 0)
        tp_pct = self.state.tp_percentage
        layout.addWidget(QLabel(f"{tp_pct:.1f}%"), row, 1)
        row += 1

        layout.addWidget(QLabel("SL %:"), row, 0)
        sl_pct = self.state.stoploss_percentage
        layout.addWidget(QLabel(f"{sl_pct:.1f}%"), row, 1)
        row += 1

        # Trailing Settings
        row += 1
        layout.addWidget(QLabel("Trailing First Profit:"), row, 0)
        layout.addWidget(QLabel(f"{self.state.trailing_first_profit:.1f}%"), row, 1)
        row += 1

        layout.addWidget(QLabel("Max Profit:"), row, 0)
        layout.addWidget(QLabel(f"{self.state.max_profit:.1f}%"), row, 1)
        row += 1

        layout.addWidget(QLabel("Profit Step:"), row, 0)
        layout.addWidget(QLabel(f"{self.state.profit_step:.1f}%"), row, 1)
        row += 1

        layout.addWidget(QLabel("Loss Step:"), row, 0)
        layout.addWidget(QLabel(f"{self.state.loss_step:.1f}%"), row, 1)
        row += 1

        return widget

    def create_signal_tab(self):
        """Dynamic signal engine output"""
        widget = QWidget()
        layout = QGridLayout(widget)

        snap = self.state.get_position_snapshot()
        signal_result = self.state.get_option_signal_snapshot()

        row = 0

        # Current Signal
        layout.addWidget(QLabel("Current Signal:"), row, 0)
        signal = snap.get('option_signal', 'WAIT')
        signal_label = QLabel(signal)
        signal_label.setProperty("cssClass", "value")

        # Color code signals
        if signal in ['BUY_CALL', 'BUY_PUT']:
            signal_label.setProperty("cssClass", "positive")
        elif signal in ['EXIT_CALL', 'EXIT_PUT']:
            signal_label.setProperty("cssClass", "negative")
        elif signal == 'HOLD':
            signal_label.setProperty("cssClass", "value")
        else:  # WAIT
            signal_label.setProperty("cssClass", "")

        layout.addWidget(signal_label, row, 1)
        row += 1

        # Signal Conflict
        layout.addWidget(QLabel("Signal Conflict:"), row, 0)
        conflict = snap.get('signal_conflict', False)
        conflict_label = QLabel(str(conflict))
        if conflict:
            conflict_label.setProperty("cssClass", "negative")
        layout.addWidget(conflict_label, row, 1)
        row += 1

        # Signals Active
        layout.addWidget(QLabel("Signals Active:"), row, 0)
        active = signal_result.get('available', False)
        layout.addWidget(QLabel(str(active)), row, 1)
        row += 1

        # Fired Signals
        row += 1
        layout.addWidget(QLabel("Fired Signals:"), row, 0)
        row += 1

        fired = signal_result.get('fired', {})
        for i, (sig, val) in enumerate(fired.items()):
            layout.addWidget(QLabel(f"  {sig}:"), row + i, 0)
            val_label = QLabel(str(val))
            if val:
                val_label.setProperty("cssClass", "positive")
            layout.addWidget(val_label, row + i, 1)

        return widget

    def create_performance_tab(self):
        """Performance metrics and account stats"""
        widget = QWidget()
        layout = QGridLayout(widget)

        snap = self.state.get_snapshot()

        row = 0

        # Account Balance
        layout.addWidget(QLabel("Account Balance:"), row, 0)
        balance = snap.get('account_balance', 0)
        layout.addWidget(QLabel(f"₹{balance:,.2f}"), row, 1)
        row += 1

        # Lot Size
        layout.addWidget(QLabel("Lot Size:"), row, 0)
        layout.addWidget(QLabel(str(snap.get('lot_size', 0))), row, 1)
        row += 1

        # Capital Reserve
        layout.addWidget(QLabel("Capital Reserve:"), row, 0)
        layout.addWidget(QLabel(f"₹{snap.get('capital_reserve', 0):,.2f}"), row, 1)
        row += 1

        # Max Options
        layout.addWidget(QLabel("Max Options:"), row, 0)
        layout.addWidget(QLabel(str(snap.get('max_num_of_option', 0))), row, 1)
        row += 1

        # Trade Timing
        row += 1
        start_time = snap.get('current_trade_started_time')
        if start_time:
            layout.addWidget(QLabel("Trade Started:"), row, 0)
            layout.addWidget(QLabel(start_time.strftime("%H:%M:%S")), row, 1)
            row += 1

            if snap.get('current_price'):
                duration = datetime.now() - start_time
                layout.addWidget(QLabel("Trade Duration:"), row, 0)
                layout.addWidget(QLabel(str(duration).split('.')[0]), row, 1)
                row += 1

        return widget

    def create_market_tab(self):
        """Market data and instrument info"""
        widget = QWidget()
        layout = QGridLayout(widget)

        snap = self.state.get_snapshot()

        row = 0

        # Instruments
        layout.addWidget(QLabel("Derivative:"), row, 0)
        layout.addWidget(QLabel(snap.get('derivative', 'N/A')), row, 1)
        row += 1

        layout.addWidget(QLabel("Call Option:"), row, 0)
        layout.addWidget(QLabel(str(snap.get('call_option', 'None'))), row, 1)
        row += 1

        layout.addWidget(QLabel("Put Option:"), row, 0)
        layout.addWidget(QLabel(str(snap.get('put_option', 'None'))), row, 1)
        row += 1

        # Prices
        row += 1
        layout.addWidget(QLabel("Derivative Price:"), row, 0)
        deriv = snap.get('derivative_current_price', 0)
        layout.addWidget(QLabel(f"{deriv:.2f}"), row, 1)
        row += 1

        layout.addWidget(QLabel("Call Close:"), row, 0)
        call = snap.get('call_current_close')
        layout.addWidget(QLabel(f"{call:.2f}" if call else "None"), row, 1)
        row += 1

        layout.addWidget(QLabel("Put Close:"), row, 0)
        put = snap.get('put_current_close')
        layout.addWidget(QLabel(f"{put:.2f}" if put else "None"), row, 1)
        row += 1

        # PCR
        row += 1
        layout.addWidget(QLabel("PCR:"), row, 0)
        layout.addWidget(QLabel(f"{snap.get('current_pcr', 0):.3f}"), row, 1)
        row += 1

        layout.addWidget(QLabel("PCR Vol:"), row, 0)
        pcr_vol = snap.get('current_pcr_vol')
        layout.addWidget(QLabel(f"{pcr_vol:.3f}" if pcr_vol else "None"), row, 1)
        row += 1

        # Market Trend
        row += 1
        layout.addWidget(QLabel("Market Trend:"), row, 0)
        trend = snap.get('market_trend')
        trend_label = QLabel(str(trend) if trend is not None else "None")
        if trend == 1:
            trend_label.setProperty("cssClass", "positive")
        elif trend == -1:
            trend_label.setProperty("cssClass", "negative")
        layout.addWidget(trend_label, row, 1)
        row += 1

        return widget

    def create_debug_tab(self):
        """Raw state snapshot for debugging"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        snap = self.state.get_snapshot()

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
                val_label.setProperty("cssClass", "value")
                h_layout.addWidget(val_label)

                scroll_layout.addLayout(h_layout)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        return widget

    def refresh(self):
        """Refresh all displayed stats"""
        # Force UI update by re-fetching all data
        # This will be called by the timer in StatsPopup
        pass