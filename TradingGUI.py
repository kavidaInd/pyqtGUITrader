# PYQT: Complete replacement for Tkinter TradingGUI.py
import sys
import threading
import logging
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QRadioButton, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QMenuBar, QAction,
    QMessageBox, QApplication, QLabel, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
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

# PYQT: Import converted dialog classes (to be converted separately)
from gui.BrokerageSettingGUI import BrokerageSettingGUI
from gui.DailyTradeSettingGUI import DailyTradeSettingGUI
from gui.ProfitStoplossSettingGUI import ProfitStoplossSettingGUI
from gui.StrategySettingGUI import StrategySettingGUI
from gui.FyersManualLoginPopup import FyersManualLoginPopup


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
            QTabWidget::pane { border: 1px solid #30363d; }
            QTabBar::tab { background: #161b22; color: #8b949e;
                          padding: 8px 16px; border: 1px solid #30363d; }
            QTabBar::tab:selected { background: #21262d; color: #e6edf3;
                                    border-bottom: 2px solid #58a6ff; }
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
        """# PYQT: Build main window layout"""
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top splitter: chart (left) + controls (right) ─────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background: #30363d; }")

        # Left: chart
        self.chart_widget = ChartWidget()
        self.chart_widget.setMinimumWidth(600)
        splitter.addWidget(self.chart_widget)

        # Right: mode toggle + status + buttons
        right_panel = self._build_right_panel()
        right_panel.setFixedWidth(340)
        splitter.addWidget(right_panel)

        splitter.setSizes([1060, 340])
        root_layout.addWidget(splitter, stretch=3)

        # ── Bottom: tab widget ─────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 9))
        self._build_tabs()
        root_layout.addWidget(self.tabs, stretch=2)

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

    def _build_tabs(self):
        """# PYQT: Build bottom tabs"""
        # ── Log tab
        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumBlockCount(1000)  # PYQT: cap to avoid memory growth
        self.log_widget.setFont(QFont("Consolas", 9))
        self.log_widget.setStyleSheet(
            "background:#0d1117; color:#58a6ff; border:none;"
        )
        self.tabs.addTab(self.log_widget, "📝 Logs")

        # ── Trade history tab
        self.history_table = self._make_history_table()
        self.tabs.addTab(self.history_table, "Trade History")

        # ── Stats tab (populated after trading app is created)
        self.stats_tab_widget = None  # created in _init_trading_app

    def _make_history_table(self) -> QTableWidget:
        """# PYQT: Create trade history table"""
        cols = ["order_id", "symbol", "side", "qty", "buy_price", "sell_price",
                "pnl", "net_pnl", "percentage_change", "reason"]
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setStyleSheet("""
            QTableWidget { background:#0d1117; color:#e6edf3;
                          gridline-color:#30363d; border:none; font-size:9pt; }
            QHeaderView::section { background:#161b22; color:#8b949e;
                                  border:1px solid #30363d; padding:4px; }
        """)
        return t

    def _setup_timers(self):
        """# PYQT: QTimer always fires on the main thread — safe to update widgets"""
        self.timer_fast = QTimer(self)
        self.timer_fast.timeout.connect(self._tick_fast)
        self.timer_fast.start(1000)  # 1s — status, stats, logs

        # CHART FIX: Use longer interval and debounce
        self.timer_chart = QTimer(self)
        self.timer_chart.timeout.connect(self._tick_chart)
        self.timer_chart.start(5000)  # 5s - less frequent updates
        self._last_chart_fp = ""  # Track last fingerprint
        self._chart_update_pending = False  # Prevent overlapping updates

    @pyqtSlot()
    def _tick_fast(self):
        """# PYQT: Runs on main thread — safe to update all widgets"""
        if self.trading_app is None:
            return
        state = self.trading_app.state
        self.status_panel.refresh(state, self.config)
        if self.stats_tab_widget:
            self.stats_tab_widget.refresh()
        self._update_trade_history()
        self._update_button_states()

    @pyqtSlot()
    def _tick_chart(self):
        """# PYQT: Update chart with throttling to prevent flicker"""
        if self._chart_update_pending:
            return  # Skip if update already in progress

        if self.trading_app is None:
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

    def _update_trade_history(self):
        """# PYQT: Refresh trade history table from today's CSV"""
        import os
        from datetime import datetime
        import csv

        today_file = f"logs/trades_{datetime.now().strftime('%Y-%m-%d')}.csv"
        self.history_table.setRowCount(0)

        if not os.path.exists(today_file):
            return

        try:
            with open(today_file, newline="") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    row_pos = self.history_table.rowCount()
                    self.history_table.insertRow(row_pos)

                    cols = ["order_id", "symbol", "side", "qty", "buy_price", "sell_price",
                            "pnl", "net_pnl", "percentage_change", "reason"]

                    for col_idx, col_name in enumerate(cols):
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
                        self.history_table.setItem(row_pos, col_idx, item)
        except Exception as e:
            logging.error(f"Failed to load trade history: {e}")

    def _init_trading_app(self):
        """# PYQT: Create the trading app instance"""
        try:
            self.trading_app = TradingApp(
                config=self.config,
                broker_setting=self.brokerage_setting,
            )
            # Add Stats tab now that state exists
            self.stats_tab_widget = StatsTab(self.trading_app.state)
            self.tabs.addTab(self.stats_tab_widget, "📊 Stats")
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
        self.log_widget.appendPlainText(message)
        # Auto-scroll to bottom
        sb = self.log_widget.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _create_menu(self):
        """# PYQT: Build menu bar"""
        menubar = self.menuBar()
        menubar.setStyleSheet(
            "QMenuBar { background:#161b22; color:#e6edf3; }"
            "QMenuBar::item:selected { background:#21262d; }"
            "QMenu { background:#161b22; color:#e6edf3; border:1px solid #30363d; }"
            "QMenu::item:selected { background:#21262d; }"
        )

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

        help_menu = menubar.addMenu("Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    # Settings dialog openers — keep identical names to Tkinter version
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
            # Replace stats tab
            if self.stats_tab_widget:
                idx = self.tabs.indexOf(self.stats_tab_widget)
                new_stats = StatsTab(self.trading_app.state)
                self.tabs.removeTab(idx)
                self.tabs.insertTab(idx, new_stats, "📊 Stats")
                self.stats_tab_widget = new_stats
            QMessageBox.information(self, "Reloaded", "Broker reloaded successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Reload Error", str(e))

    def _show_about(self):
        QMessageBox.about(self, "About",
                          "Algo Trading Dashboard\nVersion 2.0 (PyQt5)\n\n"
                          "© 2025 Your Company. All rights reserved.")

    def closeEvent(self, event):
        """# PYQT: Stop timers and engine before closing"""
        self.timer_fast.stop()
        self.timer_chart.stop()
        if self.app_running and self.trading_thread:
            threading.Thread(target=self.trading_thread.stop,
                             daemon=True, name="CloseStop").start()
        event.accept()