"""
Utils/BrokerLoginPopup.py
=========================
Generic multi-broker PyQt5 login dialog.

Replaces FyersManualLoginPopup with a broker-agnostic design.
The popup adapts its UI to the active broker's auth method via BrokerLoginHelper.

Auth method variants handled:
    oauth    — URL display + auth-code/URL paste  (Fyers, Zerodha, Upstox, FlatTrade)
    session  — URL display + plain session token  (ICICI Breeze)
    totp     — No URL; TOTP entry + optional MPIN (Angel One, Shoonya, Kotak)
    static   — No URL; plain token paste          (Dhan)
    password — No URL; no entry; auto-login btn   (Alice Blue)

Usage:
    from Utils.BrokerLoginPopup import BrokerLoginPopup

    popup = BrokerLoginPopup(
        parent=main_window,
        brokerage_setting=settings,   # has .broker_type, .client_id, .secret_key, .redirect_uri
        reason="Session expired",     # optional — shows warning banner
        notifier=telegram_notifier,   # optional
    )
    if popup.exec_() == QDialog.Accepted:
        token = popup.result_token    # the obtained access token
"""

import logging
from typing import Optional
from urllib.parse import urlparse, parse_qs
import re
import webbrowser
from datetime import datetime, timedelta

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QLineEdit,
    QPushButton, QProgressBar, QApplication, QWidget, QTabWidget,
    QFrame, QScrollArea, QCheckBox, QGroupBox, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont

from Utils.BrokerLoginHelper import BrokerLoginHelper

logger = logging.getLogger(__name__)


# ── Worker thread ─────────────────────────────────────────────────────────────

class TokenExchangeWorker(QThread):
    finished = pyqtSignal(object, str)  # (token | None, error_msg)
    progress = pyqtSignal(int, str)  # (percent, status_text)
    error_occurred = pyqtSignal(str)

    def __init__(self, helper: BrokerLoginHelper, code: str, extra: dict = None):
        self._safe_defaults_init()
        try:
            super().__init__()
            self.helper = helper
            self.code = code
            self.extra = extra or {}
        except Exception as e:
            logger.error(f"[TokenExchangeWorker.__init__] {e}", exc_info=True)
            super().__init__()
            self.helper = helper
            self.code = code
            self.extra = extra or {}

    def _safe_defaults_init(self):
        self.helper = None
        self.code = None
        self.extra = {}
        self._is_stopping = False

    def run(self):
        try:
            if not self.helper:
                self.finished.emit(None, "Login helper is not initialized")
                return
            self.progress.emit(30, "Authenticating…")
            token = self.helper.exchange_code_for_token(self.code or "", **self.extra)
            self.progress.emit(100, "Done")
            if token:
                self.finished.emit(token, "")
            else:
                self.finished.emit(None, "Authentication failed — please check your credentials and try again.")
        except Exception as e:
            logger.error(f"[TokenExchangeWorker.run] {e}", exc_info=True)
            self.finished.emit(None, str(e))

    def stop(self):
        self._is_stopping = True


# ── Main popup ────────────────────────────────────────────────────────────────

