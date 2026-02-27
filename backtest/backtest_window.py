"""
backtest/backtest_window.py
============================
Full backtesting window: strategy config, run control, live progress,
equity-curve chart, trade log table, and summary statistics panel.

Opened from TradingGUI via:
    from backtest.backtest_window import BacktestWindow
    win = BacktestWindow(parent=self, trading_app=self.trading_app)
    win.show()

Visual cues
-----------
• SYNTHETIC price rows   → amber background in trade table + ⚗ badge
• REAL price rows        → no special tinting
• A banner is shown at the top of results when ANY synthetic bars exist,
  explaining that Black-Scholes approximations were used because the broker
  did not provide historical option data for those strikes/expiries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QColor, QFont, QBrush
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)
from PyQt5.QtCore import QDate

logger = logging.getLogger(__name__)

# ── Palette (matches the dark TradingGUI theme) ────────────────────────────────
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
CALL_CLR  = "#3fb950"   # green for calls
PUT_CLR   = "#f85149"   # red for puts
SYNTH_BG  = "#2d2a1a"   # amber tint for synthetic rows
REAL_BG   = "#0d1117"

_CSS = f"""
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: 'Segoe UI', 'SF Pro Display', 'Ubuntu', sans-serif;
    font-size: 11px;
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 12px;
    font-weight: bold;
    color: {SUBTEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}
