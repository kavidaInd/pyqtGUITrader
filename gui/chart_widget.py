# chart_widget.py - Market Structure Analysis with Pivot Points and HH/HL/LL/LH
# Dynamic indicator subplots driven entirely by DynamicSignalEngine rules / Config flags.
#
# HOW DYNAMIC PANELS WORK
# ─────────────────────────────────────────────────────────────────────────────
# 1. Call  set_config(config, signal_engine)  once at startup and again after
#    any settings dialog closes.
#
# 2. _resolve_active_panels() walks every rule in every DynamicSignalEngine
#    signal group and reads the "indicator" field from each LHS / RHS.
#    Those names are normalised via ENGINE_KEY_TO_PANEL and the matching
#    IndicatorSpec entries are activated.
#    Config flags (use_rsi, use_macd, …) are the fallback when no engine
#    rules are configured.
#
# 3. Each IndicatorSpec declares:
#       panel_type  "overlay"  → plotted on the price row (SuperTrend, BB)
#                   "subplot"  → its own row below price  (MACD, RSI)
#       trend_keys  dot-paths into trend_data to find the series data
#       render_fn   a small function that adds the Plotly traces
#
# 4. _generate_chart_html() is indicator-agnostic — it loops over the active
#    specs and calls their render_fn.  Adding a new indicator = add one
#    IndicatorSpec + one small render function.  Nothing else changes.
#
# CALLER INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────
#   # startup / after settings dialog:
#   chart_widget.set_config(config, detector.signal_engine)
#
#   # each bar:
#   chart_widget.update_chart(state.derivative_trend)

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from PyQt5.QtCore import QObject, QSize, QTimer, pyqtSignal
from PyQt5.QtWebEngineWidgets import QWebEngineView

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
#  INDICATOR REGISTRY
#  One IndicatorSpec per indicator — the only place that knows how to render it.
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class IndicatorSpec:
    """
    Declarative description of how one indicator is visualised.

    key         - Canonical name, used as the registry key.
    trend_keys  - Dict[alias -> dot-path in trend_data].
                  "macd.histogram"  resolves as trend_data["macd"]["histogram"]
                  "rsi_series"      resolves as trend_data["rsi_series"]
    panel_type  - "overlay": drawn on the price row, no extra subplot row.
                  "subplot": gets its own dedicated row below price.
    render_fn   - Callable(fig, x, series_dict, row, COLORS) -> None
                  Adds all Plotly traces for this indicator.
    y_range     - Optional fixed [min, max] for subplot y-axis (e.g. RSI [0,100]).
    y_label     - Y-axis title for subplot rows.
    config_flag - Name of the Config bool attribute used as fallback when no
                  engine rules are present.  None if the flag has a special name.
    """
    key: str
    trend_keys: Dict[str, str]
    panel_type: str  # "overlay" | "subplot"
    render_fn: Callable
    y_range: Optional[List[float]] = None
    y_label: str = ""
    config_flag: Optional[str] = None


# ── Per-indicator render functions ────────────────────────────────────────────

def _render_supertrend(fig, x, s, row, C, label, bull_col, bear_col):
    """Generic SuperTrend renderer — splits line into bull / bear segments."""
    trend_vals = s.get("trend", [])
    directions = s.get("direction", [])
    if not trend_vals:
        return
    bull_x, bull_y, bear_x, bear_y = [], [], [], []
    for i, tv in enumerate(trend_vals):
        if tv is None:
            continue
        d = directions[i] if i < len(directions) else "0"
        if str(d) in ("1", "1.0", "True", "bull", "up"):
            bull_x.append(x[i]);
            bull_y.append(tv)
        else:
            bear_x.append(x[i]);
            bear_y.append(tv)
    if bull_x:
        fig.add_trace(go.Scatter(
            x=bull_x, y=bull_y, name=f"{label} ↑", mode="lines",
            line=dict(color=bull_col, width=1.5),
            hovertemplate=f"{label}: %{{y:.2f}}<extra></extra>",
            showlegend=True, legendgroup=label,
        ), row=row, col=1)
    if bear_x:
        fig.add_trace(go.Scatter(
            x=bear_x, y=bear_y, name=f"{label} ↓", mode="lines",
            line=dict(color=bear_col, width=1.5),
            hovertemplate=f"{label}: %{{y:.2f}}<extra></extra>",
            showlegend=True, legendgroup=label,
        ), row=row, col=1)


def _render_supertrend_short(fig, x, s, row, C):
    _render_supertrend(fig, x, s, row, C, "ST Short",
                       C["st_short_bull"], C["st_short_bear"])


def _render_supertrend_long(fig, x, s, row, C):
    _render_supertrend(fig, x, s, row, C, "ST Long",
                       C["st_long_bull"], C["st_long_bear"])


def _render_bb(fig, x, s, row, C):
    """Bollinger Bands: upper / lower / middle overlaid on price."""
    n = len(x)
    upper = s.get("upper", [])
    lower = s.get("lower", [])
    middle = s.get("middle", [])
    if not upper or len(upper) != n:
        return
    # Upper — plotted first so fill="tonexty" on Lower fills the channel
    fig.add_trace(go.Scatter(
        x=x, y=upper, name="BB Upper",
        line=dict(color=C["bb_upper"], width=1, dash="dot"),
        hovertemplate="BB Upper: %{y:.2f}<extra></extra>",
        showlegend=True, legendgroup="bb",
    ), row=row, col=1)
    if lower and len(lower) == n:
        fig.add_trace(go.Scatter(
            x=x, y=lower, name="BB Lower",
            line=dict(color=C["bb_lower"], width=1, dash="dot"),
            fill="tonexty", fillcolor=C["bb_fill"],
            hovertemplate="BB Lower: %{y:.2f}<extra></extra>",
            showlegend=True, legendgroup="bb",
        ), row=row, col=1)
    if middle and len(middle) == n:
        fig.add_trace(go.Scatter(
            x=x, y=middle, name="BB Mid",
            line=dict(color=C["bb_mid"], width=1, dash="dash"),
            hovertemplate="BB Mid: %{y:.2f}<extra></extra>",
            showlegend=False, legendgroup="bb",
        ), row=row, col=1)


