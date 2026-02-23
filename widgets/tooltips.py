import tkinter as tk
from tkinter import ttk
import logging
import logging.handlers
import traceback
from typing import Optional

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class ModernToolTip:
    def __init__(self, widget: tk.Widget, text: str):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if widget is None:
                logger.error("ModernToolTip initialized with None widget")
                return

            if text is None:
                logger.warning("ModernToolTip initialized with None text")
                text = ""

            self.widget = widget
            self.text = text
            self.tooltip: Optional[tk.Toplevel] = None

            # Bind events
            try:
                self.widget.bind('<Enter>', self.show_tooltip)
                self.widget.bind('<Leave>', self.hide_tooltip)
            except tk.TclError as e:
                logger.error(f"Failed to bind events to widget: {e}", exc_info=True)

            logger.debug(f"ModernToolTip initialized for widget {widget}")

        except Exception as e:
            logger.critical(f"[ModernToolTip.__init__] Failed: {e}", exc_info=True)
            self.widget = widget
            self.text = text or ""
            self.tooltip = None

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.widget = None
        self.text = ""
        self.tooltip = None

    def show_tooltip(self, event=None):
        """Show the tooltip window"""
        try:
            # Check if widget still exists
            if self.widget is None:
                logger.warning("show_tooltip called with None widget")
                return

            # Validate widget existence
            try:
                if not self.widget.winfo_exists():
                    logger.debug("Widget no longer exists, cannot show tooltip")
                    return
            except tk.TclError:
                logger.debug("Widget was destroyed, cannot show tooltip")
                return

            # Get widget position
            try:
                x, y, _, _ = self.widget.bbox("insert")
                x += self.widget.winfo_rootx() + 25
                y += self.widget.winfo_rooty() + 20
            except tk.TclError as e:
                logger.error(f"Failed to get widget coordinates: {e}", exc_info=True)
                return
            except Exception as e:
                logger.error(f"Error calculating tooltip position: {e}", exc_info=True)
                return

            # Create tooltip window
            try:
                self.tooltip = tk.Toplevel(self.widget)
                self.tooltip.wm_overrideredirect(True)
                self.tooltip.wm_geometry(f"+{x}+{y}")
            except tk.TclError as e:
                logger.error(f"Failed to create tooltip window: {e}", exc_info=True)
                return

            # Create frame
            try:
                frame = ttk.Frame(self.tooltip, style="Card.TFrame", padding=4)
                frame.pack(expand=True, fill="both")
            except tk.TclError as e:
                logger.error(f"Failed to create tooltip frame: {e}", exc_info=True)
                self._destroy_tooltip()
                return
            except Exception as e:
                logger.error(f"Error creating tooltip frame: {e}", exc_info=True)
                self._destroy_tooltip()
                return

            # Create label
            try:
                label = ttk.Label(frame,
                                  text=self.text,
                                  style="Trading.TLabel",
                                  font=("Segoe UI", 9))
                label.pack()
            except tk.TclError as e:
                logger.error(f"Failed to create tooltip label: {e}", exc_info=True)
                self._destroy_tooltip()
            except Exception as e:
                logger.error(f"Error creating tooltip label: {e}", exc_info=True)
                self._destroy_tooltip()

        except Exception as e:
            logger.error(f"[ModernToolTip.show_tooltip] Failed: {e}", exc_info=True)
            self._destroy_tooltip()

    def hide_tooltip(self, event=None):
        """Hide the tooltip window"""
        try:
            self._destroy_tooltip()
        except Exception as e:
            logger.error(f"[ModernToolTip.hide_tooltip] Failed: {e}", exc_info=True)

    def _destroy_tooltip(self):
        """Safely destroy the tooltip window"""
        try:
            if self.tooltip:
                try:
                    if self.tooltip.winfo_exists():
                        self.tooltip.destroy()
                except tk.TclError:
                    # Window already destroyed
                    pass
                finally:
                    self.tooltip = None
        except Exception as e:
            logger.error(f"[_destroy_tooltip] Failed: {e}", exc_info=True)
            self.tooltip = None

    def update_text(self, text: str):
        """Update the tooltip text"""
        try:
            if text is None:
                logger.warning("update_text called with None text")
                text = ""

            self.text = text
            logger.debug(f"Tooltip text updated to: {text}")

        except Exception as e:
            logger.error(f"[ModernToolTip.update_text] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before destruction"""
        try:
            logger.info("[ModernToolTip] Starting cleanup")

            # Unbind events
            if self.widget:
                try:
                    self.widget.unbind('<Enter>')
                    self.widget.unbind('<Leave>')
                except tk.TclError as e:
                    logger.warning(f"Failed to unbind events: {e}")

            # Destroy tooltip
            self._destroy_tooltip()

            # Clear reference
            self.widget = None

            logger.info("[ModernToolTip] Cleanup completed")

        except Exception as e:
            logger.error(f"[ModernToolTip.cleanup] Error: {e}", exc_info=True)

    def __del__(self):
        """Destructor to ensure cleanup"""
        try:
            self.cleanup()
        except Exception as e:
            # Can't log in __del__ reliably
            pass