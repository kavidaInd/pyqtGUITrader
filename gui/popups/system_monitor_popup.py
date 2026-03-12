"""
System Monitor Popup - Displays system resource usage and trading app performance metrics

MODERN MINIMALIST DESIGN - Matches DailyTradeSettingGUI, BrokerageSettingGUI, etc.
UPDATED: Now uses state_manager for trading state access.
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""
import logging
import psutil
import os
from datetime import datetime
from Utils.time_utils import IST, ist_now, fmt_display, fmt_stamp
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QTimer
from gui.dialog_base import ThemedDialog, ThemedMixin, ModernCard, make_separator, make_scrollbar_ss, create_section_header, create_modern_button, apply_tab_style, build_title_bar
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QGridLayout, QProgressBar, QTabWidget, QFrame, QWidget, QScrollArea
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

    def __init__(self, text="", status="neutral"):
        super().__init__(text)
        self.setObjectName("statusBadge")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(80)
        self.set_status(status)

    def set_status(self, status):
        """Update badge color based on status."""
        c = theme_manager.palette
        sp = theme_manager.spacing
        ty = theme_manager.typography

        if status == "success":
            color = c.GREEN
            bg = c.GREEN + "20"
        elif status == "warning":
            color = c.ORANGE
            bg = c.ORANGE + "20"
        elif status == "error":
            color = c.RED
            bg = c.RED + "20"
        elif status == "info":
            color = c.BLUE
            bg = c.BLUE + "20"
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

class ValueLabel(QLabel):
    """Value label with consistent styling."""

    def __init__(self, text="--", parent=None):
        super().__init__(text, parent)
        self.setObjectName("valueLabel")
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setMinimumWidth(80)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        self._apply_style()

    def _apply_style(self):
        c = theme_manager.palette
        sp = theme_manager.spacing
        ty = theme_manager.typography

        self.setStyleSheet(f"""
            QLabel#valueLabel {{
                color: {c.TEXT_MAIN};
                background: {c.BG_HOVER};
                border-radius: {sp.RADIUS_SM}px;
                padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                font-size: {ty.SIZE_SM}pt;
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
        self.container.setStyleSheet("background: transparent;")
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

