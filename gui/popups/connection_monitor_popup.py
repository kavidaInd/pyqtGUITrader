"""
Connection Monitor Popup - Displays WebSocket and broker connection status

UPDATED: Modern minimalist design with scrollbars to prevent cramped content
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""
import logging
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QGridLayout, QTabWidget, \
    QFrame, QWidget, QScrollArea
from PyQt5.QtGui import QFont

from Utils.safe_getattr import safe_hasattr
# Import state manager
from data.trade_state_manager import state_manager
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


class StatusBadge(QLabel):
    """Status badge with color-coded background."""

    def __init__(self, text="", status="disconnected"):
        super().__init__(text)
        self.setObjectName("statusBadge")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(100)
        self.set_status(status)

    def set_status(self, status):
        """Update badge color based on status."""
        c = theme_manager.palette
        sp = theme_manager.spacing
        ty = theme_manager.typography

        if status == "connected":
            color = c.GREEN
            bg = c.GREEN + "20"  # 20 = 12% opacity in hex
        elif status == "warning":
            color = c.ORANGE
            bg = c.ORANGE + "20"
        elif status == "error":
            color = c.RED
            bg = c.RED + "20"
        else:
            color = c.TEXT_DIM
            bg = c.BG_HOVER

        self.setStyleSheet(f"""
            QLabel#statusBadge {{
                color: {color};
                background: {bg};
                border: 1px solid {color};
                border-radius: {sp.RADIUS_PILL}px;
                padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                font-size: {ty.SIZE_XS}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
        """)


class ScrollableTabWidget(QWidget):
    """Tab widget with scrollable content area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Container widget for scrollable content
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(theme_manager.spacing.GAP_LG)

        self.scroll.setWidget(self.container)
        self.layout.addWidget(self.scroll)

    def add_widget(self, widget):
        """Add a widget to the scrollable area."""
        self.container_layout.addWidget(widget)

    def add_stretch(self):
        """Add stretch to the scrollable area."""
        self.container_layout.addStretch()


