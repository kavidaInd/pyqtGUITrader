# gui/onboarding_popup.py
"""
First-time setup wizard that guides users through initial configuration.
Now with a theme matching the main application and setting pages.
"""

import logging
import json
import os
from typing import Optional, Dict, Any, List
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QPixmap, QPalette, QColor, QLinearGradient, QBrush
from PyQt5.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QGroupBox, QRadioButton, QFormLayout, QFrame, QScrollArea,
    QPushButton, QMessageBox, QButtonGroup, QTextEdit, QWidget
)

# Import your existing setting classes
from gui.brokerage_settings.BrokerageSetting import BrokerageSetting
from gui.daily_trade.DailyTradeSetting import DailyTradeSetting
from gui.profit_loss.ProfitStoplossSetting import ProfitStoplossSetting
from gui.trading_mode.TradingModeSetting import TradingModeSetting, TradingMode

# Import broker types from BrokerFactory
from broker.BrokerFactory import BrokerType

# Import database for installation flag
from db.connector import get_db
from db.crud import kv

logger = logging.getLogger(__name__)

# Flag key in app_kv table to track if onboarding has been completed
ONBOARDING_COMPLETED_KEY = "onboarding_completed"

# Broker order list (from BrokerageSettingGUI)
BROKER_ORDER = [
    BrokerType.FYERS,
    BrokerType.ZERODHA,
    BrokerType.DHAN,
    BrokerType.ANGELONE,
    BrokerType.UPSTOX,
    BrokerType.SHOONYA,
    BrokerType.KOTAK,
    BrokerType.ICICI,
    BrokerType.ALICEBLUE,
    BrokerType.FLATTRADE,
]

# Per-broker field hints (from BrokerageSettingGUI)
BROKER_HINTS = {
    BrokerType.FYERS: {
        "client_id": ("Client ID / App ID", "e.g. XY12345-100"),
        "secret_key": ("App Secret", "From myapi.fyers.in"),
        "redirect_uri": ("Redirect URI", "e.g. https://127.0.0.1/callback"),
        "redirect_note": "Redirect URI must match exactly what's registered on myapi.fyers.in",
        "auth_note": "OAuth browser login required daily. Click 'Open Login URL' after saving.",
        "redirect_disabled": False,
    },
    BrokerType.ZERODHA: {
        "client_id": ("API Key", "From developers.kite.trade"),
        "secret_key": ("API Secret", "From developers.kite.trade"),
        "redirect_uri": ("Redirect URL", "e.g. https://127.0.0.1/callback"),
        "redirect_note": "Must match redirect URL registered in Kite developer console",
        "auth_note": "OAuth browser login required daily. Token expires end-of-day.",
        "redirect_disabled": False,
    },
    BrokerType.DHAN: {
        "client_id": ("Client ID", "Your Dhan client ID"),
        "secret_key": ("Access Token", "Static token from dhanhq.co portal"),
        "redirect_uri": ("Not required", "Leave blank for Dhan"),
        "redirect_note": "Dhan uses a static access token — no OAuth redirect needed.",
        "auth_note": "Static token. No daily login required — just update when token expires.",
        "redirect_disabled": True,
    },
    BrokerType.ANGELONE: {
        "client_id": ("Client Code", "Your Angel One login ID (e.g. A123456)"),
        "secret_key": ("API Key", "From SmartAPI developer portal"),
        "redirect_uri": ("TOTP Secret", "Base32 TOTP secret from QR code scan"),
        "redirect_note": "TOTP secret from https://smartapi.angelbroking.com — scan QR with authenticator",
        "auth_note": "TOTP-based. No browser needed. Call broker.login(password='MPIN') at startup.",
        "redirect_disabled": False,
    },
    BrokerType.UPSTOX: {
        "client_id": ("API Key", "From Upstox developer console"),
        "secret_key": ("API Secret", "From Upstox developer console"),
        "redirect_uri": ("Redirect URI", "e.g. https://127.0.0.1/callback"),
        "redirect_note": "Must match redirect URI registered in Upstox developer console",
        "auth_note": "OAuth browser login required daily. Token expires end-of-day.",
        "redirect_disabled": False,
    },
    BrokerType.SHOONYA: {
        "client_id": ("User ID | Vendor Code", "e.g. FA12345|FA12345_U (pipe-separated)"),
        "secret_key": ("Password", "Your Shoonya login password (plain text)"),
        "redirect_uri": ("TOTP Secret", "Base32 TOTP secret for auto-TOTP generation"),
        "redirect_note": "Store TOTP base32 secret here. Obtain from Shoonya app → TOTP setup.",
        "auth_note": "TOTP-based login. Call broker.login() each morning before market open.",
        "redirect_disabled": False,
    },
    BrokerType.KOTAK: {
        "client_id": ("Consumer Key", "From Kotak Neo app → Trade API card"),
        "secret_key": ("Consumer Secret", "From Kotak Neo app → Trade API card"),
        "redirect_uri": ("TOTP Secret", "Base32 TOTP secret for auto-TOTP"),
        "redirect_note": "TOTP secret from Kotak Securities TOTP registration page.",
        "auth_note": "TOTP + MPIN login. Call broker.login_totp(mobile, ucc, mpin) at startup.",
        "redirect_disabled": False,
    },
    BrokerType.ICICI: {
        "client_id": ("API Key", "From https://api.icicidirect.com"),
        "secret_key": ("Secret Key", "From https://api.icicidirect.com"),
        "redirect_uri": ("Not required", "Leave blank for ICICI Breeze"),
        "redirect_note": "Visit get_login_url() each day to obtain a session token. Static IP required (SEBI mandate).",
        "auth_note": "Session-token auth. Visit login URL daily, paste token into broker.generate_session().",
        "redirect_disabled": True,
    },
    BrokerType.ALICEBLUE: {
        "client_id": ("App ID", "From Alice Blue developer console"),
        "secret_key": ("API Secret", "From Alice Blue developer console"),
        "redirect_uri": ("username|password|YOB", "e.g. AB12345|mypassword|1990"),
        "redirect_note": "Store as pipe-separated: username|password|YearOfBirth. YOB used as 2FA answer.",
        "auth_note": "Fully automated login. Call broker.login() at startup each day.",
        "redirect_disabled": False,
    },
    BrokerType.FLATTRADE: {
        "client_id": ("User ID | API Key", "e.g. FL12345|myapikey (pipe-separated)"),
        "secret_key": ("API Secret", "From Flattrade Pi → Create New API Key"),
        "redirect_uri": ("Redirect URI", "e.g. https://127.0.0.1/callback"),
        "redirect_note": "Must match redirect URI registered in Flattrade Pi API settings.",
        "auth_note": "OAuth token from browser. Call broker.set_session(token=...) after redirect. Zero brokerage!",
        "redirect_disabled": False,
    },
}


