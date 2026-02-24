import csv
import logging.handlers
import os

from PyQt5.QtCore import QDate, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDateEdit, QLabel, QPushButton, QTableWidget, \
    QHeaderView, QTableWidgetItem, QMessageBox, QFileDialog

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TradeHistoryPopup(QDialog):
    """Popup window for displaying trade history"""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setWindowTitle("Trade History")
            self.resize(1200, 700)
            self.setMinimumSize(900, 500)

            # Set window flags to make it a proper popup
            self.setWindowFlags(Qt.Window)

            # EXACT stylesheet preservation
            self.setStyleSheet("""
                QDialog { background: #0d1117; color: #e6edf3; }
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
                QComboBox {
                    background: #21262d;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    border-radius: 3px;
                    padding: 5px;
                }
                QDateEdit {
                    background: #21262d;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    border-radius: 3px;
                    padding: 5px;
                }
            """)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(10)

            # Controls row
            controls_layout = QHBoxLayout()

            # Date filter
            controls_layout.addWidget(QLabel("Date:"))
            self.date_picker = QDateEdit()
            self.date_picker.setDate(QDate.currentDate())
            self.date_picker.setCalendarPopup(True)
            self.date_picker.dateChanged.connect(self.load_trades_for_date)
            controls_layout.addWidget(self.date_picker)

            controls_layout.addStretch()

            # Refresh button
            refresh_btn = QPushButton("⟳ Refresh")
            refresh_btn.clicked.connect(self.load_trades_for_date)
            controls_layout.addWidget(refresh_btn)

            # Export button
            export_btn = QPushButton("📥 Export CSV")
            export_btn.clicked.connect(self.export_trades)
            controls_layout.addWidget(export_btn)

            layout.addLayout(controls_layout)

            # Trade history table
            self.cols = ["order_id", "symbol", "side", "qty", "buy_price", "sell_price",
                         "pnl", "net_pnl", "percentage_change", "start_time", "end_time", "reason"]
            self.table = QTableWidget(0, len(self.cols))
            self.table.setHorizontalHeaderLabels(self.cols)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSortingEnabled(True)
            layout.addWidget(self.table)

            # Close button
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)

            logger.info("TradeHistoryPopup initialized")

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
        self.date_picker = None
        self.table = None
        self.cols = []
        self._current_file = None

    def load_trades_for_date(self):
        """Load trades for selected date"""
        try:
            # Rule 6: Validate widgets
            if self.date_picker is None or self.table is None:
                logger.warning("load_trades_for_date called with None widgets")
                return

            date_obj = self.date_picker.date().toPyDate()
            date_str = date_obj.strftime('%Y-%m-%d')
            trade_file = f"logs/trades_{date_str}.csv"
            self._current_file = trade_file

            # Clear table
            try:
                self.table.setRowCount(0)
            except Exception as e:
                logger.error(f"Failed to clear table: {e}", exc_info=True)
                return

            if not os.path.exists(trade_file):
                logger.info(f"No trade file found for {date_str}")
                return

            try:
                with open(trade_file, newline="", encoding='utf-8') as file:
                    reader = csv.DictReader(file)

                    # Validate CSV has headers
                    if not reader.fieldnames:
                        logger.warning(f"CSV file {trade_file} has no headers")
                        return

                    row_count = 0
                    for row in reader:
                        try:
                            # Validate row is a dict
                            if not isinstance(row, dict):
                                logger.warning(f"Skipping non-dict row: {row}")
                                continue

                            row_pos = self.table.rowCount()
                            self.table.insertRow(row_pos)

                            for col_idx, col_name in enumerate(self.cols):
                                val = row.get(col_name, "")
                                item = QTableWidgetItem(str(val))

                                # Color PnL cells
                                if col_name in ["pnl", "net_pnl"]:
                                    try:
                                        pnl_val = float(val) if val else 0
                                        if pnl_val > 0:
                                            item.setForeground(QColor("#3fb950"))
                                        elif pnl_val < 0:
                                            item.setForeground(QColor("#f85149"))
                                    except (ValueError, TypeError) as e:
                                        logger.debug(f"Failed to parse PnL value {val}: {e}")

                                self.table.setItem(row_pos, col_idx, item)
                            row_count += 1

                        except Exception as e:
                            logger.warning(f"Failed to process row: {e}", exc_info=True)
                            continue

                    logger.info(f"Loaded {row_count} trades for {date_str}")

            except FileNotFoundError as e:
                logger.error(f"File not found: {trade_file}: {e}")
            except csv.Error as e:
                logger.error(f"CSV error reading {trade_file}: {e}", exc_info=True)
            except IOError as e:
                logger.error(f"IO error reading {trade_file}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[TradeHistoryPopup.load_trades_for_date] Failed: {e}", exc_info=True)

    def export_trades(self):
        """Export current view to CSV"""
        try:
            # Rule 6: Validate table exists
            if self.table is None:
                logger.warning("export_trades called with None table")
                QMessageBox.warning(self, "Export Failed", "Table not initialized")
                return

            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export Trades", "", "CSV Files (*.csv)"
            )

            if not file_path:
                logger.debug("Export cancelled by user")
                return

            try:
                # Validate table has content
                if self.table.rowCount() == 0:
                    logger.warning("Export attempted with empty table")
                    QMessageBox.warning(self, "Export Failed", "No data to export")
                    return

                with open(file_path, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)

                    # Write headers
                    try:
                        headers = []
                        for col in range(self.table.columnCount()):
                            header_item = self.table.horizontalHeaderItem(col)
                            if header_item:
                                headers.append(header_item.text())
                            else:
                                headers.append(f"Column_{col}")
                        writer.writerow(headers)
                    except Exception as e:
                        logger.error(f"Failed to write headers: {e}", exc_info=True)
                        raise

                    # Write data
                    rows_written = 0
                    for row in range(self.table.rowCount()):
                        try:
                            row_data = []
                            for col in range(self.table.columnCount()):
                                item = self.table.item(row, col)
                                row_data.append(item.text() if item else "")
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
            except IOError as e:
                logger.error(f"IO error writing to {file_path}: {e}", exc_info=True)
                QMessageBox.critical(
                    self, "Export Failed",
                    f"Failed to write file: {e}"
                )
            except Exception as e:
                logger.error(f"Unexpected error during export: {e}", exc_info=True)
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

            # Clear table - FIXED: Use explicit None check
            if self.table is not None:
                try:
                    self.table.setRowCount(0)
                except Exception as e:
                    logger.warning(f"Error clearing table: {e}")

            # Clear references
            self.table = None
            self.date_picker = None
            self._current_file = None

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