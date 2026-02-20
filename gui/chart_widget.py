# chart_widget.py - Fixed Plotly property errors
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QTimer, pyqtSignal, QObject
import numpy as np


class ChartUpdater(QObject):
    """# PYQT: Worker object for chart updates"""
    update_requested = pyqtSignal(object)


class ChartWidget(QWebEngineView):
    """
    # PYQT: Plotly chart inside QWebEngineView - optimized to prevent flickering
    """
    DARK_BG = "#0d1117"
    CARD_BG = "#161b22"
    TEXT_COLOR = "#e6edf3"
    GRID_COLOR = "#30363d"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {self.DARK_BG}; border: none;")

        # State tracking
        self._last_data_fingerprint = ""
        self._pending_data = None
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._perform_update)

        # Show placeholder initially
        self._show_placeholder()

    def _show_placeholder(self):
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
            </style>
        </head>
        <body>
            <div class="message">📊 Waiting for market data...</div>
        </body>
        </html>
        """
        self.setHtml(html)

    def _fingerprint(self, trend_data):
        """Create lightweight fingerprint to detect meaningful changes"""
        try:
            if not trend_data:
                return ""
            close = trend_data.get("close") or []
            if not close:
                return ""
            # Check length and last few values
            last_values = close[-5:] if len(close) >= 5 else close
            return f"{len(close)}:{last_values}"
        except:
            return ""

    def update_chart(self, trend_data: dict):
        """
        # PYQT: Thread-safe chart update - throttled to prevent flicker
        Can be called from any thread
        """
        fp = self._fingerprint(trend_data)
        if fp == self._last_data_fingerprint or fp == "":
            return

        # Store new fingerprint
        self._last_data_fingerprint = fp

        # Schedule update on main thread with debounce
        self._pending_data = trend_data
        self._update_timer.start(300)  # 300ms debounce

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
                self.setHtml(html)
        except Exception as e:
            print(f"Chart update error: {e}")

    def _generate_chart_html(self, trend_data):
        """Generate Plotly HTML - fixed property errors"""
        if not trend_data:
            return None

        def clean(raw):
            if not raw:
                return []
            try:
                return [
                    float(x) if x is not None and str(x).lower() not in ("nan", "none")
                    else None
                    for x in raw
                ]
            except Exception:
                return []

        close = clean(trend_data.get("close"))
        if len(close) < 5:
            return None

        st_short = clean((trend_data.get("super_trend_short") or {}).get("trend"))
        st_long = clean((trend_data.get("super_trend_long") or {}).get("trend"))
        bb_upper = clean((trend_data.get("bb") or {}).get("upper"))
        bb_mid = clean((trend_data.get("bb") or {}).get("middle"))
        bb_lower = clean((trend_data.get("bb") or {}).get("lower"))
        macd_line = clean((trend_data.get("macd") or {}).get("macd"))
        macd_sig = clean((trend_data.get("macd") or {}).get("signal"))
        macd_hist = clean((trend_data.get("macd") or {}).get("histogram"))
        rsi = clean(trend_data.get("rsi_series"))

        n = len(close)
        x = list(range(n))

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
            line=dict(color="#58a6ff", width=2),
            hovertemplate="Price: %{y:.2f}<extra></extra>"
        ), row=1, col=1)

        if st_short and len(st_short) == n:
            fig.add_trace(go.Scatter(
                x=x, y=st_short, name="Short ST",
                line=dict(color="#d29922", width=1.5, dash="dash"),
                hovertemplate="Short ST: %{y:.2f}<extra></extra>"
            ), row=1, col=1)

        if st_long and len(st_long) == n:
            fig.add_trace(go.Scatter(
                x=x, y=st_long, name="Long ST",
                line=dict(color="#bc8cff", width=1.5, dash="dash"),
                hovertemplate="Long ST: %{y:.2f}<extra></extra>"
            ), row=1, col=1)

        # Bollinger Bands
        if bb_upper and len(bb_upper) == n and bb_lower and len(bb_lower) == n:
            fig.add_trace(go.Scatter(
                x=x, y=bb_upper, name="BB Upper",
                line=dict(color="#3fb950", width=1, dash="dot"),
                showlegend=True,
                hovertemplate="BB Upper: %{y:.2f}<extra></extra>"
            ), row=1, col=1)

            fig.add_trace(go.Scatter(
                x=x, y=bb_lower, name="BB Lower",
                line=dict(color="#f85149", width=1, dash="dot"),
                fill="tonexty",
                fillcolor="rgba(63,185,80,0.05)",
                showlegend=True,
                hovertemplate="BB Lower: %{y:.2f}<extra></extra>"
            ), row=1, col=1)

            if bb_mid and len(bb_mid) == n:
                fig.add_trace(go.Scatter(
                    x=x, y=bb_mid, name="BB Mid",
                    line=dict(color="#8b949e", width=1),
                    showlegend=True,
                    hovertemplate="BB Mid: %{y:.2f}<extra></extra>"
                ), row=1, col=1)

        # ── Row 2: MACD ───────────────────────────────────────────────
        if macd_line and len(macd_line) == n:
            # Histogram
            hist_colors = [
                "#3fb950" if (v is not None and v >= 0) else "#f85149"
                for v in macd_hist
            ]
            fig.add_trace(go.Bar(
                x=x, y=macd_hist, name="Histogram",
                marker_color=hist_colors,
                opacity=0.6,
                hovertemplate="Histogram: %{y:.4f}<extra></extra>"
            ), row=2, col=1)

            # MACD Line
            fig.add_trace(go.Scatter(
                x=x, y=macd_line, name="MACD",
                line=dict(color="#58a6ff", width=1.5),
                hovertemplate="MACD: %{y:.4f}<extra></extra>"
            ), row=2, col=1)

            # Signal Line
            if macd_sig and len(macd_sig) == n:
                fig.add_trace(go.Scatter(
                    x=x, y=macd_sig, name="Signal",
                    line=dict(color="#f85149", width=1.5),
                    hovertemplate="Signal: %{y:.4f}<extra></extra>"
                ), row=2, col=1)

        # ── Row 3: RSI ────────────────────────────────────────────────
        if rsi and len(rsi) == n:
            fig.add_trace(go.Scatter(
                x=x, y=rsi, name="RSI",
                line=dict(color="#bc8cff", width=1.5),
                hovertemplate="RSI: %{y:.2f}<extra></extra>"
            ), row=3, col=1)

            # Add horizontal lines - FIXED: removed opacity property
            fig.add_hline(y=70, line=dict(color="#f85149", dash="dash", width=1),
                          row=3, col=1)
            fig.add_hline(y=60, line=dict(color="#f85149", dash="dot", width=0.8),
                          row=3, col=1)
            fig.add_hline(y=40, line=dict(color="#3fb950", dash="dot", width=0.8),
                          row=3, col=1)
            fig.add_hline(y=30, line=dict(color="#3fb950", dash="dash", width=1),
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
                font=dict(size=10)
            ),
            margin=dict(l=50, r=20, t=50, b=20),
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
                "showTips": False
            }
        )

        # Add custom CSS to prevent flickering - FIXED: removed transition properties
        css = """
        <style>
            .plotly-graph-div { 
                contain: strict;
            }
            .main-svg { 
                contain: strict;
            }
        </style>
        """

        # Insert CSS before closing head
        html = html.replace("</head>", css + "</head>")

        return html