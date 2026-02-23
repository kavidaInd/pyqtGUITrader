# PYQT: Complete replacement for Tkinter TradingGUI.py
import logging
import logging.handlers
import os
import threading
from datetime import datetime
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QHBoxLayout,
    QPushButton, QRadioButton, QAction,
    QMessageBox, QLabel, QVBoxLayout, QFrame
)

# PYQT: Import existing trading engine (unchanged)
import BaseEnums
from config import Config
from gui.BrokerageSetting import BrokerageSetting
from gui.BrokerageSettingGUI import BrokerageSettingGUI
from gui.DailyTradeSetting import DailyTradeSetting
from gui.DailyTradeSettingGUI import DailyTradeSettingGUI
from gui.FyersManualLoginPopup import FyersManualLoginPopup
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
from gui.status_panel import StatusPanel
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

    def __init__(self):
        # Rule 2: Safe defaults first - before any UI setup
        self._safe_defaults_init()

        try:
            super().__init__()
            self.setWindowTitle("Algo Trading Dashboard")
            self.resize(1400, 850)
            self.setMinimumSize(1100, 700)

            # Dark base style - EXACTLY preserved
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
            self.trading_mode_setting = TradingModeSetting()

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

            # FIX: Cache for trade history file modification time
            self._trade_file_mtime = 0
            self._last_loaded_trade_data = None  # Optional: cache the actual data if needed
            self.strategy_manager = StrategyManager()
            self.strategy_editor = None
            self.strategy_picker = None

            # Apply the active strategy immediately
            self._apply_active_strategy()

            # Build UI
            self._setup_log_handler()
            self._create_menu()
            self._build_layout()
            self._setup_timers()
            self._init_trading_app()

            # Rule 3: Connect internal signals
            self._setup_internal_signals()

            logger.info("TradingGUI initialized successfully")

        except Exception as e:
            logger.critical(f"[TradingGUI.__init__] Initialization failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Application initialization failed: {e}")
            # Still try to show a basic window
            super().__init__()
            self.setWindowTitle("Algo Trading Dashboard - ERROR")
            self.resize(1400, 850)

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
        self._trade_file_mtime = 0
        self._last_loaded_trade_data = None
        self.strategy_manager = None
        self.strategy_editor = None
        self.strategy_picker = None
        self._log_handler = None
        self.timer_fast = None
        self.timer_chart = None
        self.timer_app_status = None
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
        self._active_strategy_lbl = None

    def _setup_internal_signals(self):
        """Rule 3: Connect internal signals"""
        try:
            self.error_occurred.connect(self._on_error_signal)
            self.status_updated.connect(self._on_status_updated)
            self.app_state_changed.connect(self._on_app_state_changed)
            self.strategy_changed.connect(self._on_strategy_changed)
        except Exception as e:
            logger.error(f"[TradingGUI._setup_internal_signals] Signal setup failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_error_signal(self, message: str):
        """Handle error signals"""
        try:
            logger.error(f"Error signal received: {message}")
            # Update status bar if available
            if hasattr(self, 'app_status_bar') and self.app_status_bar:
                self.app_status_bar.update_status(
                    {'status': f'Error: {message[:50]}...'},
                    getattr(self, 'trading_mode', 'algo'),
                    getattr(self, 'app_running', False)
                )
        except Exception as e:
            logger.error(f"[TradingGUI._on_error_signal] Failed to handle error: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_status_updated(self, message: str):
        """Handle status updates"""
        try:
            logger.info(f"Status update: {message}")
        except Exception as e:
            logger.error(f"[TradingGUI._on_status_updated] Failed: {e}", exc_info=True)

    @pyqtSlot(bool, str)
    def _on_app_state_changed(self, running: bool, mode: str):
        """Handle app state changes"""
        try:
            self._update_button_states()
        except Exception as e:
            logger.error(f"[TradingGUI._on_app_state_changed] Failed: {e}", exc_info=True)

    def _setup_log_handler(self):
        """# PYQT: Connect Qt log signal to the log widget slot"""
        try:
            self._log_handler = QtLogHandler()
            self._log_handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            )
            self._log_handler.signaller.log_message.connect(self._append_log)

            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)

            # Print existing handlers
            # print(f"Existing handlers before cleanup: {root_logger.handlers}")

            # Remove stale handlers from previous runs
            for h in list(root_logger.handlers):
                if isinstance(h, QtLogHandler):
                    print(f"Removing stale handler: {h}")
                    root_logger.removeHandler(h)

            root_logger.addHandler(self._log_handler)
            # print(f"Handlers after adding: {root_logger.handlers}")

            # Test log immediately
            # logging.info("🟡 TEST LOG FROM SETUP - This should appear in popup")

            # Schedule another test after UI is built
            # QTimer.singleShot(2000, self._test_logging)

        except Exception as e:
            logger.error(f"[TradingGUI._setup_log_handler] Failed: {e}", exc_info=True)

    def _test_logging(self):
        """Test logging at different levels"""
        try:
            print("🧪 Running logging test...")
            logging.debug("DEBUG test message")
            logging.info("INFO test message")
            logging.warning("WARNING test message")
            logging.error("ERROR test message")

            # Also try from different modules
            logger_local = logging.getLogger(__name__)
            logger_local.info(f"Logger for {__name__} test")

            logger2 = logging.getLogger("new_main")
            logger2.info("Test from new_main logger")
        except Exception as e:
            logger.error(f"[TradingGUI._test_logging] Failed: {e}", exc_info=True)

    def _build_layout(self):
        """# PYQT: Build main window layout - chart on left, status on right, buttons below chart"""
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

            # Chart widget
            self.chart_widget = MultiChartWidget()
            self.chart_widget.setMinimumWidth(800)
            left_layout.addWidget(self.chart_widget, 1)  # Give it stretch factor

            # Button panel (now below chart)
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
            root_layout.addWidget(top_splitter, 1)  # Give top splitter stretch factor

            # ── Bottom section: App Status Bar ─────────────────────────────
            self.app_status_bar = AppStatusBar()
            root_layout.addWidget(self.app_status_bar)

        except Exception as e:
            logger.error(f"[TradingGUI._build_layout] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to build layout: {e}")

    def _build_button_panel(self) -> QWidget:
        """# PYQT: Build horizontal button panel below chart"""
        panel = QWidget()
        try:
            panel.setFixedHeight(60)
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
            # Add mode indicator before the mode toggle
            self.mode_label = QLabel(
                f"Mode: {self.trading_mode_setting.mode.value if self.trading_mode_setting else 'algo'}")
            self.mode_label.setStyleSheet(
                "color: #2ea043; font-weight: bold; padding: 5px;"
            )
            layout.addWidget(self.mode_label)

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
            def make_btn(text, color, hover, icon=None):
                btn = QPushButton(text)
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
            layout.addWidget(self.btn_strategy)  # add before btn_start

            # Control buttons
            self.btn_start = make_btn("▶  Start", "#238636", "#2ea043")
            self.btn_stop = make_btn("■  Stop", "#da3633", "#f85149")
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
        """# PYQT: QTimer always fires on the main thread — safe to update widgets"""
        try:
            self.timer_fast = QTimer(self)
            self.timer_fast.timeout.connect(self._tick_fast)
            self.timer_fast.start(1000)  # 1s — status, stats

            # CHART FIX: Use longer interval and debounce
            self.timer_chart = QTimer(self)
            self.timer_chart.timeout.connect(self._tick_chart)
            self.timer_chart.start(5000)
            self._last_chart_fp = ""
            self._chart_update_pending = False

            self.timer_app_status = QTimer(self)
            self.timer_app_status.timeout.connect(self._update_app_status)
            self.timer_app_status.start(500)

        except Exception as e:
            logger.error(f"[TradingGUI._setup_timers] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _tick_fast(self):
        """# PYQT: Runs on main thread — safe to update all widgets"""
        try:
            if self.trading_app is None:
                return
            state = self.trading_app.state
            self.status_panel.refresh(state, self.config)

            # Update popups if they're open
            if self.stats_popup and self.stats_popup.isVisible():
                self.stats_popup.refresh()

            if self.signal_debug_popup and self.signal_debug_popup.isVisible():
                self.signal_debug_popup.refresh()

            self._update_button_states()

        except Exception as e:
            logger.error(f"[TradingGUI._tick_fast] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _tick_chart(self):
        """# PYQT: Update chart and trade history with throttling"""
        try:
            if self.trading_app is None:
                return

            # Update chart
            self._update_chart_if_needed()

            # FIX: Update trade history on 5-second timer instead of 1-second
            self._update_trade_history()

        except Exception as e:
            logger.error(f"[TradingGUI._tick_chart] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _update_app_status(self):
        """Update application status from trading app"""
        try:
            if self.trading_app is None:
                return

            # Get status information from trading app
            status_info = {}

            # Check history fetch status
            if hasattr(self.trading_app, '_history_fetch_in_progress'):
                status_info['fetching_history'] = self.trading_app._history_fetch_in_progress.is_set()

            # Check processing status
            if hasattr(self.trading_app, '_processing_in_progress'):
                status_info['processing'] = self.trading_app._processing_in_progress.is_set()

            # Check order pending status
            if hasattr(self.trading_app.state, 'order_pending'):
                status_info['order_pending'] = self.trading_app.state.order_pending

            # Check if position is active
            if hasattr(self.trading_app.state, 'current_position'):
                status_info['has_position'] = self.trading_app.state.current_position is not None

            # Check if trade is confirmed
            if hasattr(self.trading_app.state, 'current_trade_confirmed'):
                status_info['trade_confirmed'] = self.trading_app.state.current_trade_confirmed

            # Get last reason to exit if any
            if hasattr(self.trading_app.state, 'reason_to_exit'):
                status_info['last_exit_reason'] = self.trading_app.state.reason_to_exit

            # Update the status bar
            self.app_status_bar.update_status(
                status_info,
                getattr(self, 'trading_mode', 'algo'),
                getattr(self, 'app_running', False)
            )

        except Exception as e:
            logger.error(f"[TradingGUI._update_app_status] Failed: {e}", exc_info=True)

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
            except:
                # If fingerprint fails, still update but throttle
                if not self._chart_update_pending:
                    self._chart_update_pending = True
                    QTimer.singleShot(100, self._do_chart_update)

        except Exception as e:
            logger.error(f"[TradingGUI._update_chart_if_needed] Failed: {e}", exc_info=True)
            self._chart_update_pending = False

    # AFTER:
    def _do_chart_update(self):
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
        """# PYQT: Enable/disable buttons based on app state"""
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
        """# PYQT: Create the trading app instance"""
        try:
            self.trading_app = TradingApp(
                config=self.config,
                broker_setting=self.brokerage_setting,
            )

            # Wire up chart config + signal engine
            try:
                engine = getattr(
                    getattr(self.trading_app, 'detector', None),
                    'signal_engine', None
                )
                self.chart_widget.set_config(self.config, engine)
                logging.info("Chart config set from trading app")
            except Exception as e:
                logging.warning(f"Could not set chart config: {e}")
                self.chart_widget.set_config(self.config, None)
            # Connect to app status updates
            self.app_status_bar.update_status({
                'initialized': True,
                'status': 'App initialized'
            }, self.trading_mode, False)

            logger.info("TradingApp initialized successfully")

        except Exception as e:
            logger.critical(f"Failed to create TradingApp: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to connect to broker: {e}")
            QMessageBox.critical(self, "Init Error",
                                 f"Could not connect to broker:\n{e}\n\n"
                                 "Check credentials via Settings → Brokerage Settings.")

    @pyqtSlot()
    def _start_app(self):
        """# PYQT: Start trading engine on QThread"""
        try:
            if self.trading_app is None:
                logger.error("Start failed: Trading app not initialized")
                QMessageBox.critical(self, "Error", "Trading app not initialised.")
                return

            # PYQT: Run trading engine on QThread — never on main thread
            self.trading_thread = TradingThread(self.trading_app)
            self.trading_thread.error_occurred.connect(self._on_engine_error)
            self.trading_thread.finished.connect(self._on_engine_finished)
            self.trading_thread.start()
            self.app_running = True
            self.app_status_bar.update_status({'status': 'Starting...'}, self.trading_mode, True)
            self._update_button_states()

            logger.info("Trading engine started")
            self.app_state_changed.emit(True, self.trading_mode)

        except Exception as e:
            logger.error(f"[TradingGUI._start_app] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to start trading engine: {e}")

    @pyqtSlot()
    def _stop_app(self):
        """# PYQT: Stop the trading engine"""
        try:
            self.btn_stop.setDisabled(True)
            self.app_status_bar.update_status({'status': 'Stopping...'}, self.trading_mode, True)
            # PYQT: Stop is blocking — run on a plain daemon thread, not main thread
            threading.Thread(target=self._threaded_stop, daemon=True, name="StopThread").start()

            logger.info("Trading engine stopping...")

        except Exception as e:
            logger.error(f"[TradingGUI._stop_app] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to stop trading engine: {e}")

    def _threaded_stop(self):
        """# PYQT: Background stop work"""
        try:
            if self.trading_thread:
                self.trading_thread.stop()
            # PYQT: Post result back to main thread via QTimer.singleShot
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self._on_engine_finished)

            logger.debug("Stop thread completed")

        except Exception as e:
            logger.error(f"[TradingGUI._threaded_stop] Failed: {e}", exc_info=True)
            QTimer.singleShot(0, lambda: self.error_occurred.emit(f"Stop failed: {e}"))

    @pyqtSlot()
    def _on_engine_finished(self):
        """# PYQT: Slot — always called on main thread"""
        try:
            self.app_running = False
            self.app_status_bar.update_status({'status': 'Stopped'}, self.trading_mode, False)
            self._update_button_states()

            logger.info("Trading engine stopped")
            self.app_state_changed.emit(False, self.trading_mode)

        except Exception as e:
            logger.error(f"[TradingGUI._on_engine_finished] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_engine_error(self, message: str):
        """# PYQT: Slot — always called on main thread"""
        try:
            self.app_running = False
            self.app_status_bar.update_status({'status': f'Error: {message[:50]}...'}, self.trading_mode, False)
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

            logger.error(f"Engine error: {message}")
            self.error_occurred.emit(message)

        except Exception as e:
            logger.error(f"[TradingGUI._on_engine_error] Failed to handle error: {e}", exc_info=True)

    def _manual_buy(self, option_type):
        """# PYQT: Manual buy in background thread"""
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
        """# PYQT: Manual exit in background thread"""
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
        """# PYQT: Handle mode switch"""
        try:
            self.trading_mode = "algo" if self.radio_algo.isChecked() else "manual"
            self.app_status_bar.update_status({}, self.trading_mode, self.app_running)
            self._update_button_states()

            logger.info(f"Trading mode changed to: {self.trading_mode}")
            self.app_state_changed.emit(self.app_running, self.trading_mode)

        except Exception as e:
            logger.error(f"[TradingGUI._on_mode_change] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _append_log(self, message: str):
        """# PYQT: Connected to QtLogHandler signal — always on main thread"""
        try:
            # Also append to popup if it's open
            if self.log_popup and self.log_popup.isVisible():
                self.log_popup.append_log(message)
        except Exception as e:
            logger.error(f"[TradingGUI._append_log] Failed: {e}", exc_info=True)

    def _create_menu(self):
        """# PYQT: Build menu bar with View menu for popups"""
        try:
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

            sig_debug_act = QAction("🔬 Dynamic Signal Debug", self)
            sig_debug_act.triggered.connect(self._show_signal_debug_popup)
            view_menu.addAction(sig_debug_act)

            view_menu.addSeparator()
            picker_act = QAction("⚡ Strategy Picker", self)
            picker_act.triggered.connect(self._show_strategy_picker)
            view_menu.addAction(picker_act)

            editor_act = QAction("📋 Strategy Editor", self)
            editor_act.triggered.connect(self._open_strategy_editor)
            view_menu.addAction(editor_act)

            view_menu.addSeparator()
            close_all_act = QAction("Close All Popups", self)
            close_all_act.triggered.connect(self._close_all_popups)
            view_menu.addAction(close_all_act)

            # Settings menu
            settings_menu = menubar.addMenu("Settings")
            actions = [
                ("Strategy Settings", self._show_strategy_picker),
                ("Daily Trade Settings", self._open_daily),
                ("Profit & Loss Settings", self._open_pnl),
                ("Brokerage Settings", self._open_brokerage),
                ("Manual Fyers Login", self._open_login),
            ]
            for label, slot in actions:
                act = QAction(label, self)
                act.triggered.connect(slot)
                settings_menu.addAction(act)

            mode_act = QAction("🎮 Trading Mode Settings", self)
            mode_act.triggered.connect(self._open_trading_mode)
            settings_menu.addAction(mode_act)
            # Help menu
            help_menu = menubar.addMenu("Help")
            about_act = QAction("About", self)
            about_act.triggered.connect(self._show_about)
            help_menu.addAction(about_act)

        except Exception as e:
            logger.error(f"[TradingGUI._create_menu] Failed: {e}", exc_info=True)

    # Popup window handlers
    def _show_log_popup(self):
        """Show log popup window"""
        try:
            if not self.log_popup:
                self.log_popup = LogPopup(self)
            self.log_popup.show()
            self.log_popup.raise_()
            self.log_popup.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_log_popup] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to show log popup: {e}")

    def _show_history_popup(self):
        """Show trade history popup window"""
        try:
            if not self.history_popup:
                self.history_popup = TradeHistoryPopup(self)
            self.history_popup.load_trades_for_date()
            self.history_popup.show()
            self.history_popup.raise_()
            self.history_popup.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_history_popup] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to show history popup: {e}")

    def _open_trading_mode(self):
        """Open trading mode settings dialog"""
        try:
            dlg = TradingModeSettingGUI(
                self,
                trading_mode_setting=self.trading_mode_setting,
                app=self.trading_app
            )
            if dlg.exec_():
                # Settings saved, update UI if needed
                self._update_mode_display()
        except Exception as e:
            logger.error(f"[TradingGUI._open_trading_mode] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to open trading mode settings: {e}")

    def _update_mode_display(self):
        """Update UI to show current trading mode"""
        try:
            mode = self.trading_mode_setting.mode.value if self.trading_mode_setting else "algo"
            color = "#f85149" if (self.trading_mode_setting and self.trading_mode_setting.is_live()) else "#2ea043"

            # Add mode indicator to status bar or somewhere visible
            if hasattr(self, 'mode_label') and self.mode_label:
                self.mode_label.setText(f"Mode: {mode}")
                self.mode_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        except Exception as e:
            logger.error(f"[TradingGUI._update_mode_display] Failed: {e}", exc_info=True)

    def _show_stats_popup(self):
        """Show statistics popup window"""
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

    def _close_all_popups(self):
        """Close all popup windows"""
        try:
            if self.log_popup:
                self.log_popup.close()
            if self.history_popup:
                self.history_popup.close()
            if self.stats_popup:
                self.stats_popup.close()
            if self.signal_debug_popup:
                self.signal_debug_popup.close()
            if self.strategy_picker:
                self.strategy_picker.close()
            if self.strategy_editor:
                self.strategy_editor.close()
        except Exception as e:
            logger.error(f"[TradingGUI._close_all_popups] Failed: {e}", exc_info=True)

    def _open_daily(self):
        try:
            dlg = DailyTradeSettingGUI(self, daily_setting=self.daily_setting,
                                       app=self.trading_app)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_daily] Failed: {e}", exc_info=True)

    def _open_pnl(self):
        try:
            dlg = ProfitStoplossSettingGUI(self, profit_stoploss_setting=self.profit_loss_setting,
                                           app=self.trading_app)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_pnl] Failed: {e}", exc_info=True)

    def _open_brokerage(self):
        try:
            dlg = BrokerageSettingGUI(self, self.brokerage_setting)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_brokerage] Failed: {e}", exc_info=True)

    def _open_login(self):
        try:
            dlg = FyersManualLoginPopup(self, self.brokerage_setting)
            dlg.exec_()
            self._reload_broker()
        except Exception as e:
            logger.error(f"[TradingGUI._open_login] Failed: {e}", exc_info=True)

    def _show_signal_debug_popup(self):
        try:
            if not self.trading_app:
                QMessageBox.information(self, "Not Ready", "Trading app not initialized yet.")
                return
            if not self.signal_debug_popup:
                self.signal_debug_popup = DynamicSignalDebugPopup(self.trading_app, self)
            self.signal_debug_popup.show()
            self.signal_debug_popup.raise_()
            self.signal_debug_popup.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_signal_debug_popup] Failed: {e}", exc_info=True)

    def _reload_broker(self):
        """# PYQT: Reload after login"""
        try:
            self.trading_app = TradingApp(
                config=self.config,
                broker_setting=self.brokerage_setting,
            )
            QMessageBox.information(self, "Reloaded", "Broker reloaded successfully.")
            logger.info("Broker reloaded successfully")
        except Exception as e:
            logger.error(f"[TradingGUI._reload_broker] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Reload Error", str(e))

    def _show_about(self):
        try:
            QMessageBox.about(self, "About",
                              "Algo Trading Dashboard\nVersion 2.0 (PyQt5)\n\n"
                              "© 2025 Your Company. All rights reserved.")
        except Exception as e:
            logger.error(f"[TradingGUI._show_about] Failed: {e}", exc_info=True)

    # FIX: Optimized trade history update with mtime caching
    def _update_trade_history(self):
        """# PYQT: Refresh trade history table only if file changed"""
        try:
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

        except Exception as e:
            logger.error(f"[TradingGUI._update_trade_history] Failed: {e}", exc_info=True)

    def closeEvent(self, event):
        """# PYQT: Stop timers, close popups, and stop engine before closing"""
        try:
            logger.info("Application closing, starting cleanup...")

            self.timer_fast.stop()
            self.timer_chart.stop()
            self.timer_app_status.stop()

            # Close all popups
            self._close_all_popups()

            if self.app_running and self.trading_thread:
                threading.Thread(target=self.trading_thread.stop,
                                 daemon=True, name="CloseStop").start()

            logger.info("Cleanup completed, closing application")
            event.accept()

        except Exception as e:
            logger.error(f"[TradingGUI.closeEvent] Failed: {e}", exc_info=True)
            event.accept()  # Still close even if cleanup fails

    def _show_strategy_picker(self):
        try:
            if not self.strategy_picker:
                self.strategy_picker = StrategyPickerSidebar(
                    manager=self.strategy_manager,
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

    # In TradingGUI.py, add/replace these methods:

    def _open_strategy_editor(self):
        """Open strategy editor as a full-page window"""
        try:
            if not self.strategy_editor:
                self.strategy_editor = StrategyEditorWindow(self.strategy_manager, parent=self)
                self.strategy_editor.strategy_activated.connect(self._on_strategy_changed)
                # Make it a full window
                self.strategy_editor.setWindowState(Qt.WindowMaximized)
                self.strategy_editor.setWindowFlags(Qt.Window)  # Ensure it's a top-level window
            self.strategy_editor.show()
            self.strategy_editor.raise_()
            self.strategy_editor.activateWindow()
            # Ensure it's maximized
            if not self.strategy_editor.isMaximized():
                self.strategy_editor.showMaximized()
        except Exception as e:
            logger.error(f"[TradingGUI._open_strategy_editor] Failed: {e}", exc_info=True)

    def _on_strategy_editor_closed(self):
        """Clean up reference when editor is closed"""
        try:
            self.strategy_editor = None
        except Exception as e:
            logger.error(f"[TradingGUI._on_strategy_editor_closed] Failed: {e}", exc_info=True)

    def _on_strategy_changed(self, slug: str):
        try:
            self._apply_active_strategy()
            # Refresh picker if open
            if self.strategy_picker and self.strategy_picker.isVisible():
                self.strategy_picker.refresh()
            self.strategy_changed.emit(slug)
        except Exception as e:
            logger.error(f"[TradingGUI._on_strategy_changed] Failed: {e}", exc_info=True)

    def _apply_active_strategy(self):
        try:
            if not self.strategy_manager:
                logger.warning("No strategy manager available")
                return

            indicator_params = self.strategy_manager.get_active_indicator_params()
            engine_config = self.strategy_manager.get_active_engine_config()

            # 1. Update the config object that TrendDetector reads
            for key, value in indicator_params.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)

            # 2. Update DynamicSignalEngine rules live
            if (self.trading_app and
                    hasattr(self.trading_app, "detector") and
                    hasattr(self.trading_app.detector, "signal_engine") and
                    self.trading_app.detector.signal_engine is not None):
                self.trading_app.detector.signal_engine.from_dict(engine_config)

            # 3. Update toolbar label
            name = self.strategy_manager.get_active_name()
            if hasattr(self, "_active_strategy_lbl") and self._active_strategy_lbl:
                self._active_strategy_lbl.setText(f"⚡  {name}")

            if hasattr(self, 'chart_widget') and self.chart_widget:
                try:
                    engine = (self.trading_app.detector.signal_engine
                              if self.trading_app
                                 and hasattr(self.trading_app, 'detector')
                              else None)
                    self.chart_widget.set_config(self.config, engine)
                except Exception as e:
                    logging.warning(f"Chart config refresh failed: {e}")

            logging.info(f"Applied strategy: {name}")

        except Exception as e:
            logger.error(f"Failed to apply strategy: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Graceful cleanup of resources"""
        try:
            logger.info("[TradingGUI] Starting cleanup")

            # Stop timers
            if hasattr(self, 'timer_fast') and self.timer_fast:
                try:
                    self.timer_fast.stop()
                except Exception as e:
                    logger.warning(f"Fast timer stop error: {e}")

            if hasattr(self, 'timer_chart') and self.timer_chart:
                try:
                    self.timer_chart.stop()
                except Exception as e:
                    logger.warning(f"Chart timer stop error: {e}")

            if hasattr(self, 'timer_app_status') and self.timer_app_status:
                try:
                    self.timer_app_status.stop()
                except Exception as e:
                    logger.warning(f"Status timer stop error: {e}")

            # Close popups
            self._close_all_popups()

            # Stop trading thread
            if hasattr(self, 'trading_thread') and self.trading_thread:
                if self.trading_thread.isRunning():
                    try:
                        self.trading_thread.request_stop()
                        if not self.trading_thread.wait(10000):
                            logger.warning("Trading thread timeout, forcing termination")
                            self.trading_thread.terminate()
                            self.trading_thread.wait(2000)
                    except Exception as e:
                        logger.error(f"Thread cleanup error: {e}", exc_info=True)

            logger.info("[TradingGUI] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradingGUI.cleanup] Error: {e}", exc_info=True)