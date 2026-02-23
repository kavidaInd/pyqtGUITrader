import logging
import logging.handlers
import traceback
from typing import Optional

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QPushButton, QComboBox, QDoubleSpinBox, QSpinBox,
                             QCheckBox, QGroupBox, QLabel, QMessageBox)
from PyQt5.QtCore import Qt, QTimer

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
            self.setMinimumWidth(500)
            self.setModal(True)

            self._build_ui()
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
            self.setMinimumWidth(400)

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
        self._save_in_progress = False

    def _build_ui(self):
        """Build the UI with all widgets"""
        try:
            layout = QVBoxLayout(self)

            # Mode Selection Group
            mode_group = QGroupBox("Trading Mode")
            mode_layout = QFormLayout(mode_group)

            self.mode_combo = QComboBox()
            self.mode_combo.addItem("Simulation (Paper Trading)", TradingMode.SIM.value)
            self.mode_combo.addItem("Live Trading", TradingMode.LIVE.value)
            self.mode_combo.addItem("Backtest", TradingMode.BACKTEST.value)
            self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
            mode_layout.addRow("Mode:", self.mode_combo)

            self.safety_warning = QLabel("⚠️ LIVE MODE - Real money will be used!")
            self.safety_warning.setStyleSheet("color: #f85149; font-weight: bold;")
            self.safety_warning.setVisible(False)
            mode_layout.addRow("", self.safety_warning)

            layout.addWidget(mode_group)

            # Safety Settings Group
            safety_group = QGroupBox("Safety Settings")
            safety_layout = QFormLayout(safety_group)

            self.allow_live_check = QCheckBox("Enable live trading (off by default for safety)")
            self.allow_live_check.setToolTip("Must be checked to allow any live trades")
            safety_layout.addRow("", self.allow_live_check)

            self.confirm_live_check = QCheckBox("Confirm each live trade before execution")
            self.confirm_live_check.setChecked(True)
            safety_layout.addRow("", self.confirm_live_check)

            layout.addWidget(safety_group)

            # Simulation Settings Group
            self.sim_group = QGroupBox("Simulation Settings")
            sim_layout = QFormLayout(self.sim_group)

            self.paper_balance_spin = QDoubleSpinBox()
            self.paper_balance_spin.setRange(1000, 10000000)
            self.paper_balance_spin.setSingleStep(10000)
            self.paper_balance_spin.setSuffix(" ₹")
            sim_layout.addRow("Paper Trading Balance:", self.paper_balance_spin)

            self.slippage_check = QCheckBox("Simulate slippage")
            sim_layout.addRow("", self.slippage_check)

            self.slippage_spin = QDoubleSpinBox()
            self.slippage_spin.setRange(0, 1)
            self.slippage_spin.setSingleStep(0.01)
            self.slippage_spin.setSuffix(" %")
            sim_layout.addRow("Slippage %:", self.slippage_spin)

            self.delay_check = QCheckBox("Simulate order delay")
            sim_layout.addRow("", self.delay_check)

            self.delay_spin = QSpinBox()
            self.delay_spin.setRange(0, 5000)
            self.delay_spin.setSingleStep(100)
            self.delay_spin.setSuffix(" ms")
            sim_layout.addRow("Delay:", self.delay_spin)

            layout.addWidget(self.sim_group)

            # Buttons
            button_layout = QHBoxLayout()
            self.save_btn = QPushButton("Save")
            self.save_btn.clicked.connect(self._save_settings)
            self.cancel_btn = QPushButton("Cancel")
            self.cancel_btn.clicked.connect(self.reject)
            self.apply_btn = QPushButton("Apply")
            self.apply_btn.clicked.connect(self._apply_settings)

            button_layout.addStretch()
            button_layout.addWidget(self.save_btn)
            button_layout.addWidget(self.apply_btn)
            button_layout.addWidget(self.cancel_btn)

            layout.addLayout(button_layout)

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._build_ui] Failed: {e}", exc_info=True)
            # Re-raise to be handled by __init__
            raise

    def _load_settings(self):
        """Load current settings into UI"""
        try:
            # Rule 6: Validate trading_mode_setting
            if self.trading_mode_setting is None:
                logger.error("Cannot load settings: trading_mode_setting is None")
                return

            # Set mode
            if self.mode_combo:
                mode_value = self.trading_mode_setting.mode.value if self.trading_mode_setting.mode else TradingMode.SIM.value
                mode_index = self.mode_combo.findData(mode_value)
                if mode_index >= 0:
                    self.mode_combo.setCurrentIndex(mode_index)

            # Safety settings
            if self.allow_live_check:
                self.allow_live_check.setChecked(bool(self.trading_mode_setting.allow_live_trading))
            if self.confirm_live_check:
                self.confirm_live_check.setChecked(bool(self.trading_mode_setting.confirm_live_trades))

            # Simulation settings
            if self.paper_balance_spin:
                self.paper_balance_spin.setValue(float(self.trading_mode_setting.paper_balance or 100000))
            if self.slippage_check:
                self.slippage_check.setChecked(bool(self.trading_mode_setting.simulate_slippage))
            if self.slippage_spin:
                self.slippage_spin.setValue(float(self.trading_mode_setting.slippage_percent or 0.05))
            if self.delay_check:
                self.delay_check.setChecked(bool(self.trading_mode_setting.simulate_delay))
            if self.delay_spin:
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
        """Update UI based on selected mode"""
        try:
            if self.mode_combo is None:
                logger.warning("_update_ui_state called with None mode_combo")
                return

            is_live = self.mode_combo.currentData() == TradingMode.LIVE.value

            # Show warning for live mode
            if self.safety_warning:
                self.safety_warning.setVisible(is_live)

            # Enable/disable simulation settings
            if self.sim_group:
                self.sim_group.setEnabled(not is_live)

            # For live mode, require explicit enable
            if is_live and self.allow_live_check and not self.allow_live_check.isChecked():
                if self.save_btn:
                    self.save_btn.setEnabled(False)
                if self.apply_btn:
                    self.apply_btn.setEnabled(False)
                if self.safety_warning:
                    self.safety_warning.setText("⚠️ Check 'Enable live trading' to save LIVE mode")
            else:
                if self.save_btn:
                    self.save_btn.setEnabled(True)
                if self.apply_btn:
                    self.apply_btn.setEnabled(True)
                if self.safety_warning:
                    self.safety_warning.setText("⚠️ LIVE MODE - Real money will be used!")

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._update_ui_state] Failed: {e}", exc_info=True)

    def _apply_settings(self):
        """Apply settings without closing dialog"""
        try:
            # Prevent multiple saves
            if self._save_in_progress:
                logger.warning("Save already in progress")
                return

            self._save_in_progress = True

            if self._validate_and_save():
                QMessageBox.information(self, "Success", "Settings applied successfully")
                logger.info("Settings applied successfully")

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._apply_settings] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to apply settings: {e}")
        finally:
            self._save_in_progress = False

    def _save_settings(self):
        """Save settings and close dialog"""
        try:
            # Prevent multiple saves
            if self._save_in_progress:
                logger.warning("Save already in progress")
                return

            self._save_in_progress = True

            if self._validate_and_save():
                logger.info("Settings saved successfully, closing dialog")
                self.accept()

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._save_settings] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")
        finally:
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
            if self.mode_combo:
                current_data = self.mode_combo.currentData()

            # Check live mode safety
            if current_data == TradingMode.LIVE.value:
                if self.allow_live_check and not self.allow_live_check.isChecked():
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

            if self.allow_live_check:
                self.trading_mode_setting.allow_live_trading = self.allow_live_check.isChecked()
            if self.confirm_live_check:
                self.trading_mode_setting.confirm_live_trades = self.confirm_live_check.isChecked()
            if self.paper_balance_spin:
                self.trading_mode_setting.paper_balance = self.paper_balance_spin.value()
            if self.slippage_check:
                self.trading_mode_setting.simulate_slippage = self.slippage_check.isChecked()
            if self.slippage_spin:
                self.trading_mode_setting.slippage_percent = self.slippage_spin.value()
            if self.delay_check:
                self.trading_mode_setting.simulate_delay = self.delay_check.isChecked()
            if self.delay_spin:
                self.trading_mode_setting.delay_ms = self.delay_spin.value()

            # Save to file
            success = self.trading_mode_setting.save()
            if not success:
                logger.error("Failed to save settings to file")
                QMessageBox.critical(self, "Error", "Failed to save settings to file")
                return False

            # Update trading app if running
            if self.app and hasattr(self.app, 'refresh_trading_mode'):
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