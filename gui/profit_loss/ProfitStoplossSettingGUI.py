# PYQT: Modern minimalist design matching DailyTradeSettingGUI and BrokerageSettingGUI
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                             QPushButton, QVBoxLayout, QHBoxLayout,
                             QLabel, QWidget, QTabWidget, QFrame,
                             QScrollArea, QComboBox, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QLocale
from PyQt5.QtGui import QFont, QDoubleValidator
from BaseEnums import STOP, TRAILING, logger
import threading

from Utils.safe_getattr import safe_getattr, safe_hasattr, safe_setattr
from gui.profit_loss import ProfitStoplossSetting

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager


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


class ModernCard(QFrame):
    """Modern card widget with consistent styling."""

    def __init__(self, parent=None, elevated=False):
        super().__init__(parent)
        self.setObjectName("modernCard")
        self.elevated = elevated
        self._apply_style()

    def _apply_style(self):
        c = theme_manager.palette
        sp = theme_manager.spacing

        base_style = f"""
            QFrame#modernCard {{
                background: {c.BG_PANEL};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                padding: {sp.PAD_LG}px;
            }}
        """

        if self.elevated:
            base_style += f"""
                QFrame#modernCard {{
                    border: 1px solid {c.BORDER_FOCUS};
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                               stop:0 {c.BG_PANEL}, stop:1 {c.BG_HOVER});
                }}
            """

        self.setStyleSheet(base_style)


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


