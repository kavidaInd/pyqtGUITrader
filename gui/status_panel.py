"""
gui/status_panel.py
--------------------
Right-panel status sidebar for the trading dashboard.

Design
──────
• Cards are placed inside a QScrollArea so nothing ever falls off-screen,
  regardless of window height or font scaling.
• The card grid uses a single-column layout (not 2-up) so every label and
  value is always fully readable without horizontal scrolling.
• Trade-only cards are dimmed (not hidden) when no position is open — they
  stay visible as placeholders so the layout never jumps.
• The header row is always visible above the scroll area.
• Tab-switch gets a cursor change + disabled-during-refresh guard so the user
  always gets feedback.
• All colours / sizes come exclusively from theme_manager.

Public interface (unchanged from original)
──────────────────────────────────────────
  .refresh(config=None)
  .set_connection_status(connected: bool)
  .pause_refresh() / .resume_refresh()
  .clear_cache()
  .cleanup()
  Signals: exit_position_clicked, modify_sl_clicked, modify_tp_clicked
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

from Utils.Utils import Utils
from Utils.safe_getattr import safe_getattr, safe_hasattr
from data.trade_state_manager import state_manager
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# StatusCard  — single metric tile
# ─────────────────────────────────────────────────────────────────────────────

class StatusCard(QFrame):
    """
    One metric tile with an icon+label header row and a large value row.
    Single-column — never truncates its text.
    """

    def __init__(self, icon: str, label: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._dimmed = False
        self._last_value: Optional[str] = None
        self._last_color: Optional[str] = None

        lay = QVBoxLayout(self)

        self._title = QLabel(f"{icon}  {label}")
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.value_label = QLabel("—")
        self.value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.value_label.setWordWrap(True)

        lay.addWidget(self._title)
        lay.addWidget(self.value_label)

        theme_manager.theme_changed.connect(self.apply_theme)
        theme_manager.density_changed.connect(self.apply_theme)
        self.apply_theme()

    # ── theme shortcuts ───────────────────────────────────────────────────────
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
        try:
            c, ty, sp = self._c, self._ty, self._sp
            lay = self.layout()
            if lay:
                lay.setContentsMargins(sp.PAD_SM, sp.PAD_XS, sp.PAD_SM, sp.PAD_XS)
                lay.setSpacing(sp.GAP_XS)

            # Card background
            if self._dimmed:
                self.setStyleSheet(f"""
                    QFrame {{
                        background: {c.BG_ROW_B};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                    }}
                """)
                dim = c.TEXT_DISABLED
                self._title.setStyleSheet(
                    f"color: {dim}; font-size: {ty.SIZE_XS}pt; "
                    f"background: transparent; border: none;"
                )
                self.value_label.setStyleSheet(
                    f"color: {dim}; font-size: {ty.SIZE_SM}pt; "
                    f"background: transparent; border: none;"
                )
            else:
                self.setStyleSheet(f"""
                    QFrame {{
                        background: {c.BG_PANEL};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                    }}
                    QFrame:hover {{
                        border-color: {c.BORDER_STRONG};
                    }}
                """)
                self._title.setStyleSheet(
                    f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; "
                    f"background: transparent; border: none; "
                    f"letter-spacing: 0.3px;"
                )
                # Restore cached value colour
                col = self._last_color or c.TEXT_MAIN
                self.value_label.setStyleSheet(
                    f"color: {col}; font-size: {ty.SIZE_BODY}pt; "
                    f"font-weight: {ty.WEIGHT_BOLD}; "
                    f"background: transparent; border: none;"
                )
        except Exception as exc:
            logger.debug(f"[StatusCard.apply_theme] {exc}")

    def set_value(self, text: str, color: Optional[str] = None) -> None:
        try:
            if text is None:
                text = "—"
            c = self._c
            ty = self._ty
            color = color or c.TEXT_MAIN

            if text == self._last_value and color == self._last_color:
                return
            self._last_value = text
            self._last_color = color

            self.value_label.setText(text)
            if not self._dimmed:
                self.value_label.setStyleSheet(
                    f"color: {color}; font-size: {ty.SIZE_BODY}pt; "
                    f"font-weight: {ty.WEIGHT_BOLD}; "
                    f"background: transparent; border: none;"
                )
        except Exception as exc:
            logger.debug(f"[StatusCard.set_value] {exc}")

    def set_dimmed(self, dimmed: bool) -> None:
        if dimmed == self._dimmed:
            return
        self._dimmed = dimmed
        self.apply_theme()
        if dimmed:
            self.value_label.setText("—")


# ─────────────────────────────────────────────────────────────────────────────
# StatusPanel
# ─────────────────────────────────────────────────────────────────────────────

class StatusPanel(QWidget):
    """
    Right-side status panel.
    • Single-column card list in a scroll area — never clips any content.
    • Header (connection dot + clock + market badge) always visible.
    • Two tabs: Trade (live metrics) and Account (fund summary).
    """

    # Cards that only make sense when a position is open
    _TRADE_ONLY: Set[str] = frozenset({
        "symbol", "buy_price", "current_price",
        "target_price", "stoploss_price", "pnl",
    })

    FIELDS: List[tuple] = [
        # Key         Icon   Label
        ("position", "🟢", "Position"),
        ("signal", "📊", "Signal"),
        ("balance", "🏦", "Balance"),
        ("derivative", "📈", "Index"),
        ("daily_pnl", "📉", "Daily P&L"),
        ("trades_today", "🎯", "Trades"),
        # Trade-specific
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

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._lock = threading.RLock()
        self._last_state: Dict[str, str] = {}
        self._refresh_enabled = True
        self._trade_active = False
        self._closing = False
        self._recent_trades: List[Dict] = []
        self._market_open = Utils.is_market_open()
        self._is_holiday = Utils.is_today_holiday()
        self._snapshot_ts: Optional[datetime] = None
        self._snapshot: dict = {}
        self._pos_snapshot: dict = {}

        # Width — wide enough to show all text, constrained to not dominate
        self.setMinimumWidth(220)
        self.setMaximumWidth(320)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )

        # Main layout
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 1. Fixed header (connection, clock, market)
        root.addWidget(self._build_header())

        # 2. Tab widget — fills remaining space
        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self._tabs, 1)

        self._build_trade_tab()
        self._build_account_tab()

        # Theme
        theme_manager.theme_changed.connect(self.apply_theme)
        theme_manager.density_changed.connect(self.apply_theme)
        self.apply_theme()

        # Market-status refresh (every minute)
        self._market_timer = QTimer()
        self._market_timer.timeout.connect(self._refresh_market_status)
        self._market_timer.start(60_000)

        logger.info("[StatusPanel] Initialized")

    # ── theme shortcuts ───────────────────────────────────────────────────────
    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    # ── theme application ─────────────────────────────────────────────────────

    def apply_theme(self, _: str = None) -> None:
        try:
            c, ty, sp = self._c, self._ty, self._sp

            self.setStyleSheet(f"""
                QWidget {{
                    background: {c.BG_MAIN};
                }}
            """)

            self._tabs.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    background: {c.BG_MAIN};
                }}
                QTabBar::tab {{
                    background:  {c.BG_PANEL};
                    color:       {c.TEXT_DIM};
                    border:      {sp.SEPARATOR}px solid {c.BORDER};
                    border-bottom: none;
                    padding:     {sp.PAD_XS}px {sp.PAD_MD}px;
                    font-size:   {ty.SIZE_XS}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                    min-width:   80px;
                }}
                QTabBar::tab:selected {{
                    background:   {c.BG_MAIN};
                    color:        {c.TEXT_MAIN};
                    border-bottom: 2px solid {c.BLUE};
                }}
                QTabBar::tab:hover:!selected {{
                    background: {c.BG_HOVER};
                    color:      {c.TEXT_MAIN};
                }}
            """)

            # Header labels
            if hasattr(self, "timestamp"):
                self.timestamp.setStyleSheet(
                    f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; "
                    f"background: transparent; border: none;"
                )
            if hasattr(self, "conflict_label"):
                self.conflict_label.setStyleSheet(
                    f"color: {c.RED_BRIGHT}; font-size: {ty.SIZE_XS}pt; "
                    f"background: transparent; border: none;"
                )

            # Cards
            for card in self.cards.values():
                card.apply_theme()

            # Buttons
            self._style_action_buttons()

        except Exception as exc:
            logger.error(f"[StatusPanel.apply_theme] {exc}", exc_info=True)

    def _style_action_buttons(self) -> None:
        c, ty, sp = self._c, self._ty, self._sp
        base_btn = f"""
            QPushButton {{
                background: {c.BG_HOVER};
                color:       {c.TEXT_MAIN};
                border:      {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
                padding:     {sp.PAD_XS}px {sp.PAD_MD}px;
                font-size:   {ty.SIZE_SM}pt;
                font-weight: {ty.WEIGHT_BOLD};
                min-height:  {sp.BTN_HEIGHT_SM}px;
            }}
            QPushButton:hover    {{ background: {c.BORDER}; }}
            QPushButton:disabled {{ color: {c.TEXT_DISABLED}; border-color: {c.BORDER}; }}
        """
        exit_btn_ss = f"""
            QPushButton {{
                background: {c.RED};
                color:       {c.TEXT_INVERSE};
                border:      none;
                border-radius: {sp.RADIUS_SM}px;
                padding:     {sp.PAD_XS}px {sp.PAD_MD}px;
                font-size:   {ty.SIZE_SM}pt;
                font-weight: {ty.WEIGHT_BOLD};
                min-height:  {sp.BTN_HEIGHT_SM}px;
            }}
            QPushButton:hover    {{ background: {c.RED_BRIGHT}; }}
            QPushButton:disabled {{ background: {c.BG_HOVER}; color: {c.TEXT_DISABLED}; }}
        """
        if hasattr(self, "exit_btn") and self.exit_btn:
            self.exit_btn.setStyleSheet(exit_btn_ss)
        for btn in (
                getattr(self, "modify_sl_btn", None),
                getattr(self, "modify_tp_btn", None),
        ):
            if btn:
                btn.setStyleSheet(base_btn)

    # ── header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        c, ty, sp = self._c, self._ty, self._sp
        hdr = QFrame()
        hdr.setFixedHeight(sp.HEADER_H)
        hdr.setStyleSheet(f"""
            QFrame {{
                background:    {c.BG_PANEL};
                border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
            }}
        """)
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(sp.PAD_SM, 0, sp.PAD_SM, 0)
        lay.setSpacing(sp.GAP_SM)

        self.conn_status = QLabel("●")
        self.conn_status.setStyleSheet(
            f"color: {c.RED}; font-size: {ty.SIZE_MD}pt; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(self.conn_status)

        self.timestamp = QLabel(datetime.now().strftime("%H:%M:%S"))
        self.timestamp.setStyleSheet(
            f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(self.timestamp)
        lay.addStretch()

        self.market_status = QLabel()
        self._update_market_status_display()
        lay.addWidget(self.market_status)

        return hdr

    # ── trade tab ─────────────────────────────────────────────────────────────

    def _build_trade_tab(self) -> None:
        sp = self._sp

        tab = QWidget()
        tab_lay = QVBoxLayout(tab)
        tab_lay.setContentsMargins(0, 0, 0, 0)
        tab_lay.setSpacing(0)

        # Scroll area — cards live inside here
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)
        inner_lay.setSpacing(sp.GAP_SM)

        self.cards: Dict[str, StatusCard] = {}
        for key, icon, label in self.FIELDS:
            card = StatusCard(icon, label)
            inner_lay.addWidget(card)
            self.cards[key] = card

        inner_lay.addStretch()
        scroll.setWidget(inner)
        tab_lay.addWidget(scroll, 1)

        # Conflict indicator (above action buttons, outside scroll)
        self.conflict_label = QLabel("")
        self.conflict_label.setAlignment(Qt.AlignCenter)
        self.conflict_label.setVisible(False)
        tab_lay.addWidget(self.conflict_label)

        # Action buttons row
        btn_row = QWidget()
        btn_lay = QHBoxLayout(btn_row)
        btn_lay.setContentsMargins(sp.PAD_SM, sp.PAD_XS, sp.PAD_SM, sp.PAD_SM)
        btn_lay.setSpacing(sp.GAP_SM)

        self.exit_btn = QPushButton("Exit Position")
        self.exit_btn.setEnabled(False)
        self.exit_btn.clicked.connect(self.exit_position_clicked.emit)
        btn_lay.addWidget(self.exit_btn, 2)

        self.modify_sl_btn = QPushButton("SL")
        self.modify_sl_btn.setEnabled(False)
        self.modify_sl_btn.clicked.connect(self.modify_sl_clicked.emit)
        btn_lay.addWidget(self.modify_sl_btn, 1)

        self.modify_tp_btn = QPushButton("TP")
        self.modify_tp_btn.setEnabled(False)
        self.modify_tp_btn.clicked.connect(self.modify_tp_clicked.emit)
        btn_lay.addWidget(self.modify_tp_btn, 1)

        tab_lay.addWidget(btn_row)

        # Start with trade-only cards dimmed
        for key in self._TRADE_ONLY:
            if key in self.cards:
                self.cards[key].set_dimmed(True)

        self._tabs.addTab(tab, "📊 Trade")

    # ── account tab ───────────────────────────────────────────────────────────

    def _build_account_tab(self) -> None:
        sp = self._sp
        c, ty = self._c, self._ty

        tab = QWidget()
        lay = QFormLayout(tab)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_SM)
        lay.setLabelAlignment(Qt.AlignLeft)

        label_ss = (
            f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt; "
            f"background: transparent; border: none;"
        )
        value_ss = (
            f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_SM}pt; "
            f"font-weight: {ty.WEIGHT_BOLD}; "
            f"background: transparent; border: none;"
        )

        fields = [
            ("Balance", "balance", "₹0"),
            ("Margin", "margin", "₹0"),
            ("Buying Power", "buying_power", "₹0"),
            ("M2M", "m2m", "₹0"),
            ("Day Trades", "day_trades", "0"),
            ("Open Pos", "open_positions", "0"),
        ]

        self._account_labels: Dict[str, QLabel] = {}
        for lbl_text, key, default in fields:
            lbl = QLabel(lbl_text + ":")
            lbl.setStyleSheet(label_ss)
            val = QLabel(default)
            val.setStyleSheet(value_ss)
            lay.addRow(lbl, val)
            self._account_labels[key] = val

        self._tabs.addTab(tab, "🏦 Account")

    # ── tab interaction feedback ──────────────────────────────────────────────

    def _on_tab_changed(self, idx: int) -> None:
        """Visual feedback when switching tabs."""
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QTimer.singleShot(120, QApplication.restoreOverrideCursor)

    # ── market status ─────────────────────────────────────────────────────────

    def _refresh_market_status(self) -> None:
        try:
            self._market_open = Utils.is_market_open()
            self._is_holiday = Utils.is_today_holiday()
            self._update_market_status_display()
        except Exception as exc:
            logger.debug(f"[StatusPanel._refresh_market_status] {exc}")

    def _update_market_status_display(self) -> None:
        try:
            c, ty = self._c, self._ty
            if self._is_holiday:
                txt, col = "Holiday", c.TEXT_DISABLED
            elif self._market_open:
                txt, col = "● Open", c.GREEN
            else:
                txt, col = "● Closed", c.RED
            self.market_status.setText(txt)
            self.market_status.setStyleSheet(
                f"color: {col}; font-size: {ty.SIZE_XS}pt; "
                f"font-weight: {ty.WEIGHT_BOLD}; "
                f"background: transparent; border: none;"
            )
        except Exception as exc:
            logger.debug(f"[StatusPanel._update_market_status_display] {exc}")

    # ── snapshot cache ────────────────────────────────────────────────────────

    def _get_cached_snapshot(self) -> dict:
        now = datetime.now()
        if (
                self._snapshot_ts is None
                or (now - self._snapshot_ts).total_seconds() > 0.1
        ):
            self._snapshot = state_manager.get_snapshot()
            self._pos_snapshot = state_manager.get_position_snapshot()
            self._snapshot_ts = now
        return self._snapshot

    def _get_cached_position_snapshot(self) -> dict:
        self._get_cached_snapshot()
        return self._pos_snapshot

    # ── formatting helpers ────────────────────────────────────────────────────

    def _fmt(self, v: Any, spec: str = ".2f") -> str:
        if v is None: return "—"
        try:
            return f"{float(v):{spec}}"
        except:
            return str(v)

    def _fmt_currency(self, v: Any) -> str:
        if v is None: return "—"
        try:
            f = float(v)
            return f"₹{f:,.0f}" if abs(f) >= 1000 else f"₹{f:.2f}"
        except:
            return str(v) if v else "—"

    def _fmt_percent(self, v: Any) -> str:
        if v is None: return "—"
        try:
            return f"{float(v):+.1f}%"
        except:
            return str(v) if v else "—"

    def _pnl_color(self, v: Any) -> str:
        c = self._c
        try:
            f = float(v) if v is not None else 0.0
            return c.GREEN if f > 0 else (c.RED if f < 0 else c.TEXT_DIM)
        except:
            return c.TEXT_DIM

    def _pos_color(self, pos: Any) -> str:
        c = self._c
        if pos and str(pos).upper() not in ("NONE", ""):
            return c.GREEN
        return c.TEXT_DIM

    def _signal_color(self, signal: Optional[str]) -> str:
        c = self._c
        if signal is None: return c.TEXT_DISABLED
        return {
            "BUY_CALL": c.GREEN,
            "BUY_PUT": c.BLUE,
            "EXIT_CALL": c.RED,
            "EXIT_PUT": c.ORANGE,
            "HOLD": c.YELLOW,
        }.get(signal, c.TEXT_DISABLED)

    def _safe_float(self, snap: dict, key: str, default: float = 0.0) -> Optional[float]:
        try:
            v = snap.get(key)
            return float(v) if v is not None else default
        except:
            return default

    def _safe_str(self, snap: dict, key: str, default: str = "") -> str:
        try:
            v = snap.get(key)
            return str(v) if v is not None else default
        except:
            return default

    def _safe_bool(self, snap: dict, key: str, default: bool = False) -> bool:
        try:
            v = snap.get(key)
            return bool(v) if v is not None else default
        except:
            return default

    def _trade_open(self, snap: dict) -> bool:
        try:
            pos = snap.get("current_position")
            return pos is not None and str(pos).upper() not in ("NONE", "")
        except:
            return False

    def _set_card(self, key: str, text: str, color: str) -> None:
        try:
            if key not in self.cards: return
            text = text or "—"
            ck, cc = f"{key}_v", f"{key}_c"
            with self._lock:
                if text != self._last_state.get(ck) or color != self._last_state.get(cc):
                    self.cards[key].set_value(text, color)
                    self._last_state[ck] = text
                    self._last_state[cc] = color
        except Exception as exc:
            logger.debug(f"[StatusPanel._set_card:{key}] {exc}")

    # ── public API ────────────────────────────────────────────────────────────

    def update_live_price(self, symbol: str, ltp: float) -> None:
        """
        Fast-path update for the index price card on every WS tick.
        Called by TradingGUI._on_price_tick before the 1-second timer fires.
        Only updates the derivative card when the tick is for the index symbol.
        """
        try:
            if self._closing or not self._refresh_enabled:
                return
            state = state_manager.get_state()
            derivative = getattr(state, 'derivative', None)
            if not derivative:
                return
            sym_upper = (symbol or "").upper()
            deriv_upper = derivative.upper()
            if sym_upper != deriv_upper and deriv_upper not in sym_upper and sym_upper not in deriv_upper:
                return
            c = self._c
            self._set_card("derivative", self._fmt(ltp) if ltp else "—", c.BLUE)
        except Exception:
            pass  # Never crash the WS thread

    def refresh(self, config=None) -> None:
        """Refresh all tiles from state_manager. Call at ~1-2 Hz from TradingGUI."""
        if self._closing or not self._refresh_enabled:
            return
        try:
            c = self._c
            self.timestamp.setText(datetime.now().strftime("%H:%M:%S"))

            snap = self._get_cached_snapshot()
            pos = self._get_cached_position_snapshot()

            # Trade-open guard
            trade_active = self._trade_open(snap)
            if trade_active != self._trade_active:
                self._trade_active = trade_active
                for key in self._TRADE_ONLY:
                    if key in self.cards:
                        self.cards[key].set_dimmed(not trade_active)
                for btn in (self.exit_btn, self.modify_sl_btn, self.modify_tp_btn):
                    if btn: btn.setEnabled(trade_active)

            # Signal
            signal = self._safe_str(pos, "option_signal", "WAIT")
            conflict = self._safe_bool(pos, "signal_conflict", False)
            self._set_card("signal", signal, self._signal_color(signal))
            self.conflict_label.setVisible(conflict)
            if conflict:
                self.conflict_label.setText("⚠ Signal Conflict")

            # Always-on cards
            cur_pos = snap.get("current_position")
            balance = self._safe_float(snap, "account_balance", 0.0)
            deriv = self._safe_float(snap, "derivative_current_price", 0.0)
            daily_pnl = self._safe_float(pos, "current_pnl", None)
            if daily_pnl is None:
                daily_pnl = self._safe_float(snap, "current_pnl", 0.0)

            trades_today_count = 1 if trade_active else 0
            try:
                from trade.risk_manager import RiskManager
                if config is not None and hasattr(config, 'risk_manager') and config.risk_manager:
                    summary = config.risk_manager.get_risk_summary()
                    trades_today_count = summary.get("trades_today", trades_today_count)
            except Exception:
                pass

            self._set_card("position", str(cur_pos) if cur_pos else "None", self._pos_color(cur_pos))
            self._set_card("balance", self._fmt_currency(balance), c.TEXT_MAIN)
            self._set_card("derivative", self._fmt(deriv) if deriv else "—", c.BLUE)
            self._set_card("daily_pnl", self._fmt_currency(daily_pnl), self._pnl_color(daily_pnl))
            self._set_card("trades_today", str(trades_today_count), c.TEXT_MAIN)

            if trade_active:
                symbol = snap.get("current_trading_symbol")
                entry = self._safe_float(pos, "current_buy_price")
                curr = self._safe_float(pos, "current_price")
                tp = self._safe_float(pos, "tp_point")
                sl = self._safe_float(pos, "stop_loss")
                pnl_pct = self._safe_float(pos, "percentage_change")

                # Fall back to snap for prices if pos values are None
                if curr is None or curr == 0:
                    curr = self._safe_float(snap, "current_price")
                if tp is None or tp == 0:
                    tp = self._safe_float(snap, "tp_point")
                if sl is None or sl == 0:
                    sl = self._safe_float(snap, "stop_loss")
                if pnl_pct is None:
                    pnl_pct = self._safe_float(snap, "percentage_change")

                self._set_card("symbol", str(symbol) if symbol else "—", c.TEXT_MAIN)
                self._set_card("buy_price", self._fmt(entry), c.TEXT_MAIN)
                self._set_card("current_price", self._fmt(curr), c.TEXT_MAIN)
                self._set_card("target_price", self._fmt(tp) if tp else "—", c.GREEN)
                self._set_card("stoploss_price", self._fmt(sl) if sl else "—", c.RED)
                self._set_card("pnl", self._fmt_percent(pnl_pct), self._pnl_color(pnl_pct))

            # Account tab
            self._account_labels.get("balance", _NullLabel()).setText(self._fmt_currency(balance))
            self._account_labels.get("m2m", _NullLabel()).setText(self._fmt_currency(daily_pnl))
            self._account_labels.get("open_positions", _NullLabel()).setText("1" if trade_active else "0")
            self._account_labels.get("day_trades", _NullLabel()).setText(str(trades_today_count))

        except Exception as exc:
            logger.error(f"[StatusPanel.refresh] {exc}", exc_info=True)

    def set_connection_status(self, connected: bool) -> None:
        c = self._c
        col = c.GREEN if connected else c.RED
        self.conn_status.setStyleSheet(
            f"color: {col}; font-size: {self._ty.SIZE_MD}pt; "
            f"background: transparent; border: none;"
        )

    def pause_refresh(self) -> None:
        self._refresh_enabled = False

    def resume_refresh(self) -> None:
        self._refresh_enabled = True

    def clear_cache(self) -> None:
        with self._lock:
            self._last_state.clear()
            self._snapshot = {}
            self._pos_snapshot = {}
            self._snapshot_ts = None

    def cleanup(self) -> None:
        try:
            logger.info("[StatusPanel] Cleanup")
            self._closing = True
            self.pause_refresh()
            self.clear_cache()
            self.cards.clear()
            if self._market_timer.isActive():
                self._market_timer.stop()
            logger.info("[StatusPanel] Cleanup done")
        except Exception as exc:
            logger.error(f"[StatusPanel.cleanup] {exc}", exc_info=True)

    def closeEvent(self, event) -> None:
        self.cleanup()


class _NullLabel:
    """Fallback when an account label key is missing — silently absorbs setText."""

    def setText(self, _: str) -> None:
        pass