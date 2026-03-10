"""
strategy_picker_sidebar.py
==========================
REDESIGN — "Ops Command Panel" aesthetic.

Design philosophy:
  · Terminal-influenced, military-ops dark panel
  · Tight information density — every pixel earns its place
  · Two-column confidence grid (not a plain list)
  · Hero strip: active strategy name fills the full width in large type
  · Monochrome base with surgical colour pops ONLY for live state
  · Hairline borders, no card shadows — flat and precise
  · Draggable, frameless, 400 px wide

All business logic (threading, state_manager, theming) is preserved intact.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Any

from PyQt5.QtCore import (
    Qt, QTimer, pyqtSignal, pyqtSlot, QMetaObject, Q_ARG
)
from PyQt5.QtGui import (
    QColor, QFont, QPainter, QBrush, QPen, QLinearGradient
)
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
    QGridLayout, QProgressBar, QScrollArea, QSizePolicy
)

from Utils.safe_getattr import safe_hasattr
from strategy.strategy_manager import strategy_manager
from data.trade_state_manager import state_manager
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)

SIGNAL_GROUPS = ["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]

# Per-signal display metadata
_SIG = {
    "BUY_CALL": dict(short="B↑", label="BUY CALL", attr="GREEN_BRIGHT"),
    "BUY_PUT": dict(short="B↓", label="BUY PUT", attr="BLUE"),
    "EXIT_CALL": dict(short="X↑", label="EXIT CALL", attr="RED_BRIGHT"),
    "EXIT_PUT": dict(short="X↓", label="EXIT PUT", attr="ORANGE"),
    "HOLD": dict(short="HLD", label="HOLD", attr="YELLOW_BRIGHT"),
    "WAIT": dict(short="---", label="WAIT", attr="TEXT_DISABLED"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Palette helpers  (always reads current theme)
# ─────────────────────────────────────────────────────────────────────────────

def _p():  return theme_manager.palette


def _ty(): return theme_manager.typography


def _sp(): return theme_manager.spacing


def _tok(attr: str, fallback: str = "#888") -> str:
    return getattr(theme_manager.palette, attr, fallback)


class _TM:
    """Mixin: shortcuts to current theme tokens."""

    @property
    def _c(self):  return theme_manager.palette

    @property
    def _ty(self): return theme_manager.typography

    @property
    def _sp(self): return theme_manager.spacing


# ─────────────────────────────────────────────────────────────────────────────
# LIVE TICKER DOT  (breathing animation via QTimer + custom paint)
# ─────────────────────────────────────────────────────────────────────────────

class _LiveDot(QWidget):
    """12×12 dot that breathes between full and 20% opacity."""

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._color = color
        self._alpha = 1.0
        self._dir = -1
        t = QTimer(self)
        t.timeout.connect(self._step)
        t.start(35)

    def _step(self):
        self._alpha += self._dir * 0.035
        if self._alpha <= 0.15: self._dir = 1
        if self._alpha >= 1.0:  self._dir = -1
        self.update()

    def set_color(self, c: str):
        self._color = c

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(self._color)
        c.setAlphaF(self._alpha)
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawEllipse(1, 1, 8, 8)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL CONFIDENCE CELL  (used in 2-column grid)
# ─────────────────────────────────────────────────────────────────────────────

class _ConfCell(QWidget, _TM):
    """
    Compact 2-row cell:
        [short-code]  ████░░  73%
        BUY CALL
    Fills width equally in a 2-col grid.
    """

    def __init__(self, signal: str, parent=None):
        super().__init__(parent)
        self.signal = signal
        self._meta = _SIG.get(signal, _SIG["WAIT"])
        self._conf = 0.0
        self._thr = 0.6
        self._build()
        self._restyle()
        try:
            theme_manager.theme_changed.connect(self._restyle)
            theme_manager.density_changed.connect(self._restyle)
        except Exception:
            pass

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(3)

        # Top row: short code + bar + pct
        top = QHBoxLayout()
        top.setSpacing(6)
        top.setContentsMargins(0, 0, 0, 0)

        self._code_lbl = QLabel(self._meta["short"])
        self._code_lbl.setFixedWidth(28)
        self._code_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        top.addWidget(self._code_lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(4)
        top.addWidget(self._bar, 1)

        self._pct_lbl = QLabel("0%")
        self._pct_lbl.setFixedWidth(30)
        self._pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self._pct_lbl)

        root.addLayout(top)

        # Bottom row: full label
        self._label_lbl = QLabel(self._meta["label"])
        self._label_lbl.setAlignment(Qt.AlignLeft)
        root.addWidget(self._label_lbl)

    def _restyle(self, _=None):
        c = self._c
        ty = self._ty
        col = _tok(self._meta["attr"])

        self._code_lbl.setStyleSheet(f"""
            color: {col};
            font-size: {ty.SIZE_BODY}pt;
            font-weight: bold;
            font-family: 'Consolas', monospace;
            background: transparent;
        """)
        self._label_lbl.setStyleSheet(f"""
            color: {c.TEXT_DIM};
            font-size: {ty.SIZE_XS}pt;
            letter-spacing: 0.4px;
            background: transparent;
        """)
        self._apply_pct_color(col)
        self._apply_bar_color(col)

        self.setStyleSheet(f"""
            QWidget {{
                background: {c.BG_INPUT};
                border: 1px solid {c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
            }}
        """)

    def _apply_pct_color(self, col: str):
        ty = self._ty
        self._pct_lbl.setStyleSheet(f"""
            color: {col};
            font-size: {ty.SIZE_XS}pt;
            font-weight: bold;
            font-family: 'Consolas', monospace;
            background: transparent;
        """)

    def _apply_bar_color(self, col: str):
        c = self._c
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 2px;
                background: {c.BG_HOVER};
            }}
            QProgressBar::chunk {{
                border-radius: 2px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {col}55, stop:1 {col});
            }}
        """)

    def set_confidence(self, conf: float, threshold: float = 0.6):
        try:
            self._conf = conf
            self._thr = threshold
            pct = int(conf * 100)
            self._bar.setValue(pct)
            self._pct_lbl.setText(f"{pct}%")

            if conf >= threshold:
                attr = "GREEN_BRIGHT"
            elif conf >= threshold * 0.6:
                attr = "YELLOW_BRIGHT"
            else:
                attr = "RED_BRIGHT"
            col = _tok(attr)
            self._apply_pct_color(col)
            self._apply_bar_color(col)
        except Exception as e:
            logger.error(f"[_ConfCell.set_confidence] {e}", exc_info=True)

    # backward compat alias used by apply_theme loop
    def apply_theme(self, _=None):
        self._restyle()


