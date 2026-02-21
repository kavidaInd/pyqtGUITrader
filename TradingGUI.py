# PYQT: Complete replacement for Tkinter TradingGUI.py
import sys
import threading
import logging
import os
from datetime import datetime
import csv
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QRadioButton, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QMenuBar, QAction,
    QMessageBox, QApplication, QLabel, QSizePolicy, QDialog,
    QDialogButtonBox, QVBoxLayout, QDateEdit
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QDate
from PyQt5.QtGui import QFont, QColor

# PYQT: Import existing trading engine (unchanged)
import BaseEnums
from gui.chart_widget import ChartWidget
from gui.log_handler import QtLogHandler
from gui.stats_tab import StatsTab
from gui.status_panel import StatusPanel
from new_main import TradingApp
from config import Config
from gui.BrokerageSetting import BrokerageSetting
from gui.DailyTradeSetting import DailyTradeSetting
from gui.ProfitStoplossSetting import ProfitStoplossSetting
from gui.StrategySetting import StrategySetting

# PYQT: Import new PyQt5 components
from trading_thread import TradingThread

# PYQT: Import converted dialog classes
from gui.BrokerageSettingGUI import BrokerageSettingGUI
from gui.DailyTradeSettingGUI import DailyTradeSettingGUI
from gui.ProfitStoplossSettingGUI import ProfitStoplossSettingGUI
from gui.StrategySettingGUI import StrategySettingGUI
from gui.FyersManualLoginPopup import FyersManualLoginPopup


# FIX: New popup windows for log, history, and stats
class LogPopup(QDialog):
    """Popup window for displaying logs"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Viewer")
        self.resize(1000, 700)
        self.setMinimumSize(800, 500)

        # Set window flags to make it a proper popup
        self.setWindowFlags(Qt.Window)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog { background: #0d1117; color: #e6edf3; }
            QPlainTextEdit { 
                background: #0d1117; 
                color: #58a6ff; 
                border: 1px solid #30363d;
                font-family: Consolas;
                font-size: 10pt;
            }
            QPushButton {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover { background: #30363d; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Log widget
        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumBlockCount(5000)
        layout.addWidget(self.log_widget)

        # Button row
        button_box = QDialogButtonBox()
        clear_btn = QPushButton("Clear Logs")
        clear_btn.clicked.connect(self.clear_logs)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        button_box.addButton(clear_btn, QDialogButtonBox.ActionRole)
        button_box.addButton(close_btn, QDialogButtonBox.AcceptRole)
        layout.addWidget(button_box)

    def append_log(self, message: str):
        """Append a log message to the widget"""
        self.log_widget.appendPlainText(message)
        # Auto-scroll to bottom
        sb = self.log_widget.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_logs(self):
        """Clear all logs"""
        self.log_widget.clear()


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


class StatsPopup(QDialog):
    """Popup window for displaying statistics"""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Trading Statistics")
        self.resize(900, 700)
        self.setMinimumSize(700, 500)

        # Set window flags to make it a proper popup
        self.setWindowFlags(Qt.Window)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog { background: #0d1117; color: #e6edf3; }
            QTabWidget::pane { border: 1px solid #30363d; }
            QTabBar::tab { background: #161b22; color: #8b949e;
                          padding: 8px 16px; border: 1px solid #30363d; }
            QTabBar::tab:selected { background: #21262d; color: #e6edf3;
                                    border-bottom: 2px solid #58a6ff; }
            QLabel { color: #e6edf3; font-size: 10pt; }
            QLabel[cssClass="value"] { color: #58a6ff; font-weight: bold; }
            QLabel[cssClass="positive"] { color: #3fb950; }
            QLabel[cssClass="negative"] { color: #f85149; }
            QGroupBox {
                border: 1px solid #30363d;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover { background: #30363d; }
        """)

        layout = QVBoxLayout(self)

        # Import StatsTab and add it
        from gui.stats_tab import StatsTab
        self.stats_tab = StatsTab(self.state)
        layout.addWidget(self.stats_tab)

        # Refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(2000)  # Refresh every 2 seconds

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def refresh(self):
        """Refresh statistics"""
        if hasattr(self.stats_tab, 'refresh'):
            self.stats_tab.refresh()

    def closeEvent(self, event):
        """Stop timer when closing"""
        self.refresh_timer.stop()
        event.accept()


