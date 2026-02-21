from PyQt5.QtWidgets import QWidget, QGridLayout, QLabel, QFrame, QVBoxLayout
from PyQt5.QtGui import QFont
import threading
from typing import Optional, Any
import traceback


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

        # Store last value for change detection
        self._last_value = None
        self._last_color = "#e6edf3"

        layout.addWidget(title)
        layout.addWidget(self.value_label)

    def set_value(self, text: str, color: str = "#e6edf3"):
        """# PYQT: Must be called on main thread only"""
        # Only update if value or color changed
        if text == self._last_value and color == self._last_color:
            return

        self.value_label.setText(text)
        self.value_label.setStyleSheet(
            f"color: {color}; border: none; background: transparent;"
        )
        self._last_value = text
        self._last_color = color


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
        ("derivative", "📈", "Derivative")
    ]

    # Default colors
    COLORS = {
        "positive": "#3fb950",
        "negative": "#f85149",
        "neutral": "#8b949e",
        "normal": "#e6edf3",
        "accent": "#58a6ff"
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._last_state = {}  # Cache last state for change detection
        self._refresh_enabled = True

        grid = QGridLayout(self)
        grid.setSpacing(6)
        self.cards = {}

        for i, (key, icon, label) in enumerate(self.FIELDS):
            card = StatusCard(icon, label)
            row, col = divmod(i, 2)
            grid.addWidget(card, row, col)
            self.cards[key] = card

    def _safe_get_attr(self, obj: Any, attr: str, default: Any = None) -> Any:
        """Safely get attribute from object with error handling"""
        try:
            if hasattr(obj, attr):
                return getattr(obj, attr)
            return default
        except Exception:
            return default

    def _format_number(self, value: Any, format_spec: str = ".2f") -> str:
        """Safely format a number"""
        if value is None:
            return "—"
        try:
            if isinstance(value, (int, float)):
                return f"{value:{format_spec}}"
            # Try to convert to float
            float_val = float(value)
            return f"{float_val:{format_spec}}"
        except (ValueError, TypeError):
            return str(value)

    def _get_pnl_color(self, pnl: Optional[float]) -> str:
        """Get color for PnL value"""
        if pnl is None:
            return self.COLORS["neutral"]
        try:
            pnl_float = float(pnl)
            if pnl_float > 0:
                return self.COLORS["positive"]
            elif pnl_float < 0:
                return self.COLORS["negative"]
            return self.COLORS["neutral"]
        except (ValueError, TypeError):
            return self.COLORS["neutral"]

    def _get_position_color(self, position: Optional[str]) -> str:
        """Get color for position indicator"""
        if position and str(position).upper() in ["LONG", "SHORT"]:
            return self.COLORS["positive"]
        return self.COLORS["neutral"]

    def refresh(self, state, config):
        """
        # PYQT: Called on main thread by QTimer every 1 second.
        Reads TradeState and updates all status cards with change detection.
        """
        if state is None or not self._refresh_enabled:
            return

        try:
            # Get current values with thread safety
            with self._lock:
                # Extract all needed values
                current_position = self._safe_get_attr(state, "current_position")
                previous_position = self._safe_get_attr(state, "previous_position")
                symbol = self._safe_get_attr(state, "current_trading_symbol")
                buy_price = self._safe_get_attr(state, "current_buy_price")
                current_price = self._safe_get_attr(state, "current_price")
                target_price = self._safe_get_attr(state, "tp_point")
                stoploss_price = self._safe_get_attr(state, "stop_loss")
                pnl = self._safe_get_attr(state, "percentage_change")
                balance = self._safe_get_attr(state, "account_balance")
                derivative = self._safe_get_attr(state, "derivative_current_price")

            # Prepare updates dictionary
            updates = {}

            # Position
            pos_text = str(current_position) if current_position else "None"
            pos_color = self._get_position_color(current_position)
            updates["position"] = (pos_text, pos_color)

            # Previous Position
            prev_pos_text = str(previous_position) if previous_position else "None"
            updates["prev_position"] = (prev_pos_text, self.COLORS["normal"])

            # Symbol
            symbol_text = str(symbol) if symbol else "No Position"
            updates["symbol"] = (symbol_text, self.COLORS["normal"])

            # Buy Price
            updates["buy_price"] = (self._format_number(buy_price), self.COLORS["normal"])

            # Current Price
            updates["current_price"] = (self._format_number(current_price), self.COLORS["normal"])

            # Target Price
            updates["target_price"] = (self._format_number(target_price), self.COLORS["positive"])

            # Stoploss Price
            updates["stoploss_price"] = (self._format_number(stoploss_price), self.COLORS["negative"])

            # PnL
            if pnl is not None:
                try:
                    pnl_float = float(pnl)
                    pnl_text = f"{pnl_float:.2f}%"
                except (ValueError, TypeError):
                    pnl_text = str(pnl)
            else:
                pnl_text = "—"
            pnl_color = self._get_pnl_color(pnl)
            updates["pnl"] = (pnl_text, pnl_color)

            # Balance
            updates["balance"] = (self._format_number(balance), self.COLORS["normal"])

            # Derivative
            updates["derivative"] = (self._format_number(derivative), self.COLORS["accent"])

            # Apply updates with change detection
            for key, (text, color) in updates.items():
                if key in self.cards:
                    # Check if value changed
                    cache_key = f"{key}_value"
                    cache_color_key = f"{key}_color"

                    with self._lock:
                        last_text = self._last_state.get(cache_key)
                        last_color = self._last_state.get(cache_color_key)

                        if text != last_text or color != last_color:
                            self.cards[key].set_value(text, color)
                            self._last_state[cache_key] = text
                            self._last_state[cache_color_key] = color

        except Exception as e:
            print(f"Error refreshing status panel: {e}")
            traceback.print_exc()

    def pause_refresh(self):
        """Pause automatic refresh"""
        self._refresh_enabled = False

    def resume_refresh(self):
        """Resume automatic refresh"""
        self._refresh_enabled = True

    def clear_cache(self):
        """Clear the state cache"""
        with self._lock:
            self._last_state.clear()

    def closeEvent(self, event):
        """Clean up when panel is closed"""
        self.pause_refresh()
        self.clear_cache()
        super().closeEvent(event)