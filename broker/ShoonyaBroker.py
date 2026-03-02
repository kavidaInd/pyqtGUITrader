"""
brokers/ShoonyaBroker.py
========================
Shoonya / Finvasia broker implementation of BaseBroker.

Uses the official Shoonya REST API via NorenRestApiPy (or ShoonyaApi-py).

Prerequisites:
    pip install NorenRestApiPy
    # or clone https://github.com/Shoonya-Dev/ShoonyaApi-py and install

Authentication (TOTP-based, no browser OAuth):
    BrokerageSetting fields:
        client_id    → Shoonya User ID  (e.g. FA12345)
        secret_key   → SHA256 hash of password  OR plain password
                       (Shoonya expects SHA256(password) — see docs)
        redirect_uri → TOTP secret (base32) OR one-time OTP string

    Credential notes:
        - vendor_code and api_secret are needed for login.
          Store vendor_code in client_id after the user ID  (e.g. "FA12345|VENDOR")
          or provide it separately via broker_setting.extra fields.
        - For simplest setup: store  user_id as client_id,
          password SHA256 as secret_key, TOTP secret as redirect_uri.

    Call broker.login() each morning before trading.

API docs: https://www.shoonya.com/api-documentation
SDK:      pip install NorenRestApiPy

FIXED: Added proper WebSocket cleanup with timeout and state tracking.
"""

import hashlib
import logging
import time
import random
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable

import pandas as pd
from requests.exceptions import Timeout, ConnectionError

from broker.BaseBroker import BaseBroker, TokenExpiredError
from db.connector import get_db
from db.crud import tokens

try:
    from NorenRestApiPy.NorenApi import NorenApi
    SHOONYA_AVAILABLE = True
except ImportError:
    try:
        # Fallback: try the older package name
        from api_helper import ShoonyaApiPy as NorenApi  # type: ignore
        SHOONYA_AVAILABLE = True
    except ImportError:
        SHOONYA_AVAILABLE = False

import pyotp as _pyotp_shoonya  # noqa – lightweight, always available if smartapi is installed

logger = logging.getLogger(__name__)

# ── Shoonya exchange / product constants ─────────────────────────────────────
SHOONYA_NSE  = "NSE"
SHOONYA_NFO  = "NFO"
SHOONYA_BSE  = "BSE"
SHOONYA_MCX  = "MCX"

SHOONYA_PRODUCT_INTRADAY = "I"
SHOONYA_PRODUCT_MARGIN   = "M"
SHOONYA_PRODUCT_CNC      = "C"
SHOONYA_PRODUCT_BO       = "B"   # Bracket order

SHOONYA_ORDER_MARKET = "MKT"
SHOONYA_ORDER_LIMIT  = "LMT"
SHOONYA_ORDER_SL     = "SL-LMT"
SHOONYA_ORDER_SLM    = "SL-MKT"

SHOONYA_BUY  = "B"
SHOONYA_SELL = "S"

SHOONYA_RETENTION_DAY = "DAY"

# Interval mapping: generic -> Shoonya
SHOONYA_INTERVAL_MAP = {
    "1":  "1",
    "2":  "2",
    "3":  "3",
    "5":  "5",
    "10": "10",
    "15": "15",
    "30": "30",
    "60": "60",
    "D":  "D",
    "day": "D",
}


