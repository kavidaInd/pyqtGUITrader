"""
Connection Monitor Popup - Displays WebSocket and broker connection status
"""
import logging
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QGridLayout

logger = logging.getLogger(__name__)


class ConnectionMonitorPopup(QDialog):
    """Popup window for monitoring connection status"""

    def __init__(self, trading_app=None, parent=None):
        super().__init__(parent)
        self.trading_app = trading_app
        self.setWindowTitle("Connection Monitor")
        self.resize(500, 400)
        self.setMinimumSize(450, 350)

        # Set window flags
        self.setWindowFlags(Qt.Window)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog { background: #0d1117; color: #e6edf3; }
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
        """)

        self._init_ui()
        self._init_timer()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # WebSocket Connection Group
        ws_group = QGroupBox("WebSocket Connection")
        ws_layout = QGridLayout()

        # Status
        ws_layout.addWidget(QLabel("Status:"), 0, 0)
        self.ws_status_label = QLabel("Disconnected")
        self.ws_status_label.setObjectName("status_disconnected")
        ws_layout.addWidget(self.ws_status_label, 0, 1)

        # Connected since
        ws_layout.addWidget(QLabel("Connected Since:"), 1, 0)
        self.ws_connected_since = QLabel("-")
        self.ws_connected_since.setObjectName("value")
        ws_layout.addWidget(self.ws_connected_since, 1, 1)

        # Last message
        ws_layout.addWidget(QLabel("Last Message:"), 2, 0)
        self.ws_last_message = QLabel("-")
        self.ws_last_message.setObjectName("value")
        ws_layout.addWidget(self.ws_last_message, 2, 1)

        # Messages received
        ws_layout.addWidget(QLabel("Messages Received:"), 3, 0)
        self.ws_msg_count = QLabel("0")
        self.ws_msg_count.setObjectName("value")
        ws_layout.addWidget(self.ws_msg_count, 3, 1)

        ws_group.setLayout(ws_layout)
        layout.addWidget(ws_group)

        # Broker API Connection Group
        broker_group = QGroupBox("Broker API Connection")
        broker_layout = QGridLayout()

        # Status
        broker_layout.addWidget(QLabel("Status:"), 0, 0)
        self.broker_status_label = QLabel("Disconnected")
        self.broker_status_label.setObjectName("status_disconnected")
        broker_layout.addWidget(self.broker_status_label, 0, 1)

        # Token expiry
        broker_layout.addWidget(QLabel("Token Expiry:"), 1, 0)
        self.token_expiry_label = QLabel("-")
        self.token_expiry_label.setObjectName("value")
        broker_layout.addWidget(self.token_expiry_label, 1, 1)

        # Last API call
        broker_layout.addWidget(QLabel("Last API Call:"), 2, 0)
        self.last_api_call = QLabel("-")
        self.last_api_call.setObjectName("value")
        broker_layout.addWidget(self.last_api_call, 2, 1)

        broker_group.setLayout(broker_layout)
        layout.addWidget(broker_group)

        # Market Data Group
        market_group = QGroupBox("Market Data")
        market_layout = QGridLayout()

        # Symbols subscribed
        market_layout.addWidget(QLabel("Subscribed Symbols:"), 0, 0)
        self.symbols_subscribed = QLabel("0")
        self.symbols_subscribed.setObjectName("value")
        market_layout.addWidget(self.symbols_subscribed, 0, 1)

        # Active symbols
        market_layout.addWidget(QLabel("Active Symbols:"), 1, 0)
        self.active_symbols = QLabel("0")
        self.active_symbols.setObjectName("value")
        market_layout.addWidget(self.active_symbols, 1, 1)

        market_group.setLayout(market_layout)
        layout.addWidget(market_group)

        # Button row
        button_layout = QHBoxLayout()

        self.reconnect_btn = QPushButton("🔄 Reconnect")
        self.reconnect_btn.setObjectName("reconnect")
        self.reconnect_btn.clicked.connect(self._reconnect)

        self.refresh_btn = QPushButton("⟳ Refresh")
        self.refresh_btn.clicked.connect(self.refresh)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        button_layout.addWidget(self.reconnect_btn)
        button_layout.addWidget(self.refresh_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _init_timer(self):
        """Initialize refresh timer"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)  # Refresh every 2 seconds

    def refresh(self):
        """Refresh connection status"""
        try:
            if not self.trading_app:
                return

            # Check WebSocket connection
            if hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                ws = self.trading_app.ws

                # Update status
                if hasattr(ws, 'is_connected') and ws.is_connected():
                    self.ws_status_label.setText("Connected")
                    self.ws_status_label.setObjectName("status_connected")

                    # Update connected since if available
                    if hasattr(ws, 'connected_since') and ws.connected_since:
                        self.ws_connected_since.setText(ws.connected_since.strftime("%H:%M:%S"))
                else:
                    self.ws_status_label.setText("Disconnected")
                    self.ws_status_label.setObjectName("status_disconnected")

                # Update message count
                if hasattr(ws, 'message_count'):
                    self.ws_msg_count.setText(str(ws.message_count))

                # Update last message time
                if hasattr(ws, 'last_message_time') and ws.last_message_time:
                    self.ws_last_message.setText(ws.last_message_time.strftime("%H:%M:%S"))

            # Check broker connection
            if hasattr(self.trading_app, 'broker') and self.trading_app.broker:
                broker = self.trading_app.broker

                # Check if authenticated
                if hasattr(broker, 'is_authenticated') and broker.is_authenticated():
                    self.broker_status_label.setText("Connected")
                    self.broker_status_label.setObjectName("status_connected")
                else:
                    self.broker_status_label.setText("Disconnected")
                    self.broker_status_label.setObjectName("status_disconnected")

                # Token expiry
                if hasattr(broker, 'token_expiry') and broker.token_expiry:
                    self.token_expiry_label.setText(broker.token_expiry.strftime("%Y-%m-%d %H:%M:%S"))

            # Update symbol counts
            if hasattr(self.trading_app.state, 'all_symbols'):
                symbols = self.trading_app.state.all_symbols or []
                self.symbols_subscribed.setText(str(len(symbols)))

                # Count active symbols (with recent data)
                active = 0
                if hasattr(self.trading_app.state, 'option_chain'):
                    for sym, data in self.trading_app.state.option_chain.items():
                        if data and data.get('ltp') is not None:
                            active += 1
                self.active_symbols.setText(str(active))

            # Update styles
            self.ws_status_label.style().unpolish(self.ws_status_label)
            self.ws_status_label.style().polish(self.ws_status_label)
            self.broker_status_label.style().unpolish(self.broker_status_label)
            self.broker_status_label.style().polish(self.broker_status_label)

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.refresh] Failed: {e}")

    def _reconnect(self):
        """Attempt to reconnect WebSocket"""
        try:
            if self.trading_app and hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                if hasattr(self.trading_app.ws, 'reconnect'):
                    self.trading_app.ws.reconnect()
                    self.reconnect_btn.setText("🔄 Reconnecting...")
                    self.reconnect_btn.setEnabled(False)
                    QTimer.singleShot(3000, self._reset_reconnect_btn)
        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._reconnect] Failed: {e}")

    def _reset_reconnect_btn(self):
        """Reset reconnect button"""
        self.reconnect_btn.setText("🔄 Reconnect")
        self.reconnect_btn.setEnabled(True)

    def closeEvent(self, event):
        """Handle close event"""
        try:
            self.timer.stop()
            event.accept()
        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.closeEvent] Failed: {e}")
            event.accept()