# chart_widget.py - Simplified chart with market structure and detailed signal data
"""
Simplified chart widget with:
- Market structure detection (HH/HL/LH/LL)
- Trend line visualization
- Support and resistance levels
- Pivot points
- Volume as simple bar chart
- Detailed signal data tab with indicator values and rule results
- Clean, minimal design with only Spot chart
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Callable, Union

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from PyQt5.QtCore import QSize, QTimer, pyqtSignal, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage
from PyQt5.QtWidgets import (
    QVBoxLayout, QWidget, QLabel, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QGroupBox, QFileDialog, QMessageBox, QProgressBar, QTabWidget
)

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class TimeFrame(Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


@dataclass
class PivotPoint:
    """Market structure pivot point"""
    index: int
    price: float
    type: str  # 'high' | 'low'
    strength: int  # 1–3
    timestamp: Optional[datetime] = None
    structure: Optional[str] = None  # 'HH', 'HL', 'LH', 'LL'


@dataclass
class DrawingObject:
    """User-drawn object on chart"""
    type: str  # 'trend_line', 'horizontal_line'
    points: List[Tuple[float, float]]
    color: str = "#58a6ff"
    width: int = 2
    style: str = "solid"  # 'solid', 'dash', 'dot'
    text: Optional[str] = None
    visible: bool = True
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class TradeAnnotation:
    """Trade entry/exit annotation"""
    entry_price: float
    entry_time: Union[datetime, int, float]
    exit_price: Optional[float] = None
    exit_time: Optional[Union[datetime, int, float]] = None
    position_type: str = "CALL"  # 'CALL', 'PUT'
    quantity: int = 1
    pnl: Optional[float] = None
    color: str = "#3fb950"


# =============================================================================
# MARKET STRUCTURE ANALYZER
# =============================================================================

class MarketStructureAnalyzer:
    """Market structure analyzer for pivot points and trend lines"""

    def __init__(self, left_bars: int = 5, right_bars: int = 5):
        self.left_bars = max(1, left_bars)
        self.right_bars = max(1, right_bars)
        self.min_strength = 1
        self.structure_history: List[Dict] = []
        self.trend_lines: Dict[str, List[Tuple[int, float]]] = {
            "uptrend": [],
            "downtrend": [],
            "support": [],
            "resistance": []
        }

    def find_pivot_points(self, high: List[float], low: List[float],
                          timestamps: Optional[List] = None) -> List[PivotPoint]:
        """
        Find pivot points with strength calculation
        """
        try:
            if not high or not low or len(high) < self.left_bars + self.right_bars + 1:
                return []

            pivots = []
            n = len(high)

            # Calculate average range for strength detection
            price_range = (max(high) - min(low)) or 1

            for i in range(self.left_bars, n - self.right_bars):
                try:
                    # Pivot High detection
                    is_ph = True
                    ph_strength = 0
                    ph_diffs = []

                    for j in range(i - self.left_bars, i + self.right_bars + 1):
                        if j != i and j < len(high):
                            if high[j] >= high[i]:
                                is_ph = False
                                break
                            ph_diffs.append(high[i] - high[j])

                    if is_ph and ph_diffs:
                        avg_diff = sum(ph_diffs) / len(ph_diffs)
                        # Strength based on how much higher this pivot is
                        ph_strength = min(3, int((avg_diff / price_range) * 15))

                        timestamp = timestamps[i] if timestamps and i < len(timestamps) else None
                        pivots.append(PivotPoint(
                            index=i,
                            price=high[i],
                            type='high',
                            strength=max(1, ph_strength),
                            timestamp=timestamp
                        ))

                    # Pivot Low detection
                    is_pl = True
                    pl_strength = 0
                    pl_diffs = []

                    for j in range(i - self.left_bars, i + self.right_bars + 1):
                        if j != i and j < len(low):
                            if low[j] <= low[i]:
                                is_pl = False
                                break
                            pl_diffs.append(low[j] - low[i])

                    if is_pl and pl_diffs:
                        avg_diff = sum(pl_diffs) / len(pl_diffs)
                        # Strength based on how much lower this pivot is
                        pl_strength = min(3, int((avg_diff / price_range) * 15))

                        timestamp = timestamps[i] if timestamps and i < len(timestamps) else None
                        pivots.append(PivotPoint(
                            index=i,
                            price=low[i],
                            type='low',
                            strength=max(1, pl_strength),
                            timestamp=timestamp
                        ))

                except Exception as e:
                    logger.debug(f"Error processing pivot at index {i}: {e}")
                    continue

            # Sort by index
            pivots.sort(key=lambda x: x.index)

            # Identify structure (HH/HL/LH/LL)
            pivots = self._identify_structure(pivots)

            # Update trend lines
            # self._update_trend_lines(pivots)

            return pivots

        except Exception as e:
            logger.error(f"[MarketStructureAnalyzer.find_pivot_points] Failed: {e}")
            return []

    def _identify_structure(self, pivots: List[PivotPoint]) -> List[PivotPoint]:
        """Identify higher highs, higher lows, etc."""
        if len(pivots) < 2:
            return pivots

        high_pivots = [p for p in pivots if p.type == 'high']
        low_pivots = [p for p in pivots if p.type == 'low']

        # Process highs
        for i, p in enumerate(high_pivots):
            if i == 0:
                p.structure = "NONE"
            else:
                prev = high_pivots[i - 1]
                p.structure = "HH" if p.price > prev.price else "LH"

        # Process lows
        for i, p in enumerate(low_pivots):
            if i == 0:
                p.structure = "NONE"
            else:
                prev = low_pivots[i - 1]
                p.structure = "HL" if p.price > prev.price else "LL"

        # Update original list
        pivot_dict = {p.index: p for p in pivots}
        for p in pivot_dict.values():
            # Find matching high/low
            for hp in high_pivots:
                if hp.index == p.index:
                    p.structure = hp.structure
                    break
            for lp in low_pivots:
                if lp.index == p.index:
                    p.structure = lp.structure
                    break

        return pivots

    def _update_trend_lines(self, pivots: List[PivotPoint]):
        """Update trend lines based on pivot points"""
        self.trend_lines = {"uptrend": [], "downtrend": [], "support": [], "resistance": []}

        # Connect HL for uptrend lines
        hl_pivots = [p for p in pivots if p.structure == "HL"]
        for i in range(1, len(hl_pivots)):
            self.trend_lines["uptrend"].append((hl_pivots[i - 1].index, hl_pivots[i - 1].price))
            self.trend_lines["uptrend"].append((hl_pivots[i].index, hl_pivots[i].price))

        # Connect LH for downtrend lines
        lh_pivots = [p for p in pivots if p.structure == "LH"]
        for i in range(1, len(lh_pivots)):
            self.trend_lines["downtrend"].append((lh_pivots[i - 1].index, lh_pivots[i - 1].price))
            self.trend_lines["downtrend"].append((lh_pivots[i].index, lh_pivots[i].price))

        # Support lines (recent HL)
        if hl_pivots:
            latest_hl = hl_pivots[-1]
            self.trend_lines["support"].append((latest_hl.index, latest_hl.price))

        # Resistance lines (recent LH)
        if lh_pivots:
            latest_lh = lh_pivots[-1]
            self.trend_lines["resistance"].append((latest_lh.index, latest_lh.price))

    def get_market_phase(self, pivots: List[PivotPoint], lookback: int = 8) -> str:
        """Determine market phase (uptrend, downtrend, ranging)"""
        if len(pivots) < 4:
            return 'neutral'

        recent = pivots[-min(lookback, len(pivots)):]

        # Count structure types
        hh = sum(1 for p in recent if p.structure == "HH")
        hl = sum(1 for p in recent if p.structure == "HL")
        lh = sum(1 for p in recent if p.structure == "LH")
        ll = sum(1 for p in recent if p.structure == "LL")

        total = hh + hl + lh + ll
        if total == 0:
            return 'neutral'

        # Calculate ratios
        uptrend_score = (hh + hl) / total
        downtrend_score = (lh + ll) / total

        if uptrend_score > 0.7:
            return 'strong_uptrend'
        elif uptrend_score > 0.55:
            return 'uptrend'
        elif downtrend_score > 0.7:
            return 'strong_downtrend'
        elif downtrend_score > 0.55:
            return 'downtrend'
        else:
            return 'ranging'


# =============================================================================
# SPOT CHART WIDGET
# =============================================================================

class SpotChartWidget(QWebEngineView):
    """
    Simplified chart widget focusing on Spot market structure:
    - Candlestick/Line chart
    - Volume as simple bar chart
    - Pivot points (HH/HL/LH/LL)
    - Trend lines
    - Support/Resistance levels
    - Trade annotations
    """

    # Signals
    chart_clicked = pyqtSignal(float, float)  # x, y
    trade_marked = pyqtSignal(dict)  # trade annotation
    timeframe_changed = pyqtSignal(str)  # new timeframe

    # Color scheme
    DARK_BG = "#0d1117"
    CARD_BG = "#161b22"
    TEXT_COLOR = "#e6edf3"
    GRID_COLOR = "#30363d"
    CHART_COLORS = {
        "candle_up": "#3fb950",
        "candle_down": "#f85149",
        "candle_up_wick": "#2ea043",
        "candle_down_wick": "#da3633",
        "line": "#58a6ff",
        "pivot_high": "#f0883e",
        "pivot_low": "#58a6ff",
        "hh": "#7ee37d",
        "hl": "#58a6ff",
        "lh": "#f85149",
        "ll": "#db6d28",
        "trend_up": "#3fb950",
        "trend_down": "#f85149",
        "support": "#58a6ff",
        "resistance": "#f0883e",
        "volume_up": "rgba(63, 185, 80, 0.45)",
        "volume_down": "rgba(248, 81, 73, 0.45)",
    }

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setStyleSheet(f"background: {self.DARK_BG}; border: none;")
            self.setMinimumSize(QSize(600, 400))

            # Configure WebEngine
            self._setup_web_engine()

            # Chart configuration
            self._config = None
            self._signal_engine = None
            self._symbol = "Spot Index"
            self._timeframe = TimeFrame.M5
            self._chart_type = "candlestick"  # 'candlestick' or 'line'

            # Data
            self._data: Dict[str, List] = {
                "open": [], "high": [], "low": [], "close": [], "volume": [],
                "timestamp": [], "datetime": []
            }
            self._drawings: List[DrawingObject] = []
            self._trade_annotations: List[TradeAnnotation] = []

            # Analysis
            self.analyzer = MarketStructureAnalyzer(left_bars=5, right_bars=5)
            self._pivots: List[PivotPoint] = []
            self._market_phase = "neutral"

            # UI State
            self._drawing_mode = None
            self._show_volume = True
            self._show_grid = True
            self._show_legend = True
            self._show_pivots = True
            self._show_trend_lines = True

            # Performance
            self._last_data_fingerprint = ""
            self._pending_data = None
            self._update_timer = QTimer()
            self._update_timer.setSingleShot(True)
            self._update_timer.timeout.connect(self._perform_update)

            # Cache
            self._html_cache = {}
            self._max_cache_size = 10
            self._error_count = 0
            self._max_errors = 3

            # Drawing tools
            self._drawing_color = "#58a6ff"
            self._drawing_width = 2
            self._drawing_style = "solid"

            # Initialize
            self._show_placeholder()

            logger.info("SpotChartWidget initialized")

        except Exception as e:
            logger.critical(f"[SpotChartWidget.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self._show_error_placeholder(str(e))

    def _safe_defaults_init(self):
        """Initialize all attributes with safe defaults"""
        self._config = None
        self._signal_engine = None
        self._symbol = "Spot Index"
        self._timeframe = TimeFrame.M5
        self._chart_type = "candlestick"
        self._data = {"open": [], "high": [], "low": [], "close": [], "volume": [], "timestamp": [], "datetime": []}
        self._drawings = []
        self._trade_annotations = []
        self.analyzer = None
        self._pivots = []
        self._market_phase = "neutral"
        self._drawing_mode = None
        self._show_volume = True
        self._show_grid = True
        self._show_legend = True
        self._show_pivots = True
        self._show_trend_lines = True
        self._last_data_fingerprint = ""
        self._pending_data = None
        self._update_timer = None
        self._html_cache = {}
        self._max_cache_size = 10
        self._error_count = 0
        self._max_errors = 3
        self._drawing_color = "#58a6ff"
        self._drawing_width = 2
        self._drawing_style = "solid"
        self._web_profile = None
        self._web_page = None

    def _setup_web_engine(self):
        """Configure WebEngine for better performance"""
        try:
            self._web_profile = QWebEngineProfile.defaultProfile()
            self._web_profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
            self._web_profile.setHttpCacheMaximumSize(50 * 1024 * 1024)  # 50 MB

            self._web_page = QWebEnginePage(self._web_profile, self)
            self.setPage(self._web_page)

        except Exception as e:
            logger.error(f"[SpotChartWidget._setup_web_engine] Failed: {e}")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def set_config(self, config, signal_engine=None) -> None:
        """Set configuration and signal engine"""
        try:
            self._config = config
            self._signal_engine = signal_engine
            self._last_data_fingerprint = ""
            self._html_cache.clear()
            logger.debug("Chart config set")
        except Exception as e:
            logger.error(f"[SpotChartWidget.set_config] Failed: {e}")

    def set_symbol(self, symbol: str) -> None:
        """Set chart symbol"""
        self._symbol = symbol
        self._last_data_fingerprint = ""

    def set_timeframe(self, timeframe: TimeFrame) -> None:
        """Set chart timeframe and immediately re-render"""
        self._timeframe = timeframe
        self._last_data_fingerprint = ""
        self._html_cache.clear()
        self.timeframe_changed.emit(timeframe.value)
        if self._data and self._data.get("close"):
            self._pending_data = self._data
            if self._update_timer:
                self._update_timer.start(50)

    def set_chart_type(self, chart_type: str) -> None:
        """Set chart type ('candlestick' or 'line')"""
        self._chart_type = chart_type
        self._last_data_fingerprint = ""
        self._html_cache.clear()
        if self._data and self._data.get("close"):
            self._pending_data = self._data
            if self._update_timer:
                self._update_timer.start(50)

    def toggle_volume(self, show: bool) -> None:
        """Toggle volume visibility"""
        self._show_volume = show
        self._last_data_fingerprint = ""
        if self._data and self._data.get("close"):
            self._pending_data = self._data
            if self._update_timer:
                self._update_timer.start(50)

    def update_data(self, data: Dict[str, List]) -> None:
        """Update chart data"""
        try:
            if not data or not data.get("close"):
                return

            # Validate data
            required = ["open", "high", "low", "close"]
            for key in required:
                if key not in data:
                    data[key] = data["close"]

            # Store data
            self._data = data

            # Generate fingerprint
            fp = self._fingerprint(data)
            if fp == self._last_data_fingerprint:
                return

            self._last_data_fingerprint = fp

            # Check cache
            if fp in self._html_cache:
                self.setHtml(self._html_cache[fp])
                return

            # Schedule update
            self._pending_data = data
            if self._update_timer:
                self._update_timer.start(300)

        except Exception as e:
            logger.error(f"[SpotChartWidget.update_data] Failed: {e}")
            self._error_count += 1
            if self._error_count >= self._max_errors:
                self._show_error_placeholder(str(e))

    def update_chart(self, trend_data: dict) -> None:
        """Backward compatibility: convert trend_data to OHLCV format"""
        try:
            if not trend_data:
                return

            # Extract OHLCV data from trend_data
            data = {
                "open": trend_data.get("open", []),
                "high": trend_data.get("high", []),
                "low": trend_data.get("low", []),
                "close": trend_data.get("close", []),
                "volume": trend_data.get("volume", []),
                "timestamp": trend_data.get("timestamps", [])
            }

            # Add datetime if timestamps available
            if data["timestamp"]:
                data["datetime"] = [datetime.fromtimestamp(ts) for ts in data["timestamp"]]

            self.update_data(data)

        except Exception as e:
            logger.error(f"[SpotChartWidget.update_chart] Failed: {e}")

    def add_drawing(self, drawing: DrawingObject) -> None:
        """Add a drawing object"""
        self._drawings.append(drawing)
        self._last_data_fingerprint = ""

    def clear_drawings(self) -> None:
        """Remove all drawings"""
        self._drawings.clear()
        self._last_data_fingerprint = ""

    def add_trade_annotation(self, annotation: TradeAnnotation) -> None:
        """Add a trade annotation"""
        self._trade_annotations.append(annotation)
        self._last_data_fingerprint = ""
        self.trade_marked.emit({
            "entry": annotation.entry_price,
            "exit": annotation.exit_price,
            "type": annotation.position_type,
            "pnl": annotation.pnl
        })

    def clear_trade_annotations(self) -> None:
        """Remove all trade annotations"""
        self._trade_annotations.clear()
        self._last_data_fingerprint = ""

    def set_drawing_mode(self, mode: Optional[str]) -> None:
        """Set drawing mode (trend_line, horizontal_line, etc.)"""
        self._drawing_mode = mode

    def export_chart(self, format: str = "png") -> None:
        """Export chart as image"""
        try:
            if format == "png":
                # Take screenshot
                self.grab().save(f"chart_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                QMessageBox.information(self, "Export", "Chart exported as PNG")
        except Exception as e:
            logger.error(f"[SpotChartWidget.export_chart] Failed: {e}")
            QMessageBox.critical(self, "Export Failed", str(e))

    def clear_cache(self) -> None:
        """Clear HTML cache"""
        self._html_cache.clear()
        self._last_data_fingerprint = ""

    def toggle_pivots(self, show: bool) -> None:
        """Toggle pivot points visibility"""
        self._show_pivots = show
        self._last_data_fingerprint = ""
        if self._data and self._data.get("close"):
            self._pending_data = self._data
            if self._update_timer:
                self._update_timer.start(50)

    def toggle_trend_lines(self, show: bool) -> None:
        """Toggle trend lines visibility"""
        self._show_trend_lines = show
        self._last_data_fingerprint = ""
        if self._data and self._data.get("close"):
            self._pending_data = self._data
            if self._update_timer:
                self._update_timer.start(50)

    def toggle_grid(self, show: bool) -> None:
        """Toggle grid visibility"""
        self._show_grid = show
        self._last_data_fingerprint = ""
        if self._data and self._data.get("close"):
            self._pending_data = self._data
            if self._update_timer:
                self._update_timer.start(50)

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _fingerprint(self, data: Dict) -> str:
        """Generate fingerprint for caching"""
        try:
            if not data:
                return ""

            close = data.get("close", [])
            if not close:
                return ""

            n = len(close)
            last_5 = close[-5:] if n >= 5 else close

            # Include drawing and annotation count in fingerprint
            draw_count = len(self._drawings)
            trade_count = len(self._trade_annotations)

            return f"{n}:{last_5}:{draw_count}:{trade_count}:{self._chart_type}:{self._show_pivots}:{self._show_trend_lines}:{self._show_volume}"

        except Exception as e:
            logger.debug(f"Fingerprint failed: {e}")
            return ""

    def _perform_update(self):
        """Perform chart update - filtered for today only"""
        if self._pending_data is None:
            return

        data = self._pending_data
        self._pending_data = None

        try:
            # Filter data to show only today
            filtered_data = self._filter_today_data(data)

            if not filtered_data or not filtered_data.get("close"):
                self._show_placeholder("No data for today")
                return

            # Run analysis on filtered data
            self._analyze_data(filtered_data)

            # Generate HTML with filtered data
            html = self._generate_chart_html(filtered_data)
            if html:
                fp = self._fingerprint(filtered_data)
                if fp and len(self._html_cache) < self._max_cache_size:
                    self._html_cache[fp] = html
                self.setHtml(html)
            else:
                self._show_placeholder("Insufficient data for chart")

        except Exception as e:
            logger.error(f"Chart update error: {e}", exc_info=True)
            self._show_error_placeholder(str(e))

    def _filter_today_data(self, data: Dict[str, List]) -> Dict[str, List]:
        """Filter data to show only today's trading session"""
        try:
            timestamps = data.get("timestamp", [])
            if not timestamps:
                return data

            # Get today's date (midnight)
            import datetime
            now = datetime.datetime.now()
            today_start = datetime.datetime(now.year, now.month, now.day).timestamp()

            # Find indices for today's data
            today_indices = []
            for i, ts in enumerate(timestamps):
                if ts >= today_start:
                    today_indices.append(i)

            if not today_indices:
                # If no timestamps from today, take last 50 bars as fallback
                logger.warning("No today's data found, using last 50 bars")
                n = len(timestamps)
                start_idx = max(0, n - 50)
                today_indices = list(range(start_idx, n))

            # Filter all arrays to keep only today's indices
            filtered_data = {}
            for key, values in data.items():
                if isinstance(values, (list, tuple)) and len(values) == len(timestamps):
                    filtered_data[key] = [values[i] for i in today_indices]
                else:
                    filtered_data[key] = values  # Keep non-list data as is

            return filtered_data

        except Exception as e:
            logger.error(f"[SpotChartWidget._filter_today_data] Failed: {e}")
            return data  # Return original on error

    def _analyze_data(self, data: Dict[str, List]) -> None:
        """Analyze market structure"""
        try:
            high = data.get("high", [])
            low = data.get("low", [])
            timestamps = data.get("timestamp", [])

            if not high or not low:
                return

            # Find pivots
            self._pivots = self.analyzer.find_pivot_points(high, low, timestamps)

            # Determine market phase
            self._market_phase = self.analyzer.get_market_phase(self._pivots)

        except Exception as e:
            logger.error(f"[SpotChartWidget._analyze_data] Failed: {e}")

    def _generate_chart_html(self, data: Dict[str, List]) -> Optional[str]:
        """Generate Plotly HTML with bar chart volume"""
        if not data or not data.get("close"):
            return None

        try:
            # Prepare data
            close = self._clean_data(data.get("close", []))
            if not close:
                return None

            n = len(close)
            if n < 5:
                return None

            # Create x-axis labels
            timestamps = data.get("timestamp", [])
            if timestamps and len(timestamps) == n:
                x = [datetime.fromtimestamp(ts).strftime("%H:%M") for ts in timestamps]
            else:
                x = list(range(n))

            # Determine number of rows
            has_volume = bool(self._show_volume and data.get("volume"))

            if has_volume:
                # 2 rows: price chart + volume bar chart
                fig = make_subplots(
                    rows=2,
                    cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.05,
                    row_heights=[0.7, 0.3],
                    subplot_titles=["Price", "Volume"]
                )

                # Add price trace (row 1)
                self._add_price_trace(fig, data, x, 1)
                self._add_pivots(fig, x, 1)
                self._add_trend_lines(fig, x, 1)
                self._add_drawings(fig, x, data, 1)
                self._add_trade_annotations(fig, x, data, 1)

                # Add volume trace as bar chart (row 2)
                self._add_volume_trace(fig, data, x, 2)

                # Apply layout for 2 rows
                self._apply_layout(fig, 2)

            else:
                # Single chart - no volume
                fig = make_subplots(
                    rows=1,
                    cols=1,
                    shared_xaxes=True,
                    subplot_titles=["Price"]
                )

                self._add_price_trace(fig, data, x, 1)
                self._add_pivots(fig, x, 1)
                self._add_trend_lines(fig, x, 1)
                self._add_drawings(fig, x, data, 1)
                self._add_trade_annotations(fig, x, data, 1)

                self._apply_layout(fig, 1)

            # Convert to HTML
            html = fig.to_html(
                include_plotlyjs="cdn",
                full_html=True,
                config={
                    "displayModeBar": True,
                    "displaylogo": False,
                    "responsive": True,
                    "scrollZoom": True,
                    "doubleClick": "reset",
                }
            )

            # Add custom CSS
            css = self._get_custom_css()
            html = html.replace("</head>", css + "</head>")

            return html

        except Exception as e:
            logger.error(f"[SpotChartWidget._generate_chart_html] Failed: {e}", exc_info=True)
            return None

    def _add_price_trace(self, fig: go.Figure, data: Dict, x: List, row: int):
        """Add price trace based on chart type"""
        open_p = self._clean_data(data.get("open", []))
        high = self._clean_data(data.get("high", []))
        low = self._clean_data(data.get("low", []))
        close = self._clean_data(data.get("close", []))

        if self._chart_type == "candlestick":
            fig.add_trace(go.Candlestick(
                x=x, open=open_p, high=high, low=low, close=close,
                name="Spot",
                increasing=dict(
                    line=dict(color=self.CHART_COLORS["candle_up"]),
                    fillcolor=self.CHART_COLORS["candle_up"]
                ),
                decreasing=dict(
                    line=dict(color=self.CHART_COLORS["candle_down"]),
                    fillcolor=self.CHART_COLORS["candle_down"]
                ),
                showlegend=False,
            ), row=row, col=1)
        else:  # line chart
            fig.add_trace(go.Scatter(
                x=x, y=close, name="Spot",
                line=dict(color=self.CHART_COLORS["line"], width=2),
                mode="lines",
                showlegend=False,
            ), row=row, col=1)

    def _add_volume_trace(self, fig: go.Figure, data: Dict, x: List, row: int):
        """Add volume trace as simple bar chart"""
        volume = self._clean_data(data.get("volume", []))
        close = self._clean_data(data.get("close", []))

        # Color volume based on price movement (simple up/down coloring)
        vol_colors = []
        for i, v in enumerate(volume):
            if i == 0 or close[i] is None or close[i - 1] is None:
                vol_colors.append(self.CHART_COLORS["volume_up"])
            elif close[i] >= close[i - 1]:
                vol_colors.append(self.CHART_COLORS["volume_up"])
            else:
                vol_colors.append(self.CHART_COLORS["volume_down"])

        fig.add_trace(go.Bar(
            x=x, y=volume, name="Volume",
            marker_color=vol_colors,
            hovertemplate="Vol: %{y:,.0f}<extra></extra>",
            showlegend=False,
        ), row=row, col=1)

    def _add_pivots(self, fig: go.Figure, x: List, row: int):
        """Add pivot points to chart"""
        if not self._show_pivots or not self._pivots:
            return

        px_list, py_list, pcol_list, ptext_list, psize_list = [], [], [], [], []

        for p in self._pivots:
            try:
                idx = p.index if p.index < len(x) else len(x) - 1
                px_list.append(x[idx] if idx >= 0 else p.index)
                py_list.append(p.price)

                # Color based on structure
                if p.structure == "HH":
                    pcol_list.append(self.CHART_COLORS["hh"])
                    ptext_list.append(f"HH")
                    psize_list.append(10 + p.strength * 3)
                elif p.structure == "HL":
                    pcol_list.append(self.CHART_COLORS["hl"])
                    ptext_list.append(f"HL")
                    psize_list.append(10 + p.strength * 3)
                elif p.structure == "LH":
                    pcol_list.append(self.CHART_COLORS["lh"])
                    ptext_list.append(f"LH")
                    psize_list.append(10 + p.strength * 3)
                elif p.structure == "LL":
                    pcol_list.append(self.CHART_COLORS["ll"])
                    ptext_list.append(f"LL")
                    psize_list.append(10 + p.strength * 3)
                else:
                    color = self.CHART_COLORS["pivot_high"] if p.type == 'high' else self.CHART_COLORS["pivot_low"]
                    pcol_list.append(color)
                    ptext_list.append(f"Pivot")
                    psize_list.append(8 + p.strength * 2)

            except Exception as e:
                logger.debug(f"Error adding pivot: {e}")
                continue

        if px_list:
            fig.add_trace(go.Scatter(
                x=px_list, y=py_list, mode="markers+text", name="Pivots",
                marker=dict(
                    size=psize_list,
                    color=pcol_list,
                    symbol="circle",
                    line=dict(width=1, color="white")
                ),
                text=ptext_list,
                textposition="top center",
                textfont=dict(size=9, color="white"),
                hovertemplate="%{text}<br>Price: %{y:.2f}<extra></extra>",
                showlegend=False,
            ), row=row, col=1)

    def _add_trend_lines(self, fig: go.Figure, x: List, row: int):
        """Add trend lines to chart"""
        if not self._show_trend_lines:
            return

        # Uptrend lines (HL connections)
        if self.analyzer.trend_lines["uptrend"]:
            for i in range(0, len(self.analyzer.trend_lines["uptrend"]), 2):
                if i + 1 < len(self.analyzer.trend_lines["uptrend"]):
                    p1, p2 = self.analyzer.trend_lines["uptrend"][i], self.analyzer.trend_lines["uptrend"][i + 1]
                    fig.add_trace(go.Scatter(
                        x=[x[p1[0]] if p1[0] < len(x) else p1[0],
                           x[p2[0]] if p2[0] < len(x) else p2[0]],
                        y=[p1[1], p2[1]],
                        mode="lines",
                        line=dict(color=self.CHART_COLORS["trend_up"], width=2, dash="solid"),
                        name="Uptrend",
                        showlegend=False,
                    ), row=row, col=1)

        # Downtrend lines (LH connections)
        if self.analyzer.trend_lines["downtrend"]:
            for i in range(0, len(self.analyzer.trend_lines["downtrend"]), 2):
                if i + 1 < len(self.analyzer.trend_lines["downtrend"]):
                    p1, p2 = self.analyzer.trend_lines["downtrend"][i], self.analyzer.trend_lines["downtrend"][i + 1]
                    fig.add_trace(go.Scatter(
                        x=[x[p1[0]] if p1[0] < len(x) else p1[0],
                           x[p2[0]] if p2[0] < len(x) else p2[0]],
                        y=[p1[1], p2[1]],
                        mode="lines",
                        line=dict(color=self.CHART_COLORS["trend_down"], width=2, dash="solid"),
                        name="Downtrend",
                        showlegend=False,
                    ), row=row, col=1)

        # Support lines
        for idx, price in self.analyzer.trend_lines["support"]:
            if idx < len(x):
                fig.add_hline(
                    y=price,
                    line=dict(color=self.CHART_COLORS["support"], width=1, dash="dash"),
                    row=row, col=1,
                    annotation_text=f"S {price:.2f}",
                    annotation_position="right"
                )

        # Resistance lines
        for idx, price in self.analyzer.trend_lines["resistance"]:
            if idx < len(x):
                fig.add_hline(
                    y=price,
                    line=dict(color=self.CHART_COLORS["resistance"], width=1, dash="dash"),
                    row=row, col=1,
                    annotation_text=f"R {price:.2f}",
                    annotation_position="right"
                )

    def _add_drawings(self, fig: go.Figure, x: List, data: Dict, row: int):
        """Add user drawings to chart"""
        for drawing in self._drawings:
            if not drawing.visible:
                continue

            if drawing.type == "horizontal_line":
                y = drawing.points[0][1]
                fig.add_hline(
                    y=y,
                    line=dict(color=drawing.color, width=drawing.width, dash=drawing.style),
                    row=row, col=1,
                    annotation_text=drawing.text or f"{y:.2f}",
                    annotation_position="right"
                )

            elif drawing.type == "trend_line" and len(drawing.points) >= 2:
                x_coords = [p[0] for p in drawing.points[:2]]
                y_coords = [p[1] for p in drawing.points[:2]]

                # Convert x indices to labels
                x_labels = [x[int(xc)] if int(xc) < len(x) else xc for xc in x_coords]

                fig.add_trace(go.Scatter(
                    x=x_labels, y=y_coords,
                    mode="lines",
                    line=dict(color=drawing.color, width=drawing.width, dash=drawing.style),
                    name=drawing.text or "Trend Line",
                    showlegend=False,
                ), row=row, col=1)

    def _add_trade_annotations(self, fig: go.Figure, x: List, data: Dict, row: int):
        """Add trade annotations to chart"""
        for trade in self._trade_annotations:
            # Entry marker
            entry_x = x[trade.entry_time] if isinstance(trade.entry_time, int) and trade.entry_time < len(
                x) else trade.entry_time
            fig.add_trace(go.Scatter(
                x=[entry_x], y=[trade.entry_price],
                mode="markers+text",
                marker=dict(
                    symbol="triangle-up" if trade.position_type == "CALL" else "triangle-down",
                    size=12,
                    color=trade.color,
                    line=dict(width=1, color="white")
                ),
                text=["Entry"],
                textposition="bottom center",
                name=f"{trade.position_type} Entry",
                showlegend=False,
            ), row=row, col=1)

            # Exit marker if exists
            if trade.exit_price and trade.exit_time:
                exit_x = x[trade.exit_time] if isinstance(trade.exit_time, int) and trade.exit_time < len(
                    x) else trade.exit_time
                fig.add_trace(go.Scatter(
                    x=[exit_x], y=[trade.exit_price],
                    mode="markers+text",
                    marker=dict(
                        symbol="x",
                        size=12,
                        color=trade.color,
                        line=dict(width=1, color="white")
                    ),
                    text=["Exit"],
                    textposition="top center",
                    name=f"{trade.position_type} Exit",
                    showlegend=False,
                ), row=row, col=1)

                # Connect entry and exit
                fig.add_trace(go.Scatter(
                    x=[entry_x, exit_x], y=[trade.entry_price, trade.exit_price],
                    mode="lines",
                    line=dict(color=trade.color, width=2, dash="dot"),
                    showlegend=False,
                ), row=row, col=1)

                # Add P&L annotation
                if trade.pnl is not None:
                    color = self.CHART_COLORS["candle_up"] if trade.pnl > 0 else self.CHART_COLORS["candle_down"]
                    fig.add_annotation(
                        x=exit_x, y=trade.exit_price,
                        text=f"P&L: {trade.pnl:.2f}",
                        showarrow=True,
                        arrowhead=1,
                        font=dict(size=9, color=color),
                        row=row, col=1
                    )

    def _apply_layout(self, fig: go.Figure, rows: int):
        """Apply layout styling"""
        # Title
        title_text = f"{self._symbol} — {self._market_phase.upper()}"

        fig.update_layout(
            title=dict(
                text=title_text,
                font=dict(color=self.TEXT_COLOR, size=14),
                x=0.5,
            ),
            paper_bgcolor=self.DARK_BG,
            plot_bgcolor=self.CARD_BG,
            font=dict(color=self.TEXT_COLOR, family="Segoe UI, sans-serif", size=11),
            showlegend=self._show_legend,
            legend=dict(
                bgcolor=self.CARD_BG,
                bordercolor=self.GRID_COLOR,
                borderwidth=1,
                font=dict(size=10),
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
            ),
            margin=dict(l=50, r=80, t=80, b=20),
            hovermode="x unified",
            hoverlabel=dict(
                bgcolor=self.CARD_BG,
                font_size=10,
                font_family="Consolas, monospace"
            ),
        )

        # Axis styling
        for i in range(1, rows + 1):
            # X-axis
            fig.update_xaxes(
                gridcolor=self.GRID_COLOR if self._show_grid else None,
                zeroline=False,
                showgrid=self._show_grid,
                tickfont=dict(size=9),
                showticklabels=(i == rows),  # Only show labels on bottom subplot
                row=i, col=1
            )

            # Y-axis
            fig.update_yaxes(
                gridcolor=self.GRID_COLOR if self._show_grid else None,
                zeroline=False,
                showgrid=self._show_grid,
                tickfont=dict(size=9),
                row=i, col=1
            )

        # Price axis title
        fig.update_yaxes(title_text="Price", row=1, col=1)

        # Volume axis title
        if rows > 1:
            fig.update_yaxes(title_text="Volume", row=2, col=1)

    def _get_custom_css(self) -> str:
        """Get custom CSS for HTML"""
        return f"""
        <style>
            body, html {{
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                overflow: hidden;
                background-color: {self.DARK_BG};
            }}
            .plotly-graph-div, .js-plotly-plot {{
                width: 100%;
                height: 100%;
            }}
            .main-svg {{
                contain: strict;
            }}
            .hovertext text {{
                fill: {self.TEXT_COLOR} !important;
            }}
            .legend .bg {{
                fill: {self.CARD_BG} !important;
            }}
            .modebar {{
                background: {self.CARD_BG} !important;
                border: 1px solid {self.GRID_COLOR} !important;
                border-radius: 6px !important;
                padding: 2px !important;
            }}
            .modebar-btn {{
                color: {self.TEXT_COLOR} !important;
            }}
            .modebar-btn:hover {{
                color: {self.CHART_COLORS["pivot_low"]} !important;
            }}
        </style>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        """

    def _clean_data(self, data: Any) -> List[Optional[float]]:
        """Clean data by removing invalid values"""
        if data is None:
            return []

        try:
            if isinstance(data, np.ndarray):
                data = data.tolist()

            if not isinstance(data, (list, tuple)):
                return []

            cleaned = []
            for x in data:
                try:
                    if x is None:
                        cleaned.append(None)
                    elif isinstance(x, (int, float)) and not np.isnan(x) and np.isfinite(x):
                        cleaned.append(float(x))
                    elif isinstance(x, str):
                        xl = x.lower().strip()
                        if xl in ("nan", "none", "null", ""):
                            cleaned.append(None)
                        else:
                            try:
                                val = float(x)
                                cleaned.append(val if np.isfinite(val) else None)
                            except ValueError:
                                cleaned.append(None)
                    else:
                        cleaned.append(None)
                except Exception:
                    cleaned.append(None)
            return cleaned

        except Exception as e:
            logger.error(f"_clean_data failed: {e}")
            return []

    def _show_placeholder(self, message: str = "Waiting for market data…"):
        """Show placeholder when no data"""
        try:
            html = f"""<!DOCTYPE html>
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
                    .container {{
                        text-align: center;
                    }}
                    .msg {{
                        color: #8b949e;
                        font-size: 16px;
                        margin: 20px;
                    }}
                    .spinner {{
                        border: 3px solid {self.CARD_BG};
                        border-top: 3px solid {self.CHART_COLORS["pivot_low"]};
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
                <div class="container">
                    <div class="spinner"></div>
                    <div class="msg">📊 {message}</div>
                </div>
            </body>
            </html>"""
            self.setHtml(html)
        except Exception as e:
            logger.error(f"[SpotChartWidget._show_placeholder] Failed: {e}")

    def _show_error_placeholder(self, error_msg: str):
        """Show error message"""
        try:
            html = f"""<!DOCTYPE html>
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
                        color: {self.CHART_COLORS["candle_down"]};
                        font-size: 14px;
                        text-align: center;
                        padding: 30px;
                        border: 1px solid {self.CHART_COLORS["candle_down"]};
                        border-radius: 8px;
                        background: rgba(248, 81, 73, 0.1);
                        max-width: 400px;
                    }}
                    .error-title {{
                        font-size: 18px;
                        font-weight: bold;
                        margin-bottom: 15px;
                    }}
                </style>
            </head>
            <body>
                <div class="error">
                    <div class="error-title">❌ Chart Error</div>
                    <div>{error_msg}</div>
                </div>
            </body>
            </html>"""
            self.setHtml(html)
        except Exception as e:
            logger.error(f"[SpotChartWidget._show_error_placeholder] Failed: {e}")

    def resizeEvent(self, event):
        """Handle resize event"""
        try:
            super().resizeEvent(event)
            # Refresh chart on resize
            self._last_data_fingerprint = ""
            if self._data and self._data.get("close"):
                self.update_data(self._data)
        except Exception as e:
            logger.error(f"[SpotChartWidget.resizeEvent] Failed: {e}")
            super().resizeEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse press for drawing tools"""
        try:
            super().mousePressEvent(event)

            if self._drawing_mode:
                # Convert screen coordinates to data coordinates
                pos = event.pos()
                self.chart_clicked.emit(pos.x(), pos.y())

        except Exception as e:
            logger.error(f"[SpotChartWidget.mousePressEvent] Failed: {e}")
            super().mousePressEvent(event)

    def cleanup(self):
        """Clean up resources before shutdown"""
        try:
            logger.info("[SpotChartWidget] Starting cleanup")

            # Stop timer
            if self._update_timer and self._update_timer.isActive():
                self._update_timer.stop()

            # Clear cache
            self._html_cache.clear()
            self._drawings.clear()
            self._trade_annotations.clear()

            # Clear references
            self._config = None
            self._signal_engine = None
            self.analyzer = None
            self._update_timer = None
            self._web_profile = None
            self._web_page = None

            logger.info("[SpotChartWidget] Cleanup completed")

        except Exception as e:
            logger.error(f"[SpotChartWidget.cleanup] Error: {e}")


# =============================================================================
# DETAILED SIGNAL DATA TAB (FULLY PRESERVED)
# =============================================================================

# Shared colour map for all signal states
_SIG_COLORS: Dict[str, str] = {
    "BUY_CALL": "#3fb950",
    "BUY_PUT": "#58a6ff",
    "EXIT_CALL": "#f85149",
    "EXIT_PUT": "#f0883e",
    "HOLD": "#d29922",
    "WAIT": "#484f58",
}

_DARK = "#0d1117"
_CARD = "#161b22"
_BORDER = "#30363d"
_MUTED = "#8b949e"
_TEXT = "#e6edf3"


def _mk_table_style() -> str:
    return f"""
        QTableWidget {{
            background: {_DARK};
            alternate-background-color: {_CARD};
            color: {_TEXT};
            border: none;
            gridline-color: {_BORDER};
            font-family: "Consolas", "Courier New", monospace;
            font-size: 9pt;
            selection-background-color: #1f3a5f;
            selection-color: {_TEXT};
        }}
        QHeaderView::section {{
            background: {_CARD};
            color: {_MUTED};
            border: none;
            border-bottom: 1px solid {_BORDER};
            padding: 5px 10px;
            font-size: 8pt;
            font-weight: bold;
            letter-spacing: 0.8px;
            text-transform: uppercase;
        }}
        QTableWidget::item {{
            padding: 4px 10px;
            border-bottom: 1px solid #1c2128;
        }}
        QScrollBar:vertical {{
            background: {_CARD};
            width: 6px;
            border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{
            background: {_BORDER};
            border-radius: 3px;
            min-height: 20px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """


def _mk_group_style(accent: str = _BORDER) -> str:
    return f"""
        QGroupBox {{
            background: {_CARD};
            border: 1px solid {accent};
            border-radius: 6px;
            margin-top: 8px;
            padding: 10px 6px 6px 6px;
            color: {_TEXT};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: {_MUTED};
            font-size: 8pt;
            font-weight: normal;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
    """


class SignalDataTab(QWidget):
    """
    Fully detailed signal data panel with:
    - Signal badge
    - Confidence bar
    - Conflict indicator
    - Fired signal pills
    - Indicator values table (4 cols: name / current / prev / Δ)
    - Rule results table (4 cols: group / rule / detail / result)
    - Timestamp
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {_DARK}; color: {_TEXT};")
        self._build_ui()

    # ─────────────────────────────────────────────────────────────────
    # UI BUILD
    # ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        # ── row 1: badge + confidence + conflict ─────────────────────
        top = QHBoxLayout()
        top.setSpacing(10)

        self.signal_badge = QLabel("WAIT")
        self.signal_badge.setAlignment(Qt.AlignCenter)
        self.signal_badge.setFixedSize(200, 58)
        self._apply_badge("WAIT")
        top.addWidget(self.signal_badge)

        # confidence column
        conf_col = QVBoxLayout()
        conf_col.setSpacing(4)
        conf_lbl = QLabel("CONFIDENCE")
        conf_lbl.setStyleSheet(
            f"color:{_MUTED}; font-size:7pt; font-weight:bold; letter-spacing:1px;"
        )
        self.conf_bar = QProgressBar()
        self.conf_bar.setRange(0, 100)
        self.conf_bar.setValue(0)
        self.conf_bar.setTextVisible(True)
        self.conf_bar.setFixedHeight(22)
        self._set_conf_bar_color("#1f6feb")
        conf_col.addWidget(conf_lbl)
        conf_col.addWidget(self.conf_bar)
        conf_col.addStretch()
        top.addLayout(conf_col, 1)

        self.conflict_lbl = QLabel("✓  No Conflict")
        self.conflict_lbl.setAlignment(Qt.AlignCenter)
        self.conflict_lbl.setFixedSize(130, 40)
        self._apply_conflict(False)
        top.addWidget(self.conflict_lbl)

        root.addLayout(top)

        # ── row 2: fired-signal pills ─────────────────────────────────
        pills_box = QGroupBox("Active Signals")
        pills_box.setStyleSheet(_mk_group_style())
        pills_row = QHBoxLayout(pills_box)
        pills_row.setContentsMargins(8, 14, 8, 6)
        pills_row.setSpacing(8)

        self._pill_labels: Dict[str, QLabel] = {}
        for sig in ["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]:
            lbl = QLabel(sig.replace("_", " "))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedHeight(30)
            lbl.setMinimumWidth(88)
            self._apply_pill(lbl, sig, False)
            self._pill_labels[sig] = lbl
            pills_row.addWidget(lbl)

        pills_row.addStretch()
        root.addWidget(pills_box)

        # ── splitter: indicator table | rule table ────────────────────
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {_BORDER}; }}")

        # indicator table
        ind_box = QGroupBox("Indicator Values")
        ind_box.setStyleSheet(_mk_group_style())
        ind_inner = QVBoxLayout(ind_box)
        ind_inner.setContentsMargins(4, 14, 4, 4)

        self.ind_table = QTableWidget(0, 4)
        self.ind_table.setHorizontalHeaderLabels(["Indicator", "Current", "Prev", "Δ"])
        self.ind_table.setStyleSheet(_mk_table_style())
        self.ind_table.setAlternatingRowColors(True)
        self.ind_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ind_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ind_table.setSelectionMode(QTableWidget.SingleSelection)
        self.ind_table.verticalHeader().setVisible(False)
        self.ind_table.setShowGrid(False)
        hh = self.ind_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        ind_inner.addWidget(self.ind_table)
        splitter.addWidget(ind_box)

        # rule table
        rule_box = QGroupBox("Rule Results")
        rule_box.setStyleSheet(_mk_group_style())
        rule_inner = QVBoxLayout(rule_box)
        rule_inner.setContentsMargins(4, 14, 4, 4)

        self.rule_table = QTableWidget(0, 4)
        self.rule_table.setHorizontalHeaderLabels(["Group", "Rule", "Detail", "Result"])
        self.rule_table.setStyleSheet(_mk_table_style())
        self.rule_table.setAlternatingRowColors(True)
        self.rule_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.rule_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.rule_table.setSelectionMode(QTableWidget.SingleSelection)
        self.rule_table.verticalHeader().setVisible(False)
        self.rule_table.setShowGrid(False)
        rh = self.rule_table.horizontalHeader()
        rh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        rh.setSectionResizeMode(1, QHeaderView.Stretch)
        rh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        rh.setSectionResizeMode(3, QHeaderView.Fixed)
        self.rule_table.setColumnWidth(3, 90)
        rule_inner.addWidget(self.rule_table)
        splitter.addWidget(rule_box)

        splitter.setSizes([220, 360])
        root.addWidget(splitter, 1)

        # ── footer ────────────────────────────────────────────────────
        self.ts_label = QLabel("—")
        self.ts_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.ts_label.setStyleSheet(f"color:{_MUTED}; font-size:8pt;")
        root.addWidget(self.ts_label)

    # ─────────────────────────────────────────────────────────────────
    # STYLE HELPERS
    # ─────────────────────────────────────────────────────────────────

    def _apply_badge(self, sv: str):
        color = _SIG_COLORS.get(sv, _SIG_COLORS["WAIT"])
        active = sv != "WAIT"
        self.signal_badge.setText(sv.replace("_", " "))
        self.signal_badge.setStyleSheet(f"""
            QLabel {{
                background: {"" + color if active else _CARD};
                color: {"#ffffff" if active else _MUTED};
                border: 2px solid {color};
                border-radius: 8px;
                font-size: 14pt;
                font-weight: bold;
                letter-spacing: 1px;
            }}
        """)

    def _apply_conflict(self, has_conflict: bool):
        if has_conflict:
            self.conflict_lbl.setText("⚠  CONFLICT")
            self.conflict_lbl.setStyleSheet(f"""
                QLabel {{
                    color: #f85149;
                    background: rgba(248,81,73,0.10);
                    border: 1px solid #f85149;
                    border-radius: 6px;
                    font-size: 8pt;
                    font-weight: bold;
                    padding: 4px;
                }}
            """)
        else:
            self.conflict_lbl.setText("✓  No Conflict")
            self.conflict_lbl.setStyleSheet(f"""
                QLabel {{
                    color: {_MUTED};
                    background: {_CARD};
                    border: 1px solid {_BORDER};
                    border-radius: 6px;
                    font-size: 8pt;
                    padding: 4px;
                }}
            """)

    @staticmethod
    def _apply_pill(lbl: QLabel, sig: str, active: bool):
        color = _SIG_COLORS.get(sig, _SIG_COLORS["WAIT"])
        if active:
            lbl.setStyleSheet(f"""
                QLabel {{
                    background: {color};
                    color: #ffffff;
                    border: 2px solid {color};
                    border-radius: 5px;
                    font-size: 8pt;
                    font-weight: bold;
                    padding: 2px 6px;
                }}
            """)
        else:
            lbl.setStyleSheet(f"""
                QLabel {{
                    background: transparent;
                    color: {color};
                    border: 1px solid {color};
                    border-radius: 5px;
                    font-size: 8pt;
                    font-weight: bold;
                    padding: 2px 6px;
                }}
            """)

    def _set_conf_bar_color(self, color: str):
        self.conf_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {_CARD};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                text-align: center;
                color: {_TEXT};
                font-size: 8pt;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 4px;
            }}
        """)

    # ─────────────────────────────────────────────────────────────────
    # FORMATTING HELPERS
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_num(val) -> str:
        """Smart numeric formatter."""
        if val is None:
            return "—"
        try:
            f = float(val)
            if abs(f) >= 10_000:
                return f"{f:,.0f}"
            elif abs(f) >= 100:
                return f"{f:,.2f}"
            elif abs(f) >= 1:
                return f"{f:.4f}"
            else:
                return f"{f:.6f}"
        except (TypeError, ValueError):
            return str(val)

    @staticmethod
    def _fmt_key(key: str) -> str:
        """Turn snake_case indicator keys into readable names."""
        parts = key.split("_")
        return " ".join(
            p.upper() if len(p) <= 4 else p.capitalize()
            for p in parts
        )

    @staticmethod
    def _delta(curr, prev) -> Tuple[str, str]:
        """Return (text, colour) for the change column."""
        try:
            if curr is None or prev is None:
                return "—", _MUTED
            d = float(curr) - float(prev)
            if abs(d) < 1e-9:
                return "  ━  0", _MUTED
            sym = "▲" if d > 0 else "▼"
            col = "#3fb950" if d > 0 else "#f85149"
            mag = abs(d)
            val_str = f"{mag:,.4f}" if mag >= 0.001 else f"{mag:.2e}"
            return f"  {sym}  {val_str}", col
        except (TypeError, ValueError):
            return "—", _MUTED

    # ─────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────

    def refresh(self, option_signal: Optional[Dict]):
        """Update the entire panel from a fresh option_signal dict."""
        try:
            if not option_signal or not option_signal.get("available"):
                self._reset()
                return

            # ── badge ──────────────────────────────────────────────
            sv = option_signal.get("signal_value", "WAIT")
            self._apply_badge(sv)

            # ── confidence bar ─────────────────────────────────────
            raw_conf = option_signal.get("confidence", 0)
            try:
                if isinstance(raw_conf, dict):
                    # If confidence is a dict, calculate average
                    if raw_conf:
                        conf_values = [v for v in raw_conf.values() if isinstance(v, (int, float))]
                        avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0
                        pct = int(avg_conf * 100)
                    else:
                        pct = 0
                else:
                    f = float(raw_conf)
                    pct = int(f * 100) if f <= 1.0 else int(f)
                pct = max(0, min(100, pct))
            except (TypeError, ValueError):
                pct = 0
            self.conf_bar.setValue(pct)
            bar_col = "#3fb950" if pct >= 70 else ("#d29922" if pct >= 40 else "#f85149")
            self._set_conf_bar_color(bar_col)

            # ── conflict ───────────────────────────────────────────
            self._apply_conflict(bool(option_signal.get("conflict", False)))

            # ── fired pills ────────────────────────────────────────
            fired = option_signal.get("fired", {})
            for sig, lbl in self._pill_labels.items():
                self._apply_pill(lbl, sig, bool(fired.get(sig, False)))

            # ── indicator values ───────────────────────────────────
            ind_vals: Dict = option_signal.get("indicator_values", {})
            self.ind_table.setRowCount(0)
            self.ind_table.setRowCount(len(ind_vals))

            for row_i, (k, v) in enumerate(ind_vals.items()):
                if isinstance(v, dict):
                    curr = v.get("last") or v.get("current") or v.get("value")
                    prev = v.get("prev") or v.get("previous")
                else:
                    curr, prev = v, None

                # name
                n_item = QTableWidgetItem(self._fmt_key(k))
                n_item.setForeground(QColor(_TEXT))
                self.ind_table.setItem(row_i, 0, n_item)

                # current
                c_item = QTableWidgetItem(self._fmt_num(curr))
                c_item.setForeground(QColor("#58a6ff"))
                c_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.ind_table.setItem(row_i, 1, c_item)

                # previous
                p_item = QTableWidgetItem(self._fmt_num(prev))
                p_item.setForeground(QColor(_MUTED))
                p_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.ind_table.setItem(row_i, 2, p_item)

                # delta
                dtxt, dcol = self._delta(curr, prev)
                d_item = QTableWidgetItem(dtxt)
                d_item.setForeground(QColor(dcol))
                d_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.ind_table.setItem(row_i, 3, d_item)

            self.ind_table.resizeRowsToContents()

            # ── rule results ───────────────────────────────────────
            rule_results: Dict = option_signal.get("rule_results", {})
            rows: List[Dict] = []
            for group, rules in rule_results.items():
                if not rules:
                    rows.append({"group": group, "rule": "No rules configured",
                                 "detail": "—", "result": None, "blocker": False})
                else:
                    for r in rules:
                        rows.append({
                            "group": group,
                            "rule": r.get("rule", "?"),
                            "detail": str(r.get("detail", "—")),
                            "result": r.get("result", False),
                            "blocker": r.get("blocker", False),
                        })

            self.rule_table.setRowCount(0)
            self.rule_table.setRowCount(len(rows))

            for row_i, r in enumerate(rows):
                g_item = QTableWidgetItem(r["group"])
                g_item.setForeground(QColor(_MUTED))
                self.rule_table.setItem(row_i, 0, g_item)

                rule_item = QTableWidgetItem(r["rule"])
                rule_item.setForeground(QColor("#f85149" if r["blocker"] else _TEXT))
                self.rule_table.setItem(row_i, 1, rule_item)

                det_item = QTableWidgetItem(r["detail"])
                det_item.setForeground(QColor(_MUTED))
                self.rule_table.setItem(row_i, 2, det_item)

                if r["result"] is None:
                    res_txt, res_col, res_bg = "—", _MUTED, "transparent"
                elif r["result"]:
                    res_txt, res_col, res_bg = "✓  PASS", "#3fb950", "rgba(63,185,80,0.10)"
                else:
                    res_txt, res_col, res_bg = "✗  FAIL", "#f85149", "rgba(248,81,73,0.10)"

                res_item = QTableWidgetItem(res_txt)
                res_item.setForeground(QColor(res_col))
                res_item.setBackground(QColor(res_bg))
                res_item.setTextAlignment(Qt.AlignCenter)
                self.rule_table.setItem(row_i, 3, res_item)

            self.rule_table.resizeRowsToContents()

            # ── timestamp ──────────────────────────────────────────
            self.ts_label.setText(f"Updated  {datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            logger.error(f"[SignalDataTab.refresh] {e}", exc_info=True)

    def _reset(self):
        self._apply_badge("WAIT")
        self.conf_bar.setValue(0)
        self._set_conf_bar_color("#1f6feb")
        self._apply_conflict(False)
        for sig, lbl in self._pill_labels.items():
            self._apply_pill(lbl, sig, False)
        self.ind_table.setRowCount(0)
        self.rule_table.setRowCount(0)
        self.ts_label.setText("—")


# =============================================================================
# SIMPLE CHART WIDGET (Spot + Signal only)
# =============================================================================

class SimpleChartWidget(QWidget):
    """
    Simplified multi-chart widget with only:
    - Spot chart (with volume as bar chart)
    - Detailed Signal data tab
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab widget with only Spot and Signal tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #30363d;
                background: #0d1117;
            }
            QTabBar::tab {
                background: #161b22;
                color: #8b949e;
                padding: 8px 22px;
                border: 1px solid #30363d;
                border-bottom: none;
                font-size: 10pt;
                font-weight: bold;
                min-width: 150px;
                height: 30px;
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

        # Create spot chart only (with volume as bar chart)
        self.spot_chart = SpotChartWidget()
        self.spot_chart.set_symbol("Spot Index")

        # Detailed signal data tab (fully preserved)
        self.signal_tab = SignalDataTab()

        # Add tabs - only Spot and Signal
        self.tabs.addTab(self.spot_chart, "📈 Spot")
        self.tabs.addTab(self.signal_tab, "🔬 Signal Data")

        layout.addWidget(self.tabs, 1)

        logger.info("SimpleChartWidget initialized (Spot + Detailed Signal)")

    # Public API

    def set_config(self, config, signal_engine=None):
        """Set configuration for spot chart"""
        self.spot_chart.set_config(config, signal_engine)

    def update_charts(self, spot_data: dict):
        """Update spot chart and signal tab with new data"""
        try:

            if spot_data:
                self.spot_chart.update_chart(spot_data)

        except Exception as e:
            logger.error(f"[SimpleChartWidget.update_charts] Failed: {e}")

    def update_chart(self, trend_data: dict):
        """Backward compatibility"""
        self.update_charts(spot_data=trend_data)

    def clear_cache(self):
        """Clear cache for spot chart"""
        self.spot_chart.clear_cache()

    def cleanup(self):
        """Clean up resources"""
        self.spot_chart.cleanup()


# Backward compatibility aliases
ChartWidget = SpotChartWidget
MultiChartWidget = SimpleChartWidget
SignalDataTab = SignalDataTab