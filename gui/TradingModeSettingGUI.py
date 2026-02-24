import logging
import logging.handlers
import traceback
from typing import Optional

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QPushButton, QComboBox, QDoubleSpinBox, QSpinBox,
                             QCheckBox, QGroupBox, QLabel, QMessageBox,
                             QTabWidget, QFrame, QScrollArea, QWidget)
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
            self.setMinimumSize(650, 600)
            self.resize(650, 600)

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
                QComboBox, QDoubleSpinBox, QSpinBox {
                    background:#21262d; color:#e6edf3; border:1px solid #30363d;
                    border-radius:4px; padding:8px; font-size:10pt;
                    min-height:20px;
                }
                QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus { border:2px solid #58a6ff; }
                QComboBox::drop-down { border:none; }
                QComboBox::down-arrow { image: none; border-left:1px solid #30363d; width:20px; }
                QCheckBox { color:#e6edf3; spacing:8px; }
                QCheckBox::indicator { width:18px; height:18px; }
                QCheckBox::indicator:unchecked { border:2px solid #30363d; background:#21262d; border-radius:3px; }
                QCheckBox::indicator:checked   { background:#238636; border:2px solid #2ea043; border-radius:3px; }
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
            self.tabs.addTab(self._build_settings_tab(), "⚙️ Settings")
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
            # Still try to create basic dialog
            super().__init__(parent)
            self.trading_mode_setting = trading_mode_setting or TradingModeSetting()
            self.app = app
            self._safe_defaults_init()
            self.setWindowTitle("Trading Mode Settings - ERROR")
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
        self.save_btn = None
        self.cancel_btn = None
        self.apply_btn = None
        self.status_label = None
        self._save_in_progress = False

    def _build_settings_tab(self):
        """Build the settings tab with enhanced UI"""
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
            self.allow_live_check.stateChanged.connect(self._update_ui_state)  # Add this line
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
            self.paper_balance_spin.setSuffix(" ₹")
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
            logger.error(f"[TradingModeSettingGUI._build_settings_tab] Failed: {e}", exc_info=True)
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
                    "⚡  Performance Impact",
                    "How different modes affect system performance:\n\n"
                    "• Simulation: Minimal impact, all calculations local.\n"
                    "• Live: API calls to broker, network latency.\n"
                    "• Backtest: CPU-intensive for large datasets.\n"
                    "• Choose mode based on your current needs.\n"
                    "• You can switch modes without restarting."
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

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._build_info_tab] Failed: {e}", exc_info=True)
            scroll = QScrollArea()
            container = QWidget()
            layout = QVBoxLayout(container)
            error_label = QLabel(f"Error building information tab: {e}")
            error_label.setStyleSheet("color: #f85149;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
            scroll.setWidget(container)
            return scroll

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
        """Update UI based on selected mode - FIXED button enable logic"""
        try:
            if self.mode_combo is None:
                logger.warning("_update_ui_state called with None mode_combo")
                return

            is_live = self.mode_combo.currentData() == TradingMode.LIVE.value

            if self.safety_warning is not None:
                self.safety_warning.setVisible(is_live)

            if self.sim_group is not None:
                self.sim_group.setEnabled(not is_live)

            # FIXED: Button enable logic - buttons should be enabled by default
            # Only disable for live mode when allow_live_check is not checked
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