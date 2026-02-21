# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QMessageBox, QVBoxLayout,
                             QCheckBox, QGroupBox, QHBoxLayout, QGridLayout,
                             QLabel, QScrollArea, QWidget)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QIntValidator, QDoubleValidator
import threading


class StrategySettingGUI(QDialog):
    # Add signals for thread-safe communication
    save_completed = pyqtSignal(bool, str)

    # Validation ranges
    VALIDATION_RANGES = {
        "long_st_length": (1, 100, "Long ST Length"),
        "long_st_multi": (0.1, 10.0, "Long ST Multiplier"),
        "short_st_length": (1, 100, "Short ST Length"),
        "short_st_multi": (0.1, 10.0, "Short ST Multiplier"),
        "bb_length": (2, 100, "BB Length"),
        "bb_std": (0.1, 5.0, "BB Std Dev"),
        "macd_fast": (1, 50, "MACD Fast"),
        "macd_slow": (2, 100, "MACD Slow"),
        "macd_signal": (1, 50, "MACD Signal"),
        "rsi_length": (2, 50, "RSI Length")
    }

    def __init__(self, parent, strategy_setting):
        super().__init__(parent)
        self.strategy_setting = strategy_setting
        self.setWindowTitle("Strategy Settings")
        self.setModal(True)
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)
        self.setStyleSheet("""
            QDialog { background:#161b22; color:#e6edf3; }
            QGroupBox { color:#e6edf3; border:2px solid #30363d; border-radius:6px;
                        margin-top:1em; padding-top:15px; font-weight:bold; }
            QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 10px; }
            QLabel { color:#8b949e; }
            QLineEdit { background:#21262d; color:#e6edf3;
                       border:1px solid #30363d; border-radius:4px; padding:8px;
                       font-size:10pt; }
            QLineEdit:focus { border:2px solid #58a6ff; }
            QLineEdit:disabled { background:#1a1f26; color:#6e7681; }
            QCheckBox { color:#e6edf3; spacing:8px; font-size:10pt; }
            QCheckBox::indicator { width:20px; height:20px; }
            QCheckBox::indicator:unchecked { border:2px solid #30363d; background:#21262d; }
            QCheckBox::indicator:checked { background:#238636; border:2px solid #2ea043; }
            QPushButton { background:#238636; color:#fff; border-radius:4px; padding:12px;
                         font-weight:bold; font-size:10pt; }
            QPushButton:hover { background:#2ea043; }
            QPushButton:pressed { background:#1e7a2f; }
            QPushButton:disabled { background:#21262d; color:#484f58; }
            QScrollArea { border: none; background: transparent; }
        """)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel("🛠️ Advanced Strategy Configuration")
        header.setFont(QFont("Segoe UI", 14, QFont.Bold))
        header.setStyleSheet("color: #e6edf3; padding: 10px;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Scroll area for many controls
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(15)

        # Create a grid layout for the groups
        grid = QGridLayout()
        grid.setSpacing(15)

        # Set up validators
        int_validator = QIntValidator()
        int_validator.setBottom(1)

        double_validator = QDoubleValidator()
        double_validator.setBottom(0.1)
        double_validator.setDecimals(2)

        # Long Supertrend Group
        long_st_group = QGroupBox("✨ Long Supertrend")
        long_st_layout = QVBoxLayout()
        long_st_layout.setSpacing(10)

        self.use_long_st_entry = QCheckBox("Use for Entry")
        self.use_long_st_entry.setChecked(strategy_setting.use_long_st_entry)
        self.use_long_st_entry.stateChanged.connect(self._toggle_long_st)

        self.use_long_st_exit = QCheckBox("Use for Exit")
        self.use_long_st_exit.setChecked(strategy_setting.use_long_st_exit)
        self.use_long_st_exit.stateChanged.connect(self._toggle_long_st)

        entry_exit_layout = QHBoxLayout()
        entry_exit_layout.addWidget(self.use_long_st_entry)
        entry_exit_layout.addWidget(self.use_long_st_exit)
        entry_exit_layout.addStretch()
        long_st_layout.addLayout(entry_exit_layout)

        form = QFormLayout()
        form.setSpacing(8)
        self.long_st_length = QLineEdit(str(strategy_setting.long_st_length))
        self.long_st_length.setValidator(int_validator)
        self.long_st_length.setPlaceholderText("e.g., 10")
        self.long_st_multi = QLineEdit(str(strategy_setting.long_st_multi))
        self.long_st_multi.setValidator(double_validator)
        self.long_st_multi.setPlaceholderText("e.g., 1.5")
        form.addRow("Length:", self.long_st_length)
        form.addRow("Multiplier:", self.long_st_multi)
        long_st_layout.addLayout(form)

        long_st_group.setLayout(long_st_layout)
        grid.addWidget(long_st_group, 0, 0)

        # Short Supertrend Group
        short_st_group = QGroupBox("✨ Short Supertrend")
        short_st_layout = QVBoxLayout()
        short_st_layout.setSpacing(10)

        self.use_short_st_entry = QCheckBox("Use for Entry")
        self.use_short_st_entry.setChecked(strategy_setting.use_short_st_entry)
        self.use_short_st_entry.stateChanged.connect(self._toggle_short_st)

        self.use_short_st_exit = QCheckBox("Use for Exit")
        self.use_short_st_exit.setChecked(strategy_setting.use_short_st_exit)
        self.use_short_st_exit.stateChanged.connect(self._toggle_short_st)

        entry_exit_layout2 = QHBoxLayout()
        entry_exit_layout2.addWidget(self.use_short_st_entry)
        entry_exit_layout2.addWidget(self.use_short_st_exit)
        entry_exit_layout2.addStretch()
        short_st_layout.addLayout(entry_exit_layout2)

        form2 = QFormLayout()
        form2.setSpacing(8)
        self.short_st_length = QLineEdit(str(strategy_setting.short_st_length))
        self.short_st_length.setValidator(int_validator)
        self.short_st_length.setPlaceholderText("e.g., 7")
        self.short_st_multi = QLineEdit(str(strategy_setting.short_st_multi))
        self.short_st_multi.setValidator(double_validator)
        self.short_st_multi.setPlaceholderText("e.g., 1.2")
        form2.addRow("Length:", self.short_st_length)
        form2.addRow("Multiplier:", self.short_st_multi)
        short_st_layout.addLayout(form2)

        short_st_group.setLayout(short_st_layout)
        grid.addWidget(short_st_group, 0, 1)

        # Bollinger Bands Group
        bb_group = QGroupBox("📊 Bollinger Bands")
        bb_layout = QVBoxLayout()
        bb_layout.setSpacing(10)

        self.bb_entry = QCheckBox("Use for Entry")
        self.bb_entry.setChecked(strategy_setting.bb_entry)
        self.bb_exit = QCheckBox("Use for Exit")
        self.bb_exit.setChecked(strategy_setting.bb_exit)
        self.bb_entry.stateChanged.connect(self._toggle_bb)
        self.bb_exit.stateChanged.connect(self._toggle_bb)

        entry_exit_layout3 = QHBoxLayout()
        entry_exit_layout3.addWidget(self.bb_entry)
        entry_exit_layout3.addWidget(self.bb_exit)
        entry_exit_layout3.addStretch()
        bb_layout.addLayout(entry_exit_layout3)

        form3 = QFormLayout()
        form3.setSpacing(8)
        self.bb_length = QLineEdit(str(strategy_setting.bb_length))
        self.bb_length.setValidator(int_validator)
        self.bb_length.setPlaceholderText("e.g., 20")
        self.bb_std = QLineEdit(str(strategy_setting.bb_std))
        self.bb_std.setValidator(double_validator)
        self.bb_std.setPlaceholderText("e.g., 2.0")
        form3.addRow("Length:", self.bb_length)
        form3.addRow("Std Dev:", self.bb_std)
        bb_layout.addLayout(form3)

        bb_group.setLayout(bb_layout)
        grid.addWidget(bb_group, 1, 0)

        # MACD Group
        macd_group = QGroupBox("📈 MACD")
        macd_layout = QVBoxLayout()
        macd_layout.setSpacing(10)

        self.use_macd_entry = QCheckBox("Use for Entry")
        self.use_macd_entry.setChecked(strategy_setting.use_macd_entry)
        self.use_macd_exit = QCheckBox("Use for Exit")
        self.use_macd_exit.setChecked(strategy_setting.use_macd_exit)
        self.use_macd_entry.stateChanged.connect(self._toggle_macd)
        self.use_macd_exit.stateChanged.connect(self._toggle_macd)

        entry_exit_layout4 = QHBoxLayout()
        entry_exit_layout4.addWidget(self.use_macd_entry)
        entry_exit_layout4.addWidget(self.use_macd_exit)
        entry_exit_layout4.addStretch()
        macd_layout.addLayout(entry_exit_layout4)

        form4 = QFormLayout()
        form4.setSpacing(8)
        self.macd_fast = QLineEdit(str(strategy_setting.macd_fast))
        self.macd_fast.setValidator(int_validator)
        self.macd_fast.setPlaceholderText("e.g., 10")
        self.macd_slow = QLineEdit(str(strategy_setting.macd_slow))
        self.macd_slow.setValidator(int_validator)
        self.macd_slow.setPlaceholderText("e.g., 20")
        self.macd_signal = QLineEdit(str(strategy_setting.macd_signal))
        self.macd_signal.setValidator(int_validator)
        self.macd_signal.setPlaceholderText("e.g., 7")
        form4.addRow("Fast Period:", self.macd_fast)
        form4.addRow("Slow Period:", self.macd_slow)
        form4.addRow("Signal Period:", self.macd_signal)
        macd_layout.addLayout(form4)

        macd_group.setLayout(macd_layout)
        grid.addWidget(macd_group, 1, 1)

        # RSI Group (spans both columns)
        rsi_group = QGroupBox("🔄 RSI")
        rsi_layout = QVBoxLayout()
        rsi_layout.setSpacing(10)

        self.use_rsi_entry = QCheckBox("Use for Entry")
        self.use_rsi_entry.setChecked(strategy_setting.use_rsi_entry)
        self.use_rsi_exit = QCheckBox("Use for Exit")
        self.use_rsi_exit.setChecked(strategy_setting.use_rsi_exit)
        self.use_rsi_entry.stateChanged.connect(self._toggle_rsi)
        self.use_rsi_exit.stateChanged.connect(self._toggle_rsi)

        entry_exit_layout5 = QHBoxLayout()
        entry_exit_layout5.addWidget(self.use_rsi_entry)
        entry_exit_layout5.addWidget(self.use_rsi_exit)
        entry_exit_layout5.addStretch()
        rsi_layout.addLayout(entry_exit_layout5)

        form5 = QFormLayout()
        form5.setSpacing(8)
        self.rsi_length = QLineEdit(str(strategy_setting.rsi_length))
        self.rsi_length.setValidator(int_validator)
        self.rsi_length.setPlaceholderText("e.g., 14")
        form5.addRow("RSI Length:", self.rsi_length)
        rsi_layout.addLayout(form5)

        rsi_group.setLayout(rsi_layout)
        grid.addWidget(rsi_group, 2, 0, 1, 2)

        scroll_layout.addLayout(grid)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Status label for feedback
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #3fb950; font-size: 9pt; font-weight: bold; padding: 5px;")
        layout.addWidget(self.status_label)

        # Save button
        self.save_btn = QPushButton("💾 Save Strategy Configuration")
        self.save_btn.clicked.connect(self.save)
        layout.addWidget(self.save_btn)

        # Connect signals
        self.save_completed.connect(self.on_save_completed)

        # Initial toggle states
        self._toggle_long_st()
        self._toggle_short_st()
        self._toggle_bb()
        self._toggle_macd()
        self._toggle_rsi()

        # Store all editable fields for style reset
        self.all_fields = [
            self.long_st_length, self.long_st_multi,
            self.short_st_length, self.short_st_multi,
            self.bb_length, self.bb_std,
            self.macd_fast, self.macd_slow, self.macd_signal,
            self.rsi_length
        ]

    def _toggle_long_st(self):
        enabled = self.use_long_st_entry.isChecked() or self.use_long_st_exit.isChecked()
        self.long_st_length.setEnabled(enabled)
        self.long_st_multi.setEnabled(enabled)
        if not enabled:
            self.long_st_length.setPlaceholderText("Disabled")
            self.long_st_multi.setPlaceholderText("Disabled")
            self.long_st_length.setStyleSheet("""
                QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
            """)
            self.long_st_multi.setStyleSheet("""
                QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
            """)
        else:
            self.long_st_length.setPlaceholderText("e.g., 10")
            self.long_st_multi.setPlaceholderText("e.g., 1.5")
            self.long_st_length.setStyleSheet("""
                QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
                QLineEdit:focus { border:2px solid #58a6ff; }
            """)
            self.long_st_multi.setStyleSheet("""
                QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
                QLineEdit:focus { border:2px solid #58a6ff; }
            """)

    def _toggle_short_st(self):
        enabled = self.use_short_st_entry.isChecked() or self.use_short_st_exit.isChecked()
        self.short_st_length.setEnabled(enabled)
        self.short_st_multi.setEnabled(enabled)
        if not enabled:
            self.short_st_length.setPlaceholderText("Disabled")
            self.short_st_multi.setPlaceholderText("Disabled")
            self.short_st_length.setStyleSheet("""
                QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
            """)
            self.short_st_multi.setStyleSheet("""
                QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
            """)
        else:
            self.short_st_length.setPlaceholderText("e.g., 7")
            self.short_st_multi.setPlaceholderText("e.g., 1.2")
            self.short_st_length.setStyleSheet("""
                QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
                QLineEdit:focus { border:2px solid #58a6ff; }
            """)
            self.short_st_multi.setStyleSheet("""
                QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
                QLineEdit:focus { border:2px solid #58a6ff; }
            """)

    def _toggle_bb(self):
        enabled = self.bb_entry.isChecked() or self.bb_exit.isChecked()
        self.bb_length.setEnabled(enabled)
        self.bb_std.setEnabled(enabled)
        if not enabled:
            self.bb_length.setPlaceholderText("Disabled")
            self.bb_std.setPlaceholderText("Disabled")
            self.bb_length.setStyleSheet("""
                QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
            """)
            self.bb_std.setStyleSheet("""
                QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
            """)
        else:
            self.bb_length.setPlaceholderText("e.g., 20")
            self.bb_std.setPlaceholderText("e.g., 2.0")
            self.bb_length.setStyleSheet("""
                QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
                QLineEdit:focus { border:2px solid #58a6ff; }
            """)
            self.bb_std.setStyleSheet("""
                QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
                QLineEdit:focus { border:2px solid #58a6ff; }
            """)

    def _toggle_macd(self):
        enabled = self.use_macd_entry.isChecked() or self.use_macd_exit.isChecked()
        self.macd_fast.setEnabled(enabled)
        self.macd_slow.setEnabled(enabled)
        self.macd_signal.setEnabled(enabled)
        if not enabled:
            self.macd_fast.setPlaceholderText("Disabled")
            self.macd_slow.setPlaceholderText("Disabled")
            self.macd_signal.setPlaceholderText("Disabled")
            for field in [self.macd_fast, self.macd_slow, self.macd_signal]:
                field.setStyleSheet("""
                    QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;
                               border-radius:4px; padding:8px; }
                """)
        else:
            self.macd_fast.setPlaceholderText("e.g., 10")
            self.macd_slow.setPlaceholderText("e.g., 20")
            self.macd_signal.setPlaceholderText("e.g., 7")
            for field in [self.macd_fast, self.macd_slow, self.macd_signal]:
                field.setStyleSheet("""
                    QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                               border-radius:4px; padding:8px; }
                    QLineEdit:focus { border:2px solid #58a6ff; }
                """)

    def _toggle_rsi(self):
        enabled = self.use_rsi_entry.isChecked() or self.use_rsi_exit.isChecked()
        self.rsi_length.setEnabled(enabled)
        if not enabled:
            self.rsi_length.setPlaceholderText("Disabled")
            self.rsi_length.setStyleSheet("""
                QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
            """)
        else:
            self.rsi_length.setPlaceholderText("e.g., 14")
            self.rsi_length.setStyleSheet("""
                QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
                QLineEdit:focus { border:2px solid #58a6ff; }
            """)

    def validate_field(self, field: QLineEdit, key: str, value: str) -> tuple:
        """Validate field value and return (is_valid, converted_value, error_message)"""
        if not field.isEnabled():
            return True, None, None

        if not value.strip():
            return False, None, f"{self.VALIDATION_RANGES[key][2]} is required"

        try:
            if key.endswith("_multi") or key == "bb_std":
                val = float(value)
            else:
                val = int(float(value))

            min_val, max_val, name = self.VALIDATION_RANGES[key]

            if val < min_val or val > max_val:
                return False, None, f"{name} must be between {min_val} and {max_val}"

            # Special validation for MACD
            if key == "macd_fast" and self.macd_slow.isEnabled():
                slow_val = int(self.macd_slow.text() or "0")
                if val >= slow_val:
                    return False, None, "MACD Fast must be less than Slow period"
            elif key == "macd_slow" and self.macd_fast.isEnabled():
                fast_val = int(self.macd_fast.text() or "0")
                if val <= fast_val:
                    return False, None, "MACD Slow must be greater than Fast period"

            return True, val, None
        except ValueError:
            return False, None, f"{self.VALIDATION_RANGES[key][2]} must be a valid number"

    def show_success_feedback(self):
        """# PYQT: Show success with visual feedback"""
        self.status_label.setText("✓ Strategy settings saved successfully!")
        self.status_label.setStyleSheet("color: #3fb950; font-size: 10pt; font-weight: bold; padding: 5px;")

        # Animate button
        self.save_btn.setText("✓ Saved!")
        self.save_btn.setStyleSheet("""
            QPushButton { background:#2ea043; color:#fff; border-radius:4px; padding:12px; }
        """)

        # Flash all enabled input fields
        for field in self.all_fields:
            if field.isEnabled():
                field.setStyleSheet("""
                    QLineEdit { background:#2d4a2d; color:#e6edf3; border:2px solid #3fb950;
                               border-radius:4px; padding:8px; }
                """)

        # Reset after delay
        QTimer.singleShot(1500, self.reset_styles)

    def reset_styles(self):
        """# PYQT: Reset all styles to normal"""
        for field in self.all_fields:
            if field.isEnabled():
                field.setStyleSheet("""
                    QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                               border-radius:4px; padding:8px; }
                    QLineEdit:focus { border:2px solid #58a6ff; }
                """)
            else:
                field.setStyleSheet("""
                    QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;
                               border-radius:4px; padding:8px; }
                """)

        self.save_btn.setText("💾 Save Strategy Configuration")
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

        # Collect and validate data in main thread
        data_to_save = {}
        validation_errors = []

        # Define field mappings
        field_mappings = [
            (self.long_st_length, "long_st_length"),
            (self.long_st_multi, "long_st_multi"),
            (self.short_st_length, "short_st_length"),
            (self.short_st_multi, "short_st_multi"),
            (self.bb_length, "bb_length"),
            (self.bb_std, "bb_std"),
            (self.macd_fast, "macd_fast"),
            (self.macd_slow, "macd_slow"),
            (self.macd_signal, "macd_signal"),
            (self.rsi_length, "rsi_length")
        ]

        for field, key in field_mappings:
            if field.isEnabled():
                is_valid, value, error = self.validate_field(field, key, field.text().strip())
                if is_valid:
                    data_to_save[key] = value
                else:
                    validation_errors.append(error)
                    field.setStyleSheet("""
                        QLineEdit { background:#4d2a2a; color:#e6edf3; border:2px solid #f85149;
                                   border-radius:4px; padding:8px; }
                    """)

        if validation_errors:
            self.show_error_feedback("\n".join(validation_errors))
            self.save_btn.setEnabled(True)
            return

        # Add checkbox states
        data_to_save.update({
            "use_long_st_entry": self.use_long_st_entry.isChecked(),
            "use_long_st_exit": self.use_long_st_exit.isChecked(),
            "use_short_st_entry": self.use_short_st_entry.isChecked(),
            "use_short_st_exit": self.use_short_st_exit.isChecked(),
            "bb_entry": self.bb_entry.isChecked(),
            "bb_exit": self.bb_exit.isChecked(),
            "use_macd_entry": self.use_macd_entry.isChecked(),
            "use_macd_exit": self.use_macd_exit.isChecked(),
            "use_rsi_entry": self.use_rsi_entry.isChecked(),
            "use_rsi_exit": self.use_rsi_exit.isChecked()
        })

        def _save():
            try:
                # Update settings object
                for key, value in data_to_save.items():
                    setattr(self.strategy_setting, key, value)

                # Save to file
                success = self.strategy_setting.save()

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
            # Close after showing success
            QTimer.singleShot(2000, self.accept)
        else:
            self.show_error_feedback(message)
            self.save_btn.setEnabled(True)