"""
Application Status Bar Module
==============================
Enhanced status bar component for the PyQt5 trading dashboard.

This module provides a comprehensive status bar that displays real-time information
about the application state, ongoing operations, and performance metrics. It features
animated indicators, tooltips, and visual feedback for various system states.

Architecture:
    The status bar is composed of several specialized components:

    1. **AnimatedLabel**: Custom QLabel with blinking/pulsing animations for active states
    2. **StatusToolTip**: Custom tooltip showing detailed operation timing
    3. **AppStatusBar**: Main status bar container with three sections:
        - Left section: Status indicator, text, and timestamp
        - Middle section: Operation indicators (fetching, processing, orders, positions)
        - Right section: Performance metrics (CPU, uptime, message rate)

Key Features:
    - **Visual Status Indicators**: Color-coded status icon (green=active, red=stopped)
    - **Operation Tracking**: Icons for history fetching, processing, orders, positions
    - **Connection Status**: Visual indicator for broker connectivity
    - **Animations**: Blinking and pulsing effects for important states
    - **Tooltips**: Hover tooltips with operation duration information
    - **Progress Bar**: Indeterminate/determinate progress for long operations
    - **Performance Metrics**: Uptime, message rate, CPU usage display
    - **Safety Timeout**: Automatic reset of stuck animations/indicators

Design Principles:
    - Rule 2: Safe defaults for all attributes
    - Rule 4: Structured logging throughout
    - Rule 6: Input validation on all public methods
    - Rule 8: Proper cleanup on shutdown

Dependencies:
    - PyQt5.QtCore: QPropertyAnimation, QEasingCurve, QTimer, Qt
    - PyQt5.QtWidgets: QHBoxLayout, QLabel, QFrame, QProgressBar, QWidget

Usage:
    status_bar = AppStatusBar(parent_window)

    # Update status from application state
    status_bar.update_status({
        'status': 'Running',
        'fetching_history': True,
        'processing': False,
        'order_pending': True,
        'has_position': True,
        'connection_status': 'Connected'
    }, mode='algo', app_running=True)

    # Show progress for long operations
    status_bar.show_progress(45, "Loading data...")

    # Update metrics
    status_bar.update_metrics({'cpu': 12.5, 'message_count': 1250})

Version: 1.0.0
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, pyqtProperty, QTimer, Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QFrame, QProgressBar, QWidget

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class AnimatedLabel(QLabel):
    """
    Label with blinking and pulsing animations for active states.

    This class extends QLabel to provide animated visual feedback for
    various application states. It supports multiple animation types:
        - BLINK: Opacity fades in and out
        - PULSE: Text scales up and down
        - FADE: Slow opacity transition (custom variant)

    The animations are implemented using QPropertyAnimation on custom
    properties (opacity and scale) to create smooth transitions.

    Attributes:
        BLINK: Constant for blink animation type
        PULSE: Constant for pulse animation type
        FADE: Constant for fade animation type
        _opacity: Current opacity value (0.0-1.0)
        _scale: Current scale factor (0.5-2.0)
    """

    # Add more animation types
    BLINK = "blink"
    PULSE = "pulse"
    FADE = "fade"

    def __init__(self, text="", parent=None):
        """
        Initialize animated label with default properties.

        Args:
            text: Initial label text
            parent: Parent widget
        """
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(text, parent)
            self._opacity = 1.0
            self._scale = 1.0

            # Blink animation (opacity)
            self._animation = QPropertyAnimation(self, b"opacity")
            self._animation.setDuration(800)  # 800ms per cycle
            self._animation.setStartValue(1.0)
            self._animation.setEndValue(0.3)
            self._animation.setLoopCount(-1)  # Infinite loop
            self._animation.setEasingCurve(QEasingCurve.InOutQuad)

            # Pulse animation (scale)
            self._pulse_animation = QPropertyAnimation(self, b"scale")
            self._pulse_animation.setDuration(1000)  # 1000ms per cycle
            self._pulse_animation.setStartValue(1.0)
            self._pulse_animation.setEndValue(1.2)
            self._pulse_animation.setLoopCount(-1)  # Infinite loop
            self._pulse_animation.setEasingCurve(QEasingCurve.InOutQuad)

            logger.debug("AnimatedLabel initialized")

        except Exception as e:
            logger.error(f"[AnimatedLabel.__init__] Failed: {e}", exc_info=True)
            super().__init__(text, parent)
            self._opacity = 1.0
            self._scale = 1.0
            self._animation = None
            self._pulse_animation = None

    def _safe_defaults_init(self):
        """
        Rule 2: Initialize all attributes with safe defaults.

        Ensures that all instance variables exist even if initialization fails,
        preventing attribute errors during error handling or cleanup.
        """
        self._opacity = 1.0
        self._scale = 1.0
        self._animation = None
        self._pulse_animation = None
        self._blinking = False
        self._pulsing = False
        self._animation_type = self.BLINK

    def get_opacity(self) -> float:
        """
        Get current opacity value.

        Returns:
            float: Current opacity between 0.0 and 1.0
        """
        try:
            return self._opacity
        except Exception as e:
            logger.error(f"[AnimatedLabel.get_opacity] Failed: {e}", exc_info=True)
            return 1.0

    def set_opacity(self, value: float) -> None:
        """
        Set opacity value and update stylesheet.

        Args:
            value: New opacity value (clamped to 0.0-1.0)

        Updates the label's stylesheet with RGBA color based on current
        opacity and stored base color.
        """
        try:
            if not isinstance(value, (int, float)):
                logger.warning(f"set_opacity called with non-numeric value: {value}")
                return

            self._opacity = max(0.0, min(1.0, float(value)))

            # Update stylesheet with opacity
            try:
                # Get current text color and apply opacity
                base_color = "#3fb950"  # Default green
                if hasattr(self, '_base_color'):
                    base_color = self._base_color

                # Convert hex to rgba
                r = int(base_color[1:3], 16)
                g = int(base_color[3:5], 16)
                b = int(base_color[5:7], 16)

                self.setStyleSheet(f"color: rgba({r}, {g}, {b}, {self._opacity}); font-size: {12 * self._scale}px;")
            except Exception as e:
                logger.error(f"Failed to set stylesheet with opacity {self._opacity}: {e}")

        except Exception as e:
            logger.error(f"[AnimatedLabel.set_opacity] Failed: {e}", exc_info=True)

    opacity = pyqtProperty(float, get_opacity, set_opacity)

    def get_scale(self) -> float:
        """
        Get current scale value.

        Returns:
            float: Current scale factor between 0.5 and 2.0
        """
        return self._scale

    def set_scale(self, value: float) -> None:
        """
        Set scale value and refresh display.

        Args:
            value: New scale factor (clamped to 0.5-2.0)
        """
        try:
            self._scale = max(0.5, min(2.0, float(value)))
            self.set_opacity(self._opacity)  # Refresh stylesheet
        except Exception as e:
            logger.error(f"[AnimatedLabel.set_scale] Failed: {e}")

    scale = pyqtProperty(float, get_scale, set_scale)

    def start_animation(self, animation_type: str = BLINK, color: str = "#3fb950") -> None:
        """
        Start animation of specified type.

        Args:
            animation_type: One of BLINK, PULSE, or FADE
            color: Base color for the animation (hex format)

        Note:
            Multiple animation types cannot run simultaneously.
            Starting a new animation stops any currently running one.
        """
        try:
            self._base_color = color
            self._animation_type = animation_type

            if animation_type == self.BLINK:
                if self._animation and not self._blinking:
                    self._animation.start()
                    self._blinking = True
                    logger.debug("Blink animation started")
            elif animation_type == self.PULSE:
                if self._pulse_animation and not self._pulsing:
                    self._pulse_animation.start()
                    self._pulsing = True
                    logger.debug("Pulse animation started")
            elif animation_type == self.FADE:
                # Custom fade effect - slower, deeper fade
                self._animation.setStartValue(1.0)
                self._animation.setEndValue(0.1)
                self._animation.setDuration(1500)
                self._animation.start()
                self._blinking = True

        except Exception as e:
            logger.error(f"[AnimatedLabel.start_animation] Failed: {e}", exc_info=True)

    def stop_animation(self) -> None:
        """
        Stop all animations and reset to normal state.

        Stops both blink and pulse animations and resets opacity/scale to 1.0.
        """
        try:
            if self._animation:
                self._animation.stop()
            if self._pulse_animation:
                self._pulse_animation.stop()

            self.set_opacity(1.0)
            self._scale = 1.0
            self._blinking = False
            self._pulsing = False
            logger.debug("Animations stopped")

        except Exception as e:
            logger.error(f"[AnimatedLabel.stop_animation] Failed: {e}", exc_info=True)


class StatusToolTip(QLabel):
    """
    Custom tooltip for showing detailed status information.

    This class provides a styled tooltip that can be shown at specific
    positions, used for displaying detailed operation information when
    hovering over status indicators.

    Features:
        - Custom dark theme styling matching the application
        - Auto-sizing based on content
        - Position control for precise placement
        - Automatic hiding when mouse leaves
    """

    def __init__(self, parent=None):
        """
        Initialize custom tooltip.

        Args:
            parent: Parent widget
        """
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
        """
        Show tooltip at specified screen position.

        Args:
            text: Tooltip text to display
            pos: QPoint screen position where tooltip should appear
                 (will be adjusted to avoid going off-screen)
        """
        self.setText(text)
        self.adjustSize()
        self.move(pos.x() + 20, pos.y() - self.height() - 10)
        self.show()

    def hide_event(self, event):
        """
        Handle hide event.

        Args:
            event: QHideEvent (ignored)
        """
        self.hide()


class AppStatusBar(QFrame):
    """
    Enhanced status bar showing application state, operations, and performance metrics.

    This is the main status bar component that provides a comprehensive view of
    the application's current state. It's divided into three logical sections:

    1. **Status Section** (left):
        - Color-coded status icon (red/green/yellow)
        - Status text (e.g., "Running", "Stopped", "Error")
        - Current timestamp

    2. **Operations Section** (middle):
        - Icons for ongoing operations (history fetch, processing, orders)
        - Position indicator when trade is active
        - Connection status indicator
        - Progress bar for long operations
        - Animated blink indicator for active states

    3. **Metrics Section** (right):
        - Performance metrics (CPU usage)
        - Uptime counter
        - Message rate (ticks/second)

    Features:
        - Hover tooltips with operation duration
        - Automatic operation timing tracking
        - Safety timeout to reset stuck indicators
        - Smooth animations for state changes
        - Comprehensive error handling

    Attributes:
        _current_status: Current status text
        _current_mode: Trading mode ("algo" or "manual")
        _app_running: Whether application is running
        _operation_start_times: Dict tracking when each operation started
        _metrics: Dict of current performance metrics
    """

    def __init__(self, parent=None):
        """
        Initialize the enhanced status bar.

        Args:
            parent: Parent widget
        """
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setFixedHeight(45)  # Slightly taller for better visibility

            # EXACT stylesheet preservation with enhancements
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

            # Left section - Status
            self._create_status_section(layout)

            # Middle section - Operations
            self._create_operations_section(layout)

            # Right section - Performance metrics
            self._create_metrics_section(layout)

            # State tracking
            self._current_status = "Ready"
            self._current_mode = "algo"
            self._app_running = False
            self._start_time = datetime.now()
            self._operation_start_times = {}
            self._last_update_time = datetime.now()

            # Update timer for dynamic updates
            self._update_timer = QTimer()
            self._update_timer.timeout.connect(self._update_dynamic_info)
            self._update_timer.start(1000)  # Update every second

            # Safety timer to prevent stuck animations
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
        """
        Rule 2: Initialize all attributes with safe defaults.

        Ensures that all instance variables exist even if initialization fails,
        preventing attribute errors during error handling or cleanup.
        """
        self.status_icon = None
        self.status_label = None
        self.mode_label = None
        self.timestamp_label = None
        self.performance_label = None
        self.op_fetch = None
        self.op_process = None
        self.op_order = None
        self.op_position = None
        self.progress_bar = None
        self.blink_label = None
        self.metrics_container = None
        self._current_status = "Ready"
        self._current_mode = "algo"
        self._app_running = False
        self._start_time = None
        self._operation_start_times = {}
        self._last_update_time = None
        self._update_timer = None
        self._safety_timer = None
        self._tooltip = None
        self._connection_status = "Disconnected"
        self._message_rate = 0
        self._last_message_count = 0
        self._metrics = {}

    def _create_status_section(self, layout):
        """
        Create left status section with status icon, text, and timestamp.

        Args:
            layout: Parent layout to add the section to
        """
        # Status container
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)

        # Status indicator with blinking
        self.status_icon = QLabel("●")
        self.status_icon.setStyleSheet("color: #f85149; font-size: 14px;")
        status_layout.addWidget(self.status_icon)

        self.status_label = QLabel("Ready")
        self.status_label.setProperty("cssClass", "status")
        status_layout.addWidget(self.status_label)

        # Timestamp
        self.timestamp_label = QLabel()
        self.timestamp_label.setProperty("cssClass", "timestamp")
        status_layout.addWidget(self.timestamp_label)

        layout.addWidget(status_container)

        # Separator
        layout.addWidget(self._create_separator())

    def _create_operations_section(self, layout):
        """
        Create middle operations section with mode indicator and operation icons.

        Args:
            layout: Parent layout to add the section to
        """
        # Operations container
        ops_container = QWidget()
        ops_layout = QHBoxLayout(ops_container)
        ops_layout.setContentsMargins(0, 0, 0, 0)
        ops_layout.setSpacing(10)

        # Mode indicator
        self.mode_label = QLabel("MODE: ALGO")
        self.mode_label.setProperty("cssClass", "mode")
        self.mode_label.setStyleSheet("background: #1f6feb; color: white;")
        ops_layout.addWidget(self.mode_label)

        # Operation indicators with tooltips
        self.op_fetch = self._create_op_indicator("📊", "Fetching history", "#f0883e")
        self.op_process = self._create_op_indicator("⚙️", "Processing", "#58a6ff")
        self.op_order = self._create_op_indicator("📝", "Order pending", "#d29922")
        self.op_position = self._create_op_indicator("💰", "Position active", "#3fb950")
        self.op_connection = self._create_op_indicator("🔌", "Connection status", "#8b949e")

        ops_layout.addWidget(self.op_fetch)
        ops_layout.addWidget(self.op_process)
        ops_layout.addWidget(self.op_order)
        ops_layout.addWidget(self.op_position)
        ops_layout.addWidget(self.op_connection)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(150)
        ops_layout.addWidget(self.progress_bar)

        # Blinking animation for active states
        self.blink_label = AnimatedLabel("●")
        self.blink_label.setVisible(False)
        ops_layout.addWidget(self.blink_label)

        layout.addWidget(ops_container)

        # Separator
        layout.addWidget(self._create_separator())

    def _create_metrics_section(self, layout):
        """
        Create right performance metrics section.

        Args:
            layout: Parent layout to add the section to
        """
        self.metrics_container = QWidget()
        metrics_layout = QHBoxLayout(self.metrics_container)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(8)

        # Performance metrics
        self.performance_label = QLabel()
        self.performance_label.setProperty("cssClass", "metric")
        metrics_layout.addWidget(self.performance_label)

        # Uptime
        self.uptime_label = QLabel()
        self.uptime_label.setProperty("cssClass", "metric")
        metrics_layout.addWidget(self.uptime_label)

        # Message rate
        self.rate_label = QLabel()
        self.rate_label.setProperty("cssClass", "metric")
        metrics_layout.addWidget(self.rate_label)

        layout.addWidget(self.metrics_container, 1)  # Stretch to fill

    def _create_separator(self) -> QFrame:
        """
        Create a vertical separator line.

        Returns:
            QFrame: Styled vertical separator
        """
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.VLine)
        return sep

    def _create_op_indicator(self, icon: str, tooltip: str, color: str) -> QLabel:
        """
        Create an operation indicator label with hover tooltip.

        Args:
            icon: Emoji or text for the indicator
            tooltip: Tooltip text to show on hover
            color: Default color for the indicator (when active)

        Returns:
            QLabel: Configured indicator label
        """
        try:
            if not isinstance(icon, str):
                icon = "?"

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

            # Enable mouse tracking for custom tooltip
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
        """
        Show detailed tooltip for operation with timing information.

        Args:
            label: The indicator label being hovered
            base_tooltip: Base tooltip text to display
        """
        try:
            # Create detailed tooltip with timing info
            tooltip_text = base_tooltip
            op_name = label.toolTip().split()[0].lower()

            if op_name in self._operation_start_times:
                start_time = self._operation_start_times[op_name]
                duration = (datetime.now() - start_time).total_seconds()
                tooltip_text += f"\nActive for: {duration:.1f}s"

            # Show tooltip
            if not hasattr(self, '_tooltip') or not self._tooltip:
                self._tooltip = StatusToolTip(self)

            pos = label.mapToGlobal(label.rect().topLeft())
            self._tooltip.show_at_position(tooltip_text, pos)

        except Exception as e:
            logger.error(f"[AppStatusBar._show_op_tooltip] Failed: {e}")

    def _hide_op_tooltip(self):
        """Hide operation tooltip."""
        if hasattr(self, '_tooltip') and self._tooltip:
            self._tooltip.hide()

    def update_status(self, status_info: Dict[str, Any], mode: str, app_running: bool) -> None:
        """
        Update status bar based on application state.

        This is the main update method that refreshes all status bar components
        based on the current application state.

        Args:
            status_info: Dictionary with status information. Expected keys:
                - status: Status text (e.g., "Running", "Error")
                - fetching_history: Boolean indicating history fetch in progress
                - processing: Boolean indicating tick processing active
                - order_pending: Boolean indicating pending orders
                - has_position: Boolean indicating active position
                - connection_status: String "Connected" or "Disconnected"
                - progress: Optional progress percentage (0-100)
            mode: Trading mode ('algo' or 'manual')
            app_running: Whether application is currently running

        Example:
            status_bar.update_status({
                'status': 'Processing',
                'fetching_history': True,
                'order_pending': False,
                'has_position': True,
                'connection_status': 'Connected',
                'progress': 45
            }, mode='algo', app_running=True)
        """
        try:
            # Input validation
            if status_info is None:
                status_info = {}

            self._current_mode = mode
            self._app_running = app_running
            self._last_update_time = datetime.now()

            # Update mode indicator
            self._update_mode_display()

            # Update status text and icon
            self._update_status_display(status_info)

            # Update operation indicators and track durations
            self._update_operation_indicators(status_info)

            # Update connection status
            self._update_connection_status(status_info)

            # Update progress bar
            self._update_progress_bar(status_info)

            # Update blink animation
            self._update_blink_animation(status_info)

            # Schedule safety update
            self._schedule_safety_update()

        except Exception as e:
            logger.error(f"[AppStatusBar.update_status] Failed: {e}", exc_info=True)

    def _update_mode_display(self):
        """Update mode indicator display based on current mode."""
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

    def _update_status_display(self, status_info: Dict[str, Any]):
        """
        Update status text and icon based on current state.

        Args:
            status_info: Status information dictionary
        """
        if self.status_icon is None or self.status_label is None:
            return

        try:
            # Update status text
            if 'status' in status_info:
                status_text = status_info['status']
                if isinstance(status_text, str):
                    self._current_status = status_text
                    self.status_label.setText(status_text)

            # Update timestamp
            if self.timestamp_label:
                self.timestamp_label.setText(datetime.now().strftime("%H:%M:%S"))

            # Update status icon color based on state
            if self._app_running:
                if status_info.get('fetching_history', False):
                    self.status_icon.setStyleSheet("color: #f0883e; font-size: 14px;")
                elif status_info.get('processing', False):
                    self.status_icon.setStyleSheet("color: #58a6ff; font-size: 14px;")
                elif status_info.get('order_pending', False):
                    self.status_icon.setStyleSheet("color: #d29922; font-size: 14px;")
                else:
                    self.status_icon.setStyleSheet("color: #3fb950; font-size: 14px;")
            else:
                self.status_icon.setStyleSheet("color: #f85149; font-size: 14px;")

        except Exception as e:
            logger.error(f"Failed to update status display: {e}")

    def _update_operation_indicators(self, status_info: Dict[str, Any]):
        """
        Update operation indicators and track operation durations.

        Args:
            status_info: Status information dictionary with boolean flags
        """
        operations = [
            ('fetching_history', self.op_fetch, "#f0883e"),
            ('processing', self.op_process, "#58a6ff"),
            ('order_pending', self.op_order, "#d29922"),
            ('has_position', self.op_position, "#3fb950")
        ]

        for key, label, color in operations:
            active = bool(status_info.get(key, False))

            # Track operation duration for tooltips
            if active:
                if key not in self._operation_start_times:
                    self._operation_start_times[key] = datetime.now()
            else:
                if key in self._operation_start_times:
                    del self._operation_start_times[key]

            # Update indicator
            self._update_op_indicator(label, active, color)

    def _update_connection_status(self, status_info: Dict[str, Any]):
        """
        Update connection status indicator.

        Args:
            status_info: Status information dictionary with connection_status key
        """
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
        """
        Update progress bar display.

        Args:
            status_info: Status information dictionary with progress key
        """
        if self.progress_bar is None:
            return

        try:
            if status_info.get('fetching_history', False):
                self.progress_bar.setVisible(True)
                self.progress_bar.setRange(0, 0)  # Indeterminate mode

                # Show progress if available
                if 'progress' in status_info:
                    self.progress_bar.setRange(0, 100)
                    self.progress_bar.setValue(status_info['progress'])
            else:
                self.progress_bar.setVisible(False)

        except Exception as e:
            logger.error(f"Failed to update progress bar: {e}")

    def _update_blink_animation(self, status_info: Dict[str, Any]):
        """
        Update blink animation for important states.

        Args:
            status_info: Status information dictionary with state flags
        """
        if self.blink_label is None:
            return

        try:
            should_blink = status_info.get('order_pending', False) or \
                           status_info.get('processing', False) or \
                           status_info.get('fetching_history', False)

            if should_blink:
                if not self.blink_label.isVisible():
                    self.blink_label.setVisible(True)

                    # Choose animation type based on operation
                    if status_info.get('order_pending', False):
                        self.blink_label.start_animation(AnimatedLabel.PULSE, "#d29922")
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

    def _update_dynamic_info(self):
        """
        Update dynamic information (uptime, rates, etc.) every second.

        This method is called by the update timer to refresh:
            - Application uptime
            - Performance metrics
            - Message rates
        """
        try:
            if not self._app_running:
                return

            # Calculate uptime
            if self._start_time:
                uptime = datetime.now() - self._start_time
                hours = uptime.seconds // 3600
                minutes = (uptime.seconds % 3600) // 60
                seconds = uptime.seconds % 60

                if self.uptime_label:
                    self.uptime_label.setText(f"⏱️ {hours:02d}:{minutes:02d}:{seconds:02d}")

            # Update performance metrics if available
            if self.performance_label and hasattr(self, '_metrics'):
                if 'cpu' in self._metrics:
                    self.performance_label.setText(f"💾 {self._metrics['cpu']:.1f}%")

            # Update message rate
            if self.rate_label and hasattr(self, '_last_message_count'):
                # This would be updated from outside
                pass

        except Exception as e:
            logger.error(f"[AppStatusBar._update_dynamic_info] Failed: {e}")

    def _update_op_indicator(self, label: Optional[QLabel], active: bool, color: str) -> None:
        """
        Update operation indicator color based on active state.

        Args:
            label: The indicator label to update
            active: Whether the operation is active
            color: Color to use when active
        """
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

    def _schedule_safety_update(self):
        """Schedule a safety update to ensure UI consistency after long operations."""
        if self._safety_timer and not self._safety_timer.isActive():
            self._safety_timer.start(10000)  # 10 second safety timeout

    def _safety_update(self):
        """
        Safety update to ensure UI doesn't get stuck in wrong state.

        This method checks for operations that have been active too long
        and resets them, preventing the UI from getting stuck in an
        inconsistent state.
        """
        try:
            logger.debug("Running safety update")

            # Check if any operation has been active too long
            for op, start_time in list(self._operation_start_times.items()):
                duration = (datetime.now() - start_time).total_seconds()
                if duration > 300:  # 5 minutes
                    logger.warning(f"Operation {op} has been active for {duration:.0f}s, resetting")
                    del self._operation_start_times[op]

            # Reset blink if stuck
            if self.blink_label and self.blink_label.isVisible():
                if not any([
                    op in self._operation_start_times
                    for op in ['fetching_history', 'processing', 'order_pending']
                ]):
                    logger.warning("Safety update: hiding stuck blink label")
                    self.blink_label.stop_animation()
                    self.blink_label.setVisible(False)

        except Exception as e:
            logger.error(f"Safety update failed: {e}")

    def update_metrics(self, metrics: Dict[str, Any]):
        """
        Update performance metrics from external sources.

        Args:
            metrics: Dictionary with performance metrics:
                - cpu: CPU usage percentage
                - message_count: Total messages received
                - Additional metrics as needed
        """
        try:
            self._metrics.update(metrics)

            # Update message rate if available
            if 'message_count' in metrics:
                count = metrics['message_count']
                if hasattr(self, '_last_message_count'):
                    rate = count - self._last_message_count
                    self._message_rate = rate
                    if self.rate_label:
                        self.rate_label.setText(f"📨 {rate}/s")
                self._last_message_count = count

        except Exception as e:
            logger.error(f"[AppStatusBar.update_metrics] Failed: {e}")

    def show_progress(self, value: int, text: str = "", determinate: bool = True) -> None:
        """
        Show progress bar with specified value.

        Args:
            value: Progress percentage (0-100) for determinate mode
            text: Optional text to display on progress bar
            determinate: True for determinate progress, False for indeterminate
        """
        if self.progress_bar is None:
            return

        try:
            self.progress_bar.setVisible(True)

            if determinate:
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(max(0, min(100, int(value))))
            else:
                self.progress_bar.setRange(0, 0)  # Indeterminate mode

            if text:
                self.progress_bar.setFormat(text)

            logger.debug(f"Progress shown: {value}% - {text}")

        except Exception as e:
            logger.error(f"[AppStatusBar.show_progress] Failed: {e}")

    def hide_progress(self) -> None:
        """Hide progress bar."""
        if self.progress_bar:
            try:
                self.progress_bar.setVisible(False)
                logger.debug("Progress bar hidden")
            except Exception as e:
                logger.error(f"[AppStatusBar.hide_progress] Failed: {e}")

    def reset(self):
        """
        Reset status bar to initial state.

        Clears all operation timers and resets all indicators to default state.
        """
        try:
            self._operation_start_times.clear()
            self._current_status = "Ready"
            self._last_message_count = 0
            self._message_rate = 0

            # Reset all indicators
            self.update_status({}, self._current_mode, False)

        except Exception as e:
            logger.error(f"[AppStatusBar.reset] Failed: {e}")

    # Rule 8: Cleanup method
    def cleanup(self):
        """
        Clean up resources before application shutdown.

        Rule 8: Proper resource cleanup to prevent memory leaks.
        Stops animations, timers, and clears references.
        """
        try:
            logger.info("[AppStatusBar] Starting cleanup")

            # Stop animations
            if self.blink_label:
                try:
                    self.blink_label.stop_animation()
                except Exception as e:
                    logger.warning(f"Error stopping animation: {e}")

            # Stop timers
            for timer in [self._update_timer, self._safety_timer]:
                if timer:
                    try:
                        if timer.isActive():
                            timer.stop()
                    except Exception as e:
                        logger.warning(f"Error stopping timer: {e}")

            # Hide tooltip
            if hasattr(self, '_tooltip') and self._tooltip:
                self._tooltip.hide()

            # Clear references
            self.status_icon = None
            self.status_label = None
            self.mode_label = None
            self.timestamp_label = None
            self.performance_label = None
            self.uptime_label = None
            self.rate_label = None
            self.op_fetch = None
            self.op_process = None
            self.op_order = None
            self.op_position = None
            self.op_connection = None
            self.progress_bar = None
            self.blink_label = None
            self.metrics_container = None
            self._update_timer = None
            self._safety_timer = None

            logger.info("[AppStatusBar] Cleanup completed")

        except Exception as e:
            logger.error(f"[AppStatusBar.cleanup] Error: {e}", exc_info=True)