import logging
import logging.handlers
import os
from datetime import datetime
import random
import csv
import traceback
from typing import Dict, List, Optional, Any, Tuple

import BaseEnums
from Utils.OptionUtils import OptionUtils
from Utils.Utils import Utils

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class OrderExecutor:
    def __init__(self, broker_api, config, trades_file="logs/trades.csv"):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            self.api = broker_api
            self.config = config
            self.trades_file = trades_file

            self.ensure_daily_trades_file()

            logger.info("OrderExecutor initialized")

        except Exception as e:
            logger.critical(f"[OrderExecutor.__init__] Failed: {e}", exc_info=True)
            self.api = broker_api
            self.config = config
            self.trades_file = trades_file

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.api = None
        self.config = None
        self.trades_file = "logs/trades.csv"

    @staticmethod
    def _trade_fields():
        """Return list of trade CSV fields"""
        try:
            return [
                "order_id", "symbol", "side", "qty", "buy_price",
                "sell_price", "pnl", "transaction_cost", "net_pnl",
                "percentage_change", "start_time", "end_time", "status", "reason"
            ]
        except Exception as e:
            logger.error(f"[_trade_fields] Failed: {e}", exc_info=True)
            return []

    def buy_option(self, state, option_type):
        """
        Attempt to buy an option (CALL or PUT) as per state and config.
        """
        try:
            # Rule 6: Input validation
            if state is None:
                logger.error("buy_option called with None state")
                return False

            if option_type not in [BaseEnums.CALL, BaseEnums.PUT]:
                logger.error(f"Invalid option_type: {option_type}")
                return False

            if state.current_position is not None:
                logger.info("[BUY] Position already open. Exiting buy.")
                return False

            if not state.order_pending:
                state.order_pending = True

                # Select option name and price
                option_name = state.call_option if option_type == BaseEnums.CALL else state.put_option
                market_price = state.call_current_close if option_type == BaseEnums.CALL else state.put_current_close

                if market_price is None:
                    logger.warning(f"{option_type} market price missing, fetching live price for {option_name}")
                    if self.api:
                        try:
                            market_price = self.api.get_option_current_price(option_name)
                        except Exception as e:
                            logger.error(f"Failed to fetch live price: {e}", exc_info=True)
                            market_price = None
                    else:
                        logger.error("API not available")
                        market_price = None

                    if market_price is None:
                        logger.error(f"Failed to fetch live price for {option_name}")
                        state.order_pending = False
                        return False

                try:
                    shares = Utils.calculate_shares_to_buy(
                        price=market_price,
                        balance=state.account_balance,
                        lot_size=state.lot_size
                    )
                except Exception as e:
                    logger.error(f"Failed to calculate shares: {e}", exc_info=True)
                    state.order_pending = False
                    return False

                logger.info(f"Buying {option_type}: {option_name}, Market Price: {market_price}, Shares: {shares}")

                if shares < state.lot_size:
                    shares = self.adjust_positions(state=state, shares=shares, side=option_type)
                    option_name = state.call_option if option_type == BaseEnums.CALL else state.put_option

                    if self.api:
                        try:
                            market_price = self.api.get_option_current_price(option_name)
                        except Exception as e:
                            logger.error(f"Failed to fetch adjusted price: {e}", exc_info=True)
                            market_price = None
                    else:
                        market_price = None

                    if market_price is None:
                        logger.error(f"Failed to fetch live price for {option_name} after adjustment")
                        state.order_pending = False
                        return False

                if shares < state.lot_size:
                    logger.warning("Insufficient balance even after adjusting positions.")
                    state.order_pending = False
                    return False

                try:
                    limit_price = Utils.percentage_above_or_below(
                        market_price,
                        state.lower_percentage,
                        BaseEnums.NEGATIVE
                    )
                except Exception as e:
                    logger.error(f"Failed to calculate limit price: {e}", exc_info=True)
                    state.order_pending = False
                    return False

                logger.info(f"Limit price for order: {limit_price:.2f}")
                orders = self.place_orders(option_name, shares, limit_price, state)

                if not orders:
                    logger.warning("No orders were placed. Aborting buy.")
                    state.order_pending = False
                    return False

                try:
                    self.record_trade_state(state, option_type, option_name, limit_price, shares, orders)
                except Exception as e:
                    logger.error(f"Failed to record trade state: {e}", exc_info=True)
                    state.order_pending = False
                    return False

                logger.info(f"{option_type} position entered at {limit_price} for {shares} shares.")
                state.order_pending = False
                return True
            else:
                logger.warning("Order already pending")
                return False

        except AttributeError as e:
            logger.error(f"Attribute error in buy_option: {e}", exc_info=True)
            if state:
                state.order_pending = False
            return False
        except Exception as e:
            logger.exception(f"Exception in buy_option: {e}")
            if state:
                state.order_pending = False
            return False

    def place_orders(self, symbol, shares, price, state):
        """
        Place orders in lots as per broker constraints and paper/live mode.
        """
        orders = []
        try:
            # Rule 6: Input validation
            if not symbol:
                logger.warning("place_orders called with empty symbol")
                return []

            if shares <= 0:
                logger.warning(f"place_orders called with invalid shares: {shares}")
                return []

            if price <= 0:
                logger.warning(f"place_orders called with invalid price: {price}")
                return []

            if state is None:
                logger.warning("place_orders called with None state")
                return []

            max_lot = getattr(state, 'max_num_of_option', 0)

            # Check if we're in live trading mode
            is_live = BaseEnums.BOT_TYPE == BaseEnums.LIVE and max_lot > 0

            if is_live and self.api:
                full_lots, remainder = divmod(shares, max_lot)
                for i in range(full_lots):
                    try:
                        oid = self.api.place_order(symbol=symbol, qty=max_lot, limitPrice=price)
                        if oid:
                            orders.append({"id": oid, "qty": max_lot, "symbol": symbol, "price": price})
                    except Exception as e:
                        logger.error(f"Failed to place lot {i + 1}: {e}", exc_info=True)

                if remainder > 0:
                    try:
                        oid = self.api.place_order(symbol=symbol, qty=remainder, limitPrice=price)
                        if oid:
                            orders.append({"id": oid, "qty": remainder, "symbol": symbol, "price": price})
                    except Exception as e:
                        logger.error(f"Failed to place remainder order: {e}", exc_info=True)
            else:
                # Paper-trading: simulate all as a single order
                try:
                    orders.append({
                        "id": f"paper_{random.randint(10000, 99999)}_{int(datetime.now().timestamp())}",
                        "qty": shares,
                        "symbol": symbol,
                        "price": price
                    })
                except Exception as e:
                    logger.error(f"Failed to create paper order: {e}", exc_info=True)

            return orders

        except Exception as e:
            logger.exception(f"Failed to place orders: {e}")
            return []

    @staticmethod
    def record_trade_state(state, option_type, symbol, price, shares, orders):
        """
        Update trading state after a buy.
        """
        try:
            # Rule 6: Input validation
            if state is None:
                logger.error("record_trade_state called with None state")
                return False

            if price <= 0:
                logger.error(f"[record_trade_state] Invalid price ({price}) for {symbol}. Cannot set trade state.")
                return False

            state.orders = orders if orders else []
            state.current_position = option_type
            state.current_trading_symbol = symbol
            state.current_buy_price = price
            state.current_price = price
            state.highest_current_price = price
            state.current_trade_started_time = datetime.now()
            state.current_trade_confirmed = False
            state.positions_hold = shares

            # Safely extract index stop loss - it's optional, so don't abort if missing
            try:
                # Get the trend list safely, default to empty list if any key is missing
                derivative_trend = getattr(state, 'derivative_trend', {})
                if derivative_trend:
                    super_trend_short = derivative_trend.get("super_trend_short", {})
                    if super_trend_short:
                        trend_list = super_trend_short.get("trend") or []

                        # Set index_stop_loss to the last value if list exists and is not empty
                        if trend_list and len(trend_list) > 0:
                            try:
                                state.index_stop_loss = float(trend_list[-1])
                                logger.debug(f"[record_trade_state] Index stop loss set to: {state.index_stop_loss}")
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Failed to convert index stop loss: {e}")
                                state.index_stop_loss = None
                        else:
                            state.index_stop_loss = None
                            logger.debug("[record_trade_state] Index stop loss not available")
                    else:
                        state.index_stop_loss = None
                else:
                    state.index_stop_loss = None

            except (AttributeError, KeyError, IndexError, ValueError, TypeError) as e:
                # Catch any unexpected errors and set to None
                state.index_stop_loss = None
                logger.warning(f"[record_trade_state] Failed to set index stop loss: {e} - continuing without it")

            # Calculate TP and SL points
            try:
                state.tp_point = price * (1 + float(state.tp_percentage) / 100)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to calculate TP point: {e}")
                state.tp_point = None

            try:
                state.stop_loss = price * (1 + float(state.stoploss_percentage) / 100)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to calculate SL point: {e}")
                state.stop_loss = None

            logger.info(f"[record_trade_state] Entry price: {price:.2f}, TP: {state.tp_point or 0:.2f} "
                        f"({state.tp_percentage}%), SL: {state.stop_loss or 0:.2f} "
                        f"({state.stoploss_percentage}%)")

            return True

        except Exception as e:
            logger.exception(f"[record_trade_state] Failed: {e}")
            return False

    def adjust_positions(self, state, shares, side):
        """
        Try to adjust lookback and get a cheaper option if not enough balance for at least one lot.
        """
        try:
            # Rule 6: Input validation
            if state is None:
                logger.warning("adjust_positions called with None state")
                return shares

            if shares is None:
                shares = 0

            max_attempts = 10
            for attempt in range(max_attempts):
                try:
                    if shares >= state.lot_size:
                        break

                    if side == BaseEnums.CALL:
                        state.call_lookback = OptionUtils.lookbacks(
                            derivative=state.derivative,
                            lookback=state.call_lookback,
                            side=side
                        )
                        state.call_option = OptionUtils.get_option_at_price(
                            derivative_price=state.derivative_current_price,
                            lookback=state.call_lookback,
                            expiry=state.expiry,
                            op_type='CE',
                            derivative_name=state.derivative
                        )
                        option_name = state.call_option
                    else:
                        state.put_lookback = OptionUtils.lookbacks(
                            derivative=state.derivative,
                            lookback=state.put_lookback,
                            side=side
                        )
                        state.put_option = OptionUtils.get_option_at_price(
                            derivative_price=state.derivative_current_price,
                            lookback=state.put_lookback,
                            expiry=state.expiry,
                            op_type='PE',
                            derivative_name=state.derivative
                        )
                        option_name = state.put_option

                    if not option_name:
                        logger.warning(f"[ADJUST] Failed to get option name for attempt {attempt + 1}")
                        continue

                    price = None
                    if self.api:
                        try:
                            price = self.api.get_option_current_price(option_name)
                        except Exception as e:
                            logger.warning(f"[ADJUST] Failed to fetch price for {option_name}: {e}")

                    if price is None:
                        logger.warning(f"[ADJUST] Failed to fetch price for {option_name}")
                        continue

                    shares = Utils.calculate_shares_to_buy(
                        price=price,
                        balance=state.account_balance,
                        lot_size=state.lot_size
                    )
                except Exception as e:
                    logger.warning(f"[ADJUST] Attempt {attempt + 1} failed: {e}")
                    continue

            return shares

        except Exception as e:
            logger.exception(f"[ADJUST] Failed to adjust positions: {e}")
            return shares

    def exit_position(self, state, reason=None):
        """
        Gracefully exits the current CALL or PUT position:
        - Sells all confirmed orders.
        - Cancels all unconfirmed orders.
        - Logs completed trades to CSV.
        - Resets trade state.
        """
        try:
            # Rule 6: Input validation
            if state is None:
                logger.error("exit_position called with None state")
                return False

            if state.current_position not in {BaseEnums.CALL, BaseEnums.PUT}:
                logger.warning(f"[EXIT] Not in CALL or PUT. Current position: {state.current_position}")
                return False

            if not state.order_pending:
                state.order_pending = True

                # Fetch current price for exit
                sell_price = state.current_price
                if sell_price is None:
                    logger.warning("[EXIT] Current price unavailable. Cannot exit position.")
                    state.order_pending = False
                    return False

                exit_reason = reason if reason else getattr(state, 'reason_to_exit', None)
                confirmed_orders = getattr(state, "confirmed_orders", [])
                unconfirmed_orders = getattr(state, "orders", [])

                # 1. Sell confirmed orders
                for order in confirmed_orders:
                    try:
                        if not isinstance(order, dict):
                            logger.warning(f"[EXIT] Invalid order format: {order}")
                            continue

                        symbol = order.get("symbol")
                        qty = order.get("qty", 0)

                        if self.api:
                            self.api.sell_at_current(symbol=symbol, qty=qty)
                            logger.info(f"[EXIT] Sold {qty} of {symbol} at {sell_price}")

                        self.save_trade_to_csv(order, state, exit_reason)
                    except Exception as e:
                        logger.error(f"[EXIT] Failed to sell order {order.get('id', 'unknown')}: {e}", exc_info=True)

                # 2. Cancel unconfirmed orders
                for order in unconfirmed_orders:
                    try:
                        if not isinstance(order, dict):
                            continue

                        order_id = order.get("id")
                        if order_id and self.api:
                            self.api.cancel_order(order_id=order_id)
                            logger.info(f"[EXIT] Cancelled unconfirmed order ID: {order_id}")
                    except Exception as e:
                        logger.error(f"[EXIT] Failed to cancel order ID {order.get('id', 'unknown')}: {e}",
                                     exc_info=True)

                logger.info(f"[EXIT] Completed exit for {state.current_position}. Reason: {exit_reason}")
                state.previous_position = state.current_position

                # Update balance
                if self.api:
                    try:
                        state.account_balance = self.api.get_balance(state.capital_reserve)
                    except Exception as e:
                        logger.error(f"[EXIT] Failed to update balance: {e}", exc_info=True)

                # Clear all orders
                state.orders = []
                state.confirmed_orders = []

                # Reset state
                if hasattr(state, 'reset_trade_attributes'):
                    try:
                        state.reset_trade_attributes(current_position=state.previous_position)
                    except Exception as e:
                        logger.error(f"[EXIT] Failed to reset trade attributes: {e}", exc_info=True)

                state.order_pending = False
                return True
            else:
                logger.warning("[EXIT] Order already pending")
                return False

        except Exception as e:
            logger.exception(f"[EXIT] Exception during exit: {e}")
            if state:
                state.order_pending = False
            return False

    def save_trade_to_csv(self, order, state, reason):
        """
        Save a closed trade to the daily trades CSV file with transaction costs.
        """
        try:
            # Rule 6: Input validation
            if order is None:
                logger.warning("save_trade_to_csv called with None order")
                return

            if state is None:
                logger.warning("save_trade_to_csv called with None state")
                return

            # Get today's trade file
            daily_file = self.ensure_daily_trades_file()

            order_id = order.get("id", "N/A")
            symbol = order.get("symbol", "N/A")
            qty = order.get("qty", 0)
            buy_price = order.get("price", 0.0)
            sell_price = getattr(state, 'current_price', 0.0) or 0.0
            start_time = getattr(state, 'current_trade_started_time', datetime.now()) or datetime.now()
            end_time = datetime.now()
            side = getattr(state, 'current_position', "UNKNOWN") or "UNKNOWN"

            # Calculate P&L and transaction costs
            gross_pnl = (sell_price - buy_price) * qty

            try:
                transaction_cost = self.calculate_total_transaction_cost(qty, buy_price, sell_price)
            except Exception as e:
                logger.error(f"Failed to calculate transaction cost: {e}", exc_info=True)
                transaction_cost = 0.0

            net_pnl = gross_pnl - transaction_cost

            percentage_change = 0.0
            if buy_price > 0:
                percentage_change = ((sell_price - buy_price) / buy_price) * 100

            row = {
                "order_id": str(order_id),
                "symbol": str(symbol),
                "side": str(side),
                "qty": int(qty),
                "buy_price": round(float(buy_price), 2),
                "sell_price": round(float(sell_price), 2),
                "pnl": round(float(gross_pnl), 2),
                "transaction_cost": round(float(transaction_cost), 2),
                "net_pnl": round(float(net_pnl), 2),
                "percentage_change": round(float(percentage_change), 2),
                "start_time": start_time.strftime('%Y-%m-%d %H:%M:%S') if hasattr(start_time, 'strftime') else str(
                    start_time),
                "end_time": end_time.strftime('%Y-%m-%d %H:%M:%S'),
                "status": "closed",
                "reason": str(reason) if reason else ""
            }

            # Append to daily file
            try:
                with open(daily_file, mode='a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=row.keys())
                    writer.writerow(row)
                logger.info(f"[SAVE] Trade recorded - Gross P&L: {gross_pnl:.2f}, "
                            f"Transaction Cost: {transaction_cost:.2f}, Net P&L: {net_pnl:.2f}")
            except IOError as e:
                logger.error(f"Failed to write to CSV file {daily_file}: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Unexpected error writing to CSV: {e}", exc_info=True)

        except Exception as e:
            logger.exception(f"[SAVE] Failed to save trade to daily CSV: {e}")

    def get_daily_trades_file(self):
        """
        Generate daily trade file path based on current date.
        Format: logs/trades_YYYY-MM-DD.csv
        """
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            base_dir = os.path.dirname(self.trades_file) if self.trades_file else "logs"
            filename = f"trades_{today}.csv"
            return os.path.join(base_dir, filename)
        except Exception as e:
            logger.error(f"[get_daily_trades_file] Failed: {e}", exc_info=True)
            return "logs/trades_error.csv"

    def ensure_daily_trades_file(self):
        """
        Ensure the daily trades file exists with proper headers.
        Creates the file if it doesn't exist.
        """
        try:
            daily_file = self.get_daily_trades_file()

            # Create directory if it doesn't exist
            try:
                dir_path = os.path.dirname(daily_file)
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)
            except PermissionError as e:
                logger.error(f"Permission denied creating directory: {e}")
            except Exception as e:
                logger.error(f"Failed to create directory: {e}", exc_info=True)

            # Create file with headers if it doesn't exist
            if not os.path.exists(daily_file):
                try:
                    with open(daily_file, mode='w', newline='', encoding='utf-8') as file:
                        fields = self._trade_fields()
                        if fields:
                            writer = csv.DictWriter(file, fieldnames=fields)
                            writer.writeheader()
                except IOError as e:
                    logger.error(f"Failed to create daily trades file {daily_file}: {e}", exc_info=True)

            return daily_file

        except Exception as e:
            logger.error(f"[ensure_daily_trades_file] Failed: {e}", exc_info=True)
            return self.trades_file or "logs/trades.csv"

    def get_trades_file_for_date(self, date_str):
        """
        Get the trades file path for a specific date.

        :param date_str: Date string in format 'YYYY-MM-DD'
        :return: File path for that date's trades
        """
        try:
            if not date_str:
                logger.warning("get_trades_file_for_date called with empty date_str")
                return self.trades_file or "logs/trades.csv"

            base_dir = os.path.dirname(self.trades_file) if self.trades_file else "logs"
            filename = f"trades_{date_str}.csv"
            return os.path.join(base_dir, filename)
        except Exception as e:
            logger.error(f"[get_trades_file_for_date] Failed: {e}", exc_info=True)
            return self.trades_file or "logs/trades.csv"

    # Optional: Method to list all daily trade files
    def list_daily_trade_files(self):
        """
        List all daily trade files in the logs directory.

        :return: List of tuples (date, filepath) sorted by date
        """
        try:
            base_dir = os.path.dirname(self.trades_file) if self.trades_file else "logs"
            if not os.path.exists(base_dir):
                logger.debug(f"Directory {base_dir} does not exist")
                return []

            trade_files = []
            if not os.path.isdir(base_dir):
                logger.warning(f"{base_dir} is not a directory")
                return []

            for filename in os.listdir(base_dir):
                if filename.startswith('trades_') and filename.endswith('.csv'):
                    # Extract date from filename
                    date_part = filename.replace('trades_', '').replace('.csv', '')
                    try:
                        # Validate date format
                        datetime.strptime(date_part, '%Y-%m-%d')
                        filepath = os.path.join(base_dir, filename)
                        trade_files.append((date_part, filepath))
                    except ValueError:
                        logger.debug(f"Skipping file with invalid date format: {filename}")
                        continue

            # Sort by date
            trade_files.sort(key=lambda x: x[0])
            return trade_files

        except PermissionError as e:
            logger.error(f"Permission denied listing directory: {e}")
            return []
        except Exception as e:
            logger.exception(f"Failed to list daily trade files: {e}")
            return []

    @staticmethod
    def calculate_total_transaction_cost(quantity, buy_price, sell_price):
        """
        Calculate total transaction cost for complete buy-sell option trade on Fyers.

        :param quantity: Number of option contracts
        :param buy_price: Price per contract when buying
        :param sell_price: Price per contract when selling
        :return: Total transaction cost (float)
        """
        try:
            # Rule 6: Input validation
            if quantity <= 0:
                logger.warning(f"calculate_total_transaction_cost called with invalid quantity: {quantity}")
                return 0.0

            if buy_price <= 0:
                logger.warning(f"calculate_total_transaction_cost called with invalid buy_price: {buy_price}")
                return 0.0

            if sell_price <= 0:
                logger.warning(f"calculate_total_transaction_cost called with invalid sell_price: {sell_price}")
                return 0.0

            # Fyers charges
            brokerage_per_order = 20.0  # Rs 20 per order
            stt_rate = 0.0125 / 100  # 0.0125% on sell side only
            exchange_charges_rate = 0.0495 / 100  # ~0.0495%
            sebi_charges_rate = 0.0001 / 100  # 0.0001%
            stamp_duty_rate = 0.003 / 100  # 0.003% on buy side only
            gst_rate = 18.0 / 100  # 18% GST

            # Calculate turnovers
            buy_turnover = quantity * buy_price
            sell_turnover = quantity * sell_price

            # Buy side costs
            buy_brokerage = brokerage_per_order
            buy_exchange_charges = buy_turnover * exchange_charges_rate
            buy_sebi_charges = buy_turnover * sebi_charges_rate
            buy_stamp_duty = buy_turnover * stamp_duty_rate
            buy_taxable = buy_brokerage + buy_exchange_charges + buy_sebi_charges
            buy_gst = buy_taxable * gst_rate
            buy_total = buy_brokerage + buy_exchange_charges + buy_sebi_charges + buy_stamp_duty + buy_gst

            # Sell side costs
            sell_brokerage = brokerage_per_order
            sell_stt = sell_turnover * stt_rate
            sell_exchange_charges = sell_turnover * exchange_charges_rate
            sell_sebi_charges = sell_turnover * sebi_charges_rate
            sell_taxable = sell_brokerage + sell_exchange_charges + sell_sebi_charges
            sell_gst = sell_taxable * gst_rate
            sell_total = sell_brokerage + sell_stt + sell_exchange_charges + sell_sebi_charges + sell_gst

            # Total transaction cost
            total_cost = buy_total + sell_total

            return round(total_cost, 2)

        except Exception as e:
            logger.exception(f"Error calculating transaction cost: {e}")
            return 0.0

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown."""
        try:
            logger.info("[OrderExecutor] Starting cleanup")

            # Clear any pending state
            self.api = None
            self.config = None

            logger.info("[OrderExecutor] Cleanup completed")

        except Exception as e:
            logger.error(f"[OrderExecutor.cleanup] Error: {e}", exc_info=True)