"""
backtest/backtest_candle_debug_tab.py
======================================
In-memory candle debug viewer — replaces the JSON file dump from CandleDebugger.

Usage
-----
1.  Add a CandleDebugTab to your BacktestWindow's QTabWidget:

        self._debug_tab = CandleDebugTab(parent=self)
        self._tabs.addTab(self._debug_tab, "🔍 Candle Debug")

2.  After a backtest run finishes, feed the debugger's entries into the tab:

        self._debug_tab.load(debugger.get_entries())

3.  The tab populates automatically. Clicking "🔍 Detail" on any row opens
    a full popup with every field from the candle record.

Layout
------
┌─────────────────────────────────────────────────────────────────┐
│  🔍 Candle Debugger   [2 000 candles]   Filter: [_________] [×] │
│  Signal: [ALL ▾]  Action: [ALL ▾]   Skip: [ALL ▾]              │
├────┬──────────────────┬───────┬────────────┬─────────┬──────────┤
│  # │ Time             │Signal │ Action     │ Skip    │          │
├────┼──────────────────┼───────┼────────────┼─────────┼──────────┤
│  0 │ 2026-01-15 09:25 │  WAIT │ WAIT       │         │ 🔍Detail │
│  1 │ 2026-01-15 09:30 │  BUY… │ BUY_CALL   │         │ 🔍Detail │
└────┴──────────────────┴───────┴────────────┴─────────┴──────────┘
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QSortFilterProxyModel, QTimer
from PyQt5.QtGui import QColor, QFont, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QTabWidget,
    QTableView, QTextEdit, QVBoxLayout, QWidget, QHeaderView,
    QApplication, QMessageBox
)

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)

SIGNAL_GROUPS = ["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]


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


def get_signal_colors():
    """Get signal colors from theme manager."""
    c = theme_manager.palette
    return {
        "BUY_CALL": c.GREEN,
        "BUY_PUT": c.BLUE,
        "EXIT_CALL": c.RED,
        "EXIT_PUT": c.ORANGE,
        "HOLD": c.YELLOW,
        "WAIT": c.TEXT_DIM,
    }


def get_action_colors():
    """Get action colors from theme manager."""
    return get_signal_colors()  # Same mapping


# ── Table column definitions ──────────────────────────────────────────────────
_COLS = ["#", "Time", "Signal", "Conf%", "Action", "Pos", "Spot Close", "Skip", ""]
_COL_IDX = 0
_COL_TIME = 1
_COL_SIG = 2
_COL_CONF = 3
_COL_ACT = 4
_COL_POS = 5
_COL_SPOT = 6
_COL_SKIP = 7
_COL_BTN = 8  # button placeholder (real buttons added via QPersistentModelIndex)


# ── Stylesheet function ───────────────────────────────────────────────────────
def _ss() -> str:
    """Generate stylesheet with current theme tokens."""
    c = theme_manager.palette
    ty = theme_manager.typography
    sp = theme_manager.spacing

    return f"""
        QWidget, QDialog {{
            background: {c.BG_MAIN};
            color: {c.TEXT_MAIN};
            font-size: {ty.SIZE_BODY}pt;
        }}
        QTableView {{
            background: {c.BG_PANEL};
            alternate-background-color: {c.BG_HOVER};
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: {sp.RADIUS_SM}px;
            gridline-color: {c.BORDER};
            selection-background-color: {c.BG_SELECTED};
        }}
        QTableView::item {{
            padding: {sp.PAD_XS}px {sp.PAD_XS}px;
        }}
        QHeaderView::section {{
            background: {c.BG_HOVER};
            color: {c.TEXT_DIM};
            border: none;
            border-right: {sp.SEPARATOR}px solid {c.BORDER};
            border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
            padding: {sp.PAD_XS}px {sp.PAD_SM}px;
            font-size: {ty.SIZE_XS}pt;
            font-weight: {ty.WEIGHT_BOLD};
        }}
        QComboBox {{
            background: {c.BG_HOVER};
            color: {c.TEXT_MAIN};
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: {sp.RADIUS_SM}px;
            padding: {sp.PAD_XS}px {sp.PAD_SM}px;
            min-width: 100px;
        }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background: {c.BG_PANEL};
            color: {c.TEXT_MAIN};
            selection-background-color: {c.BG_SELECTED};
        }}
        QLineEdit {{
            background: {c.BG_HOVER};
            color: {c.TEXT_MAIN};
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: {sp.RADIUS_SM}px;
            padding: {sp.PAD_XS}px {sp.PAD_SM}px;
        }}
        QPushButton {{
            background: {c.BG_HOVER};
            color: {c.TEXT_MAIN};
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: {sp.RADIUS_SM}px;
            padding: {sp.PAD_XS}px {sp.PAD_MD}px;
        }}
        QPushButton:hover {{ background: {c.BG_SELECTED}; border-color: {c.BLUE}; }}
        QPushButton:pressed {{ background: {c.BG_MAIN}; }}
        QGroupBox {{
            background: {c.BG_PANEL};
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: {sp.RADIUS_MD}px;
            margin-top: {sp.PAD_MD}px;
            font-weight: {ty.WEIGHT_BOLD};
            color: {c.TEXT_MAIN};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: {sp.PAD_MD}px;
            padding: 0 {sp.PAD_XS}px;
            color: {c.BLUE};
        }}
        QLabel {{ color: {c.TEXT_MAIN}; }}
        QScrollArea {{ border: none; background: {c.BG_MAIN}; }}
        QTextEdit {{
            background: {c.BG_PANEL};
            color: {c.TEXT_MAIN};
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: {sp.RADIUS_SM}px;
            font-family: {ty.FONT_MONO};
            font-size: {ty.SIZE_XS}pt;
        }}
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
            padding: {sp.PAD_XS}px {sp.PAD_MD}px;
            border-radius: {sp.RADIUS_SM}px {sp.RADIUS_SM}px 0 0;
        }}
        QTabBar::tab:selected {{
            background: {c.BG_PANEL};
            color: {c.TEXT_MAIN};
            border-bottom: {sp.PAD_XS}px solid {c.BLUE};
        }}
    """


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def _f(v, decimals: int = 2) -> str:
    """Format a numeric value for display."""
    if v is None:
        return "—"
    try:
        return f"{float(v):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def _sep_v() -> QFrame:
    """Vertical separator line."""
    c = theme_manager.palette
    sep = QFrame()
    sep.setFrameShape(QFrame.VLine)
    sep.setStyleSheet(f"color: {c.BORDER};")
    return sep


def _kv(key: str, val: str, val_color_token: str = "TEXT_MAIN") -> QFrame:
    """Key-value pair widget for the position/tpsl panels."""
    c = theme_manager.palette
    sp = theme_manager.spacing
    ty = theme_manager.typography

    f = QFrame()
    f.setStyleSheet(f"background:{c.BG_HOVER}; border:{sp.SEPARATOR}px solid {c.BORDER}; border-radius:{sp.RADIUS_SM}px;")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(sp.PAD_SM, sp.PAD_XS, sp.PAD_SM, sp.PAD_XS)
    lay.setSpacing(sp.GAP_XS)

    k_lb = QLabel(key)
    k_lb.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
    lay.addWidget(k_lb)

    v_lb = QLabel(val or "—")
    v_lb.setStyleSheet(f"color:{c.get(val_color_token, c.TEXT_MAIN)}; font-size:{ty.SIZE_BODY}pt; font-weight:{ty.WEIGHT_BOLD};")
    lay.addWidget(v_lb)

    return f


def _ohlc_group(title: str, ohlc: Dict, extra_label: str = "") -> QGroupBox:
    """Compact OHLC display group box."""
    c = theme_manager.palette
    sp = theme_manager.spacing

    box = QGroupBox(title)
    box.setStyleSheet(
        f"QGroupBox {{ background:{c.BG_HOVER}; border:{sp.SEPARATOR}px solid {c.BORDER}; "
        f"border-radius:{sp.RADIUS_MD}px; margin-top:{sp.PAD_MD}px; }}"
        f"QGroupBox::title {{ color:{c.ORANGE}; left:{sp.PAD_MD}px; padding:0 {sp.PAD_XS}px; }}"
    )
    grid = QGridLayout(box)
    grid.setSpacing(sp.GAP_SM)

    fields = [("Open", "open", "TEXT_MAIN"), ("High", "high", "GREEN"),
              ("Low", "low", "RED"), ("Close", "close", "ORANGE")]
    for i, (lbl, key, color_token) in enumerate(fields):
        r, c_pos = divmod(i, 2)
        grid.addWidget(_kv(lbl, _f(ohlc.get(key), 2), val_color_token=color_token), r, c_pos)

    if extra_label:
        lb = QLabel(extra_label)
        lb.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{theme_manager.typography.SIZE_XS}pt; padding:{sp.PAD_XS}px {sp.PAD_XS}px;")
        grid.addWidget(lb, 2, 0, 1, 2)

    return box


def _filter_combo(name: str, options: List[str]) -> QComboBox:
    cb = QComboBox()
    cb.addItems(options)
    cb.setToolTip(f"Filter by {name}")
    return cb


# ─────────────────────────────────────────────────────────────────────────────
# CandleDetailPopup — shown when user clicks "🔍 Detail"
# ─────────────────────────────────────────────────────────────────────────────
class CandleDetailPopup(QDialog, ThemedMixin):
    """
    Full-detail popup for a single candle record.
    Organised into tabbed sections: Overview, Signals, Indicators, Position, TP/SL.
    """

    def __init__(self, entry: Dict[str, Any], parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent, Qt.Window)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self._entry = entry
            self._build_ui()
            self.apply_theme()
        except Exception as e:
            logger.error(f"[CandleDetailPopup.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent, Qt.Window)

    def _safe_defaults_init(self):
        self._entry = {}

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the popup."""
        try:
            self.setStyleSheet(_ss())
            logger.debug("[CandleDetailPopup.apply_theme] Applied theme")
        except Exception as e:
            logger.error(f"[CandleDetailPopup.apply_theme] Failed: {e}", exc_info=True)

    def _build_ui(self):
        c = self._c
        sp = self._sp
        ty = self._ty
        signal_colors = get_signal_colors()
        action_colors = get_action_colors()

        bar = self._entry.get("bar_index", "?")
        time = self._entry.get("time", "")
        sig = self._entry.get("resolved_signal", "WAIT")
        act = self._entry.get("action", "WAIT")

        sig_color = signal_colors.get(sig, c.TEXT_DIM)
        act_color = action_colors.get(act, c.TEXT_DIM)

        self.setWindowTitle(f"🔍 Candle #{bar}  —  {time}")
        self.setMinimumSize(820, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        root.setSpacing(sp.GAP_SM)

        # ── Header bar ────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setStyleSheet(f"background:{c.BG_PANEL}; border:{sp.SEPARATOR}px solid {c.BORDER}; border-radius:{sp.RADIUS_MD}px;")
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM)

        def _hdr_lbl(text, color_token="TEXT_MAIN", bold=False):
            lb = QLabel(text)
            lb.setStyleSheet(f"color:{c.get(color_token, c.TEXT_MAIN)}; font-size:{ty.SIZE_BODY}pt;" + (" font-weight:bold;" if bold else ""))
            return lb

        hdr_row.addWidget(_hdr_lbl(f"Bar #{bar}", "BLUE", bold=True))
        hdr_row.addWidget(_sep_v())
        hdr_row.addWidget(_hdr_lbl(time, "TEXT_DIM"))
        hdr_row.addStretch()

        spot = self._entry.get("spot", {})
        hdr_row.addWidget(_hdr_lbl(
            f"SPOT  O:{_f(spot.get('open'))}  H:{_f(spot.get('high'))}  L:{_f(spot.get('low'))}  C:{_f(spot.get('close'))}",
            "ORANGE"))
        hdr_row.addWidget(_sep_v())
        hdr_row.addWidget(_hdr_lbl(f"Signal: {sig}", sig_color, bold=True))
        hdr_row.addWidget(_sep_v())
        hdr_row.addWidget(_hdr_lbl(f"Action: {act}", act_color, bold=True))

        skip = self._entry.get("skip_reason")
        if skip:
            hdr_row.addWidget(_sep_v())
            hdr_row.addWidget(_hdr_lbl(f"⏭ Skipped: {skip}", "YELLOW"))

        root.addWidget(hdr)

        # ── Tabs ──────────────────────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.addTab(self._build_overview_tab(), "📋 Overview")
        tabs.addTab(self._build_signals_tab(), "📊 Signals")
        tabs.addTab(self._build_indicators_tab(), "📈 Indicators")
        tabs.addTab(self._build_position_tab(), "💼 Position & TP/SL")
        tabs.addTab(self._build_raw_tab(), "🗂 Raw JSON")
        root.addWidget(tabs)

        # ── Footer ────────────────────────────────────────────────────────────
        foot = QHBoxLayout()
        foot.addStretch()
        close_btn = QPushButton("✕ Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        foot.addWidget(close_btn)
        root.addLayout(foot)

    # ── Tab builders ──────────────────────────────────────────────────────────

    def _build_overview_tab(self) -> QWidget:
        c = self._c
        sp = self._sp
        ty = self._ty

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_MD)

        # Explanation
        expl = self._entry.get("explanation", "")
        if expl:
            expl_box = QGroupBox("💬 Explanation")
            expl_lay = QVBoxLayout(expl_box)
            for part in expl.split(" | "):
                part = part.strip()
                if not part:
                    continue
                lb = QLabel(part)
                lb.setWordWrap(True)
                lb.setStyleSheet(f"color:{c.TEXT_MAIN}; font-size:{ty.SIZE_XS}pt; padding:{sp.PAD_XS}px;")
                expl_lay.addWidget(lb)
            lay.addWidget(expl_box)

        # bt_override
        override = self._entry.get("bt_override", "")
        if override:
            ov_box = QGroupBox("⚙ Backtest Override")
            ov_lay = QVBoxLayout(ov_box)
            lb = QLabel(override)
            lb.setWordWrap(True)
            lb.setStyleSheet(f"color:{c.YELLOW};")
            ov_lay.addWidget(lb)
            lay.addWidget(ov_box)

        # Spot + option OHLC side by side
        ohlc_row = QHBoxLayout()

        spot = self._entry.get("spot", {})
        ohlc_row.addWidget(_ohlc_group("📍 Spot OHLC", spot))

        opt = self._entry.get("option")
        if opt:
            ohlc_row.addWidget(_ohlc_group(
                f"📄 Option: {opt.get('symbol', '')}", opt,
                extra_label=f"Source: {opt.get('price_source', '?')}"
            ))

        lay.addLayout(ohlc_row)
        lay.addStretch()
        return w

    def _build_signals_tab(self) -> QWidget:
        c = self._c
        sp = self._sp
        signal_colors = get_signal_colors()

        w = QScrollArea()
        w.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_MD)

        signal_groups = self._entry.get("signal_groups", {})
        if not signal_groups:
            lb = QLabel("No signal group data available for this candle.")
            lb.setStyleSheet(f"color:{c.TEXT_DIM}; padding:{sp.PAD_XL}px;")
            lay.addWidget(lb)
        else:
            for grp in SIGNAL_GROUPS:
                data = signal_groups.get(grp)
                if not data:
                    continue
                lay.addWidget(self._build_signal_group_box(grp, data))

        lay.addStretch()
        w.setWidget(inner)
        return w

    def _build_signal_group_box(self, grp: str, data: Dict) -> QGroupBox:
        c = self._c
        sp = self._sp
        ty = self._ty
        signal_colors = get_signal_colors()

        conf = data.get("confidence", 0.0)
        thresh = data.get("threshold", 0.6)
        fired = data.get("fired", False)
        rules = data.get("rules", [])

        color = signal_colors.get(grp, c.TEXT_DIM)
        pct = int(conf * 100)

        if fired:
            status_txt = "✅ FIRED"
            status_color = c.GREEN
        elif conf >= thresh:
            status_txt = "⚠️ SUPPRESSED"
            status_color = c.YELLOW
        else:
            status_txt = "✗ MISS"
            status_color = c.RED

        box = QGroupBox(f"{grp}  —  {pct}%  {status_txt}")
        box.setStyleSheet(
            f"QGroupBox {{ border: {sp.SEPARATOR}px solid {color}40; border-radius:{sp.RADIUS_MD}px; "
            f"background:{c.BG_HOVER}; margin-top:{sp.PAD_MD}px; }}"
            f"QGroupBox::title {{ color:{color}; left:{sp.PAD_MD}px; padding:0 {sp.PAD_XS}px; }}"
        )
        lay = QVBoxLayout(box)
        lay.setSpacing(sp.GAP_XS)

        # Confidence bar
        conf_row = QHBoxLayout()
        conf_lbl = QLabel(f"Confidence: {pct}%  (threshold {int(thresh * 100)}%)")
        conf_lbl.setStyleSheet(f"color:{color}; font-weight:{ty.WEIGHT_BOLD};")
        conf_row.addWidget(conf_lbl)
        conf_row.addStretch()
        status_lbl = QLabel(status_txt)
        status_lbl.setStyleSheet(f"color:{status_color}; font-weight:{ty.WEIGHT_BOLD};")
        conf_row.addWidget(status_lbl)
        lay.addLayout(conf_row)

        # Conf bar visual
        bar_frame = QFrame()
        bar_frame.setFixedHeight(sp.PROGRESS_SM)
        bar_frame.setStyleSheet(f"background:{c.BORDER}; border-radius:{sp.RADIUS_SM}px;")
        bar_inner = QFrame(bar_frame)
        bar_inner.setFixedHeight(sp.PROGRESS_SM)
        bar_inner.setStyleSheet(f"background:{color}; border-radius:{sp.RADIUS_SM}px;")
        bar_inner.setFixedWidth(max(4, int(pct * 3)))  # ~300px max
        lay.addWidget(bar_frame)

        # Rules table
        if rules:
            hdr_row = QHBoxLayout()
            for txt, w_px in [("✓/✗", 30), ("Rule", 220), ("Detail", 220), ("Wt", 40)]:
                lb = QLabel(txt)
                lb.setFixedWidth(w_px)
                lb.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt; font-weight:{ty.WEIGHT_BOLD};")
                hdr_row.addWidget(lb)
            hdr_row.addStretch()
            lay.addLayout(hdr_row)

            for r in rules:
                passed = r.get("passed", False)
                rule_s = r.get("rule", "?")
                detail = r.get("detail", "")
                weight = r.get("weight", 1.0)
                error = r.get("error")

                row = QHBoxLayout()
                row.setSpacing(sp.GAP_XS)

                tick = QLabel("✓" if passed else "✗")
                tick.setFixedWidth(30)
                tick.setStyleSheet(f"color:{c.GREEN if passed else c.RED}; font-weight:{ty.WEIGHT_BOLD};")
                row.addWidget(tick)

                rule_lb = QLabel(rule_s)
                rule_lb.setFixedWidth(220)
                rule_lb.setStyleSheet(f"color:{c.TEXT_MAIN}; font-size:{ty.SIZE_XS}pt;")
                row.addWidget(rule_lb)

                det_lb = QLabel(detail if detail else "—")
                det_lb.setFixedWidth(220)
                det_lb.setStyleSheet(f"color:{c.TEAL if passed else c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
                row.addWidget(det_lb)

                wt_lb = QLabel(f"{weight:.1f}")
                wt_lb.setFixedWidth(40)
                wt_lb.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
                row.addWidget(wt_lb)

                if error:
                    err_lb = QLabel(f"⚠ {error}")
                    err_lb.setStyleSheet(f"color:{c.RED}; font-size:{ty.SIZE_XS}pt;")
                    row.addWidget(err_lb)

                row.addStretch()

                rule_frame = QFrame()
                rule_frame.setStyleSheet(
                    f"background:{c.BG_ROW_B if passed else c.BG_ROW_A}; "
                    f"border:{sp.SEPARATOR}px solid {c.GREEN if passed else c.RED}; "
                    f"border-radius:{sp.RADIUS_SM}px; margin:{sp.PAD_XS}px;"
                )
                rule_frame.setLayout(row)
                lay.addWidget(rule_frame)

        return box

    def _build_indicators_tab(self) -> QWidget:
        c = self._c
        sp = self._sp
        ty = self._ty

        w = QScrollArea()
        w.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_XS)

        indicators = self._entry.get("indicators", {})
        if not indicators:
            lb = QLabel("No indicator data for this candle.")
            lb.setStyleSheet(f"color:{c.TEXT_DIM}; padding:{sp.PAD_XL}px;")
            lay.addWidget(lb)
        else:
            # Header
            hdr = QFrame()
            hdr.setStyleSheet(f"background:{c.BG_HOVER}; border-radius:{sp.RADIUS_SM}px;")
            hdr_row = QHBoxLayout(hdr)
            hdr_row.setContentsMargins(sp.PAD_SM, sp.PAD_XS, sp.PAD_SM, sp.PAD_XS)
            for txt, stretch in [("Indicator", 3), ("Last", 1), ("Prev", 1), ("Δ", 1)]:
                lb = QLabel(txt)
                lb.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt; font-weight:{ty.WEIGHT_BOLD};")
                hdr_row.addWidget(lb, stretch)
            lay.addWidget(hdr)

            for key, val in sorted(indicators.items()):
                row_frame = QFrame()
                row_frame.setStyleSheet(
                    f"background:{c.BG_PANEL}; border-bottom:{sp.SEPARATOR}px solid {c.BORDER};"
                )
                row_lay = QHBoxLayout(row_frame)
                row_lay.setContentsMargins(sp.PAD_SM, sp.PAD_XS, sp.PAD_SM, sp.PAD_XS)

                key_lb = QLabel(str(key))
                key_lb.setStyleSheet(f"color:{c.BLUE}; font-size:{ty.SIZE_XS}pt; font-family:{ty.FONT_MONO};")
                row_lay.addWidget(key_lb, 3)

                if isinstance(val, dict):
                    last = val.get("last")
                    prev = val.get("prev")
                    last_str = _f(last, 4)
                    prev_str = _f(prev, 4)
                    if last is not None and prev is not None:
                        delta = last - prev
                        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
                        delta_color = c.GREEN if delta > 0 else c.RED if delta < 0 else c.TEXT_DIM
                        delta_str = f"{arrow} {abs(delta):.4f}"
                    else:
                        delta_str = "—"
                        delta_color = c.TEXT_DIM
                else:
                    last_str = _f(val, 4)
                    prev_str = "—"
                    delta_str = "—"
                    delta_color = c.TEXT_DIM

                last_lb = QLabel(last_str)
                last_lb.setStyleSheet(f"color:{c.TEXT_MAIN}; font-size:{ty.SIZE_XS}pt;")
                row_lay.addWidget(last_lb, 1)

                prev_lb = QLabel(prev_str)
                prev_lb.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
                row_lay.addWidget(prev_lb, 1)

                delta_lb = QLabel(delta_str)
                delta_lb.setStyleSheet(f"color:{delta_color}; font-size:{ty.SIZE_XS}pt;")
                row_lay.addWidget(delta_lb, 1)

                lay.addWidget(row_frame)

        lay.addStretch()
        w.setWidget(inner)
        return w

    def _build_position_tab(self) -> QWidget:
        c = self._c
        sp = self._sp
        ty = self._ty

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_MD)

        pos = self._entry.get("position", {})
        tpsl = self._entry.get("tp_sl", {})

        # Position group
        pos_box = QGroupBox("💼 Position")
        pos_grid = QGridLayout(pos_box)
        pos_grid.setSpacing(sp.GAP_SM)

        cur = pos.get("current")
        pos_fields = [
            ("Current", cur or "FLAT", "GREEN" if cur else "TEXT_DIM"),
            ("Entry Time", pos.get("entry_time") or "—", "TEXT_MAIN"),
            ("Entry Spot", _f(pos.get("entry_spot")), "ORANGE"),
            ("Entry Option", _f(pos.get("entry_option")), "ORANGE"),
            ("Strike", str(pos.get("strike") or "—"), "TEXT_MAIN"),
            ("Bars In Trade", str(pos.get("bars_in_trade", 0)), "BLUE"),
            ("Buy Price", _f(pos.get("buy_price")), "TEXT_MAIN"),
            ("Trailing High", _f(pos.get("trailing_high")), "TEAL"),
        ]
        for i, (lbl, val, color_token) in enumerate(pos_fields):
            r, c_pos = divmod(i, 2)
            pos_grid.addWidget(_kv(lbl, val, val_color_token=color_token), r, c_pos)

        lay.addWidget(pos_box)

        # TP/SL group
        tpsl_box = QGroupBox("🎯 TP / SL")
        tpsl_grid = QGridLayout(tpsl_box)
        tpsl_grid.setSpacing(sp.GAP_SM)

        def _hit_lbl(hit: bool, label: str) -> QLabel:
            lb = QLabel(f"{'✅ HIT' if hit else '—'}")
            lb.setStyleSheet(f"color:{c.RED if hit else c.TEXT_DIM}; font-weight:{ty.WEIGHT_BOLD if hit else ty.WEIGHT_NORMAL};")
            return lb

        tpsl_fields = [
            ("TP Price", _f(tpsl.get("tp_price"))),
            ("SL Price", _f(tpsl.get("sl_price"))),
            ("Trailing SL Price", _f(tpsl.get("trailing_sl_price"))),
            ("Index SL Level", _f(tpsl.get("index_sl_level"))),
            ("Current Option Px", _f(tpsl.get("current_option_price"))),
        ]
        for i, (lbl, val) in enumerate(tpsl_fields):
            r, c_pos = divmod(i, 2)
            tpsl_grid.addWidget(_kv(lbl, val), r, c_pos)

        # Hit indicators
        hits_row = QHBoxLayout()
        for flag_key, label in [
            ("tp_hit", "TP Hit"),
            ("sl_hit", "SL Hit"),
            ("trailing_sl_hit", "Trailing SL Hit"),
            ("index_sl_hit", "Index SL Hit"),
        ]:
            hit = bool(tpsl.get(flag_key, False))
            hits_row.addWidget(_hit_lbl(hit, label))
        hits_row.addStretch()

        tpsl_grid.addLayout(hits_row, 3, 0, 1, 2)
        lay.addWidget(tpsl_box)
        lay.addStretch()
        return w

    def _build_raw_tab(self) -> QWidget:
        """Show the raw entry dict as formatted JSON."""
        import json
        c = self._c
        sp = self._sp
        ty = self._ty

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)

        te = QTextEdit()
        te.setReadOnly(True)
        te.setFont(QFont(ty.FONT_MONO, ty.SIZE_XS))
        try:
            te.setPlainText(json.dumps(self._entry, indent=2, default=str))
        except Exception as e:
            te.setPlainText(f"Error serialising entry: {e}")

        copy_btn = QPushButton("📋 Copy JSON")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(te.toPlainText()))
        copy_btn.setFixedWidth(120)

        lay.addWidget(te)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(copy_btn)
        lay.addLayout(btn_row)
        return w


