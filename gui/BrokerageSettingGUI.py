import logging
import threading

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QVBoxLayout, QLabel,
                             QWidget, QTabWidget, QFrame, QScrollArea,
                             QHBoxLayout, QCheckBox, QGroupBox)

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class BrokerageSettingGUI(QDialog):
    """
    # PYQT: Replaces Tkinter Toplevel with QDialog.
    Enhanced with Telegram notification settings (FEATURE 4).
    """
    save_completed = pyqtSignal(bool, str)

    # Rule 3: Additional signals for error handling
    error_occurred = pyqtSignal(str)
    operation_started = pyqtSignal()
    operation_finished = pyqtSignal()

    def __init__(self, parent, brokerage_setting):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.brokerage_setting = brokerage_setting

            # Rule 6: Input validation
            if brokerage_setting is None:
                logger.error("BrokerageSettingGUI initialized with None brokerage_setting")

            self.setWindowTitle("Settings")
            self.setMinimumSize(620, 560)  # Increased height for new tab
            self.resize(620, 560)
            self.setModal(True)

            # EXACT stylesheet preservation with enhancements for new widgets
            self.setStyleSheet("""
                QDialog { background:#161b22; color:#e6edf3; }
                QLabel { color:#8b949e; }
                QGroupBox {
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    margin-top: 10px;
                    font-weight: bold;
                    color: #e6edf3;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px 0 5px;
                }
                QTabWidget::pane {
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    background: #161b22;
                }
                QTabBar::tab {
                    background: #21262d;
                    color: #8b949e;
                    padding: 8px 20px;
                    min-width: 130px;
                    border: 1px solid #30363d;
                    border-bottom: none;
                    border-radius: 4px 4px 0 0;
                    font-size: 10pt;
                }
                QTabBar::tab:selected {
                    background: #161b22;
                    color: #e6edf3;
                    border-bottom: 2px solid #58a6ff;
                    font-weight: bold;
                }
                QTabBar::tab:hover:!selected { background: #30363d; color: #e6edf3; }
                QLineEdit {
                    background:#21262d; color:#e6edf3; border:1px solid #30363d;
                    border-radius:4px; padding:8px; font-size:10pt;
                }
                QLineEdit:focus { border:2px solid #58a6ff; }
                QLineEdit:disabled {
                    background: #161b22;
                    color: #484f58;
                    border: 1px solid #21262d;
                }
                QCheckBox {
                    color: #e6edf3;
                    spacing: 8px;
                }
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                    border: 1px solid #30363d;
                    border-radius: 3px;
                    background: #21262d;
                }
                QCheckBox::indicator:checked {
                    background: #238636;
                    border: 1px solid #2ea043;
                }
                QCheckBox::indicator:checked:hover {
                    background: #2ea043;
                }
                QCheckBox::indicator:hover {
                    border: 1px solid #58a6ff;
                }
                QPushButton {
                    background:#238636; color:#fff; border-radius:4px; padding:10px;
                    font-weight:bold; font-size:10pt;
                }
                QPushButton:hover { background:#2ea043; }
                QPushButton:pressed { background:#1e7a2f; }
                QPushButton:disabled { background:#21262d; color:#484f58; }
                QPushButton#testBtn {
                    background: #1f6feb;
                }
                QPushButton#testBtn:hover {
                    background: #388bfd;
                }
                QScrollArea { border: none; background: transparent; }
                QFrame#infoCard {
                    background: #21262d;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                }
                QLabel#statusGood {
                    color: #3fb950;
                    font-size: 9pt;
                }
                QLabel#statusBad {
                    color: #f85149;
                    font-size: 9pt;
                }
            """)

            # Root layout
            root = QVBoxLayout(self)
            root.setContentsMargins(16, 16, 16, 16)
            root.setSpacing(12)

            # Header
            header = QLabel("⚙️ Application Settings")
            header.setFont(QFont("Segoe UI", 14, QFont.Bold))
            header.setStyleSheet("color:#e6edf3; padding:4px;")
            header.setAlignment(Qt.AlignCenter)
            root.addWidget(header)

            # Tab widget
            self.tabs = QTabWidget()
            root.addWidget(self.tabs)

            # Add tabs
            self.tabs.addTab(self._build_settings_tab(), "🔑 Brokerage")
            self.tabs.addTab(self._build_telegram_tab(), "📱 Notifications")  # FEATURE 4
            self.tabs.addTab(self._build_info_tab(), "ℹ️ Information")

            # Status + Save button (always visible below tabs)
            self.status_label = QLabel("")
            self.status_label.setAlignment(Qt.AlignCenter)
            self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
            root.addWidget(self.status_label)

            self.save_btn = QPushButton("💾 Save All Settings")
            self.save_btn.clicked.connect(self.save)
            root.addWidget(self.save_btn)

            self.save_completed.connect(self.on_save_completed)

            # Connect internal signals
            self._connect_signals()

            logger.info("BrokerageSettingGUI initialized")

        except Exception as e:
            logger.critical(f"[BrokerageSettingGUI.__init__] Failed: {e}", exc_info=True)
            # Still try to show a basic dialog
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.brokerage_setting = None
        self.tabs = None
        self.client_id_edit = None
        self.secret_key_edit = None
        self.redirect_edit = None
        self.telegram_token_edit = None
        self.telegram_chat_edit = None
        self.telegram_status_label = None
        self.test_telegram_btn = None
        self.status_label = None
        self.save_btn = None
        self._save_in_progress = False
        self._save_timer = None

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
        try:
            super().__init__(parent)
            self.setWindowTitle("Settings - ERROR")
            self.resize(400, 200)

            layout = QVBoxLayout(self)
            error_label = QLabel(f"❌ Failed to initialize settings dialog.\nPlease check the logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #f85149; padding: 20px; font-size: 12pt;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._create_error_dialog] Failed: {e}", exc_info=True)

    # ── Brokerage Settings Tab ────────────────────────────────────────────────
    def _build_settings_tab(self):
        """Build the brokerage settings tab with form fields"""
        widget = QWidget()
        try:
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(18, 18, 18, 10)
            layout.setSpacing(4)

            form = QFormLayout()
            form.setSpacing(6)
            form.setVerticalSpacing(3)
            form.setLabelAlignment(Qt.AlignRight)

            # Client ID
            initial_client_id = ""
            if self.brokerage_setting is not None and hasattr(self.brokerage_setting, 'client_id'):
                initial_client_id = self.brokerage_setting.client_id

            self.client_id_edit = QLineEdit(initial_client_id)
            self.client_id_edit.setPlaceholderText("e.g. ABCD1234-5678-EFGH")
            self.client_id_edit.setToolTip("Found in your brokerage developer portal under 'My Apps'.")
            client_id_hint = QLabel("Unique identifier for your registered brokerage app.")
            client_id_hint.setStyleSheet("color:#484f58; font-size:8pt;")

            # Secret Key
            initial_secret = ""
            if self.brokerage_setting is not None and hasattr(self.brokerage_setting, 'secret_key'):
                initial_secret = self.brokerage_setting.secret_key

            self.secret_key_edit = QLineEdit(initial_secret)
            self.secret_key_edit.setPlaceholderText("Paste your secret key here")
            self.secret_key_edit.setEchoMode(QLineEdit.Password)
            self.secret_key_edit.setToolTip("Keep this private — stored locally in database.")
            secret_key_hint = QLabel("Private key used to authenticate API requests. Keep it safe.")
            secret_key_hint.setStyleSheet("color:#484f58; font-size:8pt;")

            # Redirect URI
            initial_redirect = ""
            if self.brokerage_setting is not None and hasattr(self.brokerage_setting, 'redirect_uri'):
                initial_redirect = self.brokerage_setting.redirect_uri

            self.redirect_edit = QLineEdit(initial_redirect)
            self.redirect_edit.setPlaceholderText("e.g. https://127.0.0.1:8182")
            self.redirect_edit.setToolTip("Must exactly match the URI registered in your brokerage developer portal.")
            redirect_hint = QLabel("Must match the redirect URI registered in your brokerage portal.")
            redirect_hint.setStyleSheet("color:#484f58; font-size:8pt;")

            form.addRow("🆔 Client ID:", self.client_id_edit)
            form.addRow("", client_id_hint)
            form.addRow("🔑 Secret Key:", self.secret_key_edit)
            form.addRow("", secret_key_hint)
            form.addRow("🔗 Redirect URI:", self.redirect_edit)
            form.addRow("", redirect_hint)

            layout.addLayout(form)
            layout.addStretch()

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._build_settings_tab] Failed: {e}", exc_info=True)
            error_label = QLabel("Error building settings tab")
            error_label.setStyleSheet("color: #f85149;")
            layout = QVBoxLayout(widget)
            layout.addWidget(error_label)

        return widget

    # ── FEATURE 4: Telegram Notifications Tab ────────────────────────────────
    def _build_telegram_tab(self):
        """Build the Telegram notification settings tab"""
        widget = QWidget()
        try:
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(15)

            # Header with description
            desc_label = QLabel(
                "Receive real-time notifications about trades, risk breaches, "
                "and connection status via Telegram."
            )
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #8b949e; font-size: 10pt; padding: 5px;")
            layout.addWidget(desc_label)

            # Settings Group
            settings_group = QGroupBox("Telegram Configuration")
            settings_layout = QFormLayout(settings_group)
            settings_layout.setSpacing(10)
            settings_layout.setLabelAlignment(Qt.AlignRight)

            # Bot Token
            initial_token = ""
            if self.brokerage_setting is not None and hasattr(self.brokerage_setting, 'telegram_bot_token'):
                initial_token = self.brokerage_setting.telegram_bot_token

            self.telegram_token_edit = QLineEdit(initial_token)
            self.telegram_token_edit.setPlaceholderText("e.g. 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz")
            self.telegram_token_edit.setToolTip("Get this from @BotFather on Telegram")
            settings_layout.addRow("🤖 Bot Token:", self.telegram_token_edit)

            token_hint = QLabel("Create a bot via @BotFather and paste the token here.")
            token_hint.setStyleSheet("color:#484f58; font-size:8pt;")
            settings_layout.addRow("", token_hint)

            # Chat ID
            initial_chat = ""
            if self.brokerage_setting is not None and hasattr(self.brokerage_setting, 'telegram_chat_id'):
                initial_chat = self.brokerage_setting.telegram_chat_id

            self.telegram_chat_edit = QLineEdit(initial_chat)
            self.telegram_chat_edit.setPlaceholderText("e.g. 123456789")
            self.telegram_chat_edit.setToolTip("Your personal chat ID with the bot")
            settings_layout.addRow("👤 Chat ID:", self.telegram_chat_edit)

            chat_hint = QLabel(
                "Send a message to your bot, then visit https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates to find your chat ID.")
            chat_hint.setWordWrap(True)
            chat_hint.setStyleSheet("color:#484f58; font-size:8pt;")
            settings_layout.addRow("", chat_hint)

            layout.addWidget(settings_group)

            # Status and Test Group
            test_group = QGroupBox("Connection Test")
            test_layout = QVBoxLayout(test_group)

            self.telegram_status_label = QLabel("Not configured")
            self.telegram_status_label.setObjectName("statusBad")
            test_layout.addWidget(self.telegram_status_label)

            test_button_layout = QHBoxLayout()
            self.test_telegram_btn = QPushButton("📱 Test Telegram")
            self.test_telegram_btn.setObjectName("testBtn")
            self.test_telegram_btn.clicked.connect(self._test_telegram)
            test_button_layout.addWidget(self.test_telegram_btn)

            test_button_layout.addStretch()
            test_layout.addLayout(test_button_layout)

            layout.addWidget(test_group)

            # Info Card
            info_card = QFrame()
            info_card.setObjectName("infoCard")
            info_layout = QVBoxLayout(info_card)
            info_layout.setContentsMargins(14, 12, 14, 12)

            info_title = QLabel("📘 How to set up Telegram notifications:")
            info_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
            info_title.setStyleSheet("color:#e6edf3;")

            info_text = QLabel(
                "1. Open Telegram and search for @BotFather\n"
                "2. Send /newbot and follow instructions to create a bot\n"
                "3. Copy the bot token and paste it above\n"
                "4. Start a chat with your new bot and send any message\n"
                "5. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates\n"
                "6. Find your chat ID in the response and paste it above\n\n"
                "You'll receive notifications for:\n"
                "• Trade entries and exits\n"
                "• Risk limit breaches\n"
                "• WebSocket connection status\n"
                "• Token expiry warnings"
            )
            info_text.setWordWrap(True)
            info_text.setStyleSheet("color:#8b949e; font-size:9pt;")

            info_layout.addWidget(info_title)
            info_layout.addWidget(info_text)
            layout.addWidget(info_card)

            layout.addStretch()

            # Update status
            self._update_telegram_status()

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._build_telegram_tab] Failed: {e}", exc_info=True)
            error_label = QLabel("Error building Telegram tab")
            error_label.setStyleSheet("color: #f85149;")
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
                    "🆔  Client ID",
                    "A unique public identifier assigned to your application when you register it "
                    "in your brokerage's developer portal.\n\n"
                    "• It is not secret — it can appear in URLs and logs.\n"
                    "• Used by the brokerage to identify which app is making a request.\n"
                    "• Where to find it: Developer Portal → My Apps → App Details."
                ),
                (
                    "🔑  Secret Key",
                    "A private credential paired with your Client ID. Together they prove your "
                    "application's identity to the brokerage's OAuth server.\n\n"
                    "• Treat it like a password — never share or commit it to version control.\n"
                    "• Stored locally in the database.\n"
                    "• If compromised, regenerate it immediately in your developer portal."
                ),
                (
                    "🔗  Redirect URI",
                    "The URL the brokerage redirects your browser to after the user logs in and "
                    "grants permission. The app listens on this address to receive the auth code.\n\n"
                    "• Must exactly match (character-for-character) what is registered in your portal.\n"
                    "• For local use a loopback address is typical, e.g. https://127.0.0.1:8182\n"
                    "• Mismatches are the most common cause of OAuth login failures."
                ),
                (
                    "📱  Telegram Notifications",
                    "Get instant alerts about your trading activity on your phone.\n\n"
                    "• Entry/Exit notifications with P&L\n"
                    "• Risk limit breach alerts\n"
                    "• WebSocket connection status\n"
                    "• Token expiry warnings\n\n"
                    "Setup instructions are in the Telegram tab."
                ),
                (
                    "🗄️  Where are settings stored?",
                    "All settings are stored in the SQLite database at:\n\n"
                    "    config/trading.db\n\n"
                    "Credentials are encrypted at rest. Make sure this file is backed up "
                    "regularly and excluded from public repositories."
                ),
            ]

            for title, body in infos:
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

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._build_info_tab] Failed: {e}", exc_info=True)
            scroll = QScrollArea()
            container = QWidget()
            layout = QVBoxLayout(container)
            error_label = QLabel("Error building information tab")
            error_label.setStyleSheet("color: #f85149;")
            layout.addWidget(error_label)
            scroll.setWidget(container)
            return scroll

    # ── FEATURE 4: Telegram Test ─────────────────────────────────────────────
    def _test_telegram(self):
        """Test Telegram connection by sending a test message"""
        try:
            bot_token = self.telegram_token_edit.text().strip() if self.telegram_token_edit else ""
            chat_id = self.telegram_chat_edit.text().strip() if self.telegram_chat_edit else ""

            if not bot_token or not chat_id:
                self.telegram_status_label.setText("❌ Please enter both Bot Token and Chat ID")
                self.telegram_status_label.setObjectName("statusBad")
                self.telegram_status_label.style().unpolish(self.telegram_status_label)
                self.telegram_status_label.style().polish(self.telegram_status_label)
                return

            # Disable test button during test
            self.test_telegram_btn.setEnabled(False)
            self.test_telegram_btn.setText("⏳ Testing...")

            # Run test in background thread
            threading.Thread(target=self._threaded_test_telegram,
                             args=(bot_token, chat_id),
                             daemon=True).start()

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._test_telegram] Failed: {e}", exc_info=True)
            self.test_telegram_btn.setEnabled(True)
            self.test_telegram_btn.setText("📱 Test Telegram")

    def _threaded_test_telegram(self, bot_token: str, chat_id: str):
        """Test Telegram connection in background thread"""
        try:
            import requests

            # Send test message
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": "✅ *Test Message*\nYour Telegram notifications are working!",
                "parse_mode": "Markdown"
            }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                QTimer.singleShot(0, self._on_telegram_test_success)
            else:
                error_text = response.text
                QTimer.singleShot(0, lambda: self._on_telegram_test_failure(
                    f"HTTP {response.status_code}: {error_text[:100]}"))

        except requests.Timeout:
            QTimer.singleShot(0, lambda: self._on_telegram_test_failure("Connection timeout"))
        except requests.ConnectionError:
            QTimer.singleShot(0, lambda: self._on_telegram_test_failure("Network connection error"))
        except Exception as e:
            QTimer.singleShot(0, lambda: self._on_telegram_test_failure(str(e)))

    def _on_telegram_test_success(self):
        """Handle successful Telegram test"""
        self.telegram_status_label.setText("✅ Test successful! Check your Telegram.")
        self.telegram_status_label.setObjectName("statusGood")
        self.telegram_status_label.style().unpolish(self.telegram_status_label)
        self.telegram_status_label.style().polish(self.telegram_status_label)

        self.test_telegram_btn.setEnabled(True)
        self.test_telegram_btn.setText("📱 Test Telegram")

        # Auto-clear after 5 seconds
        QTimer.singleShot(5000, self._update_telegram_status)

    def _on_telegram_test_failure(self, error_msg: str):
        """Handle failed Telegram test"""
        self.telegram_status_label.setText(f"❌ Test failed: {error_msg}")
        self.telegram_status_label.setObjectName("statusBad")
        self.telegram_status_label.style().unpolish(self.telegram_status_label)
        self.telegram_status_label.style().polish(self.telegram_status_label)

        self.test_telegram_btn.setEnabled(True)
        self.test_telegram_btn.setText("📱 Test Telegram")

    def _update_telegram_status(self):
        """Update Telegram status based on current settings"""
        try:
            bot_token = self.telegram_token_edit.text().strip() if self.telegram_token_edit else ""
            chat_id = self.telegram_chat_edit.text().strip() if self.telegram_chat_edit else ""

            if bot_token and chat_id:
                self.telegram_status_label.setText("✅ Configured")
                self.telegram_status_label.setObjectName("statusGood")
            else:
                self.telegram_status_label.setText("❌ Not configured")
                self.telegram_status_label.setObjectName("statusBad")

            if self.telegram_status_label:
                self.telegram_status_label.style().unpolish(self.telegram_status_label)
                self.telegram_status_label.style().polish(self.telegram_status_label)

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._update_telegram_status] Failed: {e}", exc_info=True)

    # ── Feedback helpers ──────────────────────────────────────────────────────
    def show_success_feedback(self, message="✓ Settings saved successfully!"):
        """Show success feedback with animation"""
        try:
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
            original_text = self.save_btn.text() if self.save_btn is not None else "Save"
            if self.save_btn is not None:
                self.save_btn.setText("✓ Saved!")
                self.save_btn.setStyleSheet(
                    "QPushButton { background:#2ea043; color:#fff; border-radius:4px; padding:10px; }"
                )
            QTimer.singleShot(2000, lambda: self.reset_save_button(original_text))

            logger.info(f"Success feedback shown: {message}")

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI.show_success_feedback] Failed: {e}", exc_info=True)

    def show_error_feedback(self, error_msg):
        """Show error feedback with animation"""
        try:
            self.status_label.setText(f"✗ {error_msg}")
            self.status_label.setStyleSheet("color:#f85149; font-size:9pt; font-weight:bold;")
            if self.save_btn is not None:
                self.save_btn.setStyleSheet(
                    "QPushButton { background:#f85149; color:#fff; border-radius:4px; padding:10px; }"
                )
            QTimer.singleShot(1000, lambda: self.reset_save_button("💾 Save All Settings"))

            logger.warning(f"Error feedback shown: {error_msg}")

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI.show_error_feedback] Failed: {e}", exc_info=True)

    def reset_save_button(self, text):
        """Reset save button to normal state"""
        try:
            if self.save_btn is not None:
                self.save_btn.setText(text)
                self.save_btn.setStyleSheet("""
                    QPushButton { background:#238636; color:#fff; border-radius:4px; padding:10px; }
                    QPushButton:hover { background:#2ea043; }
                """)
        except Exception as e:
            logger.error(f"[BrokerageSettingGUI.reset_save_button] Failed: {e}", exc_info=True)

    # ── Save logic ────────────────────────────────────────────────────────────
    def save(self):
        """Save all settings with validation and background thread"""
        try:
            # Prevent multiple saves
            if self._save_in_progress:
                logger.warning("Save already in progress")
                return

            # Get values with validation
            client_id = self.client_id_edit.text().strip() if self.client_id_edit else ""
            secret_key = self.secret_key_edit.text().strip() if self.secret_key_edit else ""
            redirect_uri = self.redirect_edit.text().strip() if self.redirect_edit else ""

            # FEATURE 4: Get Telegram values
            telegram_token = self.telegram_token_edit.text().strip() if self.telegram_token_edit else ""
            telegram_chat = self.telegram_chat_edit.text().strip() if self.telegram_chat_edit else ""

            # Validate required fields (only brokerage fields are required)
            missing_fields = []
            if not client_id:
                missing_fields.append("Client ID")
            if not secret_key:
                missing_fields.append("Secret Key")
            if not redirect_uri:
                missing_fields.append("Redirect URI")

            if missing_fields:
                error_msg = f"Missing required fields: {', '.join(missing_fields)}"
                if self.tabs is not None:
                    self.tabs.setCurrentIndex(0)  # jump back to Settings tab on error
                self.show_error_feedback("All brokerage fields are required")
                logger.warning(error_msg)
                return

            # Update UI for save in progress
            self._save_in_progress = True
            self.operation_started.emit()

            if self.save_btn is not None:
                self.save_btn.setEnabled(False)
                self.save_btn.setText("⏳ Saving...")

            if self.status_label is not None:
                self.status_label.setText("")

            # Save in background thread
            threading.Thread(target=self._threaded_save,
                             args=(client_id, secret_key, redirect_uri, telegram_token, telegram_chat),
                             daemon=True, name="BrokerageSave").start()

            logger.info("Save operation started in background thread")

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI.save] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Save failed: {e}")
            self._save_in_progress = False
            self.operation_finished.emit()

    def _threaded_save(self, client_id: str, secret_key: str, redirect_uri: str,
                       telegram_token: str, telegram_chat: str):
        """Threaded save operation"""
        try:
            # Rule 6: Validate brokerage setting
            if self.brokerage_setting is None:
                raise ValueError("Brokerage setting object is None")

            # Update brokerage settings
            if hasattr(self.brokerage_setting, 'client_id'):
                self.brokerage_setting.client_id = client_id
            if hasattr(self.brokerage_setting, 'secret_key'):
                self.brokerage_setting.secret_key = secret_key
            if hasattr(self.brokerage_setting, 'redirect_uri'):
                self.brokerage_setting.redirect_uri = redirect_uri

            # FEATURE 4: Update Telegram settings
            if hasattr(self.brokerage_setting, 'telegram_bot_token'):
                self.brokerage_setting.telegram_bot_token = telegram_token
            if hasattr(self.brokerage_setting, 'telegram_chat_id'):
                self.brokerage_setting.telegram_chat_id = telegram_chat

            # Save to database
            success = False
            if hasattr(self.brokerage_setting, 'save'):
                success = self.brokerage_setting.save()
            else:
                logger.error("Brokerage setting object has no save method")

            if success:
                self.save_completed.emit(True, "Settings saved successfully!")
                logger.info("All settings saved successfully")
            else:
                self.save_completed.emit(False, "Failed to save settings to database")
                logger.error("Failed to save settings to database")

        except Exception as e:
            logger.error(f"Threaded save failed: {e}", exc_info=True)
            self.save_completed.emit(False, str(e))

        finally:
            self._save_in_progress = False
            self.operation_finished.emit()

    def on_save_completed(self, success, message):
        """Handle save completion"""
        try:
            if success:
                self.show_success_feedback()
                if self.save_btn is not None:
                    self.save_btn.setEnabled(True)
                QTimer.singleShot(1500, self.accept)
            else:
                self.show_error_feedback(f"Failed to save: {message}")
                if self.save_btn is not None:
                    self.save_btn.setEnabled(True)

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI.on_save_completed] Failed: {e}", exc_info=True)

    def _on_error(self, error_msg: str):
        """Handle error signal"""
        try:
            logger.error(f"Error signal received: {error_msg}")
            self.show_error_feedback(error_msg)
            if self.save_btn is not None:
                self.save_btn.setEnabled(True)
            self._save_in_progress = False
        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._on_error] Failed: {e}", exc_info=True)

    def _on_operation_started(self):
        """Handle operation started signal"""
        try:
            # Disable close button or any other UI elements if needed
            pass
        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._on_operation_started] Failed: {e}", exc_info=True)

    def _on_operation_finished(self):
        """Handle operation finished signal"""
        try:
            # Re-enable UI elements if needed
            pass
        except Exception as e:
            logger.error(f"[BrokerageSettingGUI._on_operation_finished] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info("[BrokerageSettingGUI] Starting cleanup")

            # Cancel any pending timers
            if hasattr(self, '_save_timer') and self._save_timer is not None:
                try:
                    if self._save_timer.isActive():
                        self._save_timer.stop()
                except Exception as e:
                    logger.warning(f"Error stopping timer: {e}")

            # Clear references
            self.brokerage_setting = None
            self.client_id_edit = None
            self.secret_key_edit = None
            self.redirect_edit = None
            self.telegram_token_edit = None
            self.telegram_chat_edit = None
            self.telegram_status_label = None
            self.test_telegram_btn = None
            self.status_label = None
            self.save_btn = None
            self.tabs = None

            logger.info("[BrokerageSettingGUI] Cleanup completed")

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup"""
        try:
            # Cancel save if in progress
            if self._save_in_progress:
                logger.warning("Closing while save in progress")

            self.cleanup()
            event.accept()

        except Exception as e:
            logger.error(f"[BrokerageSettingGUI.closeEvent] Failed: {e}", exc_info=True)
            event.accept()