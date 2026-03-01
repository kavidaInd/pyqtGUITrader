"""
backtest/backtest_window.py
============================
Full backtesting window with state_manager integration.

Layout (mirrors main TradingGUI):
  ┌──────────────────────────────────┬─────────────────┐
  │  Results Panel (tabs)            │  Settings       │
  │  ├─ 📈 Overview                   │  Sidebar        │
  │  ├─ 📋 Trade Log                  │  (right side,   │
  │  ├─ 🔬 Strategy Analysis           │   tabbed like   │
  │  └─ 📉 Equity Curve                │   StatusPanel)  │
  └──────────────────────────────────┴─────────────────┘
  │  Progress bar + Run / Stop buttons                  │
  └─────────────────────────────────────────────────────┘

Uses state_manager to access and restore trade state, ensuring consistency
between live trading and backtesting.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from PyQt5.QtCore import QDate, Qt, pyqtSlot, QTimer
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox,
    QFrame, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QFileDialog,
)

from backtest.backtest_candle_debug_tab import CandleDebugTab
from backtest.backtest_engine import BacktestConfig, BacktestResult
from backtest.backtest_help_tab import BacktestHelpTab
from backtest.backtest_thread import BacktestThread
from models.trade_state_manager import state_manager
from strategy.strategy_manager import StrategyManager

logger = logging.getLogger(__name__)

# ── Palette (matches TradingGUI / StatusPanel) ─────────────────────────────────
BG        = "#0d1117"
SURFACE   = "#161b22"
SURFACE2  = "#1c2128"
BORDER    = "#30363d"
TEXT      = "#e6edf3"
SUBTEXT   = "#8b949e"
ACCENT    = "#2ea043"
ACCENT_H  = "#3fb950"
WARN      = "#d29922"
ERROR_C   = "#f85149"
INFO      = "#58a6ff"
CALL_CLR  = "#3fb950"
PUT_CLR   = "#f85149"
SYNTH_BG  = "#2d2a1a"
REAL_BG   = BG
ORANGE    = "#ffa657"
PURPLE    = "#bc8cff"

SIGNAL_COLORS = {
    "BUY_CALL":  CALL_CLR,
    "BUY_PUT":   PUT_CLR,
    "EXIT_CALL": ERROR_C,
    "EXIT_PUT":  ORANGE,
    "HOLD":      WARN,
    "WAIT":      SUBTEXT,
}

ANALYSIS_TIMEFRAMES = ["1m", "2m", "3m", "5m", "10m", "15m", "30m", "60m", "120m", "240m"]

# ── Global stylesheet ──────────────────────────────────────────────────────────
_CSS = f"""
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: 'Segoe UI', 'SF Pro Display', 'Ubuntu', sans-serif;
    font-size: 14px;
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 14px;
    font-weight: bold;
    color: {SUBTEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {INFO};
}}
QLabel {{ color: {TEXT}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 10px;
    color: {TEXT};
    min-height: 28px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    color: {TEXT};
    selection-background-color: {ACCENT};
}}
QPushButton {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 16px;
    color: {TEXT};
    font-weight: 600;
}}
QPushButton:hover  {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {SUBTEXT}; background: {SURFACE}; }}
QPushButton#runBtn {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #fff;
    font-size: 15px;
    padding: 8px 28px;
    border-radius: 5px;
}}
QPushButton#runBtn:hover {{ background: {ACCENT_H}; }}
QPushButton#stopBtn {{
    background: {ERROR_C};
    border-color: {ERROR_C};
    color: #fff;
    border-radius: 5px;
}}
QTableWidget {{
    background: {BG};
    alternate-background-color: {SURFACE};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}
QHeaderView::section {{
    background: {SURFACE2};
    color: {SUBTEXT};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 6px 10px;
    font-weight: bold;
    font-size: 13px;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {BG};
    border-radius: 0 4px 4px 4px;
}}
QTabBar::tab {{
    background: {SURFACE};
    color: {SUBTEXT};
    padding: 7px 18px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    font-size: 13px;
    font-weight: bold;
}}
QTabBar::tab:selected {{
    background: {BG};
    color: {TEXT};
    border-bottom: 2px solid {INFO};
}}
QTabBar::tab:hover:!selected {{ background: {SURFACE2}; }}
QProgressBar {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    color: {TEXT};
    height: 8px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT}, stop:1 {ACCENT_H});
    border-radius: 3px;
}}
QScrollBar:vertical {{
    background: {SURFACE}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 4px; min-height: 20px;
}}
QCheckBox {{ color: {TEXT}; spacing: 6px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {SURFACE};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QSplitter::handle {{ background: {BORDER}; width: 2px; height: 2px; }}
QTreeWidget {{
    background: {BG};
    alternate-background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}
QTreeWidget::item {{
    padding: 4px 8px;
    border-bottom: 1px solid {BORDER};
}}
QTreeWidget::item:selected {{
    background: {SURFACE2};
    color: {ACCENT};
}}
QTextEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    color: {TEXT};
    font-family: 'Courier New', monospace;
    font-size: 13px;
}}
"""

# ── Helpers ────────────────────────────────────────────────────────────────────

def _label(text, bold=False, color=TEXT, size=14):
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {color}; font-size: {size}px;"
        + (" font-weight: bold;" if bold else "")
    )
    return lbl


def _sep():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color: {BORDER};")
    return f


def _card(title: str, title_color: str = INFO) -> QGroupBox:
    g = QGroupBox(title)
    g.setStyleSheet(f"QGroupBox::title {{ color: {title_color}; }}")
    return g


def _qdate_to_datetime(qd: QDate, end_of_day: bool = False) -> datetime:
    """Convert QDate → datetime."""
    if end_of_day:
        return datetime(qd.year(), qd.month(), qd.day(), 23, 59, 59)
    return datetime(qd.year(), qd.month(), qd.day(), 0, 0, 0)


# ── BarAnalysis ────────────────────────────────────────────────────────────────

class BarAnalysis:
    """Analysis results for a single bar/candle."""

    def __init__(self, timestamp: datetime, spot_price: float, signal: str,
                 confidence: Dict[str, float], rule_results: Dict[str, List[Dict]],
                 indicator_values: Dict[str, Dict[str, float]],
                 timeframe: str = "5m"):
        self.timestamp = timestamp
        self.spot_price = spot_price
        self.signal = signal
        self.confidence = confidence
        self.rule_results = rule_results
        self.indicator_values = indicator_values
        self.timeframe = timeframe

    def to_dict(self) -> Dict:
        result = {
            "timeframe":   self.timeframe,
            "timestamp":   self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "spot_price":  self.spot_price,
            "signal":      self.signal,
        }
        if self.confidence:
            result["overall_confidence"] = sum(self.confidence.values()) / len(self.confidence)
        else:
            result["overall_confidence"] = 0.0
        for sig, conf in self.confidence.items():
            result[f"confidence_{sig}"] = conf
        for indicator, values in self.indicator_values.items():
            result[f"indicator_{indicator}_last"] = values.get("last", "")
            result[f"indicator_{indicator}_prev"] = values.get("prev", "")
        for sig, rules in self.rule_results.items():
            passed = sum(1 for r in rules if r.get("result", False))
            total = len(rules)
            result[f"rules_{sig}_passed"] = passed
            result[f"rules_{sig}_total"] = total
            result[f"rules_{sig}_pass_rate"] = (passed / total) if total else 0
        return result


# ── Multi-Timeframe Analysis Tab ───────────────────────────────────────────────

class MultiTimeframeAnalysisTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.analysis_data: Dict[str, List[BarAnalysis]] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(ANALYSIS_TIMEFRAMES)
        self.timeframe_combo.setCurrentText("5m")
        self.timeframe_combo.currentTextChanged.connect(self._show_timeframe)
        toolbar.addWidget(_label("Timeframe:"))
        toolbar.addWidget(self.timeframe_combo)
        toolbar.addSpacing(12)

        self.export_btn = QPushButton("📥 Export Timeframe")
        self.export_btn.clicked.connect(self._export_current)
        self.export_btn.setEnabled(False)
        toolbar.addWidget(self.export_btn)

        self.export_all_btn = QPushButton("📥 Export All")
        self.export_all_btn.clicked.connect(self._export_all)
        self.export_all_btn.setEnabled(False)
        toolbar.addWidget(self.export_all_btn)

        toolbar.addStretch()
        self.stats_lbl = _label("No analysis data", color=SUBTEXT, size=13)
        toolbar.addWidget(self.stats_lbl)
        layout.addLayout(toolbar)

        # Splitter: tree on top, details below
        splitter = QSplitter(Qt.Vertical)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(
            ["Time", "Spot", "Signal", "Confidence",
             "BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]
        )
        self.tree.setAlternatingRowColors(True)
        self.tree.itemClicked.connect(self._on_bar_selected)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        splitter.addWidget(self.tree)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(220)
        splitter.addWidget(self.details_text)
        splitter.setSizes([500, 220])

        layout.addWidget(splitter, 1)

    def set_analysis_data(self, data: Dict[str, List[BarAnalysis]]):
        self.analysis_data = data
        has = any(data.values())
        self.export_btn.setEnabled(has)
        self.export_all_btn.setEnabled(has)
        total = sum(len(v) for v in data.values())
        self.stats_lbl.setText(f"{total} bars across {len(data)} timeframe(s)")
        self._show_timeframe(self.timeframe_combo.currentText())

    def _show_timeframe(self, tf: str):
        self.tree.clear()
        for bar in self.analysis_data.get(tf, []):
            item = QTreeWidgetItem()
            item.setText(0, bar.timestamp.strftime("%H:%M:%S"))
            item.setData(0, Qt.UserRole, bar.timestamp)
            item.setText(1, f"{bar.spot_price:.2f}")
            item.setText(2, bar.signal)
            item.setForeground(2, QColor(SIGNAL_COLORS.get(bar.signal, TEXT)))
            overall = (sum(bar.confidence.values()) / len(bar.confidence)
                       if bar.confidence else 0.0)
            item.setText(3, f"{overall:.1%}")
            for i, sig in enumerate(["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"], 4):
                conf = bar.confidence.get(sig, 0)
                item.setText(i, f"{conf:.1%}")
                clr = ACCENT if conf >= 0.6 else (WARN if conf >= 0.3 else SUBTEXT)
                item.setForeground(i, QColor(clr))
            self.tree.addTopLevelItem(item)

    def _on_bar_selected(self, item: QTreeWidgetItem, _col: int):
        ts = item.data(0, Qt.UserRole)
        tf = self.timeframe_combo.currentText()
        for bar in self.analysis_data.get(tf, []):
            if bar.timestamp == ts:
                self._show_details(bar)
                break

    def _show_details(self, bar: BarAnalysis):
        lines = [
            f"📊  {bar.timeframe}  —  {bar.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Spot: ₹{bar.spot_price:.2f}   Signal: {bar.signal}",
            "",
            "📈 Confidence Scores:",
        ]
        for sig, conf in bar.confidence.items():
            tag = "✓ HIGH" if conf >= 0.6 else ("⚠ MED" if conf >= 0.3 else "✗ LOW")
            lines.append(f"  {sig}: {conf:.1%}  ({tag})")
        lines.append("")
        lines.append("📋 Rule Evaluations:")
        for sig, rules in bar.rule_results.items():
            passed = [r for r in rules if r.get("result", False)]
            if passed:
                lines.append(f"  {sig} ({len(passed)}/{len(rules)} passed):")
                for r in passed[:3]:
                    lines.append(f"    ✓ {r.get('rule','')[:60]}  w={r.get('weight',1):.1f}")
        if bar.indicator_values:
            lines.append("")
            lines.append("📊 Indicator Values:")
            for name, vals in bar.indicator_values.items():
                last = vals.get("last", "N/A")
                prev = vals.get("prev", "N/A")
                try:
                    diff = f" ({last - prev:+.2f})" if isinstance(last, (int, float)) else ""
                except Exception:
                    diff = ""
                lines.append(f"  {name}: {last} / {prev}{diff}")
        self.details_text.setText("\n".join(lines))

    def _export_current(self):
        tf = self.timeframe_combo.currentText()
        data = self.analysis_data.get(tf, [])
        if not data:
            QMessageBox.warning(self, "No Data", f"No data for {tf}.")
            return
        fname, _ = QFileDialog.getSaveFileName(
            self, f"Save {tf} Analysis",
            f"analysis_{tf}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        if fname:
            pd.DataFrame([b.to_dict() for b in data]).to_csv(fname, index=False)
            QMessageBox.information(self, "Saved", fname)

    def _export_all(self):
        if not self.analysis_data:
            QMessageBox.warning(self, "No Data", "Nothing to export.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if not directory:
            return
        n = 0
        for tf, data in self.analysis_data.items():
            if data:
                fp = os.path.join(directory, f"analysis_{tf}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
                pd.DataFrame([b.to_dict() for b in data]).to_csv(fp, index=False)
                n += 1
        QMessageBox.information(self, "Done", f"Exported {n} file(s) to:\n{directory}")


# ── Settings Sidebar (RIGHT side, tabbed like StatusPanel) ─────────────────────

class SettingsSidebar(QTabWidget):
    """
    Right-side settings sidebar with horizontal tabs at the top,
    styled identically to the StatusPanel QTabWidget.
    """

    # Tab definitions: (label, builder_method)
    _TABS = [
        ("📋  Strategy",    "_build_strategy_tab"),
        ("⏱  Timeframes",   "_build_timeframe_tab"),
        ("📊  Instrument",  "_build_instrument_tab"),
        ("🛡  Risk",        "_build_risk_tab"),
        ("💰  Costs",       "_build_cost_tab"),
        ("⚙  Execution",   "_build_execution_tab"),
    ]

    def __init__(self, window_ref, parent=None):
        super().__init__(parent)
        self._win = window_ref      # BacktestWindow reference
        self.setTabPosition(QTabWidget.North)
        self.setDocumentMode(True)
        self.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {BORDER};
                background: {SURFACE};
                border-radius: 0 4px 4px 4px;
            }}
            QTabBar::tab {{
                background: #21262d;
                color: {SUBTEXT};
                border: 1px solid {BORDER};
                border-bottom: none;
                border-radius: 4px 4px 0 0;
                padding: 7px 10px;
                font-size: 14px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background: {SURFACE};
                color: {TEXT};
                border-bottom: 2px solid {INFO};
            }}
            QTabBar::tab:hover:!selected {{
                background: {SURFACE2};
            }}
        """)
        for label, method in self._TABS:
            self.addTab(getattr(self, method)(), label)

    # ── Tab builders ───────────────────────────────────────────────────────

    def _build_strategy_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        g = _card("Active Strategy")
        gl = QVBoxLayout(g)

        self.strategy_combo = QComboBox()
        self.strategy_combo.setMinimumHeight(28)
        gl.addWidget(self.strategy_combo)

        refresh_btn = QPushButton("🔄  Refresh List")
        refresh_btn.clicked.connect(lambda: self._win._load_strategies())
        gl.addWidget(refresh_btn)

        self.strategy_info = QLabel("")
        self.strategy_info.setStyleSheet(f"color:{SUBTEXT}; font-size:13px; padding:4px;")
        self.strategy_info.setWordWrap(True)
        gl.addWidget(self.strategy_info)
        lay.addWidget(g)

        g2 = _card("Strategy Stats", SUBTEXT)
        g2l = QFormLayout(g2)
        g2l.setSpacing(6)
        self.rule_count_lbl = _label("Rules: 0", color=SUBTEXT, size=13)
        self.min_conf_lbl   = _label("Min Confidence: —", color=SUBTEXT, size=13)
        self.enabled_grp_lbl= _label("Enabled Groups: —", color=SUBTEXT, size=13)
        g2l.addRow(self.rule_count_lbl)
        g2l.addRow(self.min_conf_lbl)
        g2l.addRow(self.enabled_grp_lbl)
        lay.addWidget(g2)

        lay.addStretch()
        return tab

    def _build_timeframe_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # Note: candle data is always fetched at 1-minute resolution from the
        # broker and resampled in-process — there is no "base interval" to select.

        g_tf = _card("Analysis Timeframes", PURPLE)
        gl_tf = QVBoxLayout(g_tf)
        gl_tf.addWidget(_label("Select timeframes to analyse:", size=13))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        tf_w = QWidget()
        tf_lay = QVBoxLayout(tf_w)
        tf_lay.setContentsMargins(0, 0, 0, 0)
        tf_lay.setSpacing(5)

        self.timeframe_checkboxes: Dict[str, QCheckBox] = {}
        categories = [
            ("Short Term (1–5m)",    ["1m", "2m", "3m", "5m"]),
            ("Medium Term (10–30m)", ["10m", "15m", "30m"]),
            ("Long Term (60–240m)",  ["60m", "120m", "240m"]),
        ]
        for cat, tfs in categories:
            lbl = _label(cat, color=INFO, size=13)
            tf_lay.addWidget(lbl)
            for tf in tfs:
                cb = QCheckBox(tf)
                cb.setChecked(tf == "5m")
                self.timeframe_checkboxes[tf] = cb
                tf_lay.addWidget(cb)
            tf_lay.addSpacing(4)

        scroll.setWidget(tf_w)
        gl_tf.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        sel_all = QPushButton("Select All")
        sel_all.clicked.connect(lambda: self._set_all_tfs(True))
        des_all = QPushButton("Deselect All")
        des_all.clicked.connect(lambda: self._set_all_tfs(False))
        btn_row.addWidget(sel_all)
        btn_row.addWidget(des_all)
        gl_tf.addLayout(btn_row)
        lay.addWidget(g_tf, 1)
        return tab

    def _build_instrument_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        g = _card("Instrument", ORANGE)
        gl = QFormLayout(g)
        gl.setSpacing(8)
        gl.setLabelAlignment(Qt.AlignRight)

        self.derivative = QComboBox()
        self.derivative.addItems(["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"])
        gl.addRow("Derivative:", self.derivative)

        self.expiry_type = QComboBox()
        self.expiry_type.addItems(["weekly", "monthly"])
        gl.addRow("Expiry:", self.expiry_type)

        self.lot_size = QSpinBox()
        self.lot_size.setRange(1, 1800)
        self.lot_size.setValue(50)
        gl.addRow("Lot Size:", self.lot_size)

        self.num_lots = QSpinBox()
        self.num_lots.setRange(1, 50)
        self.num_lots.setValue(1)
        gl.addRow("# Lots:", self.num_lots)
        lay.addWidget(g)

        g2 = _card("Date Range")
        g2l = QFormLayout(g2)
        g2l.setSpacing(8)
        g2l.setLabelAlignment(Qt.AlignRight)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.setDisplayFormat("dd MMM yyyy")
        g2l.addRow("From:", self.date_from)

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate().addDays(-1))
        self.date_to.setDisplayFormat("dd MMM yyyy")
        g2l.addRow("To:", self.date_to)
        lay.addWidget(g2)

        lay.addStretch()
        return tab

    def _build_risk_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        g = _card("Take Profit / Stop Loss", WARN)
        gl = QFormLayout(g)
        gl.setSpacing(8)
        gl.setLabelAlignment(Qt.AlignRight)

        self.use_tp = QCheckBox("Enable Take Profit")
        self.use_tp.setChecked(True)
        gl.addRow("", self.use_tp)

        self.tp_pct = QDoubleSpinBox()
        self.tp_pct.setRange(0, 500)
        self.tp_pct.setValue(30)
        self.tp_pct.setSuffix(" %")
        self.tp_pct.setDecimals(1)
        gl.addRow("TP %:", self.tp_pct)

        self.use_sl = QCheckBox("Enable Stop Loss")
        self.use_sl.setChecked(True)
        gl.addRow("", self.use_sl)

        self.sl_pct = QDoubleSpinBox()
        self.sl_pct.setRange(0, 100)
        self.sl_pct.setValue(25)
        self.sl_pct.setSuffix(" %")
        self.sl_pct.setDecimals(1)
        gl.addRow("SL %:", self.sl_pct)
        lay.addWidget(g)

        g2 = _card("Risk Options")
        g2l = QVBoxLayout(g2)
        self.skip_sideway = QCheckBox("Skip 12:00–14:00 (sideway zone)")
        self.skip_sideway.setChecked(True)
        g2l.addWidget(self.skip_sideway)
        lay.addWidget(g2)

        lay.addStretch()
        return tab

    def _build_cost_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        g = _card("Execution Costs", "#f97583")
        gl = QFormLayout(g)
        gl.setSpacing(8)
        gl.setLabelAlignment(Qt.AlignRight)

        self.slippage = QDoubleSpinBox()
        self.slippage.setRange(0, 5)
        self.slippage.setValue(0.25)
        self.slippage.setSuffix(" %")
        self.slippage.setDecimals(2)
        gl.addRow("Slippage:", self.slippage)

        self.brokerage = QDoubleSpinBox()
        self.brokerage.setRange(0, 500)
        self.brokerage.setValue(40)
        self.brokerage.setPrefix("₹ ")
        self.brokerage.setDecimals(0)
        gl.addRow("Brokerage/Lot:", self.brokerage)
        lay.addWidget(g)

        g2 = _card("Capital")
        g2l = QFormLayout(g2)
        g2l.setSpacing(8)
        g2l.setLabelAlignment(Qt.AlignRight)
        self.capital = QDoubleSpinBox()
        self.capital.setRange(10_000, 100_000_000)
        self.capital.setValue(100_000)
        self.capital.setPrefix("₹ ")
        self.capital.setDecimals(0)
        self.capital.setSingleStep(10_000)
        g2l.addRow("Initial Capital:", self.capital)
        lay.addWidget(g2)

        lay.addStretch()
        return tab

    def _build_execution_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        g = _card("Execution Options", ACCENT)
        gl = QVBoxLayout(g)

        gl.addWidget(_label("Execution interval (minutes):", size=13))
        self.execution_interval = QComboBox()
        self.execution_interval.addItems(["1", "2", "3", "5", "10", "15", "30"])
        self.execution_interval.setCurrentText("5")
        self.execution_interval.setToolTip(
            "Candle width used for signal evaluation and trade execution.\n"
            "Data is always fetched at 1-min resolution from the broker\n"
            "and resampled to this interval — no separate broker call needed."
        )
        gl.addWidget(self.execution_interval)

        self.auto_export = QCheckBox("Auto-export analysis after run")
        self.auto_export.setChecked(False)
        gl.addWidget(self.auto_export)
        lay.addWidget(g)

        g3 = _card("Volatility Source", INFO)
        g3l = QVBoxLayout(g3)
        self.use_vix = QCheckBox("Use India VIX for option pricing")
        self.use_vix.setChecked(True)
        self.use_vix.setToolTip(
            "When checked: fetches India VIX from NSE/yfinance for Black-Scholes sigma.\n"
            "When unchecked: computes rolling historical volatility from spot candles — \n"
            "no internet fetch needed, faster startup, works fully offline."
        )
        g3l.addWidget(self.use_vix)
        hv_note = QLabel(
            "Uncheck to use rolling historical volatility (HV) computed\n"
            "from the spot candles — no VIX download required.\n"
            "HV updates every bar using the last 20 closes."
        )
        hv_note.setStyleSheet(f"color:{SUBTEXT}; font-size:12px;")
        hv_note.setWordWrap(True)
        g3l.addWidget(hv_note)
        lay.addWidget(g3)

        g2 = _card("Notes", SUBTEXT)
        g2l = QVBoxLayout(g2)
        info = QLabel(
            "• Spot data is always fetched at 1-min resolution\n"
            "  and resampled to the execution interval above\n"
            "• Analysis timeframes are independent of execution\n"
            "• Synthetic (BS) pricing used for all option bars\n"
            "  (marked ⚗ in Trade Log)\n"
            "• HV mode: no network calls, fully offline capable"
        )
        info.setStyleSheet(f"color:{SUBTEXT}; font-size:13px;")
        info.setWordWrap(True)
        g2l.addWidget(info)
        lay.addWidget(g2)

        lay.addStretch()
        return tab

    # ── Helpers ────────────────────────────────────────────────────────────

    def _set_all_tfs(self, checked: bool):
        for cb in self.timeframe_checkboxes.values():
            cb.setChecked(checked)

    def get_selected_timeframes(self) -> List[str]:
        return [tf for tf, cb in self.timeframe_checkboxes.items() if cb.isChecked()]

    def update_strategy_stats(self, strategy: Dict):
        if not strategy:
            return
        engine = strategy.get("engine", {})
        total_rules = 0
        enabled = 0
        for sig in ["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]:
            grp = engine.get(sig, {})
            total_rules += len(grp.get("rules", []))
            if grp.get("enabled", True):
                enabled += 1
        min_conf = engine.get("min_confidence", 0.6) * 100
        self.rule_count_lbl.setText(f"Rules: {total_rules}")
        self.min_conf_lbl.setText(f"Min Confidence: {min_conf:.0f}%")
        self.enabled_grp_lbl.setText(f"Enabled Groups: {enabled}/5")


# ── Stat Card ──────────────────────────────────────────────────────────────────

class _StatCard(QFrame):
    def __init__(self, label: str, value: str = "—", value_color: str = TEXT):
        super().__init__()
        self.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER};"
            f" border-radius:6px; padding:4px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)
        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(f"color:{SUBTEXT}; font-size:12px; border:none;")
        self._val = QLabel(value)
        self._val.setStyleSheet(f"color:{value_color}; font-size:18px; font-weight:bold; border:none;")
        lay.addWidget(self._lbl)
        lay.addWidget(self._val)

    def update_value(self, value: str, color: str = TEXT):
        self._val.setText(value)
        self._val.setStyleSheet(f"color:{color}; font-size:18px; font-weight:bold; border:none;")


