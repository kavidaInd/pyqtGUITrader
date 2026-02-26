import logging
import logging.handlers
import os
import sys
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List

from PyQt5.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QHBoxLayout, QVBoxLayout,
    QPushButton, QRadioButton, QAction, QMessageBox, QLabel,
    QFrame, QApplication, QTabWidget, QMenu
)

import BaseEnums
from config import Config
from gui.BrokerageSetting import BrokerageSetting
from gui.BrokerageSettingGUI import BrokerageSettingDialog
from gui.Brokerloginpopup import BrokerLoginPopup
from gui.DailyTradeSetting import DailyTradeSetting
from gui.DailyTradeSettingGUI import DailyTradeSettingGUI
from gui.ProfitStoplossSetting import ProfitStoplossSetting
from gui.ProfitStoplossSettingGUI import ProfitStoplossSettingGUI
from gui.TradingModeSetting import TradingModeSetting
from gui.TradingModeSettingGUI import TradingModeSettingGUI
from gui.app_status_bar import AppStatusBar
from gui.chart_widget import MultiChartWidget
from gui.log_handler import QtLogHandler
from gui.popups.dynamic_signal_debug_popup import DynamicSignalDebugPopup
from gui.popups.logs_popup import LogPopup
from gui.popups.stats_popup import StatsPopup
from gui.popups.trade_history_popup import TradeHistoryPopup
from gui.popups.connection_monitor_popup import ConnectionMonitorPopup
from gui.popups.system_monitor_popup import SystemMonitorPopup
from gui.status_panel import StatusPanel
from gui.daily_pnl_widget import DailyPnLWidget  # FEATURE 5: New import
from new_main import TradingApp
from strategy.strategy_editor_window import StrategyEditorWindow
from strategy.strategy_manager import StrategyManager
from strategy.strategy_picker_sidebar import StrategyPickerSidebar
from trading_thread import TradingThread

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TradingGUI(QMainWindow):
    """# PYQT: Main window - replaces Tkinter TradingGUI class"""

    # Rule 3: Define signals at class level with typed parameters
    error_occurred = pyqtSignal(str)
    status_updated = pyqtSignal(str)
    app_state_changed = pyqtSignal(bool, str)  # running, mode
    strategy_changed = pyqtSignal(str)  # strategy slug
    log_message_received = pyqtSignal(str)  # For log messages

    # FEATURE 5: Signal for daily P&L updates
    trade_closed = pyqtSignal(float, bool)  # pnl, is_winner
    unrealized_pnl_updated = pyqtSignal(float)  # unrealized P&L

    def __init__(self):
        # Rule 2: Safe defaults first - before any UI setup
        self._safe_defaults_init()

        try:
            super().__init__()
            self.setWindowTitle("Algo Trading Dashboard")
            self.resize(1400, 850)
            self.setMinimumSize(1100, 700)

            # Dark base style - EXACTLY preserved with enhancements
            self.setStyleSheet("""
                QMainWindow, QWidget { 
                    background: #0d1117; 
                    color: #e6edf3; 
                }
                QPushButton { 
                    border-radius: 5px; 
                    padding: 8px 16px;
                    font-weight: bold; 
                    font-size: 10pt; 
                }
                QPushButton:disabled { 
                    background: #21262d; 
                    color: #484f58; 
                }
                QPushButton#successBtn {
                    background: #238636;
                }
                QPushButton#successBtn:hover {
                    background: #2ea043;
                }
                QPushButton#dangerBtn {
                    background: #da3633;
                }
                QPushButton#dangerBtn:hover {
                    background: #f85149;
                }
                QPushButton#warningBtn {
                    background: #9e6a03;
                }
                QPushButton#warningBtn:hover {
                    background: #d29922;
                }
                QSplitter::handle {
                    background: #30363d;
                }
                QMenuBar {
                    background: #161b22;
                    color: #e6edf3;
                    border-bottom: 1px solid #30363d;
                }
                QMenuBar::item {
                    padding: 5px 10px;
                    background: transparent;
                }
                QMenuBar::item:selected {
                    background: #21262d;
                }
                QMenu {
                    background: #161b22;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                }
                QMenu::item {
                    padding: 5px 20px;
                }
                QMenu::item:selected {
                    background: #21262d;
                }
                QMenu::separator {
                    height: 1px;
                    background: #30363d;
                    margin: 5px 0px;
                }
                QStatusBar {
                    background: #161b22;
                    color: #8b949e;
                    border-top: 1px solid #30363d;
                }
                QTabWidget::pane {
                    border: 1px solid #30363d;
                    background: #0d1117;
                }
                QTabBar::tab {
                    background: #161b22;
                    color: #8b949e;
                    padding: 8px 16px;
                    border: 1px solid #30363d;
                }
                QTabBar::tab:selected {
                    background: #21262d;
                    color: #e6edf3;
                    border-bottom: 2px solid #58a6ff;
                }
                QTabBar::tab:hover {
                    background: #21262d;
                }
                QScrollBar:vertical {
                    border: none;
                    background: #161b22;
                    width: 14px;
                    border-radius: 7px;
                }
                QScrollBar::handle:vertical {
                    background: #30363d;
                    border-radius: 7px;
                    min-height: 20px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #3d444d;
                }
                QScrollBar:horizontal {
                    border: none;
                    background: #161b22;
                    height: 14px;
                    border-radius: 7px;
                }
                QScrollBar::handle:horizontal {
                    background: #30363d;
                    border-radius: 7px;
                    min-width: 20px;
                }
                QScrollBar::handle:horizontal:hover {
                    background: #3d444d;
                }
            """)

            # Settings objects - Initialize with database
            self.config = Config()

            # IMPORTANT FIX: Initialize settings objects and ensure they load from database
            self.brokerage_setting = BrokerageSetting()
            self.brokerage_setting.load()  # Explicit load from database

            self.daily_setting = DailyTradeSetting()
            self.daily_setting.load()

            self.profit_loss_setting = ProfitStoplossSetting()
            self.profit_loss_setting.load()

            self.trading_mode_setting = TradingModeSetting()
            self.trading_mode_setting.load()

            # Runtime state
            self.app_running = False
            self.trading_mode = "algo"  # "algo" | "manual"
            self.trading_app = None
            self.trading_thread = None

            # Popup windows
            self.log_popup = None
            self.history_popup = None
            self.stats_popup = None
            self.signal_debug_popup = None
            self.connection_monitor_popup = None
            self.system_monitor_popup = None

            # FEATURE 5: Daily P&L Widget
            self.daily_pnl_widget = None

            # Log buffer for capturing logs when popup is closed
            self._log_buffer = []
            self._max_buffer_size = 5000  # Keep last 5000 logs
            self._log_handler = None

            # Cache for trade history file modification time
            self._trade_file_mtime = 0
            self._last_loaded_trade_data = None
            self.strategy_manager = StrategyManager()
            self.strategy_editor = None
            self.strategy_picker = None

            # Performance monitoring
            self._last_update_time = datetime.now()
            self._update_count = 0
            self._connection_status = "Disconnected"
            self._last_heartbeat = datetime.now()

            # Apply the active strategy immediately
            self._apply_active_strategy()

            # Build UI
            self._setup_log_handler()
            self._create_menu()
            self._build_layout()
            self._setup_timers()
            self._init_trading_app()
            self._setup_system_tray()

            # Rule 3: Connect internal signals
            self._setup_internal_signals()

            # Set initial status
            self.status_updated.emit("Application initialized successfully")
            logger.info("TradingGUI initialized successfully")

        except Exception as e:
            logger.critical(f"[TradingGUI.__init__] Initialization failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Application initialization failed: {e}")
            # Still try to show a basic window
            self._create_error_window()

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.config = None
        self.brokerage_setting = None
        self.daily_setting = None
        self.profit_loss_setting = None
        self.trading_mode_setting = None
        self.app_running = False
        self.trading_mode = "algo"
        self.trading_app = None
        self.trading_thread = None
        self.log_popup = None
        self.history_popup = None
        self.stats_popup = None
        self.signal_debug_popup = None
        self.connection_monitor_popup = None
        self.system_monitor_popup = None
        self.daily_pnl_widget = None
        self._log_buffer = []
        self._max_buffer_size = 5000
        self._log_handler = None
        self._trade_file_mtime = 0
        self._last_loaded_trade_data = None
        self.strategy_manager = None
        self.strategy_editor = None
        self.strategy_picker = None
        self.timer_fast = None
        self.timer_chart = None
        self.timer_app_status = None
        self.timer_connection_check = None
        self._last_chart_fp = ""
        self._chart_update_pending = False
        self.chart_widget = None
        self.status_panel = None
        self.app_status_bar = None
        self.mode_label = None
        self.radio_algo = None
        self.radio_manual = None
        self.btn_strategy = None
        self.btn_start = None
        self.btn_stop = None
        self.btn_call = None
        self.btn_put = None
        self.btn_exit = None
        self.btn_connection = None
        self._active_strategy_lbl = None
        self._system_tray_icon = None
        self._last_update_time = None
        self._update_count = 0
        self._connection_status = "Disconnected"
        self._last_heartbeat = None

    def _create_error_window(self):
        """Create error window if initialization fails"""
        try:
            super().__init__()
            self.setWindowTitle("Algo Trading Dashboard - ERROR")
            self.resize(800, 600)

            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)

            error_label = QLabel("⚠️ Application failed to initialize properly")
            error_label.setStyleSheet("color: #f85149; font-size: 16pt; font-weight: bold; padding: 20px;")
            error_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(error_label)

            details_label = QLabel("Check the logs for more information.")
            details_label.setStyleSheet("color: #8b949e; font-size: 12pt; padding: 10px;")
            details_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(details_label)

            close_btn = QPushButton("Close Application")
            close_btn.setStyleSheet("""
                QPushButton {
                    background: #da3633;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 10px 20px;
                    font-size: 12pt;
                    min-width: 200px;
                }
                QPushButton:hover {
                    background: #f85149;
                }
            """)
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn, 0, Qt.AlignCenter)

            layout.addStretch()
        except Exception as e:
            logger.error(f"[TradingGUI._create_error_window] Failed: {e}")

    def _setup_internal_signals(self):
        """Rule 3: Connect internal signals"""
        try:
            self.error_occurred.connect(self._on_error_signal)
            self.status_updated.connect(self._on_status_updated)
            self.app_state_changed.connect(self._on_app_state_changed)
            self.strategy_changed.connect(self._on_strategy_changed)
            self.log_message_received.connect(self._on_log_message)

            # FEATURE 5: Connect trade signals
            self.trade_closed.connect(self._on_trade_closed)
            self.unrealized_pnl_updated.connect(self._on_unrealized_pnl_updated)
        except Exception as e:
            logger.error(f"[TradingGUI._setup_internal_signals] Signal setup failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_error_signal(self, message: str):
        """Handle error signals"""
        try:
            logger.error(f"Error signal received: {message}")
            # Update status bar
            if self.app_status_bar is not None:
                self.app_status_bar.update_status(
                    {'status': f'Error: {message[:50]}...', 'error': True},
                    self.trading_mode,
                    self.app_running
                )

            # Show error popup for critical errors
            if any(keyword in message.lower() for keyword in ['critical', 'fatal', 'crash']):
                QMessageBox.critical(self, "Critical Error", message)
        except Exception as e:
            logger.error(f"[TradingGUI._on_error_signal] Failed to handle error: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_status_updated(self, message: str):
        """Handle status updates"""
        try:
            logger.info(f"Status update: {message}")
            # Update window title with status
            self.setWindowTitle(f"Algo Trading Dashboard - {message}")
        except Exception as e:
            logger.error(f"[TradingGUI._on_status_updated] Failed: {e}", exc_info=True)

    @pyqtSlot(bool, str)
    def _on_app_state_changed(self, running: bool, mode: str):
        """Handle app state changes"""
        try:
            self._update_button_states()
            self._update_mode_display()

            # Update system tray
            if self._system_tray_icon:
                if running:
                    self._system_tray_icon.setToolTip(f"Trading App - Running ({mode} mode)")
                else:
                    self._system_tray_icon.setToolTip(f"Trading App - Stopped ({mode} mode)")
        except Exception as e:
            logger.error(f"[TradingGUI._on_app_state_changed] Failed: {e}", exc_info=True)

    @pyqtSlot(float, bool)
    def _on_trade_closed(self, pnl: float, is_winner: bool):
        """
        FEATURE 5: Handle trade closed signal from OrderExecutor.
        Updates DailyPnLWidget when a trade is closed.
        """
        try:
            if self.daily_pnl_widget:
                self.daily_pnl_widget.on_trade_closed(pnl, is_winner)
            logger.info(f"Trade closed - P&L: ₹{pnl:.2f}, Winner: {is_winner}")
        except Exception as e:
            logger.error(f"[TradingGUI._on_trade_closed] Failed: {e}", exc_info=True)

    @pyqtSlot(float)
    def _on_unrealized_pnl_updated(self, pnl: float):
        """
        FEATURE 5: Handle unrealized P&L updates from TradingApp.
        Updates DailyPnLWidget with current unrealized P&L.
        """
        try:
            if self.daily_pnl_widget:
                self.daily_pnl_widget.on_unrealized_update(pnl)
        except Exception as e:
            logger.error(f"[TradingGUI._on_unrealized_pnl_updated] Failed: {e}", exc_info=True)

    def _setup_log_handler(self):
        """Setup Qt log handler with buffering"""
        try:
            self._log_handler = QtLogHandler()
            self._log_handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s")
            )
            self._log_handler.signaller.log_message.connect(self._on_log_message)

            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)

            # Remove stale handlers
            for h in list(root_logger.handlers):
                if isinstance(h, QtLogHandler):
                    root_logger.removeHandler(h)

            root_logger.addHandler(self._log_handler)

            # Log a test message
            logging.info("✅ Logging system initialized")

            # Set up file logging as backup
            self._setup_file_logging()

        except Exception as e:
            logger.error(f"[TradingGUI._setup_log_handler] Failed: {e}", exc_info=True)

    def _setup_file_logging(self):
        """Setup file logging as backup"""
        try:
            # Create logs directory if it doesn't exist
            os.makedirs('logs', exist_ok=True)

            # Create file handler
            log_file = f"logs/trading_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
            ))

            root_logger = logging.getLogger()
            root_logger.addHandler(file_handler)

            logger.info(f"File logging setup: {log_file}")

        except Exception as e:
            logger.error(f"[TradingGUI._setup_file_logging] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_log_message(self, message: str):
        """Handle log messages - buffer them and send to popup if open"""
        try:
            # Always add to buffer
            self._log_buffer.append(message)

            # Trim buffer if needed
            if len(self._log_buffer) > self._max_buffer_size:
                self._log_buffer = self._log_buffer[-self._max_buffer_size:]

            # If popup exists and is visible, send to it
            if self.log_popup is not None and self.log_popup.isVisible():
                self.log_popup.append_log(message)

        except Exception as e:
            logger.error(f"[TradingGUI._on_log_message] Failed: {e}", exc_info=True)

    def _setup_system_tray(self):
        """Setup system tray icon"""
        try:
            from PyQt5.QtWidgets import QSystemTrayIcon, QMenu
            from PyQt5.QtGui import QIcon

            if QSystemTrayIcon.isSystemTrayAvailable():
                self._system_tray_icon = QSystemTrayIcon(self)
                self._system_tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))

                # Create tray menu
                tray_menu = QMenu()

                show_action = tray_menu.addAction("Show Window")
                show_action.triggered.connect(self.show_normal)

                tray_menu.addSeparator()

                start_action = tray_menu.addAction("Start Trading")
                start_action.triggered.connect(self._start_app)

                stop_action = tray_menu.addAction("Stop Trading")
                stop_action.triggered.connect(self._stop_app)

                tray_menu.addSeparator()

                quit_action = tray_menu.addAction("Quit")
                quit_action.triggered.connect(self.close)

                self._system_tray_icon.setContextMenu(tray_menu)
                self._system_tray_icon.show()

                logger.info("System tray icon created")
        except Exception as e:
            logger.error(f"[TradingGUI._setup_system_tray] Failed: {e}", exc_info=True)

    def show_normal(self):
        """Show window normally (from system tray)"""
        self.show()
        self.activateWindow()
        self.raise_()

    def _build_layout(self):
        """Build main window layout with DailyPnLWidget"""
        try:
            central = QWidget()
            self.setCentralWidget(central)
            root_layout = QVBoxLayout(central)
            root_layout.setContentsMargins(5, 5, 5, 5)
            root_layout.setSpacing(5)

            # ── Top section: Chart (left) + Status Panel (right) ─────────────────────
            top_splitter = QSplitter(Qt.Horizontal)
            top_splitter.setHandleWidth(2)
            top_splitter.setStyleSheet("QSplitter::handle { background: #30363d; }")

            # Left side container for chart and buttons
            left_container = QWidget()
            left_layout = QVBoxLayout(left_container)
            left_layout.setContentsMargins(0, 0, 0, 0)
            left_layout.setSpacing(5)

            # Chart widget with tabs
            self.chart_widget = MultiChartWidget()
            self.chart_widget.setMinimumWidth(800)
            left_layout.addWidget(self.chart_widget, 1)

            # Button panel (below chart)
            button_panel = self._build_button_panel()
            left_layout.addWidget(button_panel)

            # Add left container to splitter
            top_splitter.addWidget(left_container)

            # Right side: Status panel
            self.status_panel = StatusPanel()
            self.status_panel.setFixedWidth(340)
            top_splitter.addWidget(self.status_panel)

            # Set initial sizes (chart gets 75%, status gets 25%)
            top_splitter.setSizes([1060, 340])
            root_layout.addWidget(top_splitter, 1)

            # ── FEATURE 5: Daily P&L Widget (below splitter) ─────────────────────────
            self.daily_pnl_widget = DailyPnLWidget(self.config)
            root_layout.addWidget(self.daily_pnl_widget)

            # ── Bottom section: App Status Bar ─────────────────────────────
            self.app_status_bar = AppStatusBar()
            root_layout.addWidget(self.app_status_bar)

        except Exception as e:
            logger.error(f"[TradingGUI._build_layout] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to build layout: {e}")

    def _build_button_panel(self) -> QWidget:
        """Build horizontal button panel below chart"""
        panel = QWidget()
        try:
            panel.setFixedHeight(70)
            panel.setStyleSheet("""
                QWidget {
                    background: #161b22;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                }
            """)

            layout = QHBoxLayout(panel)
            layout.setContentsMargins(15, 8, 15, 8)
            layout.setSpacing(10)

            # Mode toggle group
            mode_frame = QFrame()
            mode_frame.setStyleSheet("QFrame { border: none; }")
            mode_layout = QHBoxLayout(mode_frame)
            mode_layout.setContentsMargins(0, 0, 0, 0)

            lbl = QLabel("Mode:")
            lbl.setStyleSheet("color: #8b949e; font-size: 9pt; font-weight: bold;")
            mode_layout.addWidget(lbl)

            # Mode indicator
            self.mode_label = QLabel(
                f"Mode: {self.trading_mode_setting.mode.value if self.trading_mode_setting else 'algo'}")
            self.mode_label.setStyleSheet("color: #2ea043; font-weight: bold; padding: 5px;")
            mode_layout.addWidget(self.mode_label)

            self.radio_algo = QRadioButton("⚡ Algo")
            self.radio_manual = QRadioButton("🖐 Manual")
            self.radio_algo.setChecked(True)
            self.radio_algo.toggled.connect(self._on_mode_change)

            for rb in [self.radio_algo, self.radio_manual]:
                rb.setStyleSheet("""
                    QRadioButton {
                        color: #e6edf3;
                        font-size: 9pt;
                        spacing: 5px;
                    }
                    QRadioButton::indicator {
                        width: 12px;
                        height: 12px;
                    }
                """)
                mode_layout.addWidget(rb)

            layout.addWidget(mode_frame)

            # Separator
            separator = QFrame()
            separator.setFrameShape(QFrame.VLine)
            separator.setStyleSheet("QFrame { border: 1px solid #30363d; }")
            layout.addWidget(separator)

            # Button styling helper
            def make_btn(text, color, hover, icon=None, obj_name=None):
                btn = QPushButton(text)
                if obj_name:
                    btn.setObjectName(obj_name)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {color};
                        color: #fff;
                        border-radius: 5px;
                        padding: 8px 20px;
                        font-weight: bold;
                        min-width: 100px;
                    }}
                    QPushButton:hover {{
                        background: {hover};
                    }}
                    QPushButton:disabled {{
                        background: #21262d;
                        color: #484f58;
                    }}
                """)
                return btn

            self.btn_strategy = make_btn("⚡ Strategy", "#1f6feb", "#388bfd")
            self.btn_strategy.clicked.connect(self._show_strategy_picker)
            layout.addWidget(self.btn_strategy)

            # Control buttons
            self.btn_start = make_btn("▶  Start", "#238636", "#2ea043", obj_name="successBtn")
            self.btn_stop = make_btn("■  Stop", "#da3633", "#f85149", obj_name="dangerBtn")

            # Connection status button
            self.btn_connection = QPushButton("🔌 Disconnected")
            self.btn_connection.setStyleSheet("""
                QPushButton {
                    background: #21262d;
                    color: #f85149;
                    border: 1px solid #30363d;
                    border-radius: 5px;
                    padding: 8px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #30363d;
                }
            """)
            self.btn_connection.clicked.connect(self._show_connection_monitor)
            layout.addWidget(self.btn_connection)

            self.btn_call = make_btn("📈  Buy Call", "#1f6feb", "#388bfd")
            self.btn_put = make_btn("📉  Buy Put", "#6e40c9", "#8957e5")
            self.btn_exit = make_btn("🚪  Exit", "#9e6a03", "#d29922")

            # Initial button states
            self.btn_stop.setDisabled(True)
            self.btn_call.setDisabled(True)
            self.btn_put.setDisabled(True)
            self.btn_exit.setDisabled(True)

            # Connect signals
            self.btn_start.clicked.connect(self._start_app)
            self.btn_stop.clicked.connect(self._stop_app)
            self.btn_call.clicked.connect(lambda: self._manual_buy(BaseEnums.CALL))
            self.btn_put.clicked.connect(lambda: self._manual_buy(BaseEnums.PUT))
            self.btn_exit.clicked.connect(self._manual_exit)

            # Add buttons in order
            layout.addWidget(self.btn_start)
            layout.addWidget(self.btn_stop)
            layout.addStretch()
            layout.addWidget(self.btn_call)
            layout.addWidget(self.btn_put)
            layout.addWidget(self.btn_exit)

        except Exception as e:
            logger.error(f"[TradingGUI._build_button_panel] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to build button panel: {e}")

        return panel

    def _setup_timers(self):
        """Setup all timers"""
        try:
            # Fast timer (1 second) - for status updates
            self.timer_fast = QTimer(self)
            self.timer_fast.timeout.connect(self._tick_fast)
            self.timer_fast.start(1000)

            # Chart timer (5 seconds) - with debouncing
            self.timer_chart = QTimer(self)
            self.timer_chart.timeout.connect(self._tick_chart)
            self.timer_chart.start(5000)
            self._last_chart_fp = ""
            self._chart_update_pending = False

            # App status timer (500ms)
            self.timer_app_status = QTimer(self)
            self.timer_app_status.timeout.connect(self._update_app_status)
            self.timer_app_status.start(500)

            # Connection check timer (10 seconds)
            self.timer_connection_check = QTimer(self)
            self.timer_connection_check.timeout.connect(self._check_connection)
            self.timer_connection_check.start(10000)

        except Exception as e:
            logger.error(f"[TradingGUI._setup_timers] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _tick_fast(self):
        """Fast timer tick - update UI"""
        try:
            if self.trading_app is None:
                return

            state = self.trading_app.state
            self.status_panel.refresh(state, self.config)

            # Update popups if they're open
            if self.stats_popup is not None and self.stats_popup.isVisible():
                self.stats_popup.refresh()

            if self.signal_debug_popup is not None and self.signal_debug_popup.isVisible():
                self.signal_debug_popup.refresh()

            if self.connection_monitor_popup is not None and self.connection_monitor_popup.isVisible():
                self.connection_monitor_popup.refresh()

            self._update_button_states()

            # Update performance metrics
            self._update_count += 1
            now = datetime.now()
            if (now - self._last_update_time).seconds >= 60:
                logger.debug(f"UI Update rate: {self._update_count / 60:.1f} Hz")
                self._update_count = 0
                self._last_update_time = now

        except Exception as e:
            logger.error(f"[TradingGUI._tick_fast] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _tick_chart(self):
        """Chart timer tick"""
        try:
            if self.trading_app is None:
                return

            # Update chart
            self._update_chart_if_needed()

            # Update trade history
            self._update_trade_history()

        except Exception as e:
            logger.error(f"[TradingGUI._tick_chart] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _update_app_status(self):
        """Update application status"""
        try:
            if self.trading_app is None:
                return

            # Get status information
            status_info = {
                'fetching_history': False,
                'processing': False,
                'order_pending': False,
                'has_position': False,
                'trade_confirmed': False,
                'last_exit_reason': None,
                'connection_status': self._connection_status
            }

            # Check history fetch status
            if hasattr(self.trading_app, '_history_fetch_in_progress'):
                status_info['fetching_history'] = self.trading_app._history_fetch_in_progress.is_set()

            # Check processing status
            if hasattr(self.trading_app, '_tick_queue'):
                # Queue-based processing doesn't have an "in progress" flag
                status_info['processing'] = not self.trading_app._tick_queue.empty()

            # Check order pending status
            if hasattr(self.trading_app.state, 'order_pending'):
                status_info['order_pending'] = self.trading_app.state.order_pending

            # Check if position is active
            if hasattr(self.trading_app.state, 'current_position'):
                status_info['has_position'] = self.trading_app.state.current_position is not None
                if status_info['has_position']:
                    status_info['position_type'] = self.trading_app.state.current_position

            # Check if trade is confirmed
            if hasattr(self.trading_app.state, 'current_trade_confirmed'):
                status_info['trade_confirmed'] = self.trading_app.state.current_trade_confirmed

            # Get last reason to exit
            if hasattr(self.trading_app.state, 'reason_to_exit'):
                status_info['last_exit_reason'] = self.trading_app.state.reason_to_exit

            # Get current P&L
            if hasattr(self.trading_app.state, 'current_pnl'):
                status_info['current_pnl'] = self.trading_app.state.current_pnl

                # FEATURE 5: Emit unrealized P&L for DailyPnLWidget (FIX: handle None)
                pnl_value = status_info['current_pnl']
                if pnl_value is not None:
                    self.unrealized_pnl_updated.emit(float(pnl_value))
                else:
                    # Emit 0.0 when no position (no unrealized P&L)
                    self.unrealized_pnl_updated.emit(0.0)

            # Update status bar
            self.app_status_bar.update_status(
                status_info,
                self.trading_mode,
                self.app_running
            )

        except Exception as e:
            logger.error(f"[TradingGUI._update_app_status] Failed: {e}", exc_info=True)

    def _check_connection(self):
        """Check connection status"""
        try:
            if self.trading_app and hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                if hasattr(self.trading_app.ws, 'is_connected'):
                    is_connected = self.trading_app.ws.is_connected()
                    self._connection_status = "Connected" if is_connected else "Disconnected"
                else:
                    self._connection_status = "Unknown"
            else:
                self._connection_status = "Disconnected"

            # Update connection button
            if self.btn_connection:
                if self._connection_status == "Connected":
                    self.btn_connection.setText("🔌 Connected")
                    self.btn_connection.setStyleSheet("""
                        QPushButton {
                            background: #238636;
                            color: white;
                            border: 1px solid #2ea043;
                            border-radius: 5px;
                            padding: 8px 12px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background: #2ea043;
                        }
                    """)
                else:
                    self.btn_connection.setText("🔌 Disconnected")
                    self.btn_connection.setStyleSheet("""
                        QPushButton {
                            background: #21262d;
                            color: #f85149;
                            border: 1px solid #30363d;
                            border-radius: 5px;
                            padding: 8px 12px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background: #30363d;
                        }
                    """)
        except Exception as e:
            logger.error(f"[TradingGUI._check_connection] Failed: {e}", exc_info=True)

    def _update_chart_if_needed(self):
        """Update chart only if data has changed"""
        try:
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
            except Exception as e:
                logger.warning(f"Chart fingerprint failed: {e}")
                if not self._chart_update_pending:
                    self._chart_update_pending = True
                    QTimer.singleShot(100, self._do_chart_update)

        except Exception as e:
            logger.error(f"[TradingGUI._update_chart_if_needed] Failed: {e}", exc_info=True)
            self._chart_update_pending = False

    def _do_chart_update(self):
        """Perform actual chart update"""
        try:
            if self.trading_app:
                state = self.trading_app.state
                self.chart_widget.update_charts(
                    spot_data=getattr(state, "derivative_trend", {}) or {},
                    call_data=getattr(state, "call_trend", {}) or {},
                    put_data=getattr(state, "put_trend", {}) or {},
                )
        except Exception as e:
            logger.error(f"[TradingGUI._do_chart_update] Failed: {e}", exc_info=True)
        finally:
            self._chart_update_pending = False

    def _update_button_states(self):
        """Enable/disable buttons based on app state"""
        try:
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

        except AttributeError as e:
            logger.warning(f"[TradingGUI._update_button_states] Attribute error (normal during init): {e}")
        except Exception as e:
            logger.error(f"[TradingGUI._update_button_states] Failed: {e}", exc_info=True)

    def _init_trading_app(self):
        """Create the trading app instance"""
        try:
            # IMPORTANT FIX: Log settings before creating TradingApp for debugging
            logger.info("Initializing TradingApp with settings:")
            logger.info(
                f"  Brokerage: client_id={self.brokerage_setting.client_id[:5]}..." if self.brokerage_setting.client_id else "  Brokerage: No client_id")
            logger.info(f"  Daily: derivative={self.daily_setting.derivative}, lot_size={self.daily_setting.lot_size}")
            logger.info(
                f"  P&L: tp={self.profit_loss_setting.tp_percentage}%, sl={self.profit_loss_setting.stoploss_percentage}%")
            logger.info(f"  Mode: {self.trading_mode_setting.mode.value}")

            self.trading_app = TradingApp(
                config=self.config,
                broker_setting=self.brokerage_setting,
            )

            # FEATURE 5: Connect trade closed callback
            if hasattr(self.trading_app, 'executor'):
                self.trading_app.executor.on_trade_closed_callback = self._on_trade_closed

            # FEATURE 1: Inject risk manager config
            if hasattr(self.trading_app, 'risk_manager'):
                # Risk manager will get config from self.config
                pass

            # FEATURE 4: Inject notifier with settings
            if hasattr(self.trading_app, 'notifier'):
                # Notifier gets config from self.config
                pass

            # Wire up chart config + signal engine
            try:
                engine = getattr(
                    getattr(self.trading_app, 'detector', None),
                    'signal_engine', None
                )
                self.chart_widget.set_config(self.config, engine)
                logger.info("Chart config set from trading app")
            except Exception as e:
                logger.warning(f"Could not set chart config: {e}")
                self.chart_widget.set_config(self.config, None)

            # Update status
            self.app_status_bar.update_status({
                'initialized': True,
                'status': 'App initialized'
            }, self.trading_mode, False)

            logger.info("TradingApp initialized successfully")

        except Exception as e:
            logger.critical(f"Failed to create TradingApp: {e}", exc_info=True)
            error_str = str(e)

            # Check if this is a token expiry error
            if "Token expired" in error_str or ("token" in error_str.lower() and "expir" in error_str.lower()):
                logger.warning("Token expiry detected during init, prompting re-authentication")
                self.error_occurred.emit(f"Token expired: {e}")
                QTimer.singleShot(500, lambda: self._open_login_for_token_expiry(str(e)))
            else:
                self.error_occurred.emit(f"Failed to connect to broker: {e}")
                QMessageBox.critical(self, "Init Error",
                                     f"Could not connect to broker:\n{e}\n\n"
                                     "Check credentials via Settings → Brokerage Settings.")

    @pyqtSlot()
    def _start_app(self):
        """Start trading engine on QThread"""
        try:
            if self.trading_app is None:
                logger.error("Start failed: Trading app not initialized")
                QMessageBox.critical(self, "Error", "Trading app not initialised.")
                return

            # Check if we need to login first
            if self._check_token_expired():
                reply = QMessageBox.question(
                    self, "Token Expired",
                    "Your token appears to be expired. Would you like to login now?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._open_login_for_token_expiry("Token expired")
                    return

            # Run trading engine on QThread
            self.trading_thread = TradingThread(self.trading_app)
            self.trading_thread.error_occurred.connect(self._on_engine_error)
            self.trading_thread.token_expired.connect(self._on_token_expired)
            self.trading_thread.finished.connect(self._on_engine_finished)
            self.trading_thread.started.connect(lambda: logger.info("Trading thread started"))

            # FEATURE 5: Connect trade closed signal from thread
            self.trading_thread.position_closed.connect(
                lambda sym, pnl: self.trade_closed.emit(pnl, pnl > 0)
            )

            self.trading_thread.start()

            self.app_running = True
            self.app_status_bar.update_status({'status': 'Starting...'}, self.trading_mode, True)
            self._update_button_states()
            self.status_updated.emit("Trading engine started")

            logger.info("Trading engine started")
            self.app_state_changed.emit(True, self.trading_mode)

        except Exception as e:
            logger.error(f"[TradingGUI._start_app] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to start trading engine: {e}")

    def _check_token_expired(self) -> bool:
        """Check if token appears to be expired"""
        try:
            # This is a simple check - you might want to implement more sophisticated logic
            if hasattr(self.brokerage_setting, 'token_expiry'):
                expiry = self.brokerage_setting.token_expiry
                if expiry and datetime.now() > expiry:
                    return True
            return False
        except:
            return False

    @pyqtSlot()
    def _stop_app(self):
        """Stop the trading engine"""
        try:
            self.btn_stop.setDisabled(True)
            self.app_status_bar.update_status({'status': 'Stopping...'}, self.trading_mode, True)
            self.status_updated.emit("Stopping trading engine...")

            # Stop in background thread
            threading.Thread(target=self._threaded_stop, daemon=True, name="StopThread").start()

            logger.info("Trading engine stopping...")

        except Exception as e:
            logger.error(f"[TradingGUI._stop_app] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to stop trading engine: {e}")

    def _threaded_stop(self):
        """Background stop work"""
        try:
            if self.trading_thread:
                self.trading_thread.stop()
            # Post result back to main thread
            QTimer.singleShot(0, self._on_engine_finished)
            logger.debug("Stop thread completed")
        except Exception as e:
            logger.error(f"[TradingGUI._threaded_stop] Failed: {e}", exc_info=True)
            QTimer.singleShot(0, lambda: self.error_occurred.emit(f"Stop failed: {e}"))

    @pyqtSlot()
    def _on_engine_finished(self):
        """Slot called when engine finishes"""
        try:
            self.app_running = False
            self.app_status_bar.update_status({'status': 'Stopped'}, self.trading_mode, False)
            self._update_button_states()
            self.status_updated.emit("Trading engine stopped")

            logger.info("Trading engine stopped")
            self.app_state_changed.emit(False, self.trading_mode)

        except Exception as e:
            logger.error(f"[TradingGUI._on_engine_finished] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_token_expired(self, message: str):
        """Handle token expired signal"""
        try:
            self.app_running = False
            self.app_status_bar.update_status(
                {'status': '🔐 Token expired — re-login required', 'error': True},
                self.trading_mode, False
            )
            self._update_button_states()
            logger.warning(f"Token expired signal received: {message}")

            # Open re-authentication popup
            self._open_login_for_token_expiry(message)
        except Exception as e:
            logger.error(f"[TradingGUI._on_token_expired] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_engine_error(self, message: str):
        """Handle engine errors"""
        try:
            self.app_running = False
            self.app_status_bar.update_status(
                {'status': f'Error: {message[:50]}...', 'error': True},
                self.trading_mode, False
            )
            self._update_button_states()
            QMessageBox.critical(self, "Engine Error", f"Trading engine crashed:\n{message}")
            logger.error(f"Engine error: {message}")
            self.error_occurred.emit(message)
        except Exception as e:
            logger.error(f"[TradingGUI._on_engine_error] Failed to handle error: {e}", exc_info=True)

    def _manual_buy(self, option_type):
        """Manual buy in background thread"""
        try:
            if self.trading_mode != "manual":
                QMessageBox.information(self, "Mode", "Switch to Manual mode first.")
                return
            if not self.trading_app:
                logger.warning("Manual buy attempted with no trading app")
                return

            self.app_status_bar.update_status({'status': f'Placing {option_type} order...'}, self.trading_mode, True)
            threading.Thread(
                target=self._threaded_manual_buy,
                args=(option_type,),
                daemon=True
            ).start()

            logger.info(f"Manual {option_type} buy initiated")

        except Exception as e:
            logger.error(f"[TradingGUI._manual_buy] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Manual buy failed: {e}")

    def _threaded_manual_buy(self, option_type):
        """Execute manual buy in background"""
        try:
            self.trading_app.executor.buy_option(
                self.trading_app.state, option_type=option_type)
            QTimer.singleShot(0, lambda: self.app_status_bar.update_status(
                {'status': f'{option_type} order placed'}, self.trading_mode, True))
            logger.info(f"Manual {option_type} order placed successfully")
        except Exception as e:
            logger.error(f"Manual buy thread error: {e}", exc_info=True)
            QTimer.singleShot(0, lambda: self.error_occurred.emit(f"Order failed: {e}"))

    def _manual_exit(self):
        """Manual exit in background thread"""
        try:
            if self.trading_mode != "manual":
                QMessageBox.information(self, "Mode", "Switch to Manual mode first.")
                return
            if not self.trading_app:
                logger.warning("Manual exit attempted with no trading app")
                return

            self.app_status_bar.update_status({'status': 'Exiting position...'}, self.trading_mode, True)
            threading.Thread(
                target=self._threaded_manual_exit,
                daemon=True
            ).start()

            logger.info("Manual exit initiated")

        except Exception as e:
            logger.error(f"[TradingGUI._manual_exit] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Manual exit failed: {e}")

    def _threaded_manual_exit(self):
        """Execute manual exit in background"""
        try:
            self.trading_app.executor.exit_position(
                self.trading_app.state, reason="Manual Exit")
            QTimer.singleShot(0, lambda: self.app_status_bar.update_status(
                {'status': 'Position exited'}, self.trading_mode, True))
            logger.info("Manual exit completed successfully")
        except Exception as e:
            logger.error(f"Manual exit thread error: {e}", exc_info=True)
            QTimer.singleShot(0, lambda: self.error_occurred.emit(f"Exit failed: {e}"))

    @pyqtSlot()
    def _on_mode_change(self):
        """Handle mode switch"""
        try:
            self.trading_mode = "algo" if self.radio_algo.isChecked() else "manual"
            self.app_status_bar.update_status({}, self.trading_mode, self.app_running)
            self._update_button_states()
            self._update_mode_display()

            logger.info(f"Trading mode changed to: {self.trading_mode}")
            self.app_state_changed.emit(self.app_running, self.trading_mode)

        except Exception as e:
            logger.error(f"[TradingGUI._on_mode_change] Failed: {e}", exc_info=True)

    def _create_menu(self):
        """Build menu bar"""
        try:
            menubar = self.menuBar()

            # File menu
            file_menu = menubar.addMenu("File")

            restart_act = QAction("🔄 Restart Application", self)
            restart_act.triggered.connect(self._restart_application)
            file_menu.addAction(restart_act)

            file_menu.addSeparator()

            exit_act = QAction("❌ Exit", self)
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

            sig_debug_act = QAction("🔬 Dynamic Signal Debug", self)
            sig_debug_act.triggered.connect(self._show_signal_debug_popup)
            view_menu.addAction(sig_debug_act)

            connection_act = QAction("🌐 Connection Monitor", self)
            connection_act.triggered.connect(self._show_connection_monitor)
            view_menu.addAction(connection_act)

            system_act = QAction("💻 System Monitor", self)
            system_act.triggered.connect(self._show_system_monitor)
            view_menu.addAction(system_act)

            view_menu.addSeparator()

            picker_act = QAction("⚡ Strategy Picker", self)
            picker_act.triggered.connect(self._show_strategy_picker)
            view_menu.addAction(picker_act)

            editor_act = QAction("📋 Strategy Editor", self)
            editor_act.triggered.connect(self._open_strategy_editor)
            view_menu.addAction(editor_act)

            view_menu.addSeparator()

            close_all_act = QAction("❌ Close All Popups", self)
            close_all_act.triggered.connect(self._close_all_popups)
            view_menu.addAction(close_all_act)

            # Settings menu
            settings_menu = menubar.addMenu("Settings")

            strategy_settings = QAction("⚙️ Strategy Settings", self)
            strategy_settings.triggered.connect(self._show_strategy_picker)
            settings_menu.addAction(strategy_settings)

            daily_settings = QAction("📅 Daily Trade Settings", self)
            daily_settings.triggered.connect(self._open_daily)
            settings_menu.addAction(daily_settings)

            pnl_settings = QAction("💰 Profit & Loss Settings", self)
            pnl_settings.triggered.connect(self._open_pnl)
            settings_menu.addAction(pnl_settings)

            brokerage_settings = QAction("🏦 Brokerage Settings", self)
            brokerage_settings.triggered.connect(self._open_brokerage)
            settings_menu.addAction(brokerage_settings)

            broker_name = getattr(self.brokerage_setting, 'broker_type', 'Broker') or 'Broker'
            login_act = QAction(f"🔑 Manual {broker_name.title()} Login", self)
            login_act.triggered.connect(self._open_login)
            settings_menu.addAction(login_act)

            mode_settings = QAction("🎮 Trading Mode Settings", self)
            mode_settings.triggered.connect(self._open_trading_mode)
            settings_menu.addAction(mode_settings)

            # Tools menu
            tools_menu = menubar.addMenu("Tools")

            backup_act = QAction("💾 Backup Configuration", self)
            backup_act.triggered.connect(self._backup_config)
            tools_menu.addAction(backup_act)

            restore_act = QAction("📂 Restore Configuration", self)
            restore_act.triggered.connect(self._restore_config)
            tools_menu.addAction(restore_act)

            tools_menu.addSeparator()

            clear_cache_act = QAction("🗑️ Clear Cache", self)
            clear_cache_act.triggered.connect(self._clear_cache)
            tools_menu.addAction(clear_cache_act)

            # Help menu
            help_menu = menubar.addMenu("Help")

            about_act = QAction("ℹ️ About", self)
            about_act.triggered.connect(self._show_about)
            help_menu.addAction(about_act)

            docs_act = QAction("📚 Documentation", self)
            docs_act.triggered.connect(self._show_documentation)
            help_menu.addAction(docs_act)

            help_menu.addSeparator()

            check_updates_act = QAction("🔄 Check for Updates", self)
            check_updates_act.triggered.connect(self._check_updates)
            help_menu.addAction(check_updates_act)

        except Exception as e:
            logger.error(f"[TradingGUI._create_menu] Failed: {e}", exc_info=True)

    # Popup window handlers
    def _show_log_popup(self):
        """Show log popup window with buffered logs"""
        try:
            # Create popup if needed
            if self.log_popup is None:
                self.log_popup = LogPopup(self)

            # Send buffered logs to popup
            if self._log_buffer:
                # Send last 500 logs to avoid overload
                for msg in self._log_buffer[-500:]:
                    self.log_popup.append_log(msg)

            # Show popup
            self.log_popup.show()
            self.log_popup.raise_()
            self.log_popup.activateWindow()

        except Exception as e:
            logger.error(f"[TradingGUI._show_log_popup] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to show log popup: {e}")

    def _show_history_popup(self):
        """Show trade history popup"""
        try:
            if not self.history_popup:
                self.history_popup = TradeHistoryPopup(self)
            self.history_popup.load_trades()
            self.history_popup.show()
            self.history_popup.raise_()
            self.history_popup.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_history_popup] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to show history popup: {e}")

    def _show_stats_popup(self):
        """Show statistics popup"""
        try:
            if self.trading_app:
                if not self.stats_popup:
                    self.stats_popup = StatsPopup(self.trading_app.state, self)
                self.stats_popup.show()
                self.stats_popup.raise_()
                self.stats_popup.activateWindow()
            else:
                QMessageBox.information(self, "Not Ready", "Trading app not initialized yet.")
        except Exception as e:
            logger.error(f"[TradingGUI._show_stats_popup] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to show stats popup: {e}")

    def _show_connection_monitor(self):
        """Show connection monitor popup"""
        try:
            if not self.connection_monitor_popup:
                self.connection_monitor_popup = ConnectionMonitorPopup(self.trading_app, self)
            self.connection_monitor_popup.show()
            self.connection_monitor_popup.raise_()
            self.connection_monitor_popup.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_connection_monitor] Failed: {e}", exc_info=True)

    def _show_system_monitor(self):
        """Show system monitor popup"""
        try:
            if not self.system_monitor_popup:
                self.system_monitor_popup = SystemMonitorPopup(self)
            self.system_monitor_popup.show()
            self.system_monitor_popup.raise_()
            self.system_monitor_popup.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_system_monitor] Failed: {e}", exc_info=True)

    def _show_signal_debug_popup(self):
        """Show signal debug popup"""
        try:
            if not self.trading_app:
                QMessageBox.information(self, "Not Ready", "Trading app not initialized yet.")
                return
            if self.signal_debug_popup is None:
                self.signal_debug_popup = DynamicSignalDebugPopup(self.trading_app, self)
            self.signal_debug_popup.show()
            self.signal_debug_popup.raise_()
            self.signal_debug_popup.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_signal_debug_popup] Failed: {e}", exc_info=True)

    def _close_all_popups(self):
        """Close all popup windows"""
        try:
            popups = [
                self.log_popup,
                self.history_popup,
                self.stats_popup,
                self.signal_debug_popup,
                self.connection_monitor_popup,
                self.system_monitor_popup,
                self.strategy_picker,
                self.strategy_editor
            ]

            for popup in popups:
                if popup is not None:
                    try:
                        popup.close()
                    except:
                        pass

            logger.debug("All popups closed")
        except Exception as e:
            logger.error(f"[TradingGUI._close_all_popups] Failed: {e}", exc_info=True)

    def _open_trading_mode(self):
        """Open trading mode settings"""
        try:
            dlg = TradingModeSettingGUI(
                self,
                trading_mode_setting=self.trading_mode_setting,
                app=self.trading_app
            )
            if dlg.exec_():
                self._update_mode_display()
        except Exception as e:
            logger.error(f"[TradingGUI._open_trading_mode] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to open trading mode settings: {e}")

    def _update_mode_display(self):
        """Update UI to show current trading mode"""
        try:
            mode = self.trading_mode_setting.mode.value if self.trading_mode_setting else "algo"
            color = "#f85149" if (self.trading_mode_setting and self.trading_mode_setting.is_live()) else "#2ea043"

            if hasattr(self, 'mode_label') and self.mode_label is not None:
                self.mode_label.setText(f"Mode: {mode}")
                self.mode_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        except Exception as e:
            logger.error(f"[TradingGUI._update_mode_display] Failed: {e}", exc_info=True)

    def _open_daily(self):
        """Open daily trade settings"""
        try:
            dlg = DailyTradeSettingGUI(self, daily_setting=self.daily_setting,
                                       app=self.trading_app)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_daily] Failed: {e}", exc_info=True)

    def _open_pnl(self):
        """Open P&L settings"""
        try:
            dlg = ProfitStoplossSettingGUI(self, profit_stoploss_setting=self.profit_loss_setting,
                                           app=self.trading_app)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_pnl] Failed: {e}", exc_info=True)

    def _open_brokerage(self):
        """Open brokerage settings"""
        try:
            dlg = BrokerageSettingDialog(self.brokerage_setting, self)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_brokerage] Failed: {e}", exc_info=True)

    def _open_login_for_token_expiry(self, reason: str = None):
        """Open login popup for token expiry"""
        try:
            broker_name = getattr(self.brokerage_setting, 'broker_type', 'Broker') or 'Broker'
            logger.info(f"Opening BrokerLoginPopup for {broker_name} due to token expiry")
            reason_msg = reason or f"Your {broker_name.title()} access token has expired or is invalid."
            dlg = BrokerLoginPopup(self, self.brokerage_setting, reason=reason_msg)
            dlg.login_completed.connect(lambda _: self._reload_broker())
            result = dlg.exec_()
            if result == BrokerLoginPopup.Accepted:
                logger.info("Re-authentication completed successfully")
            else:
                logger.warning("Re-authentication dialog was cancelled")
                self.app_status_bar.update_status(
                    {'status': '⚠️ Token expired — login required to resume', 'error': True},
                    self.trading_mode, False
                )
        except Exception as e:
            logger.error(f"[TradingGUI._open_login_for_token_expiry] Failed: {e}", exc_info=True)

    def _open_login(self):
        """Open login popup"""
        try:
            dlg = BrokerLoginPopup(self, self.brokerage_setting)
            dlg.exec_()
            self._reload_broker()
        except Exception as e:
            logger.error(f"[TradingGUI._open_login] Failed: {e}", exc_info=True)

    def _reload_broker(self):
        """Reload broker after login"""
        try:
            self.trading_app = TradingApp(
                config=self.config,
                broker_setting=self.brokerage_setting,
            )

            # FEATURE 5: Reconnect trade closed callback
            if hasattr(self.trading_app, 'executor'):
                self.trading_app.executor.on_trade_closed_callback = self._on_trade_closed

            QMessageBox.information(self, "Reloaded", "Broker reloaded successfully.")
            logger.info("Broker reloaded successfully")
        except Exception as e:
            logger.error(f"[TradingGUI._reload_broker] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Reload Error", str(e))

    def _show_about(self):
        """Show about dialog"""
        try:
            QMessageBox.about(self, "About",
                              "Algo Trading Dashboard\nVersion 2.0 (PyQt5)\n\n"
                              "© 2025 Your Company. All rights reserved.\n\n"
                              "A professional algorithmic trading platform\n"
                              "supporting LIVE, PAPER, and BACKTEST modes.")
        except Exception as e:
            logger.error(f"[TradingGUI._show_about] Failed: {e}", exc_info=True)

    def _show_documentation(self):
        """Show documentation"""
        try:
            QMessageBox.information(self, "Documentation",
                                    "Documentation would open here.\n\n"
                                    "In a real application, this would open a PDF or web browser.")
        except Exception as e:
            logger.error(f"[TradingGUI._show_documentation] Failed: {e}", exc_info=True)

    def _check_updates(self):
        """Check for updates"""
        try:
            QMessageBox.information(self, "Check Updates",
                                    "This feature would check for updates.\n\n"
                                    "Currently running version 2.0")
        except Exception as e:
            logger.error(f"[TradingGUI._check_updates] Failed: {e}", exc_info=True)

    def _restart_application(self):
        """Restart the application"""
        try:
            reply = QMessageBox.question(
                self, "Restart",
                "Are you sure you want to restart the application?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                logger.info("Restarting application...")
                # Close current instance
                self.close()
                # Start new instance
                QTimer.singleShot(1000, lambda: os.execl(sys.executable, sys.executable, *sys.argv))
        except Exception as e:
            logger.error(f"[TradingGUI._restart_application] Failed: {e}", exc_info=True)

    def _backup_config(self):
        """Backup configuration"""
        try:
            from shutil import copy2
            import json

            backup_dir = "backups"
            os.makedirs(backup_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"{backup_dir}/config_backup_{timestamp}.json"

            config_data = {
                'brokerage': self.brokerage_setting.to_dict() if hasattr(self.brokerage_setting, 'to_dict') else {},
                'daily': self.daily_setting.to_dict() if hasattr(self.daily_setting, 'to_dict') else {},
                'pnl': self.profit_loss_setting.to_dict() if hasattr(self.profit_loss_setting, 'to_dict') else {},
                'mode': self.trading_mode_setting.to_dict() if hasattr(self.trading_mode_setting, 'to_dict') else {}
            }

            with open(backup_file, 'w') as f:
                json.dump(config_data, f, indent=2)

            QMessageBox.information(self, "Backup Complete", f"Configuration backed up to:\n{backup_file}")
            logger.info(f"Configuration backed up to {backup_file}")

        except Exception as e:
            logger.error(f"[TradingGUI._backup_config] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Backup Failed", str(e))

    def _restore_config(self):
        """Restore configuration"""
        try:
            from PyQt5.QtWidgets import QFileDialog
            import json

            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Select Backup File",
                "backups",
                "JSON Files (*.json)"
            )

            if filename:
                with open(filename, 'r') as f:
                    config_data = json.load(f)

                # Restore settings
                if hasattr(self.brokerage_setting, 'from_dict'):
                    self.brokerage_setting.from_dict(config_data.get('brokerage', {}))
                if hasattr(self.daily_setting, 'from_dict'):
                    self.daily_setting.from_dict(config_data.get('daily', {}))
                if hasattr(self.profit_loss_setting, 'from_dict'):
                    self.profit_loss_setting.from_dict(config_data.get('pnl', {}))
                if hasattr(self.trading_mode_setting, 'from_dict'):
                    self.trading_mode_setting.from_dict(config_data.get('mode', {}))

                # Reload trading app
                self._reload_broker()

                QMessageBox.information(self, "Restore Complete", "Configuration restored successfully.")
                logger.info(f"Configuration restored from {filename}")

        except Exception as e:
            logger.error(f"[TradingGUI._restore_config] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Restore Failed", str(e))

    def _clear_cache(self):
        """Clear application cache"""
        try:
            reply = QMessageBox.question(
                self, "Clear Cache",
                "Are you sure you want to clear the cache?\nThis may improve performance but some data will need to be reloaded.",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                # Clear log buffer
                self._log_buffer.clear()

                # Clear chart cache
                self._last_chart_fp = ""

                # Clear trade history cache
                self._trade_file_mtime = 0
                self._last_loaded_trade_data = None

                # FEATURE 5: Reset DailyPnLWidget
                if self.daily_pnl_widget:
                    self.daily_pnl_widget.reset()

                QMessageBox.information(self, "Cache Cleared", "Cache has been cleared successfully.")
                logger.info("Cache cleared")

        except Exception as e:
            logger.error(f"[TradingGUI._clear_cache] Failed: {e}", exc_info=True)

    def _update_trade_history(self):
        """Refresh trade history table only if file changed"""
        try:
            today_file = f"logs/trades_{datetime.now().strftime('%Y-%m-%d')}.csv"

            if not os.path.exists(today_file):
                self.history_popup = None
                return

            try:
                current_mtime = os.path.getmtime(today_file)

                if current_mtime != self._trade_file_mtime:
                    self._trade_file_mtime = current_mtime

                    if self.history_popup is not None and self.history_popup.isVisible():
                        self.history_popup.load_trades_for_date()

            except (OSError, IOError) as e:
                logger.error(f"Failed to check trade file mtime: {e}")

        except Exception as e:
            logger.error(f"[TradingGUI._update_trade_history] Failed: {e}", exc_info=True)

    def _show_strategy_picker(self):
        """Show strategy picker"""
        try:
            if not self.strategy_picker:
                self.strategy_picker = StrategyPickerSidebar(
                    trading_app=self.trading_app,
                    parent=self,
                )
                self.strategy_picker.strategy_activated.connect(self._on_strategy_changed)
                self.strategy_picker.open_editor_requested.connect(self._open_strategy_editor)
            self.strategy_picker.refresh()
            self.strategy_picker.show()
            self.strategy_picker.raise_()
            self.strategy_picker.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_strategy_picker] Failed: {e}", exc_info=True)

    def _open_strategy_editor(self):
        """Open strategy editor"""
        try:
            if not self.strategy_editor:
                self.strategy_editor = StrategyEditorWindow(parent=self)
                self.strategy_editor.strategy_activated.connect(self._on_strategy_changed)
                self.strategy_editor.setWindowState(Qt.WindowMaximized)
                self.strategy_editor.setWindowFlags(Qt.Window)
            self.strategy_editor.show()
            self.strategy_editor.raise_()
            self.strategy_editor.activateWindow()
            if not self.strategy_editor.isMaximized():
                self.strategy_editor.showMaximized()
        except Exception as e:
            logger.error(f"[TradingGUI._open_strategy_editor] Failed: {e}", exc_info=True)

    def _on_strategy_editor_closed(self):
        """Clean up editor reference"""
        try:
            self.strategy_editor = None
        except Exception as e:
            logger.error(f"[TradingGUI._on_strategy_editor_closed] Failed: {e}", exc_info=True)

    def _on_strategy_changed(self, slug: str):
        """Handle strategy change"""
        try:
            self._apply_active_strategy()
            if self.strategy_picker and self.strategy_picker.isVisible():
                self.strategy_picker.refresh()
            self.strategy_changed.emit(slug)
        except Exception as e:
            logger.error(f"[TradingGUI._on_strategy_changed] Failed: {e}", exc_info=True)

    def _apply_active_strategy(self):
        """Apply the active strategy to the trading app"""
        try:
            if not self.strategy_manager:
                logger.warning("No strategy manager available")
                return

            indicator_params = self.strategy_manager.get_active_indicator_params()
            engine_config = self.strategy_manager.get_active_engine_config()

            # Update config object
            for key, value in indicator_params.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)

            # Update DynamicSignalEngine
            if (self.trading_app and
                    hasattr(self.trading_app, "detector") and
                    hasattr(self.trading_app.detector, "signal_engine") and
                    self.trading_app.detector.signal_engine is not None):

                active_slug = self.strategy_manager.get_active_slug()
                if active_slug:
                    self.trading_app.detector.signal_engine.load_from_strategy(active_slug)

            # Update label
            name = self.strategy_manager.get_active_name()
            if hasattr(self, "_active_strategy_lbl") and self._active_strategy_lbl:
                self._active_strategy_lbl.setText(f"⚡  {name}")

            # Update chart
            if hasattr(self, 'chart_widget') and self.chart_widget:
                try:
                    engine = (self.trading_app.detector.signal_engine
                              if self.trading_app and hasattr(self.trading_app, 'detector')
                              else None)
                    self.chart_widget.set_config(self.config, engine)
                except Exception as e:
                    logger.warning(f"Chart config refresh failed: {e}")

            logger.info(f"Applied strategy: {name}")

        except Exception as e:
            logger.error(f"Failed to apply strategy: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event"""
        try:
            logger.info("Application closing, starting cleanup...")

            # Stop timers
            if self.timer_fast:
                self.timer_fast.stop()
            if self.timer_chart:
                self.timer_chart.stop()
            if self.timer_app_status:
                self.timer_app_status.stop()
            if self.timer_connection_check:
                self.timer_connection_check.stop()

            # Close all popups
            self._close_all_popups()

            # Stop trading thread
            if self.app_running and self.trading_thread:
                logger.info("Stopping trading thread...")
                self.trading_thread.request_stop()
                if not self.trading_thread.wait(5000):
                    logger.warning("Trading thread did not stop gracefully, terminating")
                    self.trading_thread.terminate()

            # Cleanup trading app
            if self.trading_app and hasattr(self.trading_app, 'cleanup'):
                try:
                    self.trading_app.cleanup()
                except Exception as e:
                    logger.error(f"Trading app cleanup error: {e}")

            # FEATURE 5: Cleanup DailyPnLWidget
            if self.daily_pnl_widget and hasattr(self.daily_pnl_widget, 'cleanup'):
                try:
                    self.daily_pnl_widget.cleanup()
                except Exception as e:
                    logger.error(f"DailyPnLWidget cleanup error: {e}")

            logger.info("Cleanup completed, closing application")
            event.accept()

        except Exception as e:
            logger.error(f"[TradingGUI.closeEvent] Failed: {e}", exc_info=True)
            event.accept()

    # Rule 8: Cleanup method
    def cleanup(self):
        """Graceful cleanup of resources"""
        try:
            logger.info("[TradingGUI] Starting cleanup")

            # Stop timers
            for timer in [self.timer_fast, self.timer_chart, self.timer_app_status, self.timer_connection_check]:
                if timer is not None:
                    try:
                        timer.stop()
                    except Exception as e:
                        logger.warning(f"Timer stop error: {e}")

            # Close popups
            self._close_all_popups()

            # Stop trading thread
            if self.trading_thread is not None:
                if self.trading_thread.isRunning():
                    try:
                        self.trading_thread.request_stop()
                        if not self.trading_thread.wait(10000):
                            logger.warning("Trading thread timeout, forcing termination")
                            self.trading_thread.terminate()
                            self.trading_thread.wait(2000)
                    except Exception as e:
                        logger.error(f"Thread cleanup error: {e}", exc_info=True)

            # FEATURE 5: Cleanup DailyPnLWidget
            if self.daily_pnl_widget and hasattr(self.daily_pnl_widget, 'cleanup'):
                try:
                    self.daily_pnl_widget.cleanup()
                except Exception as e:
                    logger.error(f"DailyPnLWidget cleanup error: {e}")

            # Remove log handler
            if self._log_handler:
                try:
                    root_logger = logging.getLogger()
                    root_logger.removeHandler(self._log_handler)
                except Exception as e:
                    logger.warning(f"Log handler removal error: {e}")

            logger.info("[TradingGUI] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradingGUI.cleanup] Error: {e}", exc_info=True)