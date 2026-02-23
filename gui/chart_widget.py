# chart_widget.py - Multi-instrument tabbed chart with market structure only.
# ── TABS ──────────────────────────────────────────────────────────────────────
#   MultiChartWidget  - QTabWidget containing three ChartWidget tabs:
#                           "📈 Spot (Index)"  → derivative_trend  (index OHLCV)
#                           "☎ ATM Call"       → call_trend        (call option)
#                           "🔻 ATM Put"        → put_trend         (put option)
#
#   Usage in TradingGUI:
#       self.chart_widget = MultiChartWidget()        # replaces ChartWidget()
#       self.chart_widget.set_config(config, engine)  # once, after init
#       ...
#       # In _do_chart_update():
#       state = self.trading_app.state
#       self.chart_widget.update_charts(
#           spot_data  = getattr(state, "derivative_trend",  {}) or {},
#           call_data  = getattr(state, "call_trend",        {}) or {},
#           put_data   = getattr(state, "put_trend",         {}) or {},
#       )
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import logging.handlers
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Callable, Union
import traceback

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from PyQt5.QtCore import QObject, QSize, QTimer, pyqtSignal, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import (
    QTabWidget, QVBoxLayout, QWidget, QLabel, QFrame, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QScrollArea,
)

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
#  INDICATOR REGISTRY  (cleared - no indicators)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class IndicatorSpec:
    key: str
    trend_keys: Dict[str, str]
    panel_type: str  # "overlay" | "subplot"
    render_fn: Callable
    y_range: Optional[List[float]] = None
    y_label: str = ""
    config_flag: Optional[str] = None


# Empty registry - no indicators
INDICATOR_REGISTRY: List[IndicatorSpec] = []

_REGISTRY: Dict[str, IndicatorSpec] = {}

ENGINE_KEY_TO_PANEL: Dict[str, str] = {}


def _resolve_active_panels(config, signal_engine) -> List[str]:
    """Return ordered registry keys to render - always empty now."""
    try:
        return []
    except Exception as e:
        logger.error(f"[_resolve_active_panels] Failed: {e}", exc_info=True)
        return []


def _load_series(spec: IndicatorSpec, trend_data: Dict,
                 clean_fn: Callable) -> Dict[str, List]:
    out = {}
    try:
        for alias, dot_path in spec.trend_keys.items():
            parts = dot_path.split(".", 1)
            raw = trend_data.get(parts[0])
            if len(parts) == 2 and isinstance(raw, dict):
                raw = raw.get(parts[1])
            out[alias] = (raw if alias == "direction" and isinstance(raw, list)
                          else clean_fn(raw))
        return out
    except Exception as e:
        logger.error(f"[_load_series] Failed: {e}", exc_info=True)
        return {}


# ── Timestamp helpers ─────────────────────────────────────────────────────────

def _ts_to_label(ts: Any) -> str:
    """Convert a Unix timestamp (seconds) to 'HH:MM' string."""
    try:
        if ts is None:
            return "N/A"
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M")
    except (ValueError, TypeError, OSError) as e:
        logger.debug(f"_ts_to_label failed for {ts}: {e}")
        return str(ts)
    except Exception as e:
        logger.error(f"[_ts_to_label] Unexpected error: {e}", exc_info=True)
        return str(ts)


def _build_x_axis(trend_data: Dict, n: int) -> List:
    """
    Return x-axis values.  Prefers 'timestamps' key (list of Unix seconds).
    Falls back to bar indices (0..n-1).
    """
    try:
        if not trend_data:
            return list(range(n))

        ts = trend_data.get("timestamps")
        if ts and isinstance(ts, (list, tuple)) and len(ts) == n:
            try:
                labels = [_ts_to_label(t) for t in ts]
                return labels
            except Exception as e:
                logger.warning(f"Failed to convert timestamps: {e}")
                return list(range(n))
        return list(range(n))
    except Exception as e:
        logger.error(f"[_build_x_axis] Failed: {e}", exc_info=True)
        return list(range(n))


# ═════════════════════════════════════════════════════════════════════════════
#  Market structure helpers  (unchanged)
# ═════════════════════════════════════════════════════════════════════════════

class StructureType(Enum):
    HH = "Higher High"
    HL = "Higher Low"
    LH = "Lower High"
    LL = "Lower Low"
    NONE = "None"


@dataclass
class PivotPoint:
    index: int
    price: float
    type: str  # 'high' | 'low'
    strength: int  # 1–3
    structure: StructureType = StructureType.NONE


