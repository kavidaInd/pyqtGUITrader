import tkinter as tk
from tkinter import ttk
import pandas as pd
import numpy as np


class ToolTip:
    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None

    def showtip(self, text, x, y):
        self.hidetip()
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.geometry(f"+{x + 20}+{y + 10}")
        label = tk.Label(tw, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                         font=("Segoe UI", 9), wraplength=500, justify="left")
        label.pack(ipadx=1)

    def hidetip(self):
        if self.tipwindow:
            self.tipwindow.destroy()
        self.tipwindow = None


class StatsTab:
    def __init__(self, parent_notebook, state, tab_title="All State Stats"):
        self.state = state
        self.parent_notebook = parent_notebook

        self.frame = ttk.Frame(parent_notebook, padding="18 18 18 18")
        parent_notebook.add(self.frame, text=tab_title)

        header = ttk.Label(self.frame, text="📊 All Calculated State Stats", font=("Segoe UI", 15, "bold"))
        header.pack(anchor="center", pady=(0, 12))

        # Treeview
        columns = ("Stat", "Value")
        self.tree = ttk.Treeview(self.frame, columns=columns, show="headings", height=30)
        self.tree.heading("Stat", text="Stat")
        self.tree.heading("Value", text="Value")
        self.tree.column("Stat", width=240, anchor="w")
        self.tree.column("Value", width=640, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        vscroll = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y")

        # Tooltip
        self.tooltip = ToolTip(self.tree)
        self.tree.bind("<Motion>", self.on_mouse_move)
        self.tree.bind("<Leave>", lambda e: self.tooltip.hidetip())

        # Stats setup
        self.stats_keys = [
            "option_trend", "derivative_trend", "current_index_data", "current_call_data", "current_put_data",
            "call_option", "put_option", "current_trading_symbol", "derivative", "derivative_current_price",
            "last_index_updated", "orders", "current_position", "previous_position", "current_order_id",
            "current_buy_price", "current_price", "highest_current_price", "positions_hold", "order_pending",
            "take_profit_type", "stop_loss", "tp_point", "tp_percentage", "stoploss_percentage",
            "original_profit_per", "original_stoploss_per", "trailing_first_profit", "max_profit",
            "profit_step", "loss_step", "interval", "current_trade_started_time", "current_trade_confirmed",
            "percentage_change", "put_current_close", "call_current_close", "expiry", "lot_size",
            "account_balance", "max_num_of_option", "lower_percentage", "cancel_after", "call_lookback",
            "put_lookback", "original_call_lookback", "original_put_lookback", "market_trend",
            "supertrend_reset", "b_band", "all_symbols", "option_price_update", "calculated_pcr",
            "current_pcr", "trend", "current_pcr_vol", "current_pnl", "reason_to_exit",
            "derivative_history_df", "option_history_df"
        ]

        self.item_ids = {}
        for key in self.stats_keys:
            iid = self.tree.insert("", "end", values=(key, "-"))
            self.item_ids[key] = iid

        self.refresh_stats()

    def refresh_stats(self):
        s = self.state

        def pretty(val_i):
            if hasattr(val_i, 'as_dict'):
                d = val_i.as_dict()
                return f"Open: {d['open']}, High: {d['high']}, Low: {d['low']}, Close: {d['close']}, Vol: {d['volume']}"
            elif isinstance(val_i, dict):
                return str(val_i)
            elif isinstance(val_i, np.ndarray):
                try:
                    min_val = val_i.min() if val_i.size else "-"
                    max_val = val_i.max() if val_i.size else "-"
                except Exception:
                    min_val = max_val = "?"
                return f"np.ndarray shape={val_i.shape}, min={min_val}, max={max_val}"
            elif isinstance(val_i, pd.DataFrame):
                return f"DataFrame shape={val_i.shape}, columns={list(val_i.columns)}"
            elif isinstance(val_i, list):
                return str(val_i)
            return str(val_i)

        for key in self.stats_keys:
            val = getattr(s, key, "-")
            self.tree.set(self.item_ids[key], column="Value", value=pretty(val))

        self.frame.after(1000, self.refresh_stats)

    def on_mouse_move(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "cell":
            row_id = self.tree.identify_row(event.y)
            col_id = self.tree.identify_column(event.x)
            if col_id == "#2":  # Value column
                if row_id:
                    values = self.tree.item(row_id, "values")
                    if len(values) >= 2:
                        text = values[1]
                        self.tooltip.showtip(text, event.x_root, event.y_root)
                        return
        self.tooltip.hidetip()
