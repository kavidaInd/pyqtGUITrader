"""
trade_history_popup.py
======================
Pure PyQt5 popup for displaying trade history from database.

FEATURE 7: Rebuilt as pure PyQt5 QDialog with period filtering and CSV export.
"""

import csv
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QPushButton, QComboBox, QHeaderView, QFileDialog,
    QAbstractItemView, QGroupBox, QGridLayout, QMessageBox
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


class TradeHistoryPopup(QDialog):
    """
    FEATURE 7: Pure PyQt5 trade history viewer.

    Displays trade history with period filtering, summary statistics,
    and CSV export functionality.
    """

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setWindowTitle('📊 Trade History')
            self.setMinimumSize(1100, 520)
            self.resize(1200, 600)
            self.setWindowFlags(Qt.Window)

            # Apply dark theme
            self._apply_dark_theme()

            # Build UI
            self._build_ui()

            # Load initial data
            self.load_trades('today')

            logger.info("TradeHistoryPopup initialized")

        except Exception as e:
            logger.critical(f"[TradeHistoryPopup.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
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

        # Top controls
        controls = self._build_controls()
        layout.addLayout(controls)

        # Statistics summary
        self._stats_group = self._build_stats_group()
        layout.addWidget(self._stats_group)

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

        layout.addWidget(self._table, 1)

        # Bottom button bar
        button_bar = self._build_button_bar()
        layout.addLayout(button_bar)

        # Auto-refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(lambda: self.load_trades(self._period_combo.currentData()))
        self._refresh_timer.start(30000)  # Refresh every 30 seconds

    def _build_controls(self):
        """Build top control bar"""
        controls = QHBoxLayout()
        controls.setSpacing(10)

        # Period selector
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
        self._refresh_btn.clicked.connect(lambda: self.load_trades(self._period_combo.currentData()))
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

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        super().__init__(parent)
        self.setWindowTitle("Trade History - ERROR")
        self.resize(400, 300)

        layout = QVBoxLayout(self)
        error_label = QLabel("❌ Failed to initialize trade history popup.\nPlease check the logs.")
        error_label.setWordWrap(True)
        error_label.setStyleSheet("color: #f85149; padding: 20px; font-size: 12pt;")
        layout.addWidget(error_label)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

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
                return

            # Populate table
            self._populate_table(orders)

            # Update statistics
            self._update_statistics(orders)

            logger.info(f"Loaded {len(orders)} orders for period: {period}")

        except Exception as e:
            logger.error(f"[TradeHistoryPopup.load_trades] Failed: {e}", exc_info=True)

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
            logger.error(f"[TradeHistoryPopup._populate_table] Failed: {e}", exc_info=True)

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
            self._summary_lbl = None

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