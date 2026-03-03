"""
Application Status Bar Module
==============================
Enhanced status bar component for the PyQt5 trading dashboard.

This module provides a comprehensive status bar that displays real-time information
about the application state, ongoing operations, and performance metrics. It features
animated indicators, tooltips, and visual feedback for various system states.

UPDATED: Added connection details, system metrics, and trading statistics.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import psutil
import os

from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, pyqtProperty, QTimer, Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QFrame, QProgressBar, QWidget

# Import state manager for accessing trading state
from models.trade_state_manager import state_manager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class AnimatedLabel(QLabel):
    """
    Label with blinking and pulsing animations for active states.
    """

    BLINK = "blink"
    PULSE = "pulse"
    FADE = "fade"

    def __init__(self, text="", parent=None):
        self._safe_defaults_init()

        try:
            super().__init__(text, parent)
            self._opacity = 1.0
            self._scale = 1.0

            # Blink animation (opacity)
            self._animation = QPropertyAnimation(self, b"opacity")
            self._animation.setDuration(800)
            self._animation.setStartValue(1.0)
            self._animation.setEndValue(0.3)
            self._animation.setLoopCount(-1)
            self._animation.setEasingCurve(QEasingCurve.InOutQuad)

            # Pulse animation (scale)
            self._pulse_animation = QPropertyAnimation(self, b"scale")
            self._pulse_animation.setDuration(1000)
            self._pulse_animation.setStartValue(1.0)
            self._pulse_animation.setEndValue(1.2)
            self._pulse_animation.setLoopCount(-1)
            self._pulse_animation.setEasingCurve(QEasingCurve.InOutQuad)

        except Exception as e:
            logger.error(f"[AnimatedLabel.__init__] Failed: {e}", exc_info=True)
            super().__init__(text, parent)
            self._opacity = 1.0
            self._scale = 1.0
            self._animation = None
            self._pulse_animation = None

    def _safe_defaults_init(self):
        self._opacity = 1.0
        self._scale = 1.0
        self._animation = None
        self._pulse_animation = None
        self._blinking = False
        self._pulsing = False
        self._animation_type = self.BLINK

    def get_opacity(self) -> float:
        return self._opacity

    def set_opacity(self, value: float) -> None:
        try:
            if not isinstance(value, (int, float)):
                return

            self._opacity = max(0.0, min(1.0, float(value)))

            try:
                base_color = "#3fb950"
                if hasattr(self, '_base_color'):
                    base_color = self._base_color

                r = int(base_color[1:3], 16)
                g = int(base_color[3:5], 16)
                b = int(base_color[5:7], 16)

                self.setStyleSheet(f"color: rgba({r}, {g}, {b}, {self._opacity}); font-size: {12 * self._scale}px;")
            except Exception as e:
                logger.error(f"Failed to set stylesheet: {e}")

        except Exception as e:
            logger.error(f"[AnimatedLabel.set_opacity] Failed: {e}", exc_info=True)

    opacity = pyqtProperty(float, get_opacity, set_opacity)

    def get_scale(self) -> float:
        return self._scale

    def set_scale(self, value: float) -> None:
        try:
            self._scale = max(0.5, min(2.0, float(value)))
            self.set_opacity(self._opacity)
        except Exception as e:
            logger.error(f"[AnimatedLabel.set_scale] Failed: {e}")

    scale = pyqtProperty(float, get_scale, set_scale)

    def start_animation(self, animation_type: str = BLINK, color: str = "#3fb950") -> None:
        try:
            self._base_color = color
            self._animation_type = animation_type

            if animation_type == self.BLINK:
                if self._animation and not self._blinking:
                    self._animation.start()
                    self._blinking = True
            elif animation_type == self.PULSE:
                if self._pulse_animation and not self._pulsing:
                    self._pulse_animation.start()
                    self._pulsing = True
            elif animation_type == self.FADE:
                self._animation.setStartValue(1.0)
                self._animation.setEndValue(0.1)
                self._animation.setDuration(1500)
                self._animation.start()
                self._blinking = True

        except Exception as e:
            logger.error(f"[AnimatedLabel.start_animation] Failed: {e}", exc_info=True)

    def stop_animation(self) -> None:
        try:
            if self._animation:
                self._animation.stop()
            if self._pulse_animation:
                self._pulse_animation.stop()

            self.set_opacity(1.0)
            self._scale = 1.0
            self._blinking = False
            self._pulsing = False

        except Exception as e:
            logger.error(f"[AnimatedLabel.stop_animation] Failed: {e}", exc_info=True)


class StatusToolTip(QLabel):
    """Custom tooltip for showing detailed status information."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QLabel {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 8px;
                font-size: 9pt;
            }
        """)
        self.setWordWrap(True)
        self.setMaximumWidth(300)
        self.hide()

    def show_at_position(self, text: str, pos):
        self.setText(text)
        self.adjustSize()
        self.move(pos.x() + 20, pos.y() - self.height() - 10)
        self.show()


class AppStatusBar(QFrame):
    """
    Enhanced status bar showing application state, operations, and performance metrics.

    UPDATED: Shows connection status, system metrics, and trading statistics.
    """

    def __init__(self, parent=None):
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setFixedHeight(45)

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
                QLabel[cssClass="timestamp"] {
                    color: #6e7681;
                    font-size: 8pt;
                    padding: 2px 5px;
                }
                QLabel[cssClass="metric"] {
                    color: #58a6ff;
                    font-size: 8pt;
                    padding: 2px 5px;
                    background: #21262d;
                    border-radius: 3px;
                }
                QLabel[cssClass="market"] {
                    font-size: 8pt;
                    padding: 2px 8px;
                    border-radius: 10px;
                    font-weight: bold;
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
                QFrame#separator {
                    border: 1px solid #30363d;
                    max-width: 1px;
                    min-width: 1px;
                }
            """)

            layout = QHBoxLayout(self)
            layout.setContentsMargins(10, 5, 10, 5)
            layout.setSpacing(10)

            # Left section - Status + Timestamp
            self._create_status_section(layout)

            # Middle section - Operations + Market + Connection
            self._create_operations_section(layout)

            # Right section - System + Trading Metrics
            self._create_metrics_section(layout)

            # State tracking
            self._current_status = "Ready"
            self._current_mode = "algo"
            self._app_running = False
            self._market_status = "UNKNOWN"
            self._connection_status = "Disconnected"
            self._start_time = datetime.now()
            self._operation_start_times = {}
            self._last_update_time = datetime.now()
            self._last_message_count = 0
            self._message_rate = 0
            self._peak_rate = 0

            # Cache for snapshots
            self._last_snapshot = {}
            self._last_snapshot_time = None
            self._snapshot_cache_duration = 0.1

            # Update timer for dynamic info
            self._update_timer = QTimer()
            self._update_timer.timeout.connect(self._update_dynamic_info)
            self._update_timer.start(1000)

            # Safety timer
            self._safety_timer = QTimer()
            self._safety_timer.setSingleShot(True)
            self._safety_timer.timeout.connect(self._safety_update)

            logger.info("Enhanced AppStatusBar initialized")

        except Exception as e:
            logger.critical(f"[AppStatusBar.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self.setFixedHeight(45)
            self._safe_defaults_init()

    def _safe_defaults_init(self):
        self.status_icon = None
        self.status_label = None
        self.mode_label = None
        self.timestamp_label = None
        self.op_fetch = None
        self.op_process = None
        self.op_order = None
        self.op_position = None
        self.op_connection = None
        self.op_market = None
        self.progress_bar = None
        self.blink_label = None
        self.metrics_container = None
        self.cpu_label = None
        self.memory_label = None
        self.pnl_label = None
        self.queue_label = None
        self.msg_rate_label = None
        self._current_status = "Ready"
        self._current_mode = "algo"
        self._app_running = False
        self._market_status = "UNKNOWN"
        self._connection_status = "Disconnected"
        self._start_time = None
        self._operation_start_times = {}
        self._last_update_time = None
        self._update_timer = None
        self._safety_timer = None
        self._tooltip = None
        self._message_rate = 0
        self._last_message_count = 0
        self._peak_rate = 0
        self._metrics = {}
        self._last_snapshot = {}
        self._last_snapshot_time = None
        self._snapshot_cache_duration = 0.1

    def _create_status_section(self, layout):
        """Create left status section with icon, text, and timestamp"""
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)

        self.status_icon = QLabel("●")
        self.status_icon.setStyleSheet("color: #f85149; font-size: 14px;")
        status_layout.addWidget(self.status_icon)

        self.status_label = QLabel("Ready")
        self.status_label.setProperty("cssClass", "status")
        status_layout.addWidget(self.status_label)

        self.timestamp_label = QLabel()
        self.timestamp_label.setProperty("cssClass", "timestamp")
        status_layout.addWidget(self.timestamp_label)

        layout.addWidget(status_container)
        layout.addWidget(self._create_separator())

    def _create_operations_section(self, layout):
        """Create middle operations section with indicators"""
        ops_container = QWidget()
        ops_layout = QHBoxLayout(ops_container)
        ops_layout.setContentsMargins(0, 0, 0, 0)
        ops_layout.setSpacing(10)

        # Mode indicator
        self.mode_label = QLabel("MODE: ALGO")
        self.mode_label.setProperty("cssClass", "mode")
        self.mode_label.setStyleSheet("background: #1f6feb; color: white;")
        ops_layout.addWidget(self.mode_label)

        # Operation indicators
        self.op_fetch = self._create_op_indicator("📊", "Fetching history", "#f0883e")
        self.op_process = self._create_op_indicator("⚙️", "Processing", "#58a6ff")
        self.op_order = self._create_op_indicator("📝", "Order pending", "#d29922")
        self.op_position = self._create_op_indicator("💰", "Position active", "#3fb950")
        self.op_connection = self._create_op_indicator("🔌", "Connection status", "#8b949e")
        self.op_market = self._create_op_indicator("📈", "Market status", "#8b949e")

        ops_layout.addWidget(self.op_fetch)
        ops_layout.addWidget(self.op_process)
        ops_layout.addWidget(self.op_order)
        ops_layout.addWidget(self.op_position)
        ops_layout.addWidget(self.op_connection)
        ops_layout.addWidget(self.op_market)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(150)
        ops_layout.addWidget(self.progress_bar)

        # Blinking animation
        self.blink_label = AnimatedLabel("●")
        self.blink_label.setVisible(False)
        ops_layout.addWidget(self.blink_label)

        layout.addWidget(ops_container)
        layout.addWidget(self._create_separator())

    def _create_metrics_section(self, layout):
        """Create right metrics section with system and trading stats"""
        self.metrics_container = QWidget()
        metrics_layout = QHBoxLayout(self.metrics_container)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(8)

        # CPU Usage
        self.cpu_label = QLabel()
        self.cpu_label.setProperty("cssClass", "metric")
        metrics_layout.addWidget(self.cpu_label)

        # Memory Usage
        self.memory_label = QLabel()
        self.memory_label.setProperty("cssClass", "metric")
        metrics_layout.addWidget(self.memory_label)

        # P&L
        self.pnl_label = QLabel()
        self.pnl_label.setProperty("cssClass", "metric")
        metrics_layout.addWidget(self.pnl_label)

        # Queue Size
        self.queue_label = QLabel()
        self.queue_label.setProperty("cssClass", "metric")
        metrics_layout.addWidget(self.queue_label)

        # Message Rate
        self.msg_rate_label = QLabel()
        self.msg_rate_label.setProperty("cssClass", "metric")
        metrics_layout.addWidget(self.msg_rate_label)

        layout.addWidget(self.metrics_container, 1)

    def _create_separator(self) -> QFrame:
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.VLine)
        return sep

    def _create_op_indicator(self, icon: str, tooltip: str, color: str) -> QLabel:
        try:
            label = QLabel(icon)
            label.setToolTip(tooltip)
            label.setProperty("default_color", color)
            label.setStyleSheet(f"""
                QLabel {{
                    color: #484f58;
                    font-size: 14px;
                    padding: 2px 5px;
                }}
                QLabel:hover {{
                    background: #21262d;
                    border-radius: 3px;
                }}
            """)

            label.setMouseTracking(True)
            label.enterEvent = lambda e: self._show_op_tooltip(label, tooltip)
            label.leaveEvent = lambda e: self._hide_op_tooltip()

            return label

        except Exception as e:
            logger.error(f"[AppStatusBar._create_op_indicator] Failed: {e}", exc_info=True)
            label = QLabel("?")
            label.setToolTip("Error creating indicator")
            return label

    def _show_op_tooltip(self, label: QLabel, base_tooltip: str):
        try:
            tooltip_text = base_tooltip
            op_name = label.toolTip().split()[0].lower()

            if op_name in self._operation_start_times:
                start_time = self._operation_start_times[op_name]
                duration = (datetime.now() - start_time).total_seconds()
                tooltip_text += f"\nActive for: {duration:.1f}s"

            if op_name == "position":
                snapshot = self._get_cached_snapshot()
                pos_snapshot = state_manager.get_position_snapshot()
                if pos_snapshot.get('current_position'):
                    pos_type = pos_snapshot.get('current_position')
                    entry_price = pos_snapshot.get('current_buy_price')
                    current_price = pos_snapshot.get('current_price')
                    pnl = pos_snapshot.get('current_pnl')

                    tooltip_text += f"\nPosition: {pos_type}"
                    if entry_price:
                        tooltip_text += f"\nEntry: ₹{entry_price:.2f}"
                    if current_price:
                        tooltip_text += f"\nCurrent: ₹{current_price:.2f}"
                    if pnl:
                        tooltip_text += f"\nP&L: ₹{pnl:.2f}"

            elif op_name == "market":
                tooltip_text += f"\nStatus: {self._market_status}"

            elif op_name == "connection":
                tooltip_text += f"\nStatus: {self._connection_status}"
                # Add WebSocket stats if available
                if hasattr(self, '_ws_stats'):
                    tooltip_text += f"\nMessages: {self._ws_stats.get('message_count', 0)}"
                    tooltip_text += f"\nReconnects: {self._ws_stats.get('reconnect_count', 0)}"

            if not hasattr(self, '_tooltip') or not self._tooltip:
                self._tooltip = StatusToolTip(self)

            pos = label.mapToGlobal(label.rect().topLeft())
            self._tooltip.show_at_position(tooltip_text, pos)

        except Exception as e:
            logger.error(f"[AppStatusBar._show_op_tooltip] Failed: {e}")

    def _hide_op_tooltip(self):
        if hasattr(self, '_tooltip') and self._tooltip:
            self._tooltip.hide()

    def _get_cached_snapshot(self) -> Dict[str, Any]:
        now = datetime.now()
        if (self._last_snapshot_time is None or
            (now - self._last_snapshot_time).total_seconds() > self._snapshot_cache_duration):
            self._last_snapshot = state_manager.get_snapshot()
            self._last_snapshot_time = now
        return self._last_snapshot

    def _format_bytes(self, bytes_val):
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f}GB"

    def update_status(self, status_info: Dict[str, Any], mode: str, app_running: bool) -> None:
        """Update status bar based on application state"""
        try:
            if status_info is None:
                status_info = {}

            self._current_mode = mode
            self._app_running = app_running
            self._last_update_time = datetime.now()

            snapshot = self._get_cached_snapshot()

            self._update_mode_display()
            self._update_status_display(status_info, snapshot)
            self._update_operation_indicators(status_info, snapshot)
            self._update_connection_status(status_info)

            if 'market_status' in status_info:
                self.update_market_status(status_info['market_status'])

            self._update_progress_bar(status_info)
            self._update_blink_animation(status_info)
            self._schedule_safety_update()

        except Exception as e:
            logger.error(f"[AppStatusBar.update_status] Failed: {e}", exc_info=True)

    def update_market_status(self, status: str):
        """Update market status display"""
        try:
            self._market_status = status

            if self.op_market is None:
                return

            if status == "OPEN":
                self.op_market.setText("📈")
                self._update_op_indicator(self.op_market, True, "#3fb950")
                self.op_market.setToolTip("Market: OPEN")
            elif status == "CLOSED":
                self.op_market.setText("📉")
                self._update_op_indicator(self.op_market, True, "#f85149")
                self.op_market.setToolTip("Market: CLOSED")
            else:
                self.op_market.setText("📊")
                self._update_op_indicator(self.op_market, False, "#8b949e")
                self.op_market.setToolTip("Market: UNKNOWN")

        except Exception as e:
            logger.error(f"[AppStatusBar.update_market_status] Failed: {e}", exc_info=True)

    def _update_mode_display(self):
        if self.mode_label is None:
            return

        try:
            if self._current_mode == "algo":
                self.mode_label.setText("MODE: ALGO")
                self.mode_label.setStyleSheet("background: #1f6feb; color: white;")
            else:
                self.mode_label.setText("MODE: MANUAL")
                self.mode_label.setStyleSheet("background: #9e6a03; color: white;")
        except Exception as e:
            logger.error(f"Failed to update mode label: {e}")

    def _update_status_display(self, status_info: Dict[str, Any], snapshot: Dict[str, Any]):
        if self.status_icon is None or self.status_label is None:
            return

        try:
            if 'status' in status_info:
                status_text = status_info['status']
                if isinstance(status_text, str):
                    self._current_status = status_text
                    self.status_label.setText(status_text)

            if self.timestamp_label:
                self.timestamp_label.setText(datetime.now().strftime("%H:%M:%S"))

            # Status icon color
            if self._app_running:
                if status_info.get('fetching_history', False):
                    self.status_icon.setStyleSheet("color: #f0883e; font-size: 14px;")
                elif status_info.get('processing', False):
                    self.status_icon.setStyleSheet("color: #58a6ff; font-size: 14px;")
                elif status_info.get('order_pending', False):
                    self.status_icon.setStyleSheet("color: #d29922; font-size: 14px;")
                elif snapshot.get('current_position') is not None:
                    self.status_icon.setStyleSheet("color: #3fb950; font-size: 14px;")
                else:
                    self.status_icon.setStyleSheet("color: #3fb950; font-size: 14px;")
            else:
                self.status_icon.setStyleSheet("color: #f85149; font-size: 14px;")

        except Exception as e:
            logger.error(f"Failed to update status display: {e}")

    def _update_operation_indicators(self, status_info: Dict[str, Any], snapshot: Dict[str, Any]):
        operations = [
            ('fetching_history', self.op_fetch, "#f0883e"),
            ('processing', self.op_process, "#58a6ff"),
            ('order_pending', self.op_order, "#d29922"),
            ('has_position', self.op_position, "#3fb950")
        ]

        for key, label, color in operations:
            if key == 'has_position':
                active = bool(status_info.get(key, False)) or (snapshot.get('current_position') is not None)
            else:
                active = bool(status_info.get(key, False))

            if active:
                if key not in self._operation_start_times:
                    self._operation_start_times[key] = datetime.now()
            else:
                if key in self._operation_start_times:
                    del self._operation_start_times[key]

            self._update_op_indicator(label, active, color)

    def _update_connection_status(self, status_info: Dict[str, Any]):
        if self.op_connection is None:
            return

        try:
            is_connected = status_info.get('connection_status') == "Connected"

            if is_connected:
                self._update_op_indicator(self.op_connection, True, "#3fb950")
                self.op_connection.setToolTip("Connected to broker")
            else:
                self._update_op_indicator(self.op_connection, False, "#8b949e")
                self.op_connection.setToolTip("Disconnected from broker")

            self._connection_status = "Connected" if is_connected else "Disconnected"

        except Exception as e:
            logger.error(f"Failed to update connection status: {e}")

    def _update_progress_bar(self, status_info: Dict[str, Any]):
        if self.progress_bar is None:
            return

        try:
            if status_info.get('fetching_history', False):
                self.progress_bar.setVisible(True)
                self.progress_bar.setRange(0, 0)

                if 'progress' in status_info:
                    self.progress_bar.setRange(0, 100)
                    self.progress_bar.setValue(status_info['progress'])
            else:
                self.progress_bar.setVisible(False)

        except Exception as e:
            logger.error(f"Failed to update progress bar: {e}")

    def _update_blink_animation(self, status_info: Dict[str, Any]):
        if self.blink_label is None:
            return

        try:
            snapshot = self._get_cached_snapshot()
            should_blink = (status_info.get('order_pending', False) or
                           status_info.get('processing', False) or
                           status_info.get('fetching_history', False) or
                           snapshot.get('signal_conflict', False))

            if should_blink:
                if not self.blink_label.isVisible():
                    self.blink_label.setVisible(True)

                    if status_info.get('order_pending', False):
                        self.blink_label.start_animation(AnimatedLabel.PULSE, "#d29922")
                    elif snapshot.get('signal_conflict', False):
                        self.blink_label.start_animation(AnimatedLabel.PULSE, "#f85149")
                    elif status_info.get('processing', False):
                        self.blink_label.start_animation(AnimatedLabel.BLINK, "#58a6ff")
                    elif status_info.get('fetching_history', False):
                        self.blink_label.start_animation(AnimatedLabel.FADE, "#f0883e")
            else:
                if self.blink_label.isVisible():
                    self.blink_label.stop_animation()
                    self.blink_label.setVisible(False)

        except Exception as e:
            logger.error(f"Failed to update blink animation: {e}")

    def _update_op_indicator(self, label: Optional[QLabel], active: bool, color: str) -> None:
        if label is None:
            return

        try:
            if active:
                label.setStyleSheet(f"""
                    QLabel {{
                        color: {color};
                        font-size: 14px;
                        padding: 2px 5px;
                        font-weight: bold;
                    }}
                    QLabel:hover {{
                        background: #21262d;
                        border-radius: 3px;
                    }}
                """)
            else:
                label.setStyleSheet("""
                    QLabel {
                        color: #484f58;
                        font-size: 14px;
                        padding: 2px 5px;
                    }
                    QLabel:hover {
                        background: #21262d;
                        border-radius: 3px;
                    }
                """)

        except Exception as e:
            logger.error(f"[AppStatusBar._update_op_indicator] Failed: {e}", exc_info=True)

    def _update_dynamic_info(self):
        """Update dynamic information every second"""
        try:
            if not self._app_running:
                return

            # Get snapshots
            snapshot = self._get_cached_snapshot()
            pos_snapshot = state_manager.get_position_snapshot()

            # System metrics
            try:
                # CPU
                cpu_percent = psutil.cpu_percent(interval=0.1)
                cpu_color = "#f85149" if cpu_percent > 90 else "#d29922" if cpu_percent > 70 else "#58a6ff"
                self.cpu_label.setText(f"💾 {cpu_percent:.0f}%")
                self.cpu_label.setStyleSheet(f"color: {cpu_color}; background: #21262d; border-radius: 3px; padding: 2px 5px;")

                # Memory
                mem = psutil.virtual_memory()
                mem_color = "#f85149" if mem.percent > 90 else "#d29922" if mem.percent > 80 else "#58a6ff"
                self.memory_label.setText(f"📀 {mem.percent:.0f}%")
                self.memory_label.setStyleSheet(f"color: {mem_color}; background: #21262d; border-radius: 3px; padding: 2px 5px;")
            except:
                pass

            # Trading metrics
            # P&L
            pnl = pos_snapshot.get('current_pnl', 0)
            if pnl:
                pnl_color = "#3fb950" if pnl > 0 else "#f85149"
                self.pnl_label.setText(f"💰 ₹{pnl:,.0f}")
                self.pnl_label.setStyleSheet(f"color: {pnl_color}; background: #21262d; border-radius: 3px; padding: 2px 5px;")
            else:
                self.pnl_label.setText("💰 ₹0")
                self.pnl_label.setStyleSheet("color: #58a6ff; background: #21262d; border-radius: 3px; padding: 2px 5px;")

            # Queue size
            if self.trading_app and hasattr(self.trading_app, '_tick_queue'):
                qsize = self.trading_app._tick_queue.qsize()
                queue_color = "#f85149" if qsize > 100 else "#d29922" if qsize > 50 else "#58a6ff"
                self.queue_label.setText(f"📥 {qsize}")
                self.queue_label.setStyleSheet(f"color: {queue_color}; background: #21262d; border-radius: 3px; padding: 2px 5px;")

            # Message rate
            if self.trading_app and hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                ws = self.trading_app.ws
                if hasattr(ws, 'get_statistics'):
                    stats = ws.get_statistics()
                    msg_count = stats.get('message_count', 0)

                    # Calculate rate
                    if hasattr(self, '_last_msg_count'):
                        rate = msg_count - self._last_msg_count
                        if rate > self._peak_rate:
                            self._peak_rate = rate

                        rate_color = "#f85149" if rate > 100 else "#d29922" if rate > 50 else "#58a6ff"
                        self.msg_rate_label.setText(f"📨 {rate}/s")
                        self.msg_rate_label.setStyleSheet(f"color: {rate_color}; background: #21262d; border-radius: 3px; padding: 2px 5px;")

                    self._last_msg_count = msg_count
                    self._ws_stats = stats

        except Exception as e:
            logger.error(f"[AppStatusBar._update_dynamic_info] Failed: {e}")

    def _schedule_safety_update(self):
        if self._safety_timer and not self._safety_timer.isActive():
            self._safety_timer.start(10000)

    def _safety_update(self):
        """Safety update to reset stuck states"""
        try:
            # Check for long-running operations
            for op, start_time in list(self._operation_start_times.items()):
                duration = (datetime.now() - start_time).total_seconds()
                if duration > 300:  # 5 minutes
                    logger.warning(f"Operation {op} active for {duration:.0f}s, resetting")
                    del self._operation_start_times[op]

            # Reset blink if stuck
            if self.blink_label and self.blink_label.isVisible():
                snapshot = self._get_cached_snapshot()
                if not any([
                    op in self._operation_start_times
                    for op in ['fetching_history', 'processing', 'order_pending']
                ]) and not snapshot.get('signal_conflict', False):
                    logger.warning("Safety update: hiding stuck blink label")
                    self.blink_label.stop_animation()
                    self.blink_label.setVisible(False)

        except Exception as e:
            logger.error(f"Safety update failed: {e}")

    def update_metrics(self, metrics: Dict[str, Any]):
        """Update performance metrics from external sources"""
        try:
            self._metrics.update(metrics)
        except Exception as e:
            logger.error(f"[AppStatusBar.update_metrics] Failed: {e}")

    def show_progress(self, value: int, text: str = "", determinate: bool = True) -> None:
        if self.progress_bar is None:
            return

        try:
            self.progress_bar.setVisible(True)

            if determinate:
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(max(0, min(100, int(value))))
            else:
                self.progress_bar.setRange(0, 0)

            if text:
                self.progress_bar.setFormat(text)

        except Exception as e:
            logger.error(f"[AppStatusBar.show_progress] Failed: {e}")

    def hide_progress(self) -> None:
        if self.progress_bar:
            try:
                self.progress_bar.setVisible(False)
            except Exception as e:
                logger.error(f"[AppStatusBar.hide_progress] Failed: {e}")

    def reset(self):
        """Reset status bar to initial state"""
        try:
            self._operation_start_times.clear()
            self._current_status = "Ready"
            self._last_message_count = 0
            self._message_rate = 0
            self._peak_rate = 0
            self._last_snapshot = {}
            self._last_snapshot_time = None
            self._market_status = "UNKNOWN"

            self.update_status({}, self._current_mode, False)
            self.update_market_status("UNKNOWN")

        except Exception as e:
            logger.error(f"[AppStatusBar.reset] Failed: {e}")

    def cleanup(self):
        """Clean up resources before shutdown"""
        try:
            logger.info("[AppStatusBar] Starting cleanup")

            if self.blink_label:
                try:
                    self.blink_label.stop_animation()
                except Exception as e:
                    logger.warning(f"Error stopping animation: {e}")

            for timer in [self._update_timer, self._safety_timer]:
                if timer:
                    try:
                        if timer.isActive():
                            timer.stop()
                    except Exception as e:
                        logger.warning(f"Error stopping timer: {e}")

            if hasattr(self, '_tooltip') and self._tooltip:
                self._tooltip.hide()

            self.status_icon = None
            self.status_label = None
            self.mode_label = None
            self.timestamp_label = None
            self.op_fetch = None
            self.op_process = None
            self.op_order = None
            self.op_position = None
            self.op_connection = None
            self.op_market = None
            self.progress_bar = None
            self.blink_label = None
            self.metrics_container = None
            self.cpu_label = None
            self.memory_label = None
            self.pnl_label = None
            self.queue_label = None
            self.msg_rate_label = None
            self._update_timer = None
            self._safety_timer = None
            self._last_snapshot = {}
            self._last_snapshot_time = None

            logger.info("[AppStatusBar] Cleanup completed")

        except Exception as e:
            logger.error(f"[AppStatusBar.cleanup] Error: {e}", exc_info=True)