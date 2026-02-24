# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
import logging
import logging.handlers
import re
import traceback
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTextEdit,
                             QPushButton, QLineEdit, QHBoxLayout, QMessageBox,
                             QProgressBar, QApplication, QWidget, QTabWidget,
                             QFrame, QScrollArea)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont

import webbrowser

from Utils.FyersManualLoginHelper import FyersManualLoginHelper

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TokenExchangeWorker(QThread):
    """Worker thread for token exchange to prevent UI freezing"""
    finished = pyqtSignal(object, str)  # token, error message
    progress = pyqtSignal(int, str)  # progress percentage, status message
    error_occurred = pyqtSignal(str)  # error signal

    def __init__(self, fyers_helper, auth_code):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__()
            self.fyers_helper = fyers_helper
            self.auth_code = auth_code
            logger.debug("TokenExchangeWorker initialized")
        except Exception as e:
            logger.error(f"[TokenExchangeWorker.__init__] Failed: {e}", exc_info=True)
            super().__init__()
            self.fyers_helper = fyers_helper
            self.auth_code = auth_code

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.fyers_helper = None
        self.auth_code = None
        self._is_stopping = False

    def run(self):
        try:
            # Validate inputs
            if not self.fyers_helper:
                error_msg = "Fyers helper is None"
                logger.error(error_msg)
                self.finished.emit(None, error_msg)
                return

            if not self.auth_code:
                error_msg = "Auth code is empty"
                logger.error(error_msg)
                self.finished.emit(None, error_msg)
                return

            self.progress.emit(30, "Exchanging code for token...")
            logger.info("Starting token exchange")

            token = self.fyers_helper.exchange_code_for_token(self.auth_code)

            self.progress.emit(100, "Token received")

            if token:
                logger.info("Token exchange successful")
                self.finished.emit(token, None)
            else:
                error_msg = "Failed to retrieve token"
                logger.error(error_msg)
                self.finished.emit(None, error_msg)

        except AttributeError as e:
            error_msg = f"Attribute error in token exchange: {e}"
            logger.error(error_msg, exc_info=True)
            self.finished.emit(None, error_msg)
        except Exception as e:
            error_msg = f"Token exchange error: {e!r}"
            logger.error(error_msg, exc_info=True)
            self.finished.emit(None, str(e))

    def stop(self):
        """Request worker to stop"""
        try:
            self._is_stopping = True
            logger.debug("TokenExchangeWorker stop requested")
        except Exception as e:
            logger.error(f"[TokenExchangeWorker.stop] Failed: {e}", exc_info=True)


