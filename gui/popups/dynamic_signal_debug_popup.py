"""
dynamic_signal_debug_popup.py
==============================
Signal Intelligence Console — full redesign.

Layout philosophy
─────────────────
• Full-width header: resolved signal (large) + 5 fired pills + key stats
• Two-column body:
    LEFT  (60%) — scrollable list of signal-group cards, each containing
                  a proper rule breakdown table with readable column widths
    RIGHT (40%) — sticky panel: confidence gauges + indicator values table
• Footer: auto-refresh toggle, status, controls

Key fixes vs old design
────────────────────────
• Rule table has 6 columns — Expression | Indicator | Sub-col | LHS | Op | RHS | Result
  so multi-output indicators (MACD SIGNAL vs MACD LINE, SUPERTREND DIRECTION, etc.)
  are clearly labelled, not crammed into one column
• Indicator values table shows the *cleaned* indicator name + sub-col, not the raw
  cache key (e.g.  "MACD → SIGNAL"  not  "macd_{"fast":12,...}_0_SIGNAL")
• Group cards expand to fit their rules — no more truncated fixed height
• RIGHT panel sticky confidence bars are always visible while scrolling rules
• All widths/padding come from theme_manager spacing tokens
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from Utils.time_utils import IST, ist_now, fmt_display, fmt_stamp
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView,
    QGridLayout, QTabWidget, QTextEdit, QProgressBar,
    QSplitter,
)

from Utils.safe_getattr import safe_hasattr, safe_getattr
from data.trade_state_manager import state_manager
from strategy.dynamic_signal_engine import SIGNAL_COLORS, SIGNAL_LABELS, SIGNAL_GROUPS
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Theme accessors
# ─────────────────────────────────────────────────────────────────────────────

def _p():   return theme_manager.palette
def _ty():  return theme_manager.typography
def _sp():  return theme_manager.spacing
def _tok(attr: str, fallback: str = "#888") -> str:
    return getattr(theme_manager.palette, attr, fallback)


class _TM:
    @property
    def _c(self):  return theme_manager.palette
    @property
    def _ty(self): return theme_manager.typography
    @property
    def _sp(self): return theme_manager.spacing


# ─────────────────────────────────────────────────────────────────────────────
# Signal metadata
# ─────────────────────────────────────────────────────────────────────────────

_SIG_META = {
    "BUY_CALL":  dict(label="BUY CALL",  icon="📈", short="B↑", attr="GREEN_BRIGHT"),
    "BUY_PUT":   dict(label="BUY PUT",   icon="📉", short="B↓", attr="BLUE"),
    "EXIT_CALL": dict(label="EXIT CALL", icon="🔴", short="X↑", attr="RED_BRIGHT"),
    "EXIT_PUT":  dict(label="EXIT PUT",  icon="🔵", short="X↓", attr="ORANGE"),
    "HOLD":      dict(label="HOLD",      icon="⏸",  short="HLD", attr="YELLOW_BRIGHT"),
    "WAIT":      dict(label="WAIT",      icon="—",  short="---", attr="TEXT_DISABLED"),
}

def _sig_color(sig: str) -> str:
    return _tok(_SIG_META.get(sig, _SIG_META["WAIT"])["attr"])


# ─────────────────────────────────────────────────────────────────────────────
# Cache-key parser — turns raw engine cache keys into human labels
# ─────────────────────────────────────────────────────────────────────────────

def _parse_cache_key(raw_key: str) -> Tuple[str, str]:
    """
    Convert a raw cache key like
        macd_{"fast": 12, "slow": 26, "signal": 9}_0_SIGNAL
    into a human pair:
        indicator = "MACD"
        sub_col   = "Signal Line"
    For single-output:
        rsi_{"length": 14}_0_default  →  ("RSI", "")
    Returns (indicator_label, sub_col_label).
    """
    try:
        # Strip the __norm_ prefix used for the normalised dict cache entries
        key = raw_key
        if key.startswith("__norm_"):
            return "", ""   # internal cache entry — skip

        # Pattern:  <indicator>_<json_params>_<shift>_<sub_col_or_default>
        m = re.match(r"^([a-z_]+)_(\{.*\})_(\d+)_(.+)$", key, re.DOTALL)
        if m:
            ind_raw  = m.group(1).upper()
            sub_raw  = m.group(4)
        else:
            # Simpler fallback — just take the first token
            parts = key.split("_")
            ind_raw = parts[0].upper()
            sub_raw = parts[-1] if len(parts) > 1 else ""

        # Map sub_col keys to pretty labels
        _SUB_LABELS = {
            "MACD":       "Line",
            "SIGNAL":     "Signal",
            "HIST":       "Histogram",
            "K":          "%K",
            "D":          "%D",
            "ADX":        "ADX",
            "PLUS_DI":    "+DI",
            "MINUS_DI":   "−DI",
            "PLUS_DM":    "+DM",
            "MINUS_DM":   "−DM",
            "AROON_UP":   "Aroon Up",
            "AROON_DOWN": "Aroon Down",
            "TREND":      "Trend",
            "DIRECTION":  "Direction",
            "LONG":       "Long",
            "SHORT":      "Short",
            "UPPER":      "Upper",
            "MIDDLE":     "Middle",
            "LOWER":      "Lower",
            "BANDWIDTH":  "BW",
            "PERCENT":    "%B",
            "ISA":        "Tenkan",
            "ISB":        "Kijun",
            "ITS":        "Senkou A",
            "IKS":        "Senkou B",
            "ICS":        "Chikou",
            "ADOSC":      "ADOSC",
            "AD":         "AD",
            "KVO":        "KVO",
            "MAIN":       "",
            "default":    "",
        }
        sub_label = _SUB_LABELS.get(sub_raw, sub_raw if sub_raw != "default" else "")
        return ind_raw, sub_label
    except Exception:
        return raw_key, ""


def _fmt_val(v: Any, precision: int = 4) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        import math
        if math.isnan(f) or math.isinf(f):
            return "—"
        if abs(f) >= 10000:
            return f"{f:,.0f}"
        if abs(f) >= 100:
            return f"{f:.2f}"
        if abs(f) >= 1:
            return f"{f:.4f}"
        return f"{f:.6f}"
    except Exception:
        return str(v) if v is not None else "—"


# ─────────────────────────────────────────────────────────────────────────────
# Common stylesheet helpers
# ─────────────────────────────────────────────────────────────────────────────

def _scrollbar_ss() -> str:
    c = _p()
    return f"""
        QScrollBar:vertical {{
            background: {c.BG_PANEL}; width: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{
            background: {c.BORDER_STRONG}; border-radius: 3px; min-height: 20px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: {c.BG_PANEL}; height: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:horizontal {{
            background: {c.BORDER_STRONG}; border-radius: 3px; min-width: 20px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """

def _label(text: str, color: str, size: int, bold: bool = False,
           mono: bool = False) -> QLabel:
    lbl = QLabel(text)
    fw  = "bold" if bold else "normal"
    ff  = "'Consolas', 'Courier New', monospace;" if mono else "inherit;"
    lbl.setStyleSheet(
        f"color:{color}; font-size:{size}pt; font-weight:{fw}; "
        f"font-family:{ff} background:transparent; border:none;"
    )
    return lbl

def _divider(vertical: bool = False) -> QFrame:
    d = QFrame()
    d.setFrameShape(QFrame.VLine if vertical else QFrame.HLine)
    d.setStyleSheet(f"background:{_p().BORDER}; max-{'width' if vertical else 'height'}:1px;")
    return d


# ─────────────────────────────────────────────────────────────────────────────
# FIRED PILL  — header row chips
# ─────────────────────────────────────────────────────────────────────────────

class _FiredPill(QLabel, _TM):
    def __init__(self, sig: str, parent=None):
        super().__init__(parent)
        self._sig   = sig
        self._fired = None
        meta        = _SIG_META.get(sig, _SIG_META["WAIT"])
        self._attr  = meta["attr"]
        self._label = meta["label"]
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(40)
        self.setMinimumWidth(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._paint(False)
        try:
            theme_manager.theme_changed.connect(lambda _: self._paint(self._fired or False))
        except Exception:
            pass

    def _paint(self, fired: bool):
        self._fired = fired
        c   = self._c
        col = _tok(self._attr)
        bg  = f"{col}20" if fired else "transparent"
        bw  = "2" if fired else "1"
        bc  = col if fired else c.BORDER
        tc  = col if fired else c.TEXT_DISABLED
        fw  = "bold"
        self.setText(self._label)
        self.setStyleSheet(f"""
            QLabel {{
                color: {tc};
                background: {bg};
                border: {bw}px solid {bc};
                border-radius: 5px;
                font-size: {self._ty.SIZE_XS}pt;
                font-weight: {fw};
                font-family: 'Consolas', monospace;
                padding: 2px 6px;
            }}
        """)

    def set_fired(self, fired: bool):
        if fired != self._fired:
            self._paint(fired)

    def apply_theme(self, _=None):
        self._paint(self._fired or False)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL BADGE  — large resolved signal display
# ─────────────────────────────────────────────────────────────────────────────

class _SignalBadge(QLabel, _TM):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last = ""
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(56)
        self.setMinimumWidth(180)
        self._paint("WAIT")
        try:
            theme_manager.theme_changed.connect(lambda _: self._paint(self._last or "WAIT"))
        except Exception:
            pass

    def _paint(self, sig: str):
        self._last = sig
        meta  = _SIG_META.get(sig, _SIG_META["WAIT"])
        color = _tok(meta["attr"])
        icon  = meta["icon"]
        lbl   = meta["label"]
        ty    = self._ty
        self.setText(f"{icon}  {lbl}")
        self.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background: {color}18;
                border: 2px solid {color};
                border-radius: 8px;
                font-size: {ty.SIZE_XL}pt;
                font-weight: bold;
                letter-spacing: 1.5px;
                font-family: 'Consolas', monospace;
                padding: 4px 12px;
            }}
        """)

    def update_signal(self, sig: str):
        if sig != self._last:
            self._paint(sig)

    def apply_theme(self, _=None):
        self._paint(self._last or "WAIT")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIDENCE GAUGE  — single signal bar widget
# ─────────────────────────────────────────────────────────────────────────────

class _ConfGauge(QWidget, _TM):
    """
    Full-width confidence gauge for one signal group.
    Shows: [icon label]  [████░░░░]  [73%]  [threshold line annotation]
    """

    def __init__(self, sig: str, parent=None):
        super().__init__(parent)
        meta       = _SIG_META.get(sig, _SIG_META["WAIT"])
        self._attr = meta["attr"]
        self._conf = 0.0
        self._thr  = 0.6

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Signal label
        sig_lbl = QLabel(f"{meta['icon']}  {meta['label']}")
        sig_lbl.setFixedWidth(100)
        sig_lbl.setStyleSheet(f"""
            color: {_tok(meta['attr'])};
            font-size: {_ty().SIZE_XS}pt;
            font-weight: bold;
            font-family: 'Consolas', monospace;
            background: transparent;
        """)
        lay.addWidget(sig_lbl)
        self._sig_lbl = sig_lbl

        # Bar
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        lay.addWidget(self._bar, 1)

        # Percent label
        self._pct_lbl = QLabel("0%")
        self._pct_lbl.setFixedWidth(38)
        self._pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._pct_lbl.setStyleSheet(
            f"font-size:{_ty().SIZE_XS}pt; font-weight:bold; "
            f"font-family:'Consolas',monospace; background:transparent;"
        )
        lay.addWidget(self._pct_lbl)

        # Threshold annotation
        self._thr_lbl = QLabel("/60%")
        self._thr_lbl.setFixedWidth(36)
        self._thr_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._thr_lbl.setStyleSheet(
            f"color:{_p().TEXT_DISABLED}; font-size:{_ty().SIZE_XS}pt; "
            f"font-family:'Consolas',monospace; background:transparent;"
        )
        lay.addWidget(self._thr_lbl)

        self._apply_bar(_tok(meta["attr"]))
        try:
            theme_manager.theme_changed.connect(lambda _: self.set_confidence(self._conf, self._thr))
        except Exception:
            pass

    def _apply_bar(self, col: str):
        c = _p()
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                border: none; border-radius: 4px; background: {c.BG_HOVER};
            }}
            QProgressBar::chunk {{
                border-radius: 4px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {col}44, stop:1 {col});
            }}
        """)

    def set_confidence(self, conf: float, thr: float = 0.6):
        self._conf = conf
        self._thr  = thr
        pct = max(0, min(100, int(conf * 100)))
        self._bar.setValue(pct)
        self._pct_lbl.setText(f"{pct}%")
        self._thr_lbl.setText(f"/{int(thr * 100)}%")

        if conf >= thr:          col_attr = "GREEN_BRIGHT"
        elif conf >= thr * 0.6:  col_attr = "YELLOW_BRIGHT"
        else:                    col_attr = "RED_BRIGHT"
        col = _tok(col_attr)

        self._pct_lbl.setStyleSheet(
            f"color:{col}; font-size:{_ty().SIZE_XS}pt; font-weight:bold; "
            f"font-family:'Consolas',monospace; background:transparent;"
        )
        self._apply_bar(col)


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR VALUES TABLE  — right panel, shows computed indicator values
# ─────────────────────────────────────────────────────────────────────────────

class _IndicatorTable(QWidget, _TM):
    """
    3-column table: Indicator | Sub-col | Last Value | Prev Value
    Parses raw cache keys into human-readable names.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        hdr = _label("INDICATOR VALUES", _tok("YELLOW_BRIGHT"), _ty().SIZE_XS, bold=True)
        hdr.setStyleSheet(
            f"color:{_tok('YELLOW_BRIGHT')}; font-size:{_ty().SIZE_XS}pt; "
            f"font-weight:bold; letter-spacing:0.8px; background:transparent; "
            f"padding:6px 0 4px 0;"
        )
        lay.addWidget(hdr)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Indicator", "Output", "Latest", "Previous"])
        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.Fixed);  hv.resizeSection(0, 80)   # Indicator
        hv.setSectionResizeMode(1, QHeaderView.Fixed);  hv.resizeSection(1, 80)   # Output
        hv.setSectionResizeMode(2, QHeaderView.Stretch)                            # Latest
        hv.setSectionResizeMode(3, QHeaderView.Stretch)                            # Previous
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self._table, 1)
        self._restyle()
        try:
            theme_manager.theme_changed.connect(self._restyle)
        except Exception:
            pass

    def _restyle(self, _=None):
        c = _p(); ty = _ty()
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background: {c.BG_MAIN};
                alternate-background-color: {c.BG_PANEL};
                color: {c.TEXT_MAIN};
                border: none;
                gridline-color: {c.BORDER};
                font-size: {ty.SIZE_SM}pt;
                font-family: 'Consolas', monospace;
                selection-background-color: {c.BG_SELECTED};
            }}
            QHeaderView::section {{
                background: {c.BG_PANEL};
                color: {c.TEXT_DIM};
                border: none;
                border-bottom: 1px solid {c.BORDER};
                border-right: 1px solid {c.BORDER};
                padding: 4px 6px;
                font-size: {ty.SIZE_XS}pt;
                font-weight: bold;
                letter-spacing: 0.4px;
            }}
            QTableCornerButton::section {{ background: {c.BG_PANEL}; border: none; }}
            {_scrollbar_ss()}
        """)

    def update_values(self, indicator_values: Dict[str, Any]):
        """
        indicator_values: dict of  raw_cache_key → {"last": float|None, "prev": float|None}
        """
        try:
            c = _p(); ty = _ty()
            rows = []
            for raw_key, val_dict in (indicator_values or {}).items():
                ind_label, sub_label = _parse_cache_key(raw_key)
                if not ind_label:   # skip internal __norm_ entries
                    continue
                last = val_dict.get("last") if isinstance(val_dict, dict) else None
                prev = val_dict.get("prev") if isinstance(val_dict, dict) else None
                rows.append((ind_label, sub_label, _fmt_val(last), _fmt_val(prev)))

            # Sort: indicator name then sub_col
            rows.sort(key=lambda r: (r[0], r[1]))

            self._table.setRowCount(len(rows))
            for i, (ind, sub, latest, prev) in enumerate(rows):
                self._set_cell(i, 0, ind,    c.TEXT_MAIN)
                self._set_cell(i, 1, sub,    c.TEXT_DIM)
                self._set_cell(i, 2, latest, _tok("BLUE"))
                self._set_cell(i, 3, prev,   c.TEXT_DISABLED)
        except Exception as e:
            logger.error(f"[_IndicatorTable.update_values] {e}", exc_info=True)

    def _set_cell(self, row: int, col: int, text: str, color: str):
        it = QTableWidgetItem(text or "—")
        it.setForeground(QColor(color))
        it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self._table.setItem(row, col, it)


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT PANEL — confidence gauges + indicator values
# ─────────────────────────────────────────────────────────────────────────────

class _RightPanel(QWidget, _TM):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._gauges: Dict[str, _ConfGauge] = {}
        self._ind_table = None
        self._expl_lbl  = None
        self._thr_lbl   = None
        self._build()
        try:
            theme_manager.theme_changed.connect(self._restyle)
        except Exception:
            pass

    def _build(self):
        c  = _p(); ty = _ty(); sp = _sp()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_SM * 2)

        # ── Confidence section ─────────────────────────────────────────────
        conf_frame = QFrame()
        conf_frame.setObjectName("confSection")
        cf_lay = QVBoxLayout(conf_frame)
        cf_lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        cf_lay.setSpacing(8)

        cf_hdr_row = QHBoxLayout()
        cf_hdr = _label("CONFIDENCE", _tok("YELLOW_BRIGHT"), ty.SIZE_XS, bold=True)
        cf_hdr.setStyleSheet(
            f"color:{_tok('YELLOW_BRIGHT')}; font-size:{ty.SIZE_XS}pt; "
            f"font-weight:bold; letter-spacing:0.8px; background:transparent;"
        )
        cf_hdr_row.addWidget(cf_hdr)
        cf_hdr_row.addStretch()
        self._thr_lbl = QLabel("Threshold: 60%")
        self._thr_lbl.setStyleSheet(
            f"color:{c.TEXT_DISABLED}; font-size:{ty.SIZE_XS}pt; "
            f"font-family:'Consolas',monospace; background:transparent;"
        )
        cf_hdr_row.addWidget(self._thr_lbl)
        cf_lay.addLayout(cf_hdr_row)

        cf_lay.addWidget(_divider())

        for sig in SIGNAL_GROUPS:
            gauge = _ConfGauge(sig)
            self._gauges[sig] = gauge
            cf_lay.addWidget(gauge)

        cf_lay.addWidget(_divider())

        self._expl_lbl = QLabel("No evaluation yet.")
        self._expl_lbl.setWordWrap(True)
        self._expl_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._expl_lbl.setMaximumWidth(460)
        self._expl_lbl.setStyleSheet(
            f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt; "
            f"line-height:150%; background:transparent; padding-top:4px;"
        )
        cf_lay.addWidget(self._expl_lbl)

        lay.addWidget(conf_frame)

        # ── Indicator values ───────────────────────────────────────────────
        self._ind_table = _IndicatorTable()
        self._ind_table.setMinimumHeight(120)
        lay.addWidget(self._ind_table, 1)

        self._restyle()

    def _restyle(self, _=None):
        c = _p(); sp = _sp()
        self.setStyleSheet(f"""
            QFrame#confSection {{
                background: {c.BG_PANEL};
                border: 1px solid {c.BORDER};
                border-left: 3px solid {_tok("YELLOW_BRIGHT")};
                border-radius: 4px;
            }}
        """)

    def update(self, conf_dict: Dict, threshold: float, explanation: str,
               indicator_values: Dict):
        try:
            if self._thr_lbl:
                self._thr_lbl.setText(f"Threshold: {int(threshold * 100)}%")
            for sig, gauge in self._gauges.items():
                gauge.set_confidence(conf_dict.get(sig, 0.0), threshold)
            if self._expl_lbl:
                self._expl_lbl.setText(explanation or "—")
            if self._ind_table:
                self._ind_table.update_values(indicator_values)
        except Exception as e:
            logger.error(f"[_RightPanel.update] {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# GROUP CARD  — one signal group with its rules table
# ─────────────────────────────────────────────────────────────────────────────

class _GroupCard(QFrame, _TM):
    """
    Card for one signal group.
    Header:  [● SIGNAL NAME]  [AND/OR]  [confidence bar]  [FIRED badge]
    Body:    Rule table with columns:
             Rule Name | LHS Indicator | Sub-col | LHS Value | Op | RHS | Result
    """

    _RULE_COLS = ["#", "Expression", "LHS Ind.", "Sub-col", "LHS Value", "Op", "RHS", "Result"]

    def __init__(self, sig: str, parent=None):
        super().__init__(parent)
        self.signal    = sig
        self._logic    = "AND"
        self._conf_bar = None
        self._fired_lbl = None
        self._logic_lbl = None
        self._table    = None
        self._empty_lbl = None
        self._setup()
        self._restyle()
        try:
            theme_manager.theme_changed.connect(self._restyle)
        except Exception:
            pass

    def _setup(self):
        sp   = self._sp; ty = self._ty
        meta = _SIG_META.get(self.signal, _SIG_META["WAIT"])
        col  = _sig_color(self.signal)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        hdr_w = QWidget()
        hdr_w.setObjectName("cardHdr")
        hdr   = QHBoxLayout(hdr_w)
        hdr.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM)
        hdr.setSpacing(10)

        # Dot + name
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color:{col}; font-size:{ty.SIZE_XS}pt; background:transparent;"
        )
        hdr.addWidget(dot)

        name_lbl = QLabel(f"{meta['icon']}  {meta['label']}")
        name_lbl.setStyleSheet(f"""
            color: {col};
            font-size: {ty.SIZE_MD}pt;
            font-weight: bold;
            letter-spacing: 0.6px;
            font-family: 'Consolas', monospace;
            background: transparent;
        """)
        hdr.addWidget(name_lbl)
        hdr.addStretch()

        # Logic badge
        self._logic_lbl = QLabel("AND")
        self._logic_lbl.setFixedWidth(40)
        self._logic_lbl.setAlignment(Qt.AlignCenter)
        hdr.addWidget(self._logic_lbl)

        # Confidence bar (inline)
        bar_w = QWidget()
        bar_lay = QHBoxLayout(bar_w)
        bar_lay.setContentsMargins(0, 0, 0, 0)
        bar_lay.setSpacing(4)
        self._conf_bar = QProgressBar()
        self._conf_bar.setRange(0, 100)
        self._conf_bar.setTextVisible(False)
        self._conf_bar.setFixedHeight(6)
        self._conf_bar.setMinimumWidth(120)
        bar_lay.addWidget(self._conf_bar)
        self._conf_pct = QLabel("0%")
        self._conf_pct.setFixedWidth(36)
        self._conf_pct.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        bar_lay.addWidget(self._conf_pct)
        hdr.addWidget(bar_w)

        # Fired badge
        self._fired_lbl = QLabel("NOT FIRED")
        self._fired_lbl.setFixedWidth(86)
        self._fired_lbl.setAlignment(Qt.AlignCenter)
        hdr.addWidget(self._fired_lbl)

        root.addWidget(hdr_w)

        # ── Rule table ────────────────────────────────────────────────────
        self._table = QTableWidget(0, len(self._RULE_COLS))
        self._table.setHorizontalHeaderLabels(self._RULE_COLS)
        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.Fixed);         hv.resizeSection(0, 30)    # #
        hv.setSectionResizeMode(1, QHeaderView.Interactive);   hv.resizeSection(1, 180)   # Expression
        hv.setSectionResizeMode(2, QHeaderView.Fixed);         hv.resizeSection(2, 70)    # LHS Ind.
        hv.setSectionResizeMode(3, QHeaderView.Fixed);         hv.resizeSection(3, 70)    # Sub-col
        hv.setSectionResizeMode(4, QHeaderView.Fixed);         hv.resizeSection(4, 80)    # LHS Value
        hv.setSectionResizeMode(5, QHeaderView.Fixed);         hv.resizeSection(5, 36)    # Op
        hv.setSectionResizeMode(6, QHeaderView.Fixed);         hv.resizeSection(6, 80)    # RHS
        hv.setSectionResizeMode(7, QHeaderView.Stretch)                                    # Result
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._table.setMinimumHeight(36)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self._table)

        self._empty_lbl = QLabel("  No rules configured for this signal group.")
        self._empty_lbl.hide()
        root.addWidget(self._empty_lbl)

    def _restyle(self, _=None):
        c = _p(); sp = _sp(); ty = _ty()
        col = _sig_color(self.signal)

        self.setStyleSheet(f"""
            QFrame {{
                background: {c.BG_MAIN};
                border: 1px solid {c.BORDER};
                border-left: 3px solid {col};
                border-radius: 4px;
            }}
            QWidget#cardHdr {{
                background: {c.BG_PANEL};
                border-bottom: 1px solid {c.BORDER};
                border-radius: 0;
            }}
        """)
        if self._logic_lbl:
            self._logic_lbl.setStyleSheet(f"""
                color: {c.TEXT_DIM};
                font-size: {ty.SIZE_XS}pt;
                font-weight: bold;
                font-family: 'Consolas', monospace;
                background: {c.BG_INPUT};
                border: 1px solid {c.BORDER};
                border-radius: 3px;
                padding: 1px 4px;
            """)
        if self._empty_lbl:
            self._empty_lbl.setStyleSheet(
                f"color:{c.TEXT_DISABLED}; font-size:{ty.SIZE_XS}pt; "
                f"padding:{sp.PAD_MD}px;"
            )
        if self._table:
            self._table.setStyleSheet(f"""
                QTableWidget {{
                    background: {c.BG_MAIN};
                    alternate-background-color: {c.BG_ROW_B};
                    color: {c.TEXT_MAIN};
                    border: none;
                    border-top: none;
                    gridline-color: {c.BORDER};
                    font-size: {ty.SIZE_SM}pt;
                    font-family: 'Consolas', monospace;
                    selection-background-color: {c.BG_SELECTED};
                }}
                QHeaderView::section {{
                    background: {c.BG_PANEL};
                    color: {c.TEXT_DIM};
                    border: none;
                    border-bottom: 1px solid {c.BORDER};
                    border-right: 1px solid {c.BORDER};
                    padding: 3px 6px;
                    font-size: {ty.SIZE_XS}pt;
                    font-weight: bold;
                    letter-spacing: 0.4px;
                }}
                QTableCornerButton::section {{ background: {c.BG_PANEL}; border: none; }}
                {_scrollbar_ss()}
            """)
            row_h = 28
            self._table.verticalHeader().setDefaultSectionSize(row_h)

    def _apply_conf_bar(self, col: str):
        c = _p()
        if self._conf_bar:
            self._conf_bar.setStyleSheet(f"""
                QProgressBar {{ border:none; border-radius:3px; background:{c.BG_HOVER}; }}
                QProgressBar::chunk {{
                    border-radius:3px;
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 {col}44, stop:1 {col});
                }}
            """)

    def update_data(self, rule_results: List[Dict], fired: bool, logic: str,
                    enabled: bool, confidence: float, threshold: float):
        try:
            c = _p(); ty = _ty()

            # ── Logic ──────────────────────────────────────────────────────
            if self._logic_lbl:
                self._logic_lbl.setText(logic.upper())

            # ── Confidence bar ─────────────────────────────────────────────
            pct = max(0, min(100, int(confidence * 100)))
            if self._conf_bar:
                self._conf_bar.setValue(pct)
            if confidence >= threshold:          ca = "GREEN_BRIGHT"
            elif confidence >= threshold * 0.6:  ca = "YELLOW_BRIGHT"
            else:                                ca = "RED_BRIGHT"
            col_conf = _tok(ca)
            self._apply_conf_bar(col_conf)
            if self._conf_pct:
                self._conf_pct.setText(f"{pct}%")
                self._conf_pct.setStyleSheet(
                    f"color:{col_conf}; font-size:{ty.SIZE_XS}pt; font-weight:bold; "
                    f"font-family:'Consolas',monospace; background:transparent;"
                )

            # ── Fired / disabled badge ─────────────────────────────────────
            if self._fired_lbl:
                if not enabled:
                    self._fired_lbl.setText("DISABLED")
                    self._fired_lbl.setStyleSheet(f"""
                        color:{c.TEXT_DISABLED}; background:{c.BG_HOVER};
                        border:1px solid {c.BORDER}; border-radius:3px;
                        font-size:{ty.SIZE_XS}pt; font-weight:bold;
                        font-family:'Consolas',monospace; padding:2px 4px;
                    """)
                elif fired:
                    fc = _tok("GREEN_BRIGHT")
                    self._fired_lbl.setText("✓  FIRED")
                    self._fired_lbl.setStyleSheet(f"""
                        color:{fc}; background:{fc}18;
                        border:1px solid {fc}66; border-radius:3px;
                        font-size:{ty.SIZE_XS}pt; font-weight:bold;
                        font-family:'Consolas',monospace; padding:2px 4px;
                    """)
                else:
                    self._fired_lbl.setText("NOT FIRED")
                    self._fired_lbl.setStyleSheet(f"""
                        color:{c.TEXT_DISABLED}; background:transparent;
                        border:1px solid {c.BORDER}; border-radius:3px;
                        font-size:{ty.SIZE_XS}pt; font-weight:bold;
                        font-family:'Consolas',monospace; padding:2px 4px;
                    """)

            # ── Rules ──────────────────────────────────────────────────────
            if not rule_results:
                if self._table: self._table.hide(); self._table.setRowCount(0)
                if self._empty_lbl: self._empty_lbl.show()
                self.setMinimumHeight(0)
                self.setMaximumHeight(16777215)  # restore from any prior setFixedHeight
                return

            if self._empty_lbl: self._empty_lbl.hide()
            if self._table: self._table.show()

            # Identify first blocker for AND logic
            first_blocker = -1
            if logic.upper() == "AND" and not fired:
                for idx, entry in enumerate(rule_results):
                    if not entry.get("result", True):
                        first_blocker = idx
                        break

            self._table.setRowCount(len(rule_results))

            for i, entry in enumerate(rule_results):
                try:
                    result     = entry.get("result", False)
                    error      = entry.get("error", "")
                    weight     = float(entry.get("weight", 1.0))
                    is_blocker = (i == first_blocker)

                    rule_str = entry.get("rule", "?")
                    lhs_raw  = entry.get("lhs_value")
                    rhs_raw  = entry.get("rhs_value")

                    # Parse op from rule string
                    op = "?"
                    for _op in [">=", "<=", "!=", "==", ">", "<"]:
                        if f" {_op} " in rule_str:
                            op = _op
                            break

                    # Parse indicator + sub_col from rule string
                    # rule_str format: "MACD[SIGNAL](shift=0) > MACD[HIST](shift=1)"
                    # or:              "RSI(14) > 30"
                    lhs_expr, rhs_expr = self._split_sides(rule_str, op)
                    lhs_ind,  lhs_sub  = self._parse_side_expr(lhs_expr)
                    rhs_ind,  rhs_sub  = self._parse_side_expr(rhs_expr)

                    # LHS value
                    if lhs_raw is not None:
                        lhs_val = _fmt_val(lhs_raw)
                    else:
                        lhs_val = "?"

                    # RHS: prefer parsed numeric, then rhs_raw
                    try:
                        float(rhs_expr)
                        rhs_display = rhs_expr.strip()   # it's a scalar constant
                    except (ValueError, TypeError):
                        rhs_display = _fmt_val(rhs_raw)  # it's an indicator value

                    # Result cell
                    if error:
                        result_txt = f"⚠ {error[:30]}"
                        result_col = _tok("YELLOW_BRIGHT")
                    elif result:
                        result_txt = f"✓  TRUE   w={weight:.1f}"
                        result_col = _tok("GREEN_BRIGHT")
                    else:
                        result_txt = f"✗  FALSE  w={weight:.1f}"
                        result_col = _tok("RED_BRIGHT")

                    cells = [
                        (str(i + 1),       c.TEXT_DISABLED),
                        (lhs_expr.strip(), _tok("YELLOW_BRIGHT") if is_blocker else c.TEXT_DIM),
                        (lhs_ind,          _tok("BLUE")),
                        (lhs_sub,          c.TEXT_DIM),
                        (lhs_val,          _tok("GREEN_BRIGHT") if result else _tok("RED_BRIGHT")),
                        (op,               _tok("YELLOW_BRIGHT")),
                        (rhs_display,      _tok("ORANGE")),
                        (result_txt,       result_col),
                    ]

                    for col_idx, (text, color) in enumerate(cells):
                        it = QTableWidgetItem(text or "—")
                        it.setForeground(QColor(color))
                        it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                        it.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                        if is_blocker:
                            it.setBackground(QColor(_tok("RED") + "18"))
                            fnt = it.font()
                            fnt.setBold(True)
                            it.setFont(fnt)
                        self._table.setItem(i, col_idx, it)

                except Exception as ex:
                    logger.warning(f"[_GroupCard.update_data] row {i}: {ex}")

            # Size the table to fit rows exactly without internal scrollbar
            row_h   = 28
            hdr_h   = self._table.horizontalHeader().height()
            total_h = hdr_h + row_h * len(rule_results) + 4
            self._table.setMinimumHeight(total_h)
            self._table.setMaximumHeight(total_h)
            self._table.verticalHeader().setDefaultSectionSize(row_h)

        except Exception as e:
            logger.error(f"[_GroupCard.update_data] {e}", exc_info=True)

    def _table_header_h(self) -> int:
        if self._table:
            return self._table.horizontalHeader().height()
        return 28

    @staticmethod
    def _split_sides(rule_str: str, op: str) -> Tuple[str, str]:
        if op and f" {op} " in rule_str:
            parts = rule_str.split(f" {op} ", 1)
            return parts[0], parts[1] if len(parts) > 1 else ""
        return rule_str, ""

    @staticmethod
    def _parse_side_expr(expr: str) -> Tuple[str, str]:
        """
        Parse indicator name and sub-col from a side expression string.
        Handles formats like:
            MACD[SIGNAL]      → ("MACD", "Signal")
            RSI               → ("RSI", "")
            30                → ("", "")  (scalar)
            supertrend.DIRECTION → ("SUPERTREND", "Direction")
        """
        _SUB_PRETTY = {
            "MACD": "Line", "SIGNAL": "Signal", "HIST": "Histogram",
            "K": "%K", "D": "%D",
            "ADX": "ADX", "PLUS_DI": "+DI", "MINUS_DI": "−DI",
            "AROON_UP": "↑", "AROON_DOWN": "↓",
            "TREND": "Trend", "DIRECTION": "Dir", "LONG": "Long", "SHORT": "Short",
            "UPPER": "Upper", "MIDDLE": "Mid", "LOWER": "Lower",
            "BANDWIDTH": "BW", "PERCENT": "%B",
            "ISA": "Tenkan", "ISB": "Kijun",
            "ITS": "Spn A", "IKS": "Spn B", "ICS": "Chikou",
        }
        try:
            expr = expr.strip()
            # Try to parse as a scalar
            float(expr)
            return "", ""
        except (ValueError, TypeError):
            pass

        # Pattern: NAME[SUBCOL] or NAME.SUBCOL or just NAME
        m = re.match(r"([A-Za-z0-9_]+)(?:\[([A-Z0-9_]+)\]|\.([A-Z0-9_]+))?", expr)
        if m:
            ind_raw = m.group(1).upper()
            sub_raw = (m.group(2) or m.group(3) or "").upper()
            sub_pretty = _SUB_PRETTY.get(sub_raw, sub_raw.title() if sub_raw else "")
            return ind_raw, sub_pretty
        return expr.upper(), ""

    def apply_theme(self, _=None):
        self._restyle()


# ─────────────────────────────────────────────────────────────────────────────
# RAW JSON PANEL
# ─────────────────────────────────────────────────────────────────────────────

class _RawJsonPanel(QWidget, _TM):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._edit = QTextEdit()
        self._edit.setReadOnly(True)
        lay.addWidget(self._edit)
        self._restyle()
        try:
            theme_manager.theme_changed.connect(self._restyle)
        except Exception:
            pass

    def _restyle(self, _=None):
        c = _p(); ty = _ty()
        self._edit.setStyleSheet(f"""
            QTextEdit {{
                background: {c.BG_MAIN};
                color: {_tok('GREEN_BRIGHT')};
                border: none;
                font-family: 'Consolas', monospace;
                font-size: {ty.SIZE_SM}pt;
                selection-background-color: {c.BG_SELECTED};
            }}
            {_scrollbar_ss()}
        """)

    def update_result(self, result: Dict):
        try:
            self._edit.setPlainText(
                json.dumps(result, indent=2, default=str) if result else "No data."
            )
        except Exception as e:
            self._edit.setPlainText(f"Error: {e}")

    def apply_theme(self, _=None):
        self._restyle()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN POPUP
# ─────────────────────────────────────────────────────────────────────────────

class DynamicSignalDebugPopup(QDialog, _TM):
    """
    Signal Intelligence Console.
    Two-column layout: scrollable group cards (left) + sticky right panel.
    """

    def __init__(self, trading_app, parent=None):
        self._safe_defaults()
        try:
            super().__init__(parent, Qt.Window)
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.trading_app = trading_app
            self.resize(1400, 920)
            self.setMinimumSize(1100, 700)
            self._drag_pos = None

            try:
                theme_manager.theme_changed.connect(self.apply_theme)
                theme_manager.density_changed.connect(self.apply_theme)
            except Exception:
                pass

            self._build_ui()
            self.apply_theme()

            self._timer = QTimer(self)
            self._timer.timeout.connect(self._maybe_refresh)
            self._timer.start(1000)

            logger.info("DynamicSignalDebugPopup initialized")
        except Exception as e:
            logger.critical(f"[DynamicSignalDebugPopup.__init__] {e}", exc_info=True)

    def _safe_defaults(self):
        self.trading_app            = None
        self._last_signal_value     = ""
        self._auto_refresh          = True
        self._current_strategy_slug = None
        self._timer                 = None
        self._signal_badge          = None
        self._fired_pills: Dict     = {}
        self._group_cards: Dict     = {}
        self._right_panel           = None
        self._json_panel            = None
        self._tabs                  = None
        self._status_lbl            = None
        self._auto_chk              = None
        self._outer                 = None
        self._drag_pos              = None
        # stat labels
        self._lbl_conflict     = None
        self._lbl_available    = None
        self._lbl_symbol       = None
        self._lbl_last_close   = None
        self._lbl_bars         = None
        self._lbl_timestamp    = None
        self._lbl_strategy     = None

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        self._outer = QFrame()
        self._outer.setObjectName("outerFrame")
        ol = QVBoxLayout(self._outer)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(0)

        ol.addWidget(self._build_title_bar())
        ol.addWidget(self._build_header())
        ol.addWidget(self._build_body(), 1)
        ol.addWidget(self._build_footer())

        root.addWidget(self._outer)
        self._style_outer()

    # ── Title bar ─────────────────────────────────────────────────────────────

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(44)
        bar.mousePressEvent   = self._drag_start
        bar.mouseMoveEvent    = self._drag_move
        bar.mouseReleaseEvent = lambda e: setattr(self, "_drag_pos", None)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(10)

        logo = QLabel("SIC")
        logo.setFixedSize(32, 26)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(f"""
            color: {_p().TEXT_INVERSE};
            background: {_tok('YELLOW_BRIGHT')};
            border-radius: 4px;
            font-size: {_ty().SIZE_XS}pt;
            font-weight: 900;
            font-family: 'Consolas', monospace;
            letter-spacing: 0.5px;
        """)
        lay.addWidget(logo)

        title = QLabel("SIGNAL INTELLIGENCE CONSOLE")
        title.setStyleSheet(f"""
            color: {_p().TEXT_MAIN};
            font-size: {_ty().SIZE_SM}pt;
            font-weight: bold;
            letter-spacing: 2px;
            background: transparent;
        """)
        lay.addWidget(title)
        lay.addStretch()

        for icon, tip, slot in [
            ("↺", "Refresh", self.refresh),
            ("✕", "Close",   self.close),
        ]:
            btn = QPushButton(icon)
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(tip)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {_p().TEXT_DIM};
                    border: none; border-radius: 14px;
                    font-size: {_ty().SIZE_BODY}pt; font-weight: bold;
                }}
                QPushButton:hover {{ background:{_p().BG_HOVER}; color:{_p().TEXT_MAIN}; }}
            """)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

        return bar

    # ── Header — signal badge + stats + fired pills ───────────────────────────

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setObjectName("mainHdr")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(20)

        # Signal badge
        badge_col = QVBoxLayout()
        badge_col.setSpacing(4)
        ey = QLabel("RESOLVED SIGNAL")
        ey.setStyleSheet(f"""
            color: {_tok('YELLOW_BRIGHT')};
            font-size: {_ty().SIZE_XS}pt;
            font-weight: bold; letter-spacing: 1px;
            background: transparent;
        """)
        badge_col.addWidget(ey, 0, Qt.AlignCenter)
        self._signal_badge = _SignalBadge()
        badge_col.addWidget(self._signal_badge)
        lay.addLayout(badge_col)

        lay.addWidget(_divider(vertical=True))

        # Stats grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)

        def _stat(row: int, key: str, attr: str) -> QLabel:
            kl = QLabel(key)
            kl.setStyleSheet(
                f"color:{_p().TEXT_DISABLED}; font-size:{_ty().SIZE_XS}pt; "
                f"font-weight:bold; letter-spacing:0.4px; background:transparent;"
            )
            vl = QLabel("—")
            vl.setStyleSheet(
                f"color:{_p().TEXT_MAIN}; font-size:{_ty().SIZE_SM}pt; "
                f"font-weight:bold; font-family:'Consolas',monospace; background:transparent;"
            )
            grid.addWidget(kl, row, 0)
            grid.addWidget(vl, row, 1)
            setattr(self, attr, vl)
            return vl

        _stat(0, "CONFLICT",    "_lbl_conflict")
        _stat(1, "SYMBOL",      "_lbl_symbol")
        _stat(2, "LAST CLOSE",  "_lbl_last_close")
        _stat(3, "BARS",        "_lbl_bars")
        _stat(4, "STRATEGY",    "_lbl_strategy")
        _stat(5, "UPDATED",     "_lbl_timestamp")
        lay.addLayout(grid)

        lay.addWidget(_divider(vertical=True))

        # Fired pills
        pills_col = QVBoxLayout()
        pills_col.setSpacing(6)
        pe = QLabel("SIGNAL GROUPS FIRED")
        pe.setStyleSheet(f"""
            color: {_tok('YELLOW_BRIGHT')};
            font-size: {_ty().SIZE_XS}pt;
            font-weight: bold; letter-spacing: 1px;
            background: transparent;
        """)
        pills_col.addWidget(pe, 0, Qt.AlignCenter)

        pills_w = QWidget()
        pills_lay = QHBoxLayout(pills_w)
        pills_lay.setContentsMargins(0, 0, 0, 0)
        pills_lay.setSpacing(6)
        self._fired_pills = {}
        for sig in SIGNAL_GROUPS:
            pill = _FiredPill(sig)
            pills_lay.addWidget(pill)
            self._fired_pills[sig] = pill
        pills_col.addWidget(pills_w)
        lay.addLayout(pills_col)

        lay.addStretch()
        return hdr

    # ── Body — two-column splitter ─────────────────────────────────────────────

    def _build_body(self) -> QWidget:
        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        # ── Tab widget (left side contains the tabs) ───────────────────────
        tabs = QTabWidget()
        tabs.setObjectName("mainTabs")
        self._tabs = tabs

        # Tab 1: Signal Groups
        groups_scroll = QScrollArea()
        groups_scroll.setWidgetResizable(True)
        groups_scroll.setFrameShape(QFrame.NoFrame)
        groups_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        groups_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        groups_scroll.setStyleSheet(f"QScrollArea {{ background:{_p().BG_MAIN}; border:none; }} {_scrollbar_ss()}")

        groups_w = QWidget()
        groups_w.setStyleSheet(f"background:{_p().BG_MAIN};")
        groups_v = QVBoxLayout(groups_w)
        groups_v.setContentsMargins(10, 10, 10, 10)
        groups_v.setSpacing(10)

        self._group_cards = {}
        for sig in SIGNAL_GROUPS:
            card = _GroupCard(sig)
            self._group_cards[sig] = card
            groups_v.addWidget(card)
        groups_v.addStretch()
        groups_scroll.setWidget(groups_w)
        tabs.addTab(groups_scroll, "📊  Signal Groups")

        # Tab 2: Raw JSON
        self._json_panel = _RawJsonPanel()
        tabs.addTab(self._json_panel, "{ }  Raw JSON")

        body_lay.addWidget(tabs, 62)

        # Thin separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"background:{_p().BORDER}; max-width:1px;")
        body_lay.addWidget(sep)

        # ── Right panel ────────────────────────────────────────────────────
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setStyleSheet(f"QScrollArea {{ background:{_p().BG_MAIN}; border:none; }} {_scrollbar_ss()}")
        right_scroll.setMinimumWidth(340)
        self._right_panel = _RightPanel()
        right_scroll.setWidget(self._right_panel)
        body_lay.addWidget(right_scroll, 38)

        self._apply_tab_style()
        return body

    def _apply_tab_style(self):
        if not self._tabs:
            return
        c = _p(); ty = _ty(); sp = _sp()
        self._tabs.setStyleSheet(f"""
            QTabWidget#mainTabs::pane {{
                border: none;
                border-top: 1px solid {c.BORDER};
                background: {c.BG_MAIN};
            }}
            QTabBar::tab {{
                background: {c.BG_PANEL};
                color: {c.TEXT_DIM};
                border: none;
                border-right: 1px solid {c.BORDER};
                padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                min-width: 130px;
                font-size: {ty.SIZE_SM}pt;
                font-weight: bold;
                letter-spacing: 0.3px;
            }}
            QTabBar::tab:selected {{
                color: {_tok('YELLOW_BRIGHT')};
                border-bottom: 2px solid {_tok('YELLOW_BRIGHT')};
                background: {c.BG_MAIN};
            }}
            QTabBar::tab:hover:!selected {{
                color: {c.TEXT_MAIN};
                background: {c.BG_HOVER};
            }}
        """)

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("footer")
        footer.setFixedHeight(48)
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        c = _p(); ty = _ty(); sp = _sp()

        self._auto_chk = QCheckBox("Auto-refresh (1 s)")
        self._auto_chk.setChecked(True)
        self._auto_chk.toggled.connect(self._on_auto_toggle)
        self._auto_chk.setStyleSheet(f"""
            QCheckBox {{
                color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt; spacing: {sp.GAP_SM}px;
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {c.BORDER_STRONG};
                border-radius: 3px; background: {c.BG_INPUT};
            }}
            QCheckBox::indicator:checked {{
                background: {_tok('YELLOW_BRIGHT')};
                border-color: {_tok('YELLOW_BRIGHT')};
            }}
        """)
        lay.addWidget(self._auto_chk)

        self._status_lbl = QLabel("Waiting…")
        self._status_lbl.setStyleSheet(
            f"color:{c.TEXT_DISABLED}; font-size:{ty.SIZE_XS}pt; "
            f"font-family:'Consolas',monospace; background:transparent;"
        )
        lay.addWidget(self._status_lbl)
        lay.addStretch()

        for label, style_cls, slot in [
            ("↺  Refresh", "secondary", self.refresh),
            ("✕  Close",   "danger",    self.close),
        ]:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(32)
            if style_cls == "danger":
                ss = f"""
                    QPushButton {{
                        background:{_tok('RED_BRIGHT')}22; color:{_tok('RED_BRIGHT')};
                        border:1px solid {_tok('RED_BRIGHT')}66; border-radius:{sp.RADIUS_MD}px;
                        padding:0 14px; font-size:{ty.SIZE_SM}pt; font-weight:bold;
                    }}
                    QPushButton:hover {{ background:{_tok('RED_BRIGHT')}; color:white; }}
                """
            else:
                ss = f"""
                    QPushButton {{
                        background:transparent; color:{c.TEXT_DIM};
                        border:1px solid {c.BORDER}; border-radius:{sp.RADIUS_MD}px;
                        padding:0 14px; font-size:{ty.SIZE_SM}pt; font-weight:bold;
                    }}
                    QPushButton:hover {{
                        border-color:{_tok('YELLOW_BRIGHT')}; color:{_tok('YELLOW_BRIGHT')};
                    }}
                """
            btn.setStyleSheet(ss)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

        return footer

    # ── Styling ───────────────────────────────────────────────────────────────

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
            QWidget#mainHdr {{
                background: {c.BG_PANEL};
                border-bottom: 1px solid {c.BORDER};
            }}
            QWidget#footer {{
                background: {c.BG_PANEL};
                border-top: 1px solid {c.BORDER};
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
        """)

    def apply_theme(self, _=None):
        try:
            self._style_outer()
            self._apply_tab_style()
            if self._signal_badge:
                self._signal_badge.apply_theme()
            for pill in self._fired_pills.values():
                pill.apply_theme()
            for card in self._group_cards.values():
                card.apply_theme()
            if self._json_panel:
                self._json_panel.apply_theme()
        except Exception as e:
            logger.error(f"[apply_theme] {e}", exc_info=True)

    # ── Dragging ──────────────────────────────────────────────────────────────

    def _drag_start(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def _drag_move(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(e.globalPos() - self._drag_pos)

    # ── Refresh logic ─────────────────────────────────────────────────────────

    @pyqtSlot()
    def _maybe_refresh(self):
        try:
            if self._auto_refresh and self.isVisible():
                self.refresh()
        except Exception as e:
            logger.error(f"[_maybe_refresh] {e}", exc_info=True)

    def _on_auto_toggle(self, checked: bool):
        self._auto_refresh = checked

    @pyqtSlot()
    def refresh(self):
        try:
            if self.trading_app is None:
                self._set_status("⚠  trading_app is None")
                return

            state = state_manager.get_state()
            if state is None:
                self._set_status("⚠  state_manager returned None")
                return

            # ── BUG FIX: Read from state.option_signal_result first.
            # This is updated every tick (via _evaluate_tick_close_gate and
            # _update_state_with_signal_result), so it always holds the latest
            # evaluation result.  derivative_trend["option_signal"] is only
            # written on candle close (Tier 1 fetch) and goes stale between bars.
            option_signal = safe_getattr(state, "option_signal_result", None)

            # Fallback to derivative_trend for backward compatibility
            if option_signal is None:
                trend_data    = safe_getattr(state, "derivative_trend", None) or {}
                option_signal = trend_data.get("option_signal")

            # Also pull trend_data for symbol/close metadata (always from derivative_trend)
            trend_data = safe_getattr(state, "derivative_trend", None) or {}

            if option_signal is None:
                self._set_status("⚠  No signal data in state yet — waiting for first candle.")
                return

            if not option_signal.get("available", False):
                self._set_status("ℹ  DynamicSignalEngine not available / no rules configured.")
                return

            ty = self._ty; c = self._c

            # ── Signal badge ──────────────────────────────────────────────
            signal_val = option_signal.get("signal_value", "WAIT")
            if self._signal_badge:
                self._signal_badge.update_signal(signal_val)

            # ── Stat labels ───────────────────────────────────────────────
            conflict = option_signal.get("conflict", False)
            if self._lbl_conflict:
                col = _tok("RED_BRIGHT") if conflict else _tok("GREEN_BRIGHT")
                self._lbl_conflict.setText("⚠ YES" if conflict else "No")
                self._lbl_conflict.setStyleSheet(
                    f"color:{col}; font-size:{ty.SIZE_SM}pt; font-weight:bold; "
                    f"font-family:'Consolas',monospace; background:transparent;"
                )

            symbol     = trend_data.get("name", "—")
            close_list = trend_data.get("close") or []
            last_close = close_list[-1] if close_list else "—"

            for lbl, val in [
                (self._lbl_symbol,     str(symbol)),
                (self._lbl_last_close, str(last_close)),
                (self._lbl_bars,       str(len(close_list))),
                (self._lbl_timestamp,  fmt_display(ist_now(), time_only=True)),
            ]:
                if lbl:
                    lbl.setText(val)

            # Strategy
            if self._lbl_strategy:
                try:
                    eng  = safe_getattr(
                        safe_getattr(self.trading_app, "detector", None),
                        "signal_engine", None
                    )
                    slug = safe_getattr(eng, "strategy_slug", None) if eng else None
                    self._lbl_strategy.setText(slug or "Default")
                    self._current_strategy_slug = slug
                except Exception:
                    self._lbl_strategy.setText("—")

            # ── Fired pills ────────────────────────────────────────────────
            fired_map = option_signal.get("fired", {})
            # Normalise: fired_map may have string keys ("BUY_CALL") while
            # self._fired_pills uses OptionSignal enum keys.  Build a str-keyed
            # copy so all lookups work regardless of key type.
            fired_str = {
                (k.value if hasattr(k, "value") else str(k)): v
                for k, v in fired_map.items()
            }
            for sig, pill in self._fired_pills.items():
                sig_str = sig.value if hasattr(sig, "value") else str(sig)
                pill.set_fired(bool(fired_str.get(sig_str, False)))

            # ── Group cards (left) ─────────────────────────────────────────
            rule_results = option_signal.get("rule_results", {})
            conf_dict    = option_signal.get("confidence", {})
            threshold    = option_signal.get("threshold", 0.6)
            explanation  = option_signal.get("explanation", "")

            # Normalise conf_dict and rule_results to string keys
            conf_str = {
                (k.value if hasattr(k, "value") else str(k)): v
                for k, v in conf_dict.items()
            }
            rules_str = {
                (k.value if hasattr(k, "value") else str(k)): v
                for k, v in rule_results.items()
            }

            for sig in SIGNAL_GROUPS:
                if sig not in self._group_cards:
                    continue
                sig_str = sig.value if hasattr(sig, "value") else str(sig)
                card    = self._group_cards[sig]
                rules   = rules_str.get(sig_str, [])
                is_fired = fired_str.get(sig_str, False)
                logic   = "AND"
                enabled = True
                try:
                    eng = safe_getattr(
                        safe_getattr(self.trading_app, "detector", None),
                        "signal_engine", None
                    )
                    if eng:
                        logic   = eng.get_logic(sig)
                        enabled = eng.is_enabled(sig)
                except Exception:
                    pass
                card.update_data(rules, is_fired, logic, enabled,
                                 conf_str.get(sig_str, 0.0), threshold)

            # ── Right panel ────────────────────────────────────────────────
            ind_values = option_signal.get("indicator_values", {})
            if self._right_panel:
                self._right_panel.update(conf_str, threshold, explanation, ind_values)

            # ── Raw JSON ───────────────────────────────────────────────────
            if self._json_panel:
                self._json_panel.update_result(option_signal)

            self._set_status(
                f"✓  {fmt_display(ist_now(), time_only=True)}",
                color=_tok("GREEN_BRIGHT")
            )

        except Exception as e:
            logger.error(f"[refresh] {e}", exc_info=True)
            self._set_status(f"⚠  {e}", color=_tok("RED_BRIGHT"))

    def _set_status(self, msg: str, color: str = None):
        if not self._status_lbl:
            return
        col = color or _p().TEXT_DISABLED
        self._status_lbl.setStyleSheet(
            f"color:{col}; font-size:{_ty().SIZE_XS}pt; "
            f"font-family:'Consolas',monospace; background:transparent;"
        )
        self._status_lbl.setText(msg)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            if self._timer:
                self._timer.stop()
                self._timer = None
            super().closeEvent(event)
        except Exception:
            super().closeEvent(event)

    def cleanup(self):
        try:
            if self._timer and self._timer.isActive():
                self._timer.stop()
            self._timer      = None
            self.trading_app = None
            logger.info("[DynamicSignalDebugPopup] Cleanup completed")
        except Exception as e:
            logger.error(f"[cleanup] {e}", exc_info=True)