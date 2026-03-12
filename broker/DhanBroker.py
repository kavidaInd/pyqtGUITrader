"""
brokers/DhanBroker.py
=====================
Dhan (dhanhq) implementation of BaseBroker.

Prerequisites:
    pip install dhanhq

Authentication:
    Dhan uses a static access_token + client_id (no OAuth flow needed).
    Generate tokens from: https://dhanhq.co/docs/v2/

Symbol format:
    Dhan uses securityId (numeric). This broker maps
    NSE:SYMBOL / NFO:SYMBOL to Dhan security IDs via the
    instrument file from Dhan's CDN.

API docs: https://dhanhq.co/docs/v2/

FIXED: Added proper token expiry tracking and propagation to central handler.
"""

import logging
import time
import random
import threading
from datetime import datetime, timedelta
from Utils.time_utils import IST, ist_now, fmt_display, fmt_stamp
from Utils.common import to_date_str
from typing import Optional, Dict, List, Any, Callable

import pandas as pd
from requests.exceptions import Timeout, ConnectionError

from Utils.safe_getattr import safe_getattr, safe_hasattr
from broker.BaseBroker import BaseBroker, TokenExpiredError
from broker.TokenExpiryHandler import token_expiry_handler
from db.connector import get_db
from db.crud import tokens

try:
    from dhanhq import dhanhq
    DHAN_AVAILABLE = True
except ImportError:
    DHAN_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Dhan product/order/exchange constants ─────────────────────────────────────
# Product types
DHAN_PRODUCT_INTRADAY = "INTRADAY"
DHAN_PRODUCT_MARGIN = "MARGIN"
DHAN_PRODUCT_CNC = "CNC"
DHAN_PRODUCT_CO = "CO"

# Order types
DHAN_ORDER_MARKET = "MARKET"
DHAN_ORDER_LIMIT = "LIMIT"
DHAN_ORDER_SL = "STOP_LOSS"
DHAN_ORDER_SLM = "STOP_LOSS_MARKET"

# Transaction types
DHAN_BUY = "BUY"
DHAN_SELL = "SELL"

# Exchange segments
DHAN_NSE_EQ = "NSE_EQ"
DHAN_NSE_FNO = "NSE_FNO"
DHAN_BSE_EQ = "BSE_EQ"

# Interval mapping: generic -> Dhan
DHAN_INTERVAL_MAP = {
    "1": "1",
    "2": "2",
    "3": "3",
    "5": "5",
    "10": "10",
    "15": "15",
    "25": "25",
    "30": "30",
    "60": "60",
    "D": "D",
    "day": "D",
}