_STYLESHEET = """
    QDialog { background:#161b22; color:#e6edf3; font-family:'Segoe UI', sans-serif; }
    QLabel  { color:#8b949e; font-size:10pt; }
    QGroupBox {
        border: 1px solid #30363d; border-radius: 6px;
        margin-top: 10px; font-weight: bold; color: #e6edf3;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
    QTabWidget::pane { border:1px solid #30363d; border-radius:6px; background:#161b22; }
    QTabBar::tab {
        background:#21262d; color:#8b949e; padding:8px 20px;
        min-width:130px; border:1px solid #30363d;
        border-bottom:none; border-radius:4px 4px 0 0; font-size:10pt;
    }
    QTabBar::tab:selected {
        background:#161b22; color:#e6edf3;
        border-bottom:2px solid #58a6ff; font-weight:bold;
    }
    QTabBar::tab:hover:!selected { background:#30363d; color:#e6edf3; }
    QTextEdit, QLineEdit {
        background:#21262d; color:#e6edf3;
        border:1px solid #30363d; border-radius:4px; padding:8px;
        font-family:'Consolas', monospace; font-size:9pt;
    }
    QTextEdit:focus, QLineEdit:focus { border:2px solid #58a6ff; }
    QPushButton {
        background:#238636; color:#fff; border-radius:4px;
        padding:8px 12px; font-weight:bold; font-size:10pt;
    }
    QPushButton:hover   { background:#2ea043; }
    QPushButton:pressed { background:#1e7a2f; }
    QPushButton:disabled { background:#21262d; color:#484f58; }
    QPushButton#secondary { background:#21262d; border:1px solid #30363d; }
    QPushButton#secondary:hover { background:#30363d; }
    QProgressBar {
        border:1px solid #30363d; border-radius:4px;
        text-align:center; color:#e6edf3;
        background:#21262d; height:20px;
    }
    QProgressBar::chunk { background:#238636; border-radius:3px; }
    QScrollArea { border:none; background:transparent; }
    QFrame#infoCard { background:#21262d; border:1px solid #30363d; border-radius:6px; }
    QFrame#stepCard { background:#1c2128; border:1px solid #30363d; border-radius:6px; }
    QCheckBox { color: #e6edf3; spacing: 8px; }
    QCheckBox::indicator {
        width:18px; height:18px;
        border:1px solid #30363d; border-radius:3px; background:#21262d;
    }
    QCheckBox::indicator:checked { background:#238636; border:1px solid #2ea043; }
"""


