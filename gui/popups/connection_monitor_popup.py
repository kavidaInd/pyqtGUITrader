"""
Connection Monitor Popup - Displays WebSocket and broker connection status

UPDATED: Now uses state_manager instead of direct state access.
FIXED: Removed P&L and MTF tabs as they're not required.
"""
import logging
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QGridLayout, QTabWidget

# Import state manager
from models.trade_state_manager import state_manager

logger = logging.getLogger(__name__)


class ConnectionMonitorPopup(QDialog):
    """Popup window for monitoring connection status"""

    def __init__(self, trading_app=None, parent=None):
        super().__init__(parent)
        self.trading_app = trading_app
        self.setWindowTitle("Connection Monitor")
        self.resize(700, 500)
        self.setMinimumSize(650, 450)

        # Set window flags
        self.setWindowFlags(Qt.Window)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog { background: #0d1117; color: #e6edf3; }
            QTabWidget::pane {
                border: 1px solid #30363d;
                background: #0d1117;
            }
            QTabBar::tab {
                background: #161b22;
                color: #8b949e;
                padding: 8px 16px;
                border: 1px solid #30363d;
            }
            QTabBar::tab:selected {
                background: #21262d;
                color: #e6edf3;
                border-bottom: 2px solid #58a6ff;
            }
            QGroupBox {
                border: 1px solid #30363d;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
                color: #e6edf3;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QLabel { color: #e6edf3; }
            QLabel#status_connected { color: #3fb950; }
            QLabel#status_disconnected { color: #f85149; }
            QLabel#value { color: #58a6ff; font-weight: bold; }
            QLabel#warning { color: #d29922; }
            QLabel#success { color: #3fb950; }
            QLabel#error { color: #f85149; }
            QPushButton {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover { background: #30363d; }
            QPushButton#reconnect { background: #238636; }
            QPushButton#reconnect:hover { background: #2ea043; }
            QPushButton#test { background: #1f6feb; }
            QPushButton#test:hover { background: #388bfd; }
        """)

        self._init_ui()
        self._init_timer()

    def _init_ui(self):
        layout = QVBoxLayout(self)

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

        self.reconnect_btn = QPushButton("🔄 Reconnect WebSocket")
        self.reconnect_btn.setObjectName("reconnect")
        self.reconnect_btn.clicked.connect(self._reconnect)

        self.test_btn = QPushButton("🧪 Test Connection")
        self.test_btn.setObjectName("test")
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

        row = 0

        # WebSocket Connection Group
        ws_label = QLabel("🌐 WebSocket")
        ws_label.setStyleSheet("font-weight: bold; color: #58a6ff;")
        layout.addWidget(ws_label, row, 0, 1, 2)
        row += 1

        # Status
        layout.addWidget(QLabel("Status:"), row, 0)
        self.ws_status_label = QLabel("Disconnected")
        self.ws_status_label.setObjectName("status_disconnected")
        layout.addWidget(self.ws_status_label, row, 1)
        row += 1

        # Connected since
        layout.addWidget(QLabel("Connected Since:"), row, 0)
        self.ws_connected_since = QLabel("-")
        self.ws_connected_since.setObjectName("value")
        layout.addWidget(self.ws_connected_since, row, 1)
        row += 1

        # Last message
        layout.addWidget(QLabel("Last Message:"), row, 0)
        self.ws_last_message = QLabel("-")
        self.ws_last_message.setObjectName("value")
        layout.addWidget(self.ws_last_message, row, 1)
        row += 1

        # Messages received
        layout.addWidget(QLabel("Messages Received:"), row, 0)
        self.ws_msg_count = QLabel("0")
        self.ws_msg_count.setObjectName("value")
        layout.addWidget(self.ws_msg_count, row, 1)
        row += 1

        # Reconnect count
        layout.addWidget(QLabel("Reconnects:"), row, 0)
        self.ws_reconnects = QLabel("0")
        self.ws_reconnects.setObjectName("value")
        layout.addWidget(self.ws_reconnects, row, 1)
        row += 1

        # Error count
        layout.addWidget(QLabel("Errors:"), row, 0)
        self.ws_errors = QLabel("0")
        self.ws_errors.setObjectName("value")
        layout.addWidget(self.ws_errors, row, 1)
        row += 1

        # Separator
        separator = QLabel("")
        separator.setStyleSheet("border-bottom: 1px solid #30363d;")
        layout.addWidget(separator, row, 0, 1, 2)
        row += 1

        # Broker API Connection Group
        broker_label = QLabel("🏦 Broker API")
        broker_label.setStyleSheet("font-weight: bold; color: #58a6ff;")
        layout.addWidget(broker_label, row, 0, 1, 2)
        row += 1

        # Status
        layout.addWidget(QLabel("Status:"), row, 0)
        self.broker_status_label = QLabel("Disconnected")
        self.broker_status_label.setObjectName("status_disconnected")
        layout.addWidget(self.broker_status_label, row, 1)
        row += 1

        # Token expiry
        layout.addWidget(QLabel("Token Expiry:"), row, 0)
        self.token_expiry_label = QLabel("-")
        self.token_expiry_label.setObjectName("value")
        layout.addWidget(self.token_expiry_label, row, 1)
        row += 1

        # Last API call
        layout.addWidget(QLabel("Last API Call:"), row, 0)
        self.last_api_call = QLabel("-")
        self.last_api_call.setObjectName("value")
        layout.addWidget(self.last_api_call, row, 1)
        row += 1

        # Rate limit remaining
        layout.addWidget(QLabel("Rate Limit:"), row, 0)
        self.rate_limit = QLabel("-")
        self.rate_limit.setObjectName("value")
        layout.addWidget(self.rate_limit, row, 1)
        row += 1

        # Separator
        separator2 = QLabel("")
        separator2.setStyleSheet("border-bottom: 1px solid #30363d;")
        layout.addWidget(separator2, row, 0, 1, 2)
        row += 1

        # Market Data Group
        market_label = QLabel("📊 Market Data")
        market_label.setStyleSheet("font-weight: bold; color: #58a6ff;")
        layout.addWidget(market_label, row, 0, 1, 2)
        row += 1

        # Symbols subscribed
        layout.addWidget(QLabel("Subscribed Symbols:"), row, 0)
        self.symbols_subscribed = QLabel("0")
        self.symbols_subscribed.setObjectName("value")
        layout.addWidget(self.symbols_subscribed, row, 1)
        row += 1

        # Active symbols
        layout.addWidget(QLabel("Active Symbols:"), row, 0)
        self.active_symbols = QLabel("0")
        self.active_symbols.setObjectName("value")
        layout.addWidget(self.active_symbols, row, 1)
        row += 1

        # Option chain size
        layout.addWidget(QLabel("Option Chain:"), row, 0)
        self.option_chain_size = QLabel("0")
        self.option_chain_size.setObjectName("value")
        layout.addWidget(self.option_chain_size, row, 1)

        return widget

    def _create_statistics_tab(self) -> QGroupBox:
        """Create statistics tab"""
        widget = QGroupBox("Connection Statistics")
        layout = QGridLayout(widget)

        row = 0

        # Uptime
        layout.addWidget(QLabel("Uptime:"), row, 0)
        self.uptime_label = QLabel("0s")
        self.uptime_label.setObjectName("value")
        layout.addWidget(self.uptime_label, row, 1)
        row += 1

        # Messages per second
        layout.addWidget(QLabel("Msg Rate:"), row, 0)
        self.msg_rate = QLabel("0/s")
        self.msg_rate.setObjectName("value")
        layout.addWidget(self.msg_rate, row, 1)
        row += 1

        # Peak messages
        layout.addWidget(QLabel("Peak Rate:"), row, 0)
        self.peak_rate = QLabel("0/s")
        self.peak_rate.setObjectName("value")
        layout.addWidget(self.peak_rate, row, 1)
        row += 1

        # Total bytes
        layout.addWidget(QLabel("Data Received:"), row, 0)
        self.data_received = QLabel("0 KB")
        self.data_received.setObjectName("value")
        layout.addWidget(self.data_received, row, 1)
        row += 1

        # Connection events
        layout.addWidget(QLabel("Connection Events:"), row, 0)
        self.conn_events = QLabel("0")
        self.conn_events.setObjectName("value")
        layout.addWidget(self.conn_events, row, 1)
        row += 1

        # Last disconnect reason
        layout.addWidget(QLabel("Last Disconnect:"), row, 0)
        self.last_disconnect = QLabel("-")
        self.last_disconnect.setObjectName("value")
        layout.addWidget(self.last_disconnect, row, 1)

        return widget

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

            # Update styles
            self.ws_status_label.style().unpolish(self.ws_status_label)
            self.ws_status_label.style().polish(self.ws_status_label)
            self.broker_status_label.style().unpolish(self.broker_status_label)
            self.broker_status_label.style().polish(self.broker_status_label)

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.refresh] Failed: {e}")

    def _refresh_connection_tab(self):
        """Refresh connection tab data"""
        try:
            # Check WebSocket connection
            if hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                ws = self.trading_app.ws

                # Update status
                if hasattr(ws, 'is_connected') and ws.is_connected():
                    self.ws_status_label.setText("Connected")
                    self.ws_status_label.setObjectName("status_connected")
                else:
                    self.ws_status_label.setText("Disconnected")
                    self.ws_status_label.setObjectName("status_disconnected")

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
                    self.broker_status_label.setObjectName("status_connected")
                else:
                    self.broker_status_label.setText("Disconnected")
                    self.broker_status_label.setObjectName("status_disconnected")

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
        """Handle close event"""
        try:
            self.timer.stop()
            event.accept()
        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.closeEvent] Failed: {e}")
            event.accept()