# gui/trading_gui.py
"""
Main trading dashboard window for the Algo Trading application.
Provides the primary user interface for monitoring and controlling the trading engine.
"""

import logging
import logging.handlers
import os
import sys
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List

import pandas as pd

from Utils.common import to_date_str
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QHBoxLayout, QVBoxLayout,
    QPushButton, QRadioButton, QAction, QMessageBox, QLabel,
    QFrame, QApplication, QTabWidget, QMenu, QSizePolicy
)

import BaseEnums
from config import Config
from gui.app_status_bar import AppStatusBar
from gui.brokerage_settings.BrokerageSetting import BrokerageSetting
from gui.brokerage_settings.BrokerageSettingGUI import BrokerageSettingDialog
from gui.brokerage_settings.Brokerloginpopup import BrokerLoginPopup
from gui.chart_widget import MultiChartWidget
from gui.daily_trade.DailyTradeSetting import DailyTradeSetting
from gui.daily_trade.DailyTradeSettingGUI import DailyTradeSettingGUI
from gui.log_handler import QtLogHandler
from gui.popups.dynamic_signal_debug_popup import DynamicSignalDebugPopup
from gui.popups.logs_popup import LogPopup
from gui.popups.stats_popup import StatsPopup
from gui.popups.trade_history_popup import TradeHistoryPopup
from gui.popups.connection_monitor_popup import ConnectionMonitorPopup
from gui.popups.system_monitor_popup import SystemMonitorPopup
from gui.profit_loss.ProfitStoplossSetting import ProfitStoplossSetting
from gui.profit_loss.ProfitStoplossSettingGUI import ProfitStoplossSettingGUI
from gui.profit_loss.daily_pnl_widget import DailyPnLWidget
from gui.status_panel import StatusPanel
from gui.trading_mode.TradingModeSetting import TradingModeSetting
from gui.trading_mode.TradingModeSettingGUI import TradingModeSettingGUI
from gui.theme_manager import theme_manager
from new_main import TradingApp
from strategy.strategy_editor_window import StrategyEditorWindow
from strategy.strategy_manager import StrategyManager
from strategy.strategy_picker_sidebar import StrategyPickerSidebar
from trading_thread import TradingThread
from license.license_manager import license_manager