def _render_macd(fig, x, s, row, C):
    """MACD: histogram bars + MACD line + signal line + zero reference."""
    n = len(x)
    macd_vals = s.get("macd", [])
    sig_vals = s.get("signal", [])
    hist_vals = s.get("histogram", [])
    if not macd_vals or len(macd_vals) != n:
        return
    # Histogram
    if hist_vals and len(hist_vals) == n:
        hist_colors = [C["macd_hist_pos"] if (v is not None and v >= 0)
                       else C["macd_hist_neg"] for v in hist_vals]
        fig.add_trace(go.Bar(
            x=x, y=hist_vals, name="Histogram",
            marker_color=hist_colors,
            hovertemplate="Hist: %{y:.4f}<extra></extra>",
            showlegend=True,
        ), row=row, col=1)
    # MACD line
    fig.add_trace(go.Scatter(
        x=x, y=macd_vals, name="MACD",
        line=dict(color=C["macd_line"], width=1.5),
        hovertemplate="MACD: %{y:.4f}<extra></extra>",
        showlegend=True,
    ), row=row, col=1)
    # Signal line
    if sig_vals and len(sig_vals) == n:
        fig.add_trace(go.Scatter(
            x=x, y=sig_vals, name="Signal",
            line=dict(color=C["macd_signal"], width=1.5, dash="dash"),
            hovertemplate="Signal: %{y:.4f}<extra></extra>",
            showlegend=True,
        ), row=row, col=1)
    # Zero reference
    fig.add_hline(y=0, row=row, col=1,
                  line=dict(color=C["text"], width=1, dash="dot"))


def _render_rsi(fig, x, s, row, C):
    """RSI: line + OB/OS shaded regions + reference lines + current value label."""
    series = s.get("series", [])
    if not series:
        return
    # Shaded OB / OS bands
    fig.add_hrect(y0=70, y1=100, row=row, col=1,
                  fillcolor=C["rsi_ob"], layer="below", line_width=0)
    fig.add_hrect(y0=0, y1=30, row=row, col=1,
                  fillcolor=C["rsi_os"], layer="below", line_width=0)
    # RSI line
    xs = x[:len(series)]
    fig.add_trace(go.Scatter(
        x=xs, y=series, name="RSI",
        line=dict(color=C["rsi_line"], width=1.5),
        hovertemplate="RSI: %{y:.2f}<extra></extra>",
        showlegend=True,
    ), row=row, col=1)
    # Reference lines at 70 / 50 / 30
    for lvl, col_key, lbl in (
            (70, "rsi_ob_line", "OB 70"),
            (50, "rsi_mid", "50"),
            (30, "rsi_os_line", "OS 30"),
    ):
        fig.add_hline(y=lvl, row=row, col=1,
                      line=dict(color=C[col_key], width=1, dash="dot"),
                      annotation_text=lbl, annotation_position="right",
                      annotation_font=dict(size=8, color=C[col_key]))
    # Current value annotation coloured by zone
    last = next((v for v in reversed(series) if v is not None), None)
    if last is not None:
        col = (C["rsi_ob_line"] if last > 70
               else C["rsi_os_line"] if last < 30
        else C["rsi_line"])
        fig.add_annotation(
            x=len(series) - 1, y=last,
            text=f"  {last:.1f}", showarrow=False,
            font=dict(size=9, color=col), xanchor="left",
            row=row, col=1,
        )


# ── Registry — order determines subplot row order ─────────────────────────────
INDICATOR_REGISTRY: List[IndicatorSpec] = [

    IndicatorSpec(
        key="supertrend_short",
        trend_keys={
            "trend": "super_trend_short.trend",
            "direction": "super_trend_short.direction",
        },
        panel_type="overlay",
        render_fn=_render_supertrend_short,
        config_flag="use_short_st",
    ),

    IndicatorSpec(
        key="supertrend_long",
        trend_keys={
            "trend": "super_trend_long.trend",
            "direction": "super_trend_long.direction",
        },
        panel_type="overlay",
        render_fn=_render_supertrend_long,
        config_flag="use_long_st",
    ),

    IndicatorSpec(
        key="bb",
        trend_keys={
            "upper": "bb.upper",
            "middle": "bb.middle",
            "lower": "bb.lower",
        },
        panel_type="overlay",
        render_fn=_render_bb,
        config_flag=None,  # activated by bb_entry OR bb_exit
    ),

    IndicatorSpec(
        key="macd",
        trend_keys={
            "macd": "macd.macd",
            "signal": "macd.signal",
            "histogram": "macd.histogram",
        },
        panel_type="subplot",
        render_fn=_render_macd,
        y_label="MACD",
        config_flag="use_macd",
    ),

    IndicatorSpec(
        key="rsi",
        trend_keys={
            "series": "rsi_series",
        },
        panel_type="subplot",
        render_fn=_render_rsi,
        y_range=[0, 100],
        y_label="RSI",
        config_flag="use_rsi",
    ),
]

