# PYQT: Converted from Tkinter to PyQt5 QDialog - class name preserved
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QVBoxLayout, QLabel,
                             QWidget, QTabWidget, QFrame, QScrollArea,
                             QComboBox, QCheckBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
import threading

from gui import DailyTradeSetting


class DailyTradeSettingGUI(QDialog):
    save_completed = pyqtSignal(bool, str)

    INTERVAL_CHOICES = [
        ("5 seconds",   "5S"),  ("10 seconds", "10S"), ("15 seconds", "15S"),
        ("30 seconds",  "30S"), ("45 seconds", "45S"), ("1 minute",   "1m"),
        ("2 minutes",   "2m"),  ("3 minutes",  "3m"),  ("5 minutes",  "5m"),
        ("10 minutes",  "10m"), ("15 minutes", "15m"), ("20 minutes", "20m"),
        ("30 minutes",  "30m"), ("60 minutes", "60m"), ("120 minutes","120m"),
        ("240 minutes", "240m")
    ]

    VALIDATION_RANGES = {
        "week":              (0,  53),
        "lot_size":          (1,  10000),
        "call_lookback":     (0,  100),
        "put_lookback":      (0,  100),
        "max_num_of_option": (1,  10000),
        "lower_percentage":  (0,  100),
        "cancel_after":      (1,  60),
        "capital_reserve":   (0,  1000000),
    }

    def __init__(self, parent, daily_setting: DailyTradeSetting, app=None):
        super().__init__(parent)
        self.daily_setting = daily_setting
        self.app = app
        self.setWindowTitle("Daily Trade Settings")
        self.setModal(True)
        self.setMinimumSize(650, 600)
        self.resize(650, 600)
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
        self.tabs.addTab(self._build_info_tab(),     "ℹ️ Information")

        # Status + Save (always visible below tabs)
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
        root.addWidget(self.status_label)

        self.save_btn = QPushButton("💾 Save All Settings")
        self.save_btn.clicked.connect(self.save)
        root.addWidget(self.save_btn)

        self.save_completed.connect(self.on_save_completed)

    # ── Settings Tab ──────────────────────────────────────────────────────────
    def _build_settings_tab(self):
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

        self.vars    = {}
        self.entries = {}

        # (label, key, type, icon, placeholder, hint text, tooltip)
        fields = [
            ("Exchange",          "exchange",          str,   "🌐",
             "e.g. NSE",
             "The stock exchange to trade on.",
             "Name of the exchange, e.g. NSE, BSE, NFO."),

            ("Week",              "week",              int,   "📆",
             "e.g. 0  (0 = current week)",
             "Week number for options expiry (0–53).",
             "0 means the current/nearest expiry week. Increase for far-dated contracts."),

            ("Derivative",        "derivative",        str,   "💡",
             "e.g. NIFTY",
             "Underlying symbol for the derivative contract.",
             "The instrument name, e.g. NIFTY, BANKNIFTY."),

            ("Lot Size",          "lot_size",          int,   "🔢",
             "e.g. 50",
             "Number of units per lot (1–10 000).",
             "Standard lot size for the selected derivative on your exchange."),

            ("Call Lookback",     "call_lookback",     int,   "🔎",
             "e.g. 5",
             "Number of candles to look back for call signal (0–100).",
             "How many historical candles the strategy uses to detect a call entry."),

            ("Put Lookback",      "put_lookback",      int,   "🔎",
             "e.g. 5",
             "Number of candles to look back for put signal (0–100).",
             "How many historical candles the strategy uses to detect a put entry."),

            ("Max Num of Option", "max_num_of_option", int,   "📈",
             "e.g. 10",
             "Maximum open option positions allowed at once (1–10 000).",
             "The strategy will stop opening new positions once this limit is reached."),

            ("Lower Percentage",  "lower_percentage",  float, "🔻",
             "e.g. 0.5",
             "Minimum percentage move required to trigger an entry (0–100).",
             "Filters out low-momentum signals. Higher values = stricter entries."),

            ("Cancel After",      "cancel_after",      int,   "⏰",
             "e.g. 30  (seconds)",
             "Cancel unfilled orders after this many seconds (1–60).",
             "Prevents stale orders from sitting in the book too long."),

            ("Capital Reserve",   "capital_reserve",   int,   "💰",
             "e.g. 50000",
             "Amount of capital (₹) kept reserved and not deployed (0–1 000 000).",
             "The strategy will never use more than (total capital − reserve)."),
        ]

        for label, key, typ, icon, placeholder, hint, tooltip in fields:
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setToolTip(tooltip)
            val = self.daily_setting.data.get(key, "")
            edit.setText(str(val))

            hint_lbl = QLabel(hint)
            hint_lbl.setStyleSheet("color:#484f58; font-size:8pt;")

            form.addRow(f"{icon} {label}:", edit)
            form.addRow("", hint_lbl)

            self.vars[key]    = (edit, typ)
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
        self.interval_combo.setToolTip(
            "Candle interval used to fetch historical price data.\n"
            "Smaller intervals = more granular signals but heavier data load."
        )
        interval_hint = QLabel("Candle size used for historical data and signal generation.")
        interval_hint.setStyleSheet("color:#484f58; font-size:8pt;")
        form.addRow("⏱️ History Interval:", self.interval_combo)
        form.addRow("", interval_hint)

        layout.addLayout(form)

        # Sideway Zone checkbox
        self.sideway_check = QCheckBox("Enable trading during sideways market (12:00–14:00)")
        self.sideway_check.setChecked(self.daily_setting.data.get("sideway_zone_trade", False))
        self.sideway_check.setToolTip(
            "When enabled, the strategy will continue placing orders during the\n"
            "low-volatility midday window (12:00–14:00). Disable to avoid choppy moves."
        )
        sideway_hint = QLabel("Allow entries during the low-volatility midday window.")
        sideway_hint.setStyleSheet("color:#484f58; font-size:8pt; padding-left:26px;")

        layout.addWidget(self.sideway_check)
        layout.addWidget(sideway_hint)
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

    # ── Validation ────────────────────────────────────────────────────────────
    def validate_field(self, key: str, value: str, typ: type) -> tuple:
        if not value.strip():
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
            else:
                return True, value, None
        except ValueError:
            return False, None, f"Invalid {typ.__name__} value for {key}"

    # ── Feedback helpers ──────────────────────────────────────────────────────
    def show_success_feedback(self):
        self.status_label.setText("✓ Settings saved successfully!")
        self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
        self.save_btn.setText("✓ Saved!")
        self.save_btn.setStyleSheet(
            "QPushButton { background:#2ea043; color:#fff; border-radius:4px; padding:12px; }"
        )
        for entry in self.entries.values():
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
        for entry in self.entries.values():
            entry.setStyleSheet(
                "QLineEdit { background:#21262d; color:#e6edf3; border:1px solid #30363d;"
                "            border-radius:4px; padding:8px; }"
                "QLineEdit:focus { border:2px solid #58a6ff; }"
            )
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

    # ── Save logic ────────────────────────────────────────────────────────────
    def save(self):
        self.save_btn.setEnabled(False)
        self.save_btn.setText("⏳ Saving...")
        self.status_label.setText("")

        data_to_save      = {}
        validation_errors = []

        for key, (edit, typ) in self.vars.items():
            is_valid, value, error = self.validate_field(key, edit.text().strip(), typ)
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
            return

        data_to_save["history_interval"]  = self.interval_combo.currentData()
        data_to_save["sideway_zone_trade"] = self.sideway_check.isChecked()

        def _save():
            try:
                for key, value in data_to_save.items():
                    setattr(self.daily_setting, key, value)
                success = self.daily_setting.save()
                if success:
                    self.save_completed.emit(True,  "Settings saved successfully!")
                else:
                    self.save_completed.emit(False, "Failed to save settings to file")
            except Exception as e:
                self.save_completed.emit(False, str(e))

        threading.Thread(target=_save, daemon=True).start()

    def on_save_completed(self, success, message):
        if success:
            self.show_success_feedback()
            self.save_btn.setEnabled(True)
            if self.app and hasattr(self.app, "refresh_settings_live"):
                try:
                    self.app.refresh_settings_live()
                except Exception as e:
                    print(f"Failed to refresh app: {e}")
            QTimer.singleShot(2000, self.accept)
        else:
            self.show_error_feedback(f"Failed to save: {message}")
            self.save_btn.setEnabled(True)