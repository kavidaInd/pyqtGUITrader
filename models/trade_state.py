"""
Trade State Module
==================
Thread-safe central state container for the Algo Trading Dashboard.

This module provides a thread-safe implementation of the trading system's
central state object, managing all mutable data that needs to be shared
across multiple threads. It replaces the original dataclass with a fully
thread-safe version while maintaining identical attribute names and behavior.

THREADING MODEL
---------------
Three concurrent actors touch this object:

  1. **WebSocket thread (Stage 1)** — writes price fields on every tick
     (high frequency, many writes per second)
  2. **Thread-pool (Stage 2)** — reads prices, writes position/signal state
     (moderate frequency, decision making)
  3. **GUI / QTimer** — reads everything for display
     (low frequency, periodic UI updates)

DESIGN PRINCIPLES
-----------------
1. **Single RLock** - A single `threading.RLock` (re-entrant lock) guards every
   field. This allows the same thread to nest acquisitions safely.

2. **Property-based Access** - Every field is accessed through @property/@setter
   pairs, so all call-sites remain identical to the original dataclass —
   zero caller changes required.

3. **Atomic Operations** - Critical operations (batch price updates, snapshots,
   reset) are performed in a single lock acquisition to ensure consistency.

4. **Minimal Lock Hold Time** - I/O operations (logging, callbacks) are performed
   outside the lock to minimize contention.

5. **Defensive Copying** - Collections and complex objects are returned as
   shallow copies so callers cannot mutate shared state.

SINGLETON PATTERN
-----------------
The TradeState is implemented as a thread-safe singleton to ensure a single
source of truth across the entire application. This allows both live trading
and backtesting components to work with the same state object.

Thread Safety Rules:
- Every __get__ and __set__ of a mutable field acquires _lock
- Computed properties (should_buy_call, etc.) acquire the lock for the
  whole expression to prevent torn reads mid-expression
- Heavy objects (DataFrames, dicts, lists) are stored under the lock and
  returned as shallow copies
- `get_snapshot()` returns a plain-dict copy of all scalar fields — safe
  to hand to the GUI thread without holding any lock
- `get_position_snapshot()` atomically reads every field needed for an
  entry/exit decision — use this in Stage 2 rather than N individual property reads
- `update_prices()` batch-updates all price fields in one acquisition to
  minimise lock overhead on the hot WebSocket path
- `reset_trade_attributes()` is fully atomic (single lock acquisition)
- `update_from_dict()` safely restores state from a snapshot, handling
  computed properties and type conversions

Data Flow:
    WebSocket Thread (Stage 1)
        ↓
    update_prices()  ← batch price update (1 lock)
        ↓
    Stage 2 Thread (Thread Pool)
        ↓
    get_position_snapshot() ← atomic decision data
        ↓
    decision logic → write results
        ↓
    GUI Thread
        ↓
    get_snapshot() ← full state for display

Version: 2.2.0 (Fixed state restoration)
"""

import copy
import logging
import logging.handlers
import threading
import time
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

    Returns a dictionary with all expected signal result fields initialized
    to safe default values.
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
# TradeState (Singleton)
# ---------------------------------------------------------------------------

