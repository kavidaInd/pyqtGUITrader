"""
dynamic_signal_debug_popup.py
==============================
REDESIGN — "Signal Ops Console" — matches the Strategy Picker's terminal aesthetic.

Design direction:
  · Dark bg with monospace typography throughout
  · Amber top-border accent, hairline dividers — no rounded card stacks
  · Status header: large signal readout flanked by a compact stat grid and
    a live FIRED grid (5 signal pills in a tight row)
  · Group panels: coloured left-border accent + compact gradient confidence bar
  · Indicator table: zebra-striped, monospace values
  · Confidence tab: 2-col grid matching the picker's layout
  · Raw JSON: pure monospace terminal

All business logic, state_manager access, and theming hooks preserved intact.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView,
    QGridLayout, QTabWidget, QTextEdit, QProgressBar,
)

from Utils.safe_getattr import safe_hasattr, safe_getattr
from data.trade_state_manager import state_manager
from strategy.dynamic_signal_engine import SIGNAL_COLORS, SIGNAL_LABELS, SIGNAL_GROUPS
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Palette helpers
# ─────────────────────────────────────────────────────────────────────────────

def _p():  return theme_manager.palette
def _ty(): return theme_manager.typography
def _sp(): return theme_manager.spacing
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
# Signal meta (mirrors dynamic_signal_engine values)
# ─────────────────────────────────────────────────────────────────────────────

_SIG_META = {
    "BUY_CALL":  dict(label="BUY CALL",  short="B↑", attr="GREEN_BRIGHT"),
    "BUY_PUT":   dict(label="BUY PUT",   short="B↓", attr="BLUE"),
    "EXIT_CALL": dict(label="EXIT CALL", short="X↑", attr="RED_BRIGHT"),
    "EXIT_PUT":  dict(label="EXIT PUT",  short="X↓", attr="ORANGE"),
    "HOLD":      dict(label="HOLD",      short="HLD", attr="YELLOW_BRIGHT"),
    "WAIT":      dict(label="WAIT",      short="---", attr="TEXT_DISABLED"),
}

def _sig_color(sig: str) -> str:
    attr = _SIG_META.get(sig, _SIG_META["WAIT"])["attr"]
    return _tok(attr)

def _get_signal_colors():
    try:
        return {s: _sig_color(s) for s in list(_SIG_META.keys())}
    except Exception:
        return SIGNAL_COLORS


# ─────────────────────────────────────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _table_style() -> str:
    c = _p(); sp = _sp(); ty = _ty()
    return f"""
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
            padding: {sp.PAD_XS}px {sp.PAD_SM}px;
            font-size: {ty.SIZE_XS}pt;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
        QTableCornerButton::section {{
            background: {c.BG_PANEL};
            border: none;
        }}
        QScrollBar:vertical {{
            background: {c.BG_PANEL};
            width: 5px; border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{
            background: {c.BORDER_STRONG};
            border-radius: 3px; min-height: 16px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """

def _section_hdr(text: str) -> QWidget:
    """Slim labelled section divider used inside panels."""
    w = QWidget()
    w.setObjectName("sectionHdr")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 6, 0, 4)
    lay.setSpacing(6)
    dot = QFrame()
    dot.setFixedSize(4, 4)
    dot.setStyleSheet(f"background:{_tok('YELLOW_BRIGHT')}; border-radius:2px;")
    lay.addWidget(dot)
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f"""
        color: {_p().TEXT_DISABLED};
        font-size: {_ty().SIZE_XS}pt;
        font-weight: bold;
        letter-spacing: 0.8px;
    """)
    lay.addWidget(lbl)
    lay.addStretch()
    return w


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL BADGE  (large readout in the header)
# ─────────────────────────────────────────────────────────────────────────────

class _SignalBadge(QLabel, _TM):
    """Full-width pill showing the current resolved signal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last = "WAIT"
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(160)
        self.setFixedHeight(52)
        try:
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)
        except Exception:
            pass
        self._paint("WAIT")

    def _paint(self, sig: str):
        meta  = _SIG_META.get(sig, _SIG_META["WAIT"])
        color = _tok(meta["attr"])
        label = meta["label"]
        ty    = self._ty
        self.setText(label)
        self.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background: {color}1A;
                border: 2px solid {color};
                border-radius: 6px;
                font-size: {ty.SIZE_XL}pt;
                font-weight: bold;
                letter-spacing: 1.2px;
                font-family: 'Consolas', monospace;
            }}
        """)
        self._last = sig

    def update_signal(self, sig: str):
        if sig != self._last:
            self._paint(sig)

    def apply_theme(self, _=None):
        self._paint(self._last)


# ─────────────────────────────────────────────────────────────────────────────
# FIRED PILL  (compact signal-group indicator in the status header)
# ─────────────────────────────────────────────────────────────────────────────

class _FiredPill(QLabel, _TM):
    """Compact 60×44 fired/not-fired indicator for one signal group."""

    def __init__(self, sig: str, parent=None):
        super().__init__(parent)
        self._sig   = sig
        self._fired = False
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(64, 44)
        meta = _SIG_META.get(sig, _SIG_META["WAIT"])
        self._attr = meta["attr"]
        lines = sig.replace("_", "\n")
        self.setText(lines)
        self._paint(False)

    def _paint(self, fired: bool):
        self._fired = fired
        c     = self._c
        ty    = self._ty
        color = _tok(self._attr) if fired else c.BORDER
        bg    = f"{_tok(self._attr)}22" if fired else "transparent"
        fw    = "bold" if fired else "normal"
        self.setStyleSheet(f"""
            QLabel {{
                color: {_tok(self._attr) if fired else c.TEXT_DISABLED};
                background: {bg};
                border: {'2' if fired else '1'}px solid {color};
                border-radius: 4px;
                font-size: {ty.SIZE_XS}pt;
                font-weight: {fw};
                font-family: 'Consolas', monospace;
            }}
        """)

    def set_fired(self, fired: bool):
        if fired != self._fired:
            self._paint(fired)

    def apply_theme(self, _=None):
        self._paint(self._fired)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIDENCE BAR  (gradient fill, threshold annotation)
# ─────────────────────────────────────────────────────────────────────────────

class _ConfidenceBar(QWidget, _TM):
    """Compact horizontal bar: ████░░  73%  /60%"""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setMinimumWidth(100)
        lay.addWidget(self._bar, 1)

        self._val_lbl = QLabel("0%")
        self._val_lbl.setFixedWidth(32)
        self._val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self._val_lbl)

        self._thr_lbl = QLabel()
        self._thr_lbl.setFixedWidth(32)
        self._thr_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lay.addWidget(self._thr_lbl)

        self.apply_theme()
        try:
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)
        except Exception:
            pass

    def apply_theme(self, _=None):
        c = _p()
        self._bar.setStyleSheet(f"""
            QProgressBar {{ border:none; border-radius:3px; background:{c.BG_HOVER}; }}
            QProgressBar::chunk {{ border-radius:3px; background:{c.BLUE}; }}
        """)
        self._val_lbl.setStyleSheet(
            f"color:{c.BLUE}; font-size:{_ty().SIZE_XS}pt; font-weight:bold; "
            f"font-family:'Consolas',monospace;"
        )
        self._thr_lbl.setStyleSheet(
            f"color:{c.TEXT_DISABLED}; font-size:{_ty().SIZE_XS}pt; "
            f"font-family:'Consolas',monospace;"
        )

    def set_confidence(self, confidence: float, threshold: float = 0.6):
        try:
            c   = _p()
            pct = int(confidence * 100)
            self._bar.setValue(pct)
            self._val_lbl.setText(f"{pct}%")
            self._thr_lbl.setText(f"/{int(threshold*100)}%")

            if confidence >= threshold:
                col_attr = "GREEN_BRIGHT"
            elif confidence >= threshold * 0.65:
                col_attr = "YELLOW_BRIGHT"
            else:
                col_attr = "RED_BRIGHT"
            col = _tok(col_attr)

            self._bar.setStyleSheet(f"""
                QProgressBar {{
                    border: none; border-radius: 3px;
                    background: {c.BG_HOVER};
                }}
                QProgressBar::chunk {{
                    border-radius: 3px;
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 {col}55, stop:1 {col});
                }}
            """)
            self._val_lbl.setStyleSheet(
                f"color:{col}; font-size:{_ty().SIZE_XS}pt; font-weight:bold; "
                f"font-family:'Consolas',monospace;"
            )
        except Exception as e:
            logger.error(f"[_ConfidenceBar.set_confidence] {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# RULE ROW  (populates one row of the group table)
# ─────────────────────────────────────────────────────────────────────────────

class _RuleRow:
    def __init__(self, table: QTableWidget, row: int):
        self.table = table
        self.row   = row

    def set(self, rule_str: str, lhs_val: str, op: str, rhs_val: str,
            result: bool, weight: float = 1.0, error: str = "",
            is_blocker: bool = False):
        try:
            c  = _p()
            ty = _ty()

            display_rule = f"⚠ {rule_str}  [BLOCKER]" if is_blocker else rule_str
            if weight != 1.0:
                display_rule += f"  (w={weight:.1f})"

            result_str = (f"✓ TRUE  w={weight:.1f}" if result
                          else f"✗ FALSE  w={weight:.1f}")
            if error:
                result_str = f"⚠ {error[:40]}"

            items = [
                (display_rule,  _tok("YELLOW_BRIGHT") if is_blocker else c.TEXT_MAIN),
                (lhs_val,       _tok("BLUE")),
                (op,            _tok("YELLOW_BRIGHT")),
                (rhs_val,       _tok("ORANGE")),
                (result_str,    _tok("GREEN_BRIGHT") if result else _tok("RED_BRIGHT")),
            ]

            for col, (text, color) in enumerate(items):
                item = QTableWidgetItem(str(text) if text is not None else "")
                item.setForeground(QColor(color))
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                if is_blocker:
                    fnt = item.font()
                    fnt.setBold(True)
                    item.setFont(fnt)
                    item.setBackground(QColor(_tok("RED") + "18"))
                self.table.setItem(self.row, col, item)

        except Exception as e:
            logger.error(f"[_RuleRow.set] {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# GROUP PANEL  (one per signal group, shown in the Groups tab)
# ─────────────────────────────────────────────────────────────────────────────

class _GroupPanel(QFrame, _TM):
    """
    Panel for one signal group.
    Left border is colour-coded to the signal.
    Header row: signal name | logic | confidence bar | FIRED badge.
    Body: rule table.
    """

    def __init__(self, signal: str, parent=None):
        super().__init__(parent)
        self.signal          = signal
        self._logic_lbl      = None
        self._conf_bar       = None
        self._fired_lbl      = None
        self._table          = None
        self._no_rules_lbl   = None
        self._setup_ui()
        self._restyle()
        try:
            theme_manager.theme_changed.connect(self._restyle)
            theme_manager.density_changed.connect(self._restyle)
        except Exception:
            pass

    def _setup_ui(self):
        sig_color = _sig_color(self.signal)
        meta      = _SIG_META.get(self.signal, _SIG_META["WAIT"])
        label     = meta["label"]
        c  = self._c
        ty = self._ty
        sp = self._sp

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────────────
        hdr_widget = QWidget()
        hdr_widget.setObjectName("groupHdr")
        hdr = QHBoxLayout(hdr_widget)
        hdr.setContentsMargins(12, 8, 12, 8)
        hdr.setSpacing(10)

        # Signal name
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"""
            color: {sig_color};
            font-size: {ty.SIZE_MD}pt;
            font-weight: bold;
            letter-spacing: 0.4px;
            background: transparent;
        """)
        hdr.addWidget(name_lbl)

        hdr.addStretch()

        # Logic
        self._logic_lbl = QLabel("AND")
        self._logic_lbl.setStyleSheet(f"""
            color: {c.TEXT_DIM};
            font-size: {ty.SIZE_XS}pt;
            font-weight: bold;
            background: {c.BG_INPUT};
            border: 1px solid {c.BORDER};
            border-radius: 3px;
            padding: 1px 7px;
            font-family: 'Consolas', monospace;
        """)
        hdr.addWidget(self._logic_lbl)

        # Confidence bar (inline)
        self._conf_bar = _ConfidenceBar()
        self._conf_bar.setMinimumWidth(160)
        hdr.addWidget(self._conf_bar)

        # Fired badge
        self._fired_lbl = QLabel("NOT FIRED")
        self._fired_lbl.setAlignment(Qt.AlignCenter)
        self._fired_lbl.setFixedWidth(80)
        hdr.addWidget(self._fired_lbl)

        root.addWidget(hdr_widget)

        # ── Rule table ────────────────────────────────────────────────────────
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Rule Expression", "LHS", "Op", "RHS", "Result"]
        )
        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 5):
            hv.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setMinimumHeight(72)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        root.addWidget(self._table)

        self._no_rules_lbl = QLabel("  No rules configured for this signal.")
        self._no_rules_lbl.hide()
        root.addWidget(self._no_rules_lbl)

    def _restyle(self, _=None):
        c  = self._c
        sp = self._sp
        ty = self._ty
        sig_color = _sig_color(self.signal)

        self.setStyleSheet(f"""
            QFrame {{
                background: {c.BG_MAIN};
                border: 1px solid {c.BORDER};
                border-left: 3px solid {sig_color};
                border-radius: 0px;
            }}
            QWidget#groupHdr {{
                background: {c.BG_PANEL};
                border-bottom: 1px solid {c.BORDER};
            }}
        """)
        if self._table:
            self._table.setStyleSheet(_table_style())
        if self._no_rules_lbl:
            self._no_rules_lbl.setStyleSheet(
                f"color:{c.TEXT_DISABLED}; font-size:{ty.SIZE_XS}pt; padding:{sp.PAD_SM}px;"
            )

    def apply_theme(self, _=None):
        self._restyle()
        if self._conf_bar:
            self._conf_bar.apply_theme()

    def update(self, rule_results: List[Dict], fired: bool, logic: str,
               enabled: bool, confidence: float = 0.0,
               threshold: float = 0.6, indicator_cache: Dict = None):
        try:
            c  = self._c
            ty = self._ty

            # Logic label
            if self._logic_lbl:
                self._logic_lbl.setText(logic.upper())

            # Confidence
            if self._conf_bar:
                self._conf_bar.set_confidence(confidence, threshold)

            # Fired / disabled badge
            if self._fired_lbl:
                if not enabled:
                    self._fired_lbl.setText("DISABLED")
                    self._fired_lbl.setStyleSheet(f"""
                        color: {c.TEXT_DISABLED};
                        background: {c.BG_HOVER};
                        border: 1px solid {c.BORDER};
                        border-radius: 3px;
                        font-size: {ty.SIZE_XS}pt; font-weight: bold;
                        font-family: 'Consolas', monospace; padding: 1px 4px;
                    """)
                elif fired:
                    col = _tok("GREEN_BRIGHT")
                    self._fired_lbl.setText("✓ FIRED")
                    self._fired_lbl.setStyleSheet(f"""
                        color: {col}; background: {col}22;
                        border: 1px solid {col}66; border-radius: 3px;
                        font-size: {ty.SIZE_XS}pt; font-weight: bold;
                        font-family: 'Consolas', monospace; padding: 1px 4px;
                    """)
                else:
                    col = c.TEXT_DISABLED
                    self._fired_lbl.setText("NOT FIRED")
                    self._fired_lbl.setStyleSheet(f"""
                        color: {col}; background: transparent;
                        border: 1px solid {c.BORDER}; border-radius: 3px;
                        font-size: {ty.SIZE_XS}pt; font-weight: bold;
                        font-family: 'Consolas', monospace; padding: 1px 4px;
                    """)

            if not rule_results or self._table is None:
                if self._table is not None:
                    self._table.hide()
                    self._table.setRowCount(0)
                if self._no_rules_lbl:
                    self._no_rules_lbl.show()
                return

            if self._no_rules_lbl:
                self._no_rules_lbl.hide()
            if self._table:
                self._table.show()
                self._table.setRowCount(len(rule_results))

            first_blocker = -1
            if logic.upper() == "AND" and not fired:
                for idx, entry in enumerate(rule_results):
                    if not entry.get("result", True):
                        first_blocker = idx
                        break

            for i, entry in enumerate(rule_results):
                try:
                    rule_str   = entry.get("rule", "?")
                    result     = entry.get("result", False)
                    error      = entry.get("error", "")
                    weight     = entry.get("weight", 1.0)
                    is_blocker = (i == first_blocker)

                    lhs_raw = entry.get("lhs_value")
                    rhs_raw = entry.get("rhs_value")
                    lhs_val = f"{lhs_raw:.4f}" if lhs_raw is not None else "?"
                    rhs_val = f"{rhs_raw:.4f}" if rhs_raw is not None else "?"

                    if lhs_raw is None or rhs_raw is None:
                        lv, op_s, rv = _parse_rule_display(rule_str, indicator_cache)
                        if lhs_raw is None: lhs_val = lv
                        if rhs_raw is None: rhs_val = rv

                    op = "?"
                    for _op in [">=", "<=", "!=", "==", ">", "<"]:
                        if f" {_op} " in rule_str:
                            op = _op
                            break

                    _RuleRow(self._table, i).set(
                        rule_str, lhs_val, op, rhs_val,
                        result, weight, error, is_blocker
                    )
                except Exception as ex:
                    logger.warning(f"Rule row {i}: {ex}")

            if self._table:
                self._table.setFixedHeight(28 * len(rule_results) + 28)

        except Exception as e:
            logger.error(f"[_GroupPanel.update] {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR CACHE PANEL
# ─────────────────────────────────────────────────────────────────────────────

class _IndicatorCachePanel(QWidget, _TM):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._table = None
        self._build()
        try:
            theme_manager.theme_changed.connect(self._restyle)
            theme_manager.density_changed.connect(self._restyle)
        except Exception:
            pass

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Indicator", "Latest", "Previous"])
        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.Stretch)
        hv.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hv.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        lay.addWidget(self._table)
        self._restyle()

    def _restyle(self, _=None):
        if self._table:
            self._table.setStyleSheet(_table_style())

    def apply_theme(self, _=None):
        self._restyle()

    def update_cache(self, cache: Dict):
        try:
            import pandas as pd
            rows = []
            for key, series in cache.items():
                try:
                    if isinstance(series, pd.Series) and len(series) > 0:
                        latest = series.iloc[-1]
                        prev   = series.iloc[-2] if len(series) >= 2 else None
                        ls = f"{float(latest):.6f}" if latest is not None else "N/A"
                        ps = f"{float(prev):.6f}" if prev is not None else "N/A"
                    else:
                        ls = ps = "N/A"
                except Exception:
                    ls = ps = "err"
                rows.append((key, ls, ps))
            self._render(rows)
        except Exception as e:
            logger.error(f"[_IndicatorCachePanel.update_cache] {e}", exc_info=True)

    def update_from_values(self, indicator_values: Dict):
        try:
            rows = []
            for key, val in indicator_values.items():
                try:
                    last = val.get("last") if isinstance(val, dict) else None
                    prev = val.get("prev") if isinstance(val, dict) else None
                    ls = f"{last:.6f}" if last is not None else "N/A"
                    ps = f"{prev:.6f}" if prev is not None else "N/A"
                except Exception:
                    ls = ps = "err"
                rows.append((key, ls, ps))
            self._render(rows)
        except Exception as e:
            logger.error(f"[_IndicatorCachePanel.update_from_values] {e}", exc_info=True)

    def _render(self, rows: list):
        try:
            c = _p()
            if not self._table:
                return
            self._table.setRowCount(len(rows))
            for i, (key, latest, prev) in enumerate(rows):
                pairs = [
                    (key,    c.TEXT_DIM),
                    (latest, _tok("BLUE")),
                    (prev,   c.TEXT_DISABLED),
                ]
                for j, (text, color) in enumerate(pairs):
                    it = QTableWidgetItem(str(text) if text else "N/A")
                    it.setForeground(QColor(color))
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    self._table.setItem(i, j, it)
        except Exception as e:
            logger.error(f"[_IndicatorCachePanel._render] {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIDENCE PANEL  (2-col grid matching the strategy picker layout)
# ─────────────────────────────────────────────────────────────────────────────

class _ConfidencePanel(QWidget, _TM):
    """
    2×2 + 1 grid of confidence cells with an explanation strip at the top.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cells: Dict[str, "_ConfCell"] = {}
        self._expl_lbl      = None
        self._threshold_lbl = None
        self._build()
        try:
            theme_manager.theme_changed.connect(self._restyle)
            theme_manager.density_changed.connect(self._restyle)
        except Exception:
            pass

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        # Explanation strip
        expl_frame = QFrame()
        expl_frame.setObjectName("explFrame")
        expl_lay = QVBoxLayout(expl_frame)
        expl_lay.setContentsMargins(10, 8, 10, 8)
        expl_lay.setSpacing(4)
        expl_hdr = _section_hdr("Explanation")
        expl_lay.addWidget(expl_hdr)
        self._expl_lbl = QLabel("No evaluation yet.")
        self._expl_lbl.setWordWrap(True)
        expl_lay.addWidget(self._expl_lbl)
        thr_row = QHBoxLayout()
        thr_lbl = QLabel("THRESHOLD")
        thr_lbl.setObjectName("thrKey")
        thr_row.addWidget(thr_lbl)
        self._threshold_lbl = QLabel("60%")
        self._threshold_lbl.setObjectName("thrVal")
        thr_row.addWidget(self._threshold_lbl)
        thr_row.addStretch()
        expl_lay.addLayout(thr_row)
        lay.addWidget(expl_frame)

        # 2-col grid of cells (HOLD spans full width)
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        pos = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]
        for (row, col), sig in zip(pos, SIGNAL_GROUPS):
            cell = _ConfCellLarge(sig)
            grid.addWidget(cell, row, col)
            self._cells[sig] = cell

        hold = self._cells.get("HOLD")
        if hold:
            grid.removeWidget(hold)
            grid.addWidget(hold, 2, 0, 1, 2)

        lay.addWidget(grid_w)
        lay.addStretch()
        self._restyle()

    def _restyle(self, _=None):
        c  = _p()
        ty = _ty()
        sp = _sp()
        accent = _tok("YELLOW_BRIGHT")

        self.setStyleSheet(f"""
            QFrame#explFrame {{
                background: {c.BG_PANEL};
                border: 1px solid {c.BORDER};
                border-left: 3px solid {accent};
                border-radius: 0;
            }}
            QLabel[objectName="thrKey"] {{
                color: {c.TEXT_DISABLED};
                font-size: {ty.SIZE_XS}pt;
                font-weight: bold;
                letter-spacing: 0.5px;
                background: transparent;
            }}
            QLabel[objectName="thrVal"] {{
                color: {accent};
                font-size: {ty.SIZE_BODY}pt;
                font-weight: bold;
                font-family: 'Consolas', monospace;
                background: transparent;
            }}
        """)
        if self._expl_lbl:
            self._expl_lbl.setStyleSheet(
                f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_SM}pt; background:transparent;"
            )

    def apply_theme(self, _=None):
        self._restyle()
        for cell in self._cells.values():
            cell._restyle()

    def update_confidence(self, conf_dict: Dict[str, float],
                          threshold: float = 0.6, explanation: str = ""):
        try:
            if self._expl_lbl:
                self._expl_lbl.setText(explanation or "No explanation available.")
            if self._threshold_lbl:
                self._threshold_lbl.setText(f"{int(threshold * 100)}%")
            for sig, cell in self._cells.items():
                cell.set_confidence(conf_dict.get(sig, 0.0), threshold)
        except Exception as e:
            logger.error(f"[_ConfidencePanel.update_confidence] {e}", exc_info=True)


