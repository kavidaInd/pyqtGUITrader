"""
TradingModeSettingGUI.py
========================
PyQt5 GUI for trading mode settings with support for new features.
"""

import logging
import logging.handlers
import traceback
from typing import Optional

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QPushButton, QComboBox, QDoubleSpinBox, QSpinBox,
                             QCheckBox, QGroupBox, QLabel, QMessageBox,
                             QTabWidget, QFrame, QScrollArea, QWidget, QLineEdit)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from gui.TradingModeSetting import TradingMode, TradingModeSetting

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TradingModeSettingGUI(QDialog):
    def __init__(self, parent=None, trading_mode_setting=None, app=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.trading_mode_setting = trading_mode_setting or TradingModeSetting()
            self.app = app

            # Rule 6: Input validation
            if trading_mode_setting is None:
                logger.warning("TradingModeSettingGUI initialized with None trading_mode_setting, using default")

            self.setWindowTitle("Trading Mode Settings")
            self.setModal(True)
            self.setMinimumSize(750, 700)  # Increased size for new tabs
            self.resize(750, 700)

            # Match the exact style from DailyTradeSettingGUI
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
                    background:#21262d;
                    color:#e6edf3;
                    border:1px solid #30363d;
                    border-radius:6px;
                    margin-top:12px;
                    font-weight:bold;
                    font-size:10pt;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px 0 5px;
                }
                QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {
                    background:#21262d; color:#e6edf3; border:1px solid #30363d;
                    border-radius:4px; padding:8px; font-size:10pt;
                    min-height:20px;
                }
                QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus { 
                    border:2px solid #58a6ff; 
                }
                QComboBox::drop-down { border:none; }
                QComboBox::down-arrow { 
                    image: none; 
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 5px solid #8b949e;
                    margin-right: 5px;
                }
                QCheckBox { color:#e6edf3; spacing:8px; }
                QCheckBox::indicator { width:18px; height:18px; }
                QCheckBox::indicator:unchecked { 
                    border:2px solid #30363d; 
                    background:#21262d; 
                    border-radius:3px; 
                }
                QCheckBox::indicator:checked { 
                    background:#238636; 
                    border:2px solid #2ea043; 
                    border-radius:3px; 
                }
                QPushButton {
                    background:#238636; color:#fff; border-radius:4px; padding:12px;
                    font-weight:bold; font-size:10pt; min-width:100px;
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
            header = QLabel("⚙️ Trading Mode Settings")
            header.setFont(QFont("Segoe UI", 14, QFont.Bold))
            header.setStyleSheet("color:#e6edf3; padding:4px;")
            header.setAlignment(Qt.AlignCenter)
            root.addWidget(header)

            # Tabs
            self.tabs = QTabWidget()
            root.addWidget(self.tabs)

            # Add tabs
            self.tabs.addTab(self._build_mode_tab(), "🎮 Mode")
            self.tabs.addTab(self._build_risk_tab(), "⚠️ Risk")  # FEATURE 1
            self.tabs.addTab(self._build_mtf_tab(), "📈 MTF Filter")  # FEATURE 6
            self.tabs.addTab(self._build_signal_tab(), "🎯 Signal")  # FEATURE 3
            self.tabs.addTab(self._build_info_tab(), "ℹ️ Information")

            # Status + Buttons layout
            bottom_layout = QVBoxLayout()
            bottom_layout.setSpacing(8)

            self.status_label = QLabel("")
            self.status_label.setAlignment(Qt.AlignCenter)
            self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
            bottom_layout.addWidget(self.status_label)

            # Buttons
            button_layout = QHBoxLayout()
            button_layout.addStretch()

            self.save_btn = QPushButton("💾 Save Settings")
            self.save_btn.clicked.connect(self._save_settings)
            self.apply_btn = QPushButton("✅ Apply")
            self.apply_btn.clicked.connect(self._apply_settings)
            self.cancel_btn = QPushButton("✕ Cancel")
            self.cancel_btn.clicked.connect(self.reject)

            button_layout.addWidget(self.save_btn)
            button_layout.addWidget(self.apply_btn)
            button_layout.addWidget(self.cancel_btn)

            bottom_layout.addLayout(button_layout)
            root.addLayout(bottom_layout)

            self._load_settings()
            logger.info("TradingModeSettingGUI initialized")

        except Exception as e:
            logger.critical(f"[TradingModeSettingGUI.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.trading_mode_setting = None
        self.app = None
        self.tabs = None
        self.mode_combo = None
        self.safety_warning = None
        self.allow_live_check = None
        self.confirm_live_check = None
        self.sim_group = None
        self.paper_balance_spin = None
        self.slippage_check = None
        self.slippage_spin = None
        self.delay_check = None
        self.delay_spin = None

        # FEATURE 6 widgets
        self.mtf_check = None
        self.mtf_timeframes_edit = None
        self.mtf_ema_fast_spin = None
        self.mtf_ema_slow_spin = None
        self.mtf_agreement_spin = None

        # FEATURE 1 widgets
        self.max_loss_spin = None
        self.max_trades_spin = None
        self.daily_target_spin = None

        # FEATURE 3 widgets
        self.min_confidence_spin = None

        self.save_btn = None
        self.cancel_btn = None
        self.apply_btn = None
        self.status_label = None
        self._save_in_progress = False

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            super().__init__(parent)
            self.setWindowTitle("Trading Mode Settings - ERROR")
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
            logger.error(f"[TradingModeSettingGUI._create_error_dialog] Failed: {e}", exc_info=True)

    # ── Mode Tab (Original) ───────────────────────────────────────────────────
    def _build_mode_tab(self):
        """Build the mode selection tab"""
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            container = QWidget()
            container.setStyleSheet("background:transparent;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(18, 18, 18, 12)
            layout.setSpacing(12)

            # Mode Selection Group with description
            mode_group = QGroupBox("Trading Mode")
            mode_layout = QVBoxLayout(mode_group)
            mode_layout.setSpacing(8)

            # Mode combo with form layout for better alignment
            mode_form = QFormLayout()
            mode_form.setSpacing(6)
            mode_form.setLabelAlignment(Qt.AlignRight)

            self.mode_combo = QComboBox()
            self.mode_combo.addItem("🖥️ Simulation (Paper Trading)", TradingMode.SIM.value)
            self.mode_combo.addItem("💰 Live Trading", TradingMode.LIVE.value)
            self.mode_combo.addItem("📊 Backtest", TradingMode.BACKTEST.value)
            self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

            mode_form.addRow("Select Mode:", self.mode_combo)
            mode_layout.addLayout(mode_form)

            # Mode description
            mode_desc = QLabel(
                "• Simulation: Test strategies with virtual money\n"
                "• Live: Real trading with actual funds (requires safety checks)\n"
                "• Backtest: Run strategy on historical data"
            )
            mode_desc.setStyleSheet("color:#8b949e; font-size:9pt; padding:8px; background:#161b22; border-radius:4px;")
            mode_desc.setWordWrap(True)
            mode_layout.addWidget(mode_desc)

            # Safety warning
            self.safety_warning = QLabel("⚠️ LIVE MODE - Real money will be used!")
            self.safety_warning.setStyleSheet(
                "color: #f85149; font-weight: bold; padding: 8px; background:#2d1a1a; border-radius:4px;")
            self.safety_warning.setVisible(False)
            self.safety_warning.setWordWrap(True)
            mode_layout.addWidget(self.safety_warning)

            layout.addWidget(mode_group)

            # Safety Settings Group with descriptions
            safety_group = QGroupBox("Safety Settings")
            safety_layout = QVBoxLayout(safety_group)
            safety_layout.setSpacing(8)

            self.allow_live_check = QCheckBox("✅ Enable live trading (off by default for safety)")
            self.allow_live_check.setToolTip("Must be checked to allow any live trades")
            self.allow_live_check.stateChanged.connect(self._update_ui_state)
            safety_layout.addWidget(self.allow_live_check)

            allow_desc = QLabel(
                "Safety switch for live trading. Must be explicitly enabled "
                "to prevent accidental real-money trades."
            )
            allow_desc.setStyleSheet("color:#8b949e; font-size:8pt; padding-left:26px;")
            allow_desc.setWordWrap(True)
            safety_layout.addWidget(allow_desc)

            self.confirm_live_check = QCheckBox("⚠️ Confirm each live trade before execution")
            self.confirm_live_check.setChecked(True)
            safety_layout.addWidget(self.confirm_live_check)

            confirm_desc = QLabel(
                "When enabled, you'll be prompted to approve each trade before it's sent to the exchange. "
                "Recommended for beginners and when testing new strategies."
            )
            confirm_desc.setStyleSheet("color:#8b949e; font-size:8pt; padding-left:26px;")
            confirm_desc.setWordWrap(True)
            safety_layout.addWidget(confirm_desc)

            layout.addWidget(safety_group)

            # Simulation Settings Group with descriptions
            self.sim_group = QGroupBox("Simulation Settings")
            sim_layout = QVBoxLayout(self.sim_group)
            sim_layout.setSpacing(8)

            # Paper balance
            balance_form = QFormLayout()
            balance_form.setSpacing(4)
            balance_form.setLabelAlignment(Qt.AlignRight)

            self.paper_balance_spin = QDoubleSpinBox()
            self.paper_balance_spin.setRange(1000, 10000000)
            self.paper_balance_spin.setSingleStep(10000)
            self.paper_balance_spin.setPrefix("₹ ")
            self.paper_balance_spin.setValue(100000)
            balance_form.addRow("Initial Balance:", self.paper_balance_spin)
            sim_layout.addLayout(balance_form)

            balance_desc = QLabel(
                "Starting virtual capital for paper trading. Used to simulate position sizing "
                "and track performance metrics."
            )
            balance_desc.setStyleSheet("color:#8b949e; font-size:8pt;")
            balance_desc.setWordWrap(True)
            sim_layout.addWidget(balance_desc)

            # Slippage
            self.slippage_check = QCheckBox("📉 Simulate slippage")
            sim_layout.addWidget(self.slippage_check)

            slippage_form = QFormLayout()
            slippage_form.setSpacing(4)
            slippage_form.setLabelAlignment(Qt.AlignRight)

            self.slippage_spin = QDoubleSpinBox()
            self.slippage_spin.setRange(0, 1)
            self.slippage_spin.setSingleStep(0.01)
            self.slippage_spin.setSuffix(" %")
            self.slippage_spin.setValue(0.05)
            slippage_form.addRow("Slippage:", self.slippage_spin)
            sim_layout.addLayout(slippage_form)

            slippage_desc = QLabel(
                "Simulates the difference between expected and actual fill price. "
                "0.05% = 5 paise per ₹100. Helps make backtests more realistic."
            )
            slippage_desc.setStyleSheet("color:#8b949e; font-size:8pt; padding-left:26px;")
            slippage_desc.setWordWrap(True)
            sim_layout.addWidget(slippage_desc)

            # Delay
            self.delay_check = QCheckBox("⏱️ Simulate order delay")
            sim_layout.addWidget(self.delay_check)

            delay_form = QFormLayout()
            delay_form.setSpacing(4)
            delay_form.setLabelAlignment(Qt.AlignRight)

            self.delay_spin = QSpinBox()
            self.delay_spin.setRange(0, 5000)
            self.delay_spin.setSingleStep(100)
            self.delay_spin.setSuffix(" ms")
            self.delay_spin.setValue(500)
            delay_form.addRow("Delay:", self.delay_spin)
            sim_layout.addLayout(delay_form)

            delay_desc = QLabel(
                "Simulates network latency and exchange processing time. "
                "Higher values = more realistic but slower execution."
            )
            delay_desc.setStyleSheet("color:#8b949e; font-size:8pt; padding-left:26px;")
            delay_desc.setWordWrap(True)
            sim_layout.addWidget(delay_desc)

            layout.addWidget(self.sim_group)
            layout.addStretch()

            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._build_mode_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building mode tab: {e}")

    # ── FEATURE 1: Risk Management Tab ───────────────────────────────────────
    def _build_risk_tab(self):
        """Build risk management tab"""
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(15)

            # Risk Limits Group
            limits_group = QGroupBox("Daily Risk Limits")
            limits_layout = QFormLayout(limits_group)
            limits_layout.setSpacing(8)
            limits_layout.setLabelAlignment(Qt.AlignRight)

            # Max Daily Loss
            self.max_loss_spin = QDoubleSpinBox()
            self.max_loss_spin.setRange(-1000000, 0)
            self.max_loss_spin.setSingleStep(100)
            self.max_loss_spin.setPrefix("₹ ")
            self.max_loss_spin.setToolTip("Maximum daily loss before bot stops trading (negative value)")
            self.max_loss_spin.setValue(-5000)
            limits_layout.addRow("Max Daily Loss:", self.max_loss_spin)

            loss_hint = QLabel("Trading stops when daily P&L reaches this level (negative number)")
            loss_hint.setStyleSheet("color:#484f58; font-size:8pt;")
            limits_layout.addRow("", loss_hint)

            # Max Trades Per Day
            self.max_trades_spin = QSpinBox()
            self.max_trades_spin.setRange(1, 100)
            self.max_trades_spin.setSuffix(" trades")
            self.max_trades_spin.setToolTip("Maximum number of trades per day")
            self.max_trades_spin.setValue(10)
            limits_layout.addRow("Max Trades/Day:", self.max_trades_spin)

            trades_hint = QLabel("Hard limit on number of entries per day")
            trades_hint.setStyleSheet("color:#484f58; font-size:8pt;")
            limits_layout.addRow("", trades_hint)

            # Daily Profit Target
            self.daily_target_spin = QDoubleSpinBox()
            self.daily_target_spin.setRange(0, 10000000)
            self.daily_target_spin.setSingleStep(100)
            self.daily_target_spin.setPrefix("₹ ")
            self.daily_target_spin.setToolTip("Daily profit target for progress tracking")
            self.daily_target_spin.setValue(5000)
            limits_layout.addRow("Daily Target:", self.daily_target_spin)

            target_hint = QLabel("Profit target for the day (for display purposes only)")
            target_hint.setStyleSheet("color:#484f58; font-size:8pt;")
            limits_layout.addRow("", target_hint)

            layout.addWidget(limits_group)

            # Info Card
            info_card = self._create_info_card(
                "📘 About Risk Management:",
                "• **Max Daily Loss**: When daily P&L reaches this negative value, "
                "the bot stops trading automatically.\n\n"
                "• **Max Trades/Day**: Hard limit on the number of entries per day.\n\n"
                "• **Daily Target**: Visual progress indicator only - does not stop trading.\n\n"
                "These limits help protect your capital and prevent over-trading."
            )
            layout.addWidget(info_card)

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._build_risk_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building risk tab: {e}")

    # ── FEATURE 6: Multi-Timeframe Filter Tab ────────────────────────────────
    def _build_mtf_tab(self):
        """Build Multi-Timeframe Filter settings tab"""
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(15)

            # Enable/Disable Group
            enable_group = QGroupBox("MTF Filter Status")
            enable_layout = QVBoxLayout(enable_group)

            self.mtf_check = QCheckBox("Enable Multi-Timeframe Filter")
            self.mtf_check.setToolTip("When enabled, requires agreement across multiple timeframes before entry")
            enable_layout.addWidget(self.mtf_check)

            enable_hint = QLabel("Requires at least 2 of 3 timeframes to agree with trade direction")
            enable_hint.setStyleSheet("color:#484f58; font-size:8pt; padding-left:26px;")
            enable_layout.addWidget(enable_hint)

            layout.addWidget(enable_group)

            # Timeframe Configuration Group
            tf_group = QGroupBox("Timeframe Configuration")
            tf_layout = QFormLayout(tf_group)
            tf_layout.setSpacing(8)
            tf_layout.setLabelAlignment(Qt.AlignRight)

            # Timeframes
            self.mtf_timeframes_edit = QLineEdit()
            self.mtf_timeframes_edit.setPlaceholderText("1,5,15")
            self.mtf_timeframes_edit.setToolTip("Comma-separated list of timeframes in minutes")
            tf_layout.addRow("Timeframes:", self.mtf_timeframes_edit)

            tf_hint = QLabel("Example: 1,5,15 for 1min, 5min, and 15min")
            tf_hint.setStyleSheet("color:#484f58; font-size:8pt;")
            tf_layout.addRow("", tf_hint)

            # Fast EMA
            self.mtf_ema_fast_spin = QSpinBox()
            self.mtf_ema_fast_spin.setRange(1, 50)
            self.mtf_ema_fast_spin.setSuffix(" periods")
            self.mtf_ema_fast_spin.setToolTip("Fast EMA period for trend detection")
            tf_layout.addRow("Fast EMA:", self.mtf_ema_fast_spin)

            # Slow EMA
            self.mtf_ema_slow_spin = QSpinBox()
            self.mtf_ema_slow_spin.setRange(5, 200)
            self.mtf_ema_slow_spin.setSuffix(" periods")
            self.mtf_ema_slow_spin.setToolTip("Slow EMA period for trend detection")
            tf_layout.addRow("Slow EMA:", self.mtf_ema_slow_spin)

            # Agreement Required
            self.mtf_agreement_spin = QSpinBox()
            self.mtf_agreement_spin.setRange(1, 3)
            self.mtf_agreement_spin.setSuffix(" timeframes")
            self.mtf_agreement_spin.setToolTip("Number of timeframes that must agree")
            tf_layout.addRow("Agreement Required:", self.mtf_agreement_spin)

            agree_hint = QLabel("How many timeframes must agree before allowing entry")
            agree_hint.setStyleSheet("color:#484f58; font-size:8pt;")
            tf_layout.addRow("", agree_hint)

            layout.addWidget(tf_group)

            # Info Card
            info_card = self._create_info_card(
                "📘 How Multi-Timeframe Filter Works:",
                "1. For each timeframe, calculates EMA9 and EMA21\n"
                "2. Determines trend: BULLISH (EMA9 > EMA21 > LTP) or BEARISH (EMA9 < EMA21 < LTP)\n"
                "3. Requires at least N timeframes to agree (default: 2 of 3)\n"
                "4. Entry is blocked if insufficient agreement\n\n"
                "This filter helps avoid entries during conflicting trends across timeframes."
            )
            layout.addWidget(info_card)

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._build_mtf_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building MTF tab: {e}")

    # ── FEATURE 3: Signal Confidence Tab ─────────────────────────────────────
    def _build_signal_tab(self):
        """Build signal confidence settings tab"""
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(15)

            # Confidence Group
            conf_group = QGroupBox("Signal Confidence Settings")
            conf_layout = QFormLayout(conf_group)
            conf_layout.setSpacing(8)
            conf_layout.setLabelAlignment(Qt.AlignRight)

            # Min Confidence
            self.min_confidence_spin = QDoubleSpinBox()
            self.min_confidence_spin.setRange(0.0, 1.0)
            self.min_confidence_spin.setSingleStep(0.05)
            self.min_confidence_spin.setDecimals(2)
            self.min_confidence_spin.setToolTip("Minimum confidence threshold for signals (0.0-1.0)")
            conf_layout.addRow("Min Confidence:", self.min_confidence_spin)

            conf_hint = QLabel("Signals below this confidence are suppressed (0.0-1.0)")
            conf_hint.setStyleSheet("color:#484f58; font-size:8pt;")
            conf_layout.addRow("", conf_hint)

            layout.addWidget(conf_group)

            # Info Card
            info_card = self._create_info_card(
                "📘 About Signal Confidence:",
                "• **Confidence Score**: Weighted average of rule results\n"
                "• **Min Confidence**: Signals below this threshold are ignored\n"
                "• **Rule Weights**: Configured in Strategy Editor\n\n"
                "Example: If min confidence = 0.6, a group needs 60% of weighted "
                "rules to pass before firing."
            )
            layout.addWidget(info_card)

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._build_signal_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building signal tab: {e}")

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
                    "🖥️  Simulation Mode",
                    "Paper trading environment where no real money is at risk.\n\n"
                    "• Uses virtual balance defined in settings.\n"
                    "• Perfect for testing strategies and learning.\n"
                    "• Simulates real market conditions with slippage/delay options.\n"
                    "• All order executions are virtual - no actual trades placed."
                ),
                (
                    "💰  Live Mode",
                    "Real trading with actual capital - USE WITH EXTREME CAUTION.\n\n"
                    "• Requires explicit 'Enable live trading' checkbox.\n"
                    "• Real orders sent to exchange via broker API.\n"
                    "• Real P&L - profits and losses are actual.\n"
                    "• Recommended only after extensive backtesting and paper trading.\n"
                    "• Start with small capital and gradually increase."
                ),
                (
                    "📊  Backtest Mode",
                    "Run strategy on historical data to evaluate performance.\n\n"
                    "• No live orders - purely analytical.\n"
                    "• Uses historical price data for simulation.\n"
                    "• Generate performance metrics and equity curves.\n"
                    "• Ideal for optimizing strategy parameters.\n"
                    "• Results depend on data quality and assumptions."
                ),
                (
                    "🛡️  Safety Features",
                    "Multiple layers of protection against accidental losses.\n\n"
                    "• Live Mode requires explicit enable checkbox.\n"
                    "• Per-trade confirmation option for extra safety.\n"
                    "• Cannot switch to Live without confirming.\n"
                    "• Clear visual warnings when Live mode is selected.\n"
                    "• Settings are saved with safety checks."
                ),
                (
                    "📈  Simulation Realism",
                    "Options to make paper trading more realistic:\n\n"
                    "• Slippage: Simulates price movement between order and fill.\n"
                    "• Delay: Adds artificial latency like real exchanges.\n"
                    "• Adjust these to match real-world conditions.\n"
                    "• Helps prepare for live trading challenges.\n"
                    "• More realistic simulations = better strategy validation."
                ),
                (
                    "⚠️  Risk Management",
                    "Daily loss limits and trade counts to protect capital.\n\n"
                    "• **Max Daily Loss**: Stop trading when daily P&L hits this level.\n"
                    "• **Max Trades/Day**: Hard limit on number of entries.\n"
                    "• **Daily Target**: Visual progress indicator for profit goals."
                ),
                (
                    "📈  Multi-Timeframe Filter",
                    "Confirms trend direction across multiple timeframes.\n\n"
                    "• Uses EMA 9/21 crossovers on multiple timeframes.\n"
                    "• Requires configurable number of timeframes to agree.\n"
                    "• Reduces false entries during conflicting trends."
                ),
                (
                    "🎯  Signal Confidence",
                    "Weighted voting system for signal groups.\n\n"
                    "• Each rule can have a weight (default 1.0).\n"
                    "• Confidence = passed_weight / total_weight.\n"
                    "• Signals below min_confidence are suppressed."
                ),
                (
                    "📁  Settings Storage",
                    "Trading mode settings are saved locally to:\n\n"
                    "    config/trading_mode_setting.json\n\n"
                    "The file is written atomically to prevent corruption. "
                    "Settings persist between application restarts. "
                    "Back up this file if you're moving to a new system."
                ),
            ]

            for title, body in infos:
                try:
                    card = self._create_info_card(title, body)
                    layout.addWidget(card)
                except Exception as e:
                    logger.error(f"Failed to create info card for {title}: {e}", exc_info=True)

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._build_info_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building information tab: {e}")

    def _create_info_card(self, title: str, body: str) -> QFrame:
        """Create an information card"""
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
        return card

    def _create_error_scroll(self, error_msg):
        """Create a scroll area with error message"""
        scroll = QScrollArea()
        container = QWidget()
        layout = QVBoxLayout(container)
        error_label = QLabel(f"❌ {error_msg}")
        error_label.setStyleSheet("color: #f85149; padding: 20px;")
        error_label.setWordWrap(True)
        layout.addWidget(error_label)
        scroll.setWidget(container)
        return scroll

    # ── UI Update Methods ────────────────────────────────────────────────────
    def _load_settings(self):
        """Load current settings into UI"""
        try:
            # Rule 6: Validate trading_mode_setting
            if self.trading_mode_setting is None:
                logger.error("Cannot load settings: trading_mode_setting is None")
                return

            # Set mode
            if self.mode_combo is not None:
                mode_value = self.trading_mode_setting.mode.value if self.trading_mode_setting.mode else TradingMode.SIM.value
                mode_index = self.mode_combo.findData(mode_value)
                if mode_index >= 0:
                    self.mode_combo.setCurrentIndex(mode_index)

            # Safety settings
            if self.allow_live_check is not None:
                self.allow_live_check.setChecked(bool(self.trading_mode_setting.allow_live_trading))
            if self.confirm_live_check is not None:
                self.confirm_live_check.setChecked(bool(self.trading_mode_setting.confirm_live_trades))

            # Simulation settings
            if self.paper_balance_spin is not None:
                self.paper_balance_spin.setValue(float(self.trading_mode_setting.paper_balance or 100000))
            if self.slippage_check is not None:
                self.slippage_check.setChecked(bool(self.trading_mode_setting.simulate_slippage))
            if self.slippage_spin is not None:
                self.slippage_spin.setValue(float(self.trading_mode_setting.slippage_percent or 0.05))
            if self.delay_check is not None:
                self.delay_check.setChecked(bool(self.trading_mode_setting.simulate_delay))
            if self.delay_spin is not None:
                self.delay_spin.setValue(int(self.trading_mode_setting.delay_ms or 500))

            # FEATURE 6: MTF settings
            if self.mtf_check is not None:
                self.mtf_check.setChecked(bool(self.trading_mode_setting.use_mtf_filter))
            if self.mtf_timeframes_edit is not None:
                self.mtf_timeframes_edit.setText(str(self.trading_mode_setting.mtf_timeframes or "1,5,15"))
            if self.mtf_ema_fast_spin is not None:
                self.mtf_ema_fast_spin.setValue(int(self.trading_mode_setting.mtf_ema_fast or 9))
            if self.mtf_ema_slow_spin is not None:
                self.mtf_ema_slow_spin.setValue(int(self.trading_mode_setting.mtf_ema_slow or 21))
            if self.mtf_agreement_spin is not None:
                self.mtf_agreement_spin.setValue(int(self.trading_mode_setting.mtf_agreement_required or 2))

            # FEATURE 1: Risk settings
            if self.max_loss_spin is not None:
                self.max_loss_spin.setValue(float(self.trading_mode_setting.max_daily_loss or -5000))
            if self.max_trades_spin is not None:
                self.max_trades_spin.setValue(int(self.trading_mode_setting.max_trades_per_day or 10))
            if self.daily_target_spin is not None:
                self.daily_target_spin.setValue(float(self.trading_mode_setting.daily_target or 5000))

            # FEATURE 3: Signal confidence
            if self.min_confidence_spin is not None:
                self.min_confidence_spin.setValue(float(self.trading_mode_setting.min_confidence or 0.6))

            self._update_ui_state()
            logger.debug("Settings loaded into UI")

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._load_settings] Failed: {e}", exc_info=True)

    def _on_mode_changed(self):
        """Handle mode change"""
        try:
            self._update_ui_state()
        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._on_mode_changed] Failed: {e}", exc_info=True)

    def _update_ui_state(self):
        """Update UI based on selected mode"""
        try:
            if self.mode_combo is None:
                logger.warning("_update_ui_state called with None mode_combo")
                return

            is_live = self.mode_combo.currentData() == TradingMode.LIVE.value

            if self.safety_warning is not None:
                self.safety_warning.setVisible(is_live)

            if self.sim_group is not None:
                self.sim_group.setEnabled(not is_live)

            # Button enable logic
            buttons_enabled = True

            if is_live:
                if self.allow_live_check is not None and not self.allow_live_check.isChecked():
                    buttons_enabled = False
                    if self.safety_warning is not None:
                        self.safety_warning.setText("⚠️ Check 'Enable live trading' to save LIVE mode")
                        self.safety_warning.setStyleSheet(
                            "color: #f85149; font-weight: bold; padding: 8px; background:#2d1a1a; border-radius:4px;")
                else:
                    if self.safety_warning is not None:
                        self.safety_warning.setText("⚠️ LIVE MODE - Real money will be used!")
                        self.safety_warning.setStyleSheet(
                            "color: #f85149; font-weight: bold; padding: 8px; background:#2d1a1a; border-radius:4px;")

            # Apply button states
            if self.save_btn is not None:
                self.save_btn.setEnabled(buttons_enabled)
            if self.apply_btn is not None:
                self.apply_btn.setEnabled(buttons_enabled)

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._update_ui_state] Failed: {e}", exc_info=True)

    # ── Save/Apply Methods ───────────────────────────────────────────────────
    def _apply_settings(self):
        """Apply settings without closing dialog"""
        try:
            if self._save_in_progress:
                logger.warning("Save already in progress")
                return

            self._save_in_progress = True
            self.status_label.setText("⏳ Applying settings...")
            self.status_label.setStyleSheet("color:#58a6ff; font-size:9pt; font-weight:bold;")

            if self._validate_and_save():
                self.status_label.setText("✓ Settings applied successfully!")
                self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
                logger.info("Settings applied successfully")
            else:
                self.status_label.setText("✗ Failed to apply settings")
                self.status_label.setStyleSheet("color:#f85149; font-size:9pt; font-weight:bold;")

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._apply_settings] Failed: {e}", exc_info=True)
            self.status_label.setText(f"✗ Error: {e}")
            self.status_label.setStyleSheet("color:#f85149; font-size:9pt; font-weight:bold;")
        finally:
            self._save_in_progress = False

    def _save_settings(self):
        """Save settings and close dialog"""
        try:
            if self._save_in_progress:
                logger.warning("Save already in progress")
                return

            self._save_in_progress = True
            self.status_label.setText("⏳ Saving settings...")
            self.status_label.setStyleSheet("color:#58a6ff; font-size:9pt; font-weight:bold;")

            if self._validate_and_save():
                self.status_label.setText("✓ Settings saved successfully!")
                self.status_label.setStyleSheet("color:#3fb950; font-size:9pt; font-weight:bold;")
                logger.info("Settings saved successfully, closing dialog")
                QTimer.singleShot(1000, self.accept)
            else:
                self.status_label.setText("✗ Failed to save settings")
                self.status_label.setStyleSheet("color:#f85149; font-size:9pt; font-weight:bold;")
                self._save_in_progress = False

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._save_settings] Failed: {e}", exc_info=True)
            self.status_label.setText(f"✗ Error: {e}")
            self.status_label.setStyleSheet("color:#f85149; font-size:9pt; font-weight:bold;")
            self._save_in_progress = False

    def _validate_and_save(self) -> bool:
        """Validate and save settings"""
        try:
            # Rule 6: Validate trading_mode_setting
            if self.trading_mode_setting is None:
                logger.error("Cannot save: trading_mode_setting is None")
                QMessageBox.critical(self, "Error", "Trading mode setting object is not initialized")
                return False

            # Get current mode value safely
            current_data = None
            if self.mode_combo is not None:
                current_data = self.mode_combo.currentData()

            # Check live mode safety
            if current_data == TradingMode.LIVE.value:
                if self.allow_live_check is not None and not self.allow_live_check.isChecked():
                    QMessageBox.warning(
                        self,
                        "Safety Check",
                        "You must check 'Enable live trading' to use LIVE mode.\n\n"
                        "This is a safety feature to prevent accidental live trading."
                    )
                    return False

                # Extra confirmation for live mode
                result = QMessageBox.question(
                    self,
                    "Confirm Live Trading",
                    "⚠️ YOU ARE ABOUT TO ENABLE LIVE TRADING ⚠️\n\n"
                    "This will use REAL MONEY for trades.\n\n"
                    "Are you absolutely sure?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if result != QMessageBox.Yes:
                    return False

            # Save settings with safe defaults
            try:
                if current_data is not None:
                    self.trading_mode_setting.mode = TradingMode(current_data)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid mode value: {e}")
                self.trading_mode_setting.mode = TradingMode.SIM

            # Mode settings
            if self.allow_live_check is not None:
                self.trading_mode_setting.allow_live_trading = self.allow_live_check.isChecked()
            if self.confirm_live_check is not None:
                self.trading_mode_setting.confirm_live_trades = self.confirm_live_check.isChecked()
            if self.paper_balance_spin is not None:
                self.trading_mode_setting.paper_balance = self.paper_balance_spin.value()
            if self.slippage_check is not None:
                self.trading_mode_setting.simulate_slippage = self.slippage_check.isChecked()
            if self.slippage_spin is not None:
                self.trading_mode_setting.slippage_percent = self.slippage_spin.value()
            if self.delay_check is not None:
                self.trading_mode_setting.simulate_delay = self.delay_check.isChecked()
            if self.delay_spin is not None:
                self.trading_mode_setting.delay_ms = self.delay_spin.value()

            # FEATURE 6: MTF settings
            if self.mtf_check is not None:
                self.trading_mode_setting.use_mtf_filter = self.mtf_check.isChecked()
            if self.mtf_timeframes_edit is not None:
                self.trading_mode_setting.mtf_timeframes = self.mtf_timeframes_edit.text()
            if self.mtf_ema_fast_spin is not None:
                self.trading_mode_setting.mtf_ema_fast = self.mtf_ema_fast_spin.value()
            if self.mtf_ema_slow_spin is not None:
                self.trading_mode_setting.mtf_ema_slow = self.mtf_ema_slow_spin.value()
            if self.mtf_agreement_spin is not None:
                self.trading_mode_setting.mtf_agreement_required = self.mtf_agreement_spin.value()

            # FEATURE 1: Risk settings
            if self.max_loss_spin is not None:
                self.trading_mode_setting.max_daily_loss = self.max_loss_spin.value()
            if self.max_trades_spin is not None:
                self.trading_mode_setting.max_trades_per_day = self.max_trades_spin.value()
            if self.daily_target_spin is not None:
                self.trading_mode_setting.daily_target = self.daily_target_spin.value()

            # FEATURE 3: Signal confidence
            if self.min_confidence_spin is not None:
                self.trading_mode_setting.min_confidence = self.min_confidence_spin.value()

            # Save to file
            success = self.trading_mode_setting.save()
            if not success:
                logger.error("Failed to save settings to file")
                QMessageBox.critical(self, "Error", "Failed to save settings to file")
                return False

            # Update trading app if running
            if self.app is not None and hasattr(self.app, 'refresh_trading_mode'):
                try:
                    self.app.refresh_trading_mode()
                    logger.debug("Trading app refreshed")
                except Exception as e:
                    logger.error(f"Failed to refresh trading app: {e}", exc_info=True)

            return True

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._validate_and_save] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")
            return False

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info("[TradingModeSettingGUI] Starting cleanup")

            # Clear references
            self.trading_mode_setting = None
            self.app = None
            self.tabs = None
            self.mode_combo = None
            self.safety_warning = None
            self.allow_live_check = None
            self.confirm_live_check = None
            self.sim_group = None
            self.paper_balance_spin = None
            self.slippage_check = None
            self.slippage_spin = None
            self.delay_check = None
            self.delay_spin = None
            self.mtf_check = None
            self.mtf_timeframes_edit = None
            self.mtf_ema_fast_spin = None
            self.mtf_ema_slow_spin = None
            self.mtf_agreement_spin = None
            self.max_loss_spin = None
            self.max_trades_spin = None
            self.daily_target_spin = None
            self.min_confidence_spin = None
            self.save_btn = None
            self.cancel_btn = None
            self.apply_btn = None
            self.status_label = None

            logger.info("[TradingModeSettingGUI] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup"""
        try:
            self.cleanup()
            event.accept()
        except Exception as e:
            logger.error(f"[TradingModeSettingGUI.closeEvent] Failed: {e}", exc_info=True)
            event.accept()