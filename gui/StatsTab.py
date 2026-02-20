import tkinter as tk
from tkinter import ttk
import pandas as pd
import numpy as np


class ToolTip:
    """Create a tooltip for a given widget."""

    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0

    def showtip(self, text, x, y):
        """Display text in tooltip window at the given coordinates."""
        self.hidetip()
        if not text:
            return

        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x + 20}+{y + 10}")

        # Create label with proper styling
        label = tk.Label(
            tw,
            text=text,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 9),
            wraplength=500,
            justify="left",
            padx=5,
            pady=3
        )
        label.pack(ipadx=1)

    def hidetip(self):
        """Destroy the tooltip window."""
        if self.tipwindow:
            self.tipwindow.destroy()
        self.tipwindow = None


class StatsTab:
    """
    Statistics tab for displaying all state variables in a treeview with tooltips.
    The tab automatically refreshes every second.
    """

    def __init__(self, parent_notebook, state, tab_title="📊 All State Stats"):
        """
        Initialize the Stats tab.

        Args:
            parent_notebook: The notebook widget that will contain this tab
            state: The trading state object containing all statistics
            tab_title: Title to display on the tab (default: "📊 All State Stats")
        """
        self.state = state
        self.parent_notebook = parent_notebook

        # Create the frame that will be added to the notebook
        self.frame = ttk.Frame(parent_notebook, padding="18 18 18 18", style="Light.TFrame")

        # Create header
        header_frame = ttk.Frame(self.frame, style="Light.TFrame")
        header_frame.pack(fill=tk.X, pady=(0, 12))

        header = ttk.Label(
            header_frame,
            text="📊 All Calculated State Stats",
            font=("Segoe UI", 15, "bold"),
            style="Light.TLabel"
        )
        header.pack(anchor="center")

        # Create subtitle with refresh info
        subtitle = ttk.Label(
            header_frame,
            text="Auto-refreshes every second • Hover over values to see full content",
            font=("Segoe UI", 8),
            style="Light.TLabel",
            foreground="#666666"
        )
        subtitle.pack(anchor="center", pady=(2, 0))

        # Create main content frame for treeview and scrollbar
        content_frame = ttk.Frame(self.frame, style="Light.TFrame")
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Treeview for displaying stats
        columns = ("Stat", "Value")
        self.tree = ttk.Treeview(
            content_frame,
            columns=columns,
            show="headings",
            height=30,
            selectmode="none"  # Disable selection to avoid visual distraction
        )

        # Configure columns
        self.tree.heading("Stat", text="Stat")
        self.tree.heading("Value", text="Value")
        self.tree.column("Stat", width=240, anchor="w", minwidth=200)
        self.tree.column("Value", width=640, anchor="w", minwidth=400)

        # Add tags for alternating row colors
        self.tree.tag_configure('oddrow', background='#f8f9fa')
        self.tree.tag_configure('evenrow', background='#ffffff')

        # Scrollbar
        vscroll = ttk.Scrollbar(content_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)

        # Pack treeview and scrollbar
        self.tree.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")

        # Tooltip setup
        self.tooltip = ToolTip(self.tree)
        self.tree.bind("<Motion>", self.on_mouse_move)
        self.tree.bind("<Leave>", lambda e: self.tooltip.hidetip())

        # Bind double-click to copy value to clipboard
        self.tree.bind("<Double-1>", self.copy_to_clipboard)

        # Define all state keys to display
        self.stats_keys = [
            # Trading state
            ("current_position", "Current Position"),
            ("previous_position", "Previous Position"),
            ("current_trading_symbol", "Trading Symbol"),
            ("current_order_id", "Order ID"),
            ("order_pending", "Order Pending"),
            ("positions_hold", "Positions Hold"),
            ("reason_to_exit", "Exit Reason"),

            # Price data
            ("current_buy_price", "Buy Price"),
            ("current_price", "Current Price"),
            ("highest_current_price", "Highest Price"),
            ("derivative_current_price", "Derivative Price"),
            ("current_index_data", "Index Data"),
            ("current_call_data", "Call Data"),
            ("current_put_data", "Put Data"),

            # Profit/Loss
            ("percentage_change", "P&L %"),
            ("current_pnl", "Current P&L"),
            ("account_balance", "Account Balance"),
            ("max_profit", "Max Profit"),

            # Stop Loss & Take Profit
            ("stop_loss", "Stop Loss"),
            ("tp_point", "Take Profit"),
            ("tp_percentage", "TP %"),
            ("stoploss_percentage", "SL %"),
            ("original_profit_per", "Original Profit %"),
            ("original_stoploss_per", "Original SL %"),
            ("trailing_first_profit", "Trailing First Profit"),
            ("take_profit_type", "TP Type"),

            # Strategy parameters
            ("profit_step", "Profit Step"),
            ("loss_step", "Loss Step"),
            ("interval", "Interval"),
            ("cancel_after", "Cancel After"),
            ("lot_size", "Lot Size"),
            ("expiry", "Expiry"),
            ("max_num_of_option", "Max Options"),
            ("lower_percentage", "Lower %"),

            # Technical indicators
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

            # Options data
            ("call_option", "Call Option"),
            ("put_option", "Put Option"),
            ("call_current_close", "Call Close"),
            ("put_current_close", "Put Close"),

            # PCR data
            ("calculated_pcr", "Calculated PCR"),
            ("current_pcr", "Current PCR"),
            ("current_pcr_vol", "PCR Volume"),

            # Timestamps
            ("current_trade_started_time", "Trade Start Time"),
            ("current_trade_confirmed", "Trade Confirmed"),
            ("last_index_updated", "Last Index Update"),
            ("option_price_update", "Option Price Update"),

            # History data
            ("derivative_history_df", "Derivative History"),
            ("option_history_df", "Option History"),
            ("orders", "Orders"),
            ("all_symbols", "All Symbols"),
        ]

        # Store item IDs for updating
        self.item_ids = {}

        # Insert all stats with alternating row colors
        for i, (key, display_name) in enumerate(self.stats_keys):
            tag = 'evenrow' if i % 2 == 0 else 'oddrow'
            iid = self.tree.insert("", "end", values=(display_name, "-"), tags=(tag,))
            self.item_ids[key] = iid

        # Start the refresh loop
        self.refresh_stats()

    def refresh_stats(self):
        """
        Refresh all statistics values in the treeview.
        Called automatically every second.
        """
        if not hasattr(self, 'tree') or not self.tree.winfo_exists():
            return

        s = self.state

        def format_value(val):
            """
            Format different types of values for display.
            """
            if val is None:
                return "-"

            # Handle objects with as_dict method (like market data)
            if hasattr(val, 'as_dict'):
                try:
                    d = val.as_dict()
                    return f"Open: {d.get('open', '-')}, High: {d.get('high', '-')}, Low: {d.get('low', '-')}, Close: {d.get('close', '-')}, Vol: {d.get('volume', '-')}"
                except:
                    return str(val)

            # Handle dictionaries
            elif isinstance(val, dict):
                try:
                    # Truncate long dictionaries for display
                    if len(str(val)) > 100:
                        return str(dict(list(val.items())[:5])) + "..."
                    return str(val)
                except:
                    return "{}"

            # Handle numpy arrays
            elif isinstance(val, np.ndarray):
                try:
                    if val.size == 0:
                        return "Empty array"
                    shape = val.shape
                    dtype = val.dtype

                    # Show preview of array values
                    if val.size <= 10:
                        preview = str(val.tolist())
                    else:
                        flat = val.flatten()
                        preview = f"[{flat[0]}, {flat[1]}, {flat[2]}, ..., {flat[-3]}, {flat[-2]}, {flat[-1]}]"

                    return f"np.ndarray shape={shape}, dtype={dtype}\n{preview}"
                except Exception as e:
                    return f"np.ndarray shape={val.shape}"

            # Handle pandas DataFrames
            elif isinstance(val, pd.DataFrame):
                try:
                    cols = list(val.columns)
                    # Limit columns shown
                    if len(cols) > 5:
                        cols = cols[:5] + ["..."]
                    return f"DataFrame shape={val.shape}, columns={cols}"
                except:
                    return f"DataFrame shape={val.shape}"

            # Handle lists
            elif isinstance(val, list):
                try:
                    if len(val) <= 10:
                        return str(val)
                    else:
                        return f"List[{len(val)}]: {str(val[:5])[1:-1]}, ..."
                except:
                    return f"List[{len(val)}]"

            # Handle numbers with formatting
            elif isinstance(val, (int, float)):
                if isinstance(val, float):
                    return f"{val:.4f}"
                return str(val)

            # Default to string representation
            return str(val)

        # Update each stat value
        for key, display_name in self.stats_keys:
            if key in self.item_ids:
                try:
                    val = getattr(s, key, "-")
                    formatted_val = format_value(val)
                    self.tree.set(self.item_ids[key], column="Value", value=formatted_val)
                except Exception as e:
                    # If there's an error, show error message
                    self.tree.set(self.item_ids[key], column="Value", value=f"<Error: {str(e)[:50]}>")

        # Schedule next refresh
        try:
            self.frame.after(1000, self.refresh_stats)
        except:
            pass  # Frame might be destroyed

    def on_mouse_move(self, event):
        """
        Handle mouse movement to show tooltips for cell values.
        """
        try:
            region = self.tree.identify("region", event.x, event.y)
            if region == "cell":
                row_id = self.tree.identify_row(event.y)
                col_id = self.tree.identify_column(event.x)

                if col_id == "#2":  # Value column
                    if row_id:
                        values = self.tree.item(row_id, "values")
                        if len(values) >= 2:
                            text = values[1]
                            if text and text != "-":
                                self.tooltip.showtip(text, event.x_root, event.y_root)
                                return
        except:
            pass

        self.tooltip.hidetip()

    def copy_to_clipboard(self, event):
        """
        Copy the selected cell value to clipboard on double-click.
        """
        try:
            region = self.tree.identify("region", event.x, event.y)
            if region == "cell":
                row_id = self.tree.identify_row(event.y)
                col_id = self.tree.identify_column(event.x)

                if row_id:
                    values = self.tree.item(row_id, "values")
                    if len(values) >= 2:
                        # Get the full value from state for copying
                        stat_name = values[0]
                        # Find the key for this display name
                        for key, display_name in self.stats_keys:
                            if display_name == stat_name:
                                full_value = getattr(self.state, key, "-")
                                # Copy to clipboard
                                self.frame.clipboard_clear()
                                self.frame.clipboard_append(str(full_value))

                                # Show brief feedback (optional)
                                self.show_copy_feedback()
                                break
        except Exception as e:
            print(f"Copy error: {e}")

    def show_copy_feedback(self):
        """
        Show a brief feedback message when value is copied.
        """
        try:
            # Create a temporary label for feedback
            feedback = ttk.Label(
                self.frame,
                text="✓ Copied!",
                foreground="#43a047",
                font=("Segoe UI", 8, "bold"),
                style="Light.TLabel"
            )
            feedback.place(relx=0.5, rely=0.1, anchor="center")

            # Remove after 1 second
            self.frame.after(1000, feedback.destroy)
        except:
            pass

    def destroy(self):
        """
        Clean up resources when tab is destroyed.
        """
        try:
            if hasattr(self, 'frame') and self.frame:
                self.frame.destroy()
        except:
            pass