# Fast lookup by key
_REGISTRY: Dict[str, IndicatorSpec] = {s.key: s for s in INDICATOR_REGISTRY}

# Maps DynamicSignalEngine indicator names → registry keys
ENGINE_KEY_TO_PANEL: Dict[str, str] = {
    "supertrend": "supertrend_short",
    "bbands": "bb",
    "bb": "bb",
    "bollinger": "bb",
    "macd": "macd",
    "rsi": "rsi",
}


# ── Active-panel resolution ───────────────────────────────────────────────────

def _resolve_active_panels(config, signal_engine) -> List[str]:
    """
    Return ordered list of registry keys to render this session.

    Priority: engine rules > config flags > nothing.
    Order follows INDICATOR_REGISTRY so the layout is stable.
    """
    active: Set[str] = set()

    # 1. Walk engine rules
    if signal_engine is not None:
        try:
            from strategy.dynamic_signal_engine import SIGNAL_GROUPS
            for sig in SIGNAL_GROUPS:
                for rule in signal_engine.get_rules(sig):
                    for side_key in ("lhs", "rhs"):
                        side = rule.get(side_key, {})
                        if side.get("type", "indicator") == "indicator":
                            eng_key = side.get("indicator", "").lower()
                            reg_key = ENGINE_KEY_TO_PANEL.get(eng_key)
                            if reg_key:
                                active.add(reg_key)
        except Exception as e:
            logger.warning(f"Could not inspect signal engine rules: {e}")

    # 2. Fall back to Config flags when engine produced nothing
    if not active and config is not None:
        for spec in INDICATOR_REGISTRY:
            if spec.config_flag and getattr(config, spec.config_flag, False):
                active.add(spec.key)
        # BB has two flags
        if getattr(config, "bb_entry", False) or getattr(config, "bb_exit", False):
            active.add("bb")

    # Return in registry declaration order
    return [spec.key for spec in INDICATOR_REGISTRY if spec.key in active]


def _load_series(spec: IndicatorSpec, trend_data: Dict,
                 clean_fn: Callable) -> Dict[str, List]:
    """
    Extract and clean every series declared in spec.trend_keys.
    Dot-paths support one level of nesting: "macd.histogram".
    Direction lists are passed through as-is (strings, not floats).
    """
    out = {}
    for alias, dot_path in spec.trend_keys.items():
        parts = dot_path.split(".", 1)
        raw = trend_data.get(parts[0])
        if len(parts) == 2 and isinstance(raw, dict):
            raw = raw.get(parts[1])
        out[alias] = raw if alias == "direction" and isinstance(raw, list) \
            else clean_fn(raw)
    return out


# ═════════════════════════════════════════════════════════════════════════════
#  Market structure helpers  (original code — unchanged)
# ═════════════════════════════════════════════════════════════════════════════

class StructureType(Enum):
    """Market structure types"""
    HH = "Higher High"
    HL = "Higher Low"
    LH = "Lower High"
    LL = "Lower Low"
    NONE = "None"


@dataclass
class PivotPoint:
    """Represents a pivot point in market structure"""
    index: int
    price: float
    type: str  # 'high' or 'low'
    strength: int  # 1-3, based on number of bars on each side
    structure: StructureType = StructureType.NONE


class ChartUpdater(QObject):
    """# PYQT: Worker object for chart updates"""
    update_requested = pyqtSignal(object)
    update_completed = pyqtSignal(bool, str)  # success, message


