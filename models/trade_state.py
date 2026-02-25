"""
trade_state.py
==============
Thread-safe TradeState for the Algo Trading Dashboard.

THREADING MODEL
---------------
Three concurrent actors touch this object:

  1. WebSocket thread  (Stage 1) — writes price fields on every tick
  2. Thread-pool       (Stage 2) — reads prices, writes position/signal state
  3. GUI / QTimer               — reads everything for display

A single `threading.RLock` (re-entrant so the same thread can nest
acquisitions) guards every field.  Access is through @property / @setter
pairs so all call-sites remain identical to the original dataclass —
zero caller changes required.

DESIGN RULES
------------
- Every __get__ and __set__ of a mutable field acquires _lock.
- Computed properties (should_buy_call, etc.) acquire the lock for the
  whole expression to prevent torn reads mid-expression.
- Heavy objects (DataFrames, dicts, lists) are stored under the lock and
  returned as shallow copies so callers cannot mutate shared state.
- `get_snapshot()` returns a plain-dict copy of all scalar fields — safe
  to hand to the GUI thread without holding any lock.
- `get_position_snapshot()` atomically reads every field needed for an
  entry/exit decision — use this in Stage 2 rather than N individual
  property reads.
- `update_prices()` batch-updates all price fields in one acquisition to
  minimise lock overhead on the hot WebSocket path.
- `reset_trade_attributes()` is fully atomic (single lock acquisition).
"""

import copy
import logging
import logging.handlers
import threading
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union
import traceback

import pandas as pd

from BaseEnums import STOP
from models.Candle import Candle

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

try:
    from dynamic_signal_engine import OptionSignal
    _OPTION_SIGNAL_AVAILABLE = True
except ImportError:
    _OPTION_SIGNAL_AVAILABLE = False
    logger.debug("dynamic_signal_engine not available")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_trend_dict() -> Dict[str, Any]:
    """Factory for the option_trend / derivative_trend defaults."""
    try:
        return {
            'name': None, 'close': None
        }
    except Exception as e:
        logger.error(f"[_default_trend_dict] Failed: {e}", exc_info=True)
        return {}


def _default_signal_result() -> Dict[str, Any]:
    """
    Factory for a neutral / unavailable option_signal_result.
    FEATURE 3: Added confidence and explanation fields.
    """
    try:
        return {
            'signal': 'WAIT',
            'signal_value': 'WAIT',
            'fired': {
                'BUY_CALL': False,
                'BUY_PUT': False,
                'EXIT_CALL': False,
                'EXIT_PUT': False,
                'HOLD': False,
            },
            'rule_results': {},
            'conflict': False,
            'available': False,
            # FEATURE 3: Confidence scores
            'confidence': {},  # Dict mapping group -> confidence float
            'explanation': '',  # Human-readable explanation
            'threshold': 0.6,   # Minimum confidence threshold
            'indicator_values': {},  # Dict mapping indicator -> {last, prev}
        }
    except Exception as e:
        logger.error(f"[_default_signal_result] Failed: {e}", exc_info=True)
        return {}


# ---------------------------------------------------------------------------
# TradeState
# ---------------------------------------------------------------------------

