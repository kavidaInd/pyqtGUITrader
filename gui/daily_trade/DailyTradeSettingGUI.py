"""
DailyTradeSettingGUI.py
=======================
GUI for daily trade settings with database integration.

UPDATED: Derivative selection now uses dropdown from OptionUtils constants.
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

import logging
import threading
from typing import Optional, Dict, Any, Tuple, List

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QDoubleValidator, QIntValidator
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QVBoxLayout, QLabel,
                             QWidget, QTabWidget, QFrame, QScrollArea,
                             QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox,
                             QGroupBox, QHBoxLayout)

from gui.daily_trade.DailyTradeSetting import DailyTradeSetting
from Utils.OptionUtils import OptionUtils

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class ThemedMixin:
    """Mixin class to provide theme token shortcuts."""

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing


class DailyTradeSettingGUI(QDialog, ThemedMixin):
    save_completed = pyqtSignal(bool, str)

    # Rule 3: Additional signals for error handling
    error_occurred = pyqtSignal(str)
    operation_started = pyqtSignal()
    operation_finished = pyqtSignal()

    INTERVAL_CHOICES = [
        ("1 minute", "1m"),
        ("2 minutes", "2m"), ("3 minutes", "3m"), ("5 minutes", "5m"),
        ("10 minutes", "10m"), ("15 minutes", "15m"), ("20 minutes", "20m"),
        ("30 minutes", "30m"), ("60 minutes", "60m"), ("120 minutes", "120m"),
        ("240 minutes", "240m")
    ]

    # UPDATED: Derivative choices from OptionUtils
    DERIVATIVE_CHOICES = [
        ("NIFTY 50", "NIFTY50"),
        ("BANK NIFTY", "BANKNIFTY"),
        ("FIN NIFTY", "FINNIFTY"),
        ("MIDCP NIFTY", "MIDCPNIFTY"),
        ("SENSEX", "SENSEX"),
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
        # FEATURE 6: MTF validation
        "mtf_ema_fast": (1, 50),
        "mtf_ema_slow": (5, 200),
        "mtf_agreement_required": (1, 3),
        # FEATURE 1: Risk validation
        "max_daily_loss": (-1000000, 0),  # Negative values only
        "max_trades_per_day": (1, 100),
        "daily_target": (0, 1000000),
        # FEATURE 3: Confidence validation
        "min_confidence": (0.0, 1.0),
    }

    def __init__(self, parent, daily_setting: DailyTradeSetting, app=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.daily_setting = daily_setting
            self.app = app

            # Rule 6: Input validation
            if daily_setting is None:
                logger.error("DailyTradeSettingGUI initialized with None daily_setting")

            self.setWindowTitle("Daily Trade Settings")
            self.setModal(True)
            self.setMinimumSize(750, 700)  # Increased size for new tabs
            self.resize(750, 700)

            # Root layout
            root = QVBoxLayout(self)
            # Margins and spacing will be set in apply_theme

            # Header
            header = QLabel("⚙️ Daily Trade Settings")
            header.setObjectName("header")
            header.setAlignment(Qt.AlignCenter)
            root.addWidget(header)

            # Tabs
            self.tabs = QTabWidget()
            root.addWidget(self.tabs)

            # Add all tabs
            self.tabs.addTab(self._build_settings_tab(), "⚙️ Core Settings")
            self.tabs.addTab(self._build_risk_tab(), "⚠️ Risk Management")  # FEATURE 1
            self.tabs.addTab(self._build_mtf_tab(), "📈 MTF Filter")  # FEATURE 6
            self.tabs.addTab(self._build_signal_tab(), "🎯 Signal")  # FEATURE 3
            self.tabs.addTab(self._build_info_tab(), "ℹ️ Information")

            # Status + Save (always visible below tabs)
            self.status_label = QLabel("")
            self.status_label.setAlignment(Qt.AlignCenter)
            self.status_label.setObjectName("status")
            root.addWidget(self.status_label)

            self.save_btn = QPushButton("💾 Save All Settings")
            self.save_btn.clicked.connect(self.save)
            root.addWidget(self.save_btn)

            self.save_completed.connect(self.on_save_completed)

            # Connect internal signals
            self._connect_signals()

            # Apply theme initially
            self.apply_theme()

            logger.info("DailyTradeSettingGUI initialized")

        except Exception as e:
            logger.critical(f"[DailyTradeSettingGUI.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.daily_setting = None
        self.app = None
        self.tabs = None
        self.vars = {}
        self.entries = {}
        self.interval_combo = None
        self.derivative_combo = None  # UPDATED: New field for derivative dropdown
        self.sideway_check = None
        self.status_label = None
        self.save_btn = None
        self._save_in_progress = False
        self._save_timer = None

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the dialog.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Update root layout margins and spacing
            layout = self.layout()
            if layout:
                layout.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
                layout.setSpacing(sp.GAP_MD)

            # Apply main stylesheet
            self.setStyleSheet(self._get_stylesheet())

            # Update header
            header = self.findChild(QLabel, "header")
            if header:
                header.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_XL}pt; font-weight: {ty.WEIGHT_BOLD}; padding: {sp.PAD_XS}px;")

            # Update status label
            if self.status_label:
                self.status_label.setStyleSheet(f"color: {c.GREEN}; font-size: {ty.SIZE_XS}pt; font-weight: {ty.WEIGHT_BOLD};")

            # Update save button
            if self.save_btn:
                self.save_btn.setStyleSheet(self._get_button_style())

            # Update all hint labels
            self._update_hint_styles()

            logger.debug("[DailyTradeSettingGUI.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.apply_theme] Failed: {e}", exc_info=True)

    def _get_stylesheet(self) -> str:
        """Generate stylesheet with current theme tokens"""
        c = self._c
        ty = self._ty
        sp = self._sp

        return f"""
            QDialog {{ background:{c.BG_PANEL}; color:{c.TEXT_MAIN}; }}
            QLabel  {{ color:{c.TEXT_DIM}; font-size:{ty.SIZE_SM}pt; }}
            QGroupBox {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                margin-top: {sp.PAD_MD}px;
                font-weight: {ty.WEIGHT_BOLD};
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_BODY}pt;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {sp.PAD_MD}px;
                padding: 0 {sp.PAD_XS}px 0 {sp.PAD_XS}px;
            }}
            QTabWidget::pane {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                background: {c.BG_PANEL};
            }}
            QTabBar::tab {{
                background: {c.BG_HOVER};
                color: {c.TEXT_DIM};
                padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                min-width: 130px;
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-bottom: none;
                border-radius: {sp.RADIUS_SM}px {sp.RADIUS_SM}px 0 0;
                font-size: {ty.SIZE_BODY}pt;
            }}
            QTabBar::tab:selected {{
                background: {c.BG_PANEL};
                color: {c.TEXT_MAIN};
                border-bottom: {sp.PAD_XS}px solid {c.BLUE};
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QTabBar::tab:hover:!selected {{ background:{c.BORDER}; color:{c.TEXT_MAIN}; }}
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
                background:{c.BG_HOVER}; color:{c.TEXT_MAIN}; border:{sp.SEPARATOR}px solid {c.BORDER};
                border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px; font-size:{ty.SIZE_BODY}pt;
                min-height: {sp.BTN_HEIGHT_SM}px;
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border:{sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                background: {c.BORDER};
                border: none;
                width: {sp.ICON_SM}px;
            }}
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
                image: none;
                border-left: {sp.PAD_XS}px solid transparent;
                border-right: {sp.PAD_XS}px solid transparent;
                border-bottom: {sp.PAD_XS}px solid {c.TEXT_DIM};
            }}
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
                image: none;
                border-left: {sp.PAD_XS}px solid transparent;
                border-right: {sp.PAD_XS}px solid transparent;
                border-top: {sp.PAD_XS}px solid {c.TEXT_DIM};
            }}
            QCheckBox {{ color:{c.TEXT_MAIN}; spacing:{sp.GAP_SM}px; font-size:{ty.SIZE_BODY}pt; }}
            QCheckBox::indicator {{ width:{sp.ICON_MD}px; height:{sp.ICON_MD}px; }}
            QCheckBox::indicator:unchecked {{ border:{sp.SEPARATOR}px solid {c.BORDER}; background:{c.BG_HOVER}; border-radius:{sp.RADIUS_SM}px; }}
            QCheckBox::indicator:checked   {{ background:{c.GREEN}; border:{sp.SEPARATOR}px solid {c.GREEN_BRIGHT}; border-radius:{sp.RADIUS_SM}px; }}
            QScrollArea {{ border:none; background:transparent; }}
            QFrame#infoCard {{
                background:{c.BG_HOVER};
                border:{sp.SEPARATOR}px solid {c.BORDER};
                border-radius:{sp.RADIUS_MD}px;
            }}
        """

    def _get_button_style(self) -> str:
        """Get styled button with theme tokens"""
        c = self._c
        sp = self._sp
        ty = self._ty

        return f"""
            QPushButton {{
                background:{c.GREEN}; color:{c.TEXT_INVERSE}; border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                font-weight:{ty.WEIGHT_BOLD}; font-size:{ty.SIZE_BODY}pt;
            }}
            QPushButton:hover    {{ background:{c.GREEN_BRIGHT}; }}
            QPushButton:pressed  {{ background:{c.GREEN}; }}
            QPushButton:disabled {{ background:{c.BG_HOVER}; color:{c.TEXT_DISABLED}; }}
        """

    def _update_hint_styles(self):
        """Update all hint labels with theme colors"""
        c = self._c
        sp = self._sp
        ty = self._ty

        hint_style = f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;"
        hint_indented_style = f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt; padding-left:{sp.PAD_XL}px;"

        # Find all QLabel widgets that are hints (we can't easily identify them,
        # but they'll be updated when they're recreated in refresh)

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self):
        """Connect internal signals"""
        try:
            self.error_occurred.connect(self._on_error)
            self.operation_started.connect(self._on_operation_started)
            self.operation_finished.connect(self._on_operation_finished)
        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._connect_signals] Failed: {e}", exc_info=True)

    # ── Error handling ────────────────────────────────────────────────────────

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            super().__init__(parent)
            self.setWindowTitle("Daily Trade Settings - ERROR")
            self.setMinimumSize(400, 200)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)

            error_label = QLabel("❌ Failed to initialize settings dialog.\nPlease check the logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet(f"color: {c.RED_BRIGHT}; padding: {sp.PAD_XL}px; font-size: {ty.SIZE_MD}pt;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._create_error_dialog] Failed: {e}", exc_info=True)

    # ── Core Settings Tab (Original) ──────────────────────────────────────────
    def _build_settings_tab(self):
        """Build the core settings tab with form fields"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            container = QWidget()
            container.setStyleSheet("background:transparent;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_MD)
            layout.setSpacing(sp.GAP_XS)

            form = QFormLayout()
            form.setSpacing(sp.GAP_XS)
            form.setVerticalSpacing(sp.GAP_XS)
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

                    # Safely get value from settings
                    val = ""
                    if self.daily_setting is not None and hasattr(self.daily_setting, 'data'):
                        val = self.daily_setting.data.get(key, "")
                    edit.setText(str(val))

                    hint_lbl = QLabel(hint)
                    hint_lbl.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")

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

            # UPDATED: Derivative Dropdown
            derivative_label = QLabel("💡 Derivative:")
            derivative_label.setToolTip("The underlying instrument whose options or futures will be traded.")
            form.addRow(derivative_label, self._create_derivative_dropdown())
            derivative_hint = QLabel("Underlying symbol for the derivative contract (NIFTY50, BANKNIFTY, etc.)")
            derivative_hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
            form.addRow("", derivative_hint)

            # History Interval ComboBox
            try:
                interval_label = QLabel("⏱️ History Interval:")
                interval_label.setToolTip(
                    "Candle interval used to fetch historical price data.\n"
                    "Smaller intervals = more granular signals but heavier data load."
                )
                self.interval_combo = QComboBox()
                for display, value in self.INTERVAL_CHOICES:
                    self.interval_combo.addItem(display, value)

                current_val = "2m"
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

                form.addRow(interval_label, self.interval_combo)
                interval_hint = QLabel("Candle size used for historical data and signal generation.")
                interval_hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
                form.addRow("", interval_hint)

                # Store interval in vars for validation
                self.vars["history_interval"] = (self.interval_combo, str)

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
                if self.daily_setting is not None and hasattr(self.daily_setting, 'data'):
                    checked = self.daily_setting.data.get("sideway_zone_trade", False)
                self.sideway_check.setChecked(checked)

                self.sideway_check.setToolTip(
                    "When enabled, the strategy will continue placing orders during the\n"
                    "low-volatility midday window (12:00–14:00). Disable to avoid choppy moves."
                )
                sideway_hint = QLabel("Allow entries during the low-volatility midday window.")
                sideway_hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt; padding-left:{sp.PAD_XL}px;")

                layout.addWidget(self.sideway_check)
                layout.addWidget(sideway_hint)

                # Store sideway in vars
                self.vars["sideway_zone_trade"] = (self.sideway_check, bool)

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
            return self._create_error_scroll(f"Error building settings tab: {e}")

    def _create_derivative_dropdown(self) -> QComboBox:
        """UPDATED: Create dropdown for derivative selection"""
        try:
            self.derivative_combo = QComboBox()
            self.derivative_combo.setToolTip("The underlying instrument whose options or futures will be traded.")

            # Populate from DERIVATIVE_CHOICES
            for display, value in self.DERIVATIVE_CHOICES:
                self.derivative_combo.addItem(display, value)

            # Get current value from settings
            current_val = "NIFTY50"
            if self.daily_setting is not None and hasattr(self.daily_setting, 'derivative'):
                current_val = self.daily_setting.derivative

            # Select current value
            found = False
            for i in range(self.derivative_combo.count()):
                if self.derivative_combo.itemData(i) == current_val:
                    self.derivative_combo.setCurrentIndex(i)
                    found = True
                    break

            if not found:
                logger.warning(f"Derivative value {current_val} not found in choices")

            # Store in vars for saving
            self.vars["derivative"] = (self.derivative_combo, str)
            self.entries["derivative"] = self.derivative_combo

            return self.derivative_combo

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._create_derivative_dropdown] Failed: {e}", exc_info=True)
            combo = QComboBox()
            combo.addItem("Error", "NIFTY50")
            combo.setEnabled(False)
            return combo

    # ── FEATURE 1: Risk Management Tab ───────────────────────────────────────
    def _build_risk_tab(self):
        """Build risk management tab"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)
            layout.setSpacing(sp.GAP_LG)

            # Risk Limits Group
            limits_group = QGroupBox("Daily Risk Limits")
            limits_layout = QFormLayout(limits_group)
            limits_layout.setSpacing(sp.GAP_SM)
            limits_layout.setLabelAlignment(Qt.AlignRight)

            # Max Daily Loss
            loss_spin = QDoubleSpinBox()
            loss_spin.setRange(-1000000, 0)
            loss_spin.setSingleStep(100)
            loss_spin.setPrefix("₹")
            loss_spin.setToolTip("Maximum daily loss before bot stops trading (negative value)")
            current_loss = -5000
            if self.daily_setting and hasattr(self.daily_setting, 'max_daily_loss'):
                current_loss = self.daily_setting.max_daily_loss
            loss_spin.setValue(current_loss)
            limits_layout.addRow("Max Daily Loss:", loss_spin)
            self.vars["max_daily_loss"] = (loss_spin, float)
            self.entries["max_daily_loss"] = loss_spin

            loss_hint = QLabel("Trading stops when daily P&L reaches this level (negative number)")
            loss_hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
            limits_layout.addRow("", loss_hint)

            # Max Trades Per Day
            trades_spin = QSpinBox()
            trades_spin.setRange(1, 100)
            trades_spin.setSuffix(" trades")
            trades_spin.setToolTip("Maximum number of trades per day")
            current_trades = 10
            if self.daily_setting and hasattr(self.daily_setting, 'max_trades_per_day'):
                current_trades = self.daily_setting.max_trades_per_day
            trades_spin.setValue(current_trades)
            limits_layout.addRow("Max Trades/Day:", trades_spin)
            self.vars["max_trades_per_day"] = (trades_spin, int)
            self.entries["max_trades_per_day"] = trades_spin

            trades_hint = QLabel("Hard limit on number of entries per day")
            trades_hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
            limits_layout.addRow("", trades_hint)

            # Daily Profit Target
            target_spin = QDoubleSpinBox()
            target_spin.setRange(0, 1000000)
            target_spin.setSingleStep(100)
            target_spin.setPrefix("₹")
            target_spin.setToolTip("Daily profit target for progress tracking")
            current_target = 5000
            if self.daily_setting and hasattr(self.daily_setting, 'daily_target'):
                current_target = self.daily_setting.daily_target
            target_spin.setValue(current_target)
            limits_layout.addRow("Daily Target:", target_spin)
            self.vars["daily_target"] = (target_spin, float)
            self.entries["daily_target"] = target_spin

            target_hint = QLabel("Profit target for the day (for display purposes only)")
            target_hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
            limits_layout.addRow("", target_hint)

            layout.addWidget(limits_group)

            # Info Card
            info_card = self._create_info_card(
                "📘 About Risk Management:",
                "• **Max Daily Loss**: When daily P&L reaches this negative value, "
                "the bot stops trading automatically.\n\n"
                "• **Max Trades/Day**: Hard limit on the number of entries per day. "
                "Once reached, no new positions are opened.\n\n"
                "• **Daily Target**: Visual progress indicator only - does not stop trading.\n\n"
                "These limits help protect your capital and prevent over-trading."
            )
            layout.addWidget(info_card)

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._build_risk_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building risk tab: {e}")

    # ── FEATURE 6: Multi-Timeframe Filter Tab ────────────────────────────────
    def _build_mtf_tab(self):
        """Build Multi-Timeframe Filter settings tab"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)
            layout.setSpacing(sp.GAP_LG)

            # Enable/Disable Group
            enable_group = QGroupBox("MTF Filter Status")
            enable_layout = QVBoxLayout(enable_group)

            mtf_check = QCheckBox("Enable Multi-Timeframe Filter")
            mtf_check.setToolTip("When enabled, requires agreement across multiple timeframes before entry")
            current_enabled = False
            if self.daily_setting and hasattr(self.daily_setting, 'use_mtf_filter'):
                current_enabled = self.daily_setting.use_mtf_filter
            mtf_check.setChecked(current_enabled)
            enable_layout.addWidget(mtf_check)
            self.vars["use_mtf_filter"] = (mtf_check, bool)

            enable_hint = QLabel("Requires at least 2 of 3 timeframes to agree with trade direction")
            enable_hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt; padding-left:{sp.PAD_XL}px;")
            enable_layout.addWidget(enable_hint)

            layout.addWidget(enable_group)

            # Timeframe Configuration Group
            tf_group = QGroupBox("Timeframe Configuration")
            tf_layout = QFormLayout(tf_group)
            tf_layout.setSpacing(sp.GAP_SM)
            tf_layout.setLabelAlignment(Qt.AlignRight)

            # Timeframes
            tf_edit = QLineEdit()
            tf_edit.setPlaceholderText("1,5,15")
            tf_edit.setToolTip("Comma-separated list of timeframes in minutes")
            current_tf = "1,5,15"
            if self.daily_setting and hasattr(self.daily_setting, 'mtf_timeframes'):
                current_tf = self.daily_setting.mtf_timeframes
            tf_edit.setText(current_tf)
            tf_layout.addRow("Timeframes:", tf_edit)
            self.vars["mtf_timeframes"] = (tf_edit, str)

            tf_hint = QLabel("Example: 1,5,15 for 1min, 5min, and 15min")
            tf_hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
            tf_layout.addRow("", tf_hint)

            # Fast EMA
            fast_spin = QSpinBox()
            fast_spin.setRange(1, 50)
            fast_spin.setSuffix(" periods")
            fast_spin.setToolTip("Fast EMA period for trend detection")
            current_fast = 9
            if self.daily_setting and hasattr(self.daily_setting, 'mtf_ema_fast'):
                current_fast = self.daily_setting.mtf_ema_fast
            fast_spin.setValue(current_fast)
            tf_layout.addRow("Fast EMA:", fast_spin)
            self.vars["mtf_ema_fast"] = (fast_spin, int)

            # Slow EMA
            slow_spin = QSpinBox()
            slow_spin.setRange(5, 200)
            slow_spin.setSuffix(" periods")
            slow_spin.setToolTip("Slow EMA period for trend detection")
            current_slow = 21
            if self.daily_setting and hasattr(self.daily_setting, 'mtf_ema_slow'):
                current_slow = self.daily_setting.mtf_ema_slow
            slow_spin.setValue(current_slow)
            tf_layout.addRow("Slow EMA:", slow_spin)
            self.vars["mtf_ema_slow"] = (slow_spin, int)

            # Agreement Required
            agree_spin = QSpinBox()
            agree_spin.setRange(1, 3)
            agree_spin.setSuffix(" timeframes")
            agree_spin.setToolTip("Number of timeframes that must agree")
            current_agree = 2
            if self.daily_setting and hasattr(self.daily_setting, 'mtf_agreement_required'):
                current_agree = self.daily_setting.mtf_agreement_required
            agree_spin.setValue(current_agree)
            tf_layout.addRow("Agreement Required:", agree_spin)
            self.vars["mtf_agreement_required"] = (agree_spin, int)

            agree_hint = QLabel("How many timeframes must agree before allowing entry")
            agree_hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
            tf_layout.addRow("", agree_hint)

            layout.addWidget(tf_group)

            # Info Card
            info_card = self._create_mtf_info_card()
            layout.addWidget(info_card)

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._build_mtf_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building MTF tab: {e}")

    # ── FEATURE 3: Signal Confidence Tab ─────────────────────────────────────
    def _build_signal_tab(self):
        """Build signal confidence settings tab"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)
            layout.setSpacing(sp.GAP_LG)

            # Confidence Group
            conf_group = QGroupBox("Signal Confidence Settings")
            conf_layout = QFormLayout(conf_group)
            conf_layout.setSpacing(sp.GAP_SM)
            conf_layout.setLabelAlignment(Qt.AlignRight)

            # Min Confidence
            conf_spin = QDoubleSpinBox()
            conf_spin.setRange(0.0, 1.0)
            conf_spin.setSingleStep(0.05)
            conf_spin.setDecimals(2)
            conf_spin.setToolTip("Minimum confidence threshold for signals (0.0-1.0)")
            current_conf = 0.6
            if self.daily_setting and hasattr(self.daily_setting, 'min_confidence'):
                current_conf = self.daily_setting.min_confidence
            conf_spin.setValue(current_conf)
            conf_layout.addRow("Min Confidence:", conf_spin)
            self.vars["min_confidence"] = (conf_spin, float)

            conf_hint = QLabel("Signals below this confidence are suppressed (0.0-1.0)")
            conf_hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
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
            logger.error(f"[DailyTradeSettingGUI._build_signal_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building signal tab: {e}")

    # ── Information Tab ───────────────────────────────────────────────────────
    def _build_info_tab(self):
        """Build the information tab with help content"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)
            layout.setSpacing(sp.GAP_MD)

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
                    "• Supported values: NIFTY50, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX.\n"
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
                    "⚠️  Risk Management",
                    "Daily loss limits and trade counts to protect capital.\n\n"
                    "• **Max Daily Loss**: Stop trading when daily P&L hits this level.\n"
                    "• **Max Trades/Day**: Hard limit on number of entries.\n"
                    "• **Daily Target**: Visual progress indicator for profit goals."
                ),
                (
                    "📈  Multi-Timeframe Filter",
                    "Confirms trend direction across multiple timeframes.\n\n"
                    "• Uses EMA 9/21 crossovers on 1m, 5m, 15m charts.\n"
                    "• Requires at least 2 of 3 timeframes to agree.\n"
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
                    "📁  Where are settings stored?",
                    "Daily trade settings are saved locally to:\n\n"
                    "    config/daily_trade_setting.json\n\n"
                    "The file is written atomically to prevent corruption on unexpected exits. "
                    "Back up this file before making major strategy changes."
                ),
            ]

            for title, body in infos:
                try:
                    info_card = self._create_info_card(title, body)
                    layout.addWidget(info_card)

                except Exception as e:
                    logger.error(f"Failed to create info card for {title}: {e}", exc_info=True)

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._build_info_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building information tab: {e}")

    def _create_info_card(self, title: str, body: str) -> QFrame:
        """Create an information card with themed styling"""
        c = self._c
        ty = self._ty
        sp = self._sp

        card = QFrame()
        card.setObjectName("infoCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        card_layout.setSpacing(sp.GAP_XS)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont(ty.FONT_UI, ty.SIZE_BODY, QFont.Bold))
        title_lbl.setStyleSheet(f"color:{c.TEXT_MAIN};")

        body_lbl = QLabel(body)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")

        card_layout.addWidget(title_lbl)
        card_layout.addWidget(body_lbl)
        return card

    def _create_mtf_info_card(self) -> QFrame:
        """Create info card for MTF filter"""
        c = self._c
        ty = self._ty
        sp = self._sp

        card = QFrame()
        card.setObjectName("infoCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)

        title = QLabel("📘 How Multi-Timeframe Filter Works:")
        title.setFont(QFont(ty.FONT_UI, ty.SIZE_BODY, QFont.Bold))
        title.setStyleSheet(f"color:{c.TEXT_MAIN};")

        text = QLabel(
            "1. For each timeframe, calculates EMA9 and EMA21\n"
            "2. Determines trend: BULLISH (EMA9 > EMA21 > LTP) or BEARISH (EMA9 < EMA21 < LTP)\n"
            "3. Requires at least N timeframes to agree (default: 2 of 3)\n"
            "4. Entry is blocked if insufficient agreement\n\n"
            "This filter helps avoid entries during conflicting trends across timeframes."
        )
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")

        layout.addWidget(title)
        layout.addWidget(text)
        return card

    def _create_error_scroll(self, error_msg):
        """Create a scroll area with error message"""
        c = self._c
        ty = self._ty
        sp = self._sp

        scroll = QScrollArea()
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)

        error_label = QLabel(f"❌ {error_msg}")
        error_label.setStyleSheet(f"color: {c.RED}; padding: {sp.PAD_XL}px;")
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

            # Handle empty strings - allow for string fields, convert to default for numbers
            if not value.strip():
                if typ in (int, float):
                    # Use default from validation ranges
                    if key in self.VALIDATION_RANGES:
                        lo, hi = self.VALIDATION_RANGES[key]
                        default_val = lo if typ == int else float(lo)
                        return True, default_val, None
                    return True, 0, None
                return True, "", None

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
            c = self._c
            sp = self._sp

            self.status_label.setText("✓ Settings saved successfully!")
            self.status_label.setStyleSheet(f"color:{c.GREEN}; font-size:{self._ty.SIZE_XS}pt; font-weight:{self._ty.WEIGHT_BOLD};")
            self.save_btn.setText("✓ Saved!")
            self.save_btn.setStyleSheet(f"""
                QPushButton {{
                    background:{c.GREEN_BRIGHT}; color:{c.TEXT_INVERSE}; border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                    font-weight:{self._ty.WEIGHT_BOLD}; font-size:{self._ty.SIZE_BODY}pt;
                }}
            """)
            # Reset styles after delay
            QTimer.singleShot(1500, self.reset_styles)

            logger.info("Success feedback shown")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.show_success_feedback] Failed: {e}", exc_info=True)

    def show_error_feedback(self, error_msg):
        """Show error feedback with animation"""
        try:
            c = self._c
            sp = self._sp

            self.status_label.setText(f"✗ {error_msg}")
            self.status_label.setStyleSheet(f"color:{c.RED}; font-size:{self._ty.SIZE_XS}pt; font-weight:{self._ty.WEIGHT_BOLD};")
            self.save_btn.setStyleSheet(f"""
                QPushButton {{
                    background:{c.RED}; color:{c.TEXT_INVERSE}; border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                    font-weight:{self._ty.WEIGHT_BOLD}; font-size:{self._ty.SIZE_BODY}pt;
                }}
            """)
            QTimer.singleShot(2000, self.reset_styles)

            logger.warning(f"Error feedback shown: {error_msg}")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.show_error_feedback] Failed: {e}", exc_info=True)

    def reset_styles(self):
        """Reset all styles to normal"""
        try:
            self.save_btn.setText("💾 Save All Settings")
            self.save_btn.setStyleSheet(self._get_button_style())

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
            for key, (widget, typ) in self.vars.items():
                try:
                    if widget is None:
                        logger.warning(f"Widget for {key} is None")
                        continue

                    # Get value based on widget type
                    if isinstance(widget, QLineEdit):
                        text = widget.text().strip()
                    elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                        text = str(widget.value())
                    elif isinstance(widget, QCheckBox):
                        data_to_save[key] = widget.isChecked()
                        continue
                    elif isinstance(widget, QComboBox):
                        text = widget.currentData() if widget.currentData() else widget.currentText()
                    else:
                        logger.warning(f"Unknown widget type for {key}")
                        continue

                    # Validate the value
                    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                        # Already validated by the widget
                        data_to_save[key] = widget.value()
                    else:
                        is_valid, value, error = self.validate_field(key, text, typ)
                        if is_valid:
                            data_to_save[key] = value
                        else:
                            validation_errors.append(error or f"Invalid value for {key}")
                            # Highlight the error
                            if isinstance(widget, QLineEdit):
                                widget.setStyleSheet(
                                    f"QLineEdit {{ background:{self._c.BG_ROW_B}; color:{self._c.TEXT_MAIN}; border:{self._sp.SEPARATOR}px solid {self._c.RED}; }}"
                                )

                except Exception as e:
                    logger.error(f"Error validating field {key}: {e}", exc_info=True)
                    validation_errors.append(f"Validation error for {key}")

            if validation_errors:
                self.tabs.setCurrentIndex(0)
                self.show_error_feedback(validation_errors[0])
                self.save_btn.setEnabled(True)
                self._save_in_progress = False
                self.operation_finished.emit()
                return

            # UPDATED: Add derivative from dropdown if not already in vars
            if "derivative" not in data_to_save and self.derivative_combo is not None:
                data_to_save["derivative"] = self.derivative_combo.currentData()

            # Add interval combo value
            if self.interval_combo is not None:
                data_to_save["history_interval"] = self.interval_combo.currentData()

            # Add sideway checkbox if not already in vars
            if "sideway_zone_trade" not in data_to_save and self.sideway_check is not None:
                data_to_save["sideway_zone_trade"] = self.sideway_check.isChecked()

            # Save in background thread
            threading.Thread(target=self._threaded_save,
                             args=(data_to_save,),
                             daemon=True, name="DailyTradeSave").start()

            logger.info(f"Save operation started with {len(data_to_save)} fields")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.save] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Save failed: {e}")
            self._save_in_progress = False
            self.operation_finished.emit()
            self.save_btn.setEnabled(True)

    def _threaded_save(self, data_to_save: Dict[str, Any]):
        """Threaded save operation"""
        try:
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

            # Save to database
            success = False
            if hasattr(self.daily_setting, 'save'):
                success = self.daily_setting.save()
            else:
                logger.error("Daily setting object has no save method")

            if success:
                self.save_completed.emit(True, "Settings saved successfully!")
                logger.info("Daily trade settings saved successfully")
            else:
                self.save_completed.emit(False, "Failed to save settings to database")
                logger.error("Failed to save daily trade settings to database")

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
        pass

    def _on_operation_finished(self):
        """Handle operation finished signal"""
        pass

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info("[DailyTradeSettingGUI] Starting cleanup")

            # Cancel any pending timers
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
            self.derivative_combo = None  # UPDATED: Clear new field
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
            if self._save_in_progress:
                logger.warning("Closing while save in progress")

            self.cleanup()
            event.accept()

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.closeEvent] Failed: {e}", exc_info=True)
            event.accept()