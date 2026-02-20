# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QMessageBox, QVBoxLayout,
                             QComboBox, QHBoxLayout, QLabel, QGroupBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from gui.ProfitStoplossSetting import ProfitStoplossSetting
from BaseEnums import STOP, TRAILING
import threading


class ProfitStoplossSettingGUI(QDialog):
    def __init__(self, parent, profit_stoploss_setting: ProfitStoplossSetting, app=None):
        super().__init__(parent)
        self.profit_stoploss_setting = profit_stoploss_setting
        self.app = app
        self.setWindowTitle("Profit & Stoploss Settings")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setStyleSheet("""
            QDialog { background:#161b22; color:#e6edf3; }
            QGroupBox { color:#e6edf3; border:2px solid #30363d; border-radius:6px;
                        margin-top:1em; padding-top:15px; font-weight:bold; }
            QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 10px; }
            QLabel { color:#8b949e; }
            QLineEdit, QComboBox { background:#21262d; color:#e6edf3;
                                   border:1px solid #30363d; border-radius:4px; padding:8px;
                                   font-size:10pt; }
            QLineEdit:focus, QComboBox:focus { border:2px solid #58a6ff; }
            QPushButton { background:#238636; color:#fff; border-radius:4px; padding:12px;
                         font-weight:bold; font-size:10pt; }
            QPushButton:hover { background:#2ea043; }
            QPushButton:pressed { background:#1e7a2f; }
            QPushButton:disabled { background:#21262d; color:#484f58; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Header
        header = QLabel("💹 Profit & Stoploss Configuration")
        header.setFont(QFont("Segoe UI", 14, QFont.Bold))
        header.setStyleSheet("color: #e6edf3; padding: 10px;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Main settings group
        main_group = QGroupBox("Main Settings")
        main_layout = QFormLayout()
        main_layout.setSpacing(12)
        main_layout.setLabelAlignment(Qt.AlignRight)

        # Profit Type ComboBox
        self.profit_type_combo = QComboBox()
        self.profit_type_combo.addItem("STOP (Fixed Target)", STOP)
        self.profit_type_combo.addItem("TRAILING (Dynamic)", TRAILING)
        current = STOP if profit_stoploss_setting.profit_type == STOP else TRAILING
        self.profit_type_combo.setCurrentIndex(0 if current == STOP else 1)
        self.profit_type_combo.currentIndexChanged.connect(self._on_profit_type_change)
        main_layout.addRow("💰 Profit Type:", self.profit_type_combo)

        main_group.setLayout(main_layout)
        layout.addWidget(main_group)

        # Values group
        values_group = QGroupBox("Threshold Values")
        values_layout = QFormLayout()
        values_layout.setSpacing(12)
        values_layout.setLabelAlignment(Qt.AlignRight)

        self.vars = {}
        self.entries = {}

        fields = [
            ("Take Profit (%)", "tp_percentage", float, "💰"),
            ("Stoploss (%)", "stoploss_percentage", float, "🛑"),
            ("Trailing First Profit (%)", "trailing_first_profit", float, "📈"),
            ("Max Profit (%)", "max_profit", float, "🏆"),
            ("Profit Step (%)", "profit_step", float, "➕"),
            ("Loss Step (%)", "loss_step", float, "➖"),
        ]

        for label, key, typ, icon in fields:
            edit = QLineEdit()
            edit.setPlaceholderText(f"Enter {label.lower()}")
            val = getattr(profit_stoploss_setting, key, 0)
            edit.setText(str(val))
            values_layout.addRow(f"{icon} {label}:", edit)
            self.vars[key] = (edit, typ)
            self.entries[key] = edit

        values_group.setLayout(values_layout)
        layout.addWidget(values_group)

        # Status label for feedback
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #3fb950; font-size: 9pt; font-weight: bold; padding: 5px;")
        layout.addWidget(self.status_label)

        # Button layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.save_btn = QPushButton("💾 Save Settings")
        self.save_btn.clicked.connect(self.save)

        self.cancel_btn = QPushButton("❌ Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setStyleSheet("""
            QPushButton { background:#da3633; color:#fff; border-radius:4px; padding:12px; }
            QPushButton:hover { background:#f85149; }
        """)

        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self._on_profit_type_change()

    def _on_profit_type_change(self):
        selected = self.profit_type_combo.currentData()
        trailing_keys = {"trailing_first_profit", "max_profit", "profit_step", "loss_step"}
        for key, edit in self.entries.items():
            if key in trailing_keys:
                edit.setEnabled(selected == TRAILING)
                if selected == TRAILING:
                    edit.setPlaceholderText(f"Enter value (required for trailing)")
                else:
                    edit.setPlaceholderText("Disabled in STOP mode")
            else:
                edit.setEnabled(True)

    def show_success_feedback(self):
        """# PYQT: Show success with visual feedback"""
        self.status_label.setText("✓ Settings saved successfully!")
        self.status_label.setStyleSheet("color: #3fb950; font-size: 10pt; font-weight: bold; padding: 5px;")

        # Animate button
        original_text = self.save_btn.text()
        self.save_btn.setText("✓ Saved!")
        self.save_btn.setStyleSheet("""
            QPushButton { background:#2ea043; color:#fff; border-radius:4px; padding:12px; }
        """)

        # Flash all input fields briefly
        for entry in self.entries.values():
            if entry.isEnabled():
                entry.setStyleSheet("""
                    QLineEdit { background:#2d4a2d; color:#e6edf3; border:2px solid #3fb950;
                               border-radius:4px; padding:8px; }
                """)

        # Reset after delay
        QTimer.singleShot(1500, self.reset_styles)

    def reset_styles(self):
        """# PYQT: Reset all styles to normal"""
        for entry in self.entries.values():
            entry.setStyleSheet("""
                QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
                QLineEdit:focus { border:2px solid #58a6ff; }
            """)

        self.save_btn.setText("💾 Save Settings")
        self.save_btn.setStyleSheet("""
            QPushButton { background:#238636; color:#fff; border-radius:4px; padding:12px; }
            QPushButton:hover { background:#2ea043; }
        """)

    def show_error_feedback(self, error_msg):
        """# PYQT: Show error with visual feedback"""
        self.status_label.setText(f"✗ {error_msg}")
        self.status_label.setStyleSheet("color: #f85149; font-size: 10pt; font-weight: bold; padding: 5px;")

        # Flash button red
        self.save_btn.setStyleSheet("""
            QPushButton { background:#f85149; color:#fff; border-radius:4px; padding:12px; }
        """)

        QTimer.singleShot(2000, self.reset_styles)

    def save(self):
        """# PYQT: Save with visual feedback"""
        # Disable button during save
        self.save_btn.setEnabled(False)
        self.save_btn.setText("⏳ Validating...")
        self.status_label.setText("")  # Clear any previous status

        def _save():
            try:
                # Validate all fields
                for key, (edit, typ) in self.vars.items():
                    text = edit.text().strip()
                    if not text and edit.isEnabled():
                        raise ValueError(f"{key.replace('_', ' ').title()} is required")
                    if edit.isEnabled():
                        try:
                            float(text)
                        except ValueError:
                            raise ValueError(f"{key.replace('_', ' ').title()} must be a number")

                # Set profit type
                profit_type_val = self.profit_type_combo.currentData()
                self.profit_stoploss_setting.profit_type = profit_type_val

                # Set numeric fields
                for key, (edit, typ) in self.vars.items():
                    if edit.isEnabled():
                        text = edit.text().strip()
                        value = float(text)
                        setattr(self.profit_stoploss_setting, key, value)

                self.profit_stoploss_setting.save()

                if self.app and hasattr(self.app, "refresh_settings_live"):
                    self.app.refresh_settings_live()

                # Show success and close
                QTimer.singleShot(0, self.save_success)

            except ValueError as e:
                QTimer.singleShot(0, lambda: self.save_error(str(e)))
            except Exception as e:
                QTimer.singleShot(0, lambda: self.save_error(str(e)))

        threading.Thread(target=_save, daemon=True).start()

    def save_success(self):
        """# PYQT: Handle successful save"""
        self.show_success_feedback()
        self.save_btn.setEnabled(True)
        # Close after showing success
        QTimer.singleShot(2000, self.accept)

    def save_error(self, error_msg):
        """# PYQT: Handle save error"""
        self.show_error_feedback(error_msg)
        self.save_btn.setEnabled(True)