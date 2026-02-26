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
    """

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

            self.client_id = getattr(broker_setting, 'client_id', None)
            # For Dhan the "secret_key" field carries the access token
            access_token = getattr(broker_setting, 'secret_key', None)

            # Also check the DB for a fresher token (in case it was updated)
            db_token = self._load_token_from_db()
            if db_token:
                access_token = db_token

            if not self.client_id or not access_token:
                raise ValueError("Dhan client_id and access_token (secret_key) are required.")

            self.dhan = dhanhq(self.client_id, access_token)
            self.state.token = access_token

            logger.info(f"DhanBroker initialized for client {self.client_id}")

        except Exception as e:
            logger.critical(f"[DhanBroker.__init__] {e}", exc_info=True)
            raise

    def _safe_defaults_init(self):
        self.state = None
        self.client_id = None
        self.dhan = None
        self._last_request_time = 0
        self._request_count = 0
        # Dhan instrument cache: "NSE:SYMBOL" -> security_id
        self._instrument_cache: Dict[str, str] = {}

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
        current_time = time.time()
        time_diff = current_time - self._last_request_time
        if time_diff < 1.0:
            self._request_count += 1
            if self._request_count > self.MAX_REQUESTS_PER_SECOND:
                time.sleep(1.0 - time_diff + 0.1)
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
        if not hasattr(DhanBroker, '_instruments_df') or DhanBroker._instruments_df is None:
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
        try:
            if not self.dhan:
                return 0.0
            result = self._call(self.dhan.get_fund_limits, context="get_balance")
            if self._is_ok(result):
                data = result.get("data", {})
                available = float(data.get("availabelBalance", 0.0))
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
        try:
            if not symbol or not self.dhan:
                return None
            security_id = self._get_security_id(symbol)
            if not security_id:
                return None
            exchange_seg = self._exchange_segment(symbol)
            dhan_interval = self._to_dhan_interval(interval)
            to_date = datetime.now().strftime("%Y-%m-%d")
            from_date = (datetime.now() - timedelta(days=4)).strftime("%Y-%m-%d")
            self._check_rate_limit()
            result = self._call(
                lambda: self.dhan.intraday_minute_data(
                    security_id=security_id,
                    exchange_segment=exchange_seg,
                    instrument_type="OPTIDX" if "FNO" in exchange_seg else "EQUITY",
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
            to_date = datetime.now().strftime("%Y-%m-%d")
            from_date = (datetime.now() - timedelta(days=fetch_days)).strftime("%Y-%m-%d")
            self._check_rate_limit()
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

    def get_current_order_status(self, order_id: str) -> Optional[Any]:
        try:
            if not order_id or not self.dhan:
                return None
            result = self._call(
                lambda: self.dhan.get_order_by_id(order_id=order_id),
                context="order_status"
            )
            return result.get("data") if self._is_ok(result) else None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[DhanBroker.get_current_order_status] {e!r}", exc_info=True)
            return None

    def is_connected(self) -> bool:
        try:
            return self.get_profile() is not None
        except TokenExpiredError:
            return False
        except Exception:
            return False

    def cleanup(self) -> None:
        logger.info("[DhanBroker] cleanup done")

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
        """
        try:
            from dhanhq import marketfeed  # type: ignore

            client_id    = getattr(self, 'client_id', None) or \
                           getattr(self, 'dhan_client_id', None)
            access_token = getattr(self.state, "token", None) if self.state else None
            if not client_id or not access_token:
                logger.error("DhanBroker.create_websocket: missing client_id or token")
                return None

            # Store callbacks for use in ws_connect (DhanFeed uses them at init)
            self._ws_on_tick    = on_tick
            self._ws_on_connect = on_connect
            self._ws_on_close   = on_close
            self._ws_on_error   = on_error
            self._ws_client_id  = client_id
            self._ws_token      = access_token
            # Return a sentinel; actual DhanFeed is created in ws_connect
            # because DhanFeed requires instruments list at construction time.
            logger.info("DhanBroker: WebSocket callbacks stored (DhanFeed created at subscribe)")
            return {"__dhan_pending__": True}
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

        symbol format → Dhan security_id resolution:
          - Uses _resolve_dhan_security() which looks up the Dhan instrument file.
          - Falls back to stripping NSE: prefix and using as security_id directly
            (works for index symbols like NIFTY 50 → security_id "13").
        """
        try:
            from dhanhq import marketfeed  # type: ignore

            if ws_obj is None or not symbols:
                return

            instruments = []
            for sym in symbols:
                seg, sec_id = self._resolve_dhan_security(sym)
                if seg and sec_id:
                    instruments.append((seg, sec_id, marketfeed.Quote))

            if not instruments:
                logger.warning("DhanBroker.ws_subscribe: no valid instruments")
                return

            feed = marketfeed.DhanFeed(
                client_id=self._ws_client_id,
                access_token=self._ws_token,
                instruments=instruments,
                subscription_code=marketfeed.Quote,
                on_message=self._ws_on_tick,
            )
            # Store feed object back into the sentinel dict so disconnect works
            ws_obj["__feed__"] = feed
            feed.run_forever()
            logger.info(f"DhanBroker: DhanFeed started with {len(instruments)} instruments")
        except Exception as e:
            logger.error(f"[DhanBroker.ws_subscribe] {e}", exc_info=True)

    def ws_unsubscribe(self, ws_obj, symbols: List[str]) -> None:
        """Dhan does not support partial unsubscribe; close and reconnect if needed."""
        logger.warning("DhanBroker: partial unsubscribe not supported — use ws_disconnect and reconnect")

    def ws_disconnect(self, ws_obj) -> None:
        """Stop Dhan live feed."""
        try:
            if ws_obj is None:
                return
            feed = ws_obj.get("__feed__") if isinstance(ws_obj, dict) else None
            if feed and hasattr(feed, "disconnect"):
                feed.disconnect()
            logger.info("DhanBroker: DhanFeed disconnected")
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
            if not isinstance(raw_tick, dict):
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
            cache = getattr(self, "_dhan_sec_cache", {})
            if symbol in cache:
                return cache[symbol]

            # Strip exchange prefix and use bare symbol as security_id
            bare = symbol.split(":")[-1]
            seg  = marketfeed.NSE if "NSE" in symbol.upper() else marketfeed.NSE
            result = (seg, bare)
            cache[symbol] = result
            self._dhan_sec_cache = cache
            return result
        except Exception:
            return (None, None)