class SystemMonitorPopup(ThemedDialog):
    """Popup window for monitoring system resources and trading app performance"""

    def __init__(self, trading_app=None, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent, title="SYSTEM MONITOR", icon="SM", size=(700, 700))

            # Rule 13.2: Connect to theme and density signals

            self.trading_app = trading_app
            # Set window flags for modern look
            self.resize(700, 700)
            self.setMinimumSize(600, 600)

            # Build UI
            self._init_ui()
            self._init_timer()

            # Cache for snapshots
            self._last_snapshot = {}
            self._last_snapshot_time = None
            self._last_position_snapshot = {}
            self._snapshot_cache_duration = 0.1  # 100ms

            # Apply theme initially
            self.apply_theme()

            logger.info("SystemMonitorPopup initialized")

        except Exception as e:
            logger.critical(f"[SystemMonitorPopup.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.trading_app = None
        self.timer = None
        self.tab_widget = None
        self.refresh_btn = None
        self.gc_btn = None
        self.main_card = None

        # System tab widgets
        self.cpu_progress = None
        self.cpu_cores = None
        self.cpu_freq = None
        self.cpu_load = None
        self.mem_progress = None
        self.mem_used = None
        self.mem_available = None
        self.mem_total = None
        self.disk_progress = None
        self.disk_used = None
        self.disk_free = None
        self.disk_total = None

        # App tab widgets
        self.process_pid = None
        self.process_threads = None
        self.process_memory = None
        self.process_cpu = None
        self.process_uptime = None
        self.process_fds = None
        self.trading_msg_rate = None
        self.trading_queue_size = None
        self.trading_symbols = None
        self.trading_active_chain = None
        self.trading_open_orders = None
        self.trading_position = None
        self.trading_pnl = None
        self.trading_signal = None
        self.risk_trades_today = None
        self.risk_loss_remaining = None
        self.risk_trades_left = None

        # Network tab widgets
        self.ws_status_badge = None
        self.ws_status = None
        self.ws_messages = None
        self.ws_errors = None
        self.ws_reconnects = None
        self.ws_last_msg = None
        self.net_bytes_sent = None
        self.net_bytes_recv = None
        self.net_packets_sent = None
        self.net_packets_recv = None
        self.conn_list = None

        # Cache
        self._last_snapshot = {}
        self._last_snapshot_time = None
        self._last_position_snapshot = {}
        self._snapshot_cache_duration = 0.1
        self.process_start_time = None

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            super().__init__(parent)
            self.setMinimumSize(400, 300)

            # Set window flags for modern look
            root = QVBoxLayout(self)
            root.setContentsMargins(20, 20, 20, 20)

            main_card = ModernCard(self, elevated=True)
            layout = QVBoxLayout(main_card)
            layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL,
                                     self._sp.PAD_XL, self._sp.PAD_XL)

            error_label = QLabel("❌ Failed to initialize system monitor.\nPlease check the logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet(f"color: {self._c.RED_BRIGHT}; padding: {self._sp.PAD_XL}px; font-size: {self._ty.SIZE_MD}pt;")
            layout.addWidget(error_label)

            close_btn = self._create_modern_button("Close", primary=False)
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn, 0, Qt.AlignCenter)

            root.addWidget(main_card)

        except Exception as e:
            logger.error(f"[SystemMonitorPopup._create_error_dialog] Failed: {e}", exc_info=True)

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
                    min-width: 120px;
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
                    min-width: 120px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BORDER};
                    border-color: {self._c.BORDER_FOCUS};
                }}
            """)

        return btn

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the popup.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            sp = self._sp

            # Update main card style
            if self.main_card:
                self.main_card._apply_style()

            # Update button styles
            self._update_button_styles()

            # Update progress bar colors based on current values
            self._update_progress_bar_colors()

            # Update scrollbar styles
            self._update_scrollbar_styles()

            logger.debug("[SystemMonitorPopup.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[SystemMonitorPopup.apply_theme] Failed: {e}", exc_info=True)

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

    def _update_button_styles(self):
        """Update button styles with theme tokens"""
        # Refresh button
        if self.refresh_btn:
            self.refresh_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_LG}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    min-width: 120px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BORDER};
                    border-color: {self._c.BORDER_FOCUS};
                }}
            """)

        # GC button
        if self.gc_btn:
            self.gc_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.RED};
                    color: white;
                    border: none;
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_LG}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    min-width: 120px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.RED_BRIGHT};
                }}
            """)

    def _init_ui(self):
        """Initialize the user interface"""
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

        # Create tab widget
        self.tab_widget = self._create_modern_tabs()
        content_layout.addWidget(self.tab_widget, 1)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(self._sp.GAP_MD)

        self.refresh_btn = self._create_modern_button("Refresh Now", primary=False, icon="⟳")
        self.refresh_btn.clicked.connect(self.refresh)

        self.gc_btn = self._create_modern_button("Run GC", primary=False, icon="🗑️")
        self.gc_btn.clicked.connect(self._run_garbage_collection)

        close_btn = self._create_modern_button("Close", primary=True, icon="✕")
        close_btn.clicked.connect(self.accept)

        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.gc_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)

        content_layout.addLayout(button_layout)

        main_layout.addWidget(content)
        root.addWidget(self.main_card)

        # Store process start time
        self.process_start_time = ist_now()

    def _create_title_bar(self):
        """Build new-design title bar: monogram badge + CAPS title + ghost buttons."""
        return build_title_bar(
            self,
            title="SYSTEM MONITOR",
            icon="SM",
            on_close=self.close,
            on_refresh=self.refresh,
        )

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
                min-width: 90px;
                border: 1px solid {self._c.BORDER};
                border-bottom: none;
                border-radius: {self._sp.RADIUS_MD}px {self._sp.RADIUS_MD}px 0 0;
                font-size: {self._ty.SIZE_SM}pt;
                font-weight: 600;
                margin-right: 2px;
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

        # Tab 1: System Resources (scrollable)
        system_tab = self._create_system_tab()
        tabs.addTab(system_tab, "💻 System")

        # Tab 2: Trading App Metrics (scrollable)
        app_tab = self._create_app_tab()
        tabs.addTab(app_tab, "📊 Trading")

        # Tab 3: Network Stats (scrollable)
        network_tab = self._create_network_tab()
        tabs.addTab(network_tab, "🌐 Network")

        return tabs

    def _create_system_tab(self):
        """Create system resources tab with modern card layout"""
        scrollable = ScrollableTabWidget()

        # CPU Card
        cpu_card = ModernCard()
        cpu_layout = QVBoxLayout(cpu_card)
        cpu_layout.setSpacing(self._sp.GAP_MD)

        cpu_header = QLabel("💻 CPU Usage")
        cpu_header.setStyleSheet(f"color: {self._c.BLUE}; font-size: {self._ty.SIZE_MD}pt; font-weight: {self._ty.WEIGHT_BOLD};")
        cpu_layout.addWidget(cpu_header)

        self.cpu_progress = QProgressBar()
        self.cpu_progress.setRange(0, 100)
        self.cpu_progress.setFormat("%p%")
        self.cpu_progress.setMinimumHeight(self._sp.PROGRESS_MD)
        cpu_layout.addWidget(self.cpu_progress)

        cpu_grid = QGridLayout()
        cpu_grid.setVerticalSpacing(self._sp.GAP_SM)
        cpu_grid.setHorizontalSpacing(self._sp.GAP_MD)

        cpu_grid.addWidget(QLabel("Cores:"), 0, 0)
        self.cpu_cores = ValueLabel(str(psutil.cpu_count()))
        cpu_grid.addWidget(self.cpu_cores, 0, 1)

        cpu_grid.addWidget(QLabel("Frequency:"), 1, 0)
        self.cpu_freq = ValueLabel("-")
        cpu_grid.addWidget(self.cpu_freq, 1, 1)

        cpu_grid.addWidget(QLabel("Load Average:"), 2, 0)
        self.cpu_load = ValueLabel("-")
        cpu_grid.addWidget(self.cpu_load, 2, 1)

        cpu_layout.addLayout(cpu_grid)
        scrollable.add_widget(cpu_card)

        # Memory Card
        mem_card = ModernCard()
        mem_layout = QVBoxLayout(mem_card)
        mem_layout.setSpacing(self._sp.GAP_MD)

        mem_header = QLabel("🧠 Memory Usage")
        mem_header.setStyleSheet(f"color: {self._c.BLUE}; font-size: {self._ty.SIZE_MD}pt; font-weight: {self._ty.WEIGHT_BOLD};")
        mem_layout.addWidget(mem_header)

        self.mem_progress = QProgressBar()
        self.mem_progress.setRange(0, 100)
        self.mem_progress.setFormat("%p%")
        self.mem_progress.setMinimumHeight(self._sp.PROGRESS_MD)
        mem_layout.addWidget(self.mem_progress)

        mem_grid = QGridLayout()
        mem_grid.setVerticalSpacing(self._sp.GAP_SM)
        mem_grid.setHorizontalSpacing(self._sp.GAP_MD)

        mem_grid.addWidget(QLabel("Used:"), 0, 0)
        self.mem_used = ValueLabel("-")
        mem_grid.addWidget(self.mem_used, 0, 1)

        mem_grid.addWidget(QLabel("Available:"), 1, 0)
        self.mem_available = ValueLabel("-")
        mem_grid.addWidget(self.mem_available, 1, 1)

        mem_grid.addWidget(QLabel("Total:"), 2, 0)
        self.mem_total = ValueLabel("-")
        mem_grid.addWidget(self.mem_total, 2, 1)

        mem_layout.addLayout(mem_grid)
        scrollable.add_widget(mem_card)

        # Disk Card
        disk_card = ModernCard()
        disk_layout = QVBoxLayout(disk_card)
        disk_layout.setSpacing(self._sp.GAP_MD)

        disk_header = QLabel("💾 Disk Usage")
        disk_header.setStyleSheet(f"color: {self._c.BLUE}; font-size: {self._ty.SIZE_MD}pt; font-weight: {self._ty.WEIGHT_BOLD};")
        disk_layout.addWidget(disk_header)

        self.disk_progress = QProgressBar()
        self.disk_progress.setRange(0, 100)
        self.disk_progress.setFormat("%p%")
        self.disk_progress.setMinimumHeight(self._sp.PROGRESS_MD)
        disk_layout.addWidget(self.disk_progress)

        disk_grid = QGridLayout()
        disk_grid.setVerticalSpacing(self._sp.GAP_SM)
        disk_grid.setHorizontalSpacing(self._sp.GAP_MD)

        disk_grid.addWidget(QLabel("Used:"), 0, 0)
        self.disk_used = ValueLabel("-")
        disk_grid.addWidget(self.disk_used, 0, 1)

        disk_grid.addWidget(QLabel("Free:"), 1, 0)
        self.disk_free = ValueLabel("-")
        disk_grid.addWidget(self.disk_free, 1, 1)

        disk_grid.addWidget(QLabel("Total:"), 2, 0)
        self.disk_total = ValueLabel("-")
        disk_grid.addWidget(self.disk_total, 2, 1)

        disk_layout.addLayout(disk_grid)
        scrollable.add_widget(disk_card)

        scrollable.add_stretch()
        return scrollable

    def _create_app_tab(self):
        """Create trading app metrics tab with modern card layout"""
        scrollable = ScrollableTabWidget()

        # Process Info Card
        process_card = ModernCard()
        process_layout = QVBoxLayout(process_card)
        process_layout.setSpacing(self._sp.GAP_MD)

        process_header = QLabel("⚙️ Process Info")
        process_header.setStyleSheet(f"color: {self._c.BLUE}; font-size: {self._ty.SIZE_MD}pt; font-weight: {self._ty.WEIGHT_BOLD};")
        process_layout.addWidget(process_header)

        process_grid = QGridLayout()
        process_grid.setVerticalSpacing(self._sp.GAP_SM)
        process_grid.setHorizontalSpacing(self._sp.GAP_MD)

        process_grid.addWidget(QLabel("PID:"), 0, 0)
        self.process_pid = ValueLabel(str(os.getpid()))
        process_grid.addWidget(self.process_pid, 0, 1)

        process_grid.addWidget(QLabel("Threads:"), 1, 0)
        self.process_threads = ValueLabel("-")
        process_grid.addWidget(self.process_threads, 1, 1)

        process_grid.addWidget(QLabel("Memory:"), 2, 0)
        self.process_memory = ValueLabel("-")
        process_grid.addWidget(self.process_memory, 2, 1)

        process_grid.addWidget(QLabel("CPU %:"), 3, 0)
        self.process_cpu = ValueLabel("-")
        process_grid.addWidget(self.process_cpu, 3, 1)

        process_grid.addWidget(QLabel("Uptime:"), 4, 0)
        self.process_uptime = ValueLabel("-")
        process_grid.addWidget(self.process_uptime, 4, 1)

        process_grid.addWidget(QLabel("Open FDs:"), 5, 0)
        self.process_fds = ValueLabel("-")
        process_grid.addWidget(self.process_fds, 5, 1)

        process_layout.addLayout(process_grid)
        scrollable.add_widget(process_card)

        # Trading Stats Card
        trading_card = ModernCard()
        trading_layout = QVBoxLayout(trading_card)
        trading_layout.setSpacing(self._sp.GAP_MD)

        trading_header = QLabel("📈 Trading Statistics")
        trading_header.setStyleSheet(f"color: {self._c.BLUE}; font-size: {self._ty.SIZE_MD}pt; font-weight: {self._ty.WEIGHT_BOLD};")
        trading_layout.addWidget(trading_header)

        trading_grid = QGridLayout()
        trading_grid.setVerticalSpacing(self._sp.GAP_SM)
        trading_grid.setHorizontalSpacing(self._sp.GAP_MD)

        # Row 0
        trading_grid.addWidget(QLabel("Msg Rate:"), 0, 0)
        self.trading_msg_rate = ValueLabel("0/s")
        trading_grid.addWidget(self.trading_msg_rate, 0, 1)

        trading_grid.addWidget(QLabel("Queue:"), 0, 2)
        self.trading_queue_size = ValueLabel("0")
        trading_grid.addWidget(self.trading_queue_size, 0, 3)

        # Row 1
        trading_grid.addWidget(QLabel("Symbols:"), 1, 0)
        self.trading_symbols = ValueLabel("0")
        trading_grid.addWidget(self.trading_symbols, 1, 1)

        trading_grid.addWidget(QLabel("Active Chain:"), 1, 2)
        self.trading_active_chain = ValueLabel("0")
        trading_grid.addWidget(self.trading_active_chain, 1, 3)

        # Row 2
        trading_grid.addWidget(QLabel("Open Orders:"), 2, 0)
        self.trading_open_orders = ValueLabel("0")
        trading_grid.addWidget(self.trading_open_orders, 2, 1)

        trading_grid.addWidget(QLabel("Position:"), 2, 2)
        self.trading_position = ValueLabel("None")
        trading_grid.addWidget(self.trading_position, 2, 3)

        # Row 3
        trading_grid.addWidget(QLabel("P&L:"), 3, 0)
        self.trading_pnl = ValueLabel("₹0.00")
        trading_grid.addWidget(self.trading_pnl, 3, 1)

        trading_grid.addWidget(QLabel("Signal:"), 3, 2)
        self.trading_signal = ValueLabel("WAIT")
        trading_grid.addWidget(self.trading_signal, 3, 3)

        trading_layout.addLayout(trading_grid)
        scrollable.add_widget(trading_card)

        # Risk Metrics Card
        risk_card = ModernCard()
        risk_layout = QVBoxLayout(risk_card)
        risk_layout.setSpacing(self._sp.GAP_MD)

        risk_header = QLabel("⚠️ Risk Metrics")
        risk_header.setStyleSheet(f"color: {self._c.BLUE}; font-size: {self._ty.SIZE_MD}pt; font-weight: {self._ty.WEIGHT_BOLD};")
        risk_layout.addWidget(risk_header)

        risk_grid = QGridLayout()
        risk_grid.setVerticalSpacing(self._sp.GAP_SM)
        risk_grid.setHorizontalSpacing(self._sp.GAP_MD)

        risk_grid.addWidget(QLabel("Trades Today:"), 0, 0)
        self.risk_trades_today = ValueLabel("0")
        risk_grid.addWidget(self.risk_trades_today, 0, 1)

        risk_grid.addWidget(QLabel("Loss Remaining:"), 0, 2)
        self.risk_loss_remaining = ValueLabel("₹5,000")
        risk_grid.addWidget(self.risk_loss_remaining, 0, 3)

        risk_grid.addWidget(QLabel("Trades Left:"), 1, 0)
        self.risk_trades_left = ValueLabel("10")
        risk_grid.addWidget(self.risk_trades_left, 1, 1)

        risk_layout.addLayout(risk_grid)
        scrollable.add_widget(risk_card)

        scrollable.add_stretch()
        return scrollable

    def _create_network_tab(self):
        """Create network statistics tab with modern card layout"""
        scrollable = ScrollableTabWidget()

        # WebSocket Card
        ws_card = ModernCard()
        ws_layout = QVBoxLayout(ws_card)
        ws_layout.setSpacing(self._sp.GAP_MD)

        ws_header = QLabel("🌐 WebSocket Connection")
        ws_header.setStyleSheet(f"color: {self._c.BLUE}; font-size: {self._ty.SIZE_MD}pt; font-weight: {self._ty.WEIGHT_BOLD};")
        ws_layout.addWidget(ws_header)

        ws_grid = QGridLayout()
        ws_grid.setVerticalSpacing(self._sp.GAP_SM)
        ws_grid.setHorizontalSpacing(self._sp.GAP_MD)

        ws_grid.addWidget(QLabel("Status:"), 0, 0)
        self.ws_status_badge = StatusBadge("Disconnected", "error")
        ws_grid.addWidget(self.ws_status_badge, 0, 1)

        ws_grid.addWidget(QLabel("Messages:"), 1, 0)
        self.ws_messages = ValueLabel("0")
        ws_grid.addWidget(self.ws_messages, 1, 1)

        ws_grid.addWidget(QLabel("Errors:"), 1, 2)
        self.ws_errors = ValueLabel("0")
        ws_grid.addWidget(self.ws_errors, 1, 3)

        ws_grid.addWidget(QLabel("Reconnects:"), 2, 0)
        self.ws_reconnects = ValueLabel("0")
        ws_grid.addWidget(self.ws_reconnects, 2, 1)

        ws_grid.addWidget(QLabel("Last Message:"), 2, 2)
        self.ws_last_msg = ValueLabel("-")
        ws_grid.addWidget(self.ws_last_msg, 2, 3)

        ws_layout.addLayout(ws_grid)
        scrollable.add_widget(ws_card)

        # Network I/O Card
        io_card = ModernCard()
        io_layout = QVBoxLayout(io_card)
        io_layout.setSpacing(self._sp.GAP_MD)

        io_header = QLabel("📡 Network I/O")
        io_header.setStyleSheet(f"color: {self._c.BLUE}; font-size: {self._ty.SIZE_MD}pt; font-weight: {self._ty.WEIGHT_BOLD};")
        io_layout.addWidget(io_header)

        io_grid = QGridLayout()
        io_grid.setVerticalSpacing(self._sp.GAP_SM)
        io_grid.setHorizontalSpacing(self._sp.GAP_MD)

        io_grid.addWidget(QLabel("Bytes Sent:"), 0, 0)
        self.net_bytes_sent = ValueLabel("0 B")
        io_grid.addWidget(self.net_bytes_sent, 0, 1)

        io_grid.addWidget(QLabel("Bytes Received:"), 0, 2)
        self.net_bytes_recv = ValueLabel("0 B")
        io_grid.addWidget(self.net_bytes_recv, 0, 3)

        io_grid.addWidget(QLabel("Packets Sent:"), 1, 0)
        self.net_packets_sent = ValueLabel("0")
        io_grid.addWidget(self.net_packets_sent, 1, 1)

        io_grid.addWidget(QLabel("Packets Received:"), 1, 2)
        self.net_packets_recv = ValueLabel("0")
        io_grid.addWidget(self.net_packets_recv, 1, 3)

        io_layout.addLayout(io_grid)
        scrollable.add_widget(io_card)

        # Connections Card
        conn_card = ModernCard()
        conn_layout = QVBoxLayout(conn_card)
        conn_layout.setSpacing(self._sp.GAP_MD)

        conn_header = QLabel("🔌 Active Connections")
        conn_header.setStyleSheet(f"color: {self._c.BLUE}; font-size: {self._ty.SIZE_MD}pt; font-weight: {self._ty.WEIGHT_BOLD};")
        conn_layout.addWidget(conn_header)

        self.conn_list = QLabel("No active connections")
        self.conn_list.setWordWrap(True)
        self.conn_list.setStyleSheet(f"color: {self._c.TEXT_DIM}; background: {self._c.BG_HOVER}; padding: {self._sp.PAD_MD}px; border-radius: {self._sp.RADIUS_MD}px;")
        conn_layout.addWidget(self.conn_list)

        scrollable.add_widget(conn_card)

        scrollable.add_stretch()
        return scrollable

    def _init_timer(self):
        """Initialize refresh timer"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)  # Refresh every 2 seconds

    def _format_bytes(self, bytes_val):
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} PB"

    def _run_garbage_collection(self):
        """Force garbage collection"""
        try:
            import gc
            before = gc.get_count()
            collected = gc.collect()
            after = gc.get_count()
            logger.info(f"GC: collected {collected} objects, counts: {before} -> {after}")
            self.refresh_btn.setText("✅ GC Complete")
            QTimer.singleShot(2000, lambda: self.refresh_btn.setText("⟳ Refresh Now"))
        except Exception as e:
            logger.error(f"[SystemMonitorPopup._run_garbage_collection] Failed: {e}")

    def _get_cached_snapshot(self) -> Dict[str, Any]:
        """Get cached snapshot to avoid excessive state_manager calls"""
        now = ist_now()
        if (self._last_snapshot_time is None or
            (now - self._last_snapshot_time).total_seconds() > self._snapshot_cache_duration):
            self._last_snapshot = state_manager.get_snapshot()
            self._last_position_snapshot = state_manager.get_position_snapshot()
            self._last_snapshot_time = now
        return self._last_snapshot

    def _update_progress_bar_colors(self):
        """Update progress bar colors based on current values"""
        try:
            c = self._c

            # CPU progress bar
            if self.cpu_progress:
                cpu_val = self.cpu_progress.value()
                if cpu_val > 90:
                    color = c.RED
                elif cpu_val > 70:
                    color = c.YELLOW
                else:
                    color = c.GREEN
                self.cpu_progress.setStyleSheet(f"""
                    QProgressBar::chunk {{ 
                        background-color: {color}; 
                        border-radius: {self._sp.RADIUS_SM}px; 
                    }}
                    QProgressBar {{
                        border: 1px solid {c.BORDER};
                        border-radius: {self._sp.RADIUS_SM}px;
                        text-align: center;
                        color: {c.TEXT_MAIN};
                    }}
                """)

            # Memory progress bar
            if self.mem_progress:
                mem_val = self.mem_progress.value()
                if mem_val > 90:
                    color = c.RED
                elif mem_val > 80:
                    color = c.YELLOW
                else:
                    color = c.GREEN
                self.mem_progress.setStyleSheet(f"""
                    QProgressBar::chunk {{ 
                        background-color: {color}; 
                        border-radius: {self._sp.RADIUS_SM}px; 
                    }}
                    QProgressBar {{
                        border: 1px solid {c.BORDER};
                        border-radius: {self._sp.RADIUS_SM}px;
                        text-align: center;
                        color: {c.TEXT_MAIN};
                    }}
                """)

            # Disk progress bar
            if self.disk_progress:
                self.disk_progress.setStyleSheet(f"""
                    QProgressBar::chunk {{ 
                        background-color: {c.PURPLE}; 
                        border-radius: {self._sp.RADIUS_SM}px; 
                    }}
                    QProgressBar {{
                        border: 1px solid {c.BORDER};
                        border-radius: {self._sp.RADIUS_SM}px;
                        text-align: center;
                        color: {c.TEXT_MAIN};
                    }}
                """)

        except Exception as e:
            logger.error(f"[SystemMonitorPopup._update_progress_bar_colors] Failed: {e}")

    def refresh(self):
        """Refresh all metrics"""
        try:
            self._refresh_system_metrics()
            self._refresh_app_metrics()
            self._refresh_network_metrics()

            # Update progress bar colors based on new values
            self._update_progress_bar_colors()

            # Update status label colors
            self._update_status_label_colors()

        except Exception as e:
            logger.error(f"[SystemMonitorPopup.refresh] Failed: {e}")

    def _update_status_label_colors(self):
        """Update status label colors based on current values"""
        try:
            c = self._c

            # WebSocket status
            if self.ws_status_badge and self.ws_status:
                is_connected = "Connected" in self.ws_status.text()
                if is_connected:
                    self.ws_status_badge.set_status("success")
                    self.ws_status_badge.setText("Connected")
                else:
                    self.ws_status_badge.set_status("error")
                    self.ws_status_badge.setText("Disconnected")

            # P&L
            if self.trading_pnl:
                pnl_text = self.trading_pnl.text().replace('₹', '').replace(',', '')
                try:
                    pnl = float(pnl_text)
                    if pnl > 0:
                        self.trading_pnl.setStyleSheet(f"""
                            QLabel#valueLabel {{
                                color: {c.GREEN};
                                background: {c.BG_HOVER};
                                border-radius: {self._sp.RADIUS_SM}px;
                                padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                                font-size: {self._ty.SIZE_SM}pt;
                                font-weight: {self._ty.WEIGHT_BOLD};
                            }}
                        """)
                    elif pnl < 0:
                        self.trading_pnl.setStyleSheet(f"""
                            QLabel#valueLabel {{
                                color: {c.RED};
                                background: {c.BG_HOVER};
                                border-radius: {self._sp.RADIUS_SM}px;
                                padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                                font-size: {self._ty.SIZE_SM}pt;
                                font-weight: {self._ty.WEIGHT_BOLD};
                            }}
                        """)
                    else:
                        self.trading_pnl.setStyleSheet(f"""
                            QLabel#valueLabel {{
                                color: {c.TEXT_MAIN};
                                background: {c.BG_HOVER};
                                border-radius: {self._sp.RADIUS_SM}px;
                                padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                                font-size: {self._ty.SIZE_SM}pt;
                                font-weight: {self._ty.WEIGHT_BOLD};
                            }}
                        """)
                except:
                    pass

        except Exception as e:
            logger.error(f"[SystemMonitorPopup._update_status_label_colors] Failed: {e}")

    def _refresh_system_metrics(self):
        """Refresh system resource metrics"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_progress.setValue(int(cpu_percent))

            # CPU frequency
            freq = psutil.cpu_freq()
            if freq:
                self.cpu_freq.setText(f"{freq.current:.0f} MHz")

            # Load average
            try:
                load_avg = psutil.getloadavg()
                self.cpu_load.setText(f"{load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}")
            except Exception:
                self.cpu_load.setText("N/A")

            # Memory
            mem = psutil.virtual_memory()
            self.mem_progress.setValue(int(mem.percent))
            self.mem_used.setText(self._format_bytes(mem.used))
            self.mem_available.setText(self._format_bytes(mem.available))
            self.mem_total.setText(self._format_bytes(mem.total))

            # Disk (current directory)
            disk = psutil.disk_usage('.')
            self.disk_progress.setValue(int(disk.used / disk.total * 100))
            self.disk_used.setText(self._format_bytes(disk.used))
            self.disk_free.setText(self._format_bytes(disk.free))
            self.disk_total.setText(self._format_bytes(disk.total))

        except Exception as e:
            logger.error(f"[SystemMonitorPopup._refresh_system_metrics] Failed: {e}")

    def _refresh_app_metrics(self):
        """Refresh trading app metrics using state_manager"""
        try:
            # Get snapshots from state manager
            snapshot = self._get_cached_snapshot()
            position_snapshot = self._last_position_snapshot

            # Process info (still from psutil)
            process = psutil.Process()

            # Threads
            self.process_threads.setText(str(process.num_threads()))

            # Memory
            mem_info = process.memory_info()
            self.process_memory.setText(self._format_bytes(mem_info.rss))

            # CPU
            self.process_cpu.setText(f"{process.cpu_percent(interval=0.1):.1f}%")

            # Uptime
            create_time = datetime.fromtimestamp(process.create_time())
            uptime = ist_now().replace(tzinfo=None) - create_time
            hours = uptime.seconds // 3600
            minutes = (uptime.seconds % 3600) // 60
            seconds = uptime.seconds % 60
            self.process_uptime.setText(f"{hours}h {minutes}m {seconds}s")

            # Open file descriptors
            try:
                self.process_fds.setText(str(len(process.open_files())))
            except Exception:
                self.process_fds.setText("N/A")

            # Trading stats from state_manager
            if self.trading_app:
                # Queue size (still from trading_app)
                if safe_hasattr(self.trading_app, '_tick_queue'):
                    self.trading_queue_size.setText(str(self.trading_app._tick_queue.qsize()))

                # Symbols from snapshot
                symbols = snapshot.get('all_symbols', [])
                if symbols is None:
                    symbols = []
                self.trading_symbols.setText(str(len(symbols)))

                # Active chain
                option_chain = snapshot.get('option_chain', {})
                if option_chain is None:
                    option_chain = {}
                active = 0
                for data in option_chain.values():
                    if data and data.get('ltp') is not None:
                        active += 1
                self.trading_active_chain.setText(str(active))

                # Open orders from snapshot
                orders = snapshot.get('orders', [])
                if orders is None:
                    orders = []
                self.trading_open_orders.setText(str(len(orders)) if orders else "0")

                # Position from position snapshot
                pos = position_snapshot.get('current_position')
                self.trading_position.setText(pos if pos else "None")

                # P&L from position snapshot
                pnl = position_snapshot.get('current_pnl', 0)
                if pnl:
                    self.trading_pnl.setText(f"₹{pnl:,.2f}")
                else:
                    self.trading_pnl.setText("₹0.00")

                # Signal from position snapshot
                signal = position_snapshot.get('option_signal', 'WAIT')
                self.trading_signal.setText(signal)

                # FEATURE 1: Risk metrics from snapshot
                max_loss = snapshot.get('max_daily_loss', -5000)
                trades_today = 1 if pos else 0
                trades_left = snapshot.get('max_trades_per_day', 10) - trades_today
                loss_remaining = abs(max_loss) - abs(pnl) if pnl and pnl < 0 else abs(max_loss)

                self.risk_trades_today.setText(str(trades_today))
                self.risk_loss_remaining.setText(f"₹{loss_remaining:,.2f}")
                self.risk_trades_left.setText(str(max(0, trades_left)))

        except Exception as e:
            logger.error(f"[SystemMonitorPopup._refresh_app_metrics] Failed: {e}")

    def _refresh_network_metrics(self):
        """Refresh network metrics"""
        try:
            c = self._c

            # WebSocket stats from app (still from trading_app)
            if self.trading_app and safe_hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                ws = self.trading_app.ws

                # Status
                if safe_hasattr(ws, 'is_connected') and ws.is_connected():
                    self.ws_status.setText("Connected")
                    if self.ws_status_badge:
                        self.ws_status_badge.set_status("success")
                        self.ws_status_badge.setText("Connected")
                else:
                    self.ws_status.setText("Disconnected")
                    if self.ws_status_badge:
                        self.ws_status_badge.set_status("error")
                        self.ws_status_badge.setText("Disconnected")

                # Statistics
                if safe_hasattr(ws, 'get_statistics'):
                    stats = ws.get_statistics()
                    self.ws_messages.setText(str(stats.get('message_count', 0)))
                    self.ws_errors.setText(str(stats.get('error_count', 0)))
                    self.ws_reconnects.setText(str(stats.get('reconnect_count', 0)))

                # Last message time
                if safe_hasattr(ws, '_last_message_time') and ws._last_message_time:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(ws._last_message_time)
                    self.ws_last_msg.setText(fmt_display(dt, time_only=True))
            else:
                self.ws_status.setText("No WebSocket")
                if self.ws_status_badge:
                    self.ws_status_badge.set_status("error")
                    self.ws_status_badge.setText("No WS")

            # Network I/O (from psutil)
            net_io = psutil.net_io_counters()
            if net_io:
                self.net_bytes_sent.setText(self._format_bytes(net_io.bytes_sent))
                self.net_bytes_recv.setText(self._format_bytes(net_io.bytes_recv))
                self.net_packets_sent.setText(str(net_io.packets_sent))
                self.net_packets_recv.setText(str(net_io.packets_recv))

            # Active connections
            try:
                connections = psutil.net_connections()
                # Filter to relevant connections (Fyers API)
                fyers_conns = [c for c in connections if c.raddr and 'fyers' in str(c.raddr).lower()]
                if fyers_conns:
                    conn_text = f"Fyers: {len(fyers_conns)} connection(s)"
                else:
                    conn_text = "No Fyers connections"
                self.conn_list.setText(conn_text)
            except (psutil.AccessDenied, psutil.Error):
                self.conn_list.setText("Connection info unavailable (need admin rights)")

        except Exception as e:
            logger.error(f"[SystemMonitorPopup._refresh_network_metrics] Failed: {e}")

    def closeEvent(self, event):
        """Handle close event - Rule 7"""
        try:
            if self.timer:
                self.timer.stop()
                self.timer = None
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[SystemMonitorPopup.closeEvent] Failed: {e}")
            super().closeEvent(event)

    def accept(self):
        """Handle accept with cleanup"""
        try:
            if self.timer:
                self.timer.stop()
                self.timer = None
            super().accept()
        except Exception as e:
            logger.error(f"[SystemMonitorPopup.accept] Failed: {e}")
            super().accept()

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            if self.timer and self.timer.isActive():
                self.timer.stop()
            self.timer = None
            self.trading_app = None
            logger.info("[SystemMonitorPopup] Cleanup completed")
        except Exception as e:
            logger.error(f"[SystemMonitorPopup.cleanup] Error: {e}", exc_info=True)