class BrokerLoginPopup(QDialog):
    login_completed = pyqtSignal(object)  # access token
    error_occurred = pyqtSignal(str)
    operation_started = pyqtSignal()
    operation_finished = pyqtSignal()
    token_refreshed = pyqtSignal(str, str)  # message, status

    def __init__(self, parent, brokerage_setting, reason: str = None, notifier=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)
            self.brokerage_setting = brokerage_setting
            self._reason = reason
            self.notifier = notifier
            self.result_token: Optional[str] = None

            # Build broker-aware helper
            broker_type = getattr(brokerage_setting, 'broker_type', 'fyers') or 'fyers'
            self._helper = BrokerLoginHelper.for_broker(
                broker_type=broker_type,
                client_id=getattr(brokerage_setting, 'client_id', '') or '',
                secret_key=getattr(brokerage_setting, 'secret_key', '') or '',
                redirect_uri=getattr(brokerage_setting, 'redirect_uri', '') or '',
            )

            broker_name = self._helper.broker_display_name
            self.setWindowTitle(
                f"{broker_name} — Re-authentication Required" if reason
                else f"{broker_name} — Login"
            )
            self.setMinimumSize(750, 700 if reason else 650)
            self.resize(750, 700 if reason else 650)
            self.setModal(True)
            self.setStyleSheet(_STYLESHEET)

            self._build_ui()
            self._connect_signals()
            self._init_login_url()

            logger.info(f"BrokerLoginPopup initialized for {broker_name} (auth: {self._helper.auth_method})")

        except Exception as e:
            logger.critical(f"[BrokerLoginPopup.__init__] {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        self.brokerage_setting = None
        self._reason = None
        self.notifier = None
        self.result_token = None
        self._helper = None
        self._exchange_in_progress = False
        self.token_worker = None
        # UI widgets
        self.tabs = None
        self.url_text = None
        self.code_entry = None
        self.password_entry = None
        self.progress_bar = None
        self.status_label = None
        self.clear_btn = None
        self.login_btn = None
        self.cancel_btn = None
        self.notify_check = None
        self.telegram_status_label = None

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Header
        broker_name = self._helper.broker_display_name
        header = QLabel(f"🔐 {broker_name} Authentication")
        header.setFont(QFont("Segoe UI", 14, QFont.Bold))
        header.setStyleSheet("color:#e6edf3; padding:4px;")
        header.setAlignment(Qt.AlignCenter)
        root.addWidget(header)

        # Warning banner (token-expiry reason)
        if self._reason:
            banner = QFrame()
            banner.setStyleSheet("""
                QFrame { background:#3d1f1f; border:1px solid #f85149;
                         border-radius:6px; padding:4px; }
            """)
            bl = QHBoxLayout(banner)
            bl.setContentsMargins(12, 8, 12, 8)
            bl.setSpacing(10)
            icon_lbl = QLabel("⚠️")
            icon_lbl.setFont(QFont("Segoe UI", 14))
            icon_lbl.setStyleSheet("background:transparent; border:none;")
            msg_lbl = QLabel(
                f"<b style='color:#f85149;'>Session expired — re-login required</b><br>"
                f"<span style='color:#ffa657; font-size:9pt;'>{self._reason}</span>"
            )
            msg_lbl.setWordWrap(True)
            msg_lbl.setStyleSheet("background:transparent; border:none;")
            msg_lbl.setTextFormat(Qt.RichText)
            bl.addWidget(icon_lbl, 0, Qt.AlignTop)
            bl.addWidget(msg_lbl, 1)
            root.addWidget(banner)

        # Tabs
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tabs.addTab(self._build_login_tab(), "🔑 Login")
        self.tabs.addTab(self._build_notification_tab(), "📱 Notifications")
        self.tabs.addTab(self._build_info_tab(), "ℹ️ Information")

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximum(100)
        root.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color:#8b949e; font-size:9pt;")
        root.addWidget(self.status_label)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.clear_btn = QPushButton("✖ Clear")
        self.clear_btn.setObjectName("secondary")
        self.clear_btn.clicked.connect(self._clear_entries)

        self.login_btn = QPushButton("🔒 Complete Login")
        self.login_btn.clicked.connect(self._start_exchange)

        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton { background:#da3633; color:#fff; border-radius:4px; padding:8px 12px; }
            QPushButton:hover { background:#f85149; }
        """)
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.login_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        root.addLayout(btn_layout)

    # ── Login tab (adapts to auth_method) ─────────────────────────────────────

    def _build_login_tab(self) -> QWidget:
        widget = QWidget()
        try:
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(18, 18, 18, 12)
            layout.setSpacing(10)

            auth = self._helper.auth_method

            # ── Step 1 card ───────────────────────────────────────────────────
            step1 = self._make_step_card()
            step1_inner = QVBoxLayout(step1)
            step1_inner.setContentsMargins(14, 12, 14, 12)
            step1_inner.setSpacing(8)

            t1 = QLabel(self._helper.step1_title)
            t1.setFont(QFont("Segoe UI", 10, QFont.Bold))
            t1.setStyleSheet("color:#58a6ff;")
            h1 = QLabel(self._helper.step1_hint)
            h1.setWordWrap(True)
            h1.setStyleSheet("color:#484f58; font-size:8pt;")

            step1_inner.addWidget(t1)
            step1_inner.addWidget(h1)

            if self._helper.has_login_url:
                # URL display + copy/open buttons
                url_row = QHBoxLayout()
                self.url_text = QTextEdit()
                self.url_text.setMaximumHeight(56)
                self.url_text.setReadOnly(True)
                self.url_text.setToolTip("Generated login URL — copy or open in browser")
                url_row.addWidget(self.url_text, 1)

                copy_btn = QPushButton("📋 Copy")
                copy_btn.setObjectName("secondary")
                copy_btn.setMaximumWidth(80)
                copy_btn.clicked.connect(self._copy_url)
                url_row.addWidget(copy_btn)

                open_btn = QPushButton("🌐 Open in Browser")
                open_btn.clicked.connect(self._open_url)

                step1_inner.addLayout(url_row)
                step1_inner.addWidget(open_btn, alignment=Qt.AlignRight)

            layout.addWidget(step1)

            # ── Step 2 card ───────────────────────────────────────────────────
            step2 = self._make_step_card()
            step2_inner = QVBoxLayout(step2)
            step2_inner.setContentsMargins(14, 12, 14, 12)
            step2_inner.setSpacing(8)

            t2 = QLabel(self._helper.step2_title)
            t2.setFont(QFont("Segoe UI", 10, QFont.Bold))
            t2.setStyleSheet("color:#58a6ff;")
            h2 = QLabel(self._helper.step2_hint)
            h2.setWordWrap(True)
            h2.setStyleSheet("color:#484f58; font-size:8pt;")

            step2_inner.addWidget(t2)
            step2_inner.addWidget(h2)

            # Code / token entry (hidden for password-auth brokers)
            if auth != "password":
                self.code_entry = QLineEdit()
                self.code_entry.setPlaceholderText(self._helper.code_entry_placeholder)
                step2_inner.addWidget(self.code_entry)

            # Secondary password/MPIN field (totp brokers that need it)
            if self._helper.needs_password_field:
                pwd_lbl = QLabel(self._helper.password_field_label)
                pwd_lbl.setStyleSheet("color:#8b949e; font-size:9pt;")
                self.password_entry = QLineEdit()
                self.password_entry.setPlaceholderText(self._helper.password_field_placeholder)
                self.password_entry.setEchoMode(QLineEdit.Password)
                step2_inner.addWidget(pwd_lbl)
                step2_inner.addWidget(self.password_entry)

            # Mobile + UCC fields for Kotak Neo
            if (getattr(self.brokerage_setting, 'broker_type', '') or '') == 'kotak':
                kotak_lbl = QLabel("Mobile number and UCC (required for Kotak Neo):")
                kotak_lbl.setStyleSheet("color:#8b949e; font-size:9pt;")
                self.mobile_entry = QLineEdit()
                self.mobile_entry.setPlaceholderText("Mobile number with country code (e.g. +919999999999)")
                self.ucc_entry = QLineEdit()
                self.ucc_entry.setPlaceholderText("UCC (Unique Client Code)")
                step2_inner.addWidget(kotak_lbl)
                step2_inner.addWidget(self.mobile_entry)
                step2_inner.addWidget(self.ucc_entry)

            layout.addWidget(step2)
            layout.addStretch()

        except Exception as e:
            logger.error(f"[BrokerLoginPopup._build_login_tab] {e}", exc_info=True)
            err = QLabel(f"Error building login tab: {e}")
            err.setStyleSheet("color:#f85149;")
            err.setWordWrap(True)
            layout = QVBoxLayout(widget)
            layout.addWidget(err)

        return widget

    @staticmethod
    def _make_step_card() -> QFrame:
        card = QFrame()
        card.setObjectName("stepCard")
        return card

    # ── Notifications tab ─────────────────────────────────────────────────────

    def _build_notification_tab(self) -> QWidget:
        widget = QWidget()
        try:
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(15)

            grp = QGroupBox("Notification Settings")
            grp_layout = QVBoxLayout(grp)

            self.notify_check = QCheckBox("Send Telegram notification on token expiry")
            configured = False
            if self.brokerage_setting and hasattr(self.brokerage_setting, 'is_telegram_configured'):
                configured = self.brokerage_setting.is_telegram_configured()
            self.notify_check.setChecked(configured)
            grp_layout.addWidget(self.notify_check)

            hint = QLabel(
                "When enabled, you'll receive a Telegram notification whenever "
                "your token expires and needs renewal."
            )
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#484f58; font-size:8pt; padding-left:26px;")
            grp_layout.addWidget(hint)
            layout.addWidget(grp)

            status_grp = QGroupBox("Current Status")
            status_layout = QVBoxLayout(status_grp)
            self.telegram_status_label = QLabel("")
            status_layout.addWidget(self.telegram_status_label)
            self._update_telegram_status()
            layout.addWidget(status_grp)

            info = self._make_info_card(
                "📘 About Token Expiry Notifications",
                f"• {self._helper.broker_display_name} tokens expire periodically\n"
                "• When enabled, you'll receive a Telegram alert when your token expires\n"
                "• Configure Telegram in Settings → Brokerage Settings\n"
                "• This helps you know when re-authentication is needed"
            )
            layout.addWidget(info)
            layout.addStretch()
        except Exception as e:
            logger.error(f"[_build_notification_tab] {e}", exc_info=True)
        return widget

    def _update_telegram_status(self):
        try:
            if not self.telegram_status_label:
                return
            if self.brokerage_setting and hasattr(self.brokerage_setting, 'is_telegram_configured'):
                if self.brokerage_setting.is_telegram_configured():
                    self.telegram_status_label.setText("✅ Telegram notifications configured")
                    self.telegram_status_label.setStyleSheet("color:#3fb950;")
                else:
                    self.telegram_status_label.setText("⚠️ Telegram not configured")
                    self.telegram_status_label.setStyleSheet("color:#d29922;")
            else:
                self.telegram_status_label.setText("⚠️ Telegram settings not available")
                self.telegram_status_label.setStyleSheet("color:#d29922;")
        except Exception as e:
            logger.error(f"[_update_telegram_status] {e}", exc_info=True)

    # ── Info tab ──────────────────────────────────────────────────────────────

    def _build_info_tab(self) -> QScrollArea:
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(12)

            auth = self._helper.auth_method
            broker = self._helper.broker_display_name

            cards = [
                ("🔐 What is this dialog?",
                 f"{broker} requires authentication before the trading app can place orders. "
                 f"This dialog walks you through the authentication steps.\n\n"
                 f"Authentication method: {auth.upper()}"),

                (self._helper.step1_title, self._helper.step1_hint),
                (self._helper.step2_title, self._helper.step2_hint),

                ("🔑 What happens after I click 'Complete Login'?",
                 "Your credentials are used to obtain an access token in a background thread "
                 "(so the UI stays responsive). The token is stored in the database and used "
                 "for all subsequent API calls.\n\n"
                 "• If authentication fails, check your credentials and try again.\n"
                 "• Tokens typically expire at end-of-trading-day and must be renewed daily."),

                ("📱 Token Expiry Notifications",
                 "Enable Telegram notifications in the 'Notifications' tab to be alerted "
                 "when your token expires and re-authentication is needed."),

                ("⚠️ Common Issues",
                 self._common_issues_text()),

                ("📋 Credentials used",
                 f"This dialog uses the credentials configured in Brokerage Settings:\n\n"
                 f"• Client ID — identifies your app to {broker}\n"
                 f"• Secret Key — your API secret or password\n"
                 f"• Redirect URI — the OAuth callback URI (if applicable)\n\n"
                 "Go to Settings → Brokerage Settings if any credentials are missing or incorrect."),
            ]

            for title, body in cards:
                layout.addWidget(self._make_info_card(title, body))

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[_build_info_tab] {e}", exc_info=True)
            scroll = QScrollArea()
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.addWidget(QLabel(f"Error building info tab: {e}"))
            scroll.setWidget(container)
            return scroll

    def _common_issues_text(self) -> str:
        auth = self._helper.auth_method
        base = ("Wrong credentials — double-check your Client ID and Secret Key in "
                "Brokerage Settings if authentication fails.\n\n"
                "Token expired — most broker tokens expire at midnight. "
                "Re-run the login each morning before market open.\n\n")
        if auth == "oauth":
            return (base +
                    "Auth code expired — OAuth codes are valid for only ~60 seconds. "
                    "Restart from Step 1 if you see an 'invalid code' error.\n\n"
                    "Redirect URI mismatch — the URI in settings must exactly match "
                    "what is registered in the broker's developer portal.")
        if auth == "totp":
            return (base +
                    "Invalid TOTP — check that your device clock is synced (NTP).\n\n"
                    "Auto-TOTP not working — verify the TOTP secret (base32) stored "
                    "in the redirect_uri field is correct.")
        if auth == "session":
            return (base +
                    "Static IP required — ICICI Breeze enforces a static IP per SEBI rules. "
                    "Ensure you're on the whitelisted IP address.\n\n"
                    "Session token expired — session tokens are single-use. "
                    "Visit the login URL again to get a fresh token.")
        if auth == "password":
            return (base +
                    "Wrong YOB — Alice Blue uses Year of Birth as a 2FA answer. "
                    "Ensure the YOB stored in redirect_uri matches your registered value.")
        return base

    @staticmethod
    def _make_info_card(title: str, body: str) -> QFrame:
        card = QFrame()
        card.setObjectName("infoCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(6)
        t = QLabel(title)
        t.setFont(QFont("Segoe UI", 10, QFont.Bold))
        t.setStyleSheet("color:#e6edf3;")
        b = QLabel(body)
        b.setWordWrap(True)
        b.setStyleSheet("color:#8b949e; font-size:9pt;")
        cl.addWidget(t)
        cl.addWidget(b)
        return card

    def _create_error_dialog(self, parent):
        try:
            super().__init__(parent)
            self.setWindowTitle("Login — ERROR")
            self.setMinimumSize(400, 200)
            layout = QVBoxLayout(self)
            lbl = QLabel("❌ Failed to initialize login dialog.\nPlease check the logs.")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#f85149; padding:20px; font-size:12pt;")
            layout.addWidget(lbl)
            btn = QPushButton("Close")
            btn.clicked.connect(self.reject)
            layout.addWidget(btn)
        except Exception as e:
            logger.error(f"[_create_error_dialog] {e}", exc_info=True)

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self):
        try:
            self.error_occurred.connect(self._on_error)
            self.operation_started.connect(lambda: None)
            self.operation_finished.connect(lambda: None)
            self.token_refreshed.connect(self._on_token_refreshed)
        except Exception as e:
            logger.error(f"[_connect_signals] {e}", exc_info=True)

    # ── URL management ────────────────────────────────────────────────────────

    def _init_login_url(self):
        try:
            if not self._helper or not self._helper.has_login_url:
                return
            url = self._helper.generate_login_url()
            if not url:
                if self.status_label:
                    self.status_label.setText("⚠️ Could not generate login URL — check credentials in Settings")
                return
            self.login_url = url
            if self.url_text:
                self.url_text.setText(url)
            if self.status_label:
                self.status_label.setText("✅ Login URL generated")
        except Exception as e:
            logger.error(f"[_init_login_url] {e}", exc_info=True)
            if self.status_label:
                self.status_label.setText(f"❌ {e}")

    def _copy_url(self):
        try:
            url = getattr(self, 'login_url', None)
            if url:
                QApplication.clipboard().setText(url)
                if self.status_label:
                    self.status_label.setText("📋 URL copied to clipboard")
                    QTimer.singleShot(2000, lambda: self.status_label.setText("") if self.status_label else None)
            else:
                QMessageBox.warning(self, "Warning", "No URL to copy")
        except Exception as e:
            logger.error(f"[_copy_url] {e}", exc_info=True)

    def _open_url(self):
        try:
            url = getattr(self, 'login_url', None)
            if url:
                webbrowser.open(url)
                if self.status_label:
                    self.status_label.setText("🌐 Browser opened")
            else:
                QMessageBox.critical(self, "Error", "Login URL is unavailable.")
        except Exception as e:
            logger.error(f"[_open_url] {e}", exc_info=True)

    def _clear_entries(self):
        try:
            if self.code_entry:
                self.code_entry.clear()
            if self.password_entry:
                self.password_entry.clear()
        except Exception as e:
            logger.error(f"[_clear_entries] {e}", exc_info=True)

    # ── Auth code extraction ──────────────────────────────────────────────────

    def _extract_code(self, raw: str) -> str:
        """
        Extract the token/code from various input formats:
        - Full redirect URL (extracts auth_code / code / request_token param)
        - Raw code/token string
        """
        try:
            if not raw:
                return ""
            raw = raw.strip()

            # Already a plain token (no URL characters)
            if re.match(r'^[A-Za-z0-9\-_\.]+$', raw):
                return raw

            # Skip if it looks like an access_token pasted by mistake
            if "access_token" in raw:
                logger.warning("Input contains access_token — user should paste the auth code / redirect URL")
                return ""

            # Try URL parsing
            try:
                parsed = urlparse(raw)
                for src in (parsed.query, parsed.fragment):
                    if src:
                        params = parse_qs(src)
                        for key in ('auth_code', 'code', 'request_token', 'token', 'authorization_code'):
                            if key in params and params[key]:
                                return params[key][0]
            except Exception:
                pass

            # Fall back to returning raw if it has no URL structure
            if "?" not in raw and "=" not in raw:
                return raw

            return ""
        except Exception as e:
            logger.error(f"[_extract_code] {e}", exc_info=True)
            return ""

    # ── Exchange / worker ─────────────────────────────────────────────────────

    def _start_exchange(self):
        try:
            if self._exchange_in_progress:
                return
            if not self._helper:
                return

            auth = self._helper.auth_method

            # Collect inputs
            raw_code = ""
            if self.code_entry:
                raw_code = self.code_entry.text().strip()

            extra = {}

            # For TOTP brokers that need a password
            if self._helper.needs_password_field:
                password = self.password_entry.text().strip() if self.password_entry else ""
                if not password and auth == "totp":
                    QMessageBox.warning(
                        self, "Input Needed",
                        f"Please enter your {self._helper.password_field_label}."
                    )
                    return
                extra["password"] = password

            # Kotak Neo — mobile + UCC required
            if (getattr(self.brokerage_setting, 'broker_type', '') or '') == 'kotak':
                mobile = getattr(self, 'mobile_entry', None)
                ucc = getattr(self, 'ucc_entry', None)
                mobile_val = mobile.text().strip() if mobile else ""
                ucc_val = ucc.text().strip() if ucc else ""
                if not mobile_val or not ucc_val:
                    QMessageBox.warning(self, "Input Needed",
                                        "Mobile number and UCC are required for Kotak Neo.")
                    return
                extra["mobile"] = mobile_val
                extra["ucc"] = ucc_val

            # For OAuth/session brokers: extract code from URL
            if auth in ("oauth", "session"):
                if not raw_code:
                    QMessageBox.warning(self, "Input Needed",
                                        "Please paste the auth code or full redirected URL.")
                    return
                code = self._extract_code(raw_code)
                if not code:
                    QMessageBox.critical(
                        self, "Invalid Input",
                        "Could not extract auth code from your input.\n"
                        "Paste the full redirected URL, or just the code value."
                    )
                    return
                if auth == "oauth" and len(code) < 10:
                    QMessageBox.critical(self, "Invalid Input",
                                         "Auth code seems too short — please check and try again.")
                    return
            elif auth == "static":
                # For Dhan: accept token from entry or fall back to secret_key
                code = raw_code or getattr(self._helper, 'secret_key', '') or ""
                if not code:
                    QMessageBox.warning(self, "Input Needed", "Please paste the access token.")
                    return
            elif auth == "totp":
                code = raw_code  # blank = auto-generate from secret
            else:
                code = raw_code  # password auth: blank is fine

            self._exchange_in_progress = True
            self.operation_started.emit()

            if self.login_btn:
                self.login_btn.setEnabled(False)
            if self.clear_btn:
                self.clear_btn.setEnabled(False)
            if self.progress_bar:
                self.progress_bar.setVisible(True)
                self.progress_bar.setValue(10)
            if self.status_label:
                self.status_label.setText("⏳ Processing authentication…")

            self.token_worker = TokenExchangeWorker(self._helper, code, extra)
            self.token_worker.progress.connect(self._update_progress)
            self.token_worker.finished.connect(self._on_exchange_complete)
            self.token_worker.error_occurred.connect(self._on_worker_error)
            self.token_worker.start()
            logger.info("Token exchange started")

        except Exception as e:
            logger.error(f"[_start_exchange] {e}", exc_info=True)
            self.error_occurred.emit(f"Exchange failed: {e}")
            self._exchange_in_progress = False
            self.operation_finished.emit()
            self._reset_ui()

    def _update_progress(self, pct: int, msg: str):
        try:
            if self.progress_bar:
                self.progress_bar.setValue(pct)
            if self.status_label:
                self.status_label.setText(f"⏳ {msg}")
        except Exception as e:
            logger.error(f"[_update_progress] {e}", exc_info=True)

    def _on_worker_error(self, error_msg: str):
        logger.error(f"Worker error: {error_msg}")
        self.error_occurred.emit(error_msg)

    def _on_exchange_complete(self, token, error: str):
        try:
            if self.token_worker:
                self.token_worker.stop()
                self.token_worker.deleteLater()
                self.token_worker = None

            if error:
                if self.status_label:
                    self.status_label.setText(f"❌ {error}")
                QMessageBox.critical(self, "Login Failed",
                                     f"Authentication failed.\n\nError: {error}\n\n"
                                     "Please check your credentials and try again.")
                self._reset_ui()
                return

            if token:
                # Save token to brokerage_setting if possible
                if self.brokerage_setting and hasattr(self.brokerage_setting, 'save_token'):
                    try:
                        now = datetime.now()
                        self.brokerage_setting.save_token(
                            access_token=token,
                            refresh_token="",
                            issued_at=now.isoformat(),
                            expires_at=(now + timedelta(hours=24)).isoformat(),
                        )
                    except Exception as e:
                        logger.error(f"Failed to save token to brokerage_setting: {e}", exc_info=True)

                # Telegram notification
                if self.notify_check and self.notify_check.isChecked():
                    self._send_telegram_notification(success=True)

                self.result_token = token
                if self.status_label:
                    self.status_label.setText("✅ Login successful!")
                if self.progress_bar:
                    self.progress_bar.setValue(100)

                self.login_completed.emit(token)
                QMessageBox.information(self, "Success",
                                        "Login successful! Token has been stored.")
                QTimer.singleShot(500, self.accept)
            else:
                if self.status_label:
                    self.status_label.setText("❌ Failed to retrieve token")
                QMessageBox.critical(self, "Error", "Failed to retrieve token.")
                self._reset_ui()

        except Exception as e:
            logger.error(f"[_on_exchange_complete] {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self._reset_ui()
        finally:
            self._exchange_in_progress = False
            self.operation_finished.emit()

    def _send_telegram_notification(self, success: bool = True):
        try:
            if not self.notifier:
                return
            broker = self._helper.broker_display_name if self._helper else "Broker"
            if success:
                msg = f"✅ *TOKEN REFRESHED*\n{broker} access token has been successfully renewed."
                self.notifier.notify_token_refreshed(msg)
                self.token_refreshed.emit(msg, "success")
            else:
                msg = f"❌ *TOKEN REFRESH FAILED*\nFailed to refresh {broker} token."
                self.notifier.notify_token_refresh_failed(msg)
                self.token_refreshed.emit(msg, "error")
        except Exception as e:
            logger.error(f"[_send_telegram_notification] {e}", exc_info=True)

    def _on_token_refreshed(self, message: str, status: str):
        logger.info(f"Token refresh notification: {status}")

    def _reset_ui(self):
        try:
            if self.login_btn:
                self.login_btn.setEnabled(True)
            if self.clear_btn:
                self.clear_btn.setEnabled(True)
            if self.progress_bar:
                self.progress_bar.setVisible(False)
                self.progress_bar.setValue(0)
            if self.status_label and self.status_label.text().startswith("⏳"):
                self.status_label.setText("")
        except Exception as e:
            logger.error(f"[_reset_ui] {e}", exc_info=True)

    def _on_error(self, msg: str):
        try:
            logger.error(f"Error signal: {msg}")
            QMessageBox.critical(self, "Error", msg)
            self._reset_ui()
        except Exception as e:
            logger.error(f"[_on_error] {e}", exc_info=True)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        try:
            logger.info("[BrokerLoginPopup] Starting cleanup")
            if self.token_worker and self.token_worker.isRunning():
                self.token_worker.stop()
                if not self.token_worker.wait(3000):
                    self.token_worker.terminate()
                    self.token_worker.wait(1000)
            self.token_worker = None
            if self._helper:
                self._helper.cleanup()
            self._helper = None
            self.brokerage_setting = None
            self.notifier = None
            logger.info("[BrokerLoginPopup] Cleanup completed")
        except Exception as e:
            logger.error(f"[BrokerLoginPopup.cleanup] {e}", exc_info=True)

    def closeEvent(self, event):
        try:
            self.cleanup()
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[BrokerLoginPopup.closeEvent] {e}", exc_info=True)
            super().closeEvent(event)


# ── Backward-compatibility alias ─────────────────────────────────────────────
# Any existing code that imports FyersManualLoginPopup will continue to work.
FyersManualLoginPopup = BrokerLoginPopup
