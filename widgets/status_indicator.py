import tkinter as tk
from tkinter import ttk
import logging
import logging.handlers
import traceback
from typing import Optional, Dict, Any

from theme import TradingTheme

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class StatusIndicator(ttk.Frame):
    def __init__(self, master, text: str, **kwargs):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(master, style="Card.TFrame", **kwargs)

            # Rule 6: Input validation
            if master is None:
                logger.error("StatusIndicator initialized with None master")

            if text is None:
                logger.warning("StatusIndicator initialized with None text")
                text = ""

            # Create indicator circle
            self.indicator = tk.Canvas(self,
                                       width=10,
                                       height=10,
                                       bg=TradingTheme.COLORS.get('bg_secondary', '#2d2d2d'),
                                       highlightthickness=0)
            self.indicator.pack(side="left", padx=5)

            # Create label
            self.label = ttk.Label(self,
                                   text=text,
                                   style="Primary.TLabel")
            self.label.pack(side="left", padx=5)

            self.set_state("inactive")

            logger.debug(f"StatusIndicator initialized with text: {text}")

        except Exception as e:
            logger.critical(f"[StatusIndicator.__init__] Failed: {e}", exc_info=True)
            # Still try to create basic widget
            super().__init__(master, **kwargs)
            self.indicator = None
            self.label = None

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.indicator = None
        self.label = None

    def set_state(self, state: str):
        """
        Update the indicator state with the correct theme colors

        Args:
            state: One of 'active', 'warning', 'error', 'inactive'
        """
        try:
            # Rule 6: Input validation
            if self.indicator is None:
                logger.warning("set_state called with None indicator")
                return

            if not isinstance(state, str):
                logger.warning(f"set_state called with non-string state: {state}")
                state = "inactive"

            colors = {
                "active": TradingTheme.COLORS.get('accent_success', '#00ff00'),  # Default green
                "warning": TradingTheme.COLORS.get('accent_warning', '#ffff00'),  # Default yellow
                "error": TradingTheme.COLORS.get('accent_danger', '#ff0000'),  # Default red
                "inactive": TradingTheme.COLORS.get('text_tertiary', '#808080')  # Default gray
            }

            color = colors.get(state.lower(), colors['inactive'])

            # Clear existing drawing and draw new circle
            try:
                self.indicator.delete("all")
                self.indicator.create_oval(2, 2, 8, 8, fill=color, outline=color)
                logger.debug(f"Set indicator state to: {state}")
            except tk.TclError as e:
                logger.error(f"Failed to draw indicator: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[StatusIndicator.set_state] Failed: {e}", exc_info=True)

    def set_text(self, text: str):
        """Update the indicator text"""
        try:
            # Rule 6: Input validation
            if self.label is None:
                logger.warning("set_text called with None label")
                return

            if text is None:
                logger.warning("set_text called with None text")
                text = ""

            self.label.config(text=text)
            logger.debug(f"Set indicator text to: {text}")

        except tk.TclError as e:
            logger.error(f"Tcl error setting text: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[StatusIndicator.set_text] Failed: {e}", exc_info=True)

    def set_style(self, style: str):
        """Update the indicator style"""
        try:
            # Rule 6: Input validation
            if self.label is None:
                logger.warning("set_style called with None label")
                return

            if not isinstance(style, str):
                logger.warning(f"set_style called with non-string style: {style}")
                return

            self.label.configure(style=style)
            logger.debug(f"Set indicator style to: {style}")

        except tk.TclError as e:
            logger.error(f"Tcl error setting style: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[StatusIndicator.set_style] Failed: {e}", exc_info=True)

    def get_state(self) -> str:
        """Get current indicator state by analyzing the circle color"""
        try:
            if self.indicator is None:
                logger.warning("get_state called with None indicator")
                return "inactive"

            # Try to get the fill color of the oval
            try:
                # Get the first item's fill color (assuming it's the oval)
                items = self.indicator.find_all()
                if items:
                    color = self.indicator.itemcget(items[0], "fill")

                    # Reverse lookup the state from color
                    for state, state_color in [
                        ("active", TradingTheme.COLORS.get('accent_success', '#00ff00')),
                        ("warning", TradingTheme.COLORS.get('accent_warning', '#ffff00')),
                        ("error", TradingTheme.COLORS.get('accent_danger', '#ff0000')),
                        ("inactive", TradingTheme.COLORS.get('text_tertiary', '#808080'))
                    ]:
                        if color == state_color:
                            return state
            except tk.TclError as e:
                logger.warning(f"Failed to get indicator color: {e}")

            return "inactive"

        except Exception as e:
            logger.error(f"[StatusIndicator.get_state] Failed: {e}", exc_info=True)
            return "inactive"

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before destruction"""
        try:
            logger.info("[StatusIndicator] Starting cleanup")

            # Clear references
            self.indicator = None
            self.label = None

            logger.info("[StatusIndicator] Cleanup completed")

        except Exception as e:
            logger.error(f"[StatusIndicator.cleanup] Error: {e}", exc_info=True)

    def destroy(self):
        """Override destroy to ensure cleanup"""
        try:
            self.cleanup()
            super().destroy()
        except Exception as e:
            logger.error(f"[StatusIndicator.destroy] Failed: {e}", exc_info=True)
            super().destroy()