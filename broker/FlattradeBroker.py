"""
brokers/FlattradeBroker.py
==========================
Flattrade Pi API implementation of BaseBroker.

Flattrade uses the same NorenRestApi protocol as Shoonya (Finvasia).
It provides FREE algo trading with ZERO brokerage.

Prerequisites:
    # Clone and install Flattrade's official Python library:
    pip install requests websocket-client
    # Then clone: https://github.com/flattrade/pythonAPI
    # and place api_helper.py (NorenApi) in your project path.
    # OR use NorenRestApiPy which also works:
    pip install NorenRestApiPy

Authentication (OAuth token — daily refresh):
    BrokerageSetting fields:
        client_id    → "user_id|api_key"  (pipe-separated)
                       e.g.  "FL12345|apikeyvalue"
                       Obtain api_key from https://wall.flattrade.in → Pi → Create New API Key
        secret_key   → API Secret (from Flattrade Pi API settings)
        redirect_uri → Redirect URI registered in Flattrade (e.g. https://127.0.0.1/callback)

    Token generation flow:
        1. Call broker.get_login_url()  → user visits URL in browser
        2. Flattrade redirects to redirect_uri?code=TOKEN
        3. Call broker.set_session(token="TOKEN")  → sets session, saves to DB

    Tokens expire at midnight (must regenerate daily before market open).

API docs: https://pi.flattrade.in/docs
GitHub:   https://github.com/flattrade/pythonAPI

FIXED: Added proper WebSocket cleanup with timeout and state tracking.
"""

import logging
import time
import random
import hashlib
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable

import pandas as pd
from requests.exceptions import Timeout, ConnectionError

from Utils.safe_getattr import safe_getattr, safe_hasattr
from broker.BaseBroker import BaseBroker, TokenExpiredError
from db.connector import get_db
from db.crud import tokens

# Flattrade uses the same NorenApi base as Shoonya
try:
    from NorenRestApiPy.NorenApi import NorenApi as _NorenApiBase
    FLATTRADE_AVAILABLE = True
except ImportError:
    FLATTRADE_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Flattrade endpoints ───────────────────────────────────────────────────────
FLATTRADE_HOST  = "https://piconnect.flattrade.in/PiConnectTP/"
FLATTRADE_WS    = "wss://piconnect.flattrade.in/PiConnectWSTp/"
FLATTRADE_EOD   = "https://web.flattrade.in/chartApi/getdata/"
FLATTRADE_LOGIN = "https://auth.flattrade.in/?api_key={api_key}"

# ── Flattrade product / order constants (same as Shoonya) ────────────────────
FT_EXCHANGE_NSE  = "NSE"
FT_EXCHANGE_NFO  = "NFO"
FT_EXCHANGE_BSE  = "BSE"
FT_EXCHANGE_MCX  = "MCX"

FT_PRODUCT_INTRADAY = "I"
FT_PRODUCT_MARGIN   = "M"
FT_PRODUCT_CNC      = "C"

FT_ORDER_MARKET = "MKT"
FT_ORDER_LIMIT  = "LMT"
FT_ORDER_SL     = "SL-LMT"
FT_ORDER_SLM    = "SL-MKT"

FT_BUY  = "B"
FT_SELL = "S"

FT_RETENTION_DAY = "DAY"

# Interval mapping: generic -> Flattrade (NorenApi uses seconds for intraday)
FT_INTERVAL_MAP = {
    "1":   "60",      # 1 min = 60 sec
    "2":   "120",
    "3":   "180",
    "5":   "300",
    "10":  "600",
    "15":  "900",
    "30":  "1800",
    "60":  "3600",
    "D":   "D",
    "day": "D",
}


class _FlattradeApi(_NorenApiBase if FLATTRADE_AVAILABLE else object):
    """Thin subclass of NorenApi configured for Flattrade endpoints."""
    def __init__(self):
        if FLATTRADE_AVAILABLE:
            super().__init__(host=FLATTRADE_HOST, websocket=FLATTRADE_WS)


