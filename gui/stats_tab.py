# PYQT: Replaces Tkinter StatsTab - preserves class name
import logging
import logging.handlers
import traceback
from typing import Any, Optional, Dict
import threading

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTableWidget,
                             QTableWidgetItem, QHeaderView, QLabel, QApplication)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor
import pandas as pd
import numpy as np

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


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
    _value_cache: Dict[int, str] = {}
    _cache_size_limit = 1000

    def __init__(self, state, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.state = state
            self._refresh_lock = threading.RLock()  # Use RLock for reentrant locking
            self._last_values: Dict[int, Any] = {}
            self._updating = False
            self._closing = False

            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 12, 12, 12)

            # EXACT layout preservation
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

            # EXACT stylesheet preservation
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
                try:
                    item = QTableWidgetItem(display_name)
                    item.setForeground(QColor("#8b949e"))
                    self.table.setItem(i, 0, item)
                    self.table.setItem(i, 1, QTableWidgetItem("—"))
                except Exception as e:
                    logger.error(f"Failed to create table item for row {i}: {e}", exc_info=True)

            # PYQT: Copy to clipboard on cell double-click
            self.table.cellDoubleClicked.connect(self._copy_to_clipboard)

            layout.addWidget(self.table)

            logger.info("StatsTab initialized")

        except Exception as e:
            logger.critical(f"[StatsTab.__init__] Failed: {e}", exc_info=True)
            # Still try to create basic widget
            super().__init__(parent)
            self.state = state
            self._safe_defaults_init()
            layout = QVBoxLayout(self)
            error_label = QLabel(f"❌ Error initializing stats tab: {e}")
            error_label.setStyleSheet("color: #f85149; padding: 20px;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.state = None
        self._refresh_lock = threading.RLock()
        self._last_values = {}
        self._updating = False
        self._closing = False
        self.table = None

    def _safe_get_attr(self, obj: Any, key: str, default: Any = "—") -> Any:
        """Safely get attribute from object with error handling"""
        try:
            # Rule 6: Input validation
            if obj is None:
                logger.debug(f"_safe_get_attr called with None obj for key {key}")
                return default

            if not isinstance(key, str):
                logger.warning(f"_safe_get_attr called with non-string key: {key}")
                return default

            if hasattr(obj, key):
                return getattr(obj, key)
            return default

        except AttributeError as e:
            logger.debug(f"Attribute {key} not found: {e}")
            return default
        except Exception as e:
            logger.error(f"[_safe_get_attr] Failed for key {key}: {e}", exc_info=True)
            return f"<Error: {type(e).__name__}>"

    def _format_value(self, val: Any, max_length: int = 120) -> str:
        """Format a value for display with caching for complex objects"""
        try:
            if val is None:
                return "—"

            # Use cache for complex objects to avoid repeated formatting
            cache_key = None
            if hasattr(val, '__hash__') and val is not None:
                try:
                    # Create a cache key based on type and string representation
                    type_id = id(type(val))
                    val_hash = hash(str(val)) % self._cache_size_limit
                    cache_key = type_id * self._cache_size_limit + val_hash
                except (TypeError, ValueError) as e:
                    logger.debug(f"Cannot create cache key for {type(val)}: {e}")
                    cache_key = None

            if cache_key is not None and cache_key in self._value_cache:
                return self._value_cache[cache_key]

            # Handle different types efficiently
            formatted = self._format_value_by_type(val, max_length)

            # Cache the result if possible
            if cache_key is not None:
                self._value_cache[cache_key] = formatted
                # Limit cache size
                if len(self._value_cache) > self._cache_size_limit:
                    # Remove 20% oldest entries
                    remove_count = max(1, self._cache_size_limit // 5)
                    for _ in range(remove_count):
                        if self._value_cache:
                            self._value_cache.pop(next(iter(self._value_cache)))

            return formatted

        except Exception as e:
            logger.error(f"[_format_value] Failed: {e}", exc_info=True)
            return f"<Format Error: {type(e).__name__}>"

    def _format_value_by_type(self, val: Any, max_length: int) -> str:
        """Format value based on its type"""
        try:
            # Check for as_dict method first
            if hasattr(val, "as_dict") and callable(getattr(val, "as_dict")):
                try:
                    d = val.as_dict()
                    return (f"O:{d.get('open', '-')}  H:{d.get('high', '-')}  "
                            f"L:{d.get('low', '-')}  C:{d.get('close', '-')}  Vol:{d.get('volume', '-')}")
                except Exception as e:
                    logger.debug(f"as_dict failed: {e}")
                    return str(val)

            # Handle pandas DataFrame
            if isinstance(val, pd.DataFrame):
                if val.empty:
                    return "Empty DataFrame"
                try:
                    cols = list(val.columns[:4])
                    result = f"DataFrame {val.shape}  cols={cols}"
                    if len(val) > 0:
                        # Show first row as sample
                        try:
                            first_row = val.iloc[0].to_dict()
                            sample = {k: v for k, v in list(first_row.items())[:3]}
                            result += f"  sample: {sample}"
                        except Exception as e:
                            logger.debug(f"Failed to get sample: {e}")
                    return result
                except Exception as e:
                    logger.debug(f"DataFrame formatting failed: {e}")
                    return f"DataFrame {val.shape}"

            # Handle pandas Series
            if isinstance(val, pd.Series):
                try:
                    return f"Series {val.shape}  {val.name}"
                except Exception as e:
                    logger.debug(f"Series formatting failed: {e}")
                    return "Series"

            # Handle numpy array
            if isinstance(val, np.ndarray):
                try:
                    result = f"ndarray shape={val.shape}  dtype={val.dtype}"
                    if val.size > 0 and val.size < 10:
                        result += f"  {val}"
                    return result
                except Exception as e:
                    logger.debug(f"ndarray formatting failed: {e}")
                    return "ndarray"

            # Handle dictionary
            if isinstance(val, dict):
                s = str(val)
                return s[:max_length] + "..." if len(s) > max_length else s

            # Handle lists and tuples
            if isinstance(val, (list, tuple)):
                try:
                    if len(val) > 5:
                        return f"{type(val).__name__}[{len(val)}]: {str(val[:4])[:-1]}, ..."
                    return str(val)
                except Exception as e:
                    logger.debug(f"List/tuple formatting failed: {e}")
                    return f"{type(val).__name__}[{len(val) if hasattr(val, '__len__') else '?'}]"

            # Handle float
            if isinstance(val, float):
                try:
                    return f"{val:.4f}"
                except Exception as e:
                    logger.debug(f"Float formatting failed: {e}")
                    return str(val)

            # Handle int and bool
            if isinstance(val, (int, bool)):
                return str(val)

            # Default to string
            s = str(val)
            return s[:max_length] + "..." if len(s) > max_length else s

        except Exception as e:
            logger.error(f"[_format_value_by_type] Failed: {e}", exc_info=True)
            return f"<Format Error: {type(e).__name__}>"

    def refresh(self):
        """
        # PYQT: Called on main thread by QTimer. Reads state and updates table values.
        Uses change detection to only update cells that have changed.
        """
        # Rule 6: Check if we should update
        if self._closing:
            return

        if self.state is None:
            logger.debug("Refresh called with None state")
            return

        if self._updating:
            logger.debug("Refresh already in progress, skipping")
            return

        # Prevent reentrant calls
        self._updating = True

        try:
            # Check if table exists - This is already correct (explicit None check)
            if self.table is None:
                logger.warning("Refresh called with None table")
                return

            # Get a snapshot of values with thread safety
            with self._refresh_lock:
                current_values = {}
                for i, (key, _) in enumerate(self.STATS_KEYS):
                    try:
                        val = self._safe_get_attr(self.state, key)
                        current_values[i] = val
                    except Exception as e:
                        logger.warning(f"Failed to get value for key {key}: {e}")
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

                    if current_item is not None and current_item.text() != formatted:
                        current_item.setText(formatted)

                    # Store for next comparison
                    self._last_values[i] = val

                except IndexError:
                    logger.warning(f"Row {i} out of range")
                except Exception as e:
                    logger.error(f"Error updating row {i}: {e}", exc_info=True)
                    try:
                        item = self.table.item(i, 1)
                        if item is not None:
                            item.setText(f"<Update Error>")
                    except:
                        pass

        except Exception as e:
            logger.error(f"[StatsTab.refresh] Failed: {e}", exc_info=True)
        finally:
            self._updating = False

    def _values_equal(self, a: Any, b: Any) -> bool:
        """Compare two values efficiently"""
        try:
            if a is b:
                return True

            if type(a) != type(b):
                return False

            if a is None or b is None:
                return a is b

            # Handle pandas and numpy objects
            if isinstance(a, (pd.DataFrame, pd.Series, np.ndarray)):
                try:
                    # For large data structures, just check if they're the same object
                    # or if their shapes and first elements match
                    if hasattr(a, 'shape') and hasattr(b, 'shape'):
                        if a.shape != b.shape:
                            return False

                    # Try to compare first element
                    if hasattr(a, 'iloc') and hasattr(b, 'iloc'):
                        if len(a) > 0 and len(b) > 0:
                            try:
                                return str(a.iloc[0]) == str(b.iloc[0])
                            except:
                                pass

                    # Fallback to string comparison
                    return str(a) == str(b)

                except Exception as e:
                    logger.debug(f"Pandas/numpy comparison failed: {e}")
                    return str(a) == str(b)

            # Regular comparison
            try:
                return a == b
            except Exception as e:
                logger.debug(f"Direct comparison failed: {e}")
                return str(a) == str(b)

        except Exception as e:
            logger.error(f"[_values_equal] Failed: {e}", exc_info=True)
            return False

    def _copy_to_clipboard(self, row: int, col: int):
        """# PYQT: Copy full raw value to system clipboard on double-click"""
        if col != 1:  # Only copy from value column
            return

        try:
            # Rule 6: Validate row
            if row < 0 or row >= len(self.STATS_KEYS):
                logger.warning(f"Invalid row index: {row}")
                return

            key = self.STATS_KEYS[row][0]
            val = self._safe_get_attr(self.state, key)

            # Copy to clipboard
            QApplication.clipboard().setText(str(val))
            logger.debug(f"Copied {key} to clipboard: {val}")

            # Visual feedback - briefly highlight the cell
            # FIXED: Use explicit None check
            if self.table is not None:
                item = self.table.item(row, col)
                if item is not None:
                    original_bg = item.background()
                    item.setBackground(QColor("#238636"))
                    QTimer.singleShot(200, lambda: self._reset_cell_background(item, original_bg))

        except Exception as e:
            logger.error(f"Copy failed: {e}", exc_info=True)

    def _reset_cell_background(self, item: QTableWidgetItem, original_bg):
        """Reset cell background after copy feedback"""
        try:
            # FIXED: Use explicit None check
            if item is not None and not self._closing:
                item.setBackground(original_bg)
        except Exception as e:
            logger.error(f"Failed to reset cell background: {e}", exc_info=True)

    def clear_cache(self):
        """Clear the value cache to free memory"""
        try:
            self._value_cache.clear()
            self._last_values.clear()
            logger.debug("Cache cleared")
        except Exception as e:
            logger.error(f"[StatsTab.clear_cache] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown"""
        try:
            logger.info("[StatsTab] Starting cleanup")
            self._closing = True
            self._updating = False

            # Clear cache
            self.clear_cache()

            # Clear references
            self.state = None
            self.table = None

            logger.info("[StatsTab] Cleanup completed")

        except Exception as e:
            logger.error(f"[StatsTab.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Clean up when tab is closed"""
        try:
            self.cleanup()
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[StatsTab.closeEvent] Failed: {e}", exc_info=True)
            super().closeEvent(event)