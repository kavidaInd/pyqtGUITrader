"""
status_panel.py
===============
Enhanced status panel with null-safe operations and state_manager integration.
Fully integrated with ThemeManager for dynamic theming.
"""

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

# Import state manager
from data.trade_state_manager import state_manager

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# StatusCard (YOUR ORIGINAL CARD - NOW THEMED)
# ─────────────────────────────────────────────────────────────────────────────

class StatusCard(QFrame):
    """Single status field with icon label + live value."""

    def __init__(self, icon: str, label: str, parent=None):
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self._dimmed = False

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            layout = QVBoxLayout(self)
            # Margins and spacing will be set in apply_theme

            self._title = QLabel(f"{icon}  {label}")
            self.value_label = QLabel("—")

            self._last_value = None
            self._last_color = None

            layout.addWidget(self._title)
            layout.addWidget(self.value_label)

            # Apply theme initially
            self.apply_theme()

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
        self._last_color = None

    # =========================================================================
    # Shorthand properties for theme tokens
    # =========================================================================
    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the card.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Update layout margins and spacing
            layout = self.layout()
            if layout:
                layout.setContentsMargins(sp.PAD_SM, sp.PAD_XS, sp.PAD_SM, sp.PAD_XS)
                layout.setSpacing(sp.GAP_XS)

            # Update base stylesheet
            self._BASE_SS = f"""
                QFrame {{
                    background: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                    padding: {sp.PAD_XS}px;
                }}
            """

            self._DIM_SS = f"""
                QFrame {{
                    background: {c.BG_ROW_B};
                    border: {sp.SEPARATOR}px solid {c.BORDER_STRONG};
                    border-radius: {sp.RADIUS_MD}px;
                    padding: {sp.PAD_XS}px;
                }}
            """

            # Apply appropriate style based on dimmed state
            self.setStyleSheet(self._DIM_SS if self._dimmed else self._BASE_SS)

            # Update title style
            if self._title:
                dim_col = c.TEXT_DISABLED if self._dimmed else c.TEXT_DIM
                self._title.setStyleSheet(
                    f"color: {dim_col}; border: none; background: transparent; font-size: {ty.SIZE_XS}pt;"
                )

            # Update value label if we have a cached value
            if self._last_value and self._last_color and not self._dimmed:
                self.value_label.setStyleSheet(
                    f"color: {self._last_color}; border: none; background: transparent; font-size: {ty.SIZE_BODY}pt; font-weight: {ty.WEIGHT_BOLD};"
                )
            elif self._dimmed:
                self.value_label.setStyleSheet(
                    f"color: {c.TEXT_DISABLED}; border: none; background: transparent; font-size: {ty.SIZE_BODY}pt;"
                )
            else:
                self.value_label.setStyleSheet(
                    f"color: {c.TEXT_MAIN}; border: none; background: transparent; font-size: {ty.SIZE_BODY}pt; font-weight: {ty.WEIGHT_BOLD};"
                )

        except Exception as e:
            logger.error(f"[StatusCard.apply_theme] Failed: {e}", exc_info=True)

    def set_value(self, text: str, color: str = None):
        try:
            if text is None:
                text = "—"

            if self.value_label is None:
                return

            c = self._c
            if color is None:
                color = c.TEXT_MAIN

            if text == self._last_value and color == self._last_color and not self._dimmed:
                return

            self._last_value = text
            self._last_color = color

            if not self._dimmed:
                self.value_label.setText(text)
                self.value_label.setStyleSheet(
                    f"color: {color}; border: none; background: transparent; font-size: {self._ty.SIZE_BODY}pt; font-weight: {self._ty.WEIGHT_BOLD};"
                )

        except Exception as e:
            logger.error(f"[StatusCard.set_value] Failed: {e}", exc_info=True)

    def set_dimmed(self, dimmed: bool):
        try:
            if dimmed == self._dimmed:
                return

            self._dimmed = dimmed
            self.apply_theme()

            if dimmed:
                self.value_label.setText("—")

        except Exception as e:
            logger.error(f"[StatusCard.set_dimmed] Failed: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# ConfidenceBar - FEATURE 3 (NOW THEMED)
# ─────────────────────────────────────────────────────────────────────────────

class ConfidenceBar(QWidget):
    """FEATURE 3: Confidence bar for signal groups"""

    def __init__(self, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)

            self.label = QLabel("BUY_CALL")
            self.label.setFixedWidth(70)
            layout.addWidget(self.label)

            self.progress = QProgressBar()
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFixedHeight(12)
            self.progress.setTextVisible(False)
            layout.addWidget(self.progress, 1)

            self.value = QLabel("0%")
            self.value.setFixedWidth(40)
            layout.addWidget(self.value)

            # Apply theme initially
            self.apply_theme()

        except Exception as e:
            logger.error(f"[ConfidenceBar.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self.label = None
        self.progress = None
        self.value = None

    # =========================================================================
    # Shorthand properties for theme tokens
    # =========================================================================
    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the confidence bar."""
        try:
            c = self._c
            ty = self._ty

            if self.label:
                self.label.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt;")

            if self.value:
                self.value.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_XS}pt; font-weight: {ty.WEIGHT_BOLD};")

            # Progress bar styling will be updated in set_confidence based on value
        except Exception as e:
            logger.error(f"[ConfidenceBar.apply_theme] Failed: {e}", exc_info=True)

    def set_confidence(self, signal: str, confidence: float, threshold: float = 0.6):
        """Set confidence value for a signal"""
        try:
            c = self._c

            self.label.setText(signal.replace('_', ' '))

            percent = int(confidence * 100)
            self.progress.setValue(percent)
            self.value.setText(f"{percent}%")

            # Color based on threshold
            if confidence >= threshold:
                color = c.GREEN
            elif confidence >= threshold * 0.7:
                color = c.YELLOW_BRIGHT
            else:
                color = c.RED

            self.progress.setStyleSheet(f"""
                QProgressBar::chunk {{ background: {color}; border-radius: {self._sp.RADIUS_SM}px; }}
                QProgressBar {{ border: {self._sp.SEPARATOR}px solid {c.BORDER}; border-radius: {self._sp.RADIUS_SM}px; background: {c.BG_PANEL}; }}
            """)
        except Exception as e:
            logger.error(f"[ConfidenceBar.set_confidence] Failed: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# StatusPanel - ENHANCED WITH ALL FEATURES AND THEME INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

class StatusPanel(QWidget):
    """
    Enhanced status panel with:
    - Signal in its own card
    - Market status connected to Utils
    - FEATURE 1: Risk management display
    - FEATURE 3: Signal confidence bars
    - FEATURE 6: Multi-timeframe filter status

    UPDATED: Now uses state_manager with null-safe operations and ThemeManager.
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

    # Signals
    exit_position_clicked = pyqtSignal()
    modify_sl_clicked = pyqtSignal()
    modify_tp_clicked = pyqtSignal()

    def __init__(self, parent=None):
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

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

            # Cache for snapshots to avoid excessive calls
            self._last_snapshot = {}
            self._last_snapshot_time = datetime.now()
            self._snapshot_cache_duration = 0.1  # 100ms

            # Main layout
            root = QVBoxLayout(self)
            # Margins and spacing will be set in apply_theme

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

            # Apply theme initially
            self.apply_theme()

            logger.info("Enhanced StatusPanel initialized with state_manager integration")

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
        self._last_snapshot = {}
        self._last_snapshot_time = None
        self._snapshot_cache_duration = 0.1

    # =========================================================================
    # Shorthand properties for theme tokens
    # =========================================================================
    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the status panel.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Update root layout margins
            layout = self.layout()
            if layout:
                layout.setContentsMargins(sp.PAD_XS, sp.PAD_XS, sp.PAD_XS, sp.PAD_XS)
                layout.setSpacing(sp.GAP_XS)

            # Update tab widget styling
            if self._tabs:
                self._tabs.setStyleSheet(f"""
                    QTabWidget::pane {{
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_SM}px;
                        background: {c.BG_PANEL};
                    }}
                    QTabBar::tab {{
                        background: {c.BG_HOVER};
                        color: {c.TEXT_DIM};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-bottom: none;
                        border-radius: {sp.RADIUS_SM}px {sp.RADIUS_SM}px 0 0;
                        padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                        font-size: {ty.SIZE_XS}pt;
                        font-weight: {ty.WEIGHT_BOLD};
                        min-width: 100px;
                    }}
                    QTabBar::tab:selected {{
                        background: {c.BG_PANEL};
                        color: {c.TEXT_MAIN};
                        border-bottom: {sp.PAD_XS}px solid {c.BLUE};
                    }}
                    QTabBar::tab:hover:!selected {{
                        background: {c.BORDER};
                    }}
                """)

            # Update header styles
            if self.timestamp:
                self.timestamp.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt;")

            # Update conflict label
            if self.conflict_label:
                self.conflict_label.setStyleSheet(f"color: {c.RED_BRIGHT}; font-size: {ty.SIZE_XS}pt;")

            # Update performance tab styles
            self._update_performance_tab_style()

            # Update MTF tab styles
            self._update_mtf_tab_style()

            # Update all cards
            for card in self.cards.values():
                if hasattr(card, 'apply_theme'):
                    card.apply_theme()

            # Update confidence bars
            for bar in self._confidence_bars.values():
                if hasattr(bar, 'apply_theme'):
                    bar.apply_theme()

            # Update button styles
            if self.exit_btn:
                self.exit_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {c.RED};
                        color: {c.TEXT_INVERSE};
                        border: none;
                        border-radius: {sp.RADIUS_SM}px;
                        padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                        font-size: {ty.SIZE_XS}pt;
                        font-weight: {ty.WEIGHT_BOLD};
                    }}
                    QPushButton:hover {{
                        background: {c.RED_BRIGHT};
                    }}
                    QPushButton:disabled {{
                        background: {c.BG_HOVER};
                        color: {c.TEXT_DISABLED};
                    }}
                """)

            if self.modify_sl_btn or self.modify_tp_btn:
                for btn in [self.modify_sl_btn, self.modify_tp_btn]:
                    if btn:
                        btn.setStyleSheet(f"""
                            QPushButton {{
                                background: {c.BG_HOVER};
                                color: {c.TEXT_MAIN};
                                border: {sp.SEPARATOR}px solid {c.BORDER};
                                border-radius: {sp.RADIUS_SM}px;
                                padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                                font-size: {ty.SIZE_XS}pt;
                                font-weight: {ty.WEIGHT_BOLD};
                            }}
                            QPushButton:hover {{
                                background: {c.BORDER};
                            }}
                            QPushButton:disabled {{
                                color: {c.TEXT_DISABLED};
                            }}
                        """)

            logger.debug("[StatusPanel.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[StatusPanel.apply_theme] Failed: {e}", exc_info=True)

    def _update_performance_tab_style(self):
        """Update styles for performance tab"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Group box style
            group_style = f"""
                QGroupBox {{
                    color: {c.TEXT_MAIN};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                    margin-top: {sp.PAD_MD}px;
                    font-weight: {ty.WEIGHT_BOLD};
                    color: {c.TEXT_MAIN};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: {sp.PAD_SM}px;
                    padding: 0 {sp.PAD_XS}px;
                    color: {c.BLUE};
                }}
            """

            # Table style
            table_style = f"""
                QTableWidget {{
                    background: {c.BG_PANEL};
                    gridline-color: {c.BORDER};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    color: {c.TEXT_MAIN};
                    font-size: {ty.SIZE_XS}pt;
                }}
                QTableWidget::item {{ padding: {sp.PAD_XS}px {sp.PAD_SM}px; }}
                QHeaderView::section {{
                    background: {c.BG_HOVER};
                    color: {c.TEXT_DIM};
                    border: none;
                    border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    font-size: {ty.SIZE_XS}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                }}
            """

            # Apply styles to performance tab widgets
            if hasattr(self, 'today_trades') and self.today_trades:
                self.today_trades.setStyleSheet(f"color: {c.BLUE}; font-weight: {ty.WEIGHT_BOLD};")
            if hasattr(self, 'today_wins') and self.today_wins:
                self.today_wins.setStyleSheet(f"color: {c.GREEN}; font-weight: {ty.WEIGHT_BOLD};")
            if hasattr(self, 'today_losses') and self.today_losses:
                self.today_losses.setStyleSheet(f"color: {c.RED}; font-weight: {ty.WEIGHT_BOLD};")

            if hasattr(self, 'recent_table') and self.recent_table:
                self.recent_table.setStyleSheet(table_style)

        except Exception as e:
            logger.error(f"[StatusPanel._update_performance_tab_style] Failed: {e}", exc_info=True)

    def _update_mtf_tab_style(self):
        """Update styles for MTF tab"""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            group_style = f"""
                QGroupBox {{
                    color: {c.TEXT_MAIN};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                    margin-top: {sp.PAD_MD}px;
                    font-weight: {ty.WEIGHT_BOLD};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: {sp.PAD_SM}px;
                    padding: 0 {sp.PAD_XS}px;
                    color: {c.BLUE};
                }}
            """

            # Update MTF labels with default color
            if hasattr(self, 'mtf_1m') and self.mtf_1m:
                self.mtf_1m.setStyleSheet(f"color: {c.TEXT_DIM}; font-weight: {ty.WEIGHT_BOLD};")
            if hasattr(self, 'mtf_5m') and self.mtf_5m:
                self.mtf_5m.setStyleSheet(f"color: {c.TEXT_DIM}; font-weight: {ty.WEIGHT_BOLD};")
            if hasattr(self, 'mtf_15m') and self.mtf_15m:
                self.mtf_15m.setStyleSheet(f"color: {c.TEXT_DIM}; font-weight: {ty.WEIGHT_BOLD};")

            # Summary label
            if hasattr(self, 'mtf_summary') and self.mtf_summary:
                self.mtf_summary.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt;")

        except Exception as e:
            logger.error(f"[StatusPanel._update_mtf_tab_style] Failed: {e}", exc_info=True)

    def _create_header(self) -> QWidget:
        """Create header with timestamp and market status from Utils"""
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.conn_status = QLabel("●")
        self.conn_status.setStyleSheet(f"color: {self._c.RED}; font-size: {self._ty.SIZE_MD}pt;")
        header_layout.addWidget(self.conn_status)

        self.timestamp = QLabel(datetime.now().strftime("%H:%M:%S"))
        header_layout.addWidget(self.timestamp)

        header_layout.addStretch()

        # Market status from Utils
        self.market_status = QLabel()
        self._update_market_status_display()
        header_layout.addWidget(self.market_status)

        return header

    def _get_cached_snapshot(self) -> Dict[str, Any]:
        """Get cached snapshot to avoid excessive state_manager calls"""
        now = datetime.now()
        if self._last_snapshot_time is None or (now - self._last_snapshot_time).total_seconds() > self._snapshot_cache_duration:
            self._last_snapshot = state_manager.get_snapshot()
            self._last_position_snapshot = state_manager.get_position_snapshot()
            self._last_snapshot_time = now
        return self._last_snapshot

    def _get_cached_position_snapshot(self) -> Dict[str, Any]:
        """Get cached position snapshot (always in sync with _get_cached_snapshot)"""
        # Ensure the cache is populated first
        self._get_cached_snapshot()
        return getattr(self, '_last_position_snapshot', {})

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
            c = self._c
            if self._is_holiday:
                self.market_status.setText("Market: Holiday")
                self.market_status.setStyleSheet(f"color: {c.TEXT_DISABLED}; font-size: {self._ty.SIZE_XS}pt;")
            elif self._market_open:
                self.market_status.setText("Market: Open")
                self.market_status.setStyleSheet(f"color: {c.GREEN}; font-size: {self._ty.SIZE_XS}pt;")
            else:
                self.market_status.setText("Market: Closed")
                self.market_status.setStyleSheet(f"color: {c.RED}; font-size: {self._ty.SIZE_XS}pt;")
        except Exception as e:
            logger.error(f"[StatusPanel._update_market_status_display] Failed: {e}")

    def _create_trade_tab(self):
        """Tab 1: Trade Status - YOUR CARD LAYOUT"""
        trade_tab = QWidget()
        trade_layout = QVBoxLayout(trade_tab)
        trade_layout.setContentsMargins(self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS)
        trade_layout.setSpacing(self._sp.GAP_SM)

        # YOUR ORIGINAL CARD GRID - 2 columns, 6 rows (now with new cards)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(self._sp.GAP_XS)
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
        button_layout.setSpacing(self._sp.GAP_XS)

        self.exit_btn = QPushButton("Exit")
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
        layout.setContentsMargins(self._sp.PAD_SM, self._sp.PAD_SM, self._sp.PAD_SM, self._sp.PAD_SM)
        layout.setSpacing(self._sp.GAP_MD)

        # Today's summary
        today_group = QGroupBox("Today")
        today_layout = QGridLayout()
        today_layout.setSpacing(self._sp.GAP_XS)

        today_layout.addWidget(QLabel("Trades:"), 0, 0)
        self.today_trades = QLabel("0")
        today_layout.addWidget(self.today_trades, 0, 1)

        today_layout.addWidget(QLabel("Wins:"), 0, 2)
        self.today_wins = QLabel("0")
        today_layout.addWidget(self.today_wins, 0, 3)

        today_layout.addWidget(QLabel("Losses:"), 0, 4)
        self.today_losses = QLabel("0")
        today_layout.addWidget(self.today_losses, 0, 5)

        today_layout.addWidget(QLabel("P&L:"), 1, 0)
        self.today_pnl = QLabel("₹0")
        today_layout.addWidget(self.today_pnl, 1, 1, 1, 5)

        today_group.setLayout(today_layout)
        layout.addWidget(today_group)

        # Performance stats
        perf_group = QGroupBox("Stats")
        perf_layout = QFormLayout()
        perf_layout.setSpacing(self._sp.GAP_XS)
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
        layout.setContentsMargins(self._sp.PAD_SM, self._sp.PAD_SM, self._sp.PAD_SM, self._sp.PAD_SM)
        layout.setSpacing(self._sp.GAP_SM)

        # Explanation label
        self.conf_explanation = QLabel("No signal evaluation yet")
        self.conf_explanation.setWordWrap(True)
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
        layout.setContentsMargins(self._sp.PAD_SM, self._sp.PAD_SM, self._sp.PAD_SM, self._sp.PAD_SM)
        layout.setSpacing(self._sp.GAP_SM)

        # Status group
        status_group = QGroupBox("MTF Filter Status")
        status_layout = QFormLayout()
        status_layout.setSpacing(self._sp.GAP_XS)

        self.mtf_enabled = QLabel("Disabled")
        status_layout.addRow("Enabled:", self.mtf_enabled)

        self.mtf_decision = QLabel("No decision")
        status_layout.addRow("Last Decision:", self.mtf_decision)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Timeframe directions
        tf_group = QGroupBox("Timeframe Directions")
        tf_layout = QFormLayout()
        tf_layout.setSpacing(self._sp.GAP_XS)

        self.mtf_1m = QLabel("NEUTRAL")
        tf_layout.addRow("1 Minute:", self.mtf_1m)

        self.mtf_5m = QLabel("NEUTRAL")
        tf_layout.addRow("5 Minute:", self.mtf_5m)

        self.mtf_15m = QLabel("NEUTRAL")
        tf_layout.addRow("15 Minute:", self.mtf_15m)

        self.mtf_agreement = QLabel("0/3")
        tf_layout.addRow("Agreement:", self.mtf_agreement)

        tf_group.setLayout(tf_layout)
        layout.addWidget(tf_group)

        # Summary
        summary_group = QGroupBox("Summary")
        summary_layout = QVBoxLayout()
        self.mtf_summary = QLabel("No MTF evaluation yet")
        self.mtf_summary.setWordWrap(True)
        summary_layout.addWidget(self.mtf_summary)
        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)

        layout.addStretch()
        self._tabs.addTab(mtf_tab, "📈 MTF Filter")

    def _create_positions_tab(self):
        """Tab 5: Active positions"""
        pos_tab = QWidget()
        layout = QVBoxLayout(pos_tab)
        layout.setContentsMargins(self._sp.PAD_SM, self._sp.PAD_SM, self._sp.PAD_SM, self._sp.PAD_SM)

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
        layout.setContentsMargins(self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD)
        layout.setSpacing(self._sp.GAP_SM)
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
            layout.addRow(QLabel(label), value_label)
            self._account_labels[key] = value_label

        self._tabs.addTab(account_tab, "🏦 Account")

    # ── Private helpers with null-safe operations ──────────────────────────

    def _safe_get_float(self, snap: Dict[str, Any], key: str, default: float = 0.0) -> float:
        """Safely get float value from snapshot"""
        try:
            value = snap.get(key)
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    def _safe_get_str(self, snap: Dict[str, Any], key: str, default: str = "") -> str:
        """Safely get string value from snapshot"""
        try:
            value = snap.get(key)
            if value is None:
                return default
            return str(value)
        except Exception:
            return default

    def _safe_get_bool(self, snap: Dict[str, Any], key: str, default: bool = False) -> bool:
        """Safely get boolean value from snapshot"""
        try:
            value = snap.get(key)
            if value is None:
                return default
            return bool(value)
        except Exception:
            return default

    def _safe_get_dict(self, snap: Dict[str, Any], key: str, default: Dict = None) -> Dict:
        """Safely get dictionary value from snapshot"""
        if default is None:
            default = {}
        try:
            value = snap.get(key)
            if value is None:
                return default
            if isinstance(value, dict):
                return value
            return default
        except Exception:
            return default

    def _safe_upper(self, text: Optional[str]) -> str:
        """Safely convert to uppercase"""
        if text is None:
            return ""
        try:
            return str(text).upper()
        except Exception:
            return ""

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
            val = float(value)
            if abs(val) >= 1000:
                return f"₹{val:,.0f}"
            return f"₹{val:.2f}"
        except (ValueError, TypeError):
            return str(value) if value else "—"

    def _fmt_percent(self, value: Any) -> str:
        try:
            if value is None:
                return "—"
            val = float(value)
            return f"{val:+.1f}%"
        except (ValueError, TypeError):
            return str(value) if value else "—"

    def _pnl_color(self, pnl: Any) -> str:
        try:
            if pnl is None:
                return self._c.TEXT_DIM
            v = float(pnl)
            if v > 0:
                return self._c.GREEN
            if v < 0:
                return self._c.RED
            return self._c.TEXT_DIM
        except Exception:
            return self._c.TEXT_DIM

    def _pos_color(self, pos: Any) -> str:
        try:
            if pos and str(pos).upper() in ("LONG", "SHORT", "CALL", "PUT"):
                return self._c.GREEN
            return self._c.TEXT_DIM
        except Exception:
            return self._c.TEXT_DIM

    def _signal_color(self, signal: str) -> str:
        """Get color for signal"""
        c = self._c
        colors = {
            "BUY_CALL": c.GREEN,
            "BUY_PUT": c.BLUE,
            "EXIT_CALL": c.RED,
            "EXIT_PUT": c.ORANGE,
            "HOLD": c.YELLOW,
            "WAIT": c.TEXT_DISABLED
        }
        if signal is None:
            return c.TEXT_DISABLED
        return colors.get(signal, c.TEXT_DISABLED)

    def _trade_open(self, snap: Dict[str, Any]) -> bool:
        """Check if trade is open from snapshot"""
        try:
            pos = snap.get('current_position')
            if pos is None:
                return False
            pos_str = str(pos).upper()
            return pos_str not in ("NONE", "")
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

    def refresh(self, config=None):
        """
        Refresh all tabs with current state from state_manager.

        Args:
            config: Optional config object (kept for backward compatibility)
        """
        if self._closing or not self._refresh_enabled:
            return

        try:
            # Update timestamp
            self.timestamp.setText(datetime.now().strftime("%H:%M:%S"))

            # Get snapshots
            full_snap = self._get_cached_snapshot()
            pos_snap = self._get_cached_position_snapshot()
            # Get signal snapshot safely
            try:
                signal_snap = state_manager.get_state().get_option_signal_snapshot()
            except Exception:
                signal_snap = {}

            # Get values from snapshots with null-safe operations
            pos = full_snap.get('current_position')
            symbol = full_snap.get('current_trading_symbol')
            buy_price = self._safe_get_float(pos_snap, 'current_buy_price', None)
            cur_price = self._safe_get_float(pos_snap, 'current_price', None)
            tp = self._safe_get_float(pos_snap, 'tp_point', None)
            sl = self._safe_get_float(pos_snap, 'stop_loss', None)
            pnl_pct = self._safe_get_float(pos_snap, 'percentage_change', None)
            pnl_abs = self._safe_get_float(pos_snap, 'current_pnl', None)
            balance = self._safe_get_float(full_snap, 'account_balance', 0.0)
            deriv = self._safe_get_float(full_snap, 'derivative_current_price', 0.0)
            lots = self._safe_get_float(full_snap, 'positions_hold', 0)

            # Get signal
            signal = self._safe_get_str(pos_snap, 'option_signal', 'WAIT')
            conflict = self._safe_get_bool(pos_snap, 'signal_conflict', False)

            # Update trade active state
            trade_active = self._trade_open(full_snap)
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
                    self.conflict_label.setVisible(True)
                else:
                    self.conflict_label.setVisible(False)

            # Update always-visible cards
            self._set_card("position", str(pos) if pos else "None", self._pos_color(pos))
            self._set_card("balance", self._fmt_currency(balance), self._c.TEXT_MAIN)
            self._set_card("derivative", self._fmt(deriv), self._c.BLUE)

            # Update trade-specific cards
            if trade_active:
                self._set_card("symbol", str(symbol) if symbol else "—", self._c.TEXT_MAIN)
                self._set_card("buy_price", self._fmt(buy_price), self._c.TEXT_MAIN)
                self._set_card("current_price", self._fmt(cur_price), self._c.TEXT_MAIN)
                self._set_card("target_price", self._fmt(tp), self._c.GREEN)
                self._set_card("stoploss_price", self._fmt(sl), self._c.RED)

                pnl_txt = self._fmt_percent(pnl_pct) if pnl_pct is not None else "—"
                self._set_card("pnl", pnl_txt, self._pnl_color(pnl_pct))

            # Update positions table
            self._update_positions_table(trade_active, symbol, pos, int(lots) if lots else 0, pnl_abs)

            # Update account tab
            if "balance" in self._account_labels:
                self._account_labels["balance"].setText(self._fmt_currency(balance))
            if "open_positions" in self._account_labels:
                self._account_labels["open_positions"].setText(str(1 if trade_active else 0))
            if "m2m" in self._account_labels:
                self._account_labels["m2m"].setText(self._fmt_currency(pnl_abs))

            # FEATURE 1: Update risk cards (with null-safe operations)
            self._update_risk_cards(full_snap, pos_snap)

            # FEATURE 3: Update confidence tab
            self._update_confidence_tab(signal_snap, pos_snap)

            # FEATURE 6: Update MTF tab (with null-safe operations)
            self._update_mtf_tab(full_snap, pos_snap)

        except Exception as e:
            logger.error(f"StatusPanel.refresh error: {e}", exc_info=True)

    def _update_risk_cards(self, full_snap: Dict, pos_snap: Dict):
        """
        FEATURE 1: Update risk management cards with null-safe operations.
        """
        try:
            c = self._c

            # Get daily P&L with null-safe conversion
            daily_pnl = self._safe_get_float(pos_snap, 'current_pnl', 0.0)

            # Count trades today (would need to track this separately)
            trades_today = 1 if self._trade_open(full_snap) else 0

            # Update cards with safe color determination
            if "daily_pnl" in self.cards:
                if daily_pnl > 0:
                    pnl_color = c.GREEN
                elif daily_pnl < 0:
                    pnl_color = c.RED
                else:
                    pnl_color = c.TEXT_MAIN
                self.cards["daily_pnl"].set_value(self._fmt_currency(daily_pnl), pnl_color)

            if "trades_today" in self.cards:
                self.cards["trades_today"].set_value(str(trades_today), c.TEXT_MAIN)

        except Exception as e:
            logger.error(f"[StatusPanel._update_risk_cards] Failed: {e}", exc_info=True)

    def _update_confidence_tab(self, signal_snap: Dict, pos_snap: Dict):
        """
        FEATURE 3: Update confidence tab
        """
        try:
            c = self._c
            confidence = self._safe_get_dict(signal_snap, 'confidence')
            explanation = self._safe_get_str(signal_snap, 'explanation', "No signal evaluation yet")
            threshold = self._safe_get_float(signal_snap, 'threshold', 0.6)

            # Update explanation
            if hasattr(self, 'conf_explanation') and self.conf_explanation:
                self.conf_explanation.setText(explanation)
                self.conf_explanation.setStyleSheet(
                    f"color: {c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt; padding: {self._sp.PAD_SM}px; background: {c.BG_PANEL}; border: {self._sp.SEPARATOR}px solid {c.BORDER}; border-radius: {self._sp.RADIUS_SM}px;")

            # Update threshold
            threshold_pct = int(threshold * 100)
            self.threshold_label.setText(f"Min Confidence: {threshold_pct}%")
            self.threshold_label.setStyleSheet(f"color: {c.YELLOW_BRIGHT}; font-weight: {self._ty.WEIGHT_BOLD};")

            # Update confidence bars
            for signal, bar in self._confidence_bars.items():
                conf = confidence.get(signal, 0.0)
                bar.set_confidence(signal, conf, threshold)

        except Exception as e:
            logger.error(f"[StatusPanel._update_confidence_tab] Failed: {e}", exc_info=True)

    def _update_mtf_tab(self, full_snap: Dict, pos_snap: Dict):
        """
        FEATURE 6: Update MTF filter tab with null-safe operations.
        """
        try:
            c = self._c

            # Get MTF results from state with safe dict access
            mtf_results = self._safe_get_dict(full_snap, 'mtf_results')

            # Update timeframe directions with safe string conversion
            self.mtf_1m.setText(self._safe_get_str(mtf_results, '1', 'NEUTRAL'))
            self.mtf_5m.setText(self._safe_get_str(mtf_results, '5', 'NEUTRAL'))
            self.mtf_15m.setText(self._safe_get_str(mtf_results, '15', 'NEUTRAL'))

            # Color based on direction
            self._set_mtf_direction_color(self.mtf_1m, self._safe_get_str(mtf_results, '1', 'NEUTRAL'))
            self._set_mtf_direction_color(self.mtf_5m, self._safe_get_str(mtf_results, '5', 'NEUTRAL'))
            self._set_mtf_direction_color(self.mtf_15m, self._safe_get_str(mtf_results, '15', 'NEUTRAL'))

            # Count agreement
            target = 'BULLISH' if self._safe_get_str(pos_snap, 'option_signal', '') == 'BUY_CALL' else 'BEARISH'
            matches = sum(1 for d in mtf_results.values() if d == target)
            self.mtf_agreement.setText(f"{matches}/3")

            # Update enabled status
            mtf_allowed = self._safe_get_bool(full_snap, 'mtf_allowed', True)
            self.mtf_enabled.setText("Yes" if mtf_allowed else "No")
            self.mtf_enabled.setStyleSheet(f"color: {c.GREEN if mtf_allowed else c.RED}; font-weight: {self._ty.WEIGHT_BOLD};")

            # Update decision with safe upper conversion
            summary = self._safe_get_str(full_snap, 'last_mtf_summary', 'No MTF evaluation yet')
            self.mtf_summary.setText(summary)

            # Color based on decision (using safe upper)
            summary_upper = self._safe_upper(summary)
            if "ALLOWED" in summary_upper:
                self.mtf_decision.setText("ALLOWED")
                self.mtf_decision.setStyleSheet(f"color: {c.GREEN}; font-weight: {self._ty.WEIGHT_BOLD};")
            elif "BLOCKED" in summary_upper:
                self.mtf_decision.setText("BLOCKED")
                self.mtf_decision.setStyleSheet(f"color: {c.RED}; font-weight: {self._ty.WEIGHT_BOLD};")
            else:
                self.mtf_decision.setText(summary)
                self.mtf_decision.setStyleSheet(f"color: {c.TEXT_DIM}; font-weight: {self._ty.WEIGHT_BOLD};")

        except Exception as e:
            logger.error(f"[StatusPanel._update_mtf_tab] Failed: {e}", exc_info=True)

    def _set_mtf_direction_color(self, label: QLabel, direction: str):
        """Set color for MTF direction label"""
        c = self._c
        if direction == 'BULLISH':
            label.setStyleSheet(f"color: {c.GREEN}; font-weight: {self._ty.WEIGHT_BOLD};")
        elif direction == 'BEARISH':
            label.setStyleSheet(f"color: {c.RED}; font-weight: {self._ty.WEIGHT_BOLD};")
        else:
            label.setStyleSheet(f"color: {c.TEXT_DISABLED}; font-weight: {self._ty.WEIGHT_BOLD};")

    def _update_positions_table(self, trade_active: bool, symbol: str, pos: str,
                                lots: int, pnl: float):
        """Update positions table"""
        try:
            c = self._c
            self.positions_table.setRowCount(0)

            if trade_active and symbol:
                self.positions_table.insertRow(0)
                self.positions_table.setItem(0, 0, QTableWidgetItem(str(symbol)))
                self.positions_table.setItem(0, 1, QTableWidgetItem(str(pos) if pos else "—"))
                self.positions_table.setItem(0, 2, QTableWidgetItem(f"{lots}"))

                pnl_item = QTableWidgetItem(self._fmt_currency(pnl))
                color = c.GREEN if pnl and pnl > 0 else c.RED if pnl and pnl < 0 else c.TEXT_MAIN
                pnl_item.setForeground(QColor(color))
                self.positions_table.setItem(0, 3, pnl_item)
        except Exception as e:
            logger.error(f"[StatusPanel._update_positions_table] Failed: {e}")

    def add_recent_trade(self, trade_data: Dict):
        """Add a completed trade to recent list"""
        try:
            c = self._c
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
            pnl_item.setForeground(QColor(c.GREEN if pnl > 0 else c.RED))
            self.recent_table.setItem(row, 2, pnl_item)

            # Update performance metrics
            self._update_performance_metrics()

        except Exception as e:
            logger.error(f"[StatusPanel.add_recent_trade] Failed: {e}")

    def _update_performance_metrics(self):
        """Update performance metrics from trade history"""
        try:
            c = self._c

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

            color = c.GREEN if today_pnl > 0 else c.RED if today_pnl < 0 else c.BLUE
            self.today_pnl.setStyleSheet(f"color: {color}; font-weight: {self._ty.WEIGHT_BOLD};")

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
        color = self._c.GREEN if connected else self._c.RED
        self.conn_status.setStyleSheet(f"color: {color}; font-size: {self._ty.SIZE_MD}pt;")

    def pause_refresh(self):
        self._refresh_enabled = False

    def resume_refresh(self):
        self._refresh_enabled = True

    def clear_cache(self):
        with self._lock:
            self._last_state.clear()
            self._last_snapshot = {}
            self._last_snapshot_time = datetime.now()

    def cleanup(self):
        try:
            logger.info("[StatusPanel] Starting cleanup")
            self._closing = True
            self.pause_refresh()
            self.clear_cache()
            self.cards.clear()
            self._recent_trades.clear()
            self._confidence_bars.clear()

            if self._market_timer and self._market_timer.isActive():
                self._market_timer.stop()

            logger.info("[StatusPanel] Cleanup completed")
        except Exception as e:
            logger.error(f"[StatusPanel.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)