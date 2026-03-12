"""
DailyTradeSettingGUI.py
=======================
GUI for daily trade settings with database integration.

UPDATED: Consistent tab styling across all dialogs
- Tabs now match the style of BrokerageSettingGUI and BrokerLoginPopup
- Clean card-based layout with proper spacing
- Better visual hierarchy
- Smooth hover effects and transitions
- Consistent use of theme tokens
"""

import logging
import threading
from typing import Optional, Dict, Any, Tuple, List

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve
from gui.dialog_base import ThemedDialog, ThemedMixin, ModernCard, make_separator, make_scrollbar_ss, create_section_header, create_modern_button, apply_tab_style, build_title_bar
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QVBoxLayout, QLabel,
                             QWidget, QTabWidget, QFrame, QScrollArea,
                             QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox,
                             QGroupBox, QHBoxLayout, QSizePolicy)

from Utils.safe_getattr import safe_setattr, safe_hasattr
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

class ModernHeader(QLabel):
    """Modern header with underline accent."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("modernHeader")
        self._apply_style()

    def _apply_style(self):
        c = theme_manager.palette
        ty = theme_manager.typography
        sp = theme_manager.spacing

        self.setStyleSheet(f"""
            QLabel#modernHeader {{
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_XL}pt;
                font-weight: {ty.WEIGHT_BOLD};
                padding-bottom: {sp.PAD_SM}px;
                border-bottom: 2px solid {c.BLUE};
                margin-bottom: {sp.PAD_MD}px;
            }}
        """)

class DailyTradeSettingGUI(ThemedDialog):
    save_completed = pyqtSignal(bool, str)
    # Emitted after a successful save so TradingGUI can refresh dependent widgets
    settings_saved = pyqtSignal()

    # Rule 3: Additional signals for error handling
    error_occurred = pyqtSignal(str)
    operation_started = pyqtSignal()
    operation_finished = pyqtSignal()

    # Exchange choices
    EXCHANGE_CHOICES = [
        ("NSE - National Stock Exchange", "NSE"),
        ("BSE - Bombay Stock Exchange", "BSE"),
    ]

    # Derivative choices per exchange
    DERIVATIVE_CHOICES = {
        "NSE": [
            ("NIFTY 50", "NIFTY50"),
            ("BANK NIFTY", "BANKNIFTY"),
            ("FIN NIFTY", "FINNIFTY"),
            ("MIDCP NIFTY", "MIDCPNIFTY"),
        ],
        "BSE": [
            ("SENSEX", "SENSEX"),
        ]
    }

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
            super().__init__(parent, title="DAILY TRADE SETTINGS", icon="DT", size=(900, 800))

            # Rule 13.2: Connect to theme and density signals

            self.daily_setting = daily_setting
            self.app = app

            # Rule 6: Input validation
            if daily_setting is None:
                logger.error("DailyTradeSettingGUI initialized with None daily_setting")

            self.setModal(True)
            self.setMinimumSize(900, 800)
            self.resize(900, 800)

            # Set window flags for modern look
            # Root layout with margins for shadow effect
            root = QVBoxLayout(self)
            root.setContentsMargins(20, 20, 20, 20)
            root.setSpacing(0)

            # Main container card
            self.main_card = ModernCard(self, elevated=True)
            main_layout = QVBoxLayout(self.main_card)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            # Custom title bar
            title_bar = self._create_title_bar()
            main_layout.addWidget(title_bar)

            # Separator
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setStyleSheet(f"background: {self._c.BORDER}; max-height: 1px;")
            main_layout.addWidget(separator)

            # Content area
            content = QWidget()
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL,
                                             self._sp.PAD_XL, self._sp.PAD_XL)
            content_layout.setSpacing(self._sp.GAP_LG)

            # Tabs with consistent styling matching other dialogs
            self.tabs = self._create_tabs()
            content_layout.addWidget(self.tabs)

            # Status and save area
            status_save_layout = QHBoxLayout()
            status_save_layout.setSpacing(self._sp.GAP_MD)

            self.status_label = QLabel("")
            self.status_label.setAlignment(Qt.AlignLeft)
            self.status_label.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_DIM};
                    font-size: {self._ty.SIZE_SM}pt;
                    padding: {self._sp.PAD_SM}px;
                    background: {self._c.BG_HOVER};
                    border-radius: {self._sp.RADIUS_MD}px;
                }}
            """)
            status_save_layout.addWidget(self.status_label, 1)

            self.save_btn = self._create_modern_button(
                "Save Settings",
                primary=True,
                icon="💾"
            )
            self.save_btn.clicked.connect(self.save)
            status_save_layout.addWidget(self.save_btn)

            content_layout.addLayout(status_save_layout)

            main_layout.addWidget(content)
            root.addWidget(self.main_card)

            self.save_completed.connect(self.on_save_completed)

            # Connect internal signals
            self._connect_signals()

            # Apply theme initially
            self.apply_theme()

            # Trigger initial update after UI is built
            QTimer.singleShot(0, lambda: self._on_derivative_changed(
                self.derivative_combo.currentIndex() if self.derivative_combo else 0
            ))

            logger.info("DailyTradeSettingGUI initialized")

        except Exception as e:
            logger.critical(f"[DailyTradeSettingGUI.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _create_title_bar(self):
        """Build new-design title bar: monogram badge + CAPS title + ghost buttons."""
        return build_title_bar(
            self,
            title="DAILY TRADE SETTINGS",
            icon="DT",
            on_close=self.reject,
        )

    def _create_tabs(self):
        """Create tabs with consistent styling matching other dialogs."""
        tabs = QTabWidget()

        # Apply the consistent tab styling used across all dialogs
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {self._c.BORDER};
                border-top: none;
                border-radius: 0 0 {self._sp.RADIUS_MD}px {self._sp.RADIUS_MD}px;
                background: {self._c.BG_MAIN};
            }}
            QTabBar::tab {{
                background: {self._c.BG_CARD};
                color: {self._c.TEXT_DIM};
                padding: {self._sp.PAD_SM}px {self._sp.PAD_LG}px;
                min-width: 110px;
                border: 1px solid {self._c.BORDER};
                border-bottom: none;
                border-radius: {self._sp.RADIUS_MD}px {self._sp.RADIUS_MD}px 0 0;
                font-size: {self._ty.SIZE_SM}pt;
                font-weight: 600;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {self._c.BG_MAIN};
                color: {self._c.TEXT_BRIGHT};
                border-color: {self._c.BORDER};
                border-bottom: 2px solid {self._c.BLUE};
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
            QTabBar::tab:hover:!selected {{
                background: {self._c.BG_HOVER};
                color: {self._c.TEXT_MAIN};
                border-color: {self._c.BORDER_STRONG};
            }}
        """)

        # Add all tabs
        tabs.addTab(self._build_settings_tab(), "⚙️ Core")
        tabs.addTab(self._build_risk_tab(), "⚠️ Risk")
        tabs.addTab(self._build_mtf_tab(), "📈 MTF")
        tabs.addTab(self._build_info_tab(), "ℹ️ Info")

        return tabs

    def _create_modern_button(self, text, primary=False, icon=""):
        """Create a modern styled button."""
        btn = QPushButton(f"{icon} {text}" if icon else text)
        btn.setCursor(Qt.PointingHandCursor)

        if primary:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BLUE};
                    color: white;
                    border: none;
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    min-width: 150px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BLUE_DARK};
                }}
                QPushButton:pressed {{
                    background: {self._c.BLUE};
                    opacity: 0.8;
                }}
                QPushButton:disabled {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_DISABLED};
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    min-width: 120px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BORDER};
                    border-color: {self._c.BORDER_FOCUS};
                }}
            """)

        return btn

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults."""
        self.daily_setting = None
        self.app = None
        self.tabs = None
        self.vars = {}
        self.entries = {}
        self.exchange_combo = None
        self.derivative_combo = None
        self.expiry_badge = None
        self.sideway_check = None
        self.status_label = None
        self.save_btn = None
        self._save_in_progress = False
        self._save_timer = None

    def apply_theme(self, _: str = None) -> None:
        """Rule 13.2: Apply theme colors to the dialog."""
        try:
            # Update main card style
            if self.main_card:
                self.main_card._apply_style()

            # Update title bar
            # if self.title_bar:
            #     self.title_bar.setStyleSheet(f"background: {self._c.BG_PANEL};")

            # Update status label
            if self.status_label:
                self.status_label.setStyleSheet(f"""
                    QLabel {{
                        color: {self._c.TEXT_DIM};
                        font-size: {self._ty.SIZE_SM}pt;
                        padding: {self._sp.PAD_SM}px;
                        background: {self._c.BG_HOVER};
                        border-radius: {self._sp.RADIUS_MD}px;
                    }}
                """)

            # Update tabs with consistent styling
            if self.tabs:
                self.tabs.setStyleSheet(f"""
                    QTabWidget::pane {{
                        border: {self._sp.SEPARATOR}px solid {self._c.BORDER};
                        border-radius: {self._sp.RADIUS_MD}px;
                        background: {self._c.BG_PANEL};
                        margin-top: {self._sp.PAD_SM}px;
                    }}
                    QTabBar::tab {{
                        background: {self._c.BG_HOVER};
                        color: {self._c.TEXT_DIM};
                        padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                        min-width: 130px;
                        border: {self._sp.SEPARATOR}px solid {self._c.BORDER};
                        border-bottom: none;
                        border-radius: {self._sp.RADIUS_SM}px {self._sp.RADIUS_SM}px 0 0;
                        font-size: {self._ty.SIZE_BODY}pt;
                        margin-right: {self._sp.PAD_XS}px;
                    }}
                    QTabBar::tab:selected {{
                        background: {self._c.BG_PANEL};
                        color: {self._c.TEXT_MAIN};
                        border-bottom: {self._sp.PAD_XS}px solid {self._c.BLUE};
                        font-weight: {self._ty.WEIGHT_BOLD};
                    }}
                    QTabBar::tab:hover:!selected {{
                        background: {self._c.BORDER};
                        color: {self._c.TEXT_MAIN};
                    }}
                """)

            # Update buttons
            self._update_button_styles()

            logger.debug("[DailyTradeSettingGUI.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.apply_theme] Failed: {e}", exc_info=True)

    def _update_button_styles(self):
        """Update button styles with theme tokens"""
        # Save button
        if self.save_btn:
            self.save_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BLUE};
                    color: white;
                    border: none;
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    min-width: 150px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BLUE_DARK};
                }}
                QPushButton:disabled {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_DISABLED};
                }}
            """)

    def _connect_signals(self):
        """Connect internal signals."""
        try:
            self.error_occurred.connect(self._on_error)
            self.operation_started.connect(self._on_operation_started)
            self.operation_finished.connect(self._on_operation_finished)
        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._connect_signals] Failed: {e}", exc_info=True)

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails."""
        try:
            super().__init__(parent)
            self.setMinimumSize(400, 200)

            # Set window flags for modern look
            root = QVBoxLayout(self)
            root.setContentsMargins(20, 20, 20, 20)

            main_card = ModernCard(self, elevated=True)
            layout = QVBoxLayout(main_card)
            layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL,
                                     self._sp.PAD_XL, self._sp.PAD_XL)

            error_label = QLabel("❌ Failed to initialize settings dialog.\nPlease check the logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet(
                f"color: {self._c.RED_BRIGHT}; padding: {self._sp.PAD_XL}px; "
                f"font-size: {self._ty.SIZE_MD}pt;"
            )
            layout.addWidget(error_label)

            close_btn = self._create_modern_button("Close", primary=False)
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn, 0, Qt.AlignCenter)

            root.addWidget(main_card)

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._create_error_dialog] Failed: {e}", exc_info=True)

    # ── Core Settings Tab ─────────────────────────────────────────────────────

    def _build_settings_tab(self):
        """Build the core settings tab with form fields."""
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

            container = QWidget()
            container.setStyleSheet("background: transparent;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(self._sp.GAP_LG)

            self.vars = {}
            self.entries = {}

            # Exchange Selection Card
            exchange_card = ModernCard()
            exchange_layout = QVBoxLayout(exchange_card)
            exchange_layout.setSpacing(self._sp.GAP_MD)

            exchange_header = QLabel("🌐 Exchange Selection")
            exchange_header.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            exchange_layout.addWidget(exchange_header)

            self.exchange_combo = QComboBox()
            for display, value in self.EXCHANGE_CHOICES:
                self.exchange_combo.addItem(display, value)
            self.exchange_combo.setStyleSheet(f"""
                QComboBox {{
                    background: {self._c.BG_INPUT};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                    min-height: {self._sp.INPUT_HEIGHT}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                }}
                QComboBox:hover {{
                    border-color: {self._c.BORDER_FOCUS};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: {self._sp.ICON_LG}px;
                }}
                QComboBox QAbstractItemView {{
                    background: {self._c.BG_PANEL};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    selection-background-color: {self._c.BG_SELECTED};
                }}
            """)

            # Restore saved exchange value
            current_exchange = "NSE"
            if self.daily_setting is not None and safe_hasattr(self.daily_setting, 'exchange'):
                current_exchange = self.daily_setting.exchange

            for i in range(self.exchange_combo.count()):
                if self.exchange_combo.itemData(i) == current_exchange:
                    self.exchange_combo.setCurrentIndex(i)
                    break

            self.exchange_combo.currentIndexChanged.connect(self._on_exchange_changed)
            exchange_layout.addWidget(self.exchange_combo)

            exchange_hint = QLabel("Select the exchange where you want to trade")
            exchange_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            exchange_layout.addWidget(exchange_hint)

            layout.addWidget(exchange_card)

            # Derivative Selection Card
            derivative_card = ModernCard()
            derivative_layout = QVBoxLayout(derivative_card)
            derivative_layout.setSpacing(self._sp.GAP_MD)

            derivative_header = QLabel("💡 Derivative Selection")
            derivative_header.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            derivative_layout.addWidget(derivative_header)

            deriv_row = QHBoxLayout()
            deriv_row.setSpacing(self._sp.GAP_MD)

            self.derivative_combo = self._create_derivative_dropdown()
            deriv_row.addWidget(self.derivative_combo, 1)

            self.expiry_badge = QLabel("")
            self.expiry_badge.setFixedWidth(140)
            self.expiry_badge.setAlignment(Qt.AlignCenter)
            self.expiry_badge.setStyleSheet(f"""
                QLabel {{
                    font-size: {self._ty.SIZE_XS}pt;
                    border-radius: {self._sp.RADIUS_PILL}px;
                    padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                }}
            """)
            deriv_row.addWidget(self.expiry_badge)

            derivative_layout.addLayout(deriv_row)

            derivative_hint = QLabel("Auto-fills lot size, freeze limit, and strike multiplier")
            derivative_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            derivative_layout.addWidget(derivative_hint)

            layout.addWidget(derivative_card)

            # Static Fields Card (Read-Only)
            static_card = ModernCard()
            static_layout = QVBoxLayout(static_card)
            static_layout.setSpacing(self._sp.GAP_MD)

            static_header = QLabel("📊 Static Values (Read-Only)")
            static_header.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            static_layout.addWidget(static_header)

            static_form = QFormLayout()
            static_form.setSpacing(self._sp.GAP_SM)
            static_form.setLabelAlignment(Qt.AlignRight)
            static_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

            # Lot Size
            lot_edit = QLineEdit()
            lot_edit.setReadOnly(True)
            lot_edit.setStyleSheet(f"""
                QLineEdit {{
                    background: {self._c.BG_PANEL};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER_DIM};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                }}
            """)
            static_form.addRow("🔢 Lot Size:", lot_edit)
            self.entries["lot_size"] = lot_edit
            # NOTE: lot_size is NOT added to self.vars — it's read-only and derived
            # from OptionUtils.get_lot_size() at save time, never from user input.

            # Freeze Size
            freeze_edit = QLineEdit()
            freeze_edit.setReadOnly(True)
            freeze_edit.setStyleSheet(lot_edit.styleSheet())
            static_form.addRow("❄️ Freeze Size:", freeze_edit)
            self.entries["freeze_size"] = freeze_edit

            # Strike Multiplier
            multiplier_edit = QLineEdit()
            multiplier_edit.setReadOnly(True)
            multiplier_edit.setStyleSheet(lot_edit.styleSheet())
            static_form.addRow("📊 Strike Multiplier:", multiplier_edit)
            self.entries["multiplier"] = multiplier_edit

            static_layout.addLayout(static_form)
            layout.addWidget(static_card)

            # Configurable Fields Card
            config_card = ModernCard()
            config_layout = QVBoxLayout(config_card)
            config_layout.setSpacing(self._sp.GAP_MD)

            config_header = QLabel("⚙️ Trading Parameters")
            config_header.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            config_layout.addWidget(config_header)

            config_form = QFormLayout()
            config_form.setSpacing(self._sp.GAP_MD)
            config_form.setLabelAlignment(Qt.AlignRight)
            config_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

            fields = [
                ("📆 Week", "week", int, "Weekly expiry offset (0 = current)"),
                ("📈 Max Options", "max_num_of_option", int, "Maximum open positions"),
                ("🔻 Lower %", "lower_percentage", float, "Minimum move % to trigger entry"),
                ("⏰ Cancel After (Seconds)", "cancel_after", int, "Cancel unfilled orders after (seconds)"),
                ("💰 Capital Reserve (₹)", "capital_reserve", int, "Capital to keep reserved"),
            ]

            for label, key, typ, tooltip in fields:
                edit = QLineEdit()
                edit.setPlaceholderText("Auto-filled from saved settings")
                edit.setToolTip(tooltip)
                edit.setStyleSheet(f"""
                    QLineEdit {{
                        background: {self._c.BG_INPUT};
                        color: {self._c.TEXT_MAIN};
                        border: 1px solid {self._c.BORDER};
                        border-radius: {self._sp.RADIUS_MD}px;
                        padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                        min-height: {self._sp.INPUT_HEIGHT}px;
                        font-size: {self._ty.SIZE_BODY}pt;
                    }}
                    QLineEdit:focus {{
                        border-color: {self._c.BORDER_FOCUS};
                    }}
                """)

                val = ""
                if self.daily_setting is not None and safe_hasattr(self.daily_setting, 'data'):
                    val = self.daily_setting.data.get(key, "")
                edit.setText(str(val))

                config_form.addRow(f"{label}:", edit)
                self.vars[key] = (edit, typ)
                self.entries[key] = edit

            # ── Lookback spinners (0–10 strikes from ATM) ─────────────────────
            # Value is an integer count of strikes away from ATM.
            # 0 = ATM, 1 = one strike OTM, 2 = two strikes OTM, etc.
            # The instrument multiplier (50 for NIFTY, 100 for BANKNIFTY, etc.)
            # is applied automatically in order_executor and subscribe_market_data.
            _lb_spinbox_style = f"""
                QSpinBox {{
                    background: {self._c.BG_INPUT};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                    min-height: {self._sp.INPUT_HEIGHT}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                }}
                QSpinBox:focus {{ border-color: {self._c.BORDER_FOCUS}; }}
                QSpinBox::up-button, QSpinBox::down-button {{
                    width: 18px;
                    border: none;
                    background: {self._c.BG_HOVER};
                }}
            """
            _lb_tooltip_call = (
                "Strikes from ATM for the CALL leg.\n"
                "0 = ATM  |  1 = one strike OTM  |  2 = two strikes OTM …\n"
                "Higher values select cheaper (further OTM) options."
            )
            _lb_tooltip_put = (
                "Strikes from ATM for the PUT leg.\n"
                "0 = ATM  |  1 = one strike OTM  |  2 = two strikes OTM …\n"
                "Higher values select cheaper (further OTM) options."
            )

            call_lb_spin = QSpinBox()
            call_lb_spin.setRange(0, 10)
            call_lb_spin.setSuffix(" strike(s) from ATM")
            call_lb_spin.setToolTip(_lb_tooltip_call)
            call_lb_spin.setStyleSheet(_lb_spinbox_style)
            if self.daily_setting is not None and safe_hasattr(self.daily_setting, 'data'):
                call_lb_spin.setValue(int(self.daily_setting.data.get("call_lookback", 0)))
            config_form.addRow("🔎 Call Lookback:", call_lb_spin)
            self.vars["call_lookback"] = (call_lb_spin, int)
            self.entries["call_lookback"] = call_lb_spin

            put_lb_spin = QSpinBox()
            put_lb_spin.setRange(0, 10)
            put_lb_spin.setSuffix(" strike(s) from ATM")
            put_lb_spin.setToolTip(_lb_tooltip_put)
            put_lb_spin.setStyleSheet(_lb_spinbox_style)
            if self.daily_setting is not None and safe_hasattr(self.daily_setting, 'data'):
                put_lb_spin.setValue(int(self.daily_setting.data.get("put_lookback", 0)))
            config_form.addRow("🔎 Put Lookback:", put_lb_spin)
            self.vars["put_lookback"] = (put_lb_spin, int)
            self.entries["put_lookback"] = put_lb_spin

            config_layout.addLayout(config_form)
            layout.addWidget(config_card)

            # Sideway Zone Checkbox Card
            sideway_card = ModernCard()
            sideway_layout = QVBoxLayout(sideway_card)
            sideway_layout.setSpacing(self._sp.GAP_SM)

            self.sideway_check = QCheckBox("Enable trading during sideways market (12:00–14:00)")
            self.sideway_check.setStyleSheet(f"""
                QCheckBox {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_BODY}pt;
                    spacing: {self._sp.GAP_SM}px;
                }}
                QCheckBox::indicator {{
                    width: {self._sp.ICON_MD}px;
                    height: {self._sp.ICON_MD}px;
                    border: 2px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_SM}px;
                }}
                QCheckBox::indicator:checked {{
                    background: {self._c.BLUE};
                    border-color: {self._c.BLUE};
                    image: none;
                }}
                QCheckBox::indicator:hover {{
                    border-color: {self._c.BORDER_FOCUS};
                }}
            """)

            checked = False
            if self.daily_setting is not None and safe_hasattr(self.daily_setting, 'data'):
                checked = self.daily_setting.data.get("sideway_zone_trade", False)
            self.sideway_check.setChecked(checked)

            sideway_layout.addWidget(self.sideway_check)
            sideway_hint = QLabel("Allow entries during the low-volatility midday window")
            sideway_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            sideway_layout.addWidget(sideway_hint)

            self.vars["sideway_zone_trade"] = (self.sideway_check, bool)
            layout.addWidget(sideway_card)

            layout.addStretch()
            scroll.setWidget(container)

            # Trigger initial derivative update
            QTimer.singleShot(0, lambda: self._on_derivative_changed(
                self.derivative_combo.currentIndex() if self.derivative_combo else 0
            ))

            return scroll

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._build_settings_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building settings tab: {e}")

    def _create_derivative_dropdown(self) -> QComboBox:
        """Create dropdown for derivative selection and wire the change signal."""
        try:
            combo = QComboBox()
            combo.setToolTip("The underlying instrument whose options or futures will be traded.")

            # Initially populate based on current exchange
            exchange = "NSE"
            if self.exchange_combo is not None:
                exchange = self.exchange_combo.currentData()

            for display, value in self.DERIVATIVE_CHOICES.get(exchange, self.DERIVATIVE_CHOICES["NSE"]):
                combo.addItem(display, value)

            combo.setStyleSheet(f"""
                QComboBox {{
                    background: {self._c.BG_INPUT};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                    min-height: {self._sp.INPUT_HEIGHT}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                }}
                QComboBox:hover {{
                    border-color: {self._c.BORDER_FOCUS};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: {self._sp.ICON_LG}px;
                }}
                QComboBox QAbstractItemView {{
                    background: {self._c.BG_PANEL};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    selection-background-color: {self._c.BG_SELECTED};
                }}
            """)

            # Restore saved value
            current_val = "NIFTY50"
            if self.daily_setting is not None and safe_hasattr(self.daily_setting, 'derivative'):
                current_val = self.daily_setting.derivative

            found = False
            for i in range(combo.count()):
                if combo.itemData(i) == current_val:
                    combo.setCurrentIndex(i)
                    found = True
                    break

            if not found:
                logger.warning(f"Derivative value {current_val} not found in choices")

            # Store in vars for saving
            self.vars["derivative"] = (combo, str)
            self.entries["derivative"] = combo

            # Connect change signal AFTER storing reference
            self.derivative_combo = combo
            combo.currentIndexChanged.connect(self._on_derivative_changed)

            return combo

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._create_derivative_dropdown] Failed: {e}", exc_info=True)
            combo = QComboBox()
            combo.addItem("Error", "NIFTY50")
            combo.setEnabled(False)
            return combo

    # ── Exchange change handler ───────────────────────────────────────────────

    def _on_exchange_changed(self, _index: int) -> None:
        """Update derivative choices based on selected exchange."""
        try:
            if self.exchange_combo is None or self.derivative_combo is None:
                return

            exchange = self.exchange_combo.currentData()

            # Clear and repopulate derivative combo based on exchange
            self.derivative_combo.clear()

            for display, value in self.DERIVATIVE_CHOICES.get(exchange, self.DERIVATIVE_CHOICES["NSE"]):
                self.derivative_combo.addItem(display, value)

            # Trigger derivative change to update static fields
            self._on_derivative_changed(0)

            logger.info(f"[_on_exchange_changed] Exchange set to {exchange}")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._on_exchange_changed] Failed: {e}", exc_info=True)

    # ── Derivative change handler ─────────────────────────────────────────────

    def _on_derivative_changed(self, _index: int) -> None:
        """Auto-fill lot size and update week/badge when derivative changes."""
        try:
            if self.derivative_combo is None:
                return

            derivative_val = self.derivative_combo.currentData()
            if not derivative_val:
                return

            # Update static fields from OptionUtils
            self._update_static_fields(derivative_val)

            # ── Expiry-type badge ─────────────────────────────────────────────
            has_weekly = OptionUtils.has_weekly_expiry(derivative_val)
            if self.expiry_badge is not None:
                if has_weekly:
                    self.expiry_badge.setText("Weekly + Monthly")
                    self.expiry_badge.setStyleSheet(f"""
                        QLabel {{
                            color: {self._c.GREEN};
                            background: {self._c.BG_HOVER};
                            font-size: {self._ty.SIZE_XS}pt;
                            border-radius: {self._sp.RADIUS_PILL}px;
                            padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                            border: 1px solid {self._c.GREEN};
                        }}
                    """)
                else:
                    self.expiry_badge.setText("Monthly Only")
                    self.expiry_badge.setStyleSheet(f"""
                        QLabel {{
                            color: {self._c.TEXT_DIM};
                            background: {self._c.BG_HOVER};
                            font-size: {self._ty.SIZE_XS}pt;
                            border-radius: {self._sp.RADIUS_PILL}px;
                            padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                            border: 1px solid {self._c.BORDER};
                        }}
                    """)

            # ── Week field: disable for monthly-only indices ──────────────────
            week_edit = self.entries.get("week")
            if week_edit and isinstance(week_edit, QLineEdit):
                week_edit.setEnabled(has_weekly)
                if not has_weekly:
                    week_edit.setText("0")
                    week_edit.setToolTip(
                        f"{derivative_val} has monthly-only expiry since SEBI circular "
                        "Nov 20, 2024. Weekly expiry selection is not applicable."
                    )
                else:
                    week_edit.setToolTip(
                        "0 = current/nearest weekly expiry.\n"
                        "1 = next week's expiry, 2 = two weeks out, etc."
                    )

            # ── Max options: fill default if field is empty ───────────────────
            max_edit = self.entries.get("max_num_of_option")
            if max_edit and isinstance(max_edit, QLineEdit) and not max_edit.text().strip():
                default_max = OptionUtils.get_default_max_options(derivative_val)
                max_edit.setText(str(default_max))

            # ── Lot size: fetch live in background thread ─────────────────────
            lot_edit = self.entries.get("lot_size")
            if lot_edit and isinstance(lot_edit, QLineEdit):
                # Show a placeholder while fetching
                lot_edit.setPlaceholderText("Fetching...")

                def _fetch_lot(sym: str):
                    try:
                        lot = OptionUtils.get_lot_size(sym)
                        QTimer.singleShot(0, lambda: self._apply_lot_size(lot))
                    except Exception as ex:
                        logger.error(f"[_fetch_lot] Failed for {sym}: {ex}", exc_info=True)
                        fallback = OptionUtils.LOT_SIZE_MAP.get(
                            OptionUtils.get_exchange_symbol(sym), 65
                        )
                        QTimer.singleShot(0, lambda: self._apply_lot_size(fallback))

                threading.Thread(
                    target=_fetch_lot,
                    args=(derivative_val,),
                    daemon=True,
                    name="LotSizeFetch"
                ).start()

            logger.info(
                f"[_on_derivative_changed] derivative={derivative_val}, "
                f"has_weekly={has_weekly}"
            )

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._on_derivative_changed] Failed: {e}", exc_info=True)

    def _update_static_fields(self, derivative_val: str) -> None:
        """Update static fields from OptionUtils based on selected derivative."""
        try:
            # Update lot size
            lot_edit = self.entries.get("lot_size")
            if lot_edit:
                lot_size = OptionUtils.get_lot_size(derivative_val, fallback=0)
                if lot_size > 0:
                    lot_edit.setText(str(lot_size))
                else:
                    lot_edit.setText("N/A")

            # Update freeze size
            freeze_edit = self.entries.get("freeze_size")
            if freeze_edit:
                freeze_size = OptionUtils.get_freeze_size(derivative_val)
                if freeze_size > 0:
                    freeze_edit.setText(str(freeze_size))
                else:
                    freeze_edit.setText("N/A")

            # Update multiplier
            multiplier_edit = self.entries.get("multiplier")
            if multiplier_edit:
                multiplier = OptionUtils.get_multiplier(derivative_val)
                multiplier_edit.setText(str(multiplier))

            logger.debug(f"[_update_static_fields] Updated static fields for {derivative_val}")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._update_static_fields] Failed: {e}", exc_info=True)

    def _apply_lot_size(self, lot_size: int) -> None:
        """Apply the fetched lot size to the lot_size field (must run on main thread)."""
        try:
            lot_edit = self.entries.get("lot_size")
            if lot_edit and isinstance(lot_edit, QLineEdit):
                lot_edit.setText(str(lot_size))
                lot_edit.setPlaceholderText("Auto-filled from NSE on derivative change")
            logger.debug(f"[_apply_lot_size] Set lot_size to {lot_size}")
        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._apply_lot_size] Failed: {e}", exc_info=True)

    # ── Risk Management Tab ───────────────────────────────────────────────────

    def _build_risk_tab(self):
        """Build risk management tab."""
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

            container = QWidget()
            container.setStyleSheet("background: transparent;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(self._sp.GAP_LG)

            # Risk Limits Card
            risk_card = ModernCard()
            risk_layout = QVBoxLayout(risk_card)
            risk_layout.setSpacing(self._sp.GAP_MD)

            risk_header = QLabel("⚠️ Daily Risk Limits")
            risk_header.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            risk_layout.addWidget(risk_header)

            risk_form = QFormLayout()
            risk_form.setSpacing(self._sp.GAP_MD)
            risk_form.setLabelAlignment(Qt.AlignRight)

            # Max Daily Loss
            loss_spin = QDoubleSpinBox()
            loss_spin.setRange(-1000000, 0)
            loss_spin.setSingleStep(100)
            loss_spin.setPrefix("₹")
            loss_spin.setStyleSheet(self._get_spinbox_style())
            current_loss = -5000
            if self.daily_setting and safe_hasattr(self.daily_setting, 'max_daily_loss'):
                current_loss = self.daily_setting.max_daily_loss
            loss_spin.setValue(current_loss)
            risk_form.addRow("Max Daily Loss:", loss_spin)
            self.vars["max_daily_loss"] = (loss_spin, float)
            self.entries["max_daily_loss"] = loss_spin

            # Max Trades Per Day
            trades_spin = QSpinBox()
            trades_spin.setRange(1, 100)
            trades_spin.setSuffix(" trades")
            trades_spin.setStyleSheet(self._get_spinbox_style())
            current_trades = 10
            if self.daily_setting and safe_hasattr(self.daily_setting, 'max_trades_per_day'):
                current_trades = self.daily_setting.max_trades_per_day
            trades_spin.setValue(current_trades)
            risk_form.addRow("Max Trades/Day:", trades_spin)
            self.vars["max_trades_per_day"] = (trades_spin, int)
            self.entries["max_trades_per_day"] = trades_spin

            # Daily Profit Target
            target_spin = QDoubleSpinBox()
            target_spin.setRange(0, 1000000)
            target_spin.setSingleStep(100)
            target_spin.setPrefix("₹")
            target_spin.setStyleSheet(self._get_spinbox_style())
            current_target = 5000
            if self.daily_setting and safe_hasattr(self.daily_setting, 'daily_target'):
                current_target = self.daily_setting.daily_target
            target_spin.setValue(current_target)
            risk_form.addRow("Daily Target:", target_spin)
            self.vars["daily_target"] = (target_spin, float)
            self.entries["daily_target"] = target_spin

            risk_layout.addLayout(risk_form)
            layout.addWidget(risk_card)

            # Info Card
            info_card = self._create_info_card(
                "📘 About Risk Management",
                "• Max Daily Loss: Stop trading when daily P&L reaches this level\n"
                "• Max Trades/Day: Hard limit on number of entries\n"
                "• Daily Target: Visual progress indicator only"
            )
            layout.addWidget(info_card)

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._build_risk_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building risk tab: {e}")

    def _get_spinbox_style(self):
        """Get consistent spinbox styling."""
        return f"""
            QSpinBox, QDoubleSpinBox {{
                background: {self._c.BG_INPUT};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
                padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                min-height: {self._sp.INPUT_HEIGHT}px;
                font-size: {self._ty.SIZE_BODY}pt;
            }}
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: {self._c.BORDER_FOCUS};
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                background: {self._c.BG_HOVER};
                border: none;
                width: {self._sp.ICON_MD}px;
            }}
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
                background: {self._c.BORDER};
            }}
        """

    # ── Multi-Timeframe Filter Tab ────────────────────────────────────────────

    def _build_mtf_tab(self):
        """Build Multi-Timeframe Filter settings tab."""
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            container = QWidget()
            container.setStyleSheet("background: transparent;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(self._sp.GAP_LG)

            # Enable MTF Card
            enable_card = ModernCard()
            enable_layout = QVBoxLayout(enable_card)
            enable_layout.setSpacing(self._sp.GAP_MD)

            enable_header = QLabel("📈 Multi-Timeframe Filter")
            enable_header.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            enable_layout.addWidget(enable_header)

            mtf_check = QCheckBox("Enable Multi-Timeframe Filter")
            mtf_check.setStyleSheet(f"""
                QCheckBox {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_BODY}pt;
                    spacing: {self._sp.GAP_SM}px;
                }}
                QCheckBox::indicator {{
                    width: {self._sp.ICON_MD}px;
                    height: {self._sp.ICON_MD}px;
                    border: 2px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_SM}px;
                }}
                QCheckBox::indicator:checked {{
                    background: {self._c.BLUE};
                    border-color: {self._c.BLUE};
                }}
            """)
            current_enabled = False
            if self.daily_setting and safe_hasattr(self.daily_setting, 'use_mtf_filter'):
                current_enabled = self.daily_setting.use_mtf_filter
            mtf_check.setChecked(current_enabled)
            enable_layout.addWidget(mtf_check)
            self.vars["use_mtf_filter"] = (mtf_check, bool)

            enable_hint = QLabel("Requires agreement across multiple timeframes before entry")
            enable_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            enable_layout.addWidget(enable_hint)

            layout.addWidget(enable_card)

            # Configuration Card
            config_card = ModernCard()
            config_layout = QVBoxLayout(config_card)
            config_layout.setSpacing(self._sp.GAP_MD)

            config_header = QLabel("⚙️ MTF Configuration")
            config_header.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            config_layout.addWidget(config_header)

            config_form = QFormLayout()
            config_form.setSpacing(self._sp.GAP_MD)
            config_form.setLabelAlignment(Qt.AlignRight)

            # Timeframes
            tf_edit = QLineEdit()
            tf_edit.setPlaceholderText("1,5,15")
            tf_edit.setStyleSheet(f"""
                QLineEdit {{
                    background: {self._c.BG_INPUT};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                    min-height: {self._sp.INPUT_HEIGHT}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                }}
                QLineEdit:focus {{
                    border-color: {self._c.BORDER_FOCUS};
                }}
            """)
            current_tf = "1,5,15"
            if self.daily_setting and safe_hasattr(self.daily_setting, 'mtf_timeframes'):
                current_tf = self.daily_setting.mtf_timeframes
            tf_edit.setText(current_tf)
            config_form.addRow("Timeframes:", tf_edit)
            self.vars["mtf_timeframes"] = (tf_edit, str)

            # Fast EMA
            fast_spin = QSpinBox()
            fast_spin.setRange(1, 50)
            fast_spin.setSuffix(" periods")
            fast_spin.setStyleSheet(self._get_spinbox_style())
            current_fast = 9
            if self.daily_setting and safe_hasattr(self.daily_setting, 'mtf_ema_fast'):
                current_fast = self.daily_setting.mtf_ema_fast
            fast_spin.setValue(current_fast)
            config_form.addRow("Fast EMA:", fast_spin)
            self.vars["mtf_ema_fast"] = (fast_spin, int)

            # Slow EMA
            slow_spin = QSpinBox()
            slow_spin.setRange(5, 200)
            slow_spin.setSuffix(" periods")
            slow_spin.setStyleSheet(self._get_spinbox_style())
            current_slow = 21
            if self.daily_setting and safe_hasattr(self.daily_setting, 'mtf_ema_slow'):
                current_slow = self.daily_setting.mtf_ema_slow
            slow_spin.setValue(current_slow)
            config_form.addRow("Slow EMA:", slow_spin)
            self.vars["mtf_ema_slow"] = (slow_spin, int)

            # Agreement Required
            agree_spin = QSpinBox()
            agree_spin.setRange(1, 3)
            agree_spin.setSuffix(" timeframes")
            agree_spin.setStyleSheet(self._get_spinbox_style())
            current_agree = 2
            if self.daily_setting and safe_hasattr(self.daily_setting, 'mtf_agreement_required'):
                current_agree = self.daily_setting.mtf_agreement_required
            agree_spin.setValue(current_agree)
            config_form.addRow("Agreement Required:", agree_spin)
            self.vars["mtf_agreement_required"] = (agree_spin, int)

            config_layout.addLayout(config_form)
            layout.addWidget(config_card)

            # Info Card
            info_card = self._create_mtf_info_card()
            layout.addWidget(info_card)

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._build_mtf_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building MTF tab: {e}")

    # ── Information Tab ───────────────────────────────────────────────────────

    def _build_info_tab(self):
        """Build the information tab with help content."""
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

            container = QWidget()
            container.setStyleSheet("background: transparent;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(self._sp.GAP_MD)

            infos = [
                ("🌐 Exchange", "NSE: NIFTY50, BANKNIFTY, FINNIFTY, MIDCPNIFTY\nBSE: SENSEX"),
                ("📆 Week", "Weekly expiry offset (0 = current) - only for NIFTY/SENSEX"),
                ("💡 Derivative", "Auto-fills lot size, freeze limit, and strike multiplier"),
                ("🔢 Static Fields", "Lot Size, Freeze Size, Strike Multiplier - read-only from OptionUtils"),
                ("⚠️ Risk", "Daily loss limits and trade counts to protect capital"),
                ("📈 MTF Filter", "Confirms trend across multiple timeframes"),
                ("🎯 Signal Confidence", "Weighted voting system for signal groups"),
            ]

            for title, body in infos:
                info_card = self._create_info_card(title, body)
                layout.addWidget(info_card)

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._build_info_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building information tab: {e}")

    def _create_info_card(self, title: str, body: str) -> QFrame:
        """Create an information card with themed styling."""
        card = ModernCard()
        layout = QVBoxLayout(card)
        layout.setSpacing(self._sp.GAP_SM)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_SM}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
        """)

        body_lbl = QLabel(body)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")

        layout.addWidget(title_lbl)
        layout.addWidget(body_lbl)
        return card

    def _create_mtf_info_card(self) -> QFrame:
        """Create info card for MTF filter."""
        return self._create_info_card(
            "📘 How Multi-Timeframe Filter Works",
            "1. For each timeframe, calculates EMA9 and EMA21\n"
            "2. Determines trend direction\n"
            "3. Requires N timeframes to agree (default: 2 of 3)\n"
            "4. Entry blocked if insufficient agreement"
        )

    def _create_error_scroll(self, error_msg):
        """Create a scroll area with error message."""
        scroll = QScrollArea()
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL,
                                 self._sp.PAD_XL, self._sp.PAD_XL)

        error_label = QLabel(f"❌ {error_msg}")
        error_label.setStyleSheet(f"color: {self._c.RED}; padding: {self._sp.PAD_XL}px;")
        error_label.setWordWrap(True)
        layout.addWidget(error_label)
        scroll.setWidget(container)
        return scroll

    # ── Validation ────────────────────────────────────────────────────────────

    def validate_field(self, key: str, value: str, typ: type) -> Tuple[bool, Any, Optional[str]]:
        """Validate a field value against type and range constraints."""
        try:
            if not isinstance(key, str):
                return False, None, "Invalid field key"

            if not value.strip():
                if typ in (int, float):
                    if key in self.VALIDATION_RANGES:
                        lo, hi = self.VALIDATION_RANGES[key]
                        return True, lo if typ == int else float(lo), None
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

                else:
                    return True, value, None

            except ValueError as e:
                logger.debug(f"ValueError validating {key}={value}: {e}")
                return False, None, f"Invalid {typ.__name__} value for {key}"

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.validate_field] Failed for {key}: {e}", exc_info=True)
            return False, None, f"Validation error for {key}"

    # ── Feedback helpers ──────────────────────────────────────────────────────

    def show_success_feedback(self):
        """Show success feedback with animation."""
        try:
            self.status_label.setText("✓ Settings saved successfully!")
            self.status_label.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.GREEN};
                    font-size: {self._ty.SIZE_SM}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    padding: {self._sp.PAD_SM}px;
                    background: {self._c.BG_HOVER};
                    border-radius: {self._sp.RADIUS_MD}px;
                }}
            """)
            self.save_btn.setText("✓ Saved!")
            QTimer.singleShot(1500, self.reset_styles)
            logger.info("Success feedback shown")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.show_success_feedback] Failed: {e}", exc_info=True)

    def show_error_feedback(self, error_msg):
        """Show error feedback."""
        try:
            self.status_label.setText(f"✗ {error_msg}")
            self.status_label.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.RED};
                    font-size: {self._ty.SIZE_SM}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    padding: {self._sp.PAD_SM}px;
                    background: {self._c.BG_HOVER};
                    border-radius: {self._sp.RADIUS_MD}px;
                }}
            """)
            self.save_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.RED};
                    color: white;
                    border: none;
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    min-width: 150px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.RED_BRIGHT};
                }}
            """)
            QTimer.singleShot(2000, self.reset_styles)
            logger.warning(f"Error feedback shown: {error_msg}")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.show_error_feedback] Failed: {e}", exc_info=True)

    def reset_styles(self):
        """Reset all styles to normal."""
        try:
            self.status_label.setText("")
            self.save_btn.setText("💾 Save Settings")
            self.save_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BLUE};
                    color: white;
                    border: none;
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    min-width: 150px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BLUE_DARK};
                }}
                QPushButton:disabled {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_DISABLED};
                }}
            """)
        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.reset_styles] Failed: {e}", exc_info=True)

    # ── Save logic ────────────────────────────────────────────────────────────

    def save(self):
        """Save settings with validation and background thread."""
        try:
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

            for key, (widget, typ) in self.vars.items():
                try:
                    if widget is None:
                        logger.warning(f"Widget for {key} is None")
                        continue

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

                    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                        data_to_save[key] = widget.value()
                    else:
                        is_valid, value, error = self.validate_field(key, text, typ)
                        if is_valid:
                            data_to_save[key] = value
                        else:
                            validation_errors.append(error or f"Invalid value for {key}")
                            if isinstance(widget, QLineEdit):
                                widget.setStyleSheet(f"""
                                    QLineEdit {{
                                        background: {self._c.BG_INPUT};
                                        color: {self._c.TEXT_MAIN};
                                        border: 1px solid {self._c.RED};
                                        border-radius: {self._sp.RADIUS_MD}px;
                                        padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                                        min-height: {self._sp.INPUT_HEIGHT}px;
                                        font-size: {self._ty.SIZE_BODY}pt;
                                    }}
                                """)

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

            # Ensure exchange is captured
            if "exchange" not in data_to_save and self.exchange_combo is not None:
                data_to_save["exchange"] = self.exchange_combo.currentData()

            # Ensure derivative is captured
            if "derivative" not in data_to_save and self.derivative_combo is not None:
                data_to_save["derivative"] = self.derivative_combo.currentData()

            # Ensure sideway is captured
            if "sideway_zone_trade" not in data_to_save and self.sideway_check is not None:
                data_to_save["sideway_zone_trade"] = self.sideway_check.isChecked()

            # Derive lot_size from OptionUtils — never from user input.
            # This ensures SEBI-regulated values are always used regardless of what
            # was previously stored in the database.
            try:
                deriv = data_to_save.get("derivative") or (
                    self.derivative_combo.currentData() if self.derivative_combo else None
                )
                if deriv:
                    data_to_save["lot_size"] = OptionUtils.get_lot_size(
                        deriv, fallback=data_to_save.get("lot_size", 0)
                    )
            except Exception as _e:
                logger.warning(f"[save] Could not derive lot_size from OptionUtils: {_e}")

            threading.Thread(
                target=self._threaded_save,
                args=(data_to_save,),
                daemon=True,
                name="DailyTradeSave"
            ).start()

            logger.info(f"Save operation started with {len(data_to_save)} fields")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.save] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Save failed: {e}")
            self._save_in_progress = False
            self.operation_finished.emit()
            self.save_btn.setEnabled(True)

    def _threaded_save(self, data_to_save: Dict[str, Any]):
        """Threaded save operation."""
        try:
            if self.daily_setting is None:
                raise ValueError("Daily setting object is None")

            for key, value in data_to_save.items():
                try:
                    if safe_hasattr(self.daily_setting, key):
                        safe_setattr(self.daily_setting, key, value)
                    else:
                        logger.warning(f"Setting {key} not found in daily_setting")
                except Exception as e:
                    logger.error(f"Failed to set {key}={value}: {e}", exc_info=True)

            success = False
            if safe_hasattr(self.daily_setting, 'save'):
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
        """Handle save completion."""
        try:
            if success:
                self.show_success_feedback()
                self.save_btn.setEnabled(True)

                # Notify any connected slot (e.g. TradingGUI._on_daily_settings_saved)
                self.settings_saved.emit()

                if self.app is not None and safe_hasattr(self.app, "refresh_settings_live"):
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
        """Handle error signal."""
        try:
            logger.error(f"Error signal received: {error_msg}")
            self.show_error_feedback(error_msg)
            self.save_btn.setEnabled(True)
            self._save_in_progress = False
        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI._on_error] Failed: {e}", exc_info=True)

    def _on_operation_started(self):
        pass

    def _on_operation_finished(self):
        pass

    # Rule 8: Cleanup
    def cleanup(self):
        """Clean up resources before closing."""
        try:
            logger.info("[DailyTradeSettingGUI] Starting cleanup")

            if safe_hasattr(self, '_save_timer') and self._save_timer is not None:
                try:
                    if self._save_timer.isActive():
                        self._save_timer.stop()
                except Exception as e:
                    logger.warning(f"Error stopping timer: {e}")

            self.daily_setting = None
            self.app = None
            self.vars.clear()
            self.entries.clear()
            self.exchange_combo = None
            self.derivative_combo = None
            self.expiry_badge = None
            self.sideway_check = None
            self.status_label = None
            self.save_btn = None
            self.tabs = None

            logger.info("[DailyTradeSettingGUI] Cleanup completed")

        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup."""
        try:
            if self._save_in_progress:
                logger.warning("Closing while save in progress")
            self.cleanup()
            event.accept()
        except Exception as e:
            logger.error(f"[DailyTradeSettingGUI.closeEvent] Failed: {e}", exc_info=True)
            event.accept()