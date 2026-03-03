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
from data.trade_state_manager import state_manager

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

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
        self._color_token = "GREEN_BRIGHT"

    # =========================================================================
    # Shorthand properties for theme tokens
    # =========================================================================
    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def get_opacity(self) -> float:
        return self._opacity

    def set_opacity(self, value: float) -> None:
        try:
            if not isinstance(value, (int, float)):
                return

            self._opacity = max(0.0, min(1.0, float(value)))
            self._update_style()

        except Exception as e:
            logger.error(f"[AnimatedLabel.set_opacity] Failed: {e}", exc_info=True)

    opacity = pyqtProperty(float, get_opacity, set_opacity)

    def get_scale(self) -> float:
        return self._scale

    def set_scale(self, value: float) -> None:
        try:
            self._scale = max(0.5, min(2.0, float(value)))
            self._update_style()
        except Exception as e:
            logger.error(f"[AnimatedLabel.set_scale] Failed: {e}")

    scale = pyqtProperty(float, get_scale, set_scale)

    def _update_style(self):
        """Update stylesheet with current opacity and scale"""
        try:
            c = self._c
            color = c.get(self._color_token, c.GREEN_BRIGHT)

            # Parse color hex to RGB
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)

            base_size = self._ty.SIZE_BODY
            self.setStyleSheet(
                f"color: rgba({r}, {g}, {b}, {self._opacity}); "
                f"font-size: {base_size * self._scale}pt;"
            )
        except Exception as e:
            logger.error(f"[AnimatedLabel._update_style] Failed: {e}")

    def start_animation(self, animation_type: str = BLINK, color_token: str = "GREEN_BRIGHT") -> None:
        try:
            self._color_token = color_token
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

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to animation"""
        try:
            self._update_style()
        except Exception as e:
            logger.error(f"[AnimatedLabel.apply_theme] Failed: {e}", exc_info=True)


class StatusToolTip(QLabel):
    """Custom tooltip for showing detailed status information."""

    def __init__(self, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)
            self.setWordWrap(True)
            self.setMaximumWidth(300)
            self.hide()
            self.apply_theme()
        except Exception as e:
            logger.error(f"[StatusToolTip.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self.setWordWrap(True)
            self.setMaximumWidth(300)
            self.hide()

    def _safe_defaults_init(self):
        pass

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to tooltip"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            self.setStyleSheet(f"""
                QLabel {{
                    background: {c.BG_PANEL};
                    color: {c.TEXT_MAIN};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                    padding: {sp.PAD_SM}px;
                    font-size: {ty.SIZE_SM}pt;
                }}
            """)
        except Exception as e:
            logger.error(f"[StatusToolTip.apply_theme] Failed: {e}", exc_info=True)

    def show_at_position(self, text: str, pos):
        try:
            self.setText(text)
            self.adjustSize()
            self.move(pos.x() + 20, pos.y() - self.height() - 10)
            self.show()
        except Exception as e:
            logger.error(f"[StatusToolTip.show_at_position] Failed: {e}", exc_info=True)


class AppStatusBar(QFrame):
    """
    Enhanced status bar showing application state, operations, and performance metrics.

    UPDATED: Shows connection status, system metrics, and trading statistics.
    """

    def __init__(self, parent=None):
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            # Build UI first, then apply theme
            self._build_ui()
            self.apply_theme()

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
        self.trading_app = None

    # =========================================================================
    # Shorthand properties for theme tokens
    # =========================================================================
    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def _build_ui(self):
        """Build the UI structure (without hardcoded styles)"""
        try:
            # Rule 3: No fixed heights - use tokens in apply_theme
            layout = QHBoxLayout(self)
            layout.setObjectName("mainLayout")
            # Margins and spacing will be set in apply_theme

            # Left section - Status + Timestamp
            self._create_status_section(layout)

            # Middle section - Operations + Market + Connection
            self._create_operations_section(layout)

            # Right section - System + Trading Metrics
            self._create_metrics_section(layout)

        except Exception as e:
            logger.error(f"[AppStatusBar._build_ui] Failed: {e}", exc_info=True)

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors and spacing to all components.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # =============================================================
            # 1. Update layout margins and spacing
            # =============================================================
            layout = self.layout()
            if layout:
                layout.setContentsMargins(sp.PAD_MD, sp.PAD_XS, sp.PAD_MD, sp.PAD_XS)
                layout.setSpacing(sp.GAP_MD)

            # =============================================================
            # 2. Update height (Rule 3: no fixed heights)
            # =============================================================
            self.setMinimumHeight(sp.STATUS_BAR_H - 8)
            self.setMaximumHeight(sp.STATUS_BAR_H + 8)

            # =============================================================
            # 3. Main frame stylesheet
            # =============================================================
            self.setStyleSheet(f"""
                QFrame {{
                    background: {c.BAR_BG};
                    border: {sp.SEPARATOR}px solid {c.BAR_BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                }}
                QLabel {{
                    color: {c.TEXT_DIM};
                    font-size: {ty.SIZE_SM}pt;
                }}
                QLabel[cssClass="status"] {{
                    color: {c.BLUE};
                    font-weight: {ty.WEIGHT_BOLD};
                }}
                QLabel[cssClass="mode"] {{
                    color: {c.TEXT_MAIN};
                    font-weight: {ty.WEIGHT_BOLD};
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    border-radius: {sp.RADIUS_PILL}px;
                }}
                QLabel[cssClass="timestamp"] {{
                    color: {c.TEXT_DISABLED};
                    font-size: {ty.SIZE_XS}pt;
                    padding: {sp.PAD_XS}px {sp.PAD_XS}px;
                }}
                QLabel[cssClass="metric"] {{
                    color: {c.BLUE};
                    font-size: {ty.SIZE_XS}pt;
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    background: {c.BG_HOVER};
                    border-radius: {sp.RADIUS_SM}px;
                }}
                QLabel[cssClass="market"] {{
                    font-size: {ty.SIZE_XS}pt;
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    border-radius: {sp.RADIUS_PILL}px;
                    font-weight: {ty.WEIGHT_BOLD};
                }}
                QProgressBar {{
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                    text-align: center;
                    color: {c.TEXT_MAIN};
                    background: {c.BG_INPUT};
                    max-height: {sp.PROGRESS_SM}px;
                    min-height: {sp.PROGRESS_SM}px;
                }}
                QProgressBar::chunk {{
                    background: {c.GREEN};
                    border-radius: {sp.RADIUS_SM}px;
                }}
                QFrame#separator {{
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    max-width: {sp.SEPARATOR}px;
                    min-width: {sp.SEPARATOR}px;
                }}
            """)

            # =============================================================
            # 4. Update status icon
            # =============================================================
            if self.status_icon:
                self._update_status_icon_color()

            # =============================================================
            # 5. Update mode label
            # =============================================================
            if self.mode_label:
                self._update_mode_display()

            # =============================================================
            # 6. Update operation indicators
            # =============================================================
            self._update_all_op_indicators()

            # =============================================================
            # 7. Update tooltip theme
            # =============================================================
            if hasattr(self, '_tooltip') and self._tooltip:
                self._tooltip.apply_theme()

            # =============================================================
            # 8. Update blink label theme
            # =============================================================
            if self.blink_label:
                self.blink_label.apply_theme()

            logger.debug(f"[AppStatusBar.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[AppStatusBar.apply_theme] Failed: {e}", exc_info=True)

    def _create_status_section(self, layout):
        """Create left status section with icon, text, and timestamp"""
        try:
            status_container = QWidget()
            status_layout = QHBoxLayout(status_container)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setSpacing(self._sp.GAP_SM)

            self.status_icon = QLabel("●")
            status_layout.addWidget(self.status_icon)

            self.status_label = QLabel("Ready")
            self.status_label.setProperty("cssClass", "status")
            status_layout.addWidget(self.status_label)

            self.timestamp_label = QLabel()
            self.timestamp_label.setProperty("cssClass", "timestamp")
            status_layout.addWidget(self.timestamp_label)

            layout.addWidget(status_container)
            layout.addWidget(self._create_separator())

        except Exception as e:
            logger.error(f"[AppStatusBar._create_status_section] Failed: {e}", exc_info=True)

    def _create_operations_section(self, layout):
        """Create middle operations section with indicators"""
        try:
            ops_container = QWidget()
            ops_layout = QHBoxLayout(ops_container)
            ops_layout.setContentsMargins(0, 0, 0, 0)
            ops_layout.setSpacing(self._sp.GAP_MD)

            # Mode indicator
            self.mode_label = QLabel("MODE: ALGO")
            self.mode_label.setProperty("cssClass", "mode")
            ops_layout.addWidget(self.mode_label)

            # Operation indicators
            self.op_fetch = self._create_op_indicator("📊", "Fetching history")
            self.op_process = self._create_op_indicator("⚙️", "Processing")
            self.op_order = self._create_op_indicator("📝", "Order pending")
            self.op_position = self._create_op_indicator("💰", "Position active")
            self.op_connection = self._create_op_indicator("🔌", "Connection status")
            self.op_market = self._create_op_indicator("📈", "Market status")

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

        except Exception as e:
            logger.error(f"[AppStatusBar._create_operations_section] Failed: {e}", exc_info=True)

    def _create_metrics_section(self, layout):
        """Create right metrics section with system and trading stats"""
        try:
            self.metrics_container = QWidget()
            metrics_layout = QHBoxLayout(self.metrics_container)
            metrics_layout.setContentsMargins(0, 0, 0, 0)
            metrics_layout.setSpacing(self._sp.GAP_SM)

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

        except Exception as e:
            logger.error(f"[AppStatusBar._create_metrics_section] Failed: {e}", exc_info=True)

    def _create_separator(self) -> QFrame:
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.VLine)
        return sep

    def _create_op_indicator(self, icon: str, tooltip: str) -> QLabel:
        try:
            label = QLabel(icon)
            label.setToolTip(tooltip)

            label.setMouseTracking(True)
            label.enterEvent = lambda e: self._show_op_tooltip(label, tooltip)
            label.leaveEvent = lambda e: self._hide_op_tooltip()

            # Initial inactive style (will be updated by _update_all_op_indicators)
            self._update_op_indicator(label, False, "TEXT_DISABLED")

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
                self._update_op_indicator(self.op_market, True, "GREEN_BRIGHT")
                self.op_market.setToolTip("Market: OPEN")
            elif status == "CLOSED":
                self.op_market.setText("📉")
                self._update_op_indicator(self.op_market, True, "RED_BRIGHT")
                self.op_market.setToolTip("Market: CLOSED")
            else:
                self.op_market.setText("📊")
                self._update_op_indicator(self.op_market, False, "TEXT_DISABLED")
                self.op_market.setToolTip("Market: UNKNOWN")

        except Exception as e:
            logger.error(f"[AppStatusBar.update_market_status] Failed: {e}", exc_info=True)

    def _update_mode_display(self):
        if self.mode_label is None:
            return

        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            if self._current_mode == "algo":
                self.mode_label.setText("MODE: ALGO")
                self.mode_label.setStyleSheet(f"""
                    background: {c.BLUE_DARK}; 
                    color: {c.TEXT_INVERSE}; 
                    border-radius: {sp.RADIUS_PILL}px;
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    font-size: {ty.SIZE_SM}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                """)
            else:
                self.mode_label.setText("MODE: MANUAL")
                self.mode_label.setStyleSheet(f"""
                    background: {c.YELLOW}; 
                    color: {c.TEXT_INVERSE}; 
                    border-radius: {sp.RADIUS_PILL}px;
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    font-size: {ty.SIZE_SM}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                """)
        except Exception as e:
            logger.error(f"Failed to update mode label: {e}")

    def _update_status_icon_color(self):
        """Update status icon color based on current state"""
        try:
            c = self._c
            if self.status_icon is None:
                return

            if self._app_running:
                self.status_icon.setStyleSheet(f"color: {c.GREEN_BRIGHT}; font-size: {self._ty.SIZE_MD}pt;")
            else:
                self.status_icon.setStyleSheet(f"color: {c.RED_BRIGHT}; font-size: {self._ty.SIZE_MD}pt;")
        except Exception as e:
            logger.error(f"[AppStatusBar._update_status_icon_color] Failed: {e}")

    def _update_status_display(self, status_info: Dict[str, Any], snapshot: Dict[str, Any]):
        if self.status_icon is None or self.status_label is None:
            return

        try:
            c = self._c

            if 'status' in status_info:
                status_text = status_info['status']
                if isinstance(status_text, str):
                    self._current_status = status_text
                    self.status_label.setText(status_text)

            if self.timestamp_label:
                self.timestamp_label.setText(datetime.now().strftime("%H:%M:%S"))

            # Status icon color based on state
            if self._app_running:
                if status_info.get('fetching_history', False):
                    self.status_icon.setStyleSheet(f"color: {c.ORANGE}; font-size: {self._ty.SIZE_MD}pt;")
                elif status_info.get('processing', False):
                    self.status_icon.setStyleSheet(f"color: {c.BLUE}; font-size: {self._ty.SIZE_MD}pt;")
                elif status_info.get('order_pending', False):
                    self.status_icon.setStyleSheet(f"color: {c.YELLOW_BRIGHT}; font-size: {self._ty.SIZE_MD}pt;")
                elif snapshot.get('current_position') is not None:
                    self.status_icon.setStyleSheet(f"color: {c.GREEN_BRIGHT}; font-size: {self._ty.SIZE_MD}pt;")
                else:
                    self.status_icon.setStyleSheet(f"color: {c.GREEN_BRIGHT}; font-size: {self._ty.SIZE_MD}pt;")
            else:
                self.status_icon.setStyleSheet(f"color: {c.RED_BRIGHT}; font-size: {self._ty.SIZE_MD}pt;")

        except Exception as e:
            logger.error(f"Failed to update status display: {e}")

    def _update_all_op_indicators(self):
        """Update all operation indicators to inactive state with proper theme colors"""
        try:
            if self.op_fetch:
                self._update_op_indicator(self.op_fetch, False, "TEXT_DISABLED")
            if self.op_process:
                self._update_op_indicator(self.op_process, False, "TEXT_DISABLED")
            if self.op_order:
                self._update_op_indicator(self.op_order, False, "TEXT_DISABLED")
            if self.op_position:
                self._update_op_indicator(self.op_position, False, "TEXT_DISABLED")
            if self.op_connection:
                self._update_op_indicator(self.op_connection, False, "TEXT_DISABLED")
            if self.op_market:
                self._update_op_indicator(self.op_market, False, "TEXT_DISABLED")
        except Exception as e:
            logger.error(f"[AppStatusBar._update_all_op_indicators] Failed: {e}")

    def _update_operation_indicators(self, status_info: Dict[str, Any], snapshot: Dict[str, Any]):
        operations = [
            ('fetching_history', self.op_fetch, "ORANGE"),
            ('processing', self.op_process, "BLUE"),
            ('order_pending', self.op_order, "YELLOW_BRIGHT"),
            ('has_position', self.op_position, "GREEN_BRIGHT")
        ]

        for key, label, color_token in operations:
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

            self._update_op_indicator(label, active, color_token)

    def _update_connection_status(self, status_info: Dict[str, Any]):
        if self.op_connection is None:
            return

        try:
            is_connected = status_info.get('connection_status') == "Connected"

            if is_connected:
                self._update_op_indicator(self.op_connection, True, "GREEN_BRIGHT")
                self.op_connection.setToolTip("Connected to broker")
            else:
                self._update_op_indicator(self.op_connection, False, "TEXT_DISABLED")
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
                        self.blink_label.start_animation(AnimatedLabel.PULSE, "YELLOW_BRIGHT")
                    elif snapshot.get('signal_conflict', False):
                        self.blink_label.start_animation(AnimatedLabel.PULSE, "RED_BRIGHT")
                    elif status_info.get('processing', False):
                        self.blink_label.start_animation(AnimatedLabel.BLINK, "BLUE")
                    elif status_info.get('fetching_history', False):
                        self.blink_label.start_animation(AnimatedLabel.FADE, "ORANGE")
            else:
                if self.blink_label.isVisible():
                    self.blink_label.stop_animation()
                    self.blink_label.setVisible(False)

        except Exception as e:
            logger.error(f"Failed to update blink animation: {e}")

    def _update_op_indicator(self, label: Optional[QLabel], active: bool, color_token: str) -> None:
        if label is None:
            return

        try:
            c = self._c
            sp = self._sp

            if active:
                color = c.get(color_token, c.BLUE)
                label.setStyleSheet(f"""
                    QLabel {{
                        color: {color};
                        font-size: {self._ty.SIZE_MD}pt;
                        padding: {sp.PAD_XS}px {sp.PAD_XS}px;
                        font-weight: {self._ty.WEIGHT_BOLD};
                    }}
                    QLabel:hover {{
                        background: {c.BG_HOVER};
                        border-radius: {sp.RADIUS_SM}px;
                    }}
                """)
            else:
                label.setStyleSheet(f"""
                    QLabel {{
                        color: {c.TEXT_DISABLED};
                        font-size: {self._ty.SIZE_MD}pt;
                        padding: {sp.PAD_XS}px {sp.PAD_XS}px;
                    }}
                    QLabel:hover {{
                        background: {c.BG_HOVER};
                        border-radius: {sp.RADIUS_SM}px;
                    }}
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
            c = self._c
            sp = self._sp

            # System metrics
            try:
                # CPU
                cpu_percent = psutil.cpu_percent(interval=0.1)
                if cpu_percent > 90:
                    cpu_color = c.RED_BRIGHT
                elif cpu_percent > 70:
                    cpu_color = c.YELLOW_BRIGHT
                else:
                    cpu_color = c.BLUE

                self.cpu_label.setText(f"💾 {cpu_percent:.0f}%")
                self.cpu_label.setStyleSheet(f"""
                    color: {cpu_color}; 
                    background: {c.BG_HOVER}; 
                    border-radius: {sp.RADIUS_SM}px; 
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    font-size: {self._ty.SIZE_XS}pt;
                """)

                # Memory
                mem = psutil.virtual_memory()
                if mem.percent > 90:
                    mem_color = c.RED_BRIGHT
                elif mem.percent > 80:
                    mem_color = c.YELLOW_BRIGHT
                else:
                    mem_color = c.BLUE

                self.memory_label.setText(f"📀 {mem.percent:.0f}%")
                self.memory_label.setStyleSheet(f"""
                    color: {mem_color}; 
                    background: {c.BG_HOVER}; 
                    border-radius: {sp.RADIUS_SM}px; 
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    font-size: {self._ty.SIZE_XS}pt;
                """)
            except Exception as e:
                logger.debug(f"Failed to get system metrics: {e}")

            # Trading metrics
            # P&L
            pnl = pos_snapshot.get('current_pnl', 0)
            if pnl:
                pnl_color = c.GREEN_BRIGHT if pnl > 0 else c.RED_BRIGHT
                self.pnl_label.setText(f"💰 ₹{pnl:,.0f}")
                self.pnl_label.setStyleSheet(f"""
                    color: {pnl_color}; 
                    background: {c.BG_HOVER}; 
                    border-radius: {sp.RADIUS_SM}px; 
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    font-size: {self._ty.SIZE_XS}pt;
                """)
            else:
                self.pnl_label.setText("💰 ₹0")
                self.pnl_label.setStyleSheet(f"""
                    color: {c.BLUE}; 
                    background: {c.BG_HOVER}; 
                    border-radius: {sp.RADIUS_SM}px; 
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    font-size: {self._ty.SIZE_XS}pt;
                """)

            # Queue size
            if hasattr(self, 'trading_app') and self.trading_app and hasattr(self.trading_app, '_tick_queue'):
                qsize = self.trading_app._tick_queue.qsize()
                if qsize > 100:
                    queue_color = c.RED_BRIGHT
                elif qsize > 50:
                    queue_color = c.YELLOW_BRIGHT
                else:
                    queue_color = c.BLUE

                self.queue_label.setText(f"📥 {qsize}")
                self.queue_label.setStyleSheet(f"""
                    color: {queue_color}; 
                    background: {c.BG_HOVER}; 
                    border-radius: {sp.RADIUS_SM}px; 
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    font-size: {self._ty.SIZE_XS}pt;
                """)

            # Message rate
            if hasattr(self, 'trading_app') and self.trading_app and hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                ws = self.trading_app.ws
                if hasattr(ws, 'get_statistics'):
                    stats = ws.get_statistics()
                    msg_count = stats.get('message_count', 0)

                    # Calculate rate
                    if hasattr(self, '_last_msg_count'):
                        rate = msg_count - self._last_msg_count
                        if rate > self._peak_rate:
                            self._peak_rate = rate

                        if rate > 100:
                            rate_color = c.RED_BRIGHT
                        elif rate > 50:
                            rate_color = c.YELLOW_BRIGHT
                        else:
                            rate_color = c.BLUE

                        self.msg_rate_label.setText(f"📨 {rate}/s")
                        self.msg_rate_label.setStyleSheet(f"""
                            color: {rate_color}; 
                            background: {c.BG_HOVER}; 
                            border-radius: {sp.RADIUS_SM}px; 
                            padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                            font-size: {self._ty.SIZE_XS}pt;
                        """)

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
        """Clean up resources before shutdown - Rule 7"""
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

            # Nullify references
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