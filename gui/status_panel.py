# PYQT: Live status cards widget
from PyQt5.QtWidgets import QWidget, QGridLayout, QLabel, QFrame, QVBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class StatusCard(QFrame):
    """Single status field with a label and a live value."""

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        title = QLabel(f"{icon}  {label}")
        title.setFont(QFont("Segoe UI", 8))
        title.setStyleSheet("color: #8b949e; border: none; background: transparent;")

        self.value_label = QLabel("—")
        self.value_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.value_label.setStyleSheet("color: #e6edf3; border: none; background: transparent;")

        layout.addWidget(title)
        layout.addWidget(self.value_label)

    def set_value(self, text: str, color: str = "#e6edf3"):
        # PYQT: Must be called on main thread only
        self.value_label.setText(text)
        self.value_label.setStyleSheet(
            f"color: {color}; border: none; background: transparent;"
        )


class StatusPanel(QWidget):
    """
    # PYQT: Grid of StatusCards — one per live trading field.
    Updated every 1 second via QTimer on the main thread.
    """
    FIELDS = [
        ("position", "🟢", "Position"),
        ("prev_position", "🔄", "Previous Position"),
        ("symbol", "💹", "Symbol"),
        ("buy_price", "🛒", "Buy Price"),
        ("current_price", "💰", "Current Price"),
        ("target_price", "🎯", "Target Price"),
        ("stoploss_price", "🛑", "Stoploss Price"),
        ("pnl", "💵", "PnL"),
        ("balance", "🏦", "Balance"),
        ("derivative", "📈", "Derivative"),
        ("st_short", "✨", "Supertrend"),
        ("st_long", "✨", "Long Supertrend"),
        ("macd", "📊", "MACD"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setSpacing(6)
        self.cards = {}

        for i, (key, icon, label) in enumerate(self.FIELDS):
            card = StatusCard(icon, label)
            row, col = divmod(i, 2)
            grid.addWidget(card, row, col)
            self.cards[key] = card

    def refresh(self, state, config):
        """
        # PYQT: Called on main thread by QTimer every 1 second.
        Reads TradeState and updates all status cards.
        """
        if state is None:
            return

        trend = getattr(state, "derivative_trend", {}) or {}
        short_dir = (trend.get("super_trend_short", {}).get("direction") or [])
        long_dir = (trend.get("super_trend_long", {}).get("direction") or [])
        macd_hist = (trend.get("macd", {}).get("histogram") or [])

        def last(lst):
            return lst[-1] if isinstance(lst, (list, tuple)) and lst else None

        def fmt(v, spec=None):
            if v is None:
                return "—"
            try:
                return f"{v:{spec}}" if spec else str(v)
            except Exception:
                return str(v)

        pnl = getattr(state, "percentage_change", None)
        pnl_color = (
            "#3fb950" if pnl and pnl > 0 else
            "#f85149" if pnl and pnl < 0 else
            "#8b949e"
        )
        pos_color = "#3fb950" if getattr(state, "current_position", None) else "#8b949e"

        updates = {
            "position": (getattr(state, "current_position", None) or "None", pos_color),
            "prev_position": (getattr(state, "previous_position", None) or "None", "#e6edf3"),
            "symbol": (getattr(state, "current_trading_symbol", None) or "No Position", "#e6edf3"),
            "buy_price": (fmt(getattr(state, "current_buy_price", None), ".2f"), "#e6edf3"),
            "current_price": (fmt(getattr(state, "current_price", None), ".2f"), "#e6edf3"),
            "target_price": (fmt(getattr(state, "tp_point", None), ".2f"), "#3fb950"),
            "stoploss_price": (fmt(getattr(state, "stop_loss", None), ".2f"), "#f85149"),
            "pnl": (f"{pnl:.2f}%" if pnl is not None else "—", pnl_color),
            "balance": (fmt(getattr(state, "account_balance", None), ".2f"), "#e6edf3"),
            "derivative": (fmt(getattr(state, "derivative_current_price", None), ".2f"), "#58a6ff"),
            "st_short": (fmt(last(short_dir)), "#e6edf3"),
            "st_long": (fmt(last(long_dir)) if getattr(config, "use_long_st", False) else "—", "#e6edf3"),
            "macd": (fmt(last(macd_hist), ".4f") if last(macd_hist) is not None else "—", "#e6edf3"),
        }

        for key, (text, color) in updates.items():
            self.cards[key].set_value(str(text), color)