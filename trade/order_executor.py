import logging
import os
from datetime import datetime
import random
import csv

import BaseEnums
from Utils.OptionUtils import OptionUtils
from Utils.Utils import Utils

logger = logging.getLogger(__name__)


class OrderExecutor:
    def __init__(self, broker_api, config, trades_file="logs/trades.csv"):
        self.api = broker_api
        self.config = config
        self.trades_file = trades_file

        self.ensure_daily_trades_file()

    @staticmethod
    def _trade_fields():
        return [
            "order_id", "symbol", "side", "qty", "buy_price",
            "sell_price", "pnl", "transaction_cost", "net_pnl",
            "percentage_change", "start_time", "end_time", "status", "reason"
        ]

    def buy_option(self, state, option_type):
        """
        Attempt to buy an option (CALL or PUT) as per state and config.
        """
        try:
            if state.current_position is not None:
                logger.info("[BUY] Position already open. Exiting buy.")
                return

            if not state.order_pending:
                state.order_pending = True

                # Select option name and price
                option_name = state.call_option if option_type == BaseEnums.CALL else state.put_option
                market_price = state.call_current_close if option_type == BaseEnums.CALL else state.put_current_close

                if market_price is None:
                    logger.warning(f"{option_type} market price missing, fetching live price for {option_name}")
                    market_price = self.api.get_option_current_price(option_name)
                    if market_price is None:
                        logger.error(f"Failed to fetch live price for {option_name}")
                        state.order_pending = False
                        return False

                shares = Utils.calculate_shares_to_buy(price=market_price,
                                                       balance=state.account_balance,
                                                       lot_size=state.lot_size)
                logger.info(f"Buying {option_type}: {option_name}, Market Price: {market_price}, Shares: {shares}")

                if shares < state.lot_size:
                    shares = self.adjust_positions(state=state, shares=shares, side=option_type)
                    option_name = state.call_option if option_type == BaseEnums.CALL else state.put_option
                    market_price = self.api.get_option_current_price(option_name)
                    if market_price is None:
                        logger.error(f"Failed to fetch live price for {option_name}")
                        state.order_pending = False
                        return False

                if shares < state.lot_size:
                    logger.warning("Insufficient balance even after adjusting positions.")
                    state.order_pending = False
                    return False

                limit_price = Utils.percentage_above_or_below(market_price, state.lower_percentage, BaseEnums.NEGATIVE)
                logger.info(f"Limit price for order: {limit_price:.2f}")
                orders = self.place_orders(option_name, shares, limit_price, state)

                if not orders:
                    logger.warning("No orders were placed. Aborting buy.")
                    state.order_pending = False
                    return False

                self.record_trade_state(state, option_type, option_name, limit_price, shares, orders)
                logger.info(f"{option_type} position entered at {limit_price} for {shares} shares.")
                state.order_pending = False
                return True

        except Exception as e:
            logger.exception(f"Exception in buy_option: {e}")
            return False

    def place_orders(self, symbol, shares, price, state):
        """
        Place orders in lots as per broker constraints and paper/live mode.
        """
        orders = []
        try:
            max_lot = getattr(state, 'max_num_of_option', 0)
            if BaseEnums.BOT_TYPE == BaseEnums.LIVE and max_lot > 0:
                full_lots, remainder = divmod(shares, max_lot)
                for _ in range(full_lots):
                    oid = self.api.place_order(symbol=symbol, qty=max_lot, limitPrice=price)
                    if oid:
                        orders.append({"id": oid, "qty": max_lot, "symbol": symbol, "price": price})
                if remainder:
                    oid = self.api.place_order(symbol=symbol, qty=remainder, limitPrice=price)
                    if oid:
                        orders.append({"id": oid, "qty": remainder, "symbol": symbol, "price": price})
            else:
                # Paper-trading: simulate all as a single order
                orders.append({
                    "id": str(random.random()),
                    "qty": shares,
                    "symbol": symbol,
                    "price": price
                })

            return orders
        except Exception as e:
            logger.exception(f"Failed to place orders: {e}")
            return []

    @staticmethod
    def record_trade_state(state, option_type, symbol, price, shares, orders):
        """
        Update trading state after a buy.
        """
        state.orders = orders
        state.current_position = option_type
        state.current_trading_symbol = symbol
        state.current_buy_price = price
        state.current_price = price
        state.highest_current_price = price
        state.current_trade_started_time = datetime.now()
        state.current_trade_confirmed = False
        state.positions_hold = shares
        # Defensive: super_trend_short/trend may not exist
        index_stop_loss = state.derivative_trend.get("super_trend_short", {}).get("trend", None)
        state.index_stop_loss = index_stop_loss[-1]
        state.tp_point = price + state.tp_percentage
        state.stop_loss = price - state.stoploss_percentage

    def adjust_positions(self, state, shares, side):
        """
        Try to adjust lookback and get a cheaper option if not enough balance for at least one lot.
        """
        try:
            for _ in range(10):
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

                price = self.api.get_option_current_price(option_name)
                if price is None:
                    logger.warning(f"[ADJUST] Failed to fetch price for {option_name}")
                    continue

                shares = Utils.calculate_shares_to_buy(
                    price=price,
                    balance=state.account_balance,
                    lot_size=state.lot_size
                )
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
            if state.current_position not in {BaseEnums.CALL, BaseEnums.PUT}:
                logger.warning(f"[EXIT] Not in CALL or PUT. Current position: {state.current_position}")
                return

            if not state.order_pending:
                state.order_pending = True
                # Fetch current price for exit
                sell_price = state.current_price
                if sell_price is None:
                    logger.warning("[EXIT] Current price unavailable. Cannot exit position.")
                    state.order_pending = False
                    return
                reason = reason if reason else state.reason_to_exit
                confirmed_orders = getattr(state, "confirmed_orders", [])
                unconfirmed_orders = getattr(state, "orders", [])

                # 1. Sell confirmed orders
                for order in confirmed_orders:
                    try:
                        self.api.sell_at_current(symbol=order["symbol"], qty=order["qty"])
                        logger.info(f"[EXIT] Sold {order['qty']} of {order['symbol']} at {sell_price}")
                        self.save_trade_to_csv(order, state, reason)
                    except Exception as e:
                        logger.error(f"[EXIT] Failed to sell order {order['id']}: {e}")

                # 2. Cancel unconfirmed orders
                for order in unconfirmed_orders:
                    try:
                        self.api.cancel_order(order_id=order["id"])
                        logger.info(f"[EXIT] Cancelled unconfirmed order ID: {order['id']}")
                    except Exception as e:
                        logger.error(f"[EXIT] Failed to cancel order ID {order['id']}: {e}")

                logger.info(f"[EXIT] Completed exit for {state.current_position}. Reason: {reason}")
                state.previous_position = state.current_position
                state.account_balance = self.api.get_balance(state.capital_reserve)

                # Clear all orders
                state.orders = []
                state.confirmed_orders = []

                # Reset state
                state.reset_trade_attributes(current_position=state.previous_position)
                state.order_pending = False
                return True

        except Exception as e:
            logger.exception(f"[EXIT] Exception during exit: {e}")

    def save_trade_to_csv(self, order, state, reason):
        """
        Save a closed trade to the daily trades CSV file with transaction costs.
        """
        try:
            # Get today's trade file
            daily_file = self.ensure_daily_trades_file()

            order_id = order.get("id", "N/A")
            symbol = order.get("symbol", "N/A")
            qty = order.get("qty", 0)
            buy_price = order.get("price", 0.0)
            sell_price = state.current_price or 0.0
            start_time = state.current_trade_started_time or datetime.now()
            end_time = datetime.now()
            side = state.current_position or "UNKNOWN"

            # Calculate P&L and transaction costs
            gross_pnl = (sell_price - buy_price) * qty
            transaction_cost = self.calculate_total_transaction_cost(qty, buy_price, sell_price)
            net_pnl = gross_pnl - transaction_cost

            percentage_change = ((sell_price - buy_price) / buy_price) * 100 if buy_price else 0.0

            row = {
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "buy_price": round(buy_price, 2),
                "sell_price": round(sell_price, 2),
                "pnl": round(gross_pnl, 2),
                "transaction_cost": round(transaction_cost, 2),
                "net_pnl": round(net_pnl, 2),
                "percentage_change": round(percentage_change, 2),
                "start_time": start_time.strftime('%Y-%m-%d %H:%M:%S'),
                "end_time": end_time.strftime('%Y-%m-%d %H:%M:%S'),
                "status": "closed",
                "reason": reason
            }

            # Append to daily file
            with open(daily_file, mode='a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=row.keys())
                writer.writerow(row)

            logger.info(f"[SAVE] Trade recorded - Gross P&L: {gross_pnl}, "
                        f"Transaction Cost: {transaction_cost}, Net P&L: {net_pnl}")

        except Exception as e:
            logger.exception(f"[SAVE] Failed to save trade to daily CSV: {e}")

    def get_daily_trades_file(self):
        """
        Generate daily trade file path based on current date.
        Format: logs/trades_YYYY-MM-DD.csv
        """
        today = datetime.now().strftime('%Y-%m-%d')
        base_dir = os.path.dirname(self.trades_file)
        filename = f"trades_{today}.csv"
        return os.path.join(base_dir, filename)

    def ensure_daily_trades_file(self):
        """
        Ensure the daily trades file exists with proper headers.
        Creates the file if it doesn't exist.
        """
        daily_file = self.get_daily_trades_file()

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(daily_file), exist_ok=True)

        # Create file with headers if it doesn't exist
        if not os.path.exists(daily_file):
            with open(daily_file, mode='w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=self._trade_fields())
                writer.writeheader()

        return daily_file

    def get_trades_file_for_date(self, date_str):
        """
        Get the trades file path for a specific date.

        :param date_str: Date string in format 'YYYY-MM-DD'
        :return: File path for that date's trades
        """
        base_dir = os.path.dirname(self.trades_file)
        filename = f"trades_{date_str}.csv"
        return os.path.join(base_dir, filename)

    # Optional: Method to list all daily trade files
    def list_daily_trade_files(self):
        """
        List all daily trade files in the logs directory.

        :return: List of tuples (date, filepath) sorted by date
        """
        try:
            base_dir = os.path.dirname(self.trades_file)
            if not os.path.exists(base_dir):
                return []

            trade_files = []
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
                        continue

            # Sort by date
            trade_files.sort(key=lambda x: x[0])
            return trade_files

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
