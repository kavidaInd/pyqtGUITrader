import tkinter as tk
from tkinter import ttk
from typing import Optional


class ModernToolTip:
    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.tooltip: Optional[tk.Toplevel] = None
        self.widget.bind('<Enter>', self.show_tooltip)
        self.widget.bind('<Leave>', self.hide_tooltip)

    def show_tooltip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20

        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")

        frame = ttk.Frame(self.tooltip, style="Card.TFrame", padding=4)
        frame.pack(expand=True, fill="both")

        label = ttk.Label(frame,
                          text=self.text,
                          style="Trading.TLabel",
                          font=("Segoe UI", 9))
        label.pack()

    def hide_tooltip(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None
