import tkinter as tk
from tkinter import ttk
from theme import TradingTheme


class StatusIndicator(ttk.Frame):
    def __init__(self, master, text: str, **kwargs):
        super().__init__(master, style="Card.TFrame", **kwargs)

        # Create indicator circle
        self.indicator = tk.Canvas(self,
                                   width=10,
                                   height=10,
                                   bg=TradingTheme.COLORS['bg_secondary'],
                                   highlightthickness=0)
        self.indicator.pack(side="left", padx=5)

        # Create label
        self.label = ttk.Label(self,
                               text=text,
                               style="Primary.TLabel")
        self.label.pack(side="left", padx=5)

        self.set_state("inactive")

    def set_state(self, state: str):
        """Update the indicator state with the correct theme colors"""
        colors = {
            "active": TradingTheme.COLORS['accent_success'],  # Using the correct theme color
            "warning": TradingTheme.COLORS['accent_warning'],  # Using the correct theme color
            "error": TradingTheme.COLORS['accent_danger'],  # Using the correct theme color
            "inactive": TradingTheme.COLORS['text_tertiary']  # Using the correct theme color
        }
        color = colors.get(state, colors['inactive'])
        self.indicator.create_oval(2, 2, 8, 8, fill=color, outline=color)

    def set_text(self, text: str):
        """Update the indicator text"""
        self.label.config(text=text)

    def set_style(self, style: str):
        """Update the indicator style"""
        self.label.configure(style=style)