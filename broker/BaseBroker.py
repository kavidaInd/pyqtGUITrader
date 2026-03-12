"""
BaseBroker.py
=============
Abstract base class defining the unified broker interface.
All broker implementations must inherit from this class.

Supported brokers:
- Fyers      (fyers_apiv3)
- Zerodha    (kiteconnect)
- Dhan       (dhanhq)
- AngelOne   (smartapi-python)
- Upstox     (upstox-python-sdk)
- Shoonya    (NorenRestApiPy)
- AliceBlue  (pya3)
- Flattrade  (NorenRestApiPy)

UPDATED:
- Added broker_type property and improved token expiry handling.
- Added _format_symbol(), _split_symbol(), _to_interval() default implementations
  that delegate to OptionUtils — subclasses can override for broker-specific logic.
- Added balance helpers: get_available_balance(), get_balance_after_reserve(),
  get_current_pnl_from_state(), get_net_balance() which pull live P&L from
  TradeState/TradeStateManager so any broker can compute usable capital without
  duplicating state-management code.
- Added retry + rate-limit helpers: _check_rate_limit(), retry_on_failure()
  as concrete default implementations with sensible defaults. Subclasses can
  override or call super().
- Added shared trading calculation helpers: calculate_shares_to_buy(),
  round_to_nse_price(), percentage_above_or_below().
- Added market-hours helpers (delegates to Utils/common) so broker code never
  needs to import Utils directly.
- FIXED: Token expiry is now properly propagated and never swallowed.
  Added token expiry tracking, automatic checks before API calls, and
  integration with centralized TokenExpiryHandler.
"""

import logging
import time
import threading
import random
import math
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from Utils.time_utils import IST, ist_now, fmt_display, fmt_stamp
from typing import Optional, Any, Dict, List, Callable, Union

from broker.TokenExpiryHandler import token_expiry_handler

logger = logging.getLogger(__name__)


class TokenExpiredError(RuntimeError):
    """Exception raised when broker token has expired or is invalid."""

    def __init__(self, message: str = "Token expired or invalid", code: Optional[int] = None):
        if code is not None:
            message = f"{message} (code: {code})"
        super().__init__(message)
        self.code = code
        self.timestamp = ist_now()


