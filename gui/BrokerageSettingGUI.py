# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QMessageBox, QVBoxLayout, QLabel)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
import threading


class BrokerageSettingGUI(QDialog):
    """
    # PYQT: Replaces Tkinter Toplevel with QDialog.
    Class name preserved — all callers use BrokerageSettingGUI(parent, setting).
    """

    def __init__(self, parent, brokerage_setting):
        super().__init__(parent)
        self.brokerage_setting = brokerage_setting
        self.setWindowTitle("Brokerage Settings")
        self.setFixedSize(420, 250)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog { background:#161b22; color:#e6edf3; }
            QLabel { color:#8b949e; }
            QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                       border-radius:4px; padding:8px; font-size:10pt; }
            QLineEdit:focus { border:2px solid #58a6ff; }
            QPushButton { background:#238636; color:#fff; border-radius:4px; padding:10px;
                         font-weight:bold; font-size:10pt; }
            QPushButton:hover { background:#2ea043; }
            QPushButton:pressed { background:#1e7a2f; }
            QPushButton:disabled { background:#21262d; color:#484f58; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Header
        header = QLabel("🔑 Brokerage API Settings")
        header.setFont(QFont("Segoe UI", 14, QFont.Bold))
        header.setStyleSheet("color: #e6edf3; padding: 5px;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        self.client_id_edit = QLineEdit(brokerage_setting.client_id)
        self.client_id_edit.setPlaceholderText("Enter your client ID")
        self.secret_key_edit = QLineEdit(brokerage_setting.secret_key)
        self.secret_key_edit.setPlaceholderText("Enter your secret key")
        self.secret_key_edit.setEchoMode(QLineEdit.Password)
        self.redirect_edit = QLineEdit(brokerage_setting.redirect_uri)
        self.redirect_edit.setPlaceholderText("Enter redirect URI")

        form.addRow("🆔 Client ID:", self.client_id_edit)
        form.addRow("🔑 Secret Key:", self.secret_key_edit)
        form.addRow("🔗 Redirect URI:", self.redirect_edit)
        layout.addLayout(form)

        # Status label for save feedback
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #3fb950; font-size: 9pt; font-weight: bold;")
        layout.addWidget(self.status_label)

        # Save button with loading state
        self.save_btn = QPushButton("💾 Save Settings")
        self.save_btn.clicked.connect(self.save)
        layout.addWidget(self.save_btn)

    def show_success_feedback(self, message="✓ Settings saved successfully!"):
        """# PYQT: Show success message and auto-hide after 2 seconds"""
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #3fb950; font-size: 9pt; font-weight: bold;")

        # Change button temporarily to show success
        original_text = self.save_btn.text()
        self.save_btn.setText("✓ Saved!")
        self.save_btn.setStyleSheet("""
            QPushButton { background:#2ea043; color:#fff; border-radius:4px; padding:10px; }
        """)

        # Reset after 2 seconds
        QTimer.singleShot(2000, lambda: self.reset_save_button(original_text))

    def show_error_feedback(self, error_msg):
        """# PYQT: Show error message"""
        self.status_label.setText(f"✗ {error_msg}")
        self.status_label.setStyleSheet("color: #f85149; font-size: 9pt; font-weight: bold;")

        # Flash button red
        self.save_btn.setStyleSheet("""
            QPushButton { background:#f85149; color:#fff; border-radius:4px; padding:10px; }
        """)
        QTimer.singleShot(1000, lambda: self.reset_save_button("💾 Save Settings"))

    def reset_save_button(self, text):
        """# PYQT: Reset button to normal state"""
        self.save_btn.setText(text)
        self.save_btn.setStyleSheet("""
            QPushButton { background:#238636; color:#fff; border-radius:4px; padding:10px; }
            QPushButton:hover { background:#2ea043; }
        """)

    def save(self):
        client_id = self.client_id_edit.text().strip()
        secret_key = self.secret_key_edit.text().strip()
        redirect_uri = self.redirect_edit.text().strip()

        if not all([client_id, secret_key, redirect_uri]):
            self.show_error_feedback("All fields are required")
            return

        # Disable button during save
        self.save_btn.setEnabled(False)
        self.save_btn.setText("⏳ Saving...")
        self.status_label.setText("")  # Clear any previous status

        def _save():
            try:
                # Simulate small delay to show saving state (remove in production)
                import time
                time.sleep(0.5)

                self.brokerage_setting.client_id = client_id
                self.brokerage_setting.secret_key = secret_key
                self.brokerage_setting.redirect_uri = redirect_uri
                self.brokerage_setting.save()

                # Show success and close after delay
                QTimer.singleShot(0, lambda: self.save_success())
            except Exception as e:
                QTimer.singleShot(0, lambda: self.save_error(str(e)))

        threading.Thread(target=_save, daemon=True).start()

    def save_success(self):
        """# PYQT: Handle successful save"""
        self.show_success_feedback()
        self.save_btn.setEnabled(True)
        # Close after showing success
        QTimer.singleShot(1500, self.accept)

    def save_error(self, error_msg):
        """# PYQT: Handle save error"""
        self.show_error_feedback(f"Failed to save: {error_msg}")
        self.save_btn.setEnabled(True)