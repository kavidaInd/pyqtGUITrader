# PYQT: Replaces Tkinter StatsTab - preserves class name
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTableWidget,
                              QTableWidgetItem, QHeaderView, QLabel, QApplication)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
import pandas as pd
import numpy as np


class StatsTab(QWidget):
    """
    # PYQT: Replaces the Tkinter StatsTab. Renders all TradeState fields
    in a QTableWidget. Refresh is driven by QTimer from the parent window.
    Class name preserved so any existing references still work.
    """

    STATS_KEYS = [
        ("current_position", "Current Position"),
        ("previous_position", "Previous Position"),
        ("current_trading_symbol", "Trading Symbol"),
        ("current_order_id", "Order ID"),
        ("order_pending", "Order Pending"),
        ("positions_hold", "Positions Hold"),
        ("reason_to_exit", "Exit Reason"),
        ("current_buy_price", "Buy Price"),
        ("current_price", "Current Price"),
        ("highest_current_price", "Highest Price"),
        ("derivative_current_price", "Derivative Price"),
        ("current_index_data", "Index Data"),
        ("current_call_data", "Call Data"),
        ("current_put_data", "Put Data"),
        ("percentage_change", "P&L %"),
        ("current_pnl", "Current P&L"),
        ("account_balance", "Account Balance"),
        ("max_profit", "Max Profit"),
        ("stop_loss", "Stop Loss"),
        ("tp_point", "Take Profit"),
        ("tp_percentage", "TP %"),
        ("stoploss_percentage", "SL %"),
        ("original_profit_per", "Original Profit %"),
        ("original_stoploss_per", "Original SL %"),
        ("trailing_first_profit", "Trailing First Profit"),
        ("take_profit_type", "TP Type"),
        ("profit_step", "Profit Step"),
        ("loss_step", "Loss Step"),
        ("interval", "Interval"),
        ("cancel_after", "Cancel After"),
        ("lot_size", "Lot Size"),
        ("expiry", "Expiry"),
        ("max_num_of_option", "Max Options"),
        ("lower_percentage", "Lower %"),
        ("option_trend", "Option Trend"),
        ("derivative_trend", "Derivative Trend"),
        ("market_trend", "Market Trend"),
        ("trend", "Trend"),
        ("supertrend_reset", "Supertrend Reset"),
        ("b_band", "Bollinger Bands"),
        ("call_lookback", "Call Lookback"),
        ("put_lookback", "Put Lookback"),
        ("original_call_lookback", "Original Call Lookback"),
        ("original_put_lookback", "Original Put Lookback"),
        ("call_option", "Call Option"),
        ("put_option", "Put Option"),
        ("call_current_close", "Call Close"),
        ("put_current_close", "Put Close"),
        ("calculated_pcr", "Calculated PCR"),
        ("current_pcr", "Current PCR"),
        ("current_pcr_vol", "PCR Volume"),
        ("current_trade_started_time", "Trade Start Time"),
        ("current_trade_confirmed", "Trade Confirmed"),
        ("last_index_updated", "Last Index Update"),
        ("option_price_update", "Option Price Update"),
        ("derivative_history_df", "Derivative History"),
        ("option_history_df", "Option History"),
        ("orders", "Orders"),
        ("all_symbols", "All Symbols"),
    ]

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QLabel("📊 All Calculated State Stats")
        header.setFont(QFont("Segoe UI", 13, QFont.Bold))
        header.setStyleSheet("color: #e6edf3;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        sub = QLabel("Auto-refreshes every second  •  Double-click a cell to copy value")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet("color: #8b949e;")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)

        # PYQT: QTableWidget for two-column stat display
        self.table = QTableWidget(len(self.STATS_KEYS), 2)
        self.table.setHorizontalHeaderLabels(["Stat", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background: #0d1117;
                alternate-background-color: #161b22;
                color: #e6edf3;
                gridline-color: #30363d;
                border: 1px solid #30363d;
                font-family: Consolas, monospace;
                font-size: 9pt;
            }
            QHeaderView::section {
                background: #161b22;
                color: #8b949e;
                border: 1px solid #30363d;
                padding: 4px;
                font-weight: bold;
            }
        """)

        # Pre-populate stat name column (never changes)
        for i, (_, display_name) in enumerate(self.STATS_KEYS):
            item = QTableWidgetItem(display_name)
            item.setForeground(QColor("#8b949e"))
            self.table.setItem(i, 0, item)
            self.table.setItem(i, 1, QTableWidgetItem("—"))

        # PYQT: Copy to clipboard on cell double-click
        self.table.cellDoubleClicked.connect(self._copy_to_clipboard)

        layout.addWidget(self.table)

    def refresh(self):
        """
        # PYQT: Called on main thread by QTimer. Reads state and updates table values.
        """
        if self.state is None:
            return

        def fmt(val):
            if val is None:
                return "—"
            if hasattr(val, "as_dict"):
                try:
                    d = val.as_dict()
                    return (f"O:{d.get('open','-')}  H:{d.get('high','-')}  "
                            f"L:{d.get('low','-')}  C:{d.get('close','-')}  Vol:{d.get('volume','-')}")
                except Exception:
                    return str(val)
            if isinstance(val, pd.DataFrame):
                return f"DataFrame {val.shape}  cols={list(val.columns[:4])}"
            if isinstance(val, np.ndarray):
                return f"ndarray shape={val.shape}"
            if isinstance(val, dict):
                s = str(val)
                return s[:120] + "..." if len(s) > 120 else s
            if isinstance(val, list):
                if len(val) > 5:
                    return f"List[{len(val)}]: {str(val[:4])[:-1]}, ..."
                return str(val)
            if isinstance(val, float):
                return f"{val:.4f}"
            return str(val)

        for i, (key, _) in enumerate(self.STATS_KEYS):
            try:
                val = getattr(self.state, key, "—")
                self.table.item(i, 1).setText(fmt(val))
            except Exception as e:
                self.table.item(i, 1).setText(f"<Error: {str(e)[:40]}>")

    def _copy_to_clipboard(self, row, col):
        """# PYQT: Copy full raw value to system clipboard on double-click"""
        try:
            key = self.STATS_KEYS[row][0]
            val = getattr(self.state, key, "")
            QApplication.clipboard().setText(str(val))
        except Exception:
            pass