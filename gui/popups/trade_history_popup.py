"""
trade_history_popup.py
======================
Pure PyQt5 popup for displaying trade history from database.

MODERN MINIMALIST DESIGN - Matches DailyTradeSettingGUI, BrokerageSettingGUI, etc.
FEATURE 7: Rebuilt as pure PyQt5 QDialog with period filtering and CSV export.
UPDATED: Connected to state_manager for real-time trade updates.
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

import csv
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QPushButton, QComboBox, QHeaderView, QFileDialog,
    QAbstractItemView, QGroupBox, QGridLayout, QMessageBox, QFrame, QWidget
)

from Utils.safe_getattr import safe_hasattr
from db.connector import get_db
from db.crud import orders as orders_crud

# Import state manager for trade closed signals
from data.trade_state_manager import state_manager

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

# FEATURE 7: Column definitions
COLUMNS = [
    ('Order ID',    'id',             80),
    ('Symbol',      'symbol',         150),
    ('Direction',   'position_type',  70),
    ('Qty',         'quantity',        50),
    ('Entry ₹',     'entry_price',     90),
    ('Exit ₹',      'exit_price',      90),
    ('P&L ₹',       'pnl',             90),
    ('Status',      'status',          80),
    ('Reason',      'reason_to_exit',  150),
    ('Entry Time',  'entered_at',      130),
    ('Exit Time',   'exited_at',       130),
]


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


class ValueLabel(QLabel):
    """Value label with consistent styling."""

    def __init__(self, text="--", parent=None):
        super().__init__(text, parent)
        self.setObjectName("valueLabel")
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setMinimumWidth(80)
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


class TradeHistoryPopup(QDialog, ThemedMixin):
    """
    FEATURE 7: Pure PyQt5 trade history viewer.

    Displays trade history with period filtering, summary statistics,
    and CSV export functionality.

    MODERN MINIMALIST DESIGN - Matches other dialogs.
    UPDATED: Listens to state_manager for trade closed signals to auto-refresh.
    FULLY INTEGRATED with ThemeManager for dynamic theming.
    """

    # Signal for data refresh
    data_refreshed = pyqtSignal(int)  # Number of trades loaded

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setWindowTitle('📊 Trade History')

            # Set window flags for modern look
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            self.setMinimumSize(1200, 700)
            self.resize(1300, 750)

            # Build UI
            self._build_ui()

            # Apply theme initially
            self.apply_theme()

            # Load initial data
            self.load_trades('today')

            # Connect to state manager for trade closed events
            self._connect_state_manager()

            logger.info("TradeHistoryPopup initialized with state_manager integration")

        except Exception as e:
            logger.critical(f"[TradeHistoryPopup.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._period_combo = None
        self._export_btn = None
        self._refresh_btn = None
        self._auto_refresh_btn = None
        self._table = None
        self._summary_lbl = None
        self._stats_group = None
        self._stats_labels = {}
        self._current_orders = []
        self._cleanup_done = False
        self._refresh_timer = None
        self._auto_refresh = True
        self._last_load_time = None
        self.main_card = None

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
            if hasattr(self, 'main_card'):
                self.main_card._apply_style()

            # Update table header styles
            if self._table:
                self._table.horizontalHeader().setStyleSheet(f"""
                    QHeaderView::section {{
                        background: {c.BG_HOVER};
                        color: {c.TEXT_MAIN};
                        padding: {sp.PAD_SM}px;
                        border: none;
                        border-right: 1px solid {c.BORDER};
                        border-bottom: 1px solid {c.BORDER};
                        font-weight: {self._ty.WEIGHT_BOLD};
                        font-size: {self._ty.SIZE_SM}pt;
                    }}
                """)
                self._table.verticalHeader().setStyleSheet(f"""
                    QHeaderView::section {{
                        background: {c.BG_HOVER};
                        color: {c.TEXT_DIM};
                        padding: {sp.PAD_XS}px;
                        border: none;
                        border-bottom: 1px solid {c.BORDER};
                    }}
                """)

            # Update stats labels with proper colors
            self._update_stats_colors()

            logger.debug("[TradeHistoryPopup.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[TradeHistoryPopup.apply_theme] Failed: {e}", exc_info=True)

    def _update_stats_colors(self):
        """Update statistics labels with proper colors"""
        try:
            c = self._c
            for key, label in self._stats_labels.items():
                if key == 'total_pnl':
                    # Color will be set in _update_statistics
                    continue
                elif key in ['winners', 'win_rate', 'avg_win', 'max_win']:
                    label.setStyleSheet(f"""
                        QLabel {{
                            color: {c.GREEN};
                            font-weight: {self._ty.WEIGHT_BOLD};
                            background: {c.GREEN}20;
                            padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                            border-radius: {self._sp.RADIUS_SM}px;
                        }}
                    """)
                elif key in ['losers', 'avg_loss', 'max_loss']:
                    label.setStyleSheet(f"""
                        QLabel {{
                            color: {c.RED};
                            font-weight: {self._ty.WEIGHT_BOLD};
                            background: {c.RED}20;
                            padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                            border-radius: {self._sp.RADIUS_SM}px;
                        }}
                    """)
                else:
                    label.setStyleSheet(f"""
                        QLabel {{
                            color: {c.BLUE};
                            font-weight: {self._ty.WEIGHT_BOLD};
                            background: {c.BLUE}20;
                            padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                            border-radius: {self._sp.RADIUS_SM}px;
                        }}
                    """)
        except Exception as e:
            logger.error(f"[TradeHistoryPopup._update_stats_colors] Failed: {e}", exc_info=True)

    def _build_ui(self):
        """Build the user interface"""
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
        header = ModernHeader("Trade History")
        content_layout.addWidget(header)

        # Top controls
        controls = self._build_controls()
        content_layout.addLayout(controls)

        # Statistics summary
        self._stats_group = self._build_stats_group()
        content_layout.addWidget(self._stats_group)

        # Trade table
        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels([c[0] for c in COLUMNS])
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(True)

        # Set column widths
        for i, (_, _, width) in enumerate(COLUMNS):
            self._table.setColumnWidth(i, width)

        # Make Reason column stretch
        self._table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Stretch)

        # Style the table
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background: {self._c.BG_PANEL};
                color: {self._c.TEXT_MAIN};
                gridline-color: {self._c.BORDER};
                border: 1px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
                font-size: {self._ty.SIZE_SM}pt;
                selection-background-color: {self._c.BG_SELECTED};
            }}
            QTableWidget::item {{
                padding: {self._sp.PAD_SM}px;
            }}
            QTableWidget::item:selected {{
                background-color: {self._c.BG_SELECTED};
            }}
        """)

        content_layout.addWidget(self._table, 1)

        # Bottom button bar
        button_bar = self._build_button_bar()
        content_layout.addLayout(button_bar)

        main_layout.addWidget(content)
        root.addWidget(self.main_card)

        # Auto-refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(lambda: self.load_trades(self._period_combo.currentData() if self._period_combo else 'today'))
        self._refresh_timer.start(30000)  # Refresh every 30 seconds

    def _create_title_bar(self):
        """Create custom title bar with close button."""
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet(f"background: {self._c.BG_PANEL}; border-top-left-radius: {self._sp.RADIUS_LG}px; border-top-right-radius: {self._sp.RADIUS_LG}px;")

        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(self._sp.PAD_MD, 0, self._sp.PAD_MD, 0)

        title = QLabel("📊 Trade History")
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
        close_btn.clicked.connect(self.accept)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(close_btn)

        return title_bar

    def _build_controls(self):
        """Build top control bar"""
        controls = QHBoxLayout()
        controls.setSpacing(self._sp.GAP_MD)

        # Period selector
        period_label = QLabel("📅 Period:")
        period_label.setStyleSheet(f"color: {self._c.TEXT_DIM};")
        controls.addWidget(period_label)

        self._period_combo = QComboBox()
        self._period_combo.addItem("Today", "today")
        self._period_combo.addItem("This Week", "this_week")
        self._period_combo.addItem("All Time", "all")
        self._period_combo.currentIndexChanged.connect(self._on_period_changed)
        self._period_combo.setStyleSheet(f"""
            QComboBox {{
                background: {self._c.BG_INPUT};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
                padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                min-height: {self._sp.INPUT_HEIGHT}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-width: 120px;
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
        controls.addWidget(self._period_combo)

        controls.addStretch()

        # Auto-refresh toggle
        self._auto_refresh_btn = QPushButton("🔄 Auto-refresh On")
        self._auto_refresh_btn.setCheckable(True)
        self._auto_refresh_btn.setChecked(True)
        self._auto_refresh_btn.toggled.connect(self._toggle_auto_refresh)
        self._auto_refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self._c.GREEN};
                color: white;
                border: none;
                border-radius: {self._sp.RADIUS_MD}px;
                padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                font-size: {self._ty.SIZE_BODY}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
                min-width: 160px;
                min-height: 36px;
            }}
            QPushButton:hover {{
                background: {self._c.GREEN_BRIGHT};
            }}
            QPushButton:checked {{
                background: {self._c.YELLOW};
            }}
        """)
        controls.addWidget(self._auto_refresh_btn)

        # Action buttons
        self._refresh_btn = self._create_modern_button("Refresh", primary=False, icon="⟳")
        self._refresh_btn.clicked.connect(lambda: self.load_trades(self._period_combo.currentData() if self._period_combo else 'today'))
        controls.addWidget(self._refresh_btn)

        self._export_btn = self._create_modern_button("Export CSV", primary=False, icon="📥")
        self._export_btn.clicked.connect(self._export_csv)
        controls.addWidget(self._export_btn)

        return controls

    def _build_stats_group(self):
        """Build statistics summary group with modern card styling"""
        group = ModernCard()
        layout = QVBoxLayout(group)
        layout.setSpacing(self._sp.GAP_MD)

        # Header
        header = QLabel("📈 Summary Statistics")
        header.setStyleSheet(f"color: {self._c.BLUE}; font-size: {self._ty.SIZE_MD}pt; font-weight: {self._ty.WEIGHT_BOLD};")
        layout.addWidget(header)

        # Stats grid
        grid_layout = QGridLayout()
        grid_layout.setVerticalSpacing(self._sp.GAP_SM)
        grid_layout.setHorizontalSpacing(self._sp.GAP_MD)

        stats_items = [
            ("Total Trades:", "total_trades", "0"),
            ("Total P&L:", "total_pnl", "₹0.00"),
            ("Winners:", "winners", "0"),
            ("Losers:", "losers", "0"),
            ("Win Rate:", "win_rate", "0%"),
            ("Avg Win:", "avg_win", "₹0.00"),
            ("Avg Loss:", "avg_loss", "₹0.00"),
            ("Largest Win:", "max_win", "₹0.00"),
            ("Largest Loss:", "max_loss", "₹0.00"),
            ("Profit Factor:", "profit_factor", "0.00"),
        ]

        for i, (label_text, key, default) in enumerate(stats_items):
            row, col = divmod(i, 5)
            col = col * 2

            label = QLabel(label_text)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label.setStyleSheet(f"color: {self._c.TEXT_DIM};")
            grid_layout.addWidget(label, row, col)

            value_label = QLabel(default)
            value_label.setObjectName("valueLabel")
            value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            grid_layout.addWidget(value_label, row, col + 1)

            self._stats_labels[key] = value_label

        layout.addLayout(grid_layout)
        return group

    def _build_button_bar(self):
        """Build bottom button bar"""
        button_bar = QHBoxLayout()
        button_bar.setSpacing(self._sp.GAP_MD)

        # Select All / Clear Selection buttons
        select_all_btn = self._create_modern_button("Select All", primary=False, icon="✓")
        select_all_btn.clicked.connect(self._select_all)
        button_bar.addWidget(select_all_btn)

        clear_sel_btn = self._create_modern_button("Clear", primary=False, icon="✗")
        clear_sel_btn.clicked.connect(self._clear_selection)
        button_bar.addWidget(clear_sel_btn)

        button_bar.addStretch()

        # Close button
        close_btn = self._create_modern_button("Close", primary=True, icon="✕")
        close_btn.clicked.connect(self.accept)
        button_bar.addWidget(close_btn)

        return button_bar

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            super().__init__(parent)
            self.setWindowTitle("Trade History - ERROR")
            self.setMinimumSize(400, 300)

            # Set window flags for modern look
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            root = QVBoxLayout(self)
            root.setContentsMargins(20, 20, 20, 20)

            main_card = ModernCard(self, elevated=True)
            layout = QVBoxLayout(main_card)
            layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL,
                                     self._sp.PAD_XL, self._sp.PAD_XL)

            error_label = QLabel("❌ Failed to initialize trade history popup.\nPlease check the logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet(f"color: {self._c.RED_BRIGHT}; padding: {self._sp.PAD_XL}px; font-size: {self._ty.SIZE_MD}pt;")
            layout.addWidget(error_label)

            close_btn = self._create_modern_button("Close", primary=False)
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn, 0, Qt.AlignCenter)

            root.addWidget(main_card)

        except Exception as e:
            logger.error(f"[TradeHistoryPopup._create_error_dialog] Failed: {e}", exc_info=True)

    def _connect_state_manager(self):
        """
        UPDATED: Connect to state manager for trade closed events.
        """
        try:
            # Try to connect to the state manager's trade_closed signal
            if safe_hasattr(state_manager, 'trade_closed'):
                state_manager.trade_closed.connect(self._on_trade_closed)
                logger.debug("Connected to state_manager.trade_closed signal")
        except Exception as e:
            logger.debug(f"Could not connect to state_manager.trade_closed: {e}")

    def _on_trade_closed(self, pnl: float, is_winner: bool):
        """
        UPDATED: Handle trade closed event from state manager.
        Auto-refresh if auto-refresh is enabled.
        """
        try:
            if self._cleanup_done or self._period_combo is None:
                return  # popup already cleaned up — ignore residual signal
            if self._auto_refresh:
                logger.debug(f"Trade closed (P&L: {pnl:.2f}), auto-refreshing")
                # Use QTimer.singleShot to avoid blocking the signal
                QTimer.singleShot(500, lambda: self.load_trades(
                    self._period_combo.currentData() if self._period_combo else 'today'))
        except Exception as e:
            logger.error(f"[TradeHistoryPopup._on_trade_closed] Failed: {e}", exc_info=True)

    def _toggle_auto_refresh(self, checked: bool):
        """
        UPDATED: Toggle auto-refresh on trade closed events.
        """
        try:
            if self._cleanup_done or self._auto_refresh_btn is None:
                return  # popup already cleaned up — ignore residual signal
            self._auto_refresh = checked
            if checked:
                self._auto_refresh_btn.setText("🔄 Auto-refresh On")
                self._auto_refresh_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {self._c.GREEN};
                        color: white;
                        border: none;
                        border-radius: {self._sp.RADIUS_MD}px;
                        padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                        font-size: {self._ty.SIZE_BODY}pt;
                        font-weight: {self._ty.WEIGHT_BOLD};
                        min-width: 160px;
                        min-height: 36px;
                    }}
                    QPushButton:hover {{
                        background: {self._c.GREEN_BRIGHT};
                    }}
                """)
            else:
                self._auto_refresh_btn.setText("🔄 Auto-refresh Off")
                self._auto_refresh_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {self._c.YELLOW};
                        color: black;
                        border: none;
                        border-radius: {self._sp.RADIUS_MD}px;
                        padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                        font-size: {self._ty.SIZE_BODY}pt;
                        font-weight: {self._ty.WEIGHT_BOLD};
                        min-width: 160px;
                        min-height: 36px;
                    }}
                    QPushButton:hover {{
                        background: {self._c.YELLOW_BRIGHT};
                    }}
                """)
            logger.debug(f"Auto-refresh toggled: {checked}")
        except Exception as e:
            logger.error(f"[TradeHistoryPopup._toggle_auto_refresh] Failed: {e}", exc_info=True)

    def load_trades(self, period: str = 'today'):
        """
        Load trades for the specified period.

        Args:
            period: 'today', 'this_week', or 'all'
        """
        try:
            # Guard: if cleanup() has already run, all widget refs are None — bail out
            if self._cleanup_done:
                return

            # Validate period
            if period not in ['today', 'this_week', 'all']:
                logger.warning(f"Invalid period: {period}, using 'today'")
                period = 'today'

            # Clear table
            if self._table:
                self._table.setRowCount(0)

            # Load orders from database
            db = get_db()
            orders = orders_crud.get_by_period(period, db)

            self._current_orders = orders
            self._last_load_time = datetime.now()

            if not orders:
                logger.info(f"No orders found for period: {period}")
                self._update_statistics([])
                self.data_refreshed.emit(0)
                return

            # Populate table
            self._populate_table(orders)

            # Update statistics
            self._update_statistics(orders)

            self.data_refreshed.emit(len(orders))
            logger.info(f"Loaded {len(orders)} orders for period: {period}")

        except Exception as e:
            logger.error(f"[TradeHistoryPopup.load_trades] Failed: {e}", exc_info=True)

    def _populate_table(self, orders: List[Dict[str, Any]]):
        """Populate table with order data"""
        try:
            c = self._c

            if not self._table:
                return

            self._table.setRowCount(0)

            for order in orders:
                row = self._table.rowCount()
                self._table.insertRow(row)

                for col, (_, key, _) in enumerate(COLUMNS):
                    value = order.get(key, '')

                    # Format values
                    if isinstance(value, float):
                        if key in ['entry_price', 'exit_price', 'pnl']:
                            value = f'{value:.2f}'
                        else:
                            value = str(value)
                    elif value is None:
                        value = ''
                    else:
                        value = str(value)

                    # Add ₹ symbol for price columns
                    if key in ['entry_price', 'exit_price', 'pnl'] and value:
                        value = f'₹{value}'

                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignCenter)

                    # Color P&L cells
                    if key == 'pnl':
                        try:
                            pnl = float(order.get('pnl', 0) or 0)
                            if pnl > 0:
                                item.setForeground(QColor(c.GREEN))
                                item.setBackground(QColor(c.GREEN + "20"))
                            elif pnl < 0:
                                item.setForeground(QColor(c.RED))
                                item.setBackground(QColor(c.RED + "20"))
                        except (ValueError, TypeError):
                            pass

                    # Color status cells
                    if key == 'status':
                        status = order.get('status', '')
                        if status == 'CLOSED':
                            item.setForeground(QColor(c.GREEN))
                        elif status == 'OPEN':
                            item.setForeground(QColor(c.YELLOW))
                        elif status == 'CANCELLED':
                            item.setForeground(QColor(c.TEXT_DISABLED))

                    self._table.setItem(row, col, item)

        except Exception as e:
            logger.error(f"[TradeHistoryPopup._populate_table] Failed: {e}", exc_info=True)

    def _update_statistics(self, orders: List[Dict[str, Any]]):
        """Update summary statistics"""
        try:
            c = self._c

            if not orders:
                for key in self._stats_labels:
                    if key == 'total_pnl':
                        self._stats_labels[key].setText('₹0.00')
                    elif key == 'win_rate':
                        self._stats_labels[key].setText('0%')
                    elif key in ['avg_win', 'avg_loss', 'max_win', 'max_loss']:
                        self._stats_labels[key].setText('₹0.00')
                    elif key == 'profit_factor':
                        self._stats_labels[key].setText('0.00')
                    else:
                        self._stats_labels[key].setText('0')
                return

            # Calculate statistics
            total_trades = 0
            total_pnl = 0.0
            winners = 0
            losers = 0
            wins = []
            losses = []

            for order in orders:
                # Only count closed orders for statistics
                if order.get('status') != 'CLOSED':
                    continue

                total_trades += 1
                pnl = float(order.get('pnl', 0) or 0)
                total_pnl += pnl

                if pnl > 0:
                    winners += 1
                    wins.append(pnl)
                elif pnl < 0:
                    losers += 1
                    losses.append(pnl)

            # Calculate metrics
            win_rate = (winners / total_trades * 100) if total_trades > 0 else 0
            avg_win = sum(wins) / len(wins) if wins else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            max_win = max(wins) if wins else 0
            max_loss = min(losses) if losses else 0
            profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0

            # Guard: if cleanup() ran first, all labels are gone — bail out silently
            _expected = {'total_trades','winners','losers','win_rate','avg_win',
                         'avg_loss','max_win','max_loss','profit_factor','total_pnl'}
            if not _expected.issubset(self._stats_labels.keys()):
                logger.debug("[_update_statistics] stats_labels not ready (cleanup ran?), skipping")
                return

            # Update labels
            self._stats_labels['total_trades'].setText(str(total_trades))
            self._stats_labels['winners'].setText(str(winners))
            self._stats_labels['losers'].setText(str(losers))
            self._stats_labels['win_rate'].setText(f'{win_rate:.1f}%')
            self._stats_labels['avg_win'].setText(f'₹{avg_win:.2f}')
            self._stats_labels['avg_loss'].setText(f'₹{avg_loss:.2f}')
            self._stats_labels['max_win'].setText(f'₹{max_win:.2f}')
            self._stats_labels['max_loss'].setText(f'₹{max_loss:.2f}')
            self._stats_labels['profit_factor'].setText(f'{profit_factor:.2f}')

            # Color total P&L
            total_pnl_label = self._stats_labels['total_pnl']
            total_pnl_label.setText(f'₹{total_pnl:.2f}')
            if total_pnl > 0:
                total_pnl_label.setStyleSheet(f"""
                    QLabel {{
                        color: {c.GREEN};
                        font-weight: {self._ty.WEIGHT_BOLD};
                        background: {c.GREEN}20;
                        padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                        border-radius: {self._sp.RADIUS_SM}px;
                    }}
                """)
            elif total_pnl < 0:
                total_pnl_label.setStyleSheet(f"""
                    QLabel {{
                        color: {c.RED};
                        font-weight: {self._ty.WEIGHT_BOLD};
                        background: {c.RED}20;
                        padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                        border-radius: {self._sp.RADIUS_SM}px;
                    }}
                """)
            else:
                total_pnl_label.setStyleSheet(f"""
                    QLabel {{
                        color: {c.BLUE};
                        font-weight: {self._ty.WEIGHT_BOLD};
                        background: {c.BLUE}20;
                        padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                        border-radius: {self._sp.RADIUS_SM}px;
                    }}
                """)

        except Exception as e:
            logger.error(f"[TradeHistoryPopup._update_statistics] Failed: {e}", exc_info=True)

    def _on_period_changed(self, index):
        """Handle period selection change"""
        try:
            if self._period_combo:
                period = self._period_combo.currentData()
                self.load_trades(period)
        except Exception as e:
            logger.error(f"[TradeHistoryPopup._on_period_changed] Failed: {e}", exc_info=True)

    def _export_csv(self):
        """Export current table data to CSV"""
        try:
            if not self._table or self._table.rowCount() == 0:
                QMessageBox.warning(self, "Export Failed", "No data to export")
                return

            # Generate default filename
            period = self._period_combo.currentText().lower().replace(' ', '_')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            default_filename = f"trade_history_{period}_{timestamp}.csv"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Trade History",
                default_filename,
                "CSV Files (*.csv)"
            )

            if not file_path:
                return

            try:
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)

                    # Write headers
                    writer.writerow([c[0] for c in COLUMNS])

                    # Write data
                    rows_written = 0
                    for row in range(self._table.rowCount()):
                        try:
                            row_data = []
                            for col in range(len(COLUMNS)):
                                item = self._table.item(row, col)
                                # Clean up ₹ symbol for CSV
                                text = item.text().replace('₹', '').strip() if item else ''
                                row_data.append(text)
                            writer.writerow(row_data)
                            rows_written += 1
                        except Exception as e:
                            logger.warning(f"Failed to write row {row}: {e}")
                            continue

                logger.info(f"Exported {rows_written} rows to {file_path}")
                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Exported {rows_written} trades to:\n{file_path}"
                )

            except PermissionError as e:
                logger.error(f"Permission denied: {e}")
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Permission denied. Try a different location.\n\nError: {e}"
                )
            except Exception as e:
                logger.error(f"Export failed: {e}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Error during export: {e}"
                )

        except Exception as e:
            logger.error(f"[TradeHistoryPopup._export_csv] Failed: {e}", exc_info=True)

    def _select_all(self):
        """Select all rows in table"""
        try:
            if self._table:
                self._table.selectAll()
        except Exception as e:
            logger.error(f"[TradeHistoryPopup._select_all] Failed: {e}", exc_info=True)

    def _clear_selection(self):
        """Clear current selection"""
        try:
            if self._table:
                self._table.clearSelection()
        except Exception as e:
            logger.error(f"[TradeHistoryPopup._clear_selection] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            if self._cleanup_done:
                return

            logger.info("[TradeHistoryPopup] Starting cleanup")

            # Disconnect state_manager trade_closed signal to prevent
            # _on_trade_closed from firing after cleanup via QTimer.singleShot
            try:
                if safe_hasattr(state_manager, 'trade_closed'):
                    state_manager.trade_closed.disconnect(self._on_trade_closed)
            except Exception:
                pass  # already disconnected or never connected

            # Stop timer
            if self._refresh_timer:
                try:
                    self._refresh_timer.stop()
                    self._refresh_timer = None
                except Exception as e:
                    logger.warning(f"Error stopping timer: {e}")

            # Clear table
            if self._table:
                try:
                    self._table.setRowCount(0)
                    self._table = None
                except Exception as e:
                    logger.warning(f"Error clearing table: {e}")

            # Clear data
            self._current_orders.clear()
            self._stats_labels.clear()

            # Clear references
            self._period_combo = None
            self._export_btn = None
            self._refresh_btn = None
            self._auto_refresh_btn = None
            self._stats_group = None
            self._summary_lbl = None
            self.main_card = None

            self._cleanup_done = True
            logger.info("[TradeHistoryPopup] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradeHistoryPopup.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup"""
        try:
            self.cleanup()
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[TradeHistoryPopup.closeEvent] Failed: {e}", exc_info=True)
            super().closeEvent(event)

    def accept(self):
        """Handle accept with cleanup"""
        try:
            self.cleanup()
            super().accept()
        except Exception as e:
            logger.error(f"[TradeHistoryPopup.accept] Failed: {e}", exc_info=True)
            super().accept()