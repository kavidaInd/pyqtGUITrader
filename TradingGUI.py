# gui/trading_gui.py
"""
Main trading dashboard window for the Algo Trading application.
Provides the primary user interface for monitoring and controlling the trading engine.

FIXES APPLIED
=============
BUG-1  [CRITICAL] _do_chart_update blocked GUI — candle_store_manager.fetch_all()
       was called synchronously on the main thread via QTimer.singleShot (which
       does NOT offload to a background thread). Fixed: fetch runs in a daemon
       thread; chart data is marshalled back to the main thread via the new
       _chart_data_ready pyqtSignal.

BUG-2  [CRITICAL] _force_chart_refresh called _do_chart_update() directly on the
       main thread.  Fixed: now calls the refactored (non-blocking) version.

BUG-3  [HIGH] candle_store_manager.fetch_all() never returned its results dict —
       the function fell off the end and implicitly returned None, so
       `success.get(symbol, False)` raised AttributeError every time.
       Fixed in the new _fetch_chart_data_bg helper by guarding for None.
       (The fix to fetch_all itself belongs in candle_store_manager.py — a
       comment is left there; see note at bottom of this file.)

BUG-4  [HIGH] _chart_update_pending was never reset to False when the background
       fetch thread was started, only in _do_chart_update's finally block which
       no longer executes on the main thread.  Fixed: the flag is now cleared
       inside _fetch_chart_data_bg's finally clause.

BUG-5  [MEDIUM] _on_timeframe_changed called _force_chart_refresh() which, before
       this patch, blocked the GUI.  Fixed transitively by BUG-2.

BUG-6  [MEDIUM] _threaded_stop posted _on_engine_finished via QTimer.singleShot(0)
       but also the TradingThread.finished signal was connected to the same slot,
       so _on_engine_finished was called twice on every normal stop (double-reset
       of app_running, double status-bar update, double app_state_changed emit).
       Fixed: _threaded_stop no longer posts the extra singleShot call; the
       TradingThread.finished signal is sufficient.

BUG-7  [MEDIUM] _update_button_states compared trading_mode_setting.mode (an Enum)
       to the string literal "Backtest" with == — this always evaluated False
       because Enum.__eq__ compares by identity/value, not display name.  Fixed:
       comparison uses .value.upper() == "BACKTEST" consistently.

BUG-8  [LOW] _setup_internal_signals connected trade_closed and
       unrealized_pnl_updated before _chart_data_ready was declared, so if that
       signal were ever added later it would miss the connect call.  Fixed by
       adding _chart_data_ready to signal declarations and connecting it inside
       _setup_internal_signals.

BUG-9  [LOW] strategy_manager was initialised to None in _safe_defaults_init and
       never assigned — _apply_active_strategy (called in __init__) would silently
       bail out every time.  The attribute is now created via StrategyManager() the
       same way TradingApp does it.  (Assumes StrategyManager is importable here.)
"""

import logging
import logging.handlers
import os
import sys
import threading
from datetime import datetime

import pandas as pd
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QHBoxLayout, QVBoxLayout,
    QPushButton, QRadioButton, QAction, QMessageBox, QLabel,
    QFrame, QApplication, QSizePolicy
)

