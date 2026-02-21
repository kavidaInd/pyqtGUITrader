import logging
import os
import random
import time
import json
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from typing import Optional, Dict, Any, Union, Callable

from fyers_apiv3 import fyersModel

import BaseEnums
from Utils.Utils import Utils
from gui.BrokerageSetting import BrokerageSetting

logger = logging.getLogger(__name__)

CONFIG_PATH = os.getenv("CONFIG_PATH", "Config")


# FIX: Define custom exception for token expiration
class TokenExpiredError(RuntimeError):
    """Exception raised when Fyers token has expired or is invalid."""
    pass


class Broker:
    OK = 'ok'
    SIDE_BUY = 1
    SIDE_SELL = -1
    LIMIT_ORDER_TYPE = 1
    MARKET_ORDER_TYPE = 2
    STOPLOSS_MARKET_ORDER_TYPE = 3
    PRODUCT_TYPE_MARGIN = 'MARGIN'

    # FIX: Define error code sets
    RETRYABLE_CODES = {-429, 500}  # Rate limit, internal server error
    FATAL_CODES = {-8, -15, -16, -17}  # Token expired/invalid

    def __init__(self, state, broker_setting: BrokerageSetting = None):
        self.state = state
        if broker_setting is None:
            raise ValueError("BrokerageSetting must be provided.")
        self.username = getattr(broker_setting, 'username', None)
        self.client_id = getattr(broker_setting, 'client_id', None)
        self.secret_key = getattr(broker_setting, 'secret_key', None)
        self.redirect_uri = getattr(broker_setting, 'redirect_uri', None)

        self.state.token = Utils.load_access_token()
        try:
            self.fyers = fyersModel.FyersModel(client_id=self.client_id, token=self.state.token, log_path='logs')
        except Exception as e:
            logger.critical(f"Failed initializing FyersModel: {e!r}", exc_info=True)
            raise

    @staticmethod
    def read_file():
        try:
            with open(os.path.join(CONFIG_PATH, "fyers_token.json"), "r") as f:
                try:
                    return json.load(f)
                except Exception:
                    f.seek(0)
                    return f.read().strip()
        except FileNotFoundError:
            logger.error("fyers_token.json not found.")
            return None
        except Exception as e:
            logger.error(f"Error reading fyers_token.json: {e!r}", exc_info=True)
            return None

    @staticmethod
    def _format_symbol(symbol: str) -> str:
        return symbol if symbol.startswith("NSE:") else f"NSE:{symbol}"

    # FIX: Helper to extract error code from response
    @staticmethod
    def _get_error_code(response: Any) -> int:
        """Extract error code from Fyers response."""
        if isinstance(response, dict):
            return int(response.get("code", 0))
        return 0

    def get_profile(self):
        try:
            return self.retry_on_failure(lambda: self.fyers.get_profile(), context="get_profile")
        except Exception as e:
            logger.error(f"Failed to get profile: {e!r}", exc_info=True)
            return None

    def _place_order_with_stoploss(self, **kwargs) -> bool:
        try:
            symbol = kwargs.get('symbol')
            price = kwargs.get('price')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_SELL)
            if not symbol:
                logger.error("Symbol is required to place an order.")
                return False
            if price is None or price <= 0:
                logger.error(f"Invalid stop price: {price}. Price must be greater than 0.")
                return False
            if qty <= 0:
                logger.error(f"Invalid quantity: {qty}. Quantity must be greater than 0.")
                return False
            add_stop = self.retry_on_failure(
                lambda: self._place_order(
                    symbol=symbol,
                    qty=qty,
                    side=side,
                    order_type=self.STOPLOSS_MARKET_ORDER_TYPE,
                    stopPrice=price
                ),
                context="place_stoploss"
            )
            if add_stop:
                logger.info(f"Stop-loss order placed successfully for {symbol} with stop price {price}.")
                return True
            else:
                logger.error(f"Failed to place stop-loss order for {symbol} with stop price {price}.")
                return False
        except Exception as e:
            logger.error(f'Error in adding stop-loss order: {e}', exc_info=True)
            return False

    def add_stoploss(self, **kwargs) -> bool:
        return self._place_order_with_stoploss(**kwargs)

    def sell_at_current(self, **kwargs) -> bool:
        return self._place_order_with_side(**kwargs, side=self.SIDE_SELL)

    def remove_stoploss(self, **kwargs) -> bool:
        return self._cancel_order_with_id(**kwargs)

    def cancel_order(self, **kwargs) -> bool:
        return self._cancel_order_with_id(**kwargs)

    def place_order(self, **kwargs):
        return self._place_order(**kwargs)

    def modify_order(self, **kwargs) -> bool:
        return self._modify_order_with_id(**kwargs)

    def exit_position(self, **kwargs) -> bool:
        return self._exit_position_with_symbol(**kwargs)

    def _place_order_with_side(self, side: int, **kwargs) -> bool:
        try:
            symbol = kwargs.get('symbol')
            qty = kwargs.get('qty', 75)
            if not symbol:
                logger.error("Symbol is required to place an order.")
                return False
            if qty <= 0:
                logger.error(f"Invalid quantity: {qty}. Quantity must be greater than 0.")
                return False
            order_id = self.retry_on_failure(
                lambda: self._place_order(
                    symbol=symbol,
                    qty=qty,
                    side=side,
                    order_type=self.MARKET_ORDER_TYPE
                ),
                context="place_order_with_side"
            )
            if order_id:
                logger.info(f"Order placed successfully: {order_id}")
                return True
            else:
                logger.error(f"Failed to place order for {symbol} with side {side}.")
                return False
        except Exception as e:
            logger.error(f"Error in placing order with side {side}: {e}", exc_info=True)
            return False

    def _cancel_order_with_id(self, **kwargs) -> bool:
        try:
            order_id = kwargs.get('order_id')
            if not order_id:
                logger.error("Order ID is required to cancel an order.")
                return False
            cancel_order = self.retry_on_failure(
                lambda: self.fyers.cancel_order({"id": order_id}),
                context="cancel_order"
            )
            logger.info(f"Cancel order response: {cancel_order}")
            if cancel_order and cancel_order.get('s') == self.OK:
                logger.info(f"Order {order_id} canceled successfully.")
                return True
            else:
                error_code = cancel_order.get('code', 'Unknown') if cancel_order else 'Unknown'
                logger.error(f"Failed to cancel order {order_id}. Error Code: {error_code}, Response: {cancel_order}")
                return False
        except Exception as e:
            logger.error(f"Error in canceling order: {e}", exc_info=True)
            return False

    def _place_order(self, **kwargs):
        try:
            symbol = kwargs.get('symbol')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_BUY)
            order_type = kwargs.get('order_type', self.LIMIT_ORDER_TYPE)
            product_type = kwargs.get('product_type', self.PRODUCT_TYPE_MARGIN)
            limit_price = kwargs.get('limitPrice', 0)
            stop_price = kwargs.get('stopPrice', 0)
            if not symbol:
                logger.error("Symbol is required to place an order.")
                return None
            if qty <= 0:
                logger.error(f"Invalid quantity: {qty}. Quantity must be greater than 0.")
                return None
            if limit_price < 0 or stop_price < 0:
                logger.error(
                    f"Invalid price values: limitPrice={limit_price}, stopPrice={stop_price}. Prices must be "
                    f"non-negative.")
                return None

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
            logger.info(f"Order response: {response}")
            if response and response.get('s') == self.OK:
                last_order_no = response.get('id')
                logger.info(f"Order placed successfully. Order ID: {last_order_no}")
                return last_order_no
            else:
                error_code = response.get('code', 'Unknown') if response else 'Unknown'
                logger.error(f"Failed to place order. Error Code: {error_code}, Response: {response}")
                return None
        except Exception as e:
            logger.error(f"Error in placing order: {e}", exc_info=True)
            return None

    def _modify_order_with_id(self, **kwargs) -> bool:
        try:
            order_id = kwargs.get('order_id')
            limit_price = kwargs.get('limit_price', 0)
            if not order_id:
                logger.error("Order ID is required to modify an order.")
                return False
            if limit_price <= 0:
                logger.error(f"Invalid limit price: {limit_price}. It must be greater than 0.")
                return False
            data = {
                "id": order_id,
                "limitPrice": limit_price,
            }
            modify = self.retry_on_failure(lambda: self.fyers.modify_order(data), context="modify_order")
            if modify and modify.get('s') == self.OK:
                logger.info(f"Order with ID {order_id} modified successfully to limit price {limit_price}.")
                return True
            else:
                logger.error(f"Failed to modify order with ID {order_id}. Response: {modify}")
                return False
        except Exception as e:
            logger.error(f"Error in modifying order with ID {kwargs.get('order_id', 'N/A')}: {e}", exc_info=True)
            return False

    def _exit_position_with_symbol(self, **kwargs) -> bool:
        try:
            symbol = kwargs.get('symbol')
            position_type = kwargs.get('position_type', self.PRODUCT_TYPE_MARGIN)
            if not symbol:
                logger.error("Symbol is required to exit a position.")
                return False
            formatted_symbol = self._format_symbol(symbol)
            data = {
                "id": f"{formatted_symbol}-{position_type}"
            }
            order_exit = self.retry_on_failure(lambda: self.fyers.exit_positions(data), context="exit_position")
            if order_exit and order_exit.get('s') == self.OK:
                logger.info(f"Successfully exited position for symbol: {symbol}")
                return True
            else:
                logger.error(f"Failed to exit position for symbol: {symbol}. Response: {order_exit}")
                return False
        except Exception as e:
            logger.error(f"Error in exiting position for symbol: {kwargs.get('symbol', 'N/A')}: {e}", exc_info=True)
            return False

    def get_current_order_status(self, order_id):
        try:
            response = self.retry_on_failure(lambda: self.fyers.orderbook({"id": order_id}), context="order_status")
            return response.get("orderBook") if response else None
        except Exception as e:
            logger.error(f"Exception in get_current_order_status: {e!r}", exc_info=True)
            return None

    def get_option_current_price(self, option_name):
        data = {"symbols": self._format_symbol(option_name)}
        try:
            response = self.retry_on_failure(lambda: self.fyers.quotes(data), context="option_current_price")
            if response and response.get("s") == self.OK and response.get("d"):
                v = response["d"][0]["v"]
                price = v.get("lp")
                if price is None:
                    logger.warning(f"LTP not found in response for {option_name}: {v}")
                return price
            else:
                logger.warning(f"Failed to fetch price for {option_name}: {response}")
                return None
        except Exception as e:
            logger.error(f"Exception in get_option_current_price: {e!r}", exc_info=True)
            return None

    def get_balance(self, capital_reserve: float = 0.0):
        try:
            funds = self.retry_on_failure(lambda: self.fyers.funds(), context="get_balance")
            if funds and funds.get("s") == self.OK:
                bal_data = pd.json_normalize(funds["fund_limit"])
                if not bal_data.empty and "id" in bal_data.columns and "equityAmount" in bal_data.columns:
                    account_balance = bal_data.query("id == 10")["equityAmount"].iloc[0]
                    adjusted_balance = Utils.percentage_above_or_below(
                        price=account_balance,
                        percentage=capital_reserve,
                        side=BaseEnums.NEGATIVE
                    )
                    return adjusted_balance
                else:
                    logger.warning("Balance data missing required fields.")
            else:
                logger.warning(f"Failed to retrieve funds: {funds}")
            return 0.0
        except Exception as e:
            logger.error(f"Exception in get_balance: {e!r}", exc_info=True)
            return 0.0

    def get_history(self, symbol: str, interval: str = "2", length: int = 100):
        today = datetime.today().strftime("%Y-%m-%d")
        from_date = (datetime.today() - relativedelta(days=3 if date.today().weekday() == 6 else 2)).strftime(
            "%Y-%m-%d")
        formatted_symbol = self._format_symbol(symbol)
        unit, measurement = Utils.get_interval_unit_and_measurement(interval)
        if unit.lower() == 'm':
            interval = measurement

        params = {
            "symbol": formatted_symbol,
            "resolution": interval,
            "date_format": "1",
            "range_from": from_date,
            "range_to": today,
            "cont_flag": "1"
        }
        try:
            response = self.retry_on_failure(lambda: self.fyers.history(params), context="get_history")
            if response and response.get("s") == self.OK and "candles" in response:
                df = pd.DataFrame(response['candles'], columns=["Time", "open", "high", "low", "close", "volume"])
                return df.tail(length)
            else:
                logger.warning(f"Failed to get history for {symbol}: {response}")
                return None
        except Exception as e:
            logger.error(f"Exception in get_history: {e!r}", exc_info=True)
            return None

    @staticmethod
    def calculate_pnl(current_price, buy_price=None, options=None):
        try:
            if buy_price is None or options is None:
                logger.warning("Cannot calculate PnL: buy_price or options is None.")
                return None
            pnl = int((current_price - buy_price) * options)
            logger.info(f"PnL calculated: {pnl}")
            return pnl
        except Exception as e:
            logger.error(f"Exception in calculate_pnl: {e!r}", exc_info=True)
            return None

    def retry_on_failure(self, func: Callable, context: str = "", max_retries: int = 3, base_delay: int = 1):
        """
        Retry wrapper for Fyers API calls. Accepts a callable (use lambda).
        Handles all types of errors: network, HTTP, Fyers API, token, and unknown.
        """
        import requests

        for attempt in range(max_retries):
            try:
                response = func()

                # Fyers 'ok' status - success
                if isinstance(response, dict) and response.get('s') == 'ok':
                    return response

                # Extract error code from response
                error_code = self._get_error_code(response)

                # FIX: Check fatal token errors
                if error_code in self.FATAL_CODES:
                    error_desc = {
                        -8: "Token expired or invalid",
                        -15: "Token expired",
                        -16: "Invalid Access Token",
                        -17: "Access Token missing"
                    }.get(error_code, f"Token error (code {error_code})")
                    logger.critical(f"[{context}] 🔐 {error_desc}")
                    raise TokenExpiredError(f"{error_desc}")

                # FIX: Check retryable errors
                if error_code in self.RETRYABLE_CODES:
                    delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                    error_type = "Rate limited" if error_code == -429 else "Internal Server Error"
                    logger.warning(f"[{context}] 🔁 {error_type}. Retrying after {delay:.2f}s...")
                    time.sleep(delay)
                    continue

                # Check for token errors in string response (fallback)
                if isinstance(response, str):
                    response_str = response
                else:
                    response_str = str(response)

                # Token expired or authentication errors in string
                for token_err in ["-8", "-15", "-16", "-17", "Token expired", "Invalid Access Token",
                                  "Access Token missing"]:
                    if token_err in response_str:
                        logger.critical(f"[{context}] 🔐 Token/authentication error: {token_err}")
                        raise TokenExpiredError(f"Token expired or invalid: {token_err}")

                # Market closed
                if "Market is in closed state" in response_str:
                    logger.warning(f"[{context}] ⏳ Market is closed. Skipping action.")
                    return None

                # No data or invalid symbol
                if "No data found" in response_str or "Invalid symbol" in response_str:
                    logger.warning(f"[{context}] ⚠️ Symbol issue or no data.")
                    return None

                # Invalid order
                if "Invalid order" in response_str:
                    logger.warning(f"[{context}] ⛔ Invalid order. Skipping.")
                    return None

                # Any other error response, log and return
                if isinstance(response, dict) and response.get('s', '') != 'ok':
                    logger.error(f"[{context}] ❌ Fyers API Error: {response}")
                    return response

                # Non-dict or unexpected valid response, just return
                return response

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning(f"[{context}] 🌐 Network error: {e!r}. Retrying after {delay:.2f}s...")
                time.sleep(delay)

            except TokenExpiredError:
                # Re-raise token errors immediately
                raise

            except Exception as e:
                # Check for token errors in exception string
                error_str = str(e)
                for code in self.FATAL_CODES:
                    if str(code) in error_str:
                        logger.critical(f"[{context}] 🔐 Token error in exception: {e}")
                        raise TokenExpiredError(f"Token expired or invalid (code {code})")

                # Check for rate limit in exception
                for code in self.RETRYABLE_CODES:
                    if str(code) in error_str:
                        delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                        logger.warning(
                            f"[{context}] 🔁 Rate limit/Server error in exception. Retrying after {delay:.2f}s...")
                        time.sleep(delay)
                        break
                else:
                    # Unknown exception, log and return None
                    logger.error(f"[{context}] ❌ Unexpected exception: {e!r}", exc_info=True)
                    return None

        logger.critical(f"[{context}] ❌ Max retries reached. Giving up.")
        return None
