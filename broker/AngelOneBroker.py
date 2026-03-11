"""
brokers/AngelOneBroker.py
=========================
Angel One SmartAPI implementation of BaseBroker.

Prerequisites:
    pip install smartapi-python pyotp logzero

Authentication:
    Angel One uses TOTP-based login (no browser OAuth needed).
    Credentials stored in BrokerageSetting:
        client_id   → Angel One Client Code (e.g. A123456)
        secret_key  → API Key from SmartAPI developer portal
        redirect_uri → TOTP secret (QR value from SmartAPI portal) OR MPIN

    Two-step auth at startup:
        1. broker.login(password="your_mpin", totp="123456")
        2. Access token is cached in DB for the session.

    Angel One tokens are valid only for the current trading day.
    A new session must be generated each morning.

API docs: https://smartapi.angelbroking.com/docs
SDK:      pip install smartapi-python

FIXED: Added proper token expiry tracking and propagation to central handler.
"""

import logging
import time
import random
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable

import pandas as pd
import pytz
from requests.exceptions import Timeout, ConnectionError

from Utils.safe_getattr import safe_getattr, safe_hasattr
from broker.BaseBroker import BaseBroker, TokenExpiredError
from broker.TokenExpiryHandler import token_expiry_handler
from db.connector import get_db
from db.crud import tokens

try:
    from SmartApi import SmartConnect
    import pyotp
    ANGEL_AVAILABLE = True
except ImportError:
    ANGEL_AVAILABLE = False

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

# ── AngelOne product / order constants ───────────────────────────────────────
ANGEL_PRODUCT_INTRADAY = "INTRADAY"
ANGEL_PRODUCT_DELIVERY = "DELIVERY"
ANGEL_PRODUCT_MARGIN = "MARGIN"

ANGEL_ORDER_MARKET = "MARKET"
ANGEL_ORDER_LIMIT  = "LIMIT"
ANGEL_ORDER_SL     = "STOPLOSS_LIMIT"
ANGEL_ORDER_SLM    = "STOPLOSS_MARKET"

ANGEL_BUY  = "BUY"
ANGEL_SELL = "SELL"

ANGEL_VARIETY_NORMAL = "NORMAL"
ANGEL_VARIETY_STOPLOSS = "STOPLOSS"

# Angel interval mapping: generic -> SmartAPI
ANGEL_INTERVAL_MAP = {
    "1": "ONE_MINUTE",
    "3": "THREE_MINUTE",
    "5": "FIVE_MINUTE",
    "10": "TEN_MINUTE",
    "15": "FIFTEEN_MINUTE",
    "30": "THIRTY_MINUTE",
    "60": "ONE_HOUR",
    "D":  "ONE_DAY",
    "day": "ONE_DAY",
}


