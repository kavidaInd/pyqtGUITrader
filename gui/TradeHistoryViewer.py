"""
TradeHistoryViewer.py
=====================
Pure PyQt5 trade history viewer using SQLite database.

FEATURE 7: Rebuilt as pure PyQt5 QDialog with period filtering and CSV export.
"""

import logging
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QPushButton, QComboBox, QHeaderView, QFileDialog,
    QAbstractItemView, QGroupBox, QGridLayout, QMessageBox, QWidget
)

from db.connector import get_db
from db.crud import orders as orders_crud

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


class TradeHistoryViewer(QDialog):
    """
    FEATURE 7: Pure PyQt5 trade history viewer.

    Displays trade history with period filtering, summary statistics,
    and CSV export functionality.
    """

    # Rule 3: Signals for operation feedback
    data_loaded = pyqtSignal(int)  # Number of orders loaded
    export_completed = pyqtSignal(bool, str)  # success, message

    def __init__(self, parent=None, session_id: Optional[int] = None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.session_id = session_id
            self.setWindowTitle(f"📊 Trade History" + (f" - Session {session_id}" if session_id else ""))
            self.setMinimumSize(1200, 600)
            self.resize(1300, 650)
            self.setWindowFlags(Qt.Window)

            # Apply dark theme
            self._apply_dark_theme()

            # Build UI
            self._build_ui()

            # Load initial data
            if session_id:
                self.load_session_data(session_id)
            else:
                self.load_trades('today')

            # Connect signals
            self._connect_signals()

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
        self._table = None
        self._summary_lbl = None
        self._stats_group = None
        self._stats_labels = {}
        self._current_orders = []
        self._cleanup_done = False
        self._refresh_timer = None
        self._session_info_lbl = None

    def _apply_dark_theme(self):
        """Apply dark theme styling"""
        self.setStyleSheet("""
            QDialog {
                background: #0d1117;
                color: #e6edf3;
            }
            QTableWidget {
                background: #161b22;
                color: #e6edf3;
                gridline-color: #30363d;
                border: 1px solid #30363d;
                font-size: 9pt;
                selection-background-color: #1f6feb;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #1f6feb;
            }
            QHeaderView::section {
                background: #1c2128;
                color: #8b949e;
                padding: 6px;
                border: 1px solid #30363d;
                font-weight: bold;
                font-size: 9pt;
            }
            QHeaderView::section:horizontal {
                border-top: none;
                border-left: none;
                border-right: 1px solid #30363d;
                border-bottom: 1px solid #30363d;
            }
            QHeaderView::section:vertical {
                border-left: none;
                border-right: none;
                border-bottom: 1px solid #30363d;
            }
            QComboBox, QPushButton {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 9pt;
                min-width: 100px;
            }
            QComboBox:hover, QPushButton:hover {
                background: #30363d;
                border-color: #3d444d;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #8b949e;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                selection-background-color: #1f6feb;
            }
            QGroupBox {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: #e6edf3;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #8b949e;
            }
            QLabel {
                color: #8b949e;
                font-size: 9pt;
            }
            QLabel#value {
                color: #58a6ff;
                font-weight: bold;
            }
            QLabel#positive {
                color: #3fb950;
                font-weight: bold;
            }
            QLabel#negative {
                color: #f85149;
                font-weight: bold;
            }
            QLabel#sessionInfo {
                color: #58a6ff;
                font-weight: bold;
                font-size: 10pt;
                padding: 5px;
                background: #1c2128;
                border: 1px solid #30363d;
                border-radius: 4px;
            }
            QPushButton#primary {
                background: #238636;
                border: 1px solid #2ea043;
            }
            QPushButton#primary:hover {
                background: #2ea043;
            }
            QPushButton#danger {
                background: #da3633;
                border: 1px solid #f85149;
            }
            QPushButton#danger:hover {
                background: #f85149;
            }
        """)

    def _build_ui(self):
        """Build the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

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
        controls.setSpacing(10)

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

        # Action buttons
        self._refresh_btn = QPushButton("⟳ Refresh")
        self._refresh_btn.clicked.connect(self._refresh_data)
        controls.addWidget(self._refresh_btn)

        self._export_btn = QPushButton("📥 Export CSV")
        self._export_btn.setObjectName("primary")
        self._export_btn.clicked.connect(self._export_csv)
        controls.addWidget(self._export_btn)

        return controls

    def _build_stats_group(self):
        """Build statistics summary group"""
        group = QGroupBox("📈 Summary Statistics")
        layout = QGridLayout(group)

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

        # Select All / Clear Selection buttons
        select_all_btn = QPushButton("✓ Select All")
        select_all_btn.clicked.connect(self._select_all)
        button_bar.addWidget(select_all_btn)

        clear_sel_btn = QPushButton("✗ Clear Selection")
        clear_sel_btn.clicked.connect(self._clear_selection)
        button_bar.addWidget(clear_sel_btn)

        button_bar.addStretch()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setObjectName("danger")
        close_btn.clicked.connect(self.accept)
        button_bar.addWidget(close_btn)

        return button_bar

    def _connect_signals(self):
        """Connect internal signals"""
        try:
            self.data_loaded.connect(self._on_data_loaded)
            self.export_completed.connect(self._on_export_completed)
        except Exception as e:
            logger.error(f"[TradeHistoryViewer._connect_signals] Failed: {e}", exc_info=True)

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            super().__init__(parent)
            self.setWindowTitle("Trade History - ERROR")
            self.resize(400, 300)

            layout = QVBoxLayout(self)
            error_label = QLabel("❌ Failed to initialize trade history viewer.\nPlease check the logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #f85149; padding: 20px; font-size: 12pt;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)

        except Exception as e:
            logger.error(f"[TradeHistoryViewer._create_error_dialog] Failed: {e}", exc_info=True)

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
                                item.setForeground(QColor('#3fb950'))
                            elif pnl < 0:
                                item.setForeground(QColor('#f85149'))
                        except (ValueError, TypeError):
                            pass

                    # Color status cells
                    if key == 'status':
                        status = order.get('status', '')
                        if status == 'CLOSED':
                            item.setForeground(QColor('#3fb950'))
                        elif status == 'OPEN':
                            item.setForeground(QColor('#d29922'))
                        elif status == 'CANCELLED':
                            item.setForeground(QColor('#8b949e'))

                    self._table.setItem(row, col, item)

        except Exception as e:
            logger.error(f"[TradeHistoryViewer._populate_table] Failed: {e}", exc_info=True)

    def _update_statistics(self, orders: List[Dict[str, Any]]):
        """Update summary statistics"""
        try:
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
            self._stats_labels['avg_win'].setText(f'₹{avg_win:.2f}')
            self._stats_labels['avg_loss'].setText(f'₹{avg_loss:.2f}')
            self._stats_labels['max_win'].setText(f'₹{max_win:.2f}')
            self._stats_labels['max_loss'].setText(f'₹{max_loss:.2f}')
            self._stats_labels['profit_factor'].setText(f'{profit_factor:.2f}')

            # Color total P&L
            total_pnl_label = self._stats_labels['total_pnl']
            total_pnl_label.setText(f'₹{total_pnl:.2f}')
            if total_pnl > 0:
                total_pnl_label.setObjectName('positive')
            elif total_pnl < 0:
                total_pnl_label.setObjectName('negative')
            else:
                total_pnl_label.setObjectName('value')

            # Force style update
            total_pnl_label.style().unpolish(total_pnl_label)
            total_pnl_label.style().polish(total_pnl_label)

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
            dialog = QDialog(self)
            dialog.setWindowTitle(f"📋 Order Details - ID: {order.get('id')}")
            dialog.setMinimumSize(500, 500)
            dialog.setStyleSheet(self.styleSheet())

            layout = QVBoxLayout(dialog)
            layout.setSpacing(10)

            # Details grid
            grid = QGridLayout()
            grid.setVerticalSpacing(5)
            grid.setHorizontalSpacing(15)

            details = [
                ("Order ID:", str(order.get('id', ''))),
                ("Session ID:", str(order.get('session_id', ''))),
                ("Symbol:", str(order.get('symbol', ''))),
                ("Position Type:", str(order.get('position_type', ''))),
                ("Quantity:", str(order.get('quantity', ''))),
                ("Entry Price:", f"₹{float(order.get('entry_price', 0)):.2f}" if order.get('entry_price') else "N/A"),
                ("Exit Price:", f"₹{float(order.get('exit_price', 0)):.2f}" if order.get('exit_price') else "N/A"),
                ("Stop Loss:", f"₹{float(order.get('stop_loss', 0)):.2f}" if order.get('stop_loss') else "N/A"),
                ("Take Profit:", f"₹{float(order.get('take_profit', 0)):.2f}" if order.get('take_profit') else "N/A"),
                ("P&L:", f"₹{float(order.get('pnl', 0)):.2f}" if order.get('pnl') else "0.00"),
                ("Status:", str(order.get('status', ''))),
                ("Exit Reason:", str(order.get('reason_to_exit', 'N/A'))),
                ("Broker Order ID:", str(order.get('broker_order_id', 'N/A'))),
                ("Entered At:", str(order.get('entered_at', ''))),
                ("Exited At:", str(order.get('exited_at', 'N/A'))),
                ("Created At:", str(order.get('created_at', ''))),
            ]

            for i, (label, value) in enumerate(details):
                label_widget = QLabel(label)
                label_widget.setStyleSheet("font-weight: bold; color: #8b949e;")
                grid.addWidget(label_widget, i, 0)

                value_widget = QLabel(value)
                value_widget.setStyleSheet("color: #e6edf3;")

                # Color P&L value
                if label == "P&L:" and value != "N/A":
                    try:
                        pnl = float(order.get('pnl', 0))
                        if pnl > 0:
                            value_widget.setStyleSheet("color: #3fb950; font-weight: bold;")
                        elif pnl < 0:
                            value_widget.setStyleSheet("color: #f85149; font-weight: bold;")
                    except:
                        pass

                grid.addWidget(value_widget, i, 1)

            layout.addLayout(grid)

            # Close button
            close_btn = QPushButton("Close")
            close_btn.setObjectName("danger")
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
                default_filename = f"trade_history_session_{self.session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            else:
                period = self._period_combo.currentText().lower().replace(' ', '_')
                default_filename = f"trade_history_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

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