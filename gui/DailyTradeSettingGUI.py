import tkinter as tk
from tkinter import ttk, messagebox

from gui.DailyTradeSetting import DailyTradeSetting
import threading


class DailyTradeSettingGUI(tk.Toplevel):
    INTERVAL_CHOICES = [
        ("5 seconds", "5S"),
        ("10 seconds", "10S"),
        ("15 seconds", "15S"),
        ("30 seconds", "30S"),
        ("45 seconds", "45S"),
        ("1 minute", "1m"),
        ("2 minutes", "2m"),
        ("2 minutes", "2m"),
        ("3 minutes", "3m"),
        ("5 minutes", "5m"),
        ("10 minutes", "10m"),
        ("15 minutes", "15m"),
        ("20 minutes", "20m"),
        ("30 minutes", "30m"),
        ("60 minutes", "60m"),
        ("120 minutes", "120m"),
        ("240 minutes", "240m")
    ]

    def __init__(self, master, daily_setting: DailyTradeSetting, app=None):
        super().__init__(master)
        self.sideway_var = None
        self.fields = None
        self.title("Daily Trade Setting")
        self.daily_setting = daily_setting
        self.app = app
        self.vars = {}
        self.configure(bg="#f4f6fa")
        self.resizable(False, False)
        self.grab_set()
        self._setup_styles()
        self.create_widgets()
        self.bind("<Return>", lambda e: self.save_settings())
        self.bind("<Escape>", lambda e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("Light.TFrame", background="#f4f6fa")
        style.configure("Light.TLabel", background="#f4f6fa", foreground="#333333")
        style.configure("Header.TLabel", font=("Segoe UI", 15, "bold"), background="#f4f6fa", foreground="#222831")
        style.configure("Light.TCheckbutton",
                        background="#f4f6fa",
                        foreground="#333333",
                        font=("Segoe UI", 10))

    def create_widgets(self):
        frame = ttk.Frame(self, padding="24 18 24 18", style="Light.TFrame")
        frame.grid(row=0, column=0, sticky="nsew")

        header = ttk.Label(frame, text="⚙️ Daily Trade Settings", style="Header.TLabel")
        header.grid(row=0, column=0, columnspan=2, pady=(0, 18))

        self.fields = [
            ("Exchange", "exchange", tk.StringVar, "🌐"),
            ("Week", "week", tk.IntVar, "📆"),
            ("Derivative", "derivative", tk.StringVar, "💡"),
            ("Lot Size", "lot_size", tk.IntVar, "🔢"),
            ("Call Lookback", "call_lookback", tk.IntVar, "🔎"),
            ("Put Lookback", "put_lookback", tk.IntVar, "🔎"),
            # ("History Interval", "history_interval", tk.StringVar, "⏱️"), # replaced below with Combo
            ("Max Num of Option", "max_num_of_option", tk.IntVar, "📈"),
            ("Lower Percentage", "lower_percentage", tk.DoubleVar, "🔻"),
            ("Cancel After", "cancel_after", tk.IntVar, "⏰"),
            ("Capital Reserve", "capital_reserve", tk.IntVar, "💰"),
        ]

        first_entry = None
        for idx, (label, key, var_class, icon) in enumerate(self.fields, start=1):
            ttk.Label(frame, text=f"{icon} {label}:", style="Light.TLabel", font=("Segoe UI", 10)).grid(
                row=idx, column=0, sticky="e", padx=(0, 12), pady=6)
            val = self.daily_setting.data.get(key, "" if var_class is tk.StringVar else 0)
            var = var_class(value=val)
            entry = ttk.Entry(frame, textvariable=var, width=28)
            entry.grid(row=idx, column=1, sticky="w", pady=6)
            self.vars[key] = var
            if first_entry is None:
                first_entry = entry

        # History Interval as Combobox
        interval_label_idx = 7  # 1-based row (after 6th real field)
        interval_label = ttk.Label(frame, text="⏱️ History Interval:", style="Light.TLabel", font=("Segoe UI", 10))
        interval_label.grid(row=interval_label_idx, column=0, sticky="e", padx=(0, 12), pady=6)

        self.interval_var = tk.StringVar(value=self.daily_setting.data.get("history_interval", "2m"))
        interval_combo = ttk.Combobox(
            frame,
            textvariable=self.interval_var,
            state="readonly",
            values=[label for label, val in self.INTERVAL_CHOICES],
            width=25
        )
        # Set initial selection
        current_val = self.daily_setting.data.get("history_interval", "2m")
        for i, (label, val) in enumerate(self.INTERVAL_CHOICES):
            if val == current_val:
                interval_combo.current(i)
                break
        else:
            interval_combo.current(3)  # default to "2m"
        interval_combo.grid(row=interval_label_idx, column=1, sticky="w", pady=6)

        if first_entry:
            first_entry.focus_set()

        # Add Sideway Zone Trade label and checkmark (checkbox) on the right
        sideway_label = ttk.Label(frame, text="📊 Trade in Sideway Zone:", style="Light.TLabel", font=("Segoe UI", 10))
        sideway_label.grid(row=len(self.fields) + 1, column=0, sticky="e", padx=(0, 12), pady=(8, 4))

        self.sideway_var = tk.BooleanVar(value=self.daily_setting.data.get("sideway_zone_trade", False))
        chk = ttk.Checkbutton(
            frame,
            variable=self.sideway_var,
            style="Light.TCheckbutton"
        )
        chk.grid(row=len(self.fields) + 1, column=1, sticky="w", pady=(8, 4))

        sep = ttk.Separator(frame, orient="horizontal")
        sep.grid(row=len(self.fields) + 2, column=0, columnspan=2, sticky="ew", pady=(12, 6))

        save_btn = ttk.Button(frame, text="💾 Save", command=self.save_settings)
        save_btn.grid(row=len(self.fields) + 3, column=0, columnspan=2, pady=(6, 0), sticky="ew")

    def save_settings(self):
        # Run the save logic in a background thread for responsiveness
        threading.Thread(target=self._threaded_save_settings, daemon=True).start()

    def _threaded_save_settings(self):
        try:
            new_data = {}
            for label, key, var_class, icon in self.fields:
                v = self.vars[key].get()
                if var_class is tk.StringVar:
                    v = str(v).strip()
                elif var_class is tk.DoubleVar:
                    try:
                        v = float(v)
                    except Exception:
                        self.after(0, lambda: messagebox.showerror("Error", f"{label} must be a number.", parent=self))
                        return
                elif var_class is tk.IntVar:
                    try:
                        v = int(float(v))
                    except Exception:
                        self.after(0,
                                   lambda: messagebox.showerror("Error", f"{label} must be an integer.", parent=self))
                        return
                new_data[key] = v

            # Set history_interval from ComboBox selection
            selected_label = self.interval_var.get()
            for label, val in self.INTERVAL_CHOICES:
                if label == selected_label:
                    new_data["history_interval"] = val
                    break
            else:
                new_data["history_interval"] = "2m"  # fallback

            # Add sideway_zone_trade value
            new_data["sideway_zone_trade"] = self.sideway_var.get()

            self.daily_setting.data.update(new_data)
            self.daily_setting.save()

            if self.app is not None:
                # call refresh from main thread
                self.after(0, self.app.refresh_settings_live)

            self.after(0, lambda: messagebox.showinfo("Saved", "Daily trade settings saved!", parent=self))
            self.after(0, self._close)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Failed to save settings: {e}", parent=self))

    def _close(self):
        self.grab_release()
        self.destroy()