class DhanBroker(BaseBroker):
    """
    Dhan broker implementation.

    BrokerageSetting fields used:
        client_id   → Dhan client/customer ID
        secret_key  → Dhan access token (static, generated from the portal)
        redirect_uri → Not used by Dhan

    FIXED: Added proper token expiry tracking and propagation.
    """

    # Dhan tokens are static but can expire if revoked
    MAX_REQUESTS_PER_SECOND = 5  # Per broker API rate-limit docs
    TOKEN_VALIDITY_DAYS = 30  # Typical validity period

    def __init__(self, state, broker_setting=None):
        self._safe_defaults_init()
        try:
            if not DHAN_AVAILABLE:
                raise ImportError(
                    "dhanhq is not installed. Run: pip install dhanhq"
                )

            self.state = state

            if broker_setting is None:
                raise ValueError("BrokerageSetting must be provided for DhanBroker.")

            self.client_id = safe_getattr(broker_setting, 'client_id', None)
            # For Dhan the "secret_key" field carries the access token
            access_token = safe_getattr(broker_setting, 'secret_key', None)

            # Token expiry tracking
            self._token_expiry = None
            self._token_issued_at = None
            self._last_token_check = 0
            self._token_expiry_check_interval = 60  # seconds

            # Also check the DB for a fresher token (in case it was updated)
            db_token = self._load_token_from_db()
            if db_token:
                access_token = db_token

            if not self.client_id or not access_token:
                raise ValueError("Dhan client_id and access_token (secret_key) are required.")

            self.dhan = dhanhq(self.client_id, access_token)
            self.state.token = access_token

            # Parse token timestamps from DB
            self._token_issued_at = self._parse_token_issued_at()
            self._token_expiry = self._parse_token_expiry()

            if not self._token_expiry and access_token:
                # If no expiry in DB, assume token is valid for TOKEN_VALIDITY_DAYS from now
                self._token_issued_at = ist_now()
                self._token_expiry = self._token_issued_at + timedelta(days=self.TOKEN_VALIDITY_DAYS)

            if self.is_token_expired:
                logger.warning("DhanBroker: token is expired")

            # WebSocket cleanup tracking
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()
            self._ws_feed = None
            self._ws_thread = None
            self._ws_client_id = None
            self._ws_token = None

            # Register with token expiry handler
            self._token_handler = token_expiry_handler

            logger.info(f"DhanBroker initialized for client {self.client_id}")

        except Exception as e:
            logger.critical(f"[DhanBroker.__init__] {e}", exc_info=True)
            raise

    @property
    def broker_type(self) -> str:
        return "dhan"

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
        self.dhan = None
        self._last_request_time = 0
        self._rate_lock = threading.Lock()
        self._request_count = 0
        self._token_expiry = None
        self._token_issued_at = None
        self._last_token_check = 0
        # Dhan instrument cache: "NSE:SYMBOL" -> security_id
        self._instrument_cache: Dict[str, str] = {}

        # WebSocket cleanup tracking
        self._ws_closed = False
        self._ws_cleanup_event = None
        self._ws_feed = None
        self._ws_thread = None
        self._ws_client_id = None
        self._ws_token = None
        self._ws_on_tick = None
        self._ws_on_connect = None
        self._ws_on_close = None
        self._ws_on_error = None

        self._dhan_sec_cache: Dict[str, Any] = {}

    # ── Token management ───────────────────────────────────────────────────────

    def _parse_token_expiry(self) -> Optional[datetime]:
        """Parse token expiry from token data."""
        try:
            db = get_db()
            token_data = tokens.get(db)
            if token_data and token_data.get("expires_at"):
                expiry_str = token_data["expires_at"]
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
                    try:
                        dt = datetime.strptime(expiry_str, fmt)
                        if dt.tzinfo is None:
                            dt = IST.localize(dt)
                        return dt
                    except ValueError:
                        continue
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
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
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
        logger.info("[DhanBroker] Token recovered, reloading from DB")
        # Reload token from DB
        access_token = self._load_token_from_db()
        if access_token:
            self.dhan = dhanhq(self.client_id, access_token)
            self.state.token = access_token
            self._token_expiry = self._parse_token_expiry()
            logger.info("[DhanBroker] Dhan client re-initialized with new token")

    def _load_token_from_db(self) -> Optional[str]:
        try:
            db = get_db()
            token_data = tokens.get(db)
            if token_data and token_data.get("access_token"):
                return token_data["access_token"]
            return None
        except Exception as e:
            logger.error(f"[DhanBroker._load_token_from_db] {e}", exc_info=True)
            return None

    # ── Rate limiting ─────────────────────────────────────────────────────────

    def _check_rate_limit(self):
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

    # ── Symbol / instrument helpers ───────────────────────────────────────────

    @staticmethod
    def _exchange_segment(symbol: str) -> str:
        """Determine Dhan exchange segment from symbol prefix."""
        if symbol.startswith("NFO:") or symbol.startswith("NSE_FNO"):
            return DHAN_NSE_FNO
        if symbol.startswith("BSE:"):
            return DHAN_BSE_EQ
        return DHAN_NSE_EQ

    def _get_security_id(self, symbol: str) -> Optional[str]:
        """
        Resolve NSE/NFO symbol to Dhan security_id.

        Dhan provides a daily instrument dump at:
          https://images.dhan.co/api-data/api-scrip-master.csv
        On first call this file is downloaded, parsed and cached.
        """
        if symbol in self._instrument_cache:
            return self._instrument_cache[symbol]
        try:
            instruments = self._load_dhan_instruments()
            if instruments is None:
                return None
            # Strip exchange prefix for lookup
            clean = symbol.split(":", 1)[-1]
            match = instruments[instruments['SEM_TRADING_SYMBOL'] == clean]
            if not match.empty:
                security_id = str(match.iloc[0]['SEM_SMST_SECURITY_ID'])
                self._instrument_cache[symbol] = security_id
                return security_id
            logger.warning(f"DhanBroker: security_id not found for {symbol}")
            return None
        except Exception as e:
            logger.error(f"[DhanBroker._get_security_id] {e}", exc_info=True)
            return None

    @staticmethod
    def _load_dhan_instruments():
        """Load Dhan instrument master CSV. Caches in-memory for the session."""
        if not safe_hasattr(DhanBroker, '_instruments_df') or DhanBroker._instruments_df is None:
            try:
                url = "https://images.dhan.co/api-data/api-scrip-master.csv"
                DhanBroker._instruments_df = pd.read_csv(url, low_memory=False)
                logger.info("DhanBroker: instrument master loaded")
            except Exception as e:
                logger.error(f"DhanBroker: failed to load instruments: {e}", exc_info=True)
                DhanBroker._instruments_df = None
        return DhanBroker._instruments_df

    _instruments_df = None  # class-level cache

    @staticmethod
    def _to_dhan_interval(interval: str) -> str:
        return DHAN_INTERVAL_MAP.get(str(interval), "1")

    @staticmethod
    def _to_dhan_side(side: int) -> str:
        return DHAN_BUY if side == BaseBroker.SIDE_BUY else DHAN_SELL

    # ── Response normalisation ────────────────────────────────────────────────

    @staticmethod
    def _is_ok(response: Any) -> bool:
        """Dhan returns {'status': 'success', ...} on success."""
        if isinstance(response, dict):
            return response.get("status") == "success"
        return False

    @staticmethod
    def _check_token_error(response: Any):
        if isinstance(response, dict):
            msg = response.get("remarks", "")
            if "invalid" in str(msg).lower() or "unauthori" in str(msg).lower():
                raise TokenExpiredError(str(msg))

    # ── BaseBroker implementation ─────────────────────────────────────────────

    def get_profile(self) -> Optional[Dict]:
        self._check_token_before_request()
        try:
            if not self.dhan:
                return None
            result = self._call(self.dhan.get_fund_limits, context="get_profile")
            # Dhan doesn't have a dedicated profile endpoint; fund limits confirms auth
            return result if self._is_ok(result) else None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.get_profile] {e!r}", exc_info=True)
            return None

    def get_balance(self, capital_reserve: float = 0.0) -> float:
        self._check_token_before_request()
        try:
            if not self.dhan:
                return 0.0
            result = self._call(self.dhan.get_fund_limits, context="get_balance")
            if self._is_ok(result):
                data = result.get("data", {})
                available = float(data.get("availableBalance", 0.0))
                if capital_reserve > 0:
                    available = available * (1 - capital_reserve / 100)
                return available
            return 0.0
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.get_balance] {e!r}", exc_info=True)
            return 0.0

    def get_history(self, symbol: str, interval: str = "2", length: int = 400):
        self._check_token_before_request()
        try:
            if not symbol or not self.dhan:
                return None
            security_id = self._get_security_id(symbol)
            if not security_id:
                return None
            exchange_seg = self._exchange_segment(symbol)
            dhan_interval = self._to_dhan_interval(interval)

            # Dhan requires date range for intraday data
            to_date = to_date_str(ist_now())
            from_date = to_date_str(ist_now() - timedelta(days=4))

            result = self._call(
                lambda: self.dhan.intraday_minute_data(
                    security_id=security_id,
                    exchange_segment=exchange_seg,
                    instrument_type="OPTIDX" if "FNO" in exchange_seg else "EQUITY",
                    from_date=from_date,
                    to_date=to_date,
                ),
                context="get_history"
            )
            if self._is_ok(result):
                data = result.get("data", [])
                if data:
                    df = pd.DataFrame(data)
                    return df.tail(length)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.get_history] {e!r}", exc_info=True)
            return None

    def get_history_for_timeframe(self, symbol: str, interval: str, days: int = 30):
        self._check_token_before_request()
        try:
            if not symbol or not self.dhan:
                return None
            security_id = self._get_security_id(symbol)
            if not security_id:
                return None
            exchange_seg = self._exchange_segment(symbol)
            fetch_days = max(days, 60) if interval in ["15", "30", "60"] else (
                max(days, 120) if interval in ["120", "240"] else days
            )
            to_date = to_date_str(ist_now())
            from_date = to_date_str(ist_now() - timedelta(days=fetch_days))
            result = self._call(
                lambda: self.dhan.historical_daily_data(
                    security_id=security_id,
                    exchange_segment=exchange_seg,
                    instrument_type="OPTIDX" if "FNO" in exchange_seg else "EQUITY",
                    expiry_code=0,
                    from_date=from_date,
                    to_date=to_date,
                ),
                context="get_history_for_timeframe"
            )
            if self._is_ok(result):
                data = result.get("data", [])
                if data:
                    return pd.DataFrame(data)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.get_history_for_timeframe] {e!r}", exc_info=True)
            return None

    def get_option_current_price(self, option_name: str) -> Optional[float]:
        quote = self.get_option_quote(option_name)
        return quote.get("ltp") if quote else None

    def get_option_quote(self, option_name: str) -> Optional[Dict[str, float]]:
        self._check_token_before_request()
        try:
            if not option_name or not self.dhan:
                return None
            security_id = self._get_security_id(option_name)
            if not security_id:
                return None
            exchange_seg = self._exchange_segment(option_name)
            self._check_rate_limit()
            result = self._call(
                lambda: self.dhan.get_market_quote([
                    {"securityId": security_id, "exchangeSegment": exchange_seg}
                ]),
                context="get_option_quote"
            )
            if self._is_ok(result):
                data = result.get("data", [{}])[0]
                return {
                    "ltp": data.get("lastTradedPrice"),
                    "bid": data.get("bestBidPrice"),
                    "ask": data.get("bestAskPrice"),
                    "high": data.get("dayHigh"),
                    "low": data.get("dayLow"),
                    "open": data.get("openPrice"),
                    "close": data.get("closePrice"),
                    "volume": data.get("volume"),
                    "oi": data.get("openInterest"),
                }
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.get_option_quote] {e!r}", exc_info=True)
            return None

    def get_option_chain_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        result = {}
        for sym in symbols:
            quote = self.get_option_quote(sym)
            if quote:
                clean = sym.split(":", 1)[-1]
                result[clean] = quote
        return result

    def place_order(self, **kwargs) -> Optional[str]:
        self._check_token_before_request()
        try:
            if not self.dhan:
                return None
            symbol = kwargs.get('symbol')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_BUY)
            order_type = kwargs.get('order_type', self.MARKET_ORDER_TYPE)
            product = kwargs.get('product_type', DHAN_PRODUCT_INTRADAY)
            limit_price = kwargs.get('limitPrice', 0) or 0
            stop_price = kwargs.get('stopPrice', 0) or 0

            if not symbol or qty <= 0:
                return None

            security_id = self._get_security_id(symbol)
            if not security_id:
                return None

            exchange_seg = self._exchange_segment(symbol)
            dhan_order_type = {
                self.MARKET_ORDER_TYPE: DHAN_ORDER_MARKET,
                self.LIMIT_ORDER_TYPE: DHAN_ORDER_LIMIT,
                self.STOPLOSS_MARKET_ORDER_TYPE: DHAN_ORDER_SLM,
            }.get(order_type, DHAN_ORDER_MARKET)

            self._check_rate_limit()
            result = self._call(
                lambda: self.dhan.place_order(
                    security_id=security_id,
                    exchange_segment=exchange_seg,
                    transaction_type=self._to_dhan_side(side),
                    quantity=qty,
                    order_type=dhan_order_type,
                    product_type=product,
                    price=limit_price,
                    trigger_price=stop_price,
                ),
                context="place_order"
            )
            if self._is_ok(result):
                order_id = result.get("data", {}).get("orderId")
                logger.info(f"DhanBroker: order placed {order_id}")
                return str(order_id) if order_id else None
            self._check_token_error(result)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.place_order] {e!r}", exc_info=True)
            return None

    def modify_order(self, **kwargs) -> bool:
        self._check_token_before_request()
        try:
            order_id = kwargs.get('order_id')
            limit_price = kwargs.get('limit_price', 0)
            qty = kwargs.get('qty', 0)
            if not order_id or not self.dhan:
                return False
            self._check_rate_limit()
            result = self._call(
                lambda: self.dhan.modify_order(
                    order_id=order_id,
                    order_type=DHAN_ORDER_LIMIT,
                    leg_name="ENTRY_LEG",
                    quantity=qty,
                    price=limit_price,
                    trigger_price=0,
                    disclosed_quantity=0,
                    validity="DAY",
                ),
                context="modify_order"
            )
            return self._is_ok(result)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.modify_order] {e!r}", exc_info=True)
            return False

    def cancel_order(self, **kwargs) -> bool:
        self._check_token_before_request()
        try:
            order_id = kwargs.get('order_id')
            if not order_id or not self.dhan:
                return False
            self._check_rate_limit()
            result = self._call(
                lambda: self.dhan.cancel_order(order_id=order_id),
                context="cancel_order"
            )
            return self._is_ok(result)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.cancel_order] {e!r}", exc_info=True)
            return False

    def exit_position(self, **kwargs) -> bool:
        self._check_token_before_request()
        symbol = kwargs.get('symbol')
        qty = kwargs.get('qty', 0)
        current_side = kwargs.get('side', self.SIDE_BUY)
        exit_side = self.SIDE_SELL if current_side == self.SIDE_BUY else self.SIDE_BUY
        if not symbol or qty <= 0:
            return False
        return self.place_order(symbol=symbol, qty=qty, side=exit_side,
                                order_type=self.MARKET_ORDER_TYPE) is not None

    def add_stoploss(self, **kwargs) -> bool:
        self._check_token_before_request()
        kwargs['order_type'] = self.STOPLOSS_MARKET_ORDER_TYPE
        kwargs.setdefault('side', self.SIDE_SELL)
        return self.place_order(**kwargs) is not None

    def remove_stoploss(self, **kwargs) -> bool:
        self._check_token_before_request()
        return self.cancel_order(**kwargs)

    def sell_at_current(self, **kwargs) -> bool:
        self._check_token_before_request()
        return self.place_order(order_type=self.MARKET_ORDER_TYPE,
                                side=self.SIDE_SELL, **kwargs) is not None

    def get_positions(self) -> List[Dict[str, Any]]:
        self._check_token_before_request()
        try:
            if not self.dhan:
                return []
            result = self._call(self.dhan.get_positions, context="get_positions")
            if self._is_ok(result):
                return result.get("data", [])
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.get_positions] {e!r}", exc_info=True)
            return []

    def get_orderbook(self) -> List[Dict[str, Any]]:
        self._check_token_before_request()
        try:
            if not self.dhan:
                return []
            result = self._call(self.dhan.get_order_list, context="get_orderbook")
            if self._is_ok(result):
                return result.get("data", [])
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.get_orderbook] {e!r}", exc_info=True)
            return []

    def get_current_order_status(self, order_id: str) -> Optional[int]:
        """
        Return the integer fill status for the given order_id.

        Dhan orderstatus values (from dhanhq docs):
            "TRADED"    → filled  (maps to 2)
            "PENDING"   → open    (maps to 1)
            "REJECTED" / "CANCELLED" → maps to -1
        """
        self._check_token_before_request()
        try:
            if not order_id or not self.dhan:
                return None
            result = self._call(
                lambda: self.dhan.get_order_by_id(order_id=order_id),
                context="order_status"
            )
            if not self._is_ok(result):
                return None
            data = result.get("data") or {}
            status_str = str(data.get("orderStatus") or "").upper()
            if status_str in ("TRADED", "COMPLETE", "FILLED"):
                return 2   # Filled — matches order_executor expectation
            if status_str in ("REJECTED", "CANCELLED", "CANCELED"):
                return -1
            return 1       # Pending / open
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.get_current_order_status] {e!r}", exc_info=True)
            return None

    def get_fill_price(self, broker_order_id: str) -> Optional[float]:
        """
        Return the actual average fill price for a completed order.
        """
        self._check_token_before_request()
        try:
            if not broker_order_id or not self.dhan:
                return None
            result = self._call(
                lambda: self.dhan.get_order_by_id(order_id=broker_order_id),
                context="get_fill_price"
            )
            if self._is_ok(result):
                data = result.get("data") or {}
                avg = data.get("averageTradedPrice") or data.get("tradedPrice")
                if avg:
                    return float(avg)
            return None
        except Exception as e:
            logger.error(f"[DhanBroker.get_fill_price] {e!r}", exc_info=True)
            return None

    # ── Broker-specific option symbol construction ────────────────────────────

    def build_option_symbol(
        self,
        underlying: str,
        spot_price: float,
        option_type: str,
        weeks_offset: int = 0,
        lookback_strikes: int = 0,
    ) -> Optional[str]:
        """
        Dhan option symbol: numeric ``security_id`` from Dhan instrument master.

        Dhan does NOT use a text tradingsymbol for orders — every instrument
        is identified by a numeric security_id.  This method builds the NSE
        compact core (e.g. "NIFTY2531825000CE"), looks it up in the Dhan
        instrument master CSV, and returns the security_id string.
        Returns compact core as fallback if the lookup fails.
        """
        try:
            from Utils.OptionSymbolBuilder import OptionSymbolBuilder
            params = OptionSymbolBuilder.get_option_params(
                underlying=underlying, spot_price=spot_price,
                option_type=option_type, weeks_offset=weeks_offset,
                lookback_strikes=lookback_strikes,
            )
            return self._params_to_symbol(params)
        except Exception as e:
            logger.error(f"[DhanBroker.build_option_symbol] {e}", exc_info=True)
            return None

    def _params_to_symbol(self, params) -> Optional[str]:
        """Dhan: security_id lookup from instrument master using compact core."""
        if not params:
            return None
        core = params.compact_core           # e.g. "NIFTY2531825000CE"
        try:
            security_id = self._get_security_id(f"NFO:{core}")
            if security_id:
                return security_id
        except Exception:
            pass
        logger.warning(
            f"[DhanBroker._params_to_symbol] security_id not found for "
            f"{core} — returning compact core as fallback"
        )
        return core

    def build_option_chain(
        self,
        underlying: str,
        spot_price: float,
        option_type: str,
        weeks_offset: int = 0,
        itm: int = 5,
        otm: int = 5,
    ) -> List[str]:
        """Build a Dhan option chain as a list of security_ids."""
        try:
            from Utils.OptionSymbolBuilder import OptionSymbolBuilder
            all_params = OptionSymbolBuilder.get_all_option_params(
                underlying=underlying, spot_price=spot_price,
                option_type=option_type, weeks_offset=weeks_offset,
                itm=itm, otm=otm,
            )
            return [s for s in (self._params_to_symbol(p) for p in all_params) if s]
        except Exception as e:
            logger.error(f"[DhanBroker.build_option_chain] {e}", exc_info=True)
            return []

    def is_connected(self) -> bool:
        try:
            if self.is_token_expired:
                return False
            return self.get_profile() is not None
        except TokenExpiredError:
            return False
        except Exception:
            return False

    def cleanup(self) -> None:
        """Clean up resources including WebSocket connection."""
        logger.info("[DhanBroker] Starting cleanup")

        # Mark WebSocket as closed to prevent callbacks
        self._ws_closed = True

        # Clean up WebSocket feed if it exists
        if self._ws_feed is not None:
            try:
                if self._ws_cleanup_event is None:
                    self._ws_cleanup_event = threading.Event()
                self._ws_cleanup_event.clear()

                def _do_disconnect():
                    try:
                        if safe_hasattr(self._ws_feed, "disconnect"):
                            self._ws_feed.disconnect()
                            logger.debug("[DhanBroker] DhanFeed disconnect called")
                    except Exception as e:
                        logger.warning(f"[DhanBroker] Error disconnecting feed: {e}")
                    finally:
                        self._ws_cleanup_event.set()

                # Run disconnect in separate thread with timeout
                disconnect_thread = threading.Thread(target=_do_disconnect, daemon=True)
                disconnect_thread.start()

                # Wait for disconnect with timeout
                if not self._ws_cleanup_event.wait(timeout=2.0):
                    logger.warning("[DhanBroker] DhanFeed disconnect timed out")

            except Exception as e:
                logger.error(f"[DhanBroker] Error during WebSocket cleanup: {e}", exc_info=True)
            finally:
                self._ws_feed = None

        # Wait for WebSocket thread to finish (with timeout)
        if self._ws_thread and self._ws_thread.is_alive():
            try:
                self._ws_thread.join(timeout=1.0)
                if self._ws_thread.is_alive():
                    logger.warning("[DhanBroker] WebSocket thread still alive after join")
            except Exception as e:
                logger.warning(f"[DhanBroker] Error joining WebSocket thread: {e}")

        # Clear callbacks
        self._ws_on_tick = None
        self._ws_on_connect = None
        self._ws_on_close = None
        self._ws_on_error = None

        logger.info("[DhanBroker] Cleanup completed")

    # ── Internal call wrapper ─────────────────────────────────────────────────

    def _call(self, func: Callable, context: str = "",
              max_retries: int = 3, base_delay: int = 1):
        for attempt in range(max_retries):
            try:
                self._check_token_before_request()
                self._check_rate_limit()
                response = func()
                if isinstance(response, dict):
                    self._check_token_error(response)
                return response
            except TokenExpiredError:
                raise
            except (Timeout, ConnectionError) as e:
                delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning(f"[DhanBroker.{context}] Network error, retry {attempt+1}: {e}")
                time.sleep(delay)
            except Exception as e:
                error_str = str(e).lower()
                if "unauthori" in error_str or "invalid token" in error_str:
                    raise TokenExpiredError(str(e))
                if "rate" in error_str or "throttl" in error_str:
                    delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                    logger.warning(f"[DhanBroker.{context}] Rate limited, retry {attempt+1}")
                    time.sleep(delay)
                else:
                    logger.error(f"[DhanBroker.{context}] {e!r}", exc_info=True)
                    return None
        logger.critical(f"[DhanBroker.{context}] Max retries reached.")
        return None

    # ── WebSocket interface ────────────────────────────────────────────────────

    def create_websocket(self, on_tick, on_connect, on_close, on_error) -> Any:
        """
        Create Dhan live market feed WebSocket.

        Dhan uses DhanFeed (dhanhq.market_feed module).
        Securities are identified by (exchange_segment, security_id) tuples.

        FIXED: Added state tracking and stored callbacks.
        """
        try:
            from dhanhq import marketfeed  # type: ignore

            client_id    = safe_getattr(self, 'client_id', None) or \
                           safe_getattr(self, 'dhan_client_id', None)
            access_token = safe_getattr(self.state, "token", None) if self.state else None
            if not client_id or not access_token:
                logger.error("DhanBroker.create_websocket: missing client_id or token")
                return None

            # Check token before creating websocket
            if self.is_token_expired:
                self._handle_token_expired("Cannot create websocket with expired token")

            # Reset WebSocket state
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()

            self._ws_on_tick    = on_tick
            self._ws_on_connect = on_connect
            self._ws_on_close   = on_close
            self._ws_on_error   = on_error
            self._ws_client_id  = client_id
            self._ws_token      = access_token

            # Return a sentinel; actual DhanFeed is created in ws_connect
            # because DhanFeed requires instruments list at construction time.
            logger.info("DhanBroker: WebSocket callbacks stored (DhanFeed created at subscribe)")
            return {"__dhan_pending__": True, "__dhan_client_id__": client_id, "__dhan_token__": access_token}
        except ImportError:
            logger.error("DhanBroker: dhanhq not installed — pip install dhanhq")
            return None
        except Exception as e:
            logger.error(f"[DhanBroker.create_websocket] {e}", exc_info=True)
            return None

    def ws_connect(self, ws_obj) -> None:
        """Dhan WebSocket starts when ws_subscribe is called (DhanFeed is constructed there)."""
        logger.info("DhanBroker: ws_connect called — actual connection starts at ws_subscribe")

    def ws_subscribe(self, ws_obj, symbols: List[str]) -> None:
        """
        Subscribe to Dhan live feed.

        Builds a DhanFeed instance with the given instruments and starts it.
        Dhan requires (exchange_segment, security_id, subscription_type) tuples.
        """
        try:
            from dhanhq import marketfeed  # type: ignore

            if ws_obj is None or not symbols or self._ws_closed:
                return

            instruments = []
            for sym in symbols:
                seg, sec_id = self._resolve_dhan_security(sym)
                if seg and sec_id:
                    instruments.append((seg, sec_id, marketfeed.Quote))

            if not instruments:
                logger.warning("DhanBroker.ws_subscribe: no valid instruments")
                return

            # Create feed
            feed = marketfeed.DhanFeed(
                client_id=self._ws_client_id,
                access_token=self._ws_token,
                instruments=instruments,
                subscription_code=marketfeed.Quote,
                on_message=self._ws_on_tick if not self._ws_closed else None,
            )

            # Store feed object
            self._ws_feed = feed
            ws_obj["__feed__"] = feed

            # Run feed in a separate thread
            def _run_feed():
                try:
                    if not self._ws_closed:
                        feed.run_forever()
                except Exception as e:
                    if not self._ws_closed:
                        logger.error(f"[DhanBroker] Feed error: {e}")
                        if self._ws_on_error:
                            self._ws_on_error(str(e))

            self._ws_thread = threading.Thread(target=_run_feed, daemon=True, name="DhanFeed")
            self._ws_thread.start()

            # Call on_connect callback
            if self._ws_on_connect and not self._ws_closed:
                self._ws_on_connect()

            logger.info(f"DhanBroker: DhanFeed started with {len(instruments)} instruments")

        except Exception as e:
            logger.error(f"[DhanBroker.ws_subscribe] {e}", exc_info=True)
            if self._ws_on_error and not self._ws_closed:
                self._ws_on_error(str(e))

    def ws_unsubscribe(self, ws_obj, symbols: List[str]) -> None:
        """Dhan does not support partial unsubscribe; close and reconnect if needed."""
        logger.warning("DhanBroker: partial unsubscribe not supported — use ws_disconnect and reconnect")

    def ws_disconnect(self, ws_obj) -> None:
        """
        Stop Dhan live feed with timeout protection.

        FIXED: Added timeout and better error handling.
        """
        try:
            if ws_obj is None:
                return

            logger.info("[DhanBroker] Starting WebSocket disconnect")
            self._ws_closed = True

            feed = ws_obj.get("__feed__") if isinstance(ws_obj, dict) else self._ws_feed

            if feed and safe_hasattr(feed, "disconnect"):
                # Run disconnect in separate thread with timeout
                disconnect_complete = threading.Event()

                def _do_disconnect():
                    try:
                        feed.disconnect()
                        logger.debug("[DhanBroker] disconnect completed")
                    except Exception as e:
                        logger.warning(f"[DhanBroker] disconnect error: {e}")
                    finally:
                        disconnect_complete.set()

                disconnect_thread = threading.Thread(target=_do_disconnect, daemon=True)
                disconnect_thread.start()

                # Wait for disconnect with timeout
                if not disconnect_complete.wait(timeout=2.0):
                    logger.warning("[DhanBroker] disconnect timed out")

            # Clear references
            self._ws_feed = None
            ws_obj["__feed__"] = None

            # Call on_close callback
            if self._ws_on_close:
                try:
                    self._ws_on_close("disconnected by user")
                except Exception as e:
                    logger.warning(f"[DhanBroker] Error in close callback: {e}")

            logger.info("[DhanBroker] WebSocket disconnect completed")

        except Exception as e:
            logger.error(f"[DhanBroker.ws_disconnect] {e}", exc_info=True)

    def normalize_tick(self, raw_tick) -> Optional[Dict[str, Any]]:
        """
        Normalize a Dhan market feed tick.

        Dhan DhanFeed tick dict fields:
            type, exchange_segment, security_id, LTP, LTT,
            volume, OI, bid_price, ask_price, ...
        """
        try:
            if self._ws_closed or not isinstance(raw_tick, dict):
                return None

            ltp = raw_tick.get("LTP") or raw_tick.get("ltp")
            if ltp is None:
                return None

            seg     = raw_tick.get("exchange_segment", "")
            sec_id  = raw_tick.get("security_id", "")
            symbol  = f"{seg}:{sec_id}" if seg else str(sec_id)

            return {
                "symbol":    symbol,
                "ltp":       float(ltp),
                "timestamp": str(raw_tick.get("LTT", "")),
                "bid":       raw_tick.get("best_bid_price"),
                "ask":       raw_tick.get("best_ask_price"),
                "volume":    raw_tick.get("volume"),
                "oi":        raw_tick.get("OI"),
                "open":      raw_tick.get("open"),
                "high":      raw_tick.get("high"),
                "low":       raw_tick.get("low"),
                "close":     raw_tick.get("close"),
            }
        except Exception as e:
            if not self._ws_closed:  # Only log if not during shutdown
                logger.error(f"[DhanBroker.normalize_tick] {e}", exc_info=True)
            return None

    def _resolve_dhan_security(self, symbol: str):
        """
        Resolve a generic NSE:SYMBOL to (exchange_segment, security_id) for Dhan.

        Returns ("NSE_EQ", security_id_str) or (None, None) on failure.
        Attempts cache lookup first, then falls back to symbol stripping.
        """
        try:
            from dhanhq import marketfeed  # type: ignore
            cache = safe_getattr(self, "_dhan_sec_cache", {})
            if symbol in cache:
                return cache[symbol]

            # Strip exchange prefix and use bare symbol as security_id
            bare = symbol.split(":")[-1]
            upper = symbol.upper()
            if "NFO" in upper or "FNO" in upper:
                seg = marketfeed.NFO
            elif "BSE" in upper:
                seg = marketfeed.BSE
            else:
                seg = marketfeed.NSE
            result = (seg, bare)
            cache[symbol] = result
            self._dhan_sec_cache = cache
            return result
        except Exception:
            return (None, None)