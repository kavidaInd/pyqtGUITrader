"""
Utils/BrokerLoginPopup.py
=========================
Generic multi-broker PyQt5 login dialog with modern minimalist design.
Matches the theme of DailyTradeSettingGUI.py and BrokerageSettingGUI.py

Auth method variants handled:
    oauth    — URL display + auth-code/URL paste  (Fyers, Zerodha, Upstox, FlatTrade)
    totp     — No URL; TOTP entry + optional MPIN (Angel One, Shoonya)
    static   — No URL; plain token paste          (Dhan)
    password — No URL; no entry; auto-login btn   (Alice Blue)

Usage:
    from Utils.BrokerLoginPopup import BrokerLoginPopup

    popup = BrokerLoginPopup(
        parent=main_window,
        brokerage_setting=settings,
        reason="Session expired",
        notifier=telegram_notifier,
    )
    if popup.exec_() == QDialog.Accepted:
        token = popup.result_token
"""

import logging
from typing import Optional
from urllib.parse import urlparse, parse_qs
import re
import webbrowser
from datetime import datetime, timedelta

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QLineEdit,
    QPushButton, QProgressBar, QApplication, QWidget, QTabWidget,
    QFrame, QScrollArea, QCheckBox, QGroupBox, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont

from Utils.safe_getattr import safe_getattr, safe_hasattr
from gui.brokerage_settings.BrokerLoginHelper import BrokerLoginHelper

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

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


