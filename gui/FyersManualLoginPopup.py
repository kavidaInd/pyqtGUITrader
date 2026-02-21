# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTextEdit,
                             QPushButton, QLineEdit, QHBoxLayout, QMessageBox,
                             QProgressBar, QApplication)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from urllib.parse import urlparse, parse_qs, urlunparse
import webbrowser
import logging
import re

from Utils.FyersManualLoginHelper import FyersManualLoginHelper

logger = logging.getLogger(__name__)


class TokenExchangeWorker(QThread):
    """Worker thread for token exchange to prevent UI freezing"""
    finished = pyqtSignal(object, str)  # token, error message
    progress = pyqtSignal(int, str)  # progress percentage, status message

    def __init__(self, fyers_helper, auth_code):
        super().__init__()
        self.fyers_helper = fyers_helper
        self.auth_code = auth_code

    def run(self):
        try:
            self.progress.emit(30, "Exchanging code for token...")
            token = self.fyers_helper.exchange_code_for_token(self.auth_code)
            self.progress.emit(100, "Token received")

            if token:
                self.finished.emit(token, None)
            else:
                self.finished.emit(None, "Failed to retrieve token")
        except Exception as e:
            logger.error(f"Token exchange error: {e!r}")
            self.finished.emit(None, str(e))


