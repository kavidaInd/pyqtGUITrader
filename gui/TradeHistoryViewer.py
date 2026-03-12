"""
TradeHistoryViewer.py
=====================
Pure PyQt5 trade history viewer using SQLite database.

FEATURE 7: Rebuilt as pure PyQt5 QDialog with period filtering and CSV export.
UPDATED: Connected to state_manager for real-time trade updates with null-safe operations.
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

import logging
import csv
from datetime import datetime
from Utils.time_utils import IST, ist_now, fmt_display, fmt_stamp
from typing import List, Dict, Any, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from gui.dialog_base import ThemedDialog, ThemedMixin, ModernCard, make_separator, make_scrollbar_ss, create_section_header, create_modern_button, apply_tab_style, build_title_bar
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QPushButton, QComboBox, QHeaderView, QFileDialog,
    QAbstractItemView, QGroupBox, QGridLayout, QMessageBox, QWidget, QFrame
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


class TradeHistoryViewer(ThemedDialog):
    """
    FEATURE 7: Pure PyQt5 trade history viewer.

    Displays trade history with period filtering, summary statistics,
    and CSV export functionality.

    UPDATED: Listens to state_manager for trade closed signals to auto-refresh
    with null-safe operations and ThemeManager integration.
    """

    # Rule 3: Signals for operation feedback
    data_loaded = pyqtSignal(int)  # Number of orders loaded
    export_completed = pyqtSignal(bool, str)  # success, message

    def __init__(self, parent=None, session_id: Optional[int] = None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent, title="TRADE HISTORY VIEWER", icon="TH", size=(1200, 800))

            # Rule 13.2: Connect to theme and density signals

            self.session_id = session_id
            self.setWindowTitle(f"📊 Trade History" + (f" - Session {session_id}" if session_id else ""))
            self.setMinimumSize(1200, 600)
            self.resize(1300, 650)
            self.setWindowFlags(Qt.Window)

            # Build UI (without hardcoded styles)
            self._build_ui()

            # Apply theme initially
            self.apply_theme()

            # Load initial data
            if session_id:
                self.load_session_data(session_id)
            else:
                self.load_trades('today')

            # Connect signals
            self._connect_signals()

            # UPDATED: Connect to state manager for trade closed events
            self._connect_state_manager()

            logger.info(f"TradeHistoryViewer initialized (session_id: {session_id})")

        except Exception as e:
            logger.critical(f"[TradeHistoryViewer.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.session_id = None
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
        self._session_info_lbl = None
        self._auto_refresh = True
        self._last_load_time = None

    # =========================================================================
    # Shorthand properties for theme tokens
    # =========================================================================
    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the dialog.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Apply main stylesheet
            self.setStyleSheet(self._get_stylesheet())

            # Update object names for special buttons
            if self._auto_refresh_btn:
                self._auto_refresh_btn.setStyleSheet(self._get_button_style("warning"))

            if self._export_btn:
                self._export_btn.setStyleSheet(self._get_button_style("primary"))

            if safe_hasattr(self, 'close_btn') and self.close_btn:
                self.close_btn.setStyleSheet(self._get_button_style("danger"))

            # Update stats labels with proper colors
            self._update_stats_colors()

            logger.debug("[TradeHistoryViewer.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[TradeHistoryViewer.apply_theme] Failed: {e}", exc_info=True)

    def _get_stylesheet(self) -> str:
        """Generate stylesheet with current theme tokens"""
        c = self._c
        ty = self._ty
        sp = self._sp

        return f"""
            QDialog {{
                background: {c.BG_MAIN};
                color: {c.TEXT_MAIN};
            }}
            QComboBox {{
                background: {c.BG_CARD};
                color: {c.TEXT_MAIN};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
                padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                min-height: {sp.BTN_HEIGHT_SM}px;
            }}
            QComboBox:focus {{ border-color: {c.BLUE}; }}
            QComboBox::drop-down {{ border: none; }}
            QScrollBar:vertical {{
                background: {c.BG_PANEL}; width: 8px; border-radius: 4px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {c.BORDER}; min-height: 20px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {c.BORDER_STRONG}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QTableWidget {{
                background: {c.BG_PANEL};
                color: {c.TEXT_MAIN};
                gridline-color: {c.BORDER};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                font-size: {ty.SIZE_SM}pt;
                selection-background-color: {c.BG_SELECTED};
            }}
            QTableWidget::item {{
                padding: {sp.PAD_XS}px;
            }}
            QTableWidget::item:selected {{
                background-color: {c.BG_SELECTED};
            }}
            QHeaderView::section {{
                background: {c.BG_HOVER};
                color: {c.TEXT_DIM};
                padding: {sp.PAD_XS}px;
                border: {sp.SEPARATOR}px solid {c.BORDER};
                font-weight: {ty.WEIGHT_BOLD};
                font-size: {ty.SIZE_XS}pt;
            }}
            QHeaderView::section:horizontal {{
                border-top: none;
                border-left: none;
                border-right: {sp.SEPARATOR}px solid {c.BORDER};
                border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
            }}
            QHeaderView::section:vertical {{
                border-left: none;
                border-right: none;
                border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
            }}
            QComboBox, QPushButton {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
                padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                font-size: {ty.SIZE_SM}pt;
                min-width: 100px;
            }}
            QComboBox:hover, QPushButton:hover {{
                background: {c.BORDER};
                border-color: {c.BORDER_STRONG};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: {sp.PAD_XS}px solid transparent;
                border-right: {sp.PAD_XS}px solid transparent;
                border-top: {sp.PAD_XS}px solid {c.TEXT_DIM};
                margin-right: {sp.PAD_XS}px;
            }}
            QComboBox QAbstractItemView {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                selection-background-color: {c.BG_SELECTED};
            }}
            QGroupBox {{
                background: {c.BG_PANEL};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                margin-top: {sp.PAD_MD}px;
                font-weight: {ty.WEIGHT_BOLD};
                color: {c.TEXT_MAIN};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {sp.PAD_MD}px;
                padding: 0 {sp.PAD_XS}px 0 {sp.PAD_XS}px;
                color: {c.TEXT_DIM};
            }}
            QLabel {{
                color: {c.TEXT_DIM};
                font-size: {ty.SIZE_SM}pt;
            }}
            QLabel#value {{
                color: {c.BLUE};
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QLabel#positive {{
                color: {c.GREEN};
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QLabel#negative {{
                color: {c.RED};
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QLabel#sessionInfo {{
                color: {c.BLUE};
                font-weight: {ty.WEIGHT_BOLD};
                font-size: {ty.SIZE_BODY}pt;
                padding: {sp.PAD_XS}px;
                background: {c.BG_HOVER};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
            }}
        """

    def _get_button_style(self, button_type: str) -> str:
        """Get styled button for specific types"""
        c = self._c
        sp = self._sp
        ty = self._ty

        if button_type == "primary":
            bg = c.GREEN
            bg_hover = c.GREEN_BRIGHT
            border = c.GREEN_BRIGHT
        elif button_type == "danger":
            bg = c.RED
            bg_hover = c.RED_BRIGHT
            border = c.RED_BRIGHT
        elif button_type == "warning":
            bg = c.YELLOW
            bg_hover = c.YELLOW_BRIGHT
            border = c.YELLOW_BRIGHT
        else:
            bg = c.BG_HOVER
            bg_hover = c.BORDER
            border = c.BORDER

        return f"""
            QPushButton {{
                background: {bg};
                color: {c.TEXT_INVERSE};
                border: {sp.SEPARATOR}px solid {border};
                border-radius: {sp.RADIUS_SM}px;
                padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                font-size: {ty.SIZE_SM}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QPushButton:hover {{
                background: {bg_hover};
            }}
            QPushButton:disabled {{
                background: {c.BG_HOVER};
                color: {c.TEXT_DISABLED};
                border: {sp.SEPARATOR}px solid {c.BORDER};
            }}
        """

    def _update_stats_colors(self):
        """Update statistics labels with proper colors"""
        try:
            c = self._c
            for key, label in self._stats_labels.items():
                if key == 'total_pnl':
                    # Color will be set in _update_statistics
                    continue
                elif key in ['winners', 'win_rate', 'avg_win', 'max_win']:
                    label.setStyleSheet(f"color: {c.GREEN}; font-weight: {self._ty.WEIGHT_BOLD};")
                elif key in ['losers', 'avg_loss', 'max_loss']:
                    label.setStyleSheet(f"color: {c.RED}; font-weight: {self._ty.WEIGHT_BOLD};")
                else:
                    label.setStyleSheet(f"color: {c.BLUE}; font-weight: {self._ty.WEIGHT_BOLD};")
        except Exception as e:
            logger.error(f"[TradeHistoryViewer._update_stats_colors] Failed: {e}", exc_info=True)

    def _build_ui(self):
        """Build the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD)
        layout.setSpacing(self._sp.GAP_MD)

        # Session info (if viewing specific session)
        if self.session_id:
            self._session_info_lbl = QLabel(f"📊 Viewing Session: {self.session_id}")
            self._session_info_lbl.setObjectName("sessionInfo")
            layout.addWidget(self._session_info_lbl)

        # Top controls
        controls = self._build_controls()
        layout.addLayout(controls)

        # Statistics summary
        self._stats_group = self._build_stats_group()
        layout.addWidget(self._stats_group)

        # Trade table
        self._build_table()
        layout.addWidget(self._table, 1)

        # Bottom button bar
        button_bar = self._build_button_bar()
        layout.addLayout(button_bar)

        # Auto-refresh timer (only if not viewing a specific session)
        if not self.session_id:
            self._refresh_timer = QTimer(self)
            self._refresh_timer.timeout.connect(lambda: self.load_trades(self._period_combo.currentData()))
            self._refresh_timer.start(30000)  # Refresh every 30 seconds

    def _build_controls(self):
        """Build top control bar"""
        controls = QHBoxLayout()
        controls.setSpacing(self._sp.GAP_MD)

        # Period selector (only if not viewing a specific session)
        if not self.session_id:
            controls.addWidget(QLabel("📅 Period:"))
            self._period_combo = QComboBox()
            self._period_combo.addItem("Today", "today")
            self._period_combo.addItem("This Week", "this_week")
            self._period_combo.addItem("All Time", "all")
            self._period_combo.currentIndexChanged.connect(self._on_period_changed)
            controls.addWidget(self._period_combo)

            controls.addStretch()

        # Auto-refresh toggle
        self._auto_refresh_btn = QPushButton("🔄 Auto-refresh On")
        self._auto_refresh_btn.setCheckable(True)
        self._auto_refresh_btn.setChecked(True)
        self._auto_refresh_btn.clicked.connect(self._toggle_auto_refresh)
        controls.addWidget(self._auto_refresh_btn)

        # Action buttons
        self._refresh_btn = QPushButton("⟳ Refresh")
        self._refresh_btn.clicked.connect(self._refresh_data)
        controls.addWidget(self._refresh_btn)

        self._export_btn = QPushButton("📥 Export CSV")
        self._export_btn.clicked.connect(self._export_csv)
        controls.addWidget(self._export_btn)

        return controls

    def _build_stats_group(self):
        """Build statistics summary group"""
        group = QGroupBox("📈 Summary Statistics")
        layout = QGridLayout(group)
        layout.setVerticalSpacing(self._sp.GAP_XS)
        layout.setHorizontalSpacing(self._sp.GAP_MD)

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
            layout.addWidget(label, row, col)

            value_label = QLabel(default)
            value_label.setObjectName("value")
            value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            layout.addWidget(value_label, row, col + 1)

            self._stats_labels[key] = value_label

        return group

    def _build_table(self):
        """Build the trade table"""
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

        # Connect double-click to show details
        self._table.doubleClicked.connect(self._show_order_details)

    def _build_button_bar(self):
        """Build bottom button bar"""
        button_bar = QHBoxLayout()
        button_bar.setSpacing(self._sp.GAP_MD)

        # Select All / Clear Selection buttons
        select_all_btn = QPushButton("✓ Select All")
        select_all_btn.clicked.connect(self._select_all)
        button_bar.addWidget(select_all_btn)

        clear_sel_btn = QPushButton("✗ Clear Selection")
        clear_sel_btn.clicked.connect(self._clear_selection)
        button_bar.addWidget(clear_sel_btn)

        button_bar.addStretch()

        # Close button
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        button_bar.addWidget(self.close_btn)

        return button_bar

    def _connect_signals(self):
        """Connect internal signals"""
        try:
            self.data_loaded.connect(self._on_data_loaded)
            self.export_completed.connect(self._on_export_completed)
        except Exception as e:
            logger.error(f"[TradeHistoryViewer._connect_signals] Failed: {e}", exc_info=True)

    def _connect_state_manager(self):
        """
        UPDATED: Connect to state manager for trade closed events.
        """
        try:
            # Note: This assumes state_manager has a trade_closed signal
            # If not, we'll need to create a signal in the manager
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
            if self._auto_refresh:
                logger.debug(f"Trade closed (P&L: {pnl:.2f}), auto-refreshing")
                # Use QTimer.singleShot to avoid blocking the signal
                QTimer.singleShot(500, self._refresh_data)
        except Exception as e:
            logger.error(f"[TradeHistoryViewer._on_trade_closed] Failed: {e}", exc_info=True)

    def _toggle_auto_refresh(self, checked: bool):
        """
        UPDATED: Toggle auto-refresh on trade closed events.
        """
        try:
            self._auto_refresh = checked
            if checked:
                self._auto_refresh_btn.setText("🔄 Auto-refresh On")
            else:
                self._auto_refresh_btn.setText("🔄 Auto-refresh Off")
            logger.debug(f"Auto-refresh toggled: {checked}")
        except Exception as e:
            logger.error(f"[TradeHistoryViewer._toggle_auto_refresh] Failed: {e}", exc_info=True)

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            super().__init__(parent)
            self.resize(400, 300)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL, self._sp.PAD_XL, self._sp.PAD_XL)

            error_label = QLabel("❌ Failed to initialize trade history viewer.\nPlease check the logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet(f"color: {self._c.RED_BRIGHT}; padding: {self._sp.PAD_XL}px; font-size: {self._ty.SIZE_MD}pt;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.setStyleSheet(self._get_button_style("danger"))
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)

        except Exception as e:
            logger.error(f"[TradeHistoryViewer._create_error_dialog] Failed: {e}", exc_info=True)

    # ── Null-safe helper methods ───────────────────────────────────────────

    def _safe_get_float(self, data: Dict[str, Any], key: str, default: float = 0.0) -> float:
        """Safely get float value from dictionary"""
        try:
            value = data.get(key)
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    def _safe_get_str(self, data: Dict[str, Any], key: str, default: str = "") -> str:
        """Safely get string value from dictionary"""
        try:
            value = data.get(key)
            if value is None:
                return default
            return str(value)
        except Exception:
            return default

    def _safe_get_int(self, data: Dict[str, Any], key: str, default: int = 0) -> int:
        """Safely get integer value from dictionary"""
        try:
            value = data.get(key)
            if value is None:
                return default
            return int(value)
        except (ValueError, TypeError):
            return default

    def _fmt_currency(self, value: Any) -> str:
        """Format value as currency"""
        try:
            if value is None:
                return "—"
            val = float(value)
            if abs(val) >= 1000:
                return f"₹{val:,.0f}"
            return f"₹{val:.2f}"
        except (ValueError, TypeError):
            return str(value) if value else "—"

    def _fmt_percent(self, value: Any) -> str:
        """Format value as percentage"""
        try:
            if value is None:
                return "—"
            val = float(value)
            return f"{val:.1f}%"
        except (ValueError, TypeError):
            return str(value) if value else "—"

    # ── Data loading methods ───────────────────────────────────────────────

    def load_trades(self, period: str = 'today'):
        """
        Load trades for the specified period.

        Args:
            period: 'today', 'this_week', or 'all'
        """
        try:
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
            self._last_load_time = ist_now()

            if not orders:
                logger.info(f"No orders found for period: {period}")
                self._update_statistics([])
                self.data_loaded.emit(0)
                return

            # Populate table
            self._populate_table(orders)

            # Update statistics
            self._update_statistics(orders)

            self.data_loaded.emit(len(orders))
            logger.info(f"Loaded {len(orders)} orders for period: {period}")

        except Exception as e:
            logger.error(f"[TradeHistoryViewer.load_trades] Failed: {e}", exc_info=True)

    def load_session_data(self, session_id: int):
        """
        Load trades for a specific session.

        Args:
            session_id: Session ID to load
        """
        try:
            # Clear table
            if self._table:
                self._table.setRowCount(0)

            # Load orders from database
            db = get_db()
            orders = orders_crud.list_for_session(session_id, db)

            self._current_orders = orders
            self._last_load_time = ist_now()

            if not orders:
                logger.info(f"No orders found for session: {session_id}")
                self._update_statistics([])
                self.data_loaded.emit(0)
                return

            # Populate table
            self._populate_table(orders)

            # Update statistics
            self._update_statistics(orders)

            self.data_loaded.emit(len(orders))
            logger.info(f"Loaded {len(orders)} orders for session: {session_id}")

        except Exception as e:
            logger.error(f"[TradeHistoryViewer.load_session_data] Failed: {e}", exc_info=True)

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
                            elif pnl < 0:
                                item.setForeground(QColor(c.RED))
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
            logger.error(f"[TradeHistoryViewer._populate_table] Failed: {e}", exc_info=True)

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

            # Update labels
            self._stats_labels['total_trades'].setText(str(total_trades))
            self._stats_labels['winners'].setText(str(winners))
            self._stats_labels['losers'].setText(str(losers))
            self._stats_labels['win_rate'].setText(f'{win_rate:.1f}%')
            self._stats_labels['avg_win'].setText(self._fmt_currency(avg_win))
            self._stats_labels['avg_loss'].setText(self._fmt_currency(abs(avg_loss)))
            self._stats_labels['max_win'].setText(self._fmt_currency(max_win))
            self._stats_labels['max_loss'].setText(self._fmt_currency(abs(max_loss)))
            self._stats_labels['profit_factor'].setText(f'{profit_factor:.2f}')

            # Color total P&L
            total_pnl_label = self._stats_labels['total_pnl']
            total_pnl_label.setText(self._fmt_currency(total_pnl))
            if total_pnl > 0:
                total_pnl_label.setStyleSheet(f"color: {c.GREEN}; font-weight: {self._ty.WEIGHT_BOLD};")
            elif total_pnl < 0:
                total_pnl_label.setStyleSheet(f"color: {c.RED}; font-weight: {self._ty.WEIGHT_BOLD};")
            else:
                total_pnl_label.setStyleSheet(f"color: {c.BLUE}; font-weight: {self._ty.WEIGHT_BOLD};")

        except Exception as e:
            logger.error(f"[TradeHistoryViewer._update_statistics] Failed: {e}", exc_info=True)

    def _show_order_details(self, index):
        """Show detailed order information on double-click"""
        try:
            row = index.row()
            if row < 0 or row >= len(self._current_orders):
                return

            order = self._current_orders[row]
            self._show_order_details_popup(order)

        except Exception as e:
            logger.error(f"[TradeHistoryViewer._show_order_details] Failed: {e}", exc_info=True)

    def _show_order_details_popup(self, order: Dict[str, Any]):
        """Create a popup with order details"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            dialog = QDialog(self)
            dialog.setWindowTitle(f"📋 Order Details - ID: {order.get('id')}")
            dialog.setMinimumSize(500, 500)
            dialog.setStyleSheet(self.styleSheet())

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(sp.PAD_LG, sp.PAD_LG, sp.PAD_LG, sp.PAD_LG)
            layout.setSpacing(sp.GAP_MD)

            # Details grid
            grid = QGridLayout()
            grid.setVerticalSpacing(sp.GAP_XS)
            grid.setHorizontalSpacing(sp.GAP_LG)

            details = [
                ("Order ID:", self._safe_get_str(order, 'id', 'N/A')),
                ("Session ID:", self._safe_get_str(order, 'session_id', 'N/A')),
                ("Symbol:", self._safe_get_str(order, 'symbol', 'N/A')),
                ("Position Type:", self._safe_get_str(order, 'position_type', 'N/A')),
                ("Quantity:", self._safe_get_str(order, 'quantity', 'N/A')),
                ("Entry Price:", self._fmt_currency(self._safe_get_float(order, 'entry_price'))),
                ("Exit Price:", self._fmt_currency(self._safe_get_float(order, 'exit_price'))),
                ("Stop Loss:", self._fmt_currency(self._safe_get_float(order, 'stop_loss'))),
                ("Take Profit:", self._fmt_currency(self._safe_get_float(order, 'take_profit'))),
                ("P&L:", self._fmt_currency(self._safe_get_float(order, 'pnl'))),
                ("Status:", self._safe_get_str(order, 'status', 'N/A')),
                ("Exit Reason:", self._safe_get_str(order, 'reason_to_exit', 'N/A')),
                ("Broker Order ID:", self._safe_get_str(order, 'broker_order_id', 'N/A')),
                ("Entered At:", self._safe_get_str(order, 'entered_at', 'N/A')),
                ("Exited At:", self._safe_get_str(order, 'exited_at', 'N/A')),
                ("Created At:", self._safe_get_str(order, 'created_at', 'N/A')),
            ]

            for i, (label_text, value) in enumerate(details):
                label_widget = QLabel(label_text)
                label_widget.setStyleSheet(f"font-weight: {ty.WEIGHT_BOLD}; color: {c.TEXT_DIM};")
                grid.addWidget(label_widget, i, 0)

                value_widget = QLabel(value)
                value_widget.setStyleSheet(f"color: {c.TEXT_MAIN};")
                value_widget.setWordWrap(True)

                # Color P&L value
                if "P&L:" in label_text and value != "N/A":
                    try:
                        pnl = float(order.get('pnl', 0))
                        if pnl > 0:
                            value_widget.setStyleSheet(f"color: {c.GREEN}; font-weight: {ty.WEIGHT_BOLD};")
                        elif pnl < 0:
                            value_widget.setStyleSheet(f"color: {c.RED}; font-weight: {ty.WEIGHT_BOLD};")
                    except Exception:
                        pass

                grid.addWidget(value_widget, i, 1)

            layout.addLayout(grid)

            # Close button
            close_btn = QPushButton("Close")
            close_btn.setStyleSheet(self._get_button_style("danger"))
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)

            dialog.exec_()

        except Exception as e:
            logger.error(f"[TradeHistoryViewer._show_order_details_popup] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to show order details: {e}")

    def _on_period_changed(self, index):
        """Handle period selection change"""
        try:
            if self._period_combo:
                period = self._period_combo.currentData()
                self.load_trades(period)
        except Exception as e:
            logger.error(f"[TradeHistoryViewer._on_period_changed] Failed: {e}", exc_info=True)

    def _refresh_data(self):
        """Refresh data based on current mode"""
        try:
            if self.session_id:
                self.load_session_data(self.session_id)
            elif self._period_combo:
                period = self._period_combo.currentData()
                self.load_trades(period)
        except Exception as e:
            logger.error(f"[TradeHistoryViewer._refresh_data] Failed: {e}", exc_info=True)

    def _export_csv(self):
        """Export current table data to CSV"""
        try:
            if not self._table or self._table.rowCount() == 0:
                QMessageBox.warning(self, "Export Failed", "No data to export")
                return

            # Generate default filename
            if self.session_id:
                default_filename = f"trade_history_session_{self.session_id}_{ist_now().strftime('%Y%m%d_%H%M%S')}.csv"
            else:
                period = self._period_combo.currentText().lower().replace(' ', '_')
                default_filename = f"trade_history_{period}_{ist_now().strftime('%Y%m%d_%H%M%S')}.csv"

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
                self.export_completed.emit(True, f"Exported {rows_written} rows")
                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Exported {rows_written} trades to:\n{file_path}"
                )

            except PermissionError as e:
                logger.error(f"Permission denied: {e}")
                self.export_completed.emit(False, "Permission denied")
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Permission denied. Try a different location.\n\nError: {e}"
                )
            except Exception as e:
                logger.error(f"Export failed: {e}", exc_info=True)
                self.export_completed.emit(False, str(e))
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Error during export: {e}"
                )

        except Exception as e:
            logger.error(f"[TradeHistoryViewer._export_csv] Failed: {e}", exc_info=True)

    def _select_all(self):
        """Select all rows in table"""
        try:
            if self._table:
                self._table.selectAll()
        except Exception as e:
            logger.error(f"[TradeHistoryViewer._select_all] Failed: {e}", exc_info=True)

    def _clear_selection(self):
        """Clear current selection"""
        try:
            if self._table:
                self._table.clearSelection()
        except Exception as e:
            logger.error(f"[TradeHistoryViewer._clear_selection] Failed: {e}", exc_info=True)

    def _on_data_loaded(self, count: int):
        """Handle data loaded signal"""
        try:
            if self._session_info_lbl and self.session_id:
                self._session_info_lbl.setText(f"📊 Viewing Session: {self.session_id} ({count} trades)")
        except Exception as e:
            logger.error(f"[TradeHistoryViewer._on_data_loaded] Failed: {e}", exc_info=True)

    def _on_export_completed(self, success: bool, message: str):
        """Handle export completed signal"""
        try:
            if success:
                logger.info(f"Export successful: {message}")
            else:
                logger.error(f"Export failed: {message}")
        except Exception as e:
            logger.error(f"[TradeHistoryViewer._on_export_completed] Failed: {e}", exc_info=True)

    def get_session_summary(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Calculate and return summary statistics for a session.

        Args:
            session_id: Session ID (uses current session if None)

        Returns:
            Dict[str, Any]: Summary statistics
        """
        default_summary = {
            'total_trades': 0,
            'total_pnl': 0.0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
            'profit_factor': 0.0
        }

        try:
            session_id = session_id or self.session_id
            if session_id is None:
                return default_summary

            db = get_db()
            order_list = orders_crud.list_for_session(session_id, db)

            if not order_list:
                return default_summary

            total_trades = 0
            total_pnl = 0.0
            winners = 0
            losers = 0
            wins = []
            losses = []

            for order in order_list:
                # Only count closed orders
                if order.get("status") not in ["CLOSED"]:
                    continue

                total_trades += 1
                pnl = float(order.get("pnl", 0) or 0)
                total_pnl += pnl

                if pnl > 0:
                    winners += 1
                    wins.append(pnl)
                elif pnl < 0:
                    losers += 1
                    losses.append(pnl)

            win_rate = (winners / total_trades * 100) if total_trades > 0 else 0.0
            avg_win = sum(wins) / len(wins) if wins else 0.0
            avg_loss = sum(losses) / len(losses) if losses else 0.0
            largest_win = max(wins) if wins else 0.0
            largest_loss = min(losses) if losses else 0.0
            profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0.0

            return {
                'total_trades': total_trades,
                'total_pnl': round(total_pnl, 2),
                'winning_trades': winners,
                'losing_trades': losers,
                'win_rate': round(win_rate, 2),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'largest_win': round(largest_win, 2),
                'largest_loss': round(largest_loss, 2),
                'profit_factor': round(profit_factor, 2)
            }

        except Exception as e:
            logger.error(f"Error calculating session summary: {e}", exc_info=True)
            return default_summary

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            if self._cleanup_done:
                return

            logger.info("[TradeHistoryViewer] Starting cleanup")

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
            self._session_info_lbl = None

            self._cleanup_done = True
            logger.info("[TradeHistoryViewer] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradeHistoryViewer.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup"""
        try:
            self.cleanup()
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[TradeHistoryViewer.closeEvent] Failed: {e}", exc_info=True)
            super().closeEvent(event)

    def accept(self):
        """Handle accept with cleanup"""
        try:
            self.cleanup()
            super().accept()
        except Exception as e:
            logger.error(f"[TradeHistoryViewer.accept] Failed: {e}", exc_info=True)
            super().accept()