class ChartUpdater(QObject):
    """# PYQT: Worker object for chart updates"""
    update_requested = pyqtSignal(object)
    update_completed = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        # Rule 2: Safe defaults
        try:
            super().__init__(parent)
        except Exception as e:
            logger.error(f"[ChartUpdater.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)


class MarketStructureAnalyzer:
    def __init__(self, left_bars: int = 5, right_bars: int = 5):
        # Rule 2: Safe defaults
        self.left_bars = 5
        self.right_bars = 5

        try:
            # Rule 6: Input validation
            if isinstance(left_bars, (int, float)) and left_bars > 0:
                self.left_bars = int(left_bars)
            if isinstance(right_bars, (int, float)) and right_bars > 0:
                self.right_bars = int(right_bars)
        except Exception as e:
            logger.error(f"[MarketStructureAnalyzer.__init__] Failed: {e}", exc_info=True)

    def find_pivot_points(self, high: List[float], low: List[float]) -> List[PivotPoint]:
        try:
            # Rule 6: Input validation
            if not high or not low:
                return []

            if len(high) < self.left_bars + self.right_bars + 1:
                return []

            pivots = []
            n = len(high)

            for i in range(self.left_bars, n - self.right_bars):
                try:
                    # Check for pivot high
                    is_ph = all(high[j] < high[i]
                                for j in range(i - self.left_bars, i + self.right_bars + 1)
                                if j != i and j < len(high))
                    if is_ph:
                        diffs = [high[i] - high[j]
                                 for j in range(i - self.left_bars, i + self.right_bars + 1)
                                 if j != i and j < len(high)]
                        avg = sum(diffs) / len(diffs) if diffs else 0
                        rng = (max(high) - min(high)) or 1
                        s = 3 if avg > rng * 0.05 else 2 if avg > rng * 0.02 else 1
                        pivots.append(PivotPoint(i, high[i], 'high', s))

                    # Check for pivot low
                    is_pl = all(low[j] > low[i]
                                for j in range(i - self.left_bars, i + self.right_bars + 1)
                                if j != i and j < len(low))
                    if is_pl:
                        diffs = [low[j] - low[i]
                                 for j in range(i - self.left_bars, i + self.right_bars + 1)
                                 if j != i and j < len(low)]
                        avg = sum(diffs) / len(diffs) if diffs else 0
                        rng = (max(high) - min(low)) or 1
                        s = 3 if avg > rng * 0.05 else 2 if avg > rng * 0.02 else 1
                        pivots.append(PivotPoint(i, low[i], 'low', s))

                except Exception as e:
                    logger.debug(f"Error processing pivot at index {i}: {e}")
                    continue

            return pivots

        except Exception as e:
            logger.error(f"[MarketStructureAnalyzer.find_pivot_points] Failed: {e}", exc_info=True)
            return []

    def identify_structure(self, pivots: List[PivotPoint]) -> List[PivotPoint]:
        try:
            if len(pivots) < 2:
                return pivots

            pivots.sort(key=lambda x: x.index)

            for i in range(1, len(pivots)):
                try:
                    c, p = pivots[i], pivots[i - 1]
                    if c.type == 'high' and p.type == 'high':
                        c.structure = StructureType.HH if c.price > p.price else StructureType.LH
                    elif c.type == 'low' and p.type == 'low':
                        c.structure = StructureType.HL if c.price > p.price else StructureType.LL
                except Exception as e:
                    logger.debug(f"Error identifying structure at index {i}: {e}")
                    continue

            return pivots

        except Exception as e:
            logger.error(f"[MarketStructureAnalyzer.identify_structure] Failed: {e}", exc_info=True)
            return pivots

    def get_trend_lines(self, pivots: List[PivotPoint]) -> Dict[str, List[Tuple[int, float]]]:
        try:
            up, dn = [], []
            for p in pivots:
                if p.structure == StructureType.HL:
                    up.append((p.index, p.price))
                elif p.structure == StructureType.LH:
                    dn.append((p.index, p.price))
            return {"uptrend": up, "downtrend": dn}
        except Exception as e:
            logger.error(f"[MarketStructureAnalyzer.get_trend_lines] Failed: {e}", exc_info=True)
            return {"uptrend": [], "downtrend": []}

    def get_market_phase(self, pivots: List[PivotPoint]) -> str:
        try:
            if len(pivots) < 4:
                return 'neutral'

            recent = pivots[-4:]
            hh = sum(1 for p in recent if p.structure == StructureType.HH)
            hl = sum(1 for p in recent if p.structure == StructureType.HL)
            lh = sum(1 for p in recent if p.structure == StructureType.LH)
            ll = sum(1 for p in recent if p.structure == StructureType.LL)

            if hh >= 2 and hl >= 2:
                return 'uptrend'
            if lh >= 2 and ll >= 2:
                return 'downtrend'
            if len(set(p.structure for p in recent)) >= 3:
                return 'ranging'
            return 'neutral'

        except Exception as e:
            logger.error(f"[MarketStructureAnalyzer.get_market_phase] Failed: {e}", exc_info=True)
            return 'neutral'


# ═════════════════════════════════════════════════════════════════════════════
#  ChartWidget  — single-instrument chart (price + structure only)
# ═════════════════════════════════════════════════════════════════════════════

class ChartWidget(QWebEngineView):
    """
    Market-structure candlestick chart with price and pivot points only.

    USAGE
    ─────
    1. chart.set_config(config, signal_engine)   # once at startup / after strategy change
    2. chart.update_chart(trend_data)            # on every new bar
    """

    DARK_BG = "#0d1117"
    CARD_BG = "#161b22"
    TEXT_COLOR = "#e6edf3"
    GRID_COLOR = "#30363d"

    COLORS = {
        "candle_up": "#3fb950", "candle_down": "#f85149",
        "pivot_high": "#f0883e", "pivot_low": "#58a6ff",
        "hh": "#7ee37d", "hl": "#58a6ff",
        "lh": "#f85149", "ll": "#db6d28",
        "trend_up": "#3fb950", "trend_down": "#f85149",
        "text": "#8b949e",
        "vol_up": "rgba(63,185,80,0.45)",
        "vol_down": "rgba(248,81,73,0.45)",
    }

    _MAIN_RATIO = 0.70
    _VOL_RATIO = 0.30

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setStyleSheet(f"background: {self.DARK_BG}; border: none;")
            self.setMinimumSize(QSize(400, 300))

            self._config = None
            self._signal_engine = None
            self._active_keys: List[str] = []
            self._config_set = False

            self.analyzer = MarketStructureAnalyzer(left_bars=5, right_bars=5)

            self._last_data_fingerprint = ""
            self._pending_data = None
            self._update_timer = QTimer()
            self._update_timer.setSingleShot(True)
            self._update_timer.timeout.connect(self._perform_update)

            self._html_cache = {}
            self._max_cache_size = 5
            self._error_count = 0
            self._max_errors = 3

            self.updater = ChartUpdater()
            self.updater.update_requested.connect(self.update_chart)

            self._show_placeholder()

            logger.debug("ChartWidget initialized")

        except Exception as e:
            logger.critical(f"[ChartWidget.__init__] Failed: {e}", exc_info=True)
            # Still try to initialize
            super().__init__(parent)
            self.setStyleSheet(f"background: {self.DARK_BG}; border: none;")
            self.setMinimumSize(QSize(400, 300))
            self._show_error_placeholder(str(e))

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._config = None
        self._signal_engine = None
        self._active_keys = []
        self._config_set = False
        self.analyzer = None
        self._last_data_fingerprint = ""
        self._pending_data = None
        self._update_timer = None
        self._html_cache = {}
        self._max_cache_size = 5
        self._error_count = 0
        self._max_errors = 3
        self.updater = None
        self.DARK_BG = "#0d1117"
        self.CARD_BG = "#161b22"
        self.TEXT_COLOR = "#e6edf3"
        self.GRID_COLOR = "#30363d"
        self.COLORS = {
            "candle_up": "#3fb950", "candle_down": "#f85149",
            "pivot_high": "#f0883e", "pivot_low": "#58a6ff",
            "hh": "#7ee37d", "hl": "#58a6ff",
            "lh": "#f85149", "ll": "#db6d28",
            "trend_up": "#3fb950", "trend_down": "#f85149",
            "text": "#8b949e",
            "vol_up": "rgba(63,185,80,0.45)",
            "vol_down": "rgba(248,81,73,0.45)",
        }
        self._MAIN_RATIO = 0.70
        self._VOL_RATIO = 0.30

    # ── Public API ────────────────────────────────────────────────────────────

    def set_config(self, config, signal_engine=None) -> None:
        """
        Attach Config + optional DynamicSignalEngine.
        Call at startup and again after strategy changes.
        """
        try:
            self._config = config
            self._signal_engine = signal_engine
            self._active_keys = _resolve_active_panels(config, signal_engine)
            self._config_set = True

            # Bust cache
            self._last_data_fingerprint = ""
            self._html_cache.clear()

            logger.debug("ChartWidget config set")

        except Exception as e:
            logger.error(f"[ChartWidget.set_config] Failed: {e}", exc_info=True)

    def update_chart(self, trend_data: dict):
        """Thread-safe chart update — throttled to prevent flicker."""
        try:
            if not trend_data:
                logger.debug("update_chart called with empty data")
                return

            # Auto-resolve panels if set_config was never called
            if not self._config_set:
                self._active_keys = _resolve_active_panels(None, None)
                logger.debug("ChartWidget: set_config not yet called; rendering price + structure only.")

            fp = self._fingerprint(trend_data)
            if fp == self._last_data_fingerprint or fp == "":
                return

            self._error_count = 0
            self._last_data_fingerprint = fp

            if fp in self._html_cache:
                try:
                    self.setHtml(self._html_cache[fp])
                except Exception as e:
                    logger.warning(f"Failed to set cached HTML: {e}")
                    # Fall through to regenerate
                else:
                    return

            self._pending_data = trend_data
            if self._update_timer:
                self._update_timer.start(300)

        except Exception as e:
            logger.error(f"update_chart failed: {e}", exc_info=True)
            self._error_count += 1
            if self._error_count >= self._max_errors:
                self._show_error_placeholder(str(e))

    def clear_cache(self):
        try:
            self._html_cache.clear()
        except Exception as e:
            logger.error(f"[ChartWidget.clear_cache] Failed: {e}", exc_info=True)

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
            self._last_data_fingerprint = ""
            if hasattr(self, 'updater') and self._pending_data is not None:
                self.updater.update_requested.emit(self._pending_data)
        except Exception as e:
            logger.error(f"[ChartWidget.resizeEvent] Failed: {e}", exc_info=True)
            super().resizeEvent(event)

    # ── Placeholders ──────────────────────────────────────────────────────────

    def _show_placeholder(self, message: str = "Waiting for market data…"):
        try:
            html = f"""<!DOCTYPE html><html><head><style>
                body{{background:{self.DARK_BG};display:flex;align-items:center;
                     justify-content:center;height:100vh;margin:0;
                     font-family:'Segoe UI',sans-serif;}}
                .msg{{color:#8b949e;font-size:16px;text-align:center;padding:20px;}}
                .spin{{border:3px solid {self.CARD_BG};
                       border-top:3px solid {self.COLORS['pivot_low']};
                       border-radius:50%;width:40px;height:40px;
                       animation:spin 1s linear infinite;margin:20px auto;}}
                @keyframes spin{{0%{{transform:rotate(0deg)}}100%{{transform:rotate(360deg)}}}}
            </style></head><body>
                <div class="msg"><div class="spin"></div><div>📊 {message}</div></div>
            </body></html>"""
            self.setHtml(html)
        except Exception as e:
            logger.error(f"[ChartWidget._show_placeholder] Failed: {e}", exc_info=True)

    def _show_error_placeholder(self, error_msg: str):
        try:
            html = f"""<!DOCTYPE html><html><head><style>
                body{{background:{self.DARK_BG};display:flex;align-items:center;
                     justify-content:center;height:100vh;margin:0;
                     font-family:'Segoe UI',sans-serif;}}
                .err{{color:{self.COLORS['candle_down']};font-size:14px;text-align:center;
                      padding:20px;border:1px solid {self.COLORS['candle_down']};
                      border-radius:6px;background:rgba(248,81,73,.1);}}
            </style></head><body>
                <div class="err">❌ Chart Error: {error_msg}</div>
            </body></html>"""
            self.setHtml(html)
        except Exception as e:
            logger.error(f"[ChartWidget._show_error_placeholder] Failed: {e}", exc_info=True)

    # ── Fingerprint ───────────────────────────────────────────────────────────

    def _fingerprint(self, trend_data: Optional[Dict]) -> str:
        try:
            if not trend_data or not isinstance(trend_data, dict):
                return ""

            close = trend_data.get("close") or []
            if not close or not isinstance(close, (list, np.ndarray)):
                return ""

            if isinstance(close, np.ndarray):
                close = close.tolist()

            n = len(close)
            if n == 0:
                return ""

            last = close[-5:] if n >= 5 else close

            # Safely format values
            try:
                formatted = []
                for v in last:
                    if isinstance(v, (int, float)):
                        formatted.append(str(round(v, 4)))
                    else:
                        formatted.append(str(v))
                return f"{n}:{formatted}"
            except Exception as e:
                logger.debug(f"Fingerprint formatting failed: {e}")
                return f"{n}"

        except Exception as e:
            logger.debug(f"Fingerprint failed: {e}")
            return ""

    # ── Data cleaning ─────────────────────────────────────────────────────────

    def _clean_data(self, raw: Any) -> List[float]:
        if raw is None:
            return []

        try:
            if isinstance(raw, np.ndarray):
                raw = raw.tolist()

            if not isinstance(raw, (list, tuple)):
                return []

            cleaned = []
            for x in raw:
                try:
                    if x is None:
                        cleaned.append(None)
                    elif isinstance(x, (int, float)) and not np.isnan(x):
                        cleaned.append(float(x))
                    elif isinstance(x, str):
                        xl = x.lower().strip()
                        if xl in ("nan", "none", "null", ""):
                            cleaned.append(None)
                        else:
                            try:
                                cleaned.append(float(x))
                            except ValueError:
                                cleaned.append(None)
                    else:
                        cleaned.append(None)
                except Exception:
                    cleaned.append(None)
            return cleaned

        except Exception as e:
            logger.error(f"_clean_data failed: {e}", exc_info=True)
            return []

    # ── Timer callback ────────────────────────────────────────────────────────

    def _perform_update(self):
        if self._pending_data is None:
            return

        trend_data = self._pending_data
        self._pending_data = None

        try:
            html = self._generate_chart_html(trend_data)
            if html:
                fp = self._fingerprint(trend_data)
                if fp and len(self._html_cache) < self._max_cache_size:
                    self._html_cache[fp] = html
                self.setHtml(html)
                if hasattr(self, 'updater') and self.updater:
                    self.updater.update_completed.emit(True, "Chart updated")
            else:
                self._show_placeholder("Insufficient data for chart")

        except Exception as e:
            logger.error(f"Chart update error: {e}", exc_info=True)
            self._show_error_placeholder(str(e))
            if hasattr(self, 'updater') and self.updater:
                self.updater.update_completed.emit(False, str(e))

    # ── Core renderer ─────────────────────────────────────────────────────────

    def _generate_chart_html(self, trend_data: Dict,
                             title_prefix: str = "") -> Optional[str]:
        if not trend_data or not isinstance(trend_data, dict):
            return None

        try:
            # ── 1. Price data ─────────────────────────────────────────────────
            open_p = self._clean_data(trend_data.get("open"))
            high = self._clean_data(trend_data.get("high"))
            low = self._clean_data(trend_data.get("low"))
            close = self._clean_data(trend_data.get("close"))
            volume = self._clean_data(trend_data.get("volume"))
            sym = trend_data.get("name", title_prefix or "Instrument")

            if not close:
                logger.debug("No close data for chart")
                return None

            n = len(close)
            if n < 10:
                logger.debug(f"Insufficient data points: {n}")
                return None

            # Use timestamps if available
            x = _build_x_axis(trend_data, n)

            if not high:
                high = close
            if not low:
                low = close

            # ── 2. Market structure ───────────────────────────────────────────
            pivots = []
            if self.analyzer:
                try:
                    pivots = self.analyzer.find_pivot_points(high, low)
                    pivots = self.analyzer.identify_structure(pivots)
                except Exception as e:
                    logger.warning(f"Market structure analysis failed: {e}")

            trend_lines = {"uptrend": [], "downtrend": []}
            phase = "neutral"

            if self.analyzer:
                try:
                    trend_lines = self.analyzer.get_trend_lines(pivots) if pivots else {"uptrend": [], "downtrend": []}
                    phase = self.analyzer.get_market_phase(pivots) if pivots else "neutral"
                except Exception as e:
                    logger.warning(f"Trend analysis failed: {e}")

            # ── 3. Signal annotation ──────────────────────────────────────────
            opt_signal = trend_data.get("option_signal") or {}
            signal_value = (opt_signal.get("signal_value", "")
                            if isinstance(opt_signal, dict) else "")

            # ── 4. Determine rows ─────────────────────────────────────────────
            has_vol = bool(volume and len(volume) == n)
            n_rows = 1 + (1 if has_vol else 0)
            row_heights = [self._MAIN_RATIO]
            if has_vol:
                row_heights.append(self._VOL_RATIO)

            # ── 5. Figure ─────────────────────────────────────────────────────
            fig = make_subplots(
                rows=n_rows, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=row_heights,
                specs=[[{"type": "xy"}]] * n_rows,
            )

            # ── 6. Price trace ────────────────────────────────────────────────
            if open_p and len(open_p) == n:
                fig.add_trace(go.Candlestick(
                    x=x, open=open_p, high=high, low=low, close=close,
                    name="Price",
                    increasing=dict(line=dict(color=self.COLORS["candle_up"]),
                                    fillcolor=self.COLORS["candle_up"]),
                    decreasing=dict(line=dict(color=self.COLORS["candle_down"]),
                                    fillcolor=self.COLORS["candle_down"]),
                    showlegend=False,
                ), row=1, col=1)
            else:
                fig.add_trace(go.Scatter(
                    x=x, y=close, name="Price",
                    line=dict(color="#58a6ff", width=2),
                    hovertemplate="Price: %{y:.2f}<extra></extra>",
                    showlegend=False,
                ), row=1, col=1)

            # ── 7. Pivot points ───────────────────────────────────────────────
            if pivots:
                px_, py_, pt_, pcol, psym = [], [], [], [], []
                for pv in pivots:
                    try:
                        idx = pv.index if pv.index < len(x) else len(x) - 1
                        px_.append(x[idx] if idx >= 0 else pv.index)
                        py_.append(pv.price)

                        if pv.structure == StructureType.HH:
                            pcol.append(self.COLORS["hh"])
                            psym.append("triangle-up")
                            pt_.append(f"HH {pv.price:.2f}")
                        elif pv.structure == StructureType.HL:
                            pcol.append(self.COLORS["hl"])
                            psym.append("triangle-up")
                            pt_.append(f"HL {pv.price:.2f}")
                        elif pv.structure == StructureType.LH:
                            pcol.append(self.COLORS["lh"])
                            psym.append("triangle-down")
                            pt_.append(f"LH {pv.price:.2f}")
                        elif pv.structure == StructureType.LL:
                            pcol.append(self.COLORS["ll"])
                            psym.append("triangle-down")
                            pt_.append(f"LL {pv.price:.2f}")
                        else:
                            c = self.COLORS["pivot_high"] if pv.type == 'high' else self.COLORS["pivot_low"]
                            pcol.append(c)
                            psym.append("circle")
                            pt_.append(f"Pivot {pv.price:.2f}")
                    except Exception as e:
                        logger.debug(f"Error processing pivot point: {e}")
                        continue

                if px_:
                    fig.add_trace(go.Scatter(
                        x=px_, y=py_, mode="markers+text", name="Pivots",
                        marker=dict(size=[8 + p.strength * 2 for p in pivots[:len(px_)]],
                                    color=pcol, symbol=psym,
                                    line=dict(width=1, color="white")),
                        text=[p.structure.value[:2] if p.structure != StructureType.NONE else ""
                              for p in pivots[:len(px_)]],
                        textposition="top center",
                        textfont=dict(size=9, color="white"),
                        hovertemplate="%{text}<extra></extra>",
                        showlegend=False,
                    ), row=1, col=1)

            # ── 8. Trend lines ────────────────────────────────────────────────
            if trend_lines:
                for direction, col_key, label in (
                        ("uptrend", "trend_up", "Uptrend"),
                        ("downtrend", "trend_down", "Downtrend"),
                ):
                    pts = trend_lines.get(direction, [])
                    if len(pts) >= 2:
                        try:
                            xi, yi = zip(*pts)
                            xi_lbl = [x[i] if i < len(x) else i for i in xi]
                            fig.add_trace(go.Scatter(
                                x=xi_lbl, y=yi, mode="lines", name=label,
                                line=dict(color=self.COLORS[col_key], width=2),
                                opacity=0.7, showlegend=True,
                            ), row=1, col=1)
                        except Exception as e:
                            logger.debug(f"Error adding trend line {direction}: {e}")

            # ── 9. Recent high / low reference lines ─────────────────────────
            if pivots:
                try:
                    hp = [p for p in pivots[-5:] if p.type == 'high']
                    lp = [p for p in pivots[-5:] if p.type == 'low']
                    if hp:
                        rh = max(p.price for p in hp)
                        fig.add_hline(y=rh, row=1, col=1,
                                      line=dict(color=self.COLORS["pivot_high"],
                                                dash="dash", width=1),
                                      annotation_text=f"R {rh:.2f}",
                                      annotation_position="right")
                    if lp:
                        rl = min(p.price for p in lp)
                        fig.add_hline(y=rl, row=1, col=1,
                                      line=dict(color=self.COLORS["pivot_low"],
                                                dash="dash", width=1),
                                      annotation_text=f"S {rl:.2f}",
                                      annotation_position="right")
                except Exception as e:
                    logger.debug(f"Error adding reference lines: {e}")

            # ── 10. Volume panel ──────────────────────────────────────────────
            if has_vol:
                vol_colors = []
                for i, v in enumerate(volume):
                    if v is None or i == 0:
                        vol_colors.append(self.COLORS["vol_up"])
                    elif close[i] is not None and close[i - 1] is not None:
                        vol_colors.append(
                            self.COLORS["vol_up"] if close[i] >= close[i - 1]
                            else self.COLORS["vol_down"])
                    else:
                        vol_colors.append(self.COLORS["vol_up"])

                fig.add_trace(go.Bar(
                    x=x, y=volume, name="Volume",
                    marker_color=vol_colors,
                    hovertemplate="Vol: %{y:,.0f}<extra></extra>",
                    showlegend=False,
                ), row=2, col=1)

                fig.update_yaxes(title_text="Vol",
                                 title_font=dict(size=8, color=self.COLORS["text"]),
                                 row=2, col=1)

            # ── 11. Signal annotation ─────────────────────────────────────────
            _SIG = {
                "BUY_CALL": ("#a6e3a1", "📈"),
                "BUY_PUT": ("#89b4fa", "📉"),
                "SELL_CALL": ("#f38ba8", "🔴"),
                "SELL_PUT": ("#fab387", "🔵"),
                "HOLD": ("#f9e2af", "⏸"),
            }
            if signal_value in _SIG:
                try:
                    sc, ico = _SIG[signal_value]
                    last_c = next((v for v in reversed(close) if v is not None), None)
                    if last_c is not None:
                        fig.add_annotation(
                            x=x[-1], y=last_c,
                            text=f"  {ico} {signal_value}", showarrow=False,
                            font=dict(size=11, color=sc), xanchor="left",
                            bgcolor=f"{sc}33", bordercolor=sc, borderwidth=1,
                            row=1, col=1,
                        )
                except Exception as e:
                    logger.debug(f"Error adding signal annotation: {e}")

            # ── 12. Layout ────────────────────────────────────────────────────
            title_text = f"{sym}  —  {phase.upper()}"
            if title_prefix:
                title_text = f"{title_prefix} - {title_text}"

            fig.update_layout(
                title=dict(
                    text=(f"{sym}  —  {phase.upper()}"
                          f"<br><sup style='color:{self.COLORS['text']};font-size:10px'>"
                          f"Price Structure Only</sup>"),
                    font=dict(color=self.TEXT_COLOR, size=13),
                ),
                paper_bgcolor=self.DARK_BG,
                plot_bgcolor=self.CARD_BG,
                font=dict(color=self.TEXT_COLOR,
                          family="Segoe UI, sans-serif", size=11),
                legend=dict(
                    bgcolor=self.CARD_BG, bordercolor=self.GRID_COLOR,
                    borderwidth=1, font=dict(size=10),
                    orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1,
                ),
                margin=dict(l=50, r=80, t=60, b=20),
                hovermode="x unified",
                hoverlabel=dict(bgcolor=self.CARD_BG,
                                font_size=10, font_family="Consolas, monospace"),
                xaxis_rangeslider_visible=False,
            )

            # ── 13. Axis styling ──────────────────────────────────────────────
            fig.update_xaxes(gridcolor=self.GRID_COLOR, zeroline=False,
                             showgrid=True, tickfont=dict(size=9),
                             showticklabels=False)
            fig.update_xaxes(showticklabels=True,
                             title="Time" if isinstance(x[0], str) else "Bar",
                             row=n_rows, col=1)
            fig.update_yaxes(gridcolor=self.GRID_COLOR, zeroline=False,
                             showgrid=True, tickfont=dict(size=9))
            fig.update_yaxes(title="Price", row=1, col=1)

            # ── 14. Serialise ─────────────────────────────────────────────────
            html = fig.to_html(
                include_plotlyjs="cdn", full_html=True,
                config={
                    "displayModeBar": True, "displaylogo": False,
                    "responsive": True, "scrollZoom": True,
                    "doubleClick": "reset",
                    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                },
            )
            css = """<style>
                .plotly-graph-div,.js-plotly-plot{width:100%;height:100%;}
                .main-svg{contain:strict;}
                .hovertext text{fill:#e6edf3!important;}
            </style>
            <meta name="viewport" content="width=device-width,initial-scale=1.0">"""
            html = html.replace("</head>", css + "</head>")
            return html

        except Exception as e:
            logger.error(f"_generate_chart_html failed: {e}", exc_info=True)
            return None


# ═════════════════════════════════════════════════════════════════════════════
#  _SignalDataTab  — live indicator values + rule results (4th chart tab)
# ═════════════════════════════════════════════════════════════════════════════

_SD_BG = "#0d1117"
_SD_PANEL = "#161b22"
_SD_ROW_A = "#1c2128"
_SD_ROW_B = "#22272e"
_SD_BORDER = "#30363d"
_SD_TEXT = "#e6edf3"
_SD_DIM = "#8b949e"
_SD_GREEN = "#3fb950"
_SD_RED = "#f85149"
_SD_YELLOW = "#d29922"
_SD_BLUE = "#58a6ff"
_SD_ORANGE = "#ffa657"
_SD_GREY = "#484f58"

_SIG_COLORS = {
    "BUY_CALL": "#3fb950", "BUY_PUT": "#58a6ff",
    "SELL_CALL": "#f85149", "SELL_PUT": "#ffa657",
    "HOLD": "#d29922", "WAIT": "#484f58",
}
_SIG_LABELS = {
    "BUY_CALL": "📈  Buy Call", "BUY_PUT": "📉  Buy Put",
    "SELL_CALL": "🔴  Sell Call", "SELL_PUT": "🟠  Sell Put",
    "HOLD": "⏸   Hold", "WAIT": "⏳  Wait",
}
_SIG_GROUPS = ["BUY_CALL", "BUY_PUT", "SELL_CALL", "SELL_PUT", "HOLD"]


class _SignalDataTab(QWidget):
    """
    Self-contained tab widget showing:
      • Current signal badge + per-group fired pills
      • Indicator Values table  (from option_signal["indicator_values"])
      • Rule Results table       (from option_signal["rule_results"])

    Call  refresh(option_signal_dict)  on every chart update.
    option_signal is already present inside spot_data["option_signal"].
    """

    # ── Stylesheet ─────────────────────────────────────────────────────────
    _SS = f"""
        QWidget, QFrame {{
            background: {_SD_BG}; color: {_SD_TEXT};
            font-family: 'Segoe UI', 'Consolas', monospace;
        }}
        QLabel {{ color: {_SD_TEXT}; background: transparent; }}
        QTableWidget {{
            background: {_SD_PANEL}; gridline-color: {_SD_BORDER};
            border: 1px solid {_SD_BORDER}; border-radius: 4px;
            color: {_SD_TEXT}; font-size: 9pt;
        }}
        QTableWidget::item {{ padding: 5px 10px; }}
        QHeaderView::section {{
            background: #21262d; color: {_SD_DIM};
            border: none; border-bottom: 1px solid {_SD_BORDER};
            padding: 5px 10px; font-size: 8pt; font-weight: bold;
        }}
        QScrollArea {{ border: none; background: transparent; }}
    """

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setStyleSheet(self._SS)
            root = QVBoxLayout(self)
            root.setContentsMargins(12, 12, 12, 8)
            root.setSpacing(10)

            # ── Top: signal badge + group pills ───────────────────────────────
            top = QHBoxLayout()
            top.setSpacing(16)

            # Signal badge column
            sig_col = QVBoxLayout()
            sig_col.setSpacing(3)
            sig_col.addWidget(self._dim_lbl("CURRENT SIGNAL"))
            self._badge = QLabel(_SIG_LABELS["WAIT"])
            self._badge.setAlignment(Qt.AlignCenter)
            self._badge.setFixedHeight(38)
            self._badge.setMinimumWidth(150)
            self._badge.setStyleSheet(self._badge_ss(_SD_GREY))
            sig_col.addWidget(self._badge)
            top.addLayout(sig_col)

            top.addWidget(self._vline())

            # Conflict badge
            self._conflict_badge = QLabel("  NO CONFLICT  ")
            self._conflict_badge.setAlignment(Qt.AlignCenter)
            self._conflict_badge.setFixedHeight(24)
            self._conflict_badge.setStyleSheet(
                f"color:{_SD_GREY}; background:{_SD_GREY}18; border:1px solid {_SD_GREY};"
                f" border-radius:4px; font-size:8pt; font-weight:bold; padding:1px 8px;"
            )
            sig_col.addWidget(self._conflict_badge)

            # Group pills column
            pills_col = QVBoxLayout()
            pills_col.setSpacing(3)
            pills_col.addWidget(self._dim_lbl("GROUP STATUS"))
            pills_row = QHBoxLayout()
            pills_row.setSpacing(8)
            self._pills: Dict[str, QLabel] = {}
            for sig in _SIG_GROUPS:
                p = QLabel(sig.replace("_", "\n"))
                p.setAlignment(Qt.AlignCenter)
                p.setFixedSize(80, 46)
                p.setStyleSheet(self._pill_ss(sig, False))
                self._pills[sig] = p
                pills_row.addWidget(p)
            pills_row.addStretch()
            pills_col.addLayout(pills_row)
            top.addLayout(pills_col, 1)

            root.addLayout(top)
            root.addWidget(self._hline())

            # ── Scrollable body ────────────────────────────────────────────────
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            body = QWidget()
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(0, 4, 4, 4)
            body_layout.setSpacing(14)

            # No-data placeholder
            self._no_data_lbl = QLabel("⚪  Waiting for first signal evaluation…")
            self._no_data_lbl.setAlignment(Qt.AlignCenter)
            self._no_data_lbl.setStyleSheet(
                f"color:{_SD_GREY}; font-size:10pt; padding:30px;"
            )
            body_layout.addWidget(self._no_data_lbl)

            # Indicator values section
            body_layout.addWidget(self._section_lbl("📊  Indicator Values"))
            self._ind_table = self._make_table(
                ["Indicator", "Current Value", "Prev Value"],
                [QHeaderView.Stretch, QHeaderView.ResizeToContents, QHeaderView.ResizeToContents],
            )
            body_layout.addWidget(self._ind_table)

            # Rule results section
            body_layout.addWidget(self._section_lbl("🔬  Rule Results  (last evaluation)"))
            self._rule_table = self._make_table(
                ["Group", "Rule Expression", "Actual Values", "Result"],
                [QHeaderView.ResizeToContents, QHeaderView.Stretch,
                 QHeaderView.ResizeToContents, QHeaderView.ResizeToContents],
            )
            body_layout.addWidget(self._rule_table)
            body_layout.addStretch()
            scroll.setWidget(body)
            root.addWidget(scroll, 1)

            # ── Footer timestamp ───────────────────────────────────────────────
            self._ts_lbl = QLabel("Not yet updated")
            self._ts_lbl.setAlignment(Qt.AlignRight)
            self._ts_lbl.setStyleSheet(f"color:{_SD_GREY}; font-size:8pt; padding-right:4px;")
            root.addWidget(self._ts_lbl)

            logger.debug("_SignalDataTab initialized")

        except Exception as e:
            logger.critical(f"[_SignalDataTab.__init__] Failed: {e}", exc_info=True)
            # Still try to create basic widget
            super().__init__(parent)
            self._show_error_content(str(e))

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._badge = None
        self._conflict_badge = None
        self._pills = {}
        self._no_data_lbl = None
        self._ind_table = None
        self._rule_table = None
        self._ts_lbl = None

    def _show_error_content(self, error_msg: str):
        """Show error message if initialization fails"""
        try:
            layout = QVBoxLayout(self)
            error_lbl = QLabel(f"❌ Error initializing signal tab: {error_msg}")
            error_lbl.setStyleSheet(f"color: {_SD_RED}; padding: 20px;")
            error_lbl.setWordWrap(True)
            layout.addWidget(error_lbl)
        except Exception:
            pass

    # ── Static helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _make_table(headers: list, col_modes: list) -> QTableWidget:
        try:
            t = QTableWidget(0, len(headers))
            t.setHorizontalHeaderLabels(headers)
            for i, m in enumerate(col_modes):
                t.horizontalHeader().setSectionResizeMode(i, m)
            t.verticalHeader().setVisible(False)
            t.setEditTriggers(QTableWidget.NoEditTriggers)
            t.setAlternatingRowColors(True)
            t.setSelectionBehavior(QTableWidget.SelectRows)
            t.setStyleSheet(
                f"QTableWidget {{ alternate-background-color: {_SD_ROW_B}; background: {_SD_ROW_A}; }}"
            )
            t.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            return t
        except Exception as e:
            logger.error(f"[_make_table] Failed: {e}", exc_info=True)
            return QTableWidget(0, len(headers))

    @staticmethod
    def _dim_lbl(text: str) -> QLabel:
        try:
            l = QLabel(text)
            l.setStyleSheet(f"color:{_SD_DIM}; font-size:7pt; font-weight:bold;")
            return l
        except Exception as e:
            logger.error(f"[_dim_lbl] Failed: {e}", exc_info=True)
            return QLabel(text)

    @staticmethod
    def _section_lbl(text: str) -> QLabel:
        try:
            l = QLabel(text)
            l.setStyleSheet(
                f"color:{_SD_TEXT}; font-size:10pt; font-weight:bold;"
                f" border-bottom:1px solid {_SD_BORDER}; padding-bottom:4px;"
            )
            return l
        except Exception as e:
            logger.error(f"[_section_lbl] Failed: {e}", exc_info=True)
            return QLabel(text)

    @staticmethod
    def _badge_ss(color: str) -> str:
        try:
            return (
                f"QLabel {{ background:{color}22; color:{color}; border:2px solid {color};"
                f" border-radius:6px; font-size:12pt; font-weight:bold; padding:2px 14px; }}"
            )
        except Exception as e:
            logger.error(f"[_badge_ss] Failed: {e}", exc_info=True)
            return ""

    @staticmethod
    def _pill_ss(sig: str, fired: bool) -> str:
        try:
            color = _SIG_COLORS.get(sig, _SD_GREY) if fired else _SD_GREY
            alpha = "33" if fired else "18"
            border = "2px" if fired else "1px"
            return (
                f"QLabel {{ background:{color}{alpha}; color:{color};"
                f" border:{border} solid {color}; border-radius:5px;"
                f" font-size:8pt; font-weight:bold; }}"
            )
        except Exception as e:
            logger.error(f"[_pill_ss] Failed: {e}", exc_info=True)
            return ""

    @staticmethod
    def _hline() -> QFrame:
        try:
            f = QFrame()
            f.setFrameShape(QFrame.HLine)
            f.setStyleSheet(f"QFrame {{ background:{_SD_BORDER}; max-height:1px; border:none; }}")
            return f
        except Exception as e:
            logger.error(f"[_hline] Failed: {e}", exc_info=True)
            return QFrame()

    @staticmethod
    def _vline() -> QFrame:
        try:
            f = QFrame()
            f.setFrameShape(QFrame.VLine)
            f.setStyleSheet(f"QFrame {{ background:{_SD_BORDER}; max-width:1px; border:none; }}")
            return f
        except Exception as e:
            logger.error(f"[_vline] Failed: {e}", exc_info=True)
            return QFrame()

    @staticmethod
    def _cell(text: str, color: str = _SD_TEXT, bold: bool = False,
              bg: str = None, align: int = Qt.AlignVCenter | Qt.AlignLeft) -> QTableWidgetItem:
        try:
            item = QTableWidgetItem(str(text))
            item.setForeground(QColor(color))
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setTextAlignment(align)
            if bold:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            if bg:
                item.setBackground(QColor(bg))
            return item
        except Exception as e:
            logger.error(f"[_cell] Failed: {e}", exc_info=True)
            return QTableWidgetItem(str(text))

    @staticmethod
    def _humanise_key(cache_key: str) -> str:
        """'rsi_{"length": 14}' → 'RSI  (length=14)'"""
        try:
            if not cache_key:
                return ""

            import json
            idx = cache_key.find("_")
            if idx < 0:
                return cache_key

            name = cache_key[:idx].upper()
            params_json = cache_key[idx + 1:]

            try:
                params = json.loads(params_json)
                p_str = ", ".join(f"{k}={v}" for k, v in params.items())
                return f"{name}  ({p_str})" if p_str else name
            except json.JSONDecodeError:
                return cache_key

        except Exception as e:
            logger.debug(f"_humanise_key failed for {cache_key}: {e}")
            return cache_key

    # ── Public refresh ─────────────────────────────────────────────────────

    def refresh(self, option_signal: Optional[Dict]):
        """Call every time spot_data is updated. option_signal may be None."""
        try:
            from datetime import datetime

            if not option_signal or not option_signal.get("available"):
                if self._no_data_lbl:
                    self._no_data_lbl.show()
                if self._ind_table:
                    self._ind_table.setRowCount(0)
                    self._ind_table.setFixedHeight(40)
                if self._rule_table:
                    self._rule_table.setRowCount(0)
                    self._rule_table.setFixedHeight(40)
                if self._badge:
                    self._badge.setText(_SIG_LABELS["WAIT"])
                    self._badge.setStyleSheet(self._badge_ss(_SD_GREY))
                for sig in _SIG_GROUPS:
                    if sig in self._pills:
                        self._pills[sig].setStyleSheet(self._pill_ss(sig, False))
                return

            if self._no_data_lbl:
                self._no_data_lbl.hide()

            # ── Signal badge ───────────────────────────────────────────────────
            sv = option_signal.get("signal_value", "WAIT")
            color = _SIG_COLORS.get(sv, _SD_GREY)
            if self._badge:
                self._badge.setText(_SIG_LABELS.get(sv, sv))
                self._badge.setStyleSheet(self._badge_ss(color))

            # ── Conflict badge ─────────────────────────────────────────────────
            conflict = option_signal.get("conflict", False)
            if self._conflict_badge:
                if conflict:
                    self._conflict_badge.setText("  ⚠ CONFLICT  ")
                    self._conflict_badge.setStyleSheet(
                        f"color:{_SD_RED}; background:{_SD_RED}18; border:1px solid {_SD_RED};"
                        f" border-radius:4px; font-size:8pt; font-weight:bold; padding:1px 8px;"
                    )
                else:
                    self._conflict_badge.setText("  ✓ NO CONFLICT  ")
                    self._conflict_badge.setStyleSheet(
                        f"color:{_SD_GREY}; background:{_SD_GREY}18; border:1px solid {_SD_GREY};"
                        f" border-radius:4px; font-size:8pt; font-weight:bold; padding:1px 8px;"
                    )

            # ── Fired pills ────────────────────────────────────────────────────
            fired_map = option_signal.get("fired", {})
            for sig in _SIG_GROUPS:
                if sig in self._pills:
                    self._pills[sig].setStyleSheet(self._pill_ss(sig, fired_map.get(sig, False)))

            # ── Indicator values table ─────────────────────────────────────────
            ind_vals: Dict = option_signal.get("indicator_values", {})
            if self._ind_table:
                self._ind_table.setRowCount(len(ind_vals))
                for i, (k, v) in enumerate(ind_vals.items()):
                    try:
                        last = v.get("last") if isinstance(v, dict) else None
                        prev = v.get("prev") if isinstance(v, dict) else None
                        self._ind_table.setItem(i, 0, self._cell(self._humanise_key(k), _SD_DIM))
                        self._ind_table.setItem(i, 1, self._cell(
                            f"{last:.4f}" if last is not None else "N/A",
                            _SD_BLUE, bold=True, align=Qt.AlignVCenter | Qt.AlignRight))
                        self._ind_table.setItem(i, 2, self._cell(
                            f"{prev:.4f}" if prev is not None else "N/A",
                            _SD_GREY, align=Qt.AlignVCenter | Qt.AlignRight))
                    except Exception as e:
                        logger.debug(f"Error populating indicator row {i}: {e}")
                        continue
                self._ind_table.setFixedHeight(max(50, 28 * len(ind_vals) + 30))

            # ── Rule results table ─────────────────────────────────────────────
            rule_results: Dict = option_signal.get("rule_results", {})
            display_rows: List[Dict] = []

            for group in _SIG_GROUPS:
                try:
                    rules = rule_results.get(group, [])
                    grp_fired = fired_map.get(group, False)
                    grp_color = _SIG_COLORS.get(group, _SD_GREY) if grp_fired else _SD_GREY

                    # First-False blocker in AND chain
                    first_false = -1
                    if not grp_fired and rules:
                        for idx, r in enumerate(rules):
                            if not r.get("result", True):
                                first_false = idx
                                break

                    if not rules:
                        display_rows.append({
                            "group": group, "gc": grp_color, "first": True,
                            "rule": "No rules configured", "values": "—",
                            "result": None, "blocker": False,
                        })
                        continue

                    for idx, r in enumerate(rules):
                        result = r.get("result", False)
                        lhs_val = r.get("lhs_value")  # float | None
                        rhs_val = r.get("rhs_value")  # float | None
                        detail = r.get("detail", "")  # pre-formatted
                        is_blocker = (idx == first_false)

                        if detail:
                            values_str = detail
                        elif lhs_val is not None and rhs_val is not None:
                            rule_str = r.get("rule", "?")
                            op = "?"
                            for _op in ("crosses_above", "crosses_below",
                                        ">=", "<=", "!=", "==", ">", "<"):
                                if f" {_op} " in rule_str:
                                    op = _op
                                    break
                            values_str = f"{lhs_val:.4f}  {op}  {rhs_val:.4f}"
                        else:
                            values_str = "—"

                        display_rows.append({
                            "group": group, "gc": grp_color, "first": (idx == 0),
                            "rule": r.get("rule", "?"), "values": values_str,
                            "result": result, "blocker": is_blocker,
                        })
                except Exception as e:
                    logger.debug(f"Error processing group {group}: {e}")
                    continue

            if self._rule_table:
                self._rule_table.setRowCount(len(display_rows))
                for i, row in enumerate(display_rows):
                    try:
                        gc = row["gc"]
                        blocker = row["blocker"]
                        result = row["result"]

                        # Group column
                        g_text = row["group"].replace("_", " ") if row["first"] else ""
                        self._rule_table.setItem(i, 0, self._cell(g_text, gc, bold=True))

                        # Rule expression
                        r_text = ("⚠ " if blocker else "  ") + row["rule"]
                        r_color = _SD_YELLOW if blocker else _SD_TEXT
                        self._rule_table.setItem(i, 1, self._cell(
                            r_text, r_color, bold=blocker,
                            bg=_SD_RED + "14" if blocker else None))

                        # Actual values
                        self._rule_table.setItem(i, 2, self._cell(row["values"], _SD_BLUE))

                        # Result
                        if result is None:
                            rt, rc = "—", _SD_GREY
                        elif result:
                            rt, rc = "✅  True", _SD_GREEN
                        else:
                            rt, rc = "❌  False", _SD_RED
                        self._rule_table.setItem(i, 3, self._cell(
                            rt, rc, bold=True, align=Qt.AlignVCenter | Qt.AlignHCenter))
                    except Exception as e:
                        logger.debug(f"Error populating rule row {i}: {e}")
                        continue

                self._rule_table.setFixedHeight(max(50, 28 * len(display_rows) + 30))

            if self._ts_lbl:
                self._ts_lbl.setText(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            logger.error(f"[_SignalDataTab.refresh] Failed: {e}", exc_info=True)


# ═════════════════════════════════════════════════════════════════════════════
#  MultiChartWidget  — tabbed Spot / Call / Put
# ═════════════════════════════════════════════════════════════════════════════

class MultiChartWidget(QWidget):
    """
    QTabWidget exposing four tabs:
        Tab 0 → "📈  Spot"          (SpotIndex OHLCV chart)
        Tab 1 → "☎   ATM Call"      (Call option OHLCV chart)
        Tab 2 → "🔻  ATM Put"        (Put option OHLCV chart)
        Tab 3 → "🔬  Signal Data"    (live indicator values + rule results)

    Integration in TradingGUI (unchanged from three-tab version)
    ─────────────────────────
        self.chart_widget = MultiChartWidget()
        self.chart_widget.set_config(config, signal_engine)

    In _do_chart_update():
        self.chart_widget.update_charts(
            spot_data = getattr(state, "derivative_trend", {}) or {},
            call_data = getattr(state, "call_trend",       {}) or {},
            put_data  = getattr(state, "put_trend",        {}) or {},
        )

    The Signal Data tab is fed automatically from spot_data["option_signal"]
    — no extra wiring required.
    """

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self._tabs = QTabWidget()
            # EXACT stylesheet preservation
            self._tabs.setStyleSheet("""
                QTabWidget::pane {
                    border: 1px solid #30363d;
                    background: #0d1117;
                }
                QTabBar::tab {
                    background: #161b22;
                    color: #8b949e;
                    padding: 7px 18px;
                    border: 1px solid #30363d;
                    border-bottom: none;
                    font-size: 10pt;
                    font-weight: bold;
                    min-width: 130px;
                }
                QTabBar::tab:selected {
                    background: #1f6feb;
                    color: #ffffff;
                    border-color: #388bfd;
                }
                QTabBar::tab:hover:!selected {
                    background: #21262d;
                    color: #e6edf3;
                }
            """)

            self._spot_chart = ChartWidget()
            self._call_chart = ChartWidget()
            self._put_chart = ChartWidget()
            self._signal_tab = _SignalDataTab()

            self._tabs.addTab(self._spot_chart, "📈  Spot")
            self._tabs.addTab(self._call_chart, "☎   ATM Call")
            self._tabs.addTab(self._put_chart, "🔻  ATM Put")
            self._tabs.addTab(self._signal_tab, "🔬  Signal Data")

            layout.addWidget(self._tabs)

            logger.info("MultiChartWidget initialized")

        except Exception as e:
            logger.critical(f"[MultiChartWidget.__init__] Failed: {e}", exc_info=True)
            # Still create basic widget
            super().__init__(parent)
            self._show_error_content(str(e))

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._tabs = None
        self._spot_chart = None
        self._call_chart = None
        self._put_chart = None
        self._signal_tab = None

    def _show_error_content(self, error_msg: str):
        """Show error message if initialization fails"""
        try:
            layout = QVBoxLayout(self)
            error_lbl = QLabel(f"❌ Error initializing charts: {error_msg}")
            error_lbl.setStyleSheet("color: #f85149; padding: 20px;")
            error_lbl.setWordWrap(True)
            layout.addWidget(error_lbl)
        except Exception:
            pass

    # ── Forward set_config to all three charts ────────────────────────────────

    def set_config(self, config, signal_engine=None) -> None:
        """Call once at startup and after every strategy change."""
        try:
            for chart in (self._spot_chart, self._call_chart, self._put_chart):
                if chart:
                    chart.set_config(config, signal_engine)
            # _signal_tab needs no config — it reads from spot_data["option_signal"]
        except Exception as e:
            logger.error(f"[MultiChartWidget.set_config] Failed: {e}", exc_info=True)

    # ── Update all three charts ───────────────────────────────────────────────

    def update_charts(self,
                      spot_data: dict,
                      call_data: Optional[dict] = None,
                      put_data: Optional[dict] = None) -> None:
        """
        Push new trend data to each chart tab and refresh the Signal Data tab.
        Pass None / {} for tabs whose data is not yet available.
        """
        try:
            if spot_data and self._spot_chart:
                self._spot_chart.update_chart(spot_data)
                # Feed the Signal Data tab from spot_data["option_signal"]
                option_signal = (spot_data.get("option_signal")
                                 if isinstance(spot_data, dict) else None)
                if self._signal_tab:
                    self._signal_tab.refresh(option_signal)

            if call_data and self._call_chart:
                self._call_chart.update_chart(call_data)

            if put_data and self._put_chart:
                self._put_chart.update_chart(put_data)

        except Exception as e:
            logger.error(f"[MultiChartWidget.update_charts] Failed: {e}", exc_info=True)

    # ── Convenience: keep old single-chart API working ────────────────────────

    def update_chart(self, trend_data: dict) -> None:
        """
        Backward-compatible: routes to spot chart only.
        Prefer update_charts() for the full multi-instrument experience.
        """
        try:
            self.update_charts(spot_data=trend_data)
        except Exception as e:
            logger.error(f"[MultiChartWidget.update_chart] Failed: {e}", exc_info=True)

    def clear_cache(self):
        try:
            for c in (self._spot_chart, self._call_chart, self._put_chart):
                if c:
                    c.clear_cache()
            # Signal tab has no cache to clear but reset its display
            if self._signal_tab:
                self._signal_tab.refresh(None)
        except Exception as e:
            logger.error(f"[MultiChartWidget.clear_cache] Failed: {e}", exc_info=True)

    # ── Expose tab references for direct access if needed ─────────────────────

    @property
    def spot_chart(self) -> Optional[ChartWidget]:
        return self._spot_chart

    @property
    def call_chart(self) -> Optional[ChartWidget]:
        return self._call_chart

    @property
    def put_chart(self) -> Optional[ChartWidget]:
        return self._put_chart

    @property
    def signal_tab(self) -> Optional["_SignalDataTab"]:
        """Direct access to the Signal Data tab if needed."""
        return self._signal_tab

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown"""
        try:
            logger.info("[MultiChartWidget] Starting cleanup")

            # Clear caches
            self.clear_cache()

            # Clear references
            self._spot_chart = None
            self._call_chart = None
            self._put_chart = None
            self._signal_tab = None
            self._tabs = None

            logger.info("[MultiChartWidget] Cleanup completed")

        except Exception as e:
            logger.error(f"[MultiChartWidget.cleanup] Error: {e}", exc_info=True)