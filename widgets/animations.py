import tkinter as tk
import logging
import logging.handlers
import traceback
from typing import Callable, Optional
import math

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class Animator:
    @staticmethod
    def pulse(widget: tk.Widget,
              duration: int = 1000,
              min_opacity: float = 0.4,
              max_opacity: float = 1.0,
              callback: Optional[Callable] = None):
        """
        Create a smooth pulse animation

        Args:
            widget: Tkinter widget to animate
            duration: Animation duration in milliseconds
            min_opacity: Minimum opacity value (0.0-1.0)
            max_opacity: Maximum opacity value (0.0-1.0)
            callback: Optional callback function called with current opacity
        """
        try:
            # Rule 6: Input validation
            if widget is None:
                logger.error("pulse animation called with None widget")
                return

            if not isinstance(duration, (int, float)) or duration <= 0:
                logger.warning(f"Invalid duration {duration}, using default 1000")
                duration = 1000

            if not isinstance(min_opacity, (int, float)):
                logger.warning(f"Invalid min_opacity {min_opacity}, using default 0.4")
                min_opacity = 0.4

            if not isinstance(max_opacity, (int, float)):
                logger.warning(f"Invalid max_opacity {max_opacity}, using default 1.0")
                max_opacity = 1.0

            # Clamp opacity values to valid range
            min_opacity = max(0.0, min(1.0, float(min_opacity)))
            max_opacity = max(0.0, min(1.0, float(max_opacity)))

            if max_opacity < min_opacity:
                logger.warning(f"max_opacity {max_opacity} < min_opacity {min_opacity}, swapping")
                min_opacity, max_opacity = max_opacity, min_opacity

            steps = 20
            step_time = duration / steps

            def update_opacity(step: int = 0):
                """Update widget opacity for current step"""
                try:
                    # Check if widget still exists
                    if not widget.winfo_exists():
                        logger.debug("Widget no longer exists, stopping animation")
                        return

                    progress = step / steps
                    # Sinusoidal oscillation between min and max
                    opacity = min_opacity + (max_opacity - min_opacity) * \
                              (math.sin(progress * math.pi * 2) + 1) / 2

                    # Apply opacity based on widget type
                    if hasattr(widget, 'set_opacity') and callable(widget.set_opacity):
                        try:
                            widget.set_opacity(opacity)
                        except Exception as e:
                            logger.error(f"Failed to set widget opacity: {e}", exc_info=True)

                    elif isinstance(widget, tk.Label):
                        try:
                            current_color = widget.cget('fg')
                            # Extract color name or hex
                            if current_color.startswith('#'):
                                # Hex color, try to add alpha
                                if len(current_color) == 7:  # #RRGGBB
                                    alpha_hex = f"{int(opacity * 255):02x}"
                                    alpha_color = f"{current_color}{alpha_hex}"
                                    widget.configure(fg=alpha_color)
                            # For named colors, we can't set alpha directly
                        except tk.TclError as e:
                            logger.warning(f"Failed to configure label color: {e}")
                        except Exception as e:
                            logger.error(f"Error updating label opacity: {e}", exc_info=True)

                    # Call callback if provided
                    if callback:
                        try:
                            callback(opacity)
                        except Exception as e:
                            logger.error(f"Animation callback failed: {e}", exc_info=True)

                    # Schedule next step if widget still exists
                    if widget.winfo_exists():
                        widget.after(int(step_time),
                                     lambda: update_opacity((step + 1) % steps))
                    else:
                        logger.debug("Animation stopping - widget destroyed")

                except tk.TclError as e:
                    # Widget was probably destroyed
                    logger.debug(f"Tcl error during animation (likely widget destroyed): {e}")
                except Exception as e:
                    logger.error(f"Error in animation step: {e}", exc_info=True)

            # Start the animation
            update_opacity()

        except Exception as e:
            logger.error(f"[Animator.pulse] Failed: {e}", exc_info=True)