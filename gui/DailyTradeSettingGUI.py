# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QMessageBox, QVBoxLayout,
                             QComboBox, QCheckBox, QLabel, QScrollArea, QWidget)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from gui.DailyTradeSetting import DailyTradeSetting
import threading


class DailyTradeSettingGUI(QDialog):
    INTERVAL_CHOICES = [
        ("5 seconds", "5S"), ("10 seconds", "10S"), ("15 seconds", "15S"),
        ("30 seconds", "30S"), ("45 seconds", "45S"), ("1 minute", "1m"),
        ("2 minutes", "2m"), ("3 minutes", "3m"), ("5 minutes", "5m"),
        ("10 minutes", "10m"), ("15 minutes", "15m"), ("20 minutes", "20m"),
        ("30 minutes", "30m"), ("60 minutes", "60m"), ("120 minutes", "120m"),
        ("240 minutes", "240m")
    ]

    def __init__(self, parent, daily_setting: DailyTradeSetting, app=None):
        super().__init__(parent)
        self.daily_setting = daily_setting
        self.app = app
        self.setWindowTitle("Daily Trade Settings")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)
        self.setStyleSheet("""
            QDialog { background:#161b22; color:#e6edf3; }
            QLabel { color:#8b949e; }
            QLineEdit, QComboBox { background:#21262d; color:#e6edf3;
                                   border:1px solid #30363d; border-radius:4px; padding:8px;
                                   font-size:10pt; }
            QLineEdit:focus, QComboBox:focus { border:2px solid #58a6ff; }
            QCheckBox { color:#e6edf3; spacing:8px; }
            QCheckBox::indicator { width:18px; height:18px; }
            QCheckBox::indicator:unchecked { border:2px solid #30363d; background:#21262d; }
            QCheckBox::indicator:checked { background:#238636; border:2px solid #2ea043; }
            QPushButton { background:#238636; color:#fff; border-radius:4px; padding:12px;
                         font-weight:bold; font-size:10pt; }
            QPushButton:hover { background:#2ea043; }
            QPushButton:pressed { background:#1e7a2f; }
            QPushButton:disabled { background:#21262d; color:#484f58; }
            QScrollArea { border: none; background: transparent; }
        """)

        # Main layout
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("⚙️ Daily Trade Settings")
        header.setFont(QFont("Segoe UI", 14, QFont.Bold))
        header.setStyleSheet("color: #e6edf3; padding: 10px;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Scroll area for many fields
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.vars = {}
        self.entries = {}

        fields = [
            ("Exchange", "exchange", str, "🌐"),
            ("Week", "week", int, "📆"),
            ("Derivative", "derivative", str, "💡"),
            ("Lot Size", "lot_size", int, "🔢"),
            ("Call Lookback", "call_lookback", int, "🔎"),
            ("Put Lookback", "put_lookback", int, "🔎"),
            ("Max Num of Option", "max_num_of_option", int, "📈"),
            ("Lower Percentage", "lower_percentage", float, "🔻"),
            ("Cancel After", "cancel_after", int, "⏰"),
            ("Capital Reserve", "capital_reserve", int, "💰"),
        ]

        for label, key, typ, icon in fields:
            edit = QLineEdit()
            edit.setPlaceholderText(f"Enter {label.lower()}")
            val = self.daily_setting.data.get(key, "")
            edit.setText(str(val))
            form.addRow(f"{icon} {label}:", edit)
            self.vars[key] = (edit, typ)
            self.entries[key] = edit

        # History Interval ComboBox
        self.interval_combo = QComboBox()
        for display, value in self.INTERVAL_CHOICES:
            self.interval_combo.addItem(display, value)
        current_val = self.daily_setting.data.get("history_interval", "2m")
        for i in range(self.interval_combo.count()):
            if self.interval_combo.itemData(i) == current_val:
                self.interval_combo.setCurrentIndex(i)
                break
        form.addRow("⏱️ History Interval:", self.interval_combo)

        scroll_layout.addLayout(form)

        # Sideway Zone Trade checkbox with better styling
        self.sideway_check = QCheckBox("Enable trading during sideways market (12:00-2:00)")
        self.sideway_check.setChecked(self.daily_setting.data.get("sideway_zone_trade", False))
        scroll_layout.addWidget(self.sideway_check)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Status label for feedback
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #3fb950; font-size: 9pt; font-weight: bold; padding: 5px;")
        layout.addWidget(self.status_label)

        # Save button
        self.save_btn = QPushButton("💾 Save All Settings")
        self.save_btn.clicked.connect(self.save)
        layout.addWidget(self.save_btn)

    def show_success_feedback(self):
        """# PYQT: Show success animation"""
        self.status_label.setText("✓ Settings saved successfully!")
        self.status_label.setStyleSheet("color: #3fb950; font-size: 10pt; font-weight: bold; padding: 5px;")

        # Animate button
        original_text = self.save_btn.text()
        self.save_btn.setText("✓ Saved!")
        self.save_btn.setStyleSheet("""
            QPushButton { background:#2ea043; color:#fff; border-radius:4px; padding:12px; }
        """)

        # Flash all input fields briefly to indicate saved state
        for entry in self.entries.values():
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

        self.save_btn.setText("💾 Save All Settings")
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

        # Find and highlight the problematic field if it's a validation error
        if "number" in error_msg.lower():
            for key, (entry, typ) in self.vars.items():
                try:
                    if typ in (int, float):
                        text = entry.text().strip()
                        if text and typ == int:
                            int(text)
                        elif text and typ == float:
                            float(text)
                except:
                    entry.setStyleSheet("""
                        QLineEdit { background:#4d2a2a; color:#e6edf3; border:2px solid #f85149;
                                   border-radius:4px; padding:8px; }
                    """)

        QTimer.singleShot(2000, self.reset_styles)

    def save(self):
        """# PYQT: Save with visual feedback"""
        # Disable button during save
        self.save_btn.setEnabled(False)
        self.save_btn.setText("⏳ Saving...")
        self.status_label.setText("")  # Clear any previous status

        def _save():
            try:
                # Validate and collect data
                for key, (edit, typ) in self.vars.items():
                    text = edit.text().strip()
                    if typ == int:
                        if text:
                            value = int(float(text))
                        else:
                            value = 0
                    elif typ == float:
                        value = float(text) if text else 0.0
                    else:
                        value = text
                    setattr(self.daily_setting, key, value)

                # Set interval
                interval_val = self.interval_combo.currentData()
                self.daily_setting.history_interval = interval_val

                # Set sideway zone
                self.daily_setting.sideway_zone_trade = self.sideway_check.isChecked()

                self.daily_setting.save()

                if self.app and hasattr(self.app, "refresh_settings_live"):
                    self.app.refresh_settings_live()

                # Show success and close
                QTimer.singleShot(0, self.save_success)

            except ValueError as e:
                QTimer.singleShot(0, lambda: self.save_error(f"Invalid number format: {e}"))
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
        self.show_error_feedback(f"Failed to save: {error_msg}")
        self.save_btn.setEnabled(True)