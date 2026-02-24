import logging
import threading
from typing import Optional, Dict, Any, Tuple

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QVBoxLayout, QLabel,
                             QWidget, QTabWidget, QFrame, QScrollArea,
                             QComboBox, QCheckBox)

from gui import DailyTradeSetting

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class DailyTradeSettingGUI(QDialog):
    save_completed = pyqtSignal(bool, str)

    # Rule 3: Additional signals for error handling
    error_occurred = pyqtSignal(str)
    operation_started = pyqtSignal()
    operation_finished = pyqtSignal()

    INTERVAL_CHOICES = [
        ("5 seconds", "5S"), ("10 seconds", "10S"), ("15 seconds", "15S"),
        ("30 seconds", "30S"), ("45 seconds", "45S"), ("1 minute", "1m"),
        ("2 minutes", "2m"), ("3 minutes", "3m"), ("5 minutes", "5m"),
        ("10 minutes", "10m"), ("15 minutes", "15m"), ("20 minutes", "20m"),
        ("30 minutes", "30m"), ("60 minutes", "60m"), ("120 minutes", "120m"),
        ("240 minutes", "240m")
    ]

    VALIDATION_RANGES = {
        "week": (0, 53),
        "lot_size": (1, 10000),
        "call_lookback": (0, 100),
        "put_lookback": (0, 100),
        "max_num_of_option": (1, 10000),
        "lower_percentage": (0, 100),
        "cancel_after": (1, 60),
        "capital_reserve": (0, 1000000),
    }

    def __init__(self, parent, daily_setting: DailyTradeSetting, app=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.daily_setting = daily_setting
            self.app = app

            # Rule 6: Input validation
            if daily_setting is None:
                logger.error("DailyTradeSettingGUI initialized with None daily_setting")

            self.setWindowTitle("Daily Trade Settings")
            self.setModal(True)
            self.setMinimumSize(650, 600)
            self.resize(650, 600)

            # EXACT stylesheet preservation - no changes
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
                QLineEdit, QComboBox {
                    background:#21262d; color:#e6edf3; border:1px solid #30363d;
                    border-radius:4px; padding:8px; font-size:10pt;
                }
                QLineEdit:focus, QComboBox:focus { border:2px solid #58a6ff; }
                QCheckBox { color:#e6edf3; spacing:8px; }
                QCheckBox::indicator { width:18px; height:18px; }
                QCheckBox::indicator:unchecked { border:2px solid #30363d; background:#21262d; border-radius:3px; }
                QCheckBox::indicator:checked   { background:#238636; border:2px solid #2ea043; border-radius:3px; }
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
            """)

            # Root layout
            root = QVBoxLayout(self)
            root.setContentsMargins(16, 16, 16, 16)
            root.setSpacing(12)

            # Header
            header = QLabel("⚙️ Daily Trade Settings")
            header.setFont(QFont("Segoe UI", 14, QFont.Bold))
            header.setStyleSheet("color:#e6edf3; padding:4px;")
            header.setAlignment(Qt.AlignCenter)
            root.addWidget(header)

            # Tabs
            self.tabs = QTabWidget()
            root.addWidget(self.tabs)
            self.tabs.addTab(self._build_settings_tab(), "⚙️ Settings")
            self.tabs.addTab(self._build_info_tab(), "ℹ️ Information")

            # Status + Save (always visible below tabs)
            self.status_label = QLabel("")
            self.status_label.setAlignment(Qt.AlignCenter)
            self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
            root.addWidget(self.status_label)

            self.save_btn = QPushButton("💾 Save All Settings")
            self.save_btn.clicked.connect(self.save)
            root.addWidget(self.save_btn)

            self.save_completed.connect(self.on_save_completed)

            # Connect internal signals
            self._connect_signals()

            logger.info("DailyTradeSettingGUI initialized")

        except Exception as e:
            logger.critical(f"[DailyTradeSettingGUI.__init__] Failed: {e}", exc_info=True)
            # Still try to show a basic dialog
            super().__init__(parent)
            self.daily_setting = daily_setting
            self.app = app
            self._safe_defaults_init()
            self.setWindowTitle("Daily Trade Settings - ERROR")
            self.setMinimumSize(400, 200)

            # Add error message
            layout = QVBoxLayout(self)
            error_label = QLabel(f"Failed to initialize settings dialog:\n{e}")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #f85149; padding: 20px;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.daily_setting = None
        self.app = None
        self.tabs = None
        self.vars = {}
        self.entries = {}
        self.interval_combo = None
        self.sideway_check = None
        self.status_label = None
        self.save_btn = None
        self._save_in_progress = False
        self._save_timer = None

    def _connect_signals(self):
        """Connect internal signals"""
        try:
            self.error_occurred.connect(self._on_error)
            self.operation_started.connect(self._on_operation_started)
            self.operation_finished.connect(self._on_operation_finished)
        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._connect_signals] Failed: {e}", exc_info=True)

    # ── Settings Tab ──────────────────────────────────────────────────────────
    def _build_settings_tab(self):
        """Build the settings tab with form fields"""
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            container = QWidget()
            container.setStyleSheet("background:transparent;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(18, 18, 18, 12)
            layout.setSpacing(4)

            form = QFormLayout()
            form.setSpacing(6)
            form.setVerticalSpacing(3)
            form.setLabelAlignment(Qt.AlignRight)
            form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

            self.vars = {}
            self.entries = {}

            # (label, key, type, icon, placeholder, hint text, tooltip)
            fields = [
                ("Exchange", "exchange", str, "🌐",
                 "e.g. NSE",
                 "The stock exchange to trade on.",
                 "Name of the exchange, e.g. NSE, BSE, NFO."),

                ("Week", "week", int, "📆",
                 "e.g. 0  (0 = current week)",
                 "Week number for options expiry (0–53).",
                 "0 means the current/nearest expiry week. Increase for far-dated contracts."),

                ("Derivative", "derivative", str, "💡",
                 "e.g. NIFTY",
                 "Underlying symbol for the derivative contract.",
                 "The instrument name, e.g. NIFTY, BANKNIFTY."),

                ("Lot Size", "lot_size", int, "🔢",
                 "e.g. 50",
                 "Number of units per lot (1–10 000).",
                 "Standard lot size for the selected derivative on your exchange."),

                ("Call Lookback", "call_lookback", int, "🔎",
                 "e.g. 5",
                 "Number of candles to look back for call signal (0–100).",
                 "How many historical candles the strategy uses to detect a call entry."),

                ("Put Lookback", "put_lookback", int, "🔎",
                 "e.g. 5",
                 "Number of candles to look back for put signal (0–100).",
                 "How many historical candles the strategy uses to detect a put entry."),

                ("Max Num of Option", "max_num_of_option", int, "📈",
                 "e.g. 10",
                 "Maximum open option positions allowed at once (1–10 000).",
                 "The strategy will stop opening new positions once this limit is reached."),

                ("Lower Percentage", "lower_percentage", float, "🔻",
                 "e.g. 0.5",
                 "Minimum percentage move required to trigger an entry (0–100).",
                 "Filters out low-momentum signals. Higher values = stricter entries."),

                ("Cancel After", "cancel_after", int, "⏰",
                 "e.g. 30  (seconds)",
                 "Cancel unfilled orders after this many seconds (1–60).",
                 "Prevents stale orders from sitting in the book too long."),

                ("Capital Reserve", "capital_reserve", int, "💰",
                 "e.g. 50000",
                 "Amount of capital (₹) kept reserved and not deployed (0–1 000 000).",
                 "The strategy will never use more than (total capital − reserve)."),
            ]

            for label, key, typ, icon, placeholder, hint, tooltip in fields:
                try:
                    edit = QLineEdit()
                    edit.setPlaceholderText(placeholder)
                    edit.setToolTip(tooltip)

                    # Safely get value from settings - FIXED: Use explicit None check
                    val = ""
                    if self.daily_setting is not None and hasattr(self.daily_setting, 'data'):
                        val = self.daily_setting.data.get(key, "")
                    edit.setText(str(val))

                    hint_lbl = QLabel(hint)
                    hint_lbl.setStyleSheet("color:#484f58; font-size:8pt;")

                    form.addRow(f"{icon} {label}:", edit)
                    form.addRow("", hint_lbl)

                    self.vars[key] = (edit, typ)
                    self.entries[key] = edit

                except Exception as e:
                    logger.error(f"Failed to create field {key}: {e}", exc_info=True)
                    # Add a placeholder to maintain layout
                    edit = QLineEdit()
                    edit.setPlaceholderText("Error loading field")
                    edit.setEnabled(False)
                    form.addRow(f"{icon} {label}:", edit)

            # History Interval ComboBox
            try:
                self.interval_combo = QComboBox()
                for display, value in self.INTERVAL_CHOICES:
                    self.interval_combo.addItem(display, value)

                current_val = "2m"
                # FIXED: Use explicit None check
                if self.daily_setting is not None and hasattr(self.daily_setting, 'data'):
                    current_val = self.daily_setting.data.get("history_interval", "2m")

                found = False
                for i in range(self.interval_combo.count()):
                    if self.interval_combo.itemData(i) == current_val:
                        self.interval_combo.setCurrentIndex(i)
                        found = True
                        break

                if not found:
                    logger.warning(f"Interval value {current_val} not found in choices")

                self.interval_combo.setToolTip(
                    "Candle interval used to fetch historical price data.\n"
                    "Smaller intervals = more granular signals but heavier data load."
                )
                interval_hint = QLabel("Candle size used for historical data and signal generation.")
                interval_hint.setStyleSheet("color:#484f58; font-size:8pt;")
                form.addRow("⏱️ History Interval:", self.interval_combo)
                form.addRow("", interval_hint)

            except Exception as e:
                logger.error(f"Failed to create interval combo: {e}", exc_info=True)
                self.interval_combo = QComboBox()
                self.interval_combo.addItem("Error", "2m")
                form.addRow("⏱️ History Interval:", self.interval_combo)

            layout.addLayout(form)

            # Sideway Zone checkbox
            try:
                self.sideway_check = QCheckBox("Enable trading during sideways market (12:00–14:00)")

                checked = False
                # FIXED: Use explicit None check
                if self.daily_setting is not None and hasattr(self.daily_setting, 'data'):
                    checked = self.daily_setting.data.get("sideway_zone_trade", False)
                self.sideway_check.setChecked(checked)

                self.sideway_check.setToolTip(
                    "When enabled, the strategy will continue placing orders during the\n"
                    "low-volatility midday window (12:00–14:00). Disable to avoid choppy moves."
                )
                sideway_hint = QLabel("Allow entries during the low-volatility midday window.")
                sideway_hint.setStyleSheet("color:#484f58; font-size:8pt; padding-left:26px;")

                layout.addWidget(self.sideway_check)
                layout.addWidget(sideway_hint)

            except Exception as e:
                logger.error(f"Failed to create sideway checkbox: {e}", exc_info=True)
                self.sideway_check = QCheckBox("Error loading setting")
                self.sideway_check.setEnabled(False)
                layout.addWidget(self.sideway_check)

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._build_settings_tab] Failed: {e}", exc_info=True)
            # Return a basic scroll area on error
            scroll = QScrollArea()
            container = QWidget()
            layout = QVBoxLayout(container)
            error_label = QLabel(f"Error building settings tab: {e}")
            error_label.setStyleSheet("color: #f85149;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
            scroll.setWidget(container)
            return scroll

    # ── Information Tab ───────────────────────────────────────────────────────
    def _build_info_tab(self):
        """Build the information tab with help content"""
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(12)

            infos = [
                (
                    "🌐  Exchange",
                    "Specifies the stock exchange where trades will be placed.\n\n"
                    "• Common values: NSE (equities), NFO (F&O), BSE.\n"
                    "• Must match the exchange codes supported by your brokerage API.\n"
                    "• Incorrect values will cause order rejection at the broker level."
                ),
                (
                    "📆  Week",
                    "Selects the expiry week for options contracts.\n\n"
                    "• 0 = current/nearest expiry week (most liquid).\n"
                    "• 1 = next week's expiry, 2 = two weeks out, and so on.\n"
                    "• Higher values select far-dated contracts with wider spreads."
                ),
                (
                    "💡  Derivative",
                    "The underlying instrument whose options or futures will be traded.\n\n"
                    "• Examples: NIFTY, BANKNIFTY, FINNIFTY.\n"
                    "• Must match the symbol name exactly as listed on your exchange.\n"
                    "• The lot size and contract specs depend on this choice."
                ),
                (
                    "🔢  Lot Size",
                    "The number of units in one contract lot for the chosen derivative.\n\n"
                    "• NIFTY = 50 units/lot, BANKNIFTY = 15 units/lot (subject to exchange changes).\n"
                    "• The strategy multiplies this by the number of lots to compute order quantity.\n"
                    "• Setting the wrong lot size will cause over- or under-sized orders."
                ),
                (
                    "🔎  Call / Put Lookback",
                    "The number of historical candles the strategy looks back to detect an entry signal.\n\n"
                    "• A higher lookback = smoother, slower signals (fewer false entries).\n"
                    "• A lower lookback = faster, noisier signals (more trades, more risk).\n"
                    "• Call and Put lookbacks can be tuned independently."
                ),
                (
                    "📈  Max Num of Option",
                    "The maximum number of open option positions the bot will hold simultaneously.\n\n"
                    "• Once this limit is reached, no new positions are opened until existing ones close.\n"
                    "• Acts as a hard position-size cap to limit overall exposure.\n"
                    "• Recommended: start low (e.g. 2–5) and increase only after backtesting."
                ),
                (
                    "🔻  Lower Percentage",
                    "A momentum filter — the minimum percentage price move required before an entry is triggered.\n\n"
                    "• Higher value = stricter filter, fewer but potentially higher-quality entries.\n"
                    "• Lower value = more entries, but with more false signals.\n"
                    "• Expressed as a percentage, e.g. 0.5 means 0.5% minimum move."
                ),
                (
                    "⏰  Cancel After",
                    "If a limit order is not filled within this many seconds, it is automatically cancelled.\n\n"
                    "• Prevents stale orders from sitting in the order book during fast-moving markets.\n"
                    "• Set lower (e.g. 10–15s) for highly liquid instruments.\n"
                    "• Set higher for less liquid contracts where fills may take longer."
                ),
                (
                    "💰  Capital Reserve",
                    "The amount of capital (in ₹) that is always kept aside and never deployed.\n\n"
                    "• The strategy uses: available capital − reserve for sizing positions.\n"
                    "• Useful for maintaining a buffer against margin calls or unexpected losses.\n"
                    "• Set to 0 to allow full capital deployment."
                ),
                (
                    "⏱️  History Interval",
                    "The candle timeframe used when fetching historical price data for signal generation.\n\n"
                    "• Smaller intervals (e.g. 5S, 1m) = more granular signals, heavier API load.\n"
                    "• Larger intervals (e.g. 15m, 30m) = slower signals, less data bandwidth.\n"
                    "• Match this to the timeframe your strategy was designed and backtested on."
                ),
                (
                    "↔️  Sideway Zone Trade",
                    "Controls whether the bot continues trading during the low-volatility midday window (12:00–14:00).\n\n"
                    "• Disabled (default): the bot pauses entries during this window to avoid choppy price action.\n"
                    "• Enabled: the bot treats this window like any other session.\n"
                    "• Recommended to leave disabled unless your strategy is specifically tuned for low-vol conditions."
                ),
                (
                    "📁  Where are settings stored?",
                    "Daily trade settings are saved locally to:\n\n"
                    "    config/daily_trade_setting.json\n\n"
                    "The file is written atomically to prevent corruption on unexpected exits. "
                    "Back up this file before making major strategy changes."
                ),
            ]

            for title, body in infos:
                try:
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

                except Exception as e:
                    logger.error(f"Failed to create info card for {title}: {e}", exc_info=True)
                    # Skip this card but continue

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._build_info_tab] Failed: {e}", exc_info=True)
            # Return a basic scroll area on error
            scroll = QScrollArea()
            container = QWidget()
            layout = QVBoxLayout(container)
            error_label = QLabel(f"Error building information tab: {e}")
            error_label.setStyleSheet("color: #f85149;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
            scroll.setWidget(container)
            return scroll

    # ── Validation ────────────────────────────────────────────────────────────
    def validate_field(self, key: str, value: str, typ: type) -> Tuple[bool, Any, Optional[str]]:
        """Validate a field value against type and range constraints"""
        try:
            # Rule 6: Input validation
            if not isinstance(key, str):
                logger.warning(f"validate_field called with non-string key: {key}")
                return False, None, "Invalid field key"

            if not value.strip():
                # Empty string is allowed for some fields (converted to default later)
                return True, (0 if typ in (int, float) else ""), None

            try:
                if typ == int:
                    val = int(float(value))
                    if key in self.VALIDATION_RANGES:
                        lo, hi = self.VALIDATION_RANGES[key]
                        if not (lo <= val <= hi):
                            return False, None, f"{key} must be between {lo} and {hi}"
                    return True, val, None

                elif typ == float:
                    val = float(value)
                    if key in self.VALIDATION_RANGES:
                        lo, hi = self.VALIDATION_RANGES[key]
                        if not (lo <= val <= hi):
                            return False, None, f"{key} must be between {lo} and {hi}"
                    return True, val, None

                else:  # str
                    return True, value, None

            except ValueError as e:
                logger.debug(f"ValueError validating {key}={value}: {e}")
                return False, None, f"Invalid {typ.__name__} value for {key}"

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.validate_field] Failed for {key}: {e}", exc_info=True)
            return False, None, f"Validation error for {key}"

    # ── Feedback helpers ──────────────────────────────────────────────────────
    def show_success_feedback(self):
        """Show success feedback with animation"""
        try:
            self.status_label.setText("✓ Settings saved successfully!")
            self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
            self.save_btn.setText("✓ Saved!")
            self.save_btn.setStyleSheet(
                "QPushButton { background:#2ea043; color:#fff; border-radius:4px; padding:12px; }"
            )
            # FIXED: Use explicit None checks in loop
            for entry in self.entries.values():
                if entry is not None:
                    entry.setStyleSheet(
                        "QLineEdit { background:#2d4a2d; color:#e6edf3; border:2px solid #3fb950;"
                        "            border-radius:4px; padding:8px; }"
                    )
            QTimer.singleShot(1500, self.reset_styles)

            logger.info("Success feedback shown")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.show_success_feedback] Failed: {e}", exc_info=True)

    def show_error_feedback(self, error_msg):
        """Show error feedback with animation"""
        try:
            self.status_label.setText(f"✗ {error_msg}")
            self.status_label.setStyleSheet("color:#f85149; font-size:9pt; font-weight:bold;")
            self.save_btn.setStyleSheet(
                "QPushButton { background:#f85149; color:#fff; border-radius:4px; padding:12px; }"
            )
            QTimer.singleShot(2000, self.reset_styles)

            logger.warning(f"Error feedback shown: {error_msg}")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.show_error_feedback] Failed: {e}", exc_info=True)

    def reset_styles(self):
        """Reset all styles to normal"""
        try:
            # FIXED: Use explicit None checks
            for entry in self.entries.values():
                if entry is not None:
                    entry.setStyleSheet(
                        "QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;"
                        "            border-radius:4px; padding:8px; }"
                        "QLineEdit:focus { border:2px solid #58a6ff; }"
                    )

            # FIXED: Use explicit None check
            if self.interval_combo is not None:
                self.interval_combo.setStyleSheet(
                    "QComboBox { background:#21262d; color:#e6edf3; border:1px solid #30363d;"
                    "            border-radius:4px; padding:8px; font-size:10pt; }"
                    "QComboBox:focus { border:2px solid #58a6ff; }"
                )

            self.save_btn.setText("💾 Save All Settings")
            self.save_btn.setStyleSheet(
                "QPushButton { background:#238636; color:#fff; border-radius:4px; padding:12px; }"
                "QPushButton:hover { background:#2ea043; }"
            )

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.reset_styles] Failed: {e}", exc_info=True)

    # ── Save logic ────────────────────────────────────────────────────────────
    def save(self):
        """Save settings with validation and background thread"""
        try:
            # Prevent multiple saves
            if self._save_in_progress:
                logger.warning("Save already in progress")
                return

            self._save_in_progress = True
            self.operation_started.emit()

            self.save_btn.setEnabled(False)
            self.save_btn.setText("⏳ Saving...")
            self.status_label.setText("")

            data_to_save = {}
            validation_errors = []

            # Validate all fields
            for key, (edit, typ) in self.vars.items():
                try:
                    # FIXED: Use explicit None check
                    if edit is None:
                        logger.warning(f"Edit widget for {key} is None")
                        continue

                    text = edit.text().strip()
                    is_valid, value, error = self.validate_field(key, text, typ)

                    if is_valid:
                        data_to_save[key] = value
                    else:
                        validation_errors.append(error or f"Invalid value for {key}")
                        if edit is not None:
                            edit.setStyleSheet(
                                "QLineEdit { background:#4d2a2a; color:#e6edf3; border:2px solid #f85149;"
                                "            border-radius:4px; padding:8px; }"
                            )
                except Exception as e:
                    logger.error(f"Error validating field {key}: {e}", exc_info=True)
                    validation_errors.append(f"Validation error for {key}")

            if validation_errors:
                # FIXED: Use explicit None check
                if self.tabs is not None:
                    self.tabs.setCurrentIndex(0)
                self.show_error_feedback(validation_errors[0])
                self.save_btn.setEnabled(True)
                self._save_in_progress = False
                self.operation_finished.emit()
                return

            # Add combo box and checkbox values - FIXED: Use explicit None checks
            if self.interval_combo is not None:
                data_to_save["history_interval"] = self.interval_combo.currentData()

            if self.sideway_check is not None:
                data_to_save["sideway_zone_trade"] = self.sideway_check.isChecked()

            # Save in background thread
            threading.Thread(target=self._threaded_save,
                             args=(data_to_save,),
                             daemon=True, name="DailyTradeSave").start()

            logger.info("Save operation started in background thread")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.save] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Save failed: {e}")
            self._save_in_progress = False
            self.operation_finished.emit()
            self.save_btn.setEnabled(True)

    def _threaded_save(self, data_to_save: Dict[str, Any]):
        """Threaded save operation"""
        try:
            # Rule 6: Validate daily setting (already correct - explicit None check)
            if self.daily_setting is None:
                raise ValueError("Daily setting object is None")

            # Update settings
            for key, value in data_to_save.items():
                try:
                    if hasattr(self.daily_setting, key):
                        setattr(self.daily_setting, key, value)
                    else:
                        logger.warning(f"Setting {key} not found in daily_setting")
                except Exception as e:
                    logger.error(f"Failed to set {key}={value}: {e}", exc_info=True)

            # Save to file
            success = False
            if hasattr(self.daily_setting, 'save'):
                success = self.daily_setting.save()
            else:
                logger.error("Daily setting object has no save method")

            if success:
                self.save_completed.emit(True, "Settings saved successfully!")
                logger.info("Daily trade settings saved successfully")
            else:
                self.save_completed.emit(False, "Failed to save settings to file")
                logger.error("Failed to save daily trade settings to file")

        except Exception as e:
            logger.error(f"Threaded save failed: {e}", exc_info=True)
            self.save_completed.emit(False, str(e))

        finally:
            self._save_in_progress = False
            self.operation_finished.emit()

    def on_save_completed(self, success, message):
        """Handle save completion"""
        try:
            if success:
                self.show_success_feedback()
                self.save_btn.setEnabled(True)

                # Refresh app if available
                if self.app is not None and hasattr(self.app, "refresh_settings_live"):
                    try:
                        self.app.refresh_settings_live()
                        logger.debug("App settings refreshed")
                    except Exception as e:
                        logger.error(f"Failed to refresh app: {e}", exc_info=True)

                QTimer.singleShot(2000, self.accept)
            else:
                self.show_error_feedback(f"Failed to save: {message}")
                self.save_btn.setEnabled(True)

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.on_save_completed] Failed: {e}", exc_info=True)

    def _on_error(self, error_msg: str):
        """Handle error signal"""
        try:
            logger.error(f"Error signal received: {error_msg}")
            self.show_error_feedback(error_msg)
            self.save_btn.setEnabled(True)
            self._save_in_progress = False
        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._on_error] Failed: {e}", exc_info=True)

    def _on_operation_started(self):
        """Handle operation started signal"""
        try:
            # Disable close button or any other UI elements if needed
            pass
        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._on_operation_started] Failed: {e}", exc_info=True)

    def _on_operation_finished(self):
        """Handle operation finished signal"""
        try:
            # Re-enable UI elements if needed
            pass
        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._on_operation_finished] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info("[DailyTradeSettingGUI] Starting cleanup")

            # Cancel any pending timers - FIXED: Use explicit None check
            if hasattr(self, '_save_timer') and self._save_timer is not None:
                try:
                    if self._save_timer.isActive():
                        self._save_timer.stop()
                except Exception as e:
                    logger.warning(f"Error stopping timer: {e}")

            # Clear references
            self.daily_setting = None
            self.app = None
            self.vars.clear()
            self.entries.clear()
            self.interval_combo = None
            self.sideway_check = None
            self.status_label = None
            self.save_btn = None
            self.tabs = None

            logger.info("[DailyTradeSettingGUI] Cleanup completed")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup"""
        try:
            # Cancel save if in progress
            if self._save_in_progress:
                logger.warning("Closing while save in progress")

            self.cleanup()
            event.accept()

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.closeEvent] Failed: {e}", exc_info=True)
            event.accept()