class WelcomePage(QWizardPage):
    """Welcome page with introduction."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Welcome to Algo Trading Pro")
        self.setSubTitle("Let's get you started with your first-time setup")

        layout = QVBoxLayout()
        layout.setSpacing(20)

        # Logo or icon with gradient background
        icon_container = QFrame()
        icon_container.setFixedSize(120, 120)
        icon_container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #238636, stop: 1 #2ea043);
                border-radius: 60px;
                margin: 10px auto;
            }
        """)
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel("📈")
        icon_label.setStyleSheet("font-size: 60px; color: white; background: transparent;")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_layout.addWidget(icon_label)

        # Center the icon
        icon_wrapper = QHBoxLayout()
        icon_wrapper.addStretch()
        icon_wrapper.addWidget(icon_container)
        icon_wrapper.addStretch()
        layout.addLayout(icon_wrapper)

        # Welcome text with styled card
        welcome_card = QFrame()
        welcome_card.setObjectName("infoCard")
        welcome_card.setStyleSheet("""
            QFrame#infoCard {
                background: #21262d;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 20px;
            }
        """)
        welcome_layout = QVBoxLayout(welcome_card)

        welcome_title = QLabel("<h2>Welcome to Algo Trading Pro!</h2>")
        welcome_title.setStyleSheet("color: #e6edf3; font-size: 18pt; font-weight: bold;")
        welcome_title.setAlignment(Qt.AlignCenter)
        welcome_layout.addWidget(welcome_title)

        welcome_text = QLabel(
            "Thank you for choosing Algo Trading Pro. This quick setup wizard will help you configure "
            "the basic settings to get started with automated trading.\n\n"
            "In the next few steps, you'll configure:\n"
            "• Your broker connection\n"
            "• Trading preferences\n"
            "• Risk management settings\n"
            "• Notification preferences\n\n"
            "The entire process takes about 2-3 minutes."
        )
        welcome_text.setWordWrap(True)
        welcome_text.setStyleSheet("color: #8b949e; font-size: 11pt; line-height: 1.5;")
        welcome_layout.addWidget(welcome_text)

        layout.addWidget(welcome_card)

        # Quick start option with styled frame
        quick_frame = QFrame()
        quick_frame.setStyleSheet("""
            QFrame {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 15px;
            }
        """)
        quick_layout = QHBoxLayout(quick_frame)

        self.quick_check = QCheckBox("✨ Use quick setup with recommended defaults")
        self.quick_check.setChecked(True)
        self.quick_check.setStyleSheet("""
            QCheckBox {
                color: #e6edf3;
                font-size: 10pt;
                font-weight: bold;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #30363d;
                background: #21262d;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background: #238636;
                border: 2px solid #2ea043;
                border-radius: 3px;
            }
        """)
        quick_layout.addWidget(self.quick_check)

        quick_layout.addStretch()
        quick_desc = QLabel("(Recommended for first-time users)")
        quick_desc.setStyleSheet("color: #8b949e; font-size: 9pt; font-style: italic;")
        quick_layout.addWidget(quick_desc)

        layout.addWidget(quick_frame)
        layout.addStretch()

        self.setLayout(layout)

    def isQuickSetup(self):
        """Return whether quick setup is selected."""
        return self.quick_check.isChecked()