# ─────────────────────────────────────────────────────────────────────────────
# CandleDebugTab — the main tab widget
# ─────────────────────────────────────────────────────────────────────────────
class CandleDebugTab(QWidget, ThemedMixin):
    """
    Tab widget that displays candle debug records from CandleDebugger.get_entries().

    Drop it into any QTabWidget:
        tab = CandleDebugTab(parent=self)
        self._tabs.addTab(tab, "🔍 Candle Debug")

    Feed data after a backtest run:
        tab.load(debugger.get_entries())
    """

    def __init__(self, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self._entries: List[Dict] = []
            self._filtered: List[Dict] = []
            self._popup: Optional[CandleDetailPopup] = None
            self._build_ui()
            self.apply_theme()
        except Exception as e:
            logger.error(f"[CandleDebugTab.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self._entries = []
        self._filtered = []
        self._popup = None
        self._count_lbl = None
        self._search = None
        self._sig_filter = None
        self._act_filter = None
        self._skip_filter = None
        self._pos_filter = None
        self._result_lbl = None
        self._status_lbl = None
        self._table_model = None
        self._table = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the tab."""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            self.setStyleSheet(_ss())

            # Update title
            title = self.findChild(QLabel, "title")
            if title:
                title.setStyleSheet(f"color:{c.BLUE}; font-size:{ty.SIZE_BODY}pt; font-weight:{ty.WEIGHT_BOLD};")

            # Update count label
            if self._count_lbl:
                self._count_lbl.setStyleSheet(
                    f"background:{c.BG_HOVER}; color:{c.TEXT_DIM}; border:{sp.SEPARATOR}px solid {c.BORDER}; "
                    f"border-radius:{sp.RADIUS_PILL}px; padding:{sp.PAD_XS}px {sp.PAD_SM}px; font-size:{ty.SIZE_XS}pt;"
                )

            # Update result label
            if self._result_lbl:
                self._result_lbl.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")

            # Update status label
            if self._status_lbl:
                self._status_lbl.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")

            # Refresh table colors
            self._populate_table(self._filtered)

            logger.debug("[CandleDebugTab.apply_theme] Applied theme")
        except Exception as e:
            logger.error(f"[CandleDebugTab.apply_theme] Failed: {e}", exc_info=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, entries: List[Dict[str, Any]]) -> None:
        """Load a list of candle debug records (from CandleDebugger.get_entries())."""
        self._entries = entries or []
        self._refresh_filter()
        self._count_lbl.setText(f"  {len(self._entries):,} candles  ")

        if len(self._entries) == 0:
            self._status_lbl.setText("No debug data available. Make sure debug_candles=True in config.")
        else:
            self._status_lbl.setText(f"Loaded {len(self._entries)} candle records")

        logger.debug(f"[CandleDebugTab] Loaded {len(self._entries)} candle records")

    def clear(self) -> None:
        """Remove all records from the view."""
        self._entries = []
        self._filtered = []
        self._table_model.setRowCount(0)
        self._count_lbl.setText("  0 candles  ")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        c = self._c
        sp = self._sp
        ty = self._ty

        root = QVBoxLayout(self)
        root.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)
        root.setSpacing(sp.GAP_XS)

        # ── Toolbar row 1: title + count + search ─────────────────────────────
        tb1 = QHBoxLayout()
        tb1.setSpacing(sp.GAP_SM)

        title = QLabel("🔍 Candle Debugger")
        title.setObjectName("title")
        title.setStyleSheet(f"color:{c.BLUE}; font-size:{ty.SIZE_BODY}pt; font-weight:{ty.WEIGHT_BOLD};")
        tb1.addWidget(title)

        self._count_lbl = QLabel("  0 candles  ")
        tb1.addWidget(self._count_lbl)
        tb1.addStretch()

        srch_lbl = QLabel("🔎 Search:")
        srch_lbl.setStyleSheet(f"color:{c.TEXT_DIM};")
        tb1.addWidget(srch_lbl)

        self._search = QLineEdit()
        self._search.setPlaceholderText("time, indicator, signal…")
        self._search.setFixedWidth(200)
        self._search.textChanged.connect(self._refresh_filter)
        tb1.addWidget(self._search)

        clr_btn = QPushButton("✕")
        clr_btn.setFixedWidth(28)
        clr_btn.setToolTip("Clear search")
        clr_btn.clicked.connect(lambda: self._search.clear())
        tb1.addWidget(clr_btn)

        root.addLayout(tb1)

        # ── Toolbar row 2: filters ────────────────────────────────────────────
        tb2 = QHBoxLayout()
        tb2.setSpacing(sp.GAP_SM)

        signal_options = ["ALL"] + list(get_signal_colors().keys())
        self._sig_filter = _filter_combo("Signal", signal_options)
        self._sig_filter.currentTextChanged.connect(self._refresh_filter)
        tb2.addWidget(QLabel("Signal:"))
        tb2.addWidget(self._sig_filter)

        self._act_filter = _filter_combo("Action", signal_options)
        self._act_filter.currentTextChanged.connect(self._refresh_filter)
        tb2.addWidget(QLabel("Action:"))
        tb2.addWidget(self._act_filter)

        self._skip_filter = _filter_combo("Skip", ["ALL", "NONE", "SIDEWAY", "MARKET_CLOSED", "WARMUP"])
        self._skip_filter.currentTextChanged.connect(self._refresh_filter)
        tb2.addWidget(QLabel("Skip:"))
        tb2.addWidget(self._skip_filter)

        self._pos_filter = _filter_combo("Position", ["ALL", "FLAT", "CALL", "PUT"])
        self._pos_filter.currentTextChanged.connect(self._refresh_filter)
        tb2.addWidget(QLabel("Pos:"))
        tb2.addWidget(self._pos_filter)

        tb2.addStretch()

        self._result_lbl = QLabel("")
        self._result_lbl.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
        tb2.addWidget(self._result_lbl)

        root.addLayout(tb2)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table_model = QStandardItemModel(0, len(_COLS))
        self._table_model.setHorizontalHeaderLabels(_COLS)

        self._table = QTableView()
        self._table.setModel(self._table_model)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setShowGrid(True)
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._on_double_click)

        # Column widths (design requirement, can stay as integers)
        hdr = self._table.horizontalHeader()
        hdr.resizeSection(_COL_IDX, 45)
        hdr.resizeSection(_COL_TIME, 145)
        hdr.resizeSection(_COL_SIG, 95)
        hdr.resizeSection(_COL_CONF, 60)
        hdr.resizeSection(_COL_ACT, 95)
        hdr.resizeSection(_COL_POS, 60)
        hdr.resizeSection(_COL_SPOT, 90)
        hdr.resizeSection(_COL_SKIP, 100)
        hdr.resizeSection(_COL_BTN, 80)

        root.addWidget(self._table, 1)

        # ── Status bar ────────────────────────────────────────────────────────
        status_row = QHBoxLayout()
        self._status_lbl = QLabel("No data loaded. Run a backtest to populate.")
        self._status_lbl.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
        status_row.addWidget(self._status_lbl)
        status_row.addStretch()

        hint = QLabel("Double-click or click 🔍 Detail to inspect a candle")
        hint.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
        status_row.addWidget(hint)

        root.addLayout(status_row)

    # ── Filter / populate ─────────────────────────────────────────────────────

    def _refresh_filter(self):
        """Re-apply all filters and repopulate the table."""
        sig_f = self._sig_filter.currentText()
        act_f = self._act_filter.currentText()
        skip_f = self._skip_filter.currentText()
        pos_f = self._pos_filter.currentText()
        search = self._search.text().strip().lower()

        result = []
        for e in self._entries:
            if sig_f != "ALL" and e.get("resolved_signal", "WAIT") != sig_f:
                continue
            if act_f != "ALL" and e.get("action", "WAIT") != act_f:
                continue

            skip = e.get("skip_reason") or ""
            if skip_f == "NONE" and skip:
                continue
            elif skip_f not in ("ALL", "NONE") and skip != skip_f:
                continue

            cur_pos = (e.get("position") or {}).get("current") or "FLAT"
            if pos_f != "ALL" and cur_pos != pos_f:
                continue

            if search:
                haystack = (
                        str(e.get("time", "")) + " " +
                        str(e.get("resolved_signal", "")) + " " +
                        str(e.get("action", "")) + " " +
                        str(e.get("skip_reason", "")) + " " +
                        str(e.get("explanation", ""))
                ).lower()
                if search not in haystack:
                    continue

            result.append(e)

        self._filtered = result
        self._populate_table(result)
        self._result_lbl.setText(f"Showing {len(result):,} of {len(self._entries):,}")
        self._status_lbl.setText(
            f"{len(result):,} candles shown" if result
            else "No candles match the current filters."
        )

    def _populate_table(self, entries: List[Dict]):
        c = self._c
        signal_colors = get_signal_colors()
        action_colors = get_action_colors()

        model = self._table_model
        model.setRowCount(0)

        # Disable sorting while populating for performance
        self._table.setSortingEnabled(False)

        def _item(text, color=None, align=Qt.AlignLeft | Qt.AlignVCenter) -> QStandardItem:
            it = QStandardItem(str(text))
            it.setTextAlignment(align)
            it.setEditable(False)
            if color:
                it.setForeground(color)
            return it

        for e in entries:
            sig = e.get("resolved_signal", "WAIT")
            act = e.get("action", "WAIT")
            skip = e.get("skip_reason") or ""
            pos = (e.get("position") or {}).get("current") or "FLAT"
            spot_c = (e.get("spot") or {}).get("close")
            time = e.get("time", "")
            bar = e.get("bar_index", 0)

            # Best confidence across fired signal groups
            sg = e.get("signal_groups", {})
            best_conf = 0.0
            for grp, gd in sg.items():
                if isinstance(gd, dict) and gd.get("fired"):
                    best_conf = max(best_conf, gd.get("confidence", 0.0))
            conf_str = f"{int(best_conf * 100)}%" if best_conf else "—"

            sig_color = QColor(signal_colors.get(sig, c.TEXT_DIM))
            act_color = QColor(action_colors.get(act, c.TEXT_DIM))
            pos_color = QColor(c.GREEN if pos == "CALL" else c.BLUE if pos == "PUT" else c.TEXT_DIM)
            skip_color = QColor(c.YELLOW) if skip else None

            row = [
                _item(str(bar), align=Qt.AlignRight | Qt.AlignVCenter),
                _item(time),
                _item(sig, color=sig_color),
                _item(conf_str, align=Qt.AlignCenter),
                _item(act, color=act_color),
                _item(pos, color=pos_color),
                _item(_f(spot_c), align=Qt.AlignRight | Qt.AlignVCenter),
                _item(skip, color=skip_color),
                _item("🔍 Detail"),  # placeholder text; real click handled below
            ]

            # Store the entry index so we can retrieve it on click
            row[0].setData(e, Qt.UserRole)

            model.appendRow(row)

        self._table.setSortingEnabled(True)

        # Set up click handler on the "Detail" column
        self._table.clicked.connect(self._on_cell_clicked)

    # ── Click handlers ────────────────────────────────────────────────────────

    def _on_cell_clicked(self, index):
        if index.column() == _COL_BTN:
            self._open_detail_for_row(index.row())

    def _on_double_click(self, index):
        self._open_detail_for_row(index.row())

    def _open_detail_for_row(self, visual_row: int):
        """Open the CandleDetailPopup for the row at visual_row."""
        try:
            # Retrieve entry from the UserRole data stored in column 0
            idx_item = self._table_model.item(visual_row, _COL_IDX)
            if idx_item is None:
                return
            entry = idx_item.data(Qt.UserRole)
            if not isinstance(entry, dict):
                return
            self._show_detail(entry)
        except Exception as e:
            logger.error(f"[CandleDebugTab._open_detail_for_row] {e}", exc_info=True)

    def _show_detail(self, entry: Dict):
        """Open or reuse the detail popup."""
        if self._popup and self._popup.isVisible():
            self._popup.close()
        self._popup = CandleDetailPopup(entry, parent=self)
        self._popup.setWindowModality(Qt.NonModal)
        self._popup.show()
        self._popup.raise_()
        self._popup.activateWindow()

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        """Clean up resources."""
        try:
            if self._popup and self._popup.isVisible():
                self._popup.close()
            self._popup = None
            self._entries = []
            self._filtered = []
            self._table_model.clear()
        except Exception as e:
            logger.error(f"[CandleDebugTab.cleanup] Failed: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup."""
        self.cleanup()
        super().closeEvent(event)