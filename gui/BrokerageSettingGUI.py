# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QVBoxLayout, QLabel,
                             QWidget, QTabWidget, QFrame, QScrollArea)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
import threading


class BrokerageSettingGUI(QDialog):
    """
    # PYQT: Replaces Tkinter Toplevel with QDialog.
    Class name preserved — all callers use BrokerageSettingGUI(parent, setting).
    """
    save_completed = pyqtSignal(bool, str)

    def __init__(self, parent, brokerage_setting):
        super().__init__(parent)
        self.brokerage_setting = brokerage_setting
        self.setWindowTitle("Brokerage Settings")
        self.setMinimumSize(520, 460)
        self.resize(520, 460)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog { background:#161b22; color:#e6edf3; }
            QLabel { color:#8b949e; }
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
            QPushButton {
                background:#238636; color:#fff; border-radius:4px; padding:10px;
                font-weight:bold; font-size:10pt;
            }
            QPushButton:hover { background:#2ea043; }
            QPushButton:pressed { background:#1e7a2f; }
            QPushButton:disabled { background:#21262d; color:#484f58; }
            QScrollArea { border: none; background: transparent; }
            QFrame#infoCard {
                background: #21262d;
                border: 1px solid #30363d;
                border-radius: 6px;
            }
        """)

        # Root layout
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Header
        header = QLabel("🔑 Brokerage API Settings")
        header.setFont(QFont("Segoe UI", 14, QFont.Bold))
        header.setStyleSheet("color:#e6edf3; padding:4px;")
        header.setAlignment(Qt.AlignCenter)
        root.addWidget(header)

        # Tab widget
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tabs.addTab(self._build_settings_tab(), "⚙️ Settings")
        self.tabs.addTab(self._build_info_tab(),     "ℹ️ Information")

        # Status + Save button (always visible below tabs)
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
        root.addWidget(self.status_label)

        self.save_btn = QPushButton("💾 Save Settings")
        self.save_btn.clicked.connect(self.save)
        root.addWidget(self.save_btn)

        self.save_completed.connect(self.on_save_completed)

    # ── Settings Tab ──────────────────────────────────────────────────────────
    def _build_settings_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(18, 18, 18, 10)
        layout.setSpacing(4)

        form = QFormLayout()
        form.setSpacing(6)
        form.setVerticalSpacing(3)
        form.setLabelAlignment(Qt.AlignRight)

        # Client ID
        self.client_id_edit = QLineEdit(self.brokerage_setting.client_id)
        self.client_id_edit.setPlaceholderText("e.g. ABCD1234-5678-EFGH")
        self.client_id_edit.setToolTip("Found in your brokerage developer portal under 'My Apps'.")
        client_id_hint = QLabel("Unique identifier for your registered brokerage app.")
        client_id_hint.setStyleSheet("color:#484f58; font-size:8pt;")

        # Secret Key
        self.secret_key_edit = QLineEdit(self.brokerage_setting.secret_key)
        self.secret_key_edit.setPlaceholderText("Paste your secret key here")
        self.secret_key_edit.setEchoMode(QLineEdit.Password)
        self.secret_key_edit.setToolTip("Keep this private — stored locally in config/brokerage_setting.json.")
        secret_key_hint = QLabel("Private key used to authenticate API requests. Keep it safe.")
        secret_key_hint.setStyleSheet("color:#484f58; font-size:8pt;")

        # Redirect URI
        self.redirect_edit = QLineEdit(self.brokerage_setting.redirect_uri)
        self.redirect_edit.setPlaceholderText("e.g. https://127.0.0.1:8182")
        self.redirect_edit.setToolTip("Must exactly match the URI registered in your brokerage developer portal.")
        redirect_hint = QLabel("Must match the redirect URI registered in your brokerage portal.")
        redirect_hint.setStyleSheet("color:#484f58; font-size:8pt;")

        form.addRow("🆔 Client ID:",    self.client_id_edit)
        form.addRow("",                 client_id_hint)
        form.addRow("🔑 Secret Key:",   self.secret_key_edit)
        form.addRow("",                 secret_key_hint)
        form.addRow("🔗 Redirect URI:", self.redirect_edit)
        form.addRow("",                 redirect_hint)

        layout.addLayout(form)
        layout.addStretch()
        return widget

    # ── Information Tab ───────────────────────────────────────────────────────
    def _build_info_tab(self):
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
                "• Stored locally on disk at: config/brokerage_setting.json\n"
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
                "📁  Where are settings stored?",
                "Your credentials are saved locally to:\n\n"
                "    config/brokerage_setting.json\n\n"
                "The file is written atomically (via a temp file) to prevent corruption. "
                "Make sure this path is excluded from any public repositories."
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

    # ── Feedback helpers ──────────────────────────────────────────────────────
    def show_success_feedback(self, message="✓ Settings saved successfully!"):
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
        original_text = self.save_btn.text()
        self.save_btn.setText("✓ Saved!")
        self.save_btn.setStyleSheet(
            "QPushButton { background:#2ea043; color:#fff; border-radius:4px; padding:10px; }"
        )
        QTimer.singleShot(2000, lambda: self.reset_save_button(original_text))

    def show_error_feedback(self, error_msg):
        self.status_label.setText(f"✗ {error_msg}")
        self.status_label.setStyleSheet("color:#f85149; font-size:9pt; font-weight:bold;")
        self.save_btn.setStyleSheet(
            "QPushButton { background:#f85149; color:#fff; border-radius:4px; padding:10px; }"
        )
        QTimer.singleShot(1000, lambda: self.reset_save_button("💾 Save Settings"))

    def reset_save_button(self, text):
        self.save_btn.setText(text)
        self.save_btn.setStyleSheet("""
            QPushButton { background:#238636; color:#fff; border-radius:4px; padding:10px; }
            QPushButton:hover { background:#2ea043; }
        """)

    # ── Save logic ────────────────────────────────────────────────────────────
    def save(self):
        client_id    = self.client_id_edit.text().strip()
        secret_key   = self.secret_key_edit.text().strip()
        redirect_uri = self.redirect_edit.text().strip()

        if not all([client_id, secret_key, redirect_uri]):
            self.tabs.setCurrentIndex(0)   # jump back to Settings tab on error
            self.show_error_feedback("All fields are required")
            return

        self.save_btn.setEnabled(False)
        self.save_btn.setText("⏳ Saving...")
        self.status_label.setText("")

        def _save():
            try:
                self.brokerage_setting.client_id   = client_id
                self.brokerage_setting.secret_key   = secret_key
                self.brokerage_setting.redirect_uri = redirect_uri
                success = self.brokerage_setting.save()
                if success:
                    self.save_completed.emit(True,  "Settings saved successfully!")
                else:
                    self.save_completed.emit(False, "Failed to save settings to file")
            except Exception as e:
                self.save_completed.emit(False, str(e))

        threading.Thread(target=_save, daemon=True).start()

    def on_save_completed(self, success, message):
        if success:
            self.show_success_feedback()
            self.save_btn.setEnabled(True)
            QTimer.singleShot(1500, self.accept)
        else:
            self.show_error_feedback(f"Failed to save: {message}")
            self.save_btn.setEnabled(True)