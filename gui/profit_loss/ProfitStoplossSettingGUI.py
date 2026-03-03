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


class ProfitStoplossSettingGUI(QDialog, ThemedMixin):
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

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.profit_stoploss_setting = profit_stoploss_setting
            self.app = app
            self.setWindowTitle("Profit & Stoploss Settings")
            self.setModal(True)
            self.setMinimumSize(750, 650)
            self.resize(750, 650)

            # Root layout
            root = QVBoxLayout(self)
            # Margins and spacing will be set in apply_theme

            # Header
            header = QLabel("💹 Profit & Stoploss Configuration")
            header.setObjectName("header")
            header.setAlignment(Qt.AlignCenter)
            root.addWidget(header)

            # BUG #1 Warning Banner
            warning_banner = self._create_warning_banner()
            root.addWidget(warning_banner)

            # Tabs
            self.tabs = QTabWidget()
            root.addWidget(self.tabs)
            self.tabs.addTab(self._build_settings_tab(), "⚙️ Settings")
            self.tabs.addTab(self._build_info_tab(), "ℹ️ Information")

            # Status label (always visible)
            self.status_label = QLabel("")
            self.status_label.setAlignment(Qt.AlignCenter)
            self.status_label.setObjectName("status")
            root.addWidget(self.status_label)

            # Save + Cancel buttons
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(self._sp.GAP_MD)

            self.save_btn = QPushButton("💾 Save Settings")
            self.save_btn.clicked.connect(self.save)

            self.cancel_btn = QPushButton("❌ Cancel")
            self.cancel_btn.clicked.connect(self.reject)

            btn_layout.addWidget(self.save_btn)
            btn_layout.addWidget(self.cancel_btn)
            root.addLayout(btn_layout)

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
                header.setStyleSheet(
                    f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_XL}pt; font-weight: {ty.WEIGHT_BOLD}; padding: {sp.PAD_XS}px;")

            # Update status label
            if self.status_label:
                self.status_label.setStyleSheet(
                    f"color: {c.GREEN}; font-size: {ty.SIZE_XS}pt; font-weight: {ty.WEIGHT_BOLD};")

            # Update button styles
            self._update_button_styles()

            # Update all entries based on enabled state
            self._on_profit_type_change()

            logger.debug("[ProfitStoplossSettingGUI.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[ProfitStoplossSettingGUI.apply_theme] Failed: {e}", exc_info=True)

    def _get_stylesheet(self) -> str:
        """Generate stylesheet with current theme tokens"""
        c = self._c
        ty = self._ty
        sp = self._sp

        return f"""
            QDialog {{ background:{c.BG_PANEL}; color:{c.TEXT_MAIN}; }}
            QLabel  {{ color:{c.TEXT_DIM}; font-size:{ty.SIZE_SM}pt; }}
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
            QGroupBox {{
                color:{c.TEXT_MAIN}; border:{sp.SEPARATOR}px solid {c.BORDER}; border-radius:{sp.RADIUS_MD}px;
                margin-top:{sp.PAD_LG}px; padding-top:{sp.PAD_MD}px; font-weight:{ty.WEIGHT_BOLD};
                font-size:{ty.SIZE_BODY}pt;
            }}
            QGroupBox::title {{ subcontrol-origin:margin; left:{sp.PAD_MD}px; padding:0 {sp.PAD_SM}px; }}
            QLineEdit, QComboBox {{
                background:{c.BG_HOVER}; color:{c.TEXT_MAIN}; border:{sp.SEPARATOR}px solid {c.BORDER};
                border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px; font-size:{ty.SIZE_BODY}pt;
            }}
            QLineEdit:focus, QComboBox:focus {{ border:{sp.SEPARATOR}px solid {c.BORDER_FOCUS}; }}
            QLineEdit:disabled {{ background:{c.BG_PANEL}; color:{c.TEXT_DISABLED}; }}
            QScrollArea {{ border:none; background:transparent; }}
            QFrame#infoCard {{
                background:{c.BG_HOVER};
                border:{sp.SEPARATOR}px solid {c.BORDER};
                border-radius:{sp.RADIUS_MD}px;
            }}
            QLabel#warning {{
                color: {c.YELLOW};
                font-size: {ty.SIZE_XS}pt;
            }}
        """

    def _update_button_styles(self):
        """Update button styles with theme tokens"""
        c = self._c
        sp = self._sp
        ty = self._ty

        # Save button
        if self.save_btn:
            self.save_btn.setStyleSheet(f"""
                QPushButton {{
                    background:{c.GREEN}; color:{c.TEXT_INVERSE}; border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                    font-weight:{ty.WEIGHT_BOLD}; font-size:{ty.SIZE_BODY}pt;
                }}
                QPushButton:hover    {{ background:{c.GREEN_BRIGHT}; }}
                QPushButton:pressed  {{ background:{c.GREEN}; }}
                QPushButton:disabled {{ background:{c.BG_HOVER}; color:{c.TEXT_DISABLED}; }}
            """)

        # Cancel button
        if self.cancel_btn:
            self.cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    background:{c.RED}; color:{c.TEXT_INVERSE}; border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                    font-weight:{ty.WEIGHT_BOLD}; font-size:{ty.SIZE_BODY}pt;
                }}
                QPushButton:hover {{ background:{c.RED_BRIGHT}; }}
            """)

    def _create_warning_banner(self) -> QFrame:
        """Create a warning banner for the stop-loss note"""
        c = self._c
        sp = self._sp
        ty = self._ty

        banner = QFrame()
        banner.setStyleSheet(f"""
            QFrame {{
                background: {c.BG_ROW_B};
                border: {sp.SEPARATOR}px solid {c.YELLOW};
                border-radius: {sp.RADIUS_MD}px;
            }}
        """)
        warning_layout = QHBoxLayout(banner)
        warning_layout.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM)

        warning_icon = QLabel("⚠️")
        warning_icon.setFont(QFont(ty.FONT_UI, ty.SIZE_MD))
        warning_layout.addWidget(warning_icon)

        warning_text = QLabel(
            "<b>Note:</b> Stop-loss is applied BELOW entry price for long positions "
            "(CALL/PUT buyers). Enter the percentage as a positive number."
        )
        warning_text.setWordWrap(True)
        warning_text.setObjectName("warning")
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
            c = self._c
            ty = self._ty
            sp = self._sp

            super().__init__(parent)
            self.setWindowTitle("Profit & Stoploss Settings - ERROR")
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
            logger.error(f"[ProfitStoplossSettingGUI._create_error_dialog] Failed: {e}", exc_info=True)

    # ── Settings Tab ──────────────────────────────────────────────────────────
    def _build_settings_tab(self):
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
        layout.setSpacing(sp.GAP_MD)

        validator = QDoubleValidator()
        validator.setLocale(QLocale.c())

        # ── Profit Type group ─────────────────────────────────────────────────
        main_group = QGroupBox("Profit Mode")
        main_layout = QFormLayout()
        main_layout.setSpacing(sp.GAP_XS)
        main_layout.setVerticalSpacing(sp.GAP_XS)
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
        profit_type_hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")

        main_layout.addRow("💰 Profit Type:", self.profit_type_combo)
        main_layout.addRow("", profit_type_hint)
        main_group.setLayout(main_layout)
        layout.addWidget(main_group)

        # ── Threshold Values group ────────────────────────────────────────────
        values_group = QGroupBox("Threshold Values")
        values_layout = QFormLayout()
        values_layout.setSpacing(sp.GAP_XS)
        values_layout.setVerticalSpacing(sp.GAP_XS)
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
            hint_lbl.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")

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
            card = self._create_info_card(title, body)
            layout.addWidget(card)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

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

    # ── Profit type toggle ────────────────────────────────────────────────────
    def _on_profit_type_change(self):
        selected = self.profit_type_combo.currentData()
        trailing_keys = {"trailing_first_profit", "max_profit", "profit_step", "loss_step"}

        c = self._c
        sp = self._sp

        for key, edit in self.entries.items():
            if key in trailing_keys:
                edit.setEnabled(selected == TRAILING)
                if selected == TRAILING:
                    edit.setStyleSheet(f"""
                        QLineEdit {{
                            background:{c.BG_HOVER}; color:{c.TEXT_MAIN}; border:{sp.SEPARATOR}px solid {c.BORDER};
                            border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                        }}
                        QLineEdit:focus {{ border:{sp.SEPARATOR}px solid {c.BORDER_FOCUS}; }}
                    """)
                else:
                    edit.setStyleSheet(f"""
                        QLineEdit {{
                            background:{c.BG_PANEL}; color:{c.TEXT_DISABLED}; border:{sp.SEPARATOR}px solid {c.BORDER};
                            border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
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
        c = self._c
        sp = self._sp

        self.status_label.setText("✓ Settings saved successfully!")
        self.status_label.setStyleSheet(
            f"color:{c.GREEN}; font-size:{self._ty.SIZE_XS}pt; font-weight:{self._ty.WEIGHT_BOLD};")
        self.save_btn.setText("✓ Saved!")
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background:{c.GREEN_BRIGHT}; color:{c.TEXT_INVERSE}; border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                font-weight:{self._ty.WEIGHT_BOLD}; font-size:{self._ty.SIZE_BODY}pt;
            }}
        """)
        for entry in self.entries.values():
            if entry.isEnabled():
                entry.setStyleSheet(f"""
                    QLineEdit {{
                        background:{c.BG_HOVER}; color:{c.TEXT_MAIN}; border:{sp.SEPARATOR}px solid {c.GREEN};
                        border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                    }}
                """)
        QTimer.singleShot(1500, self.reset_styles)

    def show_error_feedback(self, error_msg):
        c = self._c
        sp = self._sp

        self.status_label.setText(f"✗ {error_msg}")
        self.status_label.setStyleSheet(
            f"color:{c.RED}; font-size:{self._ty.SIZE_XS}pt; font-weight:{self._ty.WEIGHT_BOLD};")
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background:{c.RED}; color:{c.TEXT_INVERSE}; border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                font-weight:{self._ty.WEIGHT_BOLD}; font-size:{self._ty.SIZE_BODY}pt;
            }}
        """)
        QTimer.singleShot(2000, self.reset_styles)

    def reset_styles(self):
        c = self._c
        sp = self._sp

        for key, entry in self.entries.items():
            if entry.isEnabled():
                entry.setStyleSheet(f"""
                    QLineEdit {{
                        background:{c.BG_HOVER}; color:{c.TEXT_MAIN}; border:{sp.SEPARATOR}px solid {c.BORDER};
                        border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                    }}
                    QLineEdit:focus {{ border:{sp.SEPARATOR}px solid {c.BORDER_FOCUS}; }}
                """)
            else:
                entry.setStyleSheet(f"""
                    QLineEdit {{
                        background:{c.BG_PANEL}; color:{c.TEXT_DISABLED}; border:{sp.SEPARATOR}px solid {c.BORDER};
                        border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                    }}
                """)
        self.save_btn.setText("💾 Save Settings")
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background:{c.GREEN}; color:{c.TEXT_INVERSE}; border-radius:{sp.RADIUS_SM}px; padding:{sp.PAD_SM}px;
                font-weight:{self._ty.WEIGHT_BOLD}; font-size:{self._ty.SIZE_BODY}pt;
            }}
            QPushButton:hover {{ background:{c.GREEN_BRIGHT}; }}
        """)

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
                edit.setStyleSheet(f"""
                    QLineEdit {{
                        background:{self._c.BG_ROW_B}; color:{self._c.TEXT_MAIN}; border:{self._sp.SEPARATOR}px solid {self._c.RED};
                        border-radius:{self._sp.RADIUS_SM}px; padding:{self._sp.PAD_SM}px;
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