class ConnectionMonitorPopup(QDialog, ThemedMixin):
    """Popup window for monitoring connection status with modern design"""

    def __init__(self, trading_app=None, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.trading_app = trading_app
            self.setWindowTitle("Connection Monitor")
            self.resize(800, 700)
            self.setMinimumSize(750, 600)

            # Set window flags for modern look
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            # Build UI
            self._init_ui()

            # Apply theme initially
            self.apply_theme()

            # Initialize timer
            self._init_timer()

            logger.info("ConnectionMonitorPopup initialized")

        except Exception as e:
            logger.critical(f"[ConnectionMonitorPopup.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.trading_app = None
        self.timer = None
        self.reconnect_btn = None
        self.test_btn = None
        self.refresh_btn = None

        # Connection tab labels
        self.ws_status_label = None
        self.ws_status_badge = None
        self.ws_connected_since = None
        self.ws_last_message = None
        self.ws_msg_count = None
        self.ws_reconnects = None
        self.ws_errors = None
        self.broker_status_label = None
        self.broker_status_badge = None
        self.token_expiry_label = None
        self.last_api_call = None
        self.rate_limit = None
        self.symbols_subscribed = None
        self.active_symbols = None
        self.option_chain_size = None

        # Statistics tab labels
        self.uptime_label = None
        self.msg_rate = None
        self.peak_rate = None
        self.data_received = None
        self.conn_events = None
        self.last_disconnect = None

        self.main_card = None

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            super().__init__(parent)
            self.setWindowTitle("Connection Monitor - ERROR")
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

            error_label = QLabel("❌ Failed to initialize connection monitor.\nPlease check the logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet(f"color: {self._c.RED_BRIGHT}; padding: {self._sp.PAD_XL}px; font-size: {self._ty.SIZE_MD}pt;")
            layout.addWidget(error_label)

            close_btn = self._create_modern_button("Close", primary=False)
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn, 0, Qt.AlignCenter)

            root.addWidget(main_card)

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._create_error_dialog] Failed: {e}", exc_info=True)

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the popup.
        Called on theme change, density change, and initial render.
        """
        try:
            # Update main card style
            if hasattr(self, 'main_card'):
                self.main_card._apply_style()

            # Update button styles
            self._update_button_styles()

            # Update status badges based on current state
            self._update_status_badges()

            # Update scrollbar styles
            self._update_scrollbar_styles()

            logger.debug("[ConnectionMonitorPopup.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.apply_theme] Failed: {e}", exc_info=True)

    def _update_scrollbar_styles(self):
        """Update scrollbar styles with theme tokens."""
        c = self._c
        sp = self._sp

        scrollbar_style = f"""
            QScrollBar:vertical {{
                background: {c.BG_PANEL};
                width: {sp.ICON_MD}px;
                border-radius: {sp.RADIUS_MD}px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {c.BORDER};
                min-height: {sp.BTN_HEIGHT_SM}px;
                border-radius: {sp.RADIUS_MD}px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {c.BORDER_STRONG};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background: {c.BG_PANEL};
                height: {sp.ICON_MD}px;
                border-radius: {sp.RADIUS_MD}px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {c.BORDER};
                min-width: {sp.BTN_HEIGHT_SM}px;
                border-radius: {sp.RADIUS_MD}px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {c.BORDER_STRONG};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """

        # Apply to all scroll areas in the dialog
        for scroll_area in self.findChildren(QScrollArea):
            scroll_area.setStyleSheet(scrollbar_style)

    def _init_ui(self):
        """Initialize the user interface with modern design"""
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


        # Create tab widget with modern styling
        tabs = self._create_modern_tabs()
        content_layout.addWidget(tabs, 1)  # Give tabs stretch factor

        # Button row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(self._sp.GAP_MD)

        self.reconnect_btn = self._create_modern_button("🔄 Reconnect WebSocket", primary=False, icon="🔄")
        self.reconnect_btn.clicked.connect(self._reconnect)

        self.test_btn = self._create_modern_button("🧪 Test Connection", primary=False, icon="🧪")
        self.test_btn.clicked.connect(self._test_connection)

        self.refresh_btn = self._create_modern_button("⟳ Refresh", primary=False, icon="⟳")
        self.refresh_btn.clicked.connect(self.refresh)

        close_btn = self._create_modern_button("✕ Close", primary=False)
        close_btn.clicked.connect(self.accept)

        button_layout.addWidget(self.reconnect_btn)
        button_layout.addWidget(self.test_btn)
        button_layout.addWidget(self.refresh_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)

        content_layout.addLayout(button_layout)

        main_layout.addWidget(content)
        root.addWidget(self.main_card)

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

        title = QLabel("🔌  Connection Monitor")
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
        close_btn.clicked.connect(self.accept)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(close_btn)

        self._drag_pos = None
        title_bar.mousePressEvent   = lambda e: setattr(self,'_drag_pos', e.globalPos()-self.frameGeometry().topLeft()) if e.button()==1 else None
        title_bar.mouseMoveEvent    = lambda e: self.move(e.globalPos()-self._drag_pos) if e.buttons()==1 and self._drag_pos else None
        title_bar.mouseReleaseEvent = lambda e: setattr(self,'_drag_pos',None)

        return title_bar

    def _create_modern_tabs(self):
        """Create modern-styled tab widget."""
        tabs = QTabWidget()

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

        # Tab 1: Connection Status (scrollable)
        conn_tab = self._create_connection_tab()
        tabs.addTab(conn_tab, "🔌 Connection")

        # Tab 2: Statistics (scrollable)
        stats_tab = self._create_statistics_tab()
        tabs.addTab(stats_tab, "📊 Statistics")

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
                    min-width: 140px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BORDER};
                    border-color: {self._c.BORDER_FOCUS};
                }}
            """)

        return btn

    def _update_button_styles(self):
        """Update button styles with theme tokens"""
        # Reconnect button
        if self.reconnect_btn:
            self.reconnect_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    min-width: 160px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BORDER};
                    border-color: {self._c.BORDER_FOCUS};
                }}
                QPushButton:disabled {{
                    background: {self._c.BG_PANEL};
                    color: {self._c.TEXT_DISABLED};
                }}
            """)

        # Test button
        if self.test_btn:
            self.test_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    min-width: 140px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BORDER};
                    border-color: {self._c.BORDER_FOCUS};
                }}
            """)

        # Refresh button
        if self.refresh_btn:
            self.refresh_btn.setStyleSheet(f"""
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

    def _create_connection_tab(self) -> QWidget:
        """Create connection status tab with scrollable content"""
        scrollable = ScrollableTabWidget()

        # WebSocket Card
        ws_card = ModernCard()
        ws_layout = QVBoxLayout(ws_card)
        ws_layout.setSpacing(self._sp.GAP_MD)

        ws_header = QLabel("🌐 WebSocket Connection")
        ws_header.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_MD}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
        """)
        ws_layout.addWidget(ws_header)

        ws_grid = QGridLayout()
        ws_grid.setVerticalSpacing(self._sp.GAP_SM)
        ws_grid.setHorizontalSpacing(self._sp.GAP_MD)

        # Status with badge
        ws_grid.addWidget(self._create_label("Status:"), 0, 0)
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(self._sp.GAP_SM)
        self.ws_status_badge = StatusBadge("Disconnected", "disconnected")
        self.ws_status_label = self._create_label("")
        status_layout.addWidget(self.ws_status_badge)
        status_layout.addWidget(self.ws_status_label)
        status_layout.addStretch()
        ws_grid.addWidget(status_widget, 0, 1)

        # Connected since
        ws_grid.addWidget(self._create_label("Connected Since:"), 1, 0)
        self.ws_connected_since = self._create_value_label("-")
        ws_grid.addWidget(self.ws_connected_since, 1, 1)

        # Last message
        ws_grid.addWidget(self._create_label("Last Message:"), 2, 0)
        self.ws_last_message = self._create_value_label("-")
        ws_grid.addWidget(self.ws_last_message, 2, 1)

        # Messages received
        ws_grid.addWidget(self._create_label("Messages Received:"), 3, 0)
        self.ws_msg_count = self._create_value_label("0")
        ws_grid.addWidget(self.ws_msg_count, 3, 1)

        # Reconnect count
        ws_grid.addWidget(self._create_label("Reconnects:"), 4, 0)
        self.ws_reconnects = self._create_value_label("0")
        ws_grid.addWidget(self.ws_reconnects, 4, 1)

        # Error count
        ws_grid.addWidget(self._create_label("Errors:"), 5, 0)
        self.ws_errors = self._create_value_label("0")
        ws_grid.addWidget(self.ws_errors, 5, 1)

        ws_layout.addLayout(ws_grid)
        scrollable.add_widget(ws_card)

        # Broker API Card
        broker_card = ModernCard()
        broker_layout = QVBoxLayout(broker_card)
        broker_layout.setSpacing(self._sp.GAP_MD)

        broker_header = QLabel("🏦 Broker API")
        broker_header.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_MD}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
        """)
        broker_layout.addWidget(broker_header)

        broker_grid = QGridLayout()
        broker_grid.setVerticalSpacing(self._sp.GAP_SM)
        broker_grid.setHorizontalSpacing(self._sp.GAP_MD)

        # Status with badge
        broker_grid.addWidget(self._create_label("Status:"), 0, 0)
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(self._sp.GAP_SM)
        self.broker_status_badge = StatusBadge("Disconnected", "disconnected")
        self.broker_status_label = self._create_label("")
        status_layout.addWidget(self.broker_status_badge)
        status_layout.addWidget(self.broker_status_label)
        status_layout.addStretch()
        broker_grid.addWidget(status_widget, 0, 1)

        # Token expiry
        broker_grid.addWidget(self._create_label("Token Expiry:"), 1, 0)
        self.token_expiry_label = self._create_value_label("-")
        broker_grid.addWidget(self.token_expiry_label, 1, 1)

        # Last API call
        broker_grid.addWidget(self._create_label("Last API Call:"), 2, 0)
        self.last_api_call = self._create_value_label("-")
        broker_grid.addWidget(self.last_api_call, 2, 1)

        # Rate limit remaining
        broker_grid.addWidget(self._create_label("Rate Limit:"), 3, 0)
        self.rate_limit = self._create_value_label("-")
        broker_grid.addWidget(self.rate_limit, 3, 1)

        broker_layout.addLayout(broker_grid)
        scrollable.add_widget(broker_card)

        # Market Data Card
        market_card = ModernCard()
        market_layout = QVBoxLayout(market_card)
        market_layout.setSpacing(self._sp.GAP_MD)

        market_header = QLabel("📊 Market Data")
        market_header.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_MD}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
        """)
        market_layout.addWidget(market_header)

        market_grid = QGridLayout()
        market_grid.setVerticalSpacing(self._sp.GAP_SM)
        market_grid.setHorizontalSpacing(self._sp.GAP_MD)

        # Symbols subscribed
        market_grid.addWidget(self._create_label("Subscribed Symbols:"), 0, 0)
        self.symbols_subscribed = self._create_value_label("0")
        market_grid.addWidget(self.symbols_subscribed, 0, 1)

        # Active symbols
        market_grid.addWidget(self._create_label("Active Symbols:"), 1, 0)
        self.active_symbols = self._create_value_label("0")
        market_grid.addWidget(self.active_symbols, 1, 1)

        # Option chain size
        market_grid.addWidget(self._create_label("Option Chain:"), 2, 0)
        self.option_chain_size = self._create_value_label("0")
        market_grid.addWidget(self.option_chain_size, 2, 1)

        market_layout.addLayout(market_grid)
        scrollable.add_widget(market_card)

        scrollable.add_stretch()
        return scrollable

    def _create_statistics_tab(self) -> QWidget:
        """Create statistics tab with scrollable content"""
        scrollable = ScrollableTabWidget()

        # Statistics Card
        stats_card = ModernCard()
        stats_layout = QVBoxLayout(stats_card)
        stats_layout.setSpacing(self._sp.GAP_MD)

        stats_header = QLabel("📊 Connection Statistics")
        stats_header.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_MD}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
        """)
        stats_layout.addWidget(stats_header)

        stats_grid = QGridLayout()
        stats_grid.setVerticalSpacing(self._sp.GAP_SM)
        stats_grid.setHorizontalSpacing(self._sp.GAP_MD)

        # Uptime
        stats_grid.addWidget(self._create_label("Uptime:"), 0, 0)
        self.uptime_label = self._create_value_label("0s")
        stats_grid.addWidget(self.uptime_label, 0, 1)

        # Messages per second
        stats_grid.addWidget(self._create_label("Msg Rate:"), 1, 0)
        self.msg_rate = self._create_value_label("0/s")
        stats_grid.addWidget(self.msg_rate, 1, 1)

        # Peak messages
        stats_grid.addWidget(self._create_label("Peak Rate:"), 2, 0)
        self.peak_rate = self._create_value_label("0/s")
        stats_grid.addWidget(self.peak_rate, 2, 1)

        # Total bytes
        stats_grid.addWidget(self._create_label("Data Received:"), 3, 0)
        self.data_received = self._create_value_label("0 KB")
        stats_grid.addWidget(self.data_received, 3, 1)

        # Connection events
        stats_grid.addWidget(self._create_label("Connection Events:"), 4, 0)
        self.conn_events = self._create_value_label("0")
        stats_grid.addWidget(self.conn_events, 4, 1)

        # Last disconnect reason
        stats_grid.addWidget(self._create_label("Last Disconnect:"), 5, 0)
        self.last_disconnect = self._create_value_label("-")
        stats_grid.addWidget(self.last_disconnect, 5, 1)

        stats_layout.addLayout(stats_grid)
        scrollable.add_widget(stats_card)

        scrollable.add_stretch()
        return scrollable

    def _create_label(self, text: str) -> QLabel:
        """Create a standard label"""
        label = QLabel(text)
        label.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_SM}pt;")
        return label

    def _create_value_label(self, text: str) -> QLabel:
        """Create a value label with special styling"""
        label = QLabel(text)
        label.setStyleSheet(f"""
            color: {self._c.TEXT_MAIN};
            font-size: {self._ty.SIZE_SM}pt;
            font-weight: {self._ty.WEIGHT_BOLD};
            background: {self._c.BG_HOVER};
            padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
            border-radius: {self._sp.RADIUS_SM}px;
        """)
        return label

    def _init_timer(self):
        """Initialize refresh timer"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)  # Refresh every 2 seconds

    def refresh(self):
        """Refresh connection status using state_manager"""
        try:
            if not self.trading_app:
                return

            self._refresh_connection_tab()
            self._refresh_statistics_tab()

            # Update status badges
            self._update_status_badges()

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.refresh] Failed: {e}")

    def _update_status_badges(self):
        """Update status badges based on current connection state"""
        try:
            # WebSocket status
            if self.ws_status_badge and self.ws_status_label:
                is_connected = "Connected" in self.ws_status_label.text()
                if is_connected:
                    self.ws_status_badge.set_status("connected")
                    self.ws_status_badge.setText("Connected")
                else:
                    self.ws_status_badge.set_status("error")
                    self.ws_status_badge.setText("Disconnected")

            # Broker status
            if self.broker_status_badge and self.broker_status_label:
                is_connected = "Connected" in self.broker_status_label.text()
                if is_connected:
                    self.broker_status_badge.set_status("connected")
                    self.broker_status_badge.setText("Connected")
                else:
                    self.broker_status_badge.set_status("error")
                    self.broker_status_badge.setText("Disconnected")

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._update_status_badges] Failed: {e}")

    def _refresh_connection_tab(self):
        """Refresh connection tab data"""
        try:
            # Check WebSocket connection
            if safe_hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                ws = self.trading_app.ws

                # Update status
                if safe_hasattr(ws, 'is_connected') and ws.is_connected():
                    self.ws_status_label.setText("Connected")
                else:
                    self.ws_status_label.setText("Disconnected")

                # Get statistics
                stats = {}
                if safe_hasattr(ws, 'get_statistics'):
                    stats = ws.get_statistics()

                self.ws_msg_count.setText(str(stats.get('message_count', 0)))
                self.ws_reconnects.setText(str(stats.get('reconnect_count', 0)))
                self.ws_errors.setText(str(stats.get('error_count', 0)))

                # Last message time
                if safe_hasattr(ws, '_last_message_time') and ws._last_message_time:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(ws._last_message_time)
                    self.ws_last_message.setText(dt.strftime("%H:%M:%S"))

                # Connected since
                if safe_hasattr(ws, '_connected_since') and ws._connected_since:
                    self.ws_connected_since.setText(ws._connected_since.strftime("%H:%M:%S"))

            # Check broker connection
            if safe_hasattr(self.trading_app, 'broker') and self.trading_app.broker:
                broker = self.trading_app.broker

                # Check if authenticated
                if safe_hasattr(broker, 'is_connected') and broker.is_connected():
                    self.broker_status_label.setText("Connected")
                else:
                    self.broker_status_label.setText("Disconnected")

                # Token expiry
                if safe_hasattr(broker, 'token_expiry') and broker.token_expiry:
                    self.token_expiry_label.setText(broker.token_expiry.strftime("%Y-%m-%d %H:%M"))

            # Get symbol counts from state manager
            snapshot = state_manager.get_snapshot()

            # Update symbol counts
            symbols = snapshot.get('all_symbols', [])
            if symbols is None:
                symbols = []
            self.symbols_subscribed.setText(str(len(symbols)))

            # Count active symbols (with recent data)
            option_chain = snapshot.get('option_chain', {})
            if option_chain is None:
                option_chain = {}

            active = 0
            for sym, data in option_chain.items():
                if data and isinstance(data, dict) and data.get('ltp') is not None:
                    active += 1
            self.active_symbols.setText(str(active))

            # Option chain size
            self.option_chain_size.setText(str(len(option_chain)))

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._refresh_connection_tab] Failed: {e}")

    def _refresh_statistics_tab(self):
        """Refresh statistics tab data"""
        try:
            if not safe_hasattr(self.trading_app, 'ws') or not self.trading_app.ws:
                return

            ws = self.trading_app.ws
            stats = {}
            if safe_hasattr(ws, 'get_statistics'):
                stats = ws.get_statistics()

            # Calculate uptime
            if safe_hasattr(ws, '_connected_since') and ws._connected_since:
                uptime = datetime.now() - ws._connected_since
                seconds = int(uptime.total_seconds())
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                secs = seconds % 60
                self.uptime_label.setText(f"{hours}h {minutes}m {secs}s")
            else:
                self.uptime_label.setText("0s")

            # Message rate
            msg_count = stats.get('message_count', 0)
            if safe_hasattr(ws, '_connected_since') and ws._connected_since:
                uptime_seconds = max(1, (datetime.now() - ws._connected_since).total_seconds())
                rate = msg_count / uptime_seconds
                self.msg_rate.setText(f"{rate:.1f}/s")
            else:
                self.msg_rate.setText("0/s")

            # Data received (estimate - 100 bytes per message)
            data_kb = (msg_count * 100) / 1024
            self.data_received.setText(f"{data_kb:.1f} KB")

            # Connection events
            self.conn_events.setText(str(stats.get('reconnect_count', 0)))

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._refresh_statistics_tab] Failed: {e}")

    def _reconnect(self):
        """Attempt to reconnect WebSocket"""
        try:
            if self.trading_app and safe_hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                ws = self.trading_app.ws

                # Disconnect first
                if safe_hasattr(ws, 'disconnect'):
                    ws.disconnect()

                # Reconnect
                if safe_hasattr(ws, 'connect'):
                    ws.connect()

                self.reconnect_btn.setText("🔄 Reconnecting...")
                self.reconnect_btn.setEnabled(False)
                QTimer.singleShot(3000, self._reset_reconnect_btn)
        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._reconnect] Failed: {e}")

    def _test_connection(self):
        """Test broker connection"""
        try:
            from PyQt5.QtWidgets import QMessageBox

            if not self.trading_app or not safe_hasattr(self.trading_app, 'broker'):
                QMessageBox.warning(self, "Test Failed", "Broker not available")
                return

            broker = self.trading_app.broker

            # Try to get profile
            if safe_hasattr(broker, 'get_profile'):
                profile = broker.get_profile()
                if profile:
                    QMessageBox.information(self, "Connection Test", "✅ Connection successful!")
                else:
                    QMessageBox.warning(self, "Connection Test", "❌ Connection failed - check token")
            else:
                QMessageBox.warning(self, "Test Failed", "Broker does not support get_profile")

        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup._test_connection] Failed: {e}")
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Test Error", f"Error testing connection: {e}")

    def _reset_reconnect_btn(self):
        """Reset reconnect button"""
        self.reconnect_btn.setText("🔄 Reconnect WebSocket")
        self.reconnect_btn.setEnabled(True)

    def closeEvent(self, event):
        """Handle close event - Rule 7"""
        try:
            if self.timer:
                self.timer.stop()
                self.timer = None
            event.accept()
        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.closeEvent] Failed: {e}")
            event.accept()

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            if self.timer and self.timer.isActive():
                self.timer.stop()
            self.timer = None
            self.trading_app = None
            logger.info("[ConnectionMonitorPopup] Cleanup completed")
        except Exception as e:
            logger.error(f"[ConnectionMonitorPopup.cleanup] Error: {e}", exc_info=True)