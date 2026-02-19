import tkinter as tk
from tkinter import ttk, messagebox
import threading


class StrategySettingGUI:
    def __init__(self, parent, strategy_setting):
        self.parent = parent
        self.strategy_setting = strategy_setting

        self.window = tk.Toplevel(parent)
        self.window.title("Strategy Settings")
        self.window.configure(bg="#f4f6fa")
        self.window.resizable(False, False)
        self.window.grab_set()

        frame = ttk.Frame(self.window, padding="24 18 24 18", style="Light.TFrame")
        frame.grid(row=0, column=0, sticky="nsew")

        header = ttk.Label(frame, text="🛠️ Strategy Settings", font=("Segoe UI", 15, "bold"), style="Light.TLabel")
        header.grid(row=0, column=0, columnspan=3, pady=(0, 18))

        # -- Long Supertrend Group --
        long_st_frame = ttk.LabelFrame(frame, text="✨ Long Supertrend", padding=10)
        long_st_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 15), pady=6)

        self.use_long_st_entry_var = tk.BooleanVar(
            value=getattr(self.strategy_setting, 'use_long_st_entry', self.strategy_setting.use_long_st))
        long_st_entry_cb = ttk.Checkbutton(long_st_frame, text="Use for Entry", variable=self.use_long_st_entry_var,
                                           command=self.toggle_long_st)
        long_st_entry_cb.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.use_long_st_exit_var = tk.BooleanVar(value=getattr(self.strategy_setting, 'use_long_st_exit', False))
        long_st_exit_cb = ttk.Checkbutton(long_st_frame, text="Use for Exit", variable=self.use_long_st_exit_var,
                                          command=self.toggle_long_st)
        long_st_exit_cb.grid(row=0, column=1, sticky="w", pady=(0, 4))

        ttk.Label(long_st_frame, text="Length:").grid(row=1, column=0, sticky="e", padx=(0, 6))
        self.long_st_length_var = tk.IntVar(value=self.strategy_setting.long_st_length)
        self.long_st_length_entry = ttk.Entry(long_st_frame, textvariable=self.long_st_length_var, width=10)
        self.long_st_length_entry.grid(row=1, column=1, sticky="w")

        ttk.Label(long_st_frame, text="Multiplier:").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=(6, 0))
        self.long_st_multi_var = tk.DoubleVar(value=self.strategy_setting.long_st_multi)
        self.long_st_multi_entry = ttk.Entry(long_st_frame, textvariable=self.long_st_multi_var, width=10)
        self.long_st_multi_entry.grid(row=2, column=1, sticky="w", pady=(6, 0))

        # -- Short Supertrend Group --
        short_st_frame = ttk.LabelFrame(frame, text="✨ Short Supertrend", padding=10)
        short_st_frame.grid(row=1, column=1, sticky="nsew", padx=(0, 15), pady=6)

        self.use_short_st_entry_var = tk.BooleanVar(
            value=getattr(self.strategy_setting, 'use_short_st_entry', self.strategy_setting.use_short_st))
        short_st_entry_cb = ttk.Checkbutton(short_st_frame, text="Use for Entry", variable=self.use_short_st_entry_var,
                                            command=self.toggle_short_st)
        short_st_entry_cb.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.use_short_st_exit_var = tk.BooleanVar(value=getattr(self.strategy_setting, 'use_short_st_exit', False))
        short_st_exit_cb = ttk.Checkbutton(short_st_frame, text="Use for Exit", variable=self.use_short_st_exit_var,
                                           command=self.toggle_short_st)
        short_st_exit_cb.grid(row=0, column=1, sticky="w", pady=(0, 4))

        ttk.Label(short_st_frame, text="Length:").grid(row=1, column=0, sticky="e", padx=(0, 6))
        self.short_st_length_var = tk.IntVar(value=self.strategy_setting.short_st_length)
        self.short_st_length_entry = ttk.Entry(short_st_frame, textvariable=self.short_st_length_var, width=10)
        self.short_st_length_entry.grid(row=1, column=1, sticky="w")

        ttk.Label(short_st_frame, text="Multiplier:").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=(6, 0))
        self.short_st_multi_var = tk.DoubleVar(value=self.strategy_setting.short_st_multi)
        self.short_st_multi_entry = ttk.Entry(short_st_frame, textvariable=self.short_st_multi_var, width=10)
        self.short_st_multi_entry.grid(row=2, column=1, sticky="w", pady=(6, 0))

        # -- Bollinger Bands Group --
        bb_frame = ttk.LabelFrame(frame, text="📊 Bollinger Bands", padding=10)
        bb_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 15), pady=6)

        self.bb_entry_var = tk.BooleanVar(value=getattr(self.strategy_setting, 'bb_entry', False))
        bb_entry_cb = ttk.Checkbutton(bb_frame, text="Use for Entry", variable=self.bb_entry_var,
                                      command=self.toggle_bb)
        bb_entry_cb.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.bb_exit_var = tk.BooleanVar(value=self.strategy_setting.bb_exit)
        self.bb_exit_cb = ttk.Checkbutton(bb_frame, text="Use for Exit", variable=self.bb_exit_var,
                                          command=self.toggle_bb)
        self.bb_exit_cb.grid(row=0, column=1, sticky="w", pady=(0, 4))

        ttk.Label(bb_frame, text="Length:").grid(row=1, column=0, sticky="e", padx=(0, 6))
        self.bb_length_var = tk.IntVar(value=self.strategy_setting.bb_length)
        self.bb_length_entry = ttk.Entry(bb_frame, textvariable=self.bb_length_var, width=10)
        self.bb_length_entry.grid(row=1, column=1, sticky="w")

        ttk.Label(bb_frame, text="Std Dev:").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=(6, 0))
        self.bb_std_var = tk.DoubleVar(value=self.strategy_setting.bb_std)
        self.bb_std_entry = ttk.Entry(bb_frame, textvariable=self.bb_std_var, width=10)
        self.bb_std_entry.grid(row=2, column=1, sticky="w", pady=(6, 0))

        # -- MACD Group --
        macd_frame = ttk.LabelFrame(frame, text="📈 MACD", padding=10)
        macd_frame.grid(row=2, column=1, sticky="nsew", padx=(0, 15), pady=6)

        self.use_macd_entry_var = tk.BooleanVar(
            value=getattr(self.strategy_setting, 'use_macd_entry', self.strategy_setting.use_macd))
        macd_entry_cb = ttk.Checkbutton(macd_frame, text="Use for Entry", variable=self.use_macd_entry_var,
                                        command=self.toggle_macd)
        macd_entry_cb.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.use_macd_exit_var = tk.BooleanVar(value=getattr(self.strategy_setting, 'use_macd_exit', False))
        macd_exit_cb = ttk.Checkbutton(macd_frame, text="Use for Exit", variable=self.use_macd_exit_var,
                                       command=self.toggle_macd)
        macd_exit_cb.grid(row=0, column=1, sticky="w", pady=(0, 4))

        ttk.Label(macd_frame, text="Fast Period:").grid(row=1, column=0, sticky="e", padx=(0, 6))
        self.macd_fast_var = tk.IntVar(value=self.strategy_setting.macd_fast)
        self.macd_fast_entry = ttk.Entry(macd_frame, textvariable=self.macd_fast_var, width=10)
        self.macd_fast_entry.grid(row=1, column=1, sticky="w")

        ttk.Label(macd_frame, text="Slow Period:").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=(6, 0))
        self.macd_slow_var = tk.IntVar(value=self.strategy_setting.macd_slow)
        self.macd_slow_entry = ttk.Entry(macd_frame, textvariable=self.macd_slow_var, width=10)
        self.macd_slow_entry.grid(row=2, column=1, sticky="w", pady=(6, 0))

        ttk.Label(macd_frame, text="Signal Period:").grid(row=3, column=0, sticky="e", padx=(0, 6), pady=(6, 0))
        self.macd_signal_var = tk.IntVar(value=self.strategy_setting.macd_signal)
        self.macd_signal_entry = ttk.Entry(macd_frame, textvariable=self.macd_signal_var, width=10)
        self.macd_signal_entry.grid(row=3, column=1, sticky="w", pady=(6, 0))

        # -- RSI Group --
        rsi_frame = ttk.LabelFrame(frame, text="🔄 RSI", padding=10)
        rsi_frame.grid(row=3, column=0, sticky="nsew", padx=(0, 15), pady=6)

        self.use_rsi_entry_var = tk.BooleanVar(
            value=getattr(self.strategy_setting, 'use_rsi_entry', self.strategy_setting.use_rsi))
        rsi_entry_cb = ttk.Checkbutton(rsi_frame, text="Use for Entry", variable=self.use_rsi_entry_var,
                                       command=self.toggle_rsi)
        rsi_entry_cb.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.use_rsi_exit_var = tk.BooleanVar(value=getattr(self.strategy_setting, 'use_rsi_exit', False))
        rsi_exit_cb = ttk.Checkbutton(rsi_frame, text="Use for Exit", variable=self.use_rsi_exit_var,
                                      command=self.toggle_rsi)
        rsi_exit_cb.grid(row=0, column=1, sticky="w", pady=(0, 4))

        ttk.Label(rsi_frame, text="RSI Length:").grid(row=1, column=0, sticky="e", padx=(0, 6))
        self.rsi_length_var = tk.IntVar(value=self.strategy_setting.rsi_length)
        self.rsi_length_entry = ttk.Entry(rsi_frame, textvariable=self.rsi_length_var, width=10)
        self.rsi_length_entry.grid(row=1, column=1, sticky="w")

        # Save button spanning two columns below groups
        save_btn = ttk.Button(frame, text="💾 Save", command=self.save_settings)
        save_btn.grid(row=4, column=0, columnspan=2, pady=(14, 0), sticky="ew")

        # Keyboard shortcuts
        self.window.bind("<Return>", lambda e: self.save_settings())
        self.window.bind("<Escape>", lambda e: self.window.destroy())
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

        # Initialize state of entries
        self.toggle_long_st()
        self.toggle_short_st()
        self.toggle_bb()
        self.toggle_macd()
        self.toggle_rsi()

    def toggle_long_st(self):
        state = "normal" if (self.use_long_st_entry_var.get() or self.use_long_st_exit_var.get()) else "disabled"
        self.long_st_length_entry.configure(state=state)
        self.long_st_multi_entry.configure(state=state)

    def toggle_short_st(self):
        state = "normal" if (self.use_short_st_entry_var.get() or self.use_short_st_exit_var.get()) else "disabled"
        self.short_st_length_entry.configure(state=state)
        self.short_st_multi_entry.configure(state=state)

    def toggle_bb(self):
        state = "normal" if (self.bb_entry_var.get() or self.bb_exit_var.get()) else "disabled"
        self.bb_length_entry.configure(state=state)
        self.bb_std_entry.configure(state=state)

    def toggle_macd(self):
        state = "normal" if (self.use_macd_entry_var.get() or self.use_macd_exit_var.get()) else "disabled"
        self.macd_fast_entry.configure(state=state)
        self.macd_slow_entry.configure(state=state)
        self.macd_signal_entry.configure(state=state)

    def toggle_rsi(self):
        state = "normal" if (self.use_rsi_entry_var.get() or self.use_rsi_exit_var.get()) else "disabled"
        self.rsi_length_entry.configure(state=state)

    def save_settings(self):
        # Run the save logic in a background thread for responsiveness
        threading.Thread(target=self._threaded_save_settings, daemon=True).start()

    def _threaded_save_settings(self):
        try:
            # Long Supertrend
            self.strategy_setting.use_long_st_entry = self.use_long_st_entry_var.get()
            self.strategy_setting.use_long_st_exit = self.use_long_st_exit_var.get()
            self.strategy_setting.use_long_st = self.use_long_st_entry_var.get()  # Maintain backward compatibility
            self.strategy_setting.long_st_length = self.long_st_length_var.get()
            self.strategy_setting.long_st_multi = self.long_st_multi_var.get()

            # Short Supertrend
            self.strategy_setting.use_short_st_entry = self.use_short_st_entry_var.get()
            self.strategy_setting.use_short_st_exit = self.use_short_st_exit_var.get()
            self.strategy_setting.use_short_st = self.use_short_st_entry_var.get()  # Maintain backward compatibility
            self.strategy_setting.short_st_length = self.short_st_length_var.get()
            self.strategy_setting.short_st_multi = self.short_st_multi_var.get()

            # Bollinger Bands
            self.strategy_setting.bb_entry = self.bb_entry_var.get()
            self.strategy_setting.bb_exit = self.bb_exit_var.get()
            self.strategy_setting.bb_length = self.bb_length_var.get()
            self.strategy_setting.bb_std = self.bb_std_var.get()

            # MACD
            self.strategy_setting.use_macd_entry = self.use_macd_entry_var.get()
            self.strategy_setting.use_macd_exit = self.use_macd_exit_var.get()
            self.strategy_setting.use_macd = self.use_macd_entry_var.get()  # Maintain backward compatibility
            self.strategy_setting.macd_fast = self.macd_fast_var.get()
            self.strategy_setting.macd_slow = self.macd_slow_var.get()
            self.strategy_setting.macd_signal = self.macd_signal_var.get()

            # RSI
            self.strategy_setting.use_rsi_entry = self.use_rsi_entry_var.get()
            self.strategy_setting.use_rsi_exit = self.use_rsi_exit_var.get()
            self.strategy_setting.use_rsi = self.use_rsi_entry_var.get()  # Maintain backward compatibility
            self.strategy_setting.rsi_length = self.rsi_length_var.get()

            self.strategy_setting.save()
            self.window.after(0,
                              lambda: messagebox.showinfo("Settings", "Strategy settings saved!", parent=self.window))
            self.window.after(0, self.window.destroy)
        except Exception as e:
            self.window.after(0, lambda: messagebox.showerror("Error", f"Invalid setting: {e}", parent=self.window))
