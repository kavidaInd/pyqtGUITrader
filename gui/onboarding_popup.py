# gui/onboarding_popup.py
"""
First-time setup wizard that guides users through initial configuration.
Now with a theme matching the main application and setting pages.
Fully integrated with ThemeManager for dynamic theme support.
Includes a disclaimer page for risk acknowledgment.
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

from Utils.safe_getattr import safe_hasattr
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

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

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

# Per-broker field hints (from BrokerageSettingGUI) - These are text, not colors
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


class ThemedPageMixin:
    """Mixin class to provide theme token shortcuts for all pages."""

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing


class DisclaimerPage(QWizardPage, ThemedPageMixin):
    """Disclaimer page acknowledging the risks of live trading."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setTitle("⚠️ Important Disclaimer")
            self.setSubTitle("Please read and acknowledge the risks before proceeding")

            self._build_ui()

            # Apply theme
            self.apply_theme()

            logger.info("[DisclaimerPage.__init__] Initialized successfully")

        except Exception as e:
            logger.error(f"[DisclaimerPage.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        try:
            self.acknowledge_check = None
            self._closing = False
        except Exception as e:
            logger.error(f"[DisclaimerPage._safe_defaults_init] Failed: {e}", exc_info=True)

    def _build_ui(self):
        """Build the disclaimer UI with proper formatting."""
        try:
            # Main layout with proper margins
            layout = QVBoxLayout()
            layout.setContentsMargins(
                self._sp.PAD_XL * 2,  # Left margin
                self._sp.PAD_XL,  # Top margin
                self._sp.PAD_XL * 2,  # Right margin
                self._sp.PAD_XL  # Bottom margin
            )
            layout.setSpacing(self._sp.PAD_LG)

            # =============================================================
            # Warning Header
            # =============================================================
            warning_header = QFrame()
            warning_header.setObjectName("warningHeader")
            warning_header.setStyleSheet(f"""
                QFrame#warningHeader {{
                    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                        stop: 0 rgba({int(self._c.RED[1:3], 16)}, {int(self._c.RED[3:5], 16)}, {int(self._c.RED[5:7], 16)}, 0.2),
                        stop: 1 rgba({int(self._c.RED[1:3], 16)}, {int(self._c.RED[3:5], 16)}, {int(self._c.RED[5:7], 16)}, 0.05));
                    border-radius: {self._sp.RADIUS_LG}px;
                    border-left: {self._sp.PAD_SM}px solid {self._c.RED_BRIGHT};
                }}
            """)

            header_layout = QHBoxLayout(warning_header)
            header_layout.setContentsMargins(
                self._sp.PAD_XL, self._sp.PAD_LG,
                self._sp.PAD_XL, self._sp.PAD_LG
            )
            header_layout.setSpacing(self._sp.PAD_LG)

            # Warning icon
            icon_label = QLabel("⚠️")
            icon_label.setStyleSheet(f"""
                font-size: {self._ty.SIZE_DISPLAY * 2}pt;
                color: {self._c.RED_BRIGHT};
                background: transparent;
                padding-right: {self._sp.PAD_MD}px;
            """)
            header_layout.addWidget(icon_label)

            # Header text
            header_text = QLabel("RISK WARNING")
            header_text.setStyleSheet(f"""
                font-size: {self._ty.SIZE_XL}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
                color: {self._c.RED_BRIGHT};
                background: transparent;
                letter-spacing: 1px;
            """)
            header_layout.addWidget(header_text)
            header_layout.addStretch()

            layout.addWidget(warning_header)

            # =============================================================
            # Main Disclaimer Content (Scrollable)
            # =============================================================
            disclaimer_frame = QFrame()
            disclaimer_frame.setObjectName("disclaimerFrame")
            disclaimer_frame.setStyleSheet(f"""
                QFrame#disclaimerFrame {{
                    background: {self._c.BG_PANEL};
                    border: {self._sp.SEPARATOR}px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_LG}px;
                }}
            """)

            disclaimer_layout = QVBoxLayout(disclaimer_frame)
            disclaimer_layout.setContentsMargins(0, 0, 0, 0)

            # Scroll area for long content
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setFrameShape(QFrame.NoFrame)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll_area.setStyleSheet(f"""
                QScrollArea {{
                    background: transparent;
                    border: none;
                    border-radius: {self._sp.RADIUS_LG}px;
                }}
                QScrollArea > QWidget > QWidget {{
                    background: transparent;
                }}
                QScrollBar:vertical {{
                    background: {self._c.BG_MAIN};
                    width: {self._sp.ICON_MD}px;
                    border-radius: {self._sp.RADIUS_MD}px;
                }}
                QScrollBar::handle:vertical {{
                    background: {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    min-height: {self._sp.BTN_HEIGHT_SM}px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background: {self._c.BORDER_STRONG};
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                    height: 0;
                }}
            """)

            # Content widget for scroll area
            scroll_content = QWidget()
            scroll_content.setObjectName("scrollContent")
            scroll_content.setStyleSheet("background: transparent;")

            scroll_layout = QVBoxLayout(scroll_content)
            scroll_layout.setContentsMargins(
                self._sp.PAD_XL, self._sp.PAD_XL,
                self._sp.PAD_XL, self._sp.PAD_XL
            )
            scroll_layout.setSpacing(self._sp.PAD_LG)

            # Risk acknowledgment text sections
            sections = [
                ("⚠️ TRADING RISK DISCLAIMER",
                 "Trading in financial instruments, particularly options, involves substantial risk of loss and is not suitable for all investors. You should carefully consider whether trading is appropriate for you in light of your experience, objectives, financial resources, and risk tolerance."),

                ("💀 CAPITAL AT RISK",
                 "You may sustain a total loss of your invested capital and potentially more. Never invest money you cannot afford to lose. Past performance does not guarantee future results."),

                ("📊 MARKET RISKS",
                 "Market conditions can change rapidly due to economic, political, or technical factors. These changes can adversely affect trade outcomes regardless of strategy performance."),

                ("🔧 TECHNICAL RISKS",
                 "This software relies on internet connectivity, broker APIs, and third-party services. Technical failures, connectivity issues, software bugs, or data inaccuracies may occur and affect trading results."),

                ("⚖️ NO ADVICE",
                 "The developers and distributors of this software are not financial advisors. This software is a tool for executing your trading strategies, not financial advice. You are solely responsible for your trading decisions."),

                ("📜 LIMITATION OF LIABILITY",
                 "To the maximum extent permitted by law, the developers and distributors shall not be liable for any direct, indirect, incidental, special, exemplary, or consequential damages arising from the use or inability to use this software.")
            ]

            for title, content in sections:
                # Section title
                title_label = QLabel(title)
                title_label.setStyleSheet(f"""
                    QLabel {{
                        color: {self._c.RED_BRIGHT if "RISK" in title or "CAPITAL" in title else self._c.YELLOW_BRIGHT};
                        font-size: {self._ty.SIZE_MD}pt;
                        font-weight: {self._ty.WEIGHT_BOLD};
                        background: transparent;
                        padding-top: {self._sp.PAD_SM}px;
                    }}
                """)
                scroll_layout.addWidget(title_label)

                # Section content
                content_label = QLabel(content)
                content_label.setWordWrap(True)
                content_label.setStyleSheet(f"""
                    QLabel {{
                        color: {self._c.TEXT_DIM};
                        font-size: {self._ty.SIZE_BODY}pt;
                        line-height: 1.6;
                        background: transparent;
                        padding-left: {self._sp.PAD_LG}px;
                        padding-right: {self._sp.PAD_LG}px;
                        padding-bottom: {self._sp.PAD_MD}px;
                    }}
                """)
                scroll_layout.addWidget(content_label)

                # Add separator except for last item
                if title != sections[-1][0]:
                    separator = QFrame()
                    separator.setFrameShape(QFrame.HLine)
                    separator.setStyleSheet(f"""
                        QFrame {{
                            background: {self._c.BORDER};
                            max-height: {self._sp.SEPARATOR}px;
                            margin: {self._sp.PAD_SM}px {self._sp.PAD_LG}px;
                        }}
                    """)
                    scroll_layout.addWidget(separator)

            scroll_layout.addStretch()
            scroll_area.setWidget(scroll_content)
            disclaimer_layout.addWidget(scroll_area)

            layout.addWidget(disclaimer_frame, 1)  # Give it stretch factor

            # =============================================================
            # Acknowledgment Section
            # =============================================================
            ack_frame = QFrame()
            ack_frame.setObjectName("ackFrame")
            ack_frame.setStyleSheet(f"""
                QFrame#ackFrame {{
                    background: {self._c.BG_HOVER};
                    border: {self._sp.SEPARATOR}px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_LG}px;
                }}
            """)

            ack_layout = QHBoxLayout(ack_frame)
            ack_layout.setContentsMargins(
                self._sp.PAD_XL, self._sp.PAD_LG,
                self._sp.PAD_XL, self._sp.PAD_LG
            )
            ack_layout.setSpacing(self._sp.PAD_LG)

            # Checkbox
            self.acknowledge_check = QCheckBox()
            self.acknowledge_check.setMinimumSize(self._sp.ICON_XL, self._sp.ICON_XL)
            self.acknowledge_check.setStyleSheet(f"""
                QCheckBox {{
                    background: transparent;
                }}
                QCheckBox::indicator {{
                    width: {self._sp.ICON_LG}px;
                    height: {self._sp.ICON_LG}px;
                }}
                QCheckBox::indicator:unchecked {{
                    border: {self._sp.SEPARATOR}px solid {self._c.BORDER};
                    background: {self._c.BG_MAIN};
                    border-radius: {self._sp.RADIUS_SM}px;
                }}
                QCheckBox::indicator:checked {{
                    background: {self._c.GREEN};
                    border: {self._sp.SEPARATOR}px solid {self._c.GREEN_BRIGHT};
                    border-radius: {self._sp.RADIUS_SM}px;
                }}
                QCheckBox::indicator:hover {{
                    border: {self._sp.SEPARATOR}px solid {self._c.BORDER_FOCUS};
                }}
            """)
            self.acknowledge_check.stateChanged.connect(self._on_check_changed)
            ack_layout.addWidget(self.acknowledge_check)

            # Acknowledgment text (in a QVBoxLayout to allow multiple lines)
            text_container = QWidget()
            text_container.setStyleSheet("background: transparent;")
            text_layout = QVBoxLayout(text_container)
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(self._sp.PAD_XS)

            ack_title = QLabel("ACKNOWLEDGMENT AND ACCEPTANCE")
            ack_title.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    background: transparent;
                }}
            """)
            text_layout.addWidget(ack_title)

            ack_text = QLabel(
                "I have read, understood, and agree to all the terms and conditions above. "
                "I acknowledge that I am solely responsible for all trading decisions and "
                "any financial losses incurred while using this software. I confirm that I "
                "am aware of the risks involved in option trading and accept full responsibility."
            )
            ack_text.setWordWrap(True)
            ack_text.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_DIM};
                    font-size: {self._ty.SIZE_BODY}pt;
                    line-height: 1.5;
                    background: transparent;
                }}
            """)
            text_layout.addWidget(ack_text)

            ack_layout.addWidget(text_container, 1)  # Give it stretch factor

            layout.addWidget(ack_frame)

            self.setLayout(layout)

            # Register field to control Next button
            self.registerField("disclaimer_acknowledged", self.acknowledge_check)

        except Exception as e:
            logger.error(f"[DisclaimerPage._build_ui] Failed: {e}", exc_info=True)

    def _on_check_changed(self, state):
        """Handle checkbox state change."""
        try:
            self.completeChanged.emit()  # Notify wizard that complete state may have changed
        except Exception as e:
            logger.error(f"[DisclaimerPage._on_check_changed] Failed: {e}", exc_info=True)

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the page."""
        try:
            if self._closing:
                return

            # Update styles that depend on theme
            if self.acknowledge_check:
                self.acknowledge_check.setStyleSheet(f"""
                    QCheckBox {{
                        background: transparent;
                    }}
                    QCheckBox::indicator {{
                        width: {self._sp.ICON_LG}px;
                        height: {self._sp.ICON_LG}px;
                    }}
                    QCheckBox::indicator:unchecked {{
                        border: {self._sp.SEPARATOR}px solid {self._c.BORDER};
                        background: {self._c.BG_MAIN};
                        border-radius: {self._sp.RADIUS_SM}px;
                    }}
                    QCheckBox::indicator:checked {{
                        background: {self._c.GREEN};
                        border: {self._sp.SEPARATOR}px solid {self._c.GREEN_BRIGHT};
                        border-radius: {self._sp.RADIUS_SM}px;
                    }}
                    QCheckBox::indicator:hover {{
                        border: {self._sp.SEPARATOR}px solid {self._c.BORDER_FOCUS};
                    }}
                """)

            logger.debug("[DisclaimerPage.apply_theme] Applied theme")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[DisclaimerPage.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[DisclaimerPage.apply_theme] Failed: {e}", exc_info=True)

    def isComplete(self):
        """Override to enable Next button only when checkbox is checked."""
        return self.acknowledge_check.isChecked() if self.acknowledge_check else False

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            logger.info("[DisclaimerPage.cleanup] Starting cleanup")
            self._closing = True
            self.acknowledge_check = None
            logger.info("[DisclaimerPage.cleanup] Cleanup completed")
        except Exception as e:
            logger.error(f"[DisclaimerPage.cleanup] Error: {e}", exc_info=True)

class WelcomePage(QWizardPage, ThemedPageMixin):
    """Welcome page with introduction."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setTitle("Welcome to Algo Trading Pro")
            self.setSubTitle("Let's get you started with your first-time setup")

            self._build_ui()

            # Apply theme
            self.apply_theme()

            logger.info("[WelcomePage.__init__] Initialized successfully")

        except Exception as e:
            logger.error(f"[WelcomePage.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        try:
            self.quick_check = None
            self._closing = False
        except Exception as e:
            logger.error(f"[WelcomePage._safe_defaults_init] Failed: {e}", exc_info=True)

    def _build_ui(self):
        """Build the UI with proper spacing."""
        try:
            # Main layout with proper margins
            layout = QVBoxLayout()
            layout.setContentsMargins(
                self._sp.PAD_XL * 2,  # Left margin
                self._sp.PAD_XL,  # Top margin
                self._sp.PAD_XL * 2,  # Right margin
                self._sp.PAD_XL  # Bottom margin
            )
            layout.setSpacing(self._sp.PAD_LG)

            # =============================================================
            # Logo or icon with gradient background
            # =============================================================
            icon_container = QFrame()
            icon_container.setFixedSize(120, 120)
            icon_container.setObjectName("iconContainer")
            icon_container.setStyleSheet(self._get_icon_container_style())

            icon_layout = QVBoxLayout(icon_container)
            icon_layout.setContentsMargins(0, 0, 0, 0)

            icon_label = QLabel("📈")
            icon_label.setStyleSheet(f"""
                font-size: 60px; 
                color: {self._c.TEXT_INVERSE}; 
                background: transparent;
            """)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_layout.addWidget(icon_label)

            # Center the icon
            icon_wrapper = QHBoxLayout()
            icon_wrapper.addStretch()
            icon_wrapper.addWidget(icon_container)
            icon_wrapper.addStretch()
            layout.addLayout(icon_wrapper)

            # =============================================================
            # Welcome text with styled card
            # =============================================================
            welcome_card = QFrame()
            welcome_card.setObjectName("infoCard")
            welcome_card.setStyleSheet(self._get_card_style())

            welcome_layout = QVBoxLayout(welcome_card)
            welcome_layout.setContentsMargins(
                self._sp.PAD_XL, self._sp.PAD_XL,
                self._sp.PAD_XL, self._sp.PAD_XL
            )
            welcome_layout.setSpacing(self._sp.PAD_MD)

            welcome_title = QLabel("<h2>Welcome to Algo Trading Pro!</h2>")
            welcome_title.setStyleSheet(f"""
                color: {self._c.TEXT_MAIN}; 
                font-size: {self._ty.SIZE_XL}pt; 
                font-weight: {self._ty.WEIGHT_BOLD};
                background: transparent;
                margin-bottom: {self._sp.PAD_MD}px;
            """)
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
            welcome_text.setStyleSheet(f"""
                color: {self._c.TEXT_DIM}; 
                font-size: {self._ty.SIZE_BODY}pt; 
                line-height: 1.6;
                background: transparent;
            """)
            welcome_layout.addWidget(welcome_text)

            layout.addWidget(welcome_card)

            # =============================================================
            # Quick start option with styled frame
            # =============================================================
            quick_frame = QFrame()
            quick_frame.setStyleSheet(self._get_frame_style())

            quick_layout = QHBoxLayout(quick_frame)
            quick_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_MD,
                self._sp.PAD_LG, self._sp.PAD_MD
            )
            quick_layout.setSpacing(self._sp.GAP_MD)

            self.quick_check = QCheckBox("✨ Use quick setup with recommended defaults")
            self.quick_check.setChecked(True)
            self.quick_check.setMinimumHeight(self._sp.BTN_HEIGHT_MD)
            self.quick_check.setStyleSheet(self._get_checkbox_style())
            quick_layout.addWidget(self.quick_check)

            quick_layout.addStretch()
            quick_desc = QLabel("(Recommended for first-time users)")
            quick_desc.setStyleSheet(f"""
                color: {self._c.TEXT_DIM}; 
                font-size: {self._ty.SIZE_XS}pt; 
                font-style: italic;
                background: transparent;
            """)
            quick_layout.addWidget(quick_desc)

            layout.addWidget(quick_frame)

            # Add stretch to push everything up
            layout.addStretch()

            self.setLayout(layout)

        except Exception as e:
            logger.error(f"[WelcomePage._build_ui] Failed: {e}", exc_info=True)

    def _get_icon_container_style(self):
        """Get styled icon container."""
        c = self._c
        return f"""
            QFrame#iconContainer {{
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 {c.GREEN}, stop: 1 {c.GREEN_BRIGHT});
                border-radius: 60px;
                margin: {self._sp.PAD_MD}px auto;
            }}
        """

    def _get_card_style(self):
        """Get styled card with proper padding."""
        c = self._c
        sp = self._sp
        return f"""
            QFrame#infoCard {{
                background: {c.BG_HOVER};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
            }}
        """

    def _get_frame_style(self):
        """Get styled frame with proper padding."""
        c = self._c
        sp = self._sp
        return f"""
            QFrame {{
                background: {c.BG_PANEL};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
            }}
        """

    def _get_checkbox_style(self):
        """Get styled checkbox with proper spacing."""
        c = self._c
        sp = self._sp
        return f"""
            QCheckBox {{
                color: {c.TEXT_MAIN};
                font-size: {self._ty.SIZE_BODY}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
                spacing: {sp.GAP_MD}px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: {sp.ICON_LG}px;
                height: {sp.ICON_LG}px;
            }}
            QCheckBox::indicator:unchecked {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                background: {c.BG_HOVER};
                border-radius: {sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:checked {{
                background: {c.GREEN};
                border: {sp.SEPARATOR}px solid {c.GREEN_BRIGHT};
                border-radius: {sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:hover {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
        """

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the page.
        Called on theme change and initial render.
        """
        try:
            # Skip if closing
            if self._closing:
                return

            if self.quick_check:
                self.quick_check.setStyleSheet(self._get_checkbox_style())

            logger.debug("[WelcomePage.apply_theme] Applied theme")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[WelcomePage.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[WelcomePage.apply_theme] Failed: {e}", exc_info=True)

    def isQuickSetup(self):
        """Return whether quick setup is selected."""
        try:
            return self.quick_check.isChecked() if self.quick_check else True
        except Exception as e:
            logger.error(f"[WelcomePage.isQuickSetup] Failed: {e}", exc_info=True)
            return True

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            logger.info("[WelcomePage.cleanup] Starting cleanup")
            self._closing = True
            self.quick_check = None
            logger.info("[WelcomePage.cleanup] Cleanup completed")
        except Exception as e:
            logger.error(f"[WelcomePage.cleanup] Error: {e}", exc_info=True)


class BrokerConfigPage(QWizardPage, ThemedPageMixin):
    """Broker configuration page - integrates with BrokerageSetting."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setTitle("Broker Configuration")
            self.setSubTitle("Connect to your brokerage account")

            self._build_ui()

            # Connect broker change to update hints
            self.broker_combo.currentIndexChanged.connect(self._update_broker_hints)

            # Register fields
            self.registerField("broker", self.broker_combo)
            self.registerField("client_id", self.client_id)
            self.registerField("secret_key", self.secret_key)
            self.registerField("redirect_uri", self.redirect_uri)
            self.registerField("save_creds", self.save_creds)

            # Apply theme
            self.apply_theme()

            # Initial update
            QTimer.singleShot(100, self._update_broker_hints)

            logger.info("[BrokerConfigPage.__init__] Initialized successfully")

        except Exception as e:
            logger.error(f"[BrokerConfigPage.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        try:
            self.broker_combo = None
            self.broker_desc = None
            self.client_id_label = None
            self.client_id = None
            self.secret_key_label = None
            self.secret_key = None
            self.redirect_label = None
            self.redirect_uri = None
            self.field_hint = None
            self.save_creds = None
            self._closing = False
        except Exception as e:
            logger.error(f"[BrokerConfigPage._safe_defaults_init] Failed: {e}", exc_info=True)

    def _build_ui(self):
        """Build the UI with proper spacing and padding."""
        try:
            # Main layout with proper margins
            layout = QVBoxLayout()
            layout.setContentsMargins(
                self._sp.PAD_XL * 2,  # Left margin
                self._sp.PAD_XL,  # Top margin
                self._sp.PAD_XL * 2,  # Right margin
                self._sp.PAD_XL  # Bottom margin
            )
            layout.setSpacing(self._sp.PAD_LG)  # Space between groups

            # =============================================================
            # Broker selection group
            # =============================================================
            broker_group = QGroupBox("🏦 Select Your Broker")
            broker_group.setStyleSheet(self._get_groupbox_style())

            broker_layout = QVBoxLayout(broker_group)
            broker_layout.setContentsMargins(
                self._sp.PAD_LG,  # Left
                self._sp.PAD_MD,  # Top
                self._sp.PAD_LG,  # Right
                self._sp.PAD_MD  # Bottom
            )
            broker_layout.setSpacing(self._sp.GAP_MD)

            # Broker combo with proper height
            self.broker_combo = QComboBox()
            self.broker_combo.setMinimumHeight(self._sp.INPUT_HEIGHT)

            # Add all brokers from BROKER_ORDER list
            for bt in BROKER_ORDER:
                display_name = BrokerType.DISPLAY_NAMES.get(bt, bt)
                self.broker_combo.addItem(f"{display_name}  ({bt})", bt)

            self.broker_combo.setStyleSheet(self._get_combobox_style())
            broker_layout.addWidget(self.broker_combo)

            # Broker description with proper padding
            self.broker_desc = QLabel("Select your broker to see specific credential requirements")
            self.broker_desc.setWordWrap(True)
            self.broker_desc.setMinimumHeight(self._sp.INPUT_HEIGHT * 2)
            self.broker_desc.setStyleSheet(self._get_info_label_style())
            broker_layout.addWidget(self.broker_desc)

            layout.addWidget(broker_group)

            # =============================================================
            # Credentials group
            # =============================================================
            cred_group = QGroupBox("🔑 API Credentials")
            cred_group.setStyleSheet(self._get_groupbox_style())

            cred_layout = QFormLayout(cred_group)
            cred_layout.setContentsMargins(
                self._sp.PAD_LG,  # Left
                self._sp.PAD_MD,  # Top
                self._sp.PAD_LG,  # Right
                self._sp.PAD_MD  # Bottom
            )
            cred_layout.setVerticalSpacing(self._sp.GAP_LG)  # Space between rows
            cred_layout.setHorizontalSpacing(self._sp.PAD_XL)  # Space between label and field
            cred_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cred_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            # Client ID / API Key
            self.client_id_label = QLabel("Client ID / App ID:")
            self.client_id_label.setMinimumWidth(120)
            self.client_id_label.setStyleSheet(f"""
                color: {self._c.TEXT_MAIN}; 
                font-size: {self._ty.SIZE_BODY}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
                padding-right: {self._sp.PAD_MD}px;
            """)

            self.client_id = QLineEdit()
            self.client_id.setPlaceholderText("e.g. XY12345-100")
            self.client_id.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.client_id.setStyleSheet(self._get_lineedit_style())
            cred_layout.addRow(self.client_id_label, self.client_id)

            # Secret Key
            self.secret_key_label = QLabel("App Secret:")
            self.secret_key_label.setMinimumWidth(120)
            self.secret_key_label.setStyleSheet(f"""
                color: {self._c.TEXT_MAIN}; 
                font-size: {self._ty.SIZE_BODY}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
                padding-right: {self._sp.PAD_MD}px;
            """)

            self.secret_key = QLineEdit()
            self.secret_key.setEchoMode(QLineEdit.Password)
            self.secret_key.setPlaceholderText("From myapi.fyers.in")
            self.secret_key.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.secret_key.setStyleSheet(self._get_lineedit_style())
            cred_layout.addRow(self.secret_key_label, self.secret_key)

            # Redirect URI / TOTP Secret
            self.redirect_label = QLabel("Redirect URI:")
            self.redirect_label.setMinimumWidth(120)
            self.redirect_label.setStyleSheet(f"""
                color: {self._c.TEXT_MAIN}; 
                font-size: {self._ty.SIZE_BODY}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
                padding-right: {self._sp.PAD_MD}px;
            """)

            self.redirect_uri = QLineEdit()
            self.redirect_uri.setPlaceholderText("e.g. https://127.0.0.1/callback")
            self.redirect_uri.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.redirect_uri.setStyleSheet(self._get_lineedit_style(disabled_color=self._c.TEXT_DISABLED))
            cred_layout.addRow(self.redirect_label, self.redirect_uri)

            # Field hint with proper padding
            self.field_hint = QLabel("")
            self.field_hint.setWordWrap(True)
            self.field_hint.setMinimumHeight(self._sp.INPUT_HEIGHT * 2)
            self.field_hint.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.BLUE};
                    font-size: {self._ty.SIZE_SM}pt;
                    background: {self._c.BG_ROW_B};
                    border-radius: {self._sp.RADIUS_SM}px;
                    padding: {self._sp.PAD_MD}px;
                    margin-top: {self._sp.PAD_XS}px;
                    border-left: {self._sp.PAD_XS}px solid {self._c.BLUE};
                }}
            """)
            cred_layout.addRow("", self.field_hint)

            layout.addWidget(cred_group)

            # =============================================================
            # Save credentials checkbox with styled container
            # =============================================================
            save_frame = QFrame()
            save_frame.setStyleSheet(self._get_frame_style())

            save_layout = QHBoxLayout(save_frame)
            save_layout.setContentsMargins(
                self._sp.PAD_LG,  # Left
                self._sp.PAD_MD,  # Top
                self._sp.PAD_LG,  # Right
                self._sp.PAD_MD  # Bottom
            )
            save_layout.setSpacing(self._sp.GAP_MD)

            self.save_creds = QCheckBox("🔒 Save credentials (encrypted)")
            self.save_creds.setChecked(True)
            self.save_creds.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.save_creds.setStyleSheet(self._get_checkbox_style())
            save_layout.addWidget(self.save_creds)

            save_layout.addStretch()
            save_note = QLabel("Credentials are stored securely in the local database")
            save_note.setWordWrap(True)
            save_note.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_DIM};
                    font-size: {self._ty.SIZE_XS}pt;
                    font-style: italic;
                    padding: {self._sp.PAD_XS}px;
                }}
            """)
            save_layout.addWidget(save_note)

            layout.addWidget(save_frame)

            # Add stretch to push everything up
            layout.addStretch()

            self.setLayout(layout)

        except Exception as e:
            logger.error(f"[BrokerConfigPage._build_ui] Failed: {e}", exc_info=True)

    def _get_groupbox_style(self):
        """Get styled groupbox with proper padding."""
        c = self._c
        sp = self._sp
        return f"""
            QGroupBox {{
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                margin-top: {sp.PAD_LG}px;
                font-weight: {self._ty.WEIGHT_BOLD};
                font-size: {self._ty.SIZE_LG}pt;
                background: {c.BG_PANEL};
                padding-top: {sp.PAD_SM}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {sp.PAD_LG}px;
                padding: 0 {sp.PAD_MD}px 0 {sp.PAD_MD}px;
                color: {c.BLUE};
            }}
        """

    def _get_combobox_style(self):
        """Get styled combobox with proper padding."""
        c = self._c
        sp = self._sp
        return f"""
            QComboBox {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-height: {sp.INPUT_HEIGHT}px;
            }}
            QComboBox:hover {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
            QComboBox::drop-down {{
                border: none;
                width: {sp.ICON_LG * 2}px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 6px solid {c.TEXT_DIM};
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                selection-background-color: {c.BG_SELECTED};
                selection-color: {c.TEXT_MAIN};
                padding: {sp.PAD_SM}px 0px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                min-height: {sp.ROW_HEIGHT}px;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background: {c.BG_SELECTED};
            }}
        """

    def _get_lineedit_style(self, disabled_color=None):
        """Get styled lineedit with proper padding."""
        c = self._c
        sp = self._sp
        disabled = f"background: {c.BG_PANEL}; color: {disabled_color or c.TEXT_DISABLED};"

        return f"""
            QLineEdit {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-height: {sp.INPUT_HEIGHT - 8}px;
                selection-background-color: {c.BG_SELECTED};
            }}
            QLineEdit:focus {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
                background: {c.BG_HOVER};
            }}
            QLineEdit:hover {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
            QLineEdit:disabled {{
                {disabled}
            }}
            QLineEdit::placeholder {{
                color: {c.TEXT_DISABLED};
                font-style: italic;
            }}
        """

    def _get_info_label_style(self):
        """Get styled info label with proper padding."""
        c = self._c
        sp = self._sp
        return f"""
            QLabel {{
                color: {c.TEXT_DIM};
                font-size: {self._ty.SIZE_SM}pt;
                padding: {sp.PAD_MD}px;
                background: {c.BG_ROW_B};
                border-radius: {sp.RADIUS_MD}px;
                border-left: {sp.PAD_SM}px solid {c.BLUE};
                margin-top: {sp.PAD_XS}px;
                line-height: 1.5;
            }}
        """

    def _get_frame_style(self):
        """Get styled frame with proper padding."""
        c = self._c
        sp = self._sp
        return f"""
            QFrame {{
                background: {c.BG_ROW_B};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
            }}
        """

    def _get_checkbox_style(self):
        """Get styled checkbox with proper spacing."""
        c = self._c
        sp = self._sp
        return f"""
            QCheckBox {{
                color: {c.TEXT_MAIN};
                font-size: {self._ty.SIZE_BODY}pt;
                spacing: {sp.GAP_MD}px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: {sp.ICON_LG}px;
                height: {sp.ICON_LG}px;
            }}
            QCheckBox::indicator:unchecked {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                background: {c.BG_HOVER};
                border-radius: {sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:checked {{
                background: {c.GREEN};
                border: {sp.SEPARATOR}px solid {c.GREEN_BRIGHT};
                border-radius: {sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:hover {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
        """

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the page.
        Called on theme change and initial render.
        """
        try:
            # Skip if closing
            if self._closing:
                return

            # Update all widgets with theme styles
            if self.broker_combo:
                self.broker_combo.setStyleSheet(self._get_combobox_style())
            if self.client_id:
                self.client_id.setStyleSheet(self._get_lineedit_style())
            if self.secret_key:
                self.secret_key.setStyleSheet(self._get_lineedit_style())
            if self.redirect_uri:
                self.redirect_uri.setStyleSheet(self._get_lineedit_style(
                    disabled_color=self._c.TEXT_DISABLED if safe_hasattr(self, '_c') else None
                ))
            if self.save_creds:
                self.save_creds.setStyleSheet(self._get_checkbox_style())
            if self.broker_desc:
                self.broker_desc.setStyleSheet(self._get_info_label_style())
            if self.field_hint:
                self.field_hint.setStyleSheet(f"""
                    QLabel {{
                        color: {self._c.BLUE};
                        font-size: {self._ty.SIZE_SM}pt;
                        background: {self._c.BG_ROW_B};
                        border-radius: {self._sp.RADIUS_SM}px;
                        padding: {self._sp.PAD_MD}px;
                        margin-top: {self._sp.PAD_XS}px;
                        border-left: {self._sp.PAD_XS}px solid {self._c.BLUE};
                    }}
                """)

            logger.debug("[BrokerConfigPage.apply_theme] Applied theme")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[BrokerConfigPage.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[BrokerConfigPage.apply_theme] Failed: {e}", exc_info=True)

    def _update_broker_hints(self):
        """Update field labels and hints based on selected broker."""
        try:
            broker_value = self.broker_combo.currentData()

            # Get hints for this broker
            hints = BROKER_HINTS.get(broker_value, BROKER_HINTS[BrokerType.FYERS])

            # Update labels with proper text
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

            # Update hints with proper formatting
            self.field_hint.setText(f"ℹ️ {hints.get('redirect_note', '')}")
            self.broker_desc.setText(f"ℹ️ {hints.get('auth_note', '')}")

        except Exception as e:
            logger.error(f"[BrokerConfigPage._update_broker_hints] Failed: {e}", exc_info=True)

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            logger.info("[BrokerConfigPage.cleanup] Starting cleanup")
            self._closing = True
            self.broker_combo = None
            self.client_id = None
            self.secret_key = None
            self.redirect_uri = None
            self.save_creds = None
            logger.info("[BrokerConfigPage.cleanup] Cleanup completed")
        except Exception as e:
            logger.error(f"[BrokerConfigPage.cleanup] Error: {e}", exc_info=True)


class TradingPreferencesPage(QWizardPage, ThemedPageMixin):
    """Trading preferences page - integrates with DailyTradeSetting."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setTitle("Trading Preferences")
            self.setSubTitle("Configure your default trading settings")

            # Get default values from DailyTradeSetting
            self.defaults = DailyTradeSetting.DEFAULTS

            self._build_ui()

            # Register fields
            self._register_fields()

            # Apply theme
            self.apply_theme()

            logger.info("[TradingPreferencesPage.__init__] Initialized successfully")

        except Exception as e:
            logger.error(f"[TradingPreferencesPage.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.defaults = {}
        self.mode_paper = None
        self.mode_live = None
        self.live_warning = None
        self.derivative_combo = None
        self.lot_size = None
        self.exchange = None
        self.week = None
        self.interval_combo = None
        self.call_lookback = None
        self.put_lookback = None
        self.sideway_check = None
        self._closing = False

    def _build_ui(self):
        """Build the UI with proper spacing."""
        try:
            # Main layout with proper margins
            layout = QVBoxLayout()
            layout.setContentsMargins(
                self._sp.PAD_XL * 2,  # Left margin
                self._sp.PAD_XL,  # Top margin
                self._sp.PAD_XL * 2,  # Right margin
                self._sp.PAD_XL  # Bottom margin
            )
            layout.setSpacing(self._sp.PAD_LG)

            # =============================================================
            # Trading mode group
            # =============================================================
            mode_group = QGroupBox("🎮 Trading Mode")
            mode_group.setStyleSheet(self._get_groupbox_style())

            mode_layout = QVBoxLayout(mode_group)
            mode_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_MD,
                self._sp.PAD_LG, self._sp.PAD_MD
            )
            mode_layout.setSpacing(self._sp.GAP_MD)

            self.mode_paper = QRadioButton("📊 Paper Trading (simulated)")
            self.mode_live = QRadioButton("💰 Live Trading (real money)")
            self.mode_paper.setChecked(True)

            for rb in [self.mode_paper, self.mode_live]:
                rb.setMinimumHeight(self._sp.BTN_HEIGHT_MD)
                rb.setStyleSheet(self._get_radiobutton_style())
                mode_layout.addWidget(rb)

            # Live trading warning
            self.live_warning = QLabel("⚠️ Warning: Live trading uses real money")
            self.live_warning.setWordWrap(True)
            self.live_warning.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.live_warning.setStyleSheet(self._get_warning_style())
            self.live_warning.setVisible(False)
            mode_layout.addWidget(self.live_warning)

            self.mode_live.toggled.connect(lambda checked: self.live_warning.setVisible(checked))

            layout.addWidget(mode_group)

            # =============================================================
            # Instrument preferences
            # =============================================================
            instr_group = QGroupBox("📈 Instrument Preferences")
            instr_group.setStyleSheet(self._get_groupbox_style())

            instr_layout = QFormLayout(instr_group)
            instr_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_MD,
                self._sp.PAD_LG, self._sp.PAD_MD
            )
            instr_layout.setVerticalSpacing(self._sp.GAP_LG)
            instr_layout.setHorizontalSpacing(self._sp.PAD_XL)
            instr_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Derivative
            self.derivative_combo = QComboBox()
            derivatives = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCAPNIFTY", "SENSEX"]
            for d in derivatives:
                self.derivative_combo.addItem(d)
            self.derivative_combo.setCurrentText(self.defaults.get("derivative", "NIFTY"))
            self.derivative_combo.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.derivative_combo.setStyleSheet(self._get_combobox_style())
            instr_layout.addRow(self._create_label("Derivative:"), self.derivative_combo)

            # Lot Size — read-only, auto-filled from OptionUtils when derivative changes.
            # SEBI regulations fix lot sizes per index; they cannot be edited.
            self.lot_size_display = QLineEdit()
            self.lot_size_display.setReadOnly(True)
            self.lot_size_display.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.lot_size_display.setToolTip(
                "Lot size is fixed by SEBI for each index and cannot be edited.\n"
                "NIFTY=65  BANKNIFTY=30  FINNIFTY=60  MIDCPNIFTY=120  SENSEX=20"
            )
            instr_layout.addRow(self._create_label("Lot Size (Auto):"), self.lot_size_display)

            # Wire derivative combo → auto-update lot size display
            def _update_lot_size_display(index):
                try:
                    from Utils.OptionUtils import OptionUtils as _OU
                    sym = self.derivative_combo.currentText()
                    lot = _OU.get_lot_size(sym)
                    self.lot_size_display.setText(f"{lot} units")
                except Exception:
                    self.lot_size_display.setText("—")

            self.derivative_combo.currentIndexChanged.connect(_update_lot_size_display)
            _update_lot_size_display(0)  # set initial value

            # Exchange
            self.exchange = QLineEdit()
            self.exchange.setText(self.defaults.get("exchange", "NSE"))
            self.exchange.setPlaceholderText("e.g. NSE, BSE")
            self.exchange.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.exchange.setStyleSheet(self._get_lineedit_style())
            instr_layout.addRow(self._create_label("Exchange:"), self.exchange)

            # Week (expiry)
            self.week = QSpinBox()
            self.week.setRange(0, 53)
            self.week.setValue(self.defaults.get("week", 0))
            self.week.setSuffix(" (0 = current)")
            self.week.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.week.setStyleSheet(self._get_spinbox_style())
            instr_layout.addRow(self._create_label("Expiry Week:"), self.week)

            layout.addWidget(instr_group)

            # =============================================================
            # History settings
            # =============================================================
            hist_group = QGroupBox("📊 Historical Data")
            hist_group.setStyleSheet(self._get_groupbox_style())

            hist_layout = QFormLayout(hist_group)
            hist_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_MD,
                self._sp.PAD_LG, self._sp.PAD_MD
            )
            hist_layout.setVerticalSpacing(self._sp.GAP_LG)
            hist_layout.setHorizontalSpacing(self._sp.PAD_XL)

            # History interval
            self.interval_combo = QComboBox()
            intervals = ["1m", "2m", "3m", "5m", "10m", "15m", "30m", "60m"]
            for i in intervals:
                self.interval_combo.addItem(i)
            self.interval_combo.setCurrentText(self.defaults.get("history_interval", "2m"))
            self.interval_combo.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.interval_combo.setStyleSheet(self._get_combobox_style())
            hist_layout.addRow(self._create_label("Candle Interval:"), self.interval_combo)

            # Lookback periods
            # Lookback — number of strikes from ATM (0 = ATM, 1 = one strike OTM/ITM, …)
            self.call_lookback = QSpinBox()
            self.call_lookback.setRange(0, 10)
            self.call_lookback.setValue(self.defaults.get("call_lookback", 0))
            self.call_lookback.setSuffix(" strike(s) from ATM")
            self.call_lookback.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.call_lookback.setStyleSheet(self._get_spinbox_style())
            self.call_lookback.setToolTip(
                "Number of strikes away from ATM for the CALL leg.\n"
                "0 = ATM  |  1 = one strike OTM  |  2 = two strikes OTM  …\n"
                "Positive values move further OTM (cheaper premium)."
            )
            hist_layout.addRow(self._create_label("Call Lookback:"), self.call_lookback)

            self.put_lookback = QSpinBox()
            self.put_lookback.setRange(0, 10)
            self.put_lookback.setValue(self.defaults.get("put_lookback", 0))
            self.put_lookback.setSuffix(" strike(s) from ATM")
            self.put_lookback.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.put_lookback.setStyleSheet(self._get_spinbox_style())
            self.put_lookback.setToolTip(
                "Number of strikes away from ATM for the PUT leg.\n"
                "0 = ATM  |  1 = one strike OTM  |  2 = two strikes OTM  …\n"
                "Positive values move further OTM (cheaper premium)."
            )
            hist_layout.addRow(self._create_label("Put Lookback:"), self.put_lookback)

            layout.addWidget(hist_group)

            # =============================================================
            # Sideways trading
            # =============================================================
            sideway_frame = QFrame()
            sideway_frame.setStyleSheet(self._get_frame_style())

            sideway_layout = QHBoxLayout(sideway_frame)
            sideway_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_MD,
                self._sp.PAD_LG, self._sp.PAD_MD
            )
            sideway_layout.setSpacing(self._sp.GAP_MD)

            self.sideway_check = QCheckBox("Enable trading during sideways market (12:00–14:00)")
            self.sideway_check.setChecked(self.defaults.get("sideway_zone_trade", False))
            self.sideway_check.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.sideway_check.setStyleSheet(self._get_checkbox_style())
            sideway_layout.addWidget(self.sideway_check)

            sideway_layout.addStretch()
            sideway_info = QLabel("ℹ️ Allows trading during low-volatility period")
            sideway_info.setStyleSheet(f"""
                color: {self._c.TEXT_DIM}; 
                font-size: {self._ty.SIZE_XS}pt;
                background: transparent;
            """)
            sideway_layout.addWidget(sideway_info)

            layout.addWidget(sideway_frame)

            # Add stretch to push everything up
            layout.addStretch()

            self.setLayout(layout)

        except Exception as e:
            logger.error(f"[TradingPreferencesPage._build_ui] Failed: {e}", exc_info=True)

    def _create_label(self, text):
        """Create a styled label."""
        label = QLabel(text)
        label.setMinimumWidth(100)
        label.setStyleSheet(f"""
            color: {self._c.TEXT_MAIN}; 
            font-size: {self._ty.SIZE_BODY}pt;
            font-weight: {self._ty.WEIGHT_BOLD};
            padding-right: {self._sp.PAD_MD}px;
        """)
        return label

    def _get_groupbox_style(self):
        """Get styled groupbox with proper padding."""
        c = self._c
        sp = self._sp
        return f"""
            QGroupBox {{
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                margin-top: {sp.PAD_LG}px;
                font-weight: {self._ty.WEIGHT_BOLD};
                font-size: {self._ty.SIZE_LG}pt;
                background: {c.BG_PANEL};
                padding-top: {sp.PAD_SM}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {sp.PAD_LG}px;
                padding: 0 {sp.PAD_MD}px 0 {sp.PAD_MD}px;
                color: {c.BLUE};
            }}
        """

    def _get_combobox_style(self):
        """Get styled combobox."""
        c = self._c
        sp = self._sp
        return f"""
            QComboBox {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-height: {sp.INPUT_HEIGHT}px;
            }}
            QComboBox:hover {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
        """

    def _get_spinbox_style(self):
        """Get styled spinbox."""
        c = self._c
        sp = self._sp
        return f"""
            QSpinBox, QDoubleSpinBox {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-height: {sp.INPUT_HEIGHT}px;
            }}
        """

    def _get_lineedit_style(self):
        """Get styled lineedit."""
        c = self._c
        sp = self._sp
        return f"""
            QLineEdit {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-height: {sp.INPUT_HEIGHT}px;
            }}
        """

    def _get_radiobutton_style(self):
        """Get styled radiobutton."""
        c = self._c
        sp = self._sp
        return f"""
            QRadioButton {{
                color: {c.TEXT_MAIN};
                font-size: {self._ty.SIZE_BODY}pt;
                spacing: {sp.GAP_MD}px;
                background: transparent;
            }}
            QRadioButton::indicator {{
                width: {sp.ICON_LG}px;
                height: {sp.ICON_LG}px;
            }}
            QRadioButton::indicator:unchecked {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                background: {c.BG_HOVER};
                border-radius: {sp.ICON_LG // 2}px;
            }}
            QRadioButton::indicator:checked {{
                background: {c.GREEN};
                border: {sp.SEPARATOR}px solid {c.GREEN_BRIGHT};
                border-radius: {sp.ICON_LG // 2}px;
            }}
            QRadioButton::indicator:hover {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
        """

    def _get_checkbox_style(self):
        """Get styled checkbox."""
        c = self._c
        sp = self._sp
        return f"""
            QCheckBox {{
                color: {c.TEXT_MAIN};
                font-size: {self._ty.SIZE_BODY}pt;
                spacing: {sp.GAP_MD}px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: {sp.ICON_LG}px;
                height: {sp.ICON_LG}px;
            }}
            QCheckBox::indicator:unchecked {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                background: {c.BG_HOVER};
                border-radius: {sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:checked {{
                background: {c.GREEN};
                border: {sp.SEPARATOR}px solid {c.GREEN_BRIGHT};
                border-radius: {sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:hover {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
        """

    def _get_warning_style(self):
        """Get styled warning label."""
        c = self._c
        sp = self._sp
        return f"""
            QLabel {{
                color: {c.RED_BRIGHT};
                font-size: {self._ty.SIZE_SM}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
                padding: {sp.PAD_MD}px;
                background: rgba({int(c.RED[1:3], 16)}, {int(c.RED[3:5], 16)}, {int(c.RED[5:7], 16)}, 0.1);
                border-radius: {sp.RADIUS_MD}px;
                border-left: {sp.PAD_SM}px solid {c.RED_BRIGHT};
            }}
        """

    def _get_frame_style(self):
        """Get styled frame."""
        c = self._c
        sp = self._sp
        return f"""
            QFrame {{
                background: {c.BG_ROW_B};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
            }}
        """

    def _register_fields(self):
        """Register form fields."""
        try:
            self.registerField("trading_mode", self.mode_live, "checked")
            self.registerField("derivative", self.derivative_combo, "currentText")
            self.registerField("exchange", self.exchange)
            self.registerField("week", self.week)
            self.registerField("history_interval", self.interval_combo, "currentText")
            self.registerField("call_lookback", self.call_lookback)
            self.registerField("put_lookback", self.put_lookback)
            self.registerField("sideway_zone_trade", self.sideway_check)
        except Exception as e:
            logger.error(f"[TradingPreferencesPage._register_fields] Failed: {e}", exc_info=True)

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the page."""
        try:
            if self._closing:
                return

            # Update all widgets with theme styles
            if self.mode_paper and self.mode_live:
                self.mode_paper.setStyleSheet(self._get_radiobutton_style())
                self.mode_live.setStyleSheet(self._get_radiobutton_style())
            if self.live_warning:
                self.live_warning.setStyleSheet(self._get_warning_style())
            if self.derivative_combo:
                self.derivative_combo.setStyleSheet(self._get_combobox_style())
            if self.exchange:
                self.exchange.setStyleSheet(self._get_lineedit_style())
            if self.week:
                self.week.setStyleSheet(self._get_spinbox_style())
            if self.interval_combo:
                self.interval_combo.setStyleSheet(self._get_combobox_style())
            if self.call_lookback:
                self.call_lookback.setStyleSheet(self._get_spinbox_style())
            if self.put_lookback:
                self.put_lookback.setStyleSheet(self._get_spinbox_style())
            if self.sideway_check:
                self.sideway_check.setStyleSheet(self._get_checkbox_style())

            logger.debug("[TradingPreferencesPage.apply_theme] Applied theme")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[TradingPreferencesPage.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[TradingPreferencesPage.apply_theme] Failed: {e}", exc_info=True)

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            logger.info("[TradingPreferencesPage.cleanup] Starting cleanup")
            self._closing = True
            self.mode_paper = None
            self.mode_live = None
            self.derivative_combo = None
            self.lot_size_display = None
            self.exchange = None
            self.week = None
            self.interval_combo = None
            self.call_lookback = None
            self.put_lookback = None
            self.sideway_check = None
            logger.info("[TradingPreferencesPage.cleanup] Cleanup completed")
        except Exception as e:
            logger.error(f"[TradingPreferencesPage.cleanup] Error: {e}", exc_info=True)


class RiskManagementPage(QWizardPage, ThemedPageMixin):
    """Risk management page - integrates with ProfitStoplossSetting."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setTitle("Risk Management")
            self.setSubTitle("Configure your risk parameters")

            # Get default values from ProfitStoplossSetting
            self.defaults = ProfitStoplossSetting.DEFAULTS

            self._build_ui()

            # Connect profit type change
            self.profit_type.currentTextChanged.connect(self._on_profit_type_changed)

            # Register fields
            self._register_fields()

            # Apply theme
            self.apply_theme()

            # Initial update
            self._on_profit_type_changed()

            logger.info("[RiskManagementPage.__init__] Initialized successfully")

        except Exception as e:
            logger.error(f"[RiskManagementPage.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.defaults = {}
        self.capital_reserve = None
        self.max_options = None
        self.profit_type = None
        self.tp_percentage = None
        self.sl_percentage = None
        self.trailing_group = None
        self.trailing_first = None
        self.max_profit = None
        self.profit_step = None
        self.loss_step = None
        self._closing = False

    def _build_ui(self):
        """Build the UI with proper spacing."""
        try:
            # Main layout with proper margins
            layout = QVBoxLayout()
            layout.setContentsMargins(
                self._sp.PAD_XL * 2,  # Left margin
                self._sp.PAD_XL,  # Top margin
                self._sp.PAD_XL * 2,  # Right margin
                self._sp.PAD_XL  # Bottom margin
            )
            layout.setSpacing(self._sp.PAD_LG)

            # =============================================================
            # Capital allocation group
            # =============================================================
            capital_group = QGroupBox("💰 Capital Allocation")
            capital_group.setStyleSheet(self._get_groupbox_style())

            capital_layout = QFormLayout(capital_group)
            capital_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_MD,
                self._sp.PAD_LG, self._sp.PAD_MD
            )
            capital_layout.setVerticalSpacing(self._sp.GAP_LG)
            capital_layout.setHorizontalSpacing(self._sp.PAD_XL)
            capital_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Capital reserve
            self.capital_reserve = QSpinBox()
            self.capital_reserve.setRange(0, 10000000)
            self.capital_reserve.setSingleStep(10000)
            self.capital_reserve.setPrefix("₹ ")
            self.capital_reserve.setValue(self.defaults.get("capital_reserve", 500000))
            self.capital_reserve.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.capital_reserve.setStyleSheet(self._get_spinbox_style())
            capital_layout.addRow(self._create_label("Capital Reserve:"), self.capital_reserve)

            # Max options per trade
            self.max_options = QSpinBox()
            self.max_options.setRange(1, 100)
            self.max_options.setValue(self.defaults.get("max_num_of_option", 10))
            self.max_options.setSuffix(" contracts")
            self.max_options.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.max_options.setStyleSheet(self._get_spinbox_style())
            capital_layout.addRow(self._create_label("Max Options/Trade:"), self.max_options)

            layout.addWidget(capital_group)

            # =============================================================
            # Stop Loss and Take Profit group
            # =============================================================
            sltp_group = QGroupBox("🛑 Stop Loss & Take Profit")
            sltp_group.setStyleSheet(self._get_groupbox_style())

            sltp_layout = QFormLayout(sltp_group)
            sltp_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_MD,
                self._sp.PAD_LG, self._sp.PAD_MD
            )
            sltp_layout.setVerticalSpacing(self._sp.GAP_LG)
            sltp_layout.setHorizontalSpacing(self._sp.PAD_XL)
            sltp_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Profit type
            self.profit_type = QComboBox()
            self.profit_type.addItems(["STOP", "TRAILING", "FIXED"])
            self.profit_type.setCurrentText(self.defaults.get("profit_type", "STOP"))
            self.profit_type.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.profit_type.setStyleSheet(self._get_combobox_style())
            sltp_layout.addRow(self._create_label("Profit Type:"), self.profit_type)

            # Take Profit
            self.tp_percentage = QDoubleSpinBox()
            self.tp_percentage.setRange(0.1, 100.0)
            self.tp_percentage.setValue(self.defaults.get("tp_percentage", 15.0))
            self.tp_percentage.setSuffix(" %")
            self.tp_percentage.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.tp_percentage.setStyleSheet(self._get_spinbox_style())
            sltp_layout.addRow(self._create_label("Take Profit:"), self.tp_percentage)

            # Stop Loss
            self.sl_percentage = QDoubleSpinBox()
            self.sl_percentage.setRange(0.1, 50.0)
            self.sl_percentage.setValue(self.defaults.get("stoploss_percentage", 7.0))
            self.sl_percentage.setSuffix(" %")
            self.sl_percentage.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.sl_percentage.setStyleSheet(self._get_spinbox_style())
            sltp_layout.addRow(self._create_label("Stop Loss:"), self.sl_percentage)

            # Stop loss note
            sl_note = QLabel("⚠️ Stop loss is applied BELOW entry price for long positions")
            sl_note.setWordWrap(True)
            sl_note.setStyleSheet(self._get_sl_note_style())
            sltp_layout.addRow("", sl_note)

            layout.addWidget(sltp_group)

            # =============================================================
            # Trailing settings group (initially hidden)
            # =============================================================
            self.trailing_group = QGroupBox("📈 Trailing Settings")
            self.trailing_group.setStyleSheet(self._get_groupbox_style())

            trailing_layout = QFormLayout(self.trailing_group)
            trailing_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_MD,
                self._sp.PAD_LG, self._sp.PAD_MD
            )
            trailing_layout.setVerticalSpacing(self._sp.GAP_LG)
            trailing_layout.setHorizontalSpacing(self._sp.PAD_XL)

            self.trailing_first = QDoubleSpinBox()
            self.trailing_first.setRange(0.1, 50.0)
            self.trailing_first.setValue(self.defaults.get("trailing_first_profit", 3.0))
            self.trailing_first.setSuffix(" %")
            self.trailing_first.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.trailing_first.setStyleSheet(self._get_spinbox_style())
            trailing_layout.addRow(self._create_label("First Profit:"), self.trailing_first)

            self.max_profit = QDoubleSpinBox()
            self.max_profit.setRange(0.1, 200.0)
            self.max_profit.setValue(self.defaults.get("max_profit", 30.0))
            self.max_profit.setSuffix(" %")
            self.max_profit.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.max_profit.setStyleSheet(self._get_spinbox_style())
            trailing_layout.addRow(self._create_label("Max Profit:"), self.max_profit)

            self.profit_step = QDoubleSpinBox()
            self.profit_step.setRange(0.1, 20.0)
            self.profit_step.setValue(self.defaults.get("profit_step", 2.0))
            self.profit_step.setSuffix(" %")
            self.profit_step.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.profit_step.setStyleSheet(self._get_spinbox_style())
            trailing_layout.addRow(self._create_label("Profit Step:"), self.profit_step)

            self.loss_step = QDoubleSpinBox()
            self.loss_step.setRange(0.1, 20.0)
            self.loss_step.setValue(self.defaults.get("loss_step", 2.0))
            self.loss_step.setSuffix(" %")
            self.loss_step.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.loss_step.setStyleSheet(self._get_spinbox_style())
            trailing_layout.addRow(self._create_label("Loss Step:"), self.loss_step)

            layout.addWidget(self.trailing_group)

            # Add stretch to push everything up
            layout.addStretch()

            self.setLayout(layout)

        except Exception as e:
            logger.error(f"[RiskManagementPage._build_ui] Failed: {e}", exc_info=True)

    def _create_label(self, text):
        """Create a styled label."""
        label = QLabel(text)
        label.setMinimumWidth(120)
        label.setStyleSheet(f"""
            color: {self._c.TEXT_MAIN}; 
            font-size: {self._ty.SIZE_BODY}pt;
            font-weight: {self._ty.WEIGHT_BOLD};
            padding-right: {self._sp.PAD_MD}px;
        """)
        return label

    def _get_groupbox_style(self):
        """Get styled groupbox."""
        c = self._c
        sp = self._sp
        return f"""
            QGroupBox {{
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                margin-top: {sp.PAD_LG}px;
                font-weight: {self._ty.WEIGHT_BOLD};
                font-size: {self._ty.SIZE_LG}pt;
                background: {c.BG_PANEL};
                padding-top: {sp.PAD_SM}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {sp.PAD_LG}px;
                padding: 0 {sp.PAD_MD}px 0 {sp.PAD_MD}px;
                color: {c.BLUE};
            }}
        """

    def _get_spinbox_style(self):
        """Get styled spinbox."""
        c = self._c
        sp = self._sp
        return f"""
            QSpinBox, QDoubleSpinBox {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-height: {sp.INPUT_HEIGHT}px;
            }}
        """

    def _get_combobox_style(self):
        """Get styled combobox."""
        c = self._c
        sp = self._sp
        return f"""
            QComboBox {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-height: {sp.INPUT_HEIGHT}px;
            }}
        """

    def _get_sl_note_style(self):
        """Get styled stop loss note."""
        c = self._c
        sp = self._sp
        return f"""
            QLabel {{
                color: {c.YELLOW_BRIGHT};
                font-size: {self._ty.SIZE_SM}pt;
                padding: {sp.PAD_MD}px;
                background: rgba({int(c.YELLOW[1:3], 16)}, {int(c.YELLOW[3:5], 16)}, {int(c.YELLOW[5:7], 16)}, 0.1);
                border-radius: {sp.RADIUS_MD}px;
                border-left: {sp.PAD_SM}px solid {c.YELLOW_BRIGHT};
            }}
        """

    def _register_fields(self):
        """Register form fields."""
        try:
            self.registerField("capital_reserve", self.capital_reserve)
            self.registerField("max_options", self.max_options)
            self.registerField("profit_type", self.profit_type, "currentText")
            self.registerField("tp_percentage", self.tp_percentage)
            self.registerField("sl_percentage", self.sl_percentage)
            self.registerField("trailing_first", self.trailing_first)
            self.registerField("max_profit_trail", self.max_profit)
            self.registerField("profit_step", self.profit_step)
            self.registerField("loss_step", self.loss_step)
        except Exception as e:
            logger.error(f"[RiskManagementPage._register_fields] Failed: {e}", exc_info=True)

    def _on_profit_type_changed(self):
        """Show/hide trailing settings based on profit type."""
        try:
            if self.trailing_group and self.profit_type:
                is_trailing = self.profit_type.currentText() == "TRAILING"
                self.trailing_group.setVisible(is_trailing)
        except Exception as e:
            logger.error(f"[RiskManagementPage._on_profit_type_changed] Failed: {e}", exc_info=True)

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the page."""
        try:
            if self._closing:
                return

            # Update all widgets with theme styles
            if self.capital_reserve:
                self.capital_reserve.setStyleSheet(self._get_spinbox_style())
            if self.max_options:
                self.max_options.setStyleSheet(self._get_spinbox_style())
            if self.profit_type:
                self.profit_type.setStyleSheet(self._get_combobox_style())
            if self.tp_percentage:
                self.tp_percentage.setStyleSheet(self._get_spinbox_style())
            if self.sl_percentage:
                self.sl_percentage.setStyleSheet(self._get_spinbox_style())
            if self.trailing_first:
                self.trailing_first.setStyleSheet(self._get_spinbox_style())
            if self.max_profit:
                self.max_profit.setStyleSheet(self._get_spinbox_style())
            if self.profit_step:
                self.profit_step.setStyleSheet(self._get_spinbox_style())
            if self.loss_step:
                self.loss_step.setStyleSheet(self._get_spinbox_style())

            logger.debug("[RiskManagementPage.apply_theme] Applied theme")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[RiskManagementPage.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[RiskManagementPage.apply_theme] Failed: {e}", exc_info=True)

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            logger.info("[RiskManagementPage.cleanup] Starting cleanup")
            self._closing = True
            self.capital_reserve = None
            self.max_options = None
            self.profit_type = None
            self.tp_percentage = None
            self.sl_percentage = None
            self.trailing_group = None
            self.trailing_first = None
            self.max_profit = None
            self.profit_step = None
            self.loss_step = None
            logger.info("[RiskManagementPage.cleanup] Cleanup completed")
        except Exception as e:
            logger.error(f"[RiskManagementPage.cleanup] Error: {e}", exc_info=True)


class NotificationPage(QWizardPage, ThemedPageMixin):
    """Notification preferences page - integrates with BrokerageSetting."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setTitle("Notifications")
            self.setSubTitle("Configure how you want to be notified")

            self._build_ui()

            # Connect enable/disable
            self.enable_telegram.toggled.connect(self._on_telegram_toggled)

            # Register fields
            self._register_fields()

            # Apply theme
            self.apply_theme()

            logger.info("[NotificationPage.__init__] Initialized successfully")

        except Exception as e:
            logger.error(f"[NotificationPage.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.enable_telegram = None
        self.bot_token = None
        self.chat_id = None
        self.notify_trade_open = None
        self.notify_trade_close = None
        self.notify_risk_breach = None
        self.notify_connection = None
        self._closing = False

    def _build_ui(self):
        """Build the UI with proper spacing."""
        try:
            # Main layout with proper margins
            layout = QVBoxLayout()
            layout.setContentsMargins(
                self._sp.PAD_XL * 2,  # Left margin
                self._sp.PAD_XL,  # Top margin
                self._sp.PAD_XL * 2,  # Right margin
                self._sp.PAD_XL  # Bottom margin
            )
            layout.setSpacing(self._sp.PAD_LG)

            # =============================================================
            # Telegram notifications group
            # =============================================================
            telegram_group = QGroupBox("📱 Telegram Notifications")
            telegram_group.setStyleSheet(self._get_groupbox_style())

            telegram_layout = QFormLayout(telegram_group)
            telegram_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_MD,
                self._sp.PAD_LG, self._sp.PAD_MD
            )
            telegram_layout.setVerticalSpacing(self._sp.GAP_LG)
            telegram_layout.setHorizontalSpacing(self._sp.PAD_XL)

            self.enable_telegram = QCheckBox("Enable Telegram notifications")
            self.enable_telegram.setChecked(True)
            self.enable_telegram.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.enable_telegram.setStyleSheet(self._get_checkbox_style())
            telegram_layout.addRow("", self.enable_telegram)

            self.bot_token = QLineEdit()
            self.bot_token.setEchoMode(QLineEdit.Password)
            self.bot_token.setPlaceholderText("Enter your bot token from @BotFather")
            self.bot_token.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.bot_token.setStyleSheet(self._get_lineedit_style())
            telegram_layout.addRow(self._create_label("Bot Token:"), self.bot_token)

            self.chat_id = QLineEdit()
            self.chat_id.setPlaceholderText("Enter your chat ID (get from @userinfobot)")
            self.chat_id.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.chat_id.setStyleSheet(self._get_lineedit_style())
            telegram_layout.addRow(self._create_label("Chat ID:"), self.chat_id)

            layout.addWidget(telegram_group)

            # =============================================================
            # Notification events group
            # =============================================================
            events_group = QGroupBox("🔔 Notify on Events")
            events_group.setStyleSheet(self._get_groupbox_style())

            events_layout = QVBoxLayout(events_group)
            events_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_MD,
                self._sp.PAD_LG, self._sp.PAD_MD
            )
            events_layout.setSpacing(self._sp.GAP_MD)

            self.notify_trade_open = QCheckBox("Trade opened")
            self.notify_trade_open.setChecked(True)
            self.notify_trade_open.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.notify_trade_close = QCheckBox("Trade closed")
            self.notify_trade_close.setChecked(True)
            self.notify_risk_breach = QCheckBox("Risk breach")
            self.notify_risk_breach.setChecked(True)
            self.notify_connection = QCheckBox("Connection issues")
            self.notify_connection.setChecked(True)

            for cb in [self.notify_trade_open, self.notify_trade_close,
                       self.notify_risk_breach, self.notify_connection]:
                cb.setStyleSheet(self._get_checkbox_style())
                events_layout.addWidget(cb)

            layout.addWidget(events_group)

            # Add stretch to push everything up
            layout.addStretch()

            self.setLayout(layout)

        except Exception as e:
            logger.error(f"[NotificationPage._build_ui] Failed: {e}", exc_info=True)

    def _create_label(self, text):
        """Create a styled label."""
        label = QLabel(text)
        label.setMinimumWidth(80)
        label.setStyleSheet(f"""
            color: {self._c.TEXT_MAIN}; 
            font-size: {self._ty.SIZE_BODY}pt;
            font-weight: {self._ty.WEIGHT_BOLD};
            padding-right: {self._sp.PAD_MD}px;
        """)
        return label

    def _get_groupbox_style(self):
        """Get styled groupbox."""
        c = self._c
        sp = self._sp
        return f"""
            QGroupBox {{
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                margin-top: {sp.PAD_LG}px;
                font-weight: {self._ty.WEIGHT_BOLD};
                font-size: {self._ty.SIZE_LG}pt;
                background: {c.BG_PANEL};
                padding-top: {sp.PAD_SM}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {sp.PAD_LG}px;
                padding: 0 {sp.PAD_MD}px 0 {sp.PAD_MD}px;
                color: {c.BLUE};
            }}
        """

    def _get_checkbox_style(self):
        """Get styled checkbox."""
        c = self._c
        sp = self._sp
        return f"""
            QCheckBox {{
                color: {c.TEXT_MAIN};
                font-size: {self._ty.SIZE_BODY}pt;
                spacing: {sp.GAP_MD}px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: {sp.ICON_LG}px;
                height: {sp.ICON_LG}px;
            }}
            QCheckBox::indicator:unchecked {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                background: {c.BG_HOVER};
                border-radius: {sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:checked {{
                background: {c.GREEN};
                border: {sp.SEPARATOR}px solid {c.GREEN_BRIGHT};
                border-radius: {sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:hover {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
        """

    def _get_lineedit_style(self):
        """Get styled lineedit."""
        c = self._c
        sp = self._sp
        return f"""
            QLineEdit {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-height: {sp.INPUT_HEIGHT}px;
            }}
        """

    def _on_telegram_toggled(self, checked: bool):
        """Handle telegram enable toggle."""
        try:
            if self.bot_token:
                self.bot_token.setEnabled(checked)
            if self.chat_id:
                self.chat_id.setEnabled(checked)
            if self.notify_trade_open:
                self.notify_trade_open.setEnabled(checked)
            if self.notify_trade_close:
                self.notify_trade_close.setEnabled(checked)
            if self.notify_risk_breach:
                self.notify_risk_breach.setEnabled(checked)
            if self.notify_connection:
                self.notify_connection.setEnabled(checked)
        except Exception as e:
            logger.error(f"[NotificationPage._on_telegram_toggled] Failed: {e}", exc_info=True)

    def _register_fields(self):
        """Register form fields."""
        try:
            self.registerField("enable_telegram", self.enable_telegram)
            self.registerField("bot_token", self.bot_token)
            self.registerField("chat_id", self.chat_id)
        except Exception as e:
            logger.error(f"[NotificationPage._register_fields] Failed: {e}", exc_info=True)

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the page."""
        try:
            if self._closing:
                return

            # Update all widgets with theme styles
            if self.enable_telegram:
                self.enable_telegram.setStyleSheet(self._get_checkbox_style())
            if self.bot_token:
                self.bot_token.setStyleSheet(self._get_lineedit_style())
            if self.chat_id:
                self.chat_id.setStyleSheet(self._get_lineedit_style())
            if self.notify_trade_open:
                self.notify_trade_open.setStyleSheet(self._get_checkbox_style())
            if self.notify_trade_close:
                self.notify_trade_close.setStyleSheet(self._get_checkbox_style())
            if self.notify_risk_breach:
                self.notify_risk_breach.setStyleSheet(self._get_checkbox_style())
            if self.notify_connection:
                self.notify_connection.setStyleSheet(self._get_checkbox_style())

            logger.debug("[NotificationPage.apply_theme] Applied theme")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[NotificationPage.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[NotificationPage.apply_theme] Failed: {e}", exc_info=True)

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            logger.info("[NotificationPage.cleanup] Starting cleanup")
            self._closing = True
            self.enable_telegram = None
            self.bot_token = None
            self.chat_id = None
            self.notify_trade_open = None
            self.notify_trade_close = None
            self.notify_risk_breach = None
            self.notify_connection = None
            logger.info("[NotificationPage.cleanup] Cleanup completed")
        except Exception as e:
            logger.error(f"[NotificationPage.cleanup] Error: {e}", exc_info=True)


class CompletionPage(QWizardPage, ThemedPageMixin):
    """Setup completion page."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setTitle("Setup Complete!")
            self.setSubTitle("Your trading platform is ready to use")

            self._build_ui()

            # Apply theme
            self.apply_theme()

            logger.info("[CompletionPage.__init__] Initialized successfully")

        except Exception as e:
            logger.error(f"[CompletionPage.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.launch_check = None
        self._closing = False

    def _build_ui(self):
        """Build the UI with proper spacing."""
        try:
            # Main layout with proper margins
            layout = QVBoxLayout()
            layout.setContentsMargins(
                self._sp.PAD_XL * 2,  # Left margin
                self._sp.PAD_XL,  # Top margin
                self._sp.PAD_XL * 2,  # Right margin
                self._sp.PAD_XL  # Bottom margin
            )
            layout.setSpacing(self._sp.PAD_XL)

            # =============================================================
            # Success icon with animation
            # =============================================================
            icon_container = QFrame()
            icon_container.setFixedSize(120, 120)
            icon_container.setObjectName("iconContainer")
            icon_container.setStyleSheet(self._get_icon_container_style())

            icon_layout = QVBoxLayout(icon_container)
            icon_layout.setContentsMargins(0, 0, 0, 0)

            icon_label = QLabel("✅")
            icon_label.setStyleSheet(f"""
                font-size: 60px; 
                color: {self._c.TEXT_INVERSE}; 
                background: transparent;
            """)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_layout.addWidget(icon_label)

            # Center the icon
            icon_wrapper = QHBoxLayout()
            icon_wrapper.addStretch()
            icon_wrapper.addWidget(icon_container)
            icon_wrapper.addStretch()
            layout.addLayout(icon_wrapper)

            # =============================================================
            # Completion card
            # =============================================================
            complete_card = QFrame()
            complete_card.setObjectName("infoCard")
            complete_card.setStyleSheet(self._get_card_style())

            complete_layout = QVBoxLayout(complete_card)
            complete_layout.setContentsMargins(
                self._sp.PAD_XL, self._sp.PAD_XL,
                self._sp.PAD_XL, self._sp.PAD_XL
            )
            complete_layout.setSpacing(self._sp.PAD_MD)

            complete_title = QLabel("🎉 Congratulations!")
            complete_title.setStyleSheet(f"""
                color: {self._c.GREEN_BRIGHT}; 
                font-size: {self._ty.SIZE_2XL}pt; 
                font-weight: {self._ty.WEIGHT_BOLD};
                background: transparent;
                margin-bottom: {self._sp.PAD_MD}px;
            """)
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
            summary.setStyleSheet(f"""
                color: {self._c.TEXT_DIM}; 
                font-size: {self._ty.SIZE_BODY}pt; 
                line-height: 1.6;
                background: transparent;
            """)
            complete_layout.addWidget(summary)

            layout.addWidget(complete_card)

            # =============================================================
            # Quick tips
            # =============================================================
            tips_frame = QFrame()
            tips_frame.setStyleSheet(self._get_frame_style())

            tips_layout = QVBoxLayout(tips_frame)
            tips_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_LG,
                self._sp.PAD_LG, self._sp.PAD_LG
            )
            tips_layout.setSpacing(self._sp.GAP_MD)

            tips_title = QLabel("💡 Quick Tips")
            tips_title.setStyleSheet(f"""
                font-weight: {self._ty.WEIGHT_BOLD}; 
                color: {self._c.BLUE}; 
                font-size: {self._ty.SIZE_MD}pt;
                background: transparent;
                margin-bottom: {self._sp.PAD_SM}px;
            """)
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
                tip_label.setStyleSheet(f"""
                    color: {self._c.TEXT_DIM}; 
                    font-size: {self._ty.SIZE_BODY}pt; 
                    padding: {self._sp.PAD_XS}px 0;
                    background: transparent;
                """)
                tips_layout.addWidget(tip_label)

            layout.addWidget(tips_frame)

            # =============================================================
            # Launch option
            # =============================================================
            launch_frame = QFrame()
            launch_frame.setStyleSheet(self._get_frame_style())

            launch_layout = QHBoxLayout(launch_frame)
            launch_layout.setContentsMargins(
                self._sp.PAD_LG, self._sp.PAD_MD,
                self._sp.PAD_LG, self._sp.PAD_MD
            )
            launch_layout.setSpacing(self._sp.GAP_MD)

            self.launch_check = QCheckBox("🚀 Launch main application now")
            self.launch_check.setChecked(True)
            self.launch_check.setMinimumHeight(self._sp.INPUT_HEIGHT)
            self.launch_check.setStyleSheet(self._get_launch_checkbox_style())
            launch_layout.addWidget(self.launch_check)

            launch_layout.addStretch()
            launch_note = QLabel("You can also launch later from the desktop icon")
            launch_note.setStyleSheet(f"""
                color: {self._c.TEXT_DIM}; 
                font-size: {self._ty.SIZE_XS}pt; 
                font-style: italic;
                background: transparent;
            """)
            launch_layout.addWidget(launch_note)

            layout.addWidget(launch_frame)

            # Add stretch to push everything up
            layout.addStretch()

            self.setLayout(layout)

        except Exception as e:
            logger.error(f"[CompletionPage._build_ui] Failed: {e}", exc_info=True)

    def _get_icon_container_style(self):
        """Get styled icon container."""
        c = self._c
        return f"""
            QFrame#iconContainer {{
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 {c.GREEN}, stop: 1 {c.GREEN_BRIGHT});
                border-radius: 60px;
                margin: {self._sp.PAD_MD}px auto;
            }}
        """

    def _get_card_style(self):
        """Get styled card."""
        c = self._c
        sp = self._sp
        return f"""
            QFrame#infoCard {{
                background: {c.BG_HOVER};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
            }}
        """

    def _get_frame_style(self):
        """Get styled frame."""
        c = self._c
        sp = self._sp
        return f"""
            QFrame {{
                background: {c.BG_PANEL};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
            }}
        """

    def _get_launch_checkbox_style(self):
        """Get styled launch checkbox."""
        c = self._c
        sp = self._sp
        return f"""
            QCheckBox {{
                color: {c.TEXT_MAIN};
                font-size: {self._ty.SIZE_BODY}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
                spacing: {sp.GAP_MD}px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: {sp.ICON_LG}px;
                height: {sp.ICON_LG}px;
            }}
            QCheckBox::indicator:unchecked {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                background: {c.BG_HOVER};
                border-radius: {sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:checked {{
                background: {c.GREEN};
                border: {sp.SEPARATOR}px solid {c.GREEN_BRIGHT};
                border-radius: {sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:hover {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
        """

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the page."""
        try:
            if self._closing:
                return

            if self.launch_check:
                self.launch_check.setStyleSheet(self._get_launch_checkbox_style())

            logger.debug("[CompletionPage.apply_theme] Applied theme")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[CompletionPage.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[CompletionPage.apply_theme] Failed: {e}", exc_info=True)

    def shouldLaunch(self):
        """Return whether to launch main app."""
        try:
            return self.launch_check.isChecked() if self.launch_check else True
        except Exception as e:
            logger.error(f"[CompletionPage.shouldLaunch] Failed: {e}", exc_info=True)
            return True

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            logger.info("[CompletionPage.cleanup] Starting cleanup")
            self._closing = True
            self.launch_check = None
            logger.info("[CompletionPage.cleanup] Cleanup completed")
        except Exception as e:
            logger.error(f"[CompletionPage.cleanup] Error: {e}", exc_info=True)


class OnboardingWizard(QWizard, ThemedPageMixin):
    """Main onboarding wizard that guides users through setup."""

    # Signal emitted when onboarding is completed
    onboarding_completed = pyqtSignal(dict)

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            # Set window properties
            self.setWindowTitle("✨ First-Time Setup Wizard")
            self.setMinimumSize(900, 750)
            self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)

            # Set wizard style
            self.setWizardStyle(QWizard.ModernStyle)
            self.setOption(QWizard.HaveHelpButton, False)
            self.setOption(QWizard.HaveCustomButton1, False)

            # Customize button text
            self.setButtonText(QWizard.NextButton, "Next →")
            self.setButtonText(QWizard.BackButton, "← Back")
            self.setButtonText(QWizard.FinishButton, "✨ Finish")
            self.setButtonText(QWizard.CancelButton, "Cancel")

            # Apply theme initially
            self.apply_theme()

            # Add pages (Disclaimer first!)
            self.disclaimer_page = DisclaimerPage()
            self.welcome_page = WelcomePage()
            self.broker_page = BrokerConfigPage()
            self.preferences_page = TradingPreferencesPage()
            self.risk_page = RiskManagementPage()
            self.notification_page = NotificationPage()
            self.completion_page = CompletionPage()

            self.addPage(self.disclaimer_page)
            self.addPage(self.welcome_page)
            self.addPage(self.broker_page)
            self.addPage(self.preferences_page)
            self.addPage(self.risk_page)
            self.addPage(self.notification_page)
            self.addPage(self.completion_page)

            # Store configuration
            self.config = {}

            logger.info("[OnboardingWizard.__init__] Initialized successfully")

        except Exception as e:
            logger.critical(f"[OnboardingWizard.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.disclaimer_page = None
        self.welcome_page = None
        self.broker_page = None
        self.preferences_page = None
        self.risk_page = None
        self.notification_page = None
        self.completion_page = None
        self.config = {}
        self._closing = False

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the wizard.
        Called on theme change, density change, and initial render.
        """
        try:
            # Skip if closing
            if self._closing:
                return

            c = self._c
            sp = self._sp
            ty = self._ty

            self.setStyleSheet(f"""
                QWizard {{
                    background: {c.BG_MAIN};
                }}
                QWizardPage {{
                    background: {c.BG_MAIN};
                }}
                QLabel {{
                    color: {c.TEXT_MAIN};
                }}
                QLabel#subTitleLabel {{
                    color: {c.TEXT_DIM};
                }}
                QWizard QPushButton {{
                    background: {c.GREEN};
                    color: {c.TEXT_INVERSE};
                    border: none;
                    border-radius: {sp.RADIUS_MD}px;
                    padding: {sp.PAD_SM}px {sp.PAD_LG}px;
                    font-weight: {ty.WEIGHT_BOLD};
                    min-width: 90px;
                    min-height: {sp.BTN_HEIGHT_MD}px;
                    font-size: {ty.SIZE_BODY}pt;
                }}
                QWizard QPushButton:hover {{
                    background: {c.GREEN_BRIGHT};
                }}
                QWizard QPushButton:disabled {{
                    background: {c.BG_HOVER};
                    color: {c.TEXT_DISABLED};
                }}
                QWizard QPushButton[text="Cancel"] {{
                    background: {c.RED};
                }}
                QWizard QPushButton[text="Cancel"]:hover {{
                    background: {c.RED_BRIGHT};
                }}
                QWizard QPushButton[text="Back"] {{
                    background: {c.BG_HOVER};
                }}
                QWizard QPushButton[text="Back"]:hover {{
                    background: {c.BORDER};
                }}
                QWizard QFrame {{
                    border: none;
                }}
            """)

            logger.debug("[OnboardingWizard.apply_theme] Applied theme")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[OnboardingWizard.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[OnboardingWizard.apply_theme] Failed: {e}", exc_info=True)

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

                logger.info("[OnboardingWizard.accept] Onboarding completed successfully")
                super().accept()
            else:
                QMessageBox.critical(
                    self, "Save Failed",
                    "Failed to save settings to database. Please check the logs."
                )
        except Exception as e:
            logger.error(f"[OnboardingWizard.accept] Failed to complete onboarding: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to complete setup: {e}")

    def _collect_config(self) -> Dict[str, Any]:
        """Collect all configuration from wizard pages."""
        try:
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
                    'lot_size': __import__('Utils.OptionUtils', fromlist=['OptionUtils']).OptionUtils.get_lot_size(
                        self.preferences_page.derivative_combo.currentText()
                    ),
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
                'disclaimer_acknowledged': self.disclaimer_page.acknowledge_check.isChecked() if self.disclaimer_page else False,
                'completed_at': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[OnboardingWizard._collect_config] Failed: {e}", exc_info=True)
            return {}

    def _save_to_database(self) -> bool:
        """Save configuration to database via setting classes."""
        try:
            if not self.config:
                logger.error("[OnboardingWizard._save_to_database] No config to save")
                return False

            # 1. Save Brokerage Settings
            self._save_broker_settings()

            # 2. Save Trading Mode Settings
            self._save_trading_mode_settings()

            # 3. Save Daily Trade Settings
            self._save_daily_trade_settings()

            # 4. Save Profit/Stoploss Settings
            self._save_profit_stoploss_settings()

            logger.info("[OnboardingWizard._save_to_database] All settings saved to database successfully")
            return True

        except Exception as e:
            logger.error(f"[OnboardingWizard._save_to_database] Failed to save settings: {e}", exc_info=True)
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
        logger.info(f"[OnboardingWizard._save_broker_settings] Broker settings saved for {broker.broker_type}")

    def _save_trading_mode_settings(self):
        """Save trading mode settings to database."""
        mode_settings = TradingModeSetting()

        # Set mode
        if self.config['trading']['mode'] == 'Live':
            mode_settings.mode = TradingMode.LIVE
            mode_settings.allow_live_trading = True
        else:
            mode_settings.mode = TradingMode.PAPER
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
        logger.info(
            f"[OnboardingWizard._save_trading_mode_settings] Trading mode settings saved: {mode_settings.mode.value}")

    def _save_daily_trade_settings(self):
        """Save daily trade settings to database."""
        daily = DailyTradeSetting()
        daily.derivative = self.config['trading']['derivative']
        # lot_size is always derived from OptionUtils — never stored from user input
        from Utils.OptionUtils import OptionUtils as _OU
        daily.lot_size = _OU.get_lot_size(daily.derivative, fallback=self.config['trading'].get('lot_size', 0))
        daily.exchange = self.config['trading']['exchange']
        daily.week = self.config['trading']['week']
        daily.history_interval = self.config['trading']['history_interval']
        daily.call_lookback = self.config['trading']['call_lookback']
        daily.put_lookback = self.config['trading']['put_lookback']
        daily.sideway_zone_trade = self.config['trading']['sideway_zone_trade']
        daily.capital_reserve = self.config['risk']['capital_reserve']
        daily.max_num_of_option = self.config['risk']['max_options']
        daily.save()
        logger.info(f"[OnboardingWizard._save_daily_trade_settings] Daily trade settings saved for {daily.derivative}")

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
        logger.info(
            f"[OnboardingWizard._save_profit_stoploss_settings] Profit/Stoploss settings saved: TP={pnl.tp_percentage}%, SL={pnl.stoploss_percentage}%")

    def _mark_completed(self):
        """Mark onboarding as completed by setting a flag in the database."""
        try:
            db = get_db()
            kv.set(ONBOARDING_COMPLETED_KEY, {
                'completed': True,
                'timestamp': datetime.now().isoformat(),
                'version': '2.0.0',
                'disclaimer_acknowledged': True
            }, db)
            logger.info("[OnboardingWizard._mark_completed] Onboarding marked as completed in database")
        except Exception as e:
            logger.error(f"[OnboardingWizard._mark_completed] Failed to mark onboarding completed: {e}")

    def closeEvent(self, event):
        """Handle close event - Rule 7"""
        try:
            self.cleanup()
            super().closeEvent(event)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[OnboardingWizard.closeEvent] RuntimeError: {e}", exc_info=True)
            event.accept()
        except Exception as e:
            logger.error(f"[OnboardingWizard.closeEvent] Failed: {e}", exc_info=True)
            event.accept()

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            # Prevent multiple cleanups
            if self._closing:
                return

            logger.info("[OnboardingWizard.cleanup] Starting cleanup")
            self._closing = True

            # Clean up pages
            for page in [self.disclaimer_page, self.welcome_page, self.broker_page,
                         self.preferences_page, self.risk_page, self.notification_page,
                         self.completion_page]:
                if page and safe_hasattr(page, 'cleanup'):
                    try:
                        page.cleanup()
                    except Exception as e:
                        logger.warning(f"[OnboardingWizard.cleanup] Error cleaning up page: {e}")

            # Disconnect signals
            try:
                theme_manager.theme_changed.disconnect(self.apply_theme)
                theme_manager.density_changed.disconnect(self.apply_theme)
            except (TypeError, RuntimeError):
                pass  # Already disconnected or not connected

            # Nullify references
            self.disclaimer_page = None
            self.welcome_page = None
            self.broker_page = None
            self.preferences_page = None
            self.risk_page = None
            self.notification_page = None
            self.completion_page = None
            self.config = {}

            logger.info("[OnboardingWizard.cleanup] Cleanup completed")

        except Exception as e:
            logger.error(f"[OnboardingWizard.cleanup] Error: {e}", exc_info=True)


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
            logger.info("[is_first_time] Onboarding flag found in database - not first time")
            return False

        # No flag found - first time setup
        logger.info("[is_first_time] No onboarding flag found - first time setup")
        return True

    except Exception as e:
        logger.error(f"[is_first_time] Error checking first-time status: {e}")
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
        logger.info("[mark_onboarding_completed] Manually marked onboarding as completed in database")
    except Exception as e:
        logger.error(f"[mark_onboarding_completed] Failed to mark onboarding completed: {e}")