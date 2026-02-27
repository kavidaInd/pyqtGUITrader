# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QVBoxLayout, QHBoxLayout,
                             QLabel, QWidget, QTabWidget, QFrame,
                             QScrollArea, QComboBox, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QLocale
from PyQt5.QtGui import QFont, QDoubleValidator
from BaseEnums import STOP, TRAILING, logger
import threading

from gui.profit_loss import ProfitStoplossSetting


class ProfitStoplossSettingGUI(QDialog):
    save_completed = pyqtSignal(bool, str)

    # Rule 3: Additional signals
    error_occurred = pyqtSignal(str)
    operation_started = pyqtSignal()
    operation_finished = pyqtSignal()

    VALIDATION_RANGES = {
        "tp_percentage": (0.1, 100.0, "Take Profit"),
        "stoploss_percentage": (0.1, 50.0, "Stoploss"),  # Positive range
        "trailing_first_profit": (0.1, 50.0, "Trailing First Profit"),
        "max_profit": (0.1, 200.0, "Max Profit"),
        "profit_step": (0.1, 20.0, "Profit Step"),
        "loss_step": (0.1, 20.0, "Loss Step"),
    }

    def __init__(self, parent, profit_stoploss_setting: ProfitStoplossSetting, app=None):
        # Rule 2: Safe defaults
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.profit_stoploss_setting = profit_stoploss_setting
            self.app = app
            self.setWindowTitle("Profit & Stoploss Settings")
            self.setModal(True)
            self.setMinimumSize(750, 650)
            self.resize(750, 650)

            # Apply dark theme
            self.setStyleSheet("""
                QDialog { background:#161b22; color:#e6edf3; }
                QLabel  { color:#8b949e; }
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
                QTabBar::tab:hover:!selected { background:#30363d; color:#e6edf3; }
                QGroupBox {
                    color:#e6edf3; border:1px solid #30363d; border-radius:6px;
                    margin-top:1em; padding-top:14px; font-weight:bold;
                }
                QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 8px; }
                QLineEdit, QComboBox {
                    background:#21262d; color:#e6edf3; border:1px solid #30363d;
                    border-radius:4px; padding:8px; font-size:10pt;
                }
                QLineEdit:focus, QComboBox:focus { border:2px solid #58a6ff; }
                QLineEdit:disabled { background:#1a1f26; color:#6e7681; }
                QPushButton {
                    background:#238636; color:#fff; border-radius:4px; padding:12px;
                    font-weight:bold; font-size:10pt;
                }
                QPushButton:hover    { background:#2ea043; }
                QPushButton:pressed  { background:#1e7a2f; }
                QPushButton:disabled { background:#21262d; color:#484f58; }
                QScrollArea { border:none; background:transparent; }
                QFrame#infoCard {
                    background:#21262d;
                    border:1px solid #30363d;
                    border-radius:6px;
                }
                QLabel#warning {
                    color: #d29922;
                    font-size: 9pt;
                }
            """)

            # Root layout
            root = QVBoxLayout(self)
            root.setContentsMargins(16, 16, 16, 16)
            root.setSpacing(12)

            # Header
            header = QLabel("💹 Profit & Stoploss Configuration")
            header.setFont(QFont("Segoe UI", 14, QFont.Bold))
            header.setStyleSheet("color:#e6edf3; padding:4px;")
            header.setAlignment(Qt.AlignCenter)
            root.addWidget(header)

            # BUG #1 Warning Banner
            warning_banner = QFrame()
            warning_banner.setStyleSheet("""
                QFrame {
                    background: #3d2e1f;
                    border: 1px solid #d29922;
                    border-radius: 6px;
                }
            """)
            warning_layout = QHBoxLayout(warning_banner)
            warning_layout.setContentsMargins(12, 8, 12, 8)

            warning_icon = QLabel("⚠️")
            warning_icon.setFont(QFont("Segoe UI", 12))
            warning_layout.addWidget(warning_icon)

            warning_text = QLabel(
                "<b>Note:</b> Stop-loss is applied BELOW entry price for long positions "
                "(CALL/PUT buyers). Enter the percentage as a positive number."
            )
            warning_text.setWordWrap(True)
            warning_text.setStyleSheet("color: #d29922; font-size: 9pt;")
            warning_layout.addWidget(warning_text, 1)

            root.addWidget(warning_banner)

            # Tabs
            self.tabs = QTabWidget()
            root.addWidget(self.tabs)
            self.tabs.addTab(self._build_settings_tab(), "⚙️ Settings")
            self.tabs.addTab(self._build_info_tab(), "ℹ️ Information")

            # Status label (always visible)
            self.status_label = QLabel("")
            self.status_label.setAlignment(Qt.AlignCenter)
            self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
            root.addWidget(self.status_label)

            # Save + Cancel buttons
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
            root.addLayout(btn_layout)

            self.save_completed.connect(self.on_save_completed)

            # Connect internal signals
            self._connect_signals()

            # Initialize UI
            self._on_profit_type_change()

            logger.info("ProfitStoplossSettingGUI initialized")

        except Exception as e:
            logger.critical(f"[ProfitStoplossSettingGUI.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.profit_stoploss_setting = None
        self.app = None
        self.tabs = None
        self.profit_type_combo = None
        self.vars = {}
        self.entries = {}
        self.status_label = None
        self.save_btn = None
        self.cancel_btn = None
        self._save_in_progress = False

    def _connect_signals(self):
        """Connect internal signals"""
        try:
            self.error_occurred.connect(self._on_error)
            self.operation_started.connect(self._on_operation_started)
            self.operation_finished.connect(self._on_operation_finished)
        except Exception as e:
            logger.error(f"[ProfitStoplossSettingGUI._connect_signals] Failed: {e}", exc_info=True)

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            super().__init__(parent)
            self.setWindowTitle("Profit & Stoploss Settings - ERROR")
            self.setMinimumSize(400, 200)

            layout = QVBoxLayout(self)
            error_label = QLabel("❌ Failed to initialize settings dialog.\nPlease check the logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #f85149; padding: 20px; font-size: 12pt;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)

        except Exception as e:
            logger.error(f"[ProfitStoplossSettingGUI._create_error_dialog] Failed: {e}", exc_info=True)

    # ── Settings Tab ──────────────────────────────────────────────────────────
    def _build_settings_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        container.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 18, 18, 12)
        layout.setSpacing(12)

        validator = QDoubleValidator()
        validator.setLocale(QLocale.c())

        # ── Profit Type group ─────────────────────────────────────────────────
        main_group = QGroupBox("Profit Mode")
        main_layout = QFormLayout()
        main_layout.setSpacing(6)
        main_layout.setVerticalSpacing(3)
        main_layout.setLabelAlignment(Qt.AlignRight)

        self.profit_type_combo = QComboBox()
        self.profit_type_combo.addItem("STOP (Fixed Target)", STOP)
        self.profit_type_combo.addItem("TRAILING (Dynamic)", TRAILING)
        current = self.profit_stoploss_setting.profit_type
        self.profit_type_combo.setCurrentIndex(0 if current == STOP else 1)
        self.profit_type_combo.currentIndexChanged.connect(self._on_profit_type_change)
        self.profit_type_combo.setToolTip(
            "STOP: exit at a fixed take-profit target.\n"
            "TRAILING: lock in gains as price moves in your favour."
        )
        profit_type_hint = QLabel("STOP exits at a fixed target. TRAILING locks in gains dynamically.")
        profit_type_hint.setStyleSheet("color:#484f58; font-size:8pt;")

        main_layout.addRow("💰 Profit Type:", self.profit_type_combo)
        main_layout.addRow("", profit_type_hint)
        main_group.setLayout(main_layout)
        layout.addWidget(main_group)

        # ── Threshold Values group ────────────────────────────────────────────
        values_group = QGroupBox("Threshold Values")
        values_layout = QFormLayout()
        values_layout.setSpacing(6)
        values_layout.setVerticalSpacing(3)
        values_layout.setLabelAlignment(Qt.AlignRight)

        self.vars = {}
        self.entries = {}

        # (label, key, icon, placeholder, hint, tooltip)
        fields = [
            (
                "Take Profit (%)", "tp_percentage",
                "💰", "e.g. 2.5",
                "Exit the trade when profit reaches this % (0.1–100).",
                "The position is closed automatically once unrealised P&L hits this percentage."
            ),
            (
                "Stoploss (%)", "stoploss_percentage",
                "🛑", "e.g. 1.0",
                "Exit the trade when loss reaches this % (0.1–50). Enter as positive number.",
                "BUG #1 FIX: This is applied BELOW entry price for long positions. Enter the absolute value."
            ),
            (
                "Trailing First Profit (%)", "trailing_first_profit",
                "📈", "e.g. 1.0  (TRAILING only)",
                "Minimum profit % before the trailing stop activates (TRAILING only).",
                "The trailing mechanism only kicks in once this initial profit level is reached."
            ),
            (
                "Max Profit (%)", "max_profit",
                "🏆", "e.g. 10.0  (TRAILING only)",
                "Upper profit ceiling; trailing stop range ends here (TRAILING only).",
                "Must be greater than Trailing First Profit. Acts as the profit ladder's top rung."
            ),
            (
                "Profit Step (%)", "profit_step",
                "➕", "e.g. 0.5  (TRAILING only)",
                "How much profit must increase to move the trailing stop up (TRAILING only).",
                "Smaller steps = tighter trailing, locks in more gains but risks early exit."
            ),
            (
                "Loss Step (%)", "loss_step",
                "➖", "e.g. 0.5  (TRAILING only)",
                "How far price can fall back from peak before the stop triggers (TRAILING only).",
                "Larger steps = more room to breathe, but gives back more open profit."
            ),
        ]

        for label, key, icon, placeholder, hint, tooltip in fields:
            edit = QLineEdit()
            edit.setValidator(validator)
            edit.setPlaceholderText(placeholder)
            edit.setToolTip(tooltip)

            # BUG #1 FIX: Always show stoploss as positive
            if key == "stoploss_percentage":
                val = abs(getattr(self.profit_stoploss_setting, key, 0))
            else:
                val = getattr(self.profit_stoploss_setting, key, 0)
            edit.setText(f"{val:.1f}")

            hint_lbl = QLabel(hint)
            hint_lbl.setStyleSheet("color:#484f58; font-size:8pt;")

            values_layout.addRow(f"{icon} {label}:", edit)
            values_layout.addRow("", hint_lbl)

            self.vars[key] = edit
            self.entries[key] = edit

        values_group.setLayout(values_layout)
        layout.addWidget(values_group)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

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
                "💰  Profit Type",
                "Controls how the exit strategy works once a position is open.\n\n"
                "• STOP (Fixed Target): the position is closed as soon as unrealised profit hits "
                "the Take Profit percentage. Simple and predictable.\n"
                "• TRAILING (Dynamic): the exit level rises with the price, locking in gains as "
                "the trade moves in your favour. More complex but can capture larger moves."
            ),
            (
                "💰  Take Profit (%)",
                "The profit percentage at which an open position is automatically closed.\n\n"
                "• Used in both STOP and TRAILING modes.\n"
                "• In STOP mode this is the only exit target.\n"
                "• In TRAILING mode the trade may close earlier if the trailing stop is hit.\n"
                "• Valid range: 0.1 – 100."
            ),
            (
                "🛑  Stoploss (%) — BUG #1 FIX",
                "The maximum loss percentage tolerated before the position is force-closed.\n\n"
                "• **IMPORTANT**: For long positions (CALL/PUT buyers), this is applied BELOW the entry price.\n"
                "• Enter the percentage as a **positive number** (e.g., 1.5 for a 1.5% stop).\n"
                "• The system automatically applies the correct sign based on position type.\n"
                "• Valid range: 0.1 – 50."
            ),
            (
                "📈  Trailing First Profit (%) — TRAILING only",
                "The minimum profit the trade must reach before the trailing stop mechanism activates.\n\n"
                "• Prevents the trailing stop from triggering on tiny initial moves.\n"
                "• Once this level is crossed, the trailing ladder begins stepping up.\n"
                "• Must be less than Max Profit. Valid range: 0.1 – 50."
            ),
            (
                "🏆  Max Profit (%) — TRAILING only",
                "The upper ceiling of the trailing profit ladder.\n\n"
                "• The trailing stop will not step beyond this level.\n"
                "• Must be strictly greater than Trailing First Profit.\n"
                "• Think of it as the top rung of the profit ladder. Valid range: 0.1 – 200."
            ),
            (
                "➕  Profit Step (%) — TRAILING only",
                "How much the unrealised profit must increase to move the trailing stop up one step.\n\n"
                "• Smaller steps = tighter trailing, locks in more gains but risks an early exit on normal retracements.\n"
                "• Larger steps = more room for the trade to breathe before the stop moves.\n"
                "• Valid range: 0.1 – 20."
            ),
            (
                "➖  Loss Step (%) — TRAILING only",
                "How far the price is allowed to pull back from its peak profit before the stop fires.\n\n"
                "• This is the 'give-back' allowance above the current trailing stop level.\n"
                "• Smaller values = stop triggered quickly on any dip (tighter protection).\n"
                "• Larger values = trade has more room to rebound before being stopped out.\n"
                "• Valid range: 0.1 – 20."
            ),
            (
                "📁  Where are settings stored?",
                "Profit & stoploss settings are saved locally to:\n\n"
                "    config/profit_stoploss_setting.json\n\n"
                "The file is written atomically to prevent corruption. "
                "Back it up before experimenting with new threshold values."
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

    # ── Profit type toggle ────────────────────────────────────────────────────
    def _on_profit_type_change(self):
        selected = self.profit_type_combo.currentData()
        trailing_keys = {"trailing_first_profit", "max_profit", "profit_step", "loss_step"}

        for key, edit in self.entries.items():
            if key in trailing_keys:
                edit.setEnabled(selected == TRAILING)
                if selected == TRAILING:
                    edit.setStyleSheet(
                        "QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;"
                        "            border-radius:4px; padding:8px; }"
                        "QLineEdit:focus { border:2px solid #58a6ff; }"
                    )
                else:
                    edit.setStyleSheet(
                        "QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;"
                        "            border-radius:4px; padding:8px; }"
                    )

    # ── Validation ────────────────────────────────────────────────────────────
    def validate_field(self, key: str, value: str) -> tuple:
        if not value.strip():
            return False, None, f"{self.VALIDATION_RANGES[key][2]} is required"
        try:
            val = float(value)
            min_val, max_val, name = self.VALIDATION_RANGES[key]

            # BUG #1 FIX: Ensure stoploss is positive
            if key == "stoploss_percentage":
                val = abs(val)

            if not (min_val <= val <= max_val):
                return False, None, f"{name} must be between {min_val} and {max_val}"

            # Special validation for trailing values
            if key == "max_profit":
                trailing_first = float(self.entries["trailing_first_profit"].text() or "0")
                if val <= trailing_first:
                    return False, None, "Max Profit must be greater than Trailing First Profit"

            return True, val, None
        except ValueError:
            return False, None, f"{self.VALIDATION_RANGES[key][2]} must be a valid number"

    # ── Feedback helpers ──────────────────────────────────────────────────────
    def show_success_feedback(self):
        self.status_label.setText("✓ Settings saved successfully!")
        self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
        self.save_btn.setText("✓ Saved!")
        self.save_btn.setStyleSheet(
            "QPushButton { background:#2ea043; color:#fff; border-radius:4px; padding:12px; }"
        )
        for entry in self.entries.values():
            if entry.isEnabled():
                entry.setStyleSheet(
                    "QLineEdit { background:#2d4a2d; color:#e6edf3; border:2px solid #3fb950;"
                    "            border-radius:4px; padding:8px; }"
                )
        QTimer.singleShot(1500, self.reset_styles)

    def show_error_feedback(self, error_msg):
        self.status_label.setText(f"✗ {error_msg}")
        self.status_label.setStyleSheet("color:#f85149; font-size:9pt; font-weight:bold;")
        self.save_btn.setStyleSheet(
            "QPushButton { background:#f85149; color:#fff; border-radius:4px; padding:12px; }"
        )
        QTimer.singleShot(2000, self.reset_styles)

    def reset_styles(self):
        for key, entry in self.entries.items():
            if entry.isEnabled():
                entry.setStyleSheet(
                    "QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;"
                    "            border-radius:4px; padding:8px; }"
                    "QLineEdit:focus { border:2px solid #58a6ff; }"
                )
            else:
                entry.setStyleSheet(
                    "QLineEdit { background:#1a1f26; color:#6e7681; border:1px solid #30363d;"
                    "            border-radius:4px; padding:8px; }"
                )
        self.save_btn.setText("💾 Save Settings")
        self.save_btn.setStyleSheet(
            "QPushButton { background:#238636; color:#fff; border-radius:4px; padding:12px; }"
            "QPushButton:hover { background:#2ea043; }"
        )

    # ── Save logic ────────────────────────────────────────────────────────────
    def save(self):
        # Prevent multiple saves
        if self._save_in_progress:
            logger.warning("Save already in progress")
            return

        self._save_in_progress = True
        self.operation_started.emit()

        self.save_btn.setEnabled(False)
        self.save_btn.setText("⏳ Validating...")
        self.status_label.setText("")

        data_to_save = {}
        validation_errors = []

        profit_type = self.profit_type_combo.currentData()
        required_fields = ["tp_percentage", "stoploss_percentage"]
        if profit_type == TRAILING:
            required_fields.extend(["trailing_first_profit", "max_profit", "profit_step", "loss_step"])

        for key in required_fields:
            edit = self.entries[key]
            is_valid, value, error = self.validate_field(key, edit.text().strip())
            if is_valid:
                data_to_save[key] = value
            else:
                validation_errors.append(error)
                edit.setStyleSheet(
                    "QLineEdit { background:#4d2a2a; color:#e6edf3; border:2px solid #f85149;"
                    "            border-radius:4px; padding:8px; }"
                )

        if validation_errors:
            self.tabs.setCurrentIndex(0)
            self.show_error_feedback(validation_errors[0])
            self.save_btn.setEnabled(True)
            self._save_in_progress = False
            self.operation_finished.emit()
            return

        data_to_save["profit_type"] = profit_type

        def _save():
            try:
                for key, value in data_to_save.items():
                    setattr(self.profit_stoploss_setting, key, value)
                success = self.profit_stoploss_setting.save()
                if success:
                    self.save_completed.emit(True, "Settings saved successfully!")
                else:
                    self.save_completed.emit(False, "Failed to save settings to file")
            except Exception as e:
                self.save_completed.emit(False, str(e))
            finally:
                self._save_in_progress = False
                self.operation_finished.emit()

        threading.Thread(target=_save, daemon=True).start()

    def on_save_completed(self, success, message):
        if success:
            self.show_success_feedback()
            self.save_btn.setEnabled(True)
            # Refresh app if available
            if self.app is not None and hasattr(self.app, "refresh_settings_live"):
                try:
                    self.app.refresh_settings_live()
                except Exception as e:
                    logger.error(f"Failed to refresh app: {e}")
            QTimer.singleShot(2000, self.accept)
        else:
            self.show_error_feedback(message)
            self.save_btn.setEnabled(True)

    def _on_error(self, error_msg: str):
        """Handle error signal"""
        try:
            logger.error(f"Error signal received: {error_msg}")
            self.show_error_feedback(error_msg)
            self.save_btn.setEnabled(True)
            self._save_in_progress = False
        except Exception as e:
            logger.error(f"[ProfitStoplossSettingGUI._on_error] Failed: {e}", exc_info=True)

    def _on_operation_started(self):
        """Handle operation started signal"""
        pass

    def _on_operation_finished(self):
        """Handle operation finished signal"""
        pass

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info("[ProfitStoplossSettingGUI] Starting cleanup")

            # Clear references
            self.profit_stoploss_setting = None
            self.app = None
            self.vars.clear()
            self.entries.clear()
            self.profit_type_combo = None
            self.status_label = None
            self.save_btn = None
            self.cancel_btn = None
            self.tabs = None

            logger.info("[ProfitStoplossSettingGUI] Cleanup completed")

        except Exception as e:
            logger.error(f"[ProfitStoplossSettingGUI.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup"""
        try:
            self.cleanup()
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[ProfitStoplossSettingGUI.closeEvent] Failed: {e}", exc_info=True)
            super().closeEvent(event)