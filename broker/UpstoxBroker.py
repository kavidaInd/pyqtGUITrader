"""
brokers/UpstoxBroker.py
=======================
Upstox v2 SDK implementation of BaseBroker.

Prerequisites:
    pip install upstox-python-sdk

Authentication (OAuth2 PKCE flow):
    1. User visits get_login_url() in a browser
    2. After login, Upstox redirects to redirect_uri with `code` param
    3. Call generate_session(code) to exchange for access_token
    4. Token is saved to DB (valid until end of trading day)

Symbol format (Upstox instrument_key):
    NSE_EQ|ISIN   for equities  e.g. NSE_EQ|INE002A01018 (Reliance)
    NSE_FO|ISIN   for F&O       e.g. NSE_FO|...
    NSE_INDEX|Nifty 50

    For trading, Upstox uses instrument_key. This broker maps
    plain NSE:SYMBOL / NFO:SYMBOL to instrument_key via instruments API.

API docs: https://upstox.com/developer/api-documentation/
SDK:      pip install upstox-python-sdk

FIXED: Added proper token expiry tracking and propagation to central handler.
"""

import logging
import time
import random
import threading
from datetime import datetime
from Utils.common import to_date_str, timedelta
from typing import Optional, Dict, List, Any, Callable

import pandas as pd
from requests.exceptions import Timeout, ConnectionError

from Utils.safe_getattr import safe_getattr, safe_hasattr
from broker.BaseBroker import BaseBroker, TokenExpiredError
from broker.TokenExpiryHandler import token_expiry_handler
from db.connector import get_db
from db.crud import tokens

try:
    import upstox_client
    from upstox_client.rest import ApiException

    UPSTOX_AVAILABLE = True
except ImportError:
    UPSTOX_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Upstox product / order constants ─────────────────────────────────────────
UPSTOX_PRODUCT_INTRADAY = "I"  # MIS
UPSTOX_PRODUCT_DELIVERY = "D"  # CNC
UPSTOX_PRODUCT_MTF = "MTF"  # Margin Trade Financing

UPSTOX_ORDER_MARKET = "MARKET"
UPSTOX_ORDER_LIMIT = "LIMIT"
UPSTOX_ORDER_SL = "SL"
UPSTOX_ORDER_SLM = "SL-M"

UPSTOX_BUY = "BUY"
UPSTOX_SELL = "SELL"

# Upstox interval mapping: generic -> API
UPSTOX_INTERVAL_MAP = {
    "1": "1minute",
    "2": "2minute",
    "3": "3minute",
    "5": "5minute",
    "10": "10minute",
    "15": "15minute",
    "30": "30minute",
    "60": "60minute",
    "D": "day",
    "day": "day",
    "W": "week",
    "M": "month",
}


