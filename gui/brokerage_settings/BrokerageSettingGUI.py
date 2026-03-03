"""
gui/BrokerageSettingGUI.py
==========================
Brokerage settings dialog with broker selector and dynamic field hints.
PyQt5 version with proper database saving.
Matches the theme of DailyTradeSettingGUI.py
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

import logging
import webbrowser
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
                             QWidget, QLabel, QComboBox, QLineEdit,
                             QPushButton, QMessageBox, QGroupBox, QFormLayout,
                             QFrame, QScrollArea)

from broker.BrokerFactory import BrokerType, BrokerFactory
from gui.brokerage_settings.BrokerageSetting import BrokerageSetting

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)

# ── Per-broker field labels & hints ──────────────────────────────────────────
# These are text content, not colors - can remain as-is
BROKER_HINTS = {
    BrokerType.FYERS: {
        "client_id":    ("Client ID / App ID",     "e.g. XY12345-100"),
        "secret_key":   ("App Secret",             "From myapi.fyers.in"),
        "redirect_uri": ("Redirect URI",           "e.g. https://127.0.0.1/callback"),
        "redirect_note": "Redirect URI must match exactly what's registered on myapi.fyers.in",
        "help_url":     "https://myapi.fyers.in",
        "auth_note":    "OAuth browser login required daily. Click 'Open Login URL' after saving.",
        "redirect_disabled": False,
    },
    BrokerType.ZERODHA: {
        "client_id":    ("API Key",                "From developers.kite.trade"),
        "secret_key":   ("API Secret",             "From developers.kite.trade"),
        "redirect_uri": ("Redirect URL",           "e.g. https://127.0.0.1/callback"),
        "redirect_note": "Must match redirect URL registered in Kite developer console",
        "help_url":     "https://developers.kite.trade",
        "auth_note":    "OAuth browser login required daily. Token expires end-of-day.",
        "redirect_disabled": False,
    },
    BrokerType.DHAN: {
        "client_id":    ("Client ID",              "Your Dhan client ID"),
        "secret_key":   ("Access Token",           "Static token from dhanhq.co portal"),
        "redirect_uri": ("Not required",           "Leave blank for Dhan"),
        "redirect_note": "Dhan uses a static access token — no OAuth redirect needed.",
        "help_url":     "https://dhanhq.co/docs/v2",
        "auth_note":    "Static token. No daily login required — just update when token expires.",
        "redirect_disabled": True,
    },
    BrokerType.ANGELONE: {
        "client_id":    ("Client Code",            "Your Angel One login ID (e.g. A123456)"),
        "secret_key":   ("API Key",                "From SmartAPI developer portal"),
        "redirect_uri": ("TOTP Secret",            "Base32 TOTP secret from QR code scan"),
        "redirect_note": "TOTP secret from https://smartapi.angelbroking.com — scan QR with authenticator",
        "help_url":     "https://smartapi.angelbroking.com",
        "auth_note":    "TOTP-based. No browser needed. Call broker.login(password='MPIN') at startup.",
        "redirect_disabled": False,
    },
    BrokerType.UPSTOX: {
        "client_id":    ("API Key",                "From Upstox developer console"),
        "secret_key":   ("API Secret",             "From Upstox developer console"),
        "redirect_uri": ("Redirect URI",           "e.g. https://127.0.0.1/callback"),
        "redirect_note": "Must match redirect URI registered in Upstox developer console",
        "help_url":     "https://developer.upstox.com",
        "auth_note":    "OAuth browser login required daily. Token expires end-of-day.",
        "redirect_disabled": False,
    },
    BrokerType.SHOONYA: {
        "client_id":    ("User ID | Vendor Code",  "e.g. FA12345|FA12345_U  (pipe-separated)"),
        "secret_key":   ("Password",               "Your Shoonya login password (plain text)"),
        "redirect_uri": ("TOTP Secret",            "Base32 TOTP secret for auto-TOTP generation"),
        "redirect_note": "Store TOTP base32 secret here. Obtain from Shoonya app → TOTP setup.",
        "help_url":     "https://www.shoonya.com/api-documentation",
        "auth_note":    "TOTP-based login. Call broker.login() each morning before market open.",
        "redirect_disabled": False,
    },
    BrokerType.KOTAK: {
        "client_id":    ("Consumer Key",           "From Kotak Neo app → Trade API card"),
        "secret_key":   ("Consumer Secret",        "From Kotak Neo app → Trade API card"),
        "redirect_uri": ("TOTP Secret",            "Base32 TOTP secret for auto-TOTP"),
        "redirect_note": "TOTP secret from Kotak Securities TOTP registration page.",
        "help_url":     "https://github.com/Kotak-Neo/kotak-neo-api",
        "auth_note":    "TOTP + MPIN login. Call broker.login_totp(mobile, ucc, mpin) at startup.",
        "redirect_disabled": False,
    },
    BrokerType.ICICI: {
        "client_id":    ("API Key",                "From https://api.icicidirect.com"),
        "secret_key":   ("Secret Key",             "From https://api.icicidirect.com"),
        "redirect_uri": ("Not required",           "Leave blank for ICICI Breeze"),
        "redirect_note": "Visit get_login_url() each day to obtain a session token. Static IP required (SEBI mandate).",
        "help_url":     "https://api.icicidirect.com",
        "auth_note":    "Session-token auth. Visit login URL daily, paste token into broker.generate_session().",
        "redirect_disabled": True,
    },
    BrokerType.ALICEBLUE: {
        "client_id":    ("App ID",                 "From Alice Blue developer console"),
        "secret_key":   ("API Secret",             "From Alice Blue developer console"),
        "redirect_uri": ("username|password|YOB",  "e.g. AB12345|mypassword|1990"),
        "redirect_note": "Store as pipe-separated: username|password|YearOfBirth. YOB used as 2FA answer.",
        "help_url":     "https://ant.aliceblueonline.com/developers",
        "auth_note":    "Fully automated login. Call broker.login() at startup each day.",
        "redirect_disabled": False,
    },
    BrokerType.FLATTRADE: {
        "client_id":    ("User ID | API Key",      "e.g. FL12345|myapikey  (pipe-separated)"),
        "secret_key":   ("API Secret",             "From Flattrade Pi → Create New API Key"),
        "redirect_uri": ("Redirect URI",           "e.g. https://127.0.0.1/callback"),
        "redirect_note": "Must match redirect URI registered in Flattrade Pi API settings.",
        "help_url":     "https://pi.flattrade.in/docs",
        "auth_note":    "OAuth token from browser. Call broker.set_session(token=...) after redirect. Zero brokerage!",
        "redirect_disabled": False,
    },
}

# Ordered list for display in dropdown
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

BROKER_DISPLAY_OPTIONS = [
    (bt, BrokerType.DISPLAY_NAMES[bt]) for bt in BROKER_ORDER
]


class ThemedMixin:
    """Mixin class to provide theme token shortcuts."""

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing


class BrokerageSettingDialog(QDialog, ThemedMixin):
    """
    Settings dialog with two tabs:
        🏦 Broker   — broker selection + credentials
        📱 Telegram — Telegram bot credentials

    Matches the theme of DailyTradeSettingGUI.py
    FULLY INTEGRATED with ThemeManager.
    """

    # Signal emitted when settings are saved
    settings_saved = pyqtSignal(object)

    # Rule 3: Additional signals for error handling
    error_occurred = pyqtSignal(str)
    operation_started = pyqtSignal()
    operation_finished = pyqtSignal()

    def __init__(self, broker_setting: BrokerageSetting, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.broker_setting = broker_setting
            self._save_in_progress = False
            self._help_url = ""

            self.setWindowTitle("⚙️ Brokerage Settings")
            self.setModal(True)
            self.setMinimumSize(700, 650)
            self.resize(700, 650)

            # ── Variables from settings ────────────────────────────────────────
            self.broker_type = broker_setting.broker_type or 'fyers'
            self.client_id = broker_setting.client_id or ''
            self.secret_key = broker_setting.secret_key or ''
            self.redirect_uri = broker_setting.redirect_uri or ''
            self.tg_token = broker_setting.telegram_bot_token or ''
            self.tg_chat = broker_setting.telegram_chat_id or ''

            # Root layout
            root = QVBoxLayout(self)
            # Margins and spacing will be set in apply_theme

            # Header
            header = QLabel("⚙️ Brokerage Settings")
            header.setObjectName("header")
            header.setAlignment(Qt.AlignCenter)
            root.addWidget(header)

            # ── Tab Widget ─────────────────────────────────────────────────────
            self.tabs = QTabWidget()
            root.addWidget(self.tabs)

            # Tab 1 — Broker
            self.broker_tab = QWidget()
            self.tabs.addTab(self.broker_tab, "🏦  Broker")
            self._setup_broker_tab()

            # Tab 2 — Telegram
            self.telegram_tab = QWidget()
            self.tabs.addTab(self.telegram_tab, "📱  Telegram")
            self._setup_telegram_tab()

            # Tab 3 — Information (like DailyTradeSettingGUI)
            self.info_tab = QWidget()
            self.tabs.addTab(self.info_tab, "ℹ️ Information")
            self._setup_info_tab()

            # ── Status label ─────────────────────────────────────────────────────
            self.status_label = QLabel("")
            self.status_label.setAlignment(Qt.AlignCenter)
            self.status_label.setObjectName("status")
            root.addWidget(self.status_label)

            # ── Button row ───────────────────────────────────────────────────────
            button_layout = QHBoxLayout()
            root.addLayout(button_layout)

            # Left side buttons
            self.login_url_btn = QPushButton("🌐  Open Login URL")
            self.login_url_btn.clicked.connect(self._open_login_url)
            button_layout.addWidget(self.login_url_btn)

            self.test_btn = QPushButton("🔌  Test Connection")
            self.test_btn.clicked.connect(self._test_connection)
            button_layout.addWidget(self.test_btn)

            button_layout.addStretch()

            # Right side buttons
            self.save_btn = QPushButton("💾  Save All Settings")
            self.save_btn.clicked.connect(self._save)
            self.save_btn.setDefault(True)
            button_layout.addWidget(self.save_btn)

            self.cancel_btn = QPushButton("Cancel")
            self.cancel_btn.clicked.connect(self.reject)
            button_layout.addWidget(self.cancel_btn)

            # Connect internal signals
            self._connect_signals()

            # Apply theme initially
            self.apply_theme()

            # Initial update
            self._update_hints()
            self._update_token_status()

            logger.info("BrokerageSettingGUI initialized")

        except Exception as e:
            logger.critical(f"[BrokerageSettingGUI.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.broker_setting = None
        self.tabs = None
        self.broker_tab = None
        self.telegram_tab = None
        self.info_tab = None
        self.broker_combo = None
        self.client_id_entry = None
        self.secret_key_entry = None
        self.redirect_entry = None
        self.tg_token_entry = None
        self.tg_chat_entry = None
        self.client_id_label = None
        self.secret_key_label = None
        self.redirect_label = None
        self.auth_note_label = None
        self.redirect_note_label = None
        self.history_label = None
        self.token_status_label = None
        self.help_label = None
        self.login_url_btn = None
        self.test_btn = None
        self.save_btn = None
        self.cancel_btn = None
        self.status_label = None
        self._help_url = ""
        self._save_in_progress = False

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the dialog.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Update root layout margins and spacing
            layout = self.layout()
            if layout:
                layout.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
                layout.setSpacing(sp.GAP_MD)

            # Apply main stylesheet
            self.setStyleSheet(self._get_stylesheet())

            # Update header
            header = self.findChild(QLabel, "header")
            if header:
                header.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_XL}pt; font-weight: {ty.WEIGHT_BOLD}; padding: {sp.PAD_XS}px;")

            # Update status label
            if self.status_label:
                self.status_label.setStyleSheet(f"color: {c.GREEN}; font-size: {ty.SIZE_XS}pt; font-weight: {ty.WEIGHT_BOLD};")

            # Update button styles
            self._update_button_styles()

            # Update tab-specific elements
            self._update_tab_styles()

            logger.debug("[BrokerageSettingDialog.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[BrokerageSettingDialog.apply_theme] Failed: {e}", exc_info=True)

    def _get_stylesheet(self) -> str:
        """Generate stylesheet with current theme tokens"""
        c = self._c
        ty = self._ty
        sp = self._sp

        return f"""
            QDialog {{ background: {c.BG_PANEL}; color: {c.TEXT_MAIN}; }}
            QLabel  {{ color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt; }}
            QGroupBox {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                margin-top: {sp.PAD_MD}px;
                font-weight: {ty.WEIGHT_BOLD};
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_BODY}pt;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {sp.PAD_MD}px;
                padding: 0 {sp.PAD_XS}px 0 {sp.PAD_XS}px;
            }}
            QTabWidget::pane {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                background: {c.BG_PANEL};
            }}
            QTabBar::tab {{
                background: {c.BG_HOVER};
                color: {c.TEXT_DIM};
                padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                min-width: 130px;
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-bottom: none;
                border-radius: {sp.RADIUS_SM}px {sp.RADIUS_SM}px 0 0;
                font-size: {ty.SIZE_BODY}pt;
            }}
            QTabBar::tab:selected {{
                background: {c.BG_PANEL};
                color: {c.TEXT_MAIN};
                border-bottom: {sp.PAD_XS}px solid {c.BLUE};
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QTabBar::tab:hover:!selected {{ background: {c.BORDER}; color: {c.TEXT_MAIN}; }}
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
                padding: {sp.PAD_SM}px;
                font-size: {ty.SIZE_BODY}pt;
                min-height: {sp.BTN_HEIGHT_SM}px;
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                background: {c.BORDER};
                border: none;
                width: {sp.ICON_SM}px;
            }}
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
                image: none;
                border-left: {sp.PAD_XS}px solid transparent;
                border-right: {sp.PAD_XS}px solid transparent;
                border-bottom: {sp.PAD_XS}px solid {c.TEXT_DIM};
            }}
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
                image: none;
                border-left: {sp.PAD_XS}px solid transparent;
                border-right: {sp.PAD_XS}px solid transparent;
                border-top: {sp.PAD_XS}px solid {c.TEXT_DIM};
            }}
            QCheckBox {{ color: {c.TEXT_MAIN}; spacing: {sp.GAP_SM}px; font-size: {ty.SIZE_BODY}pt; }}
            QCheckBox::indicator {{ width: {sp.ICON_MD}px; height: {sp.ICON_MD}px; }}
            QCheckBox::indicator:unchecked {{ border: {sp.SEPARATOR}px solid {c.BORDER}; background: {c.BG_HOVER}; border-radius: {sp.RADIUS_SM}px; }}
            QCheckBox::indicator:checked   {{ background: {c.GREEN}; border: {sp.SEPARATOR}px solid {c.GREEN_BRIGHT}; border-radius: {sp.RADIUS_SM}px; }}
            QScrollArea {{ border: none; background: transparent; }}
            QFrame#infoCard {{
                background: {c.BG_HOVER};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
            }}
        """

    def _update_button_styles(self):
        """Update button styles with theme tokens"""
        c = self._c
        sp = self._sp
        ty = self._ty

        # Save button
        if self.save_btn:
            self.save_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c.GREEN};
                    color: {c.TEXT_INVERSE};
                    border-radius: {sp.RADIUS_SM}px;
                    padding: {sp.PAD_SM}px;
                    font-weight: {ty.WEIGHT_BOLD};
                    font-size: {ty.SIZE_BODY}pt;
                }}
                QPushButton:hover {{ background: {c.GREEN_BRIGHT}; }}
                QPushButton:pressed {{ background: {c.GREEN}; }}
                QPushButton:disabled {{ background: {c.BG_HOVER}; color: {c.TEXT_DISABLED}; }}
            """)

        # Cancel button
        if self.cancel_btn:
            self.cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c.BG_HOVER};
                    color: {c.TEXT_MAIN};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                    padding: {sp.PAD_SM}px;
                    font-weight: {ty.WEIGHT_BOLD};
                    font-size: {ty.SIZE_BODY}pt;
                }}
                QPushButton:hover {{ background: {c.BORDER}; }}
            """)

        # Login URL button and Test button
        for btn in [self.login_url_btn, self.test_btn]:
            if btn:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {c.BG_HOVER};
                        color: {c.TEXT_MAIN};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_SM}px;
                        padding: {sp.PAD_SM}px;
                        font-size: {ty.SIZE_BODY}pt;
                    }}
                    QPushButton:hover {{ background: {c.BORDER}; }}
                    QPushButton:disabled {{ background: {c.BG_PANEL}; color: {c.TEXT_DISABLED}; }}
                """)

    def _update_tab_styles(self):
        """Update tab-specific element styles"""
        c = self._c
        sp = self._sp
        ty = self._ty

        # Auth note label
        if self.auth_note_label:
            self.auth_note_label.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; padding: {sp.PAD_XS}px;")

        # Redirect note label
        if self.redirect_note_label:
            self.redirect_note_label.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; padding-left: {sp.PAD_XS}px;")

        # Token status label
        if self.token_status_label:
            self.token_status_label.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt;")

        # Help label
        if self.help_label:
            self.help_label.setStyleSheet(f"color: {c.BLUE}; font-size: {ty.SIZE_XS}pt;")

        # History label
        if self.history_label:
            self._update_history_label()

        # Test Telegram button (in Telegram tab)
        test_tg_btn = self.findChild(QPushButton, "testTelegramBtn")
        if test_tg_btn:
            test_tg_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c.BLUE_DARK};
                    color: {c.TEXT_INVERSE};
                    border-radius: {sp.RADIUS_SM}px;
                    padding: {sp.PAD_SM}px;
                    font-weight: {ty.WEIGHT_BOLD};
                    font-size: {ty.SIZE_BODY}pt;
                }}
                QPushButton:hover {{ background: {c.BLUE}; }}
            """)

    def _update_history_label(self):
        """Update history label based on current broker"""
        try:
            c = self._c
            ty = self._ty

            bt_str = self.broker_type
            bt = next((b for b in BROKER_ORDER if str(b) == bt_str), BrokerType.FYERS)

            if BrokerFactory.supports_history(bt):
                self.history_label.setText("✅  Historical OHLC data supported")
                self.history_label.setStyleSheet(f"color: {c.GREEN}; font-size: {ty.SIZE_XS}pt;")
            else:
                self.history_label.setText("⚠️  Historical data NOT available — use external data source")
                self.history_label.setStyleSheet(f"color: {c.RED}; font-size: {ty.SIZE_XS}pt;")
        except Exception as e:
            logger.error(f"Failed to update history label: {e}")

    def _connect_signals(self):
        """Connect internal signals"""
        try:
            self.error_occurred.connect(self._on_error)
            self.operation_started.connect(self._on_operation_started)
            self.operation_finished.connect(self._on_operation_finished)
        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._connect_signals] Failed: {e}", exc_info=True)

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        c = self._c
        ty = self._ty
        sp = self._sp

        try:
            super().__init__(parent)
            self.setWindowTitle("Brokerage Settings - ERROR")
            self.setMinimumSize(400, 200)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)

            error_label = QLabel("❌ Failed to initialize settings dialog.\nPlease check the logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet(f"color: {c.RED_BRIGHT}; padding: {sp.PAD_XL}px; font-size: {ty.SIZE_MD}pt;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._create_error_dialog] Failed: {e}", exc_info=True)

    def _setup_broker_tab(self):
        """Setup the broker configuration tab with scroll area like DailyTradeSettingGUI."""
        sp = self._sp

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        container.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_MD)
        layout.setSpacing(sp.GAP_MD)

        # ── Broker selector ───────────────────────────────────────────────────
        broker_group = QGroupBox("Select Broker")
        broker_layout = QVBoxLayout(broker_group)
        broker_layout.setSpacing(sp.GAP_SM)

        self.broker_combo = QComboBox()
        for bt, name in BROKER_DISPLAY_OPTIONS:
            # Store the str value (e.g. "fyers") as item data so findData() works
            # regardless of whether BrokerType subclasses str or not.
            self.broker_combo.addItem(f"{name}  ({bt})", str(bt))

        # Set current selection
        index = self.broker_combo.findData(self.broker_type)
        if index >= 0:
            self.broker_combo.setCurrentIndex(index)

        self.broker_combo.currentIndexChanged.connect(self._on_broker_changed)
        broker_layout.addWidget(self.broker_combo)

        layout.addWidget(broker_group)

        # ── Auth note banner ──────────────────────────────────────────────────
        self.auth_note_label = QLabel()
        self.auth_note_label.setWordWrap(True)
        layout.addWidget(self.auth_note_label)

        # ── Credential fields ─────────────────────────────────────────────────
        cred_group = QGroupBox("Credentials")
        form_layout = QFormLayout(cred_group)
        form_layout.setSpacing(sp.GAP_SM)
        form_layout.setVerticalSpacing(sp.GAP_XS)
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # Client ID
        self.client_id_label = QLabel("Client ID:")
        self.client_id_entry = QLineEdit()
        self.client_id_entry.setText(self.client_id)
        self.client_id_entry.setPlaceholderText("Enter client ID / API key")
        self.client_id_entry.textChanged.connect(self._clear_field_error)
        form_layout.addRow(self.client_id_label, self.client_id_entry)

        # Secret Key
        self.secret_key_label = QLabel("Secret Key:")
        self.secret_key_entry = QLineEdit()
        self.secret_key_entry.setEchoMode(QLineEdit.Password)
        self.secret_key_entry.setText(self.secret_key)
        self.secret_key_entry.setPlaceholderText("Enter secret key")
        self.secret_key_entry.textChanged.connect(self._clear_field_error)
        form_layout.addRow(self.secret_key_label, self.secret_key_entry)

        # Redirect URI
        self.redirect_label = QLabel("Redirect URI:")
        self.redirect_entry = QLineEdit()
        self.redirect_entry.setText(self.redirect_uri)
        self.redirect_entry.setPlaceholderText("Enter redirect URI")
        self.redirect_entry.textChanged.connect(self._clear_field_error)
        form_layout.addRow(self.redirect_label, self.redirect_entry)

        layout.addWidget(cred_group)

        # ── Redirect note ─────────────────────────────────────────────────────
        self.redirect_note_label = QLabel()
        self.redirect_note_label.setWordWrap(True)
        layout.addWidget(self.redirect_note_label)

        # ── Token status ─────────────────────────────────────────────────────
        token_frame = QFrame()
        token_frame.setObjectName("infoCard")
        token_layout = QHBoxLayout(token_frame)
        token_layout.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)

        token_icon = QLabel("🔑")
        token_icon.setFont(QFont(self._ty.FONT_UI, self._ty.SIZE_MD))
        token_layout.addWidget(token_icon)

        self.token_status_label = QLabel()
        self.token_status_label.setWordWrap(True)
        token_layout.addWidget(self.token_status_label, 1)

        layout.addWidget(token_frame)

        # ── Help link ─────────────────────────────────────────────────────────
        help_layout = QHBoxLayout()
        help_layout.setContentsMargins(sp.PAD_XS, sp.PAD_SM, sp.PAD_XS, sp.PAD_XS)
        self.help_label = QLabel("📖  API Documentation")
        self.help_label.setCursor(Qt.PointingHandCursor)
        help_font = QFont()
        help_font.setUnderline(True)
        self.help_label.setFont(help_font)
        self.help_label.mousePressEvent = self._open_help_url
        help_layout.addWidget(self.help_label)
        help_layout.addStretch()
        layout.addLayout(help_layout)

        # ── History support indicator ─────────────────────────────────────────
        self.history_label = QLabel()
        self.history_label.setWordWrap(True)
        layout.addWidget(self.history_label)

        layout.addStretch()
        scroll.setWidget(container)

        # Add scroll to tab layout
        tab_layout = QVBoxLayout(self.broker_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

    def _setup_telegram_tab(self):
        """Setup the Telegram configuration tab with scroll area."""
        sp = self._sp

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        container.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)
        layout.setSpacing(sp.GAP_LG)

        # ── Telegram settings ─────────────────────────────────────────────────
        tg_group = QGroupBox("Telegram Notifications")
        form_layout = QFormLayout(tg_group)
        form_layout.setSpacing(sp.GAP_SM)
        form_layout.setLabelAlignment(Qt.AlignRight)

        # Bot Token
        self.tg_token_entry = QLineEdit()
        self.tg_token_entry.setText(self.tg_token)
        self.tg_token_entry.setEchoMode(QLineEdit.Password)
        self.tg_token_entry.setPlaceholderText("Enter your bot token")
        form_layout.addRow("Bot Token:", self.tg_token_entry)

        token_hint = QLabel("From @BotFather on Telegram")
        token_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
        form_layout.addRow("", token_hint)

        # Chat ID
        self.tg_chat_entry = QLineEdit()
        self.tg_chat_entry.setText(self.tg_chat)
        self.tg_chat_entry.setPlaceholderText("Enter your chat ID")
        form_layout.addRow("Chat ID:", self.tg_chat_entry)

        chat_hint = QLabel("Get by messaging @userinfobot")
        chat_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
        form_layout.addRow("", chat_hint)

        layout.addWidget(tg_group)

        # Test Telegram button
        test_tg_btn = QPushButton("📱  Test Telegram")
        test_tg_btn.setObjectName("testTelegramBtn")
        test_tg_btn.clicked.connect(self._test_telegram)
        layout.addWidget(test_tg_btn)

        # ── Info Card ─────────────────────────────────────────────────────────
        info_card = QFrame()
        info_card.setObjectName("infoCard")
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)

        info_title = QLabel("📘 About Telegram Integration:")
        info_title.setFont(QFont(self._ty.FONT_UI, self._ty.SIZE_BODY, QFont.Bold))
        info_title.setStyleSheet(f"color: {self._c.TEXT_MAIN};")

        info_text = QLabel(
            "• **Bot Token**: Get from @BotFather on Telegram\n"
            "• **Chat ID**: Your personal chat ID for notifications\n"
            "• **Notifications**: Trade alerts, errors, and status updates\n\n"
            "Leave blank to disable Telegram notifications."
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")

        info_layout.addWidget(info_title)
        info_layout.addWidget(info_text)
        layout.addWidget(info_card)

        layout.addStretch()
        scroll.setWidget(container)

        # Add scroll to tab layout
        tab_layout = QVBoxLayout(self.telegram_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

    def _setup_info_tab(self):
        """Setup information tab with help content (like DailyTradeSettingGUI)."""
        sp = self._sp
        c = self._c
        ty = self._ty

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)
        layout.setSpacing(sp.GAP_MD)

        infos = [
            (
                "🏦  Broker Selection",
                "Choose your brokerage from the dropdown. Each broker has specific credential requirements:\n\n"
                "• **Fyers/Zerodha/Upstox**: OAuth based - requires redirect URI\n"
                "• **Dhan/ICICI**: Static token based - no redirect needed\n"
                "• **AngelOne/Shoonya/Kotak**: TOTP based - requires TOTP secret\n"
                "• **AliceBlue/Flattrade**: Combined credentials format"
            ),
            (
                "🔑  Credentials",
                "• **Client ID**: Your unique identifier for the broker API\n"
                "• **Secret Key**: Secret/API key from broker developer portal\n"
                "• **Redirect URI**: Callback URL (for OAuth brokers)\n\n"
                "All credentials are stored encrypted in the local database."
            ),
            (
                "📊  Historical Data Support",
                "Brokers marked with ✅ support historical OHLC data fetching.\n"
                "Brokers marked with ⚠️ require external data source for backtesting."
            ),
            (
                "🔐  Token Management",
                "• OAuth tokens typically expire end-of-day\n"
                "• Static tokens last longer but need manual refresh\n"
                "• TOTP secrets generate one-time passwords automatically\n\n"
                "Use 'Open Login URL' button for OAuth brokers to generate new tokens."
            ),
            (
                "📱  Telegram Notifications",
                "Configure Telegram to receive:\n"
                "• Trade entry/exit alerts\n"
                "• Error notifications\n"
                "• Daily P&L summaries\n"
                "• Connection status updates"
            ),
        ]

        for title, body in infos:
            try:
                card = QFrame()
                card.setObjectName("infoCard")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
                card_layout.setSpacing(sp.GAP_XS)

                title_lbl = QLabel(title)
                title_lbl.setFont(QFont(ty.FONT_UI, ty.SIZE_BODY, QFont.Bold))
                title_lbl.setStyleSheet(f"color: {c.TEXT_MAIN};")

                body_lbl = QLabel(body)
                body_lbl.setWordWrap(True)
                body_lbl.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt;")

                card_layout.addWidget(title_lbl)
                card_layout.addWidget(body_lbl)
                layout.addWidget(card)

            except Exception as e:
                logger.error(f"Failed to create info card for {title}: {e}", exc_info=True)

        layout.addStretch()
        scroll.setWidget(container)

        # Add scroll to tab layout
        tab_layout = QVBoxLayout(self.info_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

    def _update_token_status(self):
        """Update token status display with styled card."""
        try:
            c = self._c
            if self.broker_setting.has_valid_token:
                expiry = self.broker_setting.token_expiry
                if expiry:
                    self.token_status_label.setText(
                        f"✅ **Valid Token**\nExpires: {expiry}"
                    )
                else:
                    self.token_status_label.setText(
                        "✅ **Valid Token**\nNo expiry information"
                    )
            else:
                self.token_status_label.setText(
                    "❌ **No Valid Token**\nPlease complete login to start trading"
                )
        except Exception as e:
            logger.error(f"Error updating token status: {e}")
            self.token_status_label.setText("⚠️ **Unknown Token Status**")

    def _clear_field_error(self):
        """Clear error styling when user starts typing."""
        sender = self.sender()
        if sender:
            sender.setStyleSheet("")  # Will be reset by theme on next apply_theme

    def _on_broker_changed(self, index: int):
        """Handle broker selection change."""
        if index >= 0:
            # currentData() is str because we store str(bt) in addItem(); keep consistent.
            self.broker_type = str(self.broker_combo.currentData())
            self._update_hints()

    def _update_hints(self):
        """Update UI hints based on selected broker."""
        bt_str = self.broker_type  # str, e.g. "fyers"
        # BROKER_HINTS is keyed by BrokerType enum, so resolve the enum from the str value
        bt = next((b for b in BROKER_ORDER if str(b) == bt_str), BrokerType.FYERS)
        hints = BROKER_HINTS.get(bt, BROKER_HINTS[BrokerType.FYERS])

        c = self._c
        ty = self._ty

        # Update labels
        self.client_id_label.setText(hints["client_id"][0] + ":")
        self.client_id_entry.setPlaceholderText(hints["client_id"][1])

        self.secret_key_label.setText(hints["secret_key"][0] + ":")
        self.secret_key_entry.setPlaceholderText(hints["secret_key"][1])

        self.redirect_label.setText(hints["redirect_uri"][0] + ":")
        self.redirect_entry.setPlaceholderText(hints["redirect_uri"][1])

        # Enable/disable redirect field
        if hints.get("redirect_disabled"):
            self.redirect_entry.setEnabled(False)
            self.redirect_entry.clear()
        else:
            self.redirect_entry.setEnabled(True)

        # Update notes
        self.redirect_note_label.setText(f"ℹ️ {hints.get('redirect_note', '')}")
        self.redirect_note_label.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; padding-left: {self._sp.PAD_XS}px;")

        self.auth_note_label.setText(f"ℹ️ {hints.get('auth_note', '')}")
        self.auth_note_label.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; padding: {self._sp.PAD_XS}px;")

        self._help_url = hints.get("help_url", "")

        # History support
        self._update_history_label()

        # Show/hide login URL button based on auth method
        auth = BrokerType.AUTH_METHOD.get(bt, "oauth")
        self.login_url_btn.setEnabled(auth in ("oauth", "session"))

    def _open_help_url(self, event):
        """Open the help URL in web browser."""
        if self._help_url:
            webbrowser.open(self._help_url)

    def _open_login_url(self):
        """Attempt to construct and open the broker login URL."""
        bt_str = self.broker_type
        bt = next((b for b in BROKER_ORDER if str(b) == bt_str), None)
        api_key = self.client_id_entry.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Missing", "Please enter Client ID / API Key first.")
            return

        urls = {
            BrokerType.FYERS:     f"https://api-t1.fyers.in/api/v3/generate-authcode?client_id={api_key}&redirect_uri={self.redirect_entry.text()}&response_type=code&state=algotrade",
            BrokerType.ZERODHA:   f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}",
            BrokerType.UPSTOX:    f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={api_key}&redirect_uri={self.redirect_entry.text()}",
            BrokerType.ICICI:     f"https://api.icicidirect.com/apiuser/login?api_key={api_key}",
            BrokerType.FLATTRADE: f"https://auth.flattrade.in/?api_key={api_key.split('|')[-1] if '|' in api_key else api_key}",
        }

        url = urls.get(bt)
        if url:
            webbrowser.open(url)
            QMessageBox.information(
                self, "Login URL Opened",
                "Please complete the login in your browser.\n\n"
                "After successful login, you'll be redirected with a code.\n"
                "Some brokers require you to paste this code back into the app."
            )
        else:
            QMessageBox.information(
                self, "Info",
                f"No browser login URL for {BrokerType.DISPLAY_NAMES.get(bt, bt)}.\n"
                f"Use the broker's native authentication method."
            )

    def _test_connection(self):
        """Test the broker connection with current settings."""
        try:
            # Validate required fields first
            if not self.client_id_entry.text().strip():
                QMessageBox.warning(self, "Missing", "Please enter Client ID / API Key first.")
                return

            # In a real implementation, this would test the connection
            QMessageBox.information(
                self, "Test Connection",
                "Connection test initiated.\n\n"
                "This would verify:\n"
                "• API credentials are valid\n"
                "• Network connectivity to broker\n"
                "• Token validity (if exists)"
            )
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            QMessageBox.critical(self, "Connection Failed", str(e))

    def _test_telegram(self):
        """Test Telegram notification with current settings."""
        try:
            token = self.tg_token_entry.text().strip()
            chat_id = self.tg_chat_entry.text().strip()

            if not token or not chat_id:
                QMessageBox.warning(
                    self, "Missing",
                    "Please enter both Bot Token and Chat ID."
                )
                return

            # In a real implementation, this would send a test message
            QMessageBox.information(
                self, "Test Telegram",
                "Telegram test initiated.\n\n"
                "This would send a test message to your Telegram bot."
            )
        except Exception as e:
            logger.error(f"Telegram test failed: {e}")
            QMessageBox.critical(self, "Telegram Test Failed", str(e))

    def _save(self):
        """Save the settings with validation and feedback."""
        if self._save_in_progress:
            return

        try:
            bt = self.broker_type  # always str (e.g. "fyers")
            if not bt:
                QMessageBox.critical(self, "Error", "Please select a broker.")
                return

            client_id = self.client_id_entry.text().strip()
            secret_key = self.secret_key_entry.text().strip()

            if not client_id:
                self.client_id_entry.setStyleSheet(
                    f"QLineEdit {{ border: {self._sp.SEPARATOR}px solid {self._c.RED}; }}"
                )
                QMessageBox.critical(self, "Error", "Client ID / API Key cannot be empty.")
                return

            self._save_in_progress = True
            self.operation_started.emit()

            self.save_btn.setEnabled(False)
            self.save_btn.setText("⏳ Saving...")
            self.status_label.setText("")

            # Update settings object
            self.broker_setting.broker_type = bt
            self.broker_setting.client_id = client_id
            self.broker_setting.secret_key = secret_key
            self.broker_setting.redirect_uri = self.redirect_entry.text().strip()
            self.broker_setting.telegram_bot_token = self.tg_token_entry.text().strip()
            self.broker_setting.telegram_chat_id = self.tg_chat_entry.text().strip()

            # Save to database
            success = self.broker_setting.save()

            if success:
                logger.info(f"Brokerage settings saved for {bt}")
                self.status_label.setText("✓ Settings saved successfully!")
                self.status_label.setStyleSheet(f"color: {self._c.GREEN}; font-size: {self._ty.SIZE_XS}pt; font-weight: {self._ty.WEIGHT_BOLD};")
                self.save_btn.setText("✓ Saved!")
                self.save_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {self._c.GREEN_BRIGHT};
                        color: {self._c.TEXT_INVERSE};
                        border-radius: {self._sp.RADIUS_SM}px;
                        padding: {self._sp.PAD_SM}px;
                        font-weight: {self._ty.WEIGHT_BOLD};
                        font-size: {self._ty.SIZE_BODY}pt;
                    }}
                """)

                # Update token status
                self.broker_setting.reload_token()
                self._update_token_status()

                # Emit signal
                self.settings_saved.emit(self.broker_setting)
                self.operation_finished.emit()

                # Reset flag before auto-close so the guard doesn't stick
                self._save_in_progress = False

                # Auto-close after success
                QTimer.singleShot(1500, self.accept)
            else:
                raise Exception("Failed to save to database")

        except Exception as e:
            logger.error(f"Failed to save settings: {e}", exc_info=True)
            self.status_label.setText(f"✗ Save failed: {str(e)}")
            self.status_label.setStyleSheet(f"color: {self._c.RED}; font-size: {self._ty.SIZE_XS}pt; font-weight: {self._ty.WEIGHT_BOLD};")
            self.save_btn.setEnabled(True)
            self.save_btn.setText("💾  Save All Settings")
            self.save_btn.setStyleSheet("")  # Reset to theme default
            self._save_in_progress = False
            self.operation_finished.emit()
            QMessageBox.critical(self, "Save Error", f"Could not save settings:\n{e}")

    def _on_error(self, error_msg: str):
        """Handle error signal."""
        try:
            logger.error(f"Error signal received: {error_msg}")
            self.status_label.setText(f"✗ {error_msg}")
            self.status_label.setStyleSheet(f"color: {self._c.RED}; font-size: {self._ty.SIZE_XS}pt; font-weight: {self._ty.WEIGHT_BOLD};")
            self.save_btn.setEnabled(True)
            self._save_in_progress = False
        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._on_error] Failed: {e}", exc_info=True)

    def _on_operation_started(self):
        """Handle operation started signal."""
        pass

    def _on_operation_finished(self):
        """Handle operation finished signal."""
        pass

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing."""
        try:
            logger.info("[BrokerageSettingGUI] Starting cleanup")

            # Clear references
            self.broker_setting = None
            self.tabs = None
            self.broker_combo = None
            self.client_id_entry = None
            self.secret_key_entry = None
            self.redirect_entry = None
            self.tg_token_entry = None
            self.tg_chat_entry = None

            logger.info("[BrokerageSettingGUI] Cleanup completed")

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup."""
        try:
            if self._save_in_progress:
                logger.warning("Closing while save in progress")

            self.cleanup()
            event.accept()

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI.closeEvent] Failed: {e}", exc_info=True)
            event.accept()