class TradeState:
    """
    Central container for all mutable trading state.

    Drop-in replacement for the original @dataclass version:
    identical attribute names, same default values, same convenience
    properties — with a threading.RLock added so reads and writes from
    the WS thread, thread-pool, and GUI timer cannot interleave.

    Quick-start
    -----------
        state = TradeState()

        # Stage-1 (WS thread) — batch price write, one lock acquisition
        state.update_prices(
            derivative_ltp = ltp,
            call_ask       = ask,
            put_bid        = bid,
            has_position   = bool(state.current_position),
        )

        # Stage-2 (thread pool) — atomic snapshot for decisions
        snap = state.get_position_snapshot()
        if snap["current_price"] <= snap["stop_loss"]: ...

        # GUI timer — full scalar snapshot, no lock held by caller
        display = state.get_snapshot()
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self):
        try:
            # _lock must be set via object.__setattr__ because our own
            # __setattr__ references _lock before the instance is ready.
            object.__setattr__(self, "_lock", threading.RLock())

            # ── Trend dicts ─────────────────────────────────────────────
            self._option_trend: Dict[str, Any] = _default_trend_dict()
            self._derivative_trend: Dict[str, Any] = _default_trend_dict()
            self._call_trend: Dict[str, Any] = _default_trend_dict()
            self._put_trend: Dict[str, Any] = _default_trend_dict()
            self._option_chain = {}

            # ── Auth ────────────────────────────────────────────────────
            self._token: Optional[str] = None

            # ── Candle snapshots ─────────────────────────────────────────
            self._current_index_data: Candle = Candle()

            # ── Instrument identifiers ───────────────────────────────────
            self._call_option: Optional[str] = None
            self._put_option: Optional[str] = None
            self._current_trading_symbol: Optional[str] = None
            self._derivative: str = 'NIFTY50-INDEX'

            # ── Price fields  (HOT PATH — written every WS tick) ─────────
            self._derivative_current_price: float = 0.0
            self._current_price: Optional[float] = None
            self._highest_current_price: Optional[float] = None
            self._put_current_close: Optional[float] = None
            self._call_current_close: Optional[float] = None

            # ── History / DataFrames ─────────────────────────────────────
            self._derivative_history_df: Optional[pd.DataFrame] = None
            self._option_history_df: Optional[pd.DataFrame] = None
            self._last_index_updated: Optional[float] = None
            self._current_put_data: Optional[pd.DataFrame] = None
            self._current_call_data: Optional[pd.DataFrame] = None

            # ── Orders ───────────────────────────────────────────────────
            self._orders: List[Dict[str, Any]] = []
            self._confirmed_orders: List[Dict[str, Any]] = []

            # ── Position state ───────────────────────────────────────────
            self._current_position: Optional[str] = None
            self._previous_position: Optional[str] = None
            self._current_order_id: Dict[str, int] = {}
            self._current_buy_price: Optional[float] = None
            self._positions_hold: int = 0
            self._order_pending: bool = False
            self._take_profit_type: Optional[str] = STOP

            # ── Risk / P&L ───────────────────────────────────────────────
            self._index_stop_loss: Optional[float] = None
            self._stop_loss: Optional[float] = None
            self._tp_point: Optional[float] = None
            self._tp_percentage: float = 15.0
            self._stoploss_percentage: float = -7.0
            self._original_profit_per: float = 15.0
            self._original_stoploss_per: float = -7.0
            self._trailing_first_profit: float = 3.0
            self._max_profit: float = 30.0
            self._profit_step: float = 2.0
            self._loss_step: float = 2.0

            # ── Session config ───────────────────────────────────────────
            self._interval: Optional[str] = "2m"
            self._expiry: int = 0
            self._lot_size: int = 75
            self._account_balance: float = 0.0
            self._max_num_of_option: int = 7500
            self._lower_percentage: float = 0.01
            self._cancel_after: int = 10
            self._capital_reserve: float = 0.0
            self._sideway_zone_trade: bool = False

            # ── Lookback ─────────────────────────────────────────────────
            self._call_lookback: int = 0
            self._put_lookback: int = 0
            self._original_call_lookback: int = 0
            self._original_put_lookback: int = 0

            # ── Trade metadata ───────────────────────────────────────────
            self._current_trade_started_time: Optional[datetime] = None
            self._last_status_check: Optional[datetime] = None
            self._current_trade_confirmed: bool = False
            self._percentage_change: Optional[float] = None
            self._current_pnl: Optional[float] = None
            self._reason_to_exit: Optional[str] = None

            # ── FEATURE 2: Smart order execution fields ───────────────────
            self._last_slippage: Optional[float] = None  # Slippage from last fill
            self._order_attempts: int = 0  # Number of order attempts
            self._last_order_attempt_time: Optional[datetime] = None

            # ── FEATURE 6: Multi-timeframe filter fields ──────────────────
            self._last_mtf_summary: Optional[str] = None  # MTF filter result summary
            self._mtf_allowed: bool = True  # Last MTF filter decision
            self._mtf_results: Dict[str, str] = {}  # {'1': 'BULLISH', '5': 'NEUTRAL', ...}

            # ── Misc market state ────────────────────────────────────────
            self._market_trend: Optional[int] = None
            self._supertrend_reset: Optional[Dict[str, Any]] = None
            self._b_band: Optional[Dict[str, Any]] = None
            self._all_symbols: List[str] = []
            self._option_price_update: Optional[bool] = None
            self._calculated_pcr: Optional[float] = None
            self._current_pcr: float = 0.0
            self._trend: Any = None
            self._current_pcr_vol: Optional[float] = None

            # ── Dynamic signal result ────────────────────────────────────
            self._option_signal_result: Optional[Dict[str, Any]] = None

            # ── Callback (set once at startup, not lock-protected) ────────
            self.cancel_pending_trade: Optional[Callable] = None

            # ── Startup validation ────────────────────────────────────────
            try:
                assert self._lot_size > 0, "lot_size must be positive"
                assert self._max_num_of_option >= self._lot_size, (
                    "max_num_of_option must not be less than lot_size"
                )
            except AssertionError as e:
                logger.error(f"Startup validation failed: {e}", exc_info=True)

            logger.info("TradeState initialized")

        except Exception as e:
            logger.critical(f"[TradeState.__init__] Failed: {e}", exc_info=True)
            # Still set _lock to prevent crashes
            object.__setattr__(self, "_lock", threading.RLock())

    # ------------------------------------------------------------------
    # Private helpers — avoid repeating acquire/release boilerplate
    # ------------------------------------------------------------------

    def _get(self, attr: str) -> Any:
        """Thread-safe get with error handling"""
        try:
            with self._lock:
                return object.__getattribute__(self, attr)
        except AttributeError as e:
            logger.error(f"[_get] Attribute {attr} not found: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"[_get] Failed for {attr}: {e}", exc_info=True)
            return None

    def _set(self, attr: str, value: Any) -> None:
        """Thread-safe set with error handling"""
        try:
            with self._lock:
                object.__setattr__(self, attr, value)
        except AttributeError as e:
            logger.error(f"[_set] Attribute {attr} not found: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[_set] Failed for {attr}: {e}", exc_info=True)

    # ==================================================================
    # PROPERTIES
    # Every public attribute is a property so the lock is always held.
    # ==================================================================

    # ------------------------------------------------------------------
    # Trend dicts
    # ------------------------------------------------------------------

    @property
    def option_trend(self) -> Dict[str, Any]:
        try:
            with self._lock:
                return copy.copy(self._option_trend) if self._option_trend else _default_trend_dict()
        except Exception as e:
            logger.error(f"[option_trend getter] Failed: {e}", exc_info=True)
            return _default_trend_dict()

    @option_trend.setter
    def option_trend(self, value: Dict[str, Any]) -> None:
        try:
            with self._lock:
                self._option_trend = value if value is not None else _default_trend_dict()
        except Exception as e:
            logger.error(f"[option_trend setter] Failed: {e}", exc_info=True)

    @property
    def derivative_trend(self) -> Dict[str, Any]:
        try:
            with self._lock:
                return copy.copy(self._derivative_trend) if self._derivative_trend else _default_trend_dict()
        except Exception as e:
            logger.error(f"[derivative_trend getter] Failed: {e}", exc_info=True)
            return _default_trend_dict()

    @derivative_trend.setter
    def derivative_trend(self, value: Dict[str, Any]) -> None:
        try:
            with self._lock:
                self._derivative_trend = value if value is not None else _default_trend_dict()
        except Exception as e:
            logger.error(f"[derivative_trend setter] Failed: {e}", exc_info=True)

    @property
    def call_trend(self) -> Dict[str, Any]:
        try:
            with self._lock:
                return copy.copy(self._call_trend) if self._call_trend else _default_trend_dict()
        except Exception as e:
            logger.error(f"[call_trend getter] Failed: {e}", exc_info=True)
            return _default_trend_dict()

    @call_trend.setter
    def call_trend(self, value: Dict[str, Any]) -> None:
        try:
            with self._lock:
                self._call_trend = value if value is not None else _default_trend_dict()
        except Exception as e:
            logger.error(f"[call_trend setter] Failed: {e}", exc_info=True)

    @property
    def put_trend(self) -> Dict[str, Any]:
        try:
            with self._lock:
                return copy.copy(self._put_trend) if self._put_trend else _default_trend_dict()
        except Exception as e:
            logger.error(f"[put_trend getter] Failed: {e}", exc_info=True)
            return _default_trend_dict()

    @put_trend.setter
    def put_trend(self, value: Dict[str, Any]) -> None:
        try:
            with self._lock:
                self._put_trend = value if value is not None else _default_trend_dict()
        except Exception as e:
            logger.error(f"[put_trend setter] Failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    @property
    def token(self) -> Optional[str]:
        return self._get("_token")

    @token.setter
    def token(self, value: Optional[str]) -> None:
        self._set("_token", value)

    # ------------------------------------------------------------------
    # Candle snapshots
    # ------------------------------------------------------------------

    @property
    def current_index_data(self) -> Candle:
        return self._get("_current_index_data")

    @current_index_data.setter
    def current_index_data(self, value: Candle) -> None:
        self._set("_current_index_data", value)

    @property
    def current_put_data(self) -> Optional[pd.DataFrame]:
        return self._get("_current_put_data")

    @current_put_data.setter
    def current_put_data(self, value: Optional[pd.DataFrame]) -> None:
        self._set("_current_put_data", value)

    @property
    def current_call_data(self) -> Optional[pd.DataFrame]:
        return self._get("_current_call_data")

    @current_call_data.setter
    def current_call_data(self, value: Optional[pd.DataFrame]) -> None:
        self._set("_current_call_data", value)

    # ------------------------------------------------------------------
    # Instrument identifiers
    # ------------------------------------------------------------------

    @property
    def call_option(self) -> Optional[str]:
        return self._get("_call_option")

    @call_option.setter
    def call_option(self, value: Optional[str]) -> None:
        self._set("_call_option", value)

    @property
    def put_option(self) -> Optional[str]:
        return self._get("_put_option")

    @put_option.setter
    def put_option(self, value: Optional[str]) -> None:
        self._set("_put_option", value)

    @property
    def current_trading_symbol(self) -> Optional[str]:
        return self._get("_current_trading_symbol")

    @current_trading_symbol.setter
    def current_trading_symbol(self, value: Optional[str]) -> None:
        self._set("_current_trading_symbol", value)

    @property
    def derivative(self) -> str:
        return self._get("_derivative")

    @derivative.setter
    def derivative(self, value: str) -> None:
        self._set("_derivative", value)

    # ------------------------------------------------------------------
    # Price fields  (HOT PATH)
    # Scalar reads/writes — no copy overhead.
    # ------------------------------------------------------------------

    @property
    def derivative_current_price(self) -> float:
        return self._get("_derivative_current_price")

    @derivative_current_price.setter
    def derivative_current_price(self, value: float) -> None:
        self._set("_derivative_current_price", value)

    @property
    def current_price(self) -> Optional[float]:
        return self._get("_current_price")

    @current_price.setter
    def current_price(self, value: Optional[float]) -> None:
        self._set("_current_price", value)

    @property
    def highest_current_price(self) -> Optional[float]:
        return self._get("_highest_current_price")

    @highest_current_price.setter
    def highest_current_price(self, value: Optional[float]) -> None:
        self._set("_highest_current_price", value)

    @property
    def put_current_close(self) -> Optional[float]:
        return self._get("_put_current_close")

    @put_current_close.setter
    def put_current_close(self, value: Optional[float]) -> None:
        self._set("_put_current_close", value)

    @property
    def call_current_close(self) -> Optional[float]:
        return self._get("_call_current_close")

    @call_current_close.setter
    def call_current_close(self, value: Optional[float]) -> None:
        self._set("_call_current_close", value)

    # ------------------------------------------------------------------
    # Batch price update  (Stage-1 optimisation)
    # One lock acquisition instead of N individual property sets.
    # ------------------------------------------------------------------

    def update_prices(
            self,
            derivative_ltp: Optional[float] = None,
            current_price: Optional[float] = None,
            call_ask: Optional[float] = None,
            call_bid: Optional[float] = None,
            put_ask: Optional[float] = None,
            put_bid: Optional[float] = None,
            has_position: bool = False,
    ) -> None:
        """
        Atomically update all price fields in **one** lock acquisition.

        Replaces the original Stage-1 update_market_state() pattern of
        setting each property individually.  Call from the WS thread:

            state.update_prices(
                derivative_ltp = ltp,
                call_ask       = ask_price,
                call_bid       = bid_price,
                put_ask        = put_ask,
                put_bid        = put_bid,
                has_position   = bool(state.current_position),
            )

        Rules
        -----
        - derivative_ltp  → always stored if provided
        - call / put price → use ask when in a position (buying back),
                             use bid when not in a position (for entry calc)
        - current_price   → stored directly if provided; callers can also
                            let on_message derive it from call/put close
        """
        try:
            with self._lock:
                if derivative_ltp is not None:
                    self._derivative_current_price = derivative_ltp

                if current_price is not None:
                    self._current_price = current_price

                # Call leg
                if has_position:
                    if call_ask is not None:
                        self._call_current_close = call_ask
                else:
                    if call_bid is not None:
                        self._call_current_close = call_bid

                # Put leg
                if has_position:
                    if put_ask is not None:
                        self._put_current_close = put_ask
                else:
                    if put_bid is not None:
                        self._put_current_close = put_bid

        except Exception as e:
            logger.error(f"[TradeState.update_prices] Failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # DataFrames
    # Returned as the actual reference (DataFrames should be treated as
    # read-only by callers; the setter replaces under the lock).
    # ------------------------------------------------------------------

    @property
    def derivative_history_df(self) -> Optional[pd.DataFrame]:
        return self._get("_derivative_history_df")

    @derivative_history_df.setter
    def derivative_history_df(self, value: Optional[pd.DataFrame]) -> None:
        self._set("_derivative_history_df", value)

    @property
    def option_history_df(self) -> Optional[pd.DataFrame]:
        return self._get("_option_history_df")

    @option_history_df.setter
    def option_history_df(self, value: Optional[pd.DataFrame]) -> None:
        self._set("_option_history_df", value)

    @property
    def last_index_updated(self) -> Optional[float]:
        return self._get("_last_index_updated")

    @last_index_updated.setter
    def last_index_updated(self, value: Optional[float]) -> None:
        self._set("_last_index_updated", value)

    # ------------------------------------------------------------------
    # Orders  (list — returns shallow copy; mutate via helpers)
    # ------------------------------------------------------------------

    @property
    def orders(self) -> List[Dict[str, Any]]:
        try:
            with self._lock:
                return list(self._orders) if self._orders else []
        except Exception as e:
            logger.error(f"[orders getter] Failed: {e}", exc_info=True)
            return []

    @orders.setter
    def orders(self, value: List[Dict[str, Any]]) -> None:
        try:
            with self._lock:
                self._orders = list(value) if value is not None else []
        except Exception as e:
            logger.error(f"[orders setter] Failed: {e}", exc_info=True)

    def append_order(self, order: Dict[str, Any]) -> None:
        """Thread-safe append — prefer over orders = orders + [order]."""
        try:
            with self._lock:
                self._orders.append(order)
        except Exception as e:
            logger.error(f"[append_order] Failed: {e}", exc_info=True)

    def remove_order(self, order_id: str) -> bool:
        """Thread-safe removal by id. Returns True if the order was found."""
        try:
            with self._lock:
                before = len(self._orders)
                self._orders = [o for o in self._orders if str(o.get("id")) != str(order_id)]
                return len(self._orders) < before
        except Exception as e:
            logger.error(f"[remove_order] Failed for order {order_id}: {e}", exc_info=True)
            return False

    @property
    def confirmed_orders(self) -> List[Dict[str, Any]]:
        try:
            with self._lock:
                return list(self._confirmed_orders) if self._confirmed_orders else []
        except Exception as e:
            logger.error(f"[confirmed_orders getter] Failed: {e}", exc_info=True)
            return []

    @confirmed_orders.setter
    def confirmed_orders(self, value: List[Dict[str, Any]]) -> None:
        try:
            with self._lock:
                self._confirmed_orders = list(value) if value is not None else []
        except Exception as e:
            logger.error(f"[confirmed_orders setter] Failed: {e}", exc_info=True)

    def extend_confirmed_orders(self, orders: List[Dict[str, Any]]) -> None:
        """Thread-safe extend — prefer over confirmed_orders = confirmed_orders + list."""
        try:
            with self._lock:
                self._confirmed_orders.extend(orders)
        except Exception as e:
            logger.error(f"[extend_confirmed_orders] Failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Position state
    # ------------------------------------------------------------------

    @property
    def current_position(self) -> Optional[str]:
        return self._get("_current_position")

    @current_position.setter
    def current_position(self, value: Optional[str]) -> None:
        self._set("_current_position", value)

    @property
    def previous_position(self) -> Optional[str]:
        return self._get("_previous_position")

    @previous_position.setter
    def previous_position(self, value: Optional[str]) -> None:
        self._set("_previous_position", value)

    @property
    def current_order_id(self) -> Dict[str, int]:
        try:
            with self._lock:
                return dict(self._current_order_id) if self._current_order_id else {}
        except Exception as e:
            logger.error(f"[current_order_id getter] Failed: {e}", exc_info=True)
            return {}

    @current_order_id.setter
    def current_order_id(self, value: Dict[str, int]) -> None:
        try:
            with self._lock:
                self._current_order_id = dict(value) if value is not None else {}
        except Exception as e:
            logger.error(f"[current_order_id setter] Failed: {e}", exc_info=True)

    @property
    def current_buy_price(self) -> Optional[float]:
        return self._get("_current_buy_price")

    @current_buy_price.setter
    def current_buy_price(self, value: Optional[float]) -> None:
        self._set("_current_buy_price", value)

    @property
    def positions_hold(self) -> int:
        return self._get("_positions_hold")

    @positions_hold.setter
    def positions_hold(self, value: int) -> None:
        self._set("_positions_hold", int(value))

    @property
    def order_pending(self) -> bool:
        return self._get("_order_pending")

    @order_pending.setter
    def order_pending(self, value: bool) -> None:
        self._set("_order_pending", bool(value))

    @property
    def take_profit_type(self) -> Optional[str]:
        return self._get("_take_profit_type")

    @take_profit_type.setter
    def take_profit_type(self, value: Optional[str]) -> None:
        self._set("_take_profit_type", value)

    # ------------------------------------------------------------------
    # Risk / P&L
    # ------------------------------------------------------------------

    @property
    def index_stop_loss(self) -> Optional[float]:
        return self._get("_index_stop_loss")

    @index_stop_loss.setter
    def index_stop_loss(self, value: Optional[float]) -> None:
        self._set("_index_stop_loss", value)

    @property
    def stop_loss(self) -> Optional[float]:
        return self._get("_stop_loss")

    @stop_loss.setter
    def stop_loss(self, value: Optional[float]) -> None:
        self._set("_stop_loss", value)

    @property
    def tp_point(self) -> Optional[float]:
        return self._get("_tp_point")

    @tp_point.setter
    def tp_point(self, value: Optional[float]) -> None:
        self._set("_tp_point", value)

    @property
    def tp_percentage(self) -> float:
        return self._get("_tp_percentage")

    @tp_percentage.setter
    def tp_percentage(self, value: float) -> None:
        self._set("_tp_percentage", float(value))

    @property
    def stoploss_percentage(self) -> float:
        return self._get("_stoploss_percentage")

    @stoploss_percentage.setter
    def stoploss_percentage(self, value: float) -> None:
        self._set("_stoploss_percentage", float(value))

    @property
    def original_profit_per(self) -> float:
        return self._get("_original_profit_per")

    @original_profit_per.setter
    def original_profit_per(self, value: float) -> None:
        self._set("_original_profit_per", float(value))

    @property
    def original_stoploss_per(self) -> float:
        return self._get("_original_stoploss_per")

    @original_stoploss_per.setter
    def original_stoploss_per(self, value: float) -> None:
        self._set("_original_stoploss_per", float(value))

    @property
    def trailing_first_profit(self) -> float:
        return self._get("_trailing_first_profit")

    @trailing_first_profit.setter
    def trailing_first_profit(self, value: float) -> None:
        self._set("_trailing_first_profit", float(value))

    @property
    def max_profit(self) -> float:
        return self._get("_max_profit")

    @max_profit.setter
    def max_profit(self, value: float) -> None:
        self._set("_max_profit", float(value))

    @property
    def profit_step(self) -> float:
        return self._get("_profit_step")

    @profit_step.setter
    def profit_step(self, value: float) -> None:
        self._set("_profit_step", float(value))

    @property
    def loss_step(self) -> float:
        return self._get("_loss_step")

    @loss_step.setter
    def loss_step(self, value: float) -> None:
        self._set("_loss_step", float(value))

    # ------------------------------------------------------------------
    # Session config
    # ------------------------------------------------------------------

    @property
    def interval(self) -> Optional[str]:
        return self._get("_interval")

    @interval.setter
    def interval(self, value: Optional[str]) -> None:
        self._set("_interval", value)

    @property
    def expiry(self) -> int:
        return self._get("_expiry")

    @expiry.setter
    def expiry(self, value: int) -> None:
        self._set("_expiry", int(value))

    @property
    def lot_size(self) -> int:
        return self._get("_lot_size")

    @lot_size.setter
    def lot_size(self, value: int) -> None:
        try:
            if int(value) <= 0:
                logger.error(f"lot_size must be positive, got {value}")
                return
            self._set("_lot_size", int(value))
        except Exception as e:
            logger.error(f"[lot_size setter] Failed: {e}", exc_info=True)

    @property
    def account_balance(self) -> float:
        return self._get("_account_balance")

    @account_balance.setter
    def account_balance(self, value: float) -> None:
        self._set("_account_balance", float(value))

    @property
    def max_num_of_option(self) -> int:
        return self._get("_max_num_of_option")

    @max_num_of_option.setter
    def max_num_of_option(self, value: int) -> None:
        self._set("_max_num_of_option", int(value))

    @property
    def lower_percentage(self) -> float:
        return self._get("_lower_percentage")

    @lower_percentage.setter
    def lower_percentage(self, value: float) -> None:
        self._set("_lower_percentage", float(value))

    @property
    def cancel_after(self) -> int:
        return self._get("_cancel_after")

    @cancel_after.setter
    def cancel_after(self, value: int) -> None:
        self._set("_cancel_after", int(value))

    @property
    def capital_reserve(self) -> float:
        return self._get("_capital_reserve")

    @capital_reserve.setter
    def capital_reserve(self, value: float) -> None:
        self._set("_capital_reserve", float(value))

    @property
    def sideway_zone_trade(self) -> bool:
        return self._get("_sideway_zone_trade")

    @sideway_zone_trade.setter
    def sideway_zone_trade(self, value: bool) -> None:
        self._set("_sideway_zone_trade", bool(value))

    # ------------------------------------------------------------------
    # Lookback
    # ------------------------------------------------------------------

    @property
    def call_lookback(self) -> int:
        return self._get("_call_lookback")

    @call_lookback.setter
    def call_lookback(self, value: int) -> None:
        self._set("_call_lookback", int(value))

    @property
    def put_lookback(self) -> int:
        return self._get("_put_lookback")

    @put_lookback.setter
    def put_lookback(self, value: int) -> None:
        self._set("_put_lookback", int(value))

    @property
    def original_call_lookback(self) -> int:
        return self._get("_original_call_lookback")

    @original_call_lookback.setter
    def original_call_lookback(self, value: int) -> None:
        self._set("_original_call_lookback", int(value))

    @property
    def original_put_lookback(self) -> int:
        return self._get("_original_put_lookback")

    @original_put_lookback.setter
    def original_put_lookback(self, value: int) -> None:
        self._set("_original_put_lookback", int(value))

    # ------------------------------------------------------------------
    # Trade metadata
    # ------------------------------------------------------------------

    @property
    def current_trade_started_time(self) -> Optional[datetime]:
        return self._get("_current_trade_started_time")

    @current_trade_started_time.setter
    def current_trade_started_time(self, value: Optional[datetime]) -> None:
        self._set("_current_trade_started_time", value)

    @property
    def last_status_check(self) -> Optional[datetime]:
        return self._get("_last_status_check")

    @last_status_check.setter
    def last_status_check(self, value: Optional[datetime]) -> None:
        self._set("_last_status_check", value)

    @property
    def current_trade_confirmed(self) -> bool:
        return self._get("_current_trade_confirmed")

    @current_trade_confirmed.setter
    def current_trade_confirmed(self, value: bool) -> None:
        self._set("_current_trade_confirmed", bool(value))

    @property
    def percentage_change(self) -> Optional[float]:
        return self._get("_percentage_change")

    @percentage_change.setter
    def percentage_change(self, value: Optional[float]) -> None:
        self._set("_percentage_change", value)

    @property
    def current_pnl(self) -> Optional[float]:
        return self._get("_current_pnl")

    @current_pnl.setter
    def current_pnl(self, value: Optional[float]) -> None:
        self._set("_current_pnl", value)

    @property
    def reason_to_exit(self) -> Optional[str]:
        return self._get("_reason_to_exit")

    @reason_to_exit.setter
    def reason_to_exit(self, value: Optional[str]) -> None:
        self._set("_reason_to_exit", value)

    # ------------------------------------------------------------------
    # FEATURE 2: Smart order execution fields
    # ------------------------------------------------------------------

    @property
    def last_slippage(self) -> Optional[float]:
        """Slippage from last order fill (positive = worse price)"""
        return self._get("_last_slippage")

    @last_slippage.setter
    def last_slippage(self, value: Optional[float]) -> None:
        self._set("_last_slippage", value)

    @property
    def order_attempts(self) -> int:
        """Number of order attempts made (for metrics)"""
        return self._get("_order_attempts")

    @order_attempts.setter
    def order_attempts(self, value: int) -> None:
        self._set("_order_attempts", int(value))

    @property
    def last_order_attempt_time(self) -> Optional[datetime]:
        """Timestamp of last order attempt"""
        return self._get("_last_order_attempt_time")

    @last_order_attempt_time.setter
    def last_order_attempt_time(self, value: Optional[datetime]) -> None:
        self._set("_last_order_attempt_time", value)

    # ------------------------------------------------------------------
    # FEATURE 6: Multi-timeframe filter fields
    # ------------------------------------------------------------------

    @property
    def last_mtf_summary(self) -> Optional[str]:
        """Human-readable summary of last MTF filter decision"""
        return self._get("_last_mtf_summary")

    @last_mtf_summary.setter
    def last_mtf_summary(self, value: Optional[str]) -> None:
        self._set("_last_mtf_summary", value)

    @property
    def mtf_allowed(self) -> bool:
        """Whether last MTF filter allowed entry"""
        return self._get("_mtf_allowed")

    @mtf_allowed.setter
    def mtf_allowed(self, value: bool) -> None:
        self._set("_mtf_allowed", bool(value))

    @property
    def mtf_results(self) -> Dict[str, str]:
        """Detailed MTF results per timeframe: {'1': 'BULLISH', '5': 'NEUTRAL', ...}"""
        try:
            with self._lock:
                return dict(self._mtf_results) if self._mtf_results else {}
        except Exception as e:
            logger.error(f"[mtf_results getter] Failed: {e}", exc_info=True)
            return {}

    @mtf_results.setter
    def mtf_results(self, value: Dict[str, str]) -> None:
        try:
            with self._lock:
                self._mtf_results = dict(value) if value is not None else {}
        except Exception as e:
            logger.error(f"[mtf_results setter] Failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Misc market state
    # ------------------------------------------------------------------

    @property
    def market_trend(self) -> Optional[int]:
        return self._get("_market_trend")

    @market_trend.setter
    def market_trend(self, value: Optional[int]) -> None:
        self._set("_market_trend", value)

    @property
    def supertrend_reset(self) -> Optional[Dict[str, Any]]:
        try:
            with self._lock:
                return copy.copy(self._supertrend_reset) if self._supertrend_reset else None
        except Exception as e:
            logger.error(f"[supertrend_reset getter] Failed: {e}", exc_info=True)
            return None

    @supertrend_reset.setter
    def supertrend_reset(self, value: Optional[Dict[str, Any]]) -> None:
        try:
            with self._lock:
                self._supertrend_reset = value
        except Exception as e:
            logger.error(f"[supertrend_reset setter] Failed: {e}", exc_info=True)

    @property
    def b_band(self) -> Optional[Dict[str, Any]]:
        try:
            with self._lock:
                return copy.copy(self._b_band) if self._b_band else None
        except Exception as e:
            logger.error(f"[b_band getter] Failed: {e}", exc_info=True)
            return None

    @b_band.setter
    def b_band(self, value: Optional[Dict[str, Any]]) -> None:
        try:
            with self._lock:
                self._b_band = value
        except Exception as e:
            logger.error(f"[b_band setter] Failed: {e}", exc_info=True)

    @property
    def all_symbols(self) -> List[str]:
        try:
            with self._lock:
                return list(self._all_symbols) if self._all_symbols else []
        except Exception as e:
            logger.error(f"[all_symbols getter] Failed: {e}", exc_info=True)
            return []

    @all_symbols.setter
    def all_symbols(self, value: List[str]) -> None:
        try:
            with self._lock:
                self._all_symbols = list(value) if value is not None else []
        except Exception as e:
            logger.error(f"[all_symbols setter] Failed: {e}", exc_info=True)

    @property
    def option_price_update(self) -> Optional[bool]:
        return self._get("_option_price_update")

    @option_price_update.setter
    def option_price_update(self, value: Optional[bool]) -> None:
        self._set("_option_price_update", value)

    @property
    def calculated_pcr(self) -> Optional[float]:
        return self._get("_calculated_pcr")

    @calculated_pcr.setter
    def calculated_pcr(self, value: Optional[float]) -> None:
        self._set("_calculated_pcr", value)

    @property
    def current_pcr(self) -> float:
        return self._get("_current_pcr")

    @current_pcr.setter
    def current_pcr(self, value: float) -> None:
        self._set("_current_pcr", float(value))

    @property
    def trend(self) -> Any:
        return self._get("_trend")

    @trend.setter
    def trend(self, value: Any) -> None:
        self._set("_trend", value)

    @property
    def current_pcr_vol(self) -> Optional[float]:
        return self._get("_current_pcr_vol")

    @current_pcr_vol.setter
    def current_pcr_vol(self, value: Optional[float]) -> None:
        self._set("_current_pcr_vol", value)

    # ------------------------------------------------------------------
    # Option chain
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Option chain
    # ------------------------------------------------------------------

    @property
    def option_chain(self) -> Dict[str, Any]:
        """Option chain data (bid/ask for calculating mid-price)"""
        try:
            with self._lock:
                # Use object.__getattribute__ to bypass property getter
                chain = object.__getattribute__(self, "_option_chain")
                return copy.copy(chain) if chain else {}
        except AttributeError:
            # If _option_chain doesn't exist yet, return empty dict
            return {}
        except Exception as e:
            logger.error(f"[option_chain getter] Failed: {e}", exc_info=True)
            return {}

    @option_chain.setter
    def option_chain(self, value: Dict[str, Any]) -> None:
        try:
            with self._lock:
                # Use object.__setattr__ to bypass property setter
                object.__setattr__(self, "_option_chain", value)
        except AttributeError:
            # If _option_chain doesn't exist yet, create it
            object.__setattr__(self, "_option_chain", value)
        except Exception as e:
            logger.error(f"[option_chain setter] Failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Dynamic signal result
    # ------------------------------------------------------------------

    @property
    def option_signal_result(self) -> Optional[Dict[str, Any]]:
        try:
            with self._lock:
                # shallow copy — callers must not mutate returned dict
                return copy.copy(self._option_signal_result) if self._option_signal_result else None
        except Exception as e:
            logger.error(f"[option_signal_result getter] Failed: {e}", exc_info=True)
            return None

    @option_signal_result.setter
    def option_signal_result(self, value: Optional[Dict[str, Any]]) -> None:
        try:
            with self._lock:
                self._option_signal_result = value
        except Exception as e:
            logger.error(f"[option_signal_result setter] Failed: {e}", exc_info=True)

    # ==================================================================
    # COMPUTED / CONVENIENCE PROPERTIES
    # Each acquires the lock for the whole expression — no torn reads.
    # ==================================================================

    @property
    def option_signal(self) -> str:
        """Resolved signal string: BUY_CALL | BUY_PUT | EXIT_CALL | EXIT_PUT | HOLD | WAIT."""
        try:
            with self._lock:
                r = self._option_signal_result
                if r and r.get("available"):
                    return r.get("signal_value", "WAIT")
                return "WAIT"
        except Exception as e:
            logger.error(f"[option_signal getter] Failed: {e}", exc_info=True)
            return "WAIT"

    @property
    def should_buy_call(self) -> bool:
        try:
            return self.option_signal == "BUY_CALL"
        except Exception as e:
            logger.error(f"[should_buy_call] Failed: {e}", exc_info=True)
            return False

    @property
    def should_buy_put(self) -> bool:
        try:
            return self.option_signal == "BUY_PUT"
        except Exception as e:
            logger.error(f"[should_buy_put] Failed: {e}", exc_info=True)
            return False

    @property
    def should_sell_call(self) -> bool:
        try:
            return self.option_signal == "EXIT_CALL"
        except Exception as e:
            logger.error(f"[should_sell_call] Failed: {e}", exc_info=True)
            return False

    @property
    def should_sell_put(self) -> bool:
        try:
            return self.option_signal == "EXIT_PUT"
        except Exception as e:
            logger.error(f"[should_sell_put] Failed: {e}", exc_info=True)
            return False

    @property
    def should_hold(self) -> bool:
        try:
            return self.option_signal == "HOLD"
        except Exception as e:
            logger.error(f"[should_hold] Failed: {e}", exc_info=True)
            return False

    @property
    def should_wait(self) -> bool:
        try:
            return self.option_signal == "WAIT"
        except Exception as e:
            logger.error(f"[should_wait] Failed: {e}", exc_info=True)
            return True

    @property
    def signal_conflict(self) -> bool:
        """True when BUY_CALL and BUY_PUT both fired simultaneously."""
        try:
            with self._lock:
                r = self._option_signal_result
                return bool(r and r.get("conflict", False))
        except Exception as e:
            logger.error(f"[signal_conflict] Failed: {e}", exc_info=True)
            return False

    @property
    def dynamic_signals_active(self) -> bool:
        """True when a valid signal-engine result is available."""
        try:
            with self._lock:
                r = self._option_signal_result
                return bool(r and r.get("available", False))
        except Exception as e:
            logger.error(f"[dynamic_signals_active] Failed: {e}", exc_info=True)
            return False

    # FEATURE 3: Signal confidence properties
    @property
    def signal_confidence(self) -> Dict[str, float]:
        """Confidence scores for each signal group."""
        try:
            with self._lock:
                if not self._option_signal_result:
                    return {}
                return dict(self._option_signal_result.get("confidence", {}))
        except Exception as e:
            logger.error(f"[signal_confidence] Failed: {e}", exc_info=True)
            return {}

    @property
    def signal_explanation(self) -> str:
        """Human-readable explanation of last signal."""
        try:
            with self._lock:
                if not self._option_signal_result:
                    return ""
                return str(self._option_signal_result.get("explanation", ""))
        except Exception as e:
            logger.error(f"[signal_explanation] Failed: {e}", exc_info=True)
            return ""

    # ==================================================================
    # ATOMIC COMPOSITE READS
    # Use these in Stage-2 instead of N individual property reads so
    # the snapshot is guaranteed to be internally consistent.
    # ==================================================================

    def get_position_snapshot(self) -> Dict[str, Any]:
        """
        Atomically read every field needed for entry / exit decisions.

        Recommended usage in Stage-2 (_process_message_stage2):

            snap = state.get_position_snapshot()
            if snap["current_price"] and snap["stop_loss"]:
                if snap["current_price"] <= snap["stop_loss"]:
                    ...exit...
        """
        try:
            with self._lock:
                r = self._option_signal_result
                signal_value = (
                    r.get("signal_value", "WAIT")
                    if r and r.get("available") else "WAIT"
                )
                return {
                    "current_position": self._current_position,
                    "previous_position": self._previous_position,
                    "current_trade_confirmed": self._current_trade_confirmed,
                    "order_pending": self._order_pending,
                    "positions_hold": self._positions_hold,
                    "current_buy_price": self._current_buy_price,
                    "current_price": self._current_price,
                    "highest_current_price": self._highest_current_price,
                    "derivative_current_price": self._derivative_current_price,
                    "call_current_close": self._call_current_close,
                    "put_current_close": self._put_current_close,
                    "stop_loss": self._stop_loss,
                    "tp_point": self._tp_point,
                    "index_stop_loss": self._index_stop_loss,
                    "tp_percentage": self._tp_percentage,
                    "stoploss_percentage": self._stoploss_percentage,
                    "percentage_change": self._percentage_change,
                    "current_pnl": self._current_pnl,
                    "reason_to_exit": self._reason_to_exit,
                    "option_signal": signal_value,
                    "signal_conflict": bool(r and r.get("conflict", False)),
                    # FEATURE 2 fields
                    "last_slippage": self._last_slippage,
                    # FEATURE 6 fields
                    "last_mtf_summary": self._last_mtf_summary,
                    "mtf_allowed": self._mtf_allowed,
                }
        except Exception as e:
            logger.error(f"[get_position_snapshot] Failed: {e}", exc_info=True)
            return {}

    def get_option_signal_snapshot(self) -> Dict[str, Any]:
        """Thread-safe shallow copy of option_signal_result for GUI reads."""
        try:
            with self._lock:
                if not self._option_signal_result:
                    return _default_signal_result()
                return dict(self._option_signal_result)
        except Exception as e:
            logger.error(f"[get_option_signal_snapshot] Failed: {e}", exc_info=True)
            return _default_signal_result()

    def get_snapshot(self) -> Dict[str, Any]:
        """
        Full read-only snapshot of all state — safe to hand to the GUI
        thread without holding any lock.

        DataFrames are represented as shape strings to avoid copying
        potentially large objects.
        """
        try:
            with self._lock:
                def _df_repr(df: Optional[pd.DataFrame]) -> str:
                    if df is None:
                        return "None"
                    return "Empty DataFrame" if df.empty else f"DataFrame{df.shape}"

                r = self._option_signal_result
                sig = (r.get("signal_value", "WAIT") if r and r.get("available") else "WAIT")
                confidence = r.get("confidence", {}) if r else {}
                explanation = r.get("explanation", "") if r else ""

                return {
                    # Identifiers
                    "derivative": self._derivative,
                    "call_option": self._call_option,
                    "put_option": self._put_option,
                    "current_trading_symbol": self._current_trading_symbol,
                    "expiry": self._expiry,
                    "interval": self._interval,
                    "all_symbols": list(self._all_symbols) if self._all_symbols else [],
                    # Prices
                    "derivative_current_price": self._derivative_current_price,
                    "current_price": self._current_price,
                    "highest_current_price": self._highest_current_price,
                    "call_current_close": self._call_current_close,
                    "put_current_close": self._put_current_close,
                    # Position
                    "current_position": self._current_position,
                    "previous_position": self._previous_position,
                    "current_buy_price": self._current_buy_price,
                    "positions_hold": self._positions_hold,
                    "order_pending": self._order_pending,
                    "current_trade_confirmed": self._current_trade_confirmed,
                    "current_order_id": dict(self._current_order_id) if self._current_order_id else {},
                    "orders": len(self._orders) if self._orders else 0,
                    "confirmed_orders": len(self._confirmed_orders) if self._confirmed_orders else 0,
                    # Risk
                    "stop_loss": self._stop_loss,
                    "tp_point": self._tp_point,
                    "index_stop_loss": self._index_stop_loss,
                    "tp_percentage": self._tp_percentage,
                    "stoploss_percentage": self._stoploss_percentage,
                    "original_profit_per": self._original_profit_per,
                    "original_stoploss_per": self._original_stoploss_per,
                    "trailing_first_profit": self._trailing_first_profit,
                    "max_profit": self._max_profit,
                    "profit_step": self._profit_step,
                    "loss_step": self._loss_step,
                    "take_profit_type": self._take_profit_type,
                    # P&L
                    "current_pnl": self._current_pnl,
                    "percentage_change": self._percentage_change,
                    "account_balance": self._account_balance,
                    # Config
                    "lot_size": self._lot_size,
                    "max_num_of_option": self._max_num_of_option,
                    "lower_percentage": self._lower_percentage,
                    "cancel_after": self._cancel_after,
                    "capital_reserve": self._capital_reserve,
                    "sideway_zone_trade": self._sideway_zone_trade,
                    "call_lookback": self._call_lookback,
                    "put_lookback": self._put_lookback,
                    "original_call_lookback": self._original_call_lookback,
                    "original_put_lookback": self._original_put_lookback,
                    # Metadata
                    "reason_to_exit": self._reason_to_exit,
                    "current_trade_started_time": self._current_trade_started_time,
                    "last_status_check": self._last_status_check,
                    "last_index_updated": self._last_index_updated,
                    # FEATURE 2 fields
                    "last_slippage": self._last_slippage,
                    "order_attempts": self._order_attempts,
                    "last_order_attempt_time": self._last_order_attempt_time,
                    # FEATURE 6 fields
                    "last_mtf_summary": self._last_mtf_summary,
                    "mtf_allowed": self._mtf_allowed,
                    "mtf_results": dict(self._mtf_results) if self._mtf_results else {},
                    # PCR
                    "calculated_pcr": self._calculated_pcr,
                    "current_pcr": self._current_pcr,
                    "current_pcr_vol": self._current_pcr_vol,
                    # Misc
                    "market_trend": self._market_trend,
                    "option_price_update": self._option_price_update,
                    "trend": self._trend,
                    # Signal summary
                    "option_signal": sig,
                    "signal_conflict": bool(r and r.get("conflict", False)),
                    "dynamic_signals_active": bool(r and r.get("available", False)),
                    # FEATURE 3: Signal confidence
                    "signal_confidence": dict(confidence) if confidence else {},
                    "signal_explanation": explanation,
                    # DataFrame summaries (not full data)
                    "derivative_history_df": _df_repr(self._derivative_history_df),
                    "option_history_df": _df_repr(self._option_history_df),
                }
        except Exception as e:
            logger.error(f"[get_snapshot] Failed: {e}", exc_info=True)
            return {}

    # ==================================================================
    # ATOMIC RESET
    # ==================================================================

    def reset_trade_attributes(
            self,
            current_position: Optional[str],
            log_fn: Optional[Callable] = None,
    ) -> None:
        """
        Atomically reset all trade-lifecycle fields in one lock acquisition.

        Parameters
        ----------
        current_position:
            The position that just closed — stored as previous_position.
        log_fn:
            Optional callable (e.g. logger.info) — called *outside* the
            lock so we never do I/O while holding it.
        """
        audit = {}
        try:
            with self._lock:
                # ── Build audit record while values are still live ────────
                audit = {
                    "order_id": dict(self._current_order_id) if self._current_order_id else {},
                    "position": self._current_position,
                    "symbol": self._current_trading_symbol,
                    "start_time": self._current_trade_started_time,
                    "end_time": datetime.now(),
                    "buy_price": self._current_buy_price,
                    "sell_price": self._current_price,
                    "highest_price": self._highest_current_price,
                    "pnl": self._current_pnl,
                    "percentage_change": self._percentage_change,
                    "confirmed": self._current_trade_confirmed,
                    "reason_to_exit": self._reason_to_exit,
                    # FEATURE 2 fields
                    "last_slippage": self._last_slippage,
                    "order_attempts": self._order_attempts,
                }

                # ── Reset all trade-lifecycle fields atomically ───────────
                self._previous_position = current_position
                self._orders = []
                self._confirmed_orders = []
                self._current_position = None
                self._positions_hold = 0
                self._order_pending = False
                self._current_trading_symbol = None
                self._current_buy_price = None
                self._current_price = None
                self._stop_loss = None
                self._index_stop_loss = None
                self._tp_point = None
                self._last_status_check = None
                self._stoploss_percentage = self._original_stoploss_per
                self._tp_percentage = self._original_profit_per
                self._call_lookback = self._original_call_lookback
                self._put_lookback = self._original_put_lookback
                self._current_trade_confirmed = False
                self._current_trade_started_time = None
                self._highest_current_price = None
                self._current_pnl = None
                self._percentage_change = None
                self._reason_to_exit = None
                # FEATURE 2 fields
                self._last_slippage = None
                self._order_attempts = 0
                self._last_order_attempt_time = None
                # FEATURE 6 fields
                self._last_mtf_summary = None
                self._mtf_allowed = True
                self._mtf_results = {}
                # NOTE: option_signal_result is refreshed every bar — do NOT clear here

            # ── Log outside the lock so no I/O is done while holding it ──
            if log_fn:
                try:
                    filtered = {k: v for k, v in audit.items() if v is not None}
                    log_fn(f"Trade reset complete. Audit record: {filtered}")
                except Exception as e:
                    logger.error(f"Failed to log trade reset: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[reset_trade_attributes] Failed: {e}", exc_info=True)

    # ==================================================================
    # REPR
    # ==================================================================

    def __repr__(self) -> str:
        try:
            with self._lock:
                pos = self._current_position
                price = self._derivative_current_price
                r = self._option_signal_result
                sig = r.get("signal_value", "WAIT") if r else "WAIT"
            return (
                f"TradeState("
                f"position={pos!r}, "
                f"derivative_price={price}, "
                f"signal={sig!r}"
                f")"
            )
        except Exception as e:
            logger.error(f"[__repr__] Failed: {e}", exc_info=True)
            return "TradeState(Error)"

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        try:
            logger.info("[TradeState] Starting cleanup")

            with self._lock:
                # Clear collections
                self._orders.clear()
                self._confirmed_orders.clear()
                self._all_symbols.clear()
                self._mtf_results.clear()
                object.__setattr__(self, "option_chain", {})

                # Clear DataFrames
                self._derivative_history_df = None
                self._option_history_df = None
                self._current_put_data = None
                self._current_call_data = None

                # Clear dictionaries
                self._current_order_id.clear()
                self._supertrend_reset = None
                self._b_band = None
                self._option_signal_result = None

                # Reset to defaults
                self._current_position = None
                self._previous_position = None
                self._current_trading_symbol = None
                self._current_buy_price = None
                self._current_price = None
                self._highest_current_price = None
                self._put_current_close = None
                self._call_current_close = None
                # FEATURE 2 fields
                self._last_slippage = None
                self._order_attempts = 0
                self._last_order_attempt_time = None
                # FEATURE 6 fields
                self._last_mtf_summary = None
                self._mtf_allowed = True

            logger.info("[TradeState] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradeState.cleanup] Error: {e}", exc_info=True)