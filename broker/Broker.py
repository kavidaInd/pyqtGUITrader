import logging
import logging.handlers
import os
import random
import time
import json
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from typing import Optional, Dict, Any, Union, Callable, List
import requests
from requests.exceptions import Timeout, ConnectionError

from fyers_apiv3 import fyersModel

import BaseEnums
from Utils.Utils import Utils
from gui.BrokerageSetting import BrokerageSetting

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

CONFIG_PATH = os.getenv("CONFIG_PATH", "Config")


# FIX: Define custom exception for token expiration
class TokenExpiredError(RuntimeError):
    """Exception raised when Fyers token has expired or is invalid."""

    def __init__(self, message: str = "Token expired or invalid", code: Optional[int] = None):
        try:
            # Rule 6: Input validation
            if code is not None:
                message = f"{message} (code: {code})"
            super().__init__(message)
            self.code = code
            logger.debug(f"TokenExpiredError created: {message}")
        except Exception as e:
            logger.error(f"[TokenExpiredError.__init__] Failed: {e}", exc_info=True)
            super().__init__(message)


class Broker:
    OK = 'ok'
    SIDE_BUY = 1
    SIDE_SELL = -1
    LIMIT_ORDER_TYPE = 1
    MARKET_ORDER_TYPE = 2
    STOPLOSS_MARKET_ORDER_TYPE = 3
    PRODUCT_TYPE_MARGIN = 'MARGIN'

    # FIX: Define error code sets
    RETRYABLE_CODES = {-429, 500, 502, 503, 504}  # Rate limit, server errors
    FATAL_CODES = {-8, -15, -16, -17, -100, -101, -102}  # Token expired/invalid, auth errors
    RATE_LIMIT_CODES = {-429, 429}  # Rate limiting

    def __init__(self, state, broker_setting: BrokerageSetting = None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            self.state = state

            # Rule 6: Input validation
            if broker_setting is None:
                error_msg = "BrokerageSetting must be provided."
                logger.critical(error_msg)
                raise ValueError(error_msg)

            self.username = getattr(broker_setting, 'username', None)
            self.client_id = getattr(broker_setting, 'client_id', None)
            self.secret_key = getattr(broker_setting, 'secret_key', None)
            self.redirect_uri = getattr(broker_setting, 'redirect_uri', None)

            # Validate required credentials
            if not self.client_id:
                logger.warning("client_id is missing in broker settings")

            # Load token
            try:
                self.state.token = Utils.load_access_token()
                if not self.state.token:
                    logger.warning("Access token is empty or None")
            except Exception as e:
                logger.error(f"Failed to load access token: {e}", exc_info=True)
                self.state.token = None

            # Initialize FyersModel
            try:
                self.fyers = fyersModel.FyersModel(
                    client_id=self.client_id,
                    token=self.state.token,
                    log_path='logs'
                )
                logger.info("FyersModel initialized successfully")
            except Exception as e:
                logger.critical(f"Failed initializing FyersModel: {e!r}", exc_info=True)
                self.fyers = None
                # Don't raise here - allow app to continue with limited functionality

        except Exception as e:
            logger.critical(f"[Broker.__init__] Failed: {e}", exc_info=True)
            # Re-raise as this is a critical component
            raise

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.state = None
        self.username = None
        self.client_id = None
        self.secret_key = None
        self.redirect_uri = None
        self.fyers = None
        self._last_request_time = 0
        self._request_count = 0
        self.MAX_REQUESTS_PER_SECOND = 10
        self._retry_count = 0
        self.MAX_RETRIES = 3

    @staticmethod
    def read_file():
        """Read token file with comprehensive error handling"""
        try:
            file_path = os.path.join(CONFIG_PATH, "fyers_token.json")

            # Rule 6: Check if file exists
            if not os.path.exists(file_path):
                logger.error(f"fyers_token.json not found at {file_path}")
                return None

            # Read file with proper encoding
            with open(file_path, "r", encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    logger.debug("Token file parsed as JSON")
                    return data
                except json.JSONDecodeError:
                    # If JSON parsing fails, try reading as plain text
                    logger.warning("Token file is not valid JSON, reading as text")
                    f.seek(0)
                    return f.read().strip()

        except PermissionError as e:
            logger.error(f"Permission denied reading token file: {e}")
            return None
        except FileNotFoundError as e:
            logger.error(f"Token file not found: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading fyers_token.json: {e!r}", exc_info=True)
            return None

    @staticmethod
    def _format_symbol(symbol: str) -> Optional[str]:
        """Format symbol with NSE prefix if needed"""
        try:
            if not symbol:
                logger.warning("_format_symbol called with None or empty symbol")
                return None

            return symbol if symbol.startswith("NSE:") else f"NSE:{symbol}"

        except Exception as e:
            logger.error(f"[_format_symbol] Failed for {symbol}: {e}", exc_info=True)
            return symbol  # Return original on error

    # FIX: Helper to extract error code from response
    @staticmethod
    def _get_error_code(response: Any) -> int:
        """Extract error code from Fyers response."""
        try:
            if response is None:
                return 0

            if isinstance(response, dict):
                code = response.get("code", 0)
                try:
                    return int(code)
                except (ValueError, TypeError):
                    logger.warning(f"Non-integer error code: {code}")
                    return 0

            return 0

        except Exception as e:
            logger.error(f"[_get_error_code] Failed: {e}", exc_info=True)
            return 0

    def _check_rate_limit(self):
        """Implement rate limiting to avoid hitting API limits"""
        try:
            current_time = time.time()
            time_diff = current_time - self._last_request_time

            if time_diff < 1.0:  # Within same second
                self._request_count += 1
                if self._request_count > self.MAX_REQUESTS_PER_SECOND:
                    sleep_time = 1.0 - time_diff + 0.1
                    logger.warning(f"Rate limit reached, sleeping {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    self._request_count = 0
                    self._last_request_time = time.time()
            else:
                self._request_count = 1
                self._last_request_time = current_time

        except Exception as e:
            logger.error(f"[_check_rate_limit] Failed: {e}", exc_info=True)

    def get_profile(self):
        """Get user profile with error handling"""
        try:
            if not self.fyers:
                logger.error("Cannot get profile: FyersModel not initialized")
                return None

            return self.retry_on_failure(
                lambda: self.fyers.get_profile(),
                context="get_profile"
            )

        except TokenExpiredError:
            raise  # Re-raise token errors
        except Exception as e:
            logger.error(f"Failed to get profile: {e!r}", exc_info=True)
            return None

    def _place_order_with_stoploss(self, **kwargs) -> bool:
        """Place an order with stoploss"""
        try:
            # Rule 6: Extract and validate parameters
            symbol = kwargs.get('symbol')
            price = kwargs.get('price')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_SELL)

            # Validation
            if not symbol:
                logger.error("Symbol is required to place an order.")
                return False

            if price is None or price <= 0:
                logger.error(f"Invalid stop price: {price}. Price must be greater than 0.")
                return False

            if qty <= 0:
                logger.error(f"Invalid quantity: {qty}. Quantity must be greater than 0.")
                return False

            # Place stoploss order
            order_id = self.retry_on_failure(
                lambda: self._place_order(
                    symbol=symbol,
                    qty=qty,
                    side=side,
                    order_type=self.STOPLOSS_MARKET_ORDER_TYPE,
                    stopPrice=price
                ),
                context="place_stoploss"
            )

            if order_id:
                logger.info(f"Stop-loss order placed successfully for {symbol} with stop price {price}.")
                return True
            else:
                logger.error(f"Failed to place stop-loss order for {symbol} with stop price {price}.")
                return False

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f'Error in adding stop-loss order: {e}', exc_info=True)
            return False

    def add_stoploss(self, **kwargs) -> bool:
        """Add stoploss to an existing position"""
        try:
            return self._place_order_with_stoploss(**kwargs)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[add_stoploss] Failed: {e}", exc_info=True)
            return False

    def sell_at_current(self, **kwargs) -> bool:
        """Sell at current market price"""
        try:
            return self._place_order_with_side(**kwargs, side=self.SIDE_SELL)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[sell_at_current] Failed: {e}", exc_info=True)
            return False

    def remove_stoploss(self, **kwargs) -> bool:
        """Remove stoploss order"""
        try:
            return self._cancel_order_with_id(**kwargs)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[remove_stoploss] Failed: {e}", exc_info=True)
            return False

    def cancel_order(self, **kwargs) -> bool:
        """Cancel an order"""
        try:
            return self._cancel_order_with_id(**kwargs)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[cancel_order] Failed: {e}", exc_info=True)
            return False

    def place_order(self, **kwargs):
        """Place an order"""
        try:
            return self._place_order(**kwargs)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[place_order] Failed: {e}", exc_info=True)
            return None

    def modify_order(self, **kwargs) -> bool:
        """Modify an existing order"""
        try:
            return self._modify_order_with_id(**kwargs)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[modify_order] Failed: {e}", exc_info=True)
            return False

    def exit_position(self, **kwargs) -> bool:
        """Exit a position"""
        try:
            return self._exit_position_with_symbol(**kwargs)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[exit_position] Failed: {e}", exc_info=True)
            return False

    def _place_order_with_side(self, side: int, **kwargs) -> bool:
        """Place an order with specified side"""
        try:
            # Rule 6: Parameter validation
            if side not in [self.SIDE_BUY, self.SIDE_SELL]:
                logger.error(f"Invalid side: {side}")
                return False

            symbol = kwargs.get('symbol')
            qty = kwargs.get('qty', 75)

            if not symbol:
                logger.error("Symbol is required to place an order.")
                return False

            if qty <= 0:
                logger.error(f"Invalid quantity: {qty}. Quantity must be greater than 0.")
                return False

            # Place order
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

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error in placing order with side {side}: {e}", exc_info=True)
            return False

    def _cancel_order_with_id(self, **kwargs) -> bool:
        """Cancel order by ID"""
        try:
            order_id = kwargs.get('order_id')

            if not order_id:
                logger.error("Order ID is required to cancel an order.")
                return False

            # Cancel order
            cancel_response = self.retry_on_failure(
                lambda: self.fyers.cancel_order({"id": order_id}) if self.fyers else None,
                context="cancel_order"
            )

            logger.info(f"Cancel order response: {cancel_response}")

            if cancel_response and cancel_response.get('s') == self.OK:
                logger.info(f"Order {order_id} canceled successfully.")
                return True
            else:
                error_code = cancel_response.get('code', 'Unknown') if cancel_response else 'Unknown'
                logger.error(
                    f"Failed to cancel order {order_id}. Error Code: {error_code}, Response: {cancel_response}")
                return False

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error in canceling order: {e}", exc_info=True)
            return False

    def _place_order(self, **kwargs):
        """Place order with Fyers"""
        try:
            # Extract and validate parameters
            symbol = kwargs.get('symbol')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_BUY)
            order_type = kwargs.get('order_type', self.LIMIT_ORDER_TYPE)
            product_type = kwargs.get('product_type', self.PRODUCT_TYPE_MARGIN)
            limit_price = kwargs.get('limitPrice', 0)
            stop_price = kwargs.get('stopPrice', 0)

            # Validation
            if not symbol:
                logger.error("Symbol is required to place an order.")
                return None

            if qty <= 0:
                logger.error(f"Invalid quantity: {qty}. Quantity must be greater than 0.")
                return None

            if limit_price < 0 or stop_price < 0:
                logger.error(
                    f"Invalid price values: limitPrice={limit_price}, stopPrice={stop_price}. "
                    f"Prices must be non-negative."
                )
                return None

            # Check if fyers is initialized
            if not self.fyers:
                logger.error("Cannot place order: FyersModel not initialized")
                return None

            # Apply rate limiting
            self._check_rate_limit()

            # Format symbol
            formatted_symbol = self._format_symbol(symbol)
            if not formatted_symbol:
                logger.error(f"Failed to format symbol: {symbol}")
                return None

            # Prepare order data
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

            # Place order with retry
            response = self.retry_on_failure(
                lambda: self.fyers.place_order(data),
                context="place_order"
            )

            logger.info(f"Order response: {response}")

            if response and response.get('s') == self.OK:
                last_order_no = response.get('id')
                logger.info(f"Order placed successfully. Order ID: {last_order_no}")
                return last_order_no
            else:
                error_code = response.get('code', 'Unknown') if response else 'Unknown'
                logger.error(f"Failed to place order. Error Code: {error_code}, Response: {response}")
                return None

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error in placing order: {e}", exc_info=True)
            return None

    def _modify_order_with_id(self, **kwargs) -> bool:
        """Modify order by ID"""
        try:
            order_id = kwargs.get('order_id')
            limit_price = kwargs.get('limit_price', 0)

            if not order_id:
                logger.error("Order ID is required to modify an order.")
                return False

            if limit_price <= 0:
                logger.error(f"Invalid limit price: {limit_price}. It must be greater than 0.")
                return False

            if not self.fyers:
                logger.error("Cannot modify order: FyersModel not initialized")
                return False

            # Prepare modification data
            data = {
                "id": order_id,
                "limitPrice": limit_price,
            }

            # Apply rate limiting
            self._check_rate_limit()

            # Modify order
            modify_response = self.retry_on_failure(
                lambda: self.fyers.modify_order(data),
                context="modify_order"
            )

            if modify_response and modify_response.get('s') == self.OK:
                logger.info(f"Order with ID {order_id} modified successfully to limit price {limit_price}.")
                return True
            else:
                logger.error(f"Failed to modify order with ID {order_id}. Response: {modify_response}")
                return False

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error in modifying order with ID {kwargs.get('order_id', 'N/A')}: {e}", exc_info=True)
            return False

    def _exit_position_with_symbol(self, **kwargs) -> bool:
        """Exit position by symbol"""
        try:
            symbol = kwargs.get('symbol')
            position_type = kwargs.get('position_type', self.PRODUCT_TYPE_MARGIN)

            if not symbol:
                logger.error("Symbol is required to exit a position.")
                return False

            if not self.fyers:
                logger.error("Cannot exit position: FyersModel not initialized")
                return False

            # Format symbol
            formatted_symbol = self._format_symbol(symbol)
            if not formatted_symbol:
                logger.error(f"Failed to format symbol: {symbol}")
                return False

            # Prepare exit data
            data = {
                "id": f"{formatted_symbol}-{position_type}"
            }

            # Apply rate limiting
            self._check_rate_limit()

            # Exit position
            exit_response = self.retry_on_failure(
                lambda: self.fyers.exit_positions(data),
                context="exit_position"
            )

            if exit_response and exit_response.get('s') == self.OK:
                logger.info(f"Successfully exited position for symbol: {symbol}")
                return True
            else:
                logger.error(f"Failed to exit position for symbol: {symbol}. Response: {exit_response}")
                return False

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error in exiting position for symbol: {kwargs.get('symbol', 'N/A')}: {e}", exc_info=True)
            return False

    def get_current_order_status(self, order_id):
        """Get current status of an order"""
        try:
            if not order_id:
                logger.error("Order ID is required to get order status")
                return None

            if not self.fyers:
                logger.error("Cannot get order status: FyersModel not initialized")
                return None

            # Get order status
            response = self.retry_on_failure(
                lambda: self.fyers.orderbook({"id": order_id}),
                context="order_status"
            )

            return response.get("orderBook") if response else None

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Exception in get_current_order_status: {e!r}", exc_info=True)
            return None

    def get_option_current_price(self, option_name):
        """Get current price of an option"""
        try:
            if not option_name:
                logger.warning("get_option_current_price called with empty option_name")
                return None

            if not self.fyers:
                logger.error("Cannot get option price: FyersModel not initialized")
                return None

            # Format symbol
            formatted_symbol = self._format_symbol(option_name)
            if not formatted_symbol:
                return None

            data = {"symbols": formatted_symbol}

            # Apply rate limiting
            self._check_rate_limit()

            # Get quotes
            response = self.retry_on_failure(
                lambda: self.fyers.quotes(data),
                context="option_current_price"
            )

            if response and response.get("s") == self.OK and response.get("d"):
                v = response["d"][0]["v"]
                price = v.get("lp")
                if price is None:
                    logger.warning(f"LTP not found in response for {option_name}: {v}")
                return price
            else:
                logger.warning(f"Failed to fetch price for {option_name}: {response}")
                return None

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Exception in get_option_current_price: {e!r}", exc_info=True)
            return None

    def get_balance(self, capital_reserve: float = 0.0):
        """Get account balance"""
        try:
            if not self.fyers:
                logger.error("Cannot get balance: FyersModel not initialized")
                return 0.0

            # Get funds
            funds = self.retry_on_failure(lambda: self.fyers.funds(), context="get_balance")

            if funds and funds.get("s") == self.OK:
                try:
                    bal_data = pd.json_normalize(funds["fund_limit"])
                    if not bal_data.empty and "id" in bal_data.columns and "equityAmount" in bal_data.columns:
                        equity_row = bal_data[bal_data["id"] == 10]
                        if not equity_row.empty:
                            account_balance = equity_row["equityAmount"].iloc[0]
                            adjusted_balance = Utils.percentage_above_or_below(
                                price=account_balance,
                                percentage=capital_reserve,
                                side=BaseEnums.NEGATIVE
                            )
                            return adjusted_balance
                        else:
                            logger.warning("No equity row (id=10) found in balance data")
                    else:
                        logger.warning("Balance data missing required fields.")
                except Exception as e:
                    logger.error(f"Error parsing balance data: {e}", exc_info=True)
            else:
                logger.warning(f"Failed to retrieve funds: {funds}")

            return 0.0

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Exception in get_balance: {e!r}", exc_info=True)
            return 0.0

    def get_history(self, symbol: str, interval: str = "2", length: int = 400):
        """Get historical data"""
        try:
            # Rule 6: Input validation
            if not symbol:
                logger.error("Symbol is required for get_history")
                return None

            if length <= 0:
                logger.warning(f"Invalid length {length}, using default 100")
                length = 100

            if not self.fyers:
                logger.error("Cannot get history: FyersModel not initialized")
                return None

            # Calculate date range
            today = datetime.today().strftime("%Y-%m-%d")
            from_date = (datetime.today() - relativedelta(days=6 if date.today().weekday() == 6 else 4)).strftime(
                "%Y-%m-%d")

            # Format symbol
            formatted_symbol = self._format_symbol(symbol)
            if not formatted_symbol:
                return None

            # Handle interval
            unit, measurement = Utils.get_interval_unit_and_measurement(interval)
            if unit and unit.lower() == 'm':
                interval = measurement

            # Prepare parameters
            params = {
                "symbol": formatted_symbol,
                "resolution": interval,
                "date_format": "1",
                "range_from": from_date,
                "range_to": today,
                "cont_flag": "1"
            }

            # Apply rate limiting
            self._check_rate_limit()

            # Get history
            response = self.retry_on_failure(
                lambda: self.fyers.history(params),
                context="get_history"
            )

            if response and response.get("s") == self.OK and "candles" in response:
                df = pd.DataFrame(response['candles'], columns=["time", "open", "high", "low", "close", "volume"])
                return df.tail(length)
            else:
                logger.warning(f"Failed to get history for {symbol}: {response}")
                return None

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Exception in get_history: {e!r}", exc_info=True)
            return None

    @staticmethod
    def calculate_pnl(current_price, buy_price=None, options=None):
        """Calculate profit/loss"""
        try:
            # Rule 6: Input validation
            if buy_price is None or options is None:
                logger.warning("Cannot calculate PnL: buy_price or options is None.")
                return None

            if current_price is None:
                logger.warning("Cannot calculate PnL: current_price is None")
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
        for attempt in range(max_retries):
            try:
                # Rule 6: Validate function
                if func is None:
                    logger.error(f"[{context}] Called with None function")
                    return None

                # Apply rate limiting before call
                self._check_rate_limit()

                # Make the API call
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
                        -17: "Access Token missing",
                        -100: "Authentication failed",
                        -101: "Invalid credentials",
                        -102: "Session expired"
                    }.get(error_code, f"Token error (code {error_code})")
                    logger.critical(f"[{context}] 🔐 {error_desc}")
                    raise TokenExpiredError(error_desc, error_code)

                # FIX: Check retryable errors
                if error_code in self.RETRYABLE_CODES:
                    delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                    error_type = "Rate limited" if error_code in self.RATE_LIMIT_CODES else "Server Error"
                    logger.warning(f"[{context}] 🔁 {error_type}. Retrying after {delay:.2f}s...")
                    time.sleep(delay)
                    continue

                # Check for token errors in string response (fallback)
                response_str = str(response) if response else ""

                # Token expired or authentication errors in string
                token_error_patterns = ["-8", "-15", "-16", "-17", "Token expired",
                                        "Invalid Access Token", "Access Token missing",
                                        "Authentication failed", "Session expired"]

                for pattern in token_error_patterns:
                    if pattern in response_str:
                        logger.critical(f"[{context}] 🔐 Token/authentication error: {pattern}")
                        raise TokenExpiredError(f"Token expired or invalid: {pattern}")

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

            except (Timeout, ConnectionError) as e:
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

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up broker resources"""
        try:
            logger.info("[Broker] Starting cleanup")

            # Close any open connections if needed
            if hasattr(self, 'fyers') and self.fyers:
                try:
                    # FyersModel might have cleanup methods
                    if hasattr(self.fyers, 'close'):
                        self.fyers.close()
                except Exception as e:
                    logger.warning(f"Error closing Fyers connection: {e}")

            logger.info("[Broker] Cleanup completed")

        except Exception as e:
            logger.error(f"[Broker.cleanup] Error: {e}", exc_info=True)