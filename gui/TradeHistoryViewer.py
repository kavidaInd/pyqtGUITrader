"""
TradeHistoryViewer_db.py
========================
Database-backed trade history viewer using SQLite database.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from tkinter import ttk
from tkinter import messagebox

from db.connector import get_db
from db.crud import sessions, orders

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TradeHistoryViewer(ttk.Frame):
    def __init__(self, parent, session_id: Optional[int] = None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            self.session_id = session_id  # If None, show all today's trades
            self.current_sort_col = None
            self.current_sort_descending = False

            self.columns = [
                "order_id", "symbol", "side", "qty", "entry_price", "exit_price",
                "pnl", "status", "reason_to_exit", "entered_at", "exited_at"
            ]

            self.column_widths = {
                "order_id": 80,
                "symbol": 100,
                "side": 60,
                "qty": 60,
                "entry_price": 80,
                "exit_price": 80,
                "pnl": 80,
                "status": 80,
                "reason_to_exit": 150,
                "entered_at": 130,
                "exited_at": 130
            }

            self.column_labels = {
                "order_id": "Order ID",
                "symbol": "Symbol",
                "side": "Side",
                "qty": "Qty",
                "entry_price": "Entry",
                "exit_price": "Exit",
                "pnl": "P&L",
                "status": "Status",
                "reason_to_exit": "Exit Reason",
                "entered_at": "Entry Time",
                "exited_at": "Exit Time"
            }

            self.tree = ttk.Treeview(self, columns=self.columns, show="headings", height=20)

            for col in self.columns:
                try:
                    label = self.column_labels.get(col, col.replace("_", " ").title())
                    self.tree.heading(col, text=label,
                                      command=lambda _col=col: self.sort_by(_col))
                    self.tree.column(col, anchor="center", width=self.column_widths.get(col, 100))
                except Exception as e:
                    logger.error(f"Failed to configure column {col}: {e}", exc_info=True)

            # Make the reason column stretchable
            try:
                self.tree.column("reason_to_exit", stretch=True)
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

            # Add horizontal scrollbar
            try:
                h_scrollbar = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
                self.tree.configure(xscrollcommand=h_scrollbar.set)
                h_scrollbar.pack(side="bottom", fill="x")
            except Exception as e:
                logger.error(f"Failed to configure horizontal scrollbar: {e}", exc_info=True)

            # Configure tag colors
            try:
                self.tree.tag_configure("profit", background="#d0f0c0")  # light green
                self.tree.tag_configure("loss", background="#f8d7da")    # light red
                self.tree.tag_configure("open", background="#fff3cd")    # light yellow
                self.tree.tag_configure("cancelled", background="#e2e3e5")  # light gray
            except Exception as e:
                logger.error(f"Failed to configure tags: {e}", exc_info=True)

            # Bind double-click to show order details
            self.tree.bind("<Double-1>", self.show_order_details)

            self.load_data()

            logger.info(f"TradeHistoryViewer initialized (session_id: {session_id})")

        except Exception as e:
            logger.critical(f"[TradeHistoryViewer.__init__] Failed: {e}", exc_info=True)
            # Still try to create basic widget
            super().__init__(parent)
            self._safe_defaults_init()

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.session_id = None
        self.current_sort_col = None
        self.current_sort_descending = False
        self.columns = []
        self.column_widths = {}
        self.column_labels = {}
        self.tree = None

    def load_data(self) -> None:
        """Load trade data from database."""
        try:
            # Rule 6: Check if tree exists
            if self.tree is None:
                logger.error("Cannot load data: tree is None")
                return

            # Clear existing items
            try:
                for item in self.tree.get_children():
                    self.tree.delete(item)
            except Exception as e:
                logger.error(f"Failed to clear tree: {e}", exc_info=True)

            db = get_db()
            order_list = []

            if self.session_id is not None:
                # Load orders for specific session
                order_list = orders.list_for_session(self.session_id, db)
                logger.debug(f"Loading orders for session {self.session_id}")
            else:
                # Load all orders from today
                today = datetime.now().date()
                all_sessions = sessions.list_recent(limit=100, db=db)

                for session in all_sessions:
                    session_orders = orders.list_for_session(session["id"], db)
                    # Filter for today's orders
                    for order in session_orders:
                        entered_at = order.get("entered_at", "")
                        if entered_at and entered_at.startswith(today.isoformat()):
                            order_list.append(order)

                logger.debug(f"Loading all orders from today")

            if not order_list:
                logger.info("No orders found")
                self.tree.insert("", "end",
                                 values=["No orders found"] + [""] * (len(self.columns) - 1))
                return

            # Insert orders into tree
            row_count = 0
            for order in order_list:
                try:
                    # Calculate P&L if order is closed
                    pnl = order.get("pnl", 0)
                    if pnl is None:
                        pnl = 0

                    # Determine tag for coloring
                    if order.get("status") == "OPEN":
                        tag = "open"
                    elif order.get("status") == "CANCELLED":
                        tag = "cancelled"
                    elif pnl > 0:
                        tag = "profit"
                    elif pnl < 0:
                        tag = "loss"
                    else:
                        tag = ""

                    values = [
                        str(order.get("id", "")),
                        str(order.get("symbol", "")),
                        str(order.get("position_type", "")),
                        str(order.get("quantity", "")),
                        str(order.get("entry_price", "")),
                        str(order.get("exit_price", "")),
                        f"{float(pnl):.2f}" if pnl != 0 else "0.00",
                        str(order.get("status", "")),
                        str(order.get("reason_to_exit", "")),
                        str(order.get("entered_at", "")),
                        str(order.get("exited_at", ""))
                    ]

                    self.tree.insert("", "end", values=values, tags=(tag,))
                    row_count += 1

                except Exception as e:
                    logger.warning(f"Failed to process order {order.get('id')}: {e}", exc_info=True)
                    continue

            logger.info(f"Loaded {row_count} orders")

            # Apply current sort if any
            if self.current_sort_col:
                self.sort_by(self.current_sort_col)

        except Exception as e:
            logger.error(f"Error loading orders: {e}", exc_info=True)
            try:
                if self.tree is not None:
                    self.tree.insert("", "end",
                                     values=[f"Error loading data: {str(e)}"] + [""] * (len(self.columns) - 1))
            except Exception:
                pass

    def sort_by(self, col: str) -> None:
        """Sort the treeview by the specified column."""
        try:
            # Rule 6: Input validation
            if not isinstance(col, str):
                logger.warning(f"sort_by called with non-string col: {col}")
                return

            if self.tree is None:
                logger.warning("Cannot sort: tree is None")
                return

            # Toggle sort order if same column
            if col == self.current_sort_col:
                self.current_sort_descending = not self.current_sort_descending
            else:
                self.current_sort_col = col
                self.current_sort_descending = False

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
                    # Remove currency symbols and commas
                    clean_val = val.replace('₹', '').replace(',', '').strip()
                    if clean_val and clean_val != '-':
                        return float(clean_val)
                except (ValueError, TypeError):
                    pass
                return val

            try:
                data.sort(key=lambda t: try_float(t[0]), reverse=self.current_sort_descending)
            except Exception as e:
                logger.warning(f"Numeric sort failed, using string sort: {e}")
                data.sort(reverse=self.current_sort_descending)

            # Reorder items
            for index, (val, item) in enumerate(data):
                try:
                    self.tree.move(item, '', index)
                except Exception as e:
                    logger.warning(f"Failed to move item {item}: {e}")
                    continue

            # Update heading indicator
            for col_name in self.columns:
                try:
                    heading_text = self.column_labels.get(col_name, col_name.replace("_", " ").title())
                    if col_name == col:
                        arrow = " ↓" if self.current_sort_descending else " ↑"
                        self.tree.heading(col_name, text=heading_text + arrow)
                    else:
                        self.tree.heading(col_name, text=heading_text)
                except Exception as e:
                    logger.warning(f"Failed to update heading for {col_name}: {e}")

        except Exception as e:
            logger.error(f"[sort_by] Failed for column {col}: {e}", exc_info=True)

    def show_order_details(self, event):
        """Show detailed order information on double-click."""
        try:
            if self.tree is None:
                return

            selection = self.tree.selection()
            if not selection:
                return

            item = selection[0]
            order_id = self.tree.item(item, "values")[0]

            if not order_id or order_id == "No orders found":
                return

            try:
                order_id = int(order_id)
            except ValueError:
                return

            db = get_db()
            order = orders.get(order_id, db)

            if not order:
                messagebox.showerror("Error", f"Order {order_id} not found")
                return

            # Create a popup with order details
            self._show_order_details_popup(order)

        except Exception as e:
            logger.error(f"[show_order_details] Failed: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to show order details: {e}")

    def _show_order_details_popup(self, order: Dict[str, Any]):
        """Create a popup window with order details."""
        try:
            from tkinter import Toplevel, Label, Frame

            popup = Toplevel(self)
            popup.title(f"Order Details - ID: {order.get('id')}")
            popup.geometry("400x500")
            popup.transient(self.master)
            popup.grab_set()

            # Make popup modal
            popup.focus_set()

            # Create frames
            main_frame = Frame(popup, padx=20, pady=20)
            main_frame.pack(fill="both", expand=True)

            # Order details
            details = [
                ("Order ID", order.get("id")),
                ("Session ID", order.get("session_id")),
                ("Symbol", order.get("symbol")),
                ("Position Type", order.get("position_type")),
                ("Quantity", order.get("quantity")),
                ("Entry Price", f"₹{order.get('entry_price'):.2f}" if order.get('entry_price') else "N/A"),
                ("Exit Price", f"₹{order.get('exit_price'):.2f}" if order.get('exit_price') else "N/A"),
                ("Stop Loss", f"₹{order.get('stop_loss'):.2f}" if order.get('stop_loss') else "N/A"),
                ("Take Profit", f"₹{order.get('take_profit'):.2f}" if order.get('take_profit') else "N/A"),
                ("P&L", f"₹{order.get('pnl'):.2f}" if order.get('pnl') else "0.00"),
                ("Status", order.get("status")),
                ("Exit Reason", order.get("reason_to_exit") or "N/A"),
                ("Broker Order ID", order.get("broker_order_id") or "N/A"),
                ("Entered At", order.get("entered_at")),
                ("Exited At", order.get("exited_at") or "N/A"),
                ("Created At", order.get("created_at")),
            ]

            for i, (label, value) in enumerate(details):
                lbl = Label(main_frame, text=f"{label}:", font=("Arial", 10, "bold"))
                lbl.grid(row=i, column=0, sticky="w", pady=2)

                val_lbl = Label(main_frame, text=str(value), font=("Arial", 10))
                val_lbl.grid(row=i, column=1, sticky="w", pady=2, padx=(10, 0))

            # Close button
            from tkinter import Button
            close_btn = Button(main_frame, text="Close", command=popup.destroy)
            close_btn.grid(row=len(details), column=0, columnspan=2, pady=20)

        except Exception as e:
            logger.error(f"[_show_order_details_popup] Failed: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to create details popup: {e}")

    def refresh(self) -> None:
        """Refresh the data display."""
        try:
            self.load_data()
            logger.info("Trade history refreshed")
        except Exception as e:
            logger.error(f"[refresh] Failed: {e}", exc_info=True)

    def set_session(self, session_id: Optional[int]) -> None:
        """Set the session to display orders for."""
        try:
            self.session_id = session_id
            self.current_sort_col = None
            self.current_sort_descending = False
            self.refresh()
            logger.info(f"Session set to: {session_id}")
        except Exception as e:
            logger.error(f"[set_session] Failed: {e}", exc_info=True)

    def get_session_summary(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Calculate and return summary statistics for a session.

        Args:
            session_id: Session ID (uses current session if None)

        Returns:
            Dict[str, Any]: Summary statistics
        """
        default_summary = {
            'total_trades': 0,
            'total_pnl': 0.0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0
        }

        try:
            session_id = session_id or self.session_id
            if session_id is None:
                return default_summary

            db = get_db()
            order_list = orders.list_for_session(session_id, db)

            if not order_list:
                return default_summary

            total_trades = 0
            total_pnl = 0.0
            winning_trades = 0
            losing_trades = 0
            wins = []
            losses = []

            for order in order_list:
                # Only count closed orders
                if order.get("status") not in ["CLOSED"]:
                    continue

                total_trades += 1
                pnl = order.get("pnl", 0) or 0
                total_pnl += pnl

                if pnl > 0:
                    winning_trades += 1
                    wins.append(pnl)
                elif pnl < 0:
                    losing_trades += 1
                    losses.append(pnl)

            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
            avg_win = sum(wins) / len(wins) if wins else 0.0
            avg_loss = sum(losses) / len(losses) if losses else 0.0
            largest_win = max(wins) if wins else 0.0
            largest_loss = min(losses) if losses else 0.0

            return {
                'total_trades': total_trades,
                'total_pnl': round(total_pnl, 2),
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': round(win_rate, 2),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'largest_win': round(largest_win, 2),
                'largest_loss': round(largest_loss, 2)
            }

        except Exception as e:
            logger.error(f"Error calculating session summary: {e}", exc_info=True)
            return default_summary

    def export_to_csv(self, filename: Optional[str] = None) -> bool:
        """
        Export current view to CSV file.

        Args:
            filename: Output filename (auto-generated if None)

        Returns:
            bool: True if successful
        """
        try:
            if self.tree is None:
                logger.error("Cannot export: tree is None")
                return False

            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                session_part = f"_session_{self.session_id}" if self.session_id else ""
                filename = f"logs/trade_export{session_part}_{timestamp}.csv"

            # Ensure directory exists
            import os
            os.makedirs("logs", exist_ok=True)

            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # Write headers
                headers = [self.column_labels.get(col, col) for col in self.columns]
                writer.writerow(headers)

                # Write data
                for item in self.tree.get_children():
                    values = self.tree.item(item, "values")
                    writer.writerow(values)

            logger.info(f"Exported trade history to {filename}")
            return True

        except Exception as e:
            logger.error(f"[export_to_csv] Failed: {e}", exc_info=True)
            return False

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        try:
            logger.info("[TradeHistoryViewer] Starting cleanup")

            # Clear tree
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
            self.column_labels = {}

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