import os
import csv
import logging
import logging.handlers
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import traceback

from tkinter import ttk

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TradeHistoryViewer(ttk.Frame):
    def __init__(self, parent):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            self.columns = [
                "order_id", "symbol", "side", "qty", "buy_price", "sell_price",
                "pnl", "transaction_cost", "net_pnl", "percentage_change",
                "start_time", "end_time", "status", "reason"
            ]

            self.column_widths = {
                "order_id": 100,
                "symbol": 100,
                "side": 80,
                "qty": 60,
                "buy_price": 80,
                "sell_price": 80,
                "pnl": 80,
                "transaction_cost": 100,
                "net_pnl": 80,
                "percentage_change": 110,
                "start_time": 130,
                "end_time": 130,
                "status": 100,
                "reason": 200  # wider for last column
            }

            self.tree = ttk.Treeview(self, columns=self.columns, show="headings", height=20)

            for col in self.columns:
                try:
                    self.tree.heading(col, text=col.replace("_", " ").title(),
                                      command=lambda _col=col: self.sort_by(_col, False))
                    self.tree.column(col, anchor="center", width=self.column_widths.get(col, 100))
                except Exception as e:
                    logger.error(f"Failed to configure column {col}: {e}", exc_info=True)

            # Make the last column stretchable so it can expand if the widget is resized
            try:
                self.tree.column("reason", stretch=True)
            except Exception as e:
                logger.error(f"Failed to set reason column stretch: {e}", exc_info=True)

            self.tree.pack(fill="both", expand=True)

            # Add vertical scrollbar
            try:
                scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
                self.tree.configure(yscrollcommand=scrollbar.set)
                scrollbar.pack(side="right", fill="y")
            except Exception as e:
                logger.error(f"Failed to configure scrollbar: {e}", exc_info=True)

            self.load_data()

            logger.info("TradeHistoryViewer initialized")

        except Exception as e:
            logger.critical(f"[TradeHistoryViewer.__init__] Failed: {e}", exc_info=True)
            # Still try to create basic widget
            super().__init__(parent)
            self._safe_defaults_init()

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.columns = []
        self.column_widths = {}
        self.tree = None
        self._load_attempts = 0
        self.MAX_LOAD_ATTEMPTS = 3

    def get_today_trades_file(self) -> str:
        """
        Get today's trades file path.
        Format: logs/trades_YYYY-MM-DD.csv

        Returns:
            str: Path to today's trades file
        """
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            return f"logs/trades_{today}.csv"
        except Exception as e:
            logger.error(f"[get_today_trades_file] Failed: {e}", exc_info=True)
            return "logs/trades_error.csv"

    def load_data(self) -> None:
        """Load only today's trade data from the daily CSV file."""
        try:
            # Rule 6: Check if tree exists (already correct - explicit None check)
            if self.tree is None:
                logger.error("Cannot load data: tree is None")
                return

            # Clear existing items
            try:
                for item in self.tree.get_children():
                    self.tree.delete(item)
            except Exception as e:
                logger.error(f"Failed to clear tree: {e}", exc_info=True)

            today_file = self.get_today_trades_file()

            if not os.path.exists(today_file):
                logger.info(f"No trades file for today: {today_file}")
                # Insert a message row to show no data
                try:
                    self.tree.insert("", "end",
                                     values=["No trades found for today", "", "", "", "", "", "", "", "", "", "", "",
                                             "", ""])
                except Exception as e:
                    logger.error(f"Failed to insert no-data message: {e}", exc_info=True)
                return

            try:
                with open(today_file, newline="", encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    row_count = 0

                    for row in reader:
                        try:
                            # Validate row has required fields
                            if not isinstance(row, dict):
                                logger.warning(f"Skipping non-dict row: {row}")
                                continue

                            # Use net_pnl for profit/loss coloring if available, otherwise use pnl
                            pnl_value = row.get("net_pnl") or row.get("pnl", "0")
                            try:
                                pnl = float(pnl_value)
                            except (ValueError, TypeError):
                                pnl = 0
                                logger.debug(f"Could not parse PnL value: {pnl_value}")

                            tag = "profit" if pnl > 0 else "loss" if pnl < 0 else ""

                            values = [
                                row.get("order_id", ""),
                                row.get("symbol", ""),
                                row.get("side", ""),
                                row.get("qty", ""),
                                row.get("buy_price", ""),
                                row.get("sell_price", ""),
                                row.get("pnl", ""),
                                row.get("transaction_cost", ""),
                                row.get("net_pnl", ""),
                                row.get("percentage_change", ""),
                                row.get("start_time", ""),
                                row.get("end_time", ""),
                                row.get("status", ""),
                                row.get("reason", "")
                            ]

                            # Ensure all values are strings
                            values = [str(v) if v is not None else "" for v in values]

                            self.tree.insert("", "end", values=values, tags=(tag,))
                            row_count += 1

                        except Exception as e:
                            logger.warning(f"Failed to process row: {e}", exc_info=True)
                            continue

                    if row_count == 0:
                        self.tree.insert("", "end",
                                         values=["No trades completed today", "", "", "", "", "", "", "", "", "", "",
                                                 "", "", ""])
                    else:
                        logger.info(f"Loaded {row_count} trades for today")

            except FileNotFoundError:
                logger.error(f"File not found: {today_file}")
                self.tree.insert("", "end",
                                 values=[f"File not found: {today_file}", "", "", "", "", "", "", "", "", "", "", "",
                                         "", ""])
            except csv.Error as e:
                logger.error(f"CSV error reading {today_file}: {e}", exc_info=True)
                self.tree.insert("", "end",
                                 values=[f"CSV error: {str(e)}", "", "", "", "", "", "", "", "", "", "", "", "", ""])
            except IOError as e:
                logger.error(f"IO error reading {today_file}: {e}", exc_info=True)
                self.tree.insert("", "end",
                                 values=[f"File read error: {str(e)}", "", "", "", "", "", "", "", "", "", "", "", "",
                                         ""])

        except Exception as e:
            logger.error(f"Error loading today's trades: {e}", exc_info=True)
            try:
                # FIXED: Use explicit None check
                if self.tree is not None:
                    self.tree.insert("", "end",
                                     values=[f"Error loading data: {str(e)}", "", "", "", "", "", "", "", "", "", "",
                                             "", "", ""])
            except Exception:
                pass

        # Configure tag colors - FIXED: Use explicit None check
        try:
            if self.tree is not None:
                self.tree.tag_configure("profit", background="#d0f0c0")  # light green
                self.tree.tag_configure("loss", background="#f8d7da")  # light red
        except Exception as e:
            logger.error(f"Failed to configure tags: {e}", exc_info=True)

    def sort_by(self, col: str, descending: bool) -> None:
        """Sort the treeview by the specified column."""
        try:
            # Rule 6: Input validation
            if not isinstance(col, str):
                logger.warning(f"sort_by called with non-string col: {col}")
                return

            # FIXED: Use explicit None check (this was already correct)
            if self.tree is None:
                logger.warning("Cannot sort: tree is None")
                return

            # Get all items
            try:
                children = self.tree.get_children('')
            except Exception as e:
                logger.error(f"Failed to get tree children: {e}", exc_info=True)
                return

            data = []
            for child in children:
                try:
                    value = self.tree.set(child, col)
                    data.append((value, child))
                except Exception as e:
                    logger.warning(f"Failed to get value for child {child}: {e}")
                    continue

            if not data:
                return

            # Try converting to float for numeric sorting
            def try_float(val: str) -> Any:
                try:
                    # Remove any non-numeric characters except decimal and minus
                    clean_val = ''.join(c for c in val if c.isdigit() or c in '.-')
                    if clean_val and clean_val != '-':
                        return float(clean_val)
                except (ValueError, TypeError):
                    pass
                return val

            try:
                data.sort(key=lambda t: try_float(t[0]), reverse=descending)
            except Exception as e:
                logger.warning(f"Numeric sort failed, using string sort: {e}")
                data.sort(reverse=descending)

            # Reorder items
            for index, (val, item) in enumerate(data):
                try:
                    self.tree.move(item, '', index)
                except Exception as e:
                    logger.warning(f"Failed to move item {item}: {e}")
                    continue

            # Toggle sort order next time
            try:
                self.tree.heading(col, command=lambda: self.sort_by(col, not descending))
            except Exception as e:
                logger.error(f"Failed to update heading command: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[sort_by] Failed for column {col}: {e}", exc_info=True)

    def refresh(self) -> None:
        """Refresh the data display with today's trades."""
        try:
            self.load_data()
            logger.info(f"Refreshed trade history for {datetime.now().strftime('%Y-%m-%d')}")
        except Exception as e:
            logger.error(f"[refresh] Failed: {e}", exc_info=True)

    def get_daily_summary(self) -> Dict[str, Any]:
        """
        Calculate and return summary statistics for today's trades.

        Returns:
            Dict[str, Any]: Summary statistics
        """
        default_summary = {
            'total_trades': 0,
            'total_gross_pnl': 0.0,
            'total_transaction_cost': 0.0,
            'total_net_pnl': 0.0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0
        }

        try:
            today_file = self.get_today_trades_file()

            if not os.path.exists(today_file):
                logger.info(f"No trades file found for summary: {today_file}")
                return default_summary

            try:
                with open(today_file, newline="", encoding='utf-8') as file:
                    reader = csv.DictReader(file)

                    # Validate CSV has headers
                    if not reader.fieldnames:
                        logger.warning(f"CSV file {today_file} has no headers")
                        return default_summary

                    total_trades = 0
                    total_gross_pnl = 0.0
                    total_transaction_cost = 0.0
                    total_net_pnl = 0.0
                    winning_trades = 0
                    losing_trades = 0

                    for row in reader:
                        try:
                            if not isinstance(row, dict):
                                continue

                            total_trades += 1

                            try:
                                gross_pnl = float(row.get("pnl", "0"))
                            except (ValueError, TypeError):
                                gross_pnl = 0.0

                            try:
                                transaction_cost = float(row.get("transaction_cost", "0"))
                            except (ValueError, TypeError):
                                transaction_cost = 0.0

                            try:
                                net_pnl = float(row.get("net_pnl", "0"))
                            except (ValueError, TypeError):
                                net_pnl = 0.0

                            total_gross_pnl += gross_pnl
                            total_transaction_cost += transaction_cost
                            total_net_pnl += net_pnl

                            if net_pnl > 0:
                                winning_trades += 1
                            elif net_pnl < 0:
                                losing_trades += 1

                        except Exception as e:
                            logger.warning(f"Failed to process row for summary: {e}", exc_info=True)
                            continue

                    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

                    return {
                        'total_trades': total_trades,
                        'total_gross_pnl': round(total_gross_pnl, 2),
                        'total_transaction_cost': round(total_transaction_cost, 2),
                        'total_net_pnl': round(total_net_pnl, 2),
                        'winning_trades': winning_trades,
                        'losing_trades': losing_trades,
                        'win_rate': round(win_rate, 2)
                    }

            except FileNotFoundError:
                logger.error(f"File not found for summary: {today_file}")
                return default_summary
            except csv.Error as e:
                logger.error(f"CSV error in summary for {today_file}: {e}", exc_info=True)
                return default_summary
            except IOError as e:
                logger.error(f"IO error in summary for {today_file}: {e}", exc_info=True)
                return default_summary

        except Exception as e:
            logger.error(f"Error calculating daily summary: {e}", exc_info=True)
            return default_summary

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        try:
            logger.info("[TradeHistoryViewer] Starting cleanup")

            # Clear tree - FIXED: Use explicit None check
            if self.tree is not None:
                try:
                    for item in self.tree.get_children():
                        self.tree.delete(item)
                except Exception as e:
                    logger.warning(f"Error clearing tree: {e}")

            # Clear references
            self.tree = None
            self.columns = []
            self.column_widths = {}

            logger.info("[TradeHistoryViewer] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradeHistoryViewer.cleanup] Error: {e}", exc_info=True)

    def destroy(self):
        """Override destroy to ensure cleanup"""
        try:
            self.cleanup()
            super().destroy()
        except Exception as e:
            logger.error(f"[TradeHistoryViewer.destroy] Failed: {e}", exc_info=True)
            super().destroy()