class FyersManualLoginPopup(QDialog):
    login_completed = pyqtSignal(object)  # token object

    # Rule 3: Additional signals for error handling
    error_occurred = pyqtSignal(str)
    operation_started = pyqtSignal()
    operation_finished = pyqtSignal()

    def __init__(self, parent, brokerage_setting, reason: str = None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.brokerage_setting = brokerage_setting
            self._reason = reason  # Optional context message (e.g. token expired)

            # Rule 6: Input validation
            if brokerage_setting is None:
                logger.error("FyersManualLoginPopup initialized with None brokerage_setting")

            self.setWindowTitle("Fyers Manual Login — Re-authentication Required" if reason else "Fyers Manual Login")
            self.setMinimumSize(750, 640 if reason else 600)
            self.resize(750, 640 if reason else 600)
            self.setModal(True)

            # EXACT stylesheet preservation - no changes
            self.setStyleSheet("""
                QDialog { background:#161b22; color:#e6edf3; font-family:'Segoe UI', sans-serif; }
                QLabel  { color:#8b949e; font-size:10pt; }
                QTabWidget::pane {
                    border:1px solid #30363d;
                    border-radius:6px;
                    background:#161b22;
                }
                QTabBar::tab {
                    background:#21262d;
                    color:#8b949e;
                    padding:8px 20px;
                    min-width:130px;
                    border:1px solid #30363d;
                    border-bottom:none;
                    border-radius:4px 4px 0 0;
                    font-size:10pt;
                }
                QTabBar::tab:selected {
                    background:#161b22;
                    color:#e6edf3;
                    border-bottom:2px solid #58a6ff;
                    font-weight:bold;
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
                QPushButton:hover    { background:#2ea043; }
                QPushButton:pressed  { background:#1e7a2f; }
                QPushButton:disabled { background:#21262d; color:#484f58; }
                QProgressBar {
                    border:1px solid #30363d; border-radius:4px;
                    text-align:center; color:#e6edf3;
                    background:#21262d; height:20px;
                }
                QProgressBar::chunk { background:#238636; border-radius:3px; }
                QScrollArea { border:none; background:transparent; }
                QFrame#infoCard {
                    background:#21262d;
                    border:1px solid #30363d;
                    border-radius:6px;
                }
                QFrame#stepCard {
                    background:#1c2128;
                    border:1px solid #30363d;
                    border-radius:6px;
                }
            """)

            # Root layout
            root = QVBoxLayout(self)
            root.setContentsMargins(16, 16, 16, 16)
            root.setSpacing(12)

            # Header
            header = QLabel("🔐 Fyers Manual Authentication")
            header.setFont(QFont("Segoe UI", 14, QFont.Bold))
            header.setStyleSheet("color:#e6edf3; padding:4px;")
            header.setAlignment(Qt.AlignCenter)
            root.addWidget(header)

            # Token-expiry / reason banner (shown only when reason is set)
            if self._reason:
                banner = QFrame()
                banner.setStyleSheet("""
                    QFrame {
                        background: #3d1f1f;
                        border: 1px solid #f85149;
                        border-radius: 6px;
                        padding: 4px;
                    }
                """)
                banner_layout = QHBoxLayout(banner)
                banner_layout.setContentsMargins(12, 8, 12, 8)
                banner_layout.setSpacing(10)

                icon_lbl = QLabel("⚠️")
                icon_lbl.setFont(QFont("Segoe UI", 14))
                icon_lbl.setStyleSheet("background: transparent; border: none;")

                msg_lbl = QLabel(
                    f"<b style='color:#f85149;'>Session expired — re-login required</b><br>"
                    f"<span style='color:#ffa657; font-size:9pt;'>{self._reason}</span>"
                )
                msg_lbl.setWordWrap(True)
                msg_lbl.setStyleSheet("background: transparent; border: none;")
                msg_lbl.setTextFormat(Qt.RichText)

                banner_layout.addWidget(icon_lbl, 0, Qt.AlignTop)
                banner_layout.addWidget(msg_lbl, 1)
                root.addWidget(banner)

            # Tabs
            self.tabs = QTabWidget()
            root.addWidget(self.tabs)
            self.tabs.addTab(self._build_login_tab(), "🔑 Login")
            self.tabs.addTab(self._build_info_tab(), "ℹ️ Information")

            # Progress bar (always visible below tabs)
            self.progress_bar = QProgressBar()
            self.progress_bar.setVisible(False)
            self.progress_bar.setMaximum(100)
            root.addWidget(self.progress_bar)

            # Status label
            self.status_label = QLabel("")
            self.status_label.setAlignment(Qt.AlignCenter)
            self.status_label.setStyleSheet("color:#8b949e; font-size:9pt;")
            root.addWidget(self.status_label)

            # Buttons
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(10)

            self.clear_btn = QPushButton("✖ Clear")
            self.clear_btn.setStyleSheet("""
                QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                             border-radius:4px; padding:8px 12px; }
                QPushButton:hover { background:#30363d; }
            """)
            self.clear_btn.clicked.connect(self.clear_code_entry)

            self.login_btn = QPushButton("🔒 Complete Login")
            self.login_btn.clicked.connect(self.exchange_code)

            self.cancel_btn = QPushButton("✕ Cancel")
            self.cancel_btn.setStyleSheet("""
                QPushButton { background:#da3633; color:#fff; border-radius:4px; padding:8px 12px; }
                QPushButton:hover { background:#f85149; }
            """)
            self.cancel_btn.clicked.connect(self.reject)

            btn_layout.addWidget(self.clear_btn)
            btn_layout.addWidget(self.login_btn)
            btn_layout.addWidget(self.cancel_btn)
            root.addLayout(btn_layout)

            # State
            self.fyers = None
            self.login_url = None
            self.token_worker = None

            # Connect internal signals
            self._connect_signals()

            # Initialize login URL
            self.init_login_url()

            logger.info("FyersManualLoginPopup initialized")

        except Exception as e:
            logger.critical(f"[FyersManualLoginPopup.__init__] Failed: {e}", exc_info=True)
            # Still try to show a basic dialog
            super().__init__(parent)
            self.brokerage_setting = brokerage_setting
            self._safe_defaults_init()
            self.setWindowTitle("Fyers Manual Login - ERROR")
            self.setMinimumSize(400, 200)

            # Add error message
            layout = QVBoxLayout(self)
            error_label = QLabel(f"Failed to initialize login dialog:\n{e}")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #f85149; padding: 20px;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.brokerage_setting = None
        self._reason = None
        self.tabs = None
        self.url_text = None
        self.code_entry = None
        self.progress_bar = None
        self.status_label = None
        self.clear_btn = None
        self.login_btn = None
        self.cancel_btn = None
        self.fyers = None
        self.login_url = None
        self.token_worker = None
        self._exchange_in_progress = False

    def _connect_signals(self):
        """Connect internal signals"""
        try:
            self.error_occurred.connect(self._on_error)
            self.operation_started.connect(self._on_operation_started)
            self.operation_finished.connect(self._on_operation_finished)
        except Exception as e:
            logger.error(f"[FyersManualLoginPopup._connect_signals] Failed: {e}", exc_info=True)

    # ── Login Tab ─────────────────────────────────────────────────────────────
    def _build_login_tab(self):
        """Build the login tab with step-by-step instructions"""
        widget = QWidget()
        try:
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(18, 18, 18, 12)
            layout.setSpacing(10)

            # ── Step 1 ────────────────────────────────────────────────────────────
            step1_card = QFrame()
            step1_card.setObjectName("stepCard")
            step1_inner = QVBoxLayout(step1_card)
            step1_inner.setContentsMargins(14, 12, 14, 12)
            step1_inner.setSpacing(8)

            step1_title = QLabel("Step 1 — Open the login URL and authorise")
            step1_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
            step1_title.setStyleSheet("color:#58a6ff;")
            step1_hint = QLabel("Click the button below to open the Fyers login page in your browser.")
            step1_hint.setStyleSheet("color:#484f58; font-size:8pt;")

            url_row = QHBoxLayout()
            self.url_text = QTextEdit()
            self.url_text.setMaximumHeight(56)
            self.url_text.setReadOnly(True)
            self.url_text.setToolTip("The generated Fyers OAuth login URL. Copy or open it in your browser.")
            url_row.addWidget(self.url_text, 1)

            copy_btn = QPushButton("📋 Copy")
            copy_btn.setMaximumWidth(80)
            copy_btn.setToolTip("Copy the login URL to clipboard.")
            copy_btn.clicked.connect(self.copy_url_to_clipboard)
            url_row.addWidget(copy_btn)

            open_btn = QPushButton("🌐 Open in Browser")
            open_btn.setToolTip("Open the login URL in your default web browser.")
            open_btn.clicked.connect(self.open_login_url)

            step1_inner.addWidget(step1_title)
            step1_inner.addWidget(step1_hint)
            step1_inner.addLayout(url_row)
            step1_inner.addWidget(open_btn, alignment=Qt.AlignRight)
            layout.addWidget(step1_card)

            # ── Step 2 ────────────────────────────────────────────────────────────
            step2_card = QFrame()
            step2_card.setObjectName("stepCard")
            step2_inner = QVBoxLayout(step2_card)
            step2_inner.setContentsMargins(14, 12, 14, 12)
            step2_inner.setSpacing(8)

            step2_title = QLabel("Step 2 — Paste the redirected URL or auth code")
            step2_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
            step2_title.setStyleSheet("color:#58a6ff;")

            step2_hint = QLabel(
                "After authorising, your browser will redirect to your Redirect URI.\n"
                "Paste the entire redirected URL here, or just the auth code if you already have it."
            )
            step2_hint.setWordWrap(True)
            step2_hint.setStyleSheet("color:#484f58; font-size:8pt;")

            self.code_entry = QLineEdit()
            self.code_entry.setPlaceholderText("Paste full redirected URL or auth code here…")
            self.code_entry.setToolTip(
                "Accepts:\n"
                "• The full redirected URL (e.g. https://127.0.0.1:8182/broker/fyers?auth_code=xxx)\n"
                "• Just the auth code string on its own."
            )

            step2_inner.addWidget(step2_title)
            step2_inner.addWidget(step2_hint)
            step2_inner.addWidget(self.code_entry)
            layout.addWidget(step2_card)

            layout.addStretch()

        except Exception as e:
            logger.error(f"[FyersManualLoginPopup._build_login_tab] Failed: {e}", exc_info=True)
            # Return a basic widget on error
            error_label = QLabel(f"Error building login tab: {e}")
            error_label.setStyleSheet("color: #f85149;")
            error_label.setWordWrap(True)
            layout = QVBoxLayout(widget)
            layout.addWidget(error_label)

        return widget

    # ── Information Tab ───────────────────────────────────────────────────────
    def _build_info_tab(self):
        """Build the information tab with help content"""
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(12)

            infos = [
                (
                    "🔐  What is Manual Login?",
                    "Fyers uses OAuth 2.0 for authentication. Normally this is handled automatically, "
                    "but when running on a machine without a browser callback listener (e.g. a server or VM), "
                    "you need to complete the login manually.\n\n"
                    "This dialog walks you through the two steps required to obtain a valid access token."
                ),
                (
                    "Step 1 — The Login URL",
                    "The login URL is generated from your Client ID, Secret Key, and Redirect URI "
                    "(configured in Brokerage Settings).\n\n"
                    "• Click 'Open in Browser' to launch the Fyers login page.\n"
                    "• Log in with your Fyers credentials and approve the permission request.\n"
                    "• Fyers will then redirect your browser to your Redirect URI with an auth code "
                    "appended as a query parameter."
                ),
                (
                    "Step 2 — The Auth Code",
                    "After you authorise, your browser will be redirected to a URL that looks like:\n\n"
                    "    https://127.0.0.1:8182/broker/fyers?auth_code=ey...\n\n"
                    "You can paste:\n"
                    "• The ENTIRE redirected URL — the app will extract the code automatically.\n"
                    "• Just the auth_code value on its own if you've already copied it.\n\n"
                    "Auth codes are short-lived (typically ~60 seconds). Complete Step 2 quickly after authorising."
                ),
                (
                    "🔑  What happens after I click 'Complete Login'?",
                    "The auth code is sent to Fyers' token endpoint in a background thread "
                    "(so the UI stays responsive). Fyers returns a session token which is then "
                    "stored in memory and used to authenticate all subsequent API calls.\n\n"
                    "• The token is never logged or written to disk by this dialog.\n"
                    "• If the exchange fails, check that your auth code hasn't expired and try again."
                ),
                (
                    "⚠️  Common Issues",
                    "Auth code expired — Fyers codes are valid for only ~60 seconds. "
                    "If you see an 'invalid code' error, restart from Step 1.\n\n"
                    "Redirect URI mismatch — The URI in Brokerage Settings must exactly match "
                    "what is registered in your Fyers developer portal. Even a trailing slash difference will fail.\n\n"
                    "Wrong credentials — Double-check your Client ID and Secret Key in Brokerage Settings "
                    "if the login URL fails to generate.\n\n"
                    "Browser doesn't open — Use the 📋 Copy button and paste the URL manually into your browser."
                ),
                (
                    "📋  Credentials used",
                    "This dialog uses the credentials configured in Brokerage Settings:\n\n"
                    "• Client ID — identifies your app to Fyers.\n"
                    "• Secret Key — proves your app's identity during token exchange.\n"
                    "• Redirect URI — the address Fyers redirects to after login.\n\n"
                    "If any of these are missing or incorrect, go to Settings → Brokerage Settings to update them."
                ),
            ]

            for title, body in infos:
                try:
                    card = QFrame()
                    card.setObjectName("infoCard")
                    card_layout = QVBoxLayout(card)
                    card_layout.setContentsMargins(14, 12, 14, 12)
                    card_layout.setSpacing(6)

                    title_lbl = QLabel(title)
                    title_lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
                    title_lbl.setStyleSheet("color:#e6edf3;")

                    body_lbl = QLabel(body)
                    body_lbl.setWordWrap(True)
                    body_lbl.setStyleSheet("color:#8b949e; font-size:9pt;")

                    card_layout.addWidget(title_lbl)
                    card_layout.addWidget(body_lbl)
                    layout.addWidget(card)

                except Exception as e:
                    logger.error(f"Failed to create info card for {title}: {e}", exc_info=True)
                    # Skip this card but continue

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[FyersManualLoginPopup._build_info_tab] Failed: {e}", exc_info=True)
            # Return a basic scroll area on error
            scroll = QScrollArea()
            container = QWidget()
            layout = QVBoxLayout(container)
            error_label = QLabel(f"Error building information tab: {e}")
            error_label.setStyleSheet("color: #f85149;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
            scroll.setWidget(container)
            return scroll

    # ── Login logic ───────────────────────────────────────────────────────────
    def init_login_url(self):
        """Initialize the login URL from brokerage settings"""
        try:
            # Rule 6: Validate brokerage settings
            if not self.brokerage_setting:
                raise ValueError("Brokerage setting is not initialized")

            if not hasattr(self.brokerage_setting, 'client_id') or not self.brokerage_setting.client_id:
                raise ValueError("Client ID is missing")

            if not hasattr(self.brokerage_setting, 'secret_key') or not self.brokerage_setting.secret_key:
                raise ValueError("Secret Key is missing")

            if not hasattr(self.brokerage_setting, 'redirect_uri') or not self.brokerage_setting.redirect_uri:
                raise ValueError("Redirect URI is missing")

            self.fyers = FyersManualLoginHelper(
                client_id=self.brokerage_setting.client_id,
                secret_key=self.brokerage_setting.secret_key,
                redirect_uri=self.brokerage_setting.redirect_uri,
            )

            self.login_url = self.fyers.generate_login_url()

            # FIXED: Use explicit None checks
            if self.url_text is not None:
                self.url_text.setText(self.login_url)

            if self.status_label is not None:
                self.status_label.setText("✅ Login URL generated successfully")

            logger.info("Login URL generated successfully")

        except AttributeError as e:
            error_msg = f"Attribute error generating login URL: {e}"
            logger.error(error_msg, exc_info=True)
            self._handle_login_url_error(error_msg)

        except Exception as e:
            error_msg = f"Failed to generate login URL: {e!r}"
            logger.critical(error_msg, exc_info=True)
            self._handle_login_url_error(error_msg)

    def _handle_login_url_error(self, error_msg: str):
        """Handle login URL generation error"""
        try:
            # FIXED: Use explicit None check
            if self.status_label is not None:
                self.status_label.setText(f"❌ {error_msg}")

            QMessageBox.critical(self, "Error", error_msg)
            self.reject()

        except Exception as e:
            logger.error(f"[_handle_login_url_error] Failed: {e}", exc_info=True)

    def copy_url_to_clipboard(self):
        """Copy login URL to clipboard"""
        try:
            # FIXED: Use explicit check for login_url
            if self.login_url is not None:
                QApplication.clipboard().setText(self.login_url)
                # FIXED: Use explicit None check
                if self.status_label is not None:
                    self.status_label.setText("📋 URL copied to clipboard")
                    QTimer.singleShot(2000, lambda: self.status_label.setText("") if self.status_label is not None else None)
            else:
                QMessageBox.warning(self, "Warning", "No URL to copy")

        except Exception as e:
            logger.error(f"[copy_url_to_clipboard] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to copy URL: {e}")

    def open_login_url(self):
        """Open login URL in default browser"""
        try:
            if self.login_url:
                webbrowser.open(self.login_url)
                if self.status_label is not None:
                    self.status_label.setText("🌐 Browser opened")
            else:
                QMessageBox.critical(self, "Error", "Login URL is unavailable.")

        except Exception as e:
            logger.error(f"Failed to open URL in browser: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to open URL in browser: {e}")

    def clear_code_entry(self):
        """Clear the code entry field"""
        try:
            # FIXED: Use explicit None check
            if self.code_entry is not None:
                self.code_entry.clear()
        except Exception as e:
            logger.error(f"[clear_code_entry] Failed: {e}", exc_info=True)

    def extract_auth_code(self, input_text: str) -> str:
        """Extract auth code from various input formats"""
        try:
            if not input_text:
                return ""

            input_text = input_text.strip()

            # Direct auth code (alphanumeric with possible hyphens/underscores)
            if re.match(r'^[A-Za-z0-9\-_]+$', input_text):
                logger.debug("Input recognized as direct auth code")
                return input_text

            # Check for access_token (should not be here)
            if "access_token" in input_text:
                logger.warning("Input contains access_token instead of auth_code")
                return ""

            # Try to parse as URL
            try:
                parsed = urlparse(input_text)

                # Check query parameters
                if parsed.query:
                    params = parse_qs(parsed.query)
                    for key in ['auth_code', 'code', 'authorization_code']:
                        if key in params and params[key]:
                            return params[key][0]

                # Check fragment
                if parsed.fragment:
                    frag_params = parse_qs(parsed.fragment)
                    for key in ['auth_code', 'code', 'authorization_code']:
                        if key in frag_params and frag_params[key]:
                            return frag_params[key][0]

            except Exception as e:
                logger.debug(f"URL parsing failed: {e}")

            # If not URL format and not direct code, return as is
            if "?" not in input_text and "=" not in input_text:
                return input_text

            return ""

        except Exception as e:
            logger.error(f"[extract_auth_code] Failed: {e}", exc_info=True)
            return ""

    def exchange_code(self):
        """Exchange auth code for token"""
        try:
            # Prevent multiple exchanges
            if self._exchange_in_progress:
                logger.warning("Exchange already in progress")
                return

            # FIXED: Use explicit None check
            if self.code_entry is None:
                logger.error("Code entry widget not initialized")
                return

            code_or_url = self.code_entry.text().strip()
            if not code_or_url:
                QMessageBox.warning(self, "Input Needed", "Please paste the auth code or full URL.")
                return

            auth_code = self.extract_auth_code(code_or_url)
            if not auth_code:
                QMessageBox.critical(
                    self, "Error",
                    "Could not extract auth code.\nPlease paste the full redirected URL or just the code."
                )
                return

            if len(auth_code) < 10:
                QMessageBox.critical(
                    self, "Error",
                    "Auth code seems too short. Please check and try again."
                )
                return

            self._exchange_in_progress = True
            self.operation_started.emit()

            # Disable UI - FIXED: Use explicit None checks
            if self.login_btn is not None:
                self.login_btn.setEnabled(False)
            if self.clear_btn is not None:
                self.clear_btn.setEnabled(False)
            if self.progress_bar is not None:
                self.progress_bar.setVisible(True)
                self.progress_bar.setValue(10)
            if self.status_label is not None:
                self.status_label.setText("⏳ Processing authentication…")

            # Create and start worker
            self.token_worker = TokenExchangeWorker(self.fyers, auth_code)
            self.token_worker.progress.connect(self.update_progress)
            self.token_worker.finished.connect(self.on_token_exchange_complete)
            self.token_worker.error_occurred.connect(self.on_worker_error)
            self.token_worker.start()

            logger.info("Token exchange started")

        except Exception as e:
            logger.error(f"[exchange_code] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Exchange failed: {e}")
            self._exchange_in_progress = False
            self.operation_finished.emit()
            self.reset_ui()

    def update_progress(self, percentage: int, message: str):
        """Update progress bar and status"""
        try:
            # FIXED: Use explicit None checks
            if self.progress_bar is not None:
                self.progress_bar.setValue(percentage)
            if self.status_label is not None:
                self.status_label.setText(f"⏳ {message}")
        except Exception as e:
            logger.error(f"[update_progress] Failed: {e}", exc_info=True)

    def on_worker_error(self, error_msg: str):
        """Handle worker error"""
        try:
            logger.error(f"Worker error: {error_msg}")
            self.error_occurred.emit(error_msg)
        except Exception as e:
            logger.error(f"[on_worker_error] Failed: {e}", exc_info=True)

    def on_token_exchange_complete(self, token, error):
        """Handle token exchange completion"""
        try:
            # Clean up worker
            if self.token_worker:
                self.token_worker.stop()
                self.token_worker.deleteLater()
                self.token_worker = None

            if error:
                logger.error(f"Token exchange failed: {error}")
                # FIXED: Use explicit None check
                if self.status_label is not None:
                    self.status_label.setText(f"❌ Login failed: {error}")
                QMessageBox.critical(
                    self, "Login Failed",
                    f"Failed to retrieve token.\nError: {error}\n\nPlease check your auth code and try again."
                )
                self.reset_ui()
                return

            if token:
                logger.info("✓ Token received successfully")
                # FIXED: Use explicit None checks
                if self.status_label is not None:
                    self.status_label.setText("✅ Login successful!")
                if self.progress_bar is not None:
                    self.progress_bar.setValue(100)

                self.login_completed.emit(token)

                QMessageBox.information(
                    self, "Success",
                    "Login successful! Token has been received and will be used for trading."
                )

                # Close dialog after short delay
                QTimer.singleShot(500, self.accept)
            else:
                # FIXED: Use explicit None check
                if self.status_label is not None:
                    self.status_label.setText("❌ Failed to retrieve token")
                QMessageBox.critical(
                    self, "Error",
                    "Failed to retrieve token. The auth code might be invalid or expired."
                )
                self.reset_ui()

        except Exception as e:
            logger.error(f"[on_token_exchange_complete] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Completion handler error: {e}")
            self.reset_ui()
        finally:
            self._exchange_in_progress = False
            self.operation_finished.emit()

    def reset_ui(self):
        """Reset UI to initial state"""
        try:
            # FIXED: Use explicit None checks
            if self.login_btn is not None:
                self.login_btn.setEnabled(True)
            if self.clear_btn is not None:
                self.clear_btn.setEnabled(True)
            if self.progress_bar is not None:
                self.progress_bar.setVisible(False)
                self.progress_bar.setValue(0)
            if self.status_label is not None and self.status_label.text().startswith("⏳"):
                self.status_label.setText("")

        except Exception as e:
            logger.error(f"[reset_ui] Failed: {e}", exc_info=True)

    def _on_error(self, error_msg: str):
        """Handle error signal"""
        try:
            logger.error(f"Error signal received: {error_msg}")
            QMessageBox.critical(self, "Error", error_msg)
            self.reset_ui()
        except Exception as e:
            logger.error(f"[_on_error] Failed: {e}", exc_info=True)

    def _on_operation_started(self):
        """Handle operation started signal"""
        try:
            # Disable close button or any other UI elements if needed
            pass
        except Exception as e:
            logger.error(f"[_on_operation_started] Failed: {e}", exc_info=True)

    def _on_operation_finished(self):
        """Handle operation finished signal"""
        try:
            # Re-enable UI elements if needed
            pass
        except Exception as e:
            logger.error(f"[_on_operation_finished] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info("[FyersManualLoginPopup] Starting cleanup")

            # Stop worker if running
            if self.token_worker and self.token_worker.isRunning():
                logger.info("Stopping token worker")
                self.token_worker.stop()
                if not self.token_worker.wait(3000):
                    logger.warning("Token worker did not stop gracefully, terminating")
                    self.token_worker.terminate()
                    self.token_worker.wait(1000)

            # Clear references
            self.token_worker = None
            self.fyers = None
            self.brokerage_setting = None

            logger.info("[FyersManualLoginPopup] Cleanup completed")

        except Exception as e:
            logger.error(f"[FyersManualLoginPopup.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup"""
        try:
            self.cleanup()
            super().closeEvent(event)

        except Exception as e:
            logger.error(f"[FyersManualLoginPopup.closeEvent] Failed: {e}", exc_info=True)
            super().closeEvent(event)