# ── Equity Chart ───────────────────────────────────────────────────────────────

class EquityChart(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._equity_data = []
        self._use_pg = False
        self._setup()

    def _setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        try:
            import pyqtgraph as pg
            pg.setConfigOptions(antialias=True, background=BG, foreground=TEXT)
            self._pg_widget = pg.PlotWidget()
            self._pg_widget.setLabel("left", "Equity (₹)", color=SUBTEXT)
            self._pg_widget.setLabel("bottom", "Trade #", color=SUBTEXT)
            self._pg_widget.showGrid(x=True, y=True, alpha=0.15)
            layout.addWidget(self._pg_widget)
            self._use_pg = True
        except ImportError:
            self._fallback = _EquityPainter()
            layout.addWidget(self._fallback)

    def _is_synthetic(self, trade) -> bool:
        """Safely check if trade used synthetic pricing."""
        try:
            from backtest.backtest_option_pricer import PriceSource
            return (trade.entry_source == PriceSource.SYNTHETIC or
                    trade.exit_source  == PriceSource.SYNTHETIC)
        except Exception:
            try:
                return (getattr(trade.entry_source, "value", "") == "synthetic" or
                        getattr(trade.exit_source,  "value", "") == "synthetic")
            except Exception:
                return False

    def set_data(self, equity_curve, trades):
        self._equity_data = equity_curve
        synth_indices = [i for i, t in enumerate(trades) if self._is_synthetic(t)]
        if self._use_pg:
            self._draw_pg(equity_curve, trades, synth_indices)
        else:
            self._fallback.set_data(equity_curve, trades)

    def _draw_pg(self, equity_curve, trades, synth_indices):
        import pyqtgraph as pg
        pw = self._pg_widget
        pw.clear()
        if not equity_curve:
            return
        equities = [e["equity"] for e in equity_curve]
        xs = list(range(len(equities)))
        pen_clr = ACCENT if equities[-1] >= equities[0] else ERROR_C
        pen = pg.mkPen(color=pen_clr, width=2)
        curve = pw.plot(xs, equities, pen=pen, name="Equity")
        base  = pw.plot(xs, [equities[0]] * len(xs), pen=pg.mkPen(None))
        fc = QColor(pen_clr)
        fc.setAlpha(30)
        pw.addItem(pg.FillBetweenItem(curve, base, brush=fc))

        if synth_indices:
            regions = []
            start_idx = synth_indices[0]
            end_idx   = synth_indices[0]
            for idx in synth_indices[1:]:
                if idx <= end_idx + 2:
                    end_idx = idx
                else:
                    regions.append((start_idx, end_idx))
                    start_idx = end_idx = idx
            regions.append((start_idx, end_idx))

            synth_color = QColor(WARN)
            synth_color.setAlpha(35)
            synth_brush = QBrush(synth_color)

            for rs, re in regions:
                if 0 <= rs < len(xs) and 0 <= re < len(xs):
                    r = pg.LinearRegionItem(
                        values=[max(0, rs - 0.5), min(len(xs) - 1, re + 0.5)],
                        brush=synth_brush,
                    )
                    r.setMovable(False)
                    pw.addItem(r)

        for i, trade in enumerate(trades):
            y = equities[min(i, len(equities) - 1)]
            clr = CALL_CLR if getattr(trade, "direction", "") in ("CE", "CALL") else PUT_CLR
            pw.addItem(pg.ScatterPlotItem(
                [i], [y],
                symbol="t1" if getattr(trade, "net_pnl", 0) > 0 else "t",
                size=13, brush=clr, pen=pg.mkPen(None),
            ))

    def clear(self):
        if self._use_pg:
            self._pg_widget.clear()
        elif hasattr(self, "_fallback"):
            self._fallback.set_data([], [])


class _EquityPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._equity = []
        self.setMinimumHeight(200)

    def set_data(self, equity_curve, _trades):
        self._equity = [e["equity"] for e in equity_curve]
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h, pad = self.width(), self.height(), 40
        p.fillRect(0, 0, w, h, QColor(BG))
        if not self._equity or len(self._equity) < 2:
            p.setPen(QColor(SUBTEXT))
            p.drawText(0, 0, w, h, Qt.AlignCenter, "No equity data")
            return
        mn, mx = min(self._equity), max(self._equity)
        rng = mx - mn or 1
        tx = lambda i: pad + int((i / (len(self._equity) - 1)) * (w - 2 * pad))
        ty = lambda v: h - pad - int(((v - mn) / rng) * (h - 2 * pad))
        p.setPen(QPen(QColor(BORDER), 1, Qt.DashLine))
        p.drawLine(pad, ty(self._equity[0]), w - pad, ty(self._equity[0]))
        clr = QColor(ACCENT if self._equity[-1] >= self._equity[0] else ERROR_C)
        p.setPen(QPen(clr, 2))
        for i in range(1, len(self._equity)):
            p.drawLine(tx(i - 1), ty(self._equity[i - 1]), tx(i), ty(self._equity[i]))
        p.setPen(QColor(SUBTEXT))
        p.drawText(2, ty(mx) + 4, f"₹{mx:,.0f}")
        p.drawText(2, ty(mn) + 4, f"₹{mn:,.0f}")


# ── Main Backtest Window ───────────────────────────────────────────────────────

class BacktestWindow(QMainWindow):
    """
    Standalone QMainWindow for running and reviewing backtests.
    Uses state_manager to access and restore trade state.

    Layout mirrors TradingGUI:
      • Left/centre: tabbed results panel
      • Right: settings sidebar (tabbed, like StatusPanel)
      • Bottom: progress bar + Run/Stop buttons
    """

    def __init__(self, trading_app=None, strategy_manager=None, parent=None):
        super().__init__(parent)
        self._trading_app      = trading_app
        self._strategy_manager = strategy_manager or StrategyManager()
        self._thread: Optional[BacktestThread] = None
        self._result = None
        self._analysis_data: Dict[str, List[BarAnalysis]] = {}

        # Get current state snapshot for reference and restoration
        self._pre_backtest_state = state_manager.save_state()
        logger.info(f"[BacktestWindow] Saved pre-backtest state: {len(self._pre_backtest_state)} fields")

        self.setWindowTitle("📊  Strategy Backtester")
        self.setMinimumSize(1500, 900)
        self.setStyleSheet(_CSS)

        self._build()
        self._load_defaults()
        self._load_strategies()

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Synthetic-price disclaimer banner ──────────────────────────
        self._synth_banner = QFrame()
        self._synth_banner.setStyleSheet(
            f"background:#2d2500; border-bottom:1px solid {WARN}; padding:6px 16px;"
        )
        sb_lay = QHBoxLayout(self._synth_banner)
        sb_lay.setContentsMargins(0, 0, 0, 0)
        self._synth_banner_lbl = QLabel()
        self._synth_banner_lbl.setStyleSheet(f"color:{WARN}; font-size:13px;")
        self._synth_banner_lbl.setWordWrap(True)
        sb_lay.addWidget(self._synth_banner_lbl)
        self._synth_banner.hide()
        root.addWidget(self._synth_banner)

        # ── Main horizontal split: Results | Sidebar ───────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {BORDER}; }}")

        # Left: Results panel
        results_panel = self._build_results_panel()
        splitter.addWidget(results_panel)

        # Right: Settings sidebar (mirrors StatusPanel position)
        self.settings_sidebar = SettingsSidebar(self)
        self.settings_sidebar.setFixedWidth(420)
        splitter.addWidget(self.settings_sidebar)

        splitter.setSizes([1100, 380])
        root.addWidget(splitter, 1)

        # ── Bottom bar: progress + buttons ─────────────────────────────
        bottom = self._build_bottom_bar()
        root.addWidget(bottom)

        # Wire strategy combo change
        self.settings_sidebar.strategy_combo.currentIndexChanged.connect(
            self._update_strategy_info
        )

    def _build_results_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        lay.addWidget(self._tabs, 1)

        self._tabs.addTab(self._build_overview_tab(),       "📈  Overview")
        self._tabs.addTab(self._build_trade_log_tab(),      "📋  Trade Log")
        self._analysis_tab = MultiTimeframeAnalysisTab()
        self._tabs.addTab(self._analysis_tab,               "🔬  Strategy Analysis")
        self._tabs.addTab(self._build_chart_tab(),          "📉  Equity Curve")
        self._debug_tab = CandleDebugTab(parent=self)
        self._tabs.addTab(self._debug_tab, "🔍 Candle Debug")
        self._help_tab = BacktestHelpTab(parent=self)
        self._tabs.addTab(self._help_tab, "❓ Help")

        return panel

    def _build_overview_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(14)

        # Stat cards grid (4 columns)
        cards_w = QWidget()
        cards_lay = QGridLayout(cards_w)
        cards_lay.setSpacing(10)

        self._cards = {}
        card_defs = [
            ("net_pnl",      "Net P&L",           "—", TEXT),
            ("total_trades", "Total Trades",       "—", TEXT),
            ("win_rate",     "Win Rate",           "—", TEXT),
            ("profit_factor","Profit Factor",      "—", TEXT),
            ("best_trade",   "Best Trade",         "—", ACCENT),
            ("worst_trade",  "Worst Trade",        "—", ERROR_C),
            ("avg_pnl",      "Avg Net P&L/Trade",  "—", TEXT),
            ("max_dd",       "Max Drawdown",       "—", WARN),
            ("sharpe",       "Sharpe Ratio",       "—", INFO),
            ("winners",      "Winners",            "—", ACCENT),
            ("losers",       "Losers",             "—", ERROR_C),
            ("data_quality", "Data Source",        "—", TEXT),
        ]
        for n, (key, lbl, val, clr) in enumerate(card_defs):
            card = _StatCard(lbl, val, clr)
            self._cards[key] = card
            cards_lay.addWidget(card, n // 4, n % 4)

        lay.addWidget(cards_w)

        self._timeframe_info = _label("", color=INFO, size=14)
        lay.addWidget(self._timeframe_info)

        self._cfg_summary = _label(
            "No results yet — configure settings on the right and press ▶ Run.",
            color=SUBTEXT, size=13
        )
        self._cfg_summary.setWordWrap(True)
        lay.addWidget(self._cfg_summary)

        lay.addStretch()
        return w

    def _build_trade_log_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        legend = QHBoxLayout()
        for sym, lbl, clr in [
            ("⚗", "Synthetic (Black-Scholes) price", WARN),
            ("✓", "Real broker data",                 ACCENT),
        ]:
            legend.addWidget(_label(f"{sym}  {lbl}", color=clr, size=13))
        legend.addStretch()
        lay.addLayout(legend)

        cols = [
            "#", "Dir", "Entry Time", "Exit Time",
            "Spot In", "Spot Out", "Strike",
            "Opt Entry", "Opt Exit", "Lots",
            "Gross P&L", "Net P&L", "Exit", "Signal", "Src"
        ]
        self._trade_table = QTableWidget(0, len(cols))
        self._trade_table.setHorizontalHeaderLabels(cols)
        self._trade_table.setAlternatingRowColors(True)
        self._trade_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._trade_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._trade_table.setSortingEnabled(True)
        hdr = self._trade_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(True)
        lay.addWidget(self._trade_table, 1)
        return w

    def _build_chart_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._equity_chart = EquityChart()
        self._equity_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self._equity_chart, 1)
        note = _label(
            "⚗ Amber-shaded bars = Black-Scholes synthetic pricing (real option data unavailable).",
            color=WARN, size=13
        )
        lay.addWidget(note)
        return w

    def _build_bottom_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(64)
        bar.setStyleSheet(f"background:{SURFACE}; border-top:1px solid {BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)

        # Progress section
        prog_col = QVBoxLayout()
        prog_col.setSpacing(2)

        self._status_lbl = _label("Ready", color=SUBTEXT, size=13)
        prog_col.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        prog_col.addWidget(self._progress)

        lay.addLayout(prog_col, 1)

        # Buttons
        self.run_btn = QPushButton("▶  Run Backtest")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.setFixedHeight(42)
        self.run_btn.setMinimumWidth(160)
        self.run_btn.clicked.connect(self._on_run)
        lay.addWidget(self.run_btn)

        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setFixedHeight(42)
        self.stop_btn.setMinimumWidth(100)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        lay.addWidget(self.stop_btn)

        return bar

    # ── Strategy management ────────────────────────────────────────────────────

    def _load_strategies(self):
        combo = self.settings_sidebar.strategy_combo
        combo.blockSignals(True)
        combo.clear()
        try:
            strategies  = self._strategy_manager.list_strategies()
            active_slug = self._strategy_manager.get_active_slug()
            for s in strategies:
                slug = s.get("slug", "")
                name = s.get("name", "Unknown")
                prefix = "⚡ " if slug == active_slug else "   "
                combo.addItem(f"{prefix}{name}", slug)
            if combo.count():
                combo.setCurrentIndex(0)
        except Exception as e:
            logger.warning(f"[BacktestWindow._load_strategies] {e}")
        combo.blockSignals(False)
        self._update_strategy_info()

    def _update_strategy_info(self):
        combo = self.settings_sidebar.strategy_combo
        slug  = combo.currentData()
        if not slug:
            return
        try:
            strategy = self._strategy_manager.get(slug)
            if strategy:
                engine   = strategy.get("engine", {})
                min_conf = engine.get("min_confidence", 0.6)
                desc     = strategy.get("description", "")
                info     = f"📊 {strategy.get('name', '')}\nMin Confidence: {min_conf:.0%}"
                if desc:
                    info += f"\n{desc[:120]}" + ("…" if len(desc) > 120 else "")
                self.settings_sidebar.strategy_info.setText(info)
                self.settings_sidebar.update_strategy_stats(strategy)
        except Exception as e:
            logger.debug(f"[BacktestWindow._update_strategy_info] {e}")

    # ── Load defaults from live config ────────────────────────────────────────

    def _load_defaults(self):
        try:
            sb = self.settings_sidebar
            if self._trading_app and hasattr(self._trading_app, "trade_config"):
                tc = self._trading_app.trade_config
                if getattr(tc, "derivative", None):
                    idx = sb.derivative.findText(tc.derivative.upper())
                    if idx >= 0:
                        sb.derivative.setCurrentIndex(idx)
                if getattr(tc, "lot_size", None):
                    sb.lot_size.setValue(int(tc.lot_size))
                if getattr(tc, "history_interval", None):
                    idx = sb.execution_interval.findText(str(tc.history_interval).replace("m", ""))
                    if idx >= 0:
                        sb.execution_interval.setCurrentIndex(idx)
            if self._trading_app and hasattr(self._trading_app, "profit_loss_config"):
                pl = self._trading_app.profit_loss_config
                if getattr(pl, "tp_percentage", None):
                    sb.tp_pct.setValue(float(pl.tp_percentage))
                if getattr(pl, "stoploss_percentage", None):
                    sb.sl_pct.setValue(float(pl.stoploss_percentage))
        except Exception as e:
            logger.debug(f"[BacktestWindow._load_defaults] {e}")

    # ── Run / Stop ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_run(self):
        """Start the backtest thread."""
        if self._thread and self._thread.isRunning():
            return

        broker = self._get_broker()
        if broker is None:
            QMessageBox.warning(
                self, "No Broker",
                "Trading app / broker not initialised.\n\n"
                "Please connect to a broker first, then open the backtester.",
            )
            return

        combo         = self.settings_sidebar.strategy_combo
        strategy_slug = combo.currentData()
        if not strategy_slug:
            QMessageBox.warning(self, "No Strategy", "Please select a strategy.")
            return

        strategy = self._strategy_manager.get(strategy_slug)
        if not strategy:
            QMessageBox.warning(self, "Invalid Strategy", "Selected strategy not found.")
            return

        selected_tfs = self.settings_sidebar.get_selected_timeframes()
        if not selected_tfs:
            reply = QMessageBox.question(
                self, "No Timeframes Selected",
                "No analysis timeframes selected. Run backtest anyway?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        sb     = self.settings_sidebar
        d_from = sb.date_from.date()
        d_to   = sb.date_to.date()

        start = _qdate_to_datetime(d_from, end_of_day=False)
        end   = _qdate_to_datetime(d_to,   end_of_day=True)

        cfg = BacktestConfig(
            start_date          = start,
            end_date            = end,
            derivative          = sb.derivative.currentText(),
            expiry_type         = sb.expiry_type.currentText(),
            lot_size            = sb.lot_size.value(),
            num_lots            = sb.num_lots.value(),
            tp_pct              = (sb.tp_pct.value() / 100) if sb.use_tp.isChecked() else None,
            sl_pct              = (sb.sl_pct.value() / 100) if sb.use_sl.isChecked() else None,
            slippage_pct        = sb.slippage.value() / 100,
            brokerage_per_lot   = sb.brokerage.value(),
            capital             = sb.capital.value(),
            execution_interval_minutes = int(sb.execution_interval.currentText()),
            sideway_zone_skip   = sb.skip_sideway.isChecked(),
            use_vix             = sb.use_vix.isChecked(),
            strategy_slug       = strategy_slug,
            signal_engine_cfg   = strategy.get("engine", {}),
            debug_candles       = True,   # collect per-candle data for Strategy Analysis tab
        )

        # Always include the execution interval in analysis
        exec_tf = f"{int(sb.execution_interval.currentText())}m"
        if exec_tf not in selected_tfs:
            selected_tfs = [exec_tf] + selected_tfs

        # Store for later
        self._selected_analysis_tfs = selected_tfs

        self._reset_results()
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._progress.setValue(0)
        self._status_lbl.setText("Starting backtest…")
        self._tabs.setCurrentIndex(0)

        if selected_tfs:
            self._timeframe_info.setText(f"Analysing timeframes: {', '.join(selected_tfs)}")
        else:
            self._timeframe_info.setText("No analysis timeframes selected")

        # Save current state before backtest (refresh snapshot)
        self._pre_backtest_state = state_manager.save_state()
        logger.debug(f"[BacktestWindow] Saved pre-backtest state with {len(self._pre_backtest_state)} fields")

        self._thread = BacktestThread(broker, cfg)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_finished)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    @pyqtSlot()
    def _on_stop(self):
        if self._thread:
            self._thread.stop()
        self.stop_btn.setEnabled(False)
        self._status_lbl.setText("Stopping…")

    def _get_broker(self):
        try:
            if self._trading_app and hasattr(self._trading_app, "broker"):
                return self._trading_app.broker
        except Exception:
            pass
        return None

    # ── Thread signals ─────────────────────────────────────────────────────────

    @pyqtSlot(float, str)
    def _on_progress(self, pct: float, msg: str):
        self._progress.setValue(int(pct))
        self._status_lbl.setText(msg)

    @pyqtSlot(object)
    def _on_finished(self, result):
        """Handle backtest completion."""
        self._result = result
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._progress.setValue(100)

        if result.error_msg:
            self._status_lbl.setText(f"⚠  {result.error_msg}")
            QMessageBox.warning(self, "Backtest Error", result.error_msg)

            # Restore original state on error
            state_manager.restore_state(self._pre_backtest_state)
            return

        self._status_lbl.setText(
            f"✓  Done — {result.total_trades} trades  |  "
            f"Net P&L ₹{result.total_net_pnl:+,.0f}  |  "
            f"Win Rate {result.win_rate:.1f}%"
        )
        self._populate_results(result)

        # Auto-export analysis
        if (self.settings_sidebar.auto_export.isChecked()
                and hasattr(result, "analysis_data")
                and result.analysis_data):
            self._export_analysis()

        # FIX: Load debug entries from the saved JSON file
        if hasattr(result, 'debug_log_path') and result.debug_log_path:
            try:
                import json
                import os

                if os.path.exists(result.debug_log_path):
                    with open(result.debug_log_path, 'r', encoding='utf-8') as f:
                        debug_data = json.load(f)

                    # Extract candles from the debug data
                    candles = debug_data.get('candles', [])

                    if candles:
                        self._debug_tab.load(candles)
                        logger.info(f"✅ Loaded {len(candles)} debug entries from {result.debug_log_path}")

                        # Also update the status label
                        self._status_lbl.setText(
                            f"✓  Done — {result.total_trades} trades  |  "
                            f"Net P&L ₹{result.total_net_pnl:+,.0f}  |  "
                            f"Win Rate {result.win_rate:.1f}%  |  "
                            f"Debug: {len(candles)} candles"
                        )
                    else:
                        logger.warning("Debug file contains no candles")
                        self._debug_tab.load([])
                else:
                    logger.warning(f"Debug file not found: {result.debug_log_path}")
                    self._debug_tab.load([])

            except Exception as e:
                logger.error(f"Failed to load debug file: {e}", exc_info=True)
                self._debug_tab.load([])
        else:
            logger.warning("No debug_log_path in result")
            self._debug_tab.load([])

        # State is automatically restored by BacktestThread.finished signal

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._status_lbl.setText(f"Error: {msg}")
        QMessageBox.critical(self, "Backtest Failed", msg)

        # Restore original state on error
        state_manager.restore_state(self._pre_backtest_state)

    # ── Populate results ───────────────────────────────────────────────────────

    def _reset_results(self):
        self._synth_banner.hide()
        self._equity_chart.clear()
        self._trade_table.setRowCount(0)
        for card in self._cards.values():
            card.update_value("—")
        self._analysis_data = {}
        self._analysis_tab.set_analysis_data({})

    def _populate_results(self, result: BacktestResult):
        # Synthetic banner
        total_src = result.synthetic_bars + result.real_bars
        if result.synthetic_bars > 0 and total_src:
            pct = result.synthetic_bars / total_src * 100
            self._synth_banner_lbl.setText(
                f"⚗  {result.synthetic_bars} of {total_src} trades used Black-Scholes "
                f"synthetic pricing ({pct:.0f}%) — real option history unavailable for "
                f"expired strikes. Prices approximated via India VIX. "
                f"Trades with real data are marked ✓; synthetic trades are marked ⚗ and "
                f"highlighted amber."
            )
            self._synth_banner.show()

        # Overview cards
        pnl_clr = ACCENT if result.total_net_pnl >= 0 else ERROR_C
        self._cards["net_pnl"].update_value(f"₹{result.total_net_pnl:+,.0f}", pnl_clr)
        self._cards["total_trades"].update_value(str(result.total_trades))
        wr_clr = ACCENT if result.win_rate >= 50 else WARN
        self._cards["win_rate"].update_value(f"{result.win_rate:.1f}%", wr_clr)
        pf_clr = ACCENT if result.profit_factor >= 1 else ERROR_C
        pf_txt = (f"{result.profit_factor:.2f}"
                  if result.profit_factor != float("inf") else "∞")
        self._cards["profit_factor"].update_value(pf_txt, pf_clr)
        self._cards["best_trade"].update_value(f"₹{result.best_trade:+,.0f}", ACCENT)
        self._cards["worst_trade"].update_value(f"₹{result.worst_trade:+,.0f}", ERROR_C)
        avg_clr = ACCENT if result.avg_net_pnl >= 0 else ERROR_C
        self._cards["avg_pnl"].update_value(f"₹{result.avg_net_pnl:+,.0f}", avg_clr)
        self._cards["max_dd"].update_value(f"₹{result.max_drawdown:,.0f}", WARN)
        sh_clr = ACCENT if result.sharpe >= 1 else (WARN if result.sharpe >= 0 else ERROR_C)
        self._cards["sharpe"].update_value(f"{result.sharpe:.2f}", sh_clr)
        self._cards["winners"].update_value(str(result.winners), ACCENT)
        self._cards["losers"].update_value(str(result.losers), ERROR_C)
        if total_src:
            real_pct = result.real_bars / total_src * 100
            dq_clr = ACCENT if real_pct >= 80 else (WARN if real_pct >= 40 else ERROR_C)
            dq_lbl = (f"{result.real_bars}R / {result.synthetic_bars}S"
                      if total_src < 30
                      else f"{real_pct:.0f}% real data")
        else:
            dq_lbl, dq_clr = "N/A", SUBTEXT
        self._cards["data_quality"].update_value(dq_lbl, dq_clr)

        cfg = result.config
        self._cfg_summary.setText(
            f"Derivative: {cfg.derivative}  |  Expiry: {cfg.expiry_type}  |  "
            f"Lot Size: {cfg.lot_size}  |  Lots: {cfg.num_lots}  |  "
            f"Base Interval: {cfg.execution_interval_minutes}m  |  "
            f"Capital: ₹{cfg.capital:,.0f}  |  "
            f"Slippage: {cfg.slippage_pct * 100:.2f}%  |  "
            f"TP: {'off' if not cfg.tp_pct else f'{cfg.tp_pct * 100:.0f}%'}  |  "
            f"SL: {'off' if not cfg.sl_pct else f'{cfg.sl_pct * 100:.0f}%'}"
        )

        # Trade log
        self._trade_table.setSortingEnabled(False)
        self._trade_table.setRowCount(len(result.trades))
        for row, t in enumerate(result.trades):
            is_synth = self._equity_chart._is_synthetic(t)
            src_badge = "⚗" if is_synth else "✓"
            bg_color  = QColor(SYNTH_BG) if is_synth else QColor(REAL_BG)
            dir_clr   = CALL_CLR if getattr(t, "direction", "") in ("CE", "CALL") else PUT_CLR
            pnl_clr   = ACCENT   if t.net_pnl >= 0 else ERROR_C
            cells = [
                (str(t.trade_no),                                         TEXT),
                (f"{'📈 CE' if t.direction in ('CE','CALL') else '📉 PE'}", dir_clr),
                (t.entry_time.strftime("%d-%b %H:%M"),                    TEXT),
                (t.exit_time.strftime("%d-%b %H:%M"),                     TEXT),
                (f"{t.spot_entry:,.0f}",                                  TEXT),
                (f"{t.spot_exit:,.0f}",                                   TEXT),
                (f"{t.strike:,}",                                         TEXT),
                (f"₹{t.option_entry:.2f}",                               TEXT),
                (f"₹{t.option_exit:.2f}",                                TEXT),
                (str(t.lots),                                             TEXT),
                (f"₹{t.gross_pnl:+,.0f}",                               pnl_clr),
                (f"₹{t.net_pnl:+,.0f}",                                 pnl_clr),
                (t.exit_reason,          WARN if t.exit_reason == "SL" else TEXT),
                ((t.signal_name or "—")[:20],                            SUBTEXT),
                (src_badge,              WARN if is_synth else ACCENT),
            ]
            for col, (val, clr) in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setForeground(QBrush(QColor(clr)))
                item.setBackground(QBrush(bg_color))
                item.setTextAlignment(Qt.AlignCenter)
                self._trade_table.setItem(row, col, item)
        self._trade_table.setSortingEnabled(True)

        # Equity chart
        self._equity_chart.set_data(result.equity_curve, result.trades)

        # Analysis tab — build from candle debug log
        analysis_data = self._build_analysis_data(result)
        if analysis_data:
            self._analysis_data = analysis_data
            self._analysis_tab.set_analysis_data(analysis_data)

    # ── Analysis data builder ──────────────────────────────────────────────────

    def _build_analysis_data(self, result: BacktestResult) -> Dict[str, List[BarAnalysis]]:
        """
        Build analysis data for the Strategy Analysis tab.

        Priority order:
          1. Candle debug log (result.debug_log_path) — richest: every bar with
             full indicator values, per-group confidence, and per-rule pass/fail.
          2. Trade list fallback — one BarAnalysis per trade entry.
        """
        # ── 1. Try candle debug JSON ───────────────────────────────────────────
        debug_path = getattr(result, "debug_log_path", None)
        if debug_path:
            try:
                data = self._build_analysis_from_debug_log(debug_path, result)
                if data:
                    logger.info(
                        f"[BacktestWindow] Strategy Analysis: loaded {sum(len(v) for v in data.values())} "
                        f"bars from debug log across {len(data)} timeframe(s)"
                    )
                    return data
            except Exception as e:
                logger.warning(f"[BacktestWindow._build_analysis_data] debug log load failed: {e}")

        # ── 2. Fallback: build from trade list ─────────────────────────────────
        return self._build_analysis_from_trades(result)

    def _build_analysis_from_debug_log(
        self, path: str, result: BacktestResult
    ) -> Dict[str, List[BarAnalysis]]:
        """Parse the per-candle JSON debug log into BarAnalysis objects."""
        import json

        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        candles = payload.get("candles", [])
        if not candles:
            return {}

        tf = f"{result.config.execution_interval_minutes}m"
        bars: List[BarAnalysis] = []

        for c in candles:
            # Skip skipped bars (sideway/warmup/market-closed)
            if c.get("skip_reason"):
                continue

            try:
                ts = datetime.strptime(c["time"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

            spot = c.get("spot", {})
            close = spot.get("close", 0.0) or 0.0

            # Flatten indicator values
            raw_ind = c.get("indicators", {})
            ind_values: Dict[str, Dict[str, float]] = {}
            for k, v in raw_ind.items():
                if isinstance(v, dict):
                    ind_values[k] = {"last": v.get("last", 0.0), "prev": v.get("prev", 0.0)}
                elif isinstance(v, (int, float)):
                    ind_values[k] = {"last": float(v), "prev": float(v)}

            # Confidence map
            confidence: Dict[str, float] = {}
            rule_results: Dict[str, List[Dict]] = {}
            for grp, grp_data in c.get("signal_groups", {}).items():
                confidence[grp] = grp_data.get("confidence", 0.0)
                rule_results[grp] = [
                    {
                        "rule":   r.get("rule", ""),
                        "result": r.get("passed", False),
                        "weight": r.get("weight", 1.0),
                        "lhs_value": r.get("lhs"),
                        "rhs_value": r.get("rhs"),
                        "detail":    r.get("detail", ""),
                        "error":     r.get("error"),
                    }
                    for r in grp_data.get("rules", [])
                ]

            signal = c.get("resolved_signal", "WAIT") or "WAIT"

            bars.append(BarAnalysis(
                timestamp=ts,
                spot_price=close,
                signal=signal,
                confidence=confidence,
                rule_results=rule_results,
                indicator_values=ind_values,
                timeframe=tf,
            ))

        if not bars:
            return {}

        # Put all bars under the execution timeframe.
        selected = getattr(self, "_selected_analysis_tfs", [tf])
        data: Dict[str, List[BarAnalysis]] = {}
        for selected_tf in selected:
            relabelled = []
            for b in bars:
                relabelled.append(BarAnalysis(
                    timestamp=b.timestamp,
                    spot_price=b.spot_price,
                    signal=b.signal,
                    confidence=b.confidence,
                    rule_results=b.rule_results,
                    indicator_values=b.indicator_values,
                    timeframe=selected_tf,
                ))
            data[selected_tf] = relabelled
        return data

    def _build_analysis_from_trades(self, result: BacktestResult) -> Dict[str, List[BarAnalysis]]:
        """
        Fallback: build one BarAnalysis per trade entry from the trade list.
        """
        if not result.trades:
            return {}

        tf = f"{result.config.execution_interval_minutes}m"
        bars: List[BarAnalysis] = []

        for trade in result.trades:
            signal = trade.signal_name or "BUY_CALL"
            pseudo_conf = 0.7 if trade.net_pnl > 0 else 0.45
            confidence = {signal: pseudo_conf}

            bars.append(BarAnalysis(
                timestamp=trade.entry_time,
                spot_price=trade.spot_entry,
                signal=signal,
                confidence=confidence,
                rule_results={},
                indicator_values={},
                timeframe=tf,
            ))

        selected = getattr(self, "_selected_analysis_tfs", [tf])
        if not selected:
            selected = [tf]

        data: Dict[str, List[BarAnalysis]] = {}
        for selected_tf in selected:
            data[selected_tf] = [
                BarAnalysis(
                    timestamp=b.timestamp,
                    spot_price=b.spot_price,
                    signal=b.signal,
                    confidence=b.confidence,
                    rule_results=b.rule_results,
                    indicator_values=b.indicator_values,
                    timeframe=selected_tf,
                )
                for b in bars
            ]

        logger.info(
            f"[BacktestWindow] Strategy Analysis: trade-list fallback — "
            f"{len(bars)} entries. Enable debug_candles=True for full per-bar data."
        )
        return data

    # ── Export helpers ─────────────────────────────────────────────────────────

    def _export_analysis(self):
        if not self._analysis_data:
            QMessageBox.warning(self, "No Data", "No analysis data to export.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if not directory:
            return
        strategy_name = (self.settings_sidebar.strategy_combo.currentText()
                         .replace("⚡", "").replace("   ", "").strip())
        n = 0
        for tf, data in self._analysis_data.items():
            if data:
                fp = os.path.join(
                    directory,
                    f"{strategy_name}_{tf}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                )
                try:
                    pd.DataFrame([b.to_dict() for b in data]).to_csv(fp, index=False)
                    n += 1
                except Exception as e:
                    logger.error(f"Export {tf}: {e}")
        QMessageBox.information(self, "Export Complete", f"Exported {n} file(s) to:\n{directory}")

    def closeEvent(self, event):
        """Handle window close - ensure state is restored."""
        try:
            logger.info("[BacktestWindow] Closing, restoring original state")

            # Restore original state if needed
            if hasattr(self, '_pre_backtest_state') and self._pre_backtest_state:
                state_manager.restore_state(self._pre_backtest_state)

            # Stop thread if running
            if self._thread and self._thread.isRunning():
                self._thread.stop()
                if not self._thread.wait(2000):
                    logger.warning("[BacktestWindow] Thread did not stop gracefully")

            event.accept()
        except Exception as e:
            logger.error(f"[BacktestWindow.closeEvent] {e}", exc_info=True)
            event.accept()