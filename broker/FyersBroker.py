"""
brokers/FyersBroker.py
======================
Fyers (fyers_apiv3) implementation of BaseBroker.

Drop-in replacement for the original Broker class — all public method
signatures are preserved so existing code continues to work unchanged.
"""

import logging
import random
import time
from datetime import datetime, date, timedelta
from typing import Optional, Any, Callable, List, Dict

import pandas as pd
from dateutil.relativedelta import relativedelta
from requests.exceptions import Timeout, ConnectionError

from broker.BaseBroker import BaseBroker, TokenExpiredError
from gui.BrokerageSetting import BrokerageSetting
from db.connector import get_db
from db.crud import tokens

try:
    from fyers_apiv3 import fyersModel
    FYERS_AVAILABLE = True
except ImportError:
    FYERS_AVAILABLE = False

try:
    import BaseEnums
    from Utils.Utils import Utils
except ImportError:
    BaseEnums = None
    Utils = None

logger = logging.getLogger(__name__)


class FyersBroker(BaseBroker):
    """
    Fyers broker implementation.
    Preserves all original Broker behaviour while conforming to BaseBroker.
    """

    RETRYABLE_CODES = {-429, 500, 502, 503, 504}
    FATAL_CODES = {-8, -15, -16, -17, -100, -101, -102}
    RATE_LIMIT_CODES = {-429, 429}

    def __init__(self, state, broker_setting: BrokerageSetting = None):
        self._safe_defaults_init()
        try:
            if not FYERS_AVAILABLE:
                raise ImportError("fyers_apiv3 is not installed. Run: pip install fyers_apiv3")

            self.state = state

            if broker_setting is None:
                raise ValueError("BrokerageSetting must be provided.")

            self.username = getattr(broker_setting, 'username', None)
            self.client_id = getattr(broker_setting, 'client_id', None)
            self.secret_key = getattr(broker_setting, 'secret_key', None)
            self.redirect_uri = getattr(broker_setting, 'redirect_uri', None)

            try:
                self.state.token = self._load_token_from_db()
                if not self.state.token:
                    logger.warning("Fyers access token is empty or None")
            except Exception as e:
                logger.error(f"Failed to load Fyers token: {e}", exc_info=True)
                self.state.token = None

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

        except Exception as e:
            logger.critical(f"[FyersBroker.__init__] Failed: {e}", exc_info=True)
            raise

    def _safe_defaults_init(self):
        self.state = None
        self.username = None
        self.client_id = None
        self.secret_key = None
        self.redirect_uri = None
        self.fyers = None
        self._last_request_time = 0
        self._request_count = 0
        self._retry_count = 0

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

    # ── Symbol formatting ─────────────────────────────────────────────────────

    @staticmethod
    def _format_symbol(symbol: str) -> Optional[str]:
        if not symbol:
            return None
        return symbol if symbol.startswith("NSE:") else f"NSE:{symbol}"

    @staticmethod
    def _get_error_code(response: Any) -> int:
        if isinstance(response, dict):
            try:
                return int(response.get("code", 0))
            except (ValueError, TypeError):
                return 0
        return 0

    # ── BaseBroker implementation ─────────────────────────────────────────────

    def get_profile(self) -> Optional[Dict]:
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
                        if Utils and BaseEnums:
                            return Utils.percentage_above_or_below(
                                price=account_balance,
                                percentage=capital_reserve,
                                side=BaseEnums.NEGATIVE
                            )
                        return account_balance
            return 0.0
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_balance] {e!r}", exc_info=True)
            return 0.0

    def get_history(self, symbol: str, interval: str = "2", length: int = 400):
        try:
            if not symbol or not self.fyers:
                return None
            today = datetime.today().strftime("%Y-%m-%d")
            from_date = (datetime.today() - relativedelta(
                days=6 if date.today().weekday() == 6 else 4
            )).strftime("%Y-%m-%d")
            formatted_symbol = self._format_symbol(symbol)
            if Utils:
                unit, measurement = Utils.get_interval_unit_and_measurement(interval)
                if unit and unit.lower() == 'm':
                    interval = measurement
            params = {
                "symbol": formatted_symbol, "resolution": interval,
                "date_format": "1", "range_from": from_date,
                "range_to": today, "cont_flag": "1"
            }
            self._check_rate_limit()
            response = self.retry_on_failure(lambda: self.fyers.history(params), context="get_history")
            if response and response.get("s") == self.OK and "candles" in response:
                df = pd.DataFrame(response['candles'], columns=["time", "open", "high", "low", "close", "volume"])
                return df.tail(length)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_history] {e!r}", exc_info=True)
            return None

    def get_history_for_timeframe(self, symbol: str, interval: str, days: int = 30):
        try:
            if not symbol or not self.fyers:
                return None
            today = datetime.today()
            fetch_days = max(days, 60) if interval in ["15", "30", "60"] else (
                max(days, 120) if interval in ["120", "240"] else days
            )
            from_date = (today - timedelta(days=fetch_days)).strftime("%Y-%m-%d")
            formatted_symbol = self._format_symbol(symbol)
            params = {
                "symbol": formatted_symbol, "resolution": interval,
                "date_format": "1", "range_from": from_date,
                "range_to": today.strftime("%Y-%m-%d"), "cont_flag": "1"
            }
            self._check_rate_limit()
            response = self.retry_on_failure(lambda: self.fyers.history(params), context="get_history_for_timeframe")
            if response and response.get("s") == self.OK and "candles" in response:
                df = pd.DataFrame(response['candles'], columns=["time", "open", "high", "low", "close", "volume"])
                df['time'] = pd.to_datetime(df['time'], unit='s')
                return df
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_history_for_timeframe] {e!r}", exc_info=True)
            return None

    def get_option_current_price(self, option_name: str) -> Optional[float]:
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
                    "ltp": v.get("lp"), "bid": v.get("bid_price"), "ask": v.get("ask_price"),
                    "high": v.get("high_price"), "low": v.get("low_price"),
                    "open": v.get("open_price"), "close": v.get("prev_close_price"),
                    "volume": v.get("volume"), "oi": v.get("oi"),
                }
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_option_quote] {e!r}", exc_info=True)
            return None

    def get_option_chain_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
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
                        "ltp": v.get("lp"), "bid": v.get("bid_price"),
                        "ask": v.get("ask_price"), "high": v.get("high_price"),
                        "low": v.get("low_price"), "volume": v.get("volume"), "oi": v.get("oi"),
                    }
            return result
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_option_chain_quotes] {e!r}", exc_info=True)
            return {}

    def place_order(self, **kwargs) -> Optional[str]:
        return self._place_order(**kwargs)

    def modify_order(self, **kwargs) -> bool:
        return self._modify_order_with_id(**kwargs)

    def cancel_order(self, **kwargs) -> bool:
        return self._cancel_order_with_id(**kwargs)

    def exit_position(self, **kwargs) -> bool:
        return self._exit_position_with_symbol(**kwargs)

    def add_stoploss(self, **kwargs) -> bool:
        return self._place_order_with_stoploss(**kwargs)

    def remove_stoploss(self, **kwargs) -> bool:
        return self._cancel_order_with_id(**kwargs)

    def sell_at_current(self, **kwargs) -> bool:
        return self._place_order_with_side(side=self.SIDE_SELL, **kwargs)

    def get_positions(self) -> List[Dict[str, Any]]:
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

    def get_current_order_status(self, order_id: str) -> Optional[Any]:
        try:
            if not order_id or not self.fyers:
                return None
            response = self.retry_on_failure(
                lambda: self.fyers.orderbook({"id": order_id}),
                context="order_status"
            )
            return response.get("orderBook") if response else None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[get_current_order_status] {e!r}", exc_info=True)
            return None

    def is_connected(self) -> bool:
        try:
            if not self.fyers or not self.state or not self.state.token:
                return False
            return self.get_profile() is not None
        except TokenExpiredError:
            return False
        except Exception:
            return False

    def cleanup(self) -> None:
        try:
            if self.fyers and hasattr(self.fyers, 'close'):
                self.fyers.close()
        except Exception as e:
            logger.warning(f"[FyersBroker.cleanup] {e}")

    # ── Internal order helpers (unchanged from original Broker) ───────────────

    def _place_order(self, **kwargs) -> Optional[str]:
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
                "symbol": formatted_symbol, "qty": qty, "type": order_type,
                "side": side, "productType": product_type,
                "limitPrice": limit_price, "stopPrice": stop_price,
                "validity": "DAY", "disclosedQty": 0,
                "filledQty": 0, "offlineOrder": False,
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
        symbol = kwargs.get('symbol')
        price = kwargs.get('price')
        qty = kwargs.get('qty', 75)
        side = kwargs.get('side', self.SIDE_SELL)
        if not symbol or not price or price <= 0:
            return False
        order_id = self.retry_on_failure(
            lambda: self._place_order(symbol=symbol, qty=qty, side=side,
                                      order_type=self.STOPLOSS_MARKET_ORDER_TYPE, stopPrice=price),
            context="place_stoploss"
        )
        return bool(order_id)

    def _place_order_with_side(self, side: int, **kwargs) -> bool:
        symbol = kwargs.get('symbol')
        qty = kwargs.get('qty', 75)
        if not symbol or qty <= 0:
            return False
        order_id = self.retry_on_failure(
            lambda: self._place_order(symbol=symbol, qty=qty, side=side,
                                      order_type=self.MARKET_ORDER_TYPE),
            context="place_order_with_side"
        )
        return bool(order_id)

    def _cancel_order_with_id(self, **kwargs) -> bool:
        order_id = kwargs.get('order_id')
        if not order_id or not self.fyers:
            return False
        response = self.retry_on_failure(
            lambda: self.fyers.cancel_order({"id": order_id}),
            context="cancel_order"
        )
        return bool(response and response.get('s') == self.OK)

    def _modify_order_with_id(self, **kwargs) -> bool:
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

    # ── Retry wrapper (identical to original) ─────────────────────────────────

    def retry_on_failure(self, func: Callable, context: str = "",
                         max_retries: int = 3, base_delay: int = 1):
        for attempt in range(max_retries):
            try:
                self._check_rate_limit()
                response = func()

                if isinstance(response, dict) and response.get('s') == 'ok':
                    return response

                error_code = self._get_error_code(response)

                if error_code in self.FATAL_CODES:
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

    # ── WebSocket interface ────────────────────────────────────────────────────

    def create_websocket(self, on_tick, on_connect, on_close, on_error) -> Any:
        """
        Create Fyers v3 data WebSocket.

        Access token format required by Fyers: "client_id:access_token".
        Symbols use Fyers format: "NSE:NIFTY50-INDEX", "NSE:NIFTY24DECFUT", etc.
        """
        try:
            from fyers_apiv3.FyersWebsocket import data_ws  # type: ignore

            token = getattr(self.state, "token", None) if self.state else None
            if not self.client_id or not token:
                logger.error("FyersBroker.create_websocket: missing client_id or token")
                return None

            access_token = f"{self.client_id}:{token}"

            socket = data_ws.FyersDataSocket(
                access_token=access_token,
                log_path="",
                litemode=False,
                write_to_file=False,
                reconnect=False,
                on_connect=on_connect,
                on_close=on_close,
                on_error=on_error,
                on_message=on_tick,
            )
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
            if ws_obj is None:
                logger.error("FyersBroker.ws_connect: ws_obj is None")
                return
            ws_obj.connect()
            logger.info("FyersBroker: WebSocket connect() called")
        except Exception as e:
            logger.error(f"[FyersBroker.ws_connect] {e}", exc_info=True)

    def ws_subscribe(self, ws_obj, symbols: List[str]) -> None:
        """
        Subscribe to Fyers SymbolUpdate and OnOrders channels.

        Fyers symbols must have exchange prefix: "NSE:NIFTY50-INDEX".
        Plain symbols without prefix are auto-prefixed.
        """
        try:
            if ws_obj is None or not symbols:
                return
            fyers_syms = [s if ":" in s else f"NSE:{s}" for s in symbols]
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
            if ws_obj is None or not symbols:
                return
            fyers_syms = [s if ":" in s else f"NSE:{s}" for s in symbols]
            for data_type in ("SymbolUpdate", "OnOrders"):
                try:
                    ws_obj.unsubscribe(symbols=fyers_syms, data_type=data_type)
                except Exception as e:
                    logger.error(f"FyersBroker.ws_unsubscribe({data_type}): {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[FyersBroker.ws_unsubscribe] {e}", exc_info=True)

    def ws_disconnect(self, ws_obj) -> None:
        """Close Fyers WebSocket."""
        try:
            if ws_obj is None:
                return
            if hasattr(ws_obj, "close_connection"):
                ws_obj.close_connection()
            logger.info("FyersBroker: WebSocket disconnected")
        except Exception as e:
            logger.error(f"[FyersBroker.ws_disconnect] {e}", exc_info=True)

    def normalize_tick(self, raw_tick) -> Optional[Dict[str, Any]]:
        """
        Normalize a Fyers tick to the unified format.

        Fyers SymbolUpdate tick fields:
            symbol, ltp, timestamp, bid_price, ask_price,
            volume, open_price, high_price, low_price, prev_close_price, oi
        """
        try:
            if not isinstance(raw_tick, dict):
                return None
            symbol = raw_tick.get("symbol")
            ltp = raw_tick.get("ltp")
            if symbol is None or ltp is None:
                return None
            return {
                "symbol":    symbol,
                "ltp":       float(ltp),
                "timestamp": str(raw_tick.get("timestamp", "")),
                "bid":       raw_tick.get("bid_price"),
                "ask":       raw_tick.get("ask_price"),
                "volume":    raw_tick.get("volume"),
                "oi":        raw_tick.get("oi"),
                "open":      raw_tick.get("open_price"),
                "high":      raw_tick.get("high_price"),
                "low":       raw_tick.get("low_price"),
                "close":     raw_tick.get("prev_close_price"),
            }
        except Exception as e:
            logger.error(f"[FyersBroker.normalize_tick] {e}", exc_info=True)
            return None