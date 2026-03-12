"""
backtest/backtest_window.py
============================
Full backtesting window with state_manager integration.

MODERN MINIMALIST DESIGN - Matches DailyTradeSettingGUI, BrokerageSettingGUI, etc.
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
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from Utils.time_utils import IST, ist_now, fmt_display, fmt_stamp
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

from Utils.safe_getattr import safe_hasattr, safe_getattr
from backtest.backtest_candle_debug_tab import CandleDebugTab
from backtest.backtest_engine import BacktestConfig, BacktestResult
from backtest.backtest_help_tab import BacktestHelpTab
from backtest.backtest_thread import BacktestThread
from data.trade_state_manager import state_manager
from strategy.strategy_manager import StrategyManager

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)

ANALYSIS_TIMEFRAMES = ["1m", "2m", "3m", "5m", "10m", "15m", "30m", "60m", "120m", "240m"]


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


class ModernCard(QFrame):
    """Modern card widget with consistent styling."""

    def __init__(self, parent=None, elevated=False):
        super().__init__(parent)
        self.setObjectName("modernCard")
        self.elevated = elevated
        self._apply_style()

    def _apply_style(self):
        c = theme_manager.palette
        sp = theme_manager.spacing

        base_style = f"""
            QFrame#modernCard {{
                background: {c.BG_PANEL};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                padding: {sp.PAD_LG}px;
            }}
        """

        if self.elevated:
            base_style += f"""
                QFrame#modernCard {{
                    border: 1px solid {c.BORDER_FOCUS};
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                               stop:0 {c.BG_PANEL}, stop:1 {c.BG_HOVER});
                }}
            """

        self.setStyleSheet(base_style)


class StatusBadge(QLabel):
    """Status badge with color-coded background."""

    def __init__(self, text="", status="neutral"):
        super().__init__(text)
        self.setObjectName("statusBadge")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(60)
        self.set_status(status)

    def set_status(self, status):
        """Update badge color based on status."""
        c = theme_manager.palette
        sp = theme_manager.spacing
        ty = theme_manager.typography

        if status == "success":
            color = c.GREEN
            bg = c.GREEN + "20"
        elif status == "warning":
            color = c.ORANGE
            bg = c.ORANGE + "20"
        elif status == "error":
            color = c.RED
            bg = c.RED + "20"
        elif status == "info":
            color = c.BLUE
            bg = c.BLUE + "20"
        else:
            color = c.TEXT_DIM
            bg = c.BG_HOVER

        self.setStyleSheet(f"""
            QLabel#statusBadge {{
                color: {color};
                background: {bg};
                border: 1px solid {color};
                border-radius: {sp.RADIUS_PILL}px;
                padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                font-size: {ty.SIZE_XS}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
        """)


class ValueLabel(QLabel):
    """Value label with consistent styling."""

    def __init__(self, text="--", parent=None):
        super().__init__(text, parent)
        self.setObjectName("valueLabel")
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setMinimumWidth(60)
        self._apply_style()

    def _apply_style(self):
        c = theme_manager.palette
        sp = theme_manager.spacing
        ty = theme_manager.typography

        self.setStyleSheet(f"""
            QLabel#valueLabel {{
                color: {c.TEXT_MAIN};
                background: {c.BG_HOVER};
                border-radius: {sp.RADIUS_SM}px;
                padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                font-size: {ty.SIZE_SM}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
        """)


def get_signal_colors():
    """Get signal colors from theme manager."""
    c = theme_manager.palette
    return {
        "BUY_CALL":  c.GREEN,
        "BUY_PUT":   c.RED,
        "EXIT_CALL": c.RED_BRIGHT,
        "EXIT_PUT":  c.ORANGE,
        "HOLD":      c.YELLOW,
        "WAIT":      c.TEXT_DIM,
    }


def _label(text, bold=False, color_token="TEXT_MAIN", size_token="SIZE_BODY"):
    """Create a themed label."""
    c = theme_manager.palette
    ty = theme_manager.typography
    size = ty.get(size_token, ty.SIZE_BODY)
    color = c.get(color_token, c.TEXT_MAIN)

    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {color}; font-size: {size}pt;"
        + (" font-weight: bold;" if bold else "")
    )
    return lbl


def _sep():
    """Create a themed separator."""
    c = theme_manager.palette
    sp = theme_manager.spacing
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"background: {c.BORDER}; max-height: {sp.SEPARATOR}px;")
    return f


def _card(title: str, title_color_token: str = "BLUE") -> QGroupBox:
    """Create a themed group box card."""
    c = theme_manager.palette
    g = QGroupBox(title)
    g.setStyleSheet(f"""
        QGroupBox {{
            border: 1px solid {c.BORDER};
            border-radius: {theme_manager.spacing.RADIUS_MD}px;
            margin-top: {theme_manager.spacing.PAD_MD}px;
            padding-top: {theme_manager.spacing.PAD_MD}px;
            font-weight: {theme_manager.typography.WEIGHT_BOLD};
            color: {c.TEXT_DIM};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: {theme_manager.spacing.PAD_MD}px;
            padding: 0 {theme_manager.spacing.PAD_XS}px;
            color: {c.get(title_color_token, c.BLUE)};
        }}
    """)
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
            "timestamp":   fmt_display(self.timestamp),
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


# ── Multi-Timeframe Analysis Tab (Themed) ─────────────────────────────────────

class MultiTimeframeAnalysisTab(QWidget, ThemedMixin):

    def __init__(self, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.analysis_data: Dict[str, List[BarAnalysis]] = {}
            self._build_ui()
            self.apply_theme()
        except Exception as e:
            logger.error(f"[MultiTimeframeAnalysisTab.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self.analysis_data = {}
        self.timeframe_combo = None
        self.export_btn = None
        self.export_all_btn = None
        self.stats_lbl = None
        self.tree = None
        self.details_text = None
        self.main_card = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the tab."""
        try:
            c = self._c
            ty = self._ty

            # Update stats label
            if self.stats_lbl:
                self.stats_lbl.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_BODY}pt;")

            # Update tree widget (will be refreshed in _show_timeframe)
            self._show_timeframe(self.timeframe_combo.currentText())

            logger.debug("[MultiTimeframeAnalysisTab.apply_theme] Applied theme")
        except Exception as e:
            logger.error(f"[MultiTimeframeAnalysisTab.apply_theme] Failed: {e}", exc_info=True)

    def _build_ui(self):
        sp = self._sp

        layout = QVBoxLayout(self)
        layout.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        layout.setSpacing(sp.GAP_MD)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(sp.GAP_MD)

        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(ANALYSIS_TIMEFRAMES)
        self.timeframe_combo.setCurrentText("5m")
        self.timeframe_combo.currentTextChanged.connect(self._show_timeframe)
        self.timeframe_combo.setStyleSheet(self._get_combobox_style())
        toolbar.addWidget(_label("Timeframe:", size_token="SIZE_XS"))
        toolbar.addWidget(self.timeframe_combo)
        toolbar.addSpacing(sp.PAD_MD)

        self.export_btn = self._create_modern_button("📥 Export", primary=False, icon="📥")
        self.export_btn.clicked.connect(self._export_current)
        self.export_btn.setEnabled(False)
        toolbar.addWidget(self.export_btn)

        self.export_all_btn = self._create_modern_button("📥 Export All", primary=False, icon="📥")
        self.export_all_btn.clicked.connect(self._export_all)
        self.export_all_btn.setEnabled(False)
        toolbar.addWidget(self.export_all_btn)

        toolbar.addStretch()
        self.stats_lbl = _label("No analysis data", color_token="TEXT_DIM", size_token="SIZE_BODY")
        toolbar.addWidget(self.stats_lbl)
        layout.addLayout(toolbar)

        # Splitter: tree on top, details below
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(sp.SPLITTER)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {self._c.BORDER}; }}")

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(
            ["Time", "Spot", "Signal", "Confidence",
             "BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]
        )
        self.tree.setAlternatingRowColors(True)
        self.tree.itemClicked.connect(self._on_bar_selected)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {self._c.BG_MAIN};
                alternate-background-color: {self._c.BG_PANEL};
                border: 1px solid {self._c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                color: {self._c.TEXT_MAIN};
            }}
            QTreeWidget::item {{
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                border-bottom: 1px solid {self._c.BORDER};
            }}
            QTreeWidget::item:selected {{
                background: {self._c.BG_SELECTED};
                color: {self._c.TEXT_MAIN};
            }}
            QTreeWidget::item:hover {{
                background: {self._c.BG_HOVER};
            }}
        """)
        splitter.addWidget(self.tree)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(220)
        self.details_text.setStyleSheet(f"""
            QTextEdit {{
                background: {self._c.BG_PANEL};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                font-family: '{self._ty.FONT_MONO}';
                font-size: {self._ty.SIZE_XS}pt;
                padding: {sp.PAD_SM}px;
            }}
        """)
        splitter.addWidget(self.details_text)
        splitter.setSizes([500, 220])

        layout.addWidget(splitter, 1)

    def _get_combobox_style(self):
        """Get consistent combobox styling."""
        return f"""
            QComboBox {{
                background: {self._c.BG_INPUT};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
                padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                min-height: {self._sp.INPUT_HEIGHT}px;
                font-size: {self._ty.SIZE_BODY}pt;
                min-width: 100px;
            }}
            QComboBox:hover {{
                border-color: {self._c.BORDER_FOCUS};
            }}
            QComboBox::drop-down {{
                border: none;
                width: {self._sp.ICON_LG}px;
            }}
            QComboBox QAbstractItemView {{
                background: {self._c.BG_PANEL};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                selection-background-color: {self._c.BG_SELECTED};
            }}
        """

    def _create_modern_button(self, text, primary=False, icon=""):
        """Create a modern styled button."""
        btn = QPushButton(f"{icon} {text}" if icon else text)
        btn.setCursor(Qt.PointingHandCursor)

        if primary:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BLUE};
                    color: white;
                    border: none;
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    min-width: 120px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BLUE_DARK};
                }}
                QPushButton:disabled {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_DISABLED};
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    min-width: 120px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BORDER};
                    border-color: {self._c.BORDER_FOCUS};
                }}
            """)

        return btn

    def set_analysis_data(self, data: Dict[str, List[BarAnalysis]]):
        self.analysis_data = data
        has = any(data.values())
        self.export_btn.setEnabled(has)
        self.export_all_btn.setEnabled(has)
        total = sum(len(v) for v in data.values())
        self.stats_lbl.setText(f"{total} bars across {len(data)} timeframe(s)")
        self._show_timeframe(self.timeframe_combo.currentText())

    def _show_timeframe(self, tf: str):
        c = self._c
        signal_colors = get_signal_colors()

        self.tree.clear()
        for bar in self.analysis_data.get(tf, []):
            item = QTreeWidgetItem()
            item.setText(0, fmt_display(bar.timestamp, time_only=True))
            item.setData(0, Qt.UserRole, bar.timestamp)
            item.setText(1, f"{bar.spot_price:.2f}")
            item.setText(2, bar.signal)
            item.setForeground(2, QColor(signal_colors.get(bar.signal, c.TEXT_MAIN)))
            overall = (sum(bar.confidence.values()) / len(bar.confidence)
                       if bar.confidence else 0.0)
            item.setText(3, f"{overall:.1%}")
            for i, sig in enumerate(["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"], 4):
                conf = bar.confidence.get(sig, 0)
                item.setText(i, f"{conf:.1%}")
                if conf >= 0.6:
                    clr = c.GREEN
                elif conf >= 0.3:
                    clr = c.YELLOW
                else:
                    clr = c.TEXT_DIM
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
        c = self._c
        signal_colors = get_signal_colors()

        lines = [
            f"📊  {bar.timeframe}  —  {fmt_display(bar.timestamp)}",
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


# ── Settings Sidebar (Themed) ─────────────────────────────────────────────────

class SettingsSidebar(QTabWidget, ThemedMixin):
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
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self._win = window_ref      # BacktestWindow reference
            self.setTabPosition(QTabWidget.North)
            self.setDocumentMode(True)

            for label, method in self._TABS:
                self.addTab(safe_getattr(self, method)(), label)

            self.apply_theme()
        except Exception as e:
            logger.error(f"[SettingsSidebar.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self._win = None
        self.strategy_combo = None
        self.strategy_info = None
        self.rule_count_lbl = None
        self.min_conf_lbl = None
        self.enabled_grp_lbl = None
        self.timeframe_checkboxes = {}
        self.derivative = None
        self.expiry_type = None
        self.lot_size = None
        self.num_lots = None
        self.date_from = None
        self.date_to = None
        self.use_tp = None
        self.tp_pct = None
        self.use_sl = None
        self.sl_pct = None
        self.skip_sideway = None
        self.slippage = None
        self.brokerage = None
        self.capital = None
        self.execution_interval = None
        self.auto_export = None
        self.use_vix = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the sidebar."""
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            self.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    background: {c.BG_PANEL};
                    border-radius: 0 {sp.RADIUS_MD}px {sp.RADIUS_MD}px {sp.RADIUS_MD}px;
                }}
                QTabBar::tab {{
                    background: {c.BG_HOVER};
                    color: {c.TEXT_DIM};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-bottom: none;
                    border-radius: {sp.RADIUS_MD}px {sp.RADIUS_MD}px 0 0;
                    padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                    font-size: {ty.SIZE_BODY}pt;
                    font-weight: {ty.WEIGHT_NORMAL};
                    margin-right: {sp.PAD_XS}px;
                }}
                QTabBar::tab:selected {{
                    background: {c.BG_PANEL};
                    color: {c.TEXT_MAIN};
                    border-bottom: {sp.PAD_XS}px solid {c.BLUE};
                    font-weight: {ty.WEIGHT_BOLD};
                }}
                QTabBar::tab:hover:!selected {{
                    background: {c.BORDER};
                    color: {c.TEXT_MAIN};
                }}
            """)
            logger.debug("[SettingsSidebar.apply_theme] Applied theme")
        except Exception as e:
            logger.error(f"[SettingsSidebar.apply_theme] Failed: {e}", exc_info=True)

    def _get_combobox_style(self):
        """Get consistent combobox styling."""
        return f"""
            QComboBox {{
                background: {self._c.BG_INPUT};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
                padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                min-height: {self._sp.INPUT_HEIGHT}px;
                font-size: {self._ty.SIZE_BODY}pt;
            }}
            QComboBox:hover {{
                border-color: {self._c.BORDER_FOCUS};
            }}
            QComboBox::drop-down {{
                border: none;
                width: {self._sp.ICON_LG}px;
            }}
            QComboBox QAbstractItemView {{
                background: {self._c.BG_PANEL};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                selection-background-color: {self._c.BG_SELECTED};
            }}
        """

    def _get_spinbox_style(self):
        """Get consistent spinbox styling."""
        return f"""
            QSpinBox, QDoubleSpinBox {{
                background: {self._c.BG_INPUT};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
                padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                min-height: {self._sp.INPUT_HEIGHT}px;
                font-size: {self._ty.SIZE_BODY}pt;
            }}
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: {self._c.BORDER_FOCUS};
            }}
        """

    def _get_checkbox_style(self):
        """Get consistent checkbox styling."""
        return f"""
            QCheckBox {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_BODY}pt;
                spacing: {self._sp.GAP_SM}px;
            }}
            QCheckBox::indicator {{
                width: {self._sp.ICON_MD}px;
                height: {self._sp.ICON_MD}px;
                border: 2px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:checked {{
                background: {self._c.BLUE};
                border-color: {self._c.BLUE};
            }}
            QCheckBox::indicator:hover {{
                border-color: {self._c.BORDER_FOCUS};
            }}
        """

    # ── Tab builders ───────────────────────────────────────────────────────

    def _build_strategy_tab(self) -> QWidget:
        c = self._c
        sp = self._sp
        ty = self._ty

        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_MD)

        g = _card("Active Strategy")
        gl = QVBoxLayout(g)
        gl.setSpacing(sp.GAP_SM)

        self.strategy_combo = QComboBox()
        self.strategy_combo.setMinimumHeight(sp.BTN_HEIGHT_SM)
        self.strategy_combo.setStyleSheet(self._get_combobox_style())
        gl.addWidget(self.strategy_combo)

        refresh_btn = QPushButton("🔄  Refresh List")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {ty.SIZE_BODY}pt;
                min-height: 36px;
            }}
            QPushButton:hover {{
                background: {c.BORDER};
            }}
        """)
        refresh_btn.clicked.connect(lambda: self._win._load_strategies())
        gl.addWidget(refresh_btn)

        self.strategy_info = QLabel("")
        self.strategy_info.setWordWrap(True)
        self.strategy_info.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt; padding:{sp.PAD_SM}px; background:{c.BG_HOVER}; border-radius:{sp.RADIUS_SM}px;")
        gl.addWidget(self.strategy_info)
        lay.addWidget(g)

        g2 = _card("Strategy Stats", "TEXT_DIM")
        g2l = QFormLayout(g2)
        g2l.setSpacing(sp.GAP_SM)
        g2l.setLabelAlignment(Qt.AlignRight)

        self.rule_count_lbl = ValueLabel("0")
        self.min_conf_lbl   = ValueLabel("—")
        self.enabled_grp_lbl= ValueLabel("—")
        g2l.addRow("Rules:", self.rule_count_lbl)
        g2l.addRow("Min Confidence:", self.min_conf_lbl)
        g2l.addRow("Enabled Groups:", self.enabled_grp_lbl)
        lay.addWidget(g2)

        lay.addStretch()
        return tab

    def _build_timeframe_tab(self) -> QWidget:
        c = self._c
        sp = self._sp
        ty = self._ty

        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_MD)

        g_tf = _card("Analysis Timeframes", "PURPLE")
        gl_tf = QVBoxLayout(g_tf)
        gl_tf.setSpacing(sp.GAP_SM)
        gl_tf.addWidget(_label("Select timeframes to analyse:", size_token="SIZE_XS"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        tf_w = QWidget()
        tf_lay = QVBoxLayout(tf_w)
        tf_lay.setContentsMargins(0, 0, 0, 0)
        tf_lay.setSpacing(sp.GAP_SM)

        self.timeframe_checkboxes: Dict[str, QCheckBox] = {}
        categories = [
            ("Short Term (1–5m)",    ["1m", "2m", "3m", "5m"]),
            ("Medium Term (10–30m)", ["10m", "15m", "30m"]),
            ("Long Term (60–240m)",  ["60m", "120m", "240m"]),
        ]
        for cat, tfs in categories:
            lbl = _label(cat, color_token="BLUE", size_token="SIZE_XS")
            tf_lay.addWidget(lbl)
            for tf in tfs:
                cb = QCheckBox(tf)
                cb.setChecked(tf == "5m")
                cb.setStyleSheet(self._get_checkbox_style())
                self.timeframe_checkboxes[tf] = cb
                tf_lay.addWidget(cb)
            tf_lay.addSpacing(sp.PAD_SM)

        scroll.setWidget(tf_w)
        gl_tf.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(sp.GAP_SM)
        sel_all = QPushButton("Select All")
        sel_all.setCursor(Qt.PointingHandCursor)
        sel_all.setStyleSheet(f"""
            QPushButton {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size: {ty.SIZE_BODY}pt;
                min-height: 32px;
            }}
            QPushButton:hover {{
                background: {c.BORDER};
            }}
        """)
        sel_all.clicked.connect(lambda: self._set_all_tfs(True))
        des_all = QPushButton("Deselect All")
        des_all.setCursor(Qt.PointingHandCursor)
        des_all.setStyleSheet(sel_all.styleSheet())
        des_all.clicked.connect(lambda: self._set_all_tfs(False))
        btn_row.addWidget(sel_all)
        btn_row.addWidget(des_all)
        gl_tf.addLayout(btn_row)
        lay.addWidget(g_tf, 1)
        return tab

    def _build_instrument_tab(self) -> QWidget:
        c = self._c
        sp = self._sp
        ty = self._ty

        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_MD)

        g = _card("Instrument", "ORANGE")
        gl = QFormLayout(g)
        gl.setSpacing(sp.GAP_SM)
        gl.setLabelAlignment(Qt.AlignRight)

        self.derivative = QComboBox()
        self.derivative.addItems(["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"])
        self.derivative.setStyleSheet(self._get_combobox_style())
        gl.addRow("Derivative:", self.derivative)

        self.expiry_type = QComboBox()
        self.expiry_type.addItems(["weekly", "monthly"])
        self.expiry_type.setStyleSheet(self._get_combobox_style())
        gl.addRow("Expiry:", self.expiry_type)

        self.lot_size = QSpinBox()
        self.lot_size.setRange(1, 1800)
        self.lot_size.setValue(50)
        self.lot_size.setStyleSheet(self._get_spinbox_style())
        gl.addRow("Lot Size:", self.lot_size)

        self.num_lots = QSpinBox()
        self.num_lots.setRange(1, 50)
        self.num_lots.setValue(1)
        self.num_lots.setStyleSheet(self._get_spinbox_style())
        gl.addRow("# Lots:", self.num_lots)
        lay.addWidget(g)

        g2 = _card("Date Range")
        g2l = QFormLayout(g2)
        g2l.setSpacing(sp.GAP_SM)
        g2l.setLabelAlignment(Qt.AlignRight)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.setDisplayFormat("dd MMM yyyy")
        self.date_from.setStyleSheet(self._get_spinbox_style())
        g2l.addRow("From:", self.date_from)

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate().addDays(-1))
        self.date_to.setDisplayFormat("dd MMM yyyy")
        self.date_to.setStyleSheet(self._get_spinbox_style())
        g2l.addRow("To:", self.date_to)
        lay.addWidget(g2)

        lay.addStretch()
        return tab

    def _build_risk_tab(self) -> QWidget:
        c = self._c
        sp = self._sp
        ty = self._ty

        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_MD)

        g = _card("Take Profit / Stop Loss", "YELLOW")
        gl = QFormLayout(g)
        gl.setSpacing(sp.GAP_SM)
        gl.setLabelAlignment(Qt.AlignRight)

        self.use_tp = QCheckBox("Enable Take Profit")
        self.use_tp.setChecked(True)
        self.use_tp.setStyleSheet(self._get_checkbox_style())
        gl.addRow("", self.use_tp)

        self.tp_pct = QDoubleSpinBox()
        self.tp_pct.setRange(0, 500)
        self.tp_pct.setValue(30)
        self.tp_pct.setSuffix(" %")
        self.tp_pct.setDecimals(1)
        self.tp_pct.setStyleSheet(self._get_spinbox_style())
        gl.addRow("TP %:", self.tp_pct)

        self.use_sl = QCheckBox("Enable Stop Loss")
        self.use_sl.setChecked(True)
        self.use_sl.setStyleSheet(self._get_checkbox_style())
        gl.addRow("", self.use_sl)

        self.sl_pct = QDoubleSpinBox()
        self.sl_pct.setRange(0, 100)
        self.sl_pct.setValue(25)
        self.sl_pct.setSuffix(" %")
        self.sl_pct.setDecimals(1)
        self.sl_pct.setStyleSheet(self._get_spinbox_style())
        gl.addRow("SL %:", self.sl_pct)
        lay.addWidget(g)

        g2 = _card("Risk Options")
        g2l = QVBoxLayout(g2)
        self.skip_sideway = QCheckBox("Skip 12:00–14:00 (sideway zone)")
        self.skip_sideway.setChecked(True)
        self.skip_sideway.setStyleSheet(self._get_checkbox_style())
        g2l.addWidget(self.skip_sideway)
        lay.addWidget(g2)

        lay.addStretch()
        return tab

    def _build_cost_tab(self) -> QWidget:
        c = self._c
        sp = self._sp
        ty = self._ty

        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_MD)

        g = _card("Execution Costs", "RED_BRIGHT")
        gl = QFormLayout(g)
        gl.setSpacing(sp.GAP_SM)
        gl.setLabelAlignment(Qt.AlignRight)

        self.slippage = QDoubleSpinBox()
        self.slippage.setRange(0, 5)
        self.slippage.setValue(0.25)
        self.slippage.setSuffix(" %")
        self.slippage.setDecimals(2)
        self.slippage.setStyleSheet(self._get_spinbox_style())
        gl.addRow("Slippage:", self.slippage)

        self.brokerage = QDoubleSpinBox()
        self.brokerage.setRange(0, 500)
        self.brokerage.setValue(40)
        self.brokerage.setPrefix("₹ ")
        self.brokerage.setDecimals(0)
        self.brokerage.setStyleSheet(self._get_spinbox_style())
        gl.addRow("Brokerage/Lot:", self.brokerage)
        lay.addWidget(g)

        g2 = _card("Capital")
        g2l = QFormLayout(g2)
        g2l.setSpacing(sp.GAP_SM)
        g2l.setLabelAlignment(Qt.AlignRight)
        self.capital = QDoubleSpinBox()
        self.capital.setRange(10_000, 100_000_000)
        self.capital.setValue(100_000)
        self.capital.setPrefix("₹ ")
        self.capital.setDecimals(0)
        self.capital.setSingleStep(10_000)
        self.capital.setStyleSheet(self._get_spinbox_style())
        g2l.addRow("Initial Capital:", self.capital)
        lay.addWidget(g2)

        lay.addStretch()
        return tab

    def _build_execution_tab(self) -> QWidget:
        c = self._c
        sp = self._sp
        ty = self._ty

        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        lay.setSpacing(sp.GAP_MD)

        g = _card("Execution Options", "GREEN")
        gl = QVBoxLayout(g)
        gl.setSpacing(sp.GAP_SM)

        gl.addWidget(_label("Execution interval (minutes):", size_token="SIZE_XS"))
        self.execution_interval = QComboBox()
        self.execution_interval.addItems(["1", "2", "3", "5", "10", "15", "30"])
        self.execution_interval.setCurrentText("5")
        self.execution_interval.setStyleSheet(self._get_combobox_style())
        self.execution_interval.setToolTip(
            "Candle width used for signal evaluation and trade execution.\n"
            "Data is always fetched at 1-min resolution from the broker\n"
            "and resampled to this interval — no separate broker call needed."
        )
        gl.addWidget(self.execution_interval)

        self.auto_export = QCheckBox("Auto-export analysis after run")
        self.auto_export.setChecked(False)
        self.auto_export.setStyleSheet(self._get_checkbox_style())
        gl.addWidget(self.auto_export)
        lay.addWidget(g)

        g3 = _card("Volatility Source", "BLUE")
        g3l = QVBoxLayout(g3)
        g3l.setSpacing(sp.GAP_SM)
        self.use_vix = QCheckBox("Use India VIX for option pricing")
        self.use_vix.setChecked(True)
        self.use_vix.setStyleSheet(self._get_checkbox_style())
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
        hv_note.setWordWrap(True)
        hv_note.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt; padding-left:{sp.PAD_XL}px;")
        g3l.addWidget(hv_note)
        lay.addWidget(g3)

        g2 = _card("Notes", "TEXT_DIM")
        g2l = QVBoxLayout(g2)
        g2l.setSpacing(sp.GAP_SM)
        info = QLabel(
            "• Spot data is always fetched at 1-min resolution\n"
            "  and resampled to the execution interval above\n"
            "• Analysis timeframes are independent of execution\n"
            "• Synthetic (BS) pricing used for all option bars\n"
            "  (marked ⚗ in Trade Log)\n"
            "• HV mode: no network calls, fully offline capable"
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
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
        self.rule_count_lbl.setText(str(total_rules))
        self.min_conf_lbl.setText(f"{min_conf:.0f}%")
        self.enabled_grp_lbl.setText(f"{enabled}/5")


# ── Stat Card (Themed) ────────────────────────────────────────────────────────

class _StatCard(ModernCard, ThemedMixin):
    def __init__(self, label: str, value: str = "—", value_color_token: str = "TEXT_MAIN"):
        self._safe_defaults_init()
        try:
            super().__init__()

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self._value_color_token = value_color_token
            self.setObjectName("statCard")

            lay = QVBoxLayout(self)
            lay.setContentsMargins(self._sp.PAD_MD, self._sp.PAD_SM,
                                  self._sp.PAD_MD, self._sp.PAD_SM)
            lay.setSpacing(self._sp.GAP_XS)

            self._lbl = QLabel(label)
            self._lbl.setStyleSheet(f"color:{self._c.TEXT_DIM}; font-size:{self._ty.SIZE_XS}pt; border:none;")

            self._val = QLabel(value)
            self._val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._val.setStyleSheet(f"color:{self._c.get(value_color_token, self._c.TEXT_MAIN)}; font-size:{self._ty.SIZE_XL}pt; font-weight:bold; border:none;")

            lay.addWidget(self._lbl)
            lay.addWidget(self._val)

            self.apply_theme()
        except Exception as e:
            logger.error(f"[_StatCard.__init__] Failed: {e}", exc_info=True)
            super().__init__()

    def _safe_defaults_init(self):
        self._lbl = None
        self._val = None
        self._value_color_token = "TEXT_MAIN"

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the stat card."""
        try:
            # Call parent apply_theme to update card styling
            super()._apply_style()

            # Update label and value styles
            self._lbl.setStyleSheet(f"color:{self._c.TEXT_DIM}; font-size:{self._ty.SIZE_XS}pt; border:none;")
            self._val.setStyleSheet(f"color:{self._c.get(self._value_color_token, self._c.TEXT_MAIN)}; font-size:{self._ty.SIZE_XL}pt; font-weight:bold; border:none;")
        except Exception as e:
            logger.error(f"[_StatCard.apply_theme] Failed: {e}", exc_info=True)

    def update_value(self, value: str, color_token: str = "TEXT_MAIN"):
        self._value_color_token = color_token
        self._val.setText(value)
        self._val.setStyleSheet(f"color:{self._c.get(color_token, self._c.TEXT_MAIN)}; font-size:{self._ty.SIZE_XL}pt; font-weight:bold; border:none;")


