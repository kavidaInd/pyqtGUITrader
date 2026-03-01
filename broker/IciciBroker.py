"""
brokers/IciciBroker.py
======================
ICICI Securities Breeze API implementation of BaseBroker.

Prerequisites:
    pip install breeze-connect

Authentication (session token — semi-manual):
    BrokerageSetting fields:
        client_id    → Breeze API Key  (from https://api.icicidirect.com)
        secret_key   → Breeze Secret Key
        redirect_uri → Not used (leave blank or "N/A")

    Breeze uses a session_token that you generate by visiting:
        https://api.icicidirect.com/apiuser/login?api_key=<YOUR_API_KEY>
    The session_token is passed at runtime after the user logs in.

    NOTE: ICICI Direct (SEBI circular 2025) now requires a Static IP for API usage.

    Session flow:
        broker.generate_session(session_token="TOKEN_FROM_URL_REDIRECT")
        # This calls breeze.generate_session() and saves the token to DB.

    Unique quirks:
        - Breeze uses ICICI-specific stock_code (NOT NSE trading symbol).
          e.g. "NIFTY" → stock_code="NIFTY", "TATASTEEL" → "TATASTEEL"
        - Options require: exchange_code, stock_code, expiry_date (DD-MMM-YYYY),
          strike_price (str), right ("call"/"put"), product_type ("options")
        - This broker stores option metadata in kwargs for option orders.

API docs: https://api.icicidirect.com
SDK:      pip install breeze-connect
"""

import logging
import time
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable

import pandas as pd
from requests.exceptions import Timeout, ConnectionError

from broker.BaseBroker import BaseBroker, TokenExpiredError
from db.connector import get_db
from db.crud import tokens

try:
    from breeze_connect import BreezeConnect
    BREEZE_AVAILABLE = True
except ImportError:
    BREEZE_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Breeze product / order constants ─────────────────────────────────────────
BREEZE_PRODUCT_INTRADAY = "intraday"
BREEZE_PRODUCT_MARGIN   = "margin"
BREEZE_PRODUCT_DELIVERY = "delivery"
BREEZE_PRODUCT_OPTIONS  = "options"
BREEZE_PRODUCT_FUTURES  = "futures"

BREEZE_ORDER_MARKET = "market"
BREEZE_ORDER_LIMIT  = "limit"
BREEZE_ORDER_SL     = "stoploss"

BREEZE_BUY  = "buy"
BREEZE_SELL = "sell"

BREEZE_VALIDITY_DAY = "day"
BREEZE_VALIDITY_GTC = "gtc"
BREEZE_VALIDITY_IOC = "ioc"

# Interval mapping: generic -> Breeze
BREEZE_INTERVAL_MAP = {
    "1":   "1minute",
    "5":   "5minute",
    "10":  "10minute",
    "15":  "15minute",
    "30":  "30minute",
    "60":  "1hour",
    "D":   "1day",
    "day": "1day",
    "W":   "1week",
    "M":   "1month",
}

BREEZE_LOGIN_URL = "https://api.icicidirect.com/apiuser/login?api_key={api_key}"


