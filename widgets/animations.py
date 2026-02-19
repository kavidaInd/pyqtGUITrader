import tkinter as tk
from typing import Callable
import math


class Animator:
    @staticmethod
    def pulse(widget: tk.Widget,
              duration: int = 1000,
              min_opacity: float = 0.4,
              max_opacity: float = 1.0,
              callback: Callable = None):
        """Create a smooth pulse animation"""
        steps = 20
        step_time = duration / steps

        def update_opacity(step: int = 0):
            progress = step / steps
            opacity = min_opacity + (max_opacity - min_opacity) * \
                      (math.sin(progress * math.pi * 2) + 1) / 2

            if hasattr(widget, 'set_opacity'):
                widget.set_opacity(opacity)
            elif isinstance(widget, tk.Label):
                # Convert opacity to hex color with alpha
                current_color = widget.cget('fg')
                alpha_color = f"{current_color}{int(opacity * 255):02x}"
                widget.configure(fg=alpha_color)

            if callback:
                callback(opacity)

            if widget.winfo_exists():
                widget.after(int(step_time),
                             lambda: update_opacity((step + 1) % steps))

        update_opacity()