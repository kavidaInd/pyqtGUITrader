from __future__ import annotations

import logging.handlers
import threading
from typing import Any, Dict, Set, List, Optional
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QLabel, QFrame, QVBoxLayout, QTabWidget,
    QHBoxLayout, QPushButton, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFormLayout, QProgressBar
)

# Import Utils for market status
from Utils.Utils import Utils

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

# ── Palette ───────────────────────────────────────────────────────────────────
BG_MAIN = "#0d1117"
BG_PANEL = "#161b22"
BG_ROW_A = "#1c2128"
BG_ROW_B = "#22272e"
BORDER = "#30363d"
TEXT_MAIN = "#e6edf3"
TEXT_DIM = "#8b949e"
GREEN = "#3fb950"
RED = "#f85149"
YELLOW = "#d29922"
BLUE = "#58a6ff"
ORANGE = "#ffa657"
PURPLE = "#bc8cff"
GREY_OFF = "#484f58"
GREY_DARK = "#21262d"


def _global_ss() -> str:
    """Return global stylesheet string."""
    return f"""
        QWidget, QFrame {{
            background: {BG_MAIN};
            color: {TEXT_MAIN};
            font-family: 'Segoe UI', sans-serif;
        }}
        QTabWidget::pane {{
            border: 1px solid {BORDER};
            border-radius: 4px;
            background: {BG_PANEL};
        }}
        QTabBar::tab {{
            background: #21262d;
            color: {TEXT_DIM};
            border: 1px solid {BORDER};
            border-bottom: none;
            border-radius: 4px 4px 0 0;
            padding: 6px 16px;
            font-size: 9pt;
            font-weight: bold;
            width:120px
        }}
        QTabBar::tab:selected {{
            background: {BG_PANEL};
            color: {TEXT_MAIN};
            border-bottom: 2px solid {BLUE};
        }}
        QTabBar::tab:hover:!selected {{
            background: #2d333b;
        }}
        QGroupBox {{
            border: 1px solid {BORDER};
            border-radius: 4px;
            margin-top: 8px;
            font-weight: bold;
            color: {TEXT_MAIN};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 5px;
            color: {BLUE};
        }}
        QPushButton {{
            background: #21262d;
            color: {TEXT_MAIN};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 9pt;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background: #30363d;
        }}
        QPushButton:disabled {{
            color: {GREY_OFF};
        }}
        QPushButton#exit {{
            background: {RED};
            color: white;
            border: none;
        }}
        QPushButton#exit:hover {{
            background: #f85149;
        }}
        QPushButton#exit:disabled {{
            background: #21262d;
            color: {GREY_OFF};
        }}
        QTableWidget {{
            background: {BG_PANEL};
            gridline-color: {BORDER};
            border: 1px solid {BORDER};
            color: {TEXT_MAIN};
            font-size: 9pt;
        }}
        QTableWidget::item {{ padding: 4px 8px; }}
        QHeaderView::section {{
            background: #21262d;
            color: {TEXT_DIM};
            border: none;
            border-bottom: 1px solid {BORDER};
            padding: 4px 8px;
            font-size: 8pt;
            font-weight: bold;
        }}
        QLabel {{ color: {TEXT_MAIN}; }}
        QLabel#value {{ color: {BLUE}; font-weight: bold; }}
        QLabel#positive {{ color: {GREEN}; font-weight: bold; }}
        QLabel#negative {{ color: {RED}; font-weight: bold; }}
        QLabel#signal-badge {{
            color: white;
            border-radius: 3px;
            font-size: 8pt;
            font-weight: bold;
            padding: 2px 8px;
        }}
        QProgressBar {{
            border: 1px solid {BORDER};
            border-radius: 4px;
            background: {BG_PANEL};
            text-align: center;
            color: {TEXT_MAIN};
            font-size: 8pt;
        }}
        QProgressBar::chunk {{
            background: {BLUE};
            border-radius: 4px;
        }}
    """


# ─────────────────────────────────────────────────────────────────────────────
# StatusCard (YOUR ORIGINAL CARD - UNCHANGED)
# ─────────────────────────────────────────────────────────────────────────────

