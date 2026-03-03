"""
stats_popup.py
==============
Comprehensive statistics dashboard with multiple tabs.
Single widget handling all stats-related functionality.

VISUAL ENHANCEMENT: Modern dark theme with cards, gradients, and responsive design.
UPDATED: Now uses state_manager for all data access.
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

import logging
import traceback
from typing import Optional, Dict, Any
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize, QEvent
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QPushButton, QLabel,
                             QTabWidget, QHBoxLayout, QWidget, QFrame,
                             QScrollArea, QGridLayout, QGroupBox, QProgressBar,
                             QSizePolicy)
from PyQt5.QtGui import QFont, QColor, QPalette

from data.trade_state_manager import state_manager

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class ThemedMixin:
    """Mixin class to provide theme token shortcuts."""

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing


class ModernCard(QFrame, ThemedMixin):
    """Custom card widget with hover effect"""
    def __init__(self, title="", parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setObjectName("modernCard")
            self.setFrameStyle(QFrame.NoFrame)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

            self.layout = QVBoxLayout(self)
            # Margins and spacing will be set in apply_theme

            if title:
                title_label = QLabel(title)
                title_label.setObjectName("cardTitle")
                title_label.setAlignment(Qt.AlignLeft)
                self.layout.addWidget(title_label)
                self.title_label = title_label
            else:
                self.title_label = None

            self.title_text = title
            self.apply_theme()

        except Exception as e:
            logger.error(f"[ModernCard.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self.title_label = None
        self.title_text = ""

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the card"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Update layout margins and spacing
            self.layout.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)
            self.layout.setSpacing(sp.GAP_XS)

            # Update stylesheet
            self.setStyleSheet(f"""
                QFrame#modernCard {{
                    background-color: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_LG}px;
                    padding: {sp.PAD_SM}px;
                    margin: {sp.PAD_XS}px;
                }}
                QFrame#modernCard:hover {{
                    border: {sp.SEPARATOR}px solid {c.BLUE};
                    background-color: {c.BG_HOVER};
                }}
                QLabel#cardTitle {{
                    color: {c.BLUE};
                    font-size: {ty.SIZE_BODY}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                    padding: {sp.PAD_XS}px 0px {sp.PAD_XS}px 0px;
                    border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
                }}
            """)

            if self.title_label and self.title_text:
                self.title_label.setText(self.title_text)

        except Exception as e:
            logger.error(f"[ModernCard.apply_theme] Failed: {e}", exc_info=True)


class StatsWidget(QWidget, ThemedMixin):
    """
    Main statistics widget that can be embedded in any parent.
    Contains all statistics tabs and functionality.
    """

    data_refreshed = pyqtSignal(dict)  # Emits snapshot data

    def __init__(self, parent=None, embedded=False):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            # Initialize attributes
            self._is_small_window = False
            self._embedded = embedded  # Whether this is embedded in another widget

            # Risk tab labels
            self.risk_labels = {}

            # MTF tab labels
            self.mtf_labels = {}

            # Signal tab labels
            self.conf_labels = {}
            self.conf_bars = {}
            self.conf_explanation = None

            # Advanced tab labels
            self.adv_labels = {}

            # Cache for snapshots
            self._last_snapshot = {}
            self._last_snapshot_time = None
            self._last_position_snapshot = {}
            self._snapshot_cache_duration = 0.1

            # Storage for labels and progress bars
            self._labels = {}
            self._progress_bars = {}

            # Setup UI
            self.setup_ui()

            # Apply theme
            self.apply_theme()

            # Install event filter for resize handling
            self.installEventFilter(self)

            # Initial refresh
            QTimer.singleShot(100, self.refresh)

            logger.info("StatsWidget initialized")

        except Exception as e:
            logger.critical(f"[StatsWidget.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._labels = {}
        self._progress_bars = {}
        self._is_small_window = False
        self._embedded = False
        self.risk_labels = {}
        self.mtf_labels = {}
        self.conf_labels = {}
        self.conf_bars = {}
        self.conf_explanation = None
        self.adv_labels = {}
        self._last_snapshot = {}
        self._last_snapshot_time = None
        self._last_position_snapshot = {}
        self._snapshot_cache_duration = 0.1
        self.time_label = None
        self.tab_widget = None
        self.time_timer = None
        self.pos_progress = None
        self.loss_progress = None
        self.trade_progress = None
        self.debug_scroll_layout = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the widget"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Update main stylesheet
            self.setStyleSheet(self._get_style_sheet())

            # Update header if present
            if not self._embedded and hasattr(self, 'time_label') and self.time_label:
                self.time_label.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_BODY}pt;")

            # Update all labels and progress bars will be updated in refresh()
            # as they need current values

            logger.debug("[StatsWidget.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[StatsWidget.apply_theme] Failed: {e}", exc_info=True)

    def _get_style_sheet(self) -> str:
        """Get themed stylesheet with tabs below the content"""
        c = self._c
        ty = self._ty
        sp = self._sp

        return f"""
            QWidget {{
                background-color: {c.BG_MAIN};
                color: {c.TEXT_MAIN};
                font-family: '{ty.FONT_UI}', 'Inter', -apple-system, sans-serif;
                font-size: {ty.SIZE_SM}pt;
            }}
            QTabWidget::pane {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                background: {c.BG_PANEL};
                margin-bottom: -1px;
            }}
            QTabBar::tab {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {c.BG_HOVER}, stop:1 {c.BG_PANEL});
                color: {c.TEXT_DIM};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-top: none;
                border-bottom-left-radius: {sp.RADIUS_MD}px;
                border-bottom-right-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                margin-right: {sp.GAP_XS}px;
                font-size: {ty.SIZE_SM}pt;
                font-weight: 500;
                min-width: 70px;
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {c.BLUE_DARK}, stop:1 {c.BLUE});
                color: {c.TEXT_INVERSE};
                border: {sp.SEPARATOR}px solid {c.BLUE};
                border-top: none;
                border-bottom: {sp.PAD_XS}px solid {c.BLUE};
            }}
            QTabBar::tab:hover:!selected {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {c.BORDER}, stop:1 {c.BG_HOVER});
                color: {c.TEXT_MAIN};
            }}
            QGroupBox {{
                background-color: {c.BG_PANEL};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                margin-top: {sp.PAD_SM}px;
                font-weight: 600;
                color: {c.TEXT_MAIN};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {sp.PAD_MD}px;
                padding: 0 {sp.PAD_SM}px 0 {sp.PAD_SM}px;
                color: {c.BLUE};
                font-size: {ty.SIZE_BODY}pt;
            }}
            QLabel {{
                color: {c.TEXT_DIM};
                font-size: {ty.SIZE_BODY}pt;
                padding: {sp.PAD_XS}px;
            }}
            QLabel#value {{
                color: {c.TEXT_MAIN};
                font-weight: 600;
            }}
            QLabel#positive {{
                color: {c.GREEN_BRIGHT};
                font-weight: 700;
            }}
            QLabel#negative {{
                color: {c.RED_BRIGHT};
                font-weight: 700;
            }}
            QLabel#warning {{
                color: {c.YELLOW};
                font-weight: 700;
            }}
            QLabel#header {{
                color: {c.BLUE};
                font-size: {ty.SIZE_LG}pt;
                font-weight: 600;
            }}
            QProgressBar {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
                background: {c.BG_PANEL};
                text-align: center;
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_XS}pt;
                min-height: {sp.PROGRESS_SM}px;
                max-height: {sp.PROGRESS_MD}px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c.BLUE}, stop:1 {c.BLUE});
                border-radius: {sp.RADIUS_SM}px;
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QFrame#separator {{
                background: {c.BORDER};
                max-height: {sp.SEPARATOR}px;
                min-height: {sp.SEPARATOR}px;
            }}
        """

    def eventFilter(self, obj, event):
        """Handle resize events"""
        if event.type() == QEvent.Resize:
            self._handle_resize(event.size().width())
        return super().eventFilter(obj, event)

    def _handle_resize(self, width):
        """Adjust UI for window size"""
        is_small = width < 600
        if is_small != self._is_small_window:
            self._is_small_window = is_small
            if is_small and self.tab_widget:
                self.tab_widget.setStyleSheet(f"""
                    QTabBar::tab {{
                        font-size: {self._ty.SIZE_XS}pt;
                        padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                        min-width: 50px;
                    }}
                """)
            elif self.tab_widget:
                self.tab_widget.setStyleSheet("")

    def _update_time(self):
        """Update the time label"""
        if hasattr(self, 'time_label') and self.time_label:
            current_time = datetime.now().strftime("%H:%M:%S")
            self.time_label.setText(f"🕒 {current_time}")

    def _add_label(self, key: str, label: QLabel):
        """Store label reference"""
        self._labels[key] = label

    def _add_progress(self, key: str, progress: QProgressBar):
        """Store progress bar reference"""
        self._progress_bars[key] = progress

    def _create_metric_row(self, layout, row, label_text, value_key, unit="", label_dict=None):
        """Helper to create a styled metric row"""
        if label_dict is None:
            label_dict = self._labels

        label = QLabel(label_text)
        label.setAlignment(Qt.AlignLeft)
        label.setMinimumWidth(80)

        value_label = QLabel("--")
        value_label.setObjectName("value")
        value_label.setAlignment(Qt.AlignRight)
        value_label.setMinimumWidth(60)

        if unit:
            unit_label = QLabel(unit)
            unit_label.setStyleSheet(f"color: {self._c.TEXT_DIM};")
            unit_label.setAlignment(Qt.AlignLeft)
            unit_label.setMaximumWidth(20)

            h_layout = QHBoxLayout()
            h_layout.setSpacing(self._sp.GAP_XS)
            h_layout.addWidget(value_label)
            h_layout.addWidget(unit_label)

            layout.addWidget(label, row, 0)
            layout.addLayout(h_layout, row, 1)
        else:
            layout.addWidget(label, row, 0)
            layout.addWidget(value_label, row, 1)

        if value_key:
            label_dict[value_key] = value_label
            self._add_label(value_key, value_label)

        return value_label

    def setup_ui(self):
        """Initialize the UI with all tabs"""
        sp = self._sp

        layout = QVBoxLayout(self)
        layout.setContentsMargins(sp.PAD_XS, sp.PAD_XS, sp.PAD_XS, sp.PAD_XS)
        layout.setSpacing(sp.GAP_XS)

        # Optional header (hide when embedded)
        if not self._embedded:
            header_layout = QHBoxLayout()
            header_layout.setContentsMargins(sp.PAD_XS, 0, sp.PAD_XS, sp.PAD_XS)

            title_label = QLabel("📊 TRADING DASHBOARD")
            title_label.setObjectName("header")
            title_label.setStyleSheet(f"color: {self._c.BLUE};")

            self.time_label = QLabel()
            self.time_label.setAlignment(Qt.AlignRight)

            header_layout.addWidget(title_label)
            header_layout.addStretch()
            header_layout.addWidget(self.time_label)

            layout.addLayout(header_layout)

            # Separator
            separator = QFrame()
            separator.setObjectName("separator")
            separator.setFrameShape(QFrame.HLine)
            separator.setStyleSheet(f"background: {self._c.BORDER}; max-height: {sp.SEPARATOR}px; min-height: {sp.SEPARATOR}px;")
            layout.addWidget(separator)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setUsesScrollButtons(True)

        # Add all tabs
        self.tab_widget.addTab(self.create_position_tab(), "📊 POSITION")
        self.tab_widget.addTab(self.create_performance_tab(), "📈 PERFORMANCE")
        self.tab_widget.addTab(self.create_risk_tab(), "⚠️ RISK")
        self.tab_widget.addTab(self.create_market_tab(), "📉 MARKET")
        self.tab_widget.addTab(self.create_mtf_tab(), "📊 MTF")
        self.tab_widget.addTab(self.create_signal_tab(), "🎯 SIGNAL")
        self.tab_widget.addTab(self.create_advanced_tab(), "📊 ADVANCED")
        self.tab_widget.addTab(self.create_debug_tab(), "⚙️ DEBUG")

        layout.addWidget(self.tab_widget, 1)

        # Time update timer (only if not embedded)
        if not self._embedded:
            self.time_timer = QTimer(self)
            self.time_timer.timeout.connect(self._update_time)
            self.time_timer.start(1000)

    def create_position_tab(self):
        """Position details tab"""
        sp = self._sp

        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(sp.GAP_SM)
        main_layout.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)

        cards_layout = QVBoxLayout()
        cards_layout.setSpacing(sp.GAP_SM)

        # Card 1: Position Status
        status_card = ModernCard("POSITION STATUS")
        status_layout = QGridLayout()
        status_layout.setVerticalSpacing(sp.GAP_SM)
        status_layout.setHorizontalSpacing(sp.PAD_MD)

        self._create_metric_row(status_layout, 0, "Position:", "current_position")
        self._create_metric_row(status_layout, 1, "Confirmed:", "current_trade_confirmed")
        self._create_metric_row(status_layout, 2, "Pending:", "order_pending")
        self._create_metric_row(status_layout, 3, "Size:", "positions_hold")

        status_card.layout.addLayout(status_layout)
        cards_layout.addWidget(status_card)

        # Card 2: Price Levels
        price_card = ModernCard("PRICE LEVELS")
        price_layout = QGridLayout()
        price_layout.setVerticalSpacing(sp.GAP_SM)
        price_layout.setHorizontalSpacing(sp.PAD_MD)

        self._create_metric_row(price_layout, 0, "Entry:", "current_buy_price", "₹")
        self._create_metric_row(price_layout, 1, "Current:", "current_price", "₹")
        self._create_metric_row(price_layout, 2, "High:", "highest_current_price", "₹")

        price_card.layout.addLayout(price_layout)
        cards_layout.addWidget(price_card)

        # Card 3: P&L
        pnl_card = ModernCard("PROFIT & LOSS")
        pnl_layout = QGridLayout()
        pnl_layout.setVerticalSpacing(sp.GAP_SM)
        pnl_layout.setHorizontalSpacing(sp.PAD_MD)

        self._create_metric_row(pnl_layout, 0, "P&L:", "current_pnl", "₹")
        self._create_metric_row(pnl_layout, 1, "Change %:", "percentage_change", "%")
        self._create_metric_row(pnl_layout, 2, "Exit:", "reason_to_exit")

        pnl_card.layout.addLayout(pnl_layout)
        cards_layout.addWidget(pnl_card)

        main_layout.addLayout(cards_layout)
        main_layout.addStretch()

        scroll.setWidget(container)

        tab_layout = QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        return widget

    def create_performance_tab(self):
        """Performance metrics tab"""
        sp = self._sp

        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(sp.GAP_SM)
        main_layout.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)

        cards_layout = QVBoxLayout()
        cards_layout.setSpacing(sp.GAP_SM)

        # Card 1: Account Overview
        account_card = ModernCard("ACCOUNT OVERVIEW")
        account_layout = QGridLayout()
        account_layout.setVerticalSpacing(sp.GAP_SM)
        account_layout.setHorizontalSpacing(sp.PAD_MD)

        self._create_metric_row(account_layout, 0, "Balance:", "account_balance", "₹")
        self._create_metric_row(account_layout, 1, "Lot Size:", "lot_size")
        self._create_metric_row(account_layout, 2, "Reserve:", "capital_reserve", "₹")
        self._create_metric_row(account_layout, 3, "Max Opt:", "max_num_of_option")

        account_card.layout.addLayout(account_layout)
        cards_layout.addWidget(account_card)

        # Card 2: Trade Timing
        timing_card = ModernCard("TRADE TIMING")
        timing_layout = QGridLayout()
        timing_layout.setVerticalSpacing(sp.GAP_SM)
        timing_layout.setHorizontalSpacing(sp.PAD_MD)

        self._create_metric_row(timing_layout, 0, "Started:", "current_trade_started_time")
        self._create_metric_row(timing_layout, 1, "Duration:", "trade_duration")

        timing_card.layout.addLayout(timing_layout)
        cards_layout.addWidget(timing_card)

        # Card 3: Position Utilization
        progress_card = ModernCard("POSITION UTILIZATION")
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(sp.GAP_XS)

        pos_label = QLabel("Position Size")
        pos_label.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")

        self.pos_progress = QProgressBar()
        self.pos_progress.setRange(0, 100)
        self.pos_progress.setValue(0)
        self.pos_progress.setFormat("%v%")
        self.pos_progress.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._add_progress("position_progress", self.pos_progress)

        progress_layout.addWidget(pos_label)
        progress_layout.addWidget(self.pos_progress)

        progress_card.layout.addLayout(progress_layout)
        cards_layout.addWidget(progress_card)

        main_layout.addLayout(cards_layout)
        main_layout.addStretch()

        scroll.setWidget(container)

        tab_layout = QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        return widget

    def create_risk_tab(self):
        """Risk management tab"""
        sp = self._sp

        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(sp.GAP_SM)
        main_layout.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)

        # Card 1: Daily Risk Limits
        limits_card = ModernCard("DAILY RISK LIMITS")
        limits_layout = QGridLayout()
        limits_layout.setVerticalSpacing(sp.GAP_SM)
        limits_layout.setHorizontalSpacing(sp.PAD_MD)

        # Max daily loss
        limits_layout.addWidget(QLabel("Max Daily Loss:"), 0, 0)
        max_loss_label = QLabel("₹-5,000")
        max_loss_label.setObjectName("value")
        limits_layout.addWidget(max_loss_label, 0, 1)
        self.risk_labels['max_loss'] = max_loss_label
        self._add_label("risk_max_loss", max_loss_label)

        # Current P&L
        limits_layout.addWidget(QLabel("Current P&L:"), 1, 0)
        pnl_label = QLabel("₹0.00")
        pnl_label.setObjectName("value")
        limits_layout.addWidget(pnl_label, 1, 1)
        self.risk_labels['current_pnl'] = pnl_label
        self._add_label("risk_current_pnl", pnl_label)

        # Loss remaining
        limits_layout.addWidget(QLabel("Loss Remaining:"), 2, 0)
        remaining_label = QLabel("₹5,000")
        remaining_label.setObjectName("value")
        limits_layout.addWidget(remaining_label, 2, 1)
        self.risk_labels['loss_remaining'] = remaining_label
        self._add_label("risk_loss_remaining", remaining_label)

        # Loss utilization bar
        limits_layout.addWidget(QLabel("Loss Used:"), 3, 0)
        self.loss_progress = QProgressBar()
        self.loss_progress.setRange(0, 100)
        self.loss_progress.setValue(0)
        self.loss_progress.setFormat("%v%")
        limits_layout.addWidget(self.loss_progress, 3, 1)
        self._add_progress("loss_progress", self.loss_progress)

        limits_card.layout.addLayout(limits_layout)
        main_layout.addWidget(limits_card)

        # Card 2: Trade Limits
        trade_card = ModernCard("TRADE LIMITS")
        trade_layout = QGridLayout()
        trade_layout.setVerticalSpacing(sp.GAP_SM)
        trade_layout.setHorizontalSpacing(sp.PAD_MD)

        # Max trades
        trade_layout.addWidget(QLabel("Max Trades/Day:"), 0, 0)
        max_trades_label = QLabel("10")
        max_trades_label.setObjectName("value")
        trade_layout.addWidget(max_trades_label, 0, 1)
        self.risk_labels['max_trades'] = max_trades_label
        self._add_label("risk_max_trades", max_trades_label)

        # Trades today
        trade_layout.addWidget(QLabel("Trades Today:"), 1, 0)
        trades_today_label = QLabel("0")
        trades_today_label.setObjectName("value")
        trade_layout.addWidget(trades_today_label, 1, 1)
        self.risk_labels['trades_today'] = trades_today_label
        self._add_label("risk_trades_today", trades_today_label)

        # Trades remaining
        trade_layout.addWidget(QLabel("Trades Remaining:"), 2, 0)
        trades_rem_label = QLabel("10")
        trades_rem_label.setObjectName("value")
        trade_layout.addWidget(trades_rem_label, 2, 1)
        self.risk_labels['trades_remaining'] = trades_rem_label
        self._add_label("risk_trades_remaining", trades_rem_label)

        # Trade utilization bar
        trade_layout.addWidget(QLabel("Trade Usage:"), 3, 0)
        self.trade_progress = QProgressBar()
        self.trade_progress.setRange(0, 100)
        self.trade_progress.setValue(0)
        self.trade_progress.setFormat("%v%")
        trade_layout.addWidget(self.trade_progress, 3, 1)
        self._add_progress("trade_progress", self.trade_progress)

        # Risk blocked status
        trade_layout.addWidget(QLabel("Risk Blocked:"), 4, 0)
        blocked_label = QLabel("No")
        blocked_label.setObjectName("positive")
        trade_layout.addWidget(blocked_label, 4, 1)
        self.risk_labels['risk_blocked'] = blocked_label
        self._add_label("risk_blocked", blocked_label)

        trade_card.layout.addLayout(trade_layout)
        main_layout.addWidget(trade_card)

        # Card 3: Stop Loss & Take Profit
        sltp_card = ModernCard("STOP LOSS & TAKE PROFIT")
        sltp_layout = QGridLayout()
        sltp_layout.setVerticalSpacing(sp.GAP_SM)
        sltp_layout.setHorizontalSpacing(sp.PAD_MD)

        # Stop Loss
        sltp_layout.addWidget(QLabel("Stop Loss:"), 0, 0)
        sl_label = QLabel("None")
        sl_label.setObjectName("negative")
        sltp_layout.addWidget(sl_label, 0, 1)
        self.risk_labels['stop_loss'] = sl_label
        self._add_label("stop_loss", sl_label)

        # Stop Loss %
        sltp_layout.addWidget(QLabel("SL %:"), 1, 0)
        sl_pct_label = QLabel("0.0%")
        sl_pct_label.setObjectName("negative")
        sltp_layout.addWidget(sl_pct_label, 1, 1)
        self.risk_labels['stoploss_percentage'] = sl_pct_label
        self._add_label("stoploss_percentage", sl_pct_label)

        # Take Profit
        sltp_layout.addWidget(QLabel("Take Profit:"), 2, 0)
        tp_label = QLabel("None")
        tp_label.setObjectName("positive")
        sltp_layout.addWidget(tp_label, 2, 1)
        self.risk_labels['tp_point'] = tp_label
        self._add_label("tp_point", tp_label)

        # TP %
        sltp_layout.addWidget(QLabel("TP %:"), 3, 0)
        tp_pct_label = QLabel("0.0%")
        tp_pct_label.setObjectName("positive")
        sltp_layout.addWidget(tp_pct_label, 3, 1)
        self.risk_labels['tp_percentage'] = tp_pct_label
        self._add_label("tp_percentage", tp_pct_label)

        sltp_card.layout.addLayout(sltp_layout)
        main_layout.addWidget(sltp_card)

        main_layout.addStretch()
        scroll.setWidget(container)

        tab_layout = QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        return widget

    def create_market_tab(self):
        """Market data tab"""
        sp = self._sp

        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(sp.GAP_SM)
        main_layout.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)

        cards_layout = QVBoxLayout()
        cards_layout.setSpacing(sp.GAP_SM)

        # Card 1: Instruments
        inst_card = ModernCard("INSTRUMENTS")
        inst_layout = QGridLayout()
        inst_layout.setVerticalSpacing(sp.GAP_SM)
        inst_layout.setHorizontalSpacing(sp.PAD_MD)

        self._create_metric_row(inst_layout, 0, "Derivative:", "derivative")
        self._create_metric_row(inst_layout, 1, "Call:", "call_option")
        self._create_metric_row(inst_layout, 2, "Put:", "put_option")
        self._create_metric_row(inst_layout, 3, "Expiry:", "expiry")

        inst_card.layout.addLayout(inst_layout)
        cards_layout.addWidget(inst_card)

        # Card 2: Prices
        price_card = ModernCard("PRICES")
        price_layout = QGridLayout()
        price_layout.setVerticalSpacing(sp.GAP_SM)
        price_layout.setHorizontalSpacing(sp.PAD_MD)

        self._create_metric_row(price_layout, 0, "Derivative:", "derivative_current_price", "₹")
        self._create_metric_row(price_layout, 1, "Call Close:", "call_current_close", "₹")
        self._create_metric_row(price_layout, 2, "Put Close:", "put_current_close", "₹")

        price_card.layout.addLayout(price_layout)
        cards_layout.addWidget(price_card)

        # Card 3: Indicators
        ind_card = ModernCard("INDICATORS")
        ind_layout = QGridLayout()
        ind_layout.setVerticalSpacing(sp.GAP_SM)
        ind_layout.setHorizontalSpacing(sp.PAD_MD)

        self._create_metric_row(ind_layout, 0, "PCR:", "current_pcr")
        self._create_metric_row(ind_layout, 1, "PCR Vol:", "current_pcr_vol")
        self._create_metric_row(ind_layout, 2, "Trend:", "market_trend")

        ind_card.layout.addLayout(ind_layout)
        cards_layout.addWidget(ind_card)

        main_layout.addLayout(cards_layout)
        main_layout.addStretch()

        scroll.setWidget(container)

        tab_layout = QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        return widget

    def create_mtf_tab(self):
        """Multi-timeframe filter tab"""
        sp = self._sp

        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(sp.GAP_SM)
        main_layout.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)

        # Card 1: MTF Status
        status_card = ModernCard("MTF FILTER STATUS")
        status_layout = QGridLayout()
        status_layout.setVerticalSpacing(sp.GAP_SM)
        status_layout.setHorizontalSpacing(sp.PAD_MD)

        status_layout.addWidget(QLabel("Enabled:"), 0, 0)
        enabled_label = QLabel("No")
        enabled_label.setObjectName("value")
        status_layout.addWidget(enabled_label, 0, 1)
        self.mtf_labels['enabled'] = enabled_label
        self._add_label("mtf_enabled", enabled_label)

        status_layout.addWidget(QLabel("Signal:"), 1, 0)
        signal_label = QLabel("WAIT")
        signal_label.setObjectName("value")
        status_layout.addWidget(signal_label, 1, 1)
        self.mtf_labels['signal'] = signal_label
        self._add_label("option_signal", signal_label)

        status_card.layout.addLayout(status_layout)
        main_layout.addWidget(status_card)

        # Card 2: Timeframe Analysis
        tf_card = ModernCard("TIMEFRAME ANALYSIS")
        tf_layout = QGridLayout()
        tf_layout.setVerticalSpacing(sp.GAP_MD)
        tf_layout.setHorizontalSpacing(sp.PAD_XL)

        timeframes = [
            ("1 MINUTE", "1m", "⚡"),
            ("5 MINUTES", "5m", "⏱️"),
            ("15 MINUTES", "15m", "📊")
        ]

        for i, (label, key, icon) in enumerate(timeframes):
            tf_layout.addWidget(QLabel(f"{icon} {label}:"), i, 0)
            dir_label = QLabel("NEUTRAL")
            dir_label.setObjectName("value")
            dir_label.setAlignment(Qt.AlignCenter)
            dir_label.setMinimumWidth(80)
            tf_layout.addWidget(dir_label, i, 1)
            self.mtf_labels[key] = dir_label
            self._add_label(f"mtf_{key}", dir_label)

        tf_layout.addWidget(QLabel("✓ Agreement:"), 3, 0)
        agree_label = QLabel("0/3")
        agree_label.setObjectName("value")
        agree_label.setAlignment(Qt.AlignCenter)
        tf_layout.addWidget(agree_label, 3, 1)
        self.mtf_labels['agreement'] = agree_label
        self._add_label("mtf_agreement", agree_label)

        tf_card.layout.addLayout(tf_layout)
        main_layout.addWidget(tf_card)

        # Card 3: Last Decision
        decision_card = ModernCard("LATEST DECISION")
        decision_layout = QVBoxLayout()

        self.mtf_labels['decision'] = QLabel("No MTF evaluation yet")
        self.mtf_labels['decision'].setWordWrap(True)
        self._add_label("mtf_summary", self.mtf_labels['decision'])

        decision_layout.addWidget(self.mtf_labels['decision'])
        decision_card.layout.addLayout(decision_layout)
        main_layout.addWidget(decision_card)

        main_layout.addStretch()
        scroll.setWidget(container)

        tab_layout = QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        return widget

    def create_signal_tab(self):
        """Signal confidence tab"""
        sp = self._sp
        c = self._c
        ty = self._ty

        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(sp.GAP_SM)
        main_layout.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)

        # Signal cards
        signal_groups = [
            ("BUY CALL", "BUY_CALL", "📈"),
            ("BUY PUT", "BUY_PUT", "📉"),
            ("EXIT CALL", "EXIT_CALL", "🚪"),
            ("EXIT PUT", "EXIT_PUT", "🚪"),
            ("HOLD", "HOLD", "⏸️")
        ]

        for display_name, signal_key, icon in signal_groups:
            signal_card = ModernCard(f"{icon} {display_name}")
            signal_layout = QVBoxLayout()
            signal_layout.setSpacing(sp.GAP_SM)

            # Confidence bar
            bar_layout = QHBoxLayout()
            bar_label = QLabel("Confidence:")
            bar_label.setStyleSheet(f"color: {c.TEXT_DIM};")

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setFormat("%p%")
            bar.setMinimumHeight(sp.PROGRESS_MD)

            bar_layout.addWidget(bar_label)
            bar_layout.addWidget(bar)

            signal_layout.addLayout(bar_layout)

            # Threshold indicator
            threshold_layout = QHBoxLayout()
            threshold_label = QLabel("Threshold:")
            threshold_value = QLabel("60%")
            threshold_value.setObjectName("value")

            threshold_layout.addWidget(threshold_label)
            threshold_layout.addWidget(threshold_value)
            threshold_layout.addStretch()

            signal_layout.addLayout(threshold_layout)

            signal_card.layout.addLayout(signal_layout)
            main_layout.addWidget(signal_card)

            self.conf_bars[signal_key] = bar
            self.conf_labels[signal_key] = threshold_value

        # Explanation card
        exp_card = ModernCard("📝 SIGNAL EXPLANATION")
        exp_layout = QVBoxLayout()

        self.conf_explanation = QLabel("No signal evaluation yet")
        self.conf_explanation.setWordWrap(True)
        self._add_label("signal_explanation", self.conf_explanation)

        exp_layout.addWidget(self.conf_explanation)
        exp_card.layout.addLayout(exp_layout)
        main_layout.addWidget(exp_card)

        main_layout.addStretch()
        scroll.setWidget(container)

        tab_layout = QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        return widget

    def create_advanced_tab(self):
        """Advanced statistics tab"""
        sp = self._sp

        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(sp.GAP_SM)
        main_layout.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)

        # Card 1: Trading Metrics
        metrics_card = ModernCard("📊 TRADING METRICS")
        metrics_layout = QGridLayout()
        metrics_layout.setVerticalSpacing(sp.GAP_SM)
        metrics_layout.setHorizontalSpacing(sp.PAD_MD)

        metrics = [
            ("Avg Win:", "avg_win", "₹0.00"),
            ("Avg Loss:", "avg_loss", "₹0.00"),
            ("Largest Win:", "max_win", "₹0.00"),
            ("Largest Loss:", "max_loss", "₹0.00"),
            ("Win/Loss Ratio:", "win_loss_ratio", "0.00"),
            ("Profit Factor:", "profit_factor", "0.00"),
            ("Sharpe Ratio:", "sharpe", "0.00"),
            ("Max Drawdown:", "max_dd", "0%")
        ]

        for i, (label, key, default) in enumerate(metrics):
            row = i // 2
            col = (i % 2) * 2

            metrics_layout.addWidget(QLabel(label), row, col)
            value_label = QLabel(default)
            value_label.setObjectName("value")
            metrics_layout.addWidget(value_label, row, col + 1)
            self.adv_labels[key] = value_label
            self._add_label(f"adv_{key}", value_label)

        metrics_card.layout.addLayout(metrics_layout)
        main_layout.addWidget(metrics_card)

        # Card 2: Session Stats
        session_card = ModernCard("⏰ SESSION STATISTICS")
        session_layout = QGridLayout()
        session_layout.setVerticalSpacing(sp.GAP_SM)
        session_layout.setHorizontalSpacing(sp.PAD_MD)

        session_stats = [
            ("Trading Since:", "session_start", "--:--"),
            ("Active Time:", "active_time", "0h 0m"),
            ("Trades/Hour:", "trades_per_hour", "0.0"),
            ("Best Hour:", "best_hour", "--:--"),
            ("Worst Hour:", "worst_hour", "--:--"),
        ]

        for i, (label, key, default) in enumerate(session_stats):
            session_layout.addWidget(QLabel(label), i, 0)
            value_label = QLabel(default)
            value_label.setObjectName("value")
            session_layout.addWidget(value_label, i, 1)
            self.adv_labels[key] = value_label
            self._add_label(f"adv_{key}", value_label)

        session_card.layout.addLayout(session_layout)
        main_layout.addWidget(session_card)

        main_layout.addStretch()
        scroll.setWidget(container)

        tab_layout = QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        return widget

    def create_debug_tab(self):
        """Debug information tab"""
        c = self._c
        ty = self._ty

        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS)

        header_label = QLabel("🔧 DEBUG INFORMATION")
        header_label.setStyleSheet(f"""
            color: {c.BLUE};
            font-size: {ty.SIZE_BODY}pt;
            font-weight: {ty.WEIGHT_BOLD};
            padding: {self._sp.PAD_XS}px;
        """)
        main_layout.addWidget(header_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(self._sp.GAP_XS)
        scroll_layout.setContentsMargins(self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # Store for updates
        self.debug_scroll_layout = scroll_layout

        return widget

    def _update_debug_tab(self, snapshot):
        """Update debug tab with current snapshot"""
        if not hasattr(self, 'debug_scroll_layout') or not self.debug_scroll_layout:
            return

        c = self._c

        # Clear existing
        while self.debug_scroll_layout.count():
            item = self.debug_scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new data
        for key, value in sorted(snapshot.items()):
            if value is not None and not key.endswith('_df'):
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS)
                row_layout.setSpacing(self._sp.GAP_XS)

                key_label = QLabel(f"{key}:")
                key_label.setStyleSheet(f"color: {c.TEXT_DIM}; min-width: 150px;")
                key_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)

                value_str = str(value)
                if len(value_str) > 50:
                    value_str = value_str[:50] + "..."

                val_label = QLabel(value_str)
                val_label.setStyleSheet(f"color: {c.TEXT_MAIN};")
                val_label.setWordWrap(True)
                val_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

                row_layout.addWidget(key_label)
                row_layout.addWidget(val_label, 1)

                self.debug_scroll_layout.addWidget(row_widget)

    def _get_cached_snapshot(self) -> Dict[str, Any]:
        """Get cached snapshot"""
        now = datetime.now()
        if (self._last_snapshot_time is None or
            (now - self._last_snapshot_time).total_seconds() > self._snapshot_cache_duration):
            self._last_snapshot = state_manager.get_snapshot()
            self._last_position_snapshot = state_manager.get_position_snapshot()
            self._last_snapshot_time = now
        return self._last_snapshot

    def refresh(self):
        """Refresh all statistics"""
        try:
            snapshot = self._get_cached_snapshot()
            pos_snapshot = self._last_position_snapshot

            # Update position tab labels
            self._update_position_labels(pos_snapshot, snapshot)

            # Update performance tab
            self._update_performance_labels(snapshot, pos_snapshot)

            # Update risk tab
            self._update_risk_labels(snapshot, pos_snapshot)

            # Update market tab
            self._update_market_labels(snapshot)

            # Update MTF tab
            self._update_mtf_labels(snapshot, pos_snapshot)

            # Update signal tab
            self._update_signal_labels(snapshot, pos_snapshot)

            # Update advanced tab
            self._update_advanced_labels(snapshot, pos_snapshot)

            # Update debug tab
            self._update_debug_tab(snapshot)

            # Update progress bars
            self._update_progress_bars(pos_snapshot)

            # Emit signal
            self.data_refreshed.emit(snapshot)

        except Exception as e:
            logger.error(f"[StatsWidget.refresh] Failed: {e}", exc_info=True)

    def _update_position_labels(self, pos_snap, snap):
        """Update position tab labels"""
        try:
            c = self._c

            pos = pos_snap.get('current_position', 'None')
            self._update_label("current_position", str(pos) if pos else "None")

            confirmed = pos_snap.get('current_trade_confirmed', False)
            self._update_label("current_trade_confirmed", "✓" if confirmed else "✗",
                              "positive" if confirmed else "value")

            pending = pos_snap.get('order_pending', False)
            self._update_label("order_pending", "⏳" if pending else "✗",
                              "warning" if pending else "value")

            positions = pos_snap.get('positions_hold', 0)
            self._update_label("positions_hold", str(positions))

            entry = pos_snap.get('current_buy_price')
            self._update_label("current_buy_price", f"{entry:.2f}" if entry else "--")

            current = pos_snap.get('current_price')
            self._update_label("current_price", f"{current:.2f}" if current else "--")

            high = pos_snap.get('highest_current_price')
            self._update_label("highest_current_price", f"{high:.2f}" if high else "--")

            pnl = pos_snap.get('current_pnl')
            if pnl is not None:
                pnl_str = f"{pnl:.2f}"
                pnl_color = "positive" if pnl > 0 else "negative" if pnl < 0 else "value"
                self._update_label("current_pnl", pnl_str, pnl_color)
            else:
                self._update_label("current_pnl", "--")

            pct = pos_snap.get('percentage_change')
            if pct is not None:
                pct_str = f"{pct:.2f}"
                pct_color = "positive" if pct > 0 else "negative" if pct < 0 else "value"
                self._update_label("percentage_change", pct_str, pct_color)
            else:
                self._update_label("percentage_change", "--")

            reason = pos_snap.get('reason_to_exit', 'None')
            self._update_label("reason_to_exit", str(reason) if reason else "None")

        except Exception as e:
            logger.error(f"Failed to update position labels: {e}")

    def _update_performance_labels(self, snap, pos_snap):
        """Update performance tab labels"""
        try:
            balance = snap.get('account_balance', 0)
            self._update_label("account_balance", f"{balance:,.2f}")

            lot_size = snap.get('lot_size', 0)
            self._update_label("lot_size", str(lot_size))

            reserve = snap.get('capital_reserve', 0)
            self._update_label("capital_reserve", f"{reserve:,.2f}")

            max_options = snap.get('max_num_of_option', 0)
            self._update_label("max_num_of_option", str(max_options))

            start_time = snap.get('current_trade_started_time')
            if start_time:
                if isinstance(start_time, datetime):
                    self._update_label("current_trade_started_time", start_time.strftime("%H:%M"))
                else:
                    self._update_label("current_trade_started_time", str(start_time))

                if pos_snap.get('current_price'):
                    duration = datetime.now() - start_time
                    hours = duration.seconds // 3600
                    minutes = (duration.seconds % 3600) // 60

                    if hours > 0:
                        duration_str = f"{hours:02d}:{minutes:02d}"
                    else:
                        duration_str = f"{minutes:02d}m"

                    self._update_label("trade_duration", duration_str)
            else:
                self._update_label("current_trade_started_time", "--:--")
                self._update_label("trade_duration", "0m")

        except Exception as e:
            logger.error(f"Failed to update performance labels: {e}")

    def _update_risk_labels(self, snap, pos_snap):
        """Update risk tab labels"""
        try:
            c = self._c

            if not self.risk_labels:
                return

            pnl = pos_snap.get('current_pnl') or 0.0
            max_loss = snap.get('max_daily_loss', -5000.0)
            max_trades = snap.get('max_trades_per_day', 10)

            trades_today = 1 if pos_snap.get('current_position') is not None else 0

            loss_remaining = max(0.0, abs(max_loss) - abs(pnl)) if pnl < 0 else abs(max_loss)
            loss_used_pct = min(100, int((abs(pnl) / abs(max_loss)) * 100)) if pnl < 0 else 0
            trades_remaining = max(0, max_trades - trades_today)
            trade_used_pct = int((trades_today / max_trades) * 100)

            # Update progress bars
            if self.loss_progress:
                self.loss_progress.setValue(loss_used_pct)
                if loss_used_pct > 80:
                    self.loss_progress.setStyleSheet(f"""
                        QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 {c.RED}, stop:1 {c.RED_BRIGHT}); border-radius: {self._sp.RADIUS_SM}px; }}
                    """)
                elif loss_used_pct > 50:
                    self.loss_progress.setStyleSheet(f"""
                        QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 {c.YELLOW}, stop:1 {c.ORANGE}); border-radius: {self._sp.RADIUS_SM}px; }}
                    """)
                else:
                    self.loss_progress.setStyleSheet(f"""
                        QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 {c.BLUE}, stop:1 {c.BLUE}); border-radius: {self._sp.RADIUS_SM}px; }}
                    """)

            if self.trade_progress:
                self.trade_progress.setValue(trade_used_pct)

            # Update labels
            self._update_label("risk_max_loss", f"₹{abs(max_loss):,.0f}")

            pnl_str = f"₹{pnl:,.2f}"
            pnl_color = "positive" if pnl > 0 else "negative" if pnl < 0 else "value"
            self._update_label("risk_current_pnl", pnl_str, pnl_color)

            self._update_label("risk_loss_remaining", f"₹{loss_remaining:,.2f}")
            self._update_label("risk_max_trades", str(max_trades))
            self._update_label("risk_trades_today", str(trades_today))
            self._update_label("risk_trades_remaining", str(trades_remaining))

            is_blocked = (pnl <= max_loss) if max_loss < 0 and pnl < 0 else False
            self._update_label("risk_blocked", "⚠️ BLOCKED" if is_blocked else "✅ Active",
                              "negative" if is_blocked else "positive")

            # Stop Loss & TP
            sl = pos_snap.get('stop_loss')
            self._update_label("stop_loss", f"{sl:.2f}" if sl else "None", "negative")

            sl_pct = snap.get('stoploss_percentage', 0)
            self._update_label("stoploss_percentage", f"{sl_pct:.1f}%", "negative")

            tp = pos_snap.get('tp_point')
            self._update_label("tp_point", f"{tp:.2f}" if tp else "None", "positive")

            tp_pct = snap.get('tp_percentage', 0)
            self._update_label("tp_percentage", f"{tp_pct:.1f}%", "positive")

        except Exception as e:
            logger.error(f"Failed to update risk labels: {e}")

    def _update_market_labels(self, snap):
        """Update market tab labels"""
        try:
            c = self._c

            self._update_label("derivative", str(snap.get('derivative', 'N/A')))
            self._update_label("call_option", str(snap.get('call_option', '--')))
            self._update_label("put_option", str(snap.get('put_option', '--')))
            self._update_label("expiry", str(snap.get('expiry', 0)))

            deriv = snap.get('derivative_current_price', 0)
            self._update_label("derivative_current_price", f"{deriv:.2f}")

            call = snap.get('call_current_close')
            self._update_label("call_current_close", f"{call:.2f}" if call else "--")

            put = snap.get('put_current_close')
            self._update_label("put_current_close", f"{put:.2f}" if put else "--")

            pcr = snap.get('current_pcr', 0)
            self._update_label("current_pcr", f"{pcr:.3f}")

            pcr_vol = snap.get('current_pcr_vol')
            self._update_label("current_pcr_vol", f"{pcr_vol:.3f}" if pcr_vol else "--")

            trend = snap.get('market_trend')
            if trend == 1:
                self._update_label("market_trend", "▲ BULL", "positive")
            elif trend == -1:
                self._update_label("market_trend", "▼ BEAR", "negative")
            else:
                self._update_label("market_trend", "◆ NEUT", "value")

        except Exception as e:
            logger.error(f"Failed to update market labels: {e}")

    def _update_mtf_labels(self, snap, pos_snap):
        """Update MTF tab labels"""
        try:
            c = self._c

            if not self.mtf_labels:
                return

            mtf_results = snap.get('mtf_results', {})

            direction_icons = {
                'BULLISH': '▲',
                'BEARISH': '▼',
                'NEUTRAL': '◆'
            }

            for key in ['1m', '5m', '15m']:
                map_key = '1' if key == '1m' else '5' if key == '5m' else '15'
                direction = mtf_results.get(map_key, 'NEUTRAL')
                icon = direction_icons.get(direction, '◆')
                css_class = 'positive' if direction == 'BULLISH' else 'negative' if direction == 'BEARISH' else 'value'

                if key in self.mtf_labels:
                    self._update_label(f"mtf_{key}", f"{icon} {direction}", css_class)

            signal = pos_snap.get('option_signal', 'WAIT')
            target = 'BULLISH' if signal == 'BUY_CALL' else 'BEARISH' if signal == 'BUY_PUT' else None

            if target:
                matches = sum(1 for d in mtf_results.values() if d == target)
                agree_text = f"{matches}/3 {'✓' if matches >= 2 else '⚠️'}"
                agree_color = 'positive' if matches >= 2 else 'warning' if matches == 1 else 'value'
            else:
                agree_text = "0/3"
                agree_color = 'value'

            self._update_label("mtf_agreement", agree_text, agree_color)

            use_mtf = snap.get('use_mtf_filter', False)
            self._update_label("mtf_enabled", "✅ ON" if use_mtf else "⭕ OFF",
                              'positive' if use_mtf else 'value')

            self._update_label("option_signal", signal)

            summary = snap.get('last_mtf_summary', 'No MTF evaluation yet')
            self._update_label("mtf_summary", summary)

        except Exception as e:
            logger.error(f"Failed to update MTF labels: {e}")

    def _update_signal_labels(self, snap, pos_snap):
        """Update signal tab labels"""
        try:
            c = self._c

            if not self.conf_bars:
                return

            try:
                signal_snap = state_manager.get_state().get_option_signal_snapshot()
            except Exception:
                signal_snap = {}

            confidence = signal_snap.get('confidence', {})
            threshold = signal_snap.get('threshold', 0.6)
            explanation = signal_snap.get('explanation', "No signal evaluation yet")

            for signal, bar in self.conf_bars.items():
                conf = confidence.get(signal, 0.0)
                conf_pct = int(float(conf) * 100)
                bar.setValue(conf_pct)

                if conf_pct >= threshold * 100:
                    bar.setStyleSheet(f"""
                        QProgressBar::chunk {{ 
                            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 {c.GREEN}, stop:1 {c.GREEN_BRIGHT});
                            border-radius: {self._sp.RADIUS_SM}px; 
                        }}
                    """)
                elif conf_pct >= threshold * 70:
                    bar.setStyleSheet(f"""
                        QProgressBar::chunk {{ 
                            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 {c.YELLOW}, stop:1 {c.ORANGE});
                            border-radius: {self._sp.RADIUS_SM}px; 
                        }}
                    """)
                else:
                    bar.setStyleSheet(f"""
                        QProgressBar::chunk {{ 
                            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 {c.RED}, stop:1 {c.RED_BRIGHT});
                            border-radius: {self._sp.RADIUS_SM}px; 
                        }}
                    """)

            threshold_pct = int(float(threshold) * 100)
            for label in self.conf_labels.values():
                label.setText(f"{threshold_pct}%")

            if self.conf_explanation:
                self.conf_explanation.setStyleSheet(f"""
                    color: {c.TEXT_DIM};
                    font-size: {self._ty.SIZE_BODY}pt;
                    padding: {self._sp.PAD_MD}px;
                    background: {c.BG_ROW_A};
                    border-radius: {self._sp.RADIUS_SM}px;
                    min-height: 60px;
                """)
                self.conf_explanation.setText(explanation)

        except Exception as e:
            logger.error(f"Failed to update signal labels: {e}")

    def _update_advanced_labels(self, snap, pos_snap):
        """Update advanced tab labels"""
        try:
            if not self.adv_labels:
                return

            # Placeholder data - would need actual trade history
            self._update_label("adv_avg_win", "₹0.00")
            self._update_label("adv_avg_loss", "₹0.00")
            self._update_label("adv_max_win", "₹0.00")
            self._update_label("adv_max_loss", "₹0.00")
            self._update_label("adv_win_loss_ratio", "0.00")
            self._update_label("adv_profit_factor", "0.00")
            self._update_label("adv_sharpe", "0.00")
            self._update_label("adv_max_dd", "0%")

            start_time = snap.get('current_trade_started_time')
            if start_time and isinstance(start_time, datetime):
                self._update_label("adv_session_start", start_time.strftime("%H:%M"))

                duration = datetime.now() - start_time
                hours = duration.seconds // 3600
                minutes = (duration.seconds % 3600) // 60
                self._update_label("adv_active_time", f"{hours}h {minutes}m")
            else:
                self._update_label("adv_session_start", "--:--")
                self._update_label("adv_active_time", "0h 0m")

        except Exception as e:
            logger.error(f"Failed to update advanced labels: {e}")

    def _update_progress_bars(self, pos_snap):
        """Update progress bars"""
        try:
            c = self._c

            if "position_progress" in self._progress_bars:
                positions = pos_snap.get('positions_hold', 0)
                max_positions = 5
                progress = min(100, int((positions / max_positions) * 100))
                self._progress_bars["position_progress"].setValue(progress)

                if progress > 80:
                    self._progress_bars["position_progress"].setStyleSheet(f"""
                        QProgressBar::chunk {{
                            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 {c.RED}, stop:1 {c.RED_BRIGHT});
                            border-radius: {self._sp.RADIUS_SM}px;
                        }}
                    """)
                elif progress > 50:
                    self._progress_bars["position_progress"].setStyleSheet(f"""
                        QProgressBar::chunk {{
                            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 {c.YELLOW}, stop:1 {c.ORANGE});
                            border-radius: {self._sp.RADIUS_SM}px;
                        }}
                    """)
        except Exception as e:
            logger.debug(f"Failed to update progress bars: {e}")

    def _update_label(self, key: str, value: str, css_class: str = "value"):
        """Update a label with error handling"""
        try:
            if key in self._labels and self._labels[key] is not None:
                label = self._labels[key]
                label.setText(str(value))
                label.setProperty("cssClass", css_class)
                label.style().unpolish(label)
                label.style().polish(label)
        except Exception as e:
            logger.debug(f"Failed to update label {key}: {e}")

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            logger.info("[StatsWidget] Starting cleanup")

            # Stop timers
            if hasattr(self, 'time_timer') and self.time_timer:
                if self.time_timer.isActive():
                    self.time_timer.stop()
                self.time_timer = None

            # Clear references
            self._labels.clear()
            self._progress_bars.clear()
            self.risk_labels.clear()
            self.mtf_labels.clear()
            self.conf_labels.clear()
            self.conf_bars.clear()
            self.adv_labels.clear()
            self._last_snapshot = {}
            self._last_snapshot_time = None
            self._last_position_snapshot = {}
            self.debug_scroll_layout = None

            logger.info("[StatsWidget] Cleanup completed")

        except Exception as e:
            logger.error(f"[StatsWidget.cleanup] Error: {e}", exc_info=True)


class StatsPopup(QDialog, ThemedMixin):
    """
    Popup window for displaying statistics.
    Wraps StatsWidget in a dialog with close button.
    """

    def __init__(self, parent=None):
        self._safe_defaults_init()
        super().__init__(parent)

        try:
            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setWindowTitle("📊 Trading Statistics Dashboard")
            self.resize(1100, 800)
            self.setMinimumSize(400, 500)
            self.setWindowFlags(Qt.Window)

            # Main layout
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Add the main stats widget (embedded=False to show header)
            self.stats_widget = StatsWidget(self, embedded=False)
            layout.addWidget(self.stats_widget, 1)

            # Button bar
            button_layout = QHBoxLayout()
            button_layout.setContentsMargins(self._sp.PAD_SM, self._sp.PAD_SM, self._sp.PAD_SM, self._sp.PAD_SM)
            button_layout.setSpacing(self._sp.GAP_SM)

            button_layout.addStretch()

            self.close_btn = QPushButton("✕ Close")
            self.close_btn.setObjectName("closeBtn")
            self.close_btn.setMinimumHeight(self._sp.BTN_HEIGHT_MD)
            self.close_btn.setMinimumWidth(100)
            self.close_btn.clicked.connect(self.accept)
            button_layout.addWidget(self.close_btn)

            layout.addLayout(button_layout)

            self.apply_theme()

            logger.info("StatsPopup initialized")

        except Exception as e:
            logger.critical(f"[StatsPopup.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self.stats_widget = None
        self.close_btn = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the popup"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            if self.close_btn:
                self.close_btn.setStyleSheet(f"""
                    QPushButton#closeBtn {{
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 {c.RED}, stop:1 {c.RED_BRIGHT});
                        border: {sp.SEPARATOR}px solid {c.RED_BRIGHT};
                        color: {c.TEXT_INVERSE};
                        border-radius: {sp.RADIUS_MD}px;
                        padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                        font-size: {ty.SIZE_BODY}pt;
                        font-weight: 500;
                    }}
                    QPushButton#closeBtn:hover {{
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 {c.RED_BRIGHT}, stop:1 {c.RED});
                    }}
                """)

            if self.stats_widget and hasattr(self.stats_widget, 'apply_theme'):
                self.stats_widget.apply_theme()

            logger.debug("[StatsPopup.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[StatsPopup.apply_theme] Failed: {e}", exc_info=True)

    # Add refresh method that forwards to stats_widget
    def refresh(self):
        """Forward refresh call to the stats widget"""
        try:
            if hasattr(self, 'stats_widget') and self.stats_widget is not None:
                self.stats_widget.refresh()
        except Exception as e:
            logger.error(f"[StatsPopup.refresh] Failed: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event - Rule 7"""
        try:
            if hasattr(self, 'stats_widget') and self.stats_widget is not None:
                self.stats_widget.cleanup()
                self.stats_widget = None
            event.accept()
        except Exception as e:
            logger.error(f"[StatsPopup.closeEvent] Failed: {e}")
            event.accept()

    def accept(self):
        """Handle accept"""
        try:
            if hasattr(self, 'stats_widget') and self.stats_widget is not None:
                self.stats_widget.cleanup()
                self.stats_widget = None
            super().accept()
        except Exception as e:
            logger.error(f"[StatsPopup.accept] Failed: {e}")
            super().accept()