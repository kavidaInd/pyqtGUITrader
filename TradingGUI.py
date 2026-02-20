import threading
import logging
import tkinter as tk
from tkinter import ttk, messagebox

import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend for thread-safe rendering
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import BaseEnums
from gui.BrokerageSetting import BrokerageSetting
from gui.BrokerageSettingGUI import BrokerageSettingGUI
from gui.DailyTradeSetting import DailyTradeSetting
from gui.DailyTradeSettingGUI import DailyTradeSettingGUI
from gui.FyersManualLoginPopup import FyersManualLoginPopup
from gui.ProfitStoplossSetting import ProfitStoplossSetting
from gui.ProfitStoplossSettingGUI import ProfitStoplossSettingGUI
from gui.StrategySetting import StrategySetting
from gui.StrategySettingGUI import StrategySettingGUI
from gui.TextHandler import TextHandler
from gui.TradeHistoryViewer import TradeHistoryViewer
from gui.StatsTab import StatsTab
from new_main import TradingApp
from config import Config

logger = logging.getLogger(__name__)

# ── Tab title constants ────────────────────────────────────────────────────────
_TAB_LOGS = "📝 Logs"
_TAB_HISTORY = "Trade History"
_TAB_STATS = "📊 Stats"


class TradingGUI:
    """Main Tkinter trading dashboard window."""

    def __init__(self, base):
        self.root = base
        self.root.title("Algo Trading Dashboard")
        self.root.geometry("1200x700")
        self.root.minsize(1100, 700)

        # ── Settings objects ───────────────────────────────────────────────────
        self.config = Config()
        self.daily_settings = DailyTradeSetting()
        self.brokerage_setting = BrokerageSetting()
        self.strategy_setting = StrategySetting()
        self.profit_stoploss_setting = ProfitStoplossSetting()
        self.trading_mode = tk.StringVar(value="algo")

        # ── Chart state ────────────────────────────────────────────────────────
        self.fig = plt.Figure(figsize=(10, 6))
        self.canvas = None
        # FIX: Initialize fingerprint as empty string (was None)
        self._last_chart_data = ""
        self._chart_render_pending = False  # guard — prevent concurrent renders

        # ── Widget references (populated during layout) ────────────────────────
        self.stats_tab = None
        self.stats_tab_idx = None
        self.status_labels = None
        self.status_frame = None
        self.trade_history_tab = None
        self.notebook = None

        # ── Runtime flags ──────────────────────────────────────────────────────
        self.app_running = False
        self._status_update_pending = False  # guard for update_status_labels loop
        self._chart_update_pending = False  # guard for update_chart loop
        self._closing = False  # set True when window is closing

        # ── Trading app ────────────────────────────────────────────────────────
        self.app = self._create_trading_app()

        # ── Build UI ───────────────────────────────────────────────────────────
        self._apply_styles()
        self.create_menu()
        self.create_main_layout()
        self.setup_logger()

        # Start periodic GUI update loops
        self._schedule_status_update()
        self._schedule_chart_update()

        self.update_trade_history()
        self.add_stats_tab()
        self._bind_events()

    # ══════════════════════════════════════════════════════════════════════════
    # Initialisation helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _create_trading_app(self):
        """Create TradingApp safely; show error and return None on failure."""
        try:
            return TradingApp(
                config=self.config,
                trading_mode_var=self.trading_mode,
                broker_setting=self.brokerage_setting,
            )
        except Exception as e:
            logger.critical(f"Failed to create TradingApp: {e}", exc_info=True)
            # Show error after mainloop starts
            self.root.after(
                200,
                lambda: messagebox.showerror(
                    "Initialisation Error",
                    f"Could not connect to broker:\n{e}\n\n"
                    "Please check your credentials via Settings > Brokerage Settings.",
                ),
            )
            return None

    @staticmethod
    def _apply_styles():
        """Configure ttk styles for the dashboard."""
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Light.TFrame", background="#f4f6fa")
        s.configure("Light.TLabel", background="#f4f6fa", foreground="#333333")
        s.configure("StatusBold.TLabel", font=("Segoe UI", 10, "bold"),
                    background="#f4f6fa", foreground="#333333")
        s.configure("StatusValue.TLabel", font=("Segoe UI", 9),
                    background="#f4f6fa", foreground="#333333")
        s.configure("TButton", font=("Segoe UI", 9), padding=4)
        s.configure("Green.TButton", background="#61e786", foreground="#222", borderwidth=1)
        s.map("Green.TButton",
              background=[("active", "#38cc6c"), ("disabled", "#b2f5c0")],
              foreground=[("disabled", "#888")])
        s.configure("Red.TButton", background="#ff6f61", foreground="#fff", borderwidth=1)
        s.map("Red.TButton",
              background=[("active", "#e53935"), ("disabled", "#ffb3b0")],
              foreground=[("disabled", "#fff")])
        s.configure("Purple.TButton", background="#b39ddb", foreground="#222", borderwidth=1)
        s.configure("Blue.TButton", background="#64b5f6", foreground="#222", borderwidth=1)
        s.configure("Orange.TButton", background="#ffb74d", foreground="#222", borderwidth=1)
        s.configure("Treeview", font=("Consolas", 9), background="#ffffff",
                    foreground="#222831", fieldbackground="#ffffff")
        s.map("Treeview", background=[("selected", "#00adb5")])

    # ══════════════════════════════════════════════════════════════════════════
    # Menu
    # ══════════════════════════════════════════════════════════════════════════

    def create_menu(self):
        """Build the top menu bar."""
        menu_bar = tk.Menu(self.root)
        self.root.config(menu=menu_bar)

        settings_menu = tk.Menu(menu_bar, tearoff=0)
        settings_menu.add_command(label="Strategy Settings",
                                  command=self.open_strategy_settings_popup)
        settings_menu.add_command(label="Daily Trade Settings",
                                  command=self.open_daily_settings_popup)
        settings_menu.add_command(label="Profit and Loss Settings",
                                  command=self.profit_and_loss_setting_popup)
        settings_menu.add_command(label="Brokerage Settings",
                                  command=self.open_brokerage_settings_popup)
        settings_menu.add_command(label="Manual Fyers Login",
                                  command=self.open_manual_login_popup)
        menu_bar.add_cascade(label="Settings", menu=settings_menu)

        help_menu = tk.Menu(menu_bar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menu_bar.add_cascade(label="Help", menu=help_menu)

    # ══════════════════════════════════════════════════════════════════════════
    # Layout
    # ══════════════════════════════════════════════════════════════════════════

    def create_main_layout(self):
        """Build main two-column layout (chart left, controls right)."""
        main_frame = ttk.Frame(self.root, style="Light.TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left — chart
        left_frame = ttk.Frame(main_frame, style="Light.TFrame")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        self.canvas = FigureCanvasTkAgg(self.fig, master=left_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Right — status & controls
        right_frame = ttk.Frame(main_frame, style="Light.TFrame")
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=16, pady=12)

        # Mode switch
        switch_frame = ttk.Frame(right_frame, style="Light.TFrame")
        switch_frame.pack(fill=tk.X, pady=(8, 8))
        ttk.Label(
            switch_frame, text="Trading Mode:", style="Light.TLabel",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Radiobutton(
            switch_frame, text="⚡ Automatic (Algo)",
            variable=self.trading_mode, value="algo",
            style="TRadiobutton", command=self.on_mode_switch,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(
            switch_frame, text="🖐️ Manual",
            variable=self.trading_mode, value="manual",
            style="TRadiobutton", command=self.on_mode_switch,
        ).pack(side=tk.LEFT)

        # Status table
        self.status_frame = ttk.Frame(right_frame, style="Light.TFrame")
        self.status_frame.pack(fill=tk.X, pady=5)
        self.status_labels = self._create_status_table(self.status_frame)

        # Buttons
        self._create_control_buttons(right_frame)

        # Log notebook (at bottom of window)
        self._create_notebook()

    @staticmethod
    def _create_status_table(parent):
        """Create the grid of status labels; return dict keyed by field name."""
        labels = {}
        fields = [
            ("Position", "🟢"),
            ("Previous Position", "🟢"),
            ("Symbol", "💹"),
            ("Buy Price", "🛒"),
            ("Current Price", "💰"),
            ("Target Price", "💰"),
            ("Stoploss Price", "💰"),
            ("PnL", "💵"),
            ("Balance", "💵"),
            ("Derivative", "📈"),
            ("Supertrend", "✨"),
            ("Long Supertrend", "✨"),
            ("MACD", "📊"),
        ]
        for i, (field, icon) in enumerate(fields):
            ttk.Label(
                parent, text=f"{icon} {field}:", anchor="w",
                style="StatusBold.TLabel",
            ).grid(row=i, column=0, sticky="w", padx=(0, 10), pady=2)
            value = ttk.Label(parent, text="", anchor="w", style="StatusValue.TLabel")
            value.grid(row=i, column=1, sticky="w", padx=1, pady=2)
            labels[field] = value
        return labels

    def _create_control_buttons(self, parent):
        """Create Start / Stop / Buy Call / Buy Put / Exit buttons."""
        self.start_button = ttk.Button(parent, text="▶ Start App",
                                       command=self.start_app,
                                       style="Green.TButton", width=18)
        self.stop_button = ttk.Button(parent, text="■ Stop App",
                                      command=self.stop_app,
                                      style="Red.TButton", width=18)
        self.call_button = ttk.Button(parent, text="📈 Buy Call",
                                      command=self.buy_call,
                                      style="Blue.TButton", width=18)
        self.put_button = ttk.Button(parent, text="📉 Buy Put",
                                     command=self.buy_put,
                                     style="Purple.TButton", width=18)
        self.exit_button = ttk.Button(parent, text="🚪 Exit Position",
                                      command=self.exit_position,
                                      style="Orange.TButton", width=18)

        for btn in [self.start_button, self.stop_button,
                    self.call_button, self.put_button, self.exit_button]:
            btn.pack(fill=tk.X, pady=4)

        # Initial disabled state
        self.stop_button.config(state=tk.DISABLED)
        self.call_button.config(state=tk.DISABLED)
        self.put_button.config(state=tk.DISABLED)
        self.exit_button.config(state=tk.DISABLED)

    def _create_notebook(self):
        """Create the bottom notebook with the Logs tab."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        self.log_tab = ttk.Frame(self.notebook, style="Light.TFrame")
        self.log_text = tk.Text(
            self.log_tab, height=15, wrap="word",
            bg="#f8f9fb", fg="#00adb5", font=("Consolas", 9),
            insertbackground="#333333",
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.configure(state="disabled")
        self.notebook.add(self.log_tab, text=_TAB_LOGS)

    # ══════════════════════════════════════════════════════════════════════════
    # Tab management
    # ══════════════════════════════════════════════════════════════════════════

    def add_stats_tab(self):
        """Add (or replace) the Stats tab in the notebook."""
        if self.notebook is None or self.app is None:
            return
        try:
            # Remove existing Stats tab to avoid duplicates on reload
            for i in range(self.notebook.index("end")):
                if self.notebook.tab(i, "text") == _TAB_STATS:
                    self.notebook.forget(i)
                    break

            self.stats_tab = StatsTab(self.notebook, self.app.state)

            # Add the stats tab's frame to the notebook
            self.notebook.add(self.stats_tab.frame, text=_TAB_STATS)
            self.stats_tab_idx = self.notebook.index("end") - 1

        except Exception as e:
            logger.error(f"add_stats_tab error: {e}", exc_info=True)

    def update_trade_history(self):
        """Add (or replace) the Trade History tab."""
        if self.notebook is None:
            return
        try:
            # Remove existing tab to avoid duplicates on reload
            for i in range(self.notebook.index("end")):
                if self.notebook.tab(i, "text") == _TAB_HISTORY:
                    self.notebook.forget(i)
                    break
            self.trade_history_tab = TradeHistoryViewer(self.notebook)
            self.notebook.add(self.trade_history_tab, text=_TAB_HISTORY)
        except Exception as e:
            logger.error(f"update_trade_history error: {e}", exc_info=True)

    # ══════════════════════════════════════════════════════════════════════════
    # Logging
    # ══════════════════════════════════════════════════════════════════════════

    def setup_logger(self):
        """Attach the Tkinter TextHandler to the root logger."""
        try:
            handler = TextHandler(self.log_text)
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            )
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)

            # Remove any existing TextHandler to avoid duplicates
            for h in list(root_logger.handlers):
                if isinstance(h, TextHandler):
                    root_logger.removeHandler(h)

            root_logger.addHandler(handler)
        except Exception as e:
            logger.error(f"setup_logger error: {e}", exc_info=True)

    # ══════════════════════════════════════════════════════════════════════════
    # App lifecycle — Start / Stop
    # ══════════════════════════════════════════════════════════════════════════

    def start_app(self):
        """Start the trading engine in a background daemon thread."""
        if self.app is None:
            messagebox.showerror("Error", "Trading app not initialised. Check broker credentials.")
            return
        try:
            self.app_running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.update_button_states()
            threading.Thread(target=self._safe_run_app, daemon=True, name="TradingAppThread").start()
        except Exception as e:
            logger.error(f"start_app error: {e}", exc_info=True)
            self.app_running = False
            self.update_button_states()

    def _safe_run_app(self):
        """Run the trading app; report any crash back to the GUI thread."""
        try:
            self.app.run()
        except Exception as e:
            logger.error(f"App run crashed: {e}", exc_info=True)
            self.root.after(
                0,
                lambda: messagebox.showerror("Critical Error", f"App crashed:\n{e}"),
            )
        finally:
            self.app_running = False
            self.root.after(0, self._post_stop_cleanup)

    def stop_app(self):
        """Trigger a graceful stop in a background thread (non-blocking)."""
        self.stop_button.config(state=tk.DISABLED)
        threading.Thread(target=self._threaded_stop_app, daemon=True, name="StopAppThread").start()

    def _threaded_stop_app(self):
        """Background: exit any open position then clean up WebSocket."""
        try:
            if self.app and getattr(self.app.state, "current_position", None):
                self.app.executor.exit_position(self.app.state, reason="Stop app Exit")
            else:
                logger.warning("No active trade running.")
        except Exception as e:
            logger.error(f"Exit on stop error: {e}", exc_info=True)
            self.root.after(
                0,
                lambda: messagebox.showerror("Error", f"Error during stop/exit:\n{e}"),
            )
        finally:
            try:
                if self.app and hasattr(self.app, "ws") and self.app.ws is not None:
                    self.app.ws.unsubscribe()
            except Exception as e:
                logger.error(f"WebSocket unsubscribe error: {e}", exc_info=True)

            self.app_running = False
            logger.info("App stopped.")
            self.root.after(0, self._post_stop_cleanup)

    def _post_stop_cleanup(self):
        """Restore button states after the engine has stopped (main thread)."""
        try:
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.update_button_states()
        except Exception as e:
            logger.error(f"_post_stop_cleanup error: {e}", exc_info=True)

    # ══════════════════════════════════════════════════════════════════════════
    # Manual trading buttons
    # ══════════════════════════════════════════════════════════════════════════

    def buy_call(self):
        """Manual buy-call button handler."""
        if self.trading_mode.get() == "manual":
            threading.Thread(
                target=self._threaded_buy_option,
                args=(BaseEnums.CALL,),
                daemon=True,
                name="BuyCallThread",
            ).start()
        else:
            messagebox.showinfo("Mode Restriction",
                                "Manual trades are only allowed in 'Manual' mode.")

    def buy_put(self):
        """Manual buy-put button handler."""
        if self.trading_mode.get() == "manual":
            threading.Thread(
                target=self._threaded_buy_option,
                args=(BaseEnums.PUT,),
                daemon=True,
                name="BuyPutThread",
            ).start()
        else:
            messagebox.showinfo("Mode Restriction",
                                "Manual trades are only allowed in 'Manual' mode.")

    def _threaded_buy_option(self, option_type):
        """Background: execute a manual buy option order."""
        try:
            if self.app is None:
                raise RuntimeError("Trading app is not initialised.")
            self.app.executor.buy_option(self.app.state, option_type=option_type)
            self.root.after(0, self._refresh_trade_history)
        except Exception as e:
            logger.error(f"Buy option ({option_type}) error: {e}", exc_info=True)
            self.root.after(
                0,
                lambda: messagebox.showerror("Buy Option Error",
                                             f"Could not execute buy {option_type}:\n{e}"),
            )

    def exit_position(self):
        """Manual exit-position button handler."""
        if self.trading_mode.get() == "manual":
            threading.Thread(
                target=self._threaded_exit_position,
                daemon=True,
                name="ExitPositionThread",
            ).start()
        else:
            messagebox.showinfo("Mode Restriction",
                                "Manual exit is only allowed in 'Manual' mode.")

    def _threaded_exit_position(self):
        """Background: execute a manual position exit."""
        try:
            if self.app is None:
                raise RuntimeError("Trading app is not initialised.")
            self.app.executor.exit_position(self.app.state, reason="Manual Exit")
            self.root.after(0, self._refresh_trade_history)
        except Exception as e:
            logger.error(f"Exit position error: {e}", exc_info=True)
            self.root.after(
                0,
                lambda: messagebox.showerror("Exit Error",
                                             f"Could not exit position:\n{e}"),
            )

    # ══════════════════════════════════════════════════════════════════════════
    # Mode switch
    # ══════════════════════════════════════════════════════════════════════════

    def on_mode_switch(self):
        """Handle Algo / Manual radio button switch."""
        try:
            mode = self.trading_mode.get()
            logger.info(f"Trading mode switched to: {mode}")
            self.update_button_states()
        except Exception as e:
            logger.error(f"on_mode_switch error: {e}", exc_info=True)

    # ══════════════════════════════════════════════════════════════════════════
    # Status labels — periodic update loop
    # ══════════════════════════════════════════════════════════════════════════

    def _schedule_status_update(self):
        """Kick-off the 1-second status-label refresh loop."""
        self._status_update_pending = True
        self.root.after(1000, self._status_update_tick)

    def _status_update_tick(self):
        """Called every 1 s by root.after; updates labels then re-schedules itself."""
        self._status_update_pending = False
        if self._closing:
            return
        try:
            self._do_update_status_labels()
        except Exception as e:
            logger.error(f"Status label tick error: {e}", exc_info=True)
        finally:
            if not self._closing:
                self._status_update_pending = True
                self.root.after(1000, self._status_update_tick)

    def _do_update_status_labels(self):
        """Perform the actual status-label refresh (must run on main thread)."""
        if self.app is None or self.status_labels is None:
            return

        s = self.app.state
        trend = getattr(s, "derivative_trend", {}) or {}
        config = self.config

        short_st_dir = trend.get("super_trend_short", {}).get("direction") or []
        long_st_dir = trend.get("super_trend_long", {}).get("direction") or []
        macd_hist = trend.get("macd", {}).get("histogram") or []

        def _last(lst):
            return lst[-1] if isinstance(lst, (list, tuple)) and lst else None

        def _fmt(val, fmt=None):
            if val is None:
                return "-"
            try:
                return f"{val:{fmt}}" if fmt else str(val)
            except (ValueError, TypeError):
                return str(val)

        data = {
            "Position": getattr(s, "current_position", None) or "None",
            "Previous Position": getattr(s, "previous_position", None) or "None",
            "Symbol": getattr(s, "current_trading_symbol", None) or "No Position",
            "Buy Price": _fmt(getattr(s, "current_buy_price", None), ".2f"),
            "Current Price": _fmt(getattr(s, "current_price", None), ".2f"),
            "Derivative": _fmt(getattr(s, "derivative_current_price", None), ".2f"),
            "Supertrend": _fmt(_last(short_st_dir)),
            "Long Supertrend": _fmt(_last(long_st_dir)) if getattr(config, "use_long_st", False) else "-",
            "MACD": _fmt(_last(macd_hist), ".4f") if _last(macd_hist) is not None else "-",
            "PnL": _fmt(getattr(s, "percentage_change", None), ".2f") + "%" if getattr(s, "percentage_change",
                                                                                       None) is not None else "-",
            "Balance": _fmt(getattr(s, "account_balance", None), ".2f"),
            "Target Price": _fmt(getattr(s, "tp_point", None), ".2f"),
            "Stoploss Price": _fmt(getattr(s, "stop_loss", None), ".2f"),
        }

        for key, label in self.status_labels.items():
            try:
                text = str(data.get(key, "-"))
                if key == "PnL":
                    pnl = getattr(s, "percentage_change", 0) or 0
                    fg = "#43a047" if pnl > 0 else "#e53935" if pnl < 0 else "#bdbdbd"
                    label.config(text=text, foreground=fg)
                elif key == "Position":
                    fg = "#43a047" if getattr(s, "current_position", None) else "#bdbdbd"
                    label.config(text=text, foreground=fg)
                else:
                    label.config(text=text, foreground="#333333")
            except Exception as e:
                logger.warning(f"Label update failed for '{key}': {e}")

        self.update_button_states()

    # Keep the original public name as a proxy so external callers still work
    def update_status_labels(self):
        """Public alias — triggers an immediate label refresh."""
        try:
            self._do_update_status_labels()
        except Exception as e:
            logger.error(f"update_status_labels error: {e}", exc_info=True)

    # ══════════════════════════════════════════════════════════════════════════
    # Button state management — single source of truth
    # ══════════════════════════════════════════════════════════════════════════

    def update_button_states(self):
        """Set every button's enabled/disabled state from current app state."""
        try:
            has_position = (
                    self.app is not None
                    and getattr(self.app.state, "current_position", None) is not None
            )
            mode = self.trading_mode.get()

            if self.app_running:
                self.start_button.config(state=tk.DISABLED)
                self.stop_button.config(state=tk.NORMAL)
                if mode == "manual":
                    self.call_button.config(state=tk.DISABLED if has_position else tk.NORMAL)
                    self.put_button.config(state=tk.DISABLED if has_position else tk.NORMAL)
                    self.exit_button.config(state=tk.NORMAL if has_position else tk.DISABLED)
                else:  # algo mode
                    self.call_button.config(state=tk.DISABLED)
                    self.put_button.config(state=tk.DISABLED)
                    self.exit_button.config(state=tk.NORMAL if has_position else tk.DISABLED)
            else:
                self.start_button.config(state=tk.NORMAL)
                self.stop_button.config(state=tk.DISABLED)
                self.call_button.config(state=tk.DISABLED)
                self.put_button.config(state=tk.DISABLED)
                self.exit_button.config(state=tk.DISABLED)
        except Exception as e:
            logger.error(f"update_button_states error: {e}", exc_info=True)

    # ══════════════════════════════════════════════════════════════════════════
    # Chart — non-blocking periodic render
    # ══════════════════════════════════════════════════════════════════════════

    def _schedule_chart_update(self):
        """Kick-off the 10-second chart refresh loop."""
        self._chart_update_pending = True
        self.root.after(10000, self._chart_update_tick)

    def _chart_update_tick(self):
        """Called every 10 s; renders chart in background thread."""
        self._chart_update_pending = False
        if self._closing:
            return
        try:
            self.update_chart()
        except Exception as e:
            logger.error(f"Chart tick error: {e}", exc_info=True)
        finally:
            if not self._closing:
                self._chart_update_pending = True
                self.root.after(10000, self._chart_update_tick)

    # FIX: Added fingerprint method to avoid numpy comparison errors
    def _chart_fingerprint(self, trend_data: dict) -> str:
        """Create a lightweight fingerprint of trend data to detect changes."""
        # FIX: Use a cheap fingerprint instead of full dict equality (avoids numpy ValueError)
        try:
            close = trend_data.get("close") or []
            return f"{len(close)}:{close[-1] if close else None}"
        except Exception:
            return ""

    def update_chart(self):
        """Render the chart in a background thread; draw result on main thread."""
        if self._chart_render_pending or self._closing:
            return
        if self.app is None or self.canvas is None:
            return

        trend_data = getattr(self.app.state, "derivative_trend", {}) or {}

        # FIX: Compare fingerprint, not the full dict (which may contain numpy arrays)
        fp = self._chart_fingerprint(trend_data)
        if fp == self._last_chart_data:
            return
        # FIX: Store fingerprint, not the full dict
        self._last_chart_data = fp

        self._chart_render_pending = True

        threading.Thread(
            target=self._render_chart_background,
            args=(trend_data,),
            daemon=True,
            name="ChartRenderThread",
        ).start()

    def _render_chart_background(self, trend_data):
        """Prepare chart data off the main thread, then post drawing to main thread."""
        # FIX: Only prepare data here — no matplotlib calls on background thread
        try:
            prepared = self._prepare_plot_data(trend_data)
            if not self._closing:
                self.root.after(0, lambda: self._draw_chart_main_thread(prepared))
        except Exception as e:
            logger.error(f"Background chart render error: {e}", exc_info=True)
        finally:
            self._chart_render_pending = False

    # FIX: New method to prepare data safely off main thread
    def _prepare_plot_data(self, trend_data):
        """Extract and clean all series from trend_data — safe to run off main thread."""

        def clean(raw):
            if not raw:
                return []
            try:
                return [
                    float(x) if x is not None and str(x).lower() not in ("nan", "none")
                    else float('nan')
                    for x in raw
                ]
            except Exception:
                return []

        td = trend_data or {}
        return {
            "close": clean(td.get("close")),
            "st_short": clean((td.get("super_trend_short") or {}).get("trend")),
            "st_long": clean((td.get("super_trend_long") or {}).get("trend")),
            "bb_upper": clean((td.get("bb") or {}).get("upper")),
            "bb_mid": clean((td.get("bb") or {}).get("middle")),
            "bb_lower": clean((td.get("bb") or {}).get("lower")),
            "macd": clean((td.get("macd") or {}).get("macd")),
            "signal": clean((td.get("macd") or {}).get("signal")),
            "hist": clean((td.get("macd") or {}).get("histogram")),
            "rsi": clean(td.get("rsi_series")),
        }

    # FIX: All matplotlib operations now on main thread
    def _draw_chart_main_thread(self, p):
        """All matplotlib operations — called on main thread via root.after()."""
        # FIX: All fig/axes operations are now on the main thread
        try:
            self.fig.clear()
            axs = self.fig.subplots(
                3, 1, sharex=True, gridspec_kw={"height_ratios": [2, 1, 1]}
            )

            n = len(p["close"])
            x = range(n)

            # ── Subplot 0: Price + SuperTrend ─────────────────────────────────
            has_plot0_artists = False

            if p["close"]:
                axs[0].plot(x, p["close"], label="Close", color="royalblue", linewidth=2)
                has_plot0_artists = True

            if p["st_short"] and len(p["st_short"]) == n:
                axs[0].plot(x, p["st_short"], label="Short ST", color="orange",
                            linestyle="--", linewidth=1.7)
                has_plot0_artists = True

            if p["st_long"] and len(p["st_long"]) == n:
                axs[0].plot(x, p["st_long"], label="Long ST", color="purple",
                            linestyle="--", linewidth=1.7)
                has_plot0_artists = True

            axs[0].set_title("Close and SuperTrend")
            axs[0].set_ylabel("Price")
            if has_plot0_artists:
                axs[0].legend(loc="upper left", fontsize=8)
            axs[0].grid(True)

            # ── Subplot 1: MACD ───────────────────────────────────────────────
            has_plot1_artists = False

            if p["macd"] and len(p["macd"]) == n:
                axs[1].plot(x, p["macd"], label="MACD", color="black")
                has_plot1_artists = True
            if p["signal"] and len(p["signal"]) == n:
                axs[1].plot(x, p["signal"], label="MACD Signal", color="red")
                has_plot1_artists = True
            if p["hist"] and len(p["hist"]) == n:
                axs[1].bar(x, p["hist"], label="MACD Histogram", color="gray", alpha=0.4)
                has_plot1_artists = True

            axs[1].set_title("MACD")
            if has_plot1_artists:
                axs[1].legend(loc="upper left", fontsize=8)
            axs[1].grid(True)

            # ── Subplot 2: RSI ────────────────────────────────────────────────
            has_plot2_artists = False

            if p["rsi"] and len(p["rsi"]) == n:
                axs[2].plot(x, p["rsi"], label="RSI", color="magenta")
                axs[2].axhline(60, linestyle="--", color="red", alpha=0.5, label="Overbought (60)")
                axs[2].axhline(40, linestyle="--", color="green", alpha=0.5, label="Oversold (40)")
                has_plot2_artists = True

            axs[2].set_ylim(0, 100)
            axs[2].set_title("RSI")
            if has_plot2_artists:
                axs[2].legend(loc="upper left", fontsize=8)
            axs[2].grid(True)

            self.fig.tight_layout()
            self._safe_canvas_draw()

        except Exception as e:
            logger.error(f"_draw_chart_main_thread error: {e}", exc_info=True)

    # Keep method name for backward compatibility, but redirect
    def plot_full_charts(self, trend_data):
        """Legacy method kept for backward compatibility."""
        # FIX: Redirect to new thread-safe implementation
        prepared = self._prepare_plot_data(trend_data)
        self._draw_chart_main_thread(prepared)

    def _safe_canvas_draw(self):
        """Draw the canvas on the main thread; ignore errors if widget is gone."""
        try:
            if self.canvas and not self._closing:
                self.canvas.draw()
        except Exception as e:
            logger.warning(f"Canvas draw error: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Settings popups
    # ══════════════════════════════════════════════════════════════════════════

    def open_strategy_settings_popup(self):
        """Open strategy settings dialog."""
        try:
            StrategySettingGUI(self.root, self.strategy_setting)
        except Exception as e:
            logger.error(f"open_strategy_settings_popup error: {e}", exc_info=True)

    def open_daily_settings_popup(self):
        """Open daily trade settings dialog."""
        try:
            DailyTradeSettingGUI(self.root, daily_setting=self.daily_settings, app=self.app)
        except Exception as e:
            logger.error(f"open_daily_settings_popup error: {e}", exc_info=True)

    def profit_and_loss_setting_popup(self):
        """Open profit / stop-loss settings dialog."""
        try:
            ProfitStoplossSettingGUI(
                self.root,
                profit_stoploss_setting=self.profit_stoploss_setting,
                app=self.app,
            )
        except Exception as e:
            logger.error(f"profit_and_loss_setting_popup error: {e}", exc_info=True)

    def open_brokerage_settings_popup(self):
        """Open brokerage credentials dialog."""
        try:
            BrokerageSettingGUI(self.root, self.brokerage_setting)
        except Exception as e:
            logger.error(f"open_brokerage_settings_popup error: {e}", exc_info=True)

    def open_manual_login_popup(self):
        """Open Fyers manual login popup then reload the broker."""
        try:
            FyersManualLoginPopup(self.root, self.brokerage_setting)
            self.reload_broker()
        except Exception as e:
            logger.error(f"open_manual_login_popup error: {e}", exc_info=True)

    # ══════════════════════════════════════════════════════════════════════════
    # Broker reload
    # ══════════════════════════════════════════════════════════════════════════

    def reload_broker(self):
        """Recreate TradingApp after a fresh login and refresh all dependants."""
        try:
            # Stop running engine first
            if self.app_running:
                self._threaded_stop_app()
                self.app_running = False

            # Recreate the app
            self.app = self._create_trading_app()
            if self.app is None:
                return
            logger.info("Broker reloaded with refreshed access token.")

            # Refresh tabs
            self.add_stats_tab()
            self.update_trade_history()

            # Refresh UI
            self.update_status_labels()
            self.update_chart()
            self.update_button_states()

            messagebox.showinfo("Login Success",
                                "Fyers login successful. Trading engine reloaded.")
        except Exception as e:
            logger.error(f"reload_broker error: {e}", exc_info=True)
            messagebox.showerror("Reload Error", f"Failed to reload after login:\n{e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Utility / event handlers
    # ══════════════════════════════════════════════════════════════════════════

    def open_stats_window(self):
        """Switch to the Stats tab in the notebook."""
        try:
            if self.stats_tab_idx is not None:
                self.notebook.select(self.stats_tab_idx)
        except Exception as e:
            logger.error(f"open_stats_window error: {e}", exc_info=True)

    def _refresh_trade_history(self):
        """Refresh the trade-history tab if it exists and supports refresh()."""
        try:
            if (
                    self.trade_history_tab is not None
                    and hasattr(self.trade_history_tab, "refresh")
            ):
                self.trade_history_tab.refresh()
        except Exception as e:
            logger.error(f"_refresh_trade_history error: {e}", exc_info=True)

    def _refresh_all(self, event=None):
        """F5 handler — refresh labels, chart and trade history."""
        try:
            self.update_status_labels()
            self.update_chart()
            self._refresh_trade_history()
        except Exception as e:
            logger.error(f"_refresh_all error: {e}", exc_info=True)

    @staticmethod
    def _quick_save_settings(event=None):
        """Ctrl+S handler — placeholder for quick-save logic."""
        logger.info("Quick save triggered (not yet implemented).")

    # FIX: Poll until engine stops before destroying window
    def _on_closing(self, event=None):
        """Handle window close / Ctrl+Q — stop the engine then destroy."""
        try:
            self._closing = True
            if self.app_running:
                threading.Thread(
                    target=self._threaded_stop_app, daemon=True, name="CloseStopThread"
                ).start()
                # FIX: Poll until stopped, then destroy — don't destroy immediately
                self.root.after(200, self._poll_until_stopped_then_destroy)
            else:
                self._destroy_root()
        except Exception as e:
            logger.error(f"_on_closing stop error: {e}", exc_info=True)
            self._destroy_root()

    # FIX: New polling method
    def _poll_until_stopped_then_destroy(self):
        """Keep polling every 200 ms until engine stops, then destroy safely."""
        if self.app_running:
            self.root.after(200, self._poll_until_stopped_then_destroy)
        else:
            self._destroy_root()

    # FIX: New destroy method
    def _destroy_root(self):
        """Safely destroy the root window."""
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def _bind_events(self):
        """Bind keyboard shortcuts and window-close protocol."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.bind("<Control-q>", self._on_closing)
        self.root.bind("<F5>", self._refresh_all)
        self.root.bind("<Control-s>", self._quick_save_settings)

    @staticmethod
    def show_about():
        """Show the About dialog."""
        messagebox.showinfo(
            "About",
            (
                "Algo Trading Dashboard\n"
                "Version 1.0.0 (2025)\n\n"
                "A comprehensive platform for monitoring, analysing, and executing\n"
                "algorithmic trades in real-time.\n\n"
                "© 2025 Your Company Name. All rights reserved."
            ),
        )


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = TradingGUI(root)
    root.mainloop()
