# trade_state.py (fixed)
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

IMPORTANT: CANDLE DATA MANAGEMENT
---------------------------------
TradeState does NOT store candle/OHLCV data. All historical and real-time
candle data is managed by CandleStore (via CandleStoreManager). This separation
ensures:
  - Single source of truth for price history
  - Proper thread safety for high-frequency tick updates
  - Efficient resampling for multiple timeframes
  - Clean separation between mutable trading state and immutable historical data

Version: 2.7.0 (Removed deprecated option/index DataFrame fields: current_call_data, current_put_data, current_index_data, derivative_history_df, option_history_df — all OHLCV data now lives exclusively in CandleStoreManager)
"""

import copy
import logging
import logging.handlers
import threading
import time
from datetime import datetime
# TZ-FIX: elapsed-time / cache comparisons must use ist_now() to match IST DB timestamps.
from Utils.time_utils import ist_now, IST
from typing import Any, Callable, Dict, List, Optional, Union

import pandas as pd

import BaseEnums
from Utils.safe_getattr import safe_getattr, safe_hasattr, safe_setattr

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
            'position_context': None,
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

    IMPORTANT: Candle/OHLCV data is NOT stored here. Use CandleStoreManager
    (from data.candle_store_manager) for all historical and real-time candle data.

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
        - Dedicated update methods for dictionary fields to avoid copy issues

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

        # Update option chain (use dedicated method, not direct assignment)
        state.update_option_chain_symbol("NSE:SYMBOL", {"ltp": 100, "ask": 101, "bid": 99})
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

                self._trading_mode: str = BaseEnums.PAPER   # default: paper (safe)
                self._is_paper_mode: bool = True             # True = paper/sim, False = live

                # ── Trend dicts ─────────────────────────────────────────────
                self._option_trend: Dict[str, Any] = _default_trend_dict()
                self._derivative_trend: Dict[str, Any] = _default_trend_dict()
                self._call_trend: Dict[str, Any] = _default_trend_dict()
                self._put_trend: Dict[str, Any] = _default_trend_dict()
                self._option_chain = {}

                # ── Auth ────────────────────────────────────────────────────
                self._token: Optional[str] = None

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

                # ── History / DataFrames (REMOVED - use CandleStore) ────────
                # derivative_history_df and option_history_df have been removed.
                # Use candle_store_manager.get_store(symbol).resample(minutes).
                self._last_index_updated: Optional[int] = None

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
                self._take_profit_type: Optional[str] = BaseEnums.STOP

                # ── Risk / P&L ───────────────────────────────────────────────
                self._index_stop_loss: Optional[float] = None
                self._stop_loss: Optional[float] = None
                self._tp_point: Optional[float] = None
                self._tp_percentage: float = 15.0
                self._stoploss_percentage: float = 7.0
                self._original_profit_per: float = 15.0
                self._original_stoploss_per: float = 7.0
                self._trailing_first_profit: float = 3.0
                self._trailing_activation_pct: float = 10.0   # % above entry to activate trailing
                self._trailing_sl_at_activation: float = 5.0  # % above entry SL jumps to on activation
                self._trailing_activated: bool = False         # True once activation threshold crossed
                self._trailing_last_step_pct: float = 0.0     # highest % from entry that triggered a step
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

                # ── Session tracking ─────────────────────────────────────────────
                self._session_id: Optional[int] = None  # Database session ID (integer)
                self._app_session_id: Optional[str] = None  # Application session ID (string)
                self._session_start_time: Optional[datetime] = None

                # ── Risk management fields (FEATURE 1) ─────────────────────────
                self._max_daily_loss: float = -5000.0
                self._max_trades_per_day: int = 10
                self._daily_target: float = 5000.0
                self._min_confidence: float = 0.6
                self._use_mtf_filter: bool = False
                self._market_open_time: str = "09:15"
                self._market_close_time: str = "15:30"

                # ── Re-entry guard settings ──────────────────────────────────────
                # Populated by ReEntrySetting._apply_to_state() on startup / save.
                # Consumed by TradingApp._check_reentry_allowed() each entry attempt.
                self._reentry_allow: bool = True
                self._reentry_min_candles_sl: int = 3
                self._reentry_min_candles_tp: int = 1
                self._reentry_min_candles_signal: int = 2
                self._reentry_min_candles_default: int = 2
                self._reentry_same_direction_only: bool = False
                self._reentry_require_new_signal: bool = True
                self._reentry_price_filter_enabled: bool = True
                self._reentry_price_filter_pct: float = 5.0
                self._reentry_max_per_day: int = 0

                # ── Startup validation ────────────────────────────────────────
                try:
                    assert self._lot_size > 0, "lot_size must be positive"
                    assert self._max_num_of_option >= self._lot_size, (
                        "max_num_of_option must not be less than lot_size"
                    )
                except AssertionError as e:
                    logger.error(f"Startup validation failed: {e}", exc_info=True)

                self._initialized = True
                logger.info("TradeState singleton initialized (CandleStore integration ready)")

            except Exception as e:
                logger.critical(f"[TradeState.__init__] Failed: {e}", exc_info=True)
                # Bug #6 fix: Don't mark as initialized on failure
                object.__setattr__(self, "_lock", threading.RLock())
                # self._initialized = True  # REMOVED - don't mask initialization failure

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
            logger.debug(f"[_get] Attribute {attr} not found: {e}")
            return None
        except Exception as e:
            logger.error(f"[_get] Failed for {attr}: {e}", exc_info=True)
            return None

    def _set(self, attr: str, value: Any) -> None:
        """
        Thread-safe set with error handling and debug logging.

        Args:
            attr: Attribute name to set
            value: Value to assign
        """
        try:
            with self._lock:
                # Use object.__getattribute__ directly to bypass property getters
                # and avoid recursive lock acquisition through safe_hasattr.
                try:
                    old_value = object.__getattribute__(self, attr)
                except AttributeError:
                    old_value = None
                object.__setattr__(self, attr, value)

                if logger.isEnabledFor(logging.DEBUG):
                    if old_value != value:
                        logger.debug(f"State update: {attr} = {value} (was: {old_value})")
        except AttributeError as e:
            logger.debug(f"[_set] Attribute {attr} not found: {e}")
        except Exception as e:
            logger.error(f"[_set] Failed for {attr}: {e}", exc_info=True)

    # ==================================================================
    # PROPERTIES
    # Every public attribute is a property so the lock is always held.
    # ==================================================================

    # ------------------------------------------------------------------
    # Trading Mode (runtime configuration, not global constant)
    # ------------------------------------------------------------------

    @property
    def trading_mode(self) -> str:
        """
        Current trading mode: LIVE, PAPER, or BACKTEST.
        This overrides the global BaseEnums.BOT_TYPE constant.
        """
        return self._get("_trading_mode")

    @trading_mode.setter
    def trading_mode(self, value: str) -> None:
        """Set trading mode and update paper flag accordingly."""
        try:
            with self._lock:
                self._trading_mode = value
                self._is_paper_mode = value != BaseEnums.LIVE
                logger.info(f"[TradeState] Trading mode set to: {value} (paper_mode={self._is_paper_mode})")
        except Exception as e:
            logger.error(f"[trading_mode setter] Failed: {e}", exc_info=True)

    @property
    def is_paper_mode(self) -> bool:
        """
        True when in paper or backtest mode (i.e., not LIVE).
        Used throughout the application to determine if real broker orders should be placed.
        """
        return self._get("_is_paper_mode")

    @is_paper_mode.setter
    def is_paper_mode(self, value: bool) -> None:
        """Set paper mode flag and update trading mode accordingly."""
        try:
            with self._lock:
                self._is_paper_mode = bool(value)
                self._trading_mode = BaseEnums.PAPER if value else BaseEnums.LIVE
                logger.debug(f"[TradeState] Paper mode set to: {value}")
        except Exception as e:
            logger.error(f"[is_paper_mode setter] Failed: {e}", exc_info=True)

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
        try:
            if value is None:
                logger.warning("Attempted to set derivative_current_price to None")
                return

            # Convert to float if possible
            try:
                float_val = float(value)
            except (ValueError, TypeError):
                logger.error(f"Cannot convert {value} to float")
                return

            self._set("_derivative_current_price", float_val)
        except Exception as e:
            logger.error(f"[derivative_current_price setter] Failed: {e}", exc_info=True)

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
                if safe_hasattr(value, 'timestamp'):
                    epoch = int(value.timestamp())
                else:
                    # Fallback for older datetime objects
                    epoch = int(time.mktime(value.timetuple()))
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
        # TZ-FIX: localize epoch to IST so returned datetime is timezone-aware.
        return datetime.fromtimestamp(ts, tz=IST)

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

    @property
    def trailing_activation_pct(self) -> float:
        """% rise above entry price at which trailing first activates."""
        return self._get("_trailing_activation_pct")

    @trailing_activation_pct.setter
    def trailing_activation_pct(self, value: float) -> None:
        self._set("_trailing_activation_pct", max(0.1, float(value)))

    @property
    def trailing_sl_at_activation(self) -> float:
        """SL level (% of entry) to jump to when trailing first activates."""
        return self._get("_trailing_sl_at_activation")

    @trailing_sl_at_activation.setter
    def trailing_sl_at_activation(self, value: float) -> None:
        self._set("_trailing_sl_at_activation", float(value))

    @property
    def trailing_activated(self) -> bool:
        """True once the trailing activation threshold has been crossed this trade."""
        return bool(self._get("_trailing_activated"))

    @trailing_activated.setter
    def trailing_activated(self, value: bool) -> None:
        self._set("_trailing_activated", bool(value))

    @property
    def trailing_last_step_pct(self) -> float:
        """Highest % gain from entry that has already triggered a trailing step."""
        return self._get("_trailing_last_step_pct")

    @trailing_last_step_pct.setter
    def trailing_last_step_pct(self, value: float) -> None:
        self._set("_trailing_last_step_pct", float(value))

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
            val = int(value)
            if val <= 0:
                logger.error(f"lot_size must be positive, got {value}")
                return
            self._set("_lot_size", val)
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
    # FEATURE 1: Risk management fields
    # ------------------------------------------------------------------

    @property
    def max_daily_loss(self) -> float:
        """Maximum allowed daily loss (negative value)."""
        return self._get("_max_daily_loss")

    @max_daily_loss.setter
    def max_daily_loss(self, value: float) -> None:
        """Set maximum daily loss."""
        self._set("_max_daily_loss", float(value))

    @property
    def max_trades_per_day(self) -> int:
        """Maximum number of trades per day."""
        return self._get("_max_trades_per_day")

    @max_trades_per_day.setter
    def max_trades_per_day(self, value: int) -> None:
        """Set maximum trades per day."""
        self._set("_max_trades_per_day", int(value))

    @property
    def daily_target(self) -> float:
        """Daily profit target."""
        return self._get("_daily_target")

    @daily_target.setter
    def daily_target(self, value: float) -> None:
        """Set daily profit target."""
        self._set("_daily_target", float(value))

    @property
    def min_confidence(self) -> float:
        """Minimum confidence threshold for signals (0.0-1.0)."""
        return self._get("_min_confidence")

    @min_confidence.setter
    def min_confidence(self, value: float) -> None:
        """Set minimum confidence threshold."""
        self._set("_min_confidence", float(value))

    @property
    def use_mtf_filter(self) -> bool:
        """Whether to use multi-timeframe filter."""
        return self._get("_use_mtf_filter")

    @use_mtf_filter.setter
    def use_mtf_filter(self, value: bool) -> None:
        """Set MTF filter usage."""
        self._set("_use_mtf_filter", bool(value))

    @property
    def market_open_time(self) -> str:
        """Market open time (HH:MM format)."""
        return self._get("_market_open_time")

    @market_open_time.setter
    def market_open_time(self, value: str) -> None:
        """Set market open time."""
        self._set("_market_open_time", value)

    @property
    def market_close_time(self) -> str:
        """Market close time (HH:MM format)."""
        return self._get("_market_close_time")

    @market_close_time.setter
    def market_close_time(self, value: str) -> None:
        """Set market close time."""
        self._set("_market_close_time", value)

    # ------------------------------------------------------------------
    # Re-entry guard settings
    # ------------------------------------------------------------------

    @property
    def reentry_allow(self) -> bool:
        """Master re-entry switch."""
        return self._get("_reentry_allow")

    @reentry_allow.setter
    def reentry_allow(self, value: bool) -> None:
        self._set("_reentry_allow", bool(value))

    @property
    def reentry_min_candles_sl(self) -> int:
        """Candles to wait after a stop-loss exit."""
        return self._get("_reentry_min_candles_sl")

    @reentry_min_candles_sl.setter
    def reentry_min_candles_sl(self, value: int) -> None:
        self._set("_reentry_min_candles_sl", max(0, int(value)))

    @property
    def reentry_min_candles_tp(self) -> int:
        """Candles to wait after a take-profit exit."""
        return self._get("_reentry_min_candles_tp")

    @reentry_min_candles_tp.setter
    def reentry_min_candles_tp(self, value: int) -> None:
        self._set("_reentry_min_candles_tp", max(0, int(value)))

    @property
    def reentry_min_candles_signal(self) -> int:
        """Candles to wait after a signal-based exit."""
        return self._get("_reentry_min_candles_signal")

    @reentry_min_candles_signal.setter
    def reentry_min_candles_signal(self, value: int) -> None:
        self._set("_reentry_min_candles_signal", max(0, int(value)))

    @property
    def reentry_min_candles_default(self) -> int:
        """Fallback candle wait when exit reason is unknown."""
        return self._get("_reentry_min_candles_default")

    @reentry_min_candles_default.setter
    def reentry_min_candles_default(self, value: int) -> None:
        self._set("_reentry_min_candles_default", max(0, int(value)))

    @property
    def reentry_same_direction_only(self) -> bool:
        """Block re-entry in same direction only (opposite allowed immediately)."""
        return self._get("_reentry_same_direction_only")

    @reentry_same_direction_only.setter
    def reentry_same_direction_only(self, value: bool) -> None:
        self._set("_reentry_same_direction_only", bool(value))

    @property
    def reentry_require_new_signal(self) -> bool:
        """Require a fresh signal after the candle wait."""
        return self._get("_reentry_require_new_signal")

    @reentry_require_new_signal.setter
    def reentry_require_new_signal(self, value: bool) -> None:
        self._set("_reentry_require_new_signal", bool(value))

    @property
    def reentry_price_filter_enabled(self) -> bool:
        """Enable price-chase filter on re-entry."""
        return self._get("_reentry_price_filter_enabled")

    @reentry_price_filter_enabled.setter
    def reentry_price_filter_enabled(self, value: bool) -> None:
        self._set("_reentry_price_filter_enabled", bool(value))

    @property
    def reentry_price_filter_pct(self) -> float:
        """Max price increase (%) allowed before blocking re-entry."""
        return self._get("_reentry_price_filter_pct")

    @reentry_price_filter_pct.setter
    def reentry_price_filter_pct(self, value: float) -> None:
        self._set("_reentry_price_filter_pct", max(0.0, float(value)))

    @property
    def reentry_max_per_day(self) -> int:
        """Max re-entries per day (0 = unlimited)."""
        return self._get("_reentry_max_per_day")

    @reentry_max_per_day.setter
    def reentry_max_per_day(self, value: int) -> None:
        self._set("_reentry_max_per_day", max(0, int(value)))

    @property
    def market_trend(self) -> Optional[int]:
        """Overall market trend indicator."""
        return self._get("_market_trend")

    @market_trend.setter
    def market_trend(self, value: Optional[int]) -> None:
        """Set market trend."""
        self._set("_market_trend", value)

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
    # Session tracking
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> Optional[int]:
        """
        Current database session ID.

        This ID is generated when a trading session is created in the database.
        """
        return self._get("_session_id")

    @session_id.setter
    def session_id(self, value: Optional[int]) -> None:
        """Set database session ID."""
        self._set("_session_id", value)

    @property
    def app_session_id(self) -> Optional[str]:
        """
        Current application session ID.

        This ID is generated at application startup and persists for the
        entire session. It can be used for:
        - Log correlation across components
        - Tracking trading sessions in logs/database
        - Identifying unique application runs
        """
        return self._get("_app_session_id")

    @app_session_id.setter
    def app_session_id(self, value: Optional[str]) -> None:
        """Set application session ID."""
        self._set("_app_session_id", value)

    @property
    def session_start_time(self) -> Optional[datetime]:
        """Session start timestamp."""
        return self._get("_session_start_time")

    @session_start_time.setter
    def session_start_time(self, value: Optional[datetime]) -> None:
        """Set session start time."""
        self._set("_session_start_time", value)

    # ------------------------------------------------------------------
    # Option chain
    # ------------------------------------------------------------------

    @property
    def option_chain(self) -> Dict[str, Any]:
        """
        Option chain data (bid/ask for calculating mid-price).

        IMPORTANT: This returns a DEEP COPY for external use.
        For internal updates, use the dedicated update methods.
        """
        try:
            with self._lock:
                # Use object.__getattribute__ to bypass property getter
                chain = object.__getattribute__(self, "_option_chain")
                if chain:
                    # Return a deep copy to prevent external mutation
                    return copy.deepcopy(chain)
                return {}
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
                # Store the original, not a copy
                object.__setattr__(self, "_option_chain", value)
        except AttributeError:
            # If _option_chain doesn't exist yet, create it
            object.__setattr__(self, "_option_chain", value)
        except Exception as e:
            logger.error(f"[option_chain setter] Failed: {e}", exc_info=True)

    def update_option_chain_symbol(self, symbol: str, data: Dict[str, Optional[float]]) -> bool:
        """
        Update a single symbol in the option chain.
        This avoids copying the entire dictionary.

        Args:
            symbol: The symbol to update
            data: Dictionary with ltp, ask, bid values

        Returns:
            bool: True if updated, False if symbol not found
        """
        try:
            with self._lock:
                if symbol in self._option_chain:
                    self._option_chain[symbol] = data
                    logger.debug(f"Updated option chain for {symbol}: {data}")
                    return True
                else:
                    logger.debug(f"Symbol {symbol} not in option chain")
                    return False
        except Exception as e:
            logger.error(f"[update_option_chain_symbol] Failed: {e}", exc_info=True)
            return False

    def update_option_chain_batch(self, updates: Dict[str, Dict[str, Optional[float]]]) -> int:
        """
        Update multiple symbols in the option chain atomically.

        Args:
            updates: Dictionary mapping symbol -> {ltp, ask, bid}

        Returns:
            int: Number of symbols successfully updated
        """
        try:
            with self._lock:
                updated = 0
                for symbol, data in updates.items():
                    if symbol in self._option_chain:
                        self._option_chain[symbol] = data
                        updated += 1
                if updated > 0:
                    logger.debug(f"Batch updated {updated} symbols in option chain")
                return updated
        except Exception as e:
            logger.error(f"[update_option_chain_batch] Failed: {e}", exc_info=True)
            return 0

    def get_option_chain_symbol(self, symbol: str) -> Optional[Dict[str, Optional[float]]]:
        """
        Get data for a specific symbol from the option chain.

        Args:
            symbol: The symbol to retrieve

        Returns:
            Optional[Dict]: Symbol data or None if not found
        """
        try:
            with self._lock:
                if symbol in self._option_chain:
                    # Return a copy to prevent mutation
                    return copy.copy(self._option_chain[symbol])
                return None
        except Exception as e:
            logger.error(f"[get_option_chain_symbol] Failed: {e}", exc_info=True)
            return None

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
        """Set signal result.  The dict is stored as-is (not copied) so the
        engine can replace it atomically; callers must never mutate the
        returned shallow copy's nested objects (fired, confidence, etc.).
        """
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
            with self._lock:
                r = self._option_signal_result
                return bool(r and r.get("available") and r.get("signal_value") == "BUY_CALL")
        except Exception as e:
            logger.error(f"[should_buy_call] Failed: {e}", exc_info=True)
            return False

    @property
    def should_buy_put(self) -> bool:
        """True if signal indicates BUY_PUT."""
        try:
            with self._lock:
                r = self._option_signal_result
                return bool(r and r.get("available") and r.get("signal_value") == "BUY_PUT")
        except Exception as e:
            logger.error(f"[should_buy_put] Failed: {e}", exc_info=True)
            return False

    @property
    def should_sell_call(self) -> bool:
        """True if signal indicates EXIT_CALL."""
        try:
            with self._lock:
                r = self._option_signal_result
                return bool(r and r.get("available") and r.get("signal_value") == "EXIT_CALL")
        except Exception as e:
            logger.error(f"[should_sell_call] Failed: {e}", exc_info=True)
            return False

    @property
    def should_sell_put(self) -> bool:
        """True if signal indicates EXIT_PUT."""
        try:
            with self._lock:
                r = self._option_signal_result
                return bool(r and r.get("available") and r.get("signal_value") == "EXIT_PUT")
        except Exception as e:
            logger.error(f"[should_sell_put] Failed: {e}", exc_info=True)
            return False

    @property
    def should_hold(self) -> bool:
        """True if signal indicates HOLD."""
        try:
            with self._lock:
                r = self._option_signal_result
                return bool(r and r.get("available") and r.get("signal_value") == "HOLD")
        except Exception as e:
            logger.error(f"[should_hold] Failed: {e}", exc_info=True)
            return False

    @property
    def should_wait(self) -> bool:
        """True if signal indicates WAIT (no clear signal)."""
        try:
            with self._lock:
                r = self._option_signal_result
                if not r or not r.get("available"):
                    return True
                return r.get("signal_value") == "WAIT"
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

        NOTE: This snapshot contains only scalar trading state.
        For OHLCV/candle data, use CandleStoreManager.

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
                - is_paper_mode (trading mode)
                - trading_mode (exact mode)
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
                    "session_id": self._session_id,
                    "app_session_id": self._app_session_id,
                    "session_start_time": self._session_start_time,
                    # FEATURE 6 fields
                    "last_mtf_summary": self._last_mtf_summary,
                    "mtf_allowed": self._mtf_allowed,
                    # Trading mode
                    "is_paper_mode": self._is_paper_mode,
                    "trading_mode": self._trading_mode,
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

        NOTE: This snapshot contains only scalar trading state and DataFrame
        summaries. For actual OHLCV/candle data, use CandleStoreManager.

        DataFrames are represented as shape strings to avoid copying
        potentially large objects (kept for backward compatibility).

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
                    # Trading mode
                    "trading_mode": self._trading_mode,
                    "is_paper_mode": self._is_paper_mode,

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
                    "trailing_activation_pct": self._trailing_activation_pct,
                    "trailing_sl_at_activation": self._trailing_sl_at_activation,
                    "trailing_activated": self._trailing_activated,
                    "trailing_last_step_pct": self._trailing_last_step_pct,
                    "max_profit": self._max_profit,
                    "profit_step": self._profit_step,
                    "loss_step": self._loss_step,
                    "take_profit_type": self._take_profit_type,

                    # FEATURE 1: Risk management
                    "max_daily_loss": self._max_daily_loss,
                    "max_trades_per_day": self._max_trades_per_day,
                    "daily_target": self._daily_target,
                    "min_confidence": self._min_confidence,
                    "use_mtf_filter": self._use_mtf_filter,
                    "market_open_time": self._market_open_time,
                    "market_close_time": self._market_close_time,

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

                    "session_id": self._session_id,
                    "app_session_id": self._app_session_id,
                    "session_start_time": self._session_start_time,

                    # Re-entry guard settings
                    "reentry_allow": self._reentry_allow,
                    "reentry_min_candles_sl": self._reentry_min_candles_sl,
                    "reentry_min_candles_tp": self._reentry_min_candles_tp,
                    "reentry_min_candles_signal": self._reentry_min_candles_signal,
                    "reentry_min_candles_default": self._reentry_min_candles_default,
                    "reentry_same_direction_only": self._reentry_same_direction_only,
                    "reentry_require_new_signal": self._reentry_require_new_signal,
                    "reentry_price_filter_enabled": self._reentry_price_filter_enabled,
                    "reentry_price_filter_pct": self._reentry_price_filter_pct,
                    "reentry_max_per_day": self._reentry_max_per_day,
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

        # Computed / read-only properties — never written back
        computed_properties = {
            'option_signal', 'should_buy_call', 'should_buy_put',
            'should_sell_call', 'should_sell_put', 'should_hold',
            'should_wait', 'signal_conflict', 'dynamic_signals_active',
            'signal_confidence', 'signal_explanation',
        }

        # Collection-type guards (checked outside lock — no I/O under lock)
        type_errors: list = []
        collection_checks = {
            'orders': (list, tuple),
            'confirmed_orders': (list, tuple),
            'all_symbols': (list, tuple),
            'mtf_results': dict,
            'current_order_id': dict,
        }

        restored_count = 0
        skipped_count = 0

        try:
            with self._lock:
                for key, value in data.items():
                    if key in computed_properties:
                        skipped_count += 1
                        continue

                    if key in collection_checks:
                        expected = collection_checks[key]
                        if not isinstance(value, expected):
                            type_errors.append((key, type(value)))
                            skipped_count += 1
                            continue

                    if safe_hasattr(self, key) and not key.startswith('_'):
                        attr = safe_getattr(type(self), key, None)
                        if isinstance(attr, property):
                            if attr.fset is None:
                                skipped_count += 1
                                continue
                            try:
                                safe_setattr(self, key, value)
                                restored_count += 1
                            except Exception:
                                skipped_count += 1
                        else:
                            try:
                                safe_setattr(self, key, value)
                                restored_count += 1
                            except Exception:
                                skipped_count += 1
                    else:
                        private_key = f"_{key}"
                        if safe_hasattr(self, private_key):
                            # Skip DataFrame summary strings from get_snapshot()
                            existing = safe_getattr(self, private_key, None)
                            if isinstance(existing, (pd.DataFrame, type(None))) and isinstance(value, str):
                                skipped_count += 1
                                continue
                            try:
                                object.__setattr__(self, private_key, value)
                                restored_count += 1
                            except Exception:
                                skipped_count += 1
                        else:
                            skipped_count += 1

        except Exception as e:
            logger.error(f"[update_from_dict] Failed: {e}", exc_info=True)

        # ── All logging outside the lock (design principle #4) ───────────────
        for key, typ in type_errors:
            logger.warning(f"[update_from_dict] {key} has wrong type {typ} - skipping")
        logger.debug(f"[update_from_dict] Restored {restored_count} fields, skipped {skipped_count} fields")

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

        This preserves trading mode settings (trading_mode, is_paper_mode)
        while resetting trade-specific fields.

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
                # Save trading mode before reset
                trading_mode = self._trading_mode
                is_paper_mode = self._is_paper_mode
                interval = self._interval  # Bug #9 fix: Preserve interval
                session_id = self._session_id
                app_session_id = self._app_session_id
                session_start_time = self._session_start_time

                # ── Build audit record while values are still live ────────
                audit = {
                    "order_id": dict(self._current_order_id) if self._current_order_id else {},
                    "position": self._current_position,
                    "symbol": self._current_trading_symbol,
                    "start_time": self._current_trade_started_time,
                    "end_time": ist_now(),
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

                # Trailing guard fields — reset for next trade
                self._trailing_activated = False
                self._trailing_last_step_pct = 0.0

                # Restore preserved settings
                self._trading_mode = trading_mode
                self._is_paper_mode = is_paper_mode
                self._interval = interval  # Bug #9 fix: Restore interval
                self._session_id = session_id
                self._app_session_id = app_session_id
                self._session_start_time = session_start_time
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
                mode = self._trading_mode
            return (
                f"TradeState("
                f"position={pos!r}, "
                f"derivative_price={price}, "
                f"signal={sig!r}, "
                f"mode={mode!r}"
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

                # Clear dictionaries
                self._current_order_id.clear()
                self._option_signal_result = None

                # Reset to defaults but preserve trading mode
                trading_mode = self._trading_mode
                is_paper_mode = self._is_paper_mode
                interval = self._interval

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

                # Restore preserved settings
                self._trading_mode = trading_mode
                self._is_paper_mode = is_paper_mode
                self._interval = interval

            logger.info("[TradeState] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradeState.cleanup] Error: {e}", exc_info=True)