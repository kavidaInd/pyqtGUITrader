"""
brokers/FyersBroker.py
======================
Fyers (fyers_apiv3) implementation of BaseBroker with full broker-aware
symbol translation and timezone handling.

FIXED: Added proper token expiry tracking and propagation to central handler.
"""

import logging
import random
import time
import threading
from datetime import datetime, date, timedelta
from typing import Optional, Any, Callable, List, Dict

import pandas as pd
from dateutil.relativedelta import relativedelta
from requests.exceptions import Timeout, ConnectionError
import pytz

from Utils.OptionUtils import OptionUtils
from Utils.safe_getattr import safe_getattr, safe_hasattr
from broker.BaseBroker import BaseBroker, TokenExpiredError
from broker.TokenExpiryHandler import token_expiry_handler
from db.connector import get_db
from db.crud import tokens
from gui.brokerage_settings.BrokerageSetting import BrokerageSetting

try:
    from fyers_apiv3 import fyersModel
    from fyers_apiv3.FyersWebsocket import data_ws
    FYERS_AVAILABLE = True
except ImportError:
    FYERS_AVAILABLE = False
    data_ws = None

logger = logging.getLogger(__name__)

# Timezone constants
IST = pytz.timezone('Asia/Kolkata')


class FyersBroker(BaseBroker):
    """
    Fyers broker implementation with broker-aware symbol translation.
    FIXED: Added proper token expiry tracking and propagation.
    """

    # Constants
    OK = "ok"
    SIDE_BUY = 1
    SIDE_SELL = -1
    LIMIT_ORDER_TYPE = 1      # Limit order
    MARKET_ORDER_TYPE = 2      # Market order
    STOPLOSS_MARKET_ORDER_TYPE = 4  # Stop loss market order
    PRODUCT_TYPE_MARGIN = "MARGIN"  # Intraday
    PRODUCT_TYPE_CNC = "CNC"   # Delivery
    MAX_REQUESTS_PER_SECOND = 3

    # Token expiry codes from Fyers API
    TOKEN_EXPIRY_CODES = {-8, -15, -16, -17, -100, -101, -102}
    RETRYABLE_CODES = {-429, 500, 502, 503, 504}
    RATE_LIMIT_CODES = {-429, 429}

    def __init__(self, state, broker_setting: BrokerageSetting = None):
        self._safe_defaults_init()
        try:
            if not FYERS_AVAILABLE:
                raise ImportError("fyers_apiv3 is not installed. Run: pip install fyers_apiv3")

            self.state = state

            if broker_setting is None:
                raise ValueError("BrokerageSetting must be provided.")

            self.client_id = safe_getattr(broker_setting, 'client_id', None)
            self.secret_key = safe_getattr(broker_setting, 'secret_key', None)
            self.redirect_uri = safe_getattr(broker_setting, 'redirect_uri', None)

            # Load token and check expiry
            self.state.token = self._load_token_from_db()
            self._token_expiry = self._parse_token_expiry()
            self._token_issued_at = self._parse_token_issued_at()

            if not self.state.token:
                logger.warning("Fyers access token is empty or None")
            elif self.is_token_expired:
                logger.warning("Fyers token is expired at load time")

            try:
                self.fyers = fyersModel.FyersModel(
                    client_id=self.client_id,
                    token=self.state.token,
                    log_path='logs'
                )
                logger.info("FyersBroker initialized successfully")
            except Exception as e:
                logger.critical(f"Failed initializing FyersModel: {e!r}", exc_info=True)
                self.fyers = None

            # Token expiry tracking
            self._token_expiry_check_interval = 60  # seconds
            self._last_token_check = 0

            # WebSocket cleanup tracking
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()
            self._ws_socket = None

            # Register with token expiry handler
            self._token_handler = token_expiry_handler

        except Exception as e:
            logger.critical(f"[FyersBroker.__init__] Failed: {e}", exc_info=True)
            raise

    @property
    def broker_type(self) -> str:
        return "fyers"

    @property
    def token_expiry(self) -> Optional[datetime]:
        """Return token expiry datetime if available."""
        return self._token_expiry

    @property
    def token_issued_at(self) -> Optional[datetime]:
        """Return token issue datetime if available."""
        return self._token_issued_at

    def _safe_defaults_init(self):
        self.state = None
        self.client_id = None
        self.secret_key = None
        self.redirect_uri = None
        self.fyers = None
        self._last_request_time = 0
        self._request_count = 0
        self._retry_count = 0
        self._token_expiry = None
        self._token_issued_at = None
        self._last_token_check = 0

        # WebSocket cleanup tracking
        self._ws_closed = False
        self._ws_cleanup_event = None
        self._ws_socket = None
        self._ws_on_tick = None
        self._ws_on_connect = None
        self._ws_on_close = None
        self._ws_on_error = None

    # ── Token management ──────────────────────────────────────────────────────

    def _load_token_from_db(self) -> Optional[str]:
        try:
            db = get_db()
            token_data = tokens.get(db)
            if token_data and token_data.get("access_token"):
                return token_data["access_token"]
            return None
        except Exception as e:
            logger.error(f"Error loading Fyers token from DB: {e}", exc_info=True)
            return None

    def _parse_token_expiry(self) -> Optional[datetime]:
        """Parse token expiry from token data."""
        try:
            db = get_db()
            token_data = tokens.get(db)

            if token_data and token_data.get("expires_at"):
                expiry_str = token_data["expires_at"]

                for fmt in [
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f"
                ]:
                    try:
                        dt = datetime.strptime(expiry_str, fmt)

                        # attach timezone correctly
                        if dt.tzinfo is None:
                            dt = IST.localize(dt)

                        return dt

                    except ValueError:
                        continue

                logger.warning(f"Could not parse token expiry: {expiry_str}")

            return None

        except Exception as e:
            logger.error(f"Error parsing token expiry: {e}", exc_info=True)
            return None

    def _parse_token_issued_at(self) -> Optional[datetime]:
        """Parse token issue time from token data."""
        try:
            db = get_db()
            token_data = tokens.get(db)

            if token_data and token_data.get("issued_at"):
                issued_str = token_data["issued_at"]

                for fmt in [
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f"
                ]:
                    try:
                        dt = datetime.strptime(issued_str, fmt)

                        if dt.tzinfo is None:
                            dt = IST.localize(dt)

                        return dt

                    except ValueError:
                        continue

            return None

        except Exception as e:
            logger.error(f"Error parsing token issued at: {e}", exc_info=True)
            return None

    def _check_token_before_request(self) -> None:
        """
        Check token validity before making any API request.
        Overrides BaseBroker._check_token_before_request with Fyers-specific checks.
        """
        now = time.time()
        if now - self._last_token_check > self._token_expiry_check_interval:
            self._last_token_check = now
            if self.is_token_expired:
                self._handle_token_expired(
                    f"Token expired at {self._token_expiry}",
                    recovery_callback=self._on_token_recovered
                )

    def _on_token_recovered(self) -> None:
        """
        Callback executed after token has been successfully refreshed.
        """
        logger.info("[FyersBroker] Token recovered, reloading from DB")
        # Reload token from DB
        self.state.token = self._load_token_from_db()
        self._token_expiry = self._parse_token_expiry()

        # Re-initialize fyers client with new token
        if self.state.token:
            try:
                self.fyers = fyersModel.FyersModel(
                    client_id=self.client_id,
                    token=self.state.token,
                    log_path='logs'
                )
                logger.info("[FyersBroker] Fyers client re-initialized with new token")
            except Exception as e:
                logger.error(f"[FyersBroker] Failed to re-initialize fyers client: {e}", exc_info=True)

    # ── Rate limiting ─────────────────────────────────────────────────────────

    def _check_rate_limit(self):
        try:
            current_time = time.time()
            time_diff = current_time - self._last_request_time
            if time_diff < 1.0:
                self._request_count += 1
                if self._request_count > self.MAX_REQUESTS_PER_SECOND:
                    sleep_time = 1.0 - time_diff + 0.1
                    time.sleep(sleep_time)
                    self._request_count = 0
                    self._last_request_time = time.time()
            else:
                self._request_count = 1
                self._last_request_time = current_time
        except Exception as e:
            logger.error(f"[_check_rate_limit] {e}", exc_info=True)

    # ── Symbol formatting ────────────────────────────────────────────────────

    def build_option_symbol(
        self,
        underlying: str,
        spot_price: float,
        option_type: str,
        weeks_offset: int = 0,
        lookback_strikes: int = 0,
    ) -> Optional[str]:
        """
        Fyers option symbol format: ``NSE:NIFTY2531825000CE``
        (or ``NSE:NIFTY25MAR25000CE`` for monthly expiry contracts).

        Fyers requires the ``NSE:`` prefix for all NFO instruments.
        SENSEX uses ``BSE:`` prefix.
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
            return self._params_to_symbol(params)
        except Exception as e:
            logger.error(f"[FyersBroker.build_option_symbol] {e}", exc_info=True)
            return None

    def _params_to_symbol(self, params) -> Optional[str]:
        """Fyers: ``NSE:`` prefix for NSE indices, ``BSE:`` for SENSEX."""
        if not params:
            return None
        prefix = "BSE:" if params.underlying == "SENSEX" else "NSE:"
        return f"{prefix}{params.compact_core}"

    def build_option_chain(
        self,
        underlying: str,
        spot_price: float,
        option_type: str,
        weeks_offset: int = 0,
        itm: int = 5,
        otm: int = 5,
    ) -> List[str]:
        """Build a Fyers option chain with NSE:/BSE: prefixes."""
        try:
            from Utils.OptionSymbolBuilder import OptionSymbolBuilder
            all_params = OptionSymbolBuilder.get_all_option_params(
                underlying=underlying, spot_price=spot_price,
                option_type=option_type, weeks_offset=weeks_offset,
                itm=itm, otm=otm,
            )
            return [s for s in (self._params_to_symbol(p) for p in all_params) if s]
        except Exception as e:
            logger.error(f"[FyersBroker.build_option_chain] {e}", exc_info=True)
            return []

    def _format_symbol(self, symbol: str) -> Optional[str]:
        """Format any symbol for the Fyers API."""
        return super()._format_symbol(symbol)

    @staticmethod
    def _get_error_code(response: Any) -> int:
        if isinstance(response, dict):
            try:
                code = response.get("code", 0)
                # Check for token expiry codes
                if str(code) in ["-8", "-15", "-16", "-17", "-100", "-101", "-102"]:
                    raise TokenExpiredError(f"Fyers auth error: {code}")
                return int(code)
            except (ValueError, TypeError):
                return 0
        return 0

    # ── BaseBroker implementation ─────────────────────────────────────────────

    def get_profile(self) -> Optional[Dict]:
        self._check_token_before_request()
        try:
            if not self.fyers:
                return None
            return self.retry_on_failure(lambda: self.fyers.get_profile(), context="get_profile")
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_profile] {e!r}", exc_info=True)
            return None

    def get_balance(self, capital_reserve: float = 0.0) -> float:
        self._check_token_before_request()
        try:
            if not self.fyers:
                return 0.0
            funds = self.retry_on_failure(lambda: self.fyers.funds(), context="get_balance")
            if funds and funds.get("s") == self.OK:
                bal_data = pd.json_normalize(funds["fund_limit"])
                if not bal_data.empty and "id" in bal_data.columns:
                    equity_row = bal_data[bal_data["id"] == 10]
                    if not equity_row.empty:
                        account_balance = equity_row["equityAmount"].iloc[0]
                        account_balance = account_balance - capital_reserve
                        return account_balance
            return 0.0
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_balance] {e!r}", exc_info=True)
            return 0.0

    def get_history(self, symbol: str, interval: str = "2", length: int = 400):
        self._check_token_before_request()
        try:
            if not symbol or not self.fyers:
                return None

            # Translate symbol and interval using OptionUtils
            broker_symbol = OptionUtils.get_index_symbol_for_broker(symbol, "fyers")
            broker_interval = OptionUtils.translate_interval(interval, "fyers")

            today = datetime.today().strftime("%Y-%m-%d")
            from_date = (datetime.today() - relativedelta(
                days=6 if date.today().weekday() == 6 else 4
            )).strftime("%Y-%m-%d")

            params = {
                "symbol": broker_symbol,
                "resolution": broker_interval,
                "date_format": "1",
                "range_from": from_date,
                "range_to": today,
                "cont_flag": "1"
            }
            self._check_rate_limit()
            response = self.retry_on_failure(lambda: self.fyers.history(params), context="get_history")

            if response and response.get("s") == self.OK and "candles" in response:
                df = pd.DataFrame(response['candles'], columns=["time", "open", "high", "low", "close", "volume"])
                # Convert timestamp (Fyers returns epoch seconds in UTC)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                # Convert to IST
                if df['time'].dt.tz is None:
                    df['time'] = df['time'].dt.tz_localize('UTC').dt.tz_convert(IST)
                else:
                    df['time'] = df['time'].dt.tz_convert(IST)
                return df.tail(length)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_history] {e!r}", exc_info=True)
            return None

    def get_history_for_timeframe(self, symbol: str, interval: str, days: int = 30):
        self._check_token_before_request()
        try:
            if not symbol or not self.fyers:
                return None

            broker_symbol = OptionUtils.get_index_symbol_for_broker(symbol, "fyers")
            broker_interval = OptionUtils.translate_interval(interval, "fyers")

            today = datetime.now(IST)
            fetch_days = max(days, 60) if interval in ["15", "30", "60"] else (
                max(days, 120) if interval in ["120", "240"] else days
            )
            from_date = (today - timedelta(days=fetch_days)).strftime("%Y-%m-%d")

            params = {
                "symbol": broker_symbol,
                "resolution": broker_interval,
                "date_format": "1",
                "range_from": from_date,
                "range_to": today.strftime("%Y-%m-%d"),
                "cont_flag": "1"
            }
            self._check_rate_limit()
            response = self.retry_on_failure(lambda: self.fyers.history(params), context="get_history_for_timeframe")

            if response and response.get("s") == self.OK and "candles" in response:
                df = pd.DataFrame(response['candles'], columns=["time", "open", "high", "low", "close", "volume"])
                df['time'] = pd.to_datetime(df['time'], unit='s')
                if df['time'].dt.tz is None:
                    df['time'] = df['time'].dt.tz_localize('UTC').dt.tz_convert(IST)
                else:
                    df['time'] = df['time'].dt.tz_convert(IST)
                return df
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_history_for_timeframe] {e!r}", exc_info=True)
            return None

    def get_option_current_price(self, option_name: str) -> Optional[float]:
        self._check_token_before_request()
        try:
            if not option_name or not self.fyers:
                return None
            formatted = self._format_symbol(option_name)
            self._check_rate_limit()
            response = self.retry_on_failure(
                lambda: self.fyers.quotes({"symbols": formatted}),
                context="option_current_price"
            )
            if response and response.get("s") == self.OK and response.get("d"):
                return response["d"][0]["v"].get("lp")
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_option_current_price] {e!r}", exc_info=True)
            return None

    def get_option_quote(self, option_name: str) -> Optional[Dict[str, float]]:
        self._check_token_before_request()
        try:
            if not option_name or not self.fyers:
                return None
            formatted = self._format_symbol(option_name)
            self._check_rate_limit()
            response = self.retry_on_failure(
                lambda: self.fyers.quotes({"symbols": formatted}),
                context="get_option_quote"
            )
            if response and response.get("s") == self.OK and response.get("d"):
                v = response["d"][0]["v"]
                return {
                    "ltp": v.get("lp"),
                    "bid": v.get("bid_price"),
                    "ask": v.get("ask_price"),
                    "high": v.get("high_price"),
                    "low": v.get("low_price"),
                    "open": v.get("open_price"),
                    "close": v.get("prev_close_price"),
                    "volume": v.get("volume"),
                    "oi": v.get("oi"),
                }
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_option_quote] {e!r}", exc_info=True)
            return None

    def get_option_chain_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        self._check_token_before_request()
        try:
            if not symbols or not self.fyers:
                return {}
            formatted = [self._format_symbol(s) for s in symbols if s]
            self._check_rate_limit()
            response = self.retry_on_failure(
                lambda: self.fyers.quotes({"symbols": ','.join(formatted)}),
                context="get_option_chain_quotes"
            )
            result = {}
            if response and response.get("s") == self.OK and response.get("d"):
                for item in response["d"]:
                    sym = (item.get("n") or item.get("symbol", "")).removeprefix("NSE:")
                    v = item.get("v", {})
                    result[sym] = {
                        "ltp": v.get("lp"),
                        "bid": v.get("bid_price"),
                        "ask": v.get("ask_price"),
                        "high": v.get("high_price"),
                        "low": v.get("low_price"),
                        "volume": v.get("volume"),
                        "oi": v.get("oi"),
                    }
            return result
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_option_chain_quotes] {e!r}", exc_info=True)
            return {}

    def place_order(self, **kwargs) -> Optional[str]:
        self._check_token_before_request()
        return self._place_order(**kwargs)

    def modify_order(self, **kwargs) -> bool:
        self._check_token_before_request()
        return self._modify_order_with_id(**kwargs)

    def cancel_order(self, **kwargs) -> bool:
        self._check_token_before_request()
        return self._cancel_order_with_id(**kwargs)

    def exit_position(self, **kwargs) -> bool:
        self._check_token_before_request()
        return self._exit_position_with_symbol(**kwargs)

    def add_stoploss(self, **kwargs) -> bool:
        self._check_token_before_request()
        return self._place_order_with_stoploss(**kwargs)

    def remove_stoploss(self, **kwargs) -> bool:
        self._check_token_before_request()
        return self._cancel_order_with_id(**kwargs)

    def sell_at_current(self, **kwargs) -> bool:
        self._check_token_before_request()
        return self._place_order_with_side(side=self.SIDE_SELL, **kwargs)

    def get_positions(self) -> List[Dict[str, Any]]:
        self._check_token_before_request()
        try:
            if not self.fyers:
                return []
            response = self.retry_on_failure(lambda: self.fyers.positions(), context="get_positions")
            if response and response.get("s") == self.OK:
                return response.get("netPositions", [])
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_positions] {e!r}", exc_info=True)
            return []

    def get_orderbook(self) -> List[Dict[str, Any]]:
        self._check_token_before_request()
        try:
            if not self.fyers:
                return []
            response = self.retry_on_failure(lambda: self.fyers.orderbook(), context="get_orderbook")
            if response and response.get("s") == self.OK:
                return response.get("orderBook", [])
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_orderbook] {e!r}", exc_info=True)
            return []

    def get_current_order_status(self, order_id: str) -> Optional[int]:
        """
        Return a normalised order status integer for *order_id*:
            2  = TRADED / FILLED (fully executed)
           -1  = CANCELLED / REJECTED / EXPIRED
            1  = still open / pending / in-transit

        Fyers v3 API returns **numeric** status codes in the orderBook:
            2  → TRADED
            1  → CANCELLED
            5  → REJECTED
            6  → PENDING
           20  → OPEN
            4  → TRANSIT / AMO_REQ_RECEIVED

        The previous implementation converted the status to a string and
        compared it against text labels ("COMPLETE", "TRADED", …).  Since
        Fyers sends integers, str(2) == "2" which is never equal to "COMPLETE",
        so every live order was permanently reported as "not filled".  This
        caused confirm_trade() to time out after cancel_after seconds and
        cancel the live position.
        """
        self._check_token_before_request()
        try:
            if not order_id or not self.fyers:
                return None

            response = self.retry_on_failure(
                lambda: self.fyers.orderbook({"id": order_id}),
                context="order_status"
            )

            if not response or response.get("s") != self.OK:
                return None

            orders = response.get("orderBook", [])
            for order in orders:
                if str(order.get("id")) == str(order_id):
                    raw_status = order.get("status")

                    # ── Numeric path (Fyers v3 native) ────────────────────────
                    if isinstance(raw_status, int):
                        if raw_status == 2:      # TRADED / fully filled
                            return 2
                        if raw_status in (1, 5):  # CANCELLED (1) or REJECTED (5)
                            return -1
                        # 6=PENDING, 20=OPEN, 4=TRANSIT, anything else = still working
                        return 1

                    # ── String path (normalise for robustness) ─────────────────
                    status_str = str(raw_status or "").upper().strip()
                    if status_str in ("2", "COMPLETE", "COMPLETED", "FILLED", "TRADED"):
                        return 2
                    if status_str in ("1", "5", "REJECTED", "CANCELLED",
                                      "CANCELED", "EXPIRED"):
                        return -1
                    # OPEN, PENDING, TRIGGER_PENDING, TRANSIT, etc.
                    return 1

            logger.debug(
                f"[get_current_order_status] order_id={order_id} not found in orderbook"
            )
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[FyersBroker.get_current_order_status] {e!r}", exc_info=True)
            return None

    def get_fill_price(self, broker_order_id: str) -> Optional[float]:
        self._check_token_before_request()
        try:
            if not broker_order_id or not self.fyers:
                return None

            response = self.retry_on_failure(
                lambda: self.fyers.orderbook({"id": broker_order_id}),
                context="get_fill_price"
            )

            if not response or response.get("s") != self.OK:
                return None

            orders = response.get("orderBook", [])
            for order in orders:
                if str(order.get("id")) == str(broker_order_id):
                    fill_price = order.get("traded_price") or order.get("avg_price")
                    if fill_price:
                        return float(fill_price)
            return None
        except Exception as e:
            logger.error(f"[FyersBroker.get_fill_price] {e!r}", exc_info=True)
            return None

    def is_connected(self) -> bool:
        try:
            if not self.fyers or not self.state or not self.state.token:
                return False
            if self.is_token_expired:
                return False
            return self.get_profile() is not None
        except TokenExpiredError:
            return False
        except Exception:
            return False

    def cleanup(self) -> None:
        """Clean up resources including WebSocket connection."""
        logger.info("[FyersBroker] Starting cleanup")

        # Mark WebSocket as closed to prevent callbacks
        self._ws_closed = True

        # Clean up WebSocket if it exists
        if self._ws_socket is not None:
            try:
                # Try to disconnect with timeout
                self._ws_cleanup_event.clear()

                def _do_disconnect():
                    try:
                        if safe_hasattr(self._ws_socket, "close_connection"):
                            self._ws_socket.close_connection()
                            logger.debug("[FyersBroker] close_connection called")
                        elif safe_hasattr(self._ws_socket, "disconnect"):
                            self._ws_socket.disconnect()
                            logger.debug("[FyersBroker] disconnect called")
                    except Exception as e:
                        logger.warning(f"[FyersBroker] Error closing WebSocket: {e}")
                    finally:
                        self._ws_cleanup_event.set()

                # Run close in separate thread with timeout
                close_thread = threading.Thread(target=_do_disconnect, daemon=True)
                close_thread.start()

                # Wait for close with timeout
                if not self._ws_cleanup_event.wait(timeout=2.0):
                    logger.warning("[FyersBroker] WebSocket close timed out")

            except Exception as e:
                logger.error(f"[FyersBroker] Error during WebSocket cleanup: {e}", exc_info=True)
            finally:
                self._ws_socket = None

        # Close fyers session
        try:
            if self.fyers and safe_hasattr(self.fyers, 'close'):
                self.fyers.close()
        except Exception as e:
            logger.warning(f"[FyersBroker.cleanup] Session close error: {e}")

        # Clear callbacks
        self._ws_on_tick = None
        self._ws_on_connect = None
        self._ws_on_close = None
        self._ws_on_error = None

        logger.info("[FyersBroker] Cleanup completed")

    # ── Internal order helpers ───────────────────────────────────────────────

    def _place_order(self, **kwargs) -> Optional[str]:
        self._check_token_before_request()
        try:
            symbol = kwargs.get('symbol')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_BUY)
            order_type = kwargs.get('order_type', self.LIMIT_ORDER_TYPE)
            product_type = kwargs.get('product_type', self.PRODUCT_TYPE_MARGIN)
            limit_price = kwargs.get('limitPrice', 0)
            stop_price = kwargs.get('stopPrice', 0)

            if not symbol or qty <= 0 or not self.fyers:
                return None

            self._check_rate_limit()
            formatted_symbol = self._format_symbol(symbol)
            data = {
                "symbol": formatted_symbol,
                "qty": qty,
                "type": order_type,
                "side": side,
                "productType": product_type,
                "limitPrice": limit_price,
                "stopPrice": stop_price,
                "validity": "DAY",
                "disclosedQty": 0,
                "filledQty": 0,
                "offlineOrder": False,
            }
            response = self.retry_on_failure(lambda: self.fyers.place_order(data), context="place_order")
            if response and response.get('s') == self.OK:
                return response.get('id')
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[_place_order] {e}", exc_info=True)
            return None

    def _place_order_with_stoploss(self, **kwargs) -> bool:
        self._check_token_before_request()
        symbol = kwargs.get('symbol')
        price = kwargs.get('price')
        qty = kwargs.get('qty', 75)
        side = kwargs.get('side', self.SIDE_SELL)
        if not symbol or not price or price <= 0:
            return False
        order_id = self.retry_on_failure(
            lambda: self._place_order(
                symbol=symbol, qty=qty, side=side,
                order_type=self.STOPLOSS_MARKET_ORDER_TYPE, stopPrice=price
            ),
            context="place_stoploss"
        )
        return bool(order_id)

    def _place_order_with_side(self, side: int, **kwargs) -> bool:
        self._check_token_before_request()
        symbol = kwargs.get('symbol')
        qty = kwargs.get('qty', 75)
        if not symbol or qty <= 0:
            return False
        order_id = self.retry_on_failure(
            lambda: self._place_order(
                symbol=symbol, qty=qty, side=side,
                order_type=self.MARKET_ORDER_TYPE
            ),
            context="place_order_with_side"
        )
        return bool(order_id)

    def _cancel_order_with_id(self, **kwargs) -> bool:
        self._check_token_before_request()
        order_id = kwargs.get('order_id')
        if not order_id or not self.fyers:
            return False
        response = self.retry_on_failure(
            lambda: self.fyers.cancel_order({"id": order_id}),
            context="cancel_order"
        )
        return bool(response and response.get('s') == self.OK)

    def _modify_order_with_id(self, **kwargs) -> bool:
        self._check_token_before_request()
        order_id = kwargs.get('order_id')
        limit_price = kwargs.get('limit_price', 0)
        if not order_id or limit_price <= 0 or not self.fyers:
            return False
        self._check_rate_limit()
        response = self.retry_on_failure(
            lambda: self.fyers.modify_order({"id": order_id, "limitPrice": limit_price}),
            context="modify_order"
        )
        return bool(response and response.get('s') == self.OK)

    def _exit_position_with_symbol(self, **kwargs) -> bool:
        self._check_token_before_request()
        symbol = kwargs.get('symbol')
        position_type = kwargs.get('position_type', self.PRODUCT_TYPE_MARGIN)
        if not symbol or not self.fyers:
            return False
        formatted = self._format_symbol(symbol)
        self._check_rate_limit()
        response = self.retry_on_failure(
            lambda: self.fyers.exit_positions({"id": f"{formatted}-{position_type}"}),
            context="exit_position"
        )
        return bool(response and response.get('s') == self.OK)

    # ── Retry wrapper ────────────────────────────────────────────────────────

    def retry_on_failure(self, func: Callable, context: str = "",
                         max_retries: int = 3, base_delay: int = 1, respect_market_hours: bool = True,):
        for attempt in range(max_retries):
            try:
                self._check_token_before_request()
                self._check_rate_limit()
                response = func()

                if isinstance(response, dict) and response.get('s') == 'ok':
                    return response

                error_code = self._get_error_code(response)

                if error_code in self.TOKEN_EXPIRY_CODES:
                    raise TokenExpiredError(f"Fyers auth error", error_code)

                if error_code in self.RETRYABLE_CODES:
                    delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                    time.sleep(delay)
                    continue

                response_str = str(response) if response else ""
                for pattern in ["-8", "-15", "-16", "Token expired", "Invalid Access Token"]:
                    if pattern in response_str:
                        raise TokenExpiredError(f"Token error: {pattern}")

                if "Market is in closed state" in response_str:
                    return None
                if "No data found" in response_str or "Invalid symbol" in response_str:
                    return None

                return response

            except (Timeout, ConnectionError) as e:
                delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning(f"[{context}] Network error: {e!r}. Retry in {delay:.1f}s")
                time.sleep(delay)
            except TokenExpiredError:
                raise
            except Exception as e:
                logger.error(f"[{context}] Unexpected: {e!r}", exc_info=True)
                return None

        logger.critical(f"[{context}] Max retries reached.")
        return None

    # ── WebSocket interface ───────────────────────────────────────────────────

    def create_websocket(self, on_tick, on_connect, on_close, on_error) -> Any:
        """
        Create Fyers v3 data WebSocket.

        Access token format required by Fyers: "client_id:access_token".
        Symbols use Fyers format: "NSE:NIFTY50-INDEX", "NSE:NIFTY24DECFUT", etc.

        FIXED: Added state tracking and stored callbacks.
        """
        try:
            from fyers_apiv3.FyersWebsocket import data_ws

            token = safe_getattr(self.state, "token", None) if self.state else None
            if not self.client_id or not token:
                logger.error("FyersBroker.create_websocket: missing client_id or token")
                return None

            # Check token expiry before creating websocket
            if self.is_token_expired:
                self._handle_token_expired("Cannot create websocket with expired token")

            # Reset WebSocket state
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()

            access_token = f"{self.client_id}:{token}"

            # Store callbacks
            self._ws_on_tick = on_tick
            self._ws_on_connect = on_connect
            self._ws_on_close = on_close
            self._ws_on_error = on_error

            # Create socket with safety-wrapped callbacks
            def safe_on_connect():
                if self._ws_closed:
                    return
                on_connect()

            def safe_on_close():
                if self._ws_closed:
                    return
                on_close()

            def safe_on_error(msg):
                if self._ws_closed:
                    return
                on_error(msg)

            def safe_on_message(msg):
                if self._ws_closed:
                    return
                on_tick(msg)

            socket = data_ws.FyersDataSocket(
                access_token=access_token,
                log_path="",
                litemode=False,
                write_to_file=False,
                reconnect=False,
                on_connect=safe_on_connect,
                on_close=safe_on_close,
                on_error=safe_on_error,
                on_message=safe_on_message,
            )

            self._ws_socket = socket
            logger.info("FyersBroker: WebSocket object created")
            return socket
        except ImportError:
            logger.error("FyersBroker: fyers_apiv3 not installed — pip install fyers_apiv3")
            return None
        except Exception as e:
            logger.error(f"[FyersBroker.create_websocket] {e}", exc_info=True)
            return None

    def ws_connect(self, ws_obj) -> None:
        """Start Fyers WebSocket (non-blocking — SDK manages its own thread)."""
        try:
            if ws_obj is None or self._ws_closed:
                logger.error("FyersBroker.ws_connect: ws_obj is None or closed")
                return
            ws_obj.connect()
            logger.info("FyersBroker: WebSocket connect() called")
        except Exception as e:
            logger.error(f"[FyersBroker.ws_connect] {e}", exc_info=True)

    def ws_subscribe(self, ws_obj, symbols: List[str]) -> None:
        """
        Subscribe to Fyers SymbolUpdate and OnOrders channels.

        Symbols are automatically formatted using OptionUtils.
        """
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return
            # Format all symbols using OptionUtils
            fyers_syms = [self._format_symbol(s) for s in symbols if s]
            for data_type in ("SymbolUpdate", "OnOrders"):
                try:
                    ws_obj.subscribe(symbols=fyers_syms, data_type=data_type)
                    logger.info(f"FyersBroker: subscribed {len(fyers_syms)} symbols ({data_type})")
                except Exception as e:
                    logger.error(f"FyersBroker.ws_subscribe({data_type}): {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[FyersBroker.ws_subscribe] {e}", exc_info=True)

    def ws_unsubscribe(self, ws_obj, symbols: List[str]) -> None:
        """Unsubscribe from Fyers channels."""
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return
            fyers_syms = [self._format_symbol(s) for s in symbols if s]
            for data_type in ("SymbolUpdate", "OnOrders"):
                try:
                    ws_obj.unsubscribe(symbols=fyers_syms, data_type=data_type)
                except Exception as e:
                    logger.error(f"FyersBroker.ws_unsubscribe({data_type}): {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[FyersBroker.ws_unsubscribe] {e}", exc_info=True)

    def ws_disconnect(self, ws_obj) -> None:
        """
        Close Fyers WebSocket with timeout protection.

        FIXED: Added timeout and better error handling.
        """
        try:
            if ws_obj is None:
                return

            logger.info("[FyersBroker] Starting WebSocket disconnect")
            self._ws_closed = True

            # Run disconnect in separate thread with timeout
            disconnect_complete = threading.Event()

            def _do_disconnect():
                try:
                    if safe_hasattr(ws_obj, "close_connection"):
                        ws_obj.close_connection()
                        logger.debug("[FyersBroker] close_connection completed")
                    elif safe_hasattr(ws_obj, "disconnect"):
                        ws_obj.disconnect()
                        logger.debug("[FyersBroker] disconnect completed")
                except Exception as e:
                    logger.warning(f"[FyersBroker] disconnect error: {e}")
                finally:
                    disconnect_complete.set()

            disconnect_thread = threading.Thread(target=_do_disconnect, daemon=True)
            disconnect_thread.start()

            # Wait for disconnect with timeout
            if not disconnect_complete.wait(timeout=2.0):
                logger.warning("[FyersBroker] disconnect timed out")

            # Clear reference
            if self._ws_socket == ws_obj:
                self._ws_socket = None

            # Call on_close callback
            if self._ws_on_close and not self._ws_closed:
                try:
                    self._ws_on_close("disconnected by user")
                except Exception as e:
                    logger.warning(f"[FyersBroker] Error in close callback: {e}")

            logger.info("[FyersBroker] WebSocket disconnect completed")

        except Exception as e:
            logger.error(f"[FyersBroker.ws_disconnect] {e}", exc_info=True)

    def normalize_tick(self, raw_tick) -> Optional[Dict[str, Any]]:
        """
        Normalize a Fyers tick to the unified format.
        """
        try:
            if self._ws_closed or not isinstance(raw_tick, dict):
                return None

            symbol = raw_tick.get("symbol")
            ltp = raw_tick.get("ltp")
            if symbol is None or ltp is None:
                return None

            # Extract timestamp and make timezone-aware
            timestamp = raw_tick.get("timestamp", "")
            if timestamp:
                try:
                    # Fyers timestamp is in milliseconds since epoch
                    ts_seconds = int(timestamp) / 1000
                    dt = datetime.fromtimestamp(ts_seconds, IST)
                    timestamp_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    timestamp_str = str(timestamp)
            else:
                timestamp_str = ""

            return {
                "symbol": symbol,
                "ltp": float(ltp),
                "timestamp": timestamp_str,
                "bid": raw_tick.get("best_bid_price"),
                "ask": raw_tick.get("best_ask_price"),
                "volume": raw_tick.get("volume"),
                "oi": raw_tick.get("oi"),
                "open": raw_tick.get("open_price"),
                "high": raw_tick.get("high_price"),
                "low": raw_tick.get("low_price"),
                "close": raw_tick.get("prev_close_price"),
            }
        except Exception as e:
            if not self._ws_closed:
                logger.error(f"[FyersBroker.normalize_tick] {e}", exc_info=True)
            return None