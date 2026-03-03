"""
Connection Monitor Popup - Displays WebSocket and broker connection status

UPDATED: Now uses state_manager instead of direct state access.
FIXED: Removed P&L and MTF tabs as they're not required.
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""
import logging
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QGridLayout, QTabWidget, \
    QFrame

# Import state manager
from data.trade_state_manager import state_manager
# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


class ConnectionMonitorPopup(QDialog):
    """Popup window for monitoring connection status"""

    def __init__(self, trading_app=None, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.trading_app = trading_app
            self.setWindowTitle("Connection Monitor")
            self.resize(700, 500)
            self.setMinimumSize(650, 450)

            # Set window flags
            self.setWindowFlags(Qt.Window)

            # Build UI (without hardcoded styles)
            self._init_ui()

            # Apply theme initially
            self.apply_theme()

            # Initialize timer
            self._init_timer()

            logger.info("ConnectionMonitorPopup initialized")

        except Exception as e:
            logger.critical(f"[ConnectionMonitorPopup.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.trading_app = None
        self.timer = None
        self.reconnect_btn = None
        self.test_btn = None
        self.refresh_btn = None

        # Connection tab labels
        self.ws_status_label = None
        self.ws_connected_since = None
        self.ws_last_message = None
        self.ws_msg_count = None
        self.ws_reconnects = None
        self.ws_errors = None
        self.broker_status_label = None
        self.token_expiry_label = None
        self.last_api_call = None
        self.rate_limit = None
        self.symbols_subscribed = None
        self.active_symbols = None
        self.option_chain_size = None

        # Statistics tab labels
        self.uptime_label = None
        self.msg_rate = None
        self.peak_rate = None
        self.data_received = None
        self.conn_events = None
        self.last_disconnect = None

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

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the popup.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Apply main stylesheet
            self.setStyleSheet(self._get_stylesheet())

            # Update button styles
            if self.reconnect_btn:
                self.reconnect_btn.setStyleSheet(self._get_button_style("reconnect"))

            if self.test_btn:
                self.test_btn.setStyleSheet(self._get_button_style("test"))

            if self.refresh_btn:
                self.refresh_btn.setStyleSheet(self._get_button_style("normal"))

            # Update status labels based on current state (will be refreshed in refresh())
            self._update_status_label_styles()

            logger.debug("[ConnectionMonitorPopup.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.apply_theme] Failed: {e}", exc_info=True)

    def _get_stylesheet(self) -> str:
        """Generate stylesheet with current theme tokens"""
        c = self._c
        ty = self._ty
        sp = self._sp

        return f"""
            QDialog {{ 
                background: {c.BG_MAIN}; 
                color: {c.TEXT_MAIN}; 
            }}
            QTabWidget::pane {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                background: {c.BG_MAIN};
            }}
            QTabBar::tab {{
                background: {c.BG_PANEL};
                color: {c.TEXT_DIM};
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                border: {sp.SEPARATOR}px solid {c.BORDER};
                font-size: {ty.SIZE_SM}pt;
            }}
            QTabBar::tab:selected {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border-bottom: {sp.PAD_XS}px solid {c.BLUE};
            }}
            QGroupBox {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                margin-top: {sp.PAD_MD}px;
                font-weight: {ty.WEIGHT_BOLD};
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_SM}pt;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {sp.PAD_MD}px;
                padding: 0 {sp.PAD_XS}px 0 {sp.PAD_XS}px;
            }}
            QLabel {{ 
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_SM}pt;
            }}
            QLabel#section-header {{
                font-weight: {ty.WEIGHT_BOLD};
                color: {c.BLUE};
                font-size: {ty.SIZE_BODY}pt;
            }}
            QLabel#value {{
                color: {c.BLUE};
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QLabel#warning {{
                color: {c.YELLOW_BRIGHT};
            }}
            QLabel#success {{
                color: {c.GREEN};
            }}
            QLabel#error {{
                color: {c.RED};
            }}
            QPushButton {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {ty.SIZE_SM}pt;
                min-width: 120px;
            }}
            QPushButton:hover {{ 
                background: {c.BORDER}; 
            }}
            QFrame#separator {{
                border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
            }}
        """

    def _get_button_style(self, button_type: str) -> str:
        """Get styled button for specific types"""
        c = self._c
        sp = self._sp
        ty = self._ty

        if button_type == "reconnect":
            bg = c.GREEN
            bg_hover = c.GREEN_BRIGHT
            border = c.GREEN_BRIGHT
        elif button_type == "test":
            bg = c.BLUE_DARK
            bg_hover = c.BLUE
            border = c.BLUE
        else:
            bg = c.BG_HOVER
            bg_hover = c.BORDER
            border = c.BORDER

        return f"""
            QPushButton {{
                background: {bg};
                color: {c.TEXT_INVERSE};
                border: {sp.SEPARATOR}px solid {border};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {ty.SIZE_SM}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QPushButton:hover {{
                background: {bg_hover};
            }}
            QPushButton:disabled {{
                background: {c.BG_HOVER};
                color: {c.TEXT_DISABLED};
                border: {sp.SEPARATOR}px solid {c.BORDER};
            }}
        """

    def _update_status_label_styles(self):
        """Update status label styles based on current connection state"""
        try:
            c = self._c

            # WebSocket status
            if self.ws_status_label:
                is_connected = "Connected" in self.ws_status_label.text()
                color = c.GREEN if is_connected else c.RED
                self.ws_status_label.setStyleSheet(f"color: {color}; font-weight: {self._ty.WEIGHT_BOLD};")

            # Broker status
            if self.broker_status_label:
                is_connected = "Connected" in self.broker_status_label.text()
                color = c.GREEN if is_connected else c.RED
                self.broker_status_label.setStyleSheet(f"color: {color}; font-weight: {self._ty.WEIGHT_BOLD};")

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._update_status_label_styles] Failed: {e}")

    def _init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD)
        layout.setSpacing(self._sp.GAP_MD)

        # Create tab widget
        tabs = QTabWidget()

        # Tab 1: Connection Status
        conn_tab = self._create_connection_tab()
        tabs.addTab(conn_tab, "🔌 Connection")

        # Tab 2: Statistics
        stats_tab = self._create_statistics_tab()
        tabs.addTab(stats_tab, "📊 Statistics")

        layout.addWidget(tabs)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(self._sp.GAP_MD)

        self.reconnect_btn = QPushButton("🔄 Reconnect WebSocket")
        self.reconnect_btn.clicked.connect(self._reconnect)

        self.test_btn = QPushButton("🧪 Test Connection")
        self.test_btn.clicked.connect(self._test_connection)

        self.refresh_btn = QPushButton("⟳ Refresh")
        self.refresh_btn.clicked.connect(self.refresh)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        button_layout.addWidget(self.reconnect_btn)
        button_layout.addWidget(self.test_btn)
        button_layout.addWidget(self.refresh_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _create_connection_tab(self) -> QGroupBox:
        """Create connection status tab"""
        widget = QGroupBox("Connection Status")
        layout = QGridLayout(widget)
        layout.setVerticalSpacing(self._sp.GAP_SM)
        layout.setHorizontalSpacing(self._sp.GAP_MD)

        row = 0

        # WebSocket Connection Group
        ws_label = QLabel("🌐 WebSocket")
        ws_label.setObjectName("section-header")
        layout.addWidget(ws_label, row, 0, 1, 2)
        row += 1

        # Status
        layout.addWidget(self._create_label("Status:"), row, 0)
        self.ws_status_label = self._create_label("Disconnected")
        layout.addWidget(self.ws_status_label, row, 1)
        row += 1

        # Connected since
        layout.addWidget(self._create_label("Connected Since:"), row, 0)
        self.ws_connected_since = self._create_value_label("-")
        layout.addWidget(self.ws_connected_since, row, 1)
        row += 1

        # Last message
        layout.addWidget(self._create_label("Last Message:"), row, 0)
        self.ws_last_message = self._create_value_label("-")
        layout.addWidget(self.ws_last_message, row, 1)
        row += 1

        # Messages received
        layout.addWidget(self._create_label("Messages Received:"), row, 0)
        self.ws_msg_count = self._create_value_label("0")
        layout.addWidget(self.ws_msg_count, row, 1)
        row += 1

        # Reconnect count
        layout.addWidget(self._create_label("Reconnects:"), row, 0)
        self.ws_reconnects = self._create_value_label("0")
        layout.addWidget(self.ws_reconnects, row, 1)
        row += 1

        # Error count
        layout.addWidget(self._create_label("Errors:"), row, 0)
        self.ws_errors = self._create_value_label("0")
        layout.addWidget(self.ws_errors, row, 1)
        row += 1

        # Separator
        separator = self._create_separator()
        layout.addWidget(separator, row, 0, 1, 2)
        row += 1

        # Broker API Connection Group
        broker_label = QLabel("🏦 Broker API")
        broker_label.setObjectName("section-header")
        layout.addWidget(broker_label, row, 0, 1, 2)
        row += 1

        # Status
        layout.addWidget(self._create_label("Status:"), row, 0)
        self.broker_status_label = self._create_label("Disconnected")
        layout.addWidget(self.broker_status_label, row, 1)
        row += 1

        # Token expiry
        layout.addWidget(self._create_label("Token Expiry:"), row, 0)
        self.token_expiry_label = self._create_value_label("-")
        layout.addWidget(self.token_expiry_label, row, 1)
        row += 1

        # Last API call
        layout.addWidget(self._create_label("Last API Call:"), row, 0)
        self.last_api_call = self._create_value_label("-")
        layout.addWidget(self.last_api_call, row, 1)
        row += 1

        # Rate limit remaining
        layout.addWidget(self._create_label("Rate Limit:"), row, 0)
        self.rate_limit = self._create_value_label("-")
        layout.addWidget(self.rate_limit, row, 1)
        row += 1

        # Separator
        separator2 = self._create_separator()
        layout.addWidget(separator2, row, 0, 1, 2)
        row += 1

        # Market Data Group
        market_label = QLabel("📊 Market Data")
        market_label.setObjectName("section-header")
        layout.addWidget(market_label, row, 0, 1, 2)
        row += 1

        # Symbols subscribed
        layout.addWidget(self._create_label("Subscribed Symbols:"), row, 0)
        self.symbols_subscribed = self._create_value_label("0")
        layout.addWidget(self.symbols_subscribed, row, 1)
        row += 1

        # Active symbols
        layout.addWidget(self._create_label("Active Symbols:"), row, 0)
        self.active_symbols = self._create_value_label("0")
        layout.addWidget(self.active_symbols, row, 1)
        row += 1

        # Option chain size
        layout.addWidget(self._create_label("Option Chain:"), row, 0)
        self.option_chain_size = self._create_value_label("0")
        layout.addWidget(self.option_chain_size, row, 1)

        return widget

    def _create_statistics_tab(self) -> QGroupBox:
        """Create statistics tab"""
        widget = QGroupBox("Connection Statistics")
        layout = QGridLayout(widget)
        layout.setVerticalSpacing(self._sp.GAP_SM)
        layout.setHorizontalSpacing(self._sp.GAP_MD)

        row = 0

        # Uptime
        layout.addWidget(self._create_label("Uptime:"), row, 0)
        self.uptime_label = self._create_value_label("0s")
        layout.addWidget(self.uptime_label, row, 1)
        row += 1

        # Messages per second
        layout.addWidget(self._create_label("Msg Rate:"), row, 0)
        self.msg_rate = self._create_value_label("0/s")
        layout.addWidget(self.msg_rate, row, 1)
        row += 1

        # Peak messages
        layout.addWidget(self._create_label("Peak Rate:"), row, 0)
        self.peak_rate = self._create_value_label("0/s")
        layout.addWidget(self.peak_rate, row, 1)
        row += 1

        # Total bytes
        layout.addWidget(self._create_label("Data Received:"), row, 0)
        self.data_received = self._create_value_label("0 KB")
        layout.addWidget(self.data_received, row, 1)
        row += 1

        # Connection events
        layout.addWidget(self._create_label("Connection Events:"), row, 0)
        self.conn_events = self._create_value_label("0")
        layout.addWidget(self.conn_events, row, 1)
        row += 1

        # Last disconnect reason
        layout.addWidget(self._create_label("Last Disconnect:"), row, 0)
        self.last_disconnect = self._create_value_label("-")
        layout.addWidget(self.last_disconnect, row, 1)

        return widget

    def _create_label(self, text: str) -> QLabel:
        """Create a standard label"""
        label = QLabel(text)
        return label

    def _create_value_label(self, text: str) -> QLabel:
        """Create a value label with special styling"""
        label = QLabel(text)
        label.setObjectName("value")
        return label

    def _create_separator(self) -> QFrame:
        """Create a separator line"""
        separator = QFrame()
        separator.setObjectName("separator")
        separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(1)
        return separator

    def _init_timer(self):
        """Initialize refresh timer"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)  # Refresh every 2 seconds

    def refresh(self):
        """Refresh connection status using state_manager"""
        try:
            if not self.trading_app:
                return

            self._refresh_connection_tab()
            self._refresh_statistics_tab()

            # Update status label colors
            self._update_status_label_styles()

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.refresh] Failed: {e}")

    def _refresh_connection_tab(self):
        """Refresh connection tab data"""
        try:
            c = self._c

            # Check WebSocket connection
            if hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                ws = self.trading_app.ws

                # Update status
                if hasattr(ws, 'is_connected') and ws.is_connected():
                    self.ws_status_label.setText("Connected")
                else:
                    self.ws_status_label.setText("Disconnected")

                # Get statistics
                stats = {}
                if hasattr(ws, 'get_statistics'):
                    stats = ws.get_statistics()

                self.ws_msg_count.setText(str(stats.get('message_count', 0)))
                self.ws_reconnects.setText(str(stats.get('reconnect_count', 0)))
                self.ws_errors.setText(str(stats.get('error_count', 0)))

                # Last message time
                if hasattr(ws, '_last_message_time') and ws._last_message_time:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(ws._last_message_time)
                    self.ws_last_message.setText(dt.strftime("%H:%M:%S"))

                # Connected since
                if hasattr(ws, '_connected_since') and ws._connected_since:
                    self.ws_connected_since.setText(ws._connected_since.strftime("%H:%M:%S"))

            # Check broker connection
            if hasattr(self.trading_app, 'broker') and self.trading_app.broker:
                broker = self.trading_app.broker

                # Check if authenticated
                if hasattr(broker, 'is_connected') and broker.is_connected():
                    self.broker_status_label.setText("Connected")
                else:
                    self.broker_status_label.setText("Disconnected")

                # Token expiry
                if hasattr(broker, 'token_expiry') and broker.token_expiry:
                    self.token_expiry_label.setText(broker.token_expiry.strftime("%Y-%m-%d %H:%M"))

            # Get symbol counts from state manager
            snapshot = state_manager.get_snapshot()

            # Update symbol counts
            symbols = snapshot.get('all_symbols', [])
            if symbols is None:
                symbols = []
            self.symbols_subscribed.setText(str(len(symbols)))

            # Count active symbols (with recent data)
            option_chain = snapshot.get('option_chain', {})
            if option_chain is None:
                option_chain = {}

            active = 0
            for sym, data in option_chain.items():
                if data and isinstance(data, dict) and data.get('ltp') is not None:
                    active += 1
            self.active_symbols.setText(str(active))

            # Option chain size
            self.option_chain_size.setText(str(len(option_chain)))

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._refresh_connection_tab] Failed: {e}")

    def _refresh_statistics_tab(self):
        """Refresh statistics tab data"""
        try:
            if not hasattr(self.trading_app, 'ws') or not self.trading_app.ws:
                return

            ws = self.trading_app.ws
            stats = {}
            if hasattr(ws, 'get_statistics'):
                stats = ws.get_statistics()

            # Calculate uptime
            if hasattr(ws, '_connected_since') and ws._connected_since:
                uptime = datetime.now() - ws._connected_since
                seconds = int(uptime.total_seconds())
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                secs = seconds % 60
                self.uptime_label.setText(f"{hours}h {minutes}m {secs}s")
            else:
                self.uptime_label.setText("0s")

            # Message rate
            msg_count = stats.get('message_count', 0)
            if hasattr(ws, '_connected_since') and ws._connected_since:
                uptime_seconds = max(1, (datetime.now() - ws._connected_since).total_seconds())
                rate = msg_count / uptime_seconds
                self.msg_rate.setText(f"{rate:.1f}/s")
            else:
                self.msg_rate.setText("0/s")

            # Data received (estimate - 100 bytes per message)
            data_kb = (msg_count * 100) / 1024
            self.data_received.setText(f"{data_kb:.1f} KB")

            # Connection events
            self.conn_events.setText(str(stats.get('reconnect_count', 0)))

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._refresh_statistics_tab] Failed: {e}")

    def _reconnect(self):
        """Attempt to reconnect WebSocket"""
        try:
            if self.trading_app and hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                ws = self.trading_app.ws

                # Disconnect first
                if hasattr(ws, 'disconnect'):
                    ws.disconnect()

                # Reconnect
                if hasattr(ws, 'connect'):
                    ws.connect()

                self.reconnect_btn.setText("🔄 Reconnecting...")
                self.reconnect_btn.setEnabled(False)
                QTimer.singleShot(3000, self._reset_reconnect_btn)
        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._reconnect] Failed: {e}")

    def _test_connection(self):
        """Test broker connection"""
        try:
            from PyQt5.QtWidgets import QMessageBox

            if not self.trading_app or not hasattr(self.trading_app, 'broker'):
                QMessageBox.warning(self, "Test Failed", "Broker not available")
                return

            broker = self.trading_app.broker

            # Try to get profile
            if hasattr(broker, 'get_profile'):
                profile = broker.get_profile()
                if profile:
                    QMessageBox.information(self, "Connection Test", "✅ Connection successful!")
                else:
                    QMessageBox.warning(self, "Connection Test", "❌ Connection failed - check token")
            else:
                QMessageBox.warning(self, "Test Failed", "Broker does not support get_profile")

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._test_connection] Failed: {e}")
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Test Error", f"Error testing connection: {e}")

    def _reset_reconnect_btn(self):
        """Reset reconnect button"""
        self.reconnect_btn.setText("🔄 Reconnect WebSocket")
        self.reconnect_btn.setEnabled(True)

    def closeEvent(self, event):
        """Handle close event - Rule 7"""
        try:
            if self.timer:
                self.timer.stop()
                self.timer = None
            event.accept()
        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.closeEvent] Failed: {e}")
            event.accept()

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            if self.timer and self.timer.isActive():
                self.timer.stop()
            self.timer = None
            self.trading_app = None
            logger.info("[ConnectionMonitorPopup] Cleanup completed")
        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.cleanup] Error: {e}", exc_info=True)