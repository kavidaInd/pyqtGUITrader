# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTextEdit,
                              QPushButton, QLineEdit, QHBoxLayout, QMessageBox)
from PyQt5.QtCore import Qt
from urllib.parse import urlparse, parse_qs
import webbrowser
import logging

from Utils.FyersManualLoginHelper import FyersManualLoginHelper

logger = logging.getLogger(__name__)


class FyersManualLoginPopup(QDialog):
    def __init__(self, parent, brokerage_setting):
        super().__init__(parent)
        self.brokerage_setting = brokerage_setting
        self.setWindowTitle("Fyers Manual Login")
        self.setFixedSize(540, 300)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog { background:#161b22; color:#e6edf3; }
            QLabel { color:#8b949e; }
            QTextEdit, QLineEdit { background:#21262d; color:#e6edf3;
                                   border:1px solid #30363d; border-radius:4px; padding:6px; }
            QPushButton { background:#238636; color:#fff; border-radius:4px; padding:8px; }
            QPushButton:hover { background:#2ea043; }
        """)

        layout = QVBoxLayout(self)

        # Step 1
        layout.addWidget(QLabel("Step 1: Open the login URL in your browser and authorize."))

        self.url_text = QTextEdit()
        self.url_text.setMaximumHeight(60)
        self.url_text.setReadOnly(True)
        layout.addWidget(self.url_text)

        open_btn = QPushButton("🌐 Open Login URL")
        open_btn.clicked.connect(self.open_login_url)
        layout.addWidget(open_btn, alignment=Qt.AlignRight)

        # Step 2
        layout.addWidget(QLabel("Step 2: Paste the full redirected URL (or just the code) here:"))

        self.code_entry = QLineEdit()
        layout.addWidget(self.code_entry)

        btn_layout = QHBoxLayout()
        self.login_btn = QPushButton("🔒 Complete Login")
        self.login_btn.clicked.connect(self.exchange_code)

        clear_btn = QPushButton("✖ Clear")
        clear_btn.clicked.connect(lambda: self.code_entry.clear())

        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(self.login_btn)
        layout.addLayout(btn_layout)

        self.fyers = None
        self.login_url = None
        self.init_login_url()

    def init_login_url(self):
        try:
            self.fyers = FyersManualLoginHelper(
                client_id=self.brokerage_setting.client_id,
                secret_key=self.brokerage_setting.secret_key,
                redirect_uri=self.brokerage_setting.redirect_uri
            )
            self.login_url = self.fyers.generate_login_url()
            self.url_text.setText(self.login_url)
        except Exception as e:
            logger.critical(f"Failed to generate login URL: {e!r}")
            QMessageBox.critical(self, "Error", f"Failed to generate login URL: {e}")
            self.reject()

    def open_login_url(self):
        if self.login_url:
            try:
                webbrowser.open(self.login_url)
            except Exception as e:
                logger.error(f"Failed to open URL in browser: {e}")
                QMessageBox.critical(self, "Error", "Failed to open URL in browser.")
        else:
            QMessageBox.critical(self, "Error", "Login URL is unavailable.")

    def exchange_code(self):
        code_or_url = self.code_entry.text().strip()
        if not code_or_url:
            QMessageBox.warning(self, "Input Needed", "Please paste the auth code or full URL.")
            return

        auth_code = self.extract_auth_code(code_or_url)
        if not auth_code:
            QMessageBox.critical(
                self, "Error",
                "Could not extract auth code. Please paste the full redirected URL or just the code."
            )
            return

        try:
            token = self.fyers.exchange_code_for_token(auth_code)
            if not token:
                logger.error("Failed to retrieve token.")
                QMessageBox.critical(
                    self, "Error",
                    "Failed to retrieve token. Please check the auth code and try again."
                )
                return

            logger.info(f"Token received: {token}")
            QMessageBox.information(self, "Success", "Login successful! Token received.")
            self.accept()
        except Exception as e:
            logger.critical(f"Exception during token exchange: {e!r}")
            QMessageBox.critical(self, "Error", f"Exception during token exchange: {e}")

    @staticmethod
    def extract_auth_code(input_text):
        if "=" not in input_text and "http" not in input_text:
            return input_text.strip()

        try:
            if "auth_code=" in input_text:
                parsed = urlparse(input_text)
                query = parsed.query or parsed.fragment
                params = parse_qs(query)
                return params.get("auth_code", [None])[0]
        except Exception:
            return None
        return None