class MarketStructureAnalyzer:
    """
    Analyzes market structure to identify pivot points and
    Higher Highs (HH), Higher Lows (HL), Lower Highs (LH), Lower Lows (LL)
    """

    def __init__(self, left_bars: int = 5, right_bars: int = 5):
        """
        Args:
            left_bars: Number of bars to check on left side for pivot confirmation
            right_bars: Number of bars to check on right side for pivot confirmation
        """
        self.left_bars = left_bars
        self.right_bars = right_bars

    def find_pivot_points(self, high: List[float], low: List[float]) -> List[PivotPoint]:
        """
        Find pivot highs and lows in the price data

        Args:
            high: List of high prices
            low: List of low prices

        Returns:
            List of PivotPoint objects
        """
        if len(high) < self.left_bars + self.right_bars + 1:
            return []

        pivots = []
        n = len(high)

        for i in range(self.left_bars, n - self.right_bars):
            # Check for pivot high
            is_pivot_high = True
            for j in range(i - self.left_bars, i + self.right_bars + 1):
                if j == i:
                    continue
                if high[j] >= high[i]:
                    is_pivot_high = False
                    break

            if is_pivot_high:
                # Calculate strength based on how many bars are clearly lower
                strength = 1
                avg_diff = 0
                count = 0
                for j in range(i - self.left_bars, i + self.right_bars + 1):
                    if j != i:
                        avg_diff += (high[i] - high[j])
                        count += 1
                if count > 0:
                    avg_diff /= count
                    if avg_diff > (max(high) - min(high)) * 0.02:  # 2% of range
                        strength = 2
                    if avg_diff > (max(high) - min(high)) * 0.05:  # 5% of range
                        strength = 3

                pivots.append(PivotPoint(
                    index=i,
                    price=high[i],
                    type='high',
                    strength=strength
                ))

            # Check for pivot low
            is_pivot_low = True
            for j in range(i - self.left_bars, i + self.right_bars + 1):
                if j == i:
                    continue
                if low[j] <= low[i]:
                    is_pivot_low = False
                    break

            if is_pivot_low:
                # Calculate strength
                strength = 1
                avg_diff = 0
                count = 0
                for j in range(i - self.left_bars, i + self.right_bars + 1):
                    if j != i:
                        avg_diff += (low[j] - low[i])
                        count += 1
                if count > 0:
                    avg_diff /= count
                    if avg_diff > (max(high) - min(low)) * 0.02:
                        strength = 2
                    if avg_diff > (max(high) - min(low)) * 0.05:
                        strength = 3

                pivots.append(PivotPoint(
                    index=i,
                    price=low[i],
                    type='low',
                    strength=strength
                ))

        return pivots

    def identify_structure(self, pivots: List[PivotPoint]) -> List[PivotPoint]:
        """
        Identify HH, HL, LH, LL patterns from pivot points

        Args:
            pivots: List of pivot points in chronological order

        Returns:
            Updated pivots with structure type identified
        """
        if len(pivots) < 2:
            return pivots

        # Sort by index
        pivots.sort(key=lambda x: x.index)

        # Identify structure
        for i in range(1, len(pivots)):
            current = pivots[i]
            previous = pivots[i - 1]

            if current.type == 'high' and previous.type == 'high':
                if current.price > previous.price:
                    current.structure = StructureType.HH
                else:
                    current.structure = StructureType.LH

            elif current.type == 'low' and previous.type == 'low':
                if current.price > previous.price:
                    current.structure = StructureType.HL
                else:
                    current.structure = StructureType.LL

        return pivots

    def get_trend_lines(self, pivots: List[PivotPoint]) -> Dict[str, List[Tuple[int, float]]]:
        """
        Generate trend lines connecting HH/HL and LH/LL

        Returns:
            Dictionary with 'uptrend' and 'downtrend' lines
        """
        uptrend_points = []
        downtrend_points = []

        # Filter pivots with structure
        for pivot in pivots:
            if pivot.structure in [StructureType.HL, StructureType.LL]:
                # For uptrend, connect Higher Lows
                if pivot.structure == StructureType.HL:
                    uptrend_points.append((pivot.index, pivot.price))
            elif pivot.structure in [StructureType.HH, StructureType.LH]:
                # For downtrend, connect Lower Highs
                if pivot.structure == StructureType.LH:
                    downtrend_points.append((pivot.index, pivot.price))

        return {
            'uptrend': uptrend_points,
            'downtrend': downtrend_points
        }

    def get_market_phase(self, pivots: List[PivotPoint]) -> str:
        """
        Determine current market phase based on recent structure

        Returns:
            'uptrend', 'downtrend', 'ranging', or 'neutral'
        """
        if len(pivots) < 4:
            return 'neutral'

        # Get last 4 pivots
        recent = pivots[-4:]

        # Check for uptrend pattern (HH and HL)
        hh_count = sum(1 for p in recent if p.structure == StructureType.HH)
        hl_count = sum(1 for p in recent if p.structure == StructureType.HL)

        if hh_count >= 2 and hl_count >= 2:
            return 'uptrend'

        # Check for downtrend pattern (LH and LL)
        lh_count = sum(1 for p in recent if p.structure == StructureType.LH)
        ll_count = sum(1 for p in recent if p.structure == StructureType.LL)

        if lh_count >= 2 and ll_count >= 2:
            return 'downtrend'

        # Check for ranging (alternating patterns)
        if len(set(p.structure for p in recent)) >= 3:
            return 'ranging'

        return 'neutral'


# ═════════════════════════════════════════════════════════════════════════════
#  ChartWidget
# ═════════════════════════════════════════════════════════════════════════════

