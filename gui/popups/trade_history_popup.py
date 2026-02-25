"""
trade_history_popup_db.py
==========================
PyQt5 popup for displaying trade history from database.
"""

import csv
import logging.handlers
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from PyQt5.QtCore import QDate, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QDateEdit,
                             QLabel, QPushButton, QTableWidget, QHeaderView,
                             QTableWidgetItem, QMessageBox, QFileDialog,
                             QComboBox, QGroupBox, QGridLayout)

from db.connector import get_db
from db.crud import sessions, orders

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TradeHistoryPopup(QDialog):
    """Popup window for displaying trade history from database"""

    def __init__(self, parent=None, session_id: Optional[int] = None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.session_id = session_id
            self.setWindowTitle("Trade History" + (f" - Session {session_id}" if session_id else ""))
            self.resize(1200, 700)
            self.setMinimumSize(900, 500)

            # Set window flags to make it a proper popup
            self.setWindowFlags(Qt.Window)

            # EXACT stylesheet preservation
            self.setStyleSheet("""
                QDialog { background: #0d1117; color: #e6edf3; }
                QGroupBox { 
                    background: #161b22; 
                    color: #e6edf3;
                    border: 1px solid #30363d; 
                    border-radius: 6px;
                    margin-top: 10px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px 0 5px;
                }
                QTableWidget { 
                    background: #0d1117; 
                    color: #e6edf3;
                    gridline-color: #30363d; 
                    border: 1px solid #30363d; 
                    font-size: 9pt; 
                }
                QHeaderView::section { 
                    background: #161b22; 
                    color: #8b949e;
                    border: 1px solid #30363d; 
                    padding: 4px; 
                }
                QPushButton {
                    background: #21262d;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    border-radius: 5px;
                    padding: 8px 16px;
                }
                QPushButton:hover { background: #30363d; }
                QPushButton#primary {
                    background: #238636;
                    border: 1px solid #2ea043;
                }
                QPushButton#primary:hover { background: #2ea043; }
                QComboBox, QDateEdit {
                    background: #21262d;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    border-radius: 3px;
                    padding: 5px;
                    min-width: 120px;
                }
                QLabel {
                    color: #8b949e;
                }
            """)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(10)

            # Controls row
            controls_layout = QHBoxLayout()

            # Session selector (if no specific session)
            if not session_id:
                controls_layout.addWidget(QLabel("Session:"))
                self.session_selector = QComboBox()
                self.session_selector.setMinimumWidth(200)
                self.session_selector.currentIndexChanged.connect(self.on_session_changed)
                controls_layout.addWidget(self.session_selector)

            # Date filter
            controls_layout.addWidget(QLabel("Date:"))
            self.date_picker = QDateEdit()
            self.date_picker.setDate(QDate.currentDate())
            self.date_picker.setCalendarPopup(True)
            self.date_picker.dateChanged.connect(self.load_trades)
            controls_layout.addWidget(self.date_picker)

            # Status filter
            controls_layout.addWidget(QLabel("Status:"))
            self.status_filter = QComboBox()
            self.status_filter.addItems(["All", "OPEN", "CLOSED", "CANCELLED", "PENDING"])
            self.status_filter.currentTextChanged.connect(self.load_trades)
            controls_layout.addWidget(self.status_filter)

            controls_layout.addStretch()

            # Refresh button
            refresh_btn = QPushButton("⟳ Refresh")
            refresh_btn.setObjectName("primary")
            refresh_btn.clicked.connect(self.load_trades)
            controls_layout.addWidget(refresh_btn)

            # Export button
            export_btn = QPushButton("📥 Export CSV")
            export_btn.clicked.connect(self.export_trades)
            controls_layout.addWidget(export_btn)

            layout.addLayout(controls_layout)

            # Summary stats
            self.stats_group = QGroupBox("Session Summary")
            stats_layout = QGridLayout(self.stats_group)

            self.stats_labels = {}
            stats_items = [
                ("Total Trades:", "total_trades", "0"),
                ("Total P&L:", "total_pnl", "₹0.00"),
                ("Winning Trades:", "winning_trades", "0"),
                ("Losing Trades:", "losing_trades", "0"),
                ("Win Rate:", "win_rate", "0%"),
                ("Avg Win:", "avg_win", "₹0.00"),
                ("Avg Loss:", "avg_loss", "₹0.00"),
                ("Largest Win:", "largest_win", "₹0.00"),
                ("Largest Loss:", "largest_loss", "₹0.00"),
            ]

            for i, (label_text, key, default) in enumerate(stats_items):
                row, col = divmod(i, 3)
                label = QLabel(label_text)
                label.setStyleSheet("font-weight: bold;")
                stats_layout.addWidget(label, row, col * 2)

                value_label = QLabel(default)
                value_label.setStyleSheet("color: #e6edf3;")
                stats_layout.addWidget(value_label, row, col * 2 + 1)
                self.stats_labels[key] = value_label

            layout.addWidget(self.stats_group)

            # Trade history table
            self.cols = [
                "order_id", "symbol", "position_type", "quantity",
                "entry_price", "exit_price", "pnl", "status",
                "reason_to_exit", "entered_at", "exited_at"
            ]

            self.col_labels = {
                "order_id": "Order ID",
                "symbol": "Symbol",
                "position_type": "Side",
                "quantity": "Qty",
                "entry_price": "Entry",
                "exit_price": "Exit",
                "pnl": "P&L",
                "status": "Status",
                "reason_to_exit": "Exit Reason",
                "entered_at": "Entry Time",
                "exited_at": "Exit Time"
            }

            self.table = QTableWidget(0, len(self.cols))
            self.table.setHorizontalHeaderLabels([self.col_labels.get(col, col) for col in self.cols])
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSortingEnabled(True)
            self.table.setAlternatingRowColors(True)
            self.table.setStyleSheet("""
                QTableWidget::item:alternate { background: #161b22; }
            """)
            layout.addWidget(self.table)

            # Close button
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)

            # Load initial data
            self.load_sessions()
            self.load_trades()

            logger.info(f"TradeHistoryPopup initialized (session_id: {session_id})")

        except Exception as e:
            logger.critical(f"[TradeHistoryPopup.__init__] Failed: {e}", exc_info=True)
            # Still try to create basic dialog
            super().__init__(parent)
            self.setWindowTitle("Trade History - ERROR")
            self.setMinimumSize(400, 300)

            layout = QVBoxLayout(self)
            error_label = QLabel(f"Failed to initialize trade history popup:\n{e}")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #f85149; padding: 20px;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.session_id = None
        self.session_selector = None
        self.date_picker = None
        self.status_filter = None
        self.table = None
        self.stats_group = None
        self.stats_labels = {}
        self.cols = []
        self.col_labels = {}
        self._current_orders = []

    def load_sessions(self):
        """Load available sessions into selector"""
        try:
            if not hasattr(self, 'session_selector') or self.session_selector is None:
                return

            self.session_selector.clear()
            self.session_selector.addItem("All Sessions", None)

            db = get_db()
            recent_sessions = sessions.list_recent(limit=50, db=db)

            for session in recent_sessions:
                session_id = session["id"]
                started = session.get("started_at", "Unknown")
                mode = session.get("mode", "Unknown")
                display_text = f"Session {session_id} - {mode} ({started})"
                self.session_selector.addItem(display_text, session_id)

            logger.debug(f"Loaded {len(recent_sessions)} sessions")

        except Exception as e:
            logger.error(f"[load_sessions] Failed: {e}", exc_info=True)

    def on_session_changed(self, index):
        """Handle session selection change"""
        try:
            if self.session_selector:
                self.session_id = self.session_selector.currentData()
                self.load_trades()
        except Exception as e:
            logger.error(f"[on_session_changed] Failed: {e}", exc_info=True)

    def load_trades(self):
        """Load trades from database based on filters"""
        try:
            # Rule 6: Validate widgets
            if self.table is None:
                logger.warning("load_trades called with None table")
                return

            # Clear table
            try:
                self.table.setRowCount(0)
            except Exception as e:
                logger.error(f"Failed to clear table: {e}", exc_info=True)
                return

            db = get_db()
            selected_date = self.date_picker.date().toPyDate() if self.date_picker else datetime.now().date()
            status_filter = self.status_filter.currentText() if self.status_filter else "All"

            orders_list = []

            if self.session_id is not None:
                # Load orders for specific session
                orders_list = orders.list_for_session(self.session_id, db)
                logger.debug(f"Loading orders for session {self.session_id}")
            else:
                # Load all orders from selected date
                all_sessions = sessions.list_recent(limit=100, db=db)

                for session in all_sessions:
                    session_orders = orders.list_for_session(session["id"], db)
                    # Filter for selected date
                    for order in session_orders:
                        entered_at = order.get("entered_at", "")
                        if entered_at and entered_at.startswith(selected_date.isoformat()):
                            orders_list.append(order)

            # Apply status filter
            if status_filter != "All":
                orders_list = [o for o in orders_list if o.get("status") == status_filter]

            self._current_orders = orders_list

            if not orders_list:
                logger.info("No orders found")
                self.update_stats([])
                return

            # Insert orders into table
            row_count = 0
            for order in orders_list:
                try:
                    # Calculate P&L
                    pnl = order.get("pnl", 0)
                    if pnl is None:
                        pnl = 0

                    row_pos = self.table.rowCount()
                    self.table.insertRow(row_pos)

                    values = [
                        str(order.get("id", "")),
                        str(order.get("symbol", "")),
                        str(order.get("position_type", "")),
                        str(order.get("quantity", "")),
                        f"₹{float(order.get('entry_price', 0)):.2f}" if order.get('entry_price') else "",
                        f"₹{float(order.get('exit_price', 0)):.2f}" if order.get('exit_price') else "",
                        f"₹{float(pnl):.2f}",
                        str(order.get("status", "")),
                        str(order.get("reason_to_exit", "")),
                        str(order.get("entered_at", "")),
                        str(order.get("exited_at", ""))
                    ]

                    for col_idx, value in enumerate(values):
                        item = QTableWidgetItem(value)

                        # Color P&L cells
                        if self.cols[col_idx] == "pnl":
                            try:
                                pnl_val = float(pnl)
                                if pnl_val > 0:
                                    item.setForeground(QColor("#3fb950"))  # green
                                elif pnl_val < 0:
                                    item.setForeground(QColor("#f85149"))  # red
                            except (ValueError, TypeError):
                                pass

                        # Color status cells
                        if self.cols[col_idx] == "status":
                            status = order.get("status", "")
                            if status == "OPEN":
                                item.setForeground(QColor("#f0883e"))  # orange
                            elif status == "CLOSED":
                                item.setForeground(QColor("#3fb950"))  # green
                            elif status == "CANCELLED":
                                item.setForeground(QColor("#8b949e"))  # gray

                        self.table.setItem(row_pos, col_idx, item)

                    row_count += 1

                except Exception as e:
                    logger.warning(f"Failed to process order {order.get('id')}: {e}", exc_info=True)
                    continue

            # Update summary statistics
            self.update_stats(orders_list)

            logger.info(f"Loaded {row_count} orders for {selected_date}")

        except Exception as e:
            logger.error(f"[TradeHistoryPopup.load_trades] Failed: {e}", exc_info=True)

    def update_stats(self, orders_list: List[Dict[str, Any]]):
        """Update summary statistics display"""
        try:
            if not orders_list:
                for key in self.stats_labels:
                    if key == "total_pnl":
                        self.stats_labels[key].setText("₹0.00")
                    elif key == "win_rate":
                        self.stats_labels[key].setText("0%")
                    elif key in ["avg_win", "avg_loss", "largest_win", "largest_loss"]:
                        self.stats_labels[key].setText("₹0.00")
                    else:
                        self.stats_labels[key].setText("0")
                return

            total_trades = 0
            total_pnl = 0.0
            winning_trades = 0
            losing_trades = 0
            wins = []
            losses = []

            for order in orders_list:
                # Only count closed orders for stats
                if order.get("status") != "CLOSED":
                    continue

                total_trades += 1
                pnl = order.get("pnl", 0) or 0
                total_pnl += pnl

                if pnl > 0:
                    winning_trades += 1
                    wins.append(pnl)
                elif pnl < 0:
                    losing_trades += 1
                    losses.append(pnl)

            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            avg_win = sum(wins) / len(wins) if wins else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            largest_win = max(wins) if wins else 0
            largest_loss = min(losses) if losses else 0

            # Update labels
            self.stats_labels["total_trades"].setText(str(total_trades))
            self.stats_labels["total_pnl"].setText(f"₹{total_pnl:.2f}")
            self.stats_labels["winning_trades"].setText(str(winning_trades))
            self.stats_labels["losing_trades"].setText(str(losing_trades))
            self.stats_labels["win_rate"].setText(f"{win_rate:.1f}%")
            self.stats_labels["avg_win"].setText(f"₹{avg_win:.2f}")
            self.stats_labels["avg_loss"].setText(f"₹{avg_loss:.2f}")
            self.stats_labels["largest_win"].setText(f"₹{largest_win:.2f}")
            self.stats_labels["largest_loss"].setText(f"₹{largest_loss:.2f}")

            # Color total P&L
            if total_pnl > 0:
                self.stats_labels["total_pnl"].setStyleSheet("color: #3fb950;")
            elif total_pnl < 0:
                self.stats_labels["total_pnl"].setStyleSheet("color: #f85149;")
            else:
                self.stats_labels["total_pnl"].setStyleSheet("color: #e6edf3;")

        except Exception as e:
            logger.error(f"[update_stats] Failed: {e}", exc_info=True)

    def export_trades(self):
        """Export current view to CSV"""
        try:
            # Rule 6: Validate table exists
            if self.table is None:
                logger.warning("export_trades called with None table")
                QMessageBox.warning(self, "Export Failed", "Table not initialized")
                return

            if not self._current_orders:
                QMessageBox.warning(self, "Export Failed", "No data to export")
                return

            # Generate default filename
            date_str = self.date_picker.date().toString("yyyy-MM-dd") if self.date_picker else "unknown"
            session_part = f"_session_{self.session_id}" if self.session_id else ""
            default_filename = f"trade_export{session_part}_{date_str}.csv"

            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export Trades", default_filename, "CSV Files (*.csv)"
            )

            if not file_path:
                logger.debug("Export cancelled by user")
                return

            try:
                import os
                os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else '.', exist_ok=True)

                with open(file_path, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)

                    # Write headers
                    headers = [self.col_labels.get(col, col) for col in self.cols]
                    writer.writerow(headers)

                    # Write data
                    rows_written = 0
                    for row in range(self.table.rowCount()):
                        try:
                            row_data = []
                            for col in range(self.table.columnCount()):
                                item = self.table.item(row, col)
                                # Clean up currency symbols for CSV
                                text = item.text() if item else ""
                                text = text.replace('₹', '').strip()
                                row_data.append(text)
                            writer.writerow(row_data)
                            rows_written += 1
                        except Exception as e:
                            logger.warning(f"Failed to write row {row}: {e}")
                            continue

                logger.info(f"Exported {rows_written} rows to {file_path}")
                QMessageBox.information(
                    self, "Export Successful",
                    f"Exported {rows_written} trades to:\n{file_path}"
                )

            except PermissionError as e:
                logger.error(f"Permission denied writing to {file_path}: {e}")
                QMessageBox.critical(
                    self, "Export Failed",
                    f"Permission denied: {e}\n\nTry a different location."
                )
            except Exception as e:
                logger.error(f"Error during export: {e}", exc_info=True)
                QMessageBox.critical(
                    self, "Export Failed",
                    f"Export failed: {e}"
                )

        except Exception as e:
            logger.error(f"[TradeHistoryPopup.export_trades] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Export Failed", f"Export error: {e}")

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info("[TradeHistoryPopup] Starting cleanup")

            # Clear table
            if self.table is not None:
                try:
                    self.table.setRowCount(0)
                except Exception as e:
                    logger.warning(f"Error clearing table: {e}")

            # Clear references
            self.table = None
            self.session_selector = None
            self.date_picker = None
            self.status_filter = None
            self.stats_group = None
            self.stats_labels.clear()
            self._current_orders.clear()

            logger.info("[TradeHistoryPopup] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradeHistoryPopup.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup"""
        try:
            self.cleanup()
            event.accept()
        except Exception as e:
            logger.error(f"[TradeHistoryPopup.closeEvent] Failed: {e}", exc_info=True)
            event.accept()

    def accept(self):
        """Handle accept with cleanup"""
        try:
            self.cleanup()
            super().accept()
        except Exception as e:
            logger.error(f"[TradeHistoryPopup.accept] Failed: {e}", exc_info=True)
            super().accept()