class TradeState:
    """
    Central container for all mutable trading state.

    Implemented as a thread-safe singleton to ensure a single source of truth
    across the entire application. This allows both live trading and backtesting
    components to work with the same state object.

    The class is designed as a drop-in replacement for the original @dataclass
    version: identical attribute names, same default values, same convenience
    properties — with a threading.RLock added so reads and writes from the
    WS thread, thread-pool, and GUI timer cannot interleave.

    Key Design Points:
        - All fields are private (underscore-prefixed) with public properties
        - Collections are returned as copies to prevent external mutation
        - Batch operations (update_prices, reset_trade_attributes) minimize
          lock acquisitions
        - Snapshot methods provide atomic, consistent views of related fields
        - I/O is performed outside locks to minimize contention
        - update_from_dict() safely restores state from snapshots

    Quick-start
    -----------
        state = TradeState.get_instance()  # Get singleton instance

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

        # Restore state from backtest
        state.update_from_dict(saved_snapshot)
    """

    # Singleton instance variables
    _instance = None
    _singleton_lock = threading.RLock()
    _initialized = False

    # ------------------------------------------------------------------
    # Singleton Pattern Implementation
    # ------------------------------------------------------------------

    def __new__(cls):
        """Thread-safe singleton instantiation."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initialize TradeState with default values for all fields.
        This runs only once due to the _initialized flag.
        """
        # Prevent re-initialization
        if self._initialized:
            return

        with self._singleton_lock:
            if self._initialized:
                return

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
                self._last_index_updated: Optional[int] = None
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

                self._initialized = True
                logger.info("TradeState singleton initialized")

            except Exception as e:
                logger.critical(f"[TradeState.__init__] Failed: {e}", exc_info=True)
                # Still set _lock to prevent crashes
                object.__setattr__(self, "_lock", threading.RLock())
                self._initialized = True  # Mark as initialized to prevent repeated failures

    @classmethod
    def get_instance(cls) -> 'TradeState':
        """
        Get the singleton instance of TradeState.

        Returns:
            TradeState: The singleton instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """
        Reset the singleton instance.

        This is primarily useful for testing or when you need a completely
        fresh state (e.g., between backtest runs).

        Warning: This will discard all current state data.
        """
        with cls._singleton_lock:
            if cls._instance is not None:
                # Clean up the old instance
                try:
                    cls._instance.cleanup()
                except Exception as e:
                    logger.error(f"[reset_instance] Cleanup failed: {e}", exc_info=True)
            cls._instance = None
            cls._initialized = False
            logger.info("TradeState singleton reset")

    # ------------------------------------------------------------------
    # Private helpers — avoid repeating acquire/release boilerplate
    # ------------------------------------------------------------------

    def _get(self, attr: str) -> Any:
        """
        Thread-safe get with error handling.

        Args:
            attr: Attribute name to retrieve

        Returns:
            Any: Attribute value, or None if error
        """
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
        """
        Thread-safe set with error handling.

        Args:
            attr: Attribute name to set
            value: Value to assign
        """
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
        """Current option trend data (shallow copy)."""
        try:
            with self._lock:
                return copy.copy(self._option_trend) if self._option_trend else _default_trend_dict()
        except Exception as e:
            logger.error(f"[option_trend getter] Failed: {e}", exc_info=True)
            return _default_trend_dict()

    @option_trend.setter
    def option_trend(self, value: Dict[str, Any]) -> None:
        """Set option trend data."""
        try:
            with self._lock:
                self._option_trend = value if value is not None else _default_trend_dict()
        except Exception as e:
            logger.error(f"[option_trend setter] Failed: {e}", exc_info=True)

    @property
    def derivative_trend(self) -> Dict[str, Any]:
        """Current derivative trend data (shallow copy)."""
        try:
            with self._lock:
                return copy.copy(self._derivative_trend) if self._derivative_trend else _default_trend_dict()
        except Exception as e:
            logger.error(f"[derivative_trend getter] Failed: {e}", exc_info=True)
            return _default_trend_dict()

    @derivative_trend.setter
    def derivative_trend(self, value: Dict[str, Any]) -> None:
        """Set derivative trend data."""
        try:
            with self._lock:
                self._derivative_trend = value if value is not None else _default_trend_dict()
        except Exception as e:
            logger.error(f"[derivative_trend setter] Failed: {e}", exc_info=True)

    @property
    def call_trend(self) -> Dict[str, Any]:
        """Current call option trend data (shallow copy)."""
        try:
            with self._lock:
                return copy.copy(self._call_trend) if self._call_trend else _default_trend_dict()
        except Exception as e:
            logger.error(f"[call_trend getter] Failed: {e}", exc_info=True)
            return _default_trend_dict()

    @call_trend.setter
    def call_trend(self, value: Dict[str, Any]) -> None:
        """Set call option trend data."""
        try:
            with self._lock:
                self._call_trend = value if value is not None else _default_trend_dict()
        except Exception as e:
            logger.error(f"[call_trend setter] Failed: {e}", exc_info=True)

    @property
    def put_trend(self) -> Dict[str, Any]:
        """Current put option trend data (shallow copy)."""
        try:
            with self._lock:
                return copy.copy(self._put_trend) if self._put_trend else _default_trend_dict()
        except Exception as e:
            logger.error(f"[put_trend getter] Failed: {e}", exc_info=True)
            return _default_trend_dict()

    @put_trend.setter
    def put_trend(self, value: Dict[str, Any]) -> None:
        """Set put option trend data."""
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
        """Broker authentication token."""
        return self._get("_token")

    @token.setter
    def token(self, value: Optional[str]) -> None:
        """Set broker authentication token."""
        self._set("_token", value)

    # ------------------------------------------------------------------
    # Candle snapshots
    # ------------------------------------------------------------------

    @property
    def current_index_data(self) -> Candle:
        """Current index candle data."""
        return self._get("_current_index_data")

    @current_index_data.setter
    def current_index_data(self, value: Candle) -> None:
        """Set current index candle data."""
        self._set("_current_index_data", value)

    @property
    def current_put_data(self) -> Optional[pd.DataFrame]:
        """Current put option historical data."""
        return self._get("_current_put_data")

    @current_put_data.setter
    def current_put_data(self, value: Optional[pd.DataFrame]) -> None:
        """Set current put option historical data."""
        self._set("_current_put_data", value)

    @property
    def current_call_data(self) -> Optional[pd.DataFrame]:
        """Current call option historical data."""
        return self._get("_current_call_data")

    @current_call_data.setter
    def current_call_data(self, value: Optional[pd.DataFrame]) -> None:
        """Set current call option historical data."""
        self._set("_current_call_data", value)

    # ------------------------------------------------------------------
    # Instrument identifiers
    # ------------------------------------------------------------------

    @property
    def call_option(self) -> Optional[str]:
        """ATM call option symbol."""
        return self._get("_call_option")

    @call_option.setter
    def call_option(self, value: Optional[str]) -> None:
        """Set ATM call option symbol."""
        self._set("_call_option", value)

    @property
    def put_option(self) -> Optional[str]:
        """ATM put option symbol."""
        return self._get("_put_option")

    @put_option.setter
    def put_option(self, value: Optional[str]) -> None:
        """Set ATM put option symbol."""
        self._set("_put_option", value)

    @property
    def current_trading_symbol(self) -> Optional[str]:
        """Currently active trading symbol (if any)."""
        return self._get("_current_trading_symbol")

    @current_trading_symbol.setter
    def current_trading_symbol(self, value: Optional[str]) -> None:
        """Set current trading symbol."""
        self._set("_current_trading_symbol", value)

    @property
    def derivative(self) -> str:
        """Underlying derivative symbol (e.g., NIFTY50-INDEX)."""
        return self._get("_derivative")

    @derivative.setter
    def derivative(self, value: str) -> None:
        """Set underlying derivative symbol."""
        self._set("_derivative", value)

    # ------------------------------------------------------------------
    # Price fields  (HOT PATH)
    # Scalar reads/writes — no copy overhead.
    # ------------------------------------------------------------------

    @property
    def derivative_current_price(self) -> float:
        """Current price of the underlying derivative."""
        return self._get("_derivative_current_price")

    @derivative_current_price.setter
    def derivative_current_price(self, value: float) -> None:
        """Set current derivative price."""
        self._set("_derivative_current_price", value)

    @property
    def current_price(self) -> Optional[float]:
        """Current price of the active option position."""
        return self._get("_current_price")

    @current_price.setter
    def current_price(self, value: Optional[float]) -> None:
        """Set current option price."""
        self._set("_current_price", value)

    @property
    def highest_current_price(self) -> Optional[float]:
        """Highest price reached during current trade."""
        return self._get("_highest_current_price")

    @highest_current_price.setter
    def highest_current_price(self, value: Optional[float]) -> None:
        """Set highest price for current trade."""
        self._set("_highest_current_price", value)

    @property
    def put_current_close(self) -> Optional[float]:
        """Current price of put option (bid or ask depending on position)."""
        return self._get("_put_current_close")

    @put_current_close.setter
    def put_current_close(self, value: Optional[float]) -> None:
        """Set current put option price."""
        self._set("_put_current_close", value)

    @property
    def call_current_close(self) -> Optional[float]:
        """Current price of call option (bid or ask depending on position)."""
        return self._get("_call_current_close")

    @call_current_close.setter
    def call_current_close(self, value: Optional[float]) -> None:
        """Set current call option price."""
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
        setting each property individually. This method is optimized for
        the high-frequency WebSocket thread.

        Rules
        -----
        - derivative_ltp → always stored if provided
        - call / put price → use ask when in a position (buying back),
                             use bid when not in a position (for entry calc)
        - current_price   → stored directly if provided; callers can also
                            let on_message derive it from call/put close

        Args:
            derivative_ltp: Last traded price of underlying
            current_price: Direct current price (if known)
            call_ask: Ask price of call option
            call_bid: Bid price of call option
            put_ask: Ask price of put option
            put_bid: Bid price of put option
            has_position: Whether a position is currently held (determines ask/bid selection)

        Example:
            state.update_prices(
                derivative_ltp = ltp,
                call_ask       = ask_price,
                call_bid       = bid_price,
                put_ask        = put_ask,
                put_bid        = put_bid,
                has_position   = bool(state.current_position),
            )
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
        """Historical OHLC data for derivative."""
        return self._get("_derivative_history_df")

    @derivative_history_df.setter
    def derivative_history_df(self, value: Optional[pd.DataFrame]) -> None:
        """Set derivative historical data."""
        if value is not None and not isinstance(value, pd.DataFrame):
            logger.error(
                f"[TradeState] derivative_history_df setter received unexpected type "
                f"{type(value).__name__!r} (value={str(value)!r:.80}); storing None instead"
            )
            value = None
        self._set("_derivative_history_df", value)

    @property
    def option_history_df(self) -> Optional[pd.DataFrame]:
        """Historical OHLC data for options."""
        return self._get("_option_history_df")

    @option_history_df.setter
    def option_history_df(self, value: Optional[pd.DataFrame]) -> None:
        """Set option historical data."""
        self._set("_option_history_df", value)

    @property
    def last_index_updated(self) -> Optional[int]:
        """Timestamp of last index update."""
        return self._get("_last_index_updated")

    @last_index_updated.setter
    def last_index_updated(self, value: Optional[Union[datetime, float, pd.Timestamp]]) -> None:
        """Set last index update timestamp. Converts to integer epoch seconds."""
        if value is None:
            self._set("_last_index_updated", None)
            return

        try:
            if isinstance(value, (datetime, pd.Timestamp)):
                # Convert datetime to integer epoch
                if hasattr(value, 'timestamp'):
                    epoch = int(value.timestamp())
                else:
                    # Fallback for older datetime objects
                    epoch = int(value.timestamp()) if hasattr(value, 'timestamp') else int(
                        time.mktime(value.timetuple()))
            elif isinstance(value, (float, int)):
                # Convert float/int to integer epoch
                epoch = int(value)
            else:
                logger.error(f"Cannot convert {type(value)} to epoch timestamp")
                self._set("_last_index_updated", None)
                return

            self._set("_last_index_updated", epoch)

        except Exception as e:
            logger.error(f"Error converting to epoch timestamp: {e}", exc_info=True)
            self._set("_last_index_updated", None)

    @property
    def last_index_updated_dt(self) -> Optional[datetime]:
        """Get last index update as datetime object."""
        ts = self.last_index_updated
        if ts is None:
            return None
        return datetime.fromtimestamp(ts)

    @last_index_updated_dt.setter
    def last_index_updated_dt(self, value: Optional[datetime]) -> None:
        """Set last index update from datetime."""
        self.last_index_updated = value

    # ------------------------------------------------------------------
    # Orders  (list — returns shallow copy; mutate via helpers)
    # ------------------------------------------------------------------

    @property
    def orders(self) -> List[Dict[str, Any]]:
        """List of pending orders (shallow copy)."""
        try:
            with self._lock:
                return list(self._orders) if self._orders else []
        except Exception as e:
            logger.error(f"[orders getter] Failed: {e}", exc_info=True)
            return []

    @orders.setter
    def orders(self, value: List[Dict[str, Any]]) -> None:
        """Set orders list with safe type handling."""
        try:
            with self._lock:
                # Handle various input types safely
                if value is None:
                    self._orders = []
                elif isinstance(value, (list, tuple)):
                    self._orders = list(value)
                elif isinstance(value, (int, float, str, bool)):
                    # Don't try to convert non-list to list - log warning and set empty
                    logger.warning(f"[orders setter] Attempted to set non-list value: {type(value)}={value}")
                    self._orders = []
                else:
                    # Try to convert if it's iterable but not list/tuple
                    try:
                        self._orders = list(value)
                    except TypeError:
                        logger.error(f"[orders setter] Cannot convert {type(value)} to list")
                        self._orders = []
        except Exception as e:
            logger.error(f"[orders setter] Failed: {e}", exc_info=True)
            with self._lock:
                self._orders = []

    def append_order(self, order: Dict[str, Any]) -> None:
        """
        Thread-safe append to orders list.

        Args:
            order: Order dictionary to append
        """
        try:
            with self._lock:
                self._orders.append(order)
        except Exception as e:
            logger.error(f"[append_order] Failed: {e}", exc_info=True)

    def remove_order(self, order_id: str) -> bool:
        """
        Thread-safe removal by id.

        Args:
            order_id: Order ID to remove

        Returns:
            bool: True if the order was found and removed
        """
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
        """List of confirmed orders (shallow copy)."""
        try:
            with self._lock:
                return list(self._confirmed_orders) if self._confirmed_orders else []
        except Exception as e:
            logger.error(f"[confirmed_orders getter] Failed: {e}", exc_info=True)
            return []

    @confirmed_orders.setter
    def confirmed_orders(self, value: List[Dict[str, Any]]) -> None:
        """Set confirmed orders list with safe type handling."""
        try:
            with self._lock:
                # Handle various input types safely
                if value is None:
                    self._confirmed_orders = []
                elif isinstance(value, (list, tuple)):
                    self._confirmed_orders = list(value)
                elif isinstance(value, (int, float, str, bool)):
                    # Don't try to convert non-list to list - log warning and set empty
                    logger.warning(f"[confirmed_orders setter] Attempted to set non-list value: {type(value)}={value}")
                    self._confirmed_orders = []
                else:
                    # Try to convert if it's iterable but not list/tuple
                    try:
                        self._confirmed_orders = list(value)
                    except TypeError:
                        logger.error(f"[confirmed_orders setter] Cannot convert {type(value)} to list")
                        self._confirmed_orders = []
        except Exception as e:
            logger.error(f"[confirmed_orders setter] Failed: {e}", exc_info=True)
            with self._lock:
                self._confirmed_orders = []

    def extend_confirmed_orders(self, orders: List[Dict[str, Any]]) -> None:
        """
        Thread-safe extend for confirmed orders.

        Args:
            orders: List of orders to append
        """
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
        """Current position type (CALL/PUT) or None."""
        return self._get("_current_position")

    @current_position.setter
    def current_position(self, value: Optional[str]) -> None:
        """Set current position."""
        self._set("_current_position", value)

    @property
    def previous_position(self) -> Optional[str]:
        """Previous position type (for reset logic)."""
        return self._get("_previous_position")

    @previous_position.setter
    def previous_position(self, value: Optional[str]) -> None:
        """Set previous position."""
        self._set("_previous_position", value)

    @property
    def current_order_id(self) -> Dict[str, int]:
        """Mapping of order IDs (shallow copy)."""
        try:
            with self._lock:
                return dict(self._current_order_id) if self._current_order_id else {}
        except Exception as e:
            logger.error(f"[current_order_id getter] Failed: {e}", exc_info=True)
            return {}

    @current_order_id.setter
    def current_order_id(self, value: Dict[str, int]) -> None:
        """Set order ID mapping."""
        try:
            with self._lock:
                self._current_order_id = dict(value) if value is not None else {}
        except Exception as e:
            logger.error(f"[current_order_id setter] Failed: {e}", exc_info=True)

    @property
    def current_buy_price(self) -> Optional[float]:
        """Entry price of current position."""
        return self._get("_current_buy_price")

    @current_buy_price.setter
    def current_buy_price(self, value: Optional[float]) -> None:
        """Set entry price."""
        self._set("_current_buy_price", value)

    @property
    def positions_hold(self) -> int:
        """Number of positions currently held."""
        return self._get("_positions_hold")

    @positions_hold.setter
    def positions_hold(self, value: int) -> None:
        """Set positions held count."""
        self._set("_positions_hold", int(value))

    @property
    def order_pending(self) -> bool:
        """Whether an order is pending execution."""
        return self._get("_order_pending")

    @order_pending.setter
    def order_pending(self, value: bool) -> None:
        """Set order pending status."""
        self._set("_order_pending", bool(value))

    @property
    def take_profit_type(self) -> Optional[str]:
        """Type of take profit (STOP/TRAILING)."""
        return self._get("_take_profit_type")

    @take_profit_type.setter
    def take_profit_type(self, value: Optional[str]) -> None:
        """Set take profit type."""
        self._set("_take_profit_type", value)

    # ------------------------------------------------------------------
    # Risk / P&L
    # ------------------------------------------------------------------

    @property
    def index_stop_loss(self) -> Optional[float]:
        """Stop loss based on index price."""
        return self._get("_index_stop_loss")

    @index_stop_loss.setter
    def index_stop_loss(self, value: Optional[float]) -> None:
        """Set index-based stop loss."""
        self._set("_index_stop_loss", value)

    @property
    def stop_loss(self) -> Optional[float]:
        """Option price stop loss level."""
        return self._get("_stop_loss")

    @stop_loss.setter
    def stop_loss(self, value: Optional[float]) -> None:
        """Set option price stop loss."""
        self._set("_stop_loss", value)

    @property
    def tp_point(self) -> Optional[float]:
        """Take profit price level."""
        return self._get("_tp_point")

    @tp_point.setter
    def tp_point(self, value: Optional[float]) -> None:
        """Set take profit level."""
        self._set("_tp_point", value)

    @property
    def tp_percentage(self) -> float:
        """Take profit percentage."""
        return self._get("_tp_percentage")

    @tp_percentage.setter
    def tp_percentage(self, value: float) -> None:
        """Set take profit percentage."""
        self._set("_tp_percentage", float(value))

    @property
    def stoploss_percentage(self) -> float:
        """Stop loss percentage."""
        return self._get("_stoploss_percentage")

    @stoploss_percentage.setter
    def stoploss_percentage(self, value: float) -> None:
        """Set stop loss percentage."""
        self._set("_stoploss_percentage", float(value))

    @property
    def original_profit_per(self) -> float:
        """Original (non-trailed) profit percentage."""
        return self._get("_original_profit_per")

    @original_profit_per.setter
    def original_profit_per(self, value: float) -> None:
        """Set original profit percentage."""
        self._set("_original_profit_per", float(value))

    @property
    def original_stoploss_per(self) -> float:
        """Original (non-trailed) stop loss percentage."""
        return self._get("_original_stoploss_per")

    @original_stoploss_per.setter
    def original_stoploss_per(self, value: float) -> None:
        """Set original stop loss percentage."""
        self._set("_original_stoploss_per", float(value))

    @property
    def trailing_first_profit(self) -> float:
        """First profit level at which trailing activates."""
        return self._get("_trailing_first_profit")

    @trailing_first_profit.setter
    def trailing_first_profit(self, value: float) -> None:
        """Set first trailing profit level."""
        self._set("_trailing_first_profit", float(value))

    @property
    def max_profit(self) -> float:
        """Maximum allowed profit percentage."""
        return self._get("_max_profit")

    @max_profit.setter
    def max_profit(self, value: float) -> None:
        """Set maximum profit percentage."""
        self._set("_max_profit", float(value))

    @property
    def profit_step(self) -> float:
        """Step size for trailing profit updates."""
        return self._get("_profit_step")

    @profit_step.setter
    def profit_step(self, value: float) -> None:
        """Set profit step size."""
        self._set("_profit_step", float(value))

    @property
    def loss_step(self) -> float:
        """Step size for trailing stop updates."""
        return self._get("_loss_step")

    @loss_step.setter
    def loss_step(self, value: float) -> None:
        """Set loss step size."""
        self._set("_loss_step", float(value))

    # ------------------------------------------------------------------
    # Session config
    # ------------------------------------------------------------------

    @property
    def interval(self) -> Optional[str]:
        """Timeframe interval for analysis."""
        return self._get("_interval")

    @interval.setter
    def interval(self, value: Optional[str]) -> None:
        """Set analysis interval."""
        self._set("_interval", value)

    @property
    def expiry(self) -> int:
        """Option expiry week/week identifier."""
        return self._get("_expiry")

    @expiry.setter
    def expiry(self, value: int) -> None:
        """Set expiry identifier."""
        self._set("_expiry", int(value))

    @property
    def lot_size(self) -> int:
        """Trading lot size (must be positive)."""
        return self._get("_lot_size")

    @lot_size.setter
    def lot_size(self, value: int) -> None:
        """Set lot size with validation."""
        try:
            if int(value) <= 0:
                logger.error(f"lot_size must be positive, got {value}")
                return
            self._set("_lot_size", int(value))
        except Exception as e:
            logger.error(f"[lot_size setter] Failed: {e}", exc_info=True)

    @property
    def account_balance(self) -> float:
        """Current account balance."""
        return self._get("_account_balance")

    @account_balance.setter
    def account_balance(self, value: float) -> None:
        """Set account balance."""
        self._set("_account_balance", float(value))

    @property
    def max_num_of_option(self) -> int:
        """Maximum number of option contracts allowed."""
        return self._get("_max_num_of_option")

    @max_num_of_option.setter
    def max_num_of_option(self, value: int) -> None:
        """Set maximum option contracts."""
        self._set("_max_num_of_option", int(value))

    @property
    def lower_percentage(self) -> float:
        """Lower percentage threshold for trading."""
        return self._get("_lower_percentage")

    @lower_percentage.setter
    def lower_percentage(self, value: float) -> None:
        """Set lower percentage threshold."""
        self._set("_lower_percentage", float(value))

    @property
    def cancel_after(self) -> int:
        """Seconds after which to cancel pending orders."""
        return self._get("_cancel_after")

    @cancel_after.setter
    def cancel_after(self, value: int) -> None:
        """Set cancel timeout."""
        self._set("_cancel_after", int(value))

    @property
    def capital_reserve(self) -> float:
        """Capital reserve percentage."""
        return self._get("_capital_reserve")

    @capital_reserve.setter
    def capital_reserve(self, value: float) -> None:
        """Set capital reserve percentage."""
        self._set("_capital_reserve", float(value))

    @property
    def sideway_zone_trade(self) -> bool:
        """Whether to trade in sideways market."""
        return self._get("_sideway_zone_trade")

    @sideway_zone_trade.setter
    def sideway_zone_trade(self, value: bool) -> None:
        """Set sideways trading flag."""
        self._set("_sideway_zone_trade", bool(value))

    # ------------------------------------------------------------------
    # Lookback
    # ------------------------------------------------------------------

    @property
    def call_lookback(self) -> int:
        """Lookback periods for call option calculations."""
        return self._get("_call_lookback")

    @call_lookback.setter
    def call_lookback(self, value: int) -> None:
        """Set call lookback."""
        self._set("_call_lookback", int(value))

    @property
    def put_lookback(self) -> int:
        """Lookback periods for put option calculations."""
        return self._get("_put_lookback")

    @put_lookback.setter
    def put_lookback(self, value: int) -> None:
        """Set put lookback."""
        self._set("_put_lookback", int(value))

    @property
    def original_call_lookback(self) -> int:
        """Original (non-adjusted) call lookback."""
        return self._get("_original_call_lookback")

    @original_call_lookback.setter
    def original_call_lookback(self, value: int) -> None:
        """Set original call lookback."""
        self._set("_original_call_lookback", int(value))

    @property
    def original_put_lookback(self) -> int:
        """Original (non-adjusted) put lookback."""
        return self._get("_original_put_lookback")

    @original_put_lookback.setter
    def original_put_lookback(self, value: int) -> None:
        """Set original put lookback."""
        self._set("_original_put_lookback", int(value))

    # ------------------------------------------------------------------
    # Trade metadata
    # ------------------------------------------------------------------

    @property
    def current_trade_started_time(self) -> Optional[datetime]:
        """Timestamp when current trade started."""
        return self._get("_current_trade_started_time")

    @current_trade_started_time.setter
    def current_trade_started_time(self, value: Optional[datetime]) -> None:
        """Set trade start time."""
        self._set("_current_trade_started_time", value)

    @property
    def last_status_check(self) -> Optional[datetime]:
        """Last time trade status was checked."""
        return self._get("_last_status_check")

    @last_status_check.setter
    def last_status_check(self, value: Optional[datetime]) -> None:
        """Set last status check time."""
        self._set("_last_status_check", value)

    @property
    def current_trade_confirmed(self) -> bool:
        """Whether current trade is confirmed (order executed)."""
        return self._get("_current_trade_confirmed")

    @current_trade_confirmed.setter
    def current_trade_confirmed(self, value: bool) -> None:
        """Set trade confirmation status."""
        self._set("_current_trade_confirmed", bool(value))

    @property
    def percentage_change(self) -> Optional[float]:
        """Percentage change since entry."""
        return self._get("_percentage_change")

    @percentage_change.setter
    def percentage_change(self, value: Optional[float]) -> None:
        """Set percentage change."""
        self._set("_percentage_change", value)

    @property
    def current_pnl(self) -> Optional[float]:
        """Current profit/loss amount."""
        return self._get("_current_pnl")

    @current_pnl.setter
    def current_pnl(self, value: Optional[float]) -> None:
        """Set current P&L."""
        self._set("_current_pnl", value)

    @property
    def reason_to_exit(self) -> Optional[str]:
        """Reason for last exit (for logging/display)."""
        return self._get("_reason_to_exit")

    @reason_to_exit.setter
    def reason_to_exit(self, value: Optional[str]) -> None:
        """Set exit reason."""
        self._set("_reason_to_exit", value)

    # ------------------------------------------------------------------
    # FEATURE 2: Smart order execution fields
    # ------------------------------------------------------------------

    @property
    def last_slippage(self) -> Optional[float]:
        """Slippage from last order fill (positive = worse price)."""
        return self._get("_last_slippage")

    @last_slippage.setter
    def last_slippage(self, value: Optional[float]) -> None:
        """Set last slippage value."""
        self._set("_last_slippage", value)

    @property
    def order_attempts(self) -> int:
        """Number of order attempts made (for metrics)."""
        return self._get("_order_attempts")

    @order_attempts.setter
    def order_attempts(self, value: int) -> None:
        """Set order attempts count."""
        self._set("_order_attempts", int(value))

    @property
    def last_order_attempt_time(self) -> Optional[datetime]:
        """Timestamp of last order attempt."""
        return self._get("_last_order_attempt_time")

    @last_order_attempt_time.setter
    def last_order_attempt_time(self, value: Optional[datetime]) -> None:
        """Set last order attempt time."""
        self._set("_last_order_attempt_time", value)

    # ------------------------------------------------------------------
    # FEATURE 6: Multi-timeframe filter fields
    # ------------------------------------------------------------------

    @property
    def last_mtf_summary(self) -> Optional[str]:
        """Human-readable summary of last MTF filter decision."""
        return self._get("_last_mtf_summary")

    @last_mtf_summary.setter
    def last_mtf_summary(self, value: Optional[str]) -> None:
        """Set MTF summary."""
        self._set("_last_mtf_summary", value)

    @property
    def mtf_allowed(self) -> bool:
        """Whether last MTF filter allowed entry."""
        return self._get("_mtf_allowed")

    @mtf_allowed.setter
    def mtf_allowed(self, value: bool) -> None:
        """Set MTF allowed flag."""
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
        """Set MTF results."""
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
        """Overall market trend indicator."""
        return self._get("_market_trend")

    @market_trend.setter
    def market_trend(self, value: Optional[int]) -> None:
        """Set market trend."""
        self._set("_market_trend", value)

    @property
    def supertrend_reset(self) -> Optional[Dict[str, Any]]:
        """Supertrend reset state (shallow copy)."""
        try:
            with self._lock:
                return copy.copy(self._supertrend_reset) if self._supertrend_reset else None
        except Exception as e:
            logger.error(f"[supertrend_reset getter] Failed: {e}", exc_info=True)
            return None

    @supertrend_reset.setter
    def supertrend_reset(self, value: Optional[Dict[str, Any]]) -> None:
        """Set supertrend reset state."""
        try:
            with self._lock:
                self._supertrend_reset = value
        except Exception as e:
            logger.error(f"[supertrend_reset setter] Failed: {e}", exc_info=True)

    @property
    def b_band(self) -> Optional[Dict[str, Any]]:
        """Bollinger Band values (shallow copy)."""
        try:
            with self._lock:
                return copy.copy(self._b_band) if self._b_band else None
        except Exception as e:
            logger.error(f"[b_band getter] Failed: {e}", exc_info=True)
            return None

    @b_band.setter
    def b_band(self, value: Optional[Dict[str, Any]]) -> None:
        """Set Bollinger Band values."""
        try:
            with self._lock:
                self._b_band = value
        except Exception as e:
            logger.error(f"[b_band setter] Failed: {e}", exc_info=True)

    @property
    def all_symbols(self) -> List[str]:
        """List of all subscribed symbols (shallow copy)."""
        try:
            with self._lock:
                return list(self._all_symbols) if self._all_symbols else []
        except Exception as e:
            logger.error(f"[all_symbols getter] Failed: {e}", exc_info=True)
            return []

    @all_symbols.setter
    def all_symbols(self, value: List[str]) -> None:
        """Set all symbols list."""
        try:
            with self._lock:
                self._all_symbols = list(value) if value is not None else []
        except Exception as e:
            logger.error(f"[all_symbols setter] Failed: {e}", exc_info=True)

    @property
    def option_price_update(self) -> Optional[bool]:
        """Whether option prices have been updated."""
        return self._get("_option_price_update")

    @option_price_update.setter
    def option_price_update(self, value: Optional[bool]) -> None:
        """Set option price update flag."""
        self._set("_option_price_update", value)

    @property
    def calculated_pcr(self) -> Optional[float]:
        """Calculated Put-Call Ratio."""
        return self._get("_calculated_pcr")

    @calculated_pcr.setter
    def calculated_pcr(self, value: Optional[float]) -> None:
        """Set calculated PCR."""
        self._set("_calculated_pcr", value)

    @property
    def current_pcr(self) -> float:
        """Current Put-Call Ratio."""
        return self._get("_current_pcr")

    @current_pcr.setter
    def current_pcr(self, value: float) -> None:
        """Set current PCR."""
        self._set("_current_pcr", float(value))

    @property
    def trend(self) -> Any:
        """Current trend value (type varies by detector)."""
        return self._get("_trend")

    @trend.setter
    def trend(self, value: Any) -> None:
        """Set trend value."""
        self._set("_trend", value)

    @property
    def current_pcr_vol(self) -> Optional[float]:
        """Current PCR based on volume."""
        return self._get("_current_pcr_vol")

    @current_pcr_vol.setter
    def current_pcr_vol(self, value: Optional[float]) -> None:
        """Set volume-based PCR."""
        self._set("_current_pcr_vol", value)

    # ------------------------------------------------------------------
    # Option chain
    # ------------------------------------------------------------------

    @property
    def option_chain(self) -> Dict[str, Any]:
        """Option chain data (bid/ask for calculating mid-price)."""
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
        """Set option chain data."""
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
        """Complete signal result dictionary (shallow copy)."""
        try:
            with self._lock:
                # shallow copy — callers must not mutate returned dict
                return copy.copy(self._option_signal_result) if self._option_signal_result else None
        except Exception as e:
            logger.error(f"[option_signal_result getter] Failed: {e}", exc_info=True)
            return None

    @option_signal_result.setter
    def option_signal_result(self, value: Optional[Dict[str, Any]]) -> None:
        """Set signal result."""
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
        """
        Resolved signal string: BUY_CALL | BUY_PUT | EXIT_CALL | EXIT_PUT | HOLD | WAIT.

        Note: This is a computed property with no setter.
        """
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
        """True if signal indicates BUY_CALL."""
        try:
            return self.option_signal == "BUY_CALL"
        except Exception as e:
            logger.error(f"[should_buy_call] Failed: {e}", exc_info=True)
            return False

    @property
    def should_buy_put(self) -> bool:
        """True if signal indicates BUY_PUT."""
        try:
            return self.option_signal == "BUY_PUT"
        except Exception as e:
            logger.error(f"[should_buy_put] Failed: {e}", exc_info=True)
            return False

    @property
    def should_sell_call(self) -> bool:
        """True if signal indicates EXIT_CALL."""
        try:
            return self.option_signal == "EXIT_CALL"
        except Exception as e:
            logger.error(f"[should_sell_call] Failed: {e}", exc_info=True)
            return False

    @property
    def should_sell_put(self) -> bool:
        """True if signal indicates EXIT_PUT."""
        try:
            return self.option_signal == "EXIT_PUT"
        except Exception as e:
            logger.error(f"[should_sell_put] Failed: {e}", exc_info=True)
            return False

    @property
    def should_hold(self) -> bool:
        """True if signal indicates HOLD."""
        try:
            return self.option_signal == "HOLD"
        except Exception as e:
            logger.error(f"[should_hold] Failed: {e}", exc_info=True)
            return False

    @property
    def should_wait(self) -> bool:
        """True if signal indicates WAIT (no clear signal)."""
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

        This method provides a consistent snapshot of all fields required
        for making trading decisions. Using this single call instead of
        multiple property reads ensures that all values are from the same
        point in time.

        Recommended usage in Stage-2 (_process_message_stage2):

            snap = state.get_position_snapshot()
            if snap["current_price"] and snap["stop_loss"]:
                if snap["current_price"] <= snap["stop_loss"]:
                    ...exit...

        Returns:
            Dict[str, Any]: Snapshot containing:
                - current_position
                - previous_position
                - current_trade_confirmed
                - order_pending
                - positions_hold
                - current_buy_price
                - current_price
                - highest_current_price
                - derivative_current_price
                - call_current_close
                - put_current_close
                - stop_loss
                - tp_point
                - index_stop_loss
                - tp_percentage
                - stoploss_percentage
                - percentage_change
                - current_pnl
                - reason_to_exit
                - option_signal
                - signal_conflict
                - last_slippage (FEATURE 2)
                - last_mtf_summary (FEATURE 6)
                - mtf_allowed (FEATURE 6)
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
        """
        Thread-safe shallow copy of option_signal_result for GUI reads.

        Returns:
            Dict[str, Any]: Complete signal result dictionary, or default
                           if no signal available.
        """
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

        Returns:
            Dict[str, Any]: Complete state snapshot with all fields.
                           DataFrames are summarized as strings to avoid
                           large data transfer to GUI.
        """
        try:
            with self._lock:
                def _df_repr(df: Optional[pd.DataFrame]) -> str:
                    if df is None:
                        return "None"
                    if not isinstance(df, pd.DataFrame):
                        logger.warning(
                            f"[get_snapshot] _df_repr received unexpected type {type(df).__name__!r} "
                            f"(value={str(df)!r:.80}); treating as None"
                        )
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
    # STATE RESTORATION
    # ==================================================================

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """
        Update state from a dictionary, handling computed properties specially.

        This method should be used instead of directly setting properties
        when restoring state from a snapshot. It safely handles:
        - Computed properties that don't have setters
        - Collection type conversions
        - Private vs public attributes

        Args:
            data: Dictionary of state values to restore
        """
        if not data:
            logger.debug("[update_from_dict] No data to restore")
            return

        try:
            with self._lock:
                # List of computed properties that should NOT be directly set
                computed_properties = {
                    'option_signal', 'should_buy_call', 'should_buy_put',
                    'should_sell_call', 'should_sell_put', 'should_hold',
                    'should_wait', 'signal_conflict', 'dynamic_signals_active',
                    'signal_confidence', 'signal_explanation'
                }

                restored_count = 0
                skipped_count = 0

                for key, value in data.items():
                    # Skip computed properties
                    if key in computed_properties:
                        logger.debug(f"[update_from_dict] Skipping computed property: {key}")
                        skipped_count += 1
                        continue

                    # Handle special cases for collections
                    if key == 'orders' and not isinstance(value, (list, tuple)):
                        logger.warning(f"[update_from_dict] orders is not a list: {type(value)} - skipping")
                        skipped_count += 1
                        continue

                    if key == 'confirmed_orders' and not isinstance(value, (list, tuple)):
                        logger.warning(f"[update_from_dict] confirmed_orders is not a list: {type(value)} - skipping")
                        skipped_count += 1
                        continue

                    if key == 'all_symbols' and not isinstance(value, (list, tuple)):
                        logger.warning(f"[update_from_dict] all_symbols is not a list: {type(value)} - skipping")
                        skipped_count += 1
                        continue

                    if key == 'mtf_results' and not isinstance(value, dict):
                        logger.warning(f"[update_from_dict] mtf_results is not a dict: {type(value)} - skipping")
                        skipped_count += 1
                        continue

                    if key == 'current_order_id' and not isinstance(value, dict):
                        logger.warning(f"[update_from_dict] current_order_id is not a dict: {type(value)} - skipping")
                        skipped_count += 1
                        continue

                    # Check if the attribute exists and is settable via property
                    if hasattr(self, key) and not key.startswith('_'):
                        # Check if it's a property with a setter
                        attr = getattr(type(self), key, None)
                        if isinstance(attr, property):
                            if attr.fset is None:
                                logger.debug(f"[update_from_dict] Property {key} has no setter - skipping")
                                skipped_count += 1
                                continue
                            else:
                                # Property with setter - use it
                                try:
                                    setattr(self, key, value)
                                    restored_count += 1
                                except Exception as e:
                                    logger.debug(f"[update_from_dict] Cannot set {key}: {e}")
                                    skipped_count += 1
                        else:
                            # Regular attribute - set directly
                            try:
                                setattr(self, key, value)
                                restored_count += 1
                            except Exception as e:
                                logger.debug(f"[update_from_dict] Cannot set {key}: {e}")
                                skipped_count += 1
                    else:
                        # Handle private attributes (those starting with _)
                        private_key = f"_{key}"
                        if hasattr(self, private_key):
                            # Skip DataFrame summary strings produced by get_snapshot()
                            # (e.g. "None", "Empty DataFrame", "DataFrame(100, 5)").
                            # These are human-readable representations, not real DataFrames,
                            # and must not be written back into DataFrame-typed attributes.
                            existing = getattr(self, private_key, _MISSING := object())
                            if isinstance(existing, (pd.DataFrame, type(None))) and isinstance(value, str):
                                logger.debug(
                                    f"[update_from_dict] Skipping DataFrame summary string "
                                    f"for private attr {private_key!r}: {value!r}"
                                )
                                skipped_count += 1
                                continue
                            try:
                                object.__setattr__(self, private_key, value)
                                restored_count += 1
                            except Exception as e:
                                logger.debug(f"[update_from_dict] Cannot set private {private_key}: {e}")
                                skipped_count += 1
                        else:
                            logger.debug(f"[update_from_dict] Attribute {key} not found - skipping")
                            skipped_count += 1

                logger.debug(f"[update_from_dict] Restored {restored_count} fields, skipped {skipped_count} fields")

        except Exception as e:
            logger.error(f"[update_from_dict] Failed: {e}", exc_info=True)

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

        This method clears all state related to the current trade and
        prepares for the next trade. It captures audit information before
        resetting, then calls the provided log function (outside the lock)
        to record the completed trade.

        Parameters
        ----------
        current_position:
            The position that just closed — stored as previous_position.
        log_fn:
            Optional callable (e.g. logger.info) — called *outside* the
            lock so we never do I/O while holding it.

        Example:
            state.reset_trade_attributes(
                current_position="CALL",
                log_fn=lambda msg: logger.info(msg)
            )
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
        """String representation for debugging."""
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
                object.__setattr__(self, "_option_chain", {})

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