class StatusCard(QFrame):
    """Single status field with icon label + live value."""

    _BASE_SS = f"""
        QFrame {{
            background: {BG_PANEL};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 4px;
        }}
    """
    _DIM_SS = f"""
        QFrame {{
            background: #0f1318;
            border: 1px solid #1c2230;
            border-radius: 6px;
            padding: 4px;
        }}
    """

    def __init__(self, icon: str, label: str, parent=None):
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self._dimmed = False
            self.setStyleSheet(self._BASE_SS)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 6, 8, 6)
            layout.setSpacing(2)

            self._title = QLabel(f"{icon}  {label}")
            self._title.setFont(QFont("Segoe UI", 8))
            self._title.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")

            self.value_label = QLabel("—")
            self.value_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.value_label.setStyleSheet(f"color: {TEXT_MAIN}; border: none; background: transparent;")

            self._last_value = None
            self._last_color = TEXT_MAIN

            layout.addWidget(self._title)
            layout.addWidget(self.value_label)

            logger.debug(f"StatusCard created: {icon} {label}")

        except Exception as e:
            logger.error(f"[StatusCard.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self._safe_defaults_init()

    def _safe_defaults_init(self):
        self._dimmed = False
        self._title = None
        self.value_label = None
        self._last_value = None
        self._last_color = TEXT_MAIN

    def set_value(self, text: str, color: str = TEXT_MAIN):
        try:
            if text is None:
                text = "—"

            if self.value_label is None:
                return

            if text == self._last_value and color == self._last_color:
                return

            self.value_label.setText(text)
            self.value_label.setStyleSheet(
                f"color: {color}; border: none; background: transparent;"
            )
            self._last_value = text
            self._last_color = color

        except Exception as e:
            logger.error(f"[StatusCard.set_value] Failed: {e}", exc_info=True)

    def set_dimmed(self, dimmed: bool):
        try:
            if dimmed == self._dimmed:
                return

            self._dimmed = dimmed
            self.setStyleSheet(self._DIM_SS if dimmed else self._BASE_SS)
            dim_col = GREY_OFF if dimmed else TEXT_DIM

            if self._title is not None:
                self._title.setStyleSheet(
                    f"color: {dim_col}; border: none; background: transparent;"
                )

            if dimmed and self.value_label is not None:
                self.value_label.setText("—")
                self.value_label.setStyleSheet(
                    f"color: {GREY_OFF}; border: none; background: transparent;"
                )
                self._last_value = None

        except Exception as e:
            logger.error(f"[StatusCard.set_dimmed] Failed: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# ConfidenceBar - FEATURE 3
# ─────────────────────────────────────────────────────────────────────────────

class ConfidenceBar(QWidget):
    """FEATURE 3: Confidence bar for signal groups"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.label = QLabel("BUY_CALL")
        self.label.setFixedWidth(70)
        self.label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 8pt;")
        layout.addWidget(self.label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(12)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress, 1)

        self.value = QLabel("0%")
        self.value.setFixedWidth(40)
        self.value.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 8pt; font-weight: bold;")
        layout.addWidget(self.value)

    def set_confidence(self, signal: str, confidence: float, threshold: float = 0.6):
        """Set confidence value for a signal"""
        try:
            self.label.setText(signal.replace('_', ' '))

            percent = int(confidence * 100)
            self.progress.setValue(percent)
            self.value.setText(f"{percent}%")

            # Color based on threshold
            if confidence >= threshold:
                self.progress.setStyleSheet(f"""
                    QProgressBar::chunk {{ background: {GREEN}; }}
                """)
            elif confidence >= threshold * 0.7:
                self.progress.setStyleSheet(f"""
                    QProgressBar::chunk {{ background: {YELLOW}; }}
                """)
            else:
                self.progress.setStyleSheet(f"""
                    QProgressBar::chunk {{ background: {RED}; }}
                """)
        except Exception as e:
            logger.error(f"[ConfidenceBar.set_confidence] Failed: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# StatusPanel - ENHANCED WITH ALL FEATURES
# ─────────────────────────────────────────────────────────────────────────────

class StatusPanel(QWidget):
    """
    Enhanced status panel with:
    - Signal in its own card
    - Market status connected to Utils
    - FEATURE 1: Risk management display
    - FEATURE 3: Signal confidence bars
    - FEATURE 6: Multi-timeframe filter status
    """

    # Cards that only make sense when a trade is open
    _TRADE_ONLY: Set[str] = frozenset({
        "symbol", "buy_price", "current_price", "target_price",
        "stoploss_price", "pnl"
    })

    # Updated FIELDS with new cards
    FIELDS = [
        # Always-visible
        ("position", "🟢", "Position"),
        ("signal", "📊", "Signal"),
        ("balance", "🏦", "Balance"),
        ("derivative", "📈", "Index"),
        # FEATURE 1: Risk cards
        ("daily_pnl", "📉", "Daily P&L"),
        ("trades_today", "🎯", "Trades"),
        # Trade-specific (dimmed when no trade)
        ("symbol", "💹", "Symbol"),
        ("buy_price", "🛒", "Entry"),
        ("current_price", "💰", "Current"),
        ("target_price", "🎯", "Target"),
        ("stoploss_price", "🛑", "Stop"),
        ("pnl", "💵", "P&L"),
    ]

    COLORS = {
        "positive": GREEN,
        "negative": RED,
        "neutral": TEXT_DIM,
        "normal": TEXT_MAIN,
        "accent": BLUE,
    }

    # Signal colors
    SIGNAL_COLORS = {
        "BUY_CALL": GREEN,
        "BUY_PUT": BLUE,
        "EXIT_CALL": RED,
        "EXIT_PUT": ORANGE,
        "HOLD": YELLOW,
        "WAIT": GREY_OFF
    }

    # Signals
    exit_position_clicked = pyqtSignal()
    modify_sl_clicked = pyqtSignal()
    modify_tp_clicked = pyqtSignal()

    def __init__(self, parent=None):
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setStyleSheet(_global_ss())
            self.setMinimumWidth(340)
            self.setMaximumWidth(400)

            self._lock = threading.RLock()
            self._last_state: Dict[str, str] = {}
            self._refresh_enabled = True
            self._trade_active = False
            self._closing = False
            self._recent_trades: List[Dict] = []

            # Market status from Utils
            self._market_open = Utils.is_market_open()
            self._is_holiday = Utils.is_today_holiday()

            # Main layout
            root = QVBoxLayout(self)
            root.setContentsMargins(4, 4, 4, 4)
            root.setSpacing(4)

            # Header with timestamp and market status
            header = self._create_header()
            root.addWidget(header)

            # Tab widget
            self._tabs = QTabWidget()

            # Tab 1: Trade Status (YOUR CARD LAYOUT)
            self._create_trade_tab()

            # Tab 2: Performance (Enhanced with win rate)
            self._create_performance_tab()

            # Tab 3: FEATURE 3 - Signal Confidence
            self._create_confidence_tab()

            # Tab 4: FEATURE 6 - MTF Filter
            self._create_mtf_tab()

            # Tab 5: Positions
            self._create_positions_tab()

            # Tab 6: Account
            self._create_account_tab()

            root.addWidget(self._tabs)

            # Start timer to update market status periodically
            self._market_timer = QTimer()
            self._market_timer.timeout.connect(self._update_market_status)
            self._market_timer.start(60000)  # Update every minute

            logger.info("Enhanced StatusPanel initialized with all features")

        except Exception as e:
            logger.critical(f"[StatusPanel.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self._safe_defaults_init()

    def _safe_defaults_init(self):
        self._lock = threading.RLock()
        self._last_state = {}
        self._refresh_enabled = True
        self._trade_active = False
        self._closing = False
        self._recent_trades = []
        self._market_open = False
        self._is_holiday = False
        self._market_timer = None
        self._tabs = None
        self._no_trade_lbl = None
        self.cards = {}
        self._perf_labels = {}
        self._account_labels = {}
        self._confidence_bars = {}
        self._mtf_labels = {}
        self.positions_table = None
        self.recent_table = None
        self.exit_btn = None
        self.modify_sl_btn = None
        self.modify_tp_btn = None
        self.timestamp = None
        self.conn_status = None
        self.market_status = None
        self.conflict_label = None

    def _create_header(self) -> QWidget:
        """Create header with timestamp and market status from Utils"""
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.conn_status = QLabel("●")
        self.conn_status.setStyleSheet(f"color: {RED}; font-size: 10px;")
        header_layout.addWidget(self.conn_status)

        self.timestamp = QLabel(datetime.now().strftime("%H:%M:%S"))
        self.timestamp.setStyleSheet(f"color: {TEXT_DIM}; font-size: 8pt;")
        header_layout.addWidget(self.timestamp)

        header_layout.addStretch()

        # Market status from Utils
        self.market_status = QLabel()
        self._update_market_status_display()
        header_layout.addWidget(self.market_status)

        return header

    def _update_market_status(self):
        """Update market status using Utils"""
        try:
            self._market_open = Utils.is_market_open()
            self._is_holiday = Utils.is_today_holiday()
            self._update_market_status_display()
        except Exception as e:
            logger.error(f"[StatusPanel._update_market_status] Failed: {e}")

    def _update_market_status_display(self):
        """Update the market status label"""
        try:
            if self._is_holiday:
                self.market_status.setText("Market: Holiday")
                self.market_status.setStyleSheet(f"color: {GREY_OFF}; font-size: 8pt;")
            elif self._market_open:
                self.market_status.setText("Market: Open")
                self.market_status.setStyleSheet(f"color: {GREEN}; font-size: 8pt;")
            else:
                self.market_status.setText("Market: Closed")
                self.market_status.setStyleSheet(f"color: {RED}; font-size: 8pt;")
        except Exception as e:
            logger.error(f"[StatusPanel._update_market_status_display] Failed: {e}")

    def _create_trade_tab(self):
        """Tab 1: Trade Status - YOUR CARD LAYOUT"""
        trade_tab = QWidget()
        trade_layout = QVBoxLayout(trade_tab)
        trade_layout.setContentsMargins(6, 6, 6, 6)
        trade_layout.setSpacing(8)

        # YOUR ORIGINAL CARD GRID - 2 columns, 6 rows (now with new cards)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        self.cards: Dict[str, StatusCard] = {}

        for i, (key, icon, label) in enumerate(self.FIELDS):
            try:
                card = StatusCard(icon, label)
                grid.addWidget(card, i // 2, i % 2)
                self.cards[key] = card
            except Exception as e:
                logger.error(f"Failed to create card for {key}: {e}", exc_info=True)

        trade_layout.addWidget(grid_widget)

        # Conflict indicator
        self.conflict_label = QLabel("")
        self.conflict_label.setAlignment(Qt.AlignCenter)
        self.conflict_label.setVisible(False)
        trade_layout.addWidget(self.conflict_label)

        # Action buttons (only enabled when trade active)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)

        self.exit_btn = QPushButton("Exit")
        self.exit_btn.setObjectName("exit")
        self.exit_btn.setEnabled(False)
        self.exit_btn.clicked.connect(self.exit_position_clicked.emit)
        button_layout.addWidget(self.exit_btn)

        self.modify_sl_btn = QPushButton("SL")
        self.modify_sl_btn.setEnabled(False)
        self.modify_sl_btn.clicked.connect(self.modify_sl_clicked.emit)
        button_layout.addWidget(self.modify_sl_btn)

        self.modify_tp_btn = QPushButton("TP")
        self.modify_tp_btn.setEnabled(False)
        self.modify_tp_btn.clicked.connect(self.modify_tp_clicked.emit)
        button_layout.addWidget(self.modify_tp_btn)

        button_layout.addStretch()
        trade_layout.addLayout(button_layout)

        # Start with trade-only cards dimmed
        for key in self._TRADE_ONLY:
            if key in self.cards:
                self.cards[key].set_dimmed(True)

        self._tabs.addTab(trade_tab, "📊 Trade")

    def _create_performance_tab(self):
        """Tab 2: Performance metrics with win rate"""
        perf_tab = QWidget()
        layout = QVBoxLayout(perf_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Today's summary
        today_group = QGroupBox("Today")
        today_layout = QGridLayout()
        today_layout.setSpacing(6)

        today_layout.addWidget(QLabel("Trades:"), 0, 0)
        self.today_trades = QLabel("0")
        self.today_trades.setObjectName("value")
        today_layout.addWidget(self.today_trades, 0, 1)

        today_layout.addWidget(QLabel("Wins:"), 0, 2)
        self.today_wins = QLabel("0")
        self.today_wins.setStyleSheet(f"color: {GREEN}; font-weight: bold;")
        today_layout.addWidget(self.today_wins, 0, 3)

        today_layout.addWidget(QLabel("Losses:"), 0, 4)
        self.today_losses = QLabel("0")
        self.today_losses.setStyleSheet(f"color: {RED}; font-weight: bold;")
        today_layout.addWidget(self.today_losses, 0, 5)

        today_layout.addWidget(QLabel("P&L:"), 1, 0)
        self.today_pnl = QLabel("₹0")
        self.today_pnl.setObjectName("value")
        today_layout.addWidget(self.today_pnl, 1, 1, 1, 5)

        today_group.setLayout(today_layout)
        layout.addWidget(today_group)

        # Performance stats
        perf_group = QGroupBox("Stats")
        perf_layout = QFormLayout()
        perf_layout.setSpacing(6)
        perf_layout.setLabelAlignment(Qt.AlignLeft)

        stats = [
            ("Win Rate:", "win_rate", "0%"),
            ("Avg Win:", "avg_win", "₹0"),
            ("Avg Loss:", "avg_loss", "₹0"),
            ("Max Win:", "max_win", "₹0"),
            ("Max Loss:", "max_loss", "₹0"),
            ("Total Trades:", "total_trades", "0"),
        ]

        for label, key, default in stats:
            value_label = QLabel(default)
            value_label.setObjectName("value")
            perf_layout.addRow(QLabel(label), value_label)
            self._perf_labels[key] = value_label

        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)

        # Recent trades mini table
        recent_group = QGroupBox("Recent")
        recent_layout = QVBoxLayout()

        self.recent_table = QTableWidget(0, 3)
        self.recent_table.setHorizontalHeaderLabels(["Time", "Type", "P&L"])
        self.recent_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.recent_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.recent_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.setMaximumHeight(100)

        recent_layout.addWidget(self.recent_table)
        recent_group.setLayout(recent_layout)
        layout.addWidget(recent_group)

        self._tabs.addTab(perf_tab, "📈 Performance")

    def _create_confidence_tab(self):
        """
        FEATURE 3: Signal confidence tab
        """
        conf_tab = QWidget()
        layout = QVBoxLayout(conf_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Explanation label
        self.conf_explanation = QLabel("No signal evaluation yet")
        self.conf_explanation.setWordWrap(True)
        self.conf_explanation.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 8pt; padding: 8px; background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 4px;")
        layout.addWidget(self.conf_explanation)

        # Confidence bars for each signal group
        signal_groups = ['BUY_CALL', 'BUY_PUT', 'EXIT_CALL', 'EXIT_PUT', 'HOLD']

        for signal in signal_groups:
            bar = ConfidenceBar()
            bar.set_confidence(signal, 0.0)
            layout.addWidget(bar)
            self._confidence_bars[signal] = bar

        # Threshold indicator
        threshold_group = QGroupBox("Threshold")
        threshold_layout = QHBoxLayout()
        self.threshold_label = QLabel("Min Confidence: 60%")
        self.threshold_label.setStyleSheet(f"color: {YELLOW}; font-weight: bold;")
        threshold_layout.addWidget(self.threshold_label)
        threshold_layout.addStretch()
        threshold_group.setLayout(threshold_layout)
        layout.addWidget(threshold_group)

        layout.addStretch()
        self._tabs.addTab(conf_tab, "🎯 Confidence")

    def _create_mtf_tab(self):
        """
        FEATURE 6: Multi-Timeframe Filter tab
        """
        mtf_tab = QWidget()
        layout = QVBoxLayout(mtf_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Status group
        status_group = QGroupBox("MTF Filter Status")
        status_layout = QFormLayout()
        status_layout.setSpacing(6)

        self.mtf_enabled = QLabel("Disabled")
        self.mtf_enabled.setObjectName("value")
        status_layout.addRow("Enabled:", self.mtf_enabled)

        self.mtf_decision = QLabel("No decision")
        self.mtf_decision.setObjectName("value")
        status_layout.addRow("Last Decision:", self.mtf_decision)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Timeframe directions
        tf_group = QGroupBox("Timeframe Directions")
        tf_layout = QFormLayout()
        tf_layout.setSpacing(6)

        self.mtf_1m = QLabel("NEUTRAL")
        self.mtf_1m.setObjectName("value")
        tf_layout.addRow("1 Minute:", self.mtf_1m)

        self.mtf_5m = QLabel("NEUTRAL")
        self.mtf_5m.setObjectName("value")
        tf_layout.addRow("5 Minute:", self.mtf_5m)

        self.mtf_15m = QLabel("NEUTRAL")
        self.mtf_15m.setObjectName("value")
        tf_layout.addRow("15 Minute:", self.mtf_15m)

        self.mtf_agreement = QLabel("0/3")
        self.mtf_agreement.setObjectName("value")
        tf_layout.addRow("Agreement:", self.mtf_agreement)

        tf_group.setLayout(tf_layout)
        layout.addWidget(tf_group)

        # Summary
        summary_group = QGroupBox("Summary")
        summary_layout = QVBoxLayout()
        self.mtf_summary = QLabel("No MTF evaluation yet")
        self.mtf_summary.setWordWrap(True)
        self.mtf_summary.setStyleSheet(f"color: {TEXT_DIM}; font-size: 8pt;")
        summary_layout.addWidget(self.mtf_summary)
        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)

        layout.addStretch()
        self._tabs.addTab(mtf_tab, "📈 MTF Filter")

    def _create_positions_tab(self):
        """Tab 5: Active positions"""
        pos_tab = QWidget()
        layout = QVBoxLayout(pos_tab)
        layout.setContentsMargins(8, 8, 8, 8)

        self.positions_table = QTableWidget(0, 4)
        self.positions_table.setHorizontalHeaderLabels(["Symbol", "Type", "Qty", "P&L"])
        self.positions_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.positions_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.positions_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.positions_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.positions_table.verticalHeader().setVisible(False)

        layout.addWidget(self.positions_table)
        self._tabs.addTab(pos_tab, "📋 Positions")

    def _create_account_tab(self):
        """Tab 6: Account info"""
        account_tab = QWidget()
        layout = QFormLayout(account_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.setLabelAlignment(Qt.AlignLeft)

        fields = [
            ("Balance:", "balance", "₹0"),
            ("Margin:", "margin", "₹0"),
            ("Buying Power:", "buying_power", "₹0"),
            ("M2M:", "m2m", "₹0"),
            ("Day Trades:", "day_trades", "0"),
            ("Open Pos:", "open_positions", "0"),
        ]

        self._account_labels = {}
        for label, key, default in fields:
            value_label = QLabel(default)
            value_label.setObjectName("value")
            layout.addRow(QLabel(label), value_label)
            self._account_labels[key] = value_label

        self._tabs.addTab(account_tab, "🏦 Account")

    # ── Private helpers ───────────────────────────────────────────────────

    def _safe_get(self, obj: Any, attr: str, default: Any = None) -> Any:
        try:
            if obj is None:
                return default
            return getattr(obj, attr) if hasattr(obj, attr) else default
        except Exception:
            return default

    def _fmt(self, value: Any, spec: str = ".2f") -> str:
        try:
            if value is None:
                return "—"
            try:
                return f"{float(value):{spec}}"
            except (ValueError, TypeError):
                return str(value)
        except Exception:
            return "—"

    def _fmt_currency(self, value: Any) -> str:
        try:
            if value is None:
                return "—"
            if abs(float(value)) >= 1000:
                return f"₹{float(value):,.0f}"
            return f"₹{float(value):.2f}"
        except (ValueError, TypeError):
            return str(value) if value else "—"

    def _fmt_percent(self, value: Any) -> str:
        try:
            if value is None:
                return "—"
            return f"{float(value):+.1f}%"
        except (ValueError, TypeError):
            return str(value) if value else "—"

    def _pnl_color(self, pnl) -> str:
        try:
            if pnl is None:
                return self.COLORS["neutral"]
            v = float(pnl)
            if v > 0:
                return self.COLORS["positive"]
            if v < 0:
                return self.COLORS["negative"]
            return self.COLORS["neutral"]
        except Exception:
            return self.COLORS["neutral"]

    def _pos_color(self, pos) -> str:
        try:
            if pos and str(pos).upper() in ("LONG", "SHORT", "CALL", "PUT"):
                return self.COLORS["positive"]
            return self.COLORS["neutral"]
        except Exception:
            return self.COLORS["neutral"]

    def _signal_color(self, signal: str) -> str:
        """Get color for signal"""
        return self.SIGNAL_COLORS.get(signal, GREY_OFF)

    def _trade_open(self, state) -> bool:
        try:
            if state is None:
                return False
            pos = self._safe_get(state, "current_position")
            if pos and str(pos).upper() not in ("NONE", ""):
                return True
            return False
        except Exception:
            return False

    def _set_card(self, key: str, text: str, color: str):
        try:
            if key not in self.cards:
                return
            if text is None:
                text = "—"
            ck, cc = f"{key}_v", f"{key}_c"
            with self._lock:
                if text != self._last_state.get(ck) or color != self._last_state.get(cc):
                    self.cards[key].set_value(text, color)
                    self._last_state[ck] = text
                    self._last_state[cc] = color
        except Exception as e:
            logger.error(f"[_set_card] Failed for key {key}: {e}", exc_info=True)

    # ── Public API ────────────────────────────────────────────────────────

    def refresh(self, state, config):
        """Refresh all tabs with current state"""
        if self._closing or not self._refresh_enabled or state is None:
            return

        try:
            # Update timestamp
            self.timestamp.setText(datetime.now().strftime("%H:%M:%S"))

            # Update market status periodically
            self._update_market_status()

            # Get values
            with self._lock:
                pos = self._safe_get(state, "current_position")
                symbol = self._safe_get(state, "current_trading_symbol")
                buy_price = self._safe_get(state, "current_buy_price")
                cur_price = self._safe_get(state, "current_price")
                tp = self._safe_get(state, "tp_point")
                sl = self._safe_get(state, "stop_loss")
                pnl_pct = self._safe_get(state, "percentage_change")
                pnl_abs = self._safe_get(state, "current_pnl")
                balance = self._safe_get(state, "account_balance")
                deriv = self._safe_get(state, "derivative_current_price")
                lots = self._safe_get(state, "positions_hold", 0)
                lot_size = self._safe_get(state, "lot_size", 1)

                # Get signal
                signal_result = self._safe_get(state, "option_signal_result", {})
                if signal_result and isinstance(signal_result, dict):
                    signal = signal_result.get("signal_value", "WAIT")
                    conflict = signal_result.get("conflict", False)
                else:
                    signal = "WAIT"
                    conflict = False

            # Update trade active state
            trade_active = self._trade_open(state)
            if trade_active != self._trade_active:
                self._trade_active = trade_active
                for key in self._TRADE_ONLY:
                    if key in self.cards:
                        self.cards[key].set_dimmed(not trade_active)

                # Update button states
                if hasattr(self, 'exit_btn') and self.exit_btn:
                    self.exit_btn.setEnabled(trade_active)
                if hasattr(self, 'modify_sl_btn') and self.modify_sl_btn:
                    self.modify_sl_btn.setEnabled(trade_active)
                if hasattr(self, 'modify_tp_btn') and self.modify_tp_btn:
                    self.modify_tp_btn.setEnabled(trade_active)

            # Update signal card
            if "signal" in self.cards:
                signal_color = self._signal_color(signal)
                self.cards["signal"].set_value(signal, signal_color)

                # Show conflict if present
                if conflict:
                    self.conflict_label.setText("⚠ Signal Conflict")
                    self.conflict_label.setStyleSheet(f"color: {RED}; font-size: 7pt;")
                    self.conflict_label.setVisible(True)
                else:
                    self.conflict_label.setVisible(False)

            # Update always-visible cards
            self._set_card("position", str(pos) if pos else "None", self._pos_color(pos))
            self._set_card("balance", self._fmt_currency(balance), self.COLORS["normal"])
            self._set_card("derivative", self._fmt(deriv), self.COLORS["accent"])

            # Update trade-specific cards
            if trade_active:
                self._set_card("symbol", str(symbol) if symbol else "—", self.COLORS["normal"])
                self._set_card("buy_price", self._fmt(buy_price), self.COLORS["normal"])
                self._set_card("current_price", self._fmt(cur_price), self.COLORS["normal"])
                self._set_card("target_price", self._fmt(tp), self.COLORS["positive"])
                self._set_card("stoploss_price", self._fmt(sl), self.COLORS["negative"])

                pnl_txt = self._fmt_percent(pnl_pct) if pnl_pct is not None else "—"
                self._set_card("pnl", pnl_txt, self._pnl_color(pnl_pct))

            # Update positions table
            self._update_positions_table(trade_active, symbol, pos, lots, lot_size, pnl_abs)

            # Update account tab
            if "balance" in self._account_labels:
                self._account_labels["balance"].setText(self._fmt_currency(balance))
            if "open_positions" in self._account_labels:
                self._account_labels["open_positions"].setText(str(1 if trade_active else 0))
            if "m2m" in self._account_labels:
                self._account_labels["m2m"].setText(self._fmt_currency(pnl_abs))

            # FEATURE 1: Update risk cards
            self._update_risk_cards(state, config)

            # FEATURE 3: Update confidence tab
            self._update_confidence_tab(state)

            # FEATURE 6: Update MTF tab
            self._update_mtf_tab(state)

        except Exception as e:
            logger.error(f"StatusPanel.refresh error: {e}", exc_info=True)

    def _update_risk_cards(self, state, config):
        """
        FEATURE 1: Update risk management cards
        """
        try:
            # Try to get risk summary from state
            daily_pnl = 0.0
            trades_today = 0
            max_loss = -5000
            daily_target = 5000

            if hasattr(state, 'get_risk_summary'):
                try:
                    risk_summary = state.get_risk_summary(state)
                    daily_pnl = risk_summary.get('pnl_today', 0)
                    trades_today = risk_summary.get('trades_today', 0)
                    max_loss = risk_summary.get('max_loss', -5000)
                    daily_target = risk_summary.get('daily_target', 5000)
                except:
                    pass

            # Update cards
            if "daily_pnl" in self.cards:
                pnl_color = GREEN if daily_pnl > 0 else RED if daily_pnl < 0 else TEXT_MAIN
                self.cards["daily_pnl"].set_value(self._fmt_currency(daily_pnl), pnl_color)

            if "trades_today" in self.cards:
                self.cards["trades_today"].set_value(str(trades_today), TEXT_MAIN)

        except Exception as e:
            logger.error(f"[StatusPanel._update_risk_cards] Failed: {e}", exc_info=True)

    def _update_confidence_tab(self, state):
        """
        FEATURE 3: Update confidence tab
        """
        try:
            confidence = {}
            explanation = ""
            threshold = 0.6

            if hasattr(state, 'signal_confidence'):
                confidence = state.signal_confidence
            if hasattr(state, 'signal_explanation'):
                explanation = state.signal_explanation
            if hasattr(state, 'option_signal_result'):
                result = state.option_signal_result
                if result:
                    threshold = result.get('threshold', 0.6)

            # Update explanation
            if self.conf_explanation:
                self.conf_explanation.setText(explanation or "No signal evaluation yet")

            # Update threshold
            threshold_pct = int(threshold * 100)
            self.threshold_label.setText(f"Min Confidence: {threshold_pct}%")

            # Update confidence bars
            for signal, bar in self._confidence_bars.items():
                conf = confidence.get(signal, 0.0)
                bar.set_confidence(signal, conf, threshold)

        except Exception as e:
            logger.error(f"[StatusPanel._update_confidence_tab] Failed: {e}", exc_info=True)

    def _update_mtf_tab(self, state):
        """
        FEATURE 6: Update MTF filter tab
        """
        try:
            # Get MTF results from state
            mtf_results = {}
            if hasattr(state, 'mtf_results'):
                mtf_results = state.mtf_results

            # Update timeframe directions
            self.mtf_1m.setText(mtf_results.get('1', 'NEUTRAL'))
            self.mtf_5m.setText(mtf_results.get('5', 'NEUTRAL'))
            self.mtf_15m.setText(mtf_results.get('15', 'NEUTRAL'))

            # Color based on direction
            self._set_mtf_direction_color(self.mtf_1m, mtf_results.get('1', 'NEUTRAL'))
            self._set_mtf_direction_color(self.mtf_5m, mtf_results.get('5', 'NEUTRAL'))
            self._set_mtf_direction_color(self.mtf_15m, mtf_results.get('15', 'NEUTRAL'))

            # Count agreement
            target = 'BULLISH' if getattr(state, 'option_signal', '') == 'BUY_CALL' else 'BEARISH'
            matches = sum(1 for d in mtf_results.values() if d == target)
            self.mtf_agreement.setText(f"{matches}/3")

            # Update enabled status
            enabled = False
            if hasattr(state, 'mtf_allowed'):
                enabled = state.mtf_allowed
            self.mtf_enabled.setText("Yes" if enabled else "No")
            self.mtf_enabled.setStyleSheet(f"color: {GREEN if enabled else RED}; font-weight: bold;")

            # Update decision
            if hasattr(state, 'last_mtf_summary'):
                summary = state.last_mtf_summary or "No decision yet"
                self.mtf_summary.setText(summary)

                # Color based on decision
                if "ALLOWED" in summary:
                    self.mtf_decision.setText("ALLOWED")
                    self.mtf_decision.setStyleSheet(f"color: {GREEN}; font-weight: bold;")
                elif "BLOCKED" in summary:
                    self.mtf_decision.setText("BLOCKED")
                    self.mtf_decision.setStyleSheet(f"color: {RED}; font-weight: bold;")
                else:
                    self.mtf_decision.setText(summary)
                    self.mtf_decision.setStyleSheet(f"color: {TEXT_DIM}; font-weight: bold;")

        except Exception as e:
            logger.error(f"[StatusPanel._update_mtf_tab] Failed: {e}", exc_info=True)

    def _set_mtf_direction_color(self, label: QLabel, direction: str):
        """Set color for MTF direction label"""
        if direction == 'BULLISH':
            label.setStyleSheet(f"color: {GREEN}; font-weight: bold;")
        elif direction == 'BEARISH':
            label.setStyleSheet(f"color: {RED}; font-weight: bold;")
        else:
            label.setStyleSheet(f"color: {GREY_OFF}; font-weight: bold;")

    def _update_positions_table(self, trade_active: bool, symbol: str, pos: str,
                                lots: int, lot_size: int, pnl: float):
        """Update positions table"""
        try:
            self.positions_table.setRowCount(0)

            if trade_active and symbol:
                self.positions_table.insertRow(0)
                self.positions_table.setItem(0, 0, QTableWidgetItem(str(symbol)))
                self.positions_table.setItem(0, 1, QTableWidgetItem(str(pos) if pos else "—"))
                self.positions_table.setItem(0, 2, QTableWidgetItem(f"{lots}"))

                pnl_item = QTableWidgetItem(self._fmt_currency(pnl))
                color = GREEN if pnl and pnl > 0 else RED if pnl and pnl < 0 else TEXT_MAIN
                pnl_item.setForeground(QColor(color))
                self.positions_table.setItem(0, 3, pnl_item)
        except Exception as e:
            logger.error(f"[StatusPanel._update_positions_table] Failed: {e}")

    def add_recent_trade(self, trade_data: Dict):
        """Add a completed trade to recent list"""
        try:
            self._recent_trades.append(trade_data)

            time_str = datetime.now().strftime("%H:%M")
            trade_type = trade_data.get('type', 'CALL')
            pnl = trade_data.get('pnl', 0)

            # Keep only last 8
            if self.recent_table.rowCount() >= 8:
                self.recent_table.removeRow(0)

            row = self.recent_table.rowCount()
            self.recent_table.insertRow(row)
            self.recent_table.setItem(row, 0, QTableWidgetItem(time_str))
            self.recent_table.setItem(row, 1, QTableWidgetItem(trade_type))

            pnl_item = QTableWidgetItem(f"{pnl:+.0f}")
            pnl_item.setForeground(QColor(GREEN if pnl > 0 else RED))
            self.recent_table.setItem(row, 2, pnl_item)

            # Update performance metrics
            self._update_performance_metrics()

        except Exception as e:
            logger.error(f"[StatusPanel.add_recent_trade] Failed: {e}")

    def _update_performance_metrics(self):
        """Update performance metrics from trade history"""
        try:
            if not self._recent_trades:
                return

            total = len(self._recent_trades)
            winning = [t for t in self._recent_trades if t.get('pnl', 0) > 0]
            losing = [t for t in self._recent_trades if t.get('pnl', 0) < 0]

            win_count = len(winning)
            loss_count = len(losing)
            win_rate = (win_count / total * 100) if total > 0 else 0

            avg_win = sum(t.get('pnl', 0) for t in winning) / win_count if win_count > 0 else 0
            avg_loss = sum(t.get('pnl', 0) for t in losing) / loss_count if loss_count > 0 else 0
            max_win = max((t.get('pnl', 0) for t in winning), default=0)
            max_loss = min((t.get('pnl', 0) for t in losing), default=0)

            # Today's stats
            today = datetime.now().date()
            today_trades = [t for t in self._recent_trades
                            if t.get('time', datetime.now()).date() == today]
            today_wins = sum(1 for t in today_trades if t.get('pnl', 0) > 0)
            today_losses = sum(1 for t in today_trades if t.get('pnl', 0) < 0)
            today_pnl = sum(t.get('pnl', 0) for t in today_trades)

            # Update UI
            self.today_trades.setText(str(len(today_trades)))
            self.today_wins.setText(str(today_wins))
            self.today_losses.setText(str(today_losses))
            self.today_pnl.setText(self._fmt_currency(today_pnl))

            color = GREEN if today_pnl > 0 else RED if today_pnl < 0 else BLUE
            self.today_pnl.setStyleSheet(f"color: {color}; font-weight: bold;")

            # Update perf labels
            if "win_rate" in self._perf_labels:
                self._perf_labels["win_rate"].setText(f"{win_rate:.1f}%")
            if "avg_win" in self._perf_labels:
                self._perf_labels["avg_win"].setText(self._fmt_currency(avg_win))
            if "avg_loss" in self._perf_labels:
                self._perf_labels["avg_loss"].setText(self._fmt_currency(abs(avg_loss)))
            if "max_win" in self._perf_labels:
                self._perf_labels["max_win"].setText(self._fmt_currency(max_win))
            if "max_loss" in self._perf_labels:
                self._perf_labels["max_loss"].setText(self._fmt_currency(abs(max_loss)))
            if "total_trades" in self._perf_labels:
                self._perf_labels["total_trades"].setText(str(total))

        except Exception as e:
            logger.error(f"[StatusPanel._update_performance_metrics] Failed: {e}")

    def set_connection_status(self, connected: bool):
        """Set connection status indicator"""
        color = GREEN if connected else RED
        self.conn_status.setStyleSheet(f"color: {color}; font-size: 10px;")

    def pause_refresh(self):
        self._refresh_enabled = False

    def resume_refresh(self):
        self._refresh_enabled = True

    def clear_cache(self):
        with self._lock:
            self._last_state.clear()

    def cleanup(self):
        try:
            logger.info("[StatusPanel] Starting cleanup")
            self._closing = True
            self.pause_refresh()
            self.clear_cache()
            self.cards.clear()
            self._recent_trades.clear()
            self._confidence_bars.clear()
            self._mtf_labels.clear()

            if self._market_timer and self._market_timer.isActive():
                self._market_timer.stop()

            logger.info("[StatusPanel] Cleanup completed")
        except Exception as e:
            logger.error(f"[StatusPanel.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)