class UpstoxBroker(BaseBroker):
    """
    Upstox v2 SDK broker implementation.

    BrokerageSetting fields used:
        client_id    → Upstox API Key
        secret_key   → Upstox API Secret
        redirect_uri → OAuth2 redirect URI registered in developer console

    FIXED: Added proper token expiry tracking and propagation.
    """

    UPSTOX_AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
    UPSTOX_TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"

    # Upstox tokens expire at the end of the trading day
    SESSION_DURATION_HOURS = 8

    MAX_REQUESTS_PER_SECOND = 5  # Per broker API rate-limit docs
    def __init__(self, state, broker_setting=None):
        self._safe_defaults_init()
        try:
            if not UPSTOX_AVAILABLE:
                raise ImportError(
                    "upstox-python-sdk is not installed.\n"
                    "Run: pip install upstox-python-sdk"
                )
            self.state = state

            if broker_setting is None:
                raise ValueError("BrokerageSetting must be provided for UpstoxBroker.")

            self.api_key = safe_getattr(broker_setting, 'client_id', None)
            self.api_secret = safe_getattr(broker_setting, 'secret_key', None)
            self.redirect_uri = safe_getattr(broker_setting, 'redirect_uri', None)

            # Token expiry tracking
            self._token_expiry = None
            self._token_issued_at = None
            self._last_token_check = 0
            self._token_expiry_check_interval = 60  # seconds

            # Load saved token
            access_token = self._load_token_from_db()

            # Configure SDK
            self._config = upstox_client.Configuration()
            if access_token:
                self._config.access_token = access_token
                self.state.token = access_token
                self._token_issued_at = self._parse_token_issued_at()
                self._token_expiry = self._parse_token_expiry()
                self._build_api_clients()
                logger.info("UpstoxBroker: token loaded from DB")

                if self.is_token_expired:
                    logger.warning("UpstoxBroker: token is expired")
            else:
                logger.warning("UpstoxBroker: no token found — call generate_session(code)")

            # WebSocket cleanup tracking
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()
            self._ws_streamer = None

            # Register with token expiry handler
            self._token_handler = token_expiry_handler

            logger.info("UpstoxBroker initialized")

        except Exception as e:
            logger.critical(f"[UpstoxBroker.__init__] {e}", exc_info=True)
            raise

    @property
    def broker_type(self) -> str:
        return "upstox"

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
        self.api_key = None
        self.api_secret = None
        self.redirect_uri = None
        self._config = None
        self._api_client = None
        self._order_api = None
        self._portfolio_api = None
        self._market_quote_api = None
        self._history_api = None
        self._user_api = None
        self._last_request_time = 0
        self._rate_lock = threading.Lock()
        self._request_count = 0
        self._token_expiry = None
        self._token_issued_at = None
        self._last_token_check = 0
        self._instrument_cache: Dict[str, str] = {}

        # WebSocket cleanup tracking
        self._ws_closed = False
        self._ws_cleanup_event = None
        self._ws_streamer = None
        self._ws_on_tick = None
        self._ws_on_connect = None
        self._ws_on_close = None
        self._ws_on_error = None

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
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
                    try:
                        dt = datetime.strptime(issued_str, fmt)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
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
        logger.info("[UpstoxBroker] Token recovered, re-login required")

    def _build_api_clients(self):
        """Instantiate all Upstox API sub-clients."""
        self._api_client = upstox_client.ApiClient(self._config)
        self._order_api = upstox_client.OrderApiV3(self._api_client)
        self._portfolio_api = upstox_client.PortfolioApi(self._api_client)
        self._market_quote_api = upstox_client.MarketQuoteApi(self._api_client)
        self._history_api = upstox_client.HistoryApi(self._api_client)
        self._user_api = upstox_client.UserApi(self._api_client)

    # ── Authentication ────────────────────────────────────────────────────────

    def get_login_url(self) -> str:
        """Return OAuth2 authorization URL for the user to visit."""
        return (f"{self.UPSTOX_AUTH_URL}"
                f"?response_type=code"
                f"&client_id={self.api_key}"
                f"&redirect_uri={self.redirect_uri}")

    def generate_session(self, auth_code: str) -> Optional[str]:
        """
        Exchange the OAuth2 authorization code for an access token.
        Call this once after the user completes the login redirect.
        """
        try:
            import requests
            payload = {
                "code": auth_code,
                "client_id": self.api_key,
                "client_secret": self.api_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            }
            resp = requests.post(self.UPSTOX_TOKEN_URL, data=payload,
                                 headers={"accept": "application/json"}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            access_token = data.get("access_token")
            if access_token:
                self._config.access_token = access_token
                self.state.token = access_token

                # Update token timestamps
                issued_at = datetime.now()
                expires_at = issued_at + timedelta(hours=self.SESSION_DURATION_HOURS)
                self._token_issued_at = issued_at
                self._token_expiry = expires_at

                self._build_api_clients()
                db = get_db()
                tokens.save_token(
                    access_token, "",
                    issued_at=issued_at.isoformat(),
                    expires_at=expires_at.isoformat(),
                    db=db
                )
                logger.info("UpstoxBroker: session generated and token saved")
                return access_token
            return None
        except Exception as e:
            logger.error(f"[UpstoxBroker.generate_session] {e}", exc_info=True)
            return None

    def _load_token_from_db(self) -> Optional[str]:
        try:
            db = get_db()
            token_data = tokens.get(db)
            if token_data and token_data.get("access_token"):
                return token_data["access_token"]
            return None
        except Exception as e:
            logger.error(f"[UpstoxBroker._load_token_from_db] {e}", exc_info=True)
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

    # ── Symbol helpers ────────────────────────────────────────────────────────

    def _get_instrument_key(self, symbol: str) -> Optional[str]:
        """
        Map NSE:SYMBOL / NFO:SYMBOL to Upstox instrument_key (e.g. NSE_EQ|INE002A01018).
        Uses the Upstox instruments API (cached per session).
        """
        if symbol in self._instrument_cache:
            return self._instrument_cache[symbol]
        try:
            instruments = self._load_upstox_instruments()
            if instruments is None:
                return None
            clean = symbol.split(":")[-1]
            match = instruments[instruments['tradingsymbol'] == clean]
            if not match.empty:
                key = str(match.iloc[0]['instrument_key'])
                self._instrument_cache[symbol] = key
                return key
            logger.warning(f"UpstoxBroker: instrument_key not found for {symbol}")
            return None
        except Exception as e:
            logger.error(f"[UpstoxBroker._get_instrument_key] {e}", exc_info=True)
            return None

    @staticmethod
    def _load_upstox_instruments():
        if not safe_hasattr(UpstoxBroker, '_instruments_df') or UpstoxBroker._instruments_df is None:
            try:
                nse_url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz"
                nfo_url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE_FO.csv.gz"
                nse = pd.read_csv(nse_url, compression="gzip")
                nfo = pd.read_csv(nfo_url, compression="gzip")
                UpstoxBroker._instruments_df = pd.concat([nse, nfo], ignore_index=True)
                logger.info("UpstoxBroker: instrument master loaded")
            except Exception as e:
                logger.error(f"UpstoxBroker: instrument load failed: {e}", exc_info=True)
                UpstoxBroker._instruments_df = None
        return UpstoxBroker._instruments_df

    _instruments_df = None

    @staticmethod
    def _to_upstox_interval(interval: str) -> str:
        return UPSTOX_INTERVAL_MAP.get(str(interval), "1minute")

    @staticmethod
    def _to_upstox_side(side: int) -> str:
        return UPSTOX_BUY if side == BaseBroker.SIDE_BUY else UPSTOX_SELL

    # ── BaseBroker implementation ─────────────────────────────────────────────

    def get_profile(self) -> Optional[Dict]:
        self._check_token_before_request()
        try:
            if not self._user_api:
                return None
            result = self._call(
                lambda: self._user_api.get_profile(api_version="2.0"),
                context="get_profile"
            )
            return result.data if result else None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.get_profile] {e!r}", exc_info=True)
            return None

    def get_balance(self, capital_reserve: float = 0.0) -> float:
        self._check_token_before_request()
        try:
            if not self._user_api:
                return 0.0
            result = self._call(
                lambda: self._user_api.get_user_fund_margin(api_version="2.0"),
                context="get_balance"
            )
            if result and result.data and result.data.equity:
                available = float(result.data.equity.available_margin or 0.0)
                if capital_reserve > 0:
                    available = available * (1 - capital_reserve / 100)
                return available
            return 0.0
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.get_balance] {e!r}", exc_info=True)
            return 0.0

    def get_history(self, symbol: str, interval: str = "2", length: int = 400):
        self._check_token_before_request()
        try:
            if not symbol or not self._history_api:
                return None
            instrument_key = self._get_instrument_key(symbol)
            if not instrument_key:
                return None
            upstox_interval = self._to_upstox_interval(interval)
            self._check_rate_limit()
            result = self._call(
                lambda: self._history_api.get_intra_day_candle_data(
                    instrument_key,
                    upstox_interval,
                    api_version="2.0"
                ),
                context="get_history"
            )
            if result and result.data and result.data.candles:
                candles = result.data.candles
                df = pd.DataFrame(candles, columns=["time", "open", "high", "low", "close", "volume", "oi"])
                return df.tail(length)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.get_history] {e!r}", exc_info=True)
            return None

    def get_history_for_timeframe(self, symbol: str, interval: str, days: int = 30):
        self._check_token_before_request()
        try:
            if not symbol or not self._history_api:
                return None
            instrument_key = self._get_instrument_key(symbol)
            if not instrument_key:
                return None
            fetch_days = max(days, 60) if interval in ["15", "30", "60"] else (
                max(days, 120) if interval in ["120", "240"] else days
            )
            to_date = to_date_str(datetime.now())
            from_date = to_date_str(datetime.now() - timedelta(days=fetch_days))
            upstox_interval = self._to_upstox_interval(interval)
            self._check_rate_limit()
            result = self._call(
                lambda: self._history_api.get_historical_candle_data(
                    instrument_key,
                    upstox_interval,
                    to_date,
                    from_date,
                    api_version="2.0"
                ),
                context="get_history_for_timeframe"
            )
            if result and result.data and result.data.candles:
                df = pd.DataFrame(result.data.candles,
                                  columns=["time", "open", "high", "low", "close", "volume", "oi"])
                df["time"] = pd.to_datetime(df["time"])
                return df
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.get_history_for_timeframe] {e!r}", exc_info=True)
            return None

    def get_option_current_price(self, option_name: str) -> Optional[float]:
        quote = self.get_option_quote(option_name)
        return quote.get("ltp") if quote else None

    def get_option_quote(self, option_name: str) -> Optional[Dict[str, float]]:
        self._check_token_before_request()
        try:
            if not option_name or not self._market_quote_api:
                return None
            instrument_key = self._get_instrument_key(option_name)
            if not instrument_key:
                return None
            self._check_rate_limit()
            result = self._call(
                lambda: self._market_quote_api.get_full_market_quote(
                    instrument_key, api_version="2.0"
                ),
                context="get_option_quote"
            )
            if result and result.data:
                q = list(result.data.values())[0]
                depth = safe_getattr(q, 'depth', None)
                bid = ask = None
                if depth:
                    bids = safe_getattr(depth, 'buy', [])
                    asks = safe_getattr(depth, 'sell', [])
                    bid = bids[0].price if bids else None
                    ask = asks[0].price if asks else None
                ohlc = safe_getattr(q, 'ohlc', None)
                return {
                    "ltp": safe_getattr(q, 'last_price', None),
                    "bid": bid, "ask": ask,
                    "high": safe_getattr(ohlc, 'high', None) if ohlc else None,
                    "low": safe_getattr(ohlc, 'low', None) if ohlc else None,
                    "open": safe_getattr(ohlc, 'open', None) if ohlc else None,
                    "close": safe_getattr(ohlc, 'close', None) if ohlc else None,
                    "volume": safe_getattr(q, 'volume', None),
                    "oi": safe_getattr(q, 'oi', None),
                }
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.get_option_quote] {e!r}", exc_info=True)
            return None

    def get_option_chain_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        self._check_token_before_request()
        try:
            if not symbols or not self._market_quote_api:
                return {}
            keys = [self._get_instrument_key(s) for s in symbols if s]
            keys = [k for k in keys if k]
            if not keys:
                return {}
            self._check_rate_limit()
            result = self._call(
                lambda: self._market_quote_api.get_full_market_quote(
                    ",".join(keys), api_version="2.0"
                ),
                context="get_option_chain_quotes"
            )
            out = {}
            if result and result.data:
                for ikey, q in result.data.items():
                    clean = ikey.split("|")[-1]
                    depth = safe_getattr(q, 'depth', None)
                    bid = ask = None
                    if depth:
                        bids = safe_getattr(depth, 'buy', [])
                        asks = safe_getattr(depth, 'sell', [])
                        bid = bids[0].price if bids else None
                        ask = asks[0].price if asks else None
                    out[clean] = {
                        "ltp": safe_getattr(q, 'last_price', None),
                        "bid": bid,
                        "ask": ask,
                        "volume": safe_getattr(q, 'volume', None),
                        "oi": safe_getattr(q, 'oi', None),
                    }
            return out
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.get_option_chain_quotes] {e!r}", exc_info=True)
            return {}

    def place_order(self, **kwargs) -> Optional[str]:
        self._check_token_before_request()
        try:
            if not self._order_api:
                return None
            symbol = kwargs.get('symbol')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_BUY)
            order_type = kwargs.get('order_type', self.MARKET_ORDER_TYPE)
            product = kwargs.get('product_type', UPSTOX_PRODUCT_INTRADAY)
            limit_price = float(kwargs.get('limitPrice', 0) or 0)
            stop_price = float(kwargs.get('stopPrice', 0) or 0)

            if not symbol or qty <= 0:
                return None

            instrument_key = self._get_instrument_key(symbol)
            if not instrument_key:
                return None

            upstox_order_type = {
                self.MARKET_ORDER_TYPE: UPSTOX_ORDER_MARKET,
                self.LIMIT_ORDER_TYPE: UPSTOX_ORDER_LIMIT,
                self.STOPLOSS_MARKET_ORDER_TYPE: UPSTOX_ORDER_SLM,
            }.get(order_type, UPSTOX_ORDER_MARKET)

            body = upstox_client.PlaceOrderV3Request(
                quantity=qty,
                product=product,
                validity="DAY",
                price=limit_price,
                tag="algotrade",
                instrument_token=instrument_key,
                order_type=upstox_order_type,
                transaction_type=self._to_upstox_side(side),
                disclosed_quantity=0,
                trigger_price=stop_price,
                is_amo=False,
            )

            self._check_rate_limit()
            result = self._call(lambda: self._order_api.place_order(body), context="place_order")
            if result and result.data:
                order_id = result.data.order_id
                logger.info(f"UpstoxBroker: order placed {order_id}")
                return str(order_id)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.place_order] {e!r}", exc_info=True)
            return None

    def modify_order(self, **kwargs) -> bool:
        self._check_token_before_request()
        try:
            order_id = kwargs.get('order_id')
            limit_price = float(kwargs.get('limit_price', 0) or 0)
            qty = int(kwargs.get('qty', 0))
            if not order_id or not self._order_api:
                return False
            body = upstox_client.ModifyOrderRequest(
                quantity=qty, price=limit_price,
                order_type=UPSTOX_ORDER_LIMIT,
                validity="DAY", disclosed_quantity=0, trigger_price=0.0
            )
            self._check_rate_limit()
            result = self._call(
                lambda: self._order_api.modify_order(body, order_id),
                context="modify_order"
            )
            return result is not None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.modify_order] {e!r}", exc_info=True)
            return False

    def cancel_order(self, **kwargs) -> bool:
        self._check_token_before_request()
        try:
            order_id = kwargs.get('order_id')
            if not order_id or not self._order_api:
                return False
            self._check_rate_limit()
            result = self._call(
                lambda: self._order_api.cancel_order(order_id),
                context="cancel_order"
            )
            return result is not None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.cancel_order] {e!r}", exc_info=True)
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
            if not self._portfolio_api:
                return []
            result = self._call(
                lambda: self._portfolio_api.get_positions(api_version="2.0"),
                context="get_positions"
            )
            positions = []
            if result and result.data:
                for p in result.data:
                    positions.append({
                        "instrument_key": safe_getattr(p, 'instrument_key', ''),
                        "quantity": safe_getattr(p, 'quantity', 0),
                        "average_price": safe_getattr(p, 'average_price', 0.0),
                        "last_price": safe_getattr(p, 'last_price', 0.0),
                        "pnl": safe_getattr(p, 'pnl', 0.0),
                        "product": safe_getattr(p, 'product', ''),
                        "exchange": safe_getattr(p, 'exchange', ''),
                    })
            return positions
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.get_positions] {e!r}", exc_info=True)
            return []

    def get_orderbook(self) -> List[Dict[str, Any]]:
        self._check_token_before_request()
        try:
            if not self._order_api:
                return []
            result = self._call(
                lambda: self._order_api.get_order_book(api_version="2.0"),
                context="get_orderbook"
            )
            orders = []
            if result and result.data:
                for o in result.data:
                    orders.append({
                        "order_id": safe_getattr(o, 'order_id', ''),
                        "instrument_key": safe_getattr(o, 'instrument_key', ''),
                        "quantity": safe_getattr(o, 'quantity', 0),
                        "filled_quantity": safe_getattr(o, 'filled_quantity', 0),
                        "status": safe_getattr(o, 'status', ''),
                        "average_price": safe_getattr(o, 'average_price', 0.0),
                        "price": safe_getattr(o, 'price', 0.0),
                        "trigger_price": safe_getattr(o, 'trigger_price', 0.0),
                        "order_type": safe_getattr(o, 'order_type', ''),
                        "transaction_type": safe_getattr(o, 'transaction_type', ''),
                        "product": safe_getattr(o, 'product', ''),
                    })
            return orders
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.get_orderbook] {e!r}", exc_info=True)
            return []

    def get_current_order_status(self, order_id: str) -> Optional[int]:
        """
        Return order status as integer:
        2 = filled, 1 = pending/open, -1 = rejected/cancelled, None = not found
        """
        self._check_token_before_request()
        try:
            if not order_id or not self._order_api:
                return None

            result = self._call(
                lambda: self._order_api.get_order_details(
                    order_id=order_id, api_version="2.0"
                ),
                context="order_status"
            )

            if not result or not result.data:
                return None

            status_str = str(safe_getattr(result.data, 'status', '')).lower()
            if status_str in ("complete", "filled", "traded", "executed"):
                return 2
            if status_str in ("rejected", "cancelled", "canceled", "expired"):
                return -1
            # open, pending, after_market_order_req_received, etc.
            return 1
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[UpstoxBroker.get_current_order_status] {e!r}", exc_info=True)
            return None

    def get_fill_price(self, broker_order_id: str) -> Optional[float]:
        """
        Return the actual average fill price for a completed order.
        Upstox order details include 'average_price' for filled orders.
        """
        self._check_token_before_request()
        try:
            if not broker_order_id or not self._order_api:
                return None

            result = self._call(
                lambda: self._order_api.get_order_details(
                    order_id=broker_order_id, api_version="2.0"
                ),
                context="get_fill_price"
            )

            if result and result.data:
                avg = safe_getattr(result.data, 'average_price', None)
                if avg:
                    return float(avg)
            return None
        except Exception as e:
            logger.error(f"[UpstoxBroker.get_fill_price] {e!r}", exc_info=True)
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
        Upstox instrument_key format: ``NSE_FO|<ISIN>``

        Upstox does NOT accept text tradingsymbols for options — it requires
        a pre-mapped instrument_key from the Upstox instrument CSV.
        This method builds the NSE compact core and looks it up via
        ``_get_instrument_key()``.  Returns compact core as fallback.
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
            logger.error(f"[UpstoxBroker.build_option_symbol] {e}", exc_info=True)
            return None

    def _params_to_symbol(self, params) -> Optional[str]:
        """UpstoxBroker symbol from OptionParams."""
        if not params:
            return None
        core = params.compact_core
        try:
            key = self._get_instrument_key(f"NFO:{core}")
            if key:
                return key
        except Exception:
            pass
        logger.warning(
            f"[UpstoxBroker._params_to_symbol] instrument_key not found for "
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
        """Upstox option chain as instrument_key strings."""
        try:
            from Utils.OptionSymbolBuilder import OptionSymbolBuilder
            all_params = OptionSymbolBuilder.get_all_option_params(
                underlying=underlying, spot_price=spot_price,
                option_type=option_type, weeks_offset=weeks_offset,
                itm=itm, otm=otm,
            )
            return [s for s in (self._params_to_symbol(p) for p in all_params) if s]
        except Exception as e:
            logger.error(f"[UpstoxBroker.build_option_chain] {e}", exc_info=True)
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
        logger.info("[UpstoxBroker] Starting cleanup")

        # Mark WebSocket as closed to prevent callbacks
        self._ws_closed = True

        # Clean up WebSocket if it exists
        if self._ws_streamer is not None:
            try:
                # Try to disconnect with timeout
                self._ws_cleanup_event.clear()

                def _do_disconnect():
                    try:
                        if safe_hasattr(self._ws_streamer, "disconnect"):
                            self._ws_streamer.disconnect()
                            logger.debug("[UpstoxBroker] disconnect called")
                    except Exception as e:
                        logger.warning(f"[UpstoxBroker] Error disconnecting WebSocket: {e}")
                    finally:
                        self._ws_cleanup_event.set()

                # Run disconnect in separate thread with timeout
                disconnect_thread = threading.Thread(target=_do_disconnect, daemon=True)
                disconnect_thread.start()

                # Wait for disconnect with timeout
                if not self._ws_cleanup_event.wait(timeout=2.0):
                    logger.warning("[UpstoxBroker] WebSocket disconnect timed out")

            except Exception as e:
                logger.error(f"[UpstoxBroker] Error during WebSocket cleanup: {e}", exc_info=True)
            finally:
                self._ws_streamer = None

        # Clear callbacks
        self._ws_on_tick = None
        self._ws_on_connect = None
        self._ws_on_close = None
        self._ws_on_error = None

        logger.info("[UpstoxBroker] Cleanup completed")

    # ── Internal call wrapper ─────────────────────────────────────────────────

    def _call(self, func: Callable, context: str = "",
              max_retries: int = 3, base_delay: int = 1):
        for attempt in range(max_retries):
            try:
                self._check_token_before_request()
                self._check_rate_limit()
                return func()
            except ApiException as e:
                if e.status in (401, 403):
                    raise TokenExpiredError(f"Upstox auth error: {e.body}")
                if e.status == 429:
                    delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                    logger.warning(f"[Upstox.{context}] Rate limit, retry {attempt + 1}")
                    time.sleep(delay)
                elif e.status in (500, 502, 503):
                    delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                    logger.warning(f"[Upstox.{context}] Server error {e.status}, retry {attempt + 1}")
                    time.sleep(delay)
                else:
                    logger.error(f"[Upstox.{context}] ApiException {e.status}: {e.body}")
                    return None
            except (Timeout, ConnectionError) as e:
                delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning(f"[Upstox.{context}] Network error, retry {attempt + 1}: {e}")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"[Upstox.{context}] Unexpected: {e!r}", exc_info=True)
                return None
        logger.critical(f"[Upstox.{context}] Max retries reached.")
        return None

    # ── WebSocket interface ────────────────────────────────────────────────────

    def create_websocket(self, on_tick, on_connect, on_close, on_error) -> Any:
        """
        Create Upstox MarketDataStreamer.

        Upstox v2 streams market data via protobuf over WebSocket.
        The SDK's MarketDataStreamer handles auth automatically using
        the access_token set in the configuration.

        FIXED: Added state tracking and stored callbacks.
        """
        try:
            import upstox_client  # type: ignore
            from upstox_client import MarketDataStreamer  # type: ignore

            access_token = safe_getattr(self.state, "token", None) if self.state else None
            if not access_token:
                logger.error("UpstoxBroker.create_websocket: no access_token — call login first")
                return None

            # Check token before creating websocket
            if self.is_token_expired:
                self._handle_token_expired("Cannot create websocket with expired token")

            # Reset WebSocket state
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()

            configuration = upstox_client.Configuration()
            configuration.access_token = access_token

            # Store callbacks
            self._ws_on_tick = on_tick
            self._ws_on_connect = on_connect
            self._ws_on_close = on_close
            self._ws_on_error = on_error

            # Create streamer with safety-wrapped callbacks
            streamer = MarketDataStreamer(
                upstox_client.ApiClient(configuration),
                [],  # instruments list — populated in ws_subscribe
                "full",  # mode: "ltpc" | "full" | "option_greeks"
            )

            def safe_on_message(data):
                if not self._ws_closed:
                    on_tick(data)

            def safe_on_open():
                if not self._ws_closed:
                    on_connect()

            def safe_on_close():
                if not self._ws_closed:
                    on_close("connection closed")

            def safe_on_error(e):
                if not self._ws_closed:
                    on_error(str(e))

            streamer.on("message", safe_on_message)
            streamer.on("open", safe_on_open)
            streamer.on("close", safe_on_close)
            streamer.on("error", safe_on_error)

            self._ws_streamer = streamer
            logger.info("UpstoxBroker: MarketDataStreamer object created")
            return streamer
        except ImportError:
            logger.error("UpstoxBroker: upstox_client not installed — pip install upstox-python-sdk")
            return None
        except Exception as e:
            logger.error(f"[UpstoxBroker.create_websocket] {e}", exc_info=True)
            return None

    def ws_connect(self, ws_obj) -> None:
        """Start Upstox MarketDataStreamer (non-blocking)."""
        try:
            if ws_obj is None or self._ws_closed:
                return
            ws_obj.connect()
            logger.info("UpstoxBroker: MarketDataStreamer connect() called")
        except Exception as e:
            logger.error(f"[UpstoxBroker.ws_connect] {e}", exc_info=True)

    def ws_subscribe(self, ws_obj, symbols: List[str]) -> None:
        """
        Subscribe to Upstox live feed.

        Upstox uses instrument_key format: "NSE_EQ|ISIN" or "NSE_INDEX|Nifty 50".
        Generic NSE:SYMBOL is mapped via _resolve_upstox_key().
        """
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return

            keys = []
            for sym in symbols:
                key = self._resolve_upstox_key(sym)
                if key:
                    keys.append(key)

            if not keys:
                logger.warning("UpstoxBroker.ws_subscribe: no valid instrument keys")
                return

            ws_obj.subscribe(keys, "full")
            logger.info(f"UpstoxBroker: subscribed {len(keys)} instrument keys")
        except Exception as e:
            logger.error(f"[UpstoxBroker.ws_subscribe] {e}", exc_info=True)

    def ws_unsubscribe(self, ws_obj, symbols: List[str]) -> None:
        """Unsubscribe from Upstox live feed."""
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return
            keys = [self._resolve_upstox_key(s) for s in symbols]
            keys = [k for k in keys if k]
            if keys:
                ws_obj.unsubscribe(keys)
        except Exception as e:
            logger.error(f"[UpstoxBroker.ws_unsubscribe] {e}", exc_info=True)

    def ws_disconnect(self, ws_obj) -> None:
        """
        Stop Upstox MarketDataStreamer with timeout protection.

        FIXED: Added timeout and better error handling.
        """
        try:
            if ws_obj is None:
                return

            logger.info("[UpstoxBroker] Starting WebSocket disconnect")
            self._ws_closed = True

            # Run disconnect in separate thread with timeout
            disconnect_complete = threading.Event()

            def _do_disconnect():
                try:
                    if safe_hasattr(ws_obj, "disconnect"):
                        ws_obj.disconnect()
                        logger.debug("[UpstoxBroker] disconnect completed")
                except Exception as e:
                    logger.warning(f"[UpstoxBroker] disconnect error: {e}")
                finally:
                    disconnect_complete.set()

            disconnect_thread = threading.Thread(target=_do_disconnect, daemon=True)
            disconnect_thread.start()

            # Wait for disconnect with timeout
            if not disconnect_complete.wait(timeout=2.0):
                logger.warning("[UpstoxBroker] disconnect timed out")

            # Clear reference
            if self._ws_streamer == ws_obj:
                self._ws_streamer = None

            # Call on_close callback
            if self._ws_on_close:
                try:
                    self._ws_on_close("disconnected by user")
                except Exception as e:
                    logger.warning(f"[UpstoxBroker] Error in close callback: {e}")

            logger.info("[UpstoxBroker] WebSocket disconnect completed")

        except Exception as e:
            logger.error(f"[UpstoxBroker.ws_disconnect] {e}", exc_info=True)

    def normalize_tick(self, raw_tick) -> Optional[Dict[str, Any]]:
        """
        Normalize an Upstox MarketDataStreamer tick.
        """
        try:
            if self._ws_closed or not isinstance(raw_tick, dict):
                return None

            feeds = raw_tick.get("feeds", {})
            if not feeds:
                return None

            results = []
            for instrument_key, feed_data in feeds.items():
                full_feed = feed_data.get("ff", {}).get("marketFF", {}) or \
                            feed_data.get("ff", {}).get("indexFF", {})
                if not full_feed:
                    continue
                ltpc = full_feed.get("ltpc", {})
                ltp = ltpc.get("ltp")
                if ltp is None:
                    continue

                ohlc_data = full_feed.get("dayOhlc", {})
                depth = full_feed.get("marketLevel", {})
                bid_ask_quotes = depth.get("bidAskQuote", [])

                # Extract best bid and ask
                bid = None
                ask = None
                for quote in bid_ask_quotes:
                    if "bp" in quote and quote.get("bp"):  # bid price
                        bid = quote.get("bp")
                    if "sp" in quote and quote.get("sp"):  # ask price
                        ask = quote.get("sp")

                # Convert instrument_key back to app format
                # "NSE_EQ|INE002A01018" → "NSE:INE002A01018"
                sym_parts = instrument_key.split("|")
                exch = sym_parts[0].split("_")[0] if sym_parts else "NSE"
                bare_sym = sym_parts[1] if len(sym_parts) > 1 else instrument_key
                symbol = f"{exch}:{bare_sym}"

                ts = full_feed.get("ltt") or raw_tick.get("currentTs", "")

                results.append({
                    "symbol": symbol,
                    "ltp": float(ltp),
                    "timestamp": str(ts),
                    "bid": float(bid) if bid else None,
                    "ask": float(ask) if ask else None,
                    "volume": full_feed.get("vtt"),
                    "oi": full_feed.get("oi"),
                    "open": ohlc_data.get("open"),
                    "high": ohlc_data.get("high"),
                    "low": ohlc_data.get("low"),
                    "close": ohlc_data.get("close"),
                })

            # Return first tick — WebSocketManager handles one at a time
            return results[0] if results else None
        except Exception as e:
            if not self._ws_closed:  # Only log if not during shutdown
                logger.error(f"[UpstoxBroker.normalize_tick] {e}", exc_info=True)
            return None

    def _resolve_upstox_key(self, symbol: str) -> Optional[str]:
        """
        Map generic NSE:SYMBOL → Upstox instrument_key.

        Index symbols: "NSE:NIFTY50-INDEX" → "NSE_INDEX|Nifty 50"
        Equity/F&O: "NSE:RELIANCE" → "NSE_EQ|ISIN" (requires instruments lookup)

        Fallback: return "NSE_EQ|<bare_symbol>" for unknown symbols.
        """
        try:
            cache = safe_getattr(self, "_upstox_key_cache", {})
            if symbol in cache:
                return cache[symbol]

            upper = symbol.upper()
            bare = symbol.split(":")[-1]

            # Known index mappings
            index_map = {
                "NIFTY50-INDEX": "NSE_INDEX|Nifty 50",
                "NIFTY 50": "NSE_INDEX|Nifty 50",
                "BANKNIFTY": "NSE_INDEX|Nifty Bank",
                "SENSEX": "BSE_INDEX|SENSEX",
            }
            for k, v in index_map.items():
                if k in upper:
                    cache[symbol] = v
                    self._upstox_key_cache = cache
                    return v

            if "NFO:" in upper:
                key = f"NFO_FO|{bare}"
            elif "BSE:" in upper:
                key = f"BSE_EQ|{bare}"
            else:
                key = f"NSE_EQ|{bare}"

            cache[symbol] = key
            self._upstox_key_cache = cache
            return key
        except Exception:
            return None