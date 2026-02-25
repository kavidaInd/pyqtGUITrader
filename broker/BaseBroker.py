"""
BaseBroker.py
=============
Abstract base class defining the unified broker interface.
All broker implementations must inherit from this class.

Supported brokers:
- Fyers (fyers_apiv3)
- Zerodha (kiteconnect)
- Dhan (dhanhq)
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Any, Dict, List

logger = logging.getLogger(__name__)


class TokenExpiredError(RuntimeError):
    """Exception raised when broker token has expired or is invalid."""

    def __init__(self, message: str = "Token expired or invalid", code: Optional[int] = None):
        if code is not None:
            message = f"{message} (code: {code})"
        super().__init__(message)
        self.code = code


class BaseBroker(ABC):
    """
    Abstract base class for all broker integrations.

    Every broker must implement these methods so the rest of the
    application can work with any broker without modification.
    """

    # ── Order side constants (universal) ──────────────────────────────────────
    SIDE_BUY = 1
    SIDE_SELL = -1

    # ── Order type constants (universal) ──────────────────────────────────────
    LIMIT_ORDER_TYPE = 1
    MARKET_ORDER_TYPE = 2
    STOPLOSS_MARKET_ORDER_TYPE = 3

    PRODUCT_TYPE_MARGIN = 'MARGIN'
    OK = 'ok'

    # ── Retry / rate-limit defaults ────────────────────────────────────────────
    MAX_REQUESTS_PER_SECOND = 10
    MAX_RETRIES = 3

    # ── Abstract methods every broker must implement ───────────────────────────

    @abstractmethod
    def get_profile(self) -> Optional[Dict]:
        """Return user profile dict or None."""

    @abstractmethod
    def get_balance(self, capital_reserve: float = 0.0) -> float:
        """Return available balance after optional reserve deduction."""

    @abstractmethod
    def get_history(self, symbol: str, interval: str = "2",
                    length: int = 400) -> Optional[Any]:
        """Return OHLCV DataFrame or None."""

    @abstractmethod
    def get_history_for_timeframe(self, symbol: str, interval: str,
                                  days: int = 30) -> Optional[Any]:
        """Return OHLCV DataFrame for specific timeframe or None."""

    @abstractmethod
    def get_option_current_price(self, option_name: str) -> Optional[float]:
        """Return last traded price for an option or None."""

    @abstractmethod
    def get_option_quote(self, option_name: str) -> Optional[Dict[str, float]]:
        """Return detailed quote dict {ltp, bid, ask, ...} or None."""

    @abstractmethod
    def get_option_chain_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        """Return quotes for multiple options in one call."""

    @abstractmethod
    def place_order(self, **kwargs) -> Optional[str]:
        """Place an order and return order_id or None."""

    @abstractmethod
    def modify_order(self, **kwargs) -> bool:
        """Modify an existing order. Returns True on success."""

    @abstractmethod
    def cancel_order(self, **kwargs) -> bool:
        """Cancel an order. Returns True on success."""

    @abstractmethod
    def exit_position(self, **kwargs) -> bool:
        """Exit a position. Returns True on success."""

    @abstractmethod
    def add_stoploss(self, **kwargs) -> bool:
        """Add a stoploss order. Returns True on success."""

    @abstractmethod
    def remove_stoploss(self, **kwargs) -> bool:
        """Remove/cancel a stoploss order. Returns True on success."""

    @abstractmethod
    def sell_at_current(self, **kwargs) -> bool:
        """Sell at current market price. Returns True on success."""

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """Return list of open position dicts."""

    @abstractmethod
    def get_orderbook(self) -> List[Dict[str, Any]]:
        """Return list of orders in the orderbook."""

    @abstractmethod
    def get_current_order_status(self, order_id: str) -> Optional[Any]:
        """Return current order status or None."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the broker session is active."""

    @abstractmethod
    def cleanup(self) -> None:
        """Release resources on shutdown."""

    # ── Shared utility ─────────────────────────────────────────────────────────

    @staticmethod
    def calculate_pnl(current_price, buy_price=None, options=None) -> Optional[int]:
        """Calculate P&L (broker-agnostic)."""
        try:
            if buy_price is None or options is None or current_price is None:
                return None
            return int((current_price - buy_price) * options)
        except Exception as e:
            logger.error(f"[BaseBroker.calculate_pnl] {e}", exc_info=True)
            return None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"