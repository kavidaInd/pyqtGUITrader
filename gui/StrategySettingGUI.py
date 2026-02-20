# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QMessageBox, QVBoxLayout,
                             QCheckBox, QGroupBox, QHBoxLayout, QGridLayout,
                             QLabel, QScrollArea, QWidget)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from gui.StrategySetting import StrategySetting
import threading


class StrategySettingGUI(QDialog):
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
        self.long_st_length.setPlaceholderText("e.g., 10")
        self.long_st_multi = QLineEdit(str(strategy_setting.long_st_multi))
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
        self.short_st_length.setPlaceholderText("e.g., 7")
        self.short_st_multi = QLineEdit(str(strategy_setting.short_st_multi))
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
        self.bb_length.setPlaceholderText("e.g., 20")
        self.bb_std = QLineEdit(str(strategy_setting.bb_std))
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
        self.macd_fast.setPlaceholderText("e.g., 10")
        self.macd_slow = QLineEdit(str(strategy_setting.macd_slow))
        self.macd_slow.setPlaceholderText("e.g., 20")
        self.macd_signal = QLineEdit(str(strategy_setting.macd_signal))
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
        else:
            self.long_st_length.setPlaceholderText("e.g., 10")
            self.long_st_multi.setPlaceholderText("e.g., 1.5")

    def _toggle_short_st(self):
        enabled = self.use_short_st_entry.isChecked() or self.use_short_st_exit.isChecked()
        self.short_st_length.setEnabled(enabled)
        self.short_st_multi.setEnabled(enabled)
        if not enabled:
            self.short_st_length.setPlaceholderText("Disabled")
            self.short_st_multi.setPlaceholderText("Disabled")
        else:
            self.short_st_length.setPlaceholderText("e.g., 7")
            self.short_st_multi.setPlaceholderText("e.g., 1.2")

    def _toggle_bb(self):
        enabled = self.bb_entry.isChecked() or self.bb_exit.isChecked()
        self.bb_length.setEnabled(enabled)
        self.bb_std.setEnabled(enabled)
        if not enabled:
            self.bb_length.setPlaceholderText("Disabled")
            self.bb_std.setPlaceholderText("Disabled")
        else:
            self.bb_length.setPlaceholderText("e.g., 20")
            self.bb_std.setPlaceholderText("e.g., 2.0")

    def _toggle_macd(self):
        enabled = self.use_macd_entry.isChecked() or self.use_macd_exit.isChecked()
        self.macd_fast.setEnabled(enabled)
        self.macd_slow.setEnabled(enabled)
        self.macd_signal.setEnabled(enabled)
        if not enabled:
            self.macd_fast.setPlaceholderText("Disabled")
            self.macd_slow.setPlaceholderText("Disabled")
            self.macd_signal.setPlaceholderText("Disabled")
        else:
            self.macd_fast.setPlaceholderText("e.g., 10")
            self.macd_slow.setPlaceholderText("e.g., 20")
            self.macd_signal.setPlaceholderText("e.g., 7")

    def _toggle_rsi(self):
        enabled = self.use_rsi_entry.isChecked() or self.use_rsi_exit.isChecked()
        self.rsi_length.setEnabled(enabled)
        if not enabled:
            self.rsi_length.setPlaceholderText("Disabled")
        else:
            self.rsi_length.setPlaceholderText("e.g., 14")

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
            field.setStyleSheet("""
                QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                           border-radius:4px; padding:8px; }
                QLineEdit:focus { border:2px solid #58a6ff; }
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

        def _save():
            try:
                # Validate all enabled fields
                if self.long_st_length.isEnabled():
                    int(self.long_st_length.text())
                    float(self.long_st_multi.text())

                if self.short_st_length.isEnabled():
                    int(self.short_st_length.text())
                    float(self.short_st_multi.text())

                if self.bb_length.isEnabled():
                    int(self.bb_length.text())
                    float(self.bb_std.text())

                if self.macd_fast.isEnabled():
                    int(self.macd_fast.text())
                    int(self.macd_slow.text())
                    int(self.macd_signal.text())

                if self.rsi_length.isEnabled():
                    int(self.rsi_length.text())

                # Long Supertrend
                self.strategy_setting.use_long_st_entry = self.use_long_st_entry.isChecked()
                self.strategy_setting.use_long_st_exit = self.use_long_st_exit.isChecked()
                self.strategy_setting.use_long_st = self.use_long_st_entry.isChecked()
                self.strategy_setting.long_st_length = int(
                    self.long_st_length.text()) if self.long_st_length.isEnabled() else 10
                self.strategy_setting.long_st_multi = float(
                    self.long_st_multi.text()) if self.long_st_multi.isEnabled() else 1.5

                # Short Supertrend
                self.strategy_setting.use_short_st_entry = self.use_short_st_entry.isChecked()
                self.strategy_setting.use_short_st_exit = self.use_short_st_exit.isChecked()
                self.strategy_setting.use_short_st = self.use_short_st_entry.isChecked()
                self.strategy_setting.short_st_length = int(
                    self.short_st_length.text()) if self.short_st_length.isEnabled() else 7
                self.strategy_setting.short_st_multi = float(
                    self.short_st_multi.text()) if self.short_st_multi.isEnabled() else 1.2

                # Bollinger Bands
                self.strategy_setting.bb_entry = self.bb_entry.isChecked()
                self.strategy_setting.bb_exit = self.bb_exit.isChecked()
                self.strategy_setting.bb_length = int(self.bb_length.text()) if self.bb_length.isEnabled() else 20
                self.strategy_setting.bb_std = float(self.bb_std.text()) if self.bb_std.isEnabled() else 2.0

                # MACD
                self.strategy_setting.use_macd_entry = self.use_macd_entry.isChecked()
                self.strategy_setting.use_macd_exit = self.use_macd_exit.isChecked()
                self.strategy_setting.use_macd = self.use_macd_entry.isChecked()
                self.strategy_setting.macd_fast = int(self.macd_fast.text()) if self.macd_fast.isEnabled() else 10
                self.strategy_setting.macd_slow = int(self.macd_slow.text()) if self.macd_slow.isEnabled() else 20
                self.strategy_setting.macd_signal = int(self.macd_signal.text()) if self.macd_signal.isEnabled() else 7

                # RSI
                self.strategy_setting.use_rsi_entry = self.use_rsi_entry.isChecked()
                self.strategy_setting.use_rsi_exit = self.use_rsi_exit.isChecked()
                self.strategy_setting.use_rsi = self.use_rsi_entry.isChecked()
                self.strategy_setting.rsi_length = int(self.rsi_length.text()) if self.rsi_length.isEnabled() else 14

                self.strategy_setting.save()

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
        self.show_error_feedback(error_msg)
        self.save_btn.setEnabled(True)