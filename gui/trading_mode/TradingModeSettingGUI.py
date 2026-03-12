"""
TradingModeSettingGUI.py
========================
PyQt5 GUI for trading mode settings with support for new features.
MODERN MINIMALIST DESIGN - Matches DailyTradeSettingGUI, BrokerageSettingGUI, etc.
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

import logging.handlers

from PyQt5.QtCore import Qt, QTimer
from gui.dialog_base import ThemedDialog, ThemedMixin, ModernCard, make_separator, make_scrollbar_ss, create_section_header, create_modern_button, apply_tab_style, build_title_bar
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QPushButton, QComboBox, QDoubleSpinBox, QSpinBox,
                             QCheckBox, QLabel, QMessageBox,
                             QTabWidget, QFrame, QScrollArea, QWidget, QLineEdit)

from Utils.safe_getattr import safe_getattr
# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager
from gui.trading_mode.TradingModeSetting import TradingMode, TradingModeSetting
from license.license_manager import license_manager
from gui.popups.upgrade_popup import UpgradePopup

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

class TradingModeSettingGUI(ThemedDialog):
    def __init__(self, parent=None, trading_mode_setting=None, app=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent, title="TRADING MODE", icon="TM", size=(860, 700))

            # Rule 13.2: Connect to theme and density signals

            self.trading_mode_setting = trading_mode_setting or TradingModeSetting()
            self.app = app

            # Rule 6: Input validation
            if trading_mode_setting is None:
                logger.warning("TradingModeSettingGUI initialized with None trading_mode_setting, using default")

            self.setModal(True)
            self.setMinimumSize(850, 750)
            self.resize(850, 750)

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

            # Tabs with consistent styling
            self.tabs = self._create_tabs()
            content_layout.addWidget(self.tabs)

            # Status + save row (matches DailyTradeSettingGUI layout)
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

            self.apply_btn = self._create_modern_button("Apply", primary=False, icon="✅")
            self.apply_btn.clicked.connect(self._apply_settings)
            status_save_layout.addWidget(self.apply_btn)

            self.save_btn = self._create_modern_button("Save Settings", primary=True, icon="💾")
            self.save_btn.clicked.connect(self._save_settings)
            status_save_layout.addWidget(self.save_btn)

            content_layout.addLayout(status_save_layout)

            main_layout.addWidget(content)
            root.addWidget(self.main_card)

            # Apply theme initially
            self.apply_theme()

            self._load_settings()
            logger.info("TradingModeSettingGUI initialized")

        except Exception as e:
            logger.critical(f"[TradingModeSettingGUI.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _create_title_bar(self):
        """Build new-design title bar: monogram badge + CAPS title + ghost buttons."""
        return build_title_bar(
            self,
            title="TRADING MODE",
            icon="TM",
            on_close=self.reject,
        )

    def _create_tabs(self):
        """Create tabs with consistent styling matching other dialogs."""
        tabs = QTabWidget()

        tabs.setStyleSheet(f"""
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

        # Only Mode and Info tabs here.
        # Risk, MTF and Signal settings are managed exclusively in
        # Daily Trade Settings (DailyTradeSettingGUI) to avoid duplication.
        tabs.addTab(self._build_mode_tab(), "🎮 Mode")
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
                    min-width: 140px;
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

        # Note: MTF / Risk / Signal widgets removed — those tabs were merged
        # into DailyTradeSettingGUI to have a single authoritative settings place.
        self.save_btn = None
        self.apply_btn = None
        self.status_label = None
        self._save_in_progress = False
        self.main_card = None

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the dialog.
        Called on theme change, density change, and initial render.
        """
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

            # Update tabs
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

            # Update button styles
            self._update_button_styles()

            # Update safety warning if visible
            self._update_safety_warning()

            # Update UI state
            self._update_ui_state()

            logger.debug("[TradingModeSettingGUI.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI.apply_theme] Failed: {e}", exc_info=True)

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
                    min-width: 140px;
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

        # Apply button
        if self.apply_btn:
            self.apply_btn.setStyleSheet(f"""
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

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
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
            error_label.setStyleSheet(f"color: {self._c.RED_BRIGHT}; padding: {self._sp.PAD_XL}px; font-size: {self._ty.SIZE_MD}pt;")
            layout.addWidget(error_label)

            close_btn = self._create_modern_button("Close", primary=False)
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn, 0, Qt.AlignCenter)

            root.addWidget(main_card)

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._create_error_dialog] Failed: {e}", exc_info=True)

    # ── Mode Tab (Original) ───────────────────────────────────────────────────
    def _build_mode_tab(self):
        """Build the mode selection tab with modern card layout"""
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

            # Mode Selection Card
            mode_card = ModernCard()
            mode_layout = QVBoxLayout(mode_card)
            mode_layout.setSpacing(self._sp.GAP_MD)

            mode_header = QLabel("🎮 Trading Mode")
            mode_header.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            mode_layout.addWidget(mode_header)

            self.mode_combo = QComboBox()
            self.mode_combo.addItem("🖥️ Simulation (Paper Trading)", TradingMode.PAPER)
            self.mode_combo.addItem("💰 Live Trading", TradingMode.LIVE)
            self.mode_combo.addItem("📊 Backtest", TradingMode.BACKTEST)
            self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
            self.mode_combo.setStyleSheet(self._get_combobox_style())
            mode_layout.addWidget(self.mode_combo)

            mode_desc = QLabel(
                "• Simulation: Test strategies with virtual money\n"
                "• Live: Real trading with actual funds (requires safety checks)\n"
                "• Backtest: Run strategy on historical data"
            )
            mode_desc.setWordWrap(True)
            mode_desc.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            mode_layout.addWidget(mode_desc)

            # Safety warning
            self.safety_warning = ModernCard()
            self.safety_warning.setVisible(False)
            warning_layout = QHBoxLayout(self.safety_warning)
            warning_layout.setContentsMargins(self._sp.PAD_SM, self._sp.PAD_SM,
                                             self._sp.PAD_SM, self._sp.PAD_SM)

            warning_icon = QLabel("⚠️")
            warning_icon.setFont(QFont(self._ty.FONT_UI, self._ty.SIZE_LG))
            warning_layout.addWidget(warning_icon)

            self.safety_warning_label = QLabel("⚠️ LIVE MODE - Real money will be used!")
            self.safety_warning_label.setWordWrap(True)
            warning_layout.addWidget(self.safety_warning_label, 1)

            mode_layout.addWidget(self.safety_warning)

            layout.addWidget(mode_card)

            # Safety Settings Card
            safety_card = ModernCard()
            safety_layout = QVBoxLayout(safety_card)
            safety_layout.setSpacing(self._sp.GAP_MD)

            safety_header = QLabel("🛡️ Safety Settings")
            safety_header.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            safety_layout.addWidget(safety_header)

            self.allow_live_check = QCheckBox("✅ Enable live trading (off by default for safety)")
            self.allow_live_check.setToolTip("Must be checked to allow any live trades")
            self.allow_live_check.stateChanged.connect(self._update_ui_state)
            self.allow_live_check.setStyleSheet(self._get_checkbox_style())
            safety_layout.addWidget(self.allow_live_check)

            allow_desc = QLabel(
                "Safety switch for live trading. Must be explicitly enabled "
                "to prevent accidental real-money trades."
            )
            allow_desc.setWordWrap(True)
            allow_desc.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt; padding-left: {self._sp.PAD_XL}px;")
            safety_layout.addWidget(allow_desc)

            self.confirm_live_check = QCheckBox("⚠️ Confirm each live trade before execution")
            self.confirm_live_check.setChecked(True)
            self.confirm_live_check.setStyleSheet(self._get_checkbox_style())
            safety_layout.addWidget(self.confirm_live_check)

            confirm_desc = QLabel(
                "When enabled, you'll be prompted to approve each trade before it's sent to the exchange. "
                "Recommended for beginners and when testing new strategies."
            )
            confirm_desc.setWordWrap(True)
            confirm_desc.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt; padding-left: {self._sp.PAD_XL}px;")
            safety_layout.addWidget(confirm_desc)

            layout.addWidget(safety_card)

            # Simulation Settings Card
            self.sim_card = ModernCard()
            sim_layout = QVBoxLayout(self.sim_card)
            sim_layout.setSpacing(self._sp.GAP_MD)

            sim_header = QLabel("📊 Simulation Settings")
            sim_header.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            sim_layout.addWidget(sim_header)

            sim_form = QFormLayout()
            sim_form.setSpacing(self._sp.GAP_MD)
            sim_form.setLabelAlignment(Qt.AlignRight)

            # Paper balance
            self.paper_balance_spin = QDoubleSpinBox()
            self.paper_balance_spin.setRange(1000, 10000000)
            self.paper_balance_spin.setSingleStep(10000)
            self.paper_balance_spin.setPrefix("₹ ")
            self.paper_balance_spin.setValue(100000)
            self.paper_balance_spin.setStyleSheet(self._get_spinbox_style())
            sim_form.addRow("Initial Balance:", self.paper_balance_spin)

            balance_desc = QLabel(
                "Starting virtual capital for paper trading. Used to simulate position sizing "
                "and track performance metrics."
            )
            balance_desc.setWordWrap(True)
            balance_desc.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")

            # Slippage
            self.slippage_check = QCheckBox("📉 Simulate slippage")
            self.slippage_check.setStyleSheet(self._get_checkbox_style())
            sim_form.addRow("", self.slippage_check)

            self.slippage_spin = QDoubleSpinBox()
            self.slippage_spin.setRange(0, 1)
            self.slippage_spin.setSingleStep(0.01)
            self.slippage_spin.setSuffix(" %")
            self.slippage_spin.setValue(0.05)
            self.slippage_spin.setStyleSheet(self._get_spinbox_style())
            sim_form.addRow("Slippage:", self.slippage_spin)

            slippage_desc = QLabel(
                "Simulates the difference between expected and actual fill price. "
                "0.05% = 5 paise per ₹100. Helps make backtests more realistic."
            )
            slippage_desc.setWordWrap(True)
            slippage_desc.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt; padding-left: {self._sp.PAD_XL}px;")

            # Delay
            self.delay_check = QCheckBox("⏱️ Simulate order delay")
            self.delay_check.setStyleSheet(self._get_checkbox_style())
            sim_form.addRow("", self.delay_check)

            self.delay_spin = QSpinBox()
            self.delay_spin.setRange(0, 5000)
            self.delay_spin.setSingleStep(100)
            self.delay_spin.setSuffix(" ms")
            self.delay_spin.setValue(500)
            self.delay_spin.setStyleSheet(self._get_spinbox_style())
            sim_form.addRow("Delay:", self.delay_spin)

            delay_desc = QLabel(
                "Simulates network latency and exchange processing time. "
                "Higher values = more realistic but slower execution."
            )
            delay_desc.setWordWrap(True)
            delay_desc.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt; padding-left: {self._sp.PAD_XL}px;")

            sim_layout.addLayout(sim_form)
            sim_layout.addWidget(balance_desc)
            sim_layout.addWidget(slippage_desc)
            sim_layout.addWidget(delay_desc)

            layout.addWidget(self.sim_card)
            layout.addStretch()

            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._build_mode_tab] Failed: {e}", exc_info=True)
            return self._create_error_scroll(f"Error building mode tab: {e}")

    def _get_combobox_style(self):
        """Get consistent combobox styling."""
        return f"""
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
        """

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

    def _get_checkbox_style(self):
        """Get consistent checkbox styling."""
        return f"""
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
            QCheckBox::indicator:hover {{
                border-color: {self._c.BORDER_FOCUS};
            }}
        """

    def _get_lineedit_style(self):
        """Get consistent line edit styling."""
        return f"""
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
        """

    def _update_safety_warning(self):
        """Update safety warning styles based on current state"""
        if not self.safety_warning or not hasattr(self, 'safety_warning_label'):
            return

        if self.safety_warning.isVisible():
            self.safety_warning.setStyleSheet(f"""
                QFrame#modernCard {{
                    background: {self._c.BG_ROW_B};
                    border: 1px solid {self._c.RED};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px;
                }}
            """)
            self.safety_warning_label.setStyleSheet(f"color: {self._c.RED}; font-weight: {self._ty.WEIGHT_BOLD};")

    # ── FEATURE 1: Risk Management Tab ───────────────────────────────────────
    def _build_risk_tab(self):
        """Build risk management tab with modern card layout"""
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
            self.max_loss_spin = QDoubleSpinBox()
            self.max_loss_spin.setRange(-1000000, 0)
            self.max_loss_spin.setSingleStep(100)
            self.max_loss_spin.setPrefix("₹ ")
            self.max_loss_spin.setToolTip("Maximum daily loss before bot stops trading (negative value)")
            self.max_loss_spin.setValue(-5000)
            self.max_loss_spin.setStyleSheet(self._get_spinbox_style())
            risk_form.addRow("Max Daily Loss:", self.max_loss_spin)

            loss_hint = QLabel("Trading stops when daily P&L reaches this level (negative number)")
            loss_hint.setWordWrap(True)
            loss_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            risk_form.addRow("", loss_hint)

            # Max Trades Per Day
            self.max_trades_spin = QSpinBox()
            self.max_trades_spin.setRange(1, 100)
            self.max_trades_spin.setSuffix(" trades")
            self.max_trades_spin.setToolTip("Maximum number of trades per day")
            self.max_trades_spin.setValue(10)
            self.max_trades_spin.setStyleSheet(self._get_spinbox_style())
            risk_form.addRow("Max Trades/Day:", self.max_trades_spin)

            trades_hint = QLabel("Hard limit on number of entries per day")
            trades_hint.setWordWrap(True)
            trades_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            risk_form.addRow("", trades_hint)

            # Daily Profit Target
            self.daily_target_spin = QDoubleSpinBox()
            self.daily_target_spin.setRange(0, 10000000)
            self.daily_target_spin.setSingleStep(100)
            self.daily_target_spin.setPrefix("₹ ")
            self.daily_target_spin.setToolTip("Daily profit target for progress tracking")
            self.daily_target_spin.setValue(5000)
            self.daily_target_spin.setStyleSheet(self._get_spinbox_style())
            risk_form.addRow("Daily Target:", self.daily_target_spin)

            target_hint = QLabel("Profit target for the day (for display purposes only)")
            target_hint.setWordWrap(True)
            target_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            risk_form.addRow("", target_hint)

            risk_layout.addLayout(risk_form)
            layout.addWidget(risk_card)

            # Info Card
            info_card = self._create_info_card(
                "📘 About Risk Management",
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
        """Build Multi-Timeframe Filter settings tab with modern card layout"""
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

            self.mtf_check = QCheckBox("Enable Multi-Timeframe Filter")
            self.mtf_check.setToolTip("When enabled, requires agreement across multiple timeframes before entry")
            self.mtf_check.setStyleSheet(self._get_checkbox_style())
            enable_layout.addWidget(self.mtf_check)

            enable_hint = QLabel("Requires at least 2 of 3 timeframes to agree with trade direction")
            enable_hint.setWordWrap(True)
            enable_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt; padding-left: {self._sp.PAD_XL}px;")
            enable_layout.addWidget(enable_hint)

            layout.addWidget(enable_card)

            # Configuration Card
            config_card = ModernCard()
            config_layout = QVBoxLayout(config_card)
            config_layout.setSpacing(self._sp.GAP_MD)

            config_header = QLabel("⚙️ Timeframe Configuration")
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
            self.mtf_timeframes_edit = QLineEdit()
            self.mtf_timeframes_edit.setPlaceholderText("1,5,15")
            self.mtf_timeframes_edit.setToolTip("Comma-separated list of timeframes in minutes")
            self.mtf_timeframes_edit.setStyleSheet(self._get_lineedit_style())
            config_form.addRow("Timeframes:", self.mtf_timeframes_edit)

            tf_hint = QLabel("Example: 1,5,15 for 1min, 5min, and 15min")
            tf_hint.setWordWrap(True)
            tf_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            config_form.addRow("", tf_hint)

            # Fast EMA
            self.mtf_ema_fast_spin = QSpinBox()
            self.mtf_ema_fast_spin.setRange(1, 50)
            self.mtf_ema_fast_spin.setSuffix(" periods")
            self.mtf_ema_fast_spin.setToolTip("Fast EMA period for trend detection")
            self.mtf_ema_fast_spin.setStyleSheet(self._get_spinbox_style())
            config_form.addRow("Fast EMA:", self.mtf_ema_fast_spin)

            # Slow EMA
            self.mtf_ema_slow_spin = QSpinBox()
            self.mtf_ema_slow_spin.setRange(5, 200)
            self.mtf_ema_slow_spin.setSuffix(" periods")
            self.mtf_ema_slow_spin.setToolTip("Slow EMA period for trend detection")
            self.mtf_ema_slow_spin.setStyleSheet(self._get_spinbox_style())
            config_form.addRow("Slow EMA:", self.mtf_ema_slow_spin)

            # Agreement Required
            self.mtf_agreement_spin = QSpinBox()
            self.mtf_agreement_spin.setRange(1, 3)
            self.mtf_agreement_spin.setSuffix(" timeframes")
            self.mtf_agreement_spin.setToolTip("Number of timeframes that must agree")
            self.mtf_agreement_spin.setStyleSheet(self._get_spinbox_style())
            config_form.addRow("Agreement Required:", self.mtf_agreement_spin)

            agree_hint = QLabel("How many timeframes must agree before allowing entry")
            agree_hint.setWordWrap(True)
            agree_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            config_form.addRow("", agree_hint)

            config_layout.addLayout(config_form)
            layout.addWidget(config_card)

            # Info Card
            info_card = self._create_info_card(
                "📘 How Multi-Timeframe Filter Works",
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
        """Build signal confidence settings tab with modern card layout"""
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

            # Confidence Card
            conf_card = ModernCard()
            conf_layout = QVBoxLayout(conf_card)
            conf_layout.setSpacing(self._sp.GAP_MD)

            conf_header = QLabel("🎯 Signal Confidence")
            conf_header.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_MAIN};
                    font-size: {self._ty.SIZE_MD}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            conf_layout.addWidget(conf_header)

            conf_form = QFormLayout()
            conf_form.setSpacing(self._sp.GAP_MD)
            conf_form.setLabelAlignment(Qt.AlignRight)

            # Min Confidence
            self.min_confidence_spin = QDoubleSpinBox()
            self.min_confidence_spin.setRange(0.0, 1.0)
            self.min_confidence_spin.setSingleStep(0.05)
            self.min_confidence_spin.setDecimals(2)
            self.min_confidence_spin.setToolTip("Minimum confidence threshold for signals (0.0-1.0)")
            self.min_confidence_spin.setStyleSheet(self._get_spinbox_style())
            conf_form.addRow("Min Confidence:", self.min_confidence_spin)

            conf_hint = QLabel("Signals below this confidence are suppressed (0.0-1.0)")
            conf_hint.setWordWrap(True)
            conf_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            conf_form.addRow("", conf_hint)

            conf_layout.addLayout(conf_form)
            layout.addWidget(conf_card)

            # Info Card
            info_card = self._create_info_card(
                "📘 About Signal Confidence",
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
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

            container = QWidget()
            container.setStyleSheet("background: transparent;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(self._sp.GAP_MD)

            infos = [
                (
                    "🖥️ Simulation Mode",
                    "Paper trading environment where no real money is at risk.\n\n"
                    "• Uses virtual balance defined in settings.\n"
                    "• Perfect for testing strategies and learning.\n"
                    "• Simulates real market conditions with slippage/delay options.\n"
                    "• All order executions are virtual - no actual trades placed."
                ),
                (
                    "💰 Live Mode",
                    "Real trading with actual capital - USE WITH EXTREME CAUTION.\n\n"
                    "• Requires explicit 'Enable live trading' checkbox.\n"
                    "• Real orders sent to exchange via broker API.\n"
                    "• Real P&L - profits and losses are actual.\n"
                    "• Recommended only after extensive backtesting and paper trading.\n"
                    "• Start with small capital and gradually increase."
                ),
                (
                    "📊 Backtest Mode",
                    "Run strategy on historical data to evaluate performance.\n\n"
                    "• No live orders - purely analytical.\n"
                    "• Uses historical price data for simulation.\n"
                    "• Generate performance metrics and equity curves.\n"
                    "• Ideal for optimizing strategy parameters.\n"
                    "• Results depend on data quality and assumptions."
                ),
                (
                    "🛡️ Safety Features",
                    "Multiple layers of protection against accidental losses.\n\n"
                    "• Live Mode requires explicit enable checkbox.\n"
                    "• Per-trade confirmation option for extra safety.\n"
                    "• Cannot switch to Live without confirming.\n"
                    "• Clear visual warnings when Live mode is selected.\n"
                    "• Settings are saved with safety checks."
                ),
                (
                    "📈 Simulation Realism",
                    "Options to make paper trading more realistic:\n\n"
                    "• Slippage: Simulates price movement between order and fill.\n"
                    "• Delay: Adds artificial latency like real exchanges.\n"
                    "• Adjust these to match real-world conditions.\n"
                    "• Helps prepare for live trading challenges.\n"
                    "• More realistic simulations = better strategy validation."
                ),
                (
                    "⚠️ Risk Management",
                    "Daily loss limits and trade counts to protect capital.\n\n"
                    "• **Max Daily Loss**: Stop trading when daily P&L hits this level.\n"
                    "• **Max Trades/Day**: Hard limit on number of entries.\n"
                    "• **Daily Target**: Visual progress indicator for profit goals."
                ),
                (
                    "📈 Multi-Timeframe Filter",
                    "Confirms trend direction across multiple timeframes.\n\n"
                    "• Uses EMA 9/21 crossovers on multiple timeframes.\n"
                    "• Requires configurable number of timeframes to agree.\n"
                    "• Reduces false entries during conflicting trends."
                ),
                (
                    "🎯 Signal Confidence",
                    "Weighted voting system for signal groups.\n\n"
                    "• Each rule can have a weight (default 1.0).\n"
                    "• Confidence = passed_weight / total_weight.\n"
                    "• Signals below min_confidence are suppressed."
                ),
                (
                    "📁 Settings Storage",
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
        """Create an information card with themed styling"""
        card = ModernCard()
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(self._sp.GAP_SM)

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

        card_layout.addWidget(title_lbl)
        card_layout.addWidget(body_lbl)
        return card

    def _create_error_scroll(self, error_msg):
        """Create a scroll area with error message"""
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
                mode_value = self.trading_mode_setting.mode if self.trading_mode_setting.mode else TradingMode.PAPER
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
        """Handle mode change — gate LIVE trading behind an active license."""
        try:
            selected = self.mode_combo.currentData() if self.mode_combo else None
            if selected == TradingMode.LIVE and self._is_free_user():
                # Revert combo silently back to PAPER before showing popup
                self.mode_combo.blockSignals(True)
                for i in range(self.mode_combo.count()):
                    if self.mode_combo.itemData(i) == TradingMode.PAPER:
                        self.mode_combo.setCurrentIndex(i)
                        break
                self.mode_combo.blockSignals(False)

                # Determine context: trial expired vs never had any license
                from license.license_manager import PLAN_TRIAL
                from db.crud import kv
                try:
                    plan_was = kv.get("license:plan", "") or ""
                    trial_expired = (plan_was == "" and
                                     bool(kv.get("license:email", "")))
                except Exception:
                    trial_expired = False

                popup = UpgradePopup(self, trial_expired=trial_expired)
                popup.exec_()
                return  # UI state already updated for PAPER by the revert above

            self._update_ui_state()
        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._on_mode_changed] Failed: {e}", exc_info=True)

    def _is_free_user(self) -> bool:
        """
        Return True when the user does NOT have a paid license.
        Delegates to license_manager.is_live_trading_allowed() — the single
        source of truth — so both this gate and the start-app gate stay in sync.
        """
        try:
            return not license_manager.is_live_trading_allowed()
        except Exception as e:
            logger.warning(f"[TradingModeSettingGUI._is_free_user] {e}")
            return True  # Fail-safe: treat as free user

    def _update_ui_state(self):
        """Update UI based on selected mode"""
        try:
            if self.mode_combo is None:
                logger.warning("_update_ui_state called with None mode_combo")
                return

            is_live = self.mode_combo.currentData() == TradingMode.LIVE

            if self.safety_warning is not None:
                self.safety_warning.setVisible(is_live)
                if is_live and self.allow_live_check is not None and not self.allow_live_check.isChecked():
                    self.safety_warning_label.setText("⚠️ Check 'Enable live trading' to save LIVE mode")
                else:
                    self.safety_warning_label.setText("⚠️ LIVE MODE - Real money will be used!")
                self._update_safety_warning()

            if self.sim_card is not None:
                self.sim_card.setEnabled(not is_live)

            # Button enable logic
            buttons_enabled = True

            if is_live:
                if self.allow_live_check is not None and not self.allow_live_check.isChecked():
                    buttons_enabled = False

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
            self.status_label.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.BLUE};
                    font-size: {self._ty.SIZE_SM}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    padding: {self._sp.PAD_SM}px;
                    background: {self._c.BG_HOVER};
                    border-radius: {self._sp.RADIUS_MD}px;
                }}
            """)

            if self._validate_and_save():
                self.status_label.setText("✓ Settings applied successfully!")
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
                logger.info("Settings applied successfully")
            else:
                self.status_label.setText("✗ Failed to apply settings")
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

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._apply_settings] Failed: {e}", exc_info=True)
            self.status_label.setText(f"✗ Error: {e}")
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
            self.status_label.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.BLUE};
                    font-size: {self._ty.SIZE_SM}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    padding: {self._sp.PAD_SM}px;
                    background: {self._c.BG_HOVER};
                    border-radius: {self._sp.RADIUS_MD}px;
                }}
            """)

            if self._validate_and_save():
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
                logger.info("Settings saved successfully, closing dialog")
                QTimer.singleShot(1000, self.accept)
            else:
                self.status_label.setText("✗ Failed to save settings")
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
                self._save_in_progress = False

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI._save_settings] Failed: {e}", exc_info=True)
            self.status_label.setText(f"✗ Error: {e}")
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
            if current_data == TradingMode.LIVE:
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
                    self.trading_mode_setting.mode = current_data  # already TradingMode enum from combo userData
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid mode value: {e}")
                self.trading_mode_setting.mode = TradingMode.PAPER

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

            # Save to file
            success = self.trading_mode_setting.save()
            if not success:
                logger.error("Failed to save settings to file")
                QMessageBox.critical(self, "Error", "Failed to save settings to file")
                return False

            if self.app is not None:
                try:
                    self.app.refresh_settings_live()
                    logger.info(
                        "[TradingModeSettingGUI] Trading app refreshed after mode change "
                        f"(mode={safe_getattr(self.trading_mode_setting, 'mode', 'N/A')})"
                    )
                except AttributeError:
                    logger.warning(
                        "[TradingModeSettingGUI] trading_app.refresh_settings_live() not found — "
                        "executor paper_mode may be stale until restart"
                    )
                except Exception as e:
                    logger.error(
                        f"[TradingModeSettingGUI] Failed to refresh trading app: {e}",
                        exc_info=True
                    )

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
            self.sim_card = None
            self.paper_balance_spin = None
            self.slippage_check = None
            self.slippage_spin = None
            self.delay_check = None
            self.delay_spin = None
            self.save_btn = None
            self.apply_btn = None
            self.status_label = None
            self.main_card = None

            logger.info("[TradingModeSettingGUI] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradingModeSettingGUI.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup"""
        try:
            if self._save_in_progress:
                logger.warning("Closing while save in progress")
            self.cleanup()
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[TradingModeSettingGUI.closeEvent] Failed: {e}", exc_info=True)
            super().closeEvent(event)