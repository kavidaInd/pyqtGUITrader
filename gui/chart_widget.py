# chart_widget.py - Enhanced with better error handling and performance
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, QSize
import numpy as np
import logging
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class ChartUpdater(QObject):
    """# PYQT: Worker object for chart updates"""
    update_requested = pyqtSignal(object)
    update_completed = pyqtSignal(bool, str)  # success, message


class ChartWidget(QWebEngineView):
    """
    # PYQT: Plotly chart inside QWebEngineView - optimized to prevent flickering
    Enhanced with better error handling and performance optimizations
    """

    DARK_BG = "#0d1117"
    CARD_BG = "#161b22"
    TEXT_COLOR = "#e6edf3"
    GRID_COLOR = "#30363d"

    # Color scheme for indicators
    COLORS = {
        "price": "#58a6ff",
        "short_st": "#d29922",
        "long_st": "#bc8cff",
        "bb_upper": "#3fb950",
        "bb_lower": "#f85149",
        "bb_mid": "#8b949e",
        "macd": "#58a6ff",
        "macd_signal": "#f85149",
        "rsi": "#bc8cff",
        "positive": "#3fb950",
        "negative": "#f85149"
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {self.DARK_BG}; border: none;")

        # Set minimum size
        self.setMinimumSize(QSize(400, 300))

        # State tracking
        self._last_data_fingerprint = ""
        self._pending_data = None
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._perform_update)

        # Cache for generated HTML to avoid regeneration
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
                    border-top: 3px solid {self.COLORS["price"]};
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
                    color: {self.COLORS["negative"]};
                    font-size: 14px;
                    text-align: center;
                    padding: 20px;
                    border: 1px solid {self.COLORS["negative"]};
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

    def _fingerprint(self, trend_data: Optional[Dict]) -> str:
        """
        Create lightweight fingerprint to detect meaningful changes.
        More robust fingerprinting that handles various data shapes.
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

            # Get last few values and their shape
            n_points = len(close)
            if n_points == 0:
                return ""

            # Get last 5 values (or all if less)
            last_values = close[-5:] if n_points >= 5 else close

            # Include key indicator presence
            indicators = []
            for key in ["super_trend_short", "super_trend_long", "bb", "macd", "rsi_series"]:
                if trend_data.get(key):
                    indicators.append(key)

            # Create fingerprint
            fp_parts = [
                str(n_points),
                str([round(v, 4) if isinstance(v, (int, float)) else str(v) for v in last_values]),
                str(sorted(indicators))
            ]

            return ":".join(fp_parts)

        except Exception as e:
            logger.debug(f"Fingerprint generation failed: {e}")
            return ""

    def _clean_data(self, raw: Any) -> List[float]:
        """
        Clean and validate data series.
        More robust version with better error handling.
        """
        if raw is None:
            return []

        try:
            # Convert numpy arrays to list
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

    def _generate_chart_html(self, trend_data: Dict) -> Optional[str]:
        """
        Generate Plotly HTML with improved error handling and data validation.
        """
        if not trend_data or not isinstance(trend_data, dict):
            return None

        try:
            # Clean and validate price data first
            close = self._clean_data(trend_data.get("close"))
            if len(close) < 5:
                logger.debug(f"Insufficient price data: {len(close)} points")
                return None

            n = len(close)
            x = list(range(n))

            # Clean other indicators
            st_short_data = trend_data.get("super_trend_short") or {}
            st_short = self._clean_data(st_short_data.get("trend"))

            st_long_data = trend_data.get("super_trend_long") or {}
            st_long = self._clean_data(st_long_data.get("trend"))

            bb_data = trend_data.get("bb") or {}
            bb_upper = self._clean_data(bb_data.get("upper"))
            bb_mid = self._clean_data(bb_data.get("middle"))
            bb_lower = self._clean_data(bb_data.get("lower"))

            macd_data = trend_data.get("macd") or {}
            macd_line = self._clean_data(macd_data.get("macd"))
            macd_sig = self._clean_data(macd_data.get("signal"))
            macd_hist = self._clean_data(macd_data.get("histogram"))

            rsi = self._clean_data(trend_data.get("rsi_series"))

            # Create figure with 3 subplots
            fig = make_subplots(
                rows=3, cols=1,
                shared_xaxes=True,
                row_heights=[0.55, 0.25, 0.20],
                vertical_spacing=0.05,
                subplot_titles=("Price & SuperTrend", "MACD", "RSI")
            )

            # ── Row 1: Price ──────────────────────────────────────────────
            fig.add_trace(go.Scatter(
                x=x, y=close, name="Price",
                line=dict(color=self.COLORS["price"], width=2),
                hovertemplate="Price: %{y:.2f}<extra></extra>"
            ), row=1, col=1)

            # Short SuperTrend
            if st_short and len(st_short) == n:
                fig.add_trace(go.Scatter(
                    x=x, y=st_short, name="Short ST",
                    line=dict(color=self.COLORS["short_st"], width=1.5, dash="dash"),
                    hovertemplate="Short ST: %{y:.2f}<extra></extra>"
                ), row=1, col=1)

            # Long SuperTrend
            if st_long and len(st_long) == n:
                fig.add_trace(go.Scatter(
                    x=x, y=st_long, name="Long ST",
                    line=dict(color=self.COLORS["long_st"], width=1.5, dash="dash"),
                    hovertemplate="Long ST: %{y:.2f}<extra></extra>"
                ), row=1, col=1)

            # Bollinger Bands
            if bb_upper and len(bb_upper) == n and bb_lower and len(bb_lower) == n:
                fig.add_trace(go.Scatter(
                    x=x, y=bb_upper, name="BB Upper",
                    line=dict(color=self.COLORS["bb_upper"], width=1, dash="dot"),
                    showlegend=True,
                    hovertemplate="BB Upper: %{y:.2f}<extra></extra>"
                ), row=1, col=1)

                fig.add_trace(go.Scatter(
                    x=x, y=bb_lower, name="BB Lower",
                    line=dict(color=self.COLORS["bb_lower"], width=1, dash="dot"),
                    fill="tonexty",
                    fillcolor="rgba(63,185,80,0.05)",
                    showlegend=True,
                    hovertemplate="BB Lower: %{y:.2f}<extra></extra>"
                ), row=1, col=1)

                if bb_mid and len(bb_mid) == n:
                    fig.add_trace(go.Scatter(
                        x=x, y=bb_mid, name="BB Mid",
                        line=dict(color=self.COLORS["bb_mid"], width=1),
                        showlegend=True,
                        hovertemplate="BB Mid: %{y:.2f}<extra></extra>"
                    ), row=1, col=1)

            # ── Row 2: MACD ───────────────────────────────────────────────
            if macd_line and len(macd_line) == n:
                # Histogram with proper null handling
                hist_colors = []
                valid_hist = []
                hist_x = []

                for i, v in enumerate(macd_hist):
                    if v is not None and i < len(x):
                        hist_colors.append(self.COLORS["positive"] if v >= 0 else self.COLORS["negative"])
                        valid_hist.append(v)
                        hist_x.append(x[i])

                if valid_hist:
                    fig.add_trace(go.Bar(
                        x=hist_x, y=valid_hist, name="Histogram",
                        marker_color=hist_colors,
                        opacity=0.6,
                        hovertemplate="Histogram: %{y:.4f}<extra></extra>"
                    ), row=2, col=1)

                # MACD Line
                fig.add_trace(go.Scatter(
                    x=x, y=macd_line, name="MACD",
                    line=dict(color=self.COLORS["macd"], width=1.5),
                    hovertemplate="MACD: %{y:.4f}<extra></extra>"
                ), row=2, col=1)

                # Signal Line
                if macd_sig and len(macd_sig) == n:
                    fig.add_trace(go.Scatter(
                        x=x, y=macd_sig, name="Signal",
                        line=dict(color=self.COLORS["macd_signal"], width=1.5),
                        hovertemplate="Signal: %{y:.4f}<extra></extra>"
                    ), row=2, col=1)

            # ── Row 3: RSI ────────────────────────────────────────────────
            if rsi and len(rsi) == n:
                fig.add_trace(go.Scatter(
                    x=x, y=rsi, name="RSI",
                    line=dict(color=self.COLORS["rsi"], width=1.5),
                    hovertemplate="RSI: %{y:.2f}<extra></extra>"
                ), row=3, col=1)

                # Add RSI reference lines
                fig.add_hline(y=70, line=dict(color=self.COLORS["negative"], dash="dash", width=1),
                              row=3, col=1)
                fig.add_hline(y=60, line=dict(color=self.COLORS["negative"], dash="dot", width=0.8),
                              row=3, col=1)
                fig.add_hline(y=40, line=dict(color=self.COLORS["positive"], dash="dot", width=0.8),
                              row=3, col=1)
                fig.add_hline(y=30, line=dict(color=self.COLORS["positive"], dash="dash", width=1),
                              row=3, col=1)

            # ── Global styling ────────────────────────────────────────────
            fig.update_layout(
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
                margin=dict(l=50, r=20, t=60, b=20),
                hovermode="x unified",
                hoverlabel=dict(
                    bgcolor=self.CARD_BG,
                    font_size=10,
                    font_family="Consolas, monospace"
                )
            )

            # Update axes
            fig.update_xaxes(
                gridcolor=self.GRID_COLOR,
                zeroline=False,
                showgrid=True,
                tickfont=dict(size=9)
            )
            fig.update_yaxes(
                gridcolor=self.GRID_COLOR,
                zeroline=False,
                showgrid=True,
                tickfont=dict(size=9)
            )

            # Set RSI range
            if rsi and len(rsi) == n:
                fig.update_yaxes(range=[0, 100], row=3, col=1)

            # Generate HTML with optimizations
            html = fig.to_html(
                include_plotlyjs="cdn",
                full_html=True,
                config={
                    "displayModeBar": False,
                    "responsive": True,
                    "scrollZoom": False,
                    "doubleClick": False,
                    "showTips": False,
                    "staticPlot": False  # Allow some interactivity
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
            </style>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            """

            # Insert CSS before closing head
            html = html.replace("</head>", css + "</head>")

            return html

        except Exception as e:
            logger.error(f"Chart HTML generation failed: {e}", exc_info=True)
            return None

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