QLabel {{ color: {TEXT}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    color: {TEXT};
    min-height: 22px;
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
    font-size: 12px;
    padding: 8px 24px;
}}
QPushButton#runBtn:hover {{ background: {ACCENT_H}; }}
QPushButton#stopBtn {{
    background: {ERROR_C};
    border-color: {ERROR_C};
    color: #fff;
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
    padding: 5px 8px;
    font-weight: bold;
    font-size: 10px;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {BG};
}}
QTabBar::tab {{
    background: {SURFACE};
    color: {SUBTEXT};
    padding: 6px 16px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-radius: 4px 4px 0 0;
}}
QTabBar::tab:selected {{
    background: {BG};
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
}}
QProgressBar {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    color: {TEXT};
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}
QScrollBar:vertical {{
    background: {SURFACE};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 20px;
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
"""


def _label(text, bold=False, color=TEXT, size=11):
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


def _card(title: str) -> QGroupBox:
    g = QGroupBox(title)
    return g


# ══════════════════════════════════════════════════════════════════════════════
#  Lightweight canvas-less equity chart using QLabel art (fallback)
#  or pyqtgraph if available
# ══════════════════════════════════════════════════════════════════════════════

class EquityChart(QWidget):
    """
    Equity curve chart.
    Uses pyqtgraph if available, falls back to a pure-Qt painter implementation.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._equity_data: List[dict] = []
        self._synth_regions: List[tuple] = []   # (x_start, x_end) index pairs
        self._use_pg = False
        self._plot   = None
        self._setup()

    def _setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        try:
            import pyqtgraph as pg
            pg.setConfigOptions(antialias=True, background=BG, foreground=TEXT)
            self._pg_widget = pg.PlotWidget()
            self._pg_widget.setLabel("left",  "Equity (₹)", color=SUBTEXT)
            self._pg_widget.setLabel("bottom", "Trade #",   color=SUBTEXT)
            self._pg_widget.showGrid(x=True, y=True, alpha=0.15)
            self._pg_widget.getAxis("left").setPen(BORDER)
            self._pg_widget.getAxis("bottom").setPen(BORDER)
            layout.addWidget(self._pg_widget)
            self._use_pg = True
        except ImportError:
            self._fallback = _EquityPainter()
            layout.addWidget(self._fallback)

    def set_data(self, equity_curve: List[dict], trades):
        self._equity_data   = equity_curve
        self._synth_regions = [
            i for i, t in enumerate(trades)
            if t.entry_source.value == "synthetic" or t.exit_source.value == "synthetic"
        ]

        if self._use_pg:
            self._draw_pg(equity_curve, trades)
        else:
            self._fallback.set_data(equity_curve, trades)

    def _draw_pg(self, equity_curve, trades):
        import pyqtgraph as pg
        pw = self._pg_widget
        pw.clear()

        if not equity_curve:
            return

        equities = [e["equity"] for e in equity_curve]
        xs = list(range(len(equities)))

        # Equity line — colour based on positive/negative vs start
        start = equities[0]
        pen_clr = ACCENT if equities[-1] >= start else ERROR_C
        pen = pg.mkPen(color=pen_clr, width=2)
        pw.plot(xs, equities, pen=pen, name="Equity")

        # Fill under curve
        fill_clr = QColor(ACCENT if equities[-1] >= start else ERROR_C)
        fill_clr.setAlpha(30)
        fill = pg.FillBetweenItem(
            pw.plot(xs, equities, pen=pen),
            pw.plot(xs, [start] * len(xs), pen=pg.mkPen(None)),
            brush=fill_clr,
        )
        pw.addItem(fill)

        # Shade synthetic-priced trade regions in amber
        for idx in self._synth_regions:
            if 0 <= idx < len(xs):
                region = pg.LinearRegionItem(
                    values=[max(0, idx - 0.5), min(len(xs) - 1, idx + 0.5)],
                    brush=QColor(WARN)
                )
                region.brush.setAlpha(40)
                region.setMovable(False)
                pw.addItem(region)

        # Draw trade markers
        for i, trade in enumerate(trades):
            y_entry = equities[min(i, len(equities) - 1)]
            dot_clr = CALL_CLR if trade.direction == "CE" else PUT_CLR
            marker = pg.ScatterPlotItem(
                [i], [y_entry],
                symbol="t1" if trade.net_pnl > 0 else "t",
                size=10, brush=dot_clr, pen=pg.mkPen(None),
            )
            pw.addItem(marker)

    def clear(self):
        if self._use_pg:
            self._pg_widget.clear()
        else:
            self._fallback.set_data([], [])


class _EquityPainter(QWidget):
    """Pure-Qt fallback equity painter (no pyqtgraph dependency)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._equity  = []
        self._trades  = []
        self._synth   = set()
        self.setMinimumHeight(200)

    def set_data(self, equity_curve, trades):
        self._equity = [e["equity"] for e in equity_curve]
        self._trades = trades
        self._synth  = {
            i for i, t in enumerate(trades)
            if t.entry_source.value == "synthetic" or t.exit_source.value == "synthetic"
        }
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QPen, QColor, QLinearGradient
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        pad  = 40

        p.fillRect(0, 0, w, h, QColor(BG))

        if not self._equity or len(self._equity) < 2:
            p.setPen(QColor(SUBTEXT))
            p.drawText(0, 0, w, h, Qt.AlignCenter, "No equity data")
            return

        mn, mx = min(self._equity), max(self._equity)
        rng    = mx - mn or 1

        def tx(i):
            return pad + int((i / (len(self._equity) - 1)) * (w - 2 * pad))

        def ty(v):
            return h - pad - int(((v - mn) / rng) * (h - 2 * pad))

        # Zero line
        z = ty(self._equity[0])
        p.setPen(QPen(QColor(BORDER), 1, Qt.DashLine))
        p.drawLine(pad, z, w - pad, z)

        # Equity path
        clr = QColor(ACCENT if self._equity[-1] >= self._equity[0] else ERROR_C)
        p.setPen(QPen(clr, 2))
        for i in range(1, len(self._equity)):
            p.drawLine(tx(i - 1), ty(self._equity[i - 1]), tx(i), ty(self._equity[i]))

        # Axis labels
        p.setPen(QColor(SUBTEXT))
        p.drawText(pad, h - 5, f"₹{self._equity[0]:,.0f}")
        p.drawText(w - pad - 60, h - 5, f"₹{self._equity[-1]:,.0f}")
        p.drawText(2, ty(mx) + 4, f"₹{mx:,.0f}")
        p.drawText(2, ty(mn) + 4, f"₹{mn:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
#  Stat card  (shows one metric with label + coloured value)
# ══════════════════════════════════════════════════════════════════════════════

class _StatCard(QFrame):
    def __init__(self, label: str, value: str = "—", value_color: str = TEXT):
        super().__init__()
        self.setStyleSheet(
            f"QFrame {{ background: {SURFACE}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 4px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(f"color: {SUBTEXT}; font-size: 10px; border: none;")
        self._val = QLabel(value)
        self._val.setStyleSheet(f"color: {value_color}; font-size: 14px; font-weight: bold; border: none;")
        lay.addWidget(self._lbl)
        lay.addWidget(self._val)

    def update_value(self, value: str, color: str = TEXT):
        self._val.setText(value)
        self._val.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold; border: none;")


# ══════════════════════════════════════════════════════════════════════════════
#  Main Backtest Window
# ══════════════════════════════════════════════════════════════════════════════

class BacktestWindow(QMainWindow):
    """
    Standalone QMainWindow for running and reviewing backtests.

    Parameters
    ----------
    trading_app   : TradingApp instance (provides broker + strategy)
    parent        : optional parent widget
    """

    def __init__(self, trading_app=None, parent=None):
        super().__init__(parent)
        self._trading_app = trading_app
        self._thread: Optional["BacktestThread"] = None
        self._result = None

        self.setWindowTitle("📊  Strategy Backtester")
        self.setMinimumSize(1280, 820)
        self.setStyleSheet(_CSS)

        self._build()
        self._load_defaults()

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel: config ────────────────────────────────────────────────
        left = self._build_config_panel()
        left.setFixedWidth(310)
        root.addWidget(left)

        # ── Right panel: results ──────────────────────────────────────────────
        right = self._build_results_panel()
        root.addWidget(right, 1)

    def _build_config_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {SURFACE}; border-right: 1px solid {BORDER};")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(14)

        # Title
        title = QLabel("⚙️  Backtest Config")
        title.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: bold;")
        lay.addWidget(title)
        lay.addWidget(_sep())

        # ── Date range ────────────────────────────────────────────────────────
        date_grp = _card("Date Range")
        dg = QGridLayout(date_grp)
        dg.setSpacing(6)

        dg.addWidget(_label("From"), 0, 0)
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addDays(-30))
        self._date_from.setDisplayFormat("dd MMM yyyy")
        dg.addWidget(self._date_from, 0, 1)

        dg.addWidget(_label("To"), 1, 0)
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate().addDays(-1))
        self._date_to.setDisplayFormat("dd MMM yyyy")
        dg.addWidget(self._date_to, 1, 1)

        lay.addWidget(date_grp)

        # ── Instrument ────────────────────────────────────────────────────────
        inst_grp = _card("Instrument")
        ig = QGridLayout(inst_grp)
        ig.setSpacing(6)

        ig.addWidget(_label("Derivative"), 0, 0)
        self._derivative = QComboBox()
        self._derivative.addItems(["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"])
        ig.addWidget(self._derivative, 0, 1)

        ig.addWidget(_label("Expiry"), 1, 0)
        self._expiry_type = QComboBox()
        self._expiry_type.addItems(["weekly", "monthly"])
        ig.addWidget(self._expiry_type, 1, 1)

        ig.addWidget(_label("Lot Size"), 2, 0)
        self._lot_size = QSpinBox()
        self._lot_size.setRange(1, 1800)
        self._lot_size.setValue(50)
        ig.addWidget(self._lot_size, 2, 1)

        ig.addWidget(_label("# Lots"), 3, 0)
        self._num_lots = QSpinBox()
        self._num_lots.setRange(1, 50)
        self._num_lots.setValue(1)
        ig.addWidget(self._num_lots, 3, 1)

        ig.addWidget(_label("Interval"), 4, 0)
        self._interval = QComboBox()
        self._interval.addItems(["1", "2", "3", "5", "10", "15", "30"])
        self._interval.setCurrentText("5")
        ig.addWidget(self._interval, 4, 1)

        lay.addWidget(inst_grp)

        # ── TP / SL ───────────────────────────────────────────────────────────
        risk_grp = _card("Take-Profit / Stop-Loss")
        rg = QGridLayout(risk_grp)
        rg.setSpacing(6)

        rg.addWidget(_label("TP %"), 0, 0)
        self._tp_pct = QDoubleSpinBox()
        self._tp_pct.setRange(0, 500)
        self._tp_pct.setValue(30)
        self._tp_pct.setSuffix(" %")
        self._tp_pct.setDecimals(1)
        rg.addWidget(self._tp_pct, 0, 1)

        rg.addWidget(_label("SL %"), 1, 0)
        self._sl_pct = QDoubleSpinBox()
        self._sl_pct.setRange(0, 100)
        self._sl_pct.setValue(25)
        self._sl_pct.setSuffix(" %")
        self._sl_pct.setDecimals(1)
        rg.addWidget(self._sl_pct, 1, 1)

        self._use_tp = QCheckBox("Enable TP")
        self._use_tp.setChecked(True)
        self._use_sl = QCheckBox("Enable SL")
        self._use_sl.setChecked(True)
        rg.addWidget(self._use_tp, 2, 0)
        rg.addWidget(self._use_sl, 2, 1)

        lay.addWidget(risk_grp)

        # ── Costs ─────────────────────────────────────────────────────────────
        cost_grp = _card("Execution Costs")
        cg = QGridLayout(cost_grp)
        cg.setSpacing(6)

        cg.addWidget(_label("Slippage"), 0, 0)
        self._slippage = QDoubleSpinBox()
        self._slippage.setRange(0, 5)
        self._slippage.setValue(0.25)
        self._slippage.setSuffix(" %")
        self._slippage.setDecimals(2)
        cg.addWidget(self._slippage, 0, 1)

        cg.addWidget(_label("Brokerage / Lot"), 1, 0)
        self._brokerage = QDoubleSpinBox()
        self._brokerage.setRange(0, 500)
        self._brokerage.setValue(40)
        self._brokerage.setPrefix("₹ ")
        self._brokerage.setDecimals(0)
        cg.addWidget(self._brokerage, 1, 1)

        cg.addWidget(_label("Capital"), 2, 0)
        self._capital = QDoubleSpinBox()
        self._capital.setRange(10000, 100_000_000)
        self._capital.setValue(100_000)
        self._capital.setPrefix("₹ ")
        self._capital.setDecimals(0)
        self._capital.setSingleStep(10_000)
        cg.addWidget(self._capital, 2, 1)

        lay.addWidget(cost_grp)

        # ── Misc ──────────────────────────────────────────────────────────────
        misc_grp = _card("Options")
        mg = QVBoxLayout(misc_grp)
        self._skip_sideway = QCheckBox("Skip 12:00–14:00 (sideway zone)")
        self._skip_sideway.setChecked(True)
        mg.addWidget(self._skip_sideway)
        lay.addWidget(misc_grp)

        lay.addStretch()

        # ── Action buttons ────────────────────────────────────────────────────
        self._run_btn = QPushButton("▶  Run Backtest")
        self._run_btn.setObjectName("runBtn")
        self._run_btn.setFixedHeight(42)
        self._run_btn.clicked.connect(self._on_run)
        lay.addWidget(self._run_btn)

        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setFixedHeight(34)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        lay.addWidget(self._stop_btn)

        return panel

    def _build_results_panel(self) -> QWidget:
        panel = QWidget()
        lay   = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Progress bar + status ─────────────────────────────────────────────
        prog_bar_widget = QWidget()
        prog_bar_widget.setStyleSheet(f"background: {SURFACE}; border-bottom: 1px solid {BORDER};")
        prog_lay = QHBoxLayout(prog_bar_widget)
        prog_lay.setContentsMargins(16, 8, 16, 8)
        prog_lay.setSpacing(12)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(8)
        self._progress.setTextVisible(False)
        prog_lay.addWidget(self._progress)

        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet(f"color: {SUBTEXT}; min-width: 340px;")
        prog_lay.addWidget(self._status_lbl)

        lay.addWidget(prog_bar_widget)

        # ── Synthetic-price disclaimer banner (hidden until results arrive) ───
        self._synth_banner = QFrame()
        self._synth_banner.setStyleSheet(
            f"background: #2d2500; border-bottom: 1px solid {WARN}; padding: 6px 16px;"
        )
        sb_lay = QHBoxLayout(self._synth_banner)
        sb_lay.setContentsMargins(0, 0, 0, 0)
        self._synth_banner_lbl = QLabel()
        self._synth_banner_lbl.setStyleSheet(f"color: {WARN}; font-size: 11px;")
        self._synth_banner_lbl.setWordWrap(True)
        sb_lay.addWidget(self._synth_banner_lbl)
        self._synth_banner.hide()
        lay.addWidget(self._synth_banner)

        # ── Tab widget ────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        lay.addWidget(self._tabs, 1)

        # Tab 1: Overview / Stats
        self._tabs.addTab(self._build_overview_tab(), "📈  Overview")
        # Tab 2: Trade Log
        self._tabs.addTab(self._build_trade_log_tab(), "📋  Trade Log")
        # Tab 3: Equity Chart
        self._tabs.addTab(self._build_chart_tab(), "📉  Equity Curve")

        return panel

    def _build_overview_tab(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        # ── Stat cards grid ───────────────────────────────────────────────────
        cards_widget = QWidget()
        cards_lay    = QGridLayout(cards_widget)
        cards_lay.setSpacing(12)

        self._cards = {}
        card_defs = [
            ("net_pnl",      "Net P&L",          "—",  TEXT),
            ("total_trades", "Total Trades",      "—",  TEXT),
            ("win_rate",     "Win Rate",          "—",  TEXT),
            ("profit_factor","Profit Factor",     "—",  TEXT),
            ("best_trade",   "Best Trade",        "—",  ACCENT),
            ("worst_trade",  "Worst Trade",       "—",  ERROR_C),
            ("avg_pnl",      "Avg Net P&L/Trade", "—",  TEXT),
            ("max_dd",       "Max Drawdown",      "—",  WARN),
            ("sharpe",       "Sharpe Ratio",      "—",  INFO),
            ("winners",      "Winners",           "—",  ACCENT),
            ("losers",       "Losers",            "—",  ERROR_C),
            ("data_quality", "Data Source",       "—",  TEXT),
        ]
        for n, (key, lbl, val, clr) in enumerate(card_defs):
            card = _StatCard(lbl, val, clr)
            self._cards[key] = card
            cards_lay.addWidget(card, n // 4, n % 4)

        lay.addWidget(cards_widget)

        # ── Config summary label ──────────────────────────────────────────────
        self._cfg_summary = QLabel("No results yet — configure and run a backtest.")
        self._cfg_summary.setStyleSheet(f"color: {SUBTEXT}; font-size: 10px;")
        self._cfg_summary.setWordWrap(True)
        lay.addWidget(self._cfg_summary)

        lay.addStretch()
        return w

    def _build_trade_log_tab(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Legend
        legend_row = QHBoxLayout()
        for sym, lbl, clr in [
            ("⚗", "Synthetic (BS) price — VIX-based approx.", WARN),
            ("✓", "Real broker data",                          ACCENT),
        ]:
            leg = QLabel(f"{sym}  {lbl}")
            leg.setStyleSheet(f"color: {clr}; font-size: 10px;")
            legend_row.addWidget(leg)
        legend_row.addStretch()
        lay.addLayout(legend_row)

        # Table
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
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        self._equity_chart = EquityChart()
        self._equity_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self._equity_chart, 1)

        synth_note = QLabel(
            "⚗ Amber-shaded bars indicate trades priced via Black-Scholes (real option data unavailable)."
        )
        synth_note.setStyleSheet(f"color: {WARN}; font-size: 10px;")
        lay.addWidget(synth_note)

        return w

    # ── Defaults ───────────────────────────────────────────────────────────────

    def _load_defaults(self):
        """Pre-fill from live trading settings if trading_app is available."""
        try:
            if self._trading_app and hasattr(self._trading_app, "trade_config"):
                tc = self._trading_app.trade_config
                if hasattr(tc, "derivative") and tc.derivative:
                    idx = self._derivative.findText(tc.derivative.upper())
                    if idx >= 0:
                        self._derivative.setCurrentIndex(idx)
                if hasattr(tc, "lot_size") and tc.lot_size:
                    self._lot_size.setValue(int(tc.lot_size))
            if self._trading_app and hasattr(self._trading_app, "profit_loss_config"):
                pl = self._trading_app.profit_loss_config
                if hasattr(pl, "tp_percentage") and pl.tp_percentage:
                    self._tp_pct.setValue(float(pl.tp_percentage))
                if hasattr(pl, "stoploss_percentage") and pl.stoploss_percentage:
                    self._sl_pct.setValue(float(pl.stoploss_percentage))
        except Exception as e:
            logger.debug(f"[BacktestWindow._load_defaults] {e}")

    # ── Run / Stop ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_run(self):
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

        from backtest.backtest_engine import BacktestConfig
        from backtest.backtest_thread import BacktestThread

        # ── Collect config ─────────────────────────────────────────────────────
        d_from = self._date_from.date()
        d_to   = self._date_to.date()

        # Pull the active strategy slug from the live trading app so the
        # backtest runs the same strategy currently configured.
        strategy_slug     = None
        signal_engine_cfg = None
        try:
            if self._trading_app and hasattr(self._trading_app, "strategy_manager"):
                sm = self._trading_app.strategy_manager
                if hasattr(sm, "get_active_slug"):
                    strategy_slug = sm.get_active_slug()
                elif hasattr(sm, "get_active_engine_config"):
                    signal_engine_cfg = sm.get_active_engine_config()
            elif self._trading_app and hasattr(self._trading_app, "signal_engine"):
                # Serialise the live signal engine config directly
                se = self._trading_app.signal_engine
                if hasattr(se, "to_dict"):
                    signal_engine_cfg = se.to_dict()
        except Exception as e:
            logger.debug(f"[BacktestWindow._on_run] Could not load strategy: {e}")

        cfg = BacktestConfig(
            start_date        = datetime(d_from.year(), d_from.month(), d_from.day()),
            end_date          = datetime(d_to.year(), d_to.month(), d_to.day(), 23, 59, 59),
            derivative        = self._derivative.currentText(),
            expiry_type       = self._expiry_type.currentText(),
            lot_size          = self._lot_size.value(),
            num_lots          = self._num_lots.value(),
            tp_pct            = (self._tp_pct.value() / 100) if self._use_tp.isChecked() else None,
            sl_pct            = (self._sl_pct.value() / 100) if self._use_sl.isChecked() else None,
            slippage_pct      = self._slippage.value() / 100,
            brokerage_per_lot = self._brokerage.value(),
            capital           = self._capital.value(),
            interval_minutes  = int(self._interval.currentText()),
            sideway_zone_skip = self._skip_sideway.isChecked(),
            strategy_slug     = strategy_slug,
            signal_engine_cfg = signal_engine_cfg,
        )

        # ── Reset UI ───────────────────────────────────────────────────────────
        self._reset_results()
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress.setValue(0)
        self._status_lbl.setText("Starting…")
        self._tabs.setCurrentIndex(0)

        # ── Launch thread ──────────────────────────────────────────────────────
        self._thread = BacktestThread(broker, cfg)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_finished)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    @pyqtSlot()
    def _on_stop(self):
        if self._thread:
            self._thread.stop()
        self._stop_btn.setEnabled(False)
        self._status_lbl.setText("Stopping…")

    def _get_broker(self):
        try:
            if self._trading_app and hasattr(self._trading_app, "broker"):
                return self._trading_app.broker
        except Exception:
            pass
        return None

    # ── Signals from thread ────────────────────────────────────────────────────

    @pyqtSlot(float, str)
    def _on_progress(self, pct: float, msg: str):
        self._progress.setValue(int(pct))
        self._status_lbl.setText(msg)

    @pyqtSlot(object)
    def _on_finished(self, result):
        self._result = result
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress.setValue(100)

        if result.error_msg:
            self._status_lbl.setText(f"⚠  {result.error_msg}")
            QMessageBox.warning(self, "Backtest Error", result.error_msg)
            return

        self._status_lbl.setText(
            f"✓  Done — {result.total_trades} trades | "
            f"Net P&L ₹{result.total_net_pnl:+,.0f} | "
            f"Win Rate {result.win_rate:.1f}%"
        )
        self._populate_results(result)

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status_lbl.setText(f"Error: {msg}")
        QMessageBox.critical(self, "Backtest Failed", msg)

    # ── Populate results ───────────────────────────────────────────────────────

    def _reset_results(self):
        self._synth_banner.hide()
        self._equity_chart.clear()
        self._trade_table.setRowCount(0)
        for card in self._cards.values():
            card.update_value("—")

    def _populate_results(self, result):
        """Fill all three tabs with backtest result data."""
        from backtest.backtest_option_pricer import PriceSource

        # ── Synthetic banner ──────────────────────────────────────────────────
        if result.synthetic_bars > 0:
            total = result.synthetic_bars + result.real_bars
            pct   = result.synthetic_bars / total * 100 if total else 0
            self._synth_banner_lbl.setText(
                f"⚗  {result.synthetic_bars} of {total} trades used Black-Scholes synthetic pricing "
                f"({pct:.0f}%) because your broker does not provide historical option data for "
                f"expired strikes.  Prices are approximated using India VIX — actual volatility "
                f"may differ, especially around events (earnings, RBI, budget).  "
                f"Trades using real data are marked ✓; synthetic trades are marked ⚗ and "
                f"highlighted in amber."
            )
            self._synth_banner.show()

        # ── Overview stats ────────────────────────────────────────────────────
        pnl_clr = ACCENT if result.total_net_pnl >= 0 else ERROR_C
        self._cards["net_pnl"].update_value(f"₹{result.total_net_pnl:+,.0f}", pnl_clr)
        self._cards["total_trades"].update_value(str(result.total_trades))
        wr_clr = ACCENT if result.win_rate >= 50 else WARN
        self._cards["win_rate"].update_value(f"{result.win_rate:.1f}%", wr_clr)
        pf_clr = ACCENT if result.profit_factor >= 1 else ERROR_C
        self._cards["profit_factor"].update_value(
            f"{result.profit_factor:.2f}" if result.profit_factor != float("inf") else "∞", pf_clr
        )
        self._cards["best_trade"].update_value(f"₹{result.best_trade:+,.0f}", ACCENT)
        self._cards["worst_trade"].update_value(f"₹{result.worst_trade:+,.0f}", ERROR_C)
        avg_clr = ACCENT if result.avg_net_pnl >= 0 else ERROR_C
        self._cards["avg_pnl"].update_value(f"₹{result.avg_net_pnl:+,.0f}", avg_clr)
        self._cards["max_dd"].update_value(f"₹{result.max_drawdown:,.0f}", WARN)
        sh_clr = ACCENT if result.sharpe >= 1 else (WARN if result.sharpe >= 0 else ERROR_C)
        self._cards["sharpe"].update_value(f"{result.sharpe:.2f}", sh_clr)
        self._cards["winners"].update_value(str(result.winners), ACCENT)
        self._cards["losers"].update_value(str(result.losers), ERROR_C)
        total_data = result.synthetic_bars + result.real_bars
        if total_data:
            real_pct = result.real_bars / total_data * 100
            dq_clr = ACCENT if real_pct >= 80 else (WARN if real_pct >= 40 else ERROR_C)
            dq_label = (
                f"{result.real_bars} real / {result.synthetic_bars} synthetic"
                if total_data < 30
                else f"{real_pct:.0f}% real data"
            )
        else:
            dq_label, dq_clr = "N/A", SUBTEXT
        self._cards["data_quality"].update_value(dq_label, dq_clr)

        cfg = result.config
        self._cfg_summary.setText(
            f"Derivative: {cfg.derivative}  |  Expiry: {cfg.expiry_type}  |  "
            f"Lot Size: {cfg.lot_size}  |  Lots: {cfg.num_lots}  |  "
            f"Interval: {cfg.interval_minutes}m  |  "
            f"Capital: ₹{cfg.capital:,.0f}  |  "
            f"Slippage: {cfg.slippage_pct*100:.2f}%  |  "
            f"TP: {'off' if not cfg.tp_pct else f'{cfg.tp_pct*100:.0f}%'}  |  "
            f"SL: {'off' if not cfg.sl_pct else f'{cfg.sl_pct*100:.0f}%'}"
        )

        # ── Trade log ─────────────────────────────────────────────────────────
        self._trade_table.setSortingEnabled(False)
        self._trade_table.setRowCount(len(result.trades))
        for row, t in enumerate(result.trades):
            is_synth = (
                t.entry_source == PriceSource.SYNTHETIC or
                t.exit_source  == PriceSource.SYNTHETIC
            )
            src_badge = "⚗" if is_synth else "✓"
            bg_color  = QColor(SYNTH_BG) if is_synth else QColor(REAL_BG)

            dir_clr = CALL_CLR if t.direction == "CE" else PUT_CLR
            pnl_clr = ACCENT   if t.net_pnl >= 0     else ERROR_C

            cells = [
                (str(t.trade_no),                           TEXT),
                (f"{'📈 CE' if t.direction=='CE' else '📉 PE'}", dir_clr),
                (t.entry_time.strftime("%d-%b %H:%M"),     TEXT),
                (t.exit_time.strftime("%d-%b %H:%M"),      TEXT),
                (f"{t.spot_entry:,.0f}",                   TEXT),
                (f"{t.spot_exit:,.0f}",                    TEXT),
                (f"{t.strike:,}",                          TEXT),
                (f"₹{t.option_entry:.2f}",                 TEXT),
                (f"₹{t.option_exit:.2f}",                  TEXT),
                (str(t.lots),                              TEXT),
                (f"₹{t.gross_pnl:+,.0f}",                 pnl_clr),
                (f"₹{t.net_pnl:+,.0f}",                   pnl_clr),
                (t.exit_reason,                            WARN if t.exit_reason=="SL" else TEXT),
                (t.signal_name[:20] if t.signal_name else "—", SUBTEXT),
                (src_badge,                                WARN if is_synth else ACCENT),
            ]

            for col, (val, clr) in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setForeground(QBrush(QColor(clr)))
                item.setBackground(QBrush(bg_color))
                item.setTextAlignment(Qt.AlignCenter)
                self._trade_table.setItem(row, col, item)

        self._trade_table.setSortingEnabled(True)

        # ── Equity chart ──────────────────────────────────────────────────────
        self._equity_chart.set_data(result.equity_curve, result.trades)