class BaseBroker(ABC):
    """
    Abstract base class for all broker integrations.

    Every broker must implement the abstract methods so the rest of the
    application can work with any broker without modification.

    Concrete helper methods provided here (and available to all subclasses):
    ─────────────────────────────────────────────────────────────────────
    Symbol helpers
        _format_symbol(symbol)          → broker-prefixed symbol string for ANY symbol type
                                          (auto-detects index vs option, replaces _get_index_symbol)
        _split_symbol(symbol)           → (exchange, trading_symbol) tuple
        _to_interval(interval)          → broker-native interval string

    Balance / P&L helpers (uses TradeStateManager)
        get_available_balance(reserve)  → float  (calls get_balance then deducts reserve)
        get_balance_after_reserve(bal, reserve_pct) → float
        get_current_pnl_from_state()    → float  (live P&L from TradeState)
        get_net_balance(reserve)        → float  (broker balance + open P&L - reserve)

    Trading calculation helpers
        calculate_shares_to_buy(bal, price, lot_size) → int
        round_to_nse_price(price)       → float
        percentage_above_or_below(price, pct, side)   → float

    Market-hours helpers (delegates to Utils/common)
        is_market_open()                → bool
        is_market_closed_for_the_day()  → bool
        is_near_market_close(minutes)   → bool
        get_market_start_time()         → datetime
        get_market_end_time()           → datetime

    Rate-limit / retry helpers
        _check_rate_limit()             → None  (token-bucket limiter)
        retry_on_failure(func, ...)     → Any   (subclass can override)

    P&L
        calculate_pnl(current, buy, qty) → float  (class-level, broker-agnostic)

    Token expiry handling (NEW)
        token_expiry                    → property returning expiry datetime
        _check_token_before_request()   → raises TokenExpiredError if token expired
        _handle_token_expired()         → delegates to central handler
    """

    # ── Order side constants (universal) ──────────────────────────────────────
    SIDE_BUY = 1
    # Each broker subclass MUST override SIDE_SELL with its own correct value.
    # -1 matches Fyers convention as fallback.
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

    # ── Internal rate-limit state (per-instance, not class-level) ─────────────
    # Subclasses that need their own counters should set these in __init__.
    _last_request_time: float = 0.0
    _request_count: int = 0
    # _rate_lock is initialized as an instance variable in each subclass __init__.
    # Class-level fallback prevents AttributeError if a subclass forgets to init it.
    _rate_lock: "threading.Lock"  # type hint only; instance lock set in subclass __init__

    # ── Paper mode flag ───────────────────────────────────────────────────────
    # When True, place_order / exit_position / sell_at_current are intercepted
    # at the BaseBroker level and SIMULATED instead of forwarded to the real
    # broker API.  Set via TradingApp._apply_trading_mode_to_executor().
    # Default is False (LIVE) so existing call sites are unaffected.
    paper_mode: bool = False

    # ── Token expiry tracking ──────────────────────────────────────────────────
    _token_expiry_check_interval: int = 60  # seconds
    _last_token_check: float = 0.0
    _token_handler = token_expiry_handler

    # =========================================================================
    # broker_type / token properties
    # =========================================================================

    @property
    def broker_type(self) -> str:
        """
        Return the broker type identifier matching BrokerType constants.

        Strips the trailing "Broker" suffix from the class name and lowercases.
        """
        class_name = self.__class__.__name__
        if class_name.endswith("Broker"):
            return class_name[:-len("Broker")].lower()
        return class_name.lower()

    @property
    def token_expiry(self) -> Optional[datetime]:
        """
        Return token expiry datetime if available, None otherwise.

        Subclasses should override this to return the actual expiry time
        from their token storage. The base implementation returns None,
        which means "token never expires" (static tokens) or "expiry unknown".
        """
        return None

    @property
    def token_issued_at(self) -> Optional[datetime]:
        """Return token issue datetime if available, None otherwise."""
        return None

    @property
    def token_remaining_seconds(self) -> Optional[float]:
        """
        Return seconds remaining until token expiry, or None if unknown.
        """
        expiry = self.token_expiry
        if expiry is None:
            return None
        remaining = (expiry - ist_now()).total_seconds()
        return max(0.0, remaining)

    @property
    def is_token_expired(self) -> bool:
        expiry = self.token_expiry
        if expiry is None:
            return False

        now = ist_now()

        if expiry.tzinfo is None:
            expiry = IST.localize(expiry)

        return now >= expiry

    # =========================================================================
    # Token expiry handling
    # =========================================================================

    def _check_token_before_request(self) -> None:
        """
        Check token validity before making any API request.

        This method should be called at the beginning of every public API method
        that makes a broker request. If the token is expired, it will raise
        TokenExpiredError and notify the central handler.

        Raises:
            TokenExpiredError: If token is expired
        """
        # Rate limit the checks to avoid excessive datetime comparisons
        now = time.time()
        if now - self._last_token_check > self._token_expiry_check_interval:
            self._last_token_check = now
            if self.is_token_expired:
                self._handle_token_expired(
                    f"Token expired at {self.token_expiry}",
                    recovery_callback=self._on_token_recovered
                )

    def _handle_token_expired(self, message: str, recovery_callback: Optional[Callable] = None) -> None:
        """
        Handle token expiry by delegating to central handler.

        This method:
        1. Logs the expiry at CRITICAL level
        2. Notifies the central TokenExpiryHandler
        3. Raises TokenExpiredError for immediate callers

        Args:
            message: Error message describing the expiry
            recovery_callback: Optional callback to execute after successful recovery

        Raises:
            TokenExpiredError: Always raised
        """
        logger.critical(f"[{self.broker_type}] {message}")

        # Register with central handler
        self._token_handler.handle_token_expired(
            source=self.broker_type,
            error_msg=message,
            recovery_callback=recovery_callback
        )

        # Raise exception for immediate callers
        raise TokenExpiredError(message)

    def _on_token_recovered(self) -> None:
        """
        Callback executed after token has been successfully refreshed.

        Subclasses can override this to perform any necessary cleanup or
        re-initialization after token refresh.
        """
        logger.info(f"[{self.broker_type}] Token recovered, resuming operations")

    # =========================================================================
    # Abstract REST methods every broker must implement
    # =========================================================================

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

    # =========================================================================
    # Paper-mode order interception
    # =========================================================================
    # These three concrete methods are the ONLY entry points for order
    # submission.  They check paper_mode first:
    #   • paper_mode=True  → log + return synthetic response; no API call
    #   • paper_mode=False → delegate to the subclass's abstract implementation
    #
    # Subclasses MUST implement the abstract methods below (place_order etc.)
    # exactly as before — the routing is fully transparent to them.
    # =========================================================================

    def _maybe_paper_place_order(self, **kwargs) -> Optional[str]:
        """
        Simulate or forward a place_order call depending on paper_mode.

        Returns a synthetic "PAPER-<ms>" order-id in paper mode so the rest
        of the system (order tracking, position state) functions identically
        to a real fill without touching the broker API.
        """
        if self.paper_mode:
            import time as _time
            paper_id = f"PAPER-{int(_time.time() * 1000)}"
            logger.info(
                f"[{self.broker_type.upper()}] PAPER MODE — order simulated: "
                f"id={paper_id} | kwargs={kwargs}"
            )
            return paper_id
        return self.place_order(**kwargs)

    def _maybe_paper_exit_position(self, **kwargs) -> bool:
        """
        Simulate or forward an exit_position call depending on paper_mode.

        Returns True immediately in paper mode so the position monitor can
        clear state without sending a real sell order.
        """
        if self.paper_mode:
            logger.info(
                f"[{self.broker_type.upper()}] PAPER MODE — exit simulated: "
                f"kwargs={kwargs}"
            )
            return True
        return self.exit_position(**kwargs)

    def _maybe_paper_sell_at_current(self, **kwargs) -> bool:
        """Simulate or forward sell_at_current depending on paper_mode."""
        if self.paper_mode:
            logger.info(
                f"[{self.broker_type.upper()}] PAPER MODE — sell_at_current simulated: "
                f"kwargs={kwargs}"
            )
            return True
        return self.sell_at_current(**kwargs)

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

    def get_fill_price(self, broker_order_id: str) -> Optional[float]:
        """
        Return the actual fill/execution price for a completed order, or None.

        This is a concrete (non-abstract) method with a safe default of None
        so existing subclasses do not need to implement it immediately.
        Each broker should override this to query its order API for the fill price.
        """
        return None

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the broker session is active."""

    @abstractmethod
    def cleanup(self) -> None:
        """Release resources on shutdown."""

    # =========================================================================
    # Abstract WebSocket methods every broker must implement
    # =========================================================================

    @abstractmethod
    def create_websocket(
        self,
        on_tick: Callable,
        on_connect: Callable,
        on_close: Callable,
        on_error: Callable,
    ) -> Any:
        """
        Create and return the broker's native WebSocket/streaming object.

        The returned object will be passed back to ws_connect(), ws_subscribe(),
        ws_unsubscribe(), and ws_disconnect().

        Args:
            on_tick    : callable(raw_tick) — called for each incoming tick.
            on_connect : callable() — called once connection is established.
            on_close   : callable(message) — called when connection closes.
            on_error   : callable(message) — called on connection errors.

        Returns:
            Broker-native WebSocket object, or None if creation fails.
        """

    @abstractmethod
    def ws_connect(self, ws_obj: Any) -> None:
        """
        Start the WebSocket connection.

        May be blocking or non-blocking. For blocking SDKs, WebSocketManager
        wraps this in a daemon thread automatically.
        """

    @abstractmethod
    def ws_subscribe(self, ws_obj: Any, symbols: List[str]) -> None:
        """Subscribe to live tick data for the given symbols."""

    @abstractmethod
    def ws_unsubscribe(self, ws_obj: Any, symbols: List[str]) -> None:
        """Unsubscribe from live tick data for the given symbols."""

    @abstractmethod
    def ws_disconnect(self, ws_obj: Any) -> None:
        """Cleanly close the WebSocket connection."""

    @abstractmethod
    def normalize_tick(self, raw_tick: Any) -> Optional[Dict[str, Any]]:
        """
        Normalize a broker-specific tick into a unified dict.

        Returns a dict with at minimum:
            {
                "symbol"    : str,   # app-generic NSE:SYMBOL format
                "ltp"       : float, # last traded price
                "timestamp" : str,   # ISO-8601 or epoch string
            }
        Returns None if the tick cannot be parsed (e.g. heartbeat frames).
        """

    # =========================================================================
    # Symbol helpers  (concrete, delegates to OptionUtils — override as needed)
    # =========================================================================

    # =========================================================================
    # Option symbol construction  (BROKER-SPECIFIC — must override)
    # =========================================================================

    def build_option_symbol(
        self,
        underlying: str,
        spot_price: float,
        option_type: str,
        weeks_offset: int = 0,
        lookback_strikes: int = 0,
    ) -> Optional[str]:
        """
        Build a complete, broker-ready option symbol string for this broker.

        WHY THIS IS HERE
        ----------------
        Every broker API expects a different symbol format for options:

            Broker      Format
            ──────────  ──────────────────────────────────────────────────
            Fyers       "NSE:NIFTY2531825000CE"
            Zerodha     "NFO:NIFTY2531825000CE"
            Shoonya     "NFO|NIFTY2531825000CE"
            FlatTrade   "NFO|NIFTY2531825000CE"
            AliceBlue   "NIFTY2531825000CE" (bare, via instrument object)
            AngelOne    "NIFTY2531825000CE" (bare, token looked up separately)
            Dhan        numeric security_id  (instrument master lookup)
            Upstox      "NSE_FO|<ISIN>"     (instrument_key lookup)

        The previous approach — building symbols in OptionUtils and then
        translating them — only worked for Fyers (prefix-based).  Every other
        broker either silently received a wrong string or needed workarounds.

        PARAMETERS
        ----------
        underlying      : Derivative name ("NIFTY", "BANKNIFTY", "SENSEX", …).
        spot_price      : Current index price (used to calculate ATM strike).
        option_type     : "CE" or "PE".
        weeks_offset    : Expiry offset (0 = nearest, 1 = next, …).
                          For monthly-only indices interpreted as month offset.
        lookback_strikes: Strikes to move away from ATM (signed int).
                          CE: positive = lower strike (deeper ITM).
                          PE: positive = higher strike (deeper ITM).

        RETURNS
        -------
        A broker-specific symbol string, or ``None`` on failure.
        Each concrete subclass MUST override this method.

        DEFAULT IMPLEMENTATION
        ----------------------
        The base class returns the NSE compact core string (no prefix) as a
        safe fallback so legacy brokers that have not yet been migrated still
        return *something* sensible.  Subclasses should always override.
        """
        try:
            from Utils.OptionSymbolBuilder import OptionSymbolBuilder
            params = OptionSymbolBuilder.get_option_params(
                underlying=underlying,
                spot_price=spot_price,
                option_type=option_type,
                weeks_offset=weeks_offset,
                lookback_strikes=lookback_strikes,
            )
            if params is None:
                return None
            logger.debug(
                f"[BaseBroker.build_option_symbol] fallback core: {params.compact_core}"
            )
            return params.compact_core   # bare core — subclass should override
        except Exception as e:
            logger.error(f"[BaseBroker.build_option_symbol] {e}", exc_info=True)
            return None

    def build_option_chain(
        self,
        underlying: str,
        spot_price: float,
        option_type: str,
        weeks_offset: int = 0,
        itm: int = 5,
        otm: int = 5,
    ) -> List[str]:
        """
        Build a list of broker-ready option symbol strings for an option chain.

        Calls ``build_option_symbol()`` for every strike from ITM to OTM.
        Each broker subclass's ``build_option_symbol()`` implementation is
        used automatically — no broker-specific logic here.

        Returns a list of valid symbol strings (None entries are dropped).
        """
        try:
            from Utils.OptionSymbolBuilder import OptionSymbolBuilder
            all_params = OptionSymbolBuilder.get_all_option_params(
                underlying=underlying,
                spot_price=spot_price,
                option_type=option_type,
                weeks_offset=weeks_offset,
                itm=itm,
                otm=otm,
            )
            result = []
            for p in all_params:
                sym = self._params_to_symbol(p)
                if sym:
                    result.append(sym)
            return result
        except Exception as e:
            logger.error(f"[BaseBroker.build_option_chain] {e}", exc_info=True)
            return []

    def _params_to_symbol(self, params) -> Optional[str]:
        """
        Convert an ``OptionParams`` object to a broker-ready symbol string.

        Subclasses override ``build_option_symbol()`` for the user-facing API.
        Internally ``build_option_chain()`` calls this to avoid recomputing
        expiry dates for every strike in the chain.

        The default implementation returns the compact core.
        Override in each broker to apply the broker-specific prefix/format.
        """
        try:
            return params.compact_core if params else None
        except Exception as e:
            logger.error(f"[BaseBroker._params_to_symbol] {e}", exc_info=True)
            return None

    def _format_symbol(self, symbol: str) -> Optional[str]:
        """
        Format any symbol — index or option/futures — for this broker's API.

        Delegates to ``OptionUtils.get_symbol_for_broker()`` which auto-detects
        whether the input is an index name (returns the full broker-specific index
        string, e.g. ``"NSE:NIFTY50-INDEX"`` for Fyers) or an option/futures core
        symbol (prepends the broker's exchange prefix, e.g. ``"NSE:NIFTY25021CE"``).

        This replaces both the old ``_format_symbol`` (option prefix) and the
        separate ``_get_index_symbol`` method — one call handles all symbol types.
        Subclasses that need custom formatting (e.g. Zerodha's token lookup) should
        still override this method; the default is correct for prefix-based brokers.

        Args:
            symbol: Raw symbol string in any recognised format — index alias,
                    canonical name, or formed option/futures symbol.

        Returns:
            Broker-ready symbol string, or ``None`` if symbol is falsy.
        """
        if not symbol:
            return None
        try:
            from Utils.OptionUtils import OptionUtils
            return OptionUtils.get_symbol_for_broker(symbol, self.broker_type)
        except Exception as e:
            logger.debug(f"[BaseBroker._format_symbol] OptionUtils unavailable: {e}")
            return symbol

    def _split_symbol(self, symbol: str):
        """
        Split a broker-prefixed symbol into (exchange, trading_symbol).

        Handles common separator styles:
            "NSE:NIFTY50"   → ("NSE", "NIFTY50")
            "NFO|BANKNIFTY" → ("NFO", "BANKNIFTY")
            "NIFTY50"       → ("NSE", "NIFTY50")   # defaults to NSE

        Args:
            symbol: Symbol string, optionally with exchange prefix.

        Returns:
            Tuple (exchange: str, trading_symbol: str).
        """
        if not symbol:
            return "NSE", symbol or ""
        for sep in (":", "|"):
            if sep in symbol:
                parts = symbol.split(sep, 1)
                return parts[0].upper(), parts[1]
        return "NSE", symbol

    def _to_interval(self, interval: str) -> str:
        """
        Translate the app's canonical interval string to the broker's native
        interval format using OptionUtils.translate_interval().

        Args:
            interval: Canonical interval string (e.g. "1", "5", "15", "D").

        Returns:
            Broker-native interval string, or interval unchanged on error.
        """
        try:
            from Utils.OptionUtils import OptionUtils
            return OptionUtils.translate_interval(interval, self.broker_type)
        except Exception as e:
            logger.debug(f"[BaseBroker._to_interval] OptionUtils unavailable: {e}")
            return str(interval)

    # =========================================================================
    # Rate-limit helpers  (concrete, subclasses can override or call super)
    # =========================================================================

    def _check_rate_limit(self) -> None:
        """
        Thread-safe token-bucket rate limiter.

        Sleeps if requests-per-second would exceed MAX_REQUESTS_PER_SECOND.
        All counter reads and writes are protected by _rate_lock to prevent
        race conditions when multiple threads (e.g. history + order threads)
        share the same broker instance.
        """
        try:
            with self._rate_lock:
                current_time = time.time()
                time_diff = current_time - self._last_request_time
                if time_diff < 1.0:
                    self._request_count += 1
                    if self._request_count > self.MAX_REQUESTS_PER_SECOND:
                        sleep_time = 1.0 - time_diff + 0.1
                        self._rate_lock.release()
                        try:
                            time.sleep(sleep_time)
                        finally:
                            self._rate_lock.acquire()
                        self._request_count = 0
                        self._last_request_time = time.time()
                else:
                    self._request_count = 1
                    self._last_request_time = current_time
        except Exception as e:
            logger.error(f"[BaseBroker._check_rate_limit] {e}", exc_info=True)

    def retry_on_failure(
        self,
        func: Callable,
        context: str = "",
        max_retries: int = 3,
        base_delay: float = 1.0,
        respect_market_hours: bool = True,
    ) -> Any:
        """
        Generic retry wrapper with exponential back-off + jitter.
        Enhanced to respect market hours and avoid unnecessary retries.

        FIXED: TokenExpiredError is always propagated, never swallowed.

        Args:
            func        : Zero-argument callable to retry.
            context     : Label used in log messages.
            max_retries : Maximum number of attempts.
            base_delay  : Base sleep time in seconds (doubles each retry).
            respect_market_hours: If True, don't retry when market is closed.

        Returns:
            The return value of func(), or None on exhausted retries.
        """
        from requests.exceptions import Timeout, ConnectionError as ReqConnError

        # Skip retries if market is closed and we should respect market hours
        if respect_market_hours and not self.is_market_open():
            logger.info(f"[{context or self.broker_type}] Market closed - skipping retry")
            return None

        for attempt in range(max_retries):
            try:
                # Check token before each attempt
                self._check_token_before_request()

                # Check market status before each attempt
                if respect_market_hours and not self.is_market_open():
                    logger.info(f"[{context or self.broker_type}] Market closed during retry {attempt + 1}")
                    return None

                self._check_rate_limit()
                return func()

            except TokenExpiredError:
                # ALWAYS re-raise - never swallow token expiry
                logger.critical(f"[{context or self.broker_type}] Token expired, propagating")
                raise

            except (Timeout, ReqConnError) as e:
                # Only retry network errors during market hours
                if respect_market_hours and not self.is_market_open():
                    logger.info(f"[{context or self.broker_type}] Market closed - stopping retry")
                    return None

                delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning(
                    f"[{context or self.broker_type}] Network error (attempt {attempt + 1}): "
                    f"{e!r}. Retry in {delay:.1f}s"
                )
                time.sleep(delay)

            except Exception as e:
                logger.error(
                    f"[{context or self.broker_type}] Unexpected error: {e!r}",
                    exc_info=True,
                )
                return None

        logger.critical(f"[{context or self.broker_type}] Max retries ({max_retries}) reached.")
        return None

    # =========================================================================
    # Balance / P&L helpers  (uses TradeStateManager — concrete)
    # =========================================================================

    def get_available_balance(self, capital_reserve: float = 0.0) -> float:
        """
        Return usable balance from the broker after deducting the capital
        reserve percentage.

        This is a convenience wrapper around get_balance() that enforces the
        reserve deduction in a uniform way across all broker subclasses.

        Args:
            capital_reserve: Percentage of balance to hold back (0–100).

        Returns:
            Usable balance as float.
        """
        try:
            raw_balance = self.get_balance(capital_reserve=0.0)
            return self.get_balance_after_reserve(raw_balance, capital_reserve)
        except Exception as e:
            logger.error(f"[BaseBroker.get_available_balance] {e}", exc_info=True)
            return 0.0

    @staticmethod
    def get_balance_after_reserve(balance: float, reserve_pct: float = 0.0) -> float:
        """
        Deduct a reserve percentage from a balance and return usable capital.

        Args:
            balance     : Raw account balance.
            reserve_pct : Percentage to hold back as reserve (0–100).

        Returns:
            balance * (1 - reserve_pct / 100), rounded to 2 dp.
        """
        try:
            if balance is None or balance <= 0:
                return 0.0
            if reserve_pct is None or reserve_pct <= 0:
                return round(balance, 2)
            reserve_pct = min(reserve_pct, 100.0)
            return round(balance * (1.0 - reserve_pct / 100.0), 2)
        except Exception as e:
            logger.error(f"[BaseBroker.get_balance_after_reserve] {e}", exc_info=True)
            return 0.0

    def get_current_pnl_from_state(self) -> float:
        """
        Return the current unrealised P&L as tracked by TradeStateManager.

        Reads `pnl`, `current_pnl`, or `unrealized_pnl` from the trade state
        snapshot (whichever is present).  Returns 0.0 if the state manager is
        unavailable or no position is open.

        This allows order executors and risk managers to know the live P&L
        without coupling to broker-specific position APIs.

        Returns:
            Current P&L float (positive = profit, negative = loss).
        """
        try:
            from data.trade_state_manager import state_manager
            snapshot = state_manager.get_position_snapshot()
            # Try common P&L field names in order of preference
            for key in ("pnl", "current_pnl", "unrealized_pnl", "live_pnl"):
                value = snapshot.get(key)
                if value is not None:
                    return float(value)
            return 0.0
        except ImportError:
            logger.debug("[BaseBroker.get_current_pnl_from_state] TradeStateManager not available")
            return 0.0
        except Exception as e:
            logger.error(f"[BaseBroker.get_current_pnl_from_state] {e}", exc_info=True)
            return 0.0

    def get_net_balance(self, capital_reserve: float = 0.0) -> float:
        """
        Return net available capital = broker balance + open P&L - reserve.

        Combines get_available_balance() and get_current_pnl_from_state() so
        callers always work with the most accurate picture of capital available
        for new positions.

        Args:
            capital_reserve: Percentage of broker balance to hold back (0–100).

        Returns:
            Net balance float.
        """
        try:
            available = self.get_available_balance(capital_reserve)
            unrealized_pnl = self.get_current_pnl_from_state()
            net = available + unrealized_pnl
            logger.debug(
                f"[BaseBroker.get_net_balance] available={available:.2f}, "
                f"pnl={unrealized_pnl:.2f}, net={net:.2f}"
            )
            return round(net, 2)
        except Exception as e:
            logger.error(f"[BaseBroker.get_net_balance] {e}", exc_info=True)
            return 0.0

    def get_trade_state_value(self, key: str, default: Any = None) -> Any:
        """
        Read any single value from the TradeStateManager snapshot by key.

        Useful for strategy logic that needs e.g. `entry_price`, `lot_size`,
        `max_loss_limit` from the central state without importing the manager.

        Args:
            key     : Attribute name in the TradeState snapshot.
            default : Value to return if key is absent or state unavailable.

        Returns:
            Value from state, or default.
        """
        try:
            from data.trade_state_manager import state_manager
            return state_manager.get_value(key, default)
        except ImportError:
            return default
        except Exception as e:
            logger.error(f"[BaseBroker.get_trade_state_value] {e}", exc_info=True)
            return default

    def update_trade_state(self, key: str, value: Any) -> bool:
        """
        Write a single value to the TradeStateManager.

        Args:
            key   : Attribute name to set on TradeState.
            value : Value to assign.

        Returns:
            True on success, False otherwise.
        """
        try:
            from data.trade_state_manager import state_manager
            return state_manager.set_value(key, value)
        except ImportError:
            return False
        except Exception as e:
            logger.error(f"[BaseBroker.update_trade_state] {e}", exc_info=True)
            return False

    # =========================================================================
    # Trading calculation helpers  (concrete, broker-agnostic)
    # =========================================================================

    @staticmethod
    def round_to_nse_price(price: float) -> Optional[float]:
        """
        Round price to nearest 0.05 tick as per NSE tick-size rules.

        Args:
            price: Raw price float.

        Returns:
            Price rounded to nearest 0.05, or None if price is invalid.
        """
        try:
            if price is None or not isinstance(price, (int, float)):
                logger.error(f"[BaseBroker.round_to_nse_price] Invalid price: {price}")
                return None
            return math.ceil(round(price, 2) * 20) / 20
        except Exception as e:
            logger.error(f"[BaseBroker.round_to_nse_price] {e}", exc_info=True)
            return None

    @staticmethod
    def calculate_shares_to_buy(
        balance: float,
        price: float,
        lot_size: int = 75,
    ) -> int:
        """
        Calculate the number of shares to buy in whole lot multiples.

        Args:
            balance  : Available capital.
            price    : Current price per share.
            lot_size : Number of shares per lot.

        Returns:
            Total shares to buy (multiple of lot_size), or 0 if not feasible.
        """
        try:
            if not all(isinstance(v, (int, float)) and v > 0 for v in (balance, price, lot_size)):
                logger.warning(
                    f"[BaseBroker.calculate_shares_to_buy] Invalid inputs: "
                    f"balance={balance}, price={price}, lot_size={lot_size}"
                )
                return 0
            lot_cost = price * lot_size
            lots = int(balance // lot_cost)
            total_shares = lots * lot_size
            logger.debug(
                f"[BaseBroker.calculate_shares_to_buy] "
                f"balance={balance}, price={price}, lot_size={lot_size} → {total_shares}"
            )
            return total_shares
        except Exception as e:
            logger.error(f"[BaseBroker.calculate_shares_to_buy] {e}", exc_info=True)
            return 0

    @staticmethod
    def percentage_above_or_below(
        price: float,
        percentage: float = 1.0,
        side: str = "positive",
    ) -> float:
        """
        Return a price adjusted by a percentage, rounded to NSE tick.

        Args:
            price      : Base price.
            percentage : Percentage to adjust (e.g. 2 for 2%).
            side       : "positive" for above, "negative" for below.

        Returns:
            Adjusted price rounded to NSE tick.
        """
        try:
            if price is None or not isinstance(price, (int, float)):
                return price or 0.0
            if side == "positive":
                adjusted = price * (1 + percentage / 100)
            elif side == "negative":
                adjusted = price * (1 - percentage / 100)
            else:
                adjusted = price
            rounded = BaseBroker.round_to_nse_price(adjusted)
            return rounded if rounded is not None else adjusted
        except Exception as e:
            logger.error(f"[BaseBroker.percentage_above_or_below] {e}", exc_info=True)
            return price

    # =========================================================================
    # Market-hours helpers  (concrete, delegates to Utils/common)
    # =========================================================================

    @staticmethod
    def is_market_open() -> bool:
        """Return True if the market is currently open."""
        try:
            from Utils.Utils import Utils
            return Utils.is_market_open()
        except Exception:
            try:
                from Utils.common import is_market_closed_for_the_day
                return not is_market_closed_for_the_day()
            except Exception as e:
                logger.error(f"[BaseBroker.is_market_open] {e}", exc_info=True)
                return False

    @staticmethod
    def is_market_closed_for_the_day() -> bool:
        """Return True if the market has closed for today."""
        try:
            from Utils.common import is_market_closed_for_the_day
            return is_market_closed_for_the_day()
        except Exception as e:
            logger.error(f"[BaseBroker.is_market_closed_for_the_day] {e}", exc_info=True)
            return True

    @staticmethod
    def is_near_market_close(buffer_minutes: int = 10) -> bool:
        """Return True if within `buffer_minutes` of market close (3:30 PM)."""
        try:
            from Utils.Utils import Utils
            return Utils.is_near_market_close(buffer_minutes)
        except Exception as e:
            logger.error(f"[BaseBroker.is_near_market_close] {e}", exc_info=True)
            return False

    @staticmethod
    def get_market_start_time(dt_obj: Optional[datetime] = None) -> datetime:
        """Return today's market open time (9:15 AM)."""
        try:
            from Utils.common import get_time_of_day
            dt_obj = dt_obj or ist_now()
            return get_time_of_day(9, 15, 0, dt_obj)
        except Exception as e:
            logger.error(f"[BaseBroker.get_market_start_time] {e}", exc_info=True)
            return ist_now()

    @staticmethod
    def get_market_end_time(dt_obj: Optional[datetime] = None) -> datetime:
        """Return today's market close time (3:30 PM)."""
        try:
            from Utils.common import get_market_end_time
            return get_market_end_time(dt_obj)
        except Exception as e:
            logger.error(f"[BaseBroker.get_market_end_time] {e}", exc_info=True)
            return ist_now()

    # =========================================================================
    # Shared P&L utility  (class-level, broker-agnostic)
    # =========================================================================

    @staticmethod
    def calculate_pnl(
        current_price: float,
        buy_price: Optional[float] = None,
        options: Optional[int] = None,
    ) -> Optional[float]:
        """
        Calculate P&L for an open position.

        Returns float (not int) to preserve fractional rupee precision across
        all lot sizes (50, 75, 100, 25, …).

        Args:
            current_price : Current market price.
            buy_price     : Entry price.
            options       : Total quantity (shares / contracts).

        Returns:
            Rounded P&L float, or None if any input is invalid.
        """
        try:
            if buy_price is None or options is None or current_price is None:
                return None
            return round((current_price - buy_price) * options, 2)
        except Exception as e:
            logger.error(f"[BaseBroker.calculate_pnl] {e}", exc_info=True)
            return None

    # =========================================================================
    # Dunder
    # =========================================================================

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"