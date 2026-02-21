import csv
import logging
import os

from PyQt5.QtCore import QDate, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDateEdit, QLabel, QPushButton, QTableWidget, \
    QHeaderView, QTableWidgetItem, QMessageBox


class TradeHistoryPopup(QDialog):
    """Popup window for displaying trade history"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trade History")
        self.resize(1200, 700)
        self.setMinimumSize(900, 500)

        # Set window flags to make it a proper popup
        self.setWindowFlags(Qt.Window)

        # Apply dark theme
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
        cols = ["order_id", "symbol", "side", "qty", "buy_price", "sell_price",
                "pnl", "net_pnl", "percentage_change", "start_time", "end_time", "reason"]
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def load_trades_for_date(self):
        """Load trades for selected date"""
        date_obj = self.date_picker.date().toPyDate()
        date_str = date_obj.strftime('%Y-%m-%d')
        trade_file = f"logs/trades_{date_str}.csv"

        self.table.setRowCount(0)

        if not os.path.exists(trade_file):
            return

        try:
            with open(trade_file, newline="") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    row_pos = self.table.rowCount()
                    self.table.insertRow(row_pos)

                    for col_idx, col_name in enumerate([
                        "order_id", "symbol", "side", "qty", "buy_price", "sell_price",
                        "pnl", "net_pnl", "percentage_change", "start_time", "end_time", "reason"
                    ]):
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
                            except:
                                pass

                        self.table.setItem(row_pos, col_idx, item)
        except Exception as e:
            logging.error(f"Failed to load trade history: {e}")

    def export_trades(self):
        """Export current view to CSV"""
        from PyQt5.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Trades", "", "CSV Files (*.csv)"
        )

        if file_path:
            try:
                with open(file_path, 'w', newline='') as file:
                    writer = csv.writer(file)
                    # Write headers
                    headers = []
                    for col in range(self.table.columnCount()):
                        headers.append(self.table.horizontalHeaderItem(col).text())
                    writer.writerow(headers)

                    # Write data
                    for row in range(self.table.rowCount()):
                        row_data = []
                        for col in range(self.table.columnCount()):
                            item = self.table.item(row, col)
                            row_data.append(item.text() if item else "")
                        writer.writerow(row_data)

                QMessageBox.information(self, "Export Successful",
                                        f"Trades exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", str(e))