class FyersManualLoginPopup(QDialog):
    # Signal for successful login with token
    login_completed = pyqtSignal(object)  # token object

    def __init__(self, parent, brokerage_setting):
        super().__init__(parent)
        self.brokerage_setting = brokerage_setting
        self.setWindowTitle("Fyers Manual Login")
        self.setFixedSize(600, 400)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog { 
                background: #161b22; 
                color: #e6edf3; 
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel { 
                color: #8b949e; 
                font-size: 10pt;
            }
            QLabel.step-label {
                color: #58a6ff;
                font-weight: bold;
                font-size: 11pt;
                margin-top: 10px;
            }
            QTextEdit, QLineEdit { 
                background: #21262d; 
                color: #e6edf3;
                border: 1px solid #30363d; 
                border-radius: 4px; 
                padding: 8px;
                font-family: 'Consolas', monospace;
                font-size: 9pt;
            }
            QTextEdit:focus, QLineEdit:focus {
                border: 2px solid #58a6ff;
            }
            QPushButton { 
                background: #238636; 
                color: #fff; 
                border-radius: 4px; 
                padding: 8px 12px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover { 
                background: #2ea043; 
            }
            QPushButton:pressed {
                background: #1e7a2f;
            }
            QPushButton:disabled {
                background: #21262d;
                color: #484f58;
            }
            QPushButton.secondary {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
            }
            QPushButton.secondary:hover {
                background: #30363d;
            }
            QProgressBar {
                border: 1px solid #30363d;
                border-radius: 4px;
                text-align: center;
                color: #e6edf3;
                background: #21262d;
                height: 20px;
            }
            QProgressBar::chunk {
                background: #238636;
                border-radius: 3px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title = QLabel("🔐 Fyers Manual Authentication")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #e6edf3; padding: 5px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Step 1
        step1_label = QLabel("Step 1: Open the login URL and authorize")
        step1_label.setProperty("class", "step-label")
        layout.addWidget(step1_label)

        # URL display with copy button
        url_layout = QHBoxLayout()
        self.url_text = QTextEdit()
        self.url_text.setMaximumHeight(60)
        self.url_text.setReadOnly(True)
        url_layout.addWidget(self.url_text, 1)

        copy_btn = QPushButton("📋 Copy")
        copy_btn.setMaximumWidth(80)
        copy_btn.clicked.connect(self.copy_url_to_clipboard)
        url_layout.addWidget(copy_btn)

        layout.addLayout(url_layout)

        # Open URL button
        open_btn = QPushButton("🌐 Open Login URL in Browser")
        open_btn.clicked.connect(self.open_login_url)
        layout.addWidget(open_btn, alignment=Qt.AlignRight)

        # Step 2
        step2_label = QLabel("Step 2: Paste the redirected URL or auth code")
        step2_label.setProperty("class", "step-label")
        layout.addWidget(step2_label)

        # Instructions
        instructions = QLabel(
            "After authorizing, you'll be redirected to a URL.\n"
            "Paste the ENTIRE redirected URL below, or just the auth code if you have it."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #8b949e; font-size: 9pt; padding: 5px;")
        layout.addWidget(instructions)

        # Code entry with paste hint
        self.code_entry = QLineEdit()
        self.code_entry.setPlaceholderText("Paste full URL or auth code here...")
        layout.addWidget(self.code_entry)

        # Progress bar (initially hidden)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximum(100)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #8b949e; font-size: 9pt;")
        layout.addWidget(self.status_label)

        # Buttons
        btn_layout = QHBoxLayout()

        self.clear_btn = QPushButton("✖ Clear")
        self.clear_btn.setProperty("class", "secondary")
        self.clear_btn.clicked.connect(lambda: self.code_entry.clear())

        self.login_btn = QPushButton("🔒 Complete Login")
        self.login_btn.clicked.connect(self.exchange_code)

        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setProperty("class", "secondary")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.login_btn)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

        # Initialize
        self.fyers = None
        self.login_url = None
        self.token_worker = None
        self.init_login_url()

    def init_login_url(self):
        """Initialize Fyers helper and generate login URL"""
        try:
            # Validate settings first
            if not self.brokerage_setting.client_id:
                raise ValueError("Client ID is missing")
            if not self.brokerage_setting.secret_key:
                raise ValueError("Secret Key is missing")
            if not self.brokerage_setting.redirect_uri:
                raise ValueError("Redirect URI is missing")

            self.fyers = FyersManualLoginHelper(
                client_id=self.brokerage_setting.client_id,
                secret_key=self.brokerage_setting.secret_key,
                redirect_uri=self.brokerage_setting.redirect_uri
            )
            self.login_url = self.fyers.generate_login_url()
            self.url_text.setText(self.login_url)
            self.status_label.setText("✅ Login URL generated successfully")

        except Exception as e:
            error_msg = f"Failed to generate login URL: {e!r}"
            logger.critical(error_msg)
            self.status_label.setText(f"❌ {error_msg}")
            QMessageBox.critical(self, "Error", error_msg)
            self.reject()

    def copy_url_to_clipboard(self):
        """Copy login URL to clipboard"""
        if self.login_url:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.login_url)
            self.status_label.setText("📋 URL copied to clipboard")
            QTimer.singleShot(2000, lambda: self.status_label.setText(""))
        else:
            QMessageBox.warning(self, "Warning", "No URL to copy")

    def open_login_url(self):
        """Open login URL in default browser"""
        if self.login_url:
            try:
                webbrowser.open(self.login_url)
                self.status_label.setText("🌐 Browser opened")
            except Exception as e:
                logger.error(f"Failed to open URL in browser: {e}")
                QMessageBox.critical(self, "Error", "Failed to open URL in browser.")
        else:
            QMessageBox.critical(self, "Error", "Login URL is unavailable.")

    def extract_auth_code(self, input_text: str) -> str:
        """
        Extract auth code from various input formats.
        More robust version handling different URL patterns.
        """
        if not input_text:
            return ""

        input_text = input_text.strip()

        # If it's just the code (no URL parts)
        if re.match(r'^[A-Za-z0-9\-_]+$', input_text):
            return input_text

        # Try to parse as URL
        try:
            # Clean up the URL if it has fragments
            if "access_token" in input_text:
                # This might be a token directly, not a code
                return ""

            parsed = urlparse(input_text)

            # Check query parameters
            if parsed.query:
                params = parse_qs(parsed.query)
                for key in ['auth_code', 'code', 'authorization_code']:
                    if key in params and params[key]:
                        return params[key][0]

            # Check fragment parameters
            if parsed.fragment:
                fragment_params = parse_qs(parsed.fragment)
                for key in ['auth_code', 'code', 'authorization_code']:
                    if key in fragment_params and fragment_params[key]:
                        return fragment_params[key][0]

            # If no auth code found but input looks like a URL, maybe the whole thing is the code?
            if "?" not in input_text and "=" not in input_text:
                return input_text

        except Exception as e:
            logger.debug(f"URL parsing failed: {e}")

        return ""

    def exchange_code(self):
        """Exchange auth code for token in background thread"""
        code_or_url = self.code_entry.text().strip()
        if not code_or_url:
            QMessageBox.warning(self, "Input Needed", "Please paste the auth code or full URL.")
            return

        # Extract auth code
        auth_code = self.extract_auth_code(code_or_url)
        if not auth_code:
            QMessageBox.critical(
                self, "Error",
                "Could not extract auth code. Please paste the full redirected URL or just the code."
            )
            return

        # Validate auth code format (basic check)
        if len(auth_code) < 10:
            QMessageBox.critical(
                self, "Error",
                "Auth code seems too short. Please check and try again."
            )
            return

        # Update UI for processing
        self.login_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(10)
        self.status_label.setText("⏳ Processing authentication...")

        # Create and start worker thread
        self.token_worker = TokenExchangeWorker(self.fyers, auth_code)
        self.token_worker.progress.connect(self.update_progress)
        self.token_worker.finished.connect(self.on_token_exchange_complete)
        self.token_worker.start()

    def update_progress(self, percentage: int, message: str):
        """Update progress bar and status message"""
        self.progress_bar.setValue(percentage)
        self.status_label.setText(f"⏳ {message}")

    def on_token_exchange_complete(self, token, error):
        """Handle token exchange completion"""
        # Clean up worker
        if self.token_worker:
            self.token_worker.deleteLater()
            self.token_worker = None

        if error:
            # Error case
            logger.error(f"Token exchange failed: {error}")
            self.status_label.setText(f"❌ Login failed: {error}")
            QMessageBox.critical(
                self, "Login Failed",
                f"Failed to retrieve token. Error: {error}\n\nPlease check your auth code and try again."
            )
            self.reset_ui()
            return

        if token:
            # Success case - DO NOT log the actual token
            logger.info("✓ Token received successfully")
            self.status_label.setText("✅ Login successful!")
            self.progress_bar.setValue(100)

            # Emit the token
            self.login_completed.emit(token)

            # Show success message
            QMessageBox.information(
                self, "Success",
                "Login successful! Token has been received and will be used for trading."
            )

            # Close dialog
            QTimer.singleShot(500, self.accept)
        else:
            # Empty token case
            self.status_label.setText("❌ Failed to retrieve token")
            QMessageBox.critical(
                self, "Error",
                "Failed to retrieve token. The auth code might be invalid or expired."
            )
            self.reset_ui()

    def reset_ui(self):
        """Reset UI to initial state"""
        self.login_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        # Don't clear the entry so user can try again

    def closeEvent(self, event):
        """Clean up when dialog is closed"""
        if self.token_worker and self.token_worker.isRunning():
            self.token_worker.terminate()
            self.token_worker.wait()
        super().closeEvent(event)