class IciciBroker(BaseBroker):
    """
    ICICI Securities Breeze API broker implementation.

    BrokerageSetting fields:
        client_id    → Breeze API Key
        secret_key   → Breeze Secret Key
        redirect_uri → (not used by Breeze; leave empty)

    To complete auth, call:
        broker.generate_session(session_token="<token from browser redirect>")

    get_login_url() returns the URL the user should visit to obtain the token.
    """

    def __init__(self, state, broker_setting=None):
        self._safe_defaults_init()
        try:
            if not BREEZE_AVAILABLE:
                raise ImportError(
                    "breeze-connect is not installed.\n"
                    "Run: pip install breeze-connect"
                )
            self.state = state

            if broker_setting is None:
                raise ValueError("BrokerageSetting must be provided for IciciBroker.")

            self.api_key    = getattr(broker_setting, 'client_id', None)
            self.api_secret = getattr(broker_setting, 'secret_key', None)

            if not self.api_key:
                raise ValueError("ICICI Breeze api_key (client_id) is required.")

            # Initialize SDK
            self.breeze = BreezeConnect(api_key=self.api_key)

            # Try to restore saved session
            saved_token = self._load_token_from_db()
            if saved_token and self.api_secret:
                try:
                    self.breeze.generate_session(
                        api_secret=self.api_secret,
                        session_token=saved_token
                    )
                    self.state.token = saved_token
                    logger.info("IciciBroker: session restored from DB")
                except Exception:
                    logger.warning("IciciBroker: saved token invalid, need fresh session")
            else:
                logger.warning("IciciBroker: no session — call generate_session(session_token=...)")

            logger.info("IciciBroker initialized")

        except Exception as e:
            logger.critical(f"[IciciBroker.__init__] {e}", exc_info=True)
            raise

    @property
    def broker_type(self) -> str:
        return "icici"

    def _safe_defaults_init(self):
        self.state = None
        self.api_key = None
        self.api_secret = None
        self.breeze = None
        self._last_request_time = 0
        self._request_count = 0

    # ── Authentication ────────────────────────────────────────────────────────

    def get_login_url(self) -> str:
        """Return the URL the user should open to obtain a session token."""
        import urllib.parse
        encoded = urllib.parse.quote_plus(self.api_key or "")
        return f"https://api.icicidirect.com/apiuser/login?api_key={encoded}"

    def generate_session(self, session_token: str) -> bool:
        """
        Complete authentication using the session token obtained from browser redirect.

        Args:
            session_token: Token from the URL query parameter after login redirect.

        Returns:
            True on success
        """
        try:
            self.breeze.generate_session(
                api_secret=self.api_secret,
                session_token=session_token
            )
            self.state.token = session_token
            expires_at = (datetime.now() + timedelta(hours=10)).isoformat()
            db = get_db()
            tokens.save_token(session_token, "", expires_at=expires_at, db=db)
            logger.info("IciciBroker: session generated successfully")
            return True
        except Exception as e:
            logger.error(f"[IciciBroker.generate_session] {e}", exc_info=True)
            return False

    def _load_token_from_db(self) -> Optional[str]:
        try:
            db = get_db()
            token_data = tokens.get(db)
            if token_data and token_data.get("access_token"):
                return token_data["access_token"]
            return None
        except Exception as e:
            logger.error(f"[IciciBroker._load_token_from_db] {e}", exc_info=True)
            return None

    # ── Rate limiting ─────────────────────────────────────────────────────────

    def _check_rate_limit(self):
        """ICICI Breeze: max 10 orders/sec per SEBI regulations."""
        current = time.time()
        diff = current - self._last_request_time
        if diff < 1.0:
            self._request_count += 1
            if self._request_count >= 10:
                time.sleep(1.0 - diff + 0.1)
                self._request_count = 0
                self._last_request_time = time.time()
        else:
            self._request_count = 1
            self._last_request_time = current

    # ── Symbol helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _exchange_code(symbol: str) -> str:
        s = symbol.upper()
        if s.startswith("NFO:") or "CE" in s or "PE" in s or "FUT" in s:
            return "NFO"
        if s.startswith("BSE:"):
            return "BSE"
        return "NSE"

    @staticmethod
    def _stock_code(symbol: str) -> str:
        """Breeze uses short stock codes like 'NIFTY', 'RELIANCE'. Strip exchange prefix."""
        return symbol.split(":")[-1].replace("-EQ", "").upper()

    @staticmethod
    def _to_breeze_interval(interval: str) -> str:
        return BREEZE_INTERVAL_MAP.get(str(interval), "1minute")

    @staticmethod
    def _to_breeze_side(side: int) -> str:
        return BREEZE_BUY if side == BaseBroker.SIDE_BUY else BREEZE_SELL

    @staticmethod
    def _is_ok(response: Any) -> bool:
        if isinstance(response, dict):
            return response.get("Status") == 200 or response.get("status") == 200
        return False

    def _check_token_error(self, response: Any):
        if isinstance(response, dict):
            error = str(response.get("Error", "") or "").lower()
            if "session" in error or "token" in error or "login" in error or "expired" in error:
                raise TokenExpiredError(response.get("Error", "Session expired"))

    # ── BaseBroker implementation ─────────────────────────────────────────────

    def get_profile(self) -> Optional[Dict]:
        try:
            if not self.breeze:
                return None
            result = self._call(
                lambda: self.breeze.get_customer_details(api_session=self.state.token or ""),
                context="get_profile"
            )
            return result.get("Success") if self._is_ok(result) else None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[IciciBroker.get_profile] {e!r}", exc_info=True)
            return None

    def get_balance(self, capital_reserve: float = 0.0) -> float:
        try:
            if not self.breeze:
                return 0.0
            result = self._call(
                lambda: self.breeze.get_funds(),
                context="get_balance"
            )
            if self._is_ok(result) and result.get("Success"):
                data = result["Success"]
                if isinstance(data, list) and data:
                    available = float(data[0].get("balance", 0.0))
                elif isinstance(data, dict):
                    available = float(data.get("balance", 0.0))
                else:
                    available = 0.0
                if capital_reserve > 0:
                    available = available * (1 - capital_reserve / 100)
                return available
            return 0.0
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[IciciBroker.get_balance] {e!r}", exc_info=True)
            return 0.0

    def get_history(self, symbol: str, interval: str = "2", length: int = 400):
        try:
            if not symbol or not self.breeze:
                return None
            exchange = self._exchange_code(symbol)
            stock_code = self._stock_code(symbol)
            to_dt = datetime.now()
            from_dt = to_dt - timedelta(days=4)
            breeze_interval = self._to_breeze_interval(interval)
            from_iso = from_dt.isoformat()[:10] + "T00:00:00.000Z"
            to_iso   = to_dt.isoformat()[:10]   + "T23:59:59.000Z"

            self._check_rate_limit()
            result = self._call(
                lambda: self.breeze.get_historical_data_v2(
                    interval=breeze_interval,
                    from_date=from_iso,
                    to_date=to_iso,
                    stock_code=stock_code,
                    exchange_code=exchange,
                    product_type="cash",
                ),
                context="get_history"
            )
            if self._is_ok(result) and result.get("Success"):
                data = result["Success"]
                if data:
                    df = pd.DataFrame(data)
                    col_map = {
                        "datetime": "time", "open": "open", "high": "high",
                        "low": "low", "close": "close", "volume": "volume",
                        "Date": "time",
                    }
                    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
                    return df.tail(length)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[IciciBroker.get_history] {e!r}", exc_info=True)
            return None

    def get_history_for_timeframe(self, symbol: str, interval: str, days: int = 30):
        try:
            if not symbol or not self.breeze:
                return None
            exchange = self._exchange_code(symbol)
            stock_code = self._stock_code(symbol)
            fetch_days = max(days, 60) if interval in ["15", "30", "60"] else (
                max(days, 120) if interval in ["120", "240"] else days
            )
            to_dt = datetime.now()
            from_dt = to_dt - timedelta(days=fetch_days)
            breeze_interval = self._to_breeze_interval(interval)
            from_iso = from_dt.isoformat()[:10] + "T00:00:00.000Z"
            to_iso   = to_dt.isoformat()[:10]   + "T23:59:59.000Z"

            self._check_rate_limit()
            result = self._call(
                lambda: self.breeze.get_historical_data_v2(
                    interval=breeze_interval,
                    from_date=from_iso,
                    to_date=to_iso,
                    stock_code=stock_code,
                    exchange_code=exchange,
                    product_type="cash",
                ),
                context="get_history_for_timeframe"
            )
            if self._is_ok(result) and result.get("Success"):
                data = result["Success"]
                if data:
                    df = pd.DataFrame(data)
                    col_map = {
                        "datetime": "time", "open": "open", "high": "high",
                        "low": "low", "close": "close", "volume": "volume",
                        "Date": "time",
                    }
                    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
                    if "time" in df.columns:
                        df["time"] = pd.to_datetime(df["time"])
                    return df
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[IciciBroker.get_history_for_timeframe] {e!r}", exc_info=True)
            return None

    def get_option_current_price(self, option_name: str) -> Optional[float]:
        quote = self.get_option_quote(option_name)
        return quote.get("ltp") if quote else None

    def get_option_quote(self, option_name: str) -> Optional[Dict[str, float]]:
        """
        For Breeze, option_name should be formatted as:
            "NFO:NIFTY:25JAN2024:21000:CE"  (exchange:symbol:expiry:strike:right)
        Or pass as standard NSE:SYMBOL and this method will attempt to get index quotes.
        """
        try:
            if not option_name or not self.breeze:
                return None
            # Try to parse structured format
            parts = option_name.split(":")
            if len(parts) >= 5:
                exchange, symbol, expiry, strike, right = parts[:5]
                breeze_right = "call" if right.upper() == "CE" else "put"
                expiry_dt = datetime.strptime(expiry, "%d%b%Y")
                expiry_breeze = expiry_dt.strftime("%d-%b-%Y").upper()
                self._check_rate_limit()
                result = self._call(
                    lambda: self.breeze.get_quotes(
                        stock_code=symbol.upper(),
                        exchange_code=exchange.upper(),
                        expiry_date=expiry_breeze,
                        product_type="options",
                        right=breeze_right,
                        strike_price=strike,
                    ),
                    context="get_option_quote"
                )
            else:
                exchange = self._exchange_code(option_name)
                stock_code = self._stock_code(option_name)
                self._check_rate_limit()
                result = self._call(
                    lambda: self.breeze.get_quotes(
                        stock_code=stock_code,
                        exchange_code=exchange,
                        expiry_date="",
                        product_type="cash",
                        right="",
                        strike_price="",
                    ),
                    context="get_option_quote"
                )

            if self._is_ok(result) and result.get("Success"):
                data = result["Success"]
                if isinstance(data, list) and data:
                    q = data[0]
                elif isinstance(data, dict):
                    q = data
                else:
                    return None
                return {
                    "ltp":    float(q.get("ltp", 0) or 0),
                    "bid":    float(q.get("best_bid_price", 0) or 0),
                    "ask":    float(q.get("best_offer_price", 0) or 0),
                    "high":   float(q.get("high", 0) or 0),
                    "low":    float(q.get("low", 0) or 0),
                    "open":   float(q.get("open", 0) or 0),
                    "close":  float(q.get("previous_close", 0) or 0),
                    "volume": int(q.get("ttq", 0) or 0),
                    "oi":     int(q.get("open_interest", 0) or 0),
                }
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[IciciBroker.get_option_quote] {e!r}", exc_info=True)
            return None

    def get_option_chain_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        result = {}
        for sym in symbols:
            quote = self.get_option_quote(sym)
            if quote:
                result[sym.split(":")[-1]] = quote
        return result

    def place_order(self, **kwargs) -> Optional[str]:
        """
        Place order via Breeze.

        For options orders, pass extra kwargs:
            expiry_date (str):  "DD-MMM-YYYY"  e.g. "25-JAN-2024"
            strike_price (str): "21000"
            right (str):        "call" or "put"
            product_type (str): "options" (default for NFO)
        """
        try:
            if not self.breeze:
                return None
            symbol = kwargs.get('symbol', '')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_BUY)
            order_type = kwargs.get('order_type', self.MARKET_ORDER_TYPE)
            product = kwargs.get('product_type', None)
            limit_price = str(float(kwargs.get('limitPrice', 0) or 0))
            stop_price  = str(float(kwargs.get('stopPrice', 0) or 0))

            if not symbol or qty <= 0:
                return None

            exchange = self._exchange_code(symbol)
            stock_code = self._stock_code(symbol)

            # Determine product type automatically
            if product is None:
                if exchange == "NFO":
                    product = BREEZE_PRODUCT_OPTIONS
                elif exchange == "NSE":
                    product = BREEZE_PRODUCT_INTRADAY
                else:
                    product = BREEZE_PRODUCT_INTRADAY

            breeze_order_type = {
                self.MARKET_ORDER_TYPE:          BREEZE_ORDER_MARKET,
                self.LIMIT_ORDER_TYPE:           BREEZE_ORDER_LIMIT,
                self.STOPLOSS_MARKET_ORDER_TYPE: BREEZE_ORDER_SL,
            }.get(order_type, BREEZE_ORDER_MARKET)

            order_kwargs = dict(
                stock_code=stock_code,
                exchange_code=exchange,
                product=product,
                action=self._to_breeze_side(side),
                order_type=breeze_order_type,
                quantity=str(qty),
                validity=BREEZE_VALIDITY_DAY,
                price=limit_price,
                stoploss=stop_price if order_type == self.STOPLOSS_MARKET_ORDER_TYPE else "0",
            )

            # Inject option-specific params if provided
            if product in (BREEZE_PRODUCT_OPTIONS, BREEZE_PRODUCT_FUTURES):
                order_kwargs["expiry_date"]  = kwargs.get("expiry_date", "")
                order_kwargs["strike_price"] = kwargs.get("strike_price", "")
                order_kwargs["right"]        = kwargs.get("right", "")

            self._check_rate_limit()
            result = self._call(
                lambda: self.breeze.place_order(**order_kwargs),
                context="place_order"
            )
            if self._is_ok(result):
                data = result.get("Success") or {}
                if isinstance(data, list) and data:
                    data = data[0]
                order_id = data.get("order_id") or data.get("orderId")
                logger.info(f"IciciBroker: order placed {order_id}")
                return str(order_id) if order_id else None
            self._check_token_error(result)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[IciciBroker.place_order] {e!r}", exc_info=True)
            return None

    def modify_order(self, **kwargs) -> bool:
        try:
            order_id = kwargs.get('order_id')
            limit_price = str(float(kwargs.get('limit_price', 0) or 0))
            qty = str(int(kwargs.get('qty', 0)))
            if not order_id or not self.breeze:
                return False
            self._check_rate_limit()
            result = self._call(
                lambda: self.breeze.modify_order(
                    order_id=order_id,
                    exchange_code=self._exchange_code(kwargs.get('symbol', 'NSE')),
                    order_type=BREEZE_ORDER_LIMIT,
                    stoploss="0",
                    quantity=qty,
                    price=limit_price,
                    validity=BREEZE_VALIDITY_DAY,
                    disclosed_quantity="0",
                    validity_date="",
                ),
                context="modify_order"
            )
            return self._is_ok(result)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[IciciBroker.modify_order] {e!r}", exc_info=True)
            return False

    def cancel_order(self, **kwargs) -> bool:
        try:
            order_id = kwargs.get('order_id')
            if not order_id or not self.breeze:
                return False
            self._check_rate_limit()
            result = self._call(
                lambda: self.breeze.cancel_order(
                    exchange_code=self._exchange_code(kwargs.get('symbol', 'NSE')),
                    order_id=order_id,
                ),
                context="cancel_order"
            )
            return self._is_ok(result)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[IciciBroker.cancel_order] {e!r}", exc_info=True)
            return False

    def exit_position(self, **kwargs) -> bool:
        symbol = kwargs.get('symbol')
        qty = kwargs.get('qty', 0)
        current_side = kwargs.get('side', self.SIDE_BUY)
        exit_side = self.SIDE_SELL if current_side == self.SIDE_BUY else self.SIDE_BUY
        if not symbol or qty <= 0:
            return False
        return self.place_order(symbol=symbol, qty=qty, side=exit_side,
                                order_type=self.MARKET_ORDER_TYPE,
                                **{k: v for k, v in kwargs.items()
                                   if k in ('expiry_date', 'strike_price', 'right', 'product_type')}
                               ) is not None

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
            if not self.breeze:
                return []
            result = self._call(
                lambda: self.breeze.get_portfolio_positions(),
                context="get_positions"
            )
            if self._is_ok(result) and result.get("Success"):
                data = result["Success"]
                return data if isinstance(data, list) else [data]
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[IciciBroker.get_positions] {e!r}", exc_info=True)
            return []

    def get_orderbook(self) -> List[Dict[str, Any]]:
        try:
            if not self.breeze:
                return []
            result = self._call(
                lambda: self.breeze.get_order_list(
                    exchange_code="NSE",
                    from_date=datetime.now().strftime("%Y-%m-%dT00:00:00.000Z"),
                    to_date=datetime.now().strftime("%Y-%m-%dT23:59:59.000Z"),
                ),
                context="get_orderbook"
            )
            if self._is_ok(result) and result.get("Success"):
                data = result["Success"]
                return data if isinstance(data, list) else [data]
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[IciciBroker.get_orderbook] {e!r}", exc_info=True)
            return []

    def get_current_order_status(self, order_id: str) -> Optional[Any]:
        try:
            if not order_id or not self.breeze:
                return None
            result = self._call(
                lambda: self.breeze.get_order_detail(
                    exchange_code="NSE",
                    order_id=order_id,
                ),
                context="order_status"
            )
            if self._is_ok(result) and result.get("Success"):
                data = result["Success"]
                return data[0] if isinstance(data, list) and data else data
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[IciciBroker.get_current_order_status] {e!r}", exc_info=True)
            return None

    def is_connected(self) -> bool:
        try:
            return self.get_profile() is not None
        except TokenExpiredError:
            return False
        except Exception:
            return False

    def cleanup(self) -> None:
        logger.info("[IciciBroker] cleanup done")

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
                logger.warning(f"[ICICI.{context}] Network error, retry {attempt+1}: {e}")
                time.sleep(delay)
            except Exception as e:
                error_str = str(e).lower()
                if "session" in error_str or "expired" in error_str or "token" in error_str:
                    raise TokenExpiredError(str(e))
                logger.error(f"[ICICI.{context}] {e!r}", exc_info=True)
                return None
        logger.critical(f"[ICICI.{context}] Max retries reached.")
        return None

    # ── WebSocket interface ────────────────────────────────────────────────────

    def create_websocket(self, on_tick, on_connect, on_close, on_error) -> Any:
        """
        Create ICICI Breeze WebSocket.

        BreezeConnect has built-in WebSocket via breeze.ws_connect() and
        breeze.subscribe_feeds(). Callbacks are set via breeze.on_ticks.

        Note: ICICI Breeze requires a static IP since the SEBI 2025 circular.
        Ensure your server IP is whitelisted in the Breeze developer portal.
        """
        try:
            if not self.breeze:
                logger.error("IciciBroker.create_websocket: breeze not initialized — call generate_session first")
                return None

            self._ws_on_tick    = on_tick
            self._ws_on_connect = on_connect
            self._ws_on_close   = on_close
            self._ws_on_error   = on_error

            # Attach tick callback on the breeze client
            self.breeze.on_ticks = lambda ticks: self._ws_on_tick(ticks)

            logger.info("IciciBroker: Breeze WebSocket callbacks configured")
            return {"__breeze__": self.breeze}
        except Exception as e:
            logger.error(f"[IciciBroker.create_websocket] {e}", exc_info=True)
            return None

    def ws_connect(self, ws_obj) -> None:
        """Start ICICI Breeze WebSocket connection."""
        try:
            if ws_obj is None:
                return
            breeze = ws_obj.get("__breeze__") if isinstance(ws_obj, dict) else self.breeze
            if breeze is None:
                return
            breeze.ws_connect()
            logger.info("IciciBroker: Breeze ws_connect() called")
            self._ws_on_connect()
        except Exception as e:
            logger.error(f"[IciciBroker.ws_connect] {e}", exc_info=True)

    def ws_subscribe(self, ws_obj, symbols: List[str]) -> None:
        """
        Subscribe to ICICI Breeze live feed.

        Breeze subscribe_feeds() uses stock_code, exchange_code and
        get_exchange_quotes feed_type. One call per symbol.

        symbol: "NSE:NIFTY50-INDEX" → stock_code="NIFTY", exchange_code="NSE"
        """
        try:
            if ws_obj is None or not symbols:
                return
            breeze = ws_obj.get("__breeze__") if isinstance(ws_obj, dict) else self.breeze
            if breeze is None:
                return

            for sym in symbols:
                exch, stock_code = self._resolve_breeze_symbol(sym)
                if not stock_code:
                    continue
                try:
                    breeze.subscribe_feeds(
                        exchange_code=exch,
                        stock_code=stock_code,
                        product_type="cash",
                        expiry_date="",
                        strike_price="",
                        right="",
                        get_exchange_quotes=True,
                        get_market_depth=False,
                    )
                    logger.info(f"IciciBroker: subscribed {exch}:{stock_code}")
                except Exception as e:
                    logger.error(f"IciciBroker.ws_subscribe({sym}): {e}")
        except Exception as e:
            logger.error(f"[IciciBroker.ws_subscribe] {e}", exc_info=True)

    def ws_unsubscribe(self, ws_obj, symbols: List[str]) -> None:
        """Unsubscribe from ICICI Breeze live feed."""
        try:
            if ws_obj is None or not symbols:
                return
            breeze = ws_obj.get("__breeze__") if isinstance(ws_obj, dict) else self.breeze
            if breeze is None:
                return
            for sym in symbols:
                exch, stock_code = self._resolve_breeze_symbol(sym)
                if stock_code:
                    breeze.unsubscribe_feeds(
                        exchange_code=exch,
                        stock_code=stock_code,
                        product_type="cash",
                        expiry_date="",
                        strike_price="",
                        right="",
                        get_exchange_quotes=True,
                        get_market_depth=False,
                    )
        except Exception as e:
            logger.error(f"[IciciBroker.ws_unsubscribe] {e}", exc_info=True)

    def ws_disconnect(self, ws_obj) -> None:
        """Close ICICI Breeze WebSocket."""
        try:
            if ws_obj is None:
                return
            breeze = ws_obj.get("__breeze__") if isinstance(ws_obj, dict) else self.breeze
            if breeze and hasattr(breeze, "ws_disconnect"):
                breeze.ws_disconnect()
            self._ws_on_close("disconnected")
            logger.info("IciciBroker: Breeze ws_disconnect() called")
        except Exception as e:
            logger.error(f"[IciciBroker.ws_disconnect] {e}", exc_info=True)

    def normalize_tick(self, raw_tick) -> Optional[Dict[str, Any]]:
        """
        Normalize an ICICI Breeze tick.

        Breeze on_ticks delivers a list of dicts per subscription.
        Each dict: stock_code, exchange_code, last, open, high, low, close,
                   best_bid_price, best_offer_price, total_quantity.
        """
        try:
            if isinstance(raw_tick, list):
                raw_tick = raw_tick[0] if raw_tick else None
            if not isinstance(raw_tick, dict):
                return None

            ltp = raw_tick.get("last") or raw_tick.get("ltp")
            if ltp is None:
                return None

            stock_code = raw_tick.get("stock_code", "")
            exch       = raw_tick.get("exchange_code", "NSE")
            symbol     = f"{exch}:{stock_code}"

            return {
                "symbol":    symbol,
                "ltp":       float(ltp),
                "timestamp": str(raw_tick.get("exchange_feed_time", "")),
                "bid":       raw_tick.get("best_bid_price"),
                "ask":       raw_tick.get("best_offer_price"),
                "volume":    raw_tick.get("total_quantity"),
                "oi":        raw_tick.get("open_interest"),
                "open":      raw_tick.get("open"),
                "high":      raw_tick.get("high"),
                "low":       raw_tick.get("low"),
                "close":     raw_tick.get("close"),
            }
        except Exception as e:
            logger.error(f"[IciciBroker.normalize_tick] {e}", exc_info=True)
            return None

    def _resolve_breeze_symbol(self, symbol: str):
        """Map generic NSE:SYMBOL → (exchange_code, stock_code) for Breeze."""
        try:
            upper = symbol.upper()
            bare  = symbol.split(":")[-1]
            # Strip Fyers-style suffixes like -INDEX, 50-INDEX
            stock_code = bare.replace("-INDEX", "").replace("50", "")
            exch = "NFO" if "NFO:" in upper else "NSE"
            return exch, stock_code
        except Exception:
            return "NSE", None