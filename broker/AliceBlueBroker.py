"""
brokers/AliceBlueBroker.py
==========================
Alice Blue ANT API (pya3) implementation of BaseBroker.

Prerequisites:
    pip install pya3

Authentication (username + password + YOB + app_id + api_secret):
    BrokerageSetting fields:
        client_id    → App ID (from https://ant.aliceblueonline.com → Apps)
        secret_key   → API Secret (from Alice Blue Apps page)
        redirect_uri → "username|password|YOB"  (pipe-separated user credentials)
                       e.g.  "AB12345|mypassword|1990"
                       YOB = Year of Birth (used as 2FA answer)

    Auth flow — fully automatic:
        broker.login()  ← generates session using credentials from redirect_uri

    Note: Alice Blue does NOT provide historical OHLC data through their official
    Python SDK. get_history returns None. Use an alternative data source for backtesting.

API docs: https://ant.aliceblueonline.com/developers
SDK:      pip install pya3
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
    from pya3 import Aliceblue, TransactionType, OrderType, ProductType, Exchange
    ALICE_AVAILABLE = True
except ImportError:
    try:
        from alice_blue import AliceBlue, TransactionType, OrderType, ProductType  # type: ignore
        Aliceblue = AliceBlue
        ALICE_AVAILABLE = True
    except ImportError:
        ALICE_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Alice Blue exchange / product / order constants ───────────────────────────
ALICE_NSE = "NSE"
ALICE_NFO = "NFO"
ALICE_BSE = "BSE"
ALICE_MCX = "MCX"

ALICE_PRODUCT_MIS  = "MIS"
ALICE_PRODUCT_NRML = "NRML"
ALICE_PRODUCT_CNC  = "CNC"

ALICE_ORDER_MARKET = "MKT"
ALICE_ORDER_LIMIT  = "L"
ALICE_ORDER_SL     = "SL"
ALICE_ORDER_SLM    = "SL-M"

ALICE_BUY  = "BUY"
ALICE_SELL = "SELL"


class AliceBlueBroker(BaseBroker):
    """
    Alice Blue ANT API broker implementation.

    BrokerageSetting fields:
        client_id    → App ID (from Alice Blue developer console)
        secret_key   → API Secret
        redirect_uri → "username|password|YOB" (pipe-separated)
                        YOB = year of birth used as 2FA answer
    """

    def __init__(self, state, broker_setting=None):
        self._safe_defaults_init()
        try:
            if not ALICE_AVAILABLE:
                raise ImportError(
                    "pya3 is not installed.\n"
                    "Run: pip install pya3"
                )
            self.state = state

            if broker_setting is None:
                raise ValueError("BrokerageSetting must be provided for AliceBlueBroker.")

            self.app_id     = getattr(broker_setting, 'client_id', None)
            self.api_secret = getattr(broker_setting, 'secret_key', None)

            # Parse "username|password|YOB" from redirect_uri
            creds_raw = getattr(broker_setting, 'redirect_uri', '') or ''
            cred_parts = creds_raw.split("|")
            self.username = cred_parts[0] if len(cred_parts) > 0 else None
            self.password = cred_parts[1] if len(cred_parts) > 1 else None
            self.yob      = cred_parts[2] if len(cred_parts) > 2 else None

            if not self.app_id or not self.api_secret or not self.username:
                raise ValueError(
                    "AliceBlue requires app_id (client_id), api_secret (secret_key), "
                    "and username|password|YOB in redirect_uri."
                )

            # Try to restore saved session
            saved_session = self._load_token_from_db()
            if saved_session:
                self.alice = Aliceblue(
                    user_id=self.username,
                    api_key=self.api_secret,
                    session_id=saved_session
                )
                self.state.token = saved_session
                logger.info("AliceBlueBroker: session restored from DB")
            else:
                logger.warning("AliceBlueBroker: no session — call broker.login()")
                self.alice = None

            logger.info("AliceBlueBroker initialized")

        except Exception as e:
            logger.critical(f"[AliceBlueBroker.__init__] {e}", exc_info=True)
            raise

    def _safe_defaults_init(self):
        self.state = None
        self.app_id = None
        self.api_secret = None
        self.username = None
        self.password = None
        self.yob = None
        self.alice = None
        self._last_request_time = 0
        self._request_count = 0

    # ── Authentication ────────────────────────────────────────────────────────

    def login(self) -> bool:
        """
        Authenticate using stored credentials (username, password, YOB).
        Generates a session_id and saves it to DB.

        Returns:
            True on success
        """
        try:
            if not self.password or not self.yob:
                raise ValueError(
                    "Password and YOB required. "
                    "Store as 'username|password|YOB' in redirect_uri field."
                )

            session_id = Aliceblue.login_and_get_access_token(
                username=self.username,
                password=self.password,
                twoFA=self.yob,
                api_secret=self.api_secret,
                app_id=self.app_id,
            )

            if not session_id:
                logger.error("AliceBlueBroker: login failed — no session_id returned")
                return False

            # Build the client with the new session
            self.alice = Aliceblue(
                user_id=self.username,
                api_key=self.api_secret,
                session_id=session_id
            )
            self.state.token = session_id

            expires_at = (datetime.now() + timedelta(hours=10)).isoformat()
            db = get_db()
            tokens.save_token(session_id, "", expires_at=expires_at, db=db)
            logger.info("AliceBlueBroker: login successful")
            return True

        except Exception as e:
            logger.error(f"[AliceBlueBroker.login] {e}", exc_info=True)
            return False

    def _load_token_from_db(self) -> Optional[str]:
        try:
            db = get_db()
            token_data = tokens.get(db)
            if token_data and token_data.get("access_token"):
                return token_data["access_token"]
            return None
        except Exception as e:
            logger.error(f"[AliceBlueBroker._load_token_from_db] {e}", exc_info=True)
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

    # ── Symbol / instrument helpers ───────────────────────────────────────────

    def _get_instrument(self, symbol: str, exchange: Optional[str] = None):
        """
        Alice Blue requires an instrument object (not just the symbol string).
        Fetches from master contracts.
        """
        try:
            if not self.alice:
                return None
            if exchange is None:
                exchange = self._exchange_from_symbol(symbol)
            clean = symbol.split(":")[-1]
            instrument = self.alice.get_instrument_by_symbol(exchange, clean)
            if not instrument:
                # Try with -EQ suffix
                instrument = self.alice.get_instrument_by_symbol(exchange, f"{clean}-EQ")
            return instrument
        except Exception as e:
            logger.error(f"[AliceBlueBroker._get_instrument] {e}", exc_info=True)
            return None

    @staticmethod
    def _exchange_from_symbol(symbol: str) -> str:
        s = symbol.upper()
        if s.startswith("NFO:") or "CE" in s or "PE" in s or "FUT" in s:
            return ALICE_NFO
        if s.startswith("BSE:"):
            return ALICE_BSE
        return ALICE_NSE

    @staticmethod
    def _to_alice_side(side: int):
        try:
            return TransactionType.Buy if side == BaseBroker.SIDE_BUY else TransactionType.Sell
        except Exception:
            return side  # Fallback to raw value

    @staticmethod
    def _to_alice_order_type(order_type: str):
        try:
            mapping = {
                BaseBroker.MARKET_ORDER_TYPE:          OrderType.Market,
                BaseBroker.LIMIT_ORDER_TYPE:           OrderType.Limit,
                BaseBroker.STOPLOSS_MARKET_ORDER_TYPE: OrderType.StopLossMarket,
            }
            return mapping.get(order_type, OrderType.Market)
        except Exception:
            return order_type

    @staticmethod
    def _to_alice_product(product_str: str):
        try:
            mapping = {
                "MIS":  ProductType.Intraday,
                "NRML": ProductType.Nrml,
                "CNC":  ProductType.CNC,
            }
            return mapping.get(product_str.upper(), ProductType.Intraday)
        except Exception:
            return product_str

    @staticmethod
    def _is_ok(response: Any) -> bool:
        if isinstance(response, dict):
            stat = str(response.get("stat", "") or "").lower()
            return stat == "ok" or response.get("status") == "success"
        if isinstance(response, list):
            return True
        return False

    def _check_token_error(self, response: Any):
        if isinstance(response, dict):
            msg = str(response.get("emsg", "") or "").lower()
            if "session" in msg or "token" in msg or "login" in msg:
                raise TokenExpiredError(response.get("emsg", "Session expired"))

    # ── BaseBroker implementation ─────────────────────────────────────────────

    def get_profile(self) -> Optional[Dict]:
        try:
            if not self.alice:
                return None
            result = self._call(self.alice.get_profile, context="get_profile")
            if isinstance(result, dict):
                return result
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AliceBlueBroker.get_profile] {e!r}", exc_info=True)
            return None

    def get_balance(self, capital_reserve: float = 0.0) -> float:
        try:
            if not self.alice:
                return 0.0
            result = self._call(self.alice.get_balance, context="get_balance")
            if isinstance(result, dict):
                net = float(result.get("Net", 0.0) or 0.0)
                if capital_reserve > 0:
                    net = net * (1 - capital_reserve / 100)
                return net
            if isinstance(result, list) and result:
                net = float(result[0].get("Net", 0.0) or 0.0)
                if capital_reserve > 0:
                    net = net * (1 - capital_reserve / 100)
                return net
            return 0.0
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AliceBlueBroker.get_balance] {e!r}", exc_info=True)
            return 0.0

    def get_history(self, symbol: str, interval: str = "2", length: int = 400):
        """
        Alice Blue SDK does not provide historical OHLC candles officially.
        Returns None.
        """
        logger.warning("AliceBlueBroker: historical candle data is not available in pya3 SDK.")
        return None

    def get_history_for_timeframe(self, symbol: str, interval: str, days: int = 30):
        logger.warning("AliceBlueBroker: historical candle data is not available in pya3 SDK.")
        return None

    def get_option_current_price(self, option_name: str) -> Optional[float]:
        quote = self.get_option_quote(option_name)
        return quote.get("ltp") if quote else None

    def get_option_quote(self, option_name: str) -> Optional[Dict[str, float]]:
        try:
            if not option_name or not self.alice:
                return None
            exchange = self._exchange_from_symbol(option_name)
            instrument = self._get_instrument(option_name, exchange)
            if not instrument:
                return None
            self._check_rate_limit()
            result = self._call(
                lambda: self.alice.get_market_feed_data(instrument),
                context="get_option_quote"
            )
            if result and isinstance(result, dict):
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
            logger.error(f"[AliceBlueBroker.get_option_quote] {e!r}", exc_info=True)
            return None

    def get_option_chain_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        result = {}
        for sym in symbols:
            quote = self.get_option_quote(sym)
            if quote:
                result[sym.split(":")[-1]] = quote
        return result

    def place_order(self, **kwargs) -> Optional[str]:
        try:
            if not self.alice:
                return None
            symbol = kwargs.get('symbol', '')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_BUY)
            order_type = kwargs.get('order_type', self.MARKET_ORDER_TYPE)
            product_str = kwargs.get('product_type', ALICE_PRODUCT_MIS)
            limit_price = float(kwargs.get('limitPrice', 0) or 0)
            stop_price  = float(kwargs.get('stopPrice', 0) or 0)

            if not symbol or qty <= 0:
                return None

            exchange = self._exchange_from_symbol(symbol)
            instrument = self._get_instrument(symbol, exchange)
            if not instrument:
                logger.error(f"AliceBlue: instrument not found for {symbol}")
                return None

            alice_side = self._to_alice_side(side)
            alice_order = self._to_alice_order_type(order_type)
            alice_product = self._to_alice_product(product_str)

            self._check_rate_limit()
            result = self._call(
                lambda: self.alice.place_order(
                    transaction_type=alice_side,
                    instrument=instrument,
                    quantity=qty,
                    order_type=alice_order,
                    product_type=alice_product,
                    price=limit_price,
                    trigger_price=stop_price if stop_price else None,
                    is_amo=False,
                ),
                context="place_order"
            )
            if result and isinstance(result, dict):
                self._check_token_error(result)
                order_id = result.get("NOrdNo") or result.get("nOrdNo") or result.get("order_id")
                if order_id:
                    logger.info(f"AliceBlue: order placed {order_id}")
                    return str(order_id)
            elif result and isinstance(result, str):
                return result
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AliceBlueBroker.place_order] {e!r}", exc_info=True)
            return None

    def modify_order(self, **kwargs) -> bool:
        try:
            order_id = kwargs.get('order_id')
            limit_price = float(kwargs.get('limit_price', 0) or 0)
            qty = int(kwargs.get('qty', 0))
            if not order_id or not self.alice:
                return False
            symbol = kwargs.get('symbol', '')
            exchange = self._exchange_from_symbol(symbol)
            instrument = self._get_instrument(symbol, exchange)
            if not instrument:
                return False
            self._check_rate_limit()
            result = self._call(
                lambda: self.alice.modify_order(
                    transaction_type=self._to_alice_side(self.SIDE_BUY),
                    instrument=instrument,
                    product_type=self._to_alice_product(ALICE_PRODUCT_MIS),
                    order_id=order_id,
                    order_type=self._to_alice_order_type(self.LIMIT_ORDER_TYPE),
                    quantity=qty,
                    price=limit_price,
                ),
                context="modify_order"
            )
            return self._is_ok(result)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AliceBlueBroker.modify_order] {e!r}", exc_info=True)
            return False

    def cancel_order(self, **kwargs) -> bool:
        try:
            order_id = kwargs.get('order_id')
            if not order_id or not self.alice:
                return False
            symbol = kwargs.get('symbol', '')
            exchange = self._exchange_from_symbol(symbol)
            instrument = self._get_instrument(symbol, exchange)
            self._check_rate_limit()
            result = self._call(
                lambda: self.alice.cancel_order(
                    instrument=instrument,
                    order_id=order_id,
                    product_type=self._to_alice_product(ALICE_PRODUCT_MIS),
                ),
                context="cancel_order"
            )
            return self._is_ok(result)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AliceBlueBroker.cancel_order] {e!r}", exc_info=True)
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
            if not self.alice:
                return []
            result = self._call(self.alice.get_daywise_positions, context="get_positions")
            if isinstance(result, list):
                return result
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AliceBlueBroker.get_positions] {e!r}", exc_info=True)
            return []

    def get_orderbook(self) -> List[Dict[str, Any]]:
        try:
            if not self.alice:
                return []
            result = self._call(self.alice.get_order_history, context="get_orderbook")
            if isinstance(result, list):
                return result
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AliceBlueBroker.get_orderbook] {e!r}", exc_info=True)
            return []

    def get_current_order_status(self, order_id: str) -> Optional[Any]:
        try:
            orders = self.get_orderbook()
            for order in orders:
                oid = order.get("Nstordno") or order.get("nOrdNo") or order.get("order_id")
                if str(oid) == str(order_id):
                    return order
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[AliceBlueBroker.get_current_order_status] {e!r}", exc_info=True)
            return None

    def is_connected(self) -> bool:
        try:
            return self.get_profile() is not None
        except TokenExpiredError:
            return False
        except Exception:
            return False

    def cleanup(self) -> None:
        logger.info("[AliceBlueBroker] cleanup done")

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
                logger.warning(f"[AliceBlue.{context}] Network error, retry {attempt+1}: {e}")
                time.sleep(delay)
            except Exception as e:
                error_str = str(e).lower()
                if "session" in error_str or "token" in error_str or "login" in error_str:
                    raise TokenExpiredError(str(e))
                logger.error(f"[AliceBlue.{context}] {e!r}", exc_info=True)
                return None
        logger.critical(f"[AliceBlue.{context}] Max retries reached.")
        return None

    # ── WebSocket interface ────────────────────────────────────────────────────

    def create_websocket(self, on_tick, on_connect, on_close, on_error) -> Any:
        """
        Create Alice Blue (pya3) WebSocket.

        Alice Blue's pya3 SDK streams ticks via start_websocket().
        Instruments are pya3 Instrument objects (retrieved by exchange + symbol).
        """
        try:
            if not self.alice:
                logger.error("AliceBlueBroker.create_websocket: alice not initialized — login first")
                return None

            self._ws_on_tick    = on_tick
            self._ws_on_connect = on_connect
            self._ws_on_close   = on_close
            self._ws_on_error   = on_error

            logger.info("AliceBlueBroker: WebSocket callbacks stored")
            return {"__alice__": self.alice}
        except Exception as e:
            logger.error(f"[AliceBlueBroker.create_websocket] {e}", exc_info=True)
            return None

    def ws_connect(self, ws_obj) -> None:
        """
        Start Alice Blue WebSocket via start_websocket().

        pya3 start_websocket() is blocking — WebSocketManager wraps in thread.
        """
        try:
            if ws_obj is None:
                return
            alice = ws_obj.get("__alice__") if isinstance(ws_obj, dict) else self.alice
            if alice is None:
                return

            def _on_tick(tick_data):
                self._ws_on_tick(tick_data)

            def _on_open():
                logger.info("AliceBlueBroker: WebSocket opened")
                self._ws_on_connect()

            def _on_close():
                logger.info("AliceBlueBroker: WebSocket closed")
                self._ws_on_close("connection closed")

            def _on_error(ws, error):
                logger.error(f"AliceBlueBroker WS error: {error}")
                self._ws_on_error(str(error))

            alice.start_websocket(
                socket_open_callback=_on_open,
                socket_close_callback=_on_close,
                socket_error_callback=_on_error,
                subscription_callback=_on_tick,
                run_in_background=True,   # non-blocking
            )
            logger.info("AliceBlueBroker: start_websocket() called")
        except Exception as e:
            logger.error(f"[AliceBlueBroker.ws_connect] {e}", exc_info=True)

    def ws_subscribe(self, ws_obj, symbols: List[str]) -> None:
        """
        Subscribe to Alice Blue live feed.

        pya3 subscribe() takes a list of Instrument objects.
        Instruments are resolved via alice.get_instrument_by_symbol().
        """
        try:
            if ws_obj is None or not symbols:
                return
            alice = ws_obj.get("__alice__") if isinstance(ws_obj, dict) else self.alice
            if alice is None:
                return

            instruments = []
            for sym in symbols:
                inst = self._resolve_alice_instrument(alice, sym)
                if inst:
                    instruments.append(inst)

            if not instruments:
                logger.warning("AliceBlueBroker.ws_subscribe: no valid instruments")
                return

            alice.subscribe(instruments)
            logger.info(f"AliceBlueBroker: subscribed {len(instruments)} instruments")
        except Exception as e:
            logger.error(f"[AliceBlueBroker.ws_subscribe] {e}", exc_info=True)

    def ws_unsubscribe(self, ws_obj, symbols: List[str]) -> None:
        """Unsubscribe from Alice Blue live feed."""
        try:
            if ws_obj is None or not symbols:
                return
            alice = ws_obj.get("__alice__") if isinstance(ws_obj, dict) else self.alice
            if alice is None:
                return
            instruments = [self._resolve_alice_instrument(alice, s) for s in symbols]
            instruments = [i for i in instruments if i]
            if instruments:
                alice.unsubscribe(instruments)
        except Exception as e:
            logger.error(f"[AliceBlueBroker.ws_unsubscribe] {e}", exc_info=True)

    def ws_disconnect(self, ws_obj) -> None:
        """Close Alice Blue WebSocket."""
        try:
            if ws_obj is None:
                return
            alice = ws_obj.get("__alice__") if isinstance(ws_obj, dict) else self.alice
            if alice and hasattr(alice, "close_websocket"):
                alice.close_websocket()
            self._ws_on_close("disconnected")
            logger.info("AliceBlueBroker: WebSocket closed")
        except Exception as e:
            logger.error(f"[AliceBlueBroker.ws_disconnect] {e}", exc_info=True)

    def normalize_tick(self, raw_tick) -> Optional[Dict[str, Any]]:
        """
        Normalize an Alice Blue pya3 tick.

        pya3 tick dict fields: symbol, ltp, ltq, ltt, atp,
        volume, best_bid_price, best_ask_price,
        open, high, low, prev_close, oi.
        """
        try:
            if not isinstance(raw_tick, dict):
                return None

            ltp = raw_tick.get("ltp") or raw_tick.get("LTP")
            if ltp is None:
                return None

            raw_symbol = raw_tick.get("symbol", "")
            # pya3 returns instrument object or string symbol
            if hasattr(raw_symbol, "tradingsymbol"):
                symbol_str = f"NSE:{raw_symbol.tradingsymbol}"
            else:
                symbol_str = f"NSE:{raw_symbol}" if ":" not in str(raw_symbol) else str(raw_symbol)

            return {
                "symbol":    symbol_str,
                "ltp":       float(ltp),
                "timestamp": str(raw_tick.get("ltt", "")),
                "bid":       raw_tick.get("best_bid_price"),
                "ask":       raw_tick.get("best_ask_price"),
                "volume":    raw_tick.get("volume"),
                "oi":        raw_tick.get("oi"),
                "open":      raw_tick.get("open"),
                "high":      raw_tick.get("high"),
                "low":       raw_tick.get("low"),
                "close":     raw_tick.get("prev_close"),
            }
        except Exception as e:
            logger.error(f"[AliceBlueBroker.normalize_tick] {e}", exc_info=True)
            return None

    def _resolve_alice_instrument(self, alice, symbol: str):
        """
        Resolve generic NSE:SYMBOL → pya3 Instrument object.
        Caches results for the session.
        """
        try:
            cache = getattr(self, "_alice_inst_cache", {})
            if symbol in cache:
                return cache[symbol]

            upper  = symbol.upper()
            bare   = symbol.split(":")[-1]
            exchange = "NFO" if "NFO:" in upper else "NSE"

            inst = alice.get_instrument_by_symbol(exchange, bare)
            if inst is None and exchange == "NSE":
                inst = alice.get_instrument_by_symbol("NSE", f"{bare}-EQ")

            cache[symbol] = inst
            self._alice_inst_cache = cache
            return inst
        except Exception as e:
            logger.warning(f"AliceBlueBroker._resolve_alice_instrument({symbol}): {e}")
            return None