class StepCard(QFrame):
    """Step card with number indicator."""

    def __init__(self, step_number: int, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("stepCard")
        self.step_number = step_number
        self.title = title
        self._apply_style()

    def _apply_style(self):
        c = theme_manager.palette
        sp = theme_manager.spacing

        self.setStyleSheet(f"""
            QFrame#stepCard {{
                background: {c.BG_HOVER};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                padding: {sp.PAD_LG}px;
            }}
        """)


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


# ── Worker thread ─────────────────────────────────────────────────────────────

class TokenExchangeWorker(QThread):
    finished = pyqtSignal(object, str)  # (token | None, error_msg)
    progress = pyqtSignal(int, str)  # (percent, status_text)
    error_occurred = pyqtSignal(str)

    def __init__(self, helper: BrokerLoginHelper, code: str, extra: dict = None):
        self._safe_defaults_init()
        try:
            super().__init__()
            self.helper = helper
            self.code = code
            self.extra = extra or {}
        except Exception as e:
            logger.error(f"[TokenExchangeWorker.__init__] {e}", exc_info=True)
            super().__init__()
            self.helper = helper
            self.code = code
            self.extra = extra or {}

    def _safe_defaults_init(self):
        self.helper = None
        self.code = None
        self.extra = {}
        self._is_stopping = False

    def run(self):
        try:
            if not self.helper:
                self.finished.emit(None, "Login helper is not initialized")
                return
            self.progress.emit(30, "Authenticating…")
            token = self.helper.exchange_code_for_token(self.code or "", **self.extra)
            self.progress.emit(100, "Done")
            if token:
                self.finished.emit(token, "")
            else:
                self.finished.emit(None, "Authentication failed — please check your credentials and try again.")
        except Exception as e:
            logger.error(f"[TokenExchangeWorker.run] {e}", exc_info=True)
            self.finished.emit(None, str(e))

    def stop(self):
        self._is_stopping = True


# ── Main popup ────────────────────────────────────────────────────────────────

class BrokerLoginPopup(QDialog, ThemedMixin):
    login_completed = pyqtSignal(object)  # access token
    error_occurred = pyqtSignal(str)
    operation_started = pyqtSignal()
    operation_finished = pyqtSignal()
    token_refreshed = pyqtSignal(str, str)  # message, status

    def __init__(self, parent, brokerage_setting, reason: str = None, notifier=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.brokerage_setting = brokerage_setting
            self._reason = reason
            self.notifier = notifier
            self.result_token: Optional[str] = None

            # Build broker-aware helper
            broker_type = safe_getattr(brokerage_setting, 'broker_type', 'fyers') or 'fyers'
            self._helper = BrokerLoginHelper.for_broker(
                broker_type=broker_type,
                client_id=safe_getattr(brokerage_setting, 'client_id', '') or '',
                secret_key=safe_getattr(brokerage_setting, 'secret_key', '') or '',
                redirect_uri=safe_getattr(brokerage_setting, 'redirect_uri', '') or '',
            )

            broker_name = self._helper.broker_display_name
            self.setWindowTitle(
                f"{broker_name} — Re-authentication Required" if reason
                else f"{broker_name} — Login"
            )

            # Set window flags for modern look
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            self.setMinimumSize(800, 750 if reason else 700)
            self.resize(800, 750 if reason else 700)
            self.setModal(True)

            self._build_ui()
            self._connect_signals()
            self._init_login_url()

            # Apply theme initially
            self.apply_theme()

            logger.info(f"BrokerLoginPopup initialized for {broker_name} (auth: {self._helper.auth_method})")

        except Exception as e:
            logger.critical(f"[BrokerLoginPopup.__init__] {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        self.brokerage_setting = None
        self._reason = None
        self.notifier = None
        self.result_token = None
        self._helper = None
        self._exchange_in_progress = False
        self.token_worker = None
        # UI widgets
        self.tabs = None
        self.url_text = None
        self.code_entry = None
        self.password_entry = None
        self.mobile_entry = None
        self.ucc_entry = None
        self.progress_bar = None
        self.status_label = None
        self.clear_btn = None
        self.login_btn = None
        self.cancel_btn = None
        self.notify_check = None
        self.telegram_status_label = None
        self.login_url = None
        self.main_card = None

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the popup.
        Called on theme change, density change, and initial render.
        """
        try:
            # Update main card style
            if hasattr(self, 'main_card'):
                self.main_card._apply_style()

            # Update step cards
            self._update_step_card_styles()

            # Update button styles
            self._update_button_styles()

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

            # Update progress bar
            if self.progress_bar:
                self.progress_bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: 1px solid {self._c.BORDER};
                        border-radius: {self._sp.RADIUS_MD}px;
                        text-align: center;
                        color: {self._c.TEXT_MAIN};
                        background: {self._c.BG_HOVER};
                        min-height: {self._sp.PROGRESS_MD}px;
                        max-height: {self._sp.PROGRESS_MD}px;
                    }}
                    QProgressBar::chunk {{
                        background: {self._c.BLUE};
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

            # Update telegram status
            self._update_telegram_status()

            logger.debug("[BrokerLoginPopup.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[BrokerLoginPopup.apply_theme] Failed: {e}", exc_info=True)

    def _update_step_card_styles(self):
        """Update step card styles."""
        c = self._c
        sp = self._sp

        # Find all step cards and update their style
        for card in self.findChildren(QFrame, "stepCard"):
            card.setStyleSheet(f"""
                QFrame#stepCard {{
                    background: {c.BG_HOVER};
                    border: 1px solid {c.BORDER};
                    border-radius: {sp.RADIUS_LG}px;
                    padding: {sp.PAD_LG}px;
                }}
            """)

    def _update_button_styles(self):
        """Update button styles with theme tokens"""
        c = self._c
        sp = self._sp
        ty = self._ty

        # Login button
        if self.login_btn:
            self.login_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c.BLUE};
                    color: white;
                    border: none;
                    border-radius: {sp.RADIUS_MD}px;
                    padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                    font-size: {ty.SIZE_BODY}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                    min-width: 160px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {c.BLUE_DARK};
                }}
                QPushButton:disabled {{
                    background: {c.BG_HOVER};
                    color: {c.TEXT_DISABLED};
                }}
            """)

        # Cancel button
        if self.cancel_btn:
            self.cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c.RED};
                    color: white;
                    border: none;
                    border-radius: {sp.RADIUS_MD}px;
                    padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                    font-size: {ty.SIZE_BODY}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                    min-width: 120px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {c.RED_BRIGHT};
                }}
            """)

        # Clear button
        if self.clear_btn:
            self.clear_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c.BG_HOVER};
                    color: {c.TEXT_MAIN};
                    border: 1px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                    padding: {sp.PAD_SM}px {sp.PAD_LG}px;
                    font-size: {ty.SIZE_BODY}pt;
                    min-width: 100px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {c.BORDER};
                }}
            """)

        # Secondary buttons (Copy, Open Browser)
        for btn_name in ["copy_btn", "open_btn"]:
            btn = getattr(self, btn_name, None)
            if btn:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {c.BG_HOVER};
                        color: {c.TEXT_MAIN};
                        border: 1px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                        padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                        font-size: {ty.SIZE_BODY}pt;
                        min-width: 100px;
                        min-height: 32px;
                    }}
                    QPushButton:hover {{
                        background: {c.BORDER};
                        border-color: {c.BORDER_FOCUS};
                    }}
                """)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        sp = self._sp

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
        content_layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)
        content_layout.setSpacing(sp.GAP_LG)


        # Warning banner (token-expiry reason)
        if self._reason:
            banner = self._create_warning_banner()
            content_layout.addWidget(banner)

        # Tabs
        self.tabs = QTabWidget()
        content_layout.addWidget(self.tabs)
        self.tabs.addTab(self._build_login_tab(), "🔑 Login")
        self.tabs.addTab(self._build_notification_tab(), "📱 Notifications")
        self.tabs.addTab(self._build_info_tab(), "ℹ️ Information")

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {self._c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                text-align: center;
                color: {self._c.TEXT_MAIN};
                background: {self._c.BG_HOVER};
                min-height: {sp.PROGRESS_MD}px;
                max-height: {sp.PROGRESS_MD}px;
            }}
            QProgressBar::chunk {{
                background: {self._c.BLUE};
                border-radius: {sp.RADIUS_MD}px;
            }}
        """)
        content_layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_DIM};
                font-size: {self._ty.SIZE_SM}pt;
                padding: {sp.PAD_SM}px;
                background: {self._c.BG_HOVER};
                border-radius: {sp.RADIUS_MD}px;
            }}
        """)
        content_layout.addWidget(self.status_label)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(sp.GAP_MD)

        self.clear_btn = QPushButton("✖ Clear")
        self.clear_btn.clicked.connect(self._clear_entries)

        self.login_btn = QPushButton("🔒 Complete Login")
        self.login_btn.clicked.connect(self._start_exchange)

        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.login_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        content_layout.addLayout(btn_layout)

        main_layout.addWidget(content)
        root.addWidget(self.main_card)

        # Apply button styles after they're created
        self._update_button_styles()

    def _create_title_bar(self):
        """Create custom title bar with close button."""
        c  = self._c
        ty = self._ty
        sp = self._sp

        title_bar = QWidget()
        title_bar.setObjectName("dialogTitleBar")
        title_bar.setFixedHeight(46)
        title_bar.setStyleSheet(f"""
            QWidget#dialogTitleBar {{
                background: {c.BG_CARD};
                border-radius: {sp.RADIUS_LG}px {sp.RADIUS_LG}px 0 0;
            }}
        """)

        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(sp.PAD_LG, 0, sp.PAD_MD, 0)
        layout.setSpacing(8)

        # Blue accent bar on left
        accent = QFrame()
        accent.setFixedSize(3, 20)
        accent.setStyleSheet(f"background: {c.BLUE}; border-radius: 2px;")
        layout.addWidget(accent)

        broker_name = self._helper.broker_display_name if self._helper else "Broker"
        title = QLabel(f"🔐 {broker_name} Login")
        title.setStyleSheet(f"""
            QLabel {{
                color: {c.TEXT_BRIGHT};
                font-size: {ty.SIZE_LG}pt;
                font-weight: {ty.WEIGHT_BOLD};
                background: transparent;
                border: none;
            }}
        """)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Close")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {c.BG_HOVER};
                color: {c.TEXT_DIM};
                border: none;
                border-radius: {sp.RADIUS_SM}px;
                font-size: {ty.SIZE_MD}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {c.RED};
                color: white;
            }}
            QPushButton:pressed {{
                background: {c.RED_BRIGHT};
            }}
        """)
        close_btn.clicked.connect(self.reject)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(close_btn)

        self._drag_pos = None
        title_bar.mousePressEvent   = lambda e: setattr(self,'_drag_pos', e.globalPos()-self.frameGeometry().topLeft()) if e.button()==1 else None
        title_bar.mouseMoveEvent    = lambda e: self.move(e.globalPos()-self._drag_pos) if e.buttons()==1 and self._drag_pos else None
        title_bar.mouseReleaseEvent = lambda e: setattr(self,'_drag_pos',None)

        return title_bar

    def _create_warning_banner(self) -> QFrame:
        """Create a warning banner for token expiry reasons"""
        c = self._c
        sp = self._sp
        ty = self._ty

        banner = ModernCard()
        banner.setStyleSheet(f"""
            QFrame#modernCard {{
                background: {c.BG_ROW_B};
                border: 1px solid {c.RED};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_MD}px;
            }}
        """)
        bl = QHBoxLayout(banner)
        bl.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM)
        bl.setSpacing(sp.GAP_MD)

        icon_lbl = QLabel("⚠️")
        icon_lbl.setFont(QFont(ty.FONT_UI, ty.SIZE_LG))
        icon_lbl.setStyleSheet("background:transparent; border:none;")

        msg_lbl = QLabel(
            f"<b style='color:{c.RED};'>Session expired — re-login required</b><br>"
            f"<span style='color:{c.ORANGE}; font-size:{ty.SIZE_XS}pt;'>{self._reason}</span>"
        )
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("background:transparent; border:none;")
        msg_lbl.setTextFormat(Qt.RichText)

        bl.addWidget(icon_lbl, 0, Qt.AlignTop)
        bl.addWidget(msg_lbl, 1)
        return banner

    # ── Login tab (adapts to auth_method) ─────────────────────────────────────

    def _build_login_tab(self) -> QWidget:
        widget = QWidget()
        try:
            sp = self._sp
            c = self._c
            ty = self._ty

            layout = QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(sp.GAP_LG)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

            container = QWidget()
            container.setStyleSheet("background: transparent;")
            scroll_layout = QVBoxLayout(container)
            scroll_layout.setContentsMargins(sp.PAD_LG, sp.PAD_LG, sp.PAD_LG, sp.PAD_LG)
            scroll_layout.setSpacing(sp.GAP_LG)

            auth = self._helper.auth_method

            # ── Step 1 card ───────────────────────────────────────────────────
            step1_card = ModernCard()
            step1_layout = QVBoxLayout(step1_card)
            step1_layout.setSpacing(sp.GAP_MD)

            # Step header with number
            step1_header = QLabel("Step 1: Generate Login URL")
            step1_header.setStyleSheet(f"""
                QLabel {{
                    color: {c.BLUE};
                    font-size: {ty.SIZE_MD}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                }}
            """)
            step1_layout.addWidget(step1_header)

            step1_desc = QLabel(self._helper.step1_hint)
            step1_desc.setWordWrap(True)
            step1_desc.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt;")
            step1_layout.addWidget(step1_desc)

            if self._helper.has_login_url:
                # URL display with copy button
                url_row = QHBoxLayout()
                url_row.setSpacing(sp.GAP_SM)

                self.url_text = QTextEdit()
                self.url_text.setMaximumHeight(sp.BTN_HEIGHT_LG * 2)
                self.url_text.setReadOnly(True)
                self.url_text.setStyleSheet(f"""
                    QTextEdit {{
                        background: {c.BG_INPUT};
                        color: {c.TEXT_MAIN};
                        border: 1px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                        padding: {sp.PAD_SM}px;
                        font-family: {ty.FONT_MONO};
                        font-size: {ty.SIZE_XS}pt;
                    }}
                """)
                url_row.addWidget(self.url_text, 1)

                copy_btn = QPushButton("📋 Copy")
                copy_btn.setObjectName("copy_btn")
                copy_btn.setCursor(Qt.PointingHandCursor)
                copy_btn.setMaximumWidth(80)
                copy_btn.clicked.connect(self._copy_url)
                url_row.addWidget(copy_btn)

                step1_layout.addLayout(url_row)

                open_btn = QPushButton("🌐 Open in Browser")
                open_btn.setObjectName("open_btn")
                open_btn.setCursor(Qt.PointingHandCursor)
                open_btn.clicked.connect(self._open_url)
                step1_layout.addWidget(open_btn, 0, Qt.AlignRight)

            scroll_layout.addWidget(step1_card)

            # ── Step 2 card ───────────────────────────────────────────────────
            step2_card = ModernCard()
            step2_layout = QVBoxLayout(step2_card)
            step2_layout.setSpacing(sp.GAP_MD)

            step2_header = QLabel("Step 2: Complete Authentication")
            step2_header.setStyleSheet(f"""
                QLabel {{
                    color: {c.BLUE};
                    font-size: {ty.SIZE_MD}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                }}
            """)
            step2_layout.addWidget(step2_header)

            step2_desc = QLabel(self._helper.step2_hint)
            step2_desc.setWordWrap(True)
            step2_desc.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt;")
            step2_layout.addWidget(step2_desc)

            # Code / token entry (hidden for password-auth brokers)
            if auth != "password":
                code_label = QLabel(self._helper.code_entry_placeholder)
                code_label.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt;")
                step2_layout.addWidget(code_label)

                self.code_entry = QLineEdit()
                self.code_entry.setPlaceholderText("Paste code or redirect URL here")
                self.code_entry.setStyleSheet(self._get_lineedit_style())
                step2_layout.addWidget(self.code_entry)

            # Secondary password/MPIN field (totp brokers that need it)
            if self._helper.needs_password_field:
                pwd_label = QLabel(self._helper.password_field_label)
                pwd_label.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt;")
                self.password_entry = QLineEdit()
                self.password_entry.setPlaceholderText(self._helper.password_field_placeholder)
                self.password_entry.setEchoMode(QLineEdit.Password)
                self.password_entry.setStyleSheet(self._get_lineedit_style())
                step2_layout.addWidget(pwd_label)
                step2_layout.addWidget(self.password_entry)

            scroll_layout.addWidget(step2_card)
            scroll_layout.addStretch()

            scroll.setWidget(container)
            layout.addWidget(scroll)

        except Exception as e:
            logger.error(f"[BrokerLoginPopup._build_login_tab] {e}", exc_info=True)
            err = QLabel(f"Error building login tab: {e}")
            err.setStyleSheet(f"color:{self._c.RED};")
            err.setWordWrap(True)
            layout = QVBoxLayout(widget)
            layout.addWidget(err)

        return widget

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

    # ── Notifications tab ─────────────────────────────────────────────────────

    def _build_notification_tab(self) -> QWidget:
        widget = QWidget()
        try:
            sp = self._sp
            c = self._c
            ty = self._ty

            layout = QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

            container = QWidget()
            container.setStyleSheet("background: transparent;")
            scroll_layout = QVBoxLayout(container)
            scroll_layout.setContentsMargins(sp.PAD_LG, sp.PAD_LG, sp.PAD_LG, sp.PAD_LG)
            scroll_layout.setSpacing(sp.GAP_LG)

            # Notification settings card
            notify_card = ModernCard()
            notify_layout = QVBoxLayout(notify_card)
            notify_layout.setSpacing(sp.GAP_MD)

            notify_header = QLabel("📱 Notification Settings")
            notify_header.setStyleSheet(f"""
                QLabel {{
                    color: {c.TEXT_MAIN};
                    font-size: {ty.SIZE_MD}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                }}
            """)
            notify_layout.addWidget(notify_header)

            self.notify_check = QCheckBox("Send Telegram notification on token expiry")
            configured = False
            if self.brokerage_setting and safe_hasattr(self.brokerage_setting, 'is_telegram_configured'):
                configured = self.brokerage_setting.is_telegram_configured()
            self.notify_check.setChecked(configured)
            self.notify_check.setStyleSheet(f"""
                QCheckBox {{
                    color: {c.TEXT_MAIN};
                    font-size: {ty.SIZE_BODY}pt;
                    spacing: {sp.GAP_SM}px;
                }}
                QCheckBox::indicator {{
                    width: {sp.ICON_MD}px;
                    height: {sp.ICON_MD}px;
                    border: 2px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                }}
                QCheckBox::indicator:checked {{
                    background: {c.BLUE};
                    border-color: {c.BLUE};
                }}
            """)
            notify_layout.addWidget(self.notify_check)

            hint = QLabel(
                "When enabled, you'll receive a Telegram notification whenever "
                "your token expires and needs renewal."
            )
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
            notify_layout.addWidget(hint)

            scroll_layout.addWidget(notify_card)

            # Status card
            status_card = ModernCard()
            status_layout = QVBoxLayout(status_card)
            status_layout.setSpacing(sp.GAP_MD)

            status_header = QLabel("📊 Current Status")
            status_header.setStyleSheet(f"""
                QLabel {{
                    color: {c.TEXT_MAIN};
                    font-size: {ty.SIZE_MD}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                }}
            """)
            status_layout.addWidget(status_header)

            self.telegram_status_label = QLabel("")
            self.telegram_status_label.setWordWrap(True)
            status_layout.addWidget(self.telegram_status_label)

            scroll_layout.addWidget(status_card)

            # Info card
            info = self._make_info_card(
                "📘 About Token Expiry Notifications",
                f"• {self._helper.broker_display_name} tokens expire periodically\n"
                "• When enabled, you'll receive a Telegram alert when your token expires\n"
                "• Configure Telegram in Settings → Brokerage Settings\n"
                "• This helps you know when re-authentication is needed"
            )
            scroll_layout.addWidget(info)

            scroll_layout.addStretch()
            scroll.setWidget(container)
            layout.addWidget(scroll)

        except Exception as e:
            logger.error(f"[_build_notification_tab] {e}", exc_info=True)
        return widget

    def _update_telegram_status(self):
        try:
            c = self._c
            if not self.telegram_status_label:
                return
            if self.brokerage_setting and safe_hasattr(self.brokerage_setting, 'is_telegram_configured'):
                if self.brokerage_setting.is_telegram_configured():
                    self.telegram_status_label.setText("✅ Telegram notifications configured")
                    self.telegram_status_label.setStyleSheet(f"color:{c.GREEN};")
                else:
                    self.telegram_status_label.setText("⚠️ Telegram not configured")
                    self.telegram_status_label.setStyleSheet(f"color:{c.ORANGE};")
            else:
                self.telegram_status_label.setText("⚠️ Telegram settings not available")
                self.telegram_status_label.setStyleSheet(f"color:{c.ORANGE};")
        except Exception as e:
            logger.error(f"[_update_telegram_status] {e}", exc_info=True)

    # ── Info tab ──────────────────────────────────────────────────────────────

    def _build_info_tab(self) -> QScrollArea:
        try:
            sp = self._sp

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

            container = QWidget()
            container.setStyleSheet("background: transparent;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(sp.PAD_LG, sp.PAD_LG, sp.PAD_LG, sp.PAD_LG)
            layout.setSpacing(sp.GAP_MD)

            auth = self._helper.auth_method
            broker = self._helper.broker_display_name

            cards = [
                ("🔐 What is this dialog?",
                 f"{broker} requires authentication before the trading app can place orders. "
                 f"This dialog walks you through the authentication steps.\n\n"
                 f"Authentication method: {auth.upper()}"),

                (self._helper.step1_title, self._helper.step1_hint),
                (self._helper.step2_title, self._helper.step2_hint),

                ("🔑 What happens after I click 'Complete Login'?",
                 "Your credentials are used to obtain an access token in a background thread "
                 "(so the UI stays responsive). The token is stored in the database and used "
                 "for all subsequent API calls.\n\n"
                 "• If authentication fails, check your credentials and try again.\n"
                 "• Tokens typically expire at end-of-trading-day and must be renewed daily."),

                ("📱 Token Expiry Notifications",
                 "Enable Telegram notifications in the 'Notifications' tab to be alerted "
                 "when your token expires and re-authentication is needed."),

                ("⚠️ Common Issues",
                 self._common_issues_text()),

                ("📋 Credentials used",
                 f"This dialog uses the credentials configured in Brokerage Settings:\n\n"
                 f"• Client ID — identifies your app to {broker}\n"
                 f"• Secret Key — your API secret or password\n"
                 f"• Redirect URI — the OAuth callback URI (if applicable)\n\n"
                 "Go to Settings → Brokerage Settings if any credentials are missing or incorrect."),
            ]

            for title, body in cards:
                layout.addWidget(self._make_info_card(title, body))

            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[_build_info_tab] {e}", exc_info=True)
            scroll = QScrollArea()
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.addWidget(QLabel(f"Error building info tab: {e}"))
            scroll.setWidget(container)
            return scroll

    def _common_issues_text(self) -> str:
        c = self._c
        auth = self._helper.auth_method
        base = ("Wrong credentials — double-check your Client ID and Secret Key in "
                "Brokerage Settings if authentication fails.\n\n"
                "Token expired — most broker tokens expire at midnight. "
                "Re-run the login each morning before market open.\n\n")
        if auth == "oauth":
            return (base +
                    "Auth code expired — OAuth codes are valid for only ~60 seconds. "
                    "Restart from Step 1 if you see an 'invalid code' error.\n\n"
                    "Redirect URI mismatch — the URI in settings must exactly match "
                    "what is registered in the broker's developer portal.")
        if auth == "totp":
            return (base +
                    "Invalid TOTP — check that your device clock is synced (NTP).\n\n"
                    "Auto-TOTP not working — verify the TOTP secret (base32) stored "
                    "in the redirect_uri field is correct.")
        if auth == "session":
            return (base +
                    "Static IP required — enforces a static IP per SEBI rules. "
                    "Ensure you're on the whitelisted IP address.\n\n"
                    "Session token expired — session tokens are single-use. "
                    "Visit the login URL again to get a fresh token.")
        if auth == "password":
            return (base +
                    "Wrong YOB — Alice Blue uses Year of Birth as a 2FA answer. "
                    "Ensure the YOB stored in redirect_uri matches your registered value.")
        return base

    def _make_info_card(self, title: str, body: str) -> QFrame:
        c = self._c
        ty = self._ty
        sp = self._sp

        card = ModernCard()
        cl = QVBoxLayout(card)
        cl.setSpacing(sp.GAP_SM)

        t = QLabel(title)
        t.setStyleSheet(f"""
            QLabel {{
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_SM}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
        """)

        b = QLabel(body)
        b.setWordWrap(True)
        b.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt;")

        cl.addWidget(t)
        cl.addWidget(b)
        return card

    def _create_error_dialog(self, parent):
        try:
            super().__init__(parent)
            self.setWindowTitle("Login — ERROR")
            self.setMinimumSize(400, 200)

            # Set window flags for modern look
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            root = QVBoxLayout(self)
            root.setContentsMargins(20, 20, 20, 20)

            main_card = ModernCard(self, elevated=True)
            layout = QVBoxLayout(main_card)
            layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL, self._sp.PAD_XL, self._sp.PAD_XL)

            lbl = QLabel("❌ Failed to initialize login dialog.\nPlease check the logs.")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:{self._c.RED_BRIGHT}; padding:{self._sp.PAD_XL}px; font-size:{self._ty.SIZE_MD}pt;")
            layout.addWidget(lbl)

            btn = QPushButton("Close")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BLUE};
                    color: white;
                    border: none;
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    min-width: 100px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BLUE_DARK};
                }}
            """)
            btn.clicked.connect(self.reject)
            layout.addWidget(btn, 0, Qt.AlignCenter)

            root.addWidget(main_card)
        except Exception as e:
            logger.error(f"[_create_error_dialog] {e}", exc_info=True)

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self):
        try:
            self.error_occurred.connect(self._on_error)
            self.operation_started.connect(lambda: None)
            self.operation_finished.connect(lambda: None)
            self.token_refreshed.connect(self._on_token_refreshed)
        except Exception as e:
            logger.error(f"[_connect_signals] {e}", exc_info=True)

    # ── URL management ────────────────────────────────────────────────────────

    def _init_login_url(self):
        try:
            if not self._helper or not self._helper.has_login_url:
                return
            url = self._helper.generate_login_url()
            if not url:
                if self.status_label:
                    self.status_label.setText("⚠️ Could not generate login URL — check credentials in Settings")
                return
            self.login_url = url
            if self.url_text:
                self.url_text.setText(url)
            if self.status_label:
                self.status_label.setText("✅ Login URL generated")
        except Exception as e:
            logger.error(f"[_init_login_url] {e}", exc_info=True)
            if self.status_label:
                self.status_label.setText(f"❌ {e}")

    def _copy_url(self):
        try:
            url = safe_getattr(self, 'login_url', None)
            if url:
                QApplication.clipboard().setText(url)
                if self.status_label:
                    self.status_label.setText("📋 URL copied to clipboard")
                    QTimer.singleShot(2000, lambda: self.status_label.setText("") if self.status_label else None)
            else:
                QMessageBox.warning(self, "Warning", "No URL to copy")
        except Exception as e:
            logger.error(f"[_copy_url] {e}", exc_info=True)

    def _open_url(self):
        try:
            url = safe_getattr(self, 'login_url', None)
            if url:
                webbrowser.open(url)
                if self.status_label:
                    self.status_label.setText("🌐 Browser opened")
            else:
                QMessageBox.critical(self, "Error", "Login URL is unavailable.")
        except Exception as e:
            logger.error(f"[_open_url] {e}", exc_info=True)

    def _clear_entries(self):
        try:
            if self.code_entry:
                self.code_entry.clear()
            if self.password_entry:
                self.password_entry.clear()
        except Exception as e:
            logger.error(f"[_clear_entries] {e}", exc_info=True)

    # ── Auth code extraction ──────────────────────────────────────────────────

    def _extract_code(self, raw: str) -> str:
        """
        Extract the token/code from various input formats:
        - Full redirect URL (extracts auth_code / code / request_token param)
        - Raw code/token string
        """
        try:
            if not raw:
                return ""
            raw = raw.strip()

            # Already a plain token (no URL characters)
            if re.match(r'^[A-Za-z0-9\-_\.]+$', raw):
                return raw

            # Skip if it looks like an access_token pasted by mistake
            if "access_token" in raw:
                logger.warning("Input contains access_token — user should paste the auth code / redirect URL")
                return ""

            # Try URL parsing
            try:
                parsed = urlparse(raw)
                for src in (parsed.query, parsed.fragment):
                    if src:
                        params = parse_qs(src)
                        for key in ('auth_code', 'code', 'request_token', 'token', 'authorization_code'):
                            if key in params and params[key]:
                                return params[key][0]
            except Exception:
                pass

            # Fall back to returning raw if it has no URL structure
            if "?" not in raw and "=" not in raw:
                return raw

            return ""
        except Exception as e:
            logger.error(f"[_extract_code] {e}", exc_info=True)
            return ""

    # ── Exchange / worker ─────────────────────────────────────────────────────

    def _start_exchange(self):
        try:
            if self._exchange_in_progress:
                return
            if not self._helper:
                return

            auth = self._helper.auth_method

            # Collect inputs
            raw_code = ""
            if self.code_entry:
                raw_code = self.code_entry.text().strip()

            extra = {}

            # For TOTP brokers that need a password
            if self._helper.needs_password_field:
                password = self.password_entry.text().strip() if self.password_entry else ""
                if not password and auth == "totp":
                    QMessageBox.warning(
                        self, "Input Needed",
                        f"Please enter your {self._helper.password_field_label}."
                    )
                    return
                extra["password"] = password

            # For OAuth/session brokers: extract code from URL
            if auth in ("oauth", "session"):
                if not raw_code:
                    QMessageBox.warning(self, "Input Needed",
                                        "Please paste the auth code or full redirected URL.")
                    return
                code = self._extract_code(raw_code)
                if not code:
                    QMessageBox.critical(
                        self, "Invalid Input",
                        "Could not extract auth code from your input.\n"
                        "Paste the full redirected URL, or just the code value."
                    )
                    return
                if auth == "oauth" and len(code) < 10:
                    QMessageBox.critical(self, "Invalid Input",
                                         "Auth code seems too short — please check and try again.")
                    return
            elif auth == "static":
                # For Dhan: accept token from entry or fall back to secret_key
                code = raw_code or safe_getattr(self._helper, 'secret_key', '') or ""
                if not code:
                    QMessageBox.warning(self, "Input Needed", "Please paste the access token.")
                    return
            elif auth == "totp":
                code = raw_code  # blank = auto-generate from secret
            else:
                code = raw_code  # password auth: blank is fine

            self._exchange_in_progress = True
            self.operation_started.emit()

            if self.login_btn:
                self.login_btn.setEnabled(False)
            if self.clear_btn:
                self.clear_btn.setEnabled(False)
            if self.progress_bar:
                self.progress_bar.setVisible(True)
                self.progress_bar.setValue(10)
            if self.status_label:
                self.status_label.setText("⏳ Processing authentication…")

            self.token_worker = TokenExchangeWorker(self._helper, code, extra)
            self.token_worker.progress.connect(self._update_progress)
            self.token_worker.finished.connect(self._on_exchange_complete)
            self.token_worker.error_occurred.connect(self._on_worker_error)
            self.token_worker.start()
            logger.info("Token exchange started")

        except Exception as e:
            logger.error(f"[_start_exchange] {e}", exc_info=True)
            self.error_occurred.emit(f"Exchange failed: {e}")
            self._exchange_in_progress = False
            self.operation_finished.emit()
            self._reset_ui()

    def _update_progress(self, pct: int, msg: str):
        try:
            if self.progress_bar:
                self.progress_bar.setValue(pct)
            if self.status_label:
                self.status_label.setText(f"⏳ {msg}")
        except Exception as e:
            logger.error(f"[_update_progress] {e}", exc_info=True)

    def _on_worker_error(self, error_msg: str):
        logger.error(f"Worker error: {error_msg}")
        self.error_occurred.emit(error_msg)

    def _on_exchange_complete(self, token, error: str):
        try:
            if self.token_worker:
                self.token_worker.stop()
                self.token_worker.deleteLater()
                self.token_worker = None

            if error:
                if self.status_label:
                    self.status_label.setText(f"❌ {error}")
                QMessageBox.critical(self, "Login Failed",
                                     f"Authentication failed.\n\nError: {error}\n\n"
                                     "Please check your credentials and try again.")
                self._reset_ui()
                return

            if token:
                # Save token to brokerage_setting if possible
                if self.brokerage_setting and safe_hasattr(self.brokerage_setting, 'save_token'):
                    try:
                        now = datetime.now()
                        self.brokerage_setting.save_token(
                            access_token=token,
                            refresh_token="",
                            issued_at=now.isoformat(),
                            expires_at=(now + timedelta(hours=24)).isoformat(),
                        )
                    except Exception as e:
                        logger.error(f"Failed to save token to brokerage_setting: {e}", exc_info=True)

                # Telegram notification
                if self.notify_check and self.notify_check.isChecked():
                    self._send_telegram_notification(success=True)

                self.result_token = token
                if self.status_label:
                    self.status_label.setText("✅ Login successful!")
                if self.progress_bar:
                    self.progress_bar.setValue(100)

                self.login_completed.emit(token)
                QMessageBox.information(self, "Success",
                                        "Login successful! Token has been stored.")
                QTimer.singleShot(500, self.accept)
            else:
                if self.status_label:
                    self.status_label.setText("❌ Failed to retrieve token")
                QMessageBox.critical(self, "Error", "Failed to retrieve token.")
                self._reset_ui()

        except Exception as e:
            logger.error(f"[_on_exchange_complete] {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self._reset_ui()
        finally:
            self._exchange_in_progress = False
            self.operation_finished.emit()

    def _send_telegram_notification(self, success: bool = True):
        try:
            if not self.notifier:
                return
            broker = self._helper.broker_display_name if self._helper else "Broker"
            if success:
                msg = f"✅ *TOKEN REFRESHED*\n{broker} access token has been successfully renewed."
                self.notifier.notify_token_refreshed(msg)
                self.token_refreshed.emit(msg, "success")
            else:
                msg = f"❌ *TOKEN REFRESH FAILED*\nFailed to refresh {broker} token."
                self.notifier.notify_token_refresh_failed(msg)
                self.token_refreshed.emit(msg, "error")
        except Exception as e:
            logger.error(f"[_send_telegram_notification] {e}", exc_info=True)

    def _on_token_refreshed(self, message: str, status: str):
        logger.info(f"Token refresh notification: {status}")

    def _reset_ui(self):
        try:
            if self.login_btn:
                self.login_btn.setEnabled(True)
            if self.clear_btn:
                self.clear_btn.setEnabled(True)
            if self.progress_bar:
                self.progress_bar.setVisible(False)
                self.progress_bar.setValue(0)
            if self.status_label and self.status_label.text().startswith("⏳"):
                self.status_label.setText("")
        except Exception as e:
            logger.error(f"[_reset_ui] {e}", exc_info=True)

    def _on_error(self, msg: str):
        try:
            logger.error(f"Error signal: {msg}")
            QMessageBox.critical(self, "Error", msg)
            self._reset_ui()
        except Exception as e:
            logger.error(f"[_on_error] {e}", exc_info=True)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        try:
            logger.info("[BrokerLoginPopup] Starting cleanup")
            if self.token_worker and self.token_worker.isRunning():
                self.token_worker.stop()
                if not self.token_worker.wait(3000):
                    self.token_worker.terminate()
                    self.token_worker.wait(1000)
            self.token_worker = None
            if self._helper:
                self._helper.cleanup()
            self._helper = None
            self.brokerage_setting = None
            self.notifier = None
            logger.info("[BrokerLoginPopup] Cleanup completed")
        except Exception as e:
            logger.error(f"[BrokerLoginPopup.cleanup] {e}", exc_info=True)

    def closeEvent(self, event):
        try:
            self.cleanup()
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[BrokerLoginPopup.closeEvent] {e}", exc_info=True)
            super().closeEvent(event)


# ── Backward-compatibility alias ─────────────────────────────────────────────
FyersManualLoginPopup = BrokerLoginPopup