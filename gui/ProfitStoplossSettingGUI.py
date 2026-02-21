# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QMessageBox, QVBoxLayout,
                             QComboBox, QHBoxLayout, QLabel, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QLocale
from PyQt5.QtGui import QFont, QDoubleValidator
from BaseEnums import STOP, TRAILING
import threading

from gui import ProfitStoplossSetting


class ProfitStoplossSettingGUI(QDialog):
    # Add signals for thread-safe communication
    save_completed = pyqtSignal(bool, str)

    # Validation ranges
    VALIDATION_RANGES = {
        "tp_percentage": (0.1, 100.0, "Take Profit"),
        "stoploss_percentage": (0.1, 50.0, "Stoploss"),
        "trailing_first_profit": (0.1, 50.0, "Trailing First Profit"),
        "max_profit": (0.1, 200.0, "Max Profit"),
        "profit_step": (0.1, 20.0, "Profit Step"),
        "loss_step": (0.1, 20.0, "Loss Step")
    }

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
            QLineEdit:disabled { background:#1a1f26; color:#6e7681; }
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
        current = profit_stoploss_setting.profit_type
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
            ("Take Profit (%)", "tp_percentage", "💰"),
            ("Stoploss (%)", "stoploss_percentage", "🛑"),
            ("Trailing First Profit (%)", "trailing_first_profit", "📈"),
            ("Max Profit (%)", "max_profit", "🏆"),
            ("Profit Step (%)", "profit_step", "➕"),
            ("Loss Step (%)", "loss_step", "➖"),
        ]

        # Set up double validator for all numeric fields
        validator = QDoubleValidator()
        validator.setLocale(QLocale.c())  # Use C locale for consistent decimal point

        for label, key, icon in fields:
            edit = QLineEdit()
            edit.setValidator(validator)
            edit.setPlaceholderText(f"Enter {label.lower()}")

            # Get value and handle stoploss sign conversion
            if key == "stoploss_percentage":
                val = abs(getattr(profit_stoploss_setting, key, 0))
            else:
                val = getattr(profit_stoploss_setting, key, 0)

            edit.setText(f"{val:.1f}")
            values_layout.addRow(f"{icon} {label}:", edit)
            self.vars[key] = edit
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

        # Connect signals
        self.save_completed.connect(self.on_save_completed)

        self._on_profit_type_change()

    def _on_profit_type_change(self):
        selected = self.profit_type_combo.currentData()
        trailing_keys = {"trailing_first_profit", "max_profit", "profit_step", "loss_step"}

        for key, edit in self.entries.items():
            if key in trailing_keys:
                edit.setEnabled(selected == TRAILING)
                if selected == TRAILING:
                    edit.setPlaceholderText("Enter value (required)")
                    # Restore original style
                    edit.setStyleSheet("""
                        QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                                   border-radius:4px; padding:8px; }
                        QLineEdit:focus { border:2px solid #58a6ff; }
                    """)
                else:
                    edit.setPlaceholderText("Disabled in STOP mode")
                    # Dim the text
                    edit.setStyleSheet("""
                        QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;
                                   border-radius:4px; padding:8px; }
                    """)
            else:
                edit.setEnabled(True)

    def validate_field(self, key: str, value: str) -> tuple:
        """Validate field value and return (is_valid, converted_value, error_message)"""
        if not value.strip():
            return False, None, f"{self.VALIDATION_RANGES[key][2]} is required"

        try:
            val = float(value)
            min_val, max_val, name = self.VALIDATION_RANGES[key]

            if val < min_val or val > max_val:
                return False, None, f"{name} must be between {min_val} and {max_val}"

            # Additional logical validations
            if key == "max_profit":
                trailing_first = float(self.entries["trailing_first_profit"].text() or "0")
                if val <= trailing_first:
                    return False, None, "Max Profit must be greater than Trailing First Profit"

            return True, val, None
        except ValueError:
            return False, None, f"{self.VALIDATION_RANGES[key][2]} must be a valid number"

    def show_success_feedback(self):
        """# PYQT: Show success with visual feedback"""
        self.status_label.setText("✓ Settings saved successfully!")
        self.status_label.setStyleSheet("color: #3fb950; font-size: 10pt; font-weight: bold; padding: 5px;")

        # Animate button
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
        for key, entry in self.entries.items():
            if entry.isEnabled():
                entry.setStyleSheet("""
                    QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                               border-radius:4px; padding:8px; }
                    QLineEdit:focus { border:2px solid #58a6ff; }
                """)
            else:
                entry.setStyleSheet("""
                    QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;
                               border-radius:4px; padding:8px; }
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

        # Validate all fields in main thread
        data_to_save = {}
        validation_errors = []

        # Determine which fields are required based on profit type
        profit_type = self.profit_type_combo.currentData()
        required_fields = ["tp_percentage", "stoploss_percentage"]
        if profit_type == TRAILING:
            required_fields.extend(["trailing_first_profit", "max_profit", "profit_step", "loss_step"])

        # Validate all required fields
        for key in required_fields:
            edit = self.entries[key]
            text = edit.text().strip()
            is_valid, value, error = self.validate_field(key, text)

            if is_valid:
                data_to_save[key] = value
            else:
                validation_errors.append(error)
                # Highlight the problematic field
                edit.setStyleSheet("""
                    QLineEdit { background:#4d2a2a; color:#e6edf3; border:2px solid #f85149;
                               border-radius:4px; padding:8px; }
                """)

        if validation_errors:
            self.show_error_feedback("\n".join(validation_errors))
            self.save_btn.setEnabled(True)
            return

        # Add profit type to data
        data_to_save['profit_type'] = profit_type

        def _save():
            try:
                # Update settings object
                for key, value in data_to_save.items():
                    setattr(self.profit_stoploss_setting, key, value)

                # Save to file
                success = self.profit_stoploss_setting.save()

                if success:
                    self.save_completed.emit(True, "Settings saved successfully!")
                else:
                    self.save_completed.emit(False, "Failed to save settings to file")

            except Exception as e:
                self.save_completed.emit(False, str(e))

        threading.Thread(target=_save, daemon=True).start()

    def on_save_completed(self, success, message):
        """Handle save completion in main thread"""
        if success:
            self.show_success_feedback()
            self.save_btn.setEnabled(True)

            # Refresh app if needed
            if self.app and hasattr(self.app, "refresh_settings_live"):
                try:
                    self.app.refresh_settings_live()
                except Exception as e:
                    print(f"Failed to refresh app: {e}")

            # Close after showing success
            QTimer.singleShot(2000, self.accept)
        else:
            self.show_error_feedback(message)
            self.save_btn.setEnabled(True)