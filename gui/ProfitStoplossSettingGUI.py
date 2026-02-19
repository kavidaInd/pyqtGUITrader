import tkinter as tk
from tkinter import ttk, messagebox, StringVar
from gui import ProfitStoplossSetting
from BaseEnums import STOP, TRAILING
import threading


class ProfitStoplossSettingGUI(tk.Toplevel):
    def __init__(self, master, profit_stoploss_setting: ProfitStoplossSetting, app=None):
        super().__init__(master)
        self.profit_type_var = None
        self.title("Profit/Stoploss Setting")
        self.profit_stoploss_setting = profit_stoploss_setting
        self.app = app
        self.vars = {}
        self.entries = {}
        self.configure(bg="#f4f6fa")
        self.resizable(False, False)
        self.grab_set()
        self._setup_styles()
        self.fields = [
            ("Take Profit", "tp_percentage", float, "💰"),
            ("Stoploss", "stoploss_percentage", float, "🛑"),
            ("Trailing First Profit", "trailing_first_profit", float, "📈"),
            ("Max Profit", "max_profit", float, "🏆"),
            ("Profit Step", "profit_step", float, "➕"),
            ("Loss Step", "loss_step", float, "➖"),
        ]
        self.create_widgets()
        self.bind("<Return>", lambda e: self.save_settings())
        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("Light.TFrame", background="#f4f6fa")
        style.configure("Light.TLabel", background="#f4f6fa", foreground="#333333")
        style.configure("Header.TLabel", font=("Segoe UI", 15, "bold"), background="#f4f6fa", foreground="#222831")

    def create_widgets(self):
        frame = ttk.Frame(self, padding="24 18 24 18", style="Light.TFrame")
        frame.grid(row=0, column=0, sticky="nsew")

        header = ttk.Label(frame, text="💹 Profit/Stoploss Settings", style="Header.TLabel")
        header.grid(row=0, column=0, columnspan=2, pady=(0, 18))

        ttk.Label(frame, text="💰 Profit Type:", style="Light.TLabel", font=("Segoe UI", 10)).grid(
            row=1, column=0, sticky="e", padx=(0, 12), pady=6
        )
        profit_type_value = STOP if self.profit_stoploss_setting.profit_type == STOP else TRAILING
        profit_type_str = "STOP" if profit_type_value == STOP else "TRAILING"
        self.profit_type_var = StringVar(value=profit_type_str)
        profit_type_combo = ttk.Combobox(
            frame, textvariable=self.profit_type_var,
            values=["STOP", "TRAILING"], state="readonly", width=25
        )
        profit_type_combo.grid(row=1, column=1, sticky="w", pady=6)
        profit_type_combo.bind("<<ComboboxSelected>>", self._on_profit_type_change)
        self.vars["profit_type"] = self.profit_type_var

        first_entry = None
        for idx, (label, key, typ, icon) in enumerate(self.fields, start=2):
            ttk.Label(frame, text=f"{icon} {label}:", style="Light.TLabel", font=("Segoe UI", 10)).grid(
                row=idx, column=0, sticky="e", padx=(0, 12), pady=6
            )
            val = getattr(self.profit_stoploss_setting, key, 0)
            var = tk.DoubleVar(value=val if val is not None else 0)
            entry = ttk.Entry(frame, textvariable=var, width=28)
            entry.grid(row=idx, column=1, sticky="w", pady=6)
            self.vars[key] = var
            self.entries[key] = entry
            if first_entry is None:
                first_entry = entry
        if first_entry:
            first_entry.focus_set()

        sep = ttk.Separator(frame, orient="horizontal")
        sep.grid(row=len(self.fields) + 2, column=0, columnspan=2, sticky="ew", pady=(12, 6))

        btn_frame = ttk.Frame(frame, style="Light.TFrame")
        btn_frame.grid(row=len(self.fields) + 3, column=0, columnspan=2, pady=(6, 0), sticky="ew")

        save_btn = ttk.Button(btn_frame, text="💾 Save", command=self.save_settings)
        save_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        cancel_btn = ttk.Button(btn_frame, text="❌ Cancel", command=self.destroy)
        cancel_btn.pack(side="left", fill="x", expand=True)

        # Set initial state of entries based on current profit_type
        self._on_profit_type_change()

    def _on_profit_type_change(self, event=None):
        selected = self.profit_type_var.get()
        # Only enable trailing fields in TRAILING mode, always enable TP/SL
        trailing_keys = {"trailing_first_profit", "max_profit", "profit_step", "loss_step"}
        for key, entry in self.entries.items():
            if key in trailing_keys:
                entry.config(state="normal" if selected == "TRAILING" else "disabled")
            else:
                entry.config(state="normal")

    def save_settings(self):
        # Run the save logic in a background thread for responsiveness
        threading.Thread(target=self._threaded_save_settings, daemon=True).start()

    def _threaded_save_settings(self):
        try:
            # Validate numeric input
            for key, var in self.vars.items():
                value = var.get()
                if key == "profit_type":
                    self.profit_stoploss_setting.profit_type = STOP if value == "STOP" else TRAILING
                else:
                    try:
                        value = float(value)
                    except Exception:
                        self.after(0, lambda k=key: messagebox.showerror(
                            "Error", f"{k.replace('_', ' ').title()} must be a number.", parent=self))
                        return
                    self.profit_stoploss_setting.__setattr__(key, value)
            self.profit_stoploss_setting.save()
            if self.app and hasattr(self.app, "refresh_settings_live"):
                self.after(0, self.app.refresh_settings_live)
            self.after(0, lambda: messagebox.showinfo("Saved", "Profit/Stoploss settings saved!", parent=self))
            self.after(0, self.destroy)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Failed to save settings: {e}", parent=self))