# PYQT: Replaces Tkinter StatsTab - preserves class name
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTableWidget,
                             QTableWidgetItem, QHeaderView, QLabel, QApplication)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor
import pandas as pd
import numpy as np
import threading
from typing import Any, Optional
import traceback


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

    # Cache for formatted values to avoid recomputing
    _value_cache = {}
    _cache_size_limit = 1000

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._refresh_lock = threading.Lock()
        self._last_values = {}  # Store last values to detect changes
        self._updating = False

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

    def _safe_get_attr(self, obj: Any, key: str, default: Any = "—") -> Any:
        """Safely get attribute from object with error handling"""
        try:
            if hasattr(obj, key):
                return getattr(obj, key)
            return default
        except Exception as e:
            return f"<Error: {type(e).__name__}>"

    def _format_value(self, val: Any, max_length: int = 120) -> str:
        """Format a value for display with caching for complex objects"""
        if val is None:
            return "—"

        # Use cache for complex objects to avoid repeated formatting
        if hasattr(val, '__hash__') and val is not None:
            try:
                cache_key = (id(type(val)), hash(str(val)) % self._cache_size_limit)
                if cache_key in self._value_cache:
                    return self._value_cache[cache_key]
            except (TypeError, ValueError):
                cache_key = None
        else:
            cache_key = None

        try:
            # Handle different types efficiently
            if hasattr(val, "as_dict"):
                try:
                    d = val.as_dict()
                    formatted = (f"O:{d.get('open', '-')}  H:{d.get('high', '-')}  "
                                 f"L:{d.get('low', '-')}  C:{d.get('close', '-')}  Vol:{d.get('volume', '-')}")
                except Exception:
                    formatted = str(val)

            elif isinstance(val, pd.DataFrame):
                # More efficient DataFrame display
                if val.empty:
                    formatted = "Empty DataFrame"
                else:
                    cols = list(val.columns[:4])
                    formatted = f"DataFrame {val.shape}  cols={cols}"
                    if len(val) > 0:
                        # Show first row as sample
                        try:
                            first_row = val.iloc[0].to_dict()
                            sample = {k: v for k, v in list(first_row.items())[:3]}
                            formatted += f"  sample: {sample}"
                        except:
                            pass

            elif isinstance(val, pd.Series):
                formatted = f"Series {val.shape}  {val.name}"

            elif isinstance(val, np.ndarray):
                formatted = f"ndarray shape={val.shape}  dtype={val.dtype}"
                if val.size > 0 and val.size < 10:
                    formatted += f"  {val}"

            elif isinstance(val, dict):
                s = str(val)
                formatted = s[:max_length] + "..." if len(s) > max_length else s

            elif isinstance(val, (list, tuple)):
                if len(val) > 5:
                    formatted = f"{type(val).__name__}[{len(val)}]: {str(val[:4])[:-1]}, ..."
                else:
                    formatted = str(val)

            elif isinstance(val, float):
                formatted = f"{val:.4f}"

            elif isinstance(val, (int, bool)):
                formatted = str(val)

            else:
                formatted = str(val)

            # Cache the result if possible
            if cache_key:
                self._value_cache[cache_key] = formatted
                # Limit cache size
                if len(self._value_cache) > self._cache_size_limit:
                    # Remove 20% oldest entries
                    remove_count = self._cache_size_limit // 5
                    for _ in range(remove_count):
                        if self._value_cache:
                            self._value_cache.pop(next(iter(self._value_cache)))

            return formatted

        except Exception as e:
            return f"<Format Error: {type(e).__name__}>"

    def refresh(self):
        """
        # PYQT: Called on main thread by QTimer. Reads state and updates table values.
        Uses change detection to only update cells that have changed.
        """
        if self.state is None or self._updating:
            return

        # Prevent reentrant calls
        self._updating = True

        try:
            # Get a snapshot of values with thread safety
            with self._refresh_lock:
                current_values = {}
                for i, (key, _) in enumerate(self.STATS_KEYS):
                    try:
                        val = self._safe_get_attr(self.state, key)
                        current_values[i] = val
                    except Exception:
                        current_values[i] = f"<Access Error>"

            # Update only changed cells
            for i, val in current_values.items():
                try:
                    # Check if value changed
                    if i in self._last_values:
                        last_val = self._last_values[i]
                        if self._values_equal(last_val, val):
                            continue

                    # Format and update
                    formatted = self._format_value(val)
                    current_item = self.table.item(i, 1)
                    if current_item.text() != formatted:
                        current_item.setText(formatted)

                    # Store for next comparison
                    self._last_values[i] = val

                except Exception as e:
                    self.table.item(i, 1).setText(f"<Update Error>")
                    print(f"Error updating row {i}: {e}")
                    traceback.print_exc()

        finally:
            self._updating = False

    def _values_equal(self, a: Any, b: Any) -> bool:
        """Compare two values efficiently"""
        if a is b:
            return True

        if type(a) != type(b):
            return False

        if isinstance(a, (pd.DataFrame, pd.Series, np.ndarray)):
            # For large data structures, just check if they're the same object
            # or if their shapes and first elements match
            try:
                if hasattr(a, 'shape') and hasattr(b, 'shape'):
                    if a.shape != b.shape:
                        return False
                if hasattr(a, 'iloc') and hasattr(b, 'iloc'):
                    # Compare first element only
                    if len(a) > 0 and len(b) > 0:
                        return str(a.iloc[0]) == str(b.iloc[0])
                return str(a) == str(b)
            except:
                return str(a) == str(b)

        try:
            return a == b
        except:
            return str(a) == str(b)

    def _copy_to_clipboard(self, row: int, col: int):
        """# PYQT: Copy full raw value to system clipboard on double-click"""
        if col != 1:  # Only copy from value column
            return

        try:
            key = self.STATS_KEYS[row][0]
            val = self._safe_get_attr(self.state, key)
            QApplication.clipboard().setText(str(val))

            # Visual feedback - briefly highlight the cell
            item = self.table.item(row, col)
            if item:
                original_bg = item.background()
                item.setBackground(QColor("#238636"))
                QTimer.singleShot(200, lambda: item.setBackground(original_bg))

        except Exception as e:
            print(f"Copy failed: {e}")

    def clear_cache(self):
        """Clear the value cache to free memory"""
        self._value_cache.clear()
        self._last_values.clear()

    def closeEvent(self, event):
        """Clean up when tab is closed"""
        self.clear_cache()
        super().closeEvent(event)