# app_status_bar.py - Status bar for displaying application state
import logging
from typing import Optional

from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, pyqtProperty, QTimer
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QFrame, QProgressBar

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class AnimatedLabel(QLabel):
    """Label with blinking animation for active states"""

    def __init__(self, text="", parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(text, parent)
            self._opacity = 1.0
            self._animation = QPropertyAnimation(self, b"opacity")
            self._animation.setDuration(800)
            self._animation.setStartValue(1.0)
            self._animation.setEndValue(0.3)
            self._animation.setLoopCount(-1)
            self._animation.setEasingCurve(QEasingCurve.InOutQuad)

            logger.debug("AnimatedLabel initialized")

        except Exception as e:
            logger.error(f"[AnimatedLabel.__init__] Failed: {e}", exc_info=True)
            # Still call super to ensure Qt object is created
            super().__init__(text, parent)
            self._opacity = 1.0
            self._animation = None

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._opacity = 1.0
        self._animation = None
        self._blinking = False

    def get_opacity(self) -> float:
        """Get current opacity value"""
        try:
            return self._opacity
        except Exception as e:
            logger.error(f"[AnimatedLabel.get_opacity] Failed: {e}", exc_info=True)
            return 1.0

    def set_opacity(self, value: float) -> None:
        """Set opacity value and update stylesheet"""
        try:
            # Rule 6: Input validation
            if not isinstance(value, (int, float)):
                logger.warning(f"set_opacity called with non-numeric value: {value}")
                return

            # Clamp value to valid range
            self._opacity = max(0.0, min(1.0, float(value)))

            # Update stylesheet safely
            try:
                self.setStyleSheet(f"color: rgba(63, 185, 80, {self._opacity});")
            except Exception as e:
                logger.error(f"Failed to set stylesheet with opacity {self._opacity}: {e}")

        except Exception as e:
            logger.error(f"[AnimatedLabel.set_opacity] Failed: {e}", exc_info=True)

    opacity = pyqtProperty(float, get_opacity, set_opacity)

    def start_blink(self) -> None:
        """Start blinking animation"""
        try:
            if self._blinking:
                logger.debug("Blink already started")
                return

            if self._animation:
                self._animation.start()
                self._blinking = True
                logger.debug("Blink animation started")
            else:
                logger.warning("Cannot start blink: animation not initialized")

        except Exception as e:
            logger.error(f"[AnimatedLabel.start_blink] Failed: {e}", exc_info=True)

    def stop_blink(self) -> None:
        """Stop blinking animation and reset opacity"""
        try:
            if self._animation:
                self._animation.stop()
            self.set_opacity(1.0)
            self._blinking = False
            logger.debug("Blink animation stopped")

        except Exception as e:
            logger.error(f"[AnimatedLabel.stop_blink] Failed: {e}", exc_info=True)


class AppStatusBar(QFrame):
    """Status bar showing application state, operations in progress, and current mode"""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setFixedHeight(40)

            # EXACT stylesheet preservation - no changes
            self.setStyleSheet("""
                QFrame {
                    background: #161b22;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                }
                QLabel {
                    color: #8b949e;
                    font-size: 9pt;
                }
                QLabel[cssClass="status"] {
                    color: #58a6ff;
                    font-weight: bold;
                }
                QLabel[cssClass="mode"] {
                    color: #e6edf3;
                    font-weight: bold;
                    padding: 2px 8px;
                    border-radius: 10px;
                }
                QProgressBar {
                    border: 1px solid #30363d;
                    border-radius: 3px;
                    text-align: center;
                    color: #e6edf3;
                    background: #0d1117;
                    max-height: 16px;
                }
                QProgressBar::chunk {
                    background: #238636;
                    border-radius: 3px;
                }
            """)

            layout = QHBoxLayout(self)
            layout.setContentsMargins(10, 5, 10, 5)
            layout.setSpacing(15)

            # Status indicator with blinking for active operations
            self.status_icon = QLabel("●")
            self.status_icon.setStyleSheet("color: #f85149; font-size: 12px;")
            layout.addWidget(self.status_icon)

            self.status_label = QLabel("Ready")
            self.status_label.setProperty("cssClass", "status")
            layout.addWidget(self.status_label)

            # Separator
            sep1 = QFrame()
            sep1.setFrameShape(QFrame.VLine)
            sep1.setStyleSheet("QFrame { border: 1px solid #30363d; }")
            layout.addWidget(sep1)

            # Mode indicator
            self.mode_label = QLabel("MODE: ALGO")
            self.mode_label.setProperty("cssClass", "mode")
            self.mode_label.setStyleSheet("background: #1f6feb; color: white;")
            layout.addWidget(self.mode_label)

            # Separator
            sep2 = QFrame()
            sep2.setFrameShape(QFrame.VLine)
            sep2.setStyleSheet("QFrame { border: 1px solid #30363d; }")
            layout.addWidget(sep2)

            # Operation status with icons
            self.op_fetch = self._create_op_indicator("📊", "Fetching history")
            self.op_process = self._create_op_indicator("⚙️", "Processing")
            self.op_order = self._create_op_indicator("📝", "Order pending")
            self.op_position = self._create_op_indicator("💰", "Position active")

            layout.addWidget(self.op_fetch)
            layout.addWidget(self.op_process)
            layout.addWidget(self.op_order)
            layout.addWidget(self.op_position)

            layout.addStretch()

            # Progress bar for operations (hidden by default)
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(False)
            self.progress_bar.setFixedWidth(150)
            layout.addWidget(self.progress_bar)

            # Blinking animation for active status
            self.blink_label = AnimatedLabel("●")
            self.blink_label.setVisible(False)
            layout.addWidget(self.blink_label)

            # State tracking
            self._current_status = "Ready"
            self._current_mode = "algo"
            self._app_running = False

            # Update timer for safety
            self._update_timer = QTimer()
            self._update_timer.setSingleShot(True)
            self._update_timer.timeout.connect(self._safety_update)

            logger.info("AppStatusBar initialized")

        except Exception as e:
            logger.critical(f"[AppStatusBar.__init__] Failed: {e}", exc_info=True)
            # Still call super to ensure Qt object exists
            super().__init__(parent)
            self.setFixedHeight(40)
            self._safe_defaults_init()

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.status_icon = None
        self.status_label = None
        self.mode_label = None
        self.op_fetch = None
        self.op_process = None
        self.op_order = None
        self.op_position = None
        self.progress_bar = None
        self.blink_label = None
        self._current_status = "Ready"
        self._current_mode = "algo"
        self._app_running = False
        self._update_timer = None

    def _create_op_indicator(self, icon: str, tooltip: str) -> QLabel:
        """Create an operation indicator label"""
        try:
            # Rule 6: Input validation
            if not isinstance(icon, str):
                logger.warning(f"_create_op_indicator called with non-string icon: {icon}")
                icon = "?"

            if not isinstance(tooltip, str):
                logger.warning(f"_create_op_indicator called with non-string tooltip: {tooltip}")
                tooltip = ""

            label = QLabel(icon)
            label.setToolTip(tooltip)
            label.setStyleSheet("""
                QLabel {
                    color: #484f58;
                    font-size: 14px;
                    padding: 2px 5px;
                }
            """)
            return label

        except Exception as e:
            logger.error(f"[AppStatusBar._create_op_indicator] Failed: {e}", exc_info=True)
            # Return a safe default label
            label = QLabel("?")
            label.setToolTip("Error creating indicator")
            return label

    def update_status(self, status_info: dict, mode: str, app_running: bool) -> None:
        """
        Update status bar based on application state

        Args:
            status_info: Dict with keys like 'fetching_history', 'processing',
                        'order_pending', 'has_position', 'status', etc.
            mode: 'algo' or 'manual'
            app_running: Whether app is running
        """
        try:
            # Rule 6: Input validation
            if status_info is None:
                logger.warning("update_status called with None status_info")
                status_info = {}

            if not isinstance(status_info, dict):
                logger.warning(f"update_status called with non-dict status_info: {type(status_info)}")
                status_info = {}

            if not isinstance(mode, str):
                logger.warning(f"update_status called with non-string mode: {mode}")
                mode = "algo"

            self._current_mode = mode
            self._app_running = app_running

            # Update mode indicator with safety checks - FIXED: Use explicit None check
            if self.mode_label is not None:
                try:
                    if mode == "algo":
                        self.mode_label.setText("MODE: ALGO")
                        self.mode_label.setStyleSheet("background: #1f6feb; color: white;")
                    else:
                        self.mode_label.setText("MODE: MANUAL")
                        self.mode_label.setStyleSheet("background: #9e6a03; color: white;")
                except Exception as e:
                    logger.error(f"Failed to update mode label: {e}")

            # Update status text - FIXED: Use explicit None check
            if 'status' in status_info and self.status_label is not None:
                try:
                    status_text = status_info['status']
                    if isinstance(status_text, str):
                        self._current_status = status_text
                        self.status_label.setText(status_text)
                except Exception as e:
                    logger.error(f"Failed to update status label: {e}")

            # Update status icon color with safety checks
            if self.status_icon is not None:
                try:
                    if app_running:
                        if status_info.get('fetching_history', False):
                            self.status_icon.setStyleSheet("color: #f0883e; font-size: 12px;")  # Orange
                            if self.status_label is not None:
                                self.status_label.setText("Fetching history...")
                        elif status_info.get('processing', False):
                            self.status_icon.setStyleSheet("color: #58a6ff; font-size: 12px;")  # Blue
                            if self.status_label is not None:
                                self.status_label.setText("Processing...")
                        elif status_info.get('order_pending', False):
                            self.status_icon.setStyleSheet("color: #d29922; font-size: 12px;")  # Yellow
                            if self.status_label is not None:
                                self.status_label.setText("Order pending...")
                        else:
                            self.status_icon.setStyleSheet("color: #3fb950; font-size: 12px;")  # Green
                    else:
                        self.status_icon.setStyleSheet("color: #f85149; font-size: 12px;")  # Red
                except Exception as e:
                    logger.error(f"Failed to update status icon: {e}")

            # Update operation indicators
            self._update_op_indicator(self.op_fetch,
                                      bool(status_info.get('fetching_history', False)),
                                      "#f0883e")

            self._update_op_indicator(self.op_process,
                                      bool(status_info.get('processing', False)),
                                      "#58a6ff")

            self._update_op_indicator(self.op_order,
                                      bool(status_info.get('order_pending', False)),
                                      "#d29922")

            self._update_op_indicator(self.op_position,
                                      bool(status_info.get('has_position', False)),
                                      "#3fb950")

            # Show/hide progress bar for long operations - FIXED: Use explicit None check
            if self.progress_bar is not None:
                try:
                    if status_info.get('fetching_history', False):
                        self.progress_bar.setVisible(True)
                        self.progress_bar.setRange(0, 0)  # Indeterminate mode
                    else:
                        self.progress_bar.setVisible(False)
                except Exception as e:
                    logger.error(f"Failed to update progress bar: {e}")

            # Start blinking for important states - FIXED: Use explicit None check
            if self.blink_label is not None:
                try:
                    if status_info.get('order_pending', False) or status_info.get('processing', False):
                        if not self.blink_label.isVisible():
                            self.blink_label.setVisible(True)
                            self.blink_label.start_blink()
                    else:
                        self.blink_label.stop_blink()
                        self.blink_label.setVisible(False)
                except Exception as e:
                    logger.error(f"Failed to update blink label: {e}")

            # Schedule a safety update to ensure UI doesn't get stuck
            self._schedule_safety_update()

        except Exception as e:
            logger.error(f"[AppStatusBar.update_status] Failed: {e}", exc_info=True)

    def _schedule_safety_update(self):
        """Schedule a safety update to ensure UI consistency"""
        try:
            # FIXED: Use explicit None check
            if self._update_timer is not None and not self._update_timer.isActive():
                self._update_timer.start(5000)  # 5 second safety timeout
        except Exception as e:
            logger.error(f"Failed to schedule safety update: {e}")

    def _safety_update(self):
        """Safety update to ensure UI doesn't get stuck in wrong state"""
        try:
            logger.debug("Running safety update")
            # If blink label is visible but shouldn't be, hide it - FIXED: Use explicit None check
            if self.blink_label is not None and self.blink_label.isVisible():
                if not (self._current_status in ["Processing...", "Order pending..."]):
                    logger.warning("Safety update: hiding stuck blink label")
                    self.blink_label.stop_blink()
                    self.blink_label.setVisible(False)
        except Exception as e:
            logger.error(f"Safety update failed: {e}")

    def _update_op_indicator(self, label: Optional[QLabel], active: bool, color: str) -> None:
        """Update operation indicator color based on active state"""
        try:
            if label is None:
                logger.warning("_update_op_indicator called with None label")
                return

            # Rule 6: Input validation
            if not isinstance(active, bool):
                logger.warning(f"_update_op_indicator called with non-bool active: {active}")
                active = bool(active)

            if not isinstance(color, str):
                logger.warning(f"_update_op_indicator called with non-string color: {color}")
                color = "#484f58"

            if active:
                label.setStyleSheet(f"""
                    QLabel {{
                        color: {color};
                        font-size: 14px;
                        padding: 2px 5px;
                        font-weight: bold;
                    }}
                """)
            else:
                label.setStyleSheet("""
                    QLabel {
                        color: #484f58;
                        font-size: 14px;
                        padding: 2px 5px;
                    }
                """)

        except Exception as e:
            logger.error(f"[AppStatusBar._update_op_indicator] Failed: {e}", exc_info=True)

    def show_progress(self, value: int, text: str = "") -> None:
        """Show progress bar with value"""
        try:
            # Rule 6: Input validation
            if not isinstance(value, (int, float)):
                logger.warning(f"show_progress called with non-numeric value: {value}")
                return

            # FIXED: Use explicit None check
            if self.progress_bar is not None:
                self.progress_bar.setVisible(True)
                self.progress_bar.setRange(0, 100)

                # Clamp value to valid range
                clamped_value = max(0, min(100, int(value)))
                self.progress_bar.setValue(clamped_value)

                if text and isinstance(text, str):
                    self.progress_bar.setFormat(text)

                logger.debug(f"Progress shown: {clamped_value}% - {text}")

        except Exception as e:
            logger.error(f"[AppStatusBar.show_progress] Failed: {e}", exc_info=True)

    def hide_progress(self) -> None:
        """Hide progress bar"""
        try:
            # FIXED: Use explicit None check
            if self.progress_bar is not None:
                self.progress_bar.setVisible(False)
                logger.debug("Progress bar hidden")
        except Exception as e:
            logger.error(f"[AppStatusBar.hide_progress] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown"""
        try:
            logger.info("[AppStatusBar] Starting cleanup")

            # Stop animations - FIXED: Use explicit None check
            if self.blink_label is not None:
                try:
                    self.blink_label.stop_blink()
                except Exception as e:
                    logger.warning(f"Error stopping blink animation: {e}")

            # Stop timer - FIXED: Use explicit None check
            if self._update_timer is not None:
                try:
                    if self._update_timer.isActive():
                        self._update_timer.stop()
                except Exception as e:
                    logger.warning(f"Error stopping timer: {e}")

            # Clear references
            self.status_icon = None
            self.status_label = None
            self.mode_label = None
            self.op_fetch = None
            self.op_process = None
            self.op_order = None
            self.op_position = None
            self.progress_bar = None
            self.blink_label = None
            self._update_timer = None

            logger.info("[AppStatusBar] Cleanup completed")

        except Exception as e:
            logger.error(f"[AppStatusBar.cleanup] Error: {e}", exc_info=True)