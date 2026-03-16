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
from Utils.time_utils import IST, ist_now, fmt_display, fmt_stamp
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
                        background: {c.BG_CARD};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                    }}
                    QFrame:hover {{
                        background: {c.BG_PANEL};
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
# StatusMessageArea  — pinned message feed between PnL cards and action buttons
# ─────────────────────────────────────────────────────────────────────────────

class StatusMessageArea(QFrame):
    """
    Card-based status message feed.

    Each message is rendered as a rounded card with:
      • A coloured left accent bar (level colour)
      • An icon badge in the accent colour
      • The message text (word-wrapped, bold for newest)
      • A small timestamp below the text (right-aligned)

    Newest card is at the top, highlighted; older cards are dimmed.

    Public API
    ──────────
      post(text, level='info')   — prepend a new card
      clear()                    — remove all cards
      Levels: 'info' | 'warning' | 'error' | 'success'
    """

    _LEVEL_META = {
        'info':    ('ℹ', 'BLUE'),
        'success': ('✓', 'GREEN'),
        'warning': ('⚠', 'YELLOW_BRIGHT'),
        'error':   ('✕', 'RED_BRIGHT'),
    }
    _MAX_MESSAGES = 8

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._messages: List[Dict] = []
        self._row_widgets: List[QWidget] = []

        self.setObjectName("msgArea")
        self._build()
        theme_manager.theme_changed.connect(self._restyle)
        theme_manager.density_changed.connect(self._restyle)
        self._restyle()

    @property
    def _c(self):  return theme_manager.palette
    @property
    def _ty(self): return theme_manager.typography
    @property
    def _sp(self): return theme_manager.spacing

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ───────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setObjectName("msgHdr")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(10, 5, 8, 5)
        hdr_lay.setSpacing(6)

        badge = QLabel("📢")
        badge.setFixedWidth(18)
        badge.setStyleSheet("background: transparent; border: none;")
        hdr_lay.addWidget(badge)

        self._hdr_lbl = QLabel("ACTIVITY")
        hdr_lay.addWidget(self._hdr_lbl)
        hdr_lay.addStretch()

        self._count_lbl = QLabel("0")
        self._count_lbl.setObjectName("msgCount")
        hdr_lay.addWidget(self._count_lbl)

        self._clear_btn = QPushButton("✕")
        self._clear_btn.setFixedSize(18, 18)
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.clicked.connect(self.clear)
        self._clear_btn.setToolTip("Clear all")
        hdr_lay.addWidget(self._clear_btn)

        root.addWidget(hdr)

        # ── Card scroll area ──────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._inner = QWidget()
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(8, 8, 8, 8)
        self._inner_lay.setSpacing(6)
        self._inner_lay.addStretch()

        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll, 1)

        self.post("Waiting for trading engine…", level="info")

    # ── styling ───────────────────────────────────────────────────────────────

    def _restyle(self, _=None) -> None:
        try:
            c, ty, sp = self._c, self._ty, self._sp

            self.setStyleSheet(f"""
                QFrame#msgArea {{
                    background:    {c.BG_PANEL};
                    border:        1px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                }}
            """)

            hdr = self._hdr_lbl.parent()
            if hdr:
                hdr.setStyleSheet(f"""
                    QWidget#msgHdr {{
                        background:    {c.BG_HOVER};
                        border-bottom: 1px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px {sp.RADIUS_MD}px 0 0;
                    }}
                """)

            self._hdr_lbl.setStyleSheet(
                f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; "
                f"font-weight: {ty.WEIGHT_BOLD}; letter-spacing: 0.8px; "
                f"background: transparent;"
            )
            self._count_lbl.setStyleSheet(
                f"color: {c.TEXT_DISABLED}; font-size: {ty.SIZE_XS}pt; "
                f"background: {c.BG_CARD}; border: 1px solid {c.BORDER}; "
                f"border-radius: 6px; padding: 0px 5px; min-width: 16px;"
            )
            self._clear_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {c.TEXT_DISABLED};
                    border: none; font-size: {ty.SIZE_XS}pt; border-radius: 4px;
                }}
                QPushButton:hover {{
                    background: {c.RED}22; color: {c.RED_BRIGHT};
                }}
            """)
            self._scroll.setStyleSheet(f"""
                QScrollArea {{ background: {c.BG_PANEL}; border: none; }}
                QScrollBar:vertical {{
                    background: transparent; width: 4px; margin: 4px 0;
                }}
                QScrollBar::handle:vertical {{
                    background: {c.BORDER}; border-radius: 2px; min-height: 16px;
                }}
                QScrollBar::handle:vertical:hover {{ background: {c.BORDER_STRONG}; }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            """)
            self._inner.setStyleSheet(f"background: {c.BG_PANEL};")

            # Re-apply cards — index 0 = newest (highlighted)
            for i, w in enumerate(self._row_widgets):
                try:
                    level = w.property("msg_level") or "info"
                    self._style_card(w, level, highlight=(i == 0))
                except Exception:
                    pass
        except Exception as exc:
            logger.debug(f"[StatusMessageArea._restyle] {exc}")

    def _style_card(self, card: QWidget, level: str, highlight: bool = False) -> None:
        c, ty, sp = self._c, self._ty, self._sp

        icon_lbl: QLabel = card.property("icon_lbl")
        text_lbl: QLabel = card.property("text_lbl")
        time_lbl: QLabel = card.property("time_lbl")
        bar:      QFrame = card.property("accent_bar")

        _, color_attr = self._LEVEL_META.get(level, ('ℹ', 'BLUE'))
        color = getattr(c, color_attr, c.BLUE)

        if highlight:
            card.setStyleSheet(f"""
                QWidget[role="msgCard"] {{
                    background:    {color}1e;
                    border:        1px solid {color}55;
                    border-left:   3px solid {color};
                    border-radius: {sp.RADIUS_SM}px;
                }}
            """)
            if bar:
                bar.setStyleSheet(f"background: {color}; border-radius: 1px;")
            if icon_lbl:
                icon_lbl.setStyleSheet(
                    f"color: {color}; font-size: {ty.SIZE_SM}pt; "
                    f"font-weight: bold; background: transparent;"
                )
            if text_lbl:
                text_lbl.setStyleSheet(
                    f"color: {c.TEXT_BRIGHT}; font-size: {ty.SIZE_XS}pt; "
                    f"font-weight: {ty.WEIGHT_BOLD}; background: transparent;"
                )
            if time_lbl:
                time_lbl.setStyleSheet(
                    f"color: {color}99; font-size: {ty.SIZE_XS - 1}pt; "
                    f"background: transparent;"
                )
        else:
            card.setStyleSheet(f"""
                QWidget[role="msgCard"] {{
                    background:    {color}0a;
                    border:        1px solid {c.BORDER};
                    border-left:   2px solid {color}55;
                    border-radius: {sp.RADIUS_SM}px;
                }}
            """)
            if bar:
                bar.setStyleSheet(f"background: {color}55; border-radius: 1px;")
            if icon_lbl:
                icon_lbl.setStyleSheet(
                    f"color: {color}77; font-size: {ty.SIZE_XS}pt; "
                    f"background: transparent;"
                )
            if text_lbl:
                text_lbl.setStyleSheet(
                    f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; "
                    f"background: transparent;"
                )
            if time_lbl:
                time_lbl.setStyleSheet(
                    f"color: {c.TEXT_DISABLED}; font-size: {ty.SIZE_XS - 1}pt; "
                    f"background: transparent;"
                )

    # ── public API ────────────────────────────────────────────────────────────

    def post(self, text: str, level: str = 'info') -> None:
        """
        Prepend a new card to the feed (newest at top, highlighted).
        Previous cards are automatically dimmed.
        """
        try:
            if not text:
                return
            level = level if level in self._LEVEL_META else 'info'
            now_str = fmt_display(ist_now(), time_only=True)

            self._messages.insert(0, {'text': text, 'level': level, 'time': now_str})
            if len(self._messages) > self._MAX_MESSAGES:
                self._messages.pop()

            icon_char, _ = self._LEVEL_META[level]

            # ── Card widget ───────────────────────────────────────────────────
            card = QWidget()
            card.setProperty("role", "msgCard")
            card.setProperty("msg_level", level)

            card_lay = QHBoxLayout(card)
            card_lay.setContentsMargins(8, 7, 8, 7)
            card_lay.setSpacing(8)

            # Icon badge
            icon_lbl = QLabel(icon_char)
            icon_lbl.setFixedSize(16, 16)
            icon_lbl.setAlignment(Qt.AlignCenter)
            card_lay.addWidget(icon_lbl, 0, Qt.AlignTop)

            # Text block: message + timestamp stacked
            text_block = QWidget()
            text_block.setStyleSheet("background: transparent;")
            tb_lay = QVBoxLayout(text_block)
            tb_lay.setContentsMargins(0, 0, 0, 0)
            tb_lay.setSpacing(2)

            txt = QLabel(text)
            txt.setWordWrap(True)
            txt.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            tb_lay.addWidget(txt)

            ts = QLabel(now_str)
            ts.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tb_lay.addWidget(ts)

            card_lay.addWidget(text_block, 1)

            # Store refs for re-styling
            card.setProperty("icon_lbl",   icon_lbl)
            card.setProperty("text_lbl",   txt)
            card.setProperty("time_lbl",   ts)
            card.setProperty("accent_bar", None)

            # Demote previous newest
            if self._row_widgets:
                prev = self._row_widgets[0]
                self._style_card(prev, prev.property("msg_level") or "info", highlight=False)

            # Style new card as highlighted newest
            self._style_card(card, level, highlight=True)

            # Insert at top (above the stretch)
            self._inner_lay.insertWidget(0, card)
            self._row_widgets.insert(0, card)

            # Trim oldest beyond cap
            while len(self._row_widgets) > self._MAX_MESSAGES:
                old = self._row_widgets.pop()
                self._inner_lay.removeWidget(old)
                old.deleteLater()

            # Update count badge
            self._count_lbl.setText(str(len(self._row_widgets)))

            # Scroll to top — newest card is always visible
            self._scroll.verticalScrollBar().setValue(0)

        except Exception as exc:
            logger.debug(f"[StatusMessageArea.post] {exc}")

    def clear(self) -> None:
        """Remove all message cards from the feed."""
        try:
            self._messages.clear()
            for w in self._row_widgets:
                self._inner_lay.removeWidget(w)
                w.deleteLater()
            self._row_widgets.clear()
            self._count_lbl.setText("0")
        except Exception as exc:
            logger.debug(f"[StatusMessageArea.clear] {exc}")
            logger.debug(f"[StatusMessageArea.clear] {exc}")




class StatusPanel(QWidget):
    """
    Right-side status panel — three-tab layout:

      Tab 1  📡 Status   — signal, position, index, daily P&L, trades
                           + full-height message feed (no cramping)
      Tab 2  📊 Trade    — trade summary cards + Exit/SL/TP buttons
                           (auto-switches in when a trade opens)
      Tab 3  🏦 Account  — balance, margin, buying power, M2M
    """

    # Cards that live on the Trade tab (only meaningful when position is open)
    _TRADE_ONLY: Set[str] = frozenset({
        "symbol", "direction", "buy_price", "current_price",
        "target_price", "stoploss_price", "pnl",
    })

    # Cards that always live on the Status tab
    _STATUS_FIELDS: List[tuple] = [
        ("position",   "🟢", "Position"),
        ("signal",     "📊", "Signal"),
        ("derivative", "📈", "Index"),
    ]

    # Cards that live on the Trade tab
    _TRADE_FIELDS: List[tuple] = [
        ("symbol",         "💹", "Symbol"),
        ("direction",      "🔀", "Direction"),
        ("buy_price",      "🛒", "Entry"),
        ("current_price",  "💰", "Current"),
        ("target_price",   "🎯", "Target (TP)"),
        ("stoploss_price", "🛑", "Stop (SL)"),
        ("pnl",            "💵", "P&L %"),
    ]

    # Union for any external code that reads FIELDS
    FIELDS: List[tuple] = _STATUS_FIELDS + _TRADE_FIELDS

    # Tab indices
    TAB_STATUS  = 0
    TAB_TRADE   = 1
    TAB_ACCOUNT = 2

    # Signals
    exit_position_clicked = pyqtSignal()
    modify_sl_clicked     = pyqtSignal()
    modify_tp_clicked     = pyqtSignal()

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
        # Signal-stall detection
        self._last_signal_seen: Optional[str] = None
        self._signal_stall_ticks: int = 0
        self._SIGNAL_STALL_THRESHOLD: int = 60
        self._stall_warned: bool = False
        # cards dict populated across all tabs
        self.cards: Dict[str, StatusCard] = {}

        self.setMinimumWidth(240)
        self.setMaximumWidth(340)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self._tabs, 1)

        self._build_status_tab()
        self._build_trade_tab()
        self._build_account_tab()

        theme_manager.theme_changed.connect(self.apply_theme)
        theme_manager.density_changed.connect(self.apply_theme)
        self.apply_theme()

        self._market_timer = QTimer()
        self._market_timer.timeout.connect(self._refresh_market_status)
        self._market_timer.start(60_000)

        logger.info("[StatusPanel] Initialized (3-tab layout)")

    # ── theme shortcuts ───────────────────────────────────────────────────────
    @property
    def _c(self):  return theme_manager.palette
    @property
    def _ty(self): return theme_manager.typography
    @property
    def _sp(self): return theme_manager.spacing

    # ── theme application ─────────────────────────────────────────────────────

    def apply_theme(self, _: str = None) -> None:
        try:
            c, ty, sp = self._c, self._ty, self._sp

            self.setStyleSheet(f"QWidget {{ background: {c.BG_MAIN}; }}")

            self._tabs.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: 1px solid {c.BORDER};
                    border-top: none;
                    background: {c.BG_MAIN};
                }}
                QTabBar::tab {{
                    background:    {c.BG_CARD};
                    color:         {c.TEXT_DIM};
                    border:        1px solid {c.BORDER};
                    border-bottom: none;
                    border-radius: {sp.RADIUS_MD}px {sp.RADIUS_MD}px 0 0;
                    padding:       {sp.PAD_XS}px {sp.PAD_SM}px;
                    font-size:     {ty.SIZE_XS}pt;
                    font-weight:   {ty.WEIGHT_BOLD};
                    min-width:     60px;
                    margin-right:  2px;
                }}
                QTabBar::tab:selected {{
                    background:    {c.BG_MAIN};
                    color:         {c.TEXT_BRIGHT};
                    border-bottom: 2px solid {c.BLUE};
                    font-weight:   {ty.WEIGHT_BOLD};
                }}
                QTabBar::tab:hover:!selected {{
                    background: {c.BG_HOVER};
                    color:      {c.TEXT_MAIN};
                }}
                QScrollBar:vertical {{
                    background: {c.BG_PANEL}; width: 5px; border-radius: 3px;
                }}
                QScrollBar::handle:vertical {{
                    background: {c.BORDER}; min-height: 16px; border-radius: 3px;
                }}
                QScrollBar::handle:vertical:hover {{ background: {c.BORDER_STRONG}; }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            """)

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
            if hasattr(self, "_no_trade_lbl") and hasattr(self._no_trade_lbl, "setStyleSheet"):
                self._no_trade_lbl.setStyleSheet(f"""
                    QFrame#noTradeCard {{
                        background:    {c.BG_CARD};
                        border:        1px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                        margin:        {sp.PAD_MD}px;
                    }}
                """)
            if hasattr(self, "_no_trade_title"):
                self._no_trade_title.setStyleSheet(
                    f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_MD}pt; "
                    f"font-weight: {ty.WEIGHT_BOLD}; background: transparent; border: none;"
                )
            if hasattr(self, "_no_trade_sub"):
                self._no_trade_sub.setStyleSheet(
                    f"color: {c.TEXT_DISABLED}; font-size: {ty.SIZE_SM}pt; "
                    f"background: transparent; border: none;"
                )
            if hasattr(self, "_no_trade_icon"):
                self._no_trade_icon.setStyleSheet(
                    f"font-size: 28pt; background: transparent; border: none;"
                )

            for card in self.cards.values():
                card.apply_theme()

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
            QPushButton:hover    {{ background: {c.BG_HOVER}; border-color: {c.BORDER_STRONG}; }}
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

        self.timestamp = QLabel(fmt_display(ist_now(), time_only=True))
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

    # ── Tab 1: Status ─────────────────────────────────────────────────────────

    def _build_status_tab(self) -> None:
        """
        Always-on overview: signal, position, index price
        + full-height message feed below occupying roughly the lower half.
        """
        sp = self._sp

        tab = QWidget()
        tab_lay = QVBoxLayout(tab)
        tab_lay.setContentsMargins(0, 0, 0, 0)
        tab_lay.setSpacing(0)

        # ── Metric cards (3 cards — naturally sized, no artificial height cap) ─
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

        for key, icon, label in self._STATUS_FIELDS:
            card = StatusCard(icon, label)
            inner_lay.addWidget(card)
            self.cards[key] = card

        inner_lay.addStretch()
        scroll.setWidget(inner)
        # stretch=1 gives cards half the space; message_area below also gets stretch=1
        tab_lay.addWidget(scroll, 1)

        # Signal conflict warning — sits between cards and feed with clear separation
        self.conflict_label = QLabel("")
        self.conflict_label.setAlignment(Qt.AlignCenter)
        self.conflict_label.setVisible(False)
        tab_lay.addWidget(self.conflict_label)

        # Thin separator so the message area header never visually bleeds into cards
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {self._c.BORDER}; border: none;")
        tab_lay.addWidget(sep)

        # ── Message feed — stretch=1 → equal share of the remaining height ───
        self.message_area = StatusMessageArea()
        self.message_area.setMinimumHeight(80)
        tab_lay.addWidget(self.message_area, 1)

        self._tabs.addTab(tab, "📡 Status")

    # ── Tab 2: Trade ──────────────────────────────────────────────────────────

    def _build_trade_tab(self) -> None:
        """
        Trade summary + action buttons.
        Auto-switches to this tab when a trade opens, returns to Status on close.
        """
        sp = self._sp
        c  = self._c
        ty = self._ty

        tab = QWidget()
        tab_lay = QVBoxLayout(tab)
        tab_lay.setContentsMargins(0, 0, 0, 0)
        tab_lay.setSpacing(0)

        # ── Empty-state placeholder (shown when no trade is active) ───────────
        self._no_trade_container = QWidget()
        no_trade_lay = QVBoxLayout(self._no_trade_container)
        no_trade_lay.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)
        no_trade_lay.setSpacing(sp.GAP_SM)
        no_trade_lay.setAlignment(Qt.AlignCenter)

        # Icon
        icon_lbl = QLabel("📭")
        icon_lbl.setObjectName("noTradeIcon")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            f"font-size: 28pt; background: transparent; border: none;"
        )
        no_trade_lay.addWidget(icon_lbl)

        # Title
        title_lbl = QLabel("No Active Position")
        title_lbl.setObjectName("noTradeTitle")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(
            f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_MD}pt; "
            f"font-weight: {ty.WEIGHT_BOLD}; background: transparent; border: none;"
        )
        no_trade_lay.addWidget(title_lbl)

        # Subtitle
        sub_lbl = QLabel("Waiting for entry signal…")
        sub_lbl.setObjectName("noTradeSub")
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet(
            f"color: {c.TEXT_DISABLED}; font-size: {ty.SIZE_SM}pt; "
            f"background: transparent; border: none;"
        )
        no_trade_lay.addWidget(sub_lbl)

        # Store refs so apply_theme can update colours
        self._no_trade_icon  = icon_lbl
        self._no_trade_title = title_lbl
        self._no_trade_sub   = sub_lbl

        # Outer card frame for the empty state
        self._no_trade_lbl = QFrame()   # kept as attribute name for compat
        self._no_trade_lbl.setObjectName("noTradeCard")
        self._no_trade_lbl.setFrameShape(QFrame.NoFrame)
        self._no_trade_lbl.setStyleSheet(f"""
            QFrame#noTradeCard {{
                background:    {c.BG_CARD};
                border:        1px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                margin:        {sp.PAD_MD}px;
            }}
        """)
        card_lay = QVBoxLayout(self._no_trade_lbl)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.addWidget(self._no_trade_container)
        self._no_trade_lbl.setVisible(True)
        tab_lay.addWidget(self._no_trade_lbl, 1)   # stretch so it fills space

        # ── Trade metric cards (scrollable, hidden until trade opens) ──────────
        self._trade_scroll = QScrollArea()
        self._trade_scroll.setWidgetResizable(True)
        self._trade_scroll.setFrameShape(QFrame.NoFrame)
        self._trade_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._trade_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._trade_scroll.setStyleSheet("QScrollArea { border: none; }")
        self._trade_scroll.setVisible(False)

        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(sp.PAD_SM, sp.PAD_MD, sp.PAD_SM, sp.PAD_SM)
        inner_lay.setSpacing(sp.GAP_SM)

        for key, icon, label in self._TRADE_FIELDS:
            card = StatusCard(icon, label)
            inner_lay.addWidget(card)
            self.cards[key] = card

        inner_lay.addStretch()
        self._trade_scroll.setWidget(inner)
        tab_lay.addWidget(self._trade_scroll, 1)

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = QWidget()
        btn_row.setObjectName("tradeBtnRow")
        btn_row.setStyleSheet(f"""
            QWidget#tradeBtnRow {{
                background:    {c.BG_PANEL};
                border-top:    1px solid {c.BORDER};
            }}
        """)
        btn_lay = QHBoxLayout(btn_row)
        btn_lay.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM)
        btn_lay.setSpacing(sp.GAP_SM)

        self.exit_btn = QPushButton("🚪 Exit")
        self.exit_btn.setEnabled(False)
        self.exit_btn.clicked.connect(self.exit_position_clicked.emit)
        btn_lay.addWidget(self.exit_btn, 2)

        self.modify_sl_btn = QPushButton("🛑 SL")
        self.modify_sl_btn.setEnabled(False)
        self.modify_sl_btn.clicked.connect(self.modify_sl_clicked.emit)
        btn_lay.addWidget(self.modify_sl_btn, 1)

        self.modify_tp_btn = QPushButton("🎯 TP")
        self.modify_tp_btn.setEnabled(False)
        self.modify_tp_btn.clicked.connect(self.modify_tp_clicked.emit)
        btn_lay.addWidget(self.modify_tp_btn, 1)

        tab_lay.addWidget(btn_row)

        self._tabs.addTab(tab, "📊 Trade")

    # ── Tab 3: Account ────────────────────────────────────────────────────────

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
            ("Balance",      "balance",        "₹0"),
            ("Margin",       "margin",         "₹0"),
            ("Buying Power", "buying_power",   "₹0"),
            ("M2M",          "m2m",            "₹0"),
            ("Day Trades",   "day_trades",     "0"),
            ("Open Pos",     "open_positions", "0"),
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
        from PyQt5.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QTimer.singleShot(120, QApplication.restoreOverrideCursor)

    def _set_trade_tab_label(self, active: bool) -> None:
        """Update the Trade tab label with a live dot when a trade is open."""
        try:
            label = "📊 Trade  🟢" if active else "📊 Trade"
            self._tabs.setTabText(self.TAB_TRADE, label)
        except Exception:
            pass


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
            self.timestamp.setText(fmt_display(ist_now(), time_only=True))

            snap = self._get_cached_snapshot()
            pos = self._get_cached_position_snapshot()

            # Trade-open guard
            trade_active = self._trade_open(snap)
            if trade_active != self._trade_active:
                self._trade_active = trade_active

                # Swap empty-state / trade cards
                if hasattr(self, "_no_trade_lbl"):
                    self._no_trade_lbl.setVisible(not trade_active)
                if hasattr(self, "_trade_scroll"):
                    self._trade_scroll.setVisible(trade_active)

                # Enable/disable action buttons
                for btn in (self.exit_btn, self.modify_sl_btn, self.modify_tp_btn):
                    if btn:
                        btn.setEnabled(trade_active)

                # Auto-switch to Trade tab when a trade opens,
                # return to Status tab when it closes
                if trade_active:
                    self._tabs.setCurrentIndex(self.TAB_TRADE)
                else:
                    self._tabs.setCurrentIndex(self.TAB_STATUS)

                # Update Trade tab label with live-dot indicator
                self._set_trade_tab_label(trade_active)

            # Signal
            signal = self._safe_str(pos, "option_signal", "WAIT")
            conflict = self._safe_bool(pos, "signal_conflict", False)
            self._set_card("signal", signal, self._signal_color(signal))
            self.conflict_label.setVisible(conflict)
            if conflict:
                self.conflict_label.setText("⚠ Signal Conflict")

            # ── Signal-stall detection ────────────────────────────────────────
            # Count how many refresh ticks the signal has stayed at WAIT while
            # the market is open and trading is running.  Warn once per stall event.
            if self._market_open and signal == "WAIT":
                self._signal_stall_ticks += 1
                if self._signal_stall_ticks >= self._SIGNAL_STALL_THRESHOLD and not self._stall_warned:
                    self._stall_warned = True
                    self.post_message(
                        f"Signal stalled — WAIT for {self._signal_stall_ticks}s", level='warning'
                    )
            else:
                if self._stall_warned and signal != "WAIT":
                    self._stall_warned = False  # reset after signal recovers
                self._signal_stall_ticks = 0

            # Always-on cards
            cur_pos = snap.get("current_position")
            balance = self._safe_float(snap, "account_balance", 0.0)
            deriv   = self._safe_float(snap, "derivative_current_price", 0.0)

            self._set_card("position",   str(cur_pos) if cur_pos else "None", self._pos_color(cur_pos))
            self._set_card("balance",    self._fmt_currency(balance),          c.TEXT_MAIN)
            self._set_card("derivative", self._fmt(deriv) if deriv else "—",   c.BLUE)

            if trade_active:
                symbol    = snap.get("current_trading_symbol")
                cur_pos   = snap.get("current_position")
                entry     = self._safe_float(pos, "current_buy_price")
                curr      = self._safe_float(pos, "current_price")
                tp        = self._safe_float(pos, "tp_point")
                sl        = self._safe_float(pos, "stop_loss")
                pnl_pct   = self._safe_float(pos, "percentage_change")

                # Fall back to snap for prices if pos values are None
                if curr is None or curr == 0:
                    curr = self._safe_float(snap, "current_price")
                if tp is None or tp == 0:
                    tp = self._safe_float(snap, "tp_point")
                if sl is None or sl == 0:
                    sl = self._safe_float(snap, "stop_loss")
                if pnl_pct is None:
                    pnl_pct = self._safe_float(snap, "percentage_change")

                # Direction card — CALL (green) or PUT (blue)
                dir_str = str(cur_pos).upper() if cur_pos else "—"
                dir_col = c.GREEN if "CALL" in dir_str else (c.BLUE if "PUT" in dir_str else c.TEXT_MAIN)

                self._set_card("symbol",        str(symbol) if symbol else "—",        c.TEXT_MAIN)
                self._set_card("direction",      dir_str,                               dir_col)
                self._set_card("buy_price",      self._fmt(entry),                      c.TEXT_MAIN)
                self._set_card("current_price",  self._fmt(curr),                       c.TEXT_MAIN)
                self._set_card("target_price",   self._fmt(tp)  if tp else "—",         c.GREEN)
                self._set_card("stoploss_price", self._fmt(sl)  if sl else "—",         c.RED)
                self._set_card("pnl",            self._fmt_percent(pnl_pct),            self._pnl_color(pnl_pct))

            # Account tab
            self._account_labels.get("balance",        _NullLabel()).setText(self._fmt_currency(balance))
            self._account_labels.get("open_positions", _NullLabel()).setText("1" if trade_active else "0")

        except Exception as exc:
            logger.error(f"[StatusPanel.refresh] {exc}", exc_info=True)

    def set_connection_status(self, connected: bool) -> None:
        c = self._c
        col = c.GREEN if connected else c.RED
        self.conn_status.setStyleSheet(
            f"color: {col}; font-size: {self._ty.SIZE_MD}pt; "
            f"background: transparent; border: none;"
        )

    def post_message(self, text: str, level: str = 'info') -> None:
        """
        Post a message to the sidebar message feed.

        Args:
            text:  Message string shown in the feed.
            level: 'info' | 'warning' | 'error' | 'success'

        Usage from TradingGUI or any other module:
            self.status_panel.post_message("Daily loss limit hit", level='error')
            self.status_panel.post_message("Strategy reloaded", level='success')
        """
        try:
            if self._closing:
                return
            if hasattr(self, 'message_area') and self.message_area:
                self.message_area.post(text, level)
        except Exception as exc:
            logger.debug(f"[StatusPanel.post_message] {exc}")

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