# IMPORTANT: Use the state manager for all state access
from data.trade_state_manager import state_manager
from data.candle_store_manager import candle_store_manager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TradingGUI(QMainWindow):
    """Main trading dashboard window - replaces Tkinter TradingGUI class"""

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
        # Rule 1: Safe defaults first - before any UI setup
        self._safe_defaults_init()

        try:
            super().__init__()
            self.setWindowTitle("Algo Trading Dashboard")

            # Get screen geometry for initial sizing
            screen = QApplication.primaryScreen()
            if screen:
                screen_rect = screen.availableGeometry()
                # Scale to 80% of screen size but respect minimum
                width = min(1400, int(screen_rect.width() * 0.8))
                height = min(850, int(screen_rect.height() * 0.8))
                self.resize(width, height)
            else:
                self.resize(1400, 850)

            self.setMinimumSize(1100, 700)

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

            # Apply the active strategy immediately
            self._apply_active_strategy()

            # Build UI
            self._setup_log_handler()
            self._create_menu()
            self._build_layout()
            self._setup_timers()

            # Initialize managers first, then trading app
            self._initialize_infrastructure()
            self._init_trading_app()

            self._setup_system_tray()

            # Rule 3: Connect internal signals
            self._setup_internal_signals()

            # Rule 13.2: Connect theme and density changes
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            # Load saved theme preference
            theme_manager.load_preference()

            # Rule 13.2: Initial theme application
            self.apply_theme()

            # Set initial status
            self.status_updated.emit("Application initialized successfully")
            logger.info("[TradingGUI.__init__] Initialized successfully")

        except Exception as e:
            logger.critical(f"[TradingGUI.__init__] Initialization failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Application initialization failed: {e}")
            # Still try to show a basic window
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
            self._density_menu = None  # Rule 13.5: Density menu
            self._compact_menu_actions = []  # For density radio states
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
            # Skip if closing
            if self._closing:
                return

            c = self._c
            ty = self._ty
            sp = self._sp

            # =============================================================
            # 1. Update layout margins and spacing (density-sensitive)
            # =============================================================
            if hasattr(self, 'centralWidget') and self.centralWidget():
                central = self.centralWidget()
                if central.layout():
                    central.layout().setContentsMargins(
                        sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM
                    )
                    central.layout().setSpacing(sp.GAP_SM)
                    self._main_layout = central.layout()

            # Update button panel height and styling
            if self.btn_panel:
                self.btn_panel.setMinimumHeight(sp.BUTTON_PANEL_H - 8)
                self.btn_panel.setMaximumHeight(sp.BUTTON_PANEL_H + 8)

                # FIX: Re-apply button panel stylesheet with current theme colors
                self.btn_panel.setStyleSheet(f"""
                    QWidget#buttonPanel {{
                        background-color: {c.BG_PANEL};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                    }}
                """)

            # Update splitter handle width
            if hasattr(self, '_splitter') and self._splitter:
                self._splitter.setHandleWidth(sp.SPLITTER)

            # Update status bar height via AppStatusBar (it handles its own apply_theme)
            if self.app_status_bar and hasattr(self.app_status_bar, 'apply_theme'):
                self.app_status_bar.apply_theme()

            # =============================================================
            # 2. Main window stylesheet
            # =============================================================
            self.setStyleSheet(f"""
                QMainWindow, QWidget {{ 
                    background-color: {c.BG_MAIN}; 
                    color: {c.TEXT_MAIN}; 
                }}
                QPushButton {{ 
                    border-radius: {sp.RADIUS_MD}px; 
                    padding: {sp.PAD_SM}px {sp.PAD_LG}px;
                    font-weight: {ty.WEIGHT_BOLD}; 
                    font-size: {ty.SIZE_BODY}pt; 
                    background-color: {c.BG_PANEL};
                    color: {c.TEXT_MAIN};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                }}
                QPushButton:hover {{
                    background-color: {c.BG_HOVER};
                }}
                QPushButton:pressed {{
                    background-color: {c.BG_ROW_B};
                }}
                QPushButton:disabled {{ 
                    background-color: {c.BG_PANEL}; 
                    color: {c.TEXT_DISABLED}; 
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                }}
                QPushButton#successBtn {{
                    background-color: {c.GREEN};
                    color: white;
                    border: none;
                }}
                QPushButton#successBtn:hover {{
                    background-color: {c.GREEN_BRIGHT};
                }}
                QPushButton#dangerBtn {{
                    background-color: {c.RED};
                    color: white;
                    border: none;
                }}
                QPushButton#dangerBtn:hover {{
                    background-color: {c.RED_BRIGHT};
                }}
                QPushButton#warningBtn {{
                    background-color: {c.YELLOW};
                    color: white;
                    border: none;
                }}
                QPushButton#warningBtn:hover {{
                    background-color: {c.YELLOW_BRIGHT};
                }}
                QSplitter::handle {{
                    background-color: {c.BORDER};
                    height: {sp.SPLITTER}px;
                }}
                QMenuBar {{
                    background-color: {c.BAR_BG};
                    color: {c.TEXT_MAIN};
                    border-bottom: {sp.SEPARATOR}px solid {c.BAR_BORDER};
                }}
                QMenuBar::item {{
                    padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                    background: transparent;
                }}
                QMenuBar::item:selected {{
                    background-color: {c.BG_HOVER};
                }}
                QMenu {{
                    background-color: {c.BG_PANEL};
                    color: {c.TEXT_MAIN};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                }}
                QMenu::item {{
                    padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                }}
                QMenu::item:selected {{
                    background-color: {c.BG_HOVER};
                }}
                QMenu::separator {{
                    height: {sp.SEPARATOR}px;
                    background-color: {c.BORDER};
                    margin: {sp.PAD_SM}px 0px;
                }}
                QStatusBar {{
                    background-color: {c.BAR_BG};
                    color: {c.TEXT_DIM};
                    border-top: {sp.SEPARATOR}px solid {c.BAR_BORDER};
                }}
                QTabWidget::pane {{
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    background-color: {c.BG_MAIN};
                }}
                QTabBar::tab {{
                    background-color: {c.BG_PANEL};
                    color: {c.TEXT_DIM};
                    padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    font-size: {ty.SIZE_SM}pt;
                }}
                QTabBar::tab:selected {{
                    background-color: {c.BG_HOVER};
                    color: {c.TEXT_MAIN};
                    border-bottom: 2px solid {c.BLUE};
                }}
                QTabBar::tab:hover {{
                    background-color: {c.BG_HOVER};
                }}
                QScrollBar:vertical {{
                    border: none;
                    background-color: {c.BG_PANEL};
                    width: {sp.ICON_MD}px;
                    border-radius: {sp.RADIUS_MD}px;
                }}
                QScrollBar::handle:vertical {{
                    background-color: {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                    min-height: {sp.BTN_HEIGHT_SM}px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background-color: {c.TEXT_DISABLED};
                }}
                QScrollBar:horizontal {{
                    border: none;
                    background-color: {c.BG_PANEL};
                    height: {sp.ICON_MD}px;
                    border-radius: {sp.RADIUS_MD}px;
                }}
                QScrollBar::handle:horizontal {{
                    background-color: {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                    min-width: {sp.BTN_HEIGHT_SM}px;
                }}
                QScrollBar::handle:horizontal:hover {{
                    background-color: {c.TEXT_DISABLED};
                }}
                QRadioButton {{
                    color: {c.TEXT_MAIN};
                    font-size: {ty.SIZE_SM}pt;
                    spacing: {sp.GAP_XS}px;
                }}
                QRadioButton::indicator {{
                    width: 12px;
                    height: 12px;
                }}
                QRadioButton::indicator:checked {{
                    background-color: {c.BLUE};
                    border: {sp.SEPARATOR}px solid {c.BLUE};
                }}
                QFrame#buttonPanel {{
                    background-color: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                }}
                QFrame[frameShape="5"] {{  /* VLine */
                    border: none;
                    background-color: {c.BORDER};
                    width: {sp.SEPARATOR}px;
                }}
            """)

            # =============================================================
            # 3. Update theme action text
            # =============================================================
            if self._theme_action:
                is_dark = theme_manager.is_dark()
                self._theme_action.setText("🌙  Dark Theme" if is_dark else "☀️  Light Theme")
                self._theme_action.setChecked(is_dark)

            # =============================================================
            # 4. Update connection button colors
            # =============================================================
            self._update_connection_button()

            # =============================================================
            # 5. Update radio buttons
            # =============================================================
            if self.radio_algo and self.radio_manual:
                for rb in [self.radio_algo, self.radio_manual]:
                    rb.setStyleSheet(f"""
                        QRadioButton {{
                            color: {c.TEXT_MAIN};
                            font-size: {ty.SIZE_SM}pt;
                            spacing: {sp.GAP_XS}px;
                        }}
                        QRadioButton::indicator {{
                            width: 12px;
                            height: 12px;
                        }}
                        QRadioButton::indicator:checked {{
                            background-color: {c.BLUE};
                            border: {sp.SEPARATOR}px solid {c.BLUE};
                        }}
                    """)

            # =============================================================
            # 6. Update mode label
            # =============================================================
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

            # Skip if closing
            if self._closing:
                return

            c = self._c
            sp = self._sp
            ty = self._ty

            if self._connection_status == "Connected":
                self.btn_connection.setText("🔌 Connected")
                self.btn_connection.setToolTip("Connected to broker - click for details")
                self.btn_connection.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {c.GREEN};
                        color: white;
                        border: {sp.SEPARATOR}px solid {c.GREEN_BRIGHT};
                        border-radius: {sp.RADIUS_MD}px;
                        padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                        font-weight: {ty.WEIGHT_BOLD};
                    }}
                    QPushButton:hover {{
                        background-color: {c.GREEN_BRIGHT};
                    }}
                """)
            else:
                self.btn_connection.setText("🔌 Disconnected")
                self.btn_connection.setToolTip("Disconnected from broker - click for details")
                self.btn_connection.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {c.BG_PANEL};
                        color: {c.RED_BRIGHT};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                        padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                        font-weight: {ty.WEIGHT_BOLD};
                    }}
                    QPushButton:hover {{
                        background-color: {c.BG_HOVER};
                    }}
                """)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[TradingGUI._update_connection_button] Failed: {e}", exc_info=True)

    def _initialize_infrastructure(self):
        """Initialize the infrastructure managers"""
        try:
            # Skip if closing
            if self._closing:
                return

            # Reset state manager for fresh start
            state_manager.reset_for_backtest()

            # Initialize candle store manager (will be properly set when broker is available)
            from data.candle_store_manager import candle_store_manager
            candle_store_manager.initialize(None)  # Broker will be set later

            logger.info("[TradingGUI._initialize_infrastructure] Infrastructure managers initialized")
        except Exception as e:
            logger.error(f"[TradingGUI._initialize_infrastructure] Failed: {e}", exc_info=True)

    def _create_error_window(self):
        """Create error window if initialization fails"""
        try:
            super().__init__()
            self.setWindowTitle("Algo Trading Dashboard - ERROR")

            # Get screen geometry
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

            # Use theme tokens even in error window
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

            # Apply theme to error window
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
            # Skip if closing
            if self._closing:
                return

            self.error_occurred.connect(self._on_error_signal)
            self.status_updated.connect(self._on_status_updated)
            self.app_state_changed.connect(self._on_app_state_changed)
            self.strategy_changed.connect(self._on_strategy_changed)
            self.log_message_received.connect(self._on_log_message)

            # FEATURE 5: Connect trade signals
            self.trade_closed.connect(self._on_trade_closed)
            self.unrealized_pnl_updated.connect(self._on_unrealized_pnl_updated)

            logger.debug("[TradingGUI._setup_internal_signals] Signals connected")
        except Exception as e:
            logger.error(f"[TradingGUI._setup_internal_signals] Signal setup failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_error_signal(self, message: str):
        """Handle error signals"""
        try:
            # Skip if closing
            if self._closing:
                return

            logger.error(f"[TradingGUI._on_error_signal] Error signal received: {message}")

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
            # Skip if closing
            if self._closing:
                return

            logger.info(f"[TradingGUI._on_status_updated] Status update: {message}")
            # Update window title with status
            self.setWindowTitle(f"Algo Trading Dashboard - {message}")
        except Exception as e:
            logger.error(f"[TradingGUI._on_status_updated] Failed: {e}", exc_info=True)

    @pyqtSlot(bool, str)
    def _on_app_state_changed(self, running: bool, mode: str):
        """Handle app state changes"""
        try:
            # Skip if closing
            if self._closing:
                return

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
        """FEATURE 5: Handle trade closed signal from OrderExecutor"""
        try:
            # Skip if closing
            if self._closing:
                return

            if self.daily_pnl_widget:
                self.daily_pnl_widget.on_trade_closed(pnl, is_winner)
            logger.info(f"[TradingGUI._on_trade_closed] Trade closed - P&L: ₹{pnl:.2f}, Winner: {is_winner}")
        except Exception as e:
            logger.error(f"[TradingGUI._on_trade_closed] Failed: {e}", exc_info=True)

    @pyqtSlot(float)
    def _on_unrealized_pnl_updated(self, pnl: float):
        """FEATURE 5: Handle unrealized P&L updates from TradingApp"""
        try:
            # Skip if closing
            if self._closing:
                return

            if self.daily_pnl_widget:
                self.daily_pnl_widget.on_unrealized_update(pnl)
        except Exception as e:
            logger.error(f"[TradingGUI._on_unrealized_pnl_updated] Failed: {e}", exc_info=True)

    def _setup_log_handler(self):
        """Setup Qt log handler with buffering"""
        try:
            # Skip if closing
            if self._closing:
                return

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
            logging.info("[TradingGUI._setup_log_handler] Logging system initialized")

            # Set up file logging as backup
            self._setup_file_logging()

        except Exception as e:
            logger.error(f"[TradingGUI._setup_log_handler] Failed: {e}", exc_info=True)

    def _setup_file_logging(self):
        """Setup file logging as backup"""
        try:
            # Skip if closing
            if self._closing:
                return

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

            logger.info(f"[TradingGUI._setup_file_logging] File logging setup: {log_file}")

        except Exception as e:
            logger.error(f"[TradingGUI._setup_file_logging] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_log_message(self, message: str):
        """Handle log messages - buffer them and send to popup if open"""
        try:
            # Skip if closing
            if self._closing:
                return

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
            # Skip if closing
            if self._closing:
                return

            from PyQt5.QtWidgets import QSystemTrayIcon, QMenu
            from PyQt5.QtGui import QIcon

            if QSystemTrayIcon.isSystemTrayAvailable():
                self._system_tray_icon = QSystemTrayIcon(self)
                self._system_tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))

                # Create tray menu
                tray_menu = QMenu()
                self._update_tray_menu_style()  # Initial styling

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

                # Connect to theme changes to update tray menu styling
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
                logger.debug("[TradingGUI._update_tray_menu_style] System tray menu style updated")
        except Exception as e:
            logger.error(f"[TradingGUI._update_tray_menu_style] Failed: {e}", exc_info=True)

    def show_normal(self):
        """Show window normally (from system tray)"""
        try:
            # Skip if closing
            if self._closing:
                return

            self.show()
            self.activateWindow()
            self.raise_()
        except Exception as e:
            logger.error(f"[TradingGUI.show_normal] Failed: {e}", exc_info=True)

    def _build_layout(self):
        """Build main window layout with DailyPnLWidget"""
        try:
            # Skip if closing
            if self._closing:
                return

            sp = self._sp

            central = QWidget()
            self.setCentralWidget(central)
            root_layout = QVBoxLayout(central)
            root_layout.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)
            root_layout.setSpacing(sp.GAP_SM)
            self._main_layout = root_layout

            # ── Top section: Chart (left) + Status Panel (right) ─────────────────────
            self._splitter = QSplitter(Qt.Horizontal)
            self._splitter.setHandleWidth(sp.SPLITTER)

            # Left side container for chart and buttons
            left_container = QWidget()
            left_layout = QVBoxLayout(left_container)
            left_layout.setContentsMargins(0, 0, 0, 0)
            left_layout.setSpacing(sp.GAP_SM)

            # Chart widget with tabs
            self.chart_widget = MultiChartWidget()
            self.chart_widget.setMinimumWidth(800)
            self.chart_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            left_layout.addWidget(self.chart_widget, 1)

            # Button panel (below chart)
            button_panel = self._build_button_panel()
            left_layout.addWidget(button_panel)

            # Add left container to splitter
            self._splitter.addWidget(left_container)

            # Right side: Status panel
            self.status_panel = StatusPanel()
            self.status_panel.setMinimumWidth(260)
            self.status_panel.setMaximumWidth(420)
            self._splitter.addWidget(self.status_panel)

            # Set stretch factors (chart gets 3, status gets 1)
            self._splitter.setStretchFactor(0, 3)
            self._splitter.setStretchFactor(1, 1)

            # Set initial sizes
            self._splitter.setSizes([1060, 340])
            root_layout.addWidget(self._splitter, 1)

            # ── FEATURE 5: Daily P&L Widget (below splitter) ─────────────────────────
            self.daily_pnl_widget = DailyPnLWidget(self.config)
            self.daily_pnl_widget.setMinimumHeight(60)
            self.daily_pnl_widget.setMaximumHeight(90)
            root_layout.addWidget(self.daily_pnl_widget)

            # ── Bottom section: App Status Bar ─────────────────────────────
            self.app_status_bar = AppStatusBar()
            self.app_status_bar.setMinimumHeight(sp.STATUS_BAR_H - 8)
            self.app_status_bar.setMaximumHeight(sp.STATUS_BAR_H + 8)
            root_layout.addWidget(self.app_status_bar)

        except Exception as e:
            logger.error(f"[TradingGUI._build_layout] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to build layout: {e}")

    def _build_button_panel(self) -> QWidget:
        """Build horizontal button panel below chart with mode-dependent visibility"""
        panel = QWidget()
        try:
            # Skip if closing
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

            # Mode toggle group
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

            # Mode indicator
            self.mode_label = QLabel(
                f"Mode: {self.trading_mode_setting.mode.value if self.trading_mode_setting else 'algo'}")
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
                rb.setStyleSheet(f"""
                    QRadioButton {{
                        color: {c.TEXT_MAIN};
                        font-size: {ty.SIZE_SM}pt;
                        spacing: {sp.GAP_XS}px;
                        background-color: transparent;
                    }}
                    QRadioButton::indicator {{
                        width: 12px;
                        height: 12px;
                    }}
                    QRadioButton::indicator:checked {{
                        background-color: {c.BLUE};
                        border: {sp.SEPARATOR}px solid {c.BLUE};
                    }}
                """)
                rb.setToolTip("Switch between automated and manual trading")
                mode_layout.addWidget(rb)

            layout.addWidget(mode_frame)

            # Separator
            separator = QFrame()
            separator.setFrameShape(QFrame.VLine)
            separator.setStyleSheet(
                f"QFrame {{ border: none; background-color: {c.BORDER}; width: {sp.SEPARATOR}px; }}")
            layout.addWidget(separator)

            # Control buttons using theme_manager.button_stylesheet helpers
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

            # Apply styles using theme_manager helpers
            self.btn_strategy.setStyleSheet(theme_manager.button_stylesheet("BLUE_DARK", "BLUE"))
            self.btn_start.setStyleSheet(theme_manager.button_stylesheet("GREEN", "GREEN_BRIGHT"))
            self.btn_stop.setStyleSheet(theme_manager.button_stylesheet("RED", "RED_BRIGHT"))

            # Add buttons to layout
            layout.addWidget(self.btn_strategy)
            layout.addWidget(self.btn_start)
            layout.addWidget(self.btn_stop)
            layout.addWidget(self.btn_connection)

            # Create a container for manual trading buttons
            self.manual_buttons_container = QWidget()
            manual_layout = QHBoxLayout(self.manual_buttons_container)
            manual_layout.setContentsMargins(0, 0, 0, 0)
            manual_layout.setSpacing(sp.GAP_MD)

            self.btn_call = QPushButton("📈  Buy Call")
            self.btn_put = QPushButton("📉  Buy Put")
            self.btn_exit = QPushButton("🚪  Exit")

            # Apply styles for manual buttons
            self.btn_call.setStyleSheet(theme_manager.button_stylesheet("BLUE_DARK", "BLUE"))
            self.btn_put.setStyleSheet(theme_manager.button_stylesheet("PURPLE", "PURPLE"))
            self.btn_exit.setStyleSheet(theme_manager.button_stylesheet("YELLOW", "YELLOW_BRIGHT"))

            # Set tooltips for manual buttons
            self.btn_call.setToolTip("Buy a CALL option (manual mode only)")
            self.btn_put.setToolTip("Buy a PUT option (manual mode only)")
            self.btn_exit.setToolTip("Exit current position (manual mode only)")

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

            # Add manual buttons to container
            manual_layout.addWidget(self.btn_call)
            manual_layout.addWidget(self.btn_put)
            manual_layout.addWidget(self.btn_exit)

            # Initially hide manual buttons (default to algo mode)
            self.manual_buttons_container.setVisible(False)

            # Add stretch and manual container
            layout.addStretch()
            layout.addWidget(self.manual_buttons_container)

            # Store panel reference for apply_theme
            self.btn_panel = panel

            # Initial connection button styling
            self._update_connection_button()

        except Exception as e:
            logger.error(f"[TradingGUI._build_button_panel] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to build button panel: {e}")

        return panel

    def _setup_timers(self):
        """Setup all timers - enhanced with market status check"""
        try:
            # Skip if closing
            if self._closing:
                return

            # Fast timer (1 second) - for status updates
            self.timer_fast = QTimer(self)
            self.timer_fast.timeout.connect(self._tick_fast)
            self.timer_fast.start(1000)

            # Chart timer (5 seconds) - with debouncing
            self.timer_chart = QTimer(self)
            self.timer_chart.timeout.connect(self._tick_chart)
            self.timer_chart.start(5000)

            # App status timer (500ms)
            self.timer_app_status = QTimer(self)
            self.timer_app_status.timeout.connect(self._update_app_status)
            self.timer_app_status.start(500)

            # Connection check timer (10 seconds)
            self.timer_connection_check = QTimer(self)
            self.timer_connection_check.timeout.connect(self._check_connection)
            self.timer_connection_check.start(10000)

            # Market status check timer (30 seconds)
            self.timer_market_status = QTimer(self)
            self.timer_market_status.timeout.connect(self._update_market_status)
            self.timer_market_status.start(30000)

            # Initial market status check
            QTimer.singleShot(100, self._update_market_status)

        except Exception as e:
            logger.error(f"[TradingGUI._setup_timers] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _tick_fast(self):
        """Fast timer tick - update UI"""
        try:
            # Skip if closing
            if self._closing:
                return

            # Always refresh status panel — index price, balance etc. must
            # update even before the trading engine is started.
            if self.status_panel is not None:
                self.status_panel.refresh(self.config)

            if self.trading_app is None:
                return

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
            # Skip if closing
            if self._closing:
                return

            if self.trading_app is None:
                return

            # Update chart
            self._update_chart_if_needed()

            # Update trade history
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
            # Skip if closing
            if self._closing:
                return

            if self.trading_app is None:
                return

            # Check if thread is actually running
            thread_is_running = self.trading_thread is not None and self.trading_thread.isRunning()

            # Only consider app running if both flag and thread are running
            actual_running = self.app_running and thread_is_running

            # If app_running is True but thread isn't running, correct the state
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

            # Get position snapshot for decision making
            position_snapshot = state_manager.get_position_snapshot()

            # Get status information from snapshot
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

            # Add position type if exists
            if status_info['has_position']:
                status_info['position_type'] = position_snapshot.get('current_position')

            # Get current P&L
            current_pnl = position_snapshot.get('current_pnl')
            if current_pnl is not None:
                status_info['current_pnl'] = current_pnl
                # FEATURE 5: Emit unrealized P&L for DailyPnLWidget
                self.unrealized_pnl_updated.emit(float(current_pnl))
            else:
                # Emit 0.0 when no position (no unrealized P&L)
                self.unrealized_pnl_updated.emit(0.0)

            # Check history fetch status from trading app
            if hasattr(self.trading_app, '_history_fetch_in_progress'):
                status_info['fetching_history'] = self.trading_app._history_fetch_in_progress.is_set()

            # Check processing status
            if hasattr(self.trading_app, '_tick_queue'):
                status_info['processing'] = not self.trading_app._tick_queue.empty()

            # Update status bar with correct running state
            self.app_status_bar.update_status(
                status_info,
                self.trading_mode,
                actual_running  # Use actual_running instead of self.app_running
            )

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[TradingGUI._update_app_status] Failed: {e}", exc_info=True)

    def _update_market_status(self):
        """Update market status and button states accordingly"""
        try:
            # Skip if closing
            if self._closing:
                return

            if self.trading_app and hasattr(self.trading_app, '_check_market_status'):
                is_open = self.trading_app._check_market_status()
                self._market_status = "OPEN" if is_open else "CLOSED"
            else:
                # Fallback to Utils
                from Utils.Utils import Utils
                is_open = Utils.is_market_open()
                self._market_status = "OPEN" if is_open else "CLOSED"

            # Update status bar with market status
            if self.app_status_bar:
                self.app_status_bar.update_market_status(self._market_status)

            # Update button states based on market status and mode
            self._update_button_states()

            logger.debug(f"[TradingGUI._update_market_status] Market status updated: {self._market_status}")

        except Exception as e:
            logger.error(f"[TradingGUI._update_market_status] Failed: {e}", exc_info=True)
            self._market_status = "UNKNOWN"

    def _check_connection(self):
        """Check connection status"""
        try:
            # Skip if closing
            if self._closing:
                return

            if self.trading_app and hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                if hasattr(self.trading_app.ws, 'is_connected'):
                    is_connected = self.trading_app.ws.is_connected()
                    self._connection_status = "Connected" if is_connected else "Disconnected"
                else:
                    self._connection_status = "Unknown"
            else:
                self._connection_status = "Disconnected"

            # Update connection button
            self._update_connection_button()

        except Exception as e:
            logger.error(f"[TradingGUI._check_connection] Failed: {e}", exc_info=True)

    def _update_chart_if_needed(self):
        """Check if chart needs update by comparing with CandleStore last bar time"""
        try:
            # Skip if closing
            if self._closing:
                return

            if self._chart_update_pending:
                return

            # Get symbol from daily settings
            symbol = self.daily_setting.derivative if self.daily_setting else None
            if not symbol:
                return

            # Get current timeframe
            tf_minutes = self.chart_widget.get_current_timeframe() if hasattr(self.chart_widget,
                                                                              'get_current_timeframe') else 5

            # Get last bar time from CandleStore
            from data.candle_store_manager import candle_store_manager
            last_bar_time = candle_store_manager.last_bar_time(symbol)

            if last_bar_time is None:
                # No data yet, try to fetch
                logger.debug(
                    f"[TradingGUI._update_chart_if_needed] No data in CandleStore for {symbol}, will attempt fetch")
                self._chart_update_pending = True
                QTimer.singleShot(100, self._do_chart_update)
                return

            # Create fingerprint based on last bar time and bar count
            bar_count = candle_store_manager.bar_count(symbol)
            current_fp = f"{last_bar_time.timestamp()}:{bar_count}:{tf_minutes}"

            if current_fp != self._last_chart_fp:
                logger.debug(
                    f"[TradingGUI._update_chart_if_needed] Chart fingerprint changed: {self._last_chart_fp[:20]}... -> {current_fp[:20]}...")
                self._last_chart_fp = current_fp
                self._chart_update_pending = True
                QTimer.singleShot(100, self._do_chart_update)

        except Exception as e:
            logger.error(f"[TradingGUI._update_chart_if_needed] Failed: {e}", exc_info=True)
            # Schedule update anyway on error
            if not self._chart_update_pending:
                self._chart_update_pending = True
                QTimer.singleShot(100, self._do_chart_update)

    def _do_chart_update(self):
        """Perform actual chart update - fetch directly from CandleStoreManager"""
        try:
            # Skip if closing
            if self._closing:
                return

            if not self.chart_widget:
                self._chart_update_pending = False
                return

            # Get symbol from daily settings
            symbol = self.daily_setting.derivative if self.daily_setting else None
            if not symbol:
                logger.warning("[TradingGUI._do_chart_update] No symbol set for chart")
                self._chart_update_pending = False
                return

            # Get current timeframe from chart widget
            tf_minutes = self.chart_widget.get_current_timeframe() if hasattr(self.chart_widget,
                                                                              'get_current_timeframe') else 5

            # Fetch directly from candle_store_manager
            from data.candle_store_manager import candle_store_manager

            # Check if store has data, if not try to fetch
            if candle_store_manager.is_empty(symbol):
                logger.info(f"[TradingGUI._do_chart_update] CandleStore empty for {symbol}, attempting to fetch...")

                # Get broker type from brokerage setting
                broker_type = None
                if hasattr(self, 'brokerage_setting') and self.brokerage_setting:
                    broker_type = getattr(self.brokerage_setting, 'broker_type', None)

                # Fetch data (2 days by default)
                success = candle_store_manager.fetch_all(days=2, symbols=[symbol], broker_type=broker_type)
                if not success.get(symbol, False):
                    logger.warning(f"[TradingGUI._do_chart_update] Failed to fetch data for {symbol}")
                    self._chart_update_pending = False
                    return

            # Get resampled data
            df = candle_store_manager.resample(symbol, tf_minutes)

            if df is None or df.empty:
                logger.debug(f"[TradingGUI._do_chart_update] No data available for {symbol} at {tf_minutes}m")
                self._chart_update_pending = False
                return

            # Convert timestamps to strings for display (format based on timeframe)
            time_col = df["time"] if "time" in df.columns else pd.Series()

            # Format timestamps based on timeframe
            if tf_minutes >= 60:  # Hourly or higher
                time_str = [t.strftime("%Y-%m-%d %H:%M") for t in time_col]
            elif tf_minutes >= 15:  # 15min or 30min
                time_str = [t.strftime("%H:%M") for t in time_col]
            else:  # 1min, 3min, 5min
                time_str = [t.strftime("%H:%M") for t in time_col]

            # Convert to the format expected by chart widget
            chart_data = {
                "open": df["open"].tolist(),
                "high": df["high"].tolist(),
                "low": df["low"].tolist(),
                "close": df["close"].tolist(),
                "volume": df["volume"].tolist() if "volume" in df.columns else [],
                "timestamps": time_str,  # Use formatted strings for display
                "datetime": time_col.tolist(),  # Keep original datetime objects
            }

            # Update chart
            self.chart_widget.update_charts(spot_data=chart_data)
            logger.debug(
                f"[TradingGUI._do_chart_update] Chart updated with {len(df)} bars for {symbol} at {tf_minutes}m")

        except Exception as e:
            logger.error(f"[TradingGUI._do_chart_update] Failed: {e}", exc_info=True)
        finally:
            self._chart_update_pending = False

    def _force_chart_refresh(self):
        """Force a chart refresh - useful after app start or timeframe change"""
        try:
            # Skip if closing
            if self._closing:
                return

            logger.info("[TradingGUI._force_chart_refresh] Forcing chart refresh")
            self._chart_update_pending = False
            self._last_chart_fp = ""

            # Clear cache in chart widget
            if hasattr(self.chart_widget, 'clear_cache'):
                self.chart_widget.clear_cache()

            # Force update
            self._do_chart_update()
        except Exception as e:
            logger.error(f"[TradingGUI._force_chart_refresh] Failed: {e}", exc_info=True)

    def _on_timeframe_changed(self, minutes: int):
        """Handle timeframe change from chart widget"""
        try:
            # Skip if closing
            if self._closing:
                return

            logger.info(f"[TradingGUI._on_timeframe_changed] Timeframe changed to {minutes}m")
            # Force chart refresh on timeframe change
            self._last_chart_fp = ""  # Reset fingerprint
            self._force_chart_refresh()
        except Exception as e:
            logger.error(f"[TradingGUI._on_timeframe_changed] Failed: {e}", exc_info=True)

    def _update_button_states(self):
        """Enable/disable buttons based on app state and market status"""
        try:
            # Skip if closing
            if self._closing:
                return

            # Get position snapshot
            position_snapshot = state_manager.get_position_snapshot()
            has_pos = position_snapshot.get('current_position') is not None
            manual = self.trading_mode == "manual"

            # Check if we're in backtest mode
            is_backtest = False
            if self.trading_mode_setting:
                is_backtest = self.trading_mode_setting.mode.value.upper() == "BACKTEST"

            # Check if market is open
            market_open = self._market_status == "OPEN"

            # Base button states
            if self.btn_start:
                self.btn_start.setDisabled(self.app_running)
            if self.btn_stop:
                self.btn_stop.setDisabled(not self.app_running)

            # Show/hide manual buttons based on mode
            if hasattr(self, 'manual_buttons_container') and self.manual_buttons_container:
                self.manual_buttons_container.setVisible(manual and not is_backtest)

            # For backtest mode, always enable start button (no market dependency)
            if is_backtest:
                if self.btn_start:
                    self.btn_start.setDisabled(self.app_running)
                    # Update start button text to indicate backtest mode
                    if not self.app_running:
                        self.btn_start.setText("▶  Start Backtest")
                return

            # For non-backtest modes, check market status
            if self.app_running:
                if manual:
                    # Manual mode - trading buttons depend on market
                    if self.btn_call:
                        self.btn_call.setDisabled(has_pos)
                    if self.btn_put:
                        self.btn_put.setDisabled(has_pos)
                    if self.btn_exit:
                        self.btn_exit.setDisabled(not has_pos)

                    if not market_open:
                        # Market closed - disable manual trading
                        if self.btn_call:
                            self.btn_call.setDisabled(True)
                        if self.btn_put:
                            self.btn_put.setDisabled(True)
                        if self.btn_exit:
                            self.btn_exit.setDisabled(True)

                        # Show tooltip explaining why buttons are disabled
                        if self.btn_call:
                            self.btn_call.setToolTip("Market is closed - manual trading unavailable")
                        if self.btn_put:
                            self.btn_put.setToolTip("Market is closed - manual trading unavailable")
                        if self.btn_exit:
                            self.btn_exit.setToolTip("Market is closed - manual trading unavailable")
            else:
                # App not running - update start button based on market status
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
        """Create the trading app instance"""
        try:
            # Skip if closing
            if self._closing:
                return

            # IMPORTANT FIX: Log settings before creating TradingApp for debugging
            logger.info("[TradingGUI._init_trading_app] Initializing TradingApp with settings:")
            logger.info(
                f"  Brokerage: client_id={self.brokerage_setting.client_id[:5] if self.brokerage_setting.client_id else 'None'}...")
            logger.info(f"  Daily: derivative={self.daily_setting.derivative}, lot_size={self.daily_setting.lot_size}")
            logger.info(
                f"  P&L: tp={self.profit_loss_setting.tp_percentage}%, sl={self.profit_loss_setting.stoploss_percentage}%")
            logger.info(f"  Mode: {self.trading_mode_setting.mode.value}")

            self.trading_app = TradingApp(
                config=self.config,
                broker_setting=self.brokerage_setting,
                trading_mode_var=self.trading_mode_setting,
            )

            # Initialize candle store manager with broker from trading app
            if hasattr(self.trading_app, 'broker') and self.trading_app.broker:
                from data.candle_store_manager import candle_store_manager
                candle_store_manager.initialize(self.trading_app.broker)
                logger.info(
                    f"[TradingGUI._init_trading_app] CandleStoreManager initialized with broker for symbol: {self.daily_setting.derivative}")

            # FEATURE 5: Connect trade closed callback
            if hasattr(self.trading_app, 'executor'):
                self.trading_app.executor.on_trade_closed_callback = self._on_trade_closed

            # Wire up chart config + signal engine
            try:
                engine = getattr(
                    getattr(self.trading_app, 'detector', None),
                    'signal_engine', None
                )
                self.chart_widget.set_config(self.config, engine)
                logger.info("[TradingGUI._init_trading_app] Chart config set from trading app")
            except Exception as e:
                logger.warning(f"[TradingGUI._init_trading_app] Could not set chart config: {e}")
                self.chart_widget.set_config(self.config, None)

            # Update status
            self.app_status_bar.update_status({
                'initialized': True,
                'status': 'App initialized'
            }, self.trading_mode, False)

            logger.info("[TradingGUI._init_trading_app] TradingApp initialized successfully")

        except Exception as e:
            logger.critical(f"[TradingGUI._init_trading_app] Failed to create TradingApp: {e}", exc_info=True)
            error_str = str(e)

            # Check if this is a token expiry error
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
        """Start trading engine on QThread - enhanced with market status check"""
        try:
            # Skip if closing
            if self._closing:
                return

            if self.trading_app is None:
                logger.error("[TradingGUI._start_app] Start failed: Trading app not initialized")
                QMessageBox.critical(self, "Error", "Trading app not initialised.")
                return

            # Check if we're in backtest mode
            is_backtest = False
            if self.trading_mode_setting:
                is_backtest = self.trading_mode_setting.mode.value.upper() == "BACKTEST"

            # ── License gate: block LIVE mode for free / trial users ──────────
            if self._is_live_mode() and not license_manager.is_live_trading_allowed():
                self._show_live_upgrade_dialog()
                return

            # For non-backtest modes, warn if market is closed
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

            # Connect to started signal to update app_running
            self.trading_thread.started.connect(self._on_thread_started)

            # FEATURE 5: Connect trade closed signal from thread
            self.trading_thread.position_closed.connect(
                lambda sym, pnl: self.trade_closed.emit(pnl, pnl > 0)
            )

            # Set initial state to starting
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

            # Start the thread
            self.trading_thread.start()

            logger.info(
                f"[TradingGUI._start_app] Trading engine thread started (mode: {'BACKTEST' if is_backtest else 'LIVE/PAPER'}")

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
            # Skip if closing
            if self._closing:
                return

            self.app_running = True
            self.app_status_bar.update_status(
                {'status': 'Running'},
                self.trading_mode,
                True
            )
            self.status_updated.emit("Trading engine running")
            logger.info("[TradingGUI._on_thread_started] Trading thread started successfully")
            self.app_state_changed.emit(True, self.trading_mode)
        except Exception as e:
            logger.error(f"[TradingGUI._on_thread_started] Failed: {e}", exc_info=True)

    def _is_live_mode(self) -> bool:
        """Return True when the trading mode setting is set to LIVE"""
        try:
            if self.trading_mode_setting and hasattr(self.trading_mode_setting, 'is_live'):
                return self.trading_mode_setting.is_live()
            # Fallback: check the mode value string directly
            if self.trading_mode_setting and hasattr(self.trading_mode_setting, 'mode'):
                return str(self.trading_mode_setting.mode.value).upper() == "LIVE"
        except Exception as e:
            logger.warning(f"[TradingGUI._is_live_mode] {e}")
        return False

    def _show_live_upgrade_dialog(self):
        """Show the LiveTradingUpgradeDialog when a free/trial user clicks Start in LIVE mode"""
        try:
            from license.activation_dialog import LiveTradingUpgradeDialog
            from PyQt5.QtWidgets import QDialog

            dlg = LiveTradingUpgradeDialog(parent=self)

            def _on_activated(result):
                """License now paid — immediately start the trading engine"""
                logger.info(f"[TradingGUI._show_live_upgrade_dialog] Upgraded to {result.plan} — starting live engine")
                self._update_mode_display()  # refresh mode label colour
                # Small delay so the success message is visible in the dialog
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(1400, self._start_app)

            def _on_paper():
                """User chose to trade in paper mode instead of upgrading"""
                try:
                    if self.trading_mode_setting:
                        self.trading_mode_setting.set_mode("PAPER")
                        self._update_mode_display()
                        logger.info(
                            "[TradingGUI._show_live_upgrade_dialog] Switched to PAPER mode at user request after upgrade prompt")
                    # Start immediately — no second click needed
                    self._start_app()
                except Exception as e:
                    logger.error(f"[TradingGUI._show_live_upgrade_dialog._on_paper] {e}", exc_info=True)

            dlg.activated.connect(_on_activated)
            dlg.switch_to_paper.connect(_on_paper)
            dlg.exec_()

        except Exception as e:
            logger.error(f"[TradingGUI._show_live_upgrade_dialog] {e}", exc_info=True)

    def _check_token_expired(self, buffer_minutes: int = 1) -> bool:
        """
        Check if the stored broker token has expired.

        Handles timezone differences by assuming stored timestamps are in UTC
        (as they typically are from brokers) and converting local time to UTC
        for comparison.

        Args:
            buffer_minutes: Number of minutes before actual expiry to consider as expired
                           (default: 1 minute)

        Returns:
            bool: True if token is expired or no valid token exists, False if token is still valid
        """
        try:
            from datetime import datetime, timezone
            from db.crud import tokens

            # Get the current token data from database
            token_data = tokens.get()

            if not token_data:
                logger.warning("[TradingGUI._check_token_expired] No token data found in database")
                return True

            # Get the expiry timestamp
            expiry_str = token_data.get('expires_at')

            if not expiry_str:
                # Also check if there's an access token at least
                access_token = token_data.get('access_token', '')
                if access_token:
                    logger.debug("[TradingGUI._check_token_expired] Token exists but no expiry date")
                    # Without expiry, assume it's valid (some tokens don't expire)
                    return False
                else:
                    logger.debug("[TradingGUI._check_token_expired] No access token found")
                    return True

            # Parse the expiry timestamp - assume it's in UTC (as most brokers provide)
            expiry = None

            # List of possible timestamp formats to try
            formats = [
                "%Y-%m-%dT%H:%M:%S",  # ISO format: 2024-01-20T15:30:00
                "%Y-%m-%d %H:%M:%S",  # SQL format: 2024-01-20 15:30:00
                "%Y-%m-%dT%H:%M:%S.%f",  # ISO with microseconds
                "%Y-%m-%d %H:%M:%S.%f",  # SQL with microseconds
            ]

            for fmt in formats:
                try:
                    # Parse as naive datetime first
                    naive_expiry = datetime.strptime(expiry_str, fmt)
                    # Assume it's UTC and add timezone
                    expiry = naive_expiry.replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue

            # Try fromisoformat as fallback
            if expiry is None:
                try:
                    # Handle Zulu time (UTC)
                    if expiry_str.endswith('Z'):
                        expiry_str = expiry_str.replace('Z', '+00:00')
                    expiry = datetime.fromisoformat(expiry_str)
                    # If the parsed datetime is naive, assume UTC
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                except (ValueError, AttributeError):
                    pass

            if expiry is None:
                logger.error(f"[TradingGUI._check_token_expired] Could not parse expiry date: {expiry_str}")
                return True

            # Get current time in UTC for fair comparison
            # This works correctly even if you're in GMT+5:30
            now_utc = datetime.now(timezone.utc)

            # Log for debugging
            logger.debug(f"[TradingGUI._check_token_expired] Current UTC: {now_utc}")
            logger.debug(f"[TradingGUI._check_token_expired] Expiry UTC: {expiry}")
            logger.debug(f"[TradingGUI._check_token_expired] Your local time: {datetime.now()}")

            # Add buffer time
            buffer_seconds = buffer_minutes * 60
            time_remaining = (expiry - now_utc).total_seconds()

            if time_remaining <= buffer_seconds:
                if time_remaining > 0:
                    logger.info(
                        f"[TradingGUI._check_token_expired] Token expires in {time_remaining / 60:.1f} minutes (within {buffer_minutes} min buffer)")
                else:
                    logger.info(
                        f"[TradingGUI._check_token_expired] Token expired {abs(time_remaining / 60):.1f} minutes ago")
                return True
            else:
                logger.debug(
                    f"[TradingGUI._check_token_expired] Token valid for {time_remaining / 60:.1f} more minutes")
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
            # Skip if closing
            if self._closing:
                return

            if self.btn_stop:
                self.btn_stop.setDisabled(True)
            self.app_status_bar.update_status({'status': 'Stopping...'}, self.trading_mode, True)
            self.status_updated.emit("Stopping trading engine...")

            # Stop in background thread
            threading.Thread(target=self._threaded_stop, daemon=True, name="StopThread").start()

            logger.info("[TradingGUI._stop_app] Trading engine stopping...")

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
            logger.debug("[TradingGUI._threaded_stop] Stop thread completed")
        except Exception as e:
            logger.error(f"[TradingGUI._threaded_stop] Failed: {e}", exc_info=True)
            QTimer.singleShot(0, lambda: self.error_occurred.emit(f"Stop failed: {e}"))

    @pyqtSlot()
    def _on_engine_finished(self):
        """Slot called when engine finishes"""
        try:
            # Skip if closing
            if self._closing:
                return

            self.app_running = False
            self.app_status_bar.update_status(
                {'status': 'Stopped'},
                self.trading_mode,
                False
            )
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
            # Skip if closing
            if self._closing:
                return

            self.app_running = False
            self.app_status_bar.update_status(
                {'status': '🔐 Token expired — re-login required', 'error': True},
                self.trading_mode, False
            )
            self._update_button_states()
            logger.warning(f"[TradingGUI._on_token_expired] Token expired signal received: {message}")

            # Open re-authentication popup
            self._open_login_for_token_expiry(message)
        except Exception as e:
            logger.error(f"[TradingGUI._on_token_expired] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_engine_error(self, message: str):
        """Handle engine errors"""
        try:
            # Skip if closing
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
            # Skip if closing
            if self._closing:
                return

            if self.trading_mode != "manual":
                QMessageBox.information(self, "Mode", "Switch to Manual mode first.")
                return
            if not self.trading_app:
                logger.warning("[TradingGUI._manual_buy] Manual buy attempted with no trading app")
                return

            # Check market status for manual trades
            if self._market_status != "OPEN":
                QMessageBox.warning(self, "Market Closed",
                                    "Cannot place manual orders when market is closed.")
                return

            self.app_status_bar.update_status({'status': f'Placing {option_type} order...'}, self.trading_mode, True)
            threading.Thread(
                target=self._threaded_manual_buy,
                args=(option_type,),
                daemon=True
            ).start()

            logger.info(f"[TradingGUI._manual_buy] Manual {option_type} buy initiated")

        except Exception as e:
            logger.error(f"[TradingGUI._manual_buy] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Manual buy failed: {e}")

    def _threaded_manual_buy(self, option_type):
        """Execute manual buy in background"""
        try:
            if self.trading_app and hasattr(self.trading_app, 'executor'):
                self.trading_app.executor.buy_option(option_type=option_type)
                QTimer.singleShot(0, lambda: self.app_status_bar.update_status(
                    {'status': f'{option_type} order placed'}, self.trading_mode, True))
                logger.info(f"[TradingGUI._threaded_manual_buy] Manual {option_type} order placed successfully")
            else:
                logger.error("[TradingGUI._threaded_manual_buy] Trading app or executor not available")
        except Exception as e:
            logger.error(f"[TradingGUI._threaded_manual_buy] Manual buy thread error: {e}", exc_info=True)
            QTimer.singleShot(0, lambda: self.error_occurred.emit(f"Order failed: {e}"))

    def _manual_exit(self):
        """Manual exit in background thread"""
        try:
            # Skip if closing
            if self._closing:
                return

            if self.trading_mode != "manual":
                QMessageBox.information(self, "Mode", "Switch to Manual mode first.")
                return
            if not self.trading_app:
                logger.warning("[TradingGUI._manual_exit] Manual exit attempted with no trading app")
                return

            # Check market status for manual exits
            if self._market_status != "OPEN":
                QMessageBox.warning(self, "Market Closed",
                                    "Cannot exit positions when market is closed.")
                return

            self.app_status_bar.update_status({'status': 'Exiting position...'}, self.trading_mode, True)
            threading.Thread(
                target=self._threaded_manual_exit,
                daemon=True
            ).start()

            logger.info("[TradingGUI._manual_exit] Manual exit initiated")

        except Exception as e:
            logger.error(f"[TradingGUI._manual_exit] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Manual exit failed: {e}")

    def _threaded_manual_exit(self):
        """Execute manual exit in background"""
        try:
            if self.trading_app and hasattr(self.trading_app, 'executor'):
                self.trading_app.executor.exit_position(reason="Manual Exit")
                QTimer.singleShot(0, lambda: self.app_status_bar.update_status(
                    {'status': 'Position exited'}, self.trading_mode, True))
                logger.info("[TradingGUI._threaded_manual_exit] Manual exit completed successfully")
            else:
                logger.error("[TradingGUI._threaded_manual_exit] Trading app or executor not available")
        except Exception as e:
            logger.error(f"[TradingGUI._threaded_manual_exit] Manual exit thread error: {e}", exc_info=True)
            QTimer.singleShot(0, lambda: self.error_occurred.emit(f"Exit failed: {e}"))

    @pyqtSlot()
    def _on_mode_change(self):
        """Handle mode switch"""
        try:
            # Skip if closing
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
        """Build menu bar - Rule 13.5: Include theme and density controls"""
        try:
            # Skip if closing
            if self._closing:
                return

            menubar = self.menuBar()

            # File menu
            file_menu = menubar.addMenu("File")

            restart_act = QAction("🔄 Restart Application", self)
            restart_act.triggered.connect(self._restart_application)
            restart_act.setToolTip("Restart the entire application")
            file_menu.addAction(restart_act)

            file_menu.addSeparator()

            exit_act = QAction("❌ Exit", self)
            exit_act.triggered.connect(self.close)
            exit_act.setToolTip("Exit the application")
            exit_act.setShortcut("Ctrl+Q")
            file_menu.addAction(exit_act)

            # View menu - for popups
            view_menu = menubar.addMenu("View")

            log_act = QAction("📝 Show Logs", self)
            log_act.triggered.connect(self._show_log_popup)
            log_act.setToolTip("View application logs")
            view_menu.addAction(log_act)

            history_act = QAction("📊 Show Trade History", self)
            history_act.triggered.connect(self._show_history_popup)
            history_act.setToolTip("View trade history")
            view_menu.addAction(history_act)

            stats_act = QAction("📈 Show Statistics", self)
            stats_act.triggered.connect(self._show_stats_popup)
            stats_act.setToolTip("View trading statistics")
            view_menu.addAction(stats_act)

            sig_debug_act = QAction("🔬 Dynamic Signal Debug", self)
            sig_debug_act.triggered.connect(self._show_signal_debug_popup)
            sig_debug_act.setToolTip("Debug signal generation")
            view_menu.addAction(sig_debug_act)

            connection_act = QAction("🌐 Connection Monitor", self)
            connection_act.triggered.connect(self._show_connection_monitor)
            connection_act.setToolTip("Monitor broker connections")
            view_menu.addAction(connection_act)

            system_act = QAction("💻 System Monitor", self)
            system_act.triggered.connect(self._show_system_monitor)
            system_act.setToolTip("Monitor system performance")
            view_menu.addAction(system_act)

            view_menu.addSeparator()

            picker_act = QAction("⚡ Strategy Picker", self)
            picker_act.triggered.connect(self._show_strategy_picker)
            picker_act.setToolTip("Select and configure strategies")
            view_menu.addAction(picker_act)

            editor_act = QAction("📋 Strategy Editor", self)
            editor_act.triggered.connect(self._open_strategy_editor)
            editor_act.setToolTip("Edit strategy parameters")
            view_menu.addAction(editor_act)

            view_menu.addSeparator()

            # ── Rule 13.5: Theme toggle ──────────────────────────────────────
            self._theme_action = QAction(
                "🌙  Dark Theme" if theme_manager.is_dark() else "☀️  Light Theme",
                self
            )
            self._theme_action.setCheckable(True)
            self._theme_action.setChecked(theme_manager.is_dark())
            self._theme_action.setShortcut("Ctrl+T")
            self._theme_action.setToolTip("Toggle between dark and light theme (Ctrl+T)")
            self._theme_action.triggered.connect(self._toggle_theme)
            view_menu.addAction(self._theme_action)

            # ── Rule 13.5: Density submenu ───────────────────────────────────
            density_menu = view_menu.addMenu("📏 Display Density")
            self._density_menu = density_menu

            # Clear any existing actions
            self._compact_menu_actions = []

            for label, value in [
                ("🔹 Compact", "compact"),
                ("🔸 Normal", "normal"),
                ("🔹 Relaxed", "relaxed")
            ]:
                act = QAction(label, self)
                act.setCheckable(True)
                act.setChecked(theme_manager.current_density == value)
                act.triggered.connect(lambda checked, v=value: self._set_density(v))
                act.setToolTip(f"Set display density to {value} mode")
                density_menu.addAction(act)
                self._compact_menu_actions.append((act, value))

            view_menu.addSeparator()

            close_all_act = QAction("❌ Close All Popups", self)
            close_all_act.triggered.connect(self._close_all_popups)
            close_all_act.setToolTip("Close all open popup windows")
            view_menu.addAction(close_all_act)

            # Settings menu
            settings_menu = menubar.addMenu("Settings")

            strategy_settings = QAction("⚙️ Strategy Settings", self)
            strategy_settings.triggered.connect(self._show_strategy_picker)
            strategy_settings.setToolTip("Configure strategy settings")
            settings_menu.addAction(strategy_settings)

            daily_settings = QAction("📅 Daily Trade Settings", self)
            daily_settings.triggered.connect(self._open_daily)
            daily_settings.setToolTip("Configure daily trade settings")
            settings_menu.addAction(daily_settings)

            pnl_settings = QAction("💰 Profit & Loss Settings", self)
            pnl_settings.triggered.connect(self._open_pnl)
            pnl_settings.setToolTip("Configure profit/loss settings")
            settings_menu.addAction(pnl_settings)

            brokerage_settings = QAction("🏦 Brokerage Settings", self)
            brokerage_settings.triggered.connect(self._open_brokerage)
            brokerage_settings.setToolTip("Configure broker settings")
            settings_menu.addAction(brokerage_settings)

            login_act = QAction(f"🔑 Manual Broker Login", self)
            login_act.triggered.connect(self._open_login)
            login_act.setToolTip("Manually log in to broker")
            settings_menu.addAction(login_act)

            mode_settings = QAction("🎮 Trading Mode Settings", self)
            mode_settings.triggered.connect(self._open_trading_mode)
            mode_settings.setToolTip("Configure trading mode (LIVE/PAPER/BACKTEST)")
            settings_menu.addAction(mode_settings)

            # Tools menu
            tools_menu = menubar.addMenu("Tools")

            backup_act = QAction("💾 Backup Configuration", self)
            backup_act.triggered.connect(self._backup_config)
            backup_act.setToolTip("Backup all configuration settings")
            tools_menu.addAction(backup_act)

            restore_act = QAction("📂 Restore Configuration", self)
            restore_act.triggered.connect(self._restore_config)
            restore_act.setToolTip("Restore configuration from backup")
            tools_menu.addAction(restore_act)

            tools_menu.addSeparator()

            clear_cache_act = QAction("🗑️ Clear Cache", self)
            clear_cache_act.triggered.connect(self._clear_cache)
            clear_cache_act.setToolTip("Clear application cache")
            tools_menu.addAction(clear_cache_act)

            # Backtest entry under Tools
            tools_menu.addSeparator()
            backtest_act = QAction("📊 Strategy Backtester", self)
            backtest_act.setShortcut("Ctrl+B")
            backtest_act.triggered.connect(self._open_backtest)
            backtest_act.setToolTip("Run strategy backtests (Ctrl+B)")
            tools_menu.addAction(backtest_act)

            # Help menu
            help_menu = menubar.addMenu("Help")

            about_act = QAction("ℹ️ About", self)
            about_act.triggered.connect(self._show_about)
            about_act.setToolTip("About this application")
            help_menu.addAction(about_act)

            docs_act = QAction("📚 Documentation", self)
            docs_act.triggered.connect(self._show_documentation)
            docs_act.setToolTip("View documentation")
            help_menu.addAction(docs_act)

            help_menu.addSeparator()

            check_updates_act = QAction("🔄 Check for Updates", self)
            check_updates_act.triggered.connect(self._check_updates)
            check_updates_act.setToolTip("Check for application updates")
            help_menu.addAction(check_updates_act)

        except Exception as e:
            logger.error(f"[TradingGUI._create_menu] Failed: {e}", exc_info=True)

    def _toggle_theme(self) -> None:
        """Rule 13.5: Toggle between dark and light themes"""
        try:
            # Skip if closing
            if self._closing:
                return

            theme_manager.toggle()
            theme_manager.save_preference()

            is_dark = theme_manager.is_dark()
            if self._theme_action:
                self._theme_action.setText("🌙  Dark Theme" if is_dark else "☀️  Light Theme")
                self._theme_action.setChecked(is_dark)

            logger.info(f"[TradingGUI._toggle_theme] Theme toggled to: {theme_manager.current_theme}")
        except Exception as e:
            logger.error(f"[TradingGUI._toggle_theme] Failed: {e}", exc_info=True)

    def _set_density(self, density: str) -> None:
        """Rule 13.5: Set display density"""
        try:
            # Skip if closing
            if self._closing:
                return

            theme_manager.set_density(density)
            theme_manager.save_preference()

            # Update menu check states
            for act, value in self._compact_menu_actions:
                if act:
                    act.setChecked(value == density)

            logger.info(f"[TradingGUI._set_density] Density set to: {density}")
        except Exception as e:
            logger.error(f"[TradingGUI._set_density] Failed: {e}", exc_info=True)

    # Popup window handlers
    def _show_log_popup(self):
        """Show log popup window with buffered logs"""
        try:
            # Skip if closing
            if self._closing:
                return

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
            # Skip if closing
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
            self.error_occurred.emit(f"Failed to show history popup: {e}")

    def _show_stats_popup(self):
        """Show statistics popup"""
        try:
            # Skip if closing
            if self._closing:
                return

            if self.trading_app:
                if not self.stats_popup:
                    # Use state_manager to get state for stats popup
                    self.stats_popup = StatsPopup(self)
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
            # Skip if closing
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
        """Show system monitor popup"""
        try:
            # Skip if closing
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
        """Show signal debug popup"""
        try:
            # Skip if closing
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
        """Close all popup windows"""
        try:
            # Skip if closing
            if self._closing:
                return

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
                    except Exception as e:
                        logger.debug(f"[TradingGUI._close_all_popups] Error closing popup: {e}")

            logger.debug("[TradingGUI._close_all_popups] All popups closed")
        except Exception as e:
            logger.error(f"[TradingGUI._close_all_popups] Failed: {e}", exc_info=True)

    def _open_trading_mode(self):
        """Open trading mode settings"""
        try:
            # Skip if closing
            if self._closing:
                return

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
            # Skip if closing
            if self._closing:
                return

            if not self.trading_mode_setting:
                return

            mode = self.trading_mode_setting.mode.value if self.trading_mode_setting else "algo"
            c = self._c
            ty = self._ty
            color = c.RED_BRIGHT if (
                    self.trading_mode_setting and self.trading_mode_setting.is_live()) else c.GREEN_BRIGHT

            if hasattr(self, 'mode_label') and self.mode_label is not None:
                self.mode_label.setText(f"Mode: {mode}")
                self.mode_label.setStyleSheet(f"""
                    color: {color}; 
                    font-weight: {ty.WEIGHT_BOLD};
                    background-color: transparent;
                """)
        except Exception as e:
            logger.error(f"[TradingGUI._update_mode_display] Failed: {e}", exc_info=True)

    def _open_daily(self):
        """Open daily trade settings"""
        try:
            # Skip if closing
            if self._closing:
                return

            dlg = DailyTradeSettingGUI(self, daily_setting=self.daily_setting,
                                       app=self.trading_app)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_daily] Failed: {e}", exc_info=True)

    def _open_pnl(self):
        """Open P&L settings"""
        try:
            # Skip if closing
            if self._closing:
                return

            dlg = ProfitStoplossSettingGUI(self, profit_stoploss_setting=self.profit_loss_setting,
                                           app=self.trading_app)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_pnl] Failed: {e}", exc_info=True)

    def _open_brokerage(self):
        """Open brokerage settings"""
        try:
            # Skip if closing
            if self._closing:
                return

            dlg = BrokerageSettingDialog(self.brokerage_setting, self)
            dlg.exec_()
        except Exception as e:
            logger.error(f"[TradingGUI._open_brokerage] Failed: {e}", exc_info=True)

    def _open_login_for_token_expiry(self, reason: str = None):
        """Open login popup for token expiry"""
        try:
            # Skip if closing
            if self._closing:
                return

            logger.info(
                f"[TradingGUI._open_login_for_token_expiry] Opening BrokerLoginPopup for Broker due to token expiry")
            reason_msg = reason or f"Your Broker access token has expired or is invalid."
            dlg = BrokerLoginPopup(self, self.brokerage_setting, reason=reason_msg)
            dlg.login_completed.connect(lambda _: self._reload_broker())
            result = dlg.exec_()
            if result == BrokerLoginPopup.Accepted:
                logger.info("[TradingGUI._open_login_for_token_expiry] Re-authentication completed successfully")
            else:
                logger.warning("[TradingGUI._open_login_for_token_expiry] Re-authentication dialog was cancelled")
                self.app_status_bar.update_status(
                    {'status': '⚠️ Token expired — login required to resume', 'error': True},
                    self.trading_mode, False
                )
        except Exception as e:
            logger.error(f"[TradingGUI._open_login_for_token_expiry] Failed: {e}", exc_info=True)

    def _open_login(self):
        """Open login popup"""
        try:
            # Skip if closing
            if self._closing:
                return

            dlg = BrokerLoginPopup(self, self.brokerage_setting)
            dlg.exec_()
            self._reload_broker()
        except Exception as e:
            logger.error(f"[TradingGUI._open_login] Failed: {e}", exc_info=True)

    def _reload_broker(self):
        """Reload broker after login"""
        try:
            # Skip if closing
            if self._closing:
                return

            self.trading_app = TradingApp(
                config=self.config,
                broker_setting=self.brokerage_setting,
                trading_mode_var=self.trading_mode_setting,
            )

            # Update candle store manager with new broker
            if hasattr(self.trading_app, 'broker') and self.trading_app.broker:
                from data.candle_store_manager import candle_store_manager
                candle_store_manager.initialize(self.trading_app.broker)

            # FEATURE 5: Reconnect trade closed callback
            if hasattr(self.trading_app, 'executor'):
                self.trading_app.executor.on_trade_closed_callback = self._on_trade_closed

            QMessageBox.information(self, "Reloaded", "Broker reloaded successfully.")
            logger.info("[TradingGUI._reload_broker] Broker reloaded successfully")
        except Exception as e:
            logger.error(f"[TradingGUI._reload_broker] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Reload Error", str(e))

    def _open_backtest(self):
        """Open the Strategy Backtester window"""
        try:
            # Skip if closing
            if self._closing:
                return

            from backtest.backtest_window import BacktestWindow
            if not hasattr(self, "_backtest_window") or self._backtest_window is None:
                self._backtest_window = BacktestWindow(
                    trading_app=self.trading_app,
                    strategy_manager=self.strategy_manager,
                    parent=self,
                )
            self._backtest_window.show()
            self._backtest_window.raise_()
            self._backtest_window.activateWindow()
        except Exception as e:
            logger.error(f"[TradingGUI._open_backtest] {e}", exc_info=True)
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Backtester Error", str(e))

    def _show_about(self):
        """Show about dialog"""
        try:
            # Skip if closing
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
        """Show documentation"""
        try:
            # Skip if closing
            if self._closing:
                return

            QMessageBox.information(self, "Documentation",
                                    "Documentation would open here.\n\n"
                                    "In a real application, this would open a PDF or web browser.")
        except Exception as e:
            logger.error(f"[TradingGUI._show_documentation] Failed: {e}", exc_info=True)

    def _check_updates(self):
        """Check for updates"""
        try:
            # Skip if closing
            if self._closing:
                return

            QMessageBox.information(self, "Check Updates",
                                    "This feature would check for updates.\n\n"
                                    "Currently running version 2.0")
        except Exception as e:
            logger.error(f"[TradingGUI._check_updates] Failed: {e}", exc_info=True)

    def _restart_application(self):
        """Restart the application"""
        try:
            # Skip if closing
            if self._closing:
                return

            reply = QMessageBox.question(
                self, "Restart",
                "Are you sure you want to restart the application?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                logger.info("[TradingGUI._restart_application] Restarting application...")
                # Close current instance
                self.close()
                # Start new instance
                QTimer.singleShot(1000, lambda: os.execl(sys.executable, sys.executable, *sys.argv))
        except Exception as e:
            logger.error(f"[TradingGUI._restart_application] Failed: {e}", exc_info=True)

    def _backup_config(self):
        """Backup configuration"""
        try:
            # Skip if closing
            if self._closing:
                return

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
            logger.info(f"[TradingGUI._backup_config] Configuration backed up to {backup_file}")

        except Exception as e:
            logger.error(f"[TradingGUI._backup_config] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Backup Failed", str(e))

    def _restore_config(self):
        """Restore configuration"""
        try:
            # Skip if closing
            if self._closing:
                return

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
                logger.info(f"[TradingGUI._restore_config] Configuration restored from {filename}")

        except Exception as e:
            logger.error(f"[TradingGUI._restore_config] Failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Restore Failed", str(e))

    def _clear_cache(self):
        """Clear application cache"""
        try:
            # Skip if closing
            if self._closing:
                return

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

                # Reset state manager for clean state
                state_manager.reset_for_backtest()

                QMessageBox.information(self, "Cache Cleared", "Cache has been cleared successfully.")
                logger.info("[TradingGUI._clear_cache] Cache cleared")

        except Exception as e:
            logger.error(f"[TradingGUI._clear_cache] Failed: {e}", exc_info=True)

    def _update_trade_history(self):
        """Refresh trade history table only if file changed"""
        try:
            # Skip if closing
            if self._closing:
                return

            today_file = f"logs/trades_{to_date_str(datetime.now())}.csv"

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
                logger.error(f"[TradingGUI._update_trade_history] Failed to check trade file mtime: {e}")

        except Exception as e:
            logger.error(f"[TradingGUI._update_trade_history] Failed: {e}", exc_info=True)

    def _show_strategy_picker(self):
        """Show strategy picker"""
        try:
            # Skip if closing
            if self._closing:
                return

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
            # Skip if closing
            if self._closing:
                return

            if not self.strategy_editor:
                self.strategy_editor = StrategyEditorWindow(
                    parent=self,
                )
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
            # Skip if closing
            if self._closing:
                return

            self.strategy_editor = None
        except Exception as e:
            logger.error(f"[TradingGUI._on_strategy_editor_closed] Failed: {e}", exc_info=True)

    def _on_strategy_changed(self, slug: str):
        """Handle strategy change"""
        try:
            # Skip if closing
            if self._closing:
                return

            self._apply_active_strategy()
            if self.strategy_picker and self.strategy_picker.isVisible():
                self.strategy_picker.refresh()
            self.strategy_changed.emit(slug)
        except Exception as e:
            logger.error(f"[TradingGUI._on_strategy_changed] Failed: {e}", exc_info=True)

    def _apply_active_strategy(self):
        """Apply the active strategy to the trading app"""
        try:
            # Skip if closing
            if self._closing:
                return

            if not self.strategy_manager:
                logger.warning("[TradingGUI._apply_active_strategy] No strategy manager available")
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
                    logger.warning(f"[TradingGUI._apply_active_strategy] Chart config refresh failed: {e}")

            logger.info(f"[TradingGUI._apply_active_strategy] Applied strategy: {name}")

        except Exception as e:
            logger.error(f"[TradingGUI._apply_active_strategy] Failed: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event - Rule 7"""
        try:
            if self._closing:
                event.accept()
                return

            self._closing = True
            logger.info("[TradingGUI.closeEvent] Application closing, starting cleanup...")

            # Stop timers
            for timer in [self.timer_fast, self.timer_chart, self.timer_app_status,
                          self.timer_connection_check, self.timer_market_status]:
                if timer is not None:
                    try:
                        timer.stop()
                    except Exception as e:
                        logger.warning(f"[TradingGUI.closeEvent] Timer stop error: {e}")

            # Close all popups
            self._close_all_popups()

            # Stop trading thread
            if self.app_running and self.trading_thread:
                logger.info("[TradingGUI.closeEvent] Stopping trading thread...")
                try:
                    self.trading_thread.request_stop()
                    if not self.trading_thread.wait(5000):
                        logger.warning("[TradingGUI.closeEvent] Trading thread did not stop gracefully, terminating")
                        self.trading_thread.terminate()
                except Exception as e:
                    logger.error(f"[TradingGUI.closeEvent] Thread cleanup error: {e}")

            # Cleanup trading app
            if self.trading_app and hasattr(self.trading_app, 'cleanup'):
                try:
                    self.trading_app.cleanup()
                except Exception as e:
                    logger.error(f"[TradingGUI.closeEvent] Trading app cleanup error: {e}")

            # FEATURE 5: Cleanup DailyPnLWidget
            if self.daily_pnl_widget and hasattr(self.daily_pnl_widget, 'cleanup'):
                try:
                    self.daily_pnl_widget.cleanup()
                except Exception as e:
                    logger.error(f"[TradingGUI.closeEvent] DailyPnLWidget cleanup error: {e}")

            # Reset state manager
            try:
                state_manager.reset_for_backtest()
            except Exception as e:
                logger.error(f"[TradingGUI.closeEvent] State manager reset error: {e}")

            # Remove log handler
            if self._log_handler:
                try:
                    root_logger = logging.getLogger()
                    root_logger.removeHandler(self._log_handler)
                except Exception as e:
                    logger.warning(f"[TradingGUI.closeEvent] Log handler removal error: {e}")

            logger.info("[TradingGUI.closeEvent] Cleanup completed, closing application")
            event.accept()

        except Exception as e:
            logger.error(f"[TradingGUI.closeEvent] Failed: {e}", exc_info=True)
            event.accept()

    # Rule 8: Cleanup method
    def cleanup(self):
        """Graceful cleanup of resources"""
        try:
            if self._closing:
                return

            self._closing = True
            logger.info("[TradingGUI.cleanup] Starting cleanup")

            # Stop timers
            for timer in [self.timer_fast, self.timer_chart, self.timer_app_status,
                          self.timer_connection_check, self.timer_market_status]:
                if timer is not None:
                    try:
                        timer.stop()
                    except Exception as e:
                        logger.warning(f"[TradingGUI.cleanup] Timer stop error: {e}")

            # Close popups
            self._close_all_popups()

            # Stop trading thread
            if self.trading_thread is not None:
                if self.trading_thread.isRunning():
                    try:
                        self.trading_thread.request_stop()
                        if not self.trading_thread.wait(10000):
                            logger.warning("[TradingGUI.cleanup] Trading thread timeout, forcing termination")
                            self.trading_thread.terminate()
                            self.trading_thread.wait(2000)
                    except Exception as e:
                        logger.error(f"[TradingGUI.cleanup] Thread cleanup error: {e}", exc_info=True)

            # FEATURE 5: Cleanup DailyPnLWidget
            if self.daily_pnl_widget and hasattr(self.daily_pnl_widget, 'cleanup'):
                try:
                    self.daily_pnl_widget.cleanup()
                except Exception as e:
                    logger.error(f"[TradingGUI.cleanup] DailyPnLWidget cleanup error: {e}")

            # Remove log handler
            if self._log_handler:
                try:
                    root_logger = logging.getLogger()
                    root_logger.removeHandler(self._log_handler)
                except Exception as e:
                    logger.warning(f"[TradingGUI.cleanup] Log handler removal error: {e}")

            # Nullify references
            self.trading_app = None
            self.trading_thread = None
            self.chart_widget = None
            self.status_panel = None
            self.app_status_bar = None

            logger.info("[TradingGUI.cleanup] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradingGUI.cleanup] Error: {e}", exc_info=True)