class _ConfCellLarge(QFrame, _TM):
    """Taller confidence cell used in the dedicated Confidence tab."""

    def __init__(self, signal: str, parent=None):
        super().__init__(parent)
        self.signal = signal
        meta = _SIG_META.get(signal, _SIG_META["WAIT"])
        self._attr  = meta["attr"]
        self._conf  = 0.0
        self._thr   = 0.6
        self._bar   = None
        self._pct   = None
        self._build(meta["label"], meta["short"])
        self._restyle()

    def _build(self, label: str, short: str):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)

        code = QLabel(short)
        code.setObjectName("cellCode")
        top.addWidget(code)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        top.addWidget(self._bar, 1)

        self._pct = QLabel("0%")
        self._pct.setObjectName("cellPct")
        self._pct.setFixedWidth(36)
        self._pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self._pct)

        lay.addLayout(top)

        lbl = QLabel(label)
        lbl.setObjectName("cellLabel")
        lay.addWidget(lbl)

    def _restyle(self, _=None):
        c   = _p()
        ty  = _ty()
        col = _tok(self._attr)
        self.setStyleSheet(f"""
            QFrame {{
                background: {c.BG_PANEL};
                border: 1px solid {c.BORDER};
                border-radius: {_sp().RADIUS_MD}px;
            }}
            QLabel[objectName="cellCode"] {{
                color: {col}; font-size:{ty.SIZE_BODY}pt; font-weight:bold;
                font-family:'Consolas',monospace; background:transparent;
            }}
            QLabel[objectName="cellPct"] {{
                color: {col}; font-size:{ty.SIZE_XS}pt; font-weight:bold;
                font-family:'Consolas',monospace; background:transparent;
            }}
            QLabel[objectName="cellLabel"] {{
                color: {c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;
                letter-spacing:0.4px; background:transparent;
            }}
        """)
        self._apply_bar(col)

    def _apply_bar(self, col: str):
        c = _p()
        if self._bar:
            self._bar.setStyleSheet(f"""
                QProgressBar {{ border:none; border-radius:3px; background:{c.BG_HOVER}; }}
                QProgressBar::chunk {{
                    border-radius:3px;
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 {col}44, stop:1 {col});
                }}
            """)

    def set_confidence(self, conf: float, thr: float = 0.6):
        self._conf = conf
        self._thr  = thr
        pct = int(conf * 100)
        if self._bar: self._bar.setValue(pct)
        if self._pct: self._pct.setText(f"{pct}%")

        if conf >= thr:          attr = "GREEN_BRIGHT"
        elif conf >= thr * 0.6:  attr = "YELLOW_BRIGHT"
        else:                    attr = "RED_BRIGHT"
        col = _tok(attr)

        if self._pct:
            self._pct.setStyleSheet(
                f"color:{col}; font-size:{_ty().SIZE_XS}pt; font-weight:bold; "
                f"font-family:'Consolas',monospace; background:transparent;"
            )
        self._apply_bar(col)


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
            theme_manager.density_changed.connect(self._restyle)
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
        """)

    def apply_theme(self, _=None):
        self._restyle()

    def update_result(self, result: Dict):
        try:
            if result is None:
                self._edit.setPlainText("No data available")
                return
            text = json.dumps(result, indent=2, default=str)
            self._edit.setPlainText(text)
        except Exception as e:
            self._edit.setPlainText(f"Error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: rule display parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_rule_display(rule_str: str, cache: Dict = None) -> Tuple[str, str, str]:
    try:
        if not rule_str:
            return "?", "?", "?"
        for op in [">=", "<=", "!=", "==", ">", "<"]:
            if f" {op} " in rule_str:
                parts = rule_str.split(f" {op} ", 1)
                lhs   = parts[0].strip()
                rhs   = parts[1].strip() if len(parts) > 1 else "?"
                lhs_v = _lookup_cache(lhs, cache)
                rhs_v = _lookup_cache(rhs, cache)
                return lhs_v, op, rhs_v
        return "?", "?", "?"
    except Exception:
        return "?", "?", "?"


def _lookup_cache(name: str, cache: Dict = None) -> str:
    try:
        if not cache:
            return name
        base = name.lower().split("(")[0].strip()
        for key, series in cache.items():
            if key.startswith(base + "_"):
                try:
                    import pandas as pd
                    if isinstance(series, pd.Series) and len(series) > 0:
                        val = series.iloc[-1]
                        if val is not None and not pd.isna(val):
                            import math
                            fval = float(val)
                            if not math.isnan(fval):
                                fmt = ".6f" if abs(fval) < 0.01 or abs(fval) > 1000 else ".2f"
                                return f"{name} [{fval:{fmt}}]"
                except Exception:
                    pass
        try:
            return f"{float(name):.2f}"
        except ValueError:
            return name
    except Exception:
        return name


# ─────────────────────────────────────────────────────────────────────────────
# MAIN POPUP
# ─────────────────────────────────────────────────────────────────────────────

class DynamicSignalDebugPopup(QDialog, _TM):
    """
    Signal Ops Console — redesigned debug popup.
    Non-modal, frameless, 1100×820 px.
    """

    def __init__(self, trading_app, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent, Qt.Window)
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            self.trading_app = trading_app
            self.resize(1100, 820)
            self.setMinimumSize(820, 600)

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

            logger.info("DynamicSignalDebugPopup (redesigned) initialized")

        except Exception as e:
            logger.critical(f"[DynamicSignalDebugPopup.__init__] {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        self.trading_app            = None
        self._last_signal_value     = ""
        self._auto_refresh          = True
        self._indicator_cache       = {}
        self._current_strategy_slug = None
        self._last_confidence: Dict[str, float] = {}
        self._last_threshold        = 0.6
        self._timer                 = None
        self._signal_badge          = None
        self._lbl_conflict          = None
        self._lbl_available         = None
        self._lbl_symbol            = None
        self._lbl_last_close        = None
        self._lbl_bars              = None
        self._lbl_timestamp         = None
        self._lbl_strategy          = None
        self._fired_pills: Dict[str, _FiredPill] = {}
        self._group_panels: Dict[str, _GroupPanel] = {}
        self._cache_panel           = None
        self._json_panel            = None
        self._confidence_panel      = None
        self._tabs                  = None
        self._status_lbl            = None
        self._auto_chk              = None
        self._outer                 = None
        self._drag_pos              = None

    # ── Error fallback ────────────────────────────────────────────────────────

    def _create_error_dialog(self, parent):
        try:
            super().__init__(parent, Qt.Window)
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
            root = QVBoxLayout(self)
            root.setContentsMargins(16, 16, 16, 16)
            card = QFrame()
            card.setStyleSheet(
                f"background:{_p().BG_PANEL}; border:1px solid {_p().RED}; "
                f"border-top:2px solid {_tok('YELLOW_BRIGHT')}; border-radius:8px;"
            )
            lay = QVBoxLayout(card)
            lbl = QLabel("❌ Signal Debug failed to initialise.\nCheck logs.")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"color:{_p().RED_BRIGHT}; padding:20px; font-size:{_ty().SIZE_MD}pt;"
            )
            lay.addWidget(lbl)
            btn = QPushButton("Close")
            btn.clicked.connect(self.close)
            lay.addWidget(btn, 0, Qt.AlignCenter)
            root.addWidget(card)
        except Exception as e:
            logger.error(f"[_create_error_dialog] {e}", exc_info=True)

    # ── UI build ──────────────────────────────────────────────────────────────

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
        outer_lay.addWidget(self._build_status_header())
        outer_lay.addWidget(self._build_tabs(), 1)
        outer_lay.addWidget(self._build_footer())

        root.addWidget(self._outer)
        self._style_outer()

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(44)
        bar.mousePressEvent   = self._drag_start
        bar.mouseMoveEvent    = self._drag_move
        bar.mouseReleaseEvent = lambda e: setattr(self, "_drag_pos", None)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(8)

        logo = QLabel("SD")
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

        title = QLabel("SIGNAL ENGINE DEBUG")
        title.setStyleSheet(f"""
            color: {_p().TEXT_MAIN};
            font-size: {_ty().SIZE_SM}pt;
            font-weight: bold;
            letter-spacing: 1.8px;
            background: transparent;
        """)
        lay.addWidget(title)
        lay.addStretch()

        ref = self._icon_btn("↺", "Refresh Now")
        ref.clicked.connect(self.refresh)
        lay.addWidget(ref)

        cls = self._icon_btn("✕")
        cls.clicked.connect(self.close)
        lay.addWidget(cls)

        return bar

    def _icon_btn(self, text: str, tip: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.PointingHandCursor)
        if tip: btn.setToolTip(tip)
        c = _p()
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {c.TEXT_DIM};
                border: none; border-radius: 14px;
                font-size: {_ty().SIZE_BODY}pt; font-weight: bold;
            }}
            QPushButton:hover {{ background:{c.BG_HOVER}; color:{c.TEXT_MAIN}; }}
        """)
        return btn

    def _build_status_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setObjectName("statusHdr")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(20)

        # ── Final signal (large badge) ─────────────────────────────────────
        sig_col = QVBoxLayout()
        sig_col.setSpacing(4)
        eyebrow = QLabel("FINAL SIGNAL")
        eyebrow.setStyleSheet(f"""
            color: {_tok('YELLOW_BRIGHT')};
            font-size: {_ty().SIZE_XS}pt;
            font-weight: bold;
            letter-spacing: 1.0px;
            background: transparent;
        """)
        sig_col.addWidget(eyebrow, 0, Qt.AlignCenter)
        self._signal_badge = _SignalBadge()
        sig_col.addWidget(self._signal_badge)
        lay.addLayout(sig_col)

        # ── Vertical divider ───────────────────────────────────────────────
        v = QFrame()
        v.setFrameShape(QFrame.VLine)
        v.setStyleSheet(f"background:{_p().BORDER}; max-width:1px;")
        lay.addWidget(v)

        # ── Stat grid ─────────────────────────────────────────────────────
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)

        def _stat(row: int, key: str, store_attr: str) -> QLabel:
            k = QLabel(key)
            k.setStyleSheet(
                f"color:{_p().TEXT_DISABLED}; font-size:{_ty().SIZE_XS}pt; "
                f"font-weight:bold; letter-spacing:0.5px; background:transparent;"
            )
            v_lbl = QLabel("—")
            v_lbl.setStyleSheet(
                f"color:{_p().TEXT_MAIN}; font-size:{_ty().SIZE_SM}pt; "
                f"font-weight:bold; font-family:'Consolas',monospace; background:transparent;"
            )
            grid.addWidget(k, row, 0)
            grid.addWidget(v_lbl, row, 1)
            setattr(self, store_attr, v_lbl)
            return v_lbl

        _stat(0, "CONFLICT",     "_lbl_conflict")
        _stat(1, "RULES AVAIL",  "_lbl_available")
        _stat(2, "SYMBOL",       "_lbl_symbol")
        _stat(3, "LAST CLOSE",   "_lbl_last_close")
        _stat(4, "BARS",         "_lbl_bars")
        _stat(5, "REFRESHED",    "_lbl_timestamp")
        _stat(6, "STRATEGY",     "_lbl_strategy")

        lay.addLayout(grid)

        # ── Vertical divider ───────────────────────────────────────────────
        v2 = QFrame()
        v2.setFrameShape(QFrame.VLine)
        v2.setStyleSheet(f"background:{_p().BORDER}; max-width:1px;")
        lay.addWidget(v2)

        # ── Fired group pills ──────────────────────────────────────────────
        pills_col = QVBoxLayout()
        pills_col.setSpacing(6)
        pills_eyebrow = QLabel("FIRED GROUPS")
        pills_eyebrow.setStyleSheet(f"""
            color: {_tok('YELLOW_BRIGHT')};
            font-size: {_ty().SIZE_XS}pt;
            font-weight: bold;
            letter-spacing: 1.0px;
            background: transparent;
        """)
        pills_col.addWidget(pills_eyebrow, 0, Qt.AlignCenter)

        pills_row = QHBoxLayout()
        pills_row.setSpacing(6)
        self._fired_pills = {}
        for sig in SIGNAL_GROUPS:
            pill = _FiredPill(sig)
            pills_row.addWidget(pill)
            self._fired_pills[sig] = pill

        pills_col.addLayout(pills_row)
        lay.addLayout(pills_col)

        lay.addStretch()
        return hdr

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("mainTabs")

        tabs.setStyleSheet(f"""
            QTabWidget#mainTabs::pane {{
                border: none;
                border-top: 1px solid {_p().BORDER};
                background: {_p().BG_MAIN};
            }}
            QTabBar::tab {{
                background: {_p().BG_PANEL};
                color: {_p().TEXT_DIM};
                border: none;
                border-right: 1px solid {_p().BORDER};
                padding: {_sp().PAD_SM}px {_sp().PAD_XL}px;
                min-width: 120px;
                font-size: {_ty().SIZE_SM}pt;
                font-weight: bold;
                letter-spacing: 0.3px;
            }}
            QTabBar::tab:selected {{
                color: {_tok('YELLOW_BRIGHT')};
                border-bottom: 2px solid {_tok('YELLOW_BRIGHT')};
                background: {_p().BG_MAIN};
            }}
            QTabBar::tab:hover:!selected {{
                color: {_p().TEXT_MAIN};
                background: {_p().BG_HOVER};
            }}
        """)

        self._tabs = tabs

        # Tab 1: Signal Groups (scrollable)
        groups_scroll = QScrollArea()
        groups_scroll.setWidgetResizable(True)
        groups_scroll.setFrameShape(QFrame.NoFrame)
        groups_scroll.setStyleSheet(f"""
            QScrollArea {{ background:{_p().BG_MAIN}; border:none; }}
            QScrollBar:vertical {{ background:{_p().BG_PANEL}; width:5px; border-radius:3px; }}
            QScrollBar::handle:vertical {{ background:{_p().BORDER_STRONG}; border-radius:3px; min-height:16px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        groups_container = QWidget()
        groups_container.setStyleSheet(f"background:{_p().BG_MAIN};")
        groups_v = QVBoxLayout(groups_container)
        groups_v.setContentsMargins(0, 0, 0, 0)
        groups_v.setSpacing(1)

        self._group_panels = {}
        for sig in SIGNAL_GROUPS:
            panel = _GroupPanel(sig)
            self._group_panels[sig] = panel
            groups_v.addWidget(panel)
        groups_v.addStretch()
        groups_scroll.setWidget(groups_container)
        tabs.addTab(groups_scroll, "SIGNAL GROUPS")

        # Tab 2: Indicators
        self._cache_panel = _IndicatorCachePanel()
        tabs.addTab(self._cache_panel, "INDICATORS")

        # Tab 3: Confidence
        conf_scroll = QScrollArea()
        conf_scroll.setWidgetResizable(True)
        conf_scroll.setFrameShape(QFrame.NoFrame)
        conf_scroll.setStyleSheet(f"""
            QScrollArea {{ background:{_p().BG_MAIN}; border:none; }}
        """)
        self._confidence_panel = _ConfidencePanel()
        conf_scroll.setWidget(self._confidence_panel)
        tabs.addTab(conf_scroll, "CONFIDENCE")

        # Tab 4: Raw JSON
        self._json_panel = _RawJsonPanel()
        tabs.addTab(self._json_panel, "RAW JSON")

        return tabs

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("footer")
        footer.setFixedHeight(50)
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(8)

        self._auto_chk = QCheckBox("Auto-refresh (1s)")
        self._auto_chk.setChecked(True)
        self._auto_chk.toggled.connect(self._on_auto_toggle)
        c = _p(); ty = _ty(); sp = _sp()
        self._auto_chk.setStyleSheet(f"""
            QCheckBox {{
                color: {c.TEXT_DIM};
                font-size: {ty.SIZE_SM}pt;
                spacing: {sp.GAP_SM}px;
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {c.BORDER_STRONG};
                border-radius: 3px;
                background: {c.BG_INPUT};
            }}
            QCheckBox::indicator:checked {{
                background: {_tok('YELLOW_BRIGHT')};
                border-color: {_tok('YELLOW_BRIGHT')};
            }}
        """)
        lay.addWidget(self._auto_chk)

        self._status_lbl = QLabel("Waiting for data…")
        self._status_lbl.setStyleSheet(
            f"color:{c.TEXT_DISABLED}; font-size:{ty.SIZE_XS}pt; "
            f"background:transparent; font-family:'Consolas',monospace;"
        )
        lay.addWidget(self._status_lbl)
        lay.addStretch()

        ref_btn = QPushButton("↺  Refresh")
        ref_btn.setCursor(Qt.PointingHandCursor)
        ref_btn.setFixedHeight(34)
        ref_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {c.TEXT_DIM};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: 0 14px;
                font-size: {ty.SIZE_SM}pt; font-weight: bold;
            }}
            QPushButton:hover {{ border-color:{_tok('YELLOW_BRIGHT')}; color:{_tok('YELLOW_BRIGHT')}; }}
        """)
        ref_btn.clicked.connect(self.refresh)
        lay.addWidget(ref_btn)

        close_btn = QPushButton("✕  Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_tok('RED_BRIGHT')}22;
                color: {_tok('RED_BRIGHT')};
                border: 1px solid {_tok('RED_BRIGHT')}66;
                border-radius: {sp.RADIUS_MD}px;
                padding: 0 14px;
                font-size: {ty.SIZE_SM}pt; font-weight: bold;
            }}
            QPushButton:hover {{
                background: {_tok('RED_BRIGHT')};
                color: white;
            }}
        """)
        close_btn.clicked.connect(self.close)
        lay.addWidget(close_btn)

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
            QWidget#statusHdr {{
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
            if self._signal_badge: self._signal_badge.apply_theme()
            for pill in self._fired_pills.values(): pill.apply_theme()
            for panel in self._group_panels.values(): panel.apply_theme()
            if self._cache_panel: self._cache_panel.apply_theme()
            if self._confidence_panel: self._confidence_panel.apply_theme()
            if self._json_panel: self._json_panel.apply_theme()
        except Exception as e:
            logger.error(f"[apply_theme] {e}", exc_info=True)

    # ── Dragging ──────────────────────────────────────────────────────────────

    def _drag_start(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def _drag_move(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(e.globalPos() - self._drag_pos)

    # ── Refresh ───────────────────────────────────────────────────────────────

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
            c  = self._c
            ty = self._ty

            if self.trading_app is None:
                self._set_status("⚠  trading_app is None")
                return

            state = state_manager.get_state()
            if state is None:
                self._set_status("⚠  state_manager returned None")
                return

            trend_data    = safe_getattr(state, "derivative_trend", None) or {}
            option_signal = trend_data.get("option_signal")

            if option_signal is None:
                self._set_status("⚠  No option_signal in state.derivative_trend yet.")
                return

            if not option_signal.get("available", False):
                msg = ("ℹ  Engine available but no rules configured."
                       if option_signal.get("fired")
                       else "ℹ  DynamicSignalEngine not available.")
                self._set_status(msg)
                return

            # ── Signal badge ─────────────────────────────────────────────────
            signal_val = option_signal.get("signal_value", "WAIT")
            if self._signal_badge:
                self._signal_badge.update_signal(signal_val)

            # ── Stat labels ───────────────────────────────────────────────────
            conflict = option_signal.get("conflict", False)
            if self._lbl_conflict:
                col = _tok("RED_BRIGHT") if conflict else _tok("GREEN_BRIGHT")
                self._lbl_conflict.setText("YES" if conflict else "No")
                self._lbl_conflict.setStyleSheet(
                    f"color:{col}; font-size:{ty.SIZE_SM}pt; font-weight:bold; "
                    f"font-family:'Consolas',monospace; background:transparent;"
                )

            if self._lbl_available:
                self._lbl_available.setText("Yes")
                self._lbl_available.setStyleSheet(
                    f"color:{_tok('GREEN_BRIGHT')}; font-size:{ty.SIZE_SM}pt; font-weight:bold; "
                    f"font-family:'Consolas',monospace; background:transparent;"
                )

            symbol      = trend_data.get("name", "—")
            close_list  = trend_data.get("close") or []
            last_close  = close_list[-1] if close_list else "—"

            for lbl, val in [
                (self._lbl_symbol,     str(symbol)),
                (self._lbl_last_close, str(last_close)),
                (self._lbl_bars,       str(len(close_list))),
                (self._lbl_timestamp,  datetime.now().strftime("%H:%M:%S")),
            ]:
                if lbl:
                    lbl.setText(val)

            # Strategy slug
            if self._lbl_strategy:
                try:
                    if (safe_hasattr(self.trading_app, "detector") and
                            safe_hasattr(self.trading_app.detector, "signal_engine") and
                            self.trading_app.detector.signal_engine is not None):
                        engine = self.trading_app.detector.signal_engine
                        slug   = safe_getattr(engine, "strategy_slug", None)
                        self._lbl_strategy.setText(slug or "Default")
                        if slug and slug != self._current_strategy_slug:
                            self._current_strategy_slug = slug
                    else:
                        self._lbl_strategy.setText("—")
                except Exception:
                    self._lbl_strategy.setText("—")

            # ── Fired pills ───────────────────────────────────────────────────
            fired_map = option_signal.get("fired", {})
            for sig, pill in self._fired_pills.items():
                pill.set_fired(bool(fired_map.get(sig, False)))

            # ── Group panels ──────────────────────────────────────────────────
            rule_results  = option_signal.get("rule_results", {})
            conf_dict     = option_signal.get("confidence", {})
            explanation   = option_signal.get("explanation", "")
            threshold     = option_signal.get("threshold", 0.6)

            self._last_confidence = conf_dict
            self._last_threshold  = threshold

            indicator_cache = {}
            try:
                if (safe_hasattr(self.trading_app, "detector") and
                        safe_hasattr(self.trading_app.detector, "signal_engine") and
                        self.trading_app.detector.signal_engine is not None):
                    indicator_cache = safe_getattr(
                        self.trading_app.detector.signal_engine, "_last_cache", {}
                    )
            except Exception:
                pass

            for sig in SIGNAL_GROUPS:
                if sig not in self._group_panels:
                    continue
                panel      = self._group_panels[sig]
                rules_sig  = rule_results.get(sig, [])
                is_fired   = fired_map.get(sig, False)
                logic      = "AND"
                enabled    = True
                confidence = conf_dict.get(sig, 0.0)

                try:
                    eng = safe_getattr(
                        safe_getattr(self.trading_app, "detector", None),
                        "signal_engine", None
                    )
                    if eng is not None:
                        logic   = eng.get_logic(sig)
                        enabled = eng.is_enabled(sig)
                except Exception:
                    pass

                panel.update(rules_sig, is_fired, logic, enabled,
                             confidence, threshold, indicator_cache)

            # ── Indicator values tab ──────────────────────────────────────────
            ind_values = option_signal.get("indicator_values", {})
            if self._cache_panel:
                try:
                    if ind_values:
                        self._cache_panel.update_from_values(ind_values)
                    else:
                        self._cache_panel.update_cache(indicator_cache)
                except Exception as ex:
                    logger.warning(f"cache panel: {ex}")

            # ── Confidence tab ────────────────────────────────────────────────
            if self._confidence_panel:
                try:
                    self._confidence_panel.update_confidence(
                        conf_dict, threshold, explanation
                    )
                except Exception as ex:
                    logger.warning(f"conf panel: {ex}")

            # ── Raw JSON tab ──────────────────────────────────────────────────
            if self._json_panel:
                try:
                    self._json_panel.update_result(option_signal)
                except Exception as ex:
                    logger.warning(f"json panel: {ex}")

            self._set_status(
                f"✓  {datetime.now().strftime('%H:%M:%S')}",
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
            f"background:transparent; font-family:'Consolas',monospace;"
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