class ChartWidget(QWebEngineView):
    """
    # PYQT: Market Structure Chart showing pivot points and HH/HL/LL/LH patterns.
    Indicator subplots (SuperTrend, BB, MACD, RSI, …) are added and removed
    automatically based on whatever indicators are referenced in the live
    DynamicSignalEngine rules or Config flags.
    """

    DARK_BG = "#0d1117"
    CARD_BG = "#161b22"
    TEXT_COLOR = "#e6edf3"
    GRID_COLOR = "#30363d"

    # Color scheme — extended to cover all indicator panels
    COLORS = {
        # Candles
        "candle_up": "#3fb950",
        "candle_down": "#f85149",
        # Pivot / structure
        "pivot_high": "#f0883e",
        "pivot_low": "#58a6ff",
        "hh": "#7ee37d",
        "hl": "#58a6ff",
        "lh": "#f85149",
        "ll": "#db6d28",
        "trend_up": "#3fb950",
        "trend_down": "#f85149",
        # SuperTrend
        "st_short_bull": "#3fb950",
        "st_short_bear": "#f85149",
        "st_long_bull": "#7ee37d",
        "st_long_bear": "#db6d28",
        # Bollinger Bands
        "bb_upper": "#f0883e",
        "bb_mid": "#8b949e",
        "bb_lower": "#58a6ff",
        "bb_fill": "rgba(88,166,255,0.07)",
        # MACD
        "macd_line": "#58a6ff",
        "macd_signal": "#f0883e",
        "macd_hist_pos": "#3fb950",
        "macd_hist_neg": "#f85149",
        # RSI
        "rsi_line": "#a371f7",
        "rsi_ob": "rgba(248,81,73,0.15)",
        "rsi_os": "rgba(63,185,80,0.15)",
        "rsi_ob_line": "#f85149",
        "rsi_os_line": "#3fb950",
        "rsi_mid": "#30363d",
        # Volume
        "vol_up": "rgba(63,185,80,0.45)",
        "vol_down": "rgba(248,81,73,0.45)",
        # Misc
        "text": "#8b949e",
    }

    # Row height proportions
    _MAIN_RATIO = 0.52
    _SUB_RATIO = 0.20  # each subplot panel
    _VOL_RATIO = 0.08

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {self.DARK_BG}; border: none;")

        # Set minimum size
        self.setMinimumSize(QSize(400, 300))

        # Dynamic panel state
        self._config = None
        self._signal_engine = None
        self._active_keys: List[str] = []  # registry keys currently active

        # Market structure analyzer
        self.analyzer = MarketStructureAnalyzer(left_bars=5, right_bars=5)

        # State tracking
        self._last_data_fingerprint = ""
        self._pending_data = None
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._perform_update)

        # Cache for generated HTML
        self._html_cache = {}
        self._max_cache_size = 5

        # Error recovery
        self._error_count = 0
        self._max_errors = 3

        # Updater for background processing
        self.updater = ChartUpdater()
        self.updater.update_requested.connect(self.update_chart)

        # Show placeholder initially
        self._show_placeholder()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_config(self, config, signal_engine=None) -> None:
        """
        Attach Config + optional DynamicSignalEngine so the chart knows
        which indicator panels to draw.

        Call once at startup and again whenever strategy settings change
        (e.g. after StrategySettingGUI closes) so the layout rebuilds on
        the next bar.

        Args:
            config:        Config instance from config.py
            signal_engine: DynamicSignalEngine instance (may be None)
        """
        self._config = config
        self._signal_engine = signal_engine
        self._active_keys = _resolve_active_panels(config, signal_engine)

        # Bust cache — layout may have changed
        self._last_data_fingerprint = ""
        self._html_cache.clear()

        logger.info(
            f"ChartWidget panels → "
            f"{self._active_keys or ['price + structure only']}"
        )

    # ── Original public methods (unchanged) ───────────────────────────────────

    def update_chart(self, trend_data: dict):
        """
        # PYQT: Thread-safe chart update - throttled to prevent flicker
        Can be called from any thread
        """
        try:
            fp = self._fingerprint(trend_data)

            # Skip if no meaningful change
            if fp == self._last_data_fingerprint or fp == "":
                return

            # Reset error count on successful data
            self._error_count = 0

            # Store new fingerprint
            self._last_data_fingerprint = fp

            # Check cache first
            if fp in self._html_cache:
                self.setHtml(self._html_cache[fp])
                return

            # Schedule update on main thread with debounce
            self._pending_data = trend_data
            self._update_timer.start(300)  # 300ms debounce

        except Exception as e:
            logger.error(f"Update chart failed: {e}")
            self._error_count += 1
            if self._error_count >= self._max_errors:
                self._show_error_placeholder(str(e))

    def clear_cache(self):
        """Clear the HTML cache to free memory"""
        self._html_cache.clear()
        logger.debug("Chart cache cleared")

    def resizeEvent(self, event):
        """Handle resize events to ensure chart fits"""
        super().resizeEvent(event)
        # Trigger a re-render on next update
        self._last_data_fingerprint = ""
        if hasattr(self, 'updater'):
            self.updater.update_requested.emit(self._pending_data)

    # ── Internal — placeholders (original code unchanged) ─────────────────────

    def _show_placeholder(self, message: str = "Waiting for market data..."):
        """Show placeholder text when no data"""
        html = f"""
        <html>
        <head>
            <style>
                body {{
                    background: {self.DARK_BG};
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    font-family: 'Segoe UI', sans-serif;
                }}
                .message {{
                    color: #8b949e;
                    font-size: 16px;
                    text-align: center;
                    padding: 20px;
                }}
                .spinner {{
                    border: 3px solid {self.CARD_BG};
                    border-top: 3px solid {self.COLORS["pivot_low"]};
                    border-radius: 50%;
                    width: 40px;
                    height: 40px;
                    animation: spin 1s linear infinite;
                    margin: 20px auto;
                }}
                @keyframes spin {{
                    0% {{ transform: rotate(0deg); }}
                    100% {{ transform: rotate(360deg); }}
                }}
            </style>
        </head>
        <body>
            <div class="message">
                <div class="spinner"></div>
                <div>📊 {message}</div>
            </div>
        </body>
        </html>
        """
        self.setHtml(html)

    def _show_error_placeholder(self, error_msg: str):
        """Show error message when chart generation fails"""
        html = f"""
        <html>
        <head>
            <style>
                body {{
                    background: {self.DARK_BG};
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    font-family: 'Segoe UI', sans-serif;
                }}
                .error {{
                    color: {self.COLORS["candle_down"]};
                    font-size: 14px;
                    text-align: center;
                    padding: 20px;
                    border: 1px solid {self.COLORS["candle_down"]};
                    border-radius: 6px;
                    background: rgba(248, 81, 73, 0.1);
                }}
            </style>
        </head>
        <body>
            <div class="error">
                ❌ Chart Error: {error_msg}
            </div>
        </body>
        </html>
        """
        self.setHtml(html)

    # ── Internal — fingerprint (original, extended with panel signature) ───────

    def _fingerprint(self, trend_data: Optional[Dict]) -> str:
        """
        Create lightweight fingerprint to detect meaningful changes.
        Panel signature is included so a config change forces a redraw.
        """
        try:
            if not trend_data or not isinstance(trend_data, dict):
                return ""

            close = trend_data.get("close") or []
            if not close or not isinstance(close, (list, np.ndarray)):
                return ""

            # Convert to list if numpy array
            if isinstance(close, np.ndarray):
                close = close.tolist()

            n_points = len(close)
            if n_points == 0:
                return ""

            # Get last few values
            last_values = close[-5:] if n_points >= 5 else close

            # Include active panel signature so layout changes trigger redraw
            panel_sig = ",".join(self._active_keys)

            fp_parts = [
                str(n_points),
                panel_sig,
                str([round(v, 4) if isinstance(v, (int, float)) else str(v)
                     for v in last_values])
            ]

            return ":".join(fp_parts)

        except Exception as e:
            logger.debug(f"Fingerprint generation failed: {e}")
            return ""

    # ── Internal — data cleaning (original code unchanged) ────────────────────

    def _clean_data(self, raw: Any) -> List[float]:
        """
        Clean and validate data series
        """
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
                        x_lower = x.lower().strip()
                        if x_lower in ("nan", "none", "null", ""):
                            cleaned.append(None)
                        else:
                            try:
                                cleaned.append(float(x))
                            except ValueError:
                                cleaned.append(None)
                    else:
                        cleaned.append(None)
                except (ValueError, TypeError):
                    cleaned.append(None)

            return cleaned

        except Exception as e:
            logger.error(f"Data cleaning failed: {e}")
            return []

    # ── Internal — Qt timer callback (original code unchanged) ────────────────

    def _perform_update(self):
        """# PYQT: Perform chart update on main thread"""
        if self._pending_data is None:
            return

        trend_data = self._pending_data
        self._pending_data = None

        try:
            # Generate HTML (on main thread)
            html = self._generate_chart_html(trend_data)
            if html:
                # Cache the HTML
                fp = self._fingerprint(trend_data)
                if fp and len(self._html_cache) < self._max_cache_size:
                    self._html_cache[fp] = html

                self.setHtml(html)

                # Emit completion signal
                if hasattr(self, 'updater'):
                    self.updater.update_completed.emit(True, "Chart updated")
            else:
                self._show_placeholder("Insufficient data for chart")

        except Exception as e:
            logger.error(f"Chart update error: {e}", exc_info=True)
            self._show_error_placeholder(str(e))
            if hasattr(self, 'updater'):
                self.updater.update_completed.emit(False, str(e))

    # ── Core renderer — fully dynamic, no hardcoded indicator names ───────────

    def _generate_chart_html(self, trend_data: Dict) -> Optional[str]:
        """
        Generate Plotly HTML.

        Layout is determined entirely by self._active_keys (populated by
        set_config from the engine rules / Config flags).
        No indicator name appears in this method — all rendering is
        delegated to the IndicatorSpec.render_fn callbacks.
        """
        if not trend_data or not isinstance(trend_data, dict):
            return None

        try:
            # ── 1. Price data ─────────────────────────────────────────────────
            open_prices = self._clean_data(trend_data.get("open"))
            high = self._clean_data(trend_data.get("high"))
            low = self._clean_data(trend_data.get("low"))
            close = self._clean_data(trend_data.get("close"))
            volume = self._clean_data(trend_data.get("volume"))
            symbol_name = trend_data.get("name", "Derivative")

            if not close:
                return None

            n = len(close)
            if n < 10:
                logger.debug(f"Insufficient data: {n} points")
                return None

            x = list(range(n))

            # Use close for high/low if OHLC not available
            if not high:
                high = close
            if not low:
                low = close

            # ── 2. Market structure ───────────────────────────────────────────
            pivots = self.analyzer.find_pivot_points(high, low)
            pivots = self.analyzer.identify_structure(pivots)
            trend_lines = self.analyzer.get_trend_lines(pivots)
            market_phase = self.analyzer.get_market_phase(pivots)

            # ── 3. Option signal for annotation ───────────────────────────────
            opt_signal = trend_data.get("option_signal") or {}
            signal_value = (opt_signal.get("signal_value", "")
                            if isinstance(opt_signal, dict) else "")

            # ── 4. Split active specs into overlay vs subplot ──────────────────
            overlay_specs = [_REGISTRY[k] for k in self._active_keys
                             if k in _REGISTRY and _REGISTRY[k].panel_type == "overlay"]
            subplot_specs = [_REGISTRY[k] for k in self._active_keys
                             if k in _REGISTRY and _REGISTRY[k].panel_type == "subplot"]

            n_sub = len(subplot_specs)
            has_vol = bool(volume and len(volume) == n)
            n_rows = 1 + n_sub + (1 if has_vol else 0)

            # Row heights
            remaining = 1.0 - self._MAIN_RATIO
            vol_h = self._VOL_RATIO if has_vol else 0.0
            sub_h = (remaining - vol_h) / n_sub if n_sub else 0.0
            row_heights = [self._MAIN_RATIO] + [sub_h] * n_sub
            if has_vol:
                row_heights.append(vol_h)

            # Map key / "price" / "volume" → plotly row number
            row_of: Dict[str, int] = {"price": 1}
            for i, spec in enumerate(subplot_specs):
                row_of[spec.key] = 2 + i
            if has_vol:
                row_of["volume"] = n_rows

            # ── 5. Create figure ──────────────────────────────────────────────
            fig = make_subplots(
                rows=n_rows, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=row_heights,
                specs=[[{"type": "xy"}]] * n_rows,
            )

            pr = row_of["price"]

            # ── 6. Price trace ────────────────────────────────────────────────
            if open_prices and len(open_prices) == n:
                fig.add_trace(go.Candlestick(
                    x=x,
                    open=open_prices, high=high, low=low, close=close,
                    name="Price",
                    increasing=dict(line=dict(color=self.COLORS["candle_up"]),
                                    fillcolor=self.COLORS["candle_up"]),
                    decreasing=dict(line=dict(color=self.COLORS["candle_down"]),
                                    fillcolor=self.COLORS["candle_down"]),
                    showlegend=False,
                ), row=pr, col=1)
            else:
                fig.add_trace(go.Scatter(
                    x=x, y=close, name="Price",
                    line=dict(color="#58a6ff", width=2),
                    hovertemplate="Price: %{y:.2f}<extra></extra>",
                    showlegend=False,
                ), row=pr, col=1)

            # ── 7. Overlay indicators on price row ────────────────────────────
            for spec in overlay_specs:
                series = _load_series(spec, trend_data, self._clean_data)
                spec.render_fn(fig, x, series, pr, self.COLORS)

            # ── 8. Pivot points ───────────────────────────────────────────────
            pivot_x, pivot_y, pivot_text, pivot_colors, pivot_symbols = [], [], [], [], []

            for pivot in pivots:
                pivot_x.append(pivot.index)
                pivot_y.append(pivot.price)

                if pivot.structure == StructureType.HH:
                    pivot_colors.append(self.COLORS["hh"])
                    pivot_symbols.append("triangle-up")
                    pivot_text.append(f"HH<br>Price: {pivot.price:.2f}<br>Strength: {pivot.strength}")
                elif pivot.structure == StructureType.HL:
                    pivot_colors.append(self.COLORS["hl"])
                    pivot_symbols.append("triangle-up")
                    pivot_text.append(f"HL<br>Price: {pivot.price:.2f}<br>Strength: {pivot.strength}")
                elif pivot.structure == StructureType.LH:
                    pivot_colors.append(self.COLORS["lh"])
                    pivot_symbols.append("triangle-down")
                    pivot_text.append(f"LH<br>Price: {pivot.price:.2f}<br>Strength: {pivot.strength}")
                elif pivot.structure == StructureType.LL:
                    pivot_colors.append(self.COLORS["ll"])
                    pivot_symbols.append("triangle-down")
                    pivot_text.append(f"LL<br>Price: {pivot.price:.2f}<br>Strength: {pivot.strength}")
                else:
                    if pivot.type == 'high':
                        pivot_colors.append(self.COLORS["pivot_high"])
                        pivot_symbols.append("circle")
                        pivot_text.append(f"Pivot High<br>Price: {pivot.price:.2f}<br>Strength: {pivot.strength}")
                    else:
                        pivot_colors.append(self.COLORS["pivot_low"])
                        pivot_symbols.append("circle")
                        pivot_text.append(f"Pivot Low<br>Price: {pivot.price:.2f}<br>Strength: {pivot.strength}")

            if pivot_x:
                fig.add_trace(go.Scatter(
                    x=pivot_x, y=pivot_y,
                    mode="markers+text",
                    name="Pivot Points",
                    marker=dict(
                        size=[8 + s * 2 for s in [p.strength for p in pivots]],
                        color=pivot_colors,
                        symbol=pivot_symbols,
                        line=dict(width=1, color="white")
                    ),
                    text=[p.structure.value[:2] if p.structure != StructureType.NONE
                          else "" for p in pivots],
                    textposition="top center",
                    textfont=dict(size=9, color="white"),
                    hovertemplate="%{text}<extra></extra>",
                    showlegend=False
                ), row=pr, col=1)

            # ── 9. Trend lines ────────────────────────────────────────────────
            if len(trend_lines['uptrend']) >= 2:
                x_vals, y_vals = zip(*trend_lines['uptrend'])
                fig.add_trace(go.Scatter(
                    x=x_vals, y=y_vals,
                    mode="lines", name="Uptrend",
                    line=dict(color=self.COLORS["trend_up"], width=2, dash="solid"),
                    opacity=0.7, showlegend=True
                ), row=pr, col=1)

            if len(trend_lines['downtrend']) >= 2:
                x_vals, y_vals = zip(*trend_lines['downtrend'])
                fig.add_trace(go.Scatter(
                    x=x_vals, y=y_vals,
                    mode="lines", name="Downtrend",
                    line=dict(color=self.COLORS["trend_down"], width=2, dash="solid"),
                    opacity=0.7, showlegend=True
                ), row=pr, col=1)

            # ── 10. Recent high / low reference lines ─────────────────────────
            if pivots:
                try:
                    hp = [p for p in pivots[-5:] if p.type == 'high']
                    lp = [p for p in pivots[-5:] if p.type == 'low']
                    if hp:
                        recent_high = max(p.price for p in hp)
                        fig.add_hline(
                            y=recent_high, row=pr, col=1,
                            line=dict(color=self.COLORS["pivot_high"], dash="dash", width=1),
                            annotation_text=f"Recent High: {recent_high:.2f}",
                            annotation_position="right"
                        )
                    if lp:
                        recent_low = min(p.price for p in lp)
                        fig.add_hline(
                            y=recent_low, row=pr, col=1,
                            line=dict(color=self.COLORS["pivot_low"], dash="dash", width=1),
                            annotation_text=f"Recent Low: {recent_low:.2f}",
                            annotation_position="right"
                        )
                except Exception:
                    pass

            # ── 11. Subplot indicators — driven purely by registry ─────────────
            for spec in subplot_specs:
                row = row_of[spec.key]
                series = _load_series(spec, trend_data, self._clean_data)
                spec.render_fn(fig, x, series, row, self.COLORS)
                y_kwargs = {}
                if spec.y_range:
                    y_kwargs["range"] = spec.y_range
                fig.update_yaxes(
                    title_text=spec.y_label,
                    title_font=dict(size=9, color=self.COLORS["text"]),
                    row=row, col=1,
                    **y_kwargs,
                )

            # ── 12. Volume panel ──────────────────────────────────────────────
            if has_vol:
                vr = row_of["volume"]
                vol_colors = []
                for i, v in enumerate(volume):
                    if v is None or i == 0:
                        vol_colors.append(self.COLORS["vol_up"])
                    elif close[i] is not None and close[i - 1] is not None:
                        vol_colors.append(
                            self.COLORS["vol_up"] if close[i] >= close[i - 1]
                            else self.COLORS["vol_down"]
                        )
                    else:
                        vol_colors.append(self.COLORS["vol_up"])

                fig.add_trace(go.Bar(
                    x=x, y=volume, name="Volume",
                    marker_color=vol_colors,
                    hovertemplate="Vol: %{y:,.0f}<extra></extra>",
                    showlegend=False,
                ), row=vr, col=1)
                fig.update_yaxes(
                    title_text="Vol",
                    title_font=dict(size=8, color=self.COLORS["text"]),
                    row=vr, col=1,
                )

            # ── 13. Active signal annotation ──────────────────────────────────
            _SIG_STYLE = {
                "BUY_CALL": ("#a6e3a1", "📈"),
                "BUY_PUT": ("#89b4fa", "📉"),
                "SELL_CALL": ("#f38ba8", "🔴"),
                "SELL_PUT": ("#fab387", "🔵"),
                "HOLD": ("#f9e2af", "⏸"),
            }
            if signal_value in _SIG_STYLE:
                sc, ico = _SIG_STYLE[signal_value]
                last_c = next((v for v in reversed(close) if v is not None), None)
                if last_c is not None:
                    fig.add_annotation(
                        x=n - 1, y=last_c,
                        text=f"  {ico} {signal_value}",
                        showarrow=False,
                        font=dict(size=11, color=sc),
                        xanchor="left",
                        bgcolor=f"{sc}22",
                        bordercolor=sc,
                        borderwidth=1,
                        row=pr, col=1,
                    )

            # ── 14. Global layout ─────────────────────────────────────────────
            active_label = " · ".join(
                k.upper().replace("_", " ") for k in self._active_keys
            ) or "Price Structure"

            fig.update_layout(
                title=dict(
                    text=(
                        f"Market Structure Analysis - {market_phase.upper()}"
                        f"<br><sup style='color:{self.COLORS['text']};font-size:10px'>"
                        f"Active: {active_label}</sup>"
                    ),
                    font=dict(color=self.TEXT_COLOR, size=14)
                ),
                paper_bgcolor=self.DARK_BG,
                plot_bgcolor=self.CARD_BG,
                font=dict(color=self.TEXT_COLOR, family="Segoe UI, sans-serif", size=11),
                legend=dict(
                    bgcolor=self.CARD_BG,
                    bordercolor=self.GRID_COLOR,
                    borderwidth=1,
                    font=dict(size=10),
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                margin=dict(l=50, r=80, t=60, b=20),
                hovermode="x unified",
                hoverlabel=dict(
                    bgcolor=self.CARD_BG,
                    font_size=10,
                    font_family="Consolas, monospace"
                ),
                xaxis_rangeslider_visible=False,
            )

            # ── 15. Axis styling ──────────────────────────────────────────────
            # Hide x-tick labels on all rows except the bottom
            fig.update_xaxes(
                gridcolor=self.GRID_COLOR,
                zeroline=False,
                showgrid=True,
                tickfont=dict(size=9),
                showticklabels=False,
            )
            # Show x labels only on bottom row
            fig.update_xaxes(
                showticklabels=True,
                title="Bar Number",
                row=n_rows, col=1,
            )
            fig.update_yaxes(
                gridcolor=self.GRID_COLOR,
                zeroline=False,
                showgrid=True,
                tickfont=dict(size=9),
            )
            fig.update_yaxes(title="Price", row=pr, col=1)

            # ── 16. Serialise to HTML ─────────────────────────────────────────
            html = fig.to_html(
                include_plotlyjs="cdn",
                full_html=True,
                config={
                    "displayModeBar": True,
                    "displaylogo": False,
                    "responsive": True,
                    "scrollZoom": True,
                    "doubleClick": "reset",
                    "showTips": True,
                    "modeBarButtonsToRemove": ["lasso2d", "select2d"]
                }
            )

            # Add custom CSS for performance
            css = """
            <style>
                .plotly-graph-div {
                    contain: strict;
                    width: 100%;
                    height: 100%;
                }
                .main-svg {
                    contain: strict;
                }
                .js-plotly-plot {
                    width: 100%;
                    height: 100%;
                }
                /* Tooltip styling */
                .hovertext text {
                    fill: #e6edf3 !important;
                }
            </style>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            """

            # Insert CSS before closing head
            html = html.replace("</head>", css + "</head>")

            return html

        except Exception as e:
            logger.error(f"Chart HTML generation failed: {e}", exc_info=True)
            return None