class TradingGUI(QMainWindow):
    """# PYQT: Main window - replaces Tkinter TradingGUI class"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Algo Trading Dashboard")
        self.resize(1400, 850)
        self.setMinimumSize(1100, 700)

        # Dark base style
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #0d1117; color: #e6edf3; }
            QPushButton { border-radius: 5px; padding: 8px 16px;
                         font-weight: bold; font-size: 10pt; }
            QPushButton:disabled { background: #21262d; color: #484f58; }
        """)

        # Settings objects
        self.config = Config()
        self.brokerage_setting = BrokerageSetting()
        self.daily_setting = DailyTradeSetting()
        self.profit_loss_setting = ProfitStoplossSetting()
        self.strategy_setting = StrategySetting()

        # Runtime state
        self.app_running = False
        self.trading_mode = "algo"  # "algo" | "manual"
        self.trading_app = None
        self.trading_thread = None

        # Popup windows
        self.log_popup = None
        self.history_popup = None
        self.stats_popup = None

        # FIX: Cache for trade history file modification time
        self._trade_file_mtime = 0
        self._last_loaded_trade_data = None  # Optional: cache the actual data if needed

        # Build UI
        self._setup_log_handler()
        self._create_menu()
        self._build_layout()
        self._setup_timers()
        self._init_trading_app()

    def _setup_log_handler(self):
        """# PYQT: Connect Qt log signal to the log widget slot"""
        self._log_handler = QtLogHandler()
        self._log_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        self._log_handler.signaller.log_message.connect(self._append_log)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        # Remove stale handlers from previous runs
        for h in list(root_logger.handlers):
            if isinstance(h, QtLogHandler):
                root_logger.removeHandler(h)
        root_logger.addHandler(self._log_handler)

    def _build_layout(self):
        """# PYQT: Build main window layout - now only with chart and controls"""
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top splitter: chart (left) + controls (right) ─────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background: #30363d; }")

        # Left: chart - now taking more space
        self.chart_widget = ChartWidget()
        self.chart_widget.setMinimumWidth(800)
        splitter.addWidget(self.chart_widget)

        # Right: mode toggle + status + buttons
        right_panel = self._build_right_panel()
        right_panel.setFixedWidth(340)
        splitter.addWidget(right_panel)

        splitter.setSizes([1060, 340])
        root_layout.addWidget(splitter)

    def _build_right_panel(self) -> QWidget:
        """# PYQT: Build right panel with status and controls"""
        panel = QWidget()
        panel.setStyleSheet("background: #0d1117;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Mode toggle
        mode_row = QHBoxLayout()
        lbl = QLabel("Mode:")
        lbl.setStyleSheet("color: #8b949e; font-size: 9pt;")
        self.radio_algo = QRadioButton("⚡ Algo")
        self.radio_manual = QRadioButton("🖐 Manual")
        self.radio_algo.setChecked(True)
        self.radio_algo.toggled.connect(self._on_mode_change)
        for rb in [self.radio_algo, self.radio_manual]:
            rb.setStyleSheet("color: #e6edf3; font-size: 9pt;")
        mode_row.addWidget(lbl)
        mode_row.addWidget(self.radio_algo)
        mode_row.addWidget(self.radio_manual)
        layout.addLayout(mode_row)

        # Status panel
        self.status_panel = StatusPanel()
        layout.addWidget(self.status_panel)

        # Buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)

        def make_btn(text, color, hover):
            b = QPushButton(text)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {color}; color: #fff;
                    border-radius: 5px; padding: 9px;
                }}
                QPushButton:hover {{ background: {hover}; }}
                QPushButton:disabled {{ background: #21262d; color: #484f58; }}
            """)
            return b

        self.btn_start = make_btn("▶  Start App", "#238636", "#2ea043")
        self.btn_stop = make_btn("■  Stop App", "#da3633", "#f85149")
        self.btn_call = make_btn("📈  Buy Call", "#1f6feb", "#388bfd")
        self.btn_put = make_btn("📉  Buy Put", "#6e40c9", "#8957e5")
        self.btn_exit = make_btn("🚪  Exit Position", "#9e6a03", "#d29922")

        self.btn_stop.setDisabled(True)
        self.btn_call.setDisabled(True)
        self.btn_put.setDisabled(True)
        self.btn_exit.setDisabled(True)

        self.btn_start.clicked.connect(self._start_app)
        self.btn_stop.clicked.connect(self._stop_app)
        self.btn_call.clicked.connect(lambda: self._manual_buy(BaseEnums.CALL))
        self.btn_put.clicked.connect(lambda: self._manual_buy(BaseEnums.PUT))
        self.btn_exit.clicked.connect(self._manual_exit)

        for b in [self.btn_start, self.btn_stop, self.btn_call, self.btn_put, self.btn_exit]:
            btn_layout.addWidget(b)

        layout.addLayout(btn_layout)
        layout.addStretch()
        return panel

    def _setup_timers(self):
        """# PYQT: QTimer always fires on the main thread — safe to update widgets"""
        self.timer_fast = QTimer(self)
        self.timer_fast.timeout.connect(self._tick_fast)
        self.timer_fast.start(1000)  # 1s — status, stats

        # CHART FIX: Use longer interval and debounce
        self.timer_chart = QTimer(self)
        self.timer_chart.timeout.connect(self._tick_chart)
        self.timer_chart.start(5000)  # 5s - chart updates and trade history
        self._last_chart_fp = ""  # Track last fingerprint
        self._chart_update_pending = False  # Prevent overlapping updates

    @pyqtSlot()
    def _tick_fast(self):
        """# PYQT: Runs on main thread — safe to update all widgets"""
        if self.trading_app is None:
            return
        state = self.trading_app.state
        self.status_panel.refresh(state, self.config)

        # Update popups if they're open
        if self.stats_popup and self.stats_popup.isVisible():
            self.stats_popup.refresh()

        self._update_button_states()

    @pyqtSlot()
    def _tick_chart(self):
        """# PYQT: Update chart and trade history with throttling"""
        if self.trading_app is None:
            return

        # Update chart
        self._update_chart_if_needed()

        # FIX: Update trade history on 5-second timer instead of 1-second
        self._update_trade_history()

    def _update_chart_if_needed(self):
        """Update chart only if data has changed"""
        if self._chart_update_pending:
            return

        trend_data = getattr(self.trading_app.state, "derivative_trend", {}) or {}
        if not trend_data:
            return

        # Create fingerprint to detect real changes
        try:
            close = trend_data.get("close") or []
            fp = f"{len(close)}:{close[-1] if close else None}"

            if fp != self._last_chart_fp:
                self._last_chart_fp = fp
                self._chart_update_pending = True
                # Schedule update with small delay to batch rapid changes
                QTimer.singleShot(100, self._do_chart_update)
        except:
            # If fingerprint fails, still update but throttle
            if not self._chart_update_pending:
                self._chart_update_pending = True
                QTimer.singleShot(100, self._do_chart_update)

    def _do_chart_update(self):
        """# PYQT: Actually perform chart update"""
        try:
            if self.trading_app:
                trend_data = getattr(self.trading_app.state, "derivative_trend", {}) or {}
                if trend_data:
                    self.chart_widget.update_chart(trend_data)
        finally:
            self._chart_update_pending = False

    def _update_button_states(self):
        """# PYQT: Enable/disable buttons based on app state"""
        state = self.trading_app.state if self.trading_app else None
        has_pos = bool(state and getattr(state, "current_position", None))
        manual = self.trading_mode == "manual"

        self.btn_start.setDisabled(self.app_running)
        self.btn_stop.setDisabled(not self.app_running)

        if self.app_running and manual:
            self.btn_call.setDisabled(has_pos)
            self.btn_put.setDisabled(has_pos)
            self.btn_exit.setDisabled(not has_pos)
        else:
            self.btn_call.setDisabled(True)
            self.btn_put.setDisabled(True)
            self.btn_exit.setDisabled(True)

    def _init_trading_app(self):
        """# PYQT: Create the trading app instance"""
        try:
            self.trading_app = TradingApp(
                config=self.config,
                broker_setting=self.brokerage_setting,
            )
        except Exception as e:
            logging.critical(f"Failed to create TradingApp: {e}", exc_info=True)
            QMessageBox.critical(self, "Init Error",
                                 f"Could not connect to broker:\n{e}\n\n"
                                 "Check credentials via Settings → Brokerage Settings.")

    @pyqtSlot()
    def _start_app(self):
        """# PYQT: Start trading engine on QThread"""
        if self.trading_app is None:
            QMessageBox.critical(self, "Error", "Trading app not initialised.")
            return
        # PYQT: Run trading engine on QThread — never on main thread
        self.trading_thread = TradingThread(self.trading_app)
        self.trading_thread.error_occurred.connect(self._on_engine_error)
        self.trading_thread.finished.connect(self._on_engine_finished)
        self.trading_thread.start()
        self.app_running = True
        self._update_button_states()

    @pyqtSlot()
    def _stop_app(self):
        """# PYQT: Stop the trading engine"""
        self.btn_stop.setDisabled(True)
        # PYQT: Stop is blocking — run on a plain daemon thread, not main thread
        threading.Thread(target=self._threaded_stop, daemon=True, name="StopThread").start()

    def _threaded_stop(self):
        """# PYQT: Background stop work"""
        if self.trading_thread:
            self.trading_thread.stop()
        # PYQT: Post result back to main thread via QTimer.singleShot
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._on_engine_finished)

    @pyqtSlot()
    def _on_engine_finished(self):
        """# PYQT: Slot — always called on main thread"""
        self.app_running = False
        self._update_button_states()

    @pyqtSlot(str)
    def _on_engine_error(self, message: str):
        """# PYQT: Slot — always called on main thread"""
        self.app_running = False
        self._update_button_states()

        # FIX: Show specific message for token expiration
        if "Token expired" in message:
            QMessageBox.critical(
                self,
                "Token Expired",
                f"{message}\n\nPlease go to Settings → Manual Fyers Login to re-authenticate."
            )
        else:
            QMessageBox.critical(self, "Engine Error", f"Trading engine crashed:\n{message}")

    def _manual_buy(self, option_type):
        """# PYQT: Manual buy in background thread"""
        if self.trading_mode != "manual":
            QMessageBox.information(self, "Mode", "Switch to Manual mode first.")
            return
        if not self.trading_app:
            return
        threading.Thread(
            target=lambda: self.trading_app.executor.buy_option(
                self.trading_app.state, option_type=option_type),
            daemon=True
        ).start()

    def _manual_exit(self):
        """# PYQT: Manual exit in background thread"""
        if self.trading_mode != "manual":
            QMessageBox.information(self, "Mode", "Switch to Manual mode first.")
            return
        if not self.trading_app:
            return
        threading.Thread(
            target=lambda: self.trading_app.executor.exit_position(
                self.trading_app.state, reason="Manual Exit"),
            daemon=True
        ).start()

    @pyqtSlot()
    def _on_mode_change(self):
        """# PYQT: Handle mode switch"""
        self.trading_mode = "algo" if self.radio_algo.isChecked() else "manual"
        self._update_button_states()

    @pyqtSlot(str)
    def _append_log(self, message: str):
        """# PYQT: Connected to QtLogHandler signal — always on main thread"""
        # Also append to popup if it's open
        if self.log_popup and self.log_popup.isVisible():
            self.log_popup.append_log(message)

    def _create_menu(self):
        """# PYQT: Build menu bar with View menu for popups"""
        menubar = self.menuBar()
        menubar.setStyleSheet(
            "QMenuBar { background:#161b22; color:#e6edf3; }"
            "QMenuBar::item:selected { background:#21262d; }"
            "QMenu { background:#161b22; color:#e6edf3; border:1px solid #30363d; }"
            "QMenu::item:selected { background:#21262d; }"
        )

        # File menu
        file_menu = menubar.addMenu("File")
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # View menu - for popups
        view_menu = menubar.addMenu("View")

        log_act = QAction("📝 Show Logs", self)
        log_act.triggered.connect(self._show_log_popup)
        view_menu.addAction(log_act)

        history_act = QAction("📊 Show Trade History", self)
        history_act.triggered.connect(self._show_history_popup)
        view_menu.addAction(history_act)

        stats_act = QAction("📈 Show Statistics", self)
        stats_act.triggered.connect(self._show_stats_popup)
        view_menu.addAction(stats_act)

        view_menu.addSeparator()

        close_all_act = QAction("Close All Popups", self)
        close_all_act.triggered.connect(self._close_all_popups)
        view_menu.addAction(close_all_act)

        # Settings menu
        settings_menu = menubar.addMenu("Settings")
        actions = [
            ("Strategy Settings", self._open_strategy),
            ("Daily Trade Settings", self._open_daily),
            ("Profit & Loss Settings", self._open_pnl),
            ("Brokerage Settings", self._open_brokerage),
            ("Manual Fyers Login", self._open_login),
        ]
        for label, slot in actions:
            act = QAction(label, self)
            act.triggered.connect(slot)
            settings_menu.addAction(act)

        # Help menu
        help_menu = menubar.addMenu("Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    # Popup window handlers
    def _show_log_popup(self):
        """Show log popup window"""
        if not self.log_popup:
            self.log_popup = LogPopup(self)
        self.log_popup.show()
        self.log_popup.raise_()
        self.log_popup.activateWindow()

    def _show_history_popup(self):
        """Show trade history popup window"""
        if not self.history_popup:
            self.history_popup = TradeHistoryPopup(self)
        self.history_popup.load_trades_for_date()
        self.history_popup.show()
        self.history_popup.raise_()
        self.history_popup.activateWindow()

    def _show_stats_popup(self):
        """Show statistics popup window"""
        if self.trading_app:
            if not self.stats_popup:
                self.stats_popup = StatsPopup(self.trading_app.state, self)
            self.stats_popup.show()
            self.stats_popup.raise_()
            self.stats_popup.activateWindow()
        else:
            QMessageBox.information(self, "Not Ready", "Trading app not initialized yet.")

    def _close_all_popups(self):
        """Close all popup windows"""
        if self.log_popup:
            self.log_popup.close()
        if self.history_popup:
            self.history_popup.close()
        if self.stats_popup:
            self.stats_popup.close()

    # Settings dialog openers
    def _open_strategy(self):
        dlg = StrategySettingGUI(self, self.strategy_setting)
        dlg.exec_()

    def _open_daily(self):
        dlg = DailyTradeSettingGUI(self, daily_setting=self.daily_setting,
                                   app=self.trading_app)
        dlg.exec_()

    def _open_pnl(self):
        dlg = ProfitStoplossSettingGUI(self, profit_stoploss_setting=self.profit_loss_setting,
                                       app=self.trading_app)
        dlg.exec_()

    def _open_brokerage(self):
        dlg = BrokerageSettingGUI(self, self.brokerage_setting)
        dlg.exec_()

    def _open_login(self):
        dlg = FyersManualLoginPopup(self, self.brokerage_setting)
        dlg.exec_()
        self._reload_broker()

    def _reload_broker(self):
        """# PYQT: Reload after login"""
        try:
            self.trading_app = TradingApp(
                config=self.config,
                broker_setting=self.brokerage_setting,
            )
            QMessageBox.information(self, "Reloaded", "Broker reloaded successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Reload Error", str(e))

    def _show_about(self):
        QMessageBox.about(self, "About",
                          "Algo Trading Dashboard\nVersion 2.0 (PyQt5)\n\n"
                          "© 2025 Your Company. All rights reserved.")

    # FIX: Optimized trade history update with mtime caching
    def _update_trade_history(self):
        """# PYQT: Refresh trade history table only if file changed"""
        today_file = f"logs/trades_{datetime.now().strftime('%Y-%m-%d')}.csv"

        # Check if file exists
        if not os.path.exists(today_file):
            self.history_popup = None  # Reset popup reference
            return

        try:
            # Get current modification time
            current_mtime = os.path.getmtime(today_file)

            # Only reload if file has been modified
            if current_mtime != self._trade_file_mtime:
                self._trade_file_mtime = current_mtime

                # If history popup exists and is visible, update it
                if self.history_popup and self.history_popup.isVisible():
                    self.history_popup.load_trades_for_date()

        except (OSError, IOError) as e:
            logging.error(f"Failed to check trade file mtime: {e}")

    def closeEvent(self, event):
        """# PYQT: Stop timers, close popups, and stop engine before closing"""
        self.timer_fast.stop()
        self.timer_chart.stop()

        # Close all popups
        self._close_all_popups()

        if self.app_running and self.trading_thread:
            threading.Thread(target=self.trading_thread.stop,
                             daemon=True, name="CloseStop").start()
        event.accept()