# ── Equity Chart (Themed) ─────────────────────────────────────────────────────

class EquityChart(QWidget, ThemedMixin):

    def __init__(self, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self._equity_data = []
            self._use_pg = False
            self._setup()
            self.apply_theme()
        except Exception as e:
            logger.error(f"[EquityChart.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self._equity_data = []
        self._use_pg = False
        self._pg_widget = None
        self._fallback = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the chart."""
        try:
            c = self._c

            if self._use_pg and self._pg_widget:
                import pyqtgraph as pg
                pg.setConfigOptions(antialias=True, background=c.BG_MAIN, foreground=c.TEXT_MAIN)
                self._pg_widget.setBackground(c.BG_MAIN)
                self._pg_widget.getAxis("left").setPen(pg.mkPen(color=c.TEXT_DIM))
                self._pg_widget.getAxis("bottom").setPen(pg.mkPen(color=c.TEXT_DIM))
        except Exception as e:
            logger.error(f"[EquityChart.apply_theme] Failed: {e}", exc_info=True)

    def _setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        try:
            import pyqtgraph as pg
            c = self._c

            pg.setConfigOptions(antialias=True, background=c.BG_MAIN, foreground=c.TEXT_MAIN)
            self._pg_widget = pg.PlotWidget()
            self._pg_widget.setLabel("left", "Equity (₹)", color=c.TEXT_DIM)
            self._pg_widget.setLabel("bottom", "Trade #", color=c.TEXT_DIM)
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
                return (safe_getattr(trade.entry_source, "value", "") == "synthetic" or
                        safe_getattr(trade.exit_source,  "value", "") == "synthetic")
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
        c = self._c

        pw = self._pg_widget
        pw.clear()
        if not equity_curve:
            return
        equities = [e["equity"] for e in equity_curve]
        xs = list(range(len(equities)))
        pen_clr = c.GREEN if equities[-1] >= equities[0] else c.RED
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

            synth_color = QColor(c.YELLOW)
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

        signal_colors = get_signal_colors()
        for i, trade in enumerate(trades):
            y = equities[min(i, len(equities) - 1)]
            clr = signal_colors.get("BUY_CALL") if safe_getattr(trade, "direction", "") in ("CE", "CALL") else signal_colors.get("BUY_PUT")
            pw.addItem(pg.ScatterPlotItem(
                [i], [y],
                symbol="t1" if safe_getattr(trade, "net_pnl", 0) > 0 else "t",
                size=13, brush=clr, pen=pg.mkPen(None),
            ))

    def clear(self):
        if self._use_pg:
            self._pg_widget.clear()
        elif safe_hasattr(self, "_fallback"):
            self._fallback.set_data([], [])


class _EquityPainter(QWidget, ThemedMixin):
    def __init__(self, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self._equity = []
            self.setMinimumHeight(200)
            self.apply_theme()
        except Exception as e:
            logger.error(f"[_EquityPainter.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self._equity = []

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the painter."""
        # Colors will be used in paintEvent
        self.update()

    def set_data(self, equity_curve, _trades):
        self._equity = [e["equity"] for e in equity_curve]
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QPen
        c = self._c
        sp = self._sp

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h, pad = self.width(), self.height(), 40
        p.fillRect(0, 0, w, h, QColor(c.BG_MAIN))
        if not self._equity or len(self._equity) < 2:
            p.setPen(QColor(c.TEXT_DIM))
            p.drawText(0, 0, w, h, Qt.AlignCenter, "No equity data")
            return
        mn, mx = min(self._equity), max(self._equity)
        rng = mx - mn or 1
        tx = lambda i: pad + int((i / (len(self._equity) - 1)) * (w - 2 * pad))
        ty = lambda v: h - pad - int(((v - mn) / rng) * (h - 2 * pad))
        p.setPen(QPen(QColor(c.BORDER), 1, Qt.DashLine))
        p.drawLine(pad, ty(self._equity[0]), w - pad, ty(self._equity[0]))
        clr = QColor(c.GREEN if self._equity[-1] >= self._equity[0] else c.RED)
        p.setPen(QPen(clr, 2))
        for i in range(1, len(self._equity)):
            p.drawLine(tx(i - 1), ty(self._equity[i - 1]), tx(i), ty(self._equity[i]))
        p.setPen(QColor(c.TEXT_DIM))
        p.drawText(2, ty(mx) + 4, f"₹{mx:,.0f}")
        p.drawText(2, ty(mn) + 4, f"₹{mn:,.0f}")


# ── Main Backtest Window (Themed) ─────────────────────────────────────────────

class BacktestWindow(QMainWindow, ThemedMixin):
    """
    Standalone QMainWindow for running and reviewing backtests.
    Uses state_manager to access and restore trade state.

    MODERN MINIMALIST DESIGN - Matches other dialogs.
    Layout mirrors TradingGUI:
      • Left/centre: tabbed results panel
      • Right: settings sidebar (tabbed, like StatusPanel)
      • Bottom: progress bar + Run/Stop buttons
    """

    def __init__(self, trading_app=None, strategy_manager=None, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self._trading_app      = trading_app
            self._strategy_manager = strategy_manager or StrategyManager()
            self._thread: Optional[BacktestThread] = None
            self._result = None
            self._analysis_data: Dict[str, List[BarAnalysis]] = {}

            # Get current state snapshot for reference and restoration
            self._pre_backtest_state = state_manager.save_state()
            logger.info(f"[BacktestWindow] Saved pre-backtest state: {len(self._pre_backtest_state)} fields")

            self.setWindowTitle("📊  Strategy Backtester")

            # Set window flags for modern look
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            self.setMinimumSize(1500, 900)

            self._build()
            self._load_defaults()
            self._load_strategies()

            self.apply_theme()

        except Exception as e:
            logger.critical(f"[BacktestWindow.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self._trading_app = None
        self._strategy_manager = None
        self._thread = None
        self._result = None
        self._analysis_data = {}
        self._pre_backtest_state = {}
        self._selected_analysis_tfs = []
        self._synth_banner = None
        self._synth_banner_lbl = None
        self._tabs = None
        self.settings_sidebar = None
        self._cards = {}
        self._timeframe_info = None
        self._cfg_summary = None
        self._trade_table = None
        self._equity_chart = None
        self._debug_tab = None
        self._help_tab = None
        self._analysis_tab = None
        self._status_lbl = None
        self._progress = None
        self.run_btn = None
        self.stop_btn = None
        self.main_card = None

    def _create_title_bar(self):
        """Create custom title bar with close button."""
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet(f"background: {self._c.BG_PANEL}; border-top-left-radius: {self._sp.RADIUS_LG}px; border-top-right-radius: {self._sp.RADIUS_LG}px;")

        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(self._sp.PAD_MD, 0, self._sp.PAD_MD, 0)

        title = QLabel("📊 Strategy Backtester")
        title.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_LG}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
        """)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self._c.BG_HOVER};
                color: {self._c.TEXT_DIM};
                border: none;
                border-radius: {self._sp.RADIUS_SM}px;
                font-size: {self._ty.SIZE_MD}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {self._c.RED};
                color: white;
            }}
        """)
        close_btn.clicked.connect(self.close)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(close_btn)

        return title_bar

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the window."""
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            # Update main card style
            if hasattr(self, 'main_card') and self.main_card:
                self.main_card._apply_style()

            # Update splitter
            splitter = self.findChild(QSplitter)
            if splitter:
                splitter.setStyleSheet(f"QSplitter::handle {{ background: {c.BORDER}; }}")

            # Update synth banner
            if self._synth_banner and self._synth_banner_lbl:
                self._synth_banner.setStyleSheet(
                    f"background:{c.BG_ROW_B}; border-bottom:1px solid {c.YELLOW}; padding:{sp.PAD_XS}px {sp.PAD_MD}px;"
                )
                self._synth_banner_lbl.setStyleSheet(f"color:{c.YELLOW}; font-size:{ty.SIZE_XS}pt;")

            # Update status label
            if self._status_lbl:
                self._status_lbl.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")

            # Update timeframe info
            if self._timeframe_info:
                self._timeframe_info.setStyleSheet(f"color:{c.BLUE}; font-size:{ty.SIZE_BODY}pt;")

            # Update progress bar
            if self._progress:
                self._progress.setStyleSheet(f"""
                    QProgressBar {{
                        background: {c.BG_HOVER};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                        text-align: center;
                        color: {c.TEXT_MAIN};
                        min-height: {sp.PROGRESS_MD}px;
                        max-height: {sp.PROGRESS_MD}px;
                    }}
                    QProgressBar::chunk {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 {c.GREEN}, stop:1 {c.GREEN_BRIGHT});
                        border-radius: {sp.RADIUS_MD}px;
                    }}
                """)

            logger.debug("[BacktestWindow.apply_theme] Applied theme")
        except Exception as e:
            logger.error(f"[BacktestWindow.apply_theme] Failed: {e}", exc_info=True)

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build(self):
        sp = self._sp

        # Root layout with margins for shadow effect
        root = QVBoxLayout()
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        # Main container card
        self.main_card = ModernCard(self, elevated=True)
        main_layout = QVBoxLayout(self.main_card)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Custom title bar
        title_bar = self._create_title_bar()
        main_layout.addWidget(title_bar)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"background: {self._c.BORDER}; max-height: 1px;")
        main_layout.addWidget(separator)

        # Content area
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL,
                                         sp.PAD_XL, sp.PAD_XL)
        content_layout.setSpacing(sp.GAP_LG)

        # ── Synthetic-price disclaimer banner ──────────────────────────
        self._synth_banner = QFrame()
        self._synth_banner.hide()
        sb_lay = QHBoxLayout(self._synth_banner)
        sb_lay.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM)
        self._synth_banner_lbl = QLabel()
        self._synth_banner_lbl.setWordWrap(True)
        sb_lay.addWidget(self._synth_banner_lbl)
        content_layout.addWidget(self._synth_banner)

        # ── Main horizontal split: Results | Sidebar ───────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(sp.SPLITTER)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {self._c.BORDER}; }}")

        # Left: Results panel
        results_panel = self._build_results_panel()
        splitter.addWidget(results_panel)

        # Right: Settings sidebar (mirrors StatusPanel position)
        self.settings_sidebar = SettingsSidebar(self)
        self.settings_sidebar.setFixedWidth(420)
        splitter.addWidget(self.settings_sidebar)

        splitter.setSizes([1100, 380])
        content_layout.addWidget(splitter, 1)

        # ── Bottom bar: progress + buttons ─────────────────────────────
        bottom = self._build_bottom_bar()
        content_layout.addWidget(bottom)

        main_layout.addWidget(content)
        root.addWidget(self.main_card)

        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

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
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: {self._sp.SEPARATOR}px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
                background: {self._c.BG_PANEL};
                margin-top: {self._sp.PAD_SM}px;
            }}
            QTabBar::tab {{
                background: {self._c.BG_HOVER};
                color: {self._c.TEXT_DIM};
                padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                min-width: 130px;
                border: {self._sp.SEPARATOR}px solid {self._c.BORDER};
                border-bottom: none;
                border-radius: {self._sp.RADIUS_SM}px {self._sp.RADIUS_SM}px 0 0;
                font-size: {self._ty.SIZE_BODY}pt;
                margin-right: {self._sp.PAD_XS}px;
            }}
            QTabBar::tab:selected {{
                background: {self._c.BG_PANEL};
                color: {self._c.TEXT_MAIN};
                border-bottom: {self._sp.PAD_XS}px solid {self._c.BLUE};
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
            QTabBar::tab:hover:!selected {{
                background: {self._c.BORDER};
                color: {self._c.TEXT_MAIN};
            }}
        """)
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
        sp = self._sp

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(sp.PAD_XL, sp.PAD_MD, sp.PAD_XL, sp.PAD_MD)
        lay.setSpacing(sp.GAP_MD)

        # Stat cards grid (4 columns)
        cards_w = QWidget()
        cards_lay = QGridLayout(cards_w)
        cards_lay.setSpacing(sp.GAP_MD)

        self._cards = {}
        card_defs = [
            ("net_pnl",      "Net P&L",           "—", "TEXT_MAIN"),
            ("total_trades", "Total Trades",       "—", "TEXT_MAIN"),
            ("win_rate",     "Win Rate",           "—", "TEXT_MAIN"),
            ("profit_factor","Profit Factor",      "—", "TEXT_MAIN"),
            ("best_trade",   "Best Trade",         "—", "GREEN"),
            ("worst_trade",  "Worst Trade",        "—", "RED"),
            ("avg_pnl",      "Avg Net P&L/Trade",  "—", "TEXT_MAIN"),
            ("max_dd",       "Max Drawdown",       "—", "YELLOW"),
            ("sharpe",       "Sharpe Ratio",       "—", "BLUE"),
            ("winners",      "Winners",            "—", "GREEN"),
            ("losers",       "Losers",             "—", "RED"),
            ("data_quality", "Data Source",        "—", "TEXT_MAIN"),
        ]
        for n, (key, lbl, val, clr) in enumerate(card_defs):
            card = _StatCard(lbl, val, clr)
            self._cards[key] = card
            cards_lay.addWidget(card, n // 4, n % 4)

        lay.addWidget(cards_w)

        self._timeframe_info = _label("", color_token="BLUE", size_token="SIZE_BODY")
        lay.addWidget(self._timeframe_info)

        self._cfg_summary = _label(
            "No results yet — configure settings on the right and press ▶ Run.",
            color_token="TEXT_DIM", size_token="SIZE_XS"
        )
        self._cfg_summary.setWordWrap(True)
        self._cfg_summary.setStyleSheet(f"color:{self._c.TEXT_DIM}; font-size:{self._ty.SIZE_XS}pt; padding:{self._sp.PAD_SM}px; background:{self._c.BG_HOVER}; border-radius:{self._sp.RADIUS_SM}px;")
        lay.addWidget(self._cfg_summary)

        lay.addStretch()
        return w

    def _build_trade_log_tab(self) -> QWidget:
        sp = self._sp
        c = self._c

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)
        lay.setSpacing(sp.GAP_XS)

        legend = QHBoxLayout()
        legend.setSpacing(sp.GAP_MD)
        for sym, lbl, clr in [
            ("⚗", "Synthetic (Black-Scholes) price", c.YELLOW),
            ("✓", "Real broker data",                 c.GREEN),
        ]:
            legend.addWidget(_label(f"{sym}  {lbl}", color_token=clr if isinstance(clr, str) else "YELLOW", size_token="SIZE_XS"))
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
        self._trade_table.setStyleSheet(f"""
            QTableWidget {{
                background: {c.BG_MAIN};
                alternate-background-color: {c.BG_PANEL};
                gridline-color: {c.BORDER};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                color: {c.TEXT_MAIN};
            }}
            QTableWidget::item {{
                padding: {sp.PAD_SM}px;
                border-bottom: 1px solid {c.BORDER};
            }}
            QTableWidget::item:selected {{
                background: {c.BG_SELECTED};
                color: {c.TEXT_MAIN};
            }}
            QHeaderView::section {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: none;
                border-bottom: 1px solid {c.BORDER};
                border-right: 1px solid {c.BORDER};
                padding: {sp.PAD_SM}px;
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
        """)
        hdr = self._trade_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(True)
        lay.addWidget(self._trade_table, 1)
        return w

    def _build_chart_tab(self) -> QWidget:
        sp = self._sp

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(sp.PAD_SM, sp.PAD_SM, sp.PAD_SM, sp.PAD_SM)
        self._equity_chart = EquityChart()
        self._equity_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self._equity_chart, 1)
        note = _label(
            "⚗ Amber-shaded bars = Black-Scholes synthetic pricing (real option data unavailable).",
            color_token="YELLOW", size_token="SIZE_XS"
        )
        note.setStyleSheet(f"color:{self._c.YELLOW}; font-size:{self._ty.SIZE_XS}pt; padding:{self._sp.PAD_SM}px; background:{self._c.BG_HOVER}; border-radius:{self._sp.RADIUS_SM}px;")
        lay.addWidget(note)
        return w

    def _build_bottom_bar(self) -> QWidget:
        c = self._c
        sp = self._sp
        ty = self._ty

        bar = QFrame()
        bar.setFixedHeight(sp.BUTTON_PANEL_H)
        bar.setStyleSheet(f"background:{c.BG_PANEL}; border-top:1px solid {c.BORDER}; border-radius:0 0 {sp.RADIUS_LG}px {sp.RADIUS_LG}px;")

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(sp.PAD_XL, sp.PAD_MD, sp.PAD_XL, sp.PAD_MD)
        lay.setSpacing(sp.GAP_MD)

        # Progress section
        prog_col = QVBoxLayout()
        prog_col.setSpacing(sp.GAP_XS)

        self._status_lbl = _label("Ready", color_token="TEXT_DIM", size_token="SIZE_XS")
        self._status_lbl.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
        prog_col.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(sp.PROGRESS_MD)
        self._progress.setTextVisible(False)
        prog_col.addWidget(self._progress)

        lay.addLayout(prog_col, 1)

        # Buttons
        self.run_btn = QPushButton("▶  Run Backtest")
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.setFixedHeight(sp.BTN_HEIGHT_LG)
        self.run_btn.setMinimumWidth(160)
        self.run_btn.clicked.connect(self._on_run)
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {c.GREEN};
                color: white;
                border: none;
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                font-size: {ty.SIZE_BODY}pt;
                font-weight: {ty.WEIGHT_BOLD};
                min-width: 160px;
            }}
            QPushButton:hover {{
                background: {c.GREEN_BRIGHT};
            }}
            QPushButton:disabled {{
                background: {c.BG_HOVER};
                color: {c.TEXT_DISABLED};
            }}
        """)
        lay.addWidget(self.run_btn)

        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setFixedHeight(sp.BTN_HEIGHT_LG)
        self.stop_btn.setMinimumWidth(100)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {c.RED};
                color: white;
                border: none;
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                font-size: {ty.SIZE_BODY}pt;
                font-weight: {ty.WEIGHT_BOLD};
                min-width: 100px;
            }}
            QPushButton:hover {{
                background: {c.RED_BRIGHT};
            }}
            QPushButton:disabled {{
                background: {c.BG_HOVER};
                color: {c.TEXT_DISABLED};
            }}
        """)
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
            if self._trading_app and safe_hasattr(self._trading_app, "trade_config"):
                tc = self._trading_app.trade_config
                if safe_getattr(tc, "derivative", None):
                    idx = sb.derivative.findText(tc.derivative.upper())
                    if idx >= 0:
                        sb.derivative.setCurrentIndex(idx)
                if safe_getattr(tc, "lot_size", None):
                    sb.lot_size.setValue(int(tc.lot_size))
                if safe_getattr(tc, "history_interval", None):
                    idx = sb.execution_interval.findText(str(tc.history_interval).replace("m", ""))
                    if idx >= 0:
                        sb.execution_interval.setCurrentIndex(idx)
            if self._trading_app and safe_hasattr(self._trading_app, "profit_loss_config"):
                pl = self._trading_app.profit_loss_config
                if safe_getattr(pl, "tp_percentage", None):
                    sb.tp_pct.setValue(float(pl.tp_percentage))
                if safe_getattr(pl, "stoploss_percentage", None):
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
            if self._trading_app and safe_hasattr(self._trading_app, "broker"):
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
                and safe_hasattr(result, "analysis_data")
                and result.analysis_data):
            self._export_analysis()

        # FIX: Load debug entries from the saved JSON file
        if safe_hasattr(result, 'debug_log_path') and result.debug_log_path:
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
        c = self._c
        signal_colors = get_signal_colors()

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
        pnl_clr = "GREEN" if result.total_net_pnl >= 0 else "RED"
        self._cards["net_pnl"].update_value(f"₹{result.total_net_pnl:+,.0f}", pnl_clr)
        self._cards["total_trades"].update_value(str(result.total_trades))
        wr_clr = "GREEN" if result.win_rate >= 50 else "YELLOW"
        self._cards["win_rate"].update_value(f"{result.win_rate:.1f}%", wr_clr)
        pf_clr = "GREEN" if result.profit_factor >= 1 else "RED"
        pf_txt = (f"{result.profit_factor:.2f}"
                  if result.profit_factor != float("inf") else "∞")
        self._cards["profit_factor"].update_value(pf_txt, pf_clr)
        self._cards["best_trade"].update_value(f"₹{result.best_trade:+,.0f}", "GREEN")
        self._cards["worst_trade"].update_value(f"₹{result.worst_trade:+,.0f}", "RED")
        avg_clr = "GREEN" if result.avg_net_pnl >= 0 else "RED"
        self._cards["avg_pnl"].update_value(f"₹{result.avg_net_pnl:+,.0f}", avg_clr)
        self._cards["max_dd"].update_value(f"₹{result.max_drawdown:,.0f}", "YELLOW")
        sh_clr = "GREEN" if result.sharpe >= 1 else ("YELLOW" if result.sharpe >= 0 else "RED")
        self._cards["sharpe"].update_value(f"{result.sharpe:.2f}", sh_clr)
        self._cards["winners"].update_value(str(result.winners), "GREEN")
        self._cards["losers"].update_value(str(result.losers), "RED")
        if total_src:
            real_pct = result.real_bars / total_src * 100
            dq_clr = "GREEN" if real_pct >= 80 else ("YELLOW" if real_pct >= 40 else "RED")
            dq_lbl = (f"{result.real_bars}R / {result.synthetic_bars}S"
                      if total_src < 30
                      else f"{real_pct:.0f}% real data")
        else:
            dq_lbl, dq_clr = "N/A", "TEXT_DIM"
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
            bg_color  = QColor(c.BG_ROW_B) if is_synth else QColor(c.BG_MAIN)
            dir_clr   = signal_colors.get("BUY_CALL") if safe_getattr(t, "direction", "") in ("CE", "CALL") else signal_colors.get("BUY_PUT")
            pnl_clr   = c.GREEN if t.net_pnl >= 0 else c.RED
            cells = [
                (str(t.trade_no),                                         c.TEXT_MAIN),
                (f"{'📈 CE' if t.direction in ('CE','CALL') else '📉 PE'}", dir_clr),
                (fmt_display(t.entry_time),                    c.TEXT_MAIN),
                (fmt_display(t.exit_time),                     c.TEXT_MAIN),
                (f"{t.spot_entry:,.0f}",                                  c.TEXT_MAIN),
                (f"{t.spot_exit:,.0f}",                                   c.TEXT_MAIN),
                (f"{t.strike:,}",                                         c.TEXT_MAIN),
                (f"₹{t.option_entry:.2f}",                               c.TEXT_MAIN),
                (f"₹{t.option_exit:.2f}",                                c.TEXT_MAIN),
                (str(t.lots),                                             c.TEXT_MAIN),
                (f"₹{t.gross_pnl:+,.0f}",                               pnl_clr),
                (f"₹{t.net_pnl:+,.0f}",                                 pnl_clr),
                (t.exit_reason,          c.YELLOW if t.exit_reason == "SL" else c.TEXT_MAIN),
                ((t.signal_name or "—")[:20],                            c.TEXT_DIM),
                (src_badge,              c.YELLOW if is_synth else c.GREEN),
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
        debug_path = safe_getattr(result, "debug_log_path", None)
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
        selected = safe_getattr(self, "_selected_analysis_tfs", [tf])
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

        selected = safe_getattr(self, "_selected_analysis_tfs", [tf])
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
            if safe_hasattr(self, '_pre_backtest_state') and self._pre_backtest_state:
                state_manager.restore_state(self._pre_backtest_state)

            # Stop thread if running
            if self._thread and self._thread.isRunning():
                self._thread.stop()
                if not self._thread.wait(2000):
                    logger.warning("[BacktestWindow] Thread did not stop gracefully")

            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[BacktestWindow.closeEvent] {e}", exc_info=True)
            super().closeEvent(event)