class ShoonyaBroker(BaseBroker):
    """
    Shoonya (Finvasia) broker implementation.

    Credential storage in BrokerageSetting:
        client_id   → "user_id|vendor_code"  (pipe-separated)
                       e.g.  "FA12345|FA12345_U"
        secret_key  → Password in plain text (broker will hash it) OR pre-hashed SHA256
        redirect_uri → TOTP secret (base32) for auto-TOTP generation

    FIXED: Added proper WebSocket cleanup with timeout and state tracking.
    """

    SHOONYA_URL = "https://api.shoonya.com/NorenWClientTP/"
    WS_URL      = "wss://api.shoonya.com/NorenWSTP/"

    def __init__(self, state, broker_setting=None):
        self._safe_defaults_init()
        try:
            if not SHOONYA_AVAILABLE:
                raise ImportError(
                    "NorenRestApiPy is not installed.\n"
                    "Run: pip install NorenRestApiPy\n"
                    "or clone https://github.com/Shoonya-Dev/ShoonyaApi-py"
                )
            self.state = state

            if broker_setting is None:
                raise ValueError("BrokerageSetting must be provided for ShoonyaBroker.")

            # Parse "user_id|vendor_code" from client_id
            client_id_raw = getattr(broker_setting, 'client_id', '') or ''
            if "|" in client_id_raw:
                self.user_id, self.vendor_code = client_id_raw.split("|", 1)
            else:
                self.user_id = client_id_raw
                self.vendor_code = client_id_raw  # fallback

            self.password    = getattr(broker_setting, 'secret_key', '') or ''
            self.totp_secret = getattr(broker_setting, 'redirect_uri', '') or ''

            if not self.user_id:
                raise ValueError("Shoonya user_id is required.")

            # Initialize API
            self.api = NorenApi(host=self.SHOONYA_URL, websocket=self.WS_URL)

            # Load saved token and try to restore session
            saved_token = self._load_token_from_db()
            if saved_token:
                self.state.token = saved_token
                self.api.susertoken = saved_token          # inject saved token
                self.api.userid = self.user_id
                logger.info("ShoonyaBroker: restored token from DB")
            else:
                logger.warning("ShoonyaBroker: no token found — call broker.login()")

            # WebSocket cleanup tracking
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()
            self._ws_api = None

            logger.info(f"ShoonyaBroker initialized for user {self.user_id}")

        except Exception as e:
            logger.critical(f"[ShoonyaBroker.__init__] {e}", exc_info=True)
            raise

    @property
    def broker_type(self) -> str:
        return "shoonya"

    def _safe_defaults_init(self):
        self.state = None
        self.user_id = None
        self.vendor_code = None
        self.password = None
        self.totp_secret = None
        self.api = None
        self._last_request_time = 0
        self._request_count = 0
        self._symbol_token_cache: Dict[str, str] = {}

        # WebSocket cleanup tracking
        self._ws_closed = False
        self._ws_cleanup_event = None
        self._ws_api = None
        self._ws_on_tick = None
        self._ws_on_connect = None
        self._ws_on_close = None
        self._ws_on_error = None

    # ── Authentication ────────────────────────────────────────────────────────

    def login(self, totp: Optional[str] = None) -> bool:
        """
        Generate a new Shoonya session.

        Args:
            totp: 6-digit TOTP code. If None, auto-generated from totp_secret.

        Returns:
            True on success
        """
        try:
            if totp is None and self.totp_secret:
                totp = _pyotp_shoonya.TOTP(self.totp_secret).now()
            if not totp:
                raise ValueError("TOTP is required. Store TOTP secret in redirect_uri.")

            # Shoonya expects SHA256 of password
            pwd_hash = hashlib.sha256(self.password.encode()).hexdigest()

            ret = self.api.login(
                userid=self.user_id,
                password=pwd_hash,
                twoFA=totp,
                vendor_code=self.vendor_code,
                api_secret=self._get_api_key(),
                imei="algo-trader",
            )

            if ret and ret.get("stat") == "Ok":
                token = ret.get("susertoken")
                self.state.token = token

                expires_at = (datetime.now() + timedelta(hours=8)).isoformat()
                db = get_db()
                tokens.save_token(token, "", expires_at=expires_at, db=db)
                logger.info("ShoonyaBroker: session generated successfully")
                return True
            else:
                logger.error(f"ShoonyaBroker login failed: {ret}")
                return False

        except Exception as e:
            logger.error(f"[ShoonyaBroker.login] {e}", exc_info=True)
            return False

    def _get_api_key(self) -> str:
        """
        For Shoonya, api_secret is SHA256(user_id + api_key).
        Since we store the api_key separately, we compute the hash here.
        For simplicity, users can store pre-computed api_secret or we
        store the raw api_key in an extended field.
        """
        # If vendor_code looks like an API key, use it
        return self.vendor_code or ""

    def _load_token_from_db(self) -> Optional[str]:
        try:
            db = get_db()
            token_data = tokens.get(db)
            if token_data and token_data.get("access_token"):
                return token_data["access_token"]
            return None
        except Exception as e:
            logger.error(f"[ShoonyaBroker._load_token_from_db] {e}", exc_info=True)
            return None

    # ── Rate limiting ─────────────────────────────────────────────────────────

    def _check_rate_limit(self):
        current = time.time()
        diff = current - self._last_request_time
        if diff < 1.0:
            self._request_count += 1
            if self._request_count > self.MAX_REQUESTS_PER_SECOND:
                time.sleep(1.0 - diff + 0.1)
                self._request_count = 0
                self._last_request_time = time.time()
        else:
            self._request_count = 1
            self._last_request_time = current

    # ── Symbol helpers ────────────────────────────────────────────────────────

    def _get_token(self, symbol: str, exchange: str = SHOONYA_NFO) -> Optional[str]:
        """Look up the Shoonya numeric token for a symbol."""
        cache_key = f"{exchange}:{symbol}"
        if cache_key in self._symbol_token_cache:
            return self._symbol_token_cache[cache_key]
        try:
            result = self._call(
                lambda: self.api.searchscrip(exchange=exchange, searchtext=symbol),
                context="search_scrip"
            )
            if result and result.get("stat") == "Ok":
                values = result.get("values", [])
                if values:
                    token = values[0].get("token")
                    self._symbol_token_cache[cache_key] = token
                    return token
            return None
        except Exception as e:
            logger.error(f"[ShoonyaBroker._get_token] {e}", exc_info=True)
            return None

    @staticmethod
    def _exchange_from_symbol(symbol: str) -> str:
        s = symbol.upper()
        if s.startswith("NFO:") or "CE" in s or "PE" in s or "FUT" in s:
            return SHOONYA_NFO
        if s.startswith("BSE:"):
            return SHOONYA_BSE
        return SHOONYA_NSE

    @staticmethod
    def _clean_symbol(symbol: str) -> str:
        return symbol.split(":")[-1]

    @staticmethod
    def _to_shoonya_interval(interval: str) -> str:
        return SHOONYA_INTERVAL_MAP.get(str(interval), "1")

    @staticmethod
    def _to_shoonya_side(side: int) -> str:
        return SHOONYA_BUY if side == BaseBroker.SIDE_BUY else SHOONYA_SELL

    @staticmethod
    def _is_ok(response: Any) -> bool:
        if isinstance(response, dict):
            return response.get("stat") == "Ok"
        return False

    def _check_token_error(self, response: Any):
        if isinstance(response, dict):
            msg = str(response.get("emsg", "")).lower()
            if "session" in msg or "token" in msg or "login" in msg or "invalid" in msg:
                raise TokenExpiredError(response.get("emsg", "Session expired"))

    # ── BaseBroker implementation ─────────────────────────────────────────────

    def get_profile(self) -> Optional[Dict]:
        try:
            if not self.api:
                return None
            result = self._call(
                lambda: self.api.get_user_details(),
                context="get_profile"
            )
            return result if self._is_ok(result) else None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[ShoonyaBroker.get_profile] {e!r}", exc_info=True)
            return None

    def get_balance(self, capital_reserve: float = 0.0) -> float:
        try:
            if not self.api:
                return 0.0
            result = self._call(
                lambda: self.api.get_limits(
                    product_type=SHOONYA_PRODUCT_MARGIN,
                    segment=SHOONYA_NSE,
                    exchange=SHOONYA_NSE
                ),
                context="get_balance"
            )
            if self._is_ok(result):
                available = float(result.get("cash", 0.0))
                if capital_reserve > 0:
                    available = available * (1 - capital_reserve / 100)
                return available
            return 0.0
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[ShoonyaBroker.get_balance] {e!r}", exc_info=True)
            return 0.0

    def get_history(self, symbol: str, interval: str = "2", length: int = 400):
        try:
            if not symbol or not self.api:
                return None
            exchange = self._exchange_from_symbol(symbol)
            clean = self._clean_symbol(symbol)
            token = self._get_token(clean, exchange)
            if not token:
                return None
            to_epoch = int(time.time())
            from_epoch = to_epoch - (4 * 86400)
            shoonya_interval = self._to_shoonya_interval(interval)
            self._check_rate_limit()
            result = self._call(
                lambda: self.api.get_time_price_series(
                    exchange=exchange, token=token,
                    starttime=from_epoch, endtime=to_epoch,
                    interval=shoonya_interval
                ),
                context="get_history"
            )
            if result and isinstance(result, list):
                df = pd.DataFrame(result)
                if "ssboe" in df.columns:
                    df = df.rename(columns={
                        "ssboe": "time", "into": "open", "inth": "high",
                        "intl": "low", "intc": "close", "intv": "volume"
                    })
                return df.tail(length)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[ShoonyaBroker.get_history] {e!r}", exc_info=True)
            return None

    def get_history_for_timeframe(self, symbol: str, interval: str, days: int = 30):
        try:
            if not symbol or not self.api:
                return None
            exchange = self._exchange_from_symbol(symbol)
            clean = self._clean_symbol(symbol)
            token = self._get_token(clean, exchange)
            if not token:
                return None
            fetch_days = max(days, 60) if interval in ["15","30","60"] else (
                max(days, 120) if interval in ["120","240"] else days
            )
            to_epoch = int(time.time())
            from_epoch = to_epoch - (fetch_days * 86400)
            shoonya_interval = self._to_shoonya_interval(interval)
            self._check_rate_limit()
            result = self._call(
                lambda: self.api.get_time_price_series(
                    exchange=exchange, token=token,
                    starttime=from_epoch, endtime=to_epoch,
                    interval=shoonya_interval
                ),
                context="get_history_for_timeframe"
            )
            if result and isinstance(result, list):
                df = pd.DataFrame(result)
                if "ssboe" in df.columns:
                    df = df.rename(columns={
                        "ssboe": "time", "into": "open", "inth": "high",
                        "intl": "low", "intc": "close", "intv": "volume"
                    })
                    df["time"] = pd.to_datetime(df["time"], unit="s")
                return df
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[ShoonyaBroker.get_history_for_timeframe] {e!r}", exc_info=True)
            return None

    def get_option_current_price(self, option_name: str) -> Optional[float]:
        quote = self.get_option_quote(option_name)
        return quote.get("ltp") if quote else None

    def get_option_quote(self, option_name: str) -> Optional[Dict[str, float]]:
        try:
            if not option_name or not self.api:
                return None
            exchange = self._exchange_from_symbol(option_name)
            clean = self._clean_symbol(option_name)
            token = self._get_token(clean, exchange)
            if not token:
                return None
            self._check_rate_limit()
            result = self._call(
                lambda: self.api.get_quotes(exchange=exchange, token=token),
                context="get_option_quote"
            )
            if self._is_ok(result):
                return {
                    "ltp":    float(result.get("lp", 0) or 0),
                    "bid":    float(result.get("bp1", 0) or 0),
                    "ask":    float(result.get("sp1", 0) or 0),
                    "high":   float(result.get("h", 0) or 0),
                    "low":    float(result.get("l", 0) or 0),
                    "open":   float(result.get("o", 0) or 0),
                    "close":  float(result.get("c", 0) or 0),
                    "volume": int(result.get("v", 0) or 0),
                    "oi":     int(result.get("oi", 0) or 0),
                }
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[ShoonyaBroker.get_option_quote] {e!r}", exc_info=True)
            return None

    def get_option_chain_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        result = {}
        for sym in symbols:
            quote = self.get_option_quote(sym)
            if quote:
                result[self._clean_symbol(sym)] = quote
        return result

    def place_order(self, **kwargs) -> Optional[str]:
        try:
            if not self.api:
                return None
            symbol = kwargs.get('symbol')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_BUY)
            order_type = kwargs.get('order_type', self.MARKET_ORDER_TYPE)
            product = kwargs.get('product_type', SHOONYA_PRODUCT_INTRADAY)
            limit_price = float(kwargs.get('limitPrice', 0) or 0)
            stop_price  = float(kwargs.get('stopPrice', 0) or 0)

            if not symbol or qty <= 0:
                return None

            exchange = self._exchange_from_symbol(symbol)
            clean = self._clean_symbol(symbol)
            token = self._get_token(clean, exchange)
            if not token:
                return None

            shoonya_order_type = {
                self.MARKET_ORDER_TYPE:          SHOONYA_ORDER_MARKET,
                self.LIMIT_ORDER_TYPE:           SHOONYA_ORDER_LIMIT,
                self.STOPLOSS_MARKET_ORDER_TYPE: SHOONYA_ORDER_SLM,
            }.get(order_type, SHOONYA_ORDER_MARKET)

            self._check_rate_limit()
            result = self._call(
                lambda: self.api.place_order(
                    buy_or_sell=self._to_shoonya_side(side),
                    product_type=product,
                    exchange=exchange,
                    tradingsymbol=clean,
                    quantity=qty,
                    discloseqty=0,
                    price_type=shoonya_order_type,
                    price=limit_price,
                    trigger_price=stop_price if stop_price else None,
                    retention=SHOONYA_RETENTION_DAY,
                    remarks="algotrade",
                ),
                context="place_order"
            )
            if self._is_ok(result):
                order_id = result.get("norenordno")
                logger.info(f"ShoonyaBroker: order placed {order_id}")
                return str(order_id) if order_id else None
            self._check_token_error(result)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[ShoonyaBroker.place_order] {e!r}", exc_info=True)
            return None

    def modify_order(self, **kwargs) -> bool:
        try:
            order_id = kwargs.get('order_id')
            limit_price = float(kwargs.get('limit_price', 0) or 0)
            qty = int(kwargs.get('qty', 0))
            if not order_id or not self.api:
                return False
            self._check_rate_limit()
            result = self._call(
                lambda: self.api.modify_order(
                    orderno=order_id,
                    exchange=self._exchange_from_symbol(kwargs.get('symbol', '')),
                    tradingsymbol=self._clean_symbol(kwargs.get('symbol', '')),
                    newquantity=qty,
                    newprice_type=SHOONYA_ORDER_LIMIT,
                    newprice=limit_price,
                ),
                context="modify_order"
            )
            return self._is_ok(result)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[ShoonyaBroker.modify_order] {e!r}", exc_info=True)
            return False

    def cancel_order(self, **kwargs) -> bool:
        try:
            order_id = kwargs.get('order_id')
            if not order_id or not self.api:
                return False
            self._check_rate_limit()
            result = self._call(
                lambda: self.api.cancel_order(orderno=order_id),
                context="cancel_order"
            )
            return self._is_ok(result)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[ShoonyaBroker.cancel_order] {e!r}", exc_info=True)
            return False

    def exit_position(self, **kwargs) -> bool:
        symbol = kwargs.get('symbol')
        qty = kwargs.get('qty', 0)
        current_side = kwargs.get('side', self.SIDE_BUY)
        exit_side = self.SIDE_SELL if current_side == self.SIDE_BUY else self.SIDE_BUY
        if not symbol or qty <= 0:
            return False
        return self.place_order(symbol=symbol, qty=qty, side=exit_side,
                                order_type=self.MARKET_ORDER_TYPE) is not None

    def add_stoploss(self, **kwargs) -> bool:
        kwargs['order_type'] = self.STOPLOSS_MARKET_ORDER_TYPE
        kwargs.setdefault('side', self.SIDE_SELL)
        return self.place_order(**kwargs) is not None

    def remove_stoploss(self, **kwargs) -> bool:
        return self.cancel_order(**kwargs)

    def sell_at_current(self, **kwargs) -> bool:
        return self.place_order(order_type=self.MARKET_ORDER_TYPE,
                                side=self.SIDE_SELL, **kwargs) is not None

    def get_positions(self) -> List[Dict[str, Any]]:
        try:
            if not self.api:
                return []
            result = self._call(self.api.get_positions, context="get_positions")
            if isinstance(result, list):
                return result
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[ShoonyaBroker.get_positions] {e!r}", exc_info=True)
            return []

    def get_orderbook(self) -> List[Dict[str, Any]]:
        try:
            if not self.api:
                return []
            result = self._call(self.api.get_order_book, context="get_orderbook")
            if isinstance(result, list):
                return result
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[ShoonyaBroker.get_orderbook] {e!r}", exc_info=True)
            return []

    def get_current_order_status(self, order_id: str) -> Optional[Any]:
        try:
            orders = self.get_orderbook()
            for order in orders:
                if str(order.get("norenordno")) == str(order_id):
                    return order
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[ShoonyaBroker.get_current_order_status] {e!r}", exc_info=True)
            return None

    def is_connected(self) -> bool:
        try:
            return self.get_profile() is not None
        except TokenExpiredError:
            return False
        except Exception:
            return False

    def cleanup(self) -> None:
        """Clean up resources including WebSocket connection."""
        logger.info("[ShoonyaBroker] Starting cleanup")

        # Mark WebSocket as closed to prevent callbacks
        self._ws_closed = True

        # Clean up WebSocket if it exists
        if self._ws_api is not None:
            try:
                # Try to close WebSocket with timeout
                self._ws_cleanup_event.clear()

                def _do_disconnect():
                    try:
                        if hasattr(self._ws_api, "close_websocket"):
                            self._ws_api.close_websocket()
                            logger.debug("[ShoonyaBroker] close_websocket called")
                    except Exception as e:
                        logger.warning(f"[ShoonyaBroker] Error closing WebSocket: {e}")
                    finally:
                        self._ws_cleanup_event.set()

                # Run close in separate thread with timeout
                close_thread = threading.Thread(target=_do_disconnect, daemon=True)
                close_thread.start()

                # Wait for close with timeout
                if not self._ws_cleanup_event.wait(timeout=2.0):
                    logger.warning("[ShoonyaBroker] WebSocket close timed out")

            except Exception as e:
                logger.error(f"[ShoonyaBroker] Error during WebSocket cleanup: {e}", exc_info=True)
            finally:
                self._ws_api = None

        # Logout from API
        try:
            if self.api:
                self.api.logout()
        except Exception as e:
            logger.warning(f"[ShoonyaBroker.cleanup] Logout error: {e}")

        # Clear callbacks
        self._ws_on_tick = None
        self._ws_on_connect = None
        self._ws_on_close = None
        self._ws_on_error = None

        logger.info("[ShoonyaBroker] Cleanup completed")

    # ── Internal call wrapper ─────────────────────────────────────────────────

    def _call(self, func: Callable, context: str = "",
              max_retries: int = 3, base_delay: int = 1):
        for attempt in range(max_retries):
            try:
                self._check_rate_limit()
                response = func()
                if isinstance(response, dict):
                    self._check_token_error(response)
                return response
            except TokenExpiredError:
                raise
            except (Timeout, ConnectionError) as e:
                delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning(f"[Shoonya.{context}] Network error, retry {attempt+1}: {e}")
                time.sleep(delay)
            except Exception as e:
                error_str = str(e).lower()
                if "session" in error_str or ("token" in error_str and "invalid" in error_str):
                    raise TokenExpiredError(str(e))
                logger.error(f"[Shoonya.{context}] {e!r}", exc_info=True)
                return None
        logger.critical(f"[Shoonya.{context}] Max retries reached.")
        return None

    # ── WebSocket interface ────────────────────────────────────────────────────

    def create_websocket(self, on_tick, on_connect, on_close, on_error) -> Any:
        """
        Create Shoonya (NorenApi) WebSocket.

        NorenApi has built-in WebSocket support via api.start_websocket().
        We store callbacks and use them in ws_connect().
        Shoonya symbols use "NSE|NIFTY-INDEX" or "NFO|TOKEN" format.

        FIXED: Added state tracking and stored callbacks.
        """
        try:
            if not self.api:
                logger.error("ShoonyaBroker.create_websocket: api not initialized — login first")
                return None

            # Reset WebSocket state
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()

            # Store callbacks for ws_connect
            self._ws_on_tick    = on_tick
            self._ws_on_connect = on_connect
            self._ws_on_close   = on_close
            self._ws_on_error   = on_error
            self._ws_api = self.api

            logger.info("ShoonyaBroker: WebSocket callbacks stored (connect via ws_connect)")
            return {"__shoonya_api__": self.api, "__ws_active__": True}
        except Exception as e:
            logger.error(f"[ShoonyaBroker.create_websocket] {e}", exc_info=True)
            return None

    def ws_connect(self, ws_obj) -> None:
        """
        Start Shoonya WebSocket via NorenApi.start_websocket().

        NorenApi WebSocket is initiated by calling api.start_websocket()
        with the open/subscribe/message/error callbacks.

        FIXED: Added safety checks.
        """
        try:
            if ws_obj is None or self._ws_closed:
                return
            api = ws_obj.get("__shoonya_api__") if isinstance(ws_obj, dict) else self.api
            if api is None:
                logger.error("ShoonyaBroker.ws_connect: no api object")
                return

            def _on_open():
                if self._ws_closed:
                    return
                logger.info("ShoonyaBroker: WebSocket opened")
                self._ws_on_connect()

            def _on_message(msg):
                if self._ws_closed:
                    return
                self._ws_on_tick(msg)

            def _on_error(msg):
                if self._ws_closed:
                    return
                logger.error(f"ShoonyaBroker WS error: {msg}")
                self._ws_on_error(str(msg))

            def _on_close():
                if self._ws_closed:
                    return
                logger.info("ShoonyaBroker: WebSocket closed")
                self._ws_on_close("connection closed")

            api.start_websocket(
                order_update_callback=_on_message,
                subscribe_callback=_on_message,
                socket_open_callback=_on_open,
                socket_close_callback=_on_close,
                socket_error_callback=_on_error,
            )
            logger.info("ShoonyaBroker: WebSocket started")
        except Exception as e:
            logger.error(f"[ShoonyaBroker.ws_connect] {e}", exc_info=True)

    def ws_subscribe(self, ws_obj, symbols: List[str]) -> None:
        """
        Subscribe to Shoonya live feed.

        Shoonya symbols format: "NSE|26000" (exchange|instrument_token).
        Translates generic NSE:SYMBOL → Shoonya scrip token.
        """
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return
            api = ws_obj.get("__shoonya_api__") if isinstance(ws_obj, dict) else self.api
            if api is None:
                return

            shoonya_syms = []
            for sym in symbols:
                sh_sym = self._resolve_shoonya_symbol(sym)
                if sh_sym:
                    shoonya_syms.append(sh_sym)

            if shoonya_syms:
                api.subscribe(shoonya_syms)
                logger.info(f"ShoonyaBroker: subscribed {len(shoonya_syms)} symbols")
        except Exception as e:
            logger.error(f"[ShoonyaBroker.ws_subscribe] {e}", exc_info=True)

    def ws_unsubscribe(self, ws_obj, symbols: List[str]) -> None:
        """Unsubscribe from Shoonya live feed."""
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return
            api = ws_obj.get("__shoonya_api__") if isinstance(ws_obj, dict) else self.api
            if api is None:
                return
            shoonya_syms = [self._resolve_shoonya_symbol(s) for s in symbols]
            shoonya_syms = [s for s in shoonya_syms if s]
            if shoonya_syms:
                api.unsubscribe(shoonya_syms)
        except Exception as e:
            logger.error(f"[ShoonyaBroker.ws_unsubscribe] {e}", exc_info=True)

    def ws_disconnect(self, ws_obj) -> None:
        """
        Close Shoonya WebSocket with timeout protection.

        FIXED: Added timeout and better error handling.
        """
        try:
            if ws_obj is None:
                return

            logger.info("[ShoonyaBroker] Starting WebSocket disconnect")
            self._ws_closed = True

            api = ws_obj.get("__shoonya_api__") if isinstance(ws_obj, dict) else self.api

            if api and hasattr(api, "close_websocket"):
                # Run close in separate thread with timeout
                disconnect_complete = threading.Event()

                def _do_disconnect():
                    try:
                        api.close_websocket()
                        logger.debug("[ShoonyaBroker] close_websocket completed")
                    except Exception as e:
                        logger.warning(f"[ShoonyaBroker] close_websocket error: {e}")
                    finally:
                        disconnect_complete.set()

                disconnect_thread = threading.Thread(target=_do_disconnect, daemon=True)
                disconnect_thread.start()

                # Wait for disconnect with timeout
                if not disconnect_complete.wait(timeout=2.0):
                    logger.warning("[ShoonyaBroker] close_websocket timed out")

            # Clear reference
            if self._ws_api == api:
                self._ws_api = None

            # Call on_close callback
            if self._ws_on_close and not self._ws_closed:
                try:
                    self._ws_on_close("disconnected by user")
                except Exception as e:
                    logger.warning(f"[ShoonyaBroker] Error in close callback: {e}")

            logger.info("[ShoonyaBroker] WebSocket disconnect completed")

        except Exception as e:
            logger.error(f"[ShoonyaBroker.ws_disconnect] {e}", exc_info=True)

    def normalize_tick(self, raw_tick) -> Optional[Dict[str, Any]]:
        """
        Normalize a Shoonya/Finvasia tick.

        Shoonya tick fields: t (type), e (exchange), tk (token), lp (last price),
        ft (feed time), v (volume), oi (OI), bp1/sp1 (bid/ask), o/h/l/c (ohlc).
        """
        try:
            if self._ws_closed or not isinstance(raw_tick, dict):
                return None

            if raw_tick.get("t") not in ("sf", "tf", "if"):
                return None   # skip non-feed messages (order updates, etc.)

            lp = raw_tick.get("lp")
            if lp is None:
                return None

            exch  = raw_tick.get("e", "NSE")
            token = raw_tick.get("tk", "")
            symbol = f"{exch}:{token}"

            return {
                "symbol":    symbol,
                "ltp":       float(lp),
                "timestamp": str(raw_tick.get("ft", "")),
                "bid":       float(raw_tick["bp1"]) if raw_tick.get("bp1") else None,
                "ask":       float(raw_tick["sp1"]) if raw_tick.get("sp1") else None,
                "volume":    raw_tick.get("v"),
                "oi":        raw_tick.get("oi"),
                "open":      float(raw_tick["o"]) if raw_tick.get("o") else None,
                "high":      float(raw_tick["h"]) if raw_tick.get("h") else None,
                "low":       float(raw_tick["lo"]) if raw_tick.get("lo") else None,
                "close":     float(raw_tick["c"]) if raw_tick.get("c") else None,
            }
        except Exception as e:
            if not self._ws_closed:  # Only log if not during shutdown
                logger.error(f"[ShoonyaBroker.normalize_tick] {e}", exc_info=True)
            return None

    def _resolve_shoonya_symbol(self, symbol: str) -> Optional[str]:
        """
        Map generic NSE:SYMBOL → Shoonya exchange|token string.
        e.g. "NSE:NIFTY50-INDEX" → "NSE|26000"

        Caches results. For unknown symbols uses searchscrip() API.
        """
        try:
            cache = getattr(self, "_sh_sym_cache", {})
            if symbol in cache:
                return cache[symbol]

            exchange = "NSE"
            bare = symbol.split(":")[-1]
            if "NFO:" in symbol.upper():
                exchange = "NFO"

            if not self.api:
                return None

            ret = self.api.searchscrip(exchange=exchange, searchtext=bare)
            if ret and ret.get("values"):
                token = ret["values"][0].get("token")
                if token:
                    result = f"{exchange}|{token}"
                    cache[symbol] = result
                    self._sh_sym_cache = cache
                    return result
            return None
        except Exception as e:
            logger.warning(f"ShoonyaBroker._resolve_shoonya_symbol({symbol}): {e}")
            return None