# app_status_bar.py - Status bar for displaying application state
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame, QProgressBar
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtGui import QFont, QColor, QPalette


class AnimatedLabel(QLabel):
    """Label with blinking animation for active states"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._opacity = 1.0
        self._animation = QPropertyAnimation(self, b"opacity")
        self._animation.setDuration(800)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.3)
        self._animation.setLoopCount(-1)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, value):
        self._opacity = value
        self.setStyleSheet(f"color: rgba(63, 185, 80, {value});")

    opacity = pyqtProperty(float, get_opacity, set_opacity)

    def start_blink(self):
        self._animation.start()

    def stop_blink(self):
        self._animation.stop()
        self.set_opacity(1.0)


class AppStatusBar(QFrame):
    """Status bar showing application state, operations in progress, and current mode"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
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

    def _create_op_indicator(self, icon, tooltip):
        """Create an operation indicator label"""
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

    def update_status(self, status_info: dict, mode: str, app_running: bool):
        """
        Update status bar based on application state

        Args:
            status_info: Dict with keys like 'fetching_history', 'processing',
                        'order_pending', 'has_position', 'status', etc.
            mode: 'algo' or 'manual'
            app_running: Whether app is running
        """
        self._current_mode = mode
        self._app_running = app_running

        # Update mode indicator
        if mode == "algo":
            self.mode_label.setText("MODE: ALGO")
            self.mode_label.setStyleSheet("background: #1f6feb; color: white;")
        else:
            self.mode_label.setText("MODE: MANUAL")
            self.mode_label.setStyleSheet("background: #9e6a03; color: white;")

        # Update status text
        if 'status' in status_info:
            self._current_status = status_info['status']
            self.status_label.setText(status_info['status'])

        # Update status icon color
        if app_running:
            if 'fetching_history' in status_info and status_info['fetching_history']:
                self.status_icon.setStyleSheet("color: #f0883e; font-size: 12px;")  # Orange
                self.status_label.setText("Fetching history...")
            elif 'processing' in status_info and status_info['processing']:
                self.status_icon.setStyleSheet("color: #58a6ff; font-size: 12px;")  # Blue
                self.status_label.setText("Processing...")
            elif 'order_pending' in status_info and status_info['order_pending']:
                self.status_icon.setStyleSheet("color: #d29922; font-size: 12px;")  # Yellow
                self.status_label.setText("Order pending...")
            else:
                self.status_icon.setStyleSheet("color: #3fb950; font-size: 12px;")  # Green
        else:
            self.status_icon.setStyleSheet("color: #f85149; font-size: 12px;")  # Red

        # Update operation indicators
        self._update_op_indicator(self.op_fetch,
                                 status_info.get('fetching_history', False),
                                 "#f0883e")

        self._update_op_indicator(self.op_process,
                                 status_info.get('processing', False),
                                 "#58a6ff")

        self._update_op_indicator(self.op_order,
                                 status_info.get('order_pending', False),
                                 "#d29922")

        self._update_op_indicator(self.op_position,
                                 status_info.get('has_position', False),
                                 "#3fb950")

        # Show/hide progress bar for long operations
        if status_info.get('fetching_history', False):
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate mode
        else:
            self.progress_bar.setVisible(False)

        # Start blinking for important states
        if status_info.get('order_pending', False) or status_info.get('processing', False):
            if not self.blink_label.isVisible():
                self.blink_label.setVisible(True)
                self.blink_label.start_blink()
        else:
            self.blink_label.stop_blink()
            self.blink_label.setVisible(False)

    def _update_op_indicator(self, label, active, color):
        """Update operation indicator color based on active state"""
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

    def show_progress(self, value: int, text: str = ""):
        """Show progress bar with value"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(value)
        if text:
            self.progress_bar.setFormat(text)

    def hide_progress(self):
        """Hide progress bar"""
        self.progress_bar.setVisible(False)