class FlattradeBroker(BaseBroker):
    """
    Flattrade Pi API broker implementation.

    BrokerageSetting fields:
        client_id    → "user_id|api_key"  (pipe-separated, e.g. "FL12345|myapikey")
        secret_key   → API Secret
        redirect_uri → Registered redirect URI (e.g. https://127.0.0.1/callback)

    FIXED: Added proper WebSocket cleanup with timeout and state tracking.
    """

    def __init__(self, state, broker_setting=None):
        self._safe_defaults_init()
        try:
            if not FLATTRADE_AVAILABLE:
                raise ImportError(
                    "NorenRestApiPy is not installed.\n"
                    "Run: pip install NorenRestApiPy\n"
                    "or clone https://github.com/flattrade/pythonAPI"
                )
            self.state = state

            if broker_setting is None:
                raise ValueError("BrokerageSetting must be provided for FlattradeBroker.")

            # Parse "user_id|api_key" from client_id
            client_raw = safe_getattr(broker_setting, 'client_id', '') or ''
            if "|" in client_raw:
                self.user_id, self.api_key = client_raw.split("|", 1)
            else:
                self.user_id = client_raw
                self.api_key = client_raw

            self.api_secret   = safe_getattr(broker_setting, 'secret_key', '') or ''
            self.redirect_uri = safe_getattr(broker_setting, 'redirect_uri', '') or ''

            if not self.user_id:
                raise ValueError("Flattrade user_id is required.")

            # Initialize API
            self.api = _FlattradeApi()

            # Load saved token and restore session
            saved_token = self._load_token_from_db()
            if saved_token:
                ret = self.api.set_session(
                    userid=self.user_id,
                    password="",
                    usertoken=saved_token
                )
                if ret and ret.get("stat") == "Ok":
                    self.state.token = saved_token
                    logger.info("FlattradeBroker: session restored from DB")
                else:
                    logger.warning("FlattradeBroker: saved token invalid, need fresh login")
            else:
                logger.warning("FlattradeBroker: no token — call set_session(token=...) "
                               "after visiting get_login_url()")

            # WebSocket cleanup tracking
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()
            self._ws_api = None

            logger.info(f"FlattradeBroker initialized for user {self.user_id}")

        except Exception as e:
            logger.critical(f"[FlattradeBroker.__init__] {e}", exc_info=True)
            raise

    @property
    def broker_type(self) -> str:
        return "flattrade"

    def _safe_defaults_init(self):
        self.state = None
        self.user_id = None
        self.api_key = None
        self.api_secret = None
        self.redirect_uri = None
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

    def get_login_url(self) -> str:
        """Return the Flattrade OAuth URL the user must visit to obtain a token."""
        return FLATTRADE_LOGIN.format(api_key=self.api_key)

    def set_session(self, token: str) -> bool:
        """
        Set the session using the token obtained from the browser redirect code.
        This is equivalent to Flattrade's set_session/token validation step.

        For Flattrade, after visiting the login URL the redirect URL will contain
        a `code` query parameter — that is the token to pass here.

        Args:
            token: The token/code from the redirect URL query parameter.

        Returns:
            True on success.
        """
        try:
            # Compute SHA256 of (user_id + api_key + token) for Flattrade auth
            app_sha256 = hashlib.sha256(
                f"{self.user_id}{self.api_key}{token}".encode()
            ).hexdigest()

            ret = self.api.set_session(
                userid=self.user_id,
                password="",
                usertoken=app_sha256
            )

            if ret and ret.get("stat") == "Ok":
                self.state.token = app_sha256
                expires_at = (datetime.now() + timedelta(hours=8)).isoformat()
                db = get_db()
                tokens.save_token(app_sha256, "", expires_at=expires_at, db=db)
                logger.info("FlattradeBroker: session set successfully")
                return True

            # Some Flattrade setups accept the raw token directly
            ret2 = self.api.set_session(
                userid=self.user_id,
                password="",
                usertoken=token
            )
            if ret2 and ret2.get("stat") == "Ok":
                self.state.token = token
                expires_at = (datetime.now() + timedelta(hours=8)).isoformat()
                db = get_db()
                tokens.save_token(token, "", expires_at=expires_at, db=db)
                logger.info("FlattradeBroker: session set with raw token")
                return True

            logger.error(f"FlattradeBroker: set_session failed: {ret}")
            return False

        except Exception as e:
            logger.error(f"[FlattradeBroker.set_session] {e}", exc_info=True)
            return False

    def _load_token_from_db(self) -> Optional[str]:
        try:
            db = get_db()
            token_data = tokens.get(db)
            if token_data and token_data.get("access_token"):
                return token_data["access_token"]
            return None
        except Exception as e:
            logger.error(f"[FlattradeBroker._load_token_from_db] {e}", exc_info=True)
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

    def _get_token(self, symbol: str, exchange: str) -> Optional[str]:
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
                    # For options, filter by expiry if needed
                    token = values[0].get("token")
                    self._symbol_token_cache[cache_key] = token
                    return token
            return None
        except Exception as e:
            logger.error(f"[FlattradeBroker._get_token] {e}", exc_info=True)
            return None

    @staticmethod
    def _exchange_from_symbol(symbol: str) -> str:
        s = symbol.upper()
        if s.startswith("NFO:") or "CE" in s or "PE" in s or "FUT" in s:
            return FT_EXCHANGE_NFO
        if s.startswith("BSE:"):
            return FT_EXCHANGE_BSE
        return FT_EXCHANGE_NSE

    @staticmethod
    def _clean_symbol(symbol: str) -> str:
        return symbol.split(":")[-1]

    @staticmethod
    def _to_ft_interval(interval: str) -> str:
        return FT_INTERVAL_MAP.get(str(interval), "60")

    @staticmethod
    def _to_ft_side(side: int) -> str:
        return FT_BUY if side == BaseBroker.SIDE_BUY else FT_SELL

    @staticmethod
    def _is_ok(response: Any) -> bool:
        if isinstance(response, dict):
            return response.get("stat") == "Ok"
        return False

    def _check_token_error(self, response: Any):
        if isinstance(response, dict):
            msg = str(response.get("emsg", "") or "").lower()
            if "session" in msg or "token" in msg or "login" in msg or "invalid" in msg:
                raise TokenExpiredError(response.get("emsg", "Session expired"))

    # ── BaseBroker implementation ─────────────────────────────────────────────

    def get_profile(self) -> Optional[Dict]:
        try:
            if not self.api:
                return None
            result = self._call(self.api.get_user_details, context="get_profile")
            return result if self._is_ok(result) else None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[FlattradeBroker.get_profile] {e!r}", exc_info=True)
            return None

    def get_balance(self, capital_reserve: float = 0.0) -> float:
        try:
            if not self.api:
                return 0.0
            result = self._call(
                lambda: self.api.get_limits(
                    product_type=FT_PRODUCT_MARGIN,
                    segment=FT_EXCHANGE_NSE,
                    exchange=FT_EXCHANGE_NSE
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
            logger.error(f"[FlattradeBroker.get_balance] {e!r}", exc_info=True)
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
            ft_interval = self._to_ft_interval(interval)
            self._check_rate_limit()
            result = self._call(
                lambda: self.api.get_time_price_series(
                    exchange=exchange, token=token,
                    starttime=from_epoch, endtime=to_epoch,
                    interval=ft_interval
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
            logger.error(f"[FlattradeBroker.get_history] {e!r}", exc_info=True)
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
            ft_interval = self._to_ft_interval(interval)
            self._check_rate_limit()
            result = self._call(
                lambda: self.api.get_time_price_series(
                    exchange=exchange, token=token,
                    starttime=from_epoch, endtime=to_epoch,
                    interval=ft_interval
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
            logger.error(f"[FlattradeBroker.get_history_for_timeframe] {e!r}", exc_info=True)
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
            logger.error(f"[FlattradeBroker.get_option_quote] {e!r}", exc_info=True)
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
            product = kwargs.get('product_type', FT_PRODUCT_INTRADAY)
            limit_price = float(kwargs.get('limitPrice', 0) or 0)
            stop_price  = float(kwargs.get('stopPrice', 0) or 0)

            if not symbol or qty <= 0:
                return None

            exchange = self._exchange_from_symbol(symbol)
            clean = self._clean_symbol(symbol)
            token = self._get_token(clean, exchange)
            if not token:
                return None

            ft_order_type = {
                self.MARKET_ORDER_TYPE:          FT_ORDER_MARKET,
                self.LIMIT_ORDER_TYPE:           FT_ORDER_LIMIT,
                self.STOPLOSS_MARKET_ORDER_TYPE: FT_ORDER_SLM,
            }.get(order_type, FT_ORDER_MARKET)

            self._check_rate_limit()
            result = self._call(
                lambda: self.api.place_order(
                    buy_or_sell=self._to_ft_side(side),
                    product_type=product,
                    exchange=exchange,
                    tradingsymbol=clean,
                    quantity=qty,
                    discloseqty=0,
                    price_type=ft_order_type,
                    price=limit_price,
                    trigger_price=stop_price if stop_price else None,
                    retention=FT_RETENTION_DAY,
                    remarks="algotrade",
                ),
                context="place_order"
            )
            if self._is_ok(result):
                order_id = result.get("norenordno")
                logger.info(f"FlattradeBroker: order placed {order_id}")
                return str(order_id) if order_id else None
            self._check_token_error(result)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[FlattradeBroker.place_order] {e!r}", exc_info=True)
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
                    newprice_type=FT_ORDER_LIMIT,
                    newprice=limit_price,
                ),
                context="modify_order"
            )
            return self._is_ok(result)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[FlattradeBroker.modify_order] {e!r}", exc_info=True)
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
            logger.error(f"[FlattradeBroker.cancel_order] {e!r}", exc_info=True)
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
            logger.error(f"[FlattradeBroker.get_positions] {e!r}", exc_info=True)
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
            logger.error(f"[FlattradeBroker.get_orderbook] {e!r}", exc_info=True)
            return []

    def get_current_order_status(self, order_id: str) -> Optional[int]:
        """
        Return order status as integer:
        2 = filled, 1 = pending/open, -1 = rejected/cancelled, None = not found
        """
        try:
            orders = self.get_orderbook()
            for order in orders:
                if str(order.get("norenordno")) == str(order_id):
                    status_str = str(order.get("status") or "").upper()
                    if status_str in ("COMPLETE", "FILLED", "TRADED"):
                        return 2
                    if status_str in ("REJECTED", "CANCELLED", "CANCELED", "EXPIRED"):
                        return -1
                    # OPEN, PENDING, TRIGGER_PENDING, etc.
                    return 1
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[FlattradeBroker.get_current_order_status] {e!r}", exc_info=True)
            return None

    def get_fill_price(self, broker_order_id: str) -> Optional[float]:
        """
        Return the actual average fill price for a completed order.
        Flattrade orderbook includes 'avgprc' (average price) on filled orders.
        """
        try:
            if not broker_order_id or not self.api:
                return None
            orders = self.get_orderbook()
            for order in orders:
                if str(order.get("norenordno")) == str(broker_order_id):
                    avg = order.get("avgprc") or order.get("prc")
                    if avg:
                        return float(avg)
            return None
        except Exception as e:
            logger.error(f"[FlattradeBroker.get_fill_price] {e!r}", exc_info=True)
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
        FlatTrade option symbol format: ``NFO|NIFTY2531825000CE``

        FlatTrade (NorenRestApiPy) uses the same pipe-separated format as
        Shoonya.  All NSE F&O instruments use ``NFO|`` prefix.
        SENSEX options use ``BFO|``.
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
            logger.error(f"[FlattradeBroker.build_option_symbol] {e}", exc_info=True)
            return None

    def _params_to_symbol(self, params) -> Optional[str]:
        """FlattradeBroker symbol from OptionParams."""
        if not params:
            return None
        prefix = "BFO|" if params.underlying == "SENSEX" else "NFO|"
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
        """FlatTrade option chain with NFO|/BFO| prefixes."""
        try:
            from Utils.OptionSymbolBuilder import OptionSymbolBuilder
            all_params = OptionSymbolBuilder.get_all_option_params(
                underlying=underlying, spot_price=spot_price,
                option_type=option_type, weeks_offset=weeks_offset,
                itm=itm, otm=otm,
            )
            return [s for s in (self._params_to_symbol(p) for p in all_params) if s]
        except Exception as e:
            logger.error(f"[FlattradeBroker.build_option_chain] {e}", exc_info=True)
            return []

    def is_connected(self) -> bool:
        try:
            return self.get_profile() is not None
        except TokenExpiredError:
            return False
        except Exception:

            return False

    def cleanup(self) -> None:
        """Clean up resources including WebSocket connection."""
        logger.info("[FlattradeBroker] Starting cleanup")

        # Mark WebSocket as closed to prevent callbacks
        self._ws_closed = True

        # Clean up WebSocket if it exists
        if self._ws_api is not None:
            try:
                # Try to close WebSocket with timeout
                self._ws_cleanup_event.clear()

                def _do_disconnect():
                    try:
                        if safe_hasattr(self._ws_api, "close_websocket"):
                            self._ws_api.close_websocket()
                            logger.debug("[FlattradeBroker] close_websocket called")
                    except Exception as e:
                        logger.warning(f"[FlattradeBroker] Error closing WebSocket: {e}")
                    finally:
                        self._ws_cleanup_event.set()

                # Run close in separate thread with timeout
                close_thread = threading.Thread(target=_do_disconnect, daemon=True)
                close_thread.start()

                # Wait for close with timeout
                if not self._ws_cleanup_event.wait(timeout=2.0):
                    logger.warning("[FlattradeBroker] WebSocket close timed out")

            except Exception as e:
                logger.error(f"[FlattradeBroker] Error during WebSocket cleanup: {e}", exc_info=True)
            finally:
                self._ws_api = None

        # Logout from API
        try:
            if self.api:
                self.api.logout()
        except Exception as e:
            logger.warning(f"[FlattradeBroker.cleanup] Logout error: {e}")

        # Clear callbacks
        self._ws_on_tick = None
        self._ws_on_connect = None
        self._ws_on_close = None
        self._ws_on_error = None

        logger.info("[FlattradeBroker] Cleanup completed")

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
                logger.warning(f"[Flattrade.{context}] Network error, retry {attempt+1}: {e}")
                time.sleep(delay)
            except Exception as e:
                error_str = str(e).lower()
                if "session" in error_str or "token" in error_str:
                    raise TokenExpiredError(str(e))
                logger.error(f"[Flattrade.{context}] {e!r}", exc_info=True)
                return None
        logger.critical(f"[Flattrade.{context}] Max retries reached.")
        return None

    # ── WebSocket interface ────────────────────────────────────────────────────

    def create_websocket(self, on_tick, on_connect, on_close, on_error) -> Any:
        """
        Create Flattrade (NorenApi) WebSocket.

        Flattrade uses the same NorenRestApiPy WebSocket as Shoonya.
        Symbols use "NSE|TOKEN" format same as Shoonya.

        FIXED: Added state tracking and stored callbacks.
        """
        try:
            if not self.api:
                logger.error("FlattradeBroker.create_websocket: api not initialized — set_session first")
                return None

            # Reset WebSocket state
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()

            self._ws_on_tick    = on_tick
            self._ws_on_connect = on_connect
            self._ws_on_close   = on_close
            self._ws_on_error   = on_error

            logger.info("FlattradeBroker: WebSocket callbacks stored")
            return {"__ft_api__": self.api, "__user_id__": self.user_id}
        except Exception as e:
            logger.error(f"[FlattradeBroker.create_websocket] {e}", exc_info=True)
            return None

    def ws_connect(self, ws_obj) -> None:
        """Start Flattrade NorenApi WebSocket with safety checks."""
        try:
            if ws_obj is None or self._ws_closed:
                return

            api = ws_obj.get("__ft_api__") if isinstance(ws_obj, dict) else self.api
            if api is None:
                return

            def _on_open():
                if self._ws_closed:
                    return
                logger.info("FlattradeBroker: WebSocket opened")
                self._ws_on_connect()

            def _on_message(msg):
                if self._ws_closed:
                    return
                self._ws_on_tick(msg)

            def _on_error(msg):
                if self._ws_closed:
                    return
                logger.error(f"FlattradeBroker WS error: {msg}")
                self._ws_on_error(str(msg))

            def _on_close():
                if self._ws_closed:
                    return
                logger.info("FlattradeBroker: WebSocket closed")
                self._ws_on_close("connection closed")

            # Store API reference for cleanup
            self._ws_api = api

            api.start_websocket(
                order_update_callback=_on_message,
                subscribe_callback=_on_message,
                socket_open_callback=_on_open,
                socket_close_callback=_on_close,
                socket_error_callback=_on_error,
            )
            logger.info("FlattradeBroker: WebSocket started")
        except Exception as e:
            logger.error(f"[FlattradeBroker.ws_connect] {e}", exc_info=True)

    def ws_subscribe(self, ws_obj, symbols: List[str]) -> None:
        """Subscribe to Flattrade live feed (same token format as Shoonya)."""
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return
            api = ws_obj.get("__ft_api__") if isinstance(ws_obj, dict) else self.api
            if api is None:
                return

            ft_syms = []
            for sym in symbols:
                ft_sym = self._resolve_ft_symbol(sym)
                if ft_sym:
                    ft_syms.append(ft_sym)

            if ft_syms:
                api.subscribe(ft_syms)
                logger.info(f"FlattradeBroker: subscribed {len(ft_syms)} symbols")
        except Exception as e:
            logger.error(f"[FlattradeBroker.ws_subscribe] {e}", exc_info=True)

    def ws_unsubscribe(self, ws_obj, symbols: List[str]) -> None:
        """Unsubscribe from Flattrade live feed."""
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return
            api = ws_obj.get("__ft_api__") if isinstance(ws_obj, dict) else self.api
            if api is None:
                return
            ft_syms = [self._resolve_ft_symbol(s) for s in symbols]
            ft_syms = [s for s in ft_syms if s]
            if ft_syms:
                api.unsubscribe(ft_syms)
        except Exception as e:
            logger.error(f"[FlattradeBroker.ws_unsubscribe] {e}", exc_info=True)

    def ws_disconnect(self, ws_obj) -> None:
        """
        Close Flattrade WebSocket with timeout protection.

        FIXED: Added timeout and better error handling.
        """
        try:
            if ws_obj is None:
                return

            logger.info("[FlattradeBroker] Starting WebSocket disconnect")
            self._ws_closed = True

            api = ws_obj.get("__ft_api__") if isinstance(ws_obj, dict) else self.api

            if api and safe_hasattr(api, "close_websocket"):
                # Run close in separate thread with timeout
                disconnect_complete = threading.Event()

                def _do_disconnect():
                    try:
                        api.close_websocket()
                        logger.debug("[FlattradeBroker] close_websocket completed")
                    except Exception as e:
                        logger.warning(f"[FlattradeBroker] close_websocket error: {e}")
                    finally:
                        disconnect_complete.set()

                disconnect_thread = threading.Thread(target=_do_disconnect, daemon=True)
                disconnect_thread.start()

                # Wait for disconnect with timeout
                if not disconnect_complete.wait(timeout=2.0):
                    logger.warning("[FlattradeBroker] close_websocket timed out")

            # Clear reference
            self._ws_api = None

            # Call on_close callback regardless of _ws_closed
            if self._ws_on_close:
                try:
                    self._ws_on_close("disconnected by user")
                except Exception as e:
                    logger.warning(f"[FlattradeBroker] Error in close callback: {e}")

            logger.info("[FlattradeBroker] WebSocket disconnect completed")

        except Exception as e:
            logger.error(f"[FlattradeBroker.ws_disconnect] {e}", exc_info=True)

    def normalize_tick(self, raw_tick) -> Optional[Dict[str, Any]]:
        """
        Normalize a Flattrade NorenApi tick.

        IMPORTANT: All numeric values in Flattrade ticks are STRINGS, not numbers.
        Must convert with float() or int() after checking existence.
        """
        try:
            if self._ws_closed or not isinstance(raw_tick, dict):
                return None

            # Filter only relevant tick types
            if raw_tick.get("t") not in ("sf", "tf", "if"):
                return None

            lp = raw_tick.get("lp")
            if lp is None:
                return None

            exch = raw_tick.get("e", "NSE")
            token = raw_tick.get("tk", "")
            symbol = f"{exch}:{token}"

            # Helper to safely convert string to float
            def to_float(val):
                if val is None:
                    return None
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None

            # Helper to safely convert to int
            def to_int(val):
                if val is None:
                    return None
                try:
                    return int(float(val))  # Convert through float first to handle "5000.0"
                except (ValueError, TypeError):
                    return None

            return {
                "symbol": symbol,
                "ltp": to_float(lp),
                "timestamp": str(raw_tick.get("ft", "")),
                "bid": to_float(raw_tick.get("bp1")),
                "ask": to_float(raw_tick.get("sp1")),
                "volume": to_int(raw_tick.get("v")),
                "oi": to_int(raw_tick.get("oi")),
                "open": to_float(raw_tick.get("o")),
                "high": to_float(raw_tick.get("h")),
                "low": to_float(raw_tick.get("lo")),
                "close": to_float(raw_tick.get("c")),
            }
        except Exception as e:
            if not self._ws_closed:
                logger.error(f"[FlattradeBroker.normalize_tick] {e}", exc_info=True)
            return None

    def _resolve_ft_symbol(self, symbol: str) -> Optional[str]:
        """
        Map generic NSE:SYMBOL → Flattrade exchange|token string.

        Uses NorenApi searchscrip() to look up the instrument token.
        Results are cached for the session.
        """
        try:
            cache = safe_getattr(self, "_ft_sym_cache", {})
            if symbol in cache:
                return cache[symbol]

            exchange = "NFO" if "NFO:" in symbol.upper() else "NSE"
            bare     = symbol.split(":")[-1]

            if not self.api:
                return None

            ret = self.api.searchscrip(exchange=exchange, searchtext=bare)
            if ret and ret.get("values"):
                token  = ret["values"][0].get("token")
                if token:
                    result = f"{exchange}|{token}"
                    cache[symbol] = result
                    self._ft_sym_cache = cache
                    return result
            return None
        except Exception as e:
            logger.warning(f"FlattradeBroker._resolve_ft_symbol({symbol}): {e}")
            return None