# ─────────────────────────────────────────────────────────────────────────────
# HERO STRIP — active strategy display
# ─────────────────────────────────────────────────────────────────────────────

class _HeroStrip(QFrame, _TM):
    """
    Full-width dark strip with:
      Left:  large strategy name + description
      Right: current signal badge stacked above live-dot
    Bottom meta row: RULES · TIMEFRAME · CONF · SAVED
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("heroStrip")
        self._dot = None
        self._name_lbl = None
        self._desc_lbl = None
        self._sig_lbl = None
        self._meta_labels = {}
        self._build()
        self._restyle()
        try:
            theme_manager.theme_changed.connect(self._restyle)
            theme_manager.density_changed.connect(self._restyle)
        except Exception:
            pass

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(6)

        # ── Top: name left, signal+dot right ────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)

        left = QVBoxLayout()
        left.setSpacing(2)

        # "ACTIVE STRATEGY" eyebrow label
        eyebrow = QLabel("ACTIVE STRATEGY")
        eyebrow.setObjectName("heroEyebrow")
        left.addWidget(eyebrow)

        self._name_lbl = QLabel("—")
        self._name_lbl.setObjectName("heroName")
        self._name_lbl.setWordWrap(True)
        left.addWidget(self._name_lbl)

        self._desc_lbl = QLabel()
        self._desc_lbl.setObjectName("heroDesc")
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setVisible(False)
        left.addWidget(self._desc_lbl)

        top.addLayout(left, 1)

        # Signal badge + live dot stacked
        right = QVBoxLayout()
        right.setSpacing(4)
        right.setAlignment(Qt.AlignTop | Qt.AlignRight)

        self._sig_lbl = QLabel("WAIT")
        self._sig_lbl.setObjectName("heroSig")
        self._sig_lbl.setAlignment(Qt.AlignCenter)
        self._sig_lbl.setMinimumWidth(72)
        right.addWidget(self._sig_lbl)

        dot_row = QHBoxLayout()
        dot_row.setAlignment(Qt.AlignRight)
        dot_row.setSpacing(4)
        self._dot = _LiveDot(_tok("TEXT_DISABLED"))
        dot_row.addWidget(self._dot)
        live_lbl = QLabel("LIVE")
        live_lbl.setObjectName("heroDotLbl")
        dot_row.addWidget(live_lbl)
        right.addLayout(dot_row)

        top.addLayout(right)
        root.addLayout(top)

        # ── Hairline separator ───────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("heroSep")
        root.addWidget(sep)

        # ── Meta row: 4 stats ────────────────────────────────────────────────
        meta = QHBoxLayout()
        meta.setSpacing(0)
        meta.setContentsMargins(0, 0, 0, 0)

        for key in ("RULES", "TIMEFRAME", "CONF", "SAVED"):
            cell = QWidget()
            cell.setObjectName("metaCell")
            cell_lay = QVBoxLayout(cell)
            cell_lay.setContentsMargins(0, 4, 0, 0)
            cell_lay.setSpacing(1)
            cell_lay.setAlignment(Qt.AlignCenter)

            key_lbl = QLabel(key)
            key_lbl.setObjectName("metaKey")
            key_lbl.setAlignment(Qt.AlignCenter)
            cell_lay.addWidget(key_lbl)

            val_lbl = QLabel("—")
            val_lbl.setObjectName("metaVal")
            val_lbl.setAlignment(Qt.AlignCenter)
            cell_lay.addWidget(val_lbl)

            self._meta_labels[key] = val_lbl
            meta.addWidget(cell, 1)

            # Vertical divider between cells (except after last)
            if key != "SAVED":
                div = QFrame()
                div.setFrameShape(QFrame.VLine)
                div.setObjectName("metaDiv")
                meta.addWidget(div)

        root.addLayout(meta)

    def _restyle(self, _=None):
        c = self._c
        ty = self._ty
        sp = self._sp
        accent = _tok("YELLOW_BRIGHT")

        self.setStyleSheet(f"""
            QFrame#heroStrip {{
                background: {c.BG_PANEL};
                border-bottom: 1px solid {c.BORDER};
            }}
            QLabel#heroEyebrow {{
                color: {accent};
                font-size: {ty.SIZE_XS}pt;
                font-weight: bold;
                letter-spacing: 1.2px;
                background: transparent;
            }}
            QLabel#heroName {{
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_XL}pt;
                font-weight: bold;
                background: transparent;
            }}
            QLabel#heroDesc {{
                color: {c.TEXT_DIM};
                font-size: {ty.SIZE_SM}pt;
                background: transparent;
            }}
            QLabel#heroSig {{
                color: {c.TEXT_DISABLED};
                background: {c.BG_HOVER};
                border: 1px solid {c.BORDER};
                border-radius: 3px;
                padding: 3px 8px;
                font-size: {ty.SIZE_XS}pt;
                font-weight: bold;
                letter-spacing: 0.6px;
            }}
            QLabel#heroDotLbl {{
                color: {c.TEXT_DISABLED};
                font-size: {ty.SIZE_XS}pt;
                letter-spacing: 0.5px;
                background: transparent;
            }}
            QFrame#heroSep {{
                background: {c.BORDER};
                max-height: 1px;
            }}
            QWidget#metaCell {{
                background: transparent;
            }}
            QLabel#metaKey {{
                color: {c.TEXT_DISABLED};
                font-size: {ty.SIZE_XS}pt;
                letter-spacing: 0.5px;
                background: transparent;
            }}
            QLabel#metaVal {{
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_BODY}pt;
                font-weight: bold;
                font-family: 'Consolas', monospace;
                background: transparent;
            }}
            QFrame#metaDiv {{
                background: {c.BORDER};
                max-width: 1px;
            }}
        """)

    def update_data(self, strategy: dict, signal: str = "WAIT", threshold: float = 0.6):
        try:
            if not strategy:
                return
            c = self._c

            # Name
            name = str(strategy.get("name", "—"))
            if self._name_lbl:
                self._name_lbl.setText(name)

            # Description
            desc = strategy.get("description", "")
            if self._desc_lbl:
                if desc:
                    self._desc_lbl.setText(desc[:100] + ("…" if len(desc) > 100 else ""))
                    self._desc_lbl.setVisible(True)
                else:
                    self._desc_lbl.setVisible(False)

            # Signal chip
            sig_meta = _SIG.get(signal, _SIG["WAIT"])
            sig_color = _tok(sig_meta["attr"])
            if self._sig_lbl:
                self._sig_lbl.setText(sig_meta["label"])
                self._sig_lbl.setStyleSheet(f"""
                    color: {sig_color};
                    background: {sig_color}1A;
                    border: 1px solid {sig_color}66;
                    border-radius: 3px;
                    padding: 3px 8px;
                    font-size: {_ty().SIZE_XS}pt;
                    font-weight: bold;
                    letter-spacing: 0.6px;
                """)
                if self._dot:
                    self._dot.set_color(sig_color if signal != "WAIT" else _tok("TEXT_DISABLED"))

            # Meta stats
            engine = strategy.get("engine", {}) or {}
            total_rules = sum(
                len((engine.get(s) or {}).get("rules", []))
                for s in SIGNAL_GROUPS
            )
            tf = (strategy.get("timeframe", "1h") or "1h").upper()
            upd = strategy.get("updated_at", "—")
            if upd and "T" in upd:
                upd = upd.replace("T", " ")[:10]

            vals = {
                "RULES": str(total_rules),
                "TIMEFRAME": tf,
                "CONF": f"{int(threshold * 100)}%",
                "SAVED": upd or "—",
            }
            for key, val in vals.items():
                lbl = self._meta_labels.get(key)
                if lbl:
                    lbl.setText(val)

        except Exception as e:
            logger.error(f"[_HeroStrip.update_data] {e}", exc_info=True)

    def apply_theme(self, _=None):
        self._restyle()


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY ROW WIDGET  (inline list item)
# ─────────────────────────────────────────────────────────────────────────────

class _StratRow(QWidget, _TM):
    """
    Single list row:
      [▌] Name                    [4h]  [12r]  [⚡]
    Active row has an amber left stripe.
    """

    def __init__(self, name: str, timeframe: str, rule_count: int,
                 is_active: bool, parent=None):
        super().__init__(parent)
        self._is_active = is_active
        self._build(name, timeframe, rule_count, is_active)

    def _build(self, name, timeframe, rule_count, is_active):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 10, 0)
        lay.setSpacing(0)
        self.setStyleSheet("background: transparent;")

        c = self._c
        ty = self._ty
        accent = _tok("YELLOW_BRIGHT")

        # Left accent stripe (4 px)
        stripe = QFrame()
        stripe.setFixedWidth(4)
        stripe.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        stripe.setStyleSheet(
            f"background: {accent}; border-radius: 0px;"
            if is_active else
            "background: transparent;"
        )
        lay.addWidget(stripe)

        # Name
        name_lbl = QLabel(name)
        name_lbl.setContentsMargins(10, 0, 0, 0)
        name_lbl.setStyleSheet(f"""
            color: {accent if is_active else c.TEXT_MAIN};
            font-size: {ty.SIZE_BODY}pt;
            font-weight: {'bold' if is_active else 'normal'};
            background: transparent;
        """)
        lay.addWidget(name_lbl, 1)

        # Timeframe pill
        tf_lbl = QLabel(timeframe.upper())
        tf_lbl.setAlignment(Qt.AlignCenter)
        tf_lbl.setStyleSheet(f"""
            color: {_tok('PURPLE')};
            background: {_tok('PURPLE')}1A;
            border: 1px solid {_tok('PURPLE')}44;
            border-radius: 999px;
            padding: 0 7px;
            font-size: {ty.SIZE_XS}pt;
            font-weight: bold;
            font-family: 'Consolas', monospace;
        """)
        lay.addWidget(tf_lbl)
        lay.addSpacing(6)

        # Rule count pill
        r_lbl = QLabel(f"{rule_count}r")
        r_lbl.setAlignment(Qt.AlignCenter)
        dim = c.TEXT_DISABLED
        r_lbl.setStyleSheet(f"""
            color: {dim};
            background: {dim}1A;
            border: 1px solid {dim}33;
            border-radius: {_sp().RADIUS_SM}px;
            padding: 0 5px;
            font-size: {ty.SIZE_XS}pt;
            font-family: 'Consolas', monospace;
        """)
        lay.addWidget(r_lbl)

        # Active bolt icon
        if is_active:
            lay.addSpacing(6)
            bolt = QLabel("⚡")
            bolt.setStyleSheet(f"color: {accent}; font-size: {ty.SIZE_SM}pt; background: transparent;")
            lay.addWidget(bolt)

        self.setMinimumHeight(38)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class StrategyPickerSidebar(QDialog, _TM):
    """
    Ops Command Panel — compact frameless picker.
    440 × 700–920 px. Draggable title bar. 2-s live refresh.
    """

    strategy_activated = pyqtSignal(str)
    open_editor_requested = pyqtSignal()

    # ── Init ──────────────────────────────────────────────────────────────────

    def __init__(self, trading_app=None, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent, Qt.Window | Qt.Tool)
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setFixedWidth(440)
            self.setMinimumHeight(660)
            self.setMaximumHeight(940)

            self.trading_app = trading_app
            self._drag_pos = None

            try:
                theme_manager.theme_changed.connect(self.apply_theme)
                theme_manager.density_changed.connect(self.apply_theme)
            except Exception:
                pass

            self._build_ui()
            self.refresh()
            self.apply_theme()

            self._timer = QTimer(self)
            self._timer.timeout.connect(self._refresh_data)
            self._timer.start(2000)

            logger.info("StrategyPickerSidebar (Ops Panel redesign) initialized")

        except Exception as e:
            logger.critical(f"[StrategyPickerSidebar.__init__] {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        self.trading_app = None
        self._current_signal = "WAIT"
        self._current_threshold = 0.6
        self._conf_cells: Dict[str, _ConfCell] = {}
        self._timer = None
        self._hero = None
        self._list = None
        self._activate_btn = None
        self._status_lbl = None
        self._count_lbl = None
        self._last_snapshot = {}
        self._last_snapshot_time = None
        self._snapshot_cache_secs = 0.1
        self._drag_pos = None
        self._outer = None

    # ── Error fallback ────────────────────────────────────────────────────────

    def _create_error_dialog(self, parent):
        try:
            super().__init__(parent, Qt.Window | Qt.Tool)
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)
            root = QVBoxLayout(self)
            root.setContentsMargins(16, 16, 16, 16)
            card = QFrame()
            card.setStyleSheet(
                f"background:{_p().BG_PANEL}; "
                f"border:1px solid {_p().RED}; border-radius:8px;"
            )
            lay = QVBoxLayout(card)
            lbl = QLabel("❌ Strategy Picker failed to initialise.\nCheck logs.")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"color:{_p().RED_BRIGHT}; padding:20px; "
                f"font-size:{_ty().SIZE_MD}pt;"
            )
            lay.addWidget(lbl)
            btn = QPushButton("Close")
            btn.clicked.connect(self.close)
            lay.addWidget(btn, 0, Qt.AlignCenter)
            root.addWidget(card)
        except Exception as e:
            logger.error(f"[_create_error_dialog] {e}", exc_info=True)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        self._outer = QFrame()
        self._outer.setObjectName("outerFrame")

        outer_lay = QVBoxLayout(self._outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        outer_lay.addWidget(self._build_title_bar())
        outer_lay.addWidget(self._hero_section())
        outer_lay.addWidget(self._build_conf_grid())
        outer_lay.addWidget(self._make_section_header(
            "ALL STRATEGIES", show_count=True
        ))
        outer_lay.addWidget(self._build_list(), 1)
        outer_lay.addWidget(self._build_footer())

        root.addWidget(self._outer)
        self._style_outer()

    # ── Title bar ─────────────────────────────────────────────────────────────

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(44)
        bar.mousePressEvent = self._drag_start
        bar.mouseMoveEvent = self._drag_move
        bar.mouseReleaseEvent = lambda e: setattr(self, "_drag_pos", None)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(8)

        # Monogram logo box
        logo = QLabel("SP")
        logo.setFixedSize(26, 26)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(f"""
            color: {_p().BG_MAIN};
            background: {_tok('YELLOW_BRIGHT')};
            border-radius: 4px;
            font-size: {_ty().SIZE_XS}pt;
            font-weight: 900;
            font-family: 'Consolas', monospace;
            letter-spacing: 0.5px;
        """)
        lay.addWidget(logo)

        title = QLabel("STRATEGY PICKER")
        title.setStyleSheet(f"""
            color: {_p().TEXT_MAIN};
            font-size: {_ty().SIZE_SM}pt;
            font-weight: bold;
            letter-spacing: 1.8px;
            background: transparent;
        """)
        lay.addWidget(title)
        lay.addStretch()

        # Refresh
        ref = self._icon_btn("↺", tooltip="Refresh")
        ref.clicked.connect(self.refresh)
        lay.addWidget(ref)

        # Close
        cls = self._icon_btn("✕")
        cls.clicked.connect(self.hide)
        cls.setProperty("danger", True)
        lay.addWidget(cls)

        return bar

    def _icon_btn(self, text: str, tooltip: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.PointingHandCursor)
        if tooltip:
            btn.setToolTip(tooltip)
        c = _p()
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {c.TEXT_DIM};
                border: none;
                border-radius: 14px;
                font-size: {_ty().SIZE_BODY}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
            }}
            QPushButton[danger=true]:hover {{
                background: {c.RED};
                color: white;
            }}
        """)
        return btn

    # ── Hero strip ────────────────────────────────────────────────────────────

    def _hero_section(self) -> _HeroStrip:
        self._hero = _HeroStrip()
        return self._hero

    # ── 2-column confidence grid ──────────────────────────────────────────────

    def _build_conf_grid(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("confWrapper")

        v = QVBoxLayout(wrapper)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        v.addWidget(self._make_section_header("SIGNAL CONFIDENCE"))

        grid_w = QWidget()
        grid_w.setObjectName("confGrid")
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(10, 8, 10, 10)
        grid.setSpacing(6)

        # 5 signals → row0:cols0-1, row1:cols0-1, row2:col0 (HOLD centred)
        positions = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]
        for (row, col), sig in zip(positions, SIGNAL_GROUPS):
            cell = _ConfCell(sig)
            grid.addWidget(cell, row, col)
            self._conf_cells[sig] = cell
        # Span HOLD across both columns
        hold_cell = self._conf_cells.get("HOLD")
        if hold_cell:
            grid.removeWidget(hold_cell)
            grid.addWidget(hold_cell, 2, 0, 1, 2)

        v.addWidget(grid_w)
        return wrapper

    # ── Section header ────────────────────────────────────────────────────────

    def _make_section_header(self, title: str, show_count: bool = False) -> QWidget:
        hdr = QWidget()
        hdr.setObjectName("sectionHdr")
        hdr.setFixedHeight(30)
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(8)

        accent_dot = QFrame()
        accent_dot.setFixedSize(5, 5)
        accent_dot.setStyleSheet(
            f"background:{_tok('YELLOW_BRIGHT')}; border-radius:3px;"
        )
        lay.addWidget(accent_dot)

        lbl = QLabel(title)
        lbl.setStyleSheet(f"""
            color: {_p().TEXT_DISABLED};
            font-size: {_ty().SIZE_XS}pt;
            font-weight: bold;
            letter-spacing: 1.0px;
            background: transparent;
        """)
        lay.addWidget(lbl)
        lay.addStretch()

        if show_count:
            self._count_lbl = QLabel()
            self._count_lbl.setStyleSheet(f"""
                color: {_p().TEXT_DISABLED};
                font-size: {_ty().SIZE_XS}pt;
                font-family: 'Consolas', monospace;
                background: transparent;
            """)
            lay.addWidget(self._count_lbl)

        return hdr

    # ── Strategy list ─────────────────────────────────────────────────────────

    def _build_list(self) -> QListWidget:
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        self._list.setMinimumHeight(140)
        self._restyle_list()
        return self._list

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("footer")
        footer.setFixedHeight(56)

        lay = QHBoxLayout(footer)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        # Editor button (ghost)
        ed_btn = QPushButton("Open Editor")
        ed_btn.setCursor(Qt.PointingHandCursor)
        ed_btn.setFixedHeight(36)
        c = _p()
        ed_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {c.TEXT_DIM};
                border: 1px solid {c.BORDER};
                border-radius: {_sp().RADIUS_MD}px;
                padding: 0 14px;
                font-size: {_ty().SIZE_SM}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border-color: {_tok('YELLOW_BRIGHT')};
                color: {_tok('YELLOW_BRIGHT')};
            }}
        """)
        ed_btn.clicked.connect(self._on_open_editor)
        lay.addWidget(ed_btn)

        lay.addStretch()

        # Status
        self._status_lbl = QLabel()
        self._status_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._status_lbl.setStyleSheet(
            f"color:{c.TEXT_DIM}; font-size:{_ty().SIZE_XS}pt; background:transparent;"
        )
        lay.addWidget(self._status_lbl)

        # Activate button (solid amber)
        self._activate_btn = QPushButton("⚡  Activate")
        self._activate_btn.setCursor(Qt.PointingHandCursor)
        self._activate_btn.setFixedHeight(36)
        accent = _tok("YELLOW_BRIGHT")
        self._activate_btn.setStyleSheet(f"""
            QPushButton {{
                background: {accent};
                color: {c.BG_MAIN};
                border: none;
                border-radius: {_sp().RADIUS_MD}px;
                padding: 0 18px;
                font-size: {_ty().SIZE_SM}pt;
                font-weight: bold;
                letter-spacing: 0.3px;
            }}
            QPushButton:hover {{
                background: {_tok('ORANGE')};
            }}
            QPushButton:disabled {{
                background: {c.BG_HOVER};
                color: {c.TEXT_DISABLED};
            }}
        """)
        self._activate_btn.clicked.connect(self._on_activate)
        lay.addWidget(self._activate_btn)

        return footer

    # ── Styling helpers ───────────────────────────────────────────────────────

    def _style_outer(self):
        c = _p()
        self._outer.setStyleSheet(f"""
            QFrame#outerFrame {{
                background: {c.BG_MAIN};
                border: 1px solid {c.BORDER_STRONG};
                border-top: 2px solid {_tok('YELLOW_BRIGHT')};
                border-radius: 8px;
            }}
            QWidget#titleBar {{
                background: {c.BG_PANEL};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom: 1px solid {c.BORDER};
            }}
            QWidget#confWrapper {{
                background: {c.BG_MAIN};
                border-bottom: 1px solid {c.BORDER};
            }}
            QWidget#confGrid {{
                background: transparent;
            }}
            QWidget#sectionHdr {{
                background: {c.BG_PANEL};
                border-bottom: 1px solid {c.BORDER};
                border-top: 1px solid {c.BORDER};
            }}
            QWidget#footer {{
                background: {c.BG_PANEL};
                border-top: 1px solid {c.BORDER};
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
        """)

    def _restyle_list(self):
        c = _p()
        ty = _ty()
        accent = _tok("YELLOW_BRIGHT")
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: {c.BG_MAIN};
                color: {c.TEXT_MAIN};
                border: none;
                outline: none;
                font-size: {ty.SIZE_BODY}pt;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {c.BORDER};
                padding: 0;
            }}
            QListWidget::item:selected {{
                background: {c.BG_SELECTED};
            }}
            QListWidget::item:hover:!selected {{
                background: {c.BG_HOVER};
            }}
            QScrollBar:vertical {{
                background: {c.BG_PANEL};
                width: 4px;
                border-radius: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {c.BORDER_STRONG};
                border-radius: 2px;
                min-height: 16px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    # ── Theme apply ───────────────────────────────────────────────────────────

    def apply_theme(self, _=None):
        try:
            self._style_outer()
            self._restyle_list()
            if self._hero:
                self._hero._restyle()
            for cell in self._conf_cells.values():
                cell._restyle()
        except Exception as e:
            logger.error(f"[apply_theme] {e}", exc_info=True)

    # ── Dragging ──────────────────────────────────────────────────────────────

    def _drag_start(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def _drag_move(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(e.globalPos() - self._drag_pos)

    # ── Data refresh ──────────────────────────────────────────────────────────

    def refresh(self):
        try:
            if self._list is None:
                return

            self._list.blockSignals(True)
            self._list.clear()

            strategies = strategy_manager.list_strategies()
            active_slug = strategy_manager.get_active_slug()

            for s in strategies:
                try:
                    slug = s.get("slug", "")
                    is_active = slug == active_slug
                    full = strategy_manager.get(slug) or {}
                    engine = full.get("engine", {}) or {}
                    rule_count = sum(
                        len((engine.get(sig) or {}).get("rules", []))
                        for sig in SIGNAL_GROUPS
                    )
                    timeframe = (full.get("timeframe", "1h") or "1h")

                    item = QListWidgetItem()
                    item.setData(Qt.UserRole, slug)
                    row_w = _StratRow(
                        name=s.get("name", "Unknown"),
                        timeframe=timeframe,
                        rule_count=rule_count,
                        is_active=is_active,
                    )
                    item.setSizeHint(row_w.sizeHint())
                    self._list.addItem(item)
                    self._list.setItemWidget(item, row_w)

                except Exception as ex:
                    logger.warning(f"Failed to build strategy row: {ex}")

            self._list.blockSignals(False)

            if self._count_lbl:
                n = len(strategies)
                self._count_lbl.setText(f"{n} total")

            self._update_active_display()

        except Exception as e:
            logger.error(f"[refresh] {e}", exc_info=True)

    @pyqtSlot()
    def _refresh_data(self):
        try:
            if not self.isVisible():
                return
            self._update_active_display()
        except Exception as e:
            logger.debug(f"[_refresh_data] {e}")

    def _get_cached_snapshot(self) -> dict:
        from datetime import datetime
        now = datetime.now()
        if (self._last_snapshot_time is None or
                (now - self._last_snapshot_time).total_seconds() > self._snapshot_cache_secs):
            self._last_snapshot = state_manager.get_snapshot()
            self._last_snapshot_time = now
        return self._last_snapshot

    def _update_active_display(self):
        try:
            position_snap = state_manager.get_position_snapshot()
            signal_value = position_snap.get("option_signal", "WAIT")

            try:
                signal_snap = state_manager.get_state().get_option_signal_snapshot()
                confidence = signal_snap.get("confidence", {})
                threshold = signal_snap.get("threshold", 0.6)
            except Exception:
                confidence = {}
                threshold = 0.6

            active = strategy_manager.get_active()
            if active is not None:
                engine = active.get("engine", {}) or {}
                threshold = float(engine.get("min_confidence", threshold))

                if self._hero is not None:
                    self._hero.update_data(active, signal_value, threshold)

                for sig, cell in self._conf_cells.items():
                    cell.set_confidence(float(confidence.get(sig, 0.0)), threshold)

        except Exception as e:
            logger.error(f"[_update_active_display] {e}", exc_info=True)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_double_click(self, item):
        try:
            if item:
                self._activate(item.data(Qt.UserRole))
        except Exception as e:
            logger.error(f"[_on_double_click] {e}", exc_info=True)

    def _on_activate(self):
        try:
            if self._list is None:
                return
            item = self._list.currentItem()
            if item:
                self._activate(item.data(Qt.UserRole))
        except Exception as e:
            logger.error(f"[_on_activate] {e}", exc_info=True)

    def _activate(self, slug: str):
        try:
            if not slug:
                return
            current = strategy_manager.get_active_slug()
            if current == slug:
                data = strategy_manager.get(slug) or {}
                self._set_status(f"✓ Already active: {data.get('name', slug)}", "green")
                return

            self._set_status("⏳ Activating…", "yellow")

            def _do():
                try:
                    ok = strategy_manager.activate(slug)
                    m = "_on_activation_success" if ok else "_on_activation_failure"
                    QMetaObject.invokeMethod(
                        self, m, Qt.QueuedConnection, Q_ARG(str, slug)
                    )
                except Exception as ex:
                    QMetaObject.invokeMethod(
                        self, "_on_activation_error",
                        Qt.QueuedConnection, Q_ARG(str, str(ex))
                    )

            from concurrent.futures import ThreadPoolExecutor
            ex = ThreadPoolExecutor(max_workers=1)
            ex.submit(_do)
            ex.shutdown(wait=False)

        except Exception as e:
            logger.error(f"[_activate] {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_activation_success(self, slug: str):
        try:
            self.refresh()
            QTimer.singleShot(100, lambda: self.strategy_activated.emit(slug))
            data = strategy_manager.get(slug) or {}
            self._set_status(f"✓ {data.get('name', slug)}", "green", 3000)
        except Exception as e:
            logger.error(f"[_on_activation_success] {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_activation_failure(self, slug: str):
        self._set_status(f"✗ Failed: {slug}", "red", 3000)

    @pyqtSlot(str)
    def _on_activation_error(self, error: str):
        self._set_status(f"✗ {error[:45]}", "red", 5000)

    def _set_status(self, msg: str, color: str = "neutral", clear_ms: int = 0):
        if not self._status_lbl:
            return
        col = {"green": _p().GREEN_BRIGHT, "yellow": _p().YELLOW_BRIGHT,
               "red": _p().RED_BRIGHT}.get(color, _p().TEXT_DIM)
        self._status_lbl.setStyleSheet(
            f"color:{col}; font-size:{_ty().SIZE_XS}pt; "
            f"font-weight:bold; background:transparent;"
        )
        self._status_lbl.setText(msg)
        if clear_ms:
            QTimer.singleShot(
                clear_ms,
                lambda: self._status_lbl.clear() if self._status_lbl else None
            )

    def _on_open_editor(self):
        try:
            self.open_editor_requested.emit()
        except Exception as e:
            logger.error(f"[_on_open_editor] {e}", exc_info=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def cleanup(self):
        try:
            if self._timer and self._timer.isActive():
                self._timer.stop()
            self._timer = None
            self.trading_app = None
            self._hero = None
            self._list = None
            self._activate_btn = None
            self._status_lbl = None
            self._last_snapshot = {}
            self._last_snapshot_time = None
            self._conf_cells.clear()
        except Exception as e:
            logger.error(f"[cleanup] {e}", exc_info=True)

    def closeEvent(self, event):
        try:
            if self._timer and self._timer.isActive():
                self._timer.stop()
            self.hide()
            event.ignore()
        except Exception:
            event.ignore()

    def showEvent(self, event):
        try:
            super().showEvent(event)
            if self._timer and not self._timer.isActive():
                self._timer.start(2000)
        except Exception as e:
            logger.error(f"[showEvent] {e}", exc_info=True)