class ProfitStoplossSettingGUI(QDialog, ThemedMixin):
    save_completed = pyqtSignal(bool, str)
    # Emitted after a successful save so TradingGUI can refresh dependent widgets
    settings_saved = pyqtSignal()

    # Rule 3: Additional signals
    error_occurred = pyqtSignal(str)
    operation_started = pyqtSignal()
    operation_finished = pyqtSignal()

    VALIDATION_RANGES = {
        "tp_percentage":            (0.1,  100.0, "Take Profit"),
        "stoploss_percentage":      (0.1,   50.0, "Stoploss"),
        "trailing_activation_pct":  (0.1,  100.0, "Activation Threshold"),
        "trailing_sl_at_activation":(-50.0, 100.0, "SL at Activation"),
        "max_profit":               (0.1,  200.0, "Max Profit"),
        "profit_step":              (0.1,   20.0, "Step Size"),
    }

    def __init__(self, parent, profit_stoploss_setting: ProfitStoplossSetting, app=None):
        # Rule 2: Safe defaults
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.profit_stoploss_setting = profit_stoploss_setting
            self.app = app
            self.setWindowTitle("Profit & Stoploss Settings")
            self.setModal(True)
            self.setMinimumSize(800, 700)
            self.resize(800, 700)

            # Set window flags for modern look
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

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

            # Header
            header = ModernHeader("Profit & Stoploss Configuration")
            content_layout.addWidget(header)

            # Tabs with consistent styling
            self.tabs = self._create_tabs()
            content_layout.addWidget(self.tabs)

            # Status label
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
            content_layout.addWidget(self.status_label)

            # Button row
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(self._sp.GAP_MD)

            self.save_btn = self._create_modern_button(" Save Settings", primary=True, icon="💾")
            self.save_btn.clicked.connect(self.save)

            self.cancel_btn = self._create_modern_button("✕ Cancel", primary=False)
            self.cancel_btn.clicked.connect(self.reject)

            btn_layout.addStretch()
            btn_layout.addWidget(self.save_btn)
            btn_layout.addWidget(self.cancel_btn)

            content_layout.addLayout(btn_layout)

            main_layout.addWidget(content)
            root.addWidget(self.main_card)

            self.save_completed.connect(self.on_save_completed)

            # Connect internal signals
            self._connect_signals()

            # Apply theme initially
            self.apply_theme()

            # Initialize UI
            self._on_profit_type_change()

            logger.info("ProfitStoplossSettingGUI initialized")

        except Exception as e:
            logger.critical(f"[ProfitStoplossSettingGUI.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _create_title_bar(self):
        """Create custom title bar with close button."""
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet(f"background: {self._c.BG_PANEL}; border-top-left-radius: {self._sp.RADIUS_LG}px; border-top-right-radius: {self._sp.RADIUS_LG}px;")

        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(self._sp.PAD_MD, 0, self._sp.PAD_MD, 0)

        title = QLabel("💹 Profit & Stoploss Settings")
        title.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_LG}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
        """)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self._c.BG_HOVER};
                color: {self._c.TEXT_DIM};
                border: none;
                border-radius: {self._sp.RADIUS_SM}px;
                font-size: {self._ty.SIZE_MD}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {self._c.RED};
                color: white;
            }}
        """)
        close_btn.clicked.connect(self.reject)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(close_btn)

        return title_bar

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

        tabs.addTab(self._build_settings_tab(), "⚙️ Settings")
        tabs.addTab(self._build_info_tab(), "ℹ️ Information")

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
        self.main_card = None

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the dialog.
        Called on theme change, density change, and initial render.
        """
        try:
            # Update main card style
            if hasattr(self, 'main_card'):
                self.main_card._apply_style()

            # Update title bar
            if hasattr(self, 'title_bar'):
                self.title_bar.setStyleSheet(f"background: {self._c.BG_PANEL};")

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

            # Update all entries based on enabled state
            self._on_profit_type_change()

            logger.debug("[ProfitStoplossSettingGUI.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[ProfitStoplossSettingGUI.apply_theme] Failed: {e}", exc_info=True)

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

        # Cancel button
        if self.cancel_btn:
            self.cancel_btn.setStyleSheet(f"""
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
                }}
            """)

    def _create_warning_banner(self) -> QFrame:
        """Create a warning banner for the stop-loss note"""
        c = self._c
        sp = self._sp
        ty = self._ty

        banner = ModernCard()
        banner.setStyleSheet(f"""
            QFrame#modernCard {{
                background: {c.BG_ROW_B};
                border: 1px solid {c.YELLOW};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px;
            }}
        """)
        warning_layout = QHBoxLayout(banner)
        warning_layout.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM)

        warning_icon = QLabel("⚠️")
        warning_icon.setFont(QFont(ty.FONT_UI, ty.SIZE_LG))
        warning_layout.addWidget(warning_icon)

        warning_text = QLabel(
            "<b>Note:</b> Stop-loss is applied BELOW entry price for long positions "
            "(CALL/PUT buyers). Enter the percentage as a positive number."
        )
        warning_text.setWordWrap(True)
        warning_text.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_SM}pt;")
        warning_layout.addWidget(warning_text, 1)

        return banner

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

            # Set window flags for modern look
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

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
            logger.error(f"[ProfitStoplossSettingGUI._create_error_dialog] Failed: {e}", exc_info=True)

    # ── Settings Tab ──────────────────────────────────────────────────────────
    def _build_settings_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._sp.GAP_LG)

        validator = QDoubleValidator()
        validator.setLocale(QLocale.c())

        # Warning Banner
        warning_banner = self._create_warning_banner()
        layout.addWidget(warning_banner)

        # ── Profit Mode Card ─────────────────────────────────────────────────
        mode_card = ModernCard()
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setSpacing(self._sp.GAP_MD)

        mode_header = QLabel("💰 Profit Mode")
        mode_header.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_MD}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
        """)
        mode_layout.addWidget(mode_header)

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
        self.profit_type_combo.setStyleSheet(self._get_combobox_style())
        mode_layout.addWidget(self.profit_type_combo)

        mode_hint = QLabel("STOP exits at a fixed target. TRAILING locks in gains dynamically.")
        mode_hint.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
        mode_layout.addWidget(mode_hint)

        layout.addWidget(mode_card)

        # ── Threshold Values Card ────────────────────────────────────────────
        values_card = ModernCard()
        values_layout = QVBoxLayout(values_card)
        values_layout.setSpacing(self._sp.GAP_MD)

        values_header = QLabel("📊 Threshold Values")
        values_header.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_MD}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
        """)
        values_layout.addWidget(values_header)

        values_form = QFormLayout()
        values_form.setSpacing(self._sp.GAP_MD)
        values_form.setLabelAlignment(Qt.AlignRight)
        values_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.vars = {}
        self.entries = {}

        # (label, key, icon, tooltip)
        fields = [
            ("Take Profit (%)",            "tp_percentage",            "💰", "Exit the trade when profit reaches this % (0.1–100)."),
            ("Stoploss (%)",               "stoploss_percentage",      "🛑", "Initial stop-loss % below entry. Enter as positive number (0.1–50)."),
            ("Activation Threshold (%)",   "trailing_activation_pct",  "🎯",
             "TRAILING only — price must rise this much above entry before trailing engages.\n"
             "Example: 10 means SL does not start moving until price is +10% above entry."),
            ("SL at Activation (%)",       "trailing_sl_at_activation","🔒",
             "TRAILING only — when activation threshold is first hit, SL immediately jumps to\n"
             "this % above entry (positive = profit lock). Example: 5 means SL moves to +5% of entry."),
            ("Max Profit (%)",             "max_profit",               "🏆", "TRAILING only — trailing steps stop once SL reaches this % above entry."),
            ("Step Size (%)",              "profit_step",              "➕",
             "TRAILING only — after activation, every time price rises another step_size % above\n"
             "the last step, both SL and TP are raised by step_size %."),
        ]

        for label, key, icon, tooltip in fields:
            edit = QLineEdit()
            edit.setValidator(validator)
            edit.setToolTip(tooltip)
            edit.setStyleSheet(self._get_lineedit_style())

            # BUG #1 FIX: Always show stoploss as positive
            if key == "stoploss_percentage":
                val = abs(safe_getattr(self.profit_stoploss_setting, key, 0))
            else:
                val = safe_getattr(self.profit_stoploss_setting, key, 0)
            edit.setText(f"{val:.1f}")

            values_form.addRow(f"{icon} {label}:", edit)
            self.vars[key] = edit
            self.entries[key] = edit

        values_layout.addLayout(values_form)
        layout.addWidget(values_card)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

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

    # ── Information Tab ───────────────────────────────────────────────────────
    def _build_info_tab(self):
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
                "💰 Profit Mode",
                "Controls how the exit strategy works once a position is open.\n\n"
                "• STOP (Fixed Target): the position is closed as soon as unrealised profit hits "
                "the Take Profit percentage. Simple and predictable.\n"
                "• TRAILING (Dynamic): the exit level rises with the price, locking in gains as "
                "the trade moves in your favour. More complex but can capture larger moves."
            ),
            (
                "💰 Take Profit (%)",
                "The profit percentage at which an open position is automatically closed.\n\n"
                "• Used in both STOP and TRAILING modes.\n"
                "• In STOP mode this is the only exit target.\n"
                "• In TRAILING mode the trade may close earlier if the trailing stop is hit.\n"
                "• Valid range: 0.1 – 100."
            ),
            (
                "🛑 Stoploss (%)",
                "Initial stop-loss percentage BELOW entry price.\n\n"
                "• Enter as a positive number (e.g., 7 = stop at entry × 0.93).\n"
                "• In TRAILING mode this is only active before the activation threshold is reached.\n"
                "  Once the threshold is crossed, SL jumps to 'SL at Activation' and never goes back.\n"
                "• Valid range: 0.1 – 50."
            ),
            (
                "🎯 Activation Threshold (%) — TRAILING only",
                "How much the price must rise above entry before the trailing mechanism first engages.\n\n"
                "Example with entry = 200, activation = 10%:\n"
                "  • SL stays at -7% of entry (= 186) until price reaches 220 (+10%).\n"
                "  • When price first hits 220, trailing activates immediately.\n\n"
                "• Keeps the initial stop-loss in place during early price discovery.\n"
                "• Valid range: 0.1 – 100."
            ),
            (
                "🔒 SL at Activation (%) — TRAILING only",
                "The SL level (as % above/below entry) that the stop jumps to the moment activation fires.\n\n"
                "Example with entry = 200, SL at activation = 5%:\n"
                "  • When price first hits the activation threshold, SL immediately moves to 200 × 1.05 = 210.\n"
                "  • This locks in a 5% profit buffer — the trade cannot close below breakeven+5%.\n\n"
                "• Positive value = SL above entry (profit locked in).\n"
                "• Negative value = SL still below entry but tighter than initial.\n"
                "• Range: -50 – 100."
            ),
            (
                "🏆 Max Profit (%) — TRAILING only",
                "Trailing steps stop once the SL has reached this % above entry.\n\n"
                "• Acts as the top of the staircase — SL will not be raised further beyond this point.\n"
                "• Must be strictly greater than the Activation Threshold.\n"
                "• Valid range: 0.1 – 200."
            ),
            (
                "➕ Step Size (%) — TRAILING only",
                "After activation, every time the price makes a new high that is step_size% above the last step,\n"
                "BOTH the SL and TP are raised by step_size% of entry.\n\n"
                "Example with entry = 200, activation = 10%, SL-at-activation = 5%, step = 2%:\n"
                "  • Price hits 220 (+10%) → SL jumps to 210 (+5%), TP advances by 2%\n"
                "  • Price hits 224 (+12%) → SL moves to 214 (+7%), TP advances by 2%\n"
                "  • Price hits 228 (+14%) → SL moves to 218 (+9%), TP advances by 2%\n"
                "  • All SL prices anchored to entry (200), never to the current peak.\n"
                "  • SL never moves down, only up.\n\n"
                "• Smaller step = tighter trailing, more profit locked in.\n"
                "• Valid range: 0.1 – 20."
            ),
            (
                "📁 Storage",
                "Profit & stoploss settings are saved locally to the app database.\n\n"
                "Changes take effect immediately for any new trades opened after saving."
            ),
        ]

        for title, body in infos:
            card = self._create_info_card(title, body)
            layout.addWidget(card)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

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

    # ── Profit type toggle ────────────────────────────────────────────────────
    def _on_profit_type_change(self):
        selected = self.profit_type_combo.currentData()
        trailing_keys = {"trailing_activation_pct", "trailing_sl_at_activation", "max_profit", "profit_step"}

        for key, edit in self.entries.items():
            if key in trailing_keys:
                edit.setEnabled(selected == TRAILING)
                if selected == TRAILING:
                    edit.setStyleSheet(self._get_lineedit_style())
                else:
                    edit.setStyleSheet(f"""
                        QLineEdit {{
                            background: {self._c.BG_PANEL};
                            color: {self._c.TEXT_DISABLED};
                            border: 1px solid {self._c.BORDER_DIM};
                            border-radius: {self._sp.RADIUS_MD}px;
                            padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                            min-height: {self._sp.INPUT_HEIGHT}px;
                            font-size: {self._ty.SIZE_BODY}pt;
                        }}
                    """)

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

            # Cross-field validations for trailing settings
            if key == "max_profit":
                activation = float(self.entries.get("trailing_activation_pct", type('', (), {'text': lambda s: '0'})()).text() or "0")
                if val <= activation:
                    return False, None, "Max Profit must be greater than Activation Threshold"

            return True, val, None
        except ValueError:
            return False, None, f"{self.VALIDATION_RANGES[key][2]} must be a valid number"

    # ── Feedback helpers ──────────────────────────────────────────────────────
    def show_success_feedback(self):
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
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self._c.GREEN};
                color: white;
                border: none;
                border-radius: {self._sp.RADIUS_MD}px;
                padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                font-size: {self._ty.SIZE_BODY}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
                min-width: 150px;
                min-height: 36px;
            }}
        """)
        for entry in self.entries.values():
            if entry.isEnabled():
                entry.setStyleSheet(f"""
                    QLineEdit {{
                        background: {self._c.BG_INPUT};
                        color: {self._c.TEXT_MAIN};
                        border: 1px solid {self._c.GREEN};
                        border-radius: {self._sp.RADIUS_MD}px;
                        padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                        min-height: {self._sp.INPUT_HEIGHT}px;
                        font-size: {self._ty.SIZE_BODY}pt;
                    }}
                """)
        QTimer.singleShot(1500, self.reset_styles)

    def show_error_feedback(self, error_msg):
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

    def reset_styles(self):
        for key, entry in self.entries.items():
            if entry.isEnabled():
                entry.setStyleSheet(self._get_lineedit_style())
            else:
                entry.setStyleSheet(f"""
                    QLineEdit {{
                        background: {self._c.BG_PANEL};
                        color: {self._c.TEXT_DISABLED};
                        border: 1px solid {self._c.BORDER_DIM};
                        border-radius: {self._sp.RADIUS_MD}px;
                        padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                        min-height: {self._sp.INPUT_HEIGHT}px;
                        font-size: {self._ty.SIZE_BODY}pt;
                    }}
                """)
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
        """)
        self.status_label.setText("")

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
            required_fields.extend([
                "trailing_activation_pct", "trailing_sl_at_activation",
                "max_profit", "profit_step",
            ])

        for key in required_fields:
            edit = self.entries[key]
            is_valid, value, error = self.validate_field(key, edit.text().strip())
            if is_valid:
                data_to_save[key] = value
            else:
                validation_errors.append(error)
                edit.setStyleSheet(f"""
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
                    safe_setattr(self.profit_stoploss_setting, key, value)
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
            # Notify any connected slot (e.g. TradingGUI._on_pnl_settings_saved)
            self.settings_saved.emit()
            # Refresh app if available
            if self.app is not None and safe_hasattr(self.app, "refresh_settings_live"):
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
            if self._save_in_progress:
                logger.warning("Closing while save in progress")
            self.cleanup()
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[ProfitStoplossSettingGUI.closeEvent] Failed: {e}", exc_info=True)
            super().closeEvent(event)