import BaseEnums
from Utils.common import to_date_str
from Utils.safe_getattr import safe_getattr, safe_setattr, safe_hasattr
from config import Config
# IMPORTANT: Use the state manager for all state access
from data.trade_state_manager import state_manager
from gui.app_status_bar import AppStatusBar
from gui.brokerage_settings.BrokerageSetting import BrokerageSetting
from gui.brokerage_settings.BrokerageSettingGUI import BrokerageSettingDialog
from gui.brokerage_settings.Brokerloginpopup import BrokerLoginPopup
from gui.chart_widget import MultiChartWidget
from gui.daily_trade.DailyTradeSetting import DailyTradeSetting
from gui.daily_trade.DailyTradeSettingGUI import DailyTradeSettingGUI
from gui.log_handler import QtLogHandler
from gui.popups.connection_monitor_popup import ConnectionMonitorPopup
from gui.popups.dynamic_signal_debug_popup import DynamicSignalDebugPopup
from gui.popups.logs_popup import LogPopup
from gui.popups.stats_popup import StatsPopup
from gui.popups.system_monitor_popup import SystemMonitorPopup
from gui.popups.trade_history_popup import TradeHistoryPopup
from gui.profit_loss.ProfitStoplossSetting import ProfitStoplossSetting
from gui.profit_loss.ProfitStoplossSettingGUI import ProfitStoplossSettingGUI
from gui.profit_loss.daily_pnl_widget import DailyPnLWidget
from gui.status_panel import StatusPanel
from gui.theme_manager import theme_manager
from gui.trading_mode.TradingModeSetting import TradingModeSetting
from gui.trading_mode.TradingModeSettingGUI import TradingModeSettingGUI
from license.license_manager import license_manager
from new_main import TradingApp
from broker.BaseBroker import TokenExpiredError
from strategy.strategy_editor_window import StrategyEditorWindow
from strategy.strategy_manager import StrategyManager
from strategy.strategy_picker_sidebar import StrategyPickerSidebar
from trading_thread import TradingThread

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TradingGUI(QMainWindow):
    """Main trading dashboard window - replaces Tkinter TradingGUI class"""

    error_occurred = pyqtSignal(str)
    status_updated = pyqtSignal(str)
    app_state_changed = pyqtSignal(bool, str)
    strategy_changed = pyqtSignal(str)
    log_message_received = pyqtSignal(str)

    trade_closed = pyqtSignal(float, bool)       # pnl, is_winner
    unrealized_pnl_updated = pyqtSignal(float)   # unrealized P&L

    # BUG-1 FIX: Signal used to marshal chart data from background thread → main thread.
    # Never emit this directly; use _fetch_chart_data_bg instead.
    _chart_data_ready = pyqtSignal(dict)
    _broker_ready     = pyqtSignal()        # emitted by BrokerInitThread on success
    _broker_failed    = pyqtSignal(str, bool)  # (error_msg, is_token_expired)

    def __init__(self):
        self._safe_defaults_init()

        try:
            super().__init__()
            self.setWindowTitle("Algo Trading Dashboard")

            screen = QApplication.primaryScreen()
            if screen:
                screen_rect = screen.availableGeometry()
                width = min(1400, int(screen_rect.width() * 0.8))
                height = min(850, int(screen_rect.height() * 0.8))
                self.resize(width, height)
            else:
                self.resize(1400, 850)

            self.setMinimumSize(1100, 700)

            self.config = Config()

            self.brokerage_setting = BrokerageSetting()
            self.brokerage_setting.load()

            self.daily_setting = DailyTradeSetting()
            self.daily_setting.load()

            self.profit_loss_setting = ProfitStoplossSetting()
            self.profit_loss_setting.load()

            self.trading_mode_setting = TradingModeSetting()
            self.trading_mode_setting.load()

            # BUG-9 FIX: actually create the strategy_manager (was always None)
            self.strategy_manager = StrategyManager()

            self._apply_active_strategy()

            # Build UI
            self._setup_log_handler()
            self._create_menu()
            self._build_layout()
            self._setup_timers()

            self._initialize_infrastructure()
            self._init_trading_app()

            self._setup_system_tray()

            self._setup_internal_signals()

            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            # load_preference() internally calls apply_startup_theme() which:
            #   1. Pushes the global QApplication stylesheet unconditionally
            #   2. Emits theme_changed + density_changed → triggers self.apply_theme()
            # This guarantees buttons, navbar and all widgets are painted correctly
            # on first show, even when saved theme == default ("dark"+"normal") and
            # set_theme/set_density would otherwise skip the stylesheet write.
            theme_manager.load_preference()

            # Set initial status
            self.status_updated.emit("Application initialized successfully")
            logger.info("[TradingGUI.__init__] Initialized successfully")

        except Exception as e:
            logger.critical(f"[TradingGUI.__init__] Initialization failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Application initialization failed: {e}")
            self._create_error_window()

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        try:
            self._is_initialized = False
            self._closing = False
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
            self.timer_market_status = None
            self._last_chart_fp = ""
            # BUG-4 FIX: this flag is now also reset inside the background thread's
            # finally block, so initialise it here as before.
            self._chart_update_pending = False
            self.chart_widget = None
            self.status_panel = None
            self.app_status_bar = None
            self.mode_label = None
            self._backtest_window = None
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
            self._market_status = "UNKNOWN"
            self._market_status_check_timer = None
            self._theme_action = None
            self._density_menu = None
            self._compact_menu_actions = []
            self.btn_panel = None
            self.manual_buttons_container = None
            self._splitter = None
            self._main_layout = None
        except Exception as e:
            logger.error(f"[TradingGUI._safe_defaults_init] Failed: {e}", exc_info=True)

    # =========================================================================
    # Shorthand properties for theme tokens (Rule 13.3)
    # =========================================================================
    @property
    def _c(self):
        """Shorthand for colour palette"""
        return theme_manager.palette

    @property
    def _ty(self):
        """Shorthand for typography tokens"""
        return theme_manager.typography

    @property
    def _sp(self):
        """Shorthand for spacing tokens"""
        return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Re-apply colours, layout margins, and spacing from the active theme.
        Called on theme change, density change, and initial render.
        """
        try:
            if self._closing:
                return

            c = self._c
            ty = self._ty
            sp = self._sp

            if safe_hasattr(self, 'centralWidget') and self.centralWidget():
                central = self.centralWidget()
                if central.layout():
                    central.layout().setContentsMargins(
                        sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM
                    )
                    central.layout().setSpacing(sp.GAP_SM)
                    self._main_layout = central.layout()

            if self.btn_panel:
                self.btn_panel.setMinimumHeight(sp.BUTTON_PANEL_H - 8)
                self.btn_panel.setMaximumHeight(sp.BUTTON_PANEL_H + 8)
                self.btn_panel.setStyleSheet(f"""
                    QWidget#buttonPanel {{
                        background-color: {c.BG_PANEL};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                    }}
                """)

            if safe_hasattr(self, '_splitter') and self._splitter:
                self._splitter.setHandleWidth(sp.SPLITTER)

            if self.app_status_bar and safe_hasattr(self.app_status_bar, 'apply_theme'):
                self.app_status_bar.apply_theme()

            # The global app stylesheet (set by theme_manager._build_app_stylesheet)
            # handles ALL widget types including buttons, inputs, tabs etc.
            # Here we only need to ensure the window background is correct and
            # forward density-dependent layout updates.
            # DO NOT re-specify button colors here — they are in the global stylesheet
            # via object-name selectors (startBtn, stopBtn, etc.) which update
            # automatically when theme_manager.set_theme() rebuilds the global sheet.
            self.setStyleSheet(f"""
                QMainWindow {{
                    background-color: {c.BG_MAIN};
                }}
                QWidget#centralWidget {{
                    background-color: {c.BG_MAIN};
                }}
                QFrame#buttonPanel {{
                    background-color: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                }}
                QFrame[frameShape="5"] {{
                    border: none;
                    background-color: {c.BORDER};
                    width: {sp.SEPARATOR}px;
                }}
            """)

            if self._theme_action:
                is_dark = theme_manager.is_dark()
                self._theme_action.setText("🌙  Dark Theme" if is_dark else "☀️  Light Theme")
                self._theme_action.setChecked(is_dark)

            self._update_connection_button()

            if self.radio_algo and self.radio_manual:
                # Radio buttons are styled by the global stylesheet via QRadioButton selector.
                # No per-widget setStyleSheet needed — this ensures theme changes propagate
                # without stale inline styles overriding the new palette.
                pass

            self._update_mode_display()

            logger.debug(
                f"[TradingGUI.apply_theme] Applied {theme_manager.current_theme} theme, density={theme_manager.current_density}")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[TradingGUI.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[TradingGUI.apply_theme] Failed: {e}", exc_info=True)

    def _update_connection_button(self):
        """Update connection button styling based on current status and theme"""
        try:
            if not self.btn_connection:
                return
            if self._closing:
                return

            if self._connection_status == "Connected":
                self.btn_connection.setText("🔗 Connected")
                self.btn_connection.setToolTip("Connected to broker - click for details")
                # Use object name so global stylesheet handles all theme variants
                self.btn_connection.setObjectName("connectionBtnConnected")
                # Force stylesheet refresh by re-polishing
                self.btn_connection.style().unpolish(self.btn_connection)
                self.btn_connection.style().polish(self.btn_connection)
            else:
                self.btn_connection.setText("🔌 Disconnected")
                self.btn_connection.setToolTip("Disconnected from broker - click for details")
                self.btn_connection.setObjectName("connectionBtnDisconnected")
                self.btn_connection.style().unpolish(self.btn_connection)
                self.btn_connection.style().polish(self.btn_connection)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[TradingGUI._update_connection_button] Failed: {e}", exc_info=True)

    def _initialize_infrastructure(self):
        """Initialize the infrastructure managers"""
        try:
            if self._closing:
                return
            state_manager.reset_for_backtest()
            from data.candle_store_manager import candle_store_manager
            candle_store_manager.initialize(None)
            logger.info("[TradingGUI._initialize_infrastructure] Infrastructure managers initialized")
        except Exception as e:
            logger.error(f"[TradingGUI._initialize_infrastructure] Failed: {e}", exc_info=True)

    def _create_error_window(self):
        """Create error window if initialization fails"""
        try:
            super().__init__()
            self.setWindowTitle("Algo Trading Dashboard - ERROR")

            screen = QApplication.primaryScreen()
            if screen:
                screen_rect = screen.availableGeometry()
                width = min(800, int(screen_rect.width() * 0.6))
                height = min(600, int(screen_rect.height() * 0.5))
                self.resize(width, height)
            else:
                self.resize(800, 600)

            self.setMinimumSize(600, 400)

            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)
            self._main_layout = layout

            sp = self._sp
            layout.setContentsMargins(sp.PAD_LG, sp.PAD_LG, sp.PAD_LG, sp.PAD_LG)
            layout.setSpacing(sp.GAP_MD)

            c = self._c
            ty = self._ty

            error_label = QLabel("⚠️ Application failed to initialize properly")
            error_label.setAlignment(Qt.AlignCenter)
            error_label.setStyleSheet(f"""
                color: {c.RED_BRIGHT}; 
                font-size: {ty.SIZE_XL}pt; 
                font-weight: {ty.WEIGHT_BOLD}; 
                padding: {sp.PAD_XL}px;
                background-color: transparent;
            """)
            layout.addWidget(error_label)

            details_label = QLabel("Check the logs for more information.")
            details_label.setAlignment(Qt.AlignCenter)
            details_label.setStyleSheet(f"""
                color: {c.TEXT_DIM}; 
                font-size: {ty.SIZE_MD}pt; 
                padding: {sp.PAD_MD}px;
                background-color: transparent;
            """)
            layout.addWidget(details_label)

            close_btn = QPushButton("Close Application")
            close_btn.setObjectName("dangerBtn")
            close_btn.setToolTip("Exit the application")
            close_btn.setStyleSheet(theme_manager.button_stylesheet("RED", "RED_BRIGHT"))
            close_btn.setMinimumWidth(200)
            close_btn.setMinimumHeight(sp.BTN_HEIGHT_MD)
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn, 0, Qt.AlignCenter)

            layout.addStretch()

            self.setStyleSheet(f"""
                QMainWindow, QWidget {{ 
                    background-color: {c.BG_MAIN}; 
                    color: {c.TEXT_MAIN}; 
                }}
            """)

        except Exception as e:
            logger.error(f"[TradingGUI._create_error_window] Failed: {e}")

    def _setup_internal_signals(self):
        """Rule 3: Connect internal signals"""
        try:
            if self._closing:
                return

            self.error_occurred.connect(self._on_error_signal)
            self.status_updated.connect(self._on_status_updated)
            self.app_state_changed.connect(self._on_app_state_changed)
            self.strategy_changed.connect(self._on_strategy_changed)
            self.log_message_received.connect(self._on_log_message)

            self.trade_closed.connect(self._on_trade_closed)
            self.unrealized_pnl_updated.connect(self._on_unrealized_pnl_updated)

            # BUG-1 FIX: connect background-fetch → main-thread chart render
            self._chart_data_ready.connect(self._on_chart_data_ready)
            self._broker_ready.connect(self._on_broker_ready)
            self._broker_failed.connect(self._on_broker_failed)

            logger.debug("[TradingGUI._setup_internal_signals] Signals connected")
        except Exception as e:
            logger.error(f"[TradingGUI._setup_internal_signals] Signal setup failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_error_signal(self, message: str):
        """Handle error signals"""
        try:
            if self._closing:
                return
            logger.error(f"[TradingGUI._on_error_signal] Error signal received: {message}")
            if self.app_status_bar is not None:
                self.app_status_bar.update_status(
                    {'status': f'Error: {message[:50]}...', 'error': True},
                    self.trading_mode,
                    self.app_running
                )
            if any(keyword in message.lower() for keyword in ['critical', 'fatal', 'crash']):
                QMessageBox.critical(self, "Critical Error", message)
        except Exception as e:
            logger.error(f"[TradingGUI._on_error_signal] Failed to handle error: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_status_updated(self, message: str):
        """Handle status updates"""
        try:
            if self._closing:
                return
            logger.info(f"[TradingGUI._on_status_updated] Status update: {message}")
            self.setWindowTitle(f"Algo Trading Dashboard - {message}")
        except Exception as e:
            logger.error(f"[TradingGUI._on_status_updated] Failed: {e}", exc_info=True)

    @pyqtSlot(bool, str)
    def _on_app_state_changed(self, running: bool, mode: str):
        """Handle app state changes"""
        try:
            if self._closing:
                return
            self._update_button_states()
            self._update_mode_display()
            if self._system_tray_icon:
                if running:
                    self._system_tray_icon.setToolTip(f"Trading App - Running ({mode} mode)")
                else:
                    self._system_tray_icon.setToolTip(f"Trading App - Stopped ({mode} mode)")
        except Exception as e:
            logger.error(f"[TradingGUI._on_app_state_changed] Failed: {e}", exc_info=True)

    @pyqtSlot(float, bool)
    def _on_trade_closed(self, pnl: float, is_winner: bool):
        """Handle trade closed signal from OrderExecutor"""
        try:
            if self._closing:
                return
            if self.daily_pnl_widget:
                self.daily_pnl_widget.on_trade_closed(pnl, is_winner)
            logger.info(f"[TradingGUI._on_trade_closed] Trade closed - P&L: ₹{pnl:.2f}, Winner: {is_winner}")
        except Exception as e:
            logger.error(f"[TradingGUI._on_trade_closed] Failed: {e}", exc_info=True)

    @pyqtSlot(float)
    def _on_unrealized_pnl_updated(self, pnl: float):
        """Handle unrealized P&L updates"""
        try:
            if self._closing:
                return
            if self.daily_pnl_widget:
                self.daily_pnl_widget.on_unrealized_update(pnl)
        except Exception as e:
            logger.error(f"[TradingGUI._on_unrealized_pnl_updated] Failed: {e}", exc_info=True)

    def _setup_log_handler(self):
        """Setup Qt log handler with buffering"""
        try:
            if self._closing:
                return
            self._log_handler = QtLogHandler()
            self._log_handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s")
            )
            self._log_handler.signaller.log_message.connect(self._on_log_message)

            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)

            for h in list(root_logger.handlers):
                if isinstance(h, QtLogHandler):
                    root_logger.removeHandler(h)

            root_logger.addHandler(self._log_handler)
            logging.info("[TradingGUI._setup_log_handler] Logging system initialized")
            self._setup_file_logging()
        except Exception as e:
            logger.error(f"[TradingGUI._setup_log_handler] Failed: {e}", exc_info=True)

    def _setup_file_logging(self):
        """Setup file logging as backup"""
        try:
            if self._closing:
                return
            os.makedirs('logs', exist_ok=True)
            log_file = f"logs/trading_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
            ))
            logging.getLogger().addHandler(file_handler)
            logger.info(f"[TradingGUI._setup_file_logging] File logging setup: {log_file}")
        except Exception as e:
            logger.error(f"[TradingGUI._setup_file_logging] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_log_message(self, message: str):
        """Handle log messages - buffer them and send to popup if open"""
        try:
            if self._closing:
                return
            self._log_buffer.append(message)
            if len(self._log_buffer) > self._max_buffer_size:
                self._log_buffer = self._log_buffer[-self._max_buffer_size:]
            if self.log_popup is not None and self.log_popup.isVisible():
                self.log_popup.append_log(message)
        except Exception as e:
            logger.error(f"[TradingGUI._on_log_message] Failed: {e}", exc_info=True)

    def _setup_system_tray(self):
        """Setup system tray icon"""
        try:
            if self._closing:
                return
            from PyQt5.QtWidgets import QSystemTrayIcon, QMenu
            from PyQt5.QtGui import QIcon

            if QSystemTrayIcon.isSystemTrayAvailable():
                self._system_tray_icon = QSystemTrayIcon(self)
                self._system_tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))

                tray_menu = QMenu()
                self._update_tray_menu_style()

                show_action = tray_menu.addAction("Show Window")
                show_action.triggered.connect(self.show_normal)
                show_action.setToolTip("Show the main application window")

                tray_menu.addSeparator()

                start_action = tray_menu.addAction("Start Trading")
                start_action.triggered.connect(self._start_app)
                start_action.setToolTip("Start the trading engine")

                stop_action = tray_menu.addAction("Stop Trading")
                stop_action.triggered.connect(self._stop_app)
                stop_action.setToolTip("Stop the trading engine")

                tray_menu.addSeparator()

                quit_action = tray_menu.addAction("Quit")
                quit_action.triggered.connect(self.close)
                quit_action.setToolTip("Exit the application")

                self._system_tray_icon.setContextMenu(tray_menu)

                theme_manager.theme_changed.connect(self._update_tray_menu_style)
                theme_manager.density_changed.connect(self._update_tray_menu_style)

                self._system_tray_icon.show()
                logger.info("[TradingGUI._setup_system_tray] System tray icon created")
        except Exception as e:
            logger.error(f"[TradingGUI._setup_system_tray] Failed: {e}", exc_info=True)

    def _update_tray_menu_style(self):
        """Update system tray menu styling when theme changes"""
        try:
            if self._system_tray_icon and self._system_tray_icon.contextMenu():
                c = self._c
                sp = self._sp
                ty = self._ty
                tray_menu = self._system_tray_icon.contextMenu()
                tray_menu.setStyleSheet(f"""
                    QMenu {{
                        background-color: {c.BG_PANEL};
                        color: {c.TEXT_MAIN};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                        padding: {sp.PAD_XS}px 0px;
                    }}
                    QMenu::item {{
                        padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                        background-color: transparent;
                        color: {c.TEXT_MAIN};
                        font-size: {ty.SIZE_SM}pt;
                    }}
                    QMenu::item:selected {{
                        background-color: {c.BG_HOVER};
                        color: {c.TEXT_MAIN};
                    }}
                    QMenu::item:disabled {{
                        color: {c.TEXT_DISABLED};
                        background-color: transparent;
                    }}
                    QMenu::separator {{
                        height: {sp.SEPARATOR}px;
                        background-color: {c.BORDER};
                        margin: {sp.PAD_XS}px {sp.PAD_SM}px;
                    }}
                """)
        except Exception as e:
            logger.error(f"[TradingGUI._update_tray_menu_style] Failed: {e}", exc_info=True)

    def show_normal(self):
        """Show window normally (from system tray)"""
        try:
            if self._closing:
                return
            self.show()
            self.activateWindow()
            self.raise_()
        except Exception as e:
            logger.error(f"[TradingGUI.show_normal] Failed: {e}", exc_info=True)

    def _build_layout(self):
        """Build main window layout"""
        try:
            if self._closing:
                return

            sp = self._sp

            central = QWidget()
            self.setCentralWidget(central)
            root_layout = QVBoxLayout(central)
            root_layout.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)
            root_layout.setSpacing(sp.GAP_SM)
            self._main_layout = root_layout

            self._splitter = QSplitter(Qt.Horizontal)
            self._splitter.setHandleWidth(sp.SPLITTER)

            left_container = QWidget()
            left_layout = QVBoxLayout(left_container)
            left_layout.setContentsMargins(0, 0, 0, 0)
            left_layout.setSpacing(sp.GAP_SM)

            self.chart_widget = MultiChartWidget()
            self.chart_widget.setMinimumWidth(800)
            self.chart_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            left_layout.addWidget(self.chart_widget, 1)

            button_panel = self._build_button_panel()
            left_layout.addWidget(button_panel)

            self._splitter.addWidget(left_container)

            self.status_panel = StatusPanel()
            self.status_panel.setMinimumWidth(260)
            self.status_panel.setMaximumWidth(420)
            self._splitter.addWidget(self.status_panel)

            self._splitter.setStretchFactor(0, 3)
            self._splitter.setStretchFactor(1, 1)
            self._splitter.setSizes([1060, 340])
            root_layout.addWidget(self._splitter, 1)

            self.daily_pnl_widget = DailyPnLWidget(self.config, daily_setting=self.daily_setting)
            self.daily_pnl_widget.setMinimumHeight(84)
            self.daily_pnl_widget.setMaximumHeight(130)
            self.daily_pnl_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            root_layout.addWidget(self.daily_pnl_widget)

            self.app_status_bar = AppStatusBar()
            self.app_status_bar.setMinimumHeight(sp.STATUS_BAR_H - 8)
            self.app_status_bar.setMaximumHeight(sp.STATUS_BAR_H + 8)
            root_layout.addWidget(self.app_status_bar)

        except Exception as e:
            logger.error(f"[TradingGUI._build_layout] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to build layout: {e}")

    def _build_button_panel(self) -> QWidget:
        """Build horizontal button panel below chart"""
        panel = QWidget()
        try:
            if self._closing:
                return panel

            c = self._c
            sp = self._sp
            ty = self._ty

            panel.setObjectName("buttonPanel")
            panel.setMinimumHeight(sp.BUTTON_PANEL_H - 8)
            panel.setMaximumHeight(sp.BUTTON_PANEL_H + 8)
            panel.setStyleSheet(f"""
                QWidget#buttonPanel {{
                    background-color: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                }}
            """)

            layout = QHBoxLayout(panel)
            layout.setContentsMargins(sp.PAD_LG, sp.PAD_SM, sp.PAD_LG, sp.PAD_SM)
            layout.setSpacing(sp.GAP_MD)

            mode_frame = QFrame()
            mode_frame.setStyleSheet("QFrame { border: none; background-color: transparent; }")
            mode_layout = QHBoxLayout(mode_frame)
            mode_layout.setContentsMargins(0, 0, 0, 0)

            lbl = QLabel("Mode:")
            lbl.setStyleSheet(f"""
                color: {c.TEXT_DIM}; 
                font-size: {ty.SIZE_SM}pt; 
                font-weight: {ty.WEIGHT_BOLD};
                background-color: transparent;
            """)
            lbl.setToolTip("Current trading mode")
            mode_layout.addWidget(lbl)

            self.mode_label = QLabel(
                f"Mode: {self.trading_mode_setting.mode.value if self.trading_mode_setting else 'Algo'}")
            mode_color = c.RED_BRIGHT if (
                    self.trading_mode_setting and self.trading_mode_setting.is_live()) else c.GREEN_BRIGHT
            self.mode_label.setStyleSheet(f"""
                color: {mode_color}; 
                font-weight: {ty.WEIGHT_BOLD}; 
                padding: {sp.PAD_XS}px;
                background-color: transparent;
            """)
            self.mode_label.setToolTip("Current trading mode - LIVE, PAPER, or BACKTEST")
            mode_layout.addWidget(self.mode_label)

            self.radio_algo = QRadioButton("⚡ Algo")
            self.radio_manual = QRadioButton("🖐 Manual")
            self.radio_algo.setChecked(True)
            self.radio_algo.toggled.connect(self._on_mode_change)

            for rb in [self.radio_algo, self.radio_manual]:
                # Styling handled by global stylesheet QRadioButton selector
                rb.setToolTip("Switch between automated and manual trading")
                mode_layout.addWidget(rb)

            layout.addWidget(mode_frame)

            separator = QFrame()
            separator.setFrameShape(QFrame.VLine)
            separator.setStyleSheet(
                f"QFrame {{ border: none; background-color: {c.BORDER}; width: {sp.SEPARATOR}px; }}")
            layout.addWidget(separator)

            self.btn_strategy = QPushButton("⚡ Strategy")
            self.btn_strategy.setToolTip("Select and configure trading strategies")
            self.btn_strategy.clicked.connect(self._show_strategy_picker)

            self.btn_start = QPushButton("▶  Start")
            self.btn_start.setToolTip("Start the trading engine (Ctrl+R)")

            self.btn_stop = QPushButton("■  Stop")
            self.btn_stop.setToolTip("Stop the trading engine")

            self.btn_connection = QPushButton("🔌 Disconnected")
            self.btn_connection.clicked.connect(self._show_connection_monitor)
            self.btn_connection.setToolTip("View connection status and details")

            # Use setObjectName for semantic coloring — theme switches automatically
            # via global app stylesheet, no need to call setStyleSheet on each
            self.btn_strategy.setObjectName("strategyBtn")
            self.btn_start.setObjectName("startBtn")
            self.btn_stop.setObjectName("stopBtn")
            self.btn_connection.setObjectName("connectionBtn")

            layout.addWidget(self.btn_strategy)
            layout.addWidget(self.btn_start)
            layout.addWidget(self.btn_stop)
            layout.addWidget(self.btn_connection)

            self.manual_buttons_container = QWidget()
            manual_layout = QHBoxLayout(self.manual_buttons_container)
            manual_layout.setContentsMargins(0, 0, 0, 0)
            manual_layout.setSpacing(sp.GAP_MD)

            self.btn_call = QPushButton("📈  Buy Call")
            self.btn_put = QPushButton("📉  Buy Put")
            self.btn_exit = QPushButton("🚪  Exit")

            # Use object names for theme-aware styling (no inline setStyleSheet needed)
            self.btn_call.setObjectName("callBtn")
            self.btn_put.setObjectName("putBtn")
            self.btn_exit.setObjectName("exitBtn")

            self.btn_call.setToolTip("Buy a CALL option (manual mode only)")
            self.btn_put.setToolTip("Buy a PUT option (manual mode only)")
            self.btn_exit.setToolTip("Exit current position (manual mode only)")

            self.btn_stop.setDisabled(True)
            self.btn_call.setDisabled(True)
            self.btn_put.setDisabled(True)
            self.btn_exit.setDisabled(True)

            self.btn_start.clicked.connect(self._start_app)
            self.btn_stop.clicked.connect(self._stop_app)
            self.btn_call.clicked.connect(lambda: self._manual_buy(BaseEnums.CALL))
            self.btn_put.clicked.connect(lambda: self._manual_buy(BaseEnums.PUT))
            self.btn_exit.clicked.connect(self._manual_exit)

            manual_layout.addWidget(self.btn_call)
            manual_layout.addWidget(self.btn_put)
            manual_layout.addWidget(self.btn_exit)

            self.manual_buttons_container.setVisible(False)

            layout.addStretch()
            layout.addWidget(self.manual_buttons_container)

            self.btn_panel = panel
            self._update_connection_button()

        except Exception as e:
            logger.error(f"[TradingGUI._build_button_panel] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to build button panel: {e}")

        return panel

    def _setup_timers(self):
        """Setup all timers"""
        try:
            if self._closing:
                return

            self.timer_fast = QTimer(self)
            self.timer_fast.timeout.connect(self._tick_fast)
            self.timer_fast.start(1000)

            self.timer_chart = QTimer(self)
            self.timer_chart.timeout.connect(self._tick_chart)
            self.timer_chart.start(5000)

            self.timer_app_status = QTimer(self)
            self.timer_app_status.timeout.connect(self._update_app_status)
            self.timer_app_status.start(500)

            self.timer_connection_check = QTimer(self)
            self.timer_connection_check.timeout.connect(self._check_connection)
            self.timer_connection_check.start(10000)

            self.timer_market_status = QTimer(self)
            self.timer_market_status.timeout.connect(self._update_market_status)
            self.timer_market_status.start(2000)

            QTimer.singleShot(100, self._update_market_status)

        except Exception as e:
            logger.error(f"[TradingGUI._setup_timers] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _tick_fast(self):
        """Fast timer tick - update UI"""
        try:
            if self._closing:
                return

            if self.status_panel is not None:
                self.status_panel.refresh(self.config)

            if self.trading_app is None:
                return

            if self.stats_popup is not None and self.stats_popup.isVisible():
                self.stats_popup.refresh()

            if self.signal_debug_popup is not None and self.signal_debug_popup.isVisible():
                self.signal_debug_popup.refresh()

            if self.connection_monitor_popup is not None and self.connection_monitor_popup.isVisible():
                self.connection_monitor_popup.refresh()

            self._update_button_states()

            self._update_count += 1
            now = datetime.now()
            if self._last_update_time and (now - self._last_update_time).seconds >= 60:
                logger.debug(f"[TradingGUI._tick_fast] UI Update rate: {self._update_count / 60:.1f} Hz")
                self._update_count = 0
                self._last_update_time = now

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[TradingGUI._tick_fast] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _tick_chart(self):
        """Chart timer tick"""
        try:
            if self._closing:
                return
            if self.trading_app is None:
                return

            self._update_chart_if_needed()
            self._update_trade_history()

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[TradingGUI._tick_chart] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _update_app_status(self):
        """Update application status"""
        try:
            if self._closing:
                return
            if self.trading_app is None:
                return

            thread_is_running = self.trading_thread is not None and self.trading_thread.isRunning()
            actual_running = self.app_running and thread_is_running

            if self.app_running and not thread_is_running:
                logger.warning(
                    "[TradingGUI._update_app_status] App state inconsistency: app_running=True but thread not running")
                self.app_running = False
                self.app_status_bar.update_status(
                    {'status': 'Stopped (unexpected)'},
                    self.trading_mode,
                    False
                )
                return

            position_snapshot = state_manager.get_position_snapshot()

            status_info = {
                'fetching_history': False,
                'processing': False,
                'order_pending': position_snapshot.get('order_pending', False),
                'has_position': position_snapshot.get('current_position') is not None,
                'trade_confirmed': position_snapshot.get('current_trade_confirmed', False),
                'last_exit_reason': position_snapshot.get('reason_to_exit'),
                'connection_status': self._connection_status,
                'market_status': self._market_status
            }

            if status_info['has_position']:
                status_info['position_type'] = position_snapshot.get('current_position')

            current_pnl = position_snapshot.get('current_pnl')
            if current_pnl is not None:
                status_info['current_pnl'] = current_pnl
                self.unrealized_pnl_updated.emit(float(current_pnl))
            else:
                self.unrealized_pnl_updated.emit(0.0)

            if safe_hasattr(self.trading_app, '_history_fetch_in_progress'):
                status_info['fetching_history'] = self.trading_app._history_fetch_in_progress.is_set()

            if safe_hasattr(self.trading_app, '_tick_queue'):
                status_info['processing'] = not self.trading_app._tick_queue.empty()

            self.app_status_bar.update_status(status_info, self.trading_mode, actual_running)

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[TradingGUI._update_app_status] Failed: {e}", exc_info=True)

    def _update_market_status(self):
        """Update market status and button states accordingly"""
        try:
            if self._closing:
                return
            if self.trading_app and safe_hasattr(self.trading_app, '_check_market_status'):
                is_open = self.trading_app._check_market_status()
                self._market_status = "OPEN" if is_open else "CLOSED"
            else:
                from Utils.Utils import Utils
                is_open = Utils.is_market_open()
                self._market_status = "OPEN" if is_open else "CLOSED"

            if self.app_status_bar:
                self.app_status_bar.update_market_status(self._market_status)
            self._update_button_states()
        except Exception as e:
            logger.error(f"[TradingGUI._update_market_status] Failed: {e}", exc_info=True)
            self._market_status = "UNKNOWN"

    def _check_connection(self):
        """Check connection status"""
        try:
            if self._closing:
                return
            if self.trading_app and safe_hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                if safe_hasattr(self.trading_app.ws, 'is_connected'):
                    is_connected = self.trading_app.ws.is_connected()
                    self._connection_status = "Connected" if is_connected else "Disconnected"
                else:
                    self._connection_status = "Unknown"
            else:
                self._connection_status = "Disconnected"
            self._update_connection_button()
        except Exception as e:
            logger.error(f"[TradingGUI._check_connection] Failed: {e}", exc_info=True)

    # =========================================================================
    # CHART UPDATE — BUG-1/2/3/4/5 FIXES
    # =========================================================================

    def _update_chart_if_needed(self):
        """Check if chart needs update by comparing CandleStore fingerprint."""
        try:
            if self._closing:
                return
            if self._chart_update_pending:
                return

            symbol = self.daily_setting.derivative if self.daily_setting else None
            if not symbol:
                return

            tf_minutes = (self.chart_widget.get_current_timeframe()
                          if safe_hasattr(self.chart_widget, 'get_current_timeframe') else 1)

            from data.candle_store_manager import candle_store_manager
            last_bar_time = candle_store_manager.last_bar_time(symbol)

            if last_bar_time is None:
                # No data yet — kick off a background fetch
                logger.debug(
                    f"[TradingGUI._update_chart_if_needed] No data in CandleStore for {symbol}, scheduling fetch")
                self._chart_update_pending = True
                self._do_chart_update()          # non-blocking now
                return

            bar_count = candle_store_manager.bar_count(symbol)
            current_fp = f"{last_bar_time.timestamp()}:{bar_count}:{tf_minutes}"

            if current_fp != self._last_chart_fp:
                logger.debug(
                    f"[TradingGUI._update_chart_if_needed] Fingerprint changed, scheduling update")
                self._last_chart_fp = current_fp
                self._chart_update_pending = True
                self._do_chart_update()          # non-blocking

        except Exception as e:
            logger.error(f"[TradingGUI._update_chart_if_needed] Failed: {e}", exc_info=True)
            if not self._chart_update_pending:
                self._chart_update_pending = True
                self._do_chart_update()

    def _do_chart_update(self):
        """
        BUG-1 FIX: Dispatch chart data fetch to a background daemon thread.

        This method is now non-blocking.  The actual broker/store call happens
        inside _fetch_chart_data_bg (background thread), which emits
        _chart_data_ready when finished so the chart is updated on the main thread.

        BUG-4 FIX: _chart_update_pending is reset inside _fetch_chart_data_bg's
        finally block, not here — so the flag stays True until the fetch is done.
        """
        if self._closing:
            self._chart_update_pending = False
            return

        if not self.chart_widget:
            self._chart_update_pending = False
            return

        symbol = self.daily_setting.derivative if self.daily_setting else None
        if not symbol:
            logger.warning("[TradingGUI._do_chart_update] No symbol set for chart")
            self._chart_update_pending = False
            return

        broker_type = None
        if safe_hasattr(self, 'brokerage_setting') and self.brokerage_setting:
            broker_type = safe_getattr(self.brokerage_setting, 'broker_type', None)

        tf_minutes = (self.chart_widget.get_current_timeframe()
                      if safe_hasattr(self.chart_widget, 'get_current_timeframe') else 1)

        threading.Thread(
            target=self._fetch_chart_data_bg,
            args=(symbol, tf_minutes, broker_type),
            daemon=True,
            name="ChartFetchThread"
        ).start()

    def _fetch_chart_data_bg(self, symbol: str, tf_minutes: int, broker_type):
        """
        Background thread: fetch candle data and emit _chart_data_ready when done.

        BUG-3 FIX: candle_store_manager.fetch_all() was missing its `return results`
        statement so it always returned None.  We guard for that here; the real fix
        belongs in candle_store_manager.py (add `return results` at the end of
        fetch_all).

        BUG-4 FIX: always clears _chart_update_pending in the finally block.
        """
        try:
            if self._closing:
                return

            from data.candle_store_manager import candle_store_manager

            # Guard: don't attempt a broker fetch before TradingApp.initialize()
            # has run on the worker thread.  Before that point, candle_store_manager
            # holds broker=None, so every store.fetch() would log an ERROR on every
            # chart timer tick (every 5 s) — producing the log spam seen in the
            # "No broker configured" issue.
            #
            # We check the manager's own _broker rather than self.trading_app.broker
            # because the manager is the authoritative gate for fetch permission.
            # _on_trading_app_initialized() injects the live broker into the manager
            # after TradingThread emits its initialized signal.
            if candle_store_manager.is_empty(symbol):
                broker_ready = (
                    safe_hasattr(candle_store_manager, '_broker') and
                    candle_store_manager._broker is not None
                )
                if not broker_ready:
                    logger.debug(
                        f"[ChartFetch] Broker not ready yet for {symbol}, skipping fetch"
                    )
                    return

                logger.info(f"[ChartFetch] CandleStore empty for {symbol}, fetching...")
                result = candle_store_manager.fetch_all(
                    days=2, symbols=[symbol], broker_type=broker_type
                )
                # BUG-3 guard: fetch_all had a missing `return results` so it could
                # return None.  Treat None as "fetch failed" rather than crashing.
                if result is None or not result.get(symbol, False):
                    logger.warning(f"[ChartFetch] Failed to fetch data for {symbol}")
                    return

            df = candle_store_manager.resample(symbol, tf_minutes)
            if df is None or df.empty:
                logger.debug(f"[ChartFetch] No data available for {symbol} at {tf_minutes}m")
                return

            time_col = df["time"] if "time" in df.columns else pd.Series()

            # BUG-10 FIX: chart_widget._to_epoch() cannot parse bare "HH:MM" strings —
            # it tries float("09:15") which raises ValueError, returns None for every bar,
            # then _filter_today_data finds zero valid timestamps and falls back to the
            # last-50-bars emergency path → chart shows only ~2:45–3:30.
            #
            # Fix: always pass Unix epoch integers (seconds since 1970 UTC).
            # _to_epoch handles int/float via the fast path `return float(ts)`.
            # The HH:MM display strings are kept separately under "time_labels" so
            # the chart can still use them for x-axis tick text.
            if hasattr(time_col, 'dt'):
                # IST-aware → .timestamp() gives correct UTC epoch
                timestamps = [int(t.timestamp()) for t in time_col]
            else:
                timestamps = []

            # Human-readable labels for x-axis display (not used by _to_epoch)
            if tf_minutes >= 60:
                time_labels = [t.strftime("%Y-%m-%d %H:%M") for t in time_col]
            else:
                time_labels = [t.strftime("%H:%M") for t in time_col]

            chart_data = {
                "open":        df["open"].tolist(),
                "high":        df["high"].tolist(),
                "low":         df["low"].tolist(),
                "close":       df["close"].tolist(),
                "volume":      df["volume"].tolist() if "volume" in df.columns else [],
                "timestamps":  timestamps,    # epoch ints — _to_epoch parses these correctly
                "time_labels": time_labels,   # HH:MM strings for display only
                "datetime":    time_col.tolist(),
            }

            # Marshal back to the main/GUI thread via signal — safe cross-thread call
            self._chart_data_ready.emit(chart_data)
            logger.debug(f"[ChartFetch] Emitted {len(df)} bars for {symbol} at {tf_minutes}m")

        except Exception as e:
            logger.error(f"[ChartFetch] Background fetch failed: {e}", exc_info=True)
        finally:
            # BUG-4 FIX: always release the pending flag
            self._chart_update_pending = False

    @pyqtSlot(dict)
    def _on_chart_data_ready(self, chart_data: dict):
        """
        Main thread slot: receives prepared chart data from the background thread
        and passes it to the chart widget.  Safe to call Qt widgets here.
        """
        try:
            if self._closing or not self.chart_widget:
                return
            self.chart_widget.update_charts(spot_data=chart_data)
        except Exception as e:
            logger.error(f"[TradingGUI._on_chart_data_ready] Failed: {e}", exc_info=True)

    def _force_chart_refresh(self):
        """
        Force a full chart refresh.

        BUG-2 FIX: previously called _do_chart_update() directly (blocking).
        Now resets state and dispatches the non-blocking version.
        """
        try:
            if self._closing:
                return
            logger.info("[TradingGUI._force_chart_refresh] Forcing chart refresh")
            self._chart_update_pending = False
            self._last_chart_fp = ""
            if safe_hasattr(self.chart_widget, 'clear_cache'):
                self.chart_widget.clear_cache()
            # _do_chart_update is now non-blocking
            self._do_chart_update()
        except Exception as e:
            logger.error(f"[TradingGUI._force_chart_refresh] Failed: {e}", exc_info=True)

    def _on_timeframe_changed(self, minutes: int):
        """Handle timeframe change from chart widget — BUG-5 fixed transitively."""
        try:
            if self._closing:
                return
            logger.info(f"[TradingGUI._on_timeframe_changed] Timeframe changed to {minutes}m")
            self._last_chart_fp = ""
            self._force_chart_refresh()
        except Exception as e:
            logger.error(f"[TradingGUI._on_timeframe_changed] Failed: {e}", exc_info=True)

    # =========================================================================
    # Button state management
    # =========================================================================

    def _update_button_states(self):
        """Enable/disable buttons based on app state and market status"""
        try:
            if self._closing:
                return

            position_snapshot = state_manager.get_position_snapshot()
            has_pos = position_snapshot.get('current_position') is not None
            manual = self.trading_mode == "manual"

            # BUG-7 FIX: compare enum value, not display name
            is_backtest = False
            if self.trading_mode_setting:
                mode_val = safe_getattr(self.trading_mode_setting, 'mode', None)
                if mode_val is not None:
                    from gui.trading_mode.TradingModeSetting import TradingMode as _TM
                    is_backtest = (mode_val == _TM.BACKTEST)

            market_open = self._market_status == "OPEN"

            if self.btn_start:
                self.btn_start.setDisabled(self.app_running)
            if self.btn_stop:
                self.btn_stop.setDisabled(not self.app_running)

            if safe_hasattr(self, 'manual_buttons_container') and self.manual_buttons_container:
                self.manual_buttons_container.setVisible(manual and not is_backtest)

            if is_backtest:
                if self.btn_start:
                    self.btn_start.setDisabled(self.app_running)
                    if not self.app_running:
                        self.btn_start.setText("▶  Start Backtest")
                return

            if self.app_running:
                if manual:
                    if self.btn_call:
                        self.btn_call.setDisabled(has_pos)
                    if self.btn_put:
                        self.btn_put.setDisabled(has_pos)
                    if self.btn_exit:
                        self.btn_exit.setDisabled(not has_pos)

                    if not market_open:
                        for btn, tip in [
                            (self.btn_call, "Market is closed - manual trading unavailable"),
                            (self.btn_put, "Market is closed - manual trading unavailable"),
                            (self.btn_exit, "Market is closed - manual trading unavailable"),
                        ]:
                            if btn:
                                btn.setDisabled(True)
                                btn.setToolTip(tip)
            else:
                if self.btn_start:
                    if not market_open:
                        self.btn_start.setText("▶  Start (Market Closed)")
                        self.btn_start.setToolTip("Market is closed - trading will start when market opens")
                    else:
                        self.btn_start.setText("▶  Start")
                        self.btn_start.setToolTip("Start trading engine (Ctrl+R)")

        except AttributeError as e:
            logger.warning(f"[TradingGUI._update_button_states] Attribute error (normal during init): {e}")
        except Exception as e:
            logger.error(f"[TradingGUI._update_button_states] Failed: {e}", exc_info=True)

    def _init_trading_app(self):
        """
        Create TradingApp (lightweight __init__, no network I/O) then immediately
        spawn a daemon thread that calls create_broker_only() so historical chart
        data is available before the user clicks Start.
        """
        try:
            if self._closing:
                return

            logger.info("[TradingGUI._init_trading_app] Initializing TradingApp with settings:")
            logger.info(
                f"  Brokerage: client_id={self.brokerage_setting.client_id[:5] if self.brokerage_setting.client_id else 'None'}...")
            logger.info(f"  Daily: derivative={self.daily_setting.derivative}, lot_size={self.daily_setting.lot_size}")
            logger.info(
                f"  P&L: tp={self.profit_loss_setting.tp_percentage}%, sl={self.profit_loss_setting.stoploss_percentage}%")
            _mode_raw = self.trading_mode_setting.mode
            logger.info(f"  Mode: {_mode_raw.value if hasattr(_mode_raw, 'value') else _mode_raw}")

            # Fast __init__ — stores settings only, no network I/O.
            self.trading_app = TradingApp(
                config=self.config,
                broker_setting=self.brokerage_setting,
                trading_mode_var=self.trading_mode_setting,
            )

            # Chart starts with engine=None (detector created in initialize()).
            try:
                self.chart_widget.set_config(self.config, None)
            except Exception as e:
                logger.warning(f"[TradingGUI._init_trading_app] Could not set chart config: {e}")

            self.app_status_bar.update_status({
                'initialized': True,
                'status': 'Connecting to broker…'
            }, self.trading_mode, False)

            logger.info("[TradingGUI._init_trading_app] TradingApp shell created — starting background broker init")

            # Spawn background thread: create broker + load chart data without
            # blocking the GUI thread.  Result arrives via _broker_ready signal.
            threading.Thread(
                target=self._init_broker_bg,
                daemon=True,
                name="BrokerInitThread",
            ).start()

        except Exception as e:
            logger.critical(f"[TradingGUI._init_trading_app] Failed to create TradingApp: {e}", exc_info=True)
            error_str = str(e)
            if "Token expired" in error_str or ("token" in error_str.lower() and "expir" in error_str.lower()):
                logger.warning(
                    "[TradingGUI._init_trading_app] Token expiry detected during init, prompting re-authentication")
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
            if self._closing:
                return

            if self.trading_app is None:
                logger.error("[TradingGUI._start_app] Start failed: Trading app not initialized")
                QMessageBox.critical(self, "Error", "Trading app not initialised.")
                return

            is_backtest = False
            if self.trading_mode_setting:
                mode_val = safe_getattr(self.trading_mode_setting, 'mode', None)
                if mode_val is not None:
                    from gui.trading_mode.TradingModeSetting import TradingMode as _TM
                    is_backtest = (mode_val == _TM.BACKTEST)

            if self._is_live_mode() and not license_manager.is_live_trading_allowed():
                self._show_live_upgrade_dialog()
                return

            if not is_backtest and self._market_status != "OPEN":
                reply = QMessageBox.question(
                    self, "Market Closed",
                    "The market is currently closed.\n\n"
                    "The trading engine can still start but will wait for market open.\n"
                    "Do you want to continue?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return

            if self._check_token_expired():
                reply = QMessageBox.question(
                    self, "Token Expired",
                    "Your token appears to be expired. Would you like to login now?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._open_login_for_token_expiry("Token expired")
                    return

            self.trading_thread = TradingThread(self.trading_app)
            self.trading_thread.error_occurred.connect(self._on_engine_error)
            self.trading_thread.token_expired.connect(self._on_token_expired)
            # BUG-6 FIX: finished signal alone updates state — _threaded_stop no
            # longer posts a duplicate QTimer.singleShot(0, _on_engine_finished).
            self.trading_thread.finished.connect(self._on_engine_finished)
            self.trading_thread.started.connect(self._on_thread_started)
            # Re-inject broker into candle_store_manager once initialize() finishes
            # on the worker thread, then trigger the first chart load.
            self.trading_thread.initialized.connect(self._on_trading_app_initialized)

            self.trading_thread.position_closed.connect(
                lambda sym, pnl: self.trade_closed.emit(pnl, pnl > 0)
            )

            self.app_running = True
            self.app_status_bar.update_status(
                {'status': 'Starting...'},
                self.trading_mode,
                True
            )
            self._update_button_states()

            if is_backtest:
                self.status_updated.emit("Starting backtest...")
            else:
                self.status_updated.emit("Starting trading engine...")

            self.trading_thread.start()
            logger.info(
                f"[TradingGUI._start_app] Trading engine thread started (mode: {'BACKTEST' if is_backtest else 'LIVE/PAPER'})")

        except Exception as e:
            logger.error(f"[TradingGUI._start_app] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to start trading engine: {e}")
            self.app_running = False
            self.app_status_bar.update_status(
                {'status': f'Start failed: {str(e)[:50]}'},
                self.trading_mode,
                False
            )

    @pyqtSlot()
    def _on_thread_started(self):
        """Handle thread started signal"""
        try:
            if self._closing:
                return
            self.app_running = True
            self.app_status_bar.update_status({'status': 'Running'}, self.trading_mode, True)
            self.status_updated.emit("Trading engine running")
            logger.info("[TradingGUI._on_thread_started] Trading thread started successfully")
            self.app_state_changed.emit(True, self.trading_mode)
        except Exception as e:
            logger.error(f"[TradingGUI._on_thread_started] Failed: {e}", exc_info=True)

    def _on_trading_app_initialized(self):
        """
        Called (on GUI thread) after TradingApp.initialize() completes on the
        worker thread, meaning the broker is now live.

        Re-injects the broker into candle_store_manager so existing CandleStore
        instances (created before the broker existed) can fetch data.  Then
        triggers an immediate chart refresh.

        ROOT CAUSE of log error "[CandleStore.fetch] No broker configured":
            _initialize_infrastructure() calls candle_store_manager.initialize(None)
            because no broker exists yet at GUI startup.  The chart fetch timer
            fires before TradingApp.initialize() finishes, so all store.fetch()
            calls find broker=None.  This slot is the bridge: once the broker is
            ready we push it into the manager and kick the chart.
        """
        try:
            if self._closing:
                return

            # Pull the live broker from trading_app (set by initialize())
            broker = None
            if self.trading_app and safe_hasattr(self.trading_app, 'broker'):
                broker = self.trading_app.broker

            if broker is None:
                logger.warning("[TradingGUI._on_trading_app_initialized] Broker still None after initialize()")
                return

            # Re-inject into manager — this also updates broker on existing stores
            from data.candle_store_manager import candle_store_manager
            candle_store_manager.initialize(broker)
            logger.info("[TradingGUI._on_trading_app_initialized] candle_store_manager re-initialized with live broker")

            # Update chart widget with the real signal engine now that initialize() ran.
            # At __init__ time this was None; now detector and signal_engine are live.
            try:
                detector = getattr(self.trading_app, 'detector', None)
                engine   = getattr(detector, 'signal_engine', None) if detector else None
                self.chart_widget.set_config(self.config, engine)
                logger.info("[TradingGUI._on_trading_app_initialized] Chart widget config updated with live engine")
            except Exception as e:
                logger.warning(f"[TradingGUI._on_trading_app_initialized] Could not update chart config: {e}")

            # Trigger immediate chart refresh now that the broker is available
            self._do_chart_update()
            logger.info("[TradingGUI._on_trading_app_initialized] Initial chart refresh triggered")

        except Exception as e:
            logger.error(f"[TradingGUI._on_trading_app_initialized] Failed: {e}", exc_info=True)

    # ── Background broker initialisation ────────────────────────────────────

    def _init_broker_bg(self):
        """
        Runs on a daemon thread (BrokerInitThread).

        Calls trading_app.create_broker_only():
          - validates / restores the stored token
          - creates the broker session (lightweight, no WS / executor)
          - calls candle_store_manager.initialize(broker)

        On success  → emits _broker_ready  (handled on GUI thread)
        On TokenExpiredError → emits _broker_failed(msg, True)
        On other error       → emits _broker_failed(msg, False)
        """
        try:
            if self.trading_app is None or self._closing:
                return
            self.trading_app.create_broker_only()
            self._broker_ready.emit()
        except TokenExpiredError as e:
            self._broker_failed.emit(str(e), True)
        except Exception as e:
            logger.error(f"[TradingGUI._init_broker_bg] Broker init failed: {e}", exc_info=True)
            self._broker_failed.emit(str(e), False)

    @pyqtSlot()
    def _on_broker_ready(self):
        """
        GUI-thread slot — broker is live and candle_store_manager is initialized.

        Updates the status bar, re-configures the chart, and triggers the first
        historical data fetch so the chart shows data before Start is clicked.
        """
        try:
            if self._closing:
                return

            logger.info("[TradingGUI._on_broker_ready] Broker ready — triggering initial chart load")

            self.app_status_bar.update_status({
                'initialized': True,
                'status': 'App initialized'
            }, self.trading_mode, False)

            # chart_widget now gets the real engine (still None — detector is created
            # in full initialize(), but the chart can render price data without it)
            try:
                detector = getattr(self.trading_app, 'detector', None)
                engine   = getattr(detector, 'signal_engine', None) if detector else None
                self.chart_widget.set_config(self.config, engine)
            except Exception:
                pass

            # Allow _tick_chart to proceed (broker is now in candle_store_manager)
            # and kick off an immediate fetch without waiting for the 5-s timer.
            self._do_chart_update()

        except Exception as e:
            logger.error(f"[TradingGUI._on_broker_ready] Failed: {e}", exc_info=True)

    @pyqtSlot(str, bool)
    def _on_broker_failed(self, error_msg: str, is_token_expired: bool):
        """
        GUI-thread slot — broker initialisation failed.

        If the token is expired we force the login dialog immediately.
        Otherwise we show a status-bar warning and let the user retry via Settings.
        """
        try:
            if self._closing:
                return

            if is_token_expired:
                logger.warning("[TradingGUI._on_broker_failed] Token expired — forcing login dialog")
                self.app_status_bar.update_status(
                    {'status': '⚠️ Token expired — please login', 'error': True},
                    self.trading_mode, False
                )
                # Force login.  On completion _reload_broker is called which
                # re-creates broker and triggers chart load.
                QTimer.singleShot(200, lambda: self._open_login_for_token_expiry(
                    "Your broker token has expired. Please login to continue."
                ))
            else:
                logger.error(f"[TradingGUI._on_broker_failed] Broker init error: {error_msg}")
                self.app_status_bar.update_status(
                    {'status': f'⚠️ Broker error: {error_msg[:60]}', 'error': True},
                    self.trading_mode, False
                )

        except Exception as e:
            logger.error(f"[TradingGUI._on_broker_failed] Failed: {e}", exc_info=True)

    def _is_live_mode(self) -> bool:
        """Return True when the trading mode setting is set to LIVE"""
        try:
            if self.trading_mode_setting and safe_hasattr(self.trading_mode_setting, 'is_live'):
                return self.trading_mode_setting.is_live()
            if self.trading_mode_setting and safe_hasattr(self.trading_mode_setting, 'mode'):
                from gui.trading_mode.TradingModeSetting import TradingMode
                return self.trading_mode_setting.mode == TradingMode.LIVE
        except Exception as e:
            logger.warning(f"[TradingGUI._is_live_mode] {e}")
        return False

    def _show_live_upgrade_dialog(self):
        """Show the LiveTradingUpgradeDialog for free/trial users"""
        try:
            from license.activation_dialog import LiveTradingUpgradeDialog

            dlg = LiveTradingUpgradeDialog(parent=self)

            def _on_activated(result):
                logger.info(f"[TradingGUI._show_live_upgrade_dialog] Upgraded to {result.plan} — starting live engine")
                self._update_mode_display()
                QTimer.singleShot(1400, self._start_app)

            def _on_paper():
                try:
                    if self.trading_mode_setting:
                        self.trading_mode_setting.set_mode("PAPER")
                        self._update_mode_display()
                    self._start_app()
                except Exception as e:
                    logger.error(f"[TradingGUI._show_live_upgrade_dialog._on_paper] {e}", exc_info=True)

            dlg.activated.connect(_on_activated)
            dlg.switch_to_paper.connect(_on_paper)
            dlg.exec_()

        except Exception as e:
            logger.error(f"[TradingGUI._show_live_upgrade_dialog] {e}", exc_info=True)

    def _check_token_expired(self, buffer_minutes: int = 1) -> bool:
        """Check if the stored broker token has expired."""
        try:
            from datetime import datetime, timezone
            from db.crud import tokens

            token_data = tokens.get()
            if not token_data:
                return True

            expiry_str = token_data.get('expires_at')
            if not expiry_str:
                access_token = token_data.get('access_token', '')
                return not bool(access_token)

            expiry = None
            formats = [
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S.%f",
            ]

            for fmt in formats:
                try:
                    expiry = datetime.strptime(expiry_str, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue

            if expiry is None:
                try:
                    if expiry_str.endswith('Z'):
                        expiry_str = expiry_str.replace('Z', '+00:00')
                    expiry = datetime.fromisoformat(expiry_str)
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                except (ValueError, AttributeError):
                    pass

            if expiry is None:
                logger.error(f"[TradingGUI._check_token_expired] Could not parse expiry: {expiry_str}")
                return True

            now_utc = datetime.now(timezone.utc)
            time_remaining = (expiry - now_utc).total_seconds()

            if time_remaining <= buffer_minutes * 60:
                logger.info(f"[TradingGUI._check_token_expired] Token expired or expiring soon")
                return True
            return False

        except ImportError as e:
            logger.error(f"[TradingGUI._check_token_expired] Failed to import: {e}")
            return True
        except Exception as e:
            logger.error(f"[TradingGUI._check_token_expired] Unexpected error: {e}", exc_info=True)
            return True

    @pyqtSlot()
    def _stop_app(self):
        """Stop the trading engine"""
        try:
            if self._closing:
                return
            if self.btn_stop:
                self.btn_stop.setDisabled(True)
            self.app_status_bar.update_status({'status': 'Stopping...'}, self.trading_mode, True)
            self.status_updated.emit("Stopping trading engine...")
            threading.Thread(target=self._threaded_stop, daemon=True, name="StopThread").start()
            logger.info("[TradingGUI._stop_app] Trading engine stopping...")
        except Exception as e:
            logger.error(f"[TradingGUI._stop_app] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to stop trading engine: {e}")

    def _threaded_stop(self):
        """
        Background stop work.

        BUG-6 FIX: Removed the duplicate `QTimer.singleShot(0, self._on_engine_finished)`
        call.  The TradingThread.finished signal (connected in _start_app) is the single
        authoritative trigger for _on_engine_finished, so we must not call it a second
        time from here.
        """
        try:
            if self.trading_thread:
                self.trading_thread.stop()
            logger.debug("[TradingGUI._threaded_stop] Stop thread completed — waiting for finished signal")
        except Exception as e:
            logger.error(f"[TradingGUI._threaded_stop] Failed: {e}", exc_info=True)
            QTimer.singleShot(0, lambda: self.error_occurred.emit(f"Stop failed: {e}"))

    @pyqtSlot()
    def _on_engine_finished(self):
        """Slot called when engine finishes"""
        try:
            if self._closing:
                return
            self.app_running = False
            self.app_status_bar.update_status({'status': 'Stopped'}, self.trading_mode, False)
            self._update_button_states()
            self.status_updated.emit("Trading engine stopped")
            logger.info("[TradingGUI._on_engine_finished] Trading engine stopped")
            self.app_state_changed.emit(False, self.trading_mode)
        except Exception as e:
            logger.error(f"[TradingGUI._on_engine_finished] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_token_expired(self, message: str):
        """Handle token expired signal"""
        try:
            if self._closing:
                return
            self.app_running = False
            self.app_status_bar.update_status(
                {'status': '🔐 Token expired — re-login required', 'error': True},
                self.trading_mode, False
            )
            self._update_button_states()
            logger.warning(f"[TradingGUI._on_token_expired] Token expired signal received: {message}")
            self._open_login_for_token_expiry(message)
        except Exception as e:
            logger.error(f"[TradingGUI._on_token_expired] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_engine_error(self, message: str):
        """Handle engine errors"""
        try:
            if self._closing:
                return
            self.app_running = False
            self.app_status_bar.update_status(
                {'status': f'Error: {message[:50]}...', 'error': True},
                self.trading_mode, False
            )
            self._update_button_states()
            QMessageBox.critical(self, "Engine Error", f"Trading engine crashed:\n{message}")
            logger.error(f"[TradingGUI._on_engine_error] Engine error: {message}")
            self.error_occurred.emit(message)
        except Exception as e:
            logger.error(f"[TradingGUI._on_engine_error] Failed to handle error: {e}", exc_info=True)

    def _manual_buy(self, option_type):
        """Manual buy in background thread"""
        try:
            if self._closing:
                return
            if self.trading_mode != "manual":
                QMessageBox.information(self, "Mode", "Switch to Manual mode first.")
                return
            if not self.trading_app:
                return
            if self._market_status != "OPEN":
                QMessageBox.warning(self, "Market Closed", "Cannot place manual orders when market is closed.")
                return
            self.app_status_bar.update_status({'status': f'Placing {option_type} order...'}, self.trading_mode, True)
            threading.Thread(target=self._threaded_manual_buy, args=(option_type,), daemon=True).start()
        except Exception as e:
            logger.error(f"[TradingGUI._manual_buy] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Manual buy failed: {e}")

    def _threaded_manual_buy(self, option_type):
        """Execute manual buy in background"""
        try:
            if self.trading_app and safe_hasattr(self.trading_app, 'executor'):
                self.trading_app.executor.buy_option(option_type=option_type)
                QTimer.singleShot(0, lambda: self.app_status_bar.update_status(
                    {'status': f'{option_type} order placed'}, self.trading_mode, True))
        except Exception as e:
            logger.error(f"[TradingGUI._threaded_manual_buy] Error: {e}", exc_info=True)
            QTimer.singleShot(0, lambda: self.error_occurred.emit(f"Order failed: {e}"))

    def _manual_exit(self):
        """Manual exit in background thread"""
        try:
            if self._closing:
                return
            if self.trading_mode != "manual":
                QMessageBox.information(self, "Mode", "Switch to Manual mode first.")
                return
            if not self.trading_app:
                return
            if self._market_status != "OPEN":
                QMessageBox.warning(self, "Market Closed", "Cannot exit positions when market is closed.")
                return
            self.app_status_bar.update_status({'status': 'Exiting position...'}, self.trading_mode, True)
            threading.Thread(target=self._threaded_manual_exit, daemon=True).start()
        except Exception as e:
            logger.error(f"[TradingGUI._manual_exit] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Manual exit failed: {e}")

    def _threaded_manual_exit(self):
        """Execute manual exit in background"""
        try:
            if self.trading_app and safe_hasattr(self.trading_app, 'executor'):
                self.trading_app.executor.exit_position(reason="Manual Exit")
                QTimer.singleShot(0, lambda: self.app_status_bar.update_status(
                    {'status': 'Position exited'}, self.trading_mode, True))
        except Exception as e:
            logger.error(f"[TradingGUI._threaded_manual_exit] Error: {e}", exc_info=True)
            QTimer.singleShot(0, lambda: self.error_occurred.emit(f"Exit failed: {e}"))

    @pyqtSlot()
    def _on_mode_change(self):
        """Handle mode switch"""
        try:
            if self._closing:
                return
            self.trading_mode = "algo" if self.radio_algo.isChecked() else "manual"
            self.app_status_bar.update_status({}, self.trading_mode, self.app_running)
            self._update_button_states()
            self._update_mode_display()
            logger.info(f"[TradingGUI._on_mode_change] Trading mode changed to: {self.trading_mode}")
            self.app_state_changed.emit(self.app_running, self.trading_mode)
        except Exception as e:
            logger.error(f"[TradingGUI._on_mode_change] Failed: {e}", exc_info=True)

    def _create_menu(self):
        """Build menu bar"""
        try:
            if self._closing:
                return

            menubar = self.menuBar()

            # File menu
            file_menu = menubar.addMenu("File")

            restart_act = QAction("🔄 Restart Application", self)
            restart_act.triggered.connect(self._restart_application)
            file_menu.addAction(restart_act)
            file_menu.addSeparator()

            exit_act = QAction("❌ Exit", self)
            exit_act.triggered.connect(self.close)
            exit_act.setShortcut("Ctrl+Q")
            file_menu.addAction(exit_act)

            # View menu
            view_menu = menubar.addMenu("View")

            for label, slot, tip in [
                ("📝 Show Logs",            self._show_log_popup,          "View application logs"),
                ("📊 Show Trade History",   self._show_history_popup,      "View trade history"),
                ("📈 Show Statistics",      self._show_stats_popup,        "View trading statistics"),
                ("🔬 Dynamic Signal Debug", self._show_signal_debug_popup, "Debug signal generation"),
                ("🌐 Connection Monitor",   self._show_connection_monitor,  "Monitor broker connections"),
                ("💻 System Monitor",       self._show_system_monitor,     "Monitor system performance"),
            ]:
                act = QAction(label, self)
                act.triggered.connect(slot)
                act.setToolTip(tip)
                view_menu.addAction(act)

            view_menu.addSeparator()

            picker_act = QAction("⚡ Strategy Picker", self)
            picker_act.triggered.connect(self._show_strategy_picker)
            view_menu.addAction(picker_act)

            editor_act = QAction("📋 Strategy Editor", self)
            editor_act.triggered.connect(self._open_strategy_editor)
            view_menu.addAction(editor_act)

            view_menu.addSeparator()

            self._theme_action = QAction(
                "🌙  Dark Theme" if theme_manager.is_dark() else "☀️  Light Theme", self
            )
            self._theme_action.setCheckable(True)
            self._theme_action.setChecked(theme_manager.is_dark())
            self._theme_action.setShortcut("Ctrl+T")
            self._theme_action.triggered.connect(self._toggle_theme)
            view_menu.addAction(self._theme_action)

            density_menu = view_menu.addMenu("📏 Display Density")
            self._density_menu = density_menu
            self._compact_menu_actions = []

            for label, value in [("🔹 Compact", "compact"), ("🔸 Normal", "normal"), ("🔹 Relaxed", "relaxed")]:
                act = QAction(label, self)
                act.setCheckable(True)
                act.setChecked(theme_manager.current_density == value)
                act.triggered.connect(lambda checked, v=value: self._set_density(v))
                density_menu.addAction(act)
                self._compact_menu_actions.append((act, value))

            view_menu.addSeparator()
            close_all_act = QAction("❌ Close All Popups", self)
            close_all_act.triggered.connect(self._close_all_popups)
            view_menu.addAction(close_all_act)

            # Settings menu
            settings_menu = menubar.addMenu("Settings")

            for label, slot in [
                ("⚙️ Strategy Settings",       self._show_strategy_picker),
                ("📅 Daily Trade Settings",     self._open_daily),
                ("💰 Profit & Loss Settings",   self._open_pnl),
                ("🏦 Brokerage Settings",       self._open_brokerage),
                ("🔑 Manual Broker Login",      self._open_login),
                ("🎮 Trading Mode Settings",    self._open_trading_mode),
            ]:
                act = QAction(label, self)
                act.triggered.connect(slot)
                settings_menu.addAction(act)

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

            tools_menu.addSeparator()

            backtest_act = QAction("📊 Strategy Backtester", self)
            backtest_act.setShortcut("Ctrl+B")
            backtest_act.triggered.connect(self._open_backtest)
            tools_menu.addAction(backtest_act)

            # Help menu
            help_menu = menubar.addMenu("Help")

            about_act = QAction("ℹ️ About", self)
            about_act.triggered.connect(self._show_about)
            help_menu.addAction(about_act)

            docs_act = QAction("📚 Documentation", self)
            docs_act.triggered.connect(self._show_documentation)
            help_menu.addAction(docs_act)

            help_menu.addSeparator()

            updates_act = QAction("🔄 Check for Updates", self)
            updates_act.triggered.connect(self._check_updates)
            help_menu.addAction(updates_act)

        except Exception as e:
            logger.error(f"[TradingGUI._create_menu] Failed: {e}", exc_info=True)

    def _toggle_theme(self) -> None:
        try:
            if self._closing:
                return
            theme_manager.toggle()
            theme_manager.save_preference()
            is_dark = theme_manager.is_dark()
            if self._theme_action:
                self._theme_action.setText("🌙  Dark Theme" if is_dark else "☀️  Light Theme")
                self._theme_action.setChecked(is_dark)
        except Exception as e:
            logger.error(f"[TradingGUI._toggle_theme] Failed: {e}", exc_info=True)

    def _set_density(self, density: str) -> None:
        try:
            if self._closing:
                return
            theme_manager.set_density(density)
            theme_manager.save_preference()
            for act, value in self._compact_menu_actions:
                if act:
                    act.setChecked(value == density)
        except Exception as e:
            logger.error(f"[TradingGUI._set_density] Failed: {e}", exc_info=True)

    # =========================================================================
    # Popup handlers
    # =========================================================================

    def _show_log_popup(self):
        try:
            if self._closing:
                return
            if self.log_popup is None:
                self.log_popup = LogPopup(self)
            if self._log_buffer:
                for msg in self._log_buffer[-500:]:
                    self.log_popup.append_log(msg)
            self.log_popup.show()
            self.log_popup.raise_()
            self.log_popup.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_log_popup] Failed: {e}", exc_info=True)

    def _show_history_popup(self):
        try:
            if self._closing:
                return
            if not self.history_popup:
                self.history_popup = TradeHistoryPopup(self)
            self.history_popup.load_trades()
            self.history_popup.show()
            self.history_popup.raise_()
            self.history_popup.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_history_popup] Failed: {e}", exc_info=True)

    def _show_stats_popup(self):
        try:
            if self._closing:
                return
            if self.trading_app:
                if not self.stats_popup:
                    self.stats_popup = StatsPopup(self)
                self.stats_popup.show()
                self.stats_popup.raise_()
                self.stats_popup.activateWindow()
            else:
                QMessageBox.information(self, "Not Ready", "Trading app not initialized yet.")
        except Exception as e:
            logger.error(f"[TradingGUI._show_stats_popup] Failed: {e}", exc_info=True)

    def _show_connection_monitor(self):
        try:
            if self._closing:
                return
            if not self.connection_monitor_popup:
                self.connection_monitor_popup = ConnectionMonitorPopup(self.trading_app, self)
            self.connection_monitor_popup.show()
            self.connection_monitor_popup.raise_()
            self.connection_monitor_popup.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_connection_monitor] Failed: {e}", exc_info=True)

    def _show_system_monitor(self):
        try:
            if self._closing:
                return
            if not self.system_monitor_popup:
                self.system_monitor_popup = SystemMonitorPopup(self)
            self.system_monitor_popup.show()
            self.system_monitor_popup.raise_()
            self.system_monitor_popup.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_system_monitor] Failed: {e}", exc_info=True)

    def _show_signal_debug_popup(self):
        try:
            if self._closing:
                return
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
        try:
            if self._closing:
                return
            for popup in [
                self.log_popup, self.history_popup, self.stats_popup,
                self.signal_debug_popup, self.connection_monitor_popup,
                self.system_monitor_popup, self.strategy_picker, self.strategy_editor
            ]:
                if popup is not None:
                    try:
                        popup.close()
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"[TradingGUI._close_all_popups] Failed: {e}", exc_info=True)

    # =========================================================================
    # Settings dialogs
    # =========================================================================

    def _open_trading_mode(self):
        try:
            if self._closing:
                return
            dlg = TradingModeSettingGUI(self, trading_mode_setting=self.trading_mode_setting, app=self.trading_app)
            if dlg.exec_():
                self._update_mode_display()
        except Exception as e:
            logger.error(f"[TradingGUI._open_trading_mode] Failed: {e}", exc_info=True)

    def _update_mode_display(self):
        try:
            if self._closing:
                return
            if not self.trading_mode_setting:
                return
            mode = self.trading_mode_setting.mode.value if self.trading_mode_setting else "Algo"
            c = self._c
            ty = self._ty
            color = c.RED_BRIGHT if (self.trading_mode_setting and self.trading_mode_setting.is_live()) else c.GREEN_BRIGHT
            if safe_hasattr(self, 'mode_label') and self.mode_label is not None:
                self.mode_label.setText(f"{mode}")
                self.mode_label.setStyleSheet(f"""
                    color: {color}; 
                    font-weight: {ty.WEIGHT_BOLD};
                    background-color: transparent;
                """)
        except Exception as e:
            logger.error(f"[TradingGUI._update_mode_display] Failed: {e}", exc_info=True)

    def _open_daily(self):
        try:
            if self._closing:
                return
            dlg = DailyTradeSettingGUI(self, daily_setting=self.daily_setting, app=self.trading_app)
            # Refresh dashboard widgets as soon as settings are saved (before dialog closes)
            dlg.settings_saved.connect(self._on_settings_saved)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_daily] Failed: {e}", exc_info=True)

    def _open_pnl(self):
        try:
            if self._closing:
                return
            dlg = ProfitStoplossSettingGUI(self, profit_stoploss_setting=self.profit_loss_setting, app=self.trading_app)
            # Refresh dashboard widgets as soon as settings are saved (before dialog closes)
            dlg.settings_saved.connect(self._on_settings_saved)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_pnl] Failed: {e}", exc_info=True)

    def _on_settings_saved(self) -> None:
        """
        Called whenever any settings dialog emits settings_saved.

        Refreshes all dashboard widgets that depend on persisted settings so
        values like daily_target and max_daily_loss appear immediately without
        requiring an app restart or manual P&L tick.
        """
        try:
            logger.info("[TradingGUI._on_settings_saved] Settings saved — refreshing dashboard")

            # Reload daily_setting from DB so we have the latest values
            if self.daily_setting is not None:
                try:
                    self.daily_setting.load()
                except Exception as e:
                    logger.warning(f"[_on_settings_saved] Reload daily_setting failed: {e}")

            # Push updated limits to the P&L widget's progress bar
            if self.daily_pnl_widget is not None:
                try:
                    self.daily_pnl_widget.refresh_settings(daily_setting=self.daily_setting)
                except Exception as e:
                    logger.warning(f"[_on_settings_saved] DailyPnLWidget refresh failed: {e}")

        except Exception as e:
            logger.error(f"[TradingGUI._on_settings_saved] Failed: {e}", exc_info=True)

    def _open_brokerage(self):
        try:
            if self._closing:
                return
            dlg = BrokerageSettingDialog(self.brokerage_setting, self)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_brokerage] Failed: {e}", exc_info=True)

    def _open_login_for_token_expiry(self, reason: str = None):
        try:
            if self._closing:
                return
            reason_msg = reason or "Your Broker access token has expired or is invalid."
            dlg = BrokerLoginPopup(self, self.brokerage_setting, reason=reason_msg)
            dlg.login_completed.connect(lambda _: self._reload_broker())
            result = dlg.exec_()
            if result == BrokerLoginPopup.Accepted:
                logger.info("[TradingGUI._open_login_for_token_expiry] Re-authentication completed successfully")
            else:
                logger.warning("[TradingGUI._open_login_for_token_expiry] Re-authentication cancelled")
                self.app_status_bar.update_status(
                    {'status': '⚠️ Token expired — login required to resume', 'error': True},
                    self.trading_mode, False
                )
        except Exception as e:
            logger.error(f"[TradingGUI._open_login_for_token_expiry] Failed: {e}", exc_info=True)

    def _open_login(self):
        try:
            if self._closing:
                return
            dlg = BrokerLoginPopup(self, self.brokerage_setting)
            dlg.exec_()
            self._reload_broker()
        except Exception as e:
            logger.error(f"[TradingGUI._open_login] Failed: {e}", exc_info=True)

    def _reload_broker(self):
        """
        Called after a successful login (token refresh).
        Tears down any running trading state, creates a fresh TradingApp shell,
        then re-runs create_broker_only() on a background thread so the chart
        reloads automatically.
        """
        try:
            if self._closing:
                return

            # ── Teardown ──────────────────────────────────────────────────────
            if self.trading_app is not None:
                try:
                    if self.trading_thread and self.trading_thread.isRunning():
                        self.trading_thread.request_stop()
                        if not self.trading_thread.wait(3000):
                            logger.warning("[_reload_broker] Trading thread did not stop in 3s — terminating")
                            self.trading_thread.terminate()
                        self.trading_thread = None
                    if safe_hasattr(self.trading_app, 'cleanup'):
                        self.trading_app.cleanup()
                    logger.info("[TradingGUI._reload_broker] Old TradingApp stopped and cleaned up")
                except Exception as cleanup_err:
                    logger.error(f"[TradingGUI._reload_broker] Old app cleanup failed: {cleanup_err}", exc_info=True)
                finally:
                    self.trading_app = None
                    self.app_running = False

            # ── Reload brokerage settings (fresh token is now in DB) ──────────
            self.brokerage_setting.load()
            self.brokerage_setting._load_token_info()

            # ── New lightweight TradingApp ─────────────────────────────────────
            self.trading_app = TradingApp(
                config=self.config,
                broker_setting=self.brokerage_setting,
                trading_mode_var=self.trading_mode_setting,
            )

            logger.info("[TradingGUI._reload_broker] New TradingApp created — starting broker init thread")

            self.app_status_bar.update_status(
                {'status': 'Connecting to broker…'}, self.trading_mode, False
            )

            # Re-run background broker init → chart reloads via _on_broker_ready
            threading.Thread(
                target=self._init_broker_bg,
                daemon=True,
                name="BrokerReloadThread",
            ).start()

        except Exception as e:
            logger.error(f"[TradingGUI._reload_broker] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Reload Error", str(e))

    def _open_backtest(self):
        try:
            if self._closing:
                return
            from backtest.backtest_window import BacktestWindow
            if not safe_hasattr(self, "_backtest_window") or self._backtest_window is None:
                self._backtest_window = BacktestWindow(
                    trading_app=self.trading_app, strategy_manager=self.strategy_manager, parent=self)
            self._backtest_window.show()
            self._backtest_window.raise_()
            self._backtest_window.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._open_backtest] {e}", exc_info=True)
            QMessageBox.critical(self, "Backtester Error", str(e))

    def _show_about(self):
        try:
            if self._closing:
                return
            QMessageBox.about(self, "About",
                              "Algo Trading Dashboard\nVersion 2.0 (PyQt5)\n\n"
                              "© 2025 Your Company. All rights reserved.\n\n"
                              "A professional algorithmic trading platform\n"
                              "supporting LIVE, PAPER, and BACKTEST modes.")
        except Exception as e:
            logger.error(f"[TradingGUI._show_about] Failed: {e}", exc_info=True)

    def _show_documentation(self):
        try:
            if self._closing:
                return
            QMessageBox.information(self, "Documentation",
                                    "Documentation would open here.\n\n"
                                    "In a real application, this would open a PDF or web browser.")
        except Exception as e:
            logger.error(f"[TradingGUI._show_documentation] Failed: {e}", exc_info=True)

    def _check_updates(self):
        try:
            if self._closing:
                return
            QMessageBox.information(self, "Check Updates",
                                    "This feature would check for updates.\n\nCurrently running version 2.0")
        except Exception as e:
            logger.error(f"[TradingGUI._check_updates] Failed: {e}", exc_info=True)

    def _restart_application(self):
        try:
            if self._closing:
                return
            reply = QMessageBox.question(self, "Restart",
                                         "Are you sure you want to restart the application?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.close()
                QTimer.singleShot(1000, lambda: os.execl(sys.executable, sys.executable, *sys.argv))
        except Exception as e:
            logger.error(f"[TradingGUI._restart_application] Failed: {e}", exc_info=True)

    def _backup_config(self):
        try:
            if self._closing:
                return
            import json
            backup_dir = "backups"
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"{backup_dir}/config_backup_{timestamp}.json"
            config_data = {
                'brokerage': self.brokerage_setting.to_dict() if safe_hasattr(self.brokerage_setting, 'to_dict') else {},
                'daily':     self.daily_setting.to_dict() if safe_hasattr(self.daily_setting, 'to_dict') else {},
                'pnl':       self.profit_loss_setting.to_dict() if safe_hasattr(self.profit_loss_setting, 'to_dict') else {},
                'mode':      self.trading_mode_setting.to_dict() if safe_hasattr(self.trading_mode_setting, 'to_dict') else {}
            }
            with open(backup_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            QMessageBox.information(self, "Backup Complete", f"Configuration backed up to:\n{backup_file}")
        except Exception as e:
            logger.error(f"[TradingGUI._backup_config] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Backup Failed", str(e))

    def _restore_config(self):
        try:
            if self._closing:
                return
            from PyQt5.QtWidgets import QFileDialog
            import json
            filename, _ = QFileDialog.getOpenFileName(self, "Select Backup File", "backups", "JSON Files (*.json)")
            if filename:
                with open(filename, 'r') as f:
                    config_data = json.load(f)
                if safe_hasattr(self.brokerage_setting, 'from_dict'):
                    self.brokerage_setting.from_dict(config_data.get('brokerage', {}))
                if safe_hasattr(self.daily_setting, 'from_dict'):
                    self.daily_setting.from_dict(config_data.get('daily', {}))
                if safe_hasattr(self.profit_loss_setting, 'from_dict'):
                    self.profit_loss_setting.from_dict(config_data.get('pnl', {}))
                if safe_hasattr(self.trading_mode_setting, 'from_dict'):
                    self.trading_mode_setting.from_dict(config_data.get('mode', {}))
                self._reload_broker()
                QMessageBox.information(self, "Restore Complete", "Configuration restored successfully.")
        except Exception as e:
            logger.error(f"[TradingGUI._restore_config] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Restore Failed", str(e))

    def _clear_cache(self):
        try:
            if self._closing:
                return
            reply = QMessageBox.question(
                self, "Clear Cache",
                "Are you sure you want to clear the cache?\nThis may improve performance but some data will need to be reloaded.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._log_buffer.clear()
                self._last_chart_fp = ""
                self._trade_file_mtime = 0
                self._last_loaded_trade_data = None
                if self.daily_pnl_widget:
                    self.daily_pnl_widget.reset()
                state_manager.reset_for_backtest()
                QMessageBox.information(self, "Cache Cleared", "Cache has been cleared successfully.")
        except Exception as e:
            logger.error(f"[TradingGUI._clear_cache] Failed: {e}", exc_info=True)

    def _update_trade_history(self):
        """Refresh trade history table only if file changed"""
        try:
            if self._closing:
                return
            today_file = f"logs/trades_{to_date_str(datetime.now())}.csv"
            if not os.path.exists(today_file):
                self.history_popup = None
                return
            current_mtime = os.path.getmtime(today_file)
            if current_mtime != self._trade_file_mtime:
                self._trade_file_mtime = current_mtime
                if self.history_popup is not None and self.history_popup.isVisible():
                    self.history_popup.load_trades_for_date()
        except (OSError, IOError) as e:
            logger.error(f"[TradingGUI._update_trade_history] File error: {e}")
        except Exception as e:
            logger.error(f"[TradingGUI._update_trade_history] Failed: {e}", exc_info=True)

    # =========================================================================
    # Strategy management
    # =========================================================================

    def _show_strategy_picker(self):
        try:
            if self._closing:
                return
            if not self.strategy_picker:
                self.strategy_picker = StrategyPickerSidebar(trading_app=self.trading_app, parent=self)
                self.strategy_picker.strategy_activated.connect(self._on_strategy_changed)
                self.strategy_picker.open_editor_requested.connect(self._open_strategy_editor)
            self.strategy_picker.refresh()
            self.strategy_picker.show()
            self.strategy_picker.raise_()
            self.strategy_picker.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._show_strategy_picker] Failed: {e}", exc_info=True)

    def _open_strategy_editor(self):
        try:
            if self._closing:
                return
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

    def _on_strategy_changed(self, slug: str):
        try:
            if self._closing:
                return
            QTimer.singleShot(100, self._apply_active_strategy_deferred)
            logger.info(f"[TradingGUI._on_strategy_changed] Strategy changed to: {slug}")
        except Exception as e:
            logger.error(f"[TradingGUI._on_strategy_changed] Failed: {e}", exc_info=True)

    def _apply_active_strategy_deferred(self):
        try:
            if self._closing:
                return
            if not self.strategy_manager:
                return
            active_slug = self.strategy_manager.get_active_slug()
            if not active_slug:
                return
            indicator_params = self.strategy_manager.get_active_indicator_params()
            for key, value in indicator_params.items():
                if safe_hasattr(self.config, key):
                    safe_setattr(self.config, key, value)
            if self.trading_app and safe_hasattr(self.trading_app, "detector"):
                try:
                    if safe_hasattr(self.trading_app.detector, "signal_engine"):
                        engine = self.trading_app.detector.signal_engine
                        if engine is not None:
                            QTimer.singleShot(0, lambda: self._load_strategy_to_engine(active_slug))
                except Exception as e:
                    logger.error(f"[TradingGUI._apply_active_strategy_deferred] Failed to update engine: {e}")
            QTimer.singleShot(200, self._update_chart_config)
        except Exception as e:
            logger.error(f"[TradingGUI._apply_active_strategy_deferred] Failed: {e}", exc_info=True)

    def _load_strategy_to_engine(self, slug: str):
        try:
            if (self.trading_app and
                    safe_hasattr(self.trading_app, "detector") and
                    safe_hasattr(self.trading_app.detector, "signal_engine") and
                    self.trading_app.detector.signal_engine is not None):
                self.trading_app.detector.signal_engine.load_from_strategy(slug)
        except Exception as e:
            logger.error(f"[TradingGUI._load_strategy_to_engine] Failed: {e}", exc_info=True)

    def _update_chart_config(self):
        try:
            if safe_hasattr(self, 'chart_widget') and self.chart_widget:
                engine = (self.trading_app.detector.signal_engine
                          if self.trading_app and safe_hasattr(self.trading_app, 'detector')
                          else None)
                self.chart_widget.set_config(self.config, engine)
        except Exception as e:
            logger.warning(f"[TradingGUI._update_chart_config] Failed: {e}")

    def _apply_active_strategy(self):
        try:
            if self._closing:
                return
            if not self.strategy_manager:
                return
            indicator_params = self.strategy_manager.get_active_indicator_params()
            for key, value in indicator_params.items():
                if safe_hasattr(self.config, key):
                    safe_setattr(self.config, key, value)
            if (self.trading_app and
                    safe_hasattr(self.trading_app, "detector") and
                    safe_hasattr(self.trading_app.detector, "signal_engine") and
                    self.trading_app.detector.signal_engine is not None):
                active_slug = self.strategy_manager.get_active_slug()
                if active_slug:
                    self.trading_app.detector.signal_engine.load_from_strategy(active_slug)
            if safe_hasattr(self, 'chart_widget') and self.chart_widget:
                try:
                    engine = (self.trading_app.detector.signal_engine
                              if self.trading_app and safe_hasattr(self.trading_app, 'detector')
                              else None)
                    self.chart_widget.set_config(self.config, engine)
                except Exception as e:
                    logger.warning(f"[TradingGUI._apply_active_strategy] Chart config refresh failed: {e}")
        except Exception as e:
            logger.error(f"[TradingGUI._apply_active_strategy] Failed: {e}", exc_info=True)

    # =========================================================================
    # Window lifecycle
    # =========================================================================

    def closeEvent(self, event):
        """Handle close event"""
        try:
            if self._closing:
                event.accept()
                return
            self._closing = True
            logger.info("[TradingGUI.closeEvent] Application closing, starting cleanup...")

            for timer in [self.timer_fast, self.timer_chart, self.timer_app_status,
                          self.timer_connection_check, self.timer_market_status]:
                if timer is not None:
                    try:
                        timer.stop()
                    except Exception as e:
                        logger.warning(f"[TradingGUI.closeEvent] Timer stop error: {e}")

            self._close_all_popups()

            if self.app_running and self.trading_thread:
                try:
                    self.trading_thread.request_stop()
                    if not self.trading_thread.wait(5000):
                        logger.warning("[TradingGUI.closeEvent] Trading thread did not stop gracefully, terminating")
                        self.trading_thread.terminate()
                except Exception as e:
                    logger.error(f"[TradingGUI.closeEvent] Thread cleanup error: {e}")

            if self.trading_app and safe_hasattr(self.trading_app, 'cleanup'):
                try:
                    self.trading_app.cleanup()
                except Exception as e:
                    logger.error(f"[TradingGUI.closeEvent] Trading app cleanup error: {e}")

            if self.daily_pnl_widget and safe_hasattr(self.daily_pnl_widget, 'cleanup'):
                try:
                    self.daily_pnl_widget.cleanup()
                except Exception as e:
                    logger.error(f"[TradingGUI.closeEvent] DailyPnLWidget cleanup error: {e}")

            try:
                state_manager.reset_for_backtest()
            except Exception as e:
                logger.error(f"[TradingGUI.closeEvent] State manager reset error: {e}")

            if self._log_handler:
                try:
                    logging.getLogger().removeHandler(self._log_handler)
                except Exception as e:
                    logger.warning(f"[TradingGUI.closeEvent] Log handler removal error: {e}")

            logger.info("[TradingGUI.closeEvent] Cleanup completed, closing application")
            event.accept()

        except Exception as e:
            logger.error(f"[TradingGUI.closeEvent] Failed: {e}", exc_info=True)
            event.accept()

    def cleanup(self):
        """Graceful cleanup of resources"""
        try:
            if self._closing:
                return
            self._closing = True

            for timer in [self.timer_fast, self.timer_chart, self.timer_app_status,
                          self.timer_connection_check, self.timer_market_status]:
                if timer is not None:
                    try:
                        timer.stop()
                    except Exception:
                        pass

            self._close_all_popups()

            if self.trading_thread is not None and self.trading_thread.isRunning():
                try:
                    self.trading_thread.request_stop()
                    if not self.trading_thread.wait(10000):
                        self.trading_thread.terminate()
                        self.trading_thread.wait(2000)
                except Exception as e:
                    logger.error(f"[TradingGUI.cleanup] Thread cleanup error: {e}", exc_info=True)

            if self.daily_pnl_widget and safe_hasattr(self.daily_pnl_widget, 'cleanup'):
                try:
                    self.daily_pnl_widget.cleanup()
                except Exception:
                    pass

            if self._log_handler:
                try:
                    logging.getLogger().removeHandler(self._log_handler)
                except Exception:
                    pass

            self.trading_app = None
            self.trading_thread = None
            self.chart_widget = None
            self.status_panel = None
            self.app_status_bar = None

            logger.info("[TradingGUI.cleanup] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradingGUI.cleanup] Error: {e}", exc_info=True)