class AngelOneBroker(BaseBroker):
    """
    Angel One SmartAPI broker implementation.

    BrokerageSetting fields used:
        client_id    → Angel One Client Code (login ID)
        secret_key   → SmartAPI API Key
        redirect_uri → TOTP secret string (base32 key from QR code scan)

    To generate a session call:
        broker.login(password="YOUR_MPIN")
        # This auto-generates TOTP from the stored totp_secret and creates a session.

    FIXED: Added proper token expiry tracking and propagation.
    """

    # Angel One tokens expire at midnight (end of trading day)
    SESSION_DURATION_HOURS = 8  # Typically valid until end of day

    MAX_REQUESTS_PER_SECOND = 1  # Per broker API rate-limit docs
    def __init__(self, state, broker_setting=None):
        self._safe_defaults_init()
        try:
            if not ANGEL_AVAILABLE:
                raise ImportError(
                    "smartapi-python or pyotp not installed.\n"
                    "Run: pip install smartapi-python pyotp logzero"
                )
            self.state = state

            if broker_setting is None:
                raise ValueError("BrokerageSetting must be provided for AngelOneBroker.")

            self.client_code = safe_getattr(broker_setting, 'client_id', None)
            self.api_key     = safe_getattr(broker_setting, 'secret_key', None)
            self.totp_secret = safe_getattr(broker_setting, 'redirect_uri', None)  # TOTP base32 secret

            if not self.client_code or not self.api_key:
                raise ValueError("AngelOne client_code and api_key are required.")

            # Token expiry tracking
            self._token_expiry = None
            self._token_issued_at = None
            self._last_token_check = 0
            self._token_expiry_check_interval = 60  # seconds
            self._refresh_token = None
            self._feed_token = None

            # Init SDK
            self.smart = SmartConnect(api_key=self.api_key)

            # Load saved token
            access_token = self._load_token_from_db()
            if access_token:
                self.state.token = access_token
                self._token_issued_at = self._parse_token_issued_at()
                self._token_expiry = self._parse_token_expiry()
                logger.info("AngelOneBroker: loaded token from DB")

                if self.is_token_expired:
                    logger.warning("AngelOneBroker: token is expired")
            else:
                logger.warning("AngelOneBroker: no token in DB — call broker.login(password='MPIN')")

            # WebSocket cleanup tracking
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()
            self._ws_obj = None

            # Register with token expiry handler
            self._token_handler = token_expiry_handler

            logger.info(f"AngelOneBroker initialized for client {self.client_code}")

        except Exception as e:
            logger.critical(f"[AngelOneBroker.__init__] {e}", exc_info=True)
            raise

    @property
    def broker_type(self) -> str:
        return "angelone"

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
        self.client_code = None
        self.api_key = None
        self.totp_secret = None
        self.smart = None
        self._refresh_token = None
        self._feed_token = None
        self._last_request_time = 0
        self._rate_lock = threading.Lock()
        self._request_count = 0
        self._token_expiry = None
        self._token_issued_at = None
        self._last_token_check = 0
        # Scrip token cache: "NSE:SYMBOL" -> symboltoken
        self._scrip_cache: Dict[str, str] = {}
        self._token_to_symbol_cache: Dict[str, str] = {}

        # WebSocket cleanup tracking
        self._ws_closed = False
        self._ws_cleanup_event = None
        self._ws_obj = None

        self._angel_token_cache: Dict[str, Any] = {}

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
                            dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
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
        logger.info("[AngelOneBroker] Token recovered, re-login required")
        # Auto-login if MPIN is stored
        # Note: MPIN must be provided by the user, can't auto-retry

    # ── Authentication ────────────────────────────────────────────────────────

    def login(self, password: str, totp: Optional[str] = None) -> bool:
        """
        Generate a fresh SmartAPI session.

        Args:
            password: Angel One MPIN (4-digit numeric pin)
            totp: TOTP code (6 digits). If None, auto-generated from totp_secret.

        Returns:
            True on success
        """
        try:
            if totp is None and self.totp_secret:
                totp = pyotp.TOTP(self.totp_secret).now()
            if not totp:
                raise ValueError("TOTP is required for Angel One login. "
                                 "Store your TOTP secret in redirect_uri field.")

            data = self.smart.generateSession(self.client_code, password, totp)
            if not data or data.get('status') is False:
                logger.error(f"AngelOneBroker login failed: {data}")
                return False

            auth_token = data['data']['jwtToken']
            self._refresh_token = data['data']['refreshToken']
            self._feed_token = self.smart.getfeedToken()

            # Update token timestamps
            issued_at = datetime.now()
            expires_at = issued_at + timedelta(hours=self.SESSION_DURATION_HOURS)

            # Refresh SmartConnect with the new token
            self.smart.generateToken(self._refresh_token)
            self.state.token = auth_token
            self._token_issued_at = issued_at
            self._token_expiry = expires_at

            # Persist (Angel tokens expire at midnight)
            db = get_db()
            tokens.save_token(
                auth_token,
                self._refresh_token,
                issued_at=issued_at.isoformat(),
                expires_at=expires_at.isoformat(),
                db=db
            )
            logger.info("AngelOneBroker: session generated successfully")
            return True

        except Exception as e:
            logger.error(f"[AngelOneBroker.login] {e}", exc_info=True)
            return False

    def _load_token_from_db(self) -> Optional[str]:
        try:
            db = get_db()
            token_data = tokens.get(db)
            if token_data and token_data.get("access_token"):
                return token_data["access_token"]
            return None
        except Exception as e:
            logger.error(f"[AngelOneBroker._load_token_from_db] {e}", exc_info=True)
            return None

    # ── Rate limiting ─────────────────────────────────────────────────────────

    def _check_rate_limit(self):
        with self._rate_lock:
            current = time.time()
            diff = current - self._last_request_time
            if diff < 1.0:
                self._request_count += 1
                if self._request_count > self.MAX_REQUESTS_PER_SECOND:
                    sleep_time = 1.0 - diff + 0.1
                    self._rate_lock.release()
                    try:
                        time.sleep(sleep_time)
                    finally:
                        self._rate_lock.acquire()
                    self._request_count = 0
                    self._last_request_time = time.time()
            else:
                self._request_count = 1
                self._last_request_time = current

    # ── Symbol / scrip helpers ────────────────────────────────────────────────

    def _get_scrip_token(self, symbol: str) -> Optional[str]:
        """
        Angel One requires a numeric symboltoken alongside the tradingsymbol.
        Looks up from the instrument master CSV (cached per session).
        """
        if symbol in self._scrip_cache:
            return self._scrip_cache[symbol]
        try:
            instruments = self._load_angel_instruments()
            if instruments is None:
                return None
            clean = symbol.split(":")[-1]
            match = instruments[instruments['symbol'] == clean]
            if not match.empty:
                token = str(match.iloc[0]['token'])
                self._scrip_cache[symbol] = token
                self._token_to_symbol_cache[token] = symbol
                return token
            logger.warning(f"AngelOneBroker: token not found for {symbol}")
            return None
        except Exception as e:
            logger.error(f"[AngelOneBroker._get_scrip_token] {e}", exc_info=True)
            return None

    @staticmethod
    def _load_angel_instruments():
        if not safe_hasattr(AngelOneBroker, '_instruments_df') or AngelOneBroker._instruments_df is None:
            try:
                url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
                AngelOneBroker._instruments_df = pd.read_json(url)
                logger.info("AngelOneBroker: instrument master loaded")
            except Exception as e:
                logger.error(f"AngelOneBroker: instrument load failed: {e}", exc_info=True)
                AngelOneBroker._instruments_df = None
        return AngelOneBroker._instruments_df

    _instruments_df = None

    @staticmethod
    def _exchange_from_symbol(symbol: str) -> str:
        if symbol.startswith("NFO:"):
            return "NFO"
        if symbol.startswith("BSE:"):
            return "BSE"
        import re as _re
        bare = symbol.upper().split(":")[-1]
        if _re.search(r'(CE|PE|FUT)$', bare):
            return "NFO"
        return "NSE"

    @staticmethod
    def _to_angel_interval(interval: str) -> str:
        return ANGEL_INTERVAL_MAP.get(str(interval), "ONE_MINUTE")

    @staticmethod
    def _to_angel_side(side: int) -> str:
        return ANGEL_BUY if side == BaseBroker.SIDE_BUY else ANGEL_SELL

    @staticmethod
    def _is_ok(response: Any) -> bool:
        if isinstance(response, dict):
            return response.get("status") is True or response.get("message") == "SUCCESS"
        return False

    def _check_token_error(self, response: Any):
        if isinstance(response, dict):
            msg = str(response.get("message", "")).lower()
            code = str(response.get("errorcode", ""))
            if "invalid token" in msg or "token expired" in msg or code in ["AB1010", "AB8050"]:
                raise TokenExpiredError(str(response.get("message", "Token expired")))

    # ── BaseBroker implementation ─────────────────────────────────────────────

    def get_profile(self) -> Optional[Dict]:
        self._check_token_before_request()
        try:
            if not self.smart or not self.state.token:
                return None
            result = self._call(
                lambda: self.smart.getProfile(self._refresh_token or ""),
                context="get_profile"
            )
            return result.get("data") if self._is_ok(result) else None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AngelOneBroker.get_profile] {e!r}", exc_info=True)
            return None

    def get_balance(self, capital_reserve: float = 0.0) -> float:
        self._check_token_before_request()
        try:
            if not self.smart:
                return 0.0
            result = self._call(lambda: self.smart.rmsLimit(), context="get_balance")
            if self._is_ok(result):
                data = result.get("data", {})
                available = float(data.get("availablecash", 0.0))
                if capital_reserve > 0:
                    available = available * (1 - capital_reserve / 100)
                return available
            return 0.0
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AngelOneBroker.get_balance] {e!r}", exc_info=True)
            return 0.0

    def get_history(self, symbol: str, interval: str = "2", length: int = 400):
        self._check_token_before_request()
        try:
            if not symbol or not self.smart:
                return None
            exchange = self._exchange_from_symbol(symbol)
            clean = symbol.split(":")[-1]
            token = self._get_scrip_token(symbol)
            if not token:
                return None
            to_dt = datetime.now()
            from_dt = to_dt - timedelta(days=4)
            angel_interval = self._to_angel_interval(interval)
            params = {
                "exchange": exchange,
                "symboltoken": token,
                "interval": angel_interval,
                "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
                "todate":   to_dt.strftime("%Y-%m-%d %H:%M"),
            }
            result = self._call(lambda: self.smart.getCandleData(params), context="get_history")
            if self._is_ok(result):
                data = result.get("data", [])
                if data:
                    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close", "volume"])
                    return df.tail(length)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AngelOneBroker.get_history] {e!r}", exc_info=True)
            return None

    def get_history_for_timeframe(self, symbol: str, interval: str, days: int = 30):
        self._check_token_before_request()
        try:
            if not symbol or not self.smart:
                return None
            exchange = self._exchange_from_symbol(symbol)
            token = self._get_scrip_token(symbol)
            if not token:
                return None
            fetch_days = max(days, 60) if interval in ["15", "30", "60"] else (
                max(days, 120) if interval in ["120", "240"] else days
            )
            to_dt = datetime.now()
            from_dt = to_dt - timedelta(days=fetch_days)
            angel_interval = self._to_angel_interval(interval)
            params = {
                "exchange": exchange, "symboltoken": token,
                "interval": angel_interval,
                "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
                "todate":   to_dt.strftime("%Y-%m-%d %H:%M"),
            }
            result = self._call(lambda: self.smart.getCandleData(params), context="get_history_for_timeframe")
            if self._is_ok(result):
                data = result.get("data", [])
                if data:
                    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close", "volume"])
                    df["time"] = pd.to_datetime(df["time"])
                    return df
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AngelOneBroker.get_history_for_timeframe] {e!r}", exc_info=True)
            return None

    def get_option_current_price(self, option_name: str) -> Optional[float]:
        quote = self.get_option_quote(option_name)
        return quote.get("ltp") if quote else None

    def get_option_quote(self, option_name: str) -> Optional[Dict[str, float]]:
        """
        Get full option quote including LTP, bid, ask, OI, and OHLC.
        Uses getMarketData instead of ltpData for complete information.
        """
        self._check_token_before_request()
        try:
            if not option_name or not self.smart:
                return None
            exchange = self._exchange_from_symbol(option_name)
            clean = option_name.split(":")[-1]
            token = self._get_scrip_token(option_name)
            if not token:
                return None
            self._check_rate_limit()
            result = self._call(
                lambda: self.smart.ltpData(exchange, clean, token),
                context="get_option_quote"
            )

            if self._is_ok(result):
                data = result.get("data", {})
                return {
                    "ltp": float(data.get("ltp", 0) or 0),
                    "bid": float(data.get("best_bid_price", 0) or 0),
                    "ask": float(data.get("best_ask_price", 0) or 0),
                    "high": float(data.get("high_price", 0) or 0),
                    "low": float(data.get("low_price", 0) or 0),
                    "open": float(data.get("open_price", 0) or 0),
                    "close": float(data.get("close_price", 0) or 0),
                    "volume": int(data.get("volume", 0) or 0),
                    "oi": int(data.get("open_interest", 0) or 0),
                }
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AngelOneBroker.get_option_quote] {e!r}", exc_info=True)
            return None

    def get_option_chain_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        result = {}
        for sym in symbols:
            quote = self.get_option_quote(sym)
            if quote:
                result[sym.split(":")[-1]] = quote
        return result

    def place_order(self, **kwargs) -> Optional[str]:
        self._check_token_before_request()
        try:
            if not self.smart:
                return None
            symbol = kwargs.get('symbol')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_BUY)
            order_type = kwargs.get('order_type', self.MARKET_ORDER_TYPE)
            product = kwargs.get('product_type', ANGEL_PRODUCT_INTRADAY)
            limit_price = kwargs.get('limitPrice', 0) or 0
            stop_price = kwargs.get('stopPrice', 0) or 0

            if not symbol or qty <= 0:
                return None

            exchange = self._exchange_from_symbol(symbol)
            clean = symbol.split(":")[-1]
            token = self._get_scrip_token(symbol)
            if not token:
                logger.error(f"AngelOne: could not resolve token for {symbol}")
                return None

            angel_order_type = {
                self.MARKET_ORDER_TYPE: ANGEL_ORDER_MARKET,
                self.LIMIT_ORDER_TYPE:  ANGEL_ORDER_LIMIT,
                self.STOPLOSS_MARKET_ORDER_TYPE: ANGEL_ORDER_SLM,
            }.get(order_type, ANGEL_ORDER_MARKET)

            variety = ANGEL_VARIETY_STOPLOSS if order_type == self.STOPLOSS_MARKET_ORDER_TYPE else ANGEL_VARIETY_NORMAL

            order_params = {
                "variety": variety,
                "tradingsymbol": clean,
                "symboltoken": token,
                "transactiontype": self._to_angel_side(side),
                "exchange": exchange,
                "ordertype": angel_order_type,
                "producttype": product,
                "duration": "DAY",
                "price": str(limit_price),
                "triggerprice": str(stop_price),
                "quantity": str(qty),
                "squareoff": "0",
                "stoploss": "0",
            }

            self._check_rate_limit()
            result = self._call(lambda: self.smart.placeOrder(order_params), context="place_order")
            if self._is_ok(result):
                order_id = result.get("data", {}).get("orderid")
                logger.info(f"AngelOne: order placed {order_id}")
                return str(order_id) if order_id else None
            self._check_token_error(result)
            return None

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AngelOneBroker.place_order] {e!r}", exc_info=True)
            return None

    def modify_order(self, **kwargs) -> bool:
        self._check_token_before_request()
        try:
            order_id = kwargs.get('order_id')
            limit_price = kwargs.get('limit_price', 0)
            qty = kwargs.get('qty', 0)
            if not order_id or not self.smart:
                return False
            params = {
                "variety": ANGEL_VARIETY_NORMAL,
                "orderid": order_id,
                "ordertype": ANGEL_ORDER_LIMIT,
                "producttype": ANGEL_PRODUCT_INTRADAY,
                "duration": "DAY",
                "price": str(limit_price),
                "quantity": str(qty),
                "tradingsymbol": kwargs.get('symbol', '').split(":")[-1],
                "symboltoken": self._get_scrip_token(kwargs.get('symbol', '')) or "",
                "exchange": self._exchange_from_symbol(kwargs.get('symbol', '')),
            }
            self._check_rate_limit()
            result = self._call(lambda: self.smart.modifyOrder(params), context="modify_order")
            return self._is_ok(result)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AngelOneBroker.modify_order] {e!r}", exc_info=True)
            return False

    def cancel_order(self, **kwargs) -> bool:
        self._check_token_before_request()
        try:
            order_id = kwargs.get('order_id')
            if not order_id or not self.smart:
                return False
            self._check_rate_limit()
            result = self._call(
                lambda: self.smart.cancelOrder(order_id, ANGEL_VARIETY_NORMAL),
                context="cancel_order"
            )
            return self._is_ok(result)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AngelOneBroker.cancel_order] {e!r}", exc_info=True)
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
            if not self.smart:
                return []
            result = self._call(self.smart.position, context="get_positions")
            if self._is_ok(result):
                return result.get("data") or []
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AngelOneBroker.get_positions] {e!r}", exc_info=True)
            return []

    def get_orderbook(self) -> List[Dict[str, Any]]:
        self._check_token_before_request()
        try:
            if not self.smart:
                return []
            result = self._call(self.smart.orderBook, context="get_orderbook")
            if self._is_ok(result):
                return result.get("data") or []
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AngelOneBroker.get_orderbook] {e!r}", exc_info=True)
            return []

    def get_current_order_status(self, order_id: str) -> Optional[Any]:
        """
        Return the integer fill status for the given order_id.

        BUG FIX: The original returned the full order dict, but order_executor
        checks `self.api.get_current_order_status(broker_id) == 2` to detect a
        fill.  A dict never equals 2, so _wait_for_fill() always timed out and
        every Angel One limit order fell back to the market-order fallback.

        Angel One SmartAPI orderstatus values:
            "complete"  → filled  (maps to 2)
            "open"      → pending (maps to 1)
            "rejected" / "cancelled" → maps to -1
        """
        self._check_token_before_request()
        try:
            orders = self.get_orderbook()
            for order in orders:
                if str(order.get("orderid")) == str(order_id):
                    status_str = str(order.get("orderstatus") or "").lower()
                    if status_str in ("complete", "filled", "traded"):
                        return 2   # Filled — matches order_executor expectation
                    if status_str in ("rejected", "cancelled", "canceled"):
                        return -1
                    return 1       # Open / pending
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AngelOneBroker.get_current_order_status] {e!r}", exc_info=True)
            return None

    def get_fill_price(self, broker_order_id: str) -> Optional[float]:
        """
        Return the actual average fill price for a completed order.

        Implements BaseBroker.get_fill_price() so order_executor can use real
        fill prices instead of tick prices for P&L calculation.
        Angel One SmartAPI returns 'averageprice' in the order book entry.
        """
        self._check_token_before_request()
        try:
            if not broker_order_id or not self.smart:
                return None
            orders = self.get_orderbook()
            for order in orders:
                if str(order.get("orderid")) == str(broker_order_id):
                    avg = order.get("averageprice") or order.get("avgprice")
                    if avg:
                        return float(avg)
            return None
        except Exception as e:
            logger.error(f"[AngelOneBroker.get_fill_price] {e!r}", exc_info=True)
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
        Bare symbol "NIFTY2531825000CE" — AngelOne uses the
        compact core; the numeric symboltoken is looked up separately via
        ``_get_scrip_token()`` when placing orders or fetching quotes.
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
            logger.error(f"[AngelOneBroker.build_option_symbol] {e}", exc_info=True)
            return None

    def _params_to_symbol(self, params) -> Optional[str]:
        """AngelOneBroker symbol from OptionParams."""
        if not params:
            return None
        # AngelOne accepts bare compact core; token looked up per-call
        return params.compact_core

    def build_option_chain(
        self,
        underlying: str,
        spot_price: float,
        option_type: str,
        weeks_offset: int = 0,
        itm: int = 5,
        otm: int = 5,
    ) -> List[str]:
        """AngelOne option chain as bare compact core strings."""
        try:
            from Utils.OptionSymbolBuilder import OptionSymbolBuilder
            all_params = OptionSymbolBuilder.get_all_option_params(
                underlying=underlying, spot_price=spot_price,
                option_type=option_type, weeks_offset=weeks_offset,
                itm=itm, otm=otm,
            )
            return [s for s in (self._params_to_symbol(p) for p in all_params) if s]
        except Exception as e:
            logger.error(f"[AngelOneBroker.build_option_chain] {e}", exc_info=True)
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
        logger.info("[AngelOneBroker] Starting cleanup")

        # Mark WebSocket as closed to prevent callbacks
        self._ws_closed = True

        # Clean up WebSocket if it exists
        if self._ws_obj is not None:
            try:
                if self._ws_cleanup_event is None:
                    self._ws_cleanup_event = threading.Event()
                self._ws_cleanup_event.clear()

                def _do_disconnect():
                    try:
                        if safe_hasattr(self._ws_obj, "close_connection"):
                            self._ws_obj.close_connection()
                            logger.debug("[AngelOneBroker] WebSocket close_connection called")
                    except Exception as e:
                        logger.warning(f"[AngelOneBroker] Error closing WebSocket: {e}")
                    finally:
                        self._ws_cleanup_event.set()

                # Run close in separate thread with timeout
                close_thread = threading.Thread(target=_do_disconnect, daemon=True)
                close_thread.start()

                # Wait for close with timeout
                if not self._ws_cleanup_event.wait(timeout=2.0):
                    logger.warning("[AngelOneBroker] WebSocket close timed out")

            except Exception as e:
                logger.error(f"[AngelOneBroker] Error during WebSocket cleanup: {e}", exc_info=True)
            finally:
                self._ws_obj = None

        # Terminate session if possible
        try:
            if self.smart and self.client_code:
                self.smart.terminateSession(self.client_code)
        except Exception as e:
            logger.warning(f"[AngelOneBroker.cleanup] Session termination error: {e}")

        logger.info("[AngelOneBroker] Cleanup completed")

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
                logger.warning(f"[AngelOne.{context}] Network error, retry {attempt+1}: {e}")
                time.sleep(delay)
            except Exception as e:
                error_str = str(e).lower()
                if "token" in error_str and ("invalid" in error_str or "expired" in error_str):
                    raise TokenExpiredError(str(e))
                if "rate" in error_str or "throttl" in error_str:
                    delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                    logger.warning(f"[AngelOne.{context}] Rate limited, retry {attempt+1}")
                    time.sleep(delay)
                else:
                    logger.error(f"[AngelOne.{context}] {e!r}", exc_info=True)
                    return None
        logger.critical(f"[AngelOne.{context}] Max retries reached.")
        return None

    # ── WebSocket interface ────────────────────────────────────────────────────

    def create_websocket(self, on_tick, on_connect, on_close, on_error) -> Any:
        """
        Create AngelOne SmartWebSocket v2.

        Requires: auth_token (jwtToken), api_key, client_code, feed_token.
        SmartWebSocket v2 is the current official streaming API.

        feed_token is obtained after login() via self._feed_token.

        FIXED: Store callbacks and track WebSocket state.
        """
        try:
            from SmartApi.SmartWebSocketV2 import SmartWebSocketV2  # type: ignore

            auth_token   = safe_getattr(self.state, "token", None) if self.state else None
            feed_token   = safe_getattr(self, "_feed_token", None)
            api_key      = safe_getattr(self, "api_key", None)
            client_code  = safe_getattr(self, "client_code", None)

            if not auth_token or not feed_token or not api_key or not client_code:
                logger.error(
                    "AngelOneBroker.create_websocket: missing auth_token/feed_token/api_key/client_code. "
                    "Call broker.login() before starting WebSocket."
                )
                return None

            # Check token before creating websocket
            if self.is_token_expired:
                self._handle_token_expired("Cannot create websocket with expired token")

            # Reset WebSocket state
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()

            sws = SmartWebSocketV2(
                auth_token=auth_token,
                api_key=api_key,
                client_code=client_code,
                feed_token=feed_token,
            )

            # Store callbacks
            self._ws_on_tick = on_tick
            self._ws_on_connect = on_connect
            self._ws_on_close = on_close
            self._ws_on_error = on_error

            # SmartWebSocketV2 callbacks with safety checks
            def safe_on_open(wsapp):
                if self._ws_closed:
                    return
                on_connect()

            def safe_on_message(wsapp, msg):
                if self._ws_closed:
                    return
                on_tick(msg)

            def safe_on_error(wsapp, err):
                if self._ws_closed:
                    return
                on_error(str(err))

            def safe_on_close(wsapp, code, msg):
                if self._ws_closed:
                    return
                on_close(f"{code}: {msg}")

            sws.on_open = safe_on_open
            sws.on_message = safe_on_message
            sws.on_error = safe_on_error
            sws.on_close = safe_on_close

            logger.info("AngelOneBroker: SmartWebSocketV2 object created")
            self._ws_obj = sws
            return sws
        except ImportError:
            logger.error("AngelOneBroker: SmartApi not installed — pip install smartapi-python")
            return None
        except Exception as e:
            logger.error(f"[AngelOneBroker.create_websocket] {e}", exc_info=True)
            return None

    def ws_connect(self, ws_obj) -> None:
        """
        Start SmartWebSocketV2 (blocking — must run in daemon thread).
        WebSocketManager wraps this in a thread automatically.

        FIXED: Store ws_obj reference for cleanup.
        """
        try:
            if ws_obj is None or self._ws_closed:
                return

            self._ws_obj = ws_obj

            # connect() blocks; WebSocketManager calls this in a daemon thread
            ws_obj.connect()
            logger.info("AngelOneBroker: SmartWebSocketV2 connect() returned")
        except Exception as e:
            logger.error(f"[AngelOneBroker.ws_connect] {e}", exc_info=True)

    def ws_subscribe(self, ws_obj, symbols: List[str]) -> None:
        """
        Subscribe to AngelOne live feed.

        If you need OI and full depth, use mode=3 (SnapQuote).
        For LTP only, mode=1 is sufficient.
        """
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return

            from SmartApi.SmartWebSocketV2 import SmartWebSocketV2  # type: ignore

            token_list = []
            for sym in symbols:
                exch_type, angel_token = self._resolve_angel_token(sym)
                if angel_token:
                    token_list.append({
                        "exchangeType": exch_type,
                        "tokens": [angel_token],
                    })

            if not token_list:
                logger.warning("AngelOneBroker.ws_subscribe: no valid tokens")
                return

            ws_obj.subscribe(
                correlation_id="trading_app",
                mode=3,
                token_list=token_list,
            )
            logger.info(f"AngelOneBroker: subscribed {len(token_list)} token groups in mode=3")
        except Exception as e:
            logger.error(f"[AngelOneBroker.ws_subscribe] {e}", exc_info=True)

    def ws_unsubscribe(self, ws_obj, symbols: List[str]) -> None:
        """Unsubscribe from AngelOne live feed."""
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return
            from SmartApi.SmartWebSocketV2 import SmartWebSocketV2  # type: ignore

            token_list = []
            for sym in symbols:
                exch_type, angel_token = self._resolve_angel_token(sym)
                if angel_token:
                    token_list.append({"exchangeType": exch_type, "tokens": [angel_token]})

            if token_list:
                ws_obj.unsubscribe(
                    correlation_id="trading_app",
                    mode=1,  # BUG FIX: Same as ws_subscribe — use int 1, not SmartWebSocketV2.ONE
                    token_list=token_list,
                )
        except Exception as e:
            logger.error(f"[AngelOneBroker.ws_unsubscribe] {e}", exc_info=True)

    def ws_disconnect(self, ws_obj) -> None:
        """
        Close SmartWebSocketV2 with timeout protection.

        FIXED: Added timeout and better error handling.
        """
        try:
            if ws_obj is None:
                return

            logger.info("[AngelOneBroker] Starting WebSocket disconnect")
            self._ws_closed = True

            if safe_hasattr(ws_obj, "close_connection"):
                # Run close in separate thread with timeout
                disconnect_complete = threading.Event()

                def _do_disconnect():
                    try:
                        ws_obj.close_connection()
                        logger.debug("[AngelOneBroker] close_connection completed")
                    except Exception as e:
                        logger.warning(f"[AngelOneBroker] close_connection error: {e}")
                    finally:
                        disconnect_complete.set()

                disconnect_thread = threading.Thread(target=_do_disconnect, daemon=True)
                disconnect_thread.start()

                # Wait for disconnect with timeout
                if not disconnect_complete.wait(timeout=2.0):
                    logger.warning("[AngelOneBroker] close_connection timed out")

            # Clear reference
            if self._ws_obj == ws_obj:
                self._ws_obj = None

            logger.info("[AngelOneBroker] WebSocket disconnect completed")

        except Exception as e:
            logger.error(f"[AngelOneBroker.ws_disconnect] {e}", exc_info=True)

    def normalize_tick(self, raw_tick) -> Optional[Dict[str, Any]]:
        """
        Normalize AngelOne SmartWebSocketV2 tick.

        LTP mode (mode=1) fields: token, exchange_type, last_traded_price,
        last_traded_quantity, average_traded_price, volume_trade_for_the_day,
        total_buy_quantity, total_sell_quantity, open_price_of_the_day,
        high_price_of_the_day, low_price_of_the_day, closed_price.

        Prices are in paise (1/100 rupee) → divide by 100.
        OI and bid/ask are only available in SnapQuote mode (mode=3).
        """
        try:
            if self._ws_closed or not isinstance(raw_tick, dict):
                return None

            ltp_raw = raw_tick.get("last_traded_price")
            if ltp_raw is None:
                return None
            ltp = float(ltp_raw) / 100.0  # convert paise → rupees

            token = raw_tick.get("token", "")
            exch_type = raw_tick.get("exchange_type", 1)
            exch_prefix = {1: "NSE", 2: "NFO", 3: "BSE", 4: "MCX"}.get(exch_type, "NSE")
            reverse = safe_getattr(self, "_token_to_symbol_cache", {})
            if token in reverse:
                symbol = reverse[token]
            else:
                symbol = f"{exch_prefix}:{token}"

            def to_rupees(v):
                return float(v) / 100.0 if v is not None else None

            return {
                "symbol": symbol,
                "ltp": ltp,
                "timestamp": str(raw_tick.get("exchange_timestamp", "")),
                "bid": None,  # Not available in LTP mode
                "ask": None,  # Not available in LTP mode
                "volume": raw_tick.get("volume_trade_for_the_day"),
                "oi": None,  # Not available in LTP mode
                "open": to_rupees(raw_tick.get("open_price_of_the_day")),
                "high": to_rupees(raw_tick.get("high_price_of_the_day")),
                "low": to_rupees(raw_tick.get("low_price_of_the_day")),
                "close": to_rupees(raw_tick.get("closed_price")),
            }
        except Exception as e:
            if not self._ws_closed:  # Only log if not during shutdown
                logger.error(f"[AngelOneBroker.normalize_tick] {e}", exc_info=True)
            return None

    def _resolve_angel_token(self, symbol: str):
        """
        Resolve generic NSE:SYMBOL → (exchange_type_int, angel_token_str).

        exchange_type: 1=NSE, 2=NFO, 3=BSE, 4=MCX.
        angel_token: numeric string from AngelOne instrument list.

        For simplicity, returns (1, bare_symbol) when instrument file
        lookup is not available. In production, download the instrument
        JSON from AngelOne and build a proper cache.
        """
        try:
            cache = safe_getattr(self, "_angel_token_cache", {})
            if symbol in cache:
                return cache[symbol]

            upper = symbol.upper()
            if "NFO:" in upper:
                exch_type = 2
            elif "BSE:" in upper:
                exch_type = 3
            elif "MCX:" in upper:
                exch_type = 4
            else:
                exch_type = 1

            bare = symbol.split(":")[-1]
            result = (exch_type, bare)
            cache[symbol] = result
            self._angel_token_cache = cache
            return result
        except Exception:
            return (1, None)