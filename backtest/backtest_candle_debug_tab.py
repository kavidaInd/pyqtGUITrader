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

logger = logging.getLogger(__name__)

# ── Palette (matches the rest of the project) ────────────────────────────────
BG = "#0d1117"
BG_PANEL = "#161b22"
BG_ITEM = "#1c2128"
BG_SEL = "#1f3d5c"
BORDER = "#30363d"
TEXT = "#e6edf3"
DIM = "#8b949e"
GREEN = "#3fb950"
RED = "#f85149"
BLUE = "#58a6ff"
YELLOW = "#d29922"
ORANGE = "#ffa657"
PURPLE = "#bc8cff"
TEAL = "#39d0d8"

SIGNAL_COLORS: Dict[str, str] = {
    "BUY_CALL": GREEN,
    "BUY_PUT": BLUE,
    "EXIT_CALL": RED,
    "EXIT_PUT": ORANGE,
    "HOLD": YELLOW,
    "WAIT": DIM,
}

ACTION_COLORS: Dict[str, str] = {
    "BUY_CALL": GREEN,
    "BUY_PUT": BLUE,
    "EXIT_CALL": RED,
    "EXIT_PUT": ORANGE,
    "HOLD": YELLOW,
    "WAIT": DIM,
}

SIGNAL_GROUPS = ["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]

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


# ── Stylesheet ─────────────────────────────────────────────────────────────────
def _ss() -> str:
    return f"""
        QWidget, QDialog {{
            background: {BG};
            color: {TEXT};
            font-size: 10pt;
        }}
        QTableView {{
            background: {BG_PANEL};
            alternate-background-color: {BG_ITEM};
            border: 1px solid {BORDER};
            border-radius: 4px;
            gridline-color: {BORDER};
            selection-background-color: {BG_SEL};
        }}
        QTableView::item {{
            padding: 3px 6px;
        }}
        QHeaderView::section {{
            background: {BG_ITEM};
            color: {DIM};
            border: none;
            border-right: 1px solid {BORDER};
            border-bottom: 1px solid {BORDER};
            padding: 4px 8px;
            font-size: 9pt;
            font-weight: bold;
        }}
        QComboBox {{
            background: {BG_ITEM};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 3px 8px;
            min-width: 100px;
        }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background: {BG_PANEL};
            color: {TEXT};
            selection-background-color: {BG_SEL};
        }}
        QLineEdit {{
            background: {BG_ITEM};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 3px 8px;
        }}
        QPushButton {{
            background: {BG_ITEM};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 5px 12px;
        }}
        QPushButton:hover {{ background: {BG_SEL}; border-color: {BLUE}; }}
        QPushButton:pressed {{ background: {BG}; }}
        QGroupBox {{
            background: {BG_PANEL};
            border: 1px solid {BORDER};
            border-radius: 6px;
            margin-top: 10px;
            font-weight: bold;
            color: {TEXT};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
            color: {BLUE};
        }}
        QLabel {{ color: {TEXT}; }}
        QScrollArea {{ border: none; background: {BG}; }}
        QTextEdit {{
            background: {BG_PANEL};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            font-family: Consolas, monospace;
            font-size: 9pt;
        }}
        QTabWidget::pane {{
            border: 1px solid {BORDER};
            border-radius: 4px;
            background: {BG_PANEL};
        }}
        QTabBar::tab {{
            background: {BG_ITEM};
            color: {DIM};
            border: 1px solid {BORDER};
            border-bottom: none;
            padding: 5px 12px;
            border-radius: 4px 4px 0 0;
        }}
        QTabBar::tab:selected {{
            background: {BG_PANEL};
            color: {TEXT};
            border-bottom: 2px solid {BLUE};
        }}
    """


# ─────────────────────────────────────────────────────────────────────────────
# CandleDetailPopup — shown when user clicks "🔍 Detail"
# ─────────────────────────────────────────────────────────────────────────────
class CandleDetailPopup(QDialog):
    """
    Full-detail popup for a single candle record.
    Organised into tabbed sections: Overview, Signals, Indicators, Position, TP/SL.
    """

    def __init__(self, entry: Dict[str, Any], parent=None):
        super().__init__(parent, Qt.Window)
        self._entry = entry
        self._build_ui()

    def _build_ui(self):
        bar = self._entry.get("bar_index", "?")
        time = self._entry.get("time", "")
        sig = self._entry.get("resolved_signal", "WAIT")
        act = self._entry.get("action", "WAIT")

        sig_color = SIGNAL_COLORS.get(sig, DIM)
        act_color = ACTION_COLORS.get(act, DIM)

        self.setWindowTitle(f"🔍 Candle #{bar}  —  {time}")
        self.setMinimumSize(820, 640)
        self.setStyleSheet(_ss())

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Header bar ────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setStyleSheet(f"background:{BG_PANEL}; border:1px solid {BORDER}; border-radius:6px;")
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(12, 8, 12, 8)

        def _hdr_lbl(text, color=TEXT, bold=False):
            lb = QLabel(text)
            lb.setStyleSheet(f"color:{color}; font-size:11pt;" + (" font-weight:bold;" if bold else ""))
            return lb

        hdr_row.addWidget(_hdr_lbl(f"Bar #{bar}", BLUE, bold=True))
        hdr_row.addWidget(_sep_v())
        hdr_row.addWidget(_hdr_lbl(time, DIM))
        hdr_row.addStretch()

        spot = self._entry.get("spot", {})
        hdr_row.addWidget(_hdr_lbl(
            f"SPOT  O:{_f(spot.get('open'))}  H:{_f(spot.get('high'))}  L:{_f(spot.get('low'))}  C:{_f(spot.get('close'))}",
            ORANGE))
        hdr_row.addWidget(_sep_v())
        hdr_row.addWidget(_hdr_lbl(f"Signal: {sig}", sig_color, bold=True))
        hdr_row.addWidget(_sep_v())
        hdr_row.addWidget(_hdr_lbl(f"Action: {act}", act_color, bold=True))

        skip = self._entry.get("skip_reason")
        if skip:
            hdr_row.addWidget(_sep_v())
            hdr_row.addWidget(_hdr_lbl(f"⏭ Skipped: {skip}", YELLOW))

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
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

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
                lb.setStyleSheet(f"color:{TEXT}; font-size:9pt; padding:2px;")
                expl_lay.addWidget(lb)
            lay.addWidget(expl_box)

        # bt_override
        override = self._entry.get("bt_override", "")
        if override:
            ov_box = QGroupBox("⚙ Backtest Override")
            ov_lay = QVBoxLayout(ov_box)
            lb = QLabel(override)
            lb.setWordWrap(True)
            lb.setStyleSheet(f"color:{YELLOW};")
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
        w = QScrollArea()
        w.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(12)

        signal_groups = self._entry.get("signal_groups", {})
        if not signal_groups:
            lb = QLabel("No signal group data available for this candle.")
            lb.setStyleSheet(f"color:{DIM}; padding:20px;")
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
        conf = data.get("confidence", 0.0)
        thresh = data.get("threshold", 0.6)
        fired = data.get("fired", False)
        rules = data.get("rules", [])

        color = SIGNAL_COLORS.get(grp, DIM)
        pct = int(conf * 100)

        if fired:
            status_txt = "✅ FIRED"
            status_color = GREEN
        elif conf >= thresh:
            status_txt = "⚠️ SUPPRESSED"
            status_color = YELLOW
        else:
            status_txt = "✗ MISS"
            status_color = RED

        box = QGroupBox(f"{grp}  —  {pct}%  {status_txt}")
        box.setStyleSheet(
            f"QGroupBox {{ border: 1px solid {color}40; border-radius:6px; "
            f"background:{BG_ITEM}; margin-top:10px; }}"
            f"QGroupBox::title {{ color:{color}; left:10px; padding:0 5px; }}"
        )
        lay = QVBoxLayout(box)
        lay.setSpacing(4)

        # Confidence bar
        conf_row = QHBoxLayout()
        conf_lbl = QLabel(f"Confidence: {pct}%  (threshold {int(thresh * 100)}%)")
        conf_lbl.setStyleSheet(f"color:{color}; font-weight:bold;")
        conf_row.addWidget(conf_lbl)
        conf_row.addStretch()
        status_lbl = QLabel(status_txt)
        status_lbl.setStyleSheet(f"color:{status_color}; font-weight:bold;")
        conf_row.addWidget(status_lbl)
        lay.addLayout(conf_row)

        # Conf bar visual
        bar_frame = QFrame()
        bar_frame.setFixedHeight(8)
        bar_frame.setStyleSheet(f"background:{BORDER}; border-radius:4px;")
        bar_inner = QFrame(bar_frame)
        bar_inner.setFixedHeight(8)
        bar_inner.setStyleSheet(f"background:{color}; border-radius:4px;")
        bar_inner.setFixedWidth(max(4, int(pct * 3)))  # ~300px max
        lay.addWidget(bar_frame)

        # Rules table
        if rules:
            hdr_row = QHBoxLayout()
            for txt, w_px in [("✓/✗", 30), ("Rule", 220), ("Detail", 220), ("Wt", 40)]:
                lb = QLabel(txt)
                lb.setFixedWidth(w_px)
                lb.setStyleSheet(f"color:{DIM}; font-size:8pt; font-weight:bold;")
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
                row.setSpacing(6)

                tick = QLabel("✓" if passed else "✗")
                tick.setFixedWidth(30)
                tick.setStyleSheet(f"color:{GREEN if passed else RED}; font-weight:bold;")
                row.addWidget(tick)

                rule_lb = QLabel(rule_s)
                rule_lb.setFixedWidth(220)
                rule_lb.setStyleSheet(f"color:{TEXT}; font-size:9pt;")
                row.addWidget(rule_lb)

                det_lb = QLabel(detail if detail else "—")
                det_lb.setFixedWidth(220)
                det_lb.setStyleSheet(f"color:{TEAL if passed else DIM}; font-size:9pt;")
                row.addWidget(det_lb)

                wt_lb = QLabel(f"{weight:.1f}")
                wt_lb.setFixedWidth(40)
                wt_lb.setStyleSheet(f"color:{DIM}; font-size:9pt;")
                row.addWidget(wt_lb)

                if error:
                    err_lb = QLabel(f"⚠ {error}")
                    err_lb.setStyleSheet(f"color:{RED}; font-size:8pt;")
                    row.addWidget(err_lb)

                row.addStretch()

                rule_frame = QFrame()
                rule_frame.setStyleSheet(
                    f"background:{'#1a2d1a' if passed else '#2d1a1a'}; "
                    f"border:1px solid {'#2a4a2a' if passed else '#4a2a2a'}; "
                    f"border-radius:4px; margin:1px;"
                )
                rule_frame.setLayout(row)
                lay.addWidget(rule_frame)

        return box

    def _build_indicators_tab(self) -> QWidget:
        w = QScrollArea()
        w.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(4)

        indicators = self._entry.get("indicators", {})
        if not indicators:
            lb = QLabel("No indicator data for this candle.")
            lb.setStyleSheet(f"color:{DIM}; padding:20px;")
            lay.addWidget(lb)
        else:
            # Header
            hdr = QFrame()
            hdr.setStyleSheet(f"background:{BG_ITEM}; border-radius:4px;")
            hdr_row = QHBoxLayout(hdr)
            hdr_row.setContentsMargins(8, 4, 8, 4)
            for txt, stretch in [("Indicator", 3), ("Last", 1), ("Prev", 1), ("Δ", 1)]:
                lb = QLabel(txt)
                lb.setStyleSheet(f"color:{DIM}; font-size:9pt; font-weight:bold;")
                hdr_row.addWidget(lb, stretch)
            lay.addWidget(hdr)

            for key, val in sorted(indicators.items()):
                row_frame = QFrame()
                row_frame.setStyleSheet(
                    f"background:{BG_PANEL}; border-bottom:1px solid {BORDER};"
                )
                row_lay = QHBoxLayout(row_frame)
                row_lay.setContentsMargins(8, 3, 8, 3)

                key_lb = QLabel(str(key))
                key_lb.setStyleSheet(f"color:{BLUE}; font-size:9pt; font-family:Consolas,monospace;")
                row_lay.addWidget(key_lb, 3)

                if isinstance(val, dict):
                    last = val.get("last")
                    prev = val.get("prev")
                    last_str = _f(last)
                    prev_str = _f(prev)
                    if last is not None and prev is not None:
                        delta = last - prev
                        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
                        delta_color = GREEN if delta > 0 else RED if delta < 0 else DIM
                        delta_str = f"{arrow} {abs(delta):.4f}"
                    else:
                        delta_str = "—"
                        delta_color = DIM
                else:
                    last_str = _f(val)
                    prev_str = "—"
                    delta_str = "—"
                    delta_color = DIM

                last_lb = QLabel(last_str)
                last_lb.setStyleSheet(f"color:{TEXT}; font-size:9pt;")
                row_lay.addWidget(last_lb, 1)

                prev_lb = QLabel(prev_str)
                prev_lb.setStyleSheet(f"color:{DIM}; font-size:9pt;")
                row_lay.addWidget(prev_lb, 1)

                delta_lb = QLabel(delta_str)
                delta_lb.setStyleSheet(f"color:{delta_color}; font-size:9pt;")
                row_lay.addWidget(delta_lb, 1)

                lay.addWidget(row_frame)

        lay.addStretch()
        w.setWidget(inner)
        return w

    def _build_position_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        pos = self._entry.get("position", {})
        tpsl = self._entry.get("tp_sl", {})

        # Position group
        pos_box = QGroupBox("💼 Position")
        pos_grid = QGridLayout(pos_box)
        pos_grid.setSpacing(8)

        cur = pos.get("current")
        pos_fields = [
            ("Current", cur or "FLAT", GREEN if cur else DIM),
            ("Entry Time", pos.get("entry_time") or "—", TEXT),
            ("Entry Spot", _f(pos.get("entry_spot")), ORANGE),
            ("Entry Option", _f(pos.get("entry_option")), ORANGE),
            ("Strike", str(pos.get("strike") or "—"), TEXT),
            ("Bars In Trade", str(pos.get("bars_in_trade", 0)), BLUE),
            ("Buy Price", _f(pos.get("buy_price")), TEXT),
            ("Trailing High", _f(pos.get("trailing_high")), TEAL),
        ]
        for i, (lbl, val, col) in enumerate(pos_fields):
            r, c = divmod(i, 2)
            pos_grid.addWidget(_kv(lbl, val, val_color=col), r, c)

        lay.addWidget(pos_box)

        # TP/SL group
        tpsl_box = QGroupBox("🎯 TP / SL")
        tpsl_grid = QGridLayout(tpsl_box)
        tpsl_grid.setSpacing(8)

        def _hit_lbl(hit: bool, label: str) -> QLabel:
            lb = QLabel(f"{'✅ HIT' if hit else '—'}")
            lb.setStyleSheet(f"color:{RED if hit else DIM}; font-weight:{'bold' if hit else 'normal'};")
            return lb

        tpsl_fields = [
            ("TP Price", _f(tpsl.get("tp_price"))),
            ("SL Price", _f(tpsl.get("sl_price"))),
            ("Trailing SL Price", _f(tpsl.get("trailing_sl_price"))),
            ("Index SL Level", _f(tpsl.get("index_sl_level"))),
            ("Current Option Px", _f(tpsl.get("current_option_price"))),
        ]
        for i, (lbl, val) in enumerate(tpsl_fields):
            r, c = divmod(i, 2)
            tpsl_grid.addWidget(_kv(lbl, val), r, c)

        # Hit indicators
        hits_row = QHBoxLayout()
        for flag_key, label in [
            ("tp_hit", "TP Hit"),
            ("sl_hit", "SL Hit"),
            ("trailing_sl_hit", "Trailing SL Hit"),
            ("index_sl_hit", "Index SL Hit"),
        ]:
            hit = bool(tpsl.get(flag_key, False))
            pill = QLabel(f"  {'✅' if hit else '○'} {label}  ")
            pill.setStyleSheet(
                f"background:{'#1a3a1a' if hit else BG_ITEM}; "
                f"color:{GREEN if hit else DIM}; "
                f"border:1px solid {'#3fb950' if hit else BORDER}; "
                f"border-radius:10px; padding:2px 6px; font-size:9pt;"
            )
            hits_row.addWidget(pill)
        hits_row.addStretch()

        tpsl_grid.addLayout(hits_row, 3, 0, 1, 2)
        lay.addWidget(tpsl_box)
        lay.addStretch()
        return w

    def _build_raw_tab(self) -> QWidget:
        """Show the raw entry dict as formatted JSON."""
        import json
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        te = QTextEdit()
        te.setReadOnly(True)
        te.setFont(QFont("Consolas", 9))
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
class CandleDebugTab(QWidget):
    """
    Tab widget that displays candle debug records from CandleDebugger.get_entries().

    Drop it into any QTabWidget:
        tab = CandleDebugTab(parent=self)
        self._tabs.addTab(tab, "🔍 Candle Debug")

    Feed data after a backtest run:
        tab.load(debugger.get_entries())
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: List[Dict] = []
        self._filtered: List[Dict] = []
        self._popup: Optional[CandleDetailPopup] = None
        self.setStyleSheet(_ss())
        self._build_ui()

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
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Toolbar row 1: title + count + search ─────────────────────────────
        tb1 = QHBoxLayout()
        tb1.setSpacing(8)

        title = QLabel("🔍 Candle Debugger")
        title.setStyleSheet(f"color:{BLUE}; font-size:12pt; font-weight:bold;")
        tb1.addWidget(title)

        self._count_lbl = QLabel("  0 candles  ")
        self._count_lbl.setStyleSheet(
            f"background:{BG_ITEM}; color:{DIM}; border:1px solid {BORDER}; "
            f"border-radius:10px; padding:2px 8px; font-size:9pt;"
        )
        tb1.addWidget(self._count_lbl)
        tb1.addStretch()

        srch_lbl = QLabel("🔎 Search:")
        srch_lbl.setStyleSheet(f"color:{DIM};")
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
        tb2.setSpacing(8)

        self._sig_filter = _filter_combo("Signal", ["ALL"] + list(SIGNAL_COLORS.keys()))
        self._sig_filter.currentTextChanged.connect(self._refresh_filter)
        tb2.addWidget(QLabel("Signal:"))
        tb2.addWidget(self._sig_filter)

        self._act_filter = _filter_combo("Action", ["ALL"] + list(SIGNAL_COLORS.keys()))
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
        self._result_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt;")
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

        # Column widths
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
        self._status_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt;")
        status_row.addWidget(self._status_lbl)
        status_row.addStretch()

        hint = QLabel("Double-click or click 🔍 Detail to inspect a candle")
        hint.setStyleSheet(f"color:{DIM}; font-size:8pt;")
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
        model = self._table_model
        model.setRowCount(0)

        # Disable sorting while populating for performance
        self._table.setSortingEnabled(False)

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

            sig_color = QColor(SIGNAL_COLORS.get(sig, DIM))
            act_color = QColor(ACTION_COLORS.get(act, DIM))

            def _item(text, color=None, align=Qt.AlignLeft | Qt.AlignVCenter) -> QStandardItem:
                it = QStandardItem(str(text))
                it.setTextAlignment(align)
                it.setEditable(False)
                if color:
                    it.setForeground(color)
                return it

            row = [
                _item(str(bar), align=Qt.AlignRight | Qt.AlignVCenter),
                _item(time),
                _item(sig, color=sig_color),
                _item(conf_str, align=Qt.AlignCenter),
                _item(act, color=act_color),
                _item(pos, color=QColor(GREEN if pos == "CALL" else BLUE if pos == "PUT" else DIM)),
                _item(_f(spot_c), align=Qt.AlignRight | Qt.AlignVCenter),
                _item(skip, color=QColor(YELLOW) if skip else None),
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


# ─────────────────────────────────────────────────────────────────────────────
# Helper widgets and functions
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
    sep = QFrame()
    sep.setFrameShape(QFrame.VLine)
    sep.setStyleSheet(f"color:{BORDER};")
    return sep


def _kv(key: str, val: str, val_color: str = TEXT) -> QFrame:
    """Key-value pair widget for the position/tpsl panels."""
    f = QFrame()
    f.setStyleSheet(f"background:{BG_ITEM}; border:1px solid {BORDER}; border-radius:4px;")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(8, 4, 8, 4)
    lay.setSpacing(2)

    k_lb = QLabel(key)
    k_lb.setStyleSheet(f"color:{DIM}; font-size:8pt;")
    lay.addWidget(k_lb)

    v_lb = QLabel(val or "—")
    v_lb.setStyleSheet(f"color:{val_color}; font-size:10pt; font-weight:bold;")
    lay.addWidget(v_lb)

    return f


def _ohlc_group(title: str, ohlc: Dict, extra_label: str = "") -> QGroupBox:
    """Compact OHLC display group box."""
    box = QGroupBox(title)
    box.setStyleSheet(
        f"QGroupBox {{ background:{BG_ITEM}; border:1px solid {BORDER}; "
        f"border-radius:6px; margin-top:10px; }}"
        f"QGroupBox::title {{ color:{ORANGE}; left:10px; padding:0 5px; }}"
    )
    grid = QGridLayout(box)
    grid.setSpacing(8)

    fields = [("Open", "open", TEXT), ("High", "high", GREEN),
              ("Low", "low", RED), ("Close", "close", ORANGE)]
    for i, (lbl, key, col) in enumerate(fields):
        r, c = divmod(i, 2)
        grid.addWidget(_kv(lbl, _f(ohlc.get(key), 2), val_color=col), r, c)

    if extra_label:
        lb = QLabel(extra_label)
        lb.setStyleSheet(f"color:{DIM}; font-size:8pt; padding:2px 4px;")
        grid.addWidget(lb, 2, 0, 1, 2)

    return box


def _filter_combo(name: str, options: List[str]) -> QComboBox:
    cb = QComboBox()
    cb.addItems(options)
    cb.setToolTip(f"Filter by {name}")
    return cb