class BrokerConfigPage(QWizardPage):
    """Broker configuration page - integrates with BrokerageSetting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Broker Configuration")
        self.setSubTitle("Connect to your brokerage account")

        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Broker selection group with styled header
        broker_group = QGroupBox("🏦 Select Your Broker")
        broker_group.setStyleSheet("""
            QGroupBox {
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                font-size: 11pt;
                background: #161b22;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #58a6ff;
            }
        """)
        broker_layout = QVBoxLayout(broker_group)
        broker_layout.setSpacing(10)

        self.broker_combo = QComboBox()

        # Add all brokers from BROKER_ORDER list
        for bt in BROKER_ORDER:
            display_name = BrokerType.DISPLAY_NAMES.get(bt, bt)
            self.broker_combo.addItem(f"{display_name}  ({bt})", bt)

        self.broker_combo.setStyleSheet("""
            QComboBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 8px;
                font-size: 10pt;
                min-height: 20px;
            }
            QComboBox:hover {
                border: 1px solid #58a6ff;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #8b949e;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                selection-background-color: #30363d;
            }
        """)
        broker_layout.addWidget(self.broker_combo)

        # Broker description with styled info box
        self.broker_desc = QLabel("Select your broker to see specific credential requirements")
        self.broker_desc.setWordWrap(True)
        self.broker_desc.setStyleSheet("""
            QLabel {
                color: #8b949e;
                font-size: 9pt;
                padding: 8px;
                background: #1a1f26;
                border-radius: 4px;
                border-left: 3px solid #58a6ff;
            }
        """)
        broker_layout.addWidget(self.broker_desc)

        layout.addWidget(broker_group)

        # Credentials group
        cred_group = QGroupBox("🔑 API Credentials")
        cred_group.setStyleSheet("""
            QGroupBox {
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                font-size: 11pt;
                background: #161b22;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #58a6ff;
            }
        """)
        cred_layout = QFormLayout(cred_group)
        cred_layout.setVerticalSpacing(12)
        cred_layout.setHorizontalSpacing(15)
        cred_layout.setLabelAlignment(Qt.AlignRight)

        # Client ID / API Key
        self.client_id_label = QLabel("Client ID:")
        self.client_id_label.setStyleSheet("color: #e6edf3; font-size: 10pt;")
        self.client_id = QLineEdit()
        self.client_id.setPlaceholderText("Enter your client ID / API key")
        self.client_id.setStyleSheet("""
            QLineEdit {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 8px;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 2px solid #58a6ff;
            }
            QLineEdit:hover {
                border: 1px solid #58a6ff;
            }
        """)
        cred_layout.addRow(self.client_id_label, self.client_id)

        # Secret Key
        self.secret_key_label = QLabel("Secret Key:")
        self.secret_key_label.setStyleSheet("color: #e6edf3; font-size: 10pt;")
        self.secret_key = QLineEdit()
        self.secret_key.setEchoMode(QLineEdit.Password)
        self.secret_key.setPlaceholderText("Enter your secret key / API secret")
        self.secret_key.setStyleSheet("""
            QLineEdit {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 8px;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 2px solid #58a6ff;
            }
            QLineEdit:hover {
                border: 1px solid #58a6ff;
            }
        """)
        cred_layout.addRow(self.secret_key_label, self.secret_key)

        # Redirect URI / TOTP Secret
        self.redirect_label = QLabel("Redirect URI:")
        self.redirect_label.setStyleSheet("color: #e6edf3; font-size: 10pt;")
        self.redirect_uri = QLineEdit()
        self.redirect_uri.setPlaceholderText("Enter redirect URI or TOTP secret")
        self.redirect_uri.setStyleSheet("""
            QLineEdit {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 8px;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 2px solid #58a6ff;
            }
            QLineEdit:hover {
                border: 1px solid #58a6ff;
            }
            QLineEdit:disabled {
                background: #1a1f26;
                color: #6e7681;
            }
        """)
        cred_layout.addRow(self.redirect_label, self.redirect_uri)

        # Field hint
        self.field_hint = QLabel("")
        self.field_hint.setWordWrap(True)
        self.field_hint.setStyleSheet("color: #58a6ff; font-size: 8pt; padding-left: 10px;")
        cred_layout.addRow("", self.field_hint)

        layout.addWidget(cred_group)

        # Save credentials checkbox with styled container
        save_frame = QFrame()
        save_frame.setStyleSheet("""
            QFrame {
                background: #1a1f26;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        save_layout = QHBoxLayout(save_frame)
        save_layout.setContentsMargins(10, 5, 10, 5)

        self.save_creds = QCheckBox("🔒 Save credentials (encrypted)")
        self.save_creds.setChecked(True)
        self.save_creds.setStyleSheet("""
            QCheckBox {
                color: #e6edf3;
                font-size: 10pt;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #30363d;
                background: #21262d;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background: #238636;
                border: 2px solid #2ea043;
                border-radius: 3px;
            }
        """)
        save_layout.addWidget(self.save_creds)

        save_layout.addStretch()
        save_note = QLabel("Credentials are stored securely in the local database")
        save_note.setStyleSheet("color: #8b949e; font-size: 8pt; font-style: italic;")
        save_layout.addWidget(save_note)

        layout.addWidget(save_frame)

        layout.addStretch()
        self.setLayout(layout)

        # Connect broker change to update hints
        self.broker_combo.currentIndexChanged.connect(self._update_broker_hints)

        # Register fields
        self.registerField("broker", self.broker_combo)
        self.registerField("client_id", self.client_id)
        self.registerField("secret_key", self.secret_key)
        self.registerField("redirect_uri", self.redirect_uri)
        self.registerField("save_creds", self.save_creds)

        # Initial update
        QTimer.singleShot(100, self._update_broker_hints)

    def _update_broker_hints(self):
        """Update field labels and hints based on selected broker."""
        broker_value = self.broker_combo.currentData()

        # Get hints for this broker
        hints = BROKER_HINTS.get(broker_value, BROKER_HINTS[BrokerType.FYERS])

        self.client_id_label.setText(hints['client_id'][0] + ":")
        self.client_id.setPlaceholderText(hints['client_id'][1])

        self.secret_key_label.setText(hints['secret_key'][0] + ":")
        self.secret_key.setPlaceholderText(hints['secret_key'][1])

        self.redirect_label.setText(hints['redirect_uri'][0] + ":")
        self.redirect_uri.setPlaceholderText(hints['redirect_uri'][1])

        # Enable/disable redirect field
        if hints.get('redirect_disabled', False):
            self.redirect_uri.setEnabled(False)
            self.redirect_uri.clear()
        else:
            self.redirect_uri.setEnabled(True)

        self.field_hint.setText(f"ℹ️ {hints.get('redirect_note', '')}")
        self.broker_desc.setText(f"ℹ️ {hints.get('auth_note', '')}")


class TradingPreferencesPage(QWizardPage):
    """Trading preferences page - integrates with DailyTradeSetting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Trading Preferences")
        self.setSubTitle("Configure your default trading settings")

        # Get default values from DailyTradeSetting
        self.defaults = DailyTradeSetting.DEFAULTS

        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Trading mode group
        mode_group = QGroupBox("🎮 Trading Mode")
        mode_group.setStyleSheet("""
            QGroupBox {
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                font-size: 11pt;
                background: #161b22;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #58a6ff;
            }
        """)
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setSpacing(10)

        self.mode_paper = QRadioButton("📊 Paper Trading (simulated)")
        self.mode_live = QRadioButton("💰 Live Trading (real money)")
        self.mode_paper.setChecked(True)

        for rb in [self.mode_paper, self.mode_live]:
            rb.setStyleSheet("""
                QRadioButton {
                    color: #e6edf3;
                    font-size: 10pt;
                    spacing: 8px;
                }
                QRadioButton::indicator {
                    width: 16px;
                    height: 16px;
                }
                QRadioButton::indicator:unchecked {
                    border: 2px solid #30363d;
                    background: #21262d;
                    border-radius: 8px;
                }
                QRadioButton::indicator:checked {
                    background: #238636;
                    border: 2px solid #2ea043;
                    border-radius: 8px;
                }
            """)
            mode_layout.addWidget(rb)

        # Live trading warning
        self.live_warning = QLabel("⚠️ Warning: Live trading uses real money")
        self.live_warning.setStyleSheet("""
            QLabel {
                color: #f85149;
                font-size: 9pt;
                font-weight: bold;
                padding: 8px;
                background: #2d1a1a;
                border-radius: 4px;
                border-left: 3px solid #f85149;
            }
        """)
        self.live_warning.setVisible(False)
        mode_layout.addWidget(self.live_warning)

        self.mode_live.toggled.connect(lambda checked: self.live_warning.setVisible(checked))

        layout.addWidget(mode_group)

        # Instrument preferences
        instr_group = QGroupBox("📈 Instrument Preferences")
        instr_group.setStyleSheet("""
            QGroupBox {
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                font-size: 11pt;
                background: #161b22;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #58a6ff;
            }
        """)
        instr_layout = QFormLayout(instr_group)
        instr_layout.setVerticalSpacing(10)
        instr_layout.setLabelAlignment(Qt.AlignRight)

        # Derivative
        self.derivative_combo = QComboBox()
        derivatives = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCAPNIFTY", "SENSEX"]
        for d in derivatives:
            self.derivative_combo.addItem(d)
        self.derivative_combo.setCurrentText(self.defaults.get("derivative", "NIFTY"))
        self.derivative_combo.setStyleSheet("""
            QComboBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        instr_layout.addRow("Derivative:", self.derivative_combo)

        # Lot Size
        self.lot_size = QSpinBox()
        self.lot_size.setRange(1, 10000)
        self.lot_size.setValue(self.defaults.get("lot_size", 50))
        self.lot_size.setSuffix(" units")
        self.lot_size.setStyleSheet("""
            QSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        instr_layout.addRow("Lot Size:", self.lot_size)

        # Exchange
        self.exchange = QLineEdit()
        self.exchange.setText(self.defaults.get("exchange", "NSE"))
        self.exchange.setPlaceholderText("e.g. NSE, BSE")
        self.exchange.setStyleSheet("""
            QLineEdit {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        instr_layout.addRow("Exchange:", self.exchange)

        # Week (expiry)
        self.week = QSpinBox()
        self.week.setRange(0, 53)
        self.week.setValue(self.defaults.get("week", 0))
        self.week.setSuffix(" (0 = current)")
        self.week.setStyleSheet("""
            QSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        instr_layout.addRow("Expiry Week:", self.week)

        layout.addWidget(instr_group)

        # History settings
        hist_group = QGroupBox("📊 Historical Data")
        hist_group.setStyleSheet("""
            QGroupBox {
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                font-size: 11pt;
                background: #161b22;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #58a6ff;
            }
        """)
        hist_layout = QFormLayout(hist_group)
        hist_layout.setVerticalSpacing(10)

        # History interval
        self.interval_combo = QComboBox()
        intervals = ["1m", "2m", "3m", "5m", "10m", "15m", "30m", "60m"]
        for i in intervals:
            self.interval_combo.addItem(i)
        self.interval_combo.setCurrentText(self.defaults.get("history_interval", "2m"))
        self.interval_combo.setStyleSheet("""
            QComboBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        hist_layout.addRow("Candle Interval:", self.interval_combo)

        # Lookback periods
        self.call_lookback = QSpinBox()
        self.call_lookback.setRange(0, 100)
        self.call_lookback.setValue(self.defaults.get("call_lookback", 5))
        self.call_lookback.setStyleSheet("""
            QSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        hist_layout.addRow("Call Lookback:", self.call_lookback)

        self.put_lookback = QSpinBox()
        self.put_lookback.setRange(0, 100)
        self.put_lookback.setValue(self.defaults.get("put_lookback", 5))
        self.put_lookback.setStyleSheet("""
            QSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        hist_layout.addRow("Put Lookback:", self.put_lookback)

        layout.addWidget(hist_group)

        # Sideways trading
        sideway_frame = QFrame()
        sideway_frame.setStyleSheet("""
            QFrame {
                background: #1a1f26;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        sideway_layout = QHBoxLayout(sideway_frame)

        self.sideway_check = QCheckBox("Enable trading during sideways market (12:00–14:00)")
        self.sideway_check.setChecked(self.defaults.get("sideway_zone_trade", False))
        self.sideway_check.setStyleSheet("""
            QCheckBox {
                color: #e6edf3;
                font-size: 10pt;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        sideway_layout.addWidget(self.sideway_check)

        sideway_layout.addStretch()
        sideway_info = QLabel("ℹ️ Allows trading during low-volatility period")
        sideway_info.setStyleSheet("color: #8b949e; font-size: 9pt;")
        sideway_layout.addWidget(sideway_info)

        layout.addWidget(sideway_frame)

        layout.addStretch()
        self.setLayout(layout)

        # Register fields
        self.registerField("trading_mode", self.mode_live, "checked")
        self.registerField("derivative", self.derivative_combo, "currentText")
        self.registerField("lot_size", self.lot_size)
        self.registerField("exchange", self.exchange)
        self.registerField("week", self.week)
        self.registerField("history_interval", self.interval_combo, "currentText")
        self.registerField("call_lookback", self.call_lookback)
        self.registerField("put_lookback", self.put_lookback)
        self.registerField("sideway_zone_trade", self.sideway_check)


class RiskManagementPage(QWizardPage):
    """Risk management page - integrates with ProfitStoplossSetting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Risk Management")
        self.setSubTitle("Configure your risk parameters")

        # Get default values from ProfitStoplossSetting
        self.defaults = ProfitStoplossSetting.DEFAULTS

        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Capital allocation
        capital_group = QGroupBox("💰 Capital Allocation")
        capital_group.setStyleSheet("""
            QGroupBox {
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                font-size: 11pt;
                background: #161b22;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #58a6ff;
            }
        """)
        capital_layout = QFormLayout(capital_group)
        capital_layout.setVerticalSpacing(10)
        capital_layout.setLabelAlignment(Qt.AlignRight)

        # Capital reserve
        self.capital_reserve = QSpinBox()
        self.capital_reserve.setRange(0, 10000000)
        self.capital_reserve.setSingleStep(10000)
        self.capital_reserve.setPrefix("₹ ")
        self.capital_reserve.setValue(self.defaults.get("capital_reserve", 500000))
        self.capital_reserve.setStyleSheet("""
            QSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        capital_layout.addRow("Capital Reserve:", self.capital_reserve)

        # Max options per trade
        self.max_options = QSpinBox()
        self.max_options.setRange(1, 100)
        self.max_options.setValue(self.defaults.get("max_num_of_option", 10))
        self.max_options.setSuffix(" contracts")
        self.max_options.setStyleSheet("""
            QSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        capital_layout.addRow("Max Options/Trade:", self.max_options)

        layout.addWidget(capital_group)

        # Stop Loss and Take Profit
        sltp_group = QGroupBox("🛑 Stop Loss & Take Profit")
        sltp_group.setStyleSheet("""
            QGroupBox {
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                font-size: 11pt;
                background: #161b22;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #58a6ff;
            }
        """)
        sltp_layout = QFormLayout(sltp_group)
        sltp_layout.setVerticalSpacing(10)
        sltp_layout.setLabelAlignment(Qt.AlignRight)

        # Profit type
        self.profit_type = QComboBox()
        self.profit_type.addItems(["STOP", "TRAILING", "FIXED"])
        self.profit_type.setCurrentText(self.defaults.get("profit_type", "STOP"))
        self.profit_type.setStyleSheet("""
            QComboBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        sltp_layout.addRow("Profit Type:", self.profit_type)

        # Take Profit
        self.tp_percentage = QDoubleSpinBox()
        self.tp_percentage.setRange(0.1, 100.0)
        self.tp_percentage.setValue(self.defaults.get("tp_percentage", 15.0))
        self.tp_percentage.setSuffix(" %")
        self.tp_percentage.setStyleSheet("""
            QDoubleSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        sltp_layout.addRow("Take Profit:", self.tp_percentage)

        # Stop Loss
        self.sl_percentage = QDoubleSpinBox()
        self.sl_percentage.setRange(0.1, 50.0)
        self.sl_percentage.setValue(self.defaults.get("stoploss_percentage", 7.0))
        self.sl_percentage.setSuffix(" %")
        self.sl_percentage.setStyleSheet("""
            QDoubleSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        sltp_layout.addRow("Stop Loss:", self.sl_percentage)

        # Stop loss note
        sl_note = QLabel("⚠️ Stop loss is applied BELOW entry price for long positions")
        sl_note.setStyleSheet("""
            QLabel {
                color: #d29922;
                font-size: 9pt;
                padding: 5px;
                background: #2d2416;
                border-radius: 4px;
            }
        """)
        sltp_layout.addRow("", sl_note)

        layout.addWidget(sltp_group)

        # Trailing settings (initially hidden)
        self.trailing_group = QGroupBox("📈 Trailing Settings")
        self.trailing_group.setStyleSheet("""
            QGroupBox {
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                font-size: 11pt;
                background: #161b22;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #58a6ff;
            }
        """)
        trailing_layout = QFormLayout(self.trailing_group)
        trailing_layout.setVerticalSpacing(10)

        self.trailing_first = QDoubleSpinBox()
        self.trailing_first.setRange(0.1, 50.0)
        self.trailing_first.setValue(self.defaults.get("trailing_first_profit", 3.0))
        self.trailing_first.setSuffix(" %")
        self.trailing_first.setStyleSheet("""
            QDoubleSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        trailing_layout.addRow("First Profit:", self.trailing_first)

        self.max_profit = QDoubleSpinBox()
        self.max_profit.setRange(0.1, 200.0)
        self.max_profit.setValue(self.defaults.get("max_profit", 30.0))
        self.max_profit.setSuffix(" %")
        self.max_profit.setStyleSheet("""
            QDoubleSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        trailing_layout.addRow("Max Profit:", self.max_profit)

        self.profit_step = QDoubleSpinBox()
        self.profit_step.setRange(0.1, 20.0)
        self.profit_step.setValue(self.defaults.get("profit_step", 2.0))
        self.profit_step.setSuffix(" %")
        self.profit_step.setStyleSheet("""
            QDoubleSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        trailing_layout.addRow("Profit Step:", self.profit_step)

        self.loss_step = QDoubleSpinBox()
        self.loss_step.setRange(0.1, 20.0)
        self.loss_step.setValue(self.defaults.get("loss_step", 2.0))
        self.loss_step.setSuffix(" %")
        self.loss_step.setStyleSheet("""
            QDoubleSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        trailing_layout.addRow("Loss Step:", self.loss_step)

        layout.addWidget(self.trailing_group)

        # Connect profit type change
        self.profit_type.currentTextChanged.connect(self._on_profit_type_changed)

        layout.addStretch()
        self.setLayout(layout)

        # Register fields
        self.registerField("capital_reserve", self.capital_reserve)
        self.registerField("max_options", self.max_options)
        self.registerField("profit_type", self.profit_type, "currentText")
        self.registerField("tp_percentage", self.tp_percentage)
        self.registerField("sl_percentage", self.sl_percentage)
        self.registerField("trailing_first", self.trailing_first)
        self.registerField("max_profit_trail", self.max_profit)
        self.registerField("profit_step", self.profit_step)
        self.registerField("loss_step", self.loss_step)

        # Initial update
        self._on_profit_type_changed()

    def _on_profit_type_changed(self):
        """Show/hide trailing settings based on profit type."""
        is_trailing = self.profit_type.currentText() == "TRAILING"
        self.trailing_group.setVisible(is_trailing)


class NotificationPage(QWizardPage):
    """Notification preferences page - integrates with BrokerageSetting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Notifications")
        self.setSubTitle("Configure how you want to be notified")

        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Telegram notifications
        telegram_group = QGroupBox("📱 Telegram Notifications")
        telegram_group.setStyleSheet("""
            QGroupBox {
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                font-size: 11pt;
                background: #161b22;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #58a6ff;
            }
        """)
        telegram_layout = QFormLayout(telegram_group)
        telegram_layout.setVerticalSpacing(12)

        self.enable_telegram = QCheckBox("Enable Telegram notifications")
        self.enable_telegram.setChecked(True)
        self.enable_telegram.setStyleSheet("""
            QCheckBox {
                color: #e6edf3;
                font-size: 10pt;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        telegram_layout.addRow("", self.enable_telegram)

        self.bot_token = QLineEdit()
        self.bot_token.setEchoMode(QLineEdit.Password)
        self.bot_token.setPlaceholderText("Enter your bot token from @BotFather")
        self.bot_token.setStyleSheet("""
            QLineEdit {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        telegram_layout.addRow("Bot Token:", self.bot_token)

        self.chat_id = QLineEdit()
        self.chat_id.setPlaceholderText("Enter your chat ID (get from @userinfobot)")
        self.chat_id.setStyleSheet("""
            QLineEdit {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        telegram_layout.addRow("Chat ID:", self.chat_id)

        layout.addWidget(telegram_group)

        # Notification events
        events_group = QGroupBox("🔔 Notify on Events")
        events_group.setStyleSheet("""
            QGroupBox {
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                font-size: 11pt;
                background: #161b22;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #58a6ff;
            }
        """)
        events_layout = QVBoxLayout(events_group)
        events_layout.setSpacing(8)

        self.notify_trade_open = QCheckBox("Trade opened")
        self.notify_trade_open.setChecked(True)
        self.notify_trade_close = QCheckBox("Trade closed")
        self.notify_trade_close.setChecked(True)
        self.notify_risk_breach = QCheckBox("Risk breach")
        self.notify_risk_breach.setChecked(True)
        self.notify_connection = QCheckBox("Connection issues")
        self.notify_connection.setChecked(True)

        for cb in [self.notify_trade_open, self.notify_trade_close,
                   self.notify_risk_breach, self.notify_connection]:
            cb.setStyleSheet("""
                QCheckBox {
                    color: #e6edf3;
                    font-size: 10pt;
                    spacing: 8px;
                }
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                }
            """)
            events_layout.addWidget(cb)

        layout.addWidget(events_group)

        # Connect enable/disable
        self.enable_telegram.toggled.connect(self.bot_token.setEnabled)
        self.enable_telegram.toggled.connect(self.chat_id.setEnabled)
        for cb in [self.notify_trade_open, self.notify_trade_close,
                   self.notify_risk_breach, self.notify_connection]:
            self.enable_telegram.toggled.connect(cb.setEnabled)

        layout.addStretch()
        self.setLayout(layout)

        # Register fields
        self.registerField("enable_telegram", self.enable_telegram)
        self.registerField("bot_token", self.bot_token)
        self.registerField("chat_id", self.chat_id)


class CompletionPage(QWizardPage):
    """Setup completion page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Setup Complete!")
        self.setSubTitle("Your trading platform is ready to use")

        layout = QVBoxLayout()
        layout.setSpacing(20)

        # Success icon with animation
        icon_container = QFrame()
        icon_container.setFixedSize(120, 120)
        icon_container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #238636, stop: 1 #2ea043);
                border-radius: 60px;
                margin: 10px auto;
            }
        """)
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel("✅")
        icon_label.setStyleSheet("font-size: 60px; color: white; background: transparent;")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_layout.addWidget(icon_label)

        # Center the icon
        icon_wrapper = QHBoxLayout()
        icon_wrapper.addStretch()
        icon_wrapper.addWidget(icon_container)
        icon_wrapper.addStretch()
        layout.addLayout(icon_wrapper)

        # Completion card
        complete_card = QFrame()
        complete_card.setObjectName("infoCard")
        complete_card.setStyleSheet("""
            QFrame#infoCard {
                background: #21262d;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 20px;
            }
        """)
        complete_layout = QVBoxLayout(complete_card)

        complete_title = QLabel("🎉 Congratulations!")
        complete_title.setStyleSheet("color: #2ea043; font-size: 24pt; font-weight: bold;")
        complete_title.setAlignment(Qt.AlignCenter)
        complete_layout.addWidget(complete_title)

        summary = QLabel(
            "You've successfully completed the initial setup. Your trading platform is now configured "
            "with your preferences and ready to use.\n\n"
            "<b>Next steps:</b>\n"
            "• Explore the main dashboard\n"
            "• Start with paper trading to test your strategies\n"
            "• Review and adjust settings as needed\n"
            "• Check the documentation for advanced features"
        )
        summary.setWordWrap(True)
        summary.setStyleSheet("color: #8b949e; font-size: 11pt; line-height: 1.5;")
        complete_layout.addWidget(summary)

        layout.addWidget(complete_card)

        # Quick tips
        tips_frame = QFrame()
        tips_frame.setStyleSheet("""
            QFrame {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 15px;
            }
        """)
        tips_layout = QVBoxLayout(tips_frame)

        tips_title = QLabel("💡 Quick Tips")
        tips_title.setStyleSheet("font-weight: bold; color: #58a6ff; font-size: 12pt; line-height: 1.5;")
        tips_layout.addWidget(tips_title)

        tips = [
            "• Use Ctrl+L to open the log viewer",
            "• Press F5 to refresh market data",
            "• Hover over any indicator for tooltips",
            "• Right-click charts for additional options",
            "• Configure strategies via the Strategy Picker"
        ]

        for tip in tips:
            tip_label = QLabel(tip)
            tip_label.setStyleSheet("color: #8b949e; font-size: 11pt; padding: 2px 0; line-height: 1.5;")
            tips_layout.addWidget(tip_label)

        layout.addWidget(tips_frame)

        # Launch option
        launch_frame = QFrame()
        launch_frame.setStyleSheet("""
            QFrame {
                background: #1a1f26;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        launch_layout = QHBoxLayout(launch_frame)

        self.launch_check = QCheckBox("🚀 Launch main application now")
        self.launch_check.setChecked(True)
        self.launch_check.setStyleSheet("""
            QCheckBox {
                color: #e6edf3;
                font-size: 11pt;
                font-weight: bold;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
            }
        """)
        launch_layout.addWidget(self.launch_check)

        launch_layout.addStretch()
        launch_note = QLabel("You can also launch later from the desktop icon")
        launch_note.setStyleSheet("color: #8b949e; font-size: 9pt; font-style: italic;")
        launch_layout.addWidget(launch_note)

        layout.addWidget(launch_frame)

        layout.addStretch()
        self.setLayout(layout)

    def shouldLaunch(self):
        """Return whether to launch main app."""
        return self.launch_check.isChecked()


class OnboardingWizard(QWizard):
    """Main onboarding wizard that guides users through setup."""

    # Signal emitted when onboarding is completed
    onboarding_completed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Set window properties
        self.setWindowTitle("✨ First-Time Setup Wizard")
        self.setMinimumSize(800, 700)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)

        # Apply the same dark theme as the main application
        self.setStyleSheet("""
            QWizard {
                background: #0d1117;
            }
            QWizardPage {
                background: #0d1117;
            }
            QLabel {
                color: #e6edf3;
            }
            QLabel#subTitleLabel {
                color: #8b949e;
            }
            QWizard QPushButton {
                background: #238636;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
                font-size: 10pt;
            }
            QWizard QPushButton:hover {
                background: #2ea043;
            }
            QWizard QPushButton:disabled {
                background: #21262d;
                color: #484f58;
            }
            QWizard QPushButton[text="Cancel"] {
                background: #da3633;
            }
            QWizard QPushButton[text="Cancel"]:hover {
                background: #f85149;
            }
            QWizard QPushButton[text="Back"] {
                background: #21262d;
            }
            QWizard QPushButton[text="Back"]:hover {
                background: #30363d;
            }
            QWizard QFrame {
                border: none;
            }
        """)

        # Set wizard style
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.HaveHelpButton, False)
        self.setOption(QWizard.HaveCustomButton1, False)

        # Customize button text
        self.setButtonText(QWizard.NextButton, "Next →")
        self.setButtonText(QWizard.BackButton, "← Back")
        self.setButtonText(QWizard.FinishButton, "✨ Finish")
        self.setButtonText(QWizard.CancelButton, "Cancel")

        # Add pages
        self.welcome_page = WelcomePage()
        self.broker_page = BrokerConfigPage()
        self.preferences_page = TradingPreferencesPage()
        self.risk_page = RiskManagementPage()
        self.notification_page = NotificationPage()
        self.completion_page = CompletionPage()

        self.addPage(self.welcome_page)
        self.addPage(self.broker_page)
        self.addPage(self.preferences_page)
        self.addPage(self.risk_page)
        self.addPage(self.notification_page)
        self.addPage(self.completion_page)

        # Store configuration
        self.config = {}

        logger.info("Onboarding wizard initialized")

    def accept(self):
        """Handle wizard completion."""
        try:
            # Collect all configuration
            self.config = self._collect_config()

            # Save to database via setting classes
            success = self._save_to_database()

            if success:
                # Mark onboarding as completed in database
                self._mark_completed()

                # Emit signal with config
                self.onboarding_completed.emit(self.config)

                logger.info("Onboarding completed successfully")
                super().accept()
            else:
                QMessageBox.critical(
                    self, "Save Failed",
                    "Failed to save settings to database. Please check the logs."
                )
        except Exception as e:
            logger.error(f"Failed to complete onboarding: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to complete setup: {e}")

    def _collect_config(self) -> Dict[str, Any]:
        """Collect all configuration from wizard pages."""
        return {
            'broker': {
                'broker_type': self.broker_page.broker_combo.currentData(),
                'client_id': self.broker_page.client_id.text(),
                'secret_key': self.broker_page.secret_key.text(),
                'redirect_uri': self.broker_page.redirect_uri.text(),
                'save_credentials': self.broker_page.save_creds.isChecked(),
                'telegram_bot_token': self.notification_page.bot_token.text(),
                'telegram_chat_id': self.notification_page.chat_id.text(),
                'enable_telegram': self.notification_page.enable_telegram.isChecked(),
            },
            'trading': {
                'mode': 'live' if self.preferences_page.mode_live.isChecked() else 'paper',
                'derivative': self.preferences_page.derivative_combo.currentText(),
                'lot_size': self.preferences_page.lot_size.value(),
                'exchange': self.preferences_page.exchange.text(),
                'week': self.preferences_page.week.value(),
                'history_interval': self.preferences_page.interval_combo.currentText(),
                'call_lookback': self.preferences_page.call_lookback.value(),
                'put_lookback': self.preferences_page.put_lookback.value(),
                'sideway_zone_trade': self.preferences_page.sideway_check.isChecked(),
            },
            'risk': {
                'capital_reserve': self.risk_page.capital_reserve.value(),
                'max_options': self.risk_page.max_options.value(),
                'profit_type': self.risk_page.profit_type.currentText(),
                'tp_percentage': self.risk_page.tp_percentage.value(),
                'sl_percentage': self.risk_page.sl_percentage.value(),
                'trailing_first': self.risk_page.trailing_first.value() if self.risk_page.trailing_group.isVisible() else 0,
                'max_profit': self.risk_page.max_profit.value() if self.risk_page.trailing_group.isVisible() else 0,
                'profit_step': self.risk_page.profit_step.value() if self.risk_page.trailing_group.isVisible() else 0,
                'loss_step': self.risk_page.loss_step.value() if self.risk_page.trailing_group.isVisible() else 0,
            },
            'notifications': {
                'notify_trade_open': self.notification_page.notify_trade_open.isChecked(),
                'notify_trade_close': self.notification_page.notify_trade_close.isChecked(),
                'notify_risk_breach': self.notification_page.notify_risk_breach.isChecked(),
                'notify_connection': self.notification_page.notify_connection.isChecked(),
            },
            'quick_setup': self.welcome_page.isQuickSetup(),
            'completed_at': datetime.now().isoformat()
        }

    def _save_to_database(self) -> bool:
        """Save configuration to database via setting classes."""
        try:
            # 1. Save Brokerage Settings
            self._save_broker_settings()

            # 2. Save Trading Mode Settings
            self._save_trading_mode_settings()

            # 3. Save Daily Trade Settings
            self._save_daily_trade_settings()

            # 4. Save Profit/Stoploss Settings
            self._save_profit_stoploss_settings()

            logger.info("All settings saved to database successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to save settings to database: {e}", exc_info=True)
            return False

    def _save_broker_settings(self):
        """Save broker settings to database."""
        broker = BrokerageSetting()
        broker.broker_type = self.config['broker']['broker_type']
        broker.client_id = self.config['broker']['client_id']
        broker.secret_key = self.config['broker']['secret_key']
        broker.redirect_uri = self.config['broker']['redirect_uri']
        broker.telegram_bot_token = self.config['broker']['telegram_bot_token']
        broker.telegram_chat_id = self.config['broker']['telegram_chat_id']
        broker.save()
        logger.info(f"Broker settings saved for {broker.broker_type}")

    def _save_trading_mode_settings(self):
        """Save trading mode settings to database."""
        mode_settings = TradingModeSetting()

        # Set mode
        if self.config['trading']['mode'] == 'live':
            mode_settings.mode = TradingMode.LIVE
            mode_settings.allow_live_trading = True
        else:
            mode_settings.mode = TradingMode.SIM
            mode_settings.allow_live_trading = False

        # Set other defaults
        mode_settings.confirm_live_trades = True
        mode_settings.paper_balance = 100000.0
        mode_settings.simulate_slippage = True
        mode_settings.slippage_percent = 0.05
        mode_settings.simulate_delay = True
        mode_settings.delay_ms = 500

        # Save
        mode_settings.save()
        logger.info(f"Trading mode settings saved: {mode_settings.mode.value}")

    def _save_daily_trade_settings(self):
        """Save daily trade settings to database."""
        daily = DailyTradeSetting()
        daily.derivative = self.config['trading']['derivative']
        daily.lot_size = self.config['trading']['lot_size']
        daily.exchange = self.config['trading']['exchange']
        daily.week = self.config['trading']['week']
        daily.history_interval = self.config['trading']['history_interval']
        daily.call_lookback = self.config['trading']['call_lookback']
        daily.put_lookback = self.config['trading']['put_lookback']
        daily.sideway_zone_trade = self.config['trading']['sideway_zone_trade']
        daily.capital_reserve = self.config['risk']['capital_reserve']
        daily.max_num_of_option = self.config['risk']['max_options']
        daily.save()
        logger.info(f"Daily trade settings saved for {daily.derivative}")

    def _save_profit_stoploss_settings(self):
        """Save profit/stoploss settings to database."""
        pnl = ProfitStoplossSetting()
        pnl.profit_type = self.config['risk']['profit_type']
        pnl.tp_percentage = self.config['risk']['tp_percentage']
        pnl.stoploss_percentage = self.config['risk']['sl_percentage']

        # Trailing settings (only if applicable)
        if self.config['risk']['profit_type'] == "TRAILING":
            pnl.trailing_first_profit = self.config['risk']['trailing_first']
            pnl.max_profit = self.config['risk']['max_profit']
            pnl.profit_step = self.config['risk']['profit_step']
            pnl.loss_step = self.config['risk']['loss_step']

        pnl.save()
        logger.info(f"Profit/Stoploss settings saved: TP={pnl.tp_percentage}%, SL={pnl.stoploss_percentage}%")

    def _mark_completed(self):
        """Mark onboarding as completed by setting a flag in the database."""
        try:
            db = get_db()
            kv.set(ONBOARDING_COMPLETED_KEY, {
                'completed': True,
                'timestamp': datetime.now().isoformat(),
                'version': '2.0.0'
            }, db)
            logger.info("Onboarding marked as completed in database")
        except Exception as e:
            logger.error(f"Failed to mark onboarding completed in database: {e}")


def is_first_time() -> bool:
    """
    Check if this is the first time the application is running.

    This function checks for the onboarding_completed flag in the app_kv table.
    If the flag exists and is True, it's not the first time.

    Returns:
        bool: True if this is first run, False otherwise
    """
    try:
        db = get_db()

        # Check for the onboarding completed flag in app_kv
        onboarding_data = kv.get(ONBOARDING_COMPLETED_KEY, None, db)

        if onboarding_data is not None:
            # If the flag exists, it's not the first time
            logger.info("Onboarding flag found in database - not first time")
            return False

        # No flag found - first time setup
        logger.info("No onboarding flag found - first time setup")
        return True

    except Exception as e:
        logger.error(f"Error checking first-time status: {e}")
        # If we can't check, assume it's not first time to be safe
        return False


def mark_onboarding_completed():
    """Manually mark onboarding as completed."""
    try:
        db = get_db()
        kv.set(ONBOARDING_COMPLETED_KEY, {
            'completed': True,
            'timestamp': datetime.now().isoformat(),
            'version': '2.0.0',
            'manual': True
        }, db)
        logger.info("Manually marked onboarding as completed in database")
    except Exception as e:
        logger.error(f"Failed to mark onboarding completed: {e}")