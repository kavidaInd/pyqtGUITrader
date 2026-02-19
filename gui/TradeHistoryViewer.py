import os
import csv
from datetime import datetime
from tkinter import ttk


class TradeHistoryViewer(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        columns = [
            "order_id", "symbol", "side", "qty", "buy_price", "sell_price",
            "pnl", "transaction_cost", "net_pnl", "percentage_change",
            "start_time", "end_time", "status", "reason"
        ]

        column_widths = {
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
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=20)

        for col in columns:
            self.tree.heading(col, text=col.replace("_", " ").title(),
                              command=lambda _col=col: self.sort_by(_col, False))
            self.tree.column(col, anchor="center", width=column_widths.get(col, 100))

        # Make the last column stretchable so it can expand if the widget is resized
        self.tree.column("reason", stretch=True)

        self.tree.pack(fill="both", expand=True)

        # Add vertical scrollbar
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.load_data()

    def get_today_trades_file(self):
        """
        Get today's trades file path.
        Format: logs/trades_YYYY-MM-DD.csv
        """
        today = datetime.now().strftime('%Y-%m-%d')
        return f"logs/trades_{today}.csv"

    def load_data(self):
        """Load only today's trade data from the daily CSV file."""
        self.tree.delete(*self.tree.get_children())  # clear existing

        today_file = self.get_today_trades_file()

        if not os.path.exists(today_file):
            print(f"No trades file for today: {today_file}")
            # Insert a message row to show no data
            self.tree.insert("", "end",
                             values=["No trades found for today", "", "", "", "", "", "", "", "", "", "", "", "", ""])
            return

        try:
            with open(today_file, newline="") as file:
                reader = csv.DictReader(file)
                row_count = 0

                for row in reader:
                    try:
                        # Use net_pnl for profit/loss coloring if available, otherwise use pnl
                        pnl_value = row.get("net_pnl") or row.get("pnl", "0")
                        pnl = float(pnl_value)
                    except (ValueError, TypeError):
                        pnl = 0

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
                    self.tree.insert("", "end", values=values, tags=(tag,))
                    row_count += 1

                if row_count == 0:
                    self.tree.insert("", "end",
                                     values=["No trades completed today", "", "", "", "", "", "", "", "", "", "", "",
                                             "", ""])
                else:
                    print(f"Loaded {row_count} trades for today")

        except Exception as e:
            print(f"Error loading today's trades: {e}")
            self.tree.insert("", "end",
                             values=[f"Error loading data: {str(e)}", "", "", "", "", "", "", "", "", "", "", "", "",
                                     ""])

        # Configure tag colors
        self.tree.tag_configure("profit", background="#d0f0c0")  # light green
        self.tree.tag_configure("loss", background="#f8d7da")  # light red

    def sort_by(self, col, descending):
        """Sort the treeview by the specified column."""
        data = [(self.tree.set(child, col), child) for child in self.tree.get_children('')]

        # Try converting to float for numeric sorting
        def try_float(val):
            try:
                return float(val)
            except (ValueError, TypeError):
                return val

        try:
            data.sort(key=lambda t: try_float(t[0]), reverse=descending)
        except Exception:
            data.sort(reverse=descending)

        for index, (val, item) in enumerate(data):
            self.tree.move(item, '', index)

        # Toggle sort order next time
        self.tree.heading(col, command=lambda: self.sort_by(col, not descending))

    def refresh(self):
        """Refresh the data display with today's trades."""
        self.load_data()
        print(f"Refreshed trade history for {datetime.now().strftime('%Y-%m-%d')}")

    def get_daily_summary(self):
        """
        Calculate and return summary statistics for today's trades.
        """
        today_file = self.get_today_trades_file()

        if not os.path.exists(today_file):
            return {
                'total_trades': 0,
                'total_gross_pnl': 0.0,
                'total_transaction_cost': 0.0,
                'total_net_pnl': 0.0,
                'winning_trades': 0,
                'losing_trades': 0
            }

        try:
            with open(today_file, newline="") as file:
                reader = csv.DictReader(file)

                total_trades = 0
                total_gross_pnl = 0.0
                total_transaction_cost = 0.0
                total_net_pnl = 0.0
                winning_trades = 0
                losing_trades = 0

                for row in reader:
                    total_trades += 1

                    try:
                        gross_pnl = float(row.get("pnl", "0"))
                        transaction_cost = float(row.get("transaction_cost", "0"))
                        net_pnl = float(row.get("net_pnl", "0"))

                        total_gross_pnl += gross_pnl
                        total_transaction_cost += transaction_cost
                        total_net_pnl += net_pnl

                        if net_pnl > 0:
                            winning_trades += 1
                        elif net_pnl < 0:
                            losing_trades += 1

                    except (ValueError, TypeError):
                        continue

                return {
                    'total_trades': total_trades,
                    'total_gross_pnl': round(total_gross_pnl, 2),
                    'total_transaction_cost': round(total_transaction_cost, 2),
                    'total_net_pnl': round(total_net_pnl, 2),
                    'winning_trades': winning_trades,
                    'losing_trades': losing_trades,
                    'win_rate': round((winning_trades / total_trades * 100), 2) if total_trades > 0 else 0.0
                }

        except Exception as e:
            print(f"Error calculating daily summary: {e}")
            return {
                'total_trades': 0,
                'total_gross_pnl': 0.0,
                'total_transaction_cost': 0.0,
                'total_net_pnl': 0.0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0
            }
