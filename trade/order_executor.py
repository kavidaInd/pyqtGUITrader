"""
order_executor_db.py
====================
Database-backed order executor that stores trades and orders in SQLite database.
"""

import logging.handlers
import random
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

import BaseEnums
from Utils.OptionUtils import OptionUtils
from Utils.Utils import Utils

from db.connector import get_db
from db.crud import orders as orders_crud, sessions as sessions_crud

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    Database-backed order executor that stores trades and orders in SQLite.
    """

    def __init__(self, broker_api, config):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            self.api = broker_api
            self.config = config

            # Feature 2: Order lock to prevent duplicate orders
            self._order_lock = threading.Lock()

            # Feature 4: Notifier (injected by TradingApp)
            self.notifier = None

            # Feature 1: Risk manager (injected by TradingApp)
            self.risk_manager = None

            # Feature 5: Trade closed callback for DailyPnLWidget
            self.on_trade_closed_callback = None

            logger.info("OrderExecutor (database) initialized")

        except Exception as e:
            logger.critical(f"[OrderExecutor.__init__] Failed: {e}", exc_info=True)
            self.api = broker_api
            self.config = config

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.api = None
        self.config = None
        self._order_lock = None
        self.notifier = None
        self.risk_manager = None
        self.on_trade_closed_callback = None

    def buy_option(self, state, option_type):
        """
        Attempt to buy an option (CALL or PUT) as per state and config.
        Feature 2: Smart order execution with mid-price -> LTP retry -> MARKET fallback
        Feature 1: Risk manager integration
        """
        try:
            # Rule 6: Input validation
            if state is None:
                logger.error("buy_option called with None state")
                return False

            if option_type not in [BaseEnums.CALL, BaseEnums.PUT]:
                logger.error(f"Invalid option_type: {option_type}")
                return False

            # Feature 1: Risk manager check
            if self.risk_manager:
                allowed, reason = self.risk_manager.should_allow_trade(state, self.config)
                if not allowed:
                    logger.warning(f"[RiskManager] Trade blocked: {reason}")
                    return False

            # Feature 2: Acquire lock to prevent duplicate orders
            if self._order_lock and not self._order_lock.acquire(blocking=False):
                logger.warning('[BUY] Duplicate order attempt blocked by lock')
                return False

            try:
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

                    # Feature 2: Smart order execution - Start with mid-price
                    success = self._smart_order_execution(state, option_type, option_name, shares, market_price)

                    if success:
                        logger.info(f"{option_type} position entered successfully.")

                    state.order_pending = False
                    return success
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
            finally:
                # Feature 2: Always release the lock
                if self._order_lock and self._order_lock.locked():
                    self._order_lock.release()

        except Exception as e:
            logger.exception(f"Unhandled exception in buy_option: {e}")
            if state:
                state.order_pending = False
            return False

    def _smart_order_execution(self, state, option_type, option_name, shares, market_price):
        """
        Feature 2: Smart order execution with three attempts:
        1. LIMIT at mid-price (based on bid/ask)
        2. LIMIT at LTP (retry)
        3. MARKET order (fallback)
        """
        try:
            # Step 1: Calculate mid-price from option chain if available
            mid_price = self._calculate_mid_price(state, option_name, market_price)

            # Attempt 1: LIMIT at mid-price
            logger.info(f"[ORDER] Attempt 1/3: LIMIT at mid-price ₹{mid_price:.2f}")
            orders = self.place_orders(option_name, shares, mid_price, state)

            if not orders:
                logger.warning("[ORDER] No orders placed in attempt 1")
                return False

            confirmed = self._wait_for_fill(orders, state, timeout_seconds=3)
            if confirmed:
                slippage = (state.current_buy_price or mid_price) - mid_price
                logger.info(f'[FILL] Mid-price fill. Slippage: ₹{slippage:+.2f}')
                state.last_slippage = slippage

                # Feature 4: Send Telegram notification
                if self.notifier:
                    self.notifier.notify_entry(
                        symbol=option_name,
                        direction=option_type,
                        price=state.current_buy_price,
                        sl=state.stop_loss or 0,
                        tp=state.tp_point or 0
                    )
                return True

            # Attempt 2: Cancel unconfirmed orders and retry at LTP
            logger.warning("[ORDER] Attempt 1 failed. Cancelling orders and retrying at LTP.")
            self._cancel_unconfirmed_orders(orders, state)

            ltp_price = Utils.round_to_nse_price(market_price)
            logger.info(f"[ORDER] Attempt 2/3: LIMIT at LTP ₹{ltp_price:.2f}")
            orders = self.place_orders(option_name, shares, ltp_price, state)

            if not orders:
                logger.warning("[ORDER] No orders placed in attempt 2")
                return False

            confirmed = self._wait_for_fill(orders, state, timeout_seconds=3)
            if confirmed:
                slippage = (state.current_buy_price or ltp_price) - mid_price
                logger.info(f'[FILL] LTP retry fill. Slippage: ₹{slippage:+.2f}')
                state.last_slippage = slippage

                # Feature 4: Send Telegram notification
                if self.notifier:
                    self.notifier.notify_entry(
                        symbol=option_name,
                        direction=option_type,
                        price=state.current_buy_price,
                        sl=state.stop_loss or 0,
                        tp=state.tp_point or 0
                    )
                return True

            # Attempt 3: MARKET order fallback (live trading only)
            logger.warning("[ORDER] Attempt 2 failed. Using MARKET order fallback.")
            self._cancel_unconfirmed_orders(orders, state)

            if self.api and BaseEnums.BOT_TYPE == BaseEnums.LIVE:
                logger.info(f"[ORDER] Attempt 3/3: MARKET order for {shares} shares")
                try:
                    # Get Broker constants (assuming they're defined)
                    side_buy = getattr(self.api, 'SIDE_BUY', 1)
                    market_order_type = getattr(self.api, 'MARKET_ORDER_TYPE', 2)

                    market_broker_id = self.api.place_order(
                        symbol=option_name,
                        qty=shares,
                        side=side_buy,
                        order_type=market_order_type
                    )

                    if market_broker_id:
                        # Record at LTP as fill price approximation
                        self.record_trade_state(state, option_type, option_name, ltp_price, shares,
                                               [{'id': 0, 'broker_id': market_broker_id,
                                                 'qty': shares, 'symbol': option_name, 'price': ltp_price}])

                        slippage = ltp_price - mid_price
                        logger.info(f'[FILL] MARKET order fill. Slippage: ₹{slippage:+.2f}')
                        state.last_slippage = slippage

                        # Feature 4: Send Telegram notification
                        if self.notifier:
                            self.notifier.notify_entry(
                                symbol=option_name,
                                direction=option_type,
                                price=ltp_price,
                                sl=state.stop_loss or 0,
                                tp=state.tp_point or 0
                            )
                        return True
                except Exception as e:
                    logger.error(f"[ORDER] MARKET order failed: {e}", exc_info=True)
            else:
                logger.warning("[ORDER] MARKET order not available (paper trading or API missing)")

            logger.error('[ORDER] All order attempts failed. No position entered.')
            return False

        except Exception as e:
            logger.exception(f"[_smart_order_execution] Failed: {e}")
            return False

    def _calculate_mid_price(self, state, option_name, market_price):
        """
        Calculate mid-price from option chain data.
        Falls back to market_price * 0.999 if bid not available.
        """
        try:
            chain_data = {}
            if hasattr(state, 'option_chain') and state.option_chain:
                # Try to get full symbol (may need mapping)
                full_sym = option_name
                if hasattr(self, 'symbol_full'):
                    full_sym = self.symbol_full(option_name)
                chain_data = state.option_chain.get(full_sym, {})

            ask = chain_data.get('ask') or market_price
            bid = chain_data.get('bid')

            if bid and bid > 0:
                mid_price = round((ask + bid) / 2, 2)
            else:
                # Estimate if no bid (use 0.1% below market price)
                mid_price = round(market_price * 0.999, 2)

            # Round to NSE price (nearest 0.05)
            mid_price = Utils.round_to_nse_price(mid_price)
            return max(mid_price, 0.05)  # Ensure minimum price

        except Exception as e:
            logger.warning(f"[_calculate_mid_price] Failed, using market price: {e}")
            return Utils.round_to_nse_price(market_price * 0.999)

    def _wait_for_fill(self, orders, state, timeout_seconds=3) -> bool:
        """
        Feature 2: Poll order status every 0.5s for up to timeout_seconds.
        Returns True if all orders reach ORDER_STATUS_EXECUTED (status code 2).
        """
        if not orders or not self.api:
            return False

        start_time = time.time()
        all_filled = False

        while time.time() - start_time < timeout_seconds:
            try:
                all_filled = True
                for order in orders:
                    broker_id = order.get('broker_id')
                    if not broker_id:
                        all_filled = False
                        continue

                    # Get order status from broker
                    status = self.api.get_current_order_status(broker_id)

                    # Status code 2 typically means executed/filled
                    if status != 2:  # Not filled
                        all_filled = False
                        break

                if all_filled:
                    # All orders filled - update state
                    if orders and not state.current_buy_price:
                        # Use first order's price as entry price
                        state.current_buy_price = orders[0].get('price')
                    return True

                time.sleep(0.5)  # Poll every 500ms

            except Exception as e:
                logger.debug(f"[_wait_for_fill] Poll error: {e}")
                time.sleep(0.5)

        return False

    def _cancel_unconfirmed_orders(self, orders, state):
        """
        Feature 2: Cancel each unconfirmed order via broker API.
        Update DB status via orders_crud.cancel().
        """
        if not orders or not self.api:
            return

        for order in orders:
            try:
                order_id = order.get('id')
                broker_id = order.get('broker_id')

                if broker_id:
                    # Cancel with broker
                    self.api.cancel_order(order_id=broker_id)
                    logger.info(f"[CANCEL] Cancelled order {broker_id}")

                # Update database
                if order_id:
                    db = get_db()
                    orders_crud.cancel(order_id, "Unfilled - switched to better price", db)

            except Exception as e:
                logger.error(f"[_cancel_unconfirmed_orders] Failed to cancel order: {e}", exc_info=True)

    def place_orders(self, symbol, shares, price, state):
        """
        Place orders in lots as per broker constraints and paper/live mode.
        Returns list of order dicts with database IDs.
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
            session_id = getattr(state, 'session_id', None)

            # Check if we're in live trading mode
            is_live = BaseEnums.BOT_TYPE == BaseEnums.LIVE and max_lot > 0

            if is_live and self.api:
                full_lots, remainder = divmod(shares, max_lot)
                for i in range(full_lots):
                    try:
                        broker_order_id = self.api.place_order(symbol=symbol, qty=max_lot, limitPrice=price)
                        if broker_order_id:
                            # Create order in database
                            db = get_db()
                            order_id = orders_crud.create(
                                session_id=session_id,
                                symbol=symbol,
                                position_type=state.current_position or "UNKNOWN",
                                quantity=max_lot,
                                broker_order_id=broker_order_id,
                                entry_price=price,
                                stop_loss=state.stop_loss,
                                take_profit=state.tp_point,
                                db=db
                            )
                            if order_id > 0:
                                orders.append({
                                    "id": order_id,
                                    "broker_id": broker_order_id,
                                    "qty": max_lot,
                                    "symbol": symbol,
                                    "price": price
                                })
                                logger.debug(f"Created order {order_id} for {max_lot} shares")
                    except Exception as e:
                        logger.error(f"Failed to place lot {i + 1}: {e}", exc_info=True)

                if remainder > 0:
                    try:
                        broker_order_id = self.api.place_order(symbol=symbol, qty=remainder, limitPrice=price)
                        if broker_order_id:
                            # Create order in database
                            db = get_db()
                            order_id = orders_crud.create(
                                session_id=session_id,
                                symbol=symbol,
                                position_type=state.current_position or "UNKNOWN",
                                quantity=remainder,
                                broker_order_id=broker_order_id,
                                entry_price=price,
                                stop_loss=state.stop_loss,
                                take_profit=state.tp_point,
                                db=db
                            )
                            if order_id > 0:
                                orders.append({
                                    "id": order_id,
                                    "broker_id": broker_order_id,
                                    "qty": remainder,
                                    "symbol": symbol,
                                    "price": price
                                })
                    except Exception as e:
                        logger.error(f"Failed to place remainder order: {e}", exc_info=True)
            else:
                # Paper-trading: simulate all as a single order
                try:
                    # Create order in database
                    db = get_db()
                    order_id = orders_crud.create(
                        session_id=session_id,
                        symbol=symbol,
                        position_type=state.current_position or "UNKNOWN",
                        quantity=shares,
                        broker_order_id=f"paper_{random.randint(10000, 99999)}_{int(datetime.now().timestamp())}",
                        entry_price=price,
                        stop_loss=state.stop_loss,
                        take_profit=state.tp_point,
                        db=db
                    )
                    if order_id > 0:
                        orders.append({
                            "id": order_id,
                            "broker_id": None,
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

        BUG #1 FIX: Stop-loss now set BELOW entry for long options (was above entry)
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

            try:
                state.tp_point = price * (1 + float(state.tp_percentage) / 100)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to calculate TP point: {e}")
                state.tp_point = None

            try:
                state.stop_loss = price * (1 - float(state.stoploss_percentage) / 100)
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
        - Updates orders in database.
        - Resets trade state.

        Feature 4: Telegram notification on exit
        Feature 5: Trade closed callback for DailyPnLWidget
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
                orders = getattr(state, "orders", [])
                db = get_db()

                total_pnl = 0.0
                total_qty = 0

                # 1. Sell and update orders
                for order in orders:
                    try:
                        if not isinstance(order, dict):
                            logger.warning(f"[EXIT] Invalid order format: {order}")
                            continue

                        order_id = order.get("id")
                        symbol = order.get("symbol")
                        qty = order.get("qty", 0)
                        broker_id = order.get("broker_id")
                        total_qty += qty

                        # Calculate P&L for this order
                        buy_price = order.get("price", 0.0)
                        pnl = (sell_price - buy_price) * qty
                        total_pnl += pnl

                        if self.api and broker_id:
                            try:
                                self.api.sell_at_current(symbol=symbol, qty=qty)
                                logger.info(f"[EXIT] Sold {qty} of {symbol} at {sell_price}")
                            except Exception as e:
                                logger.error(f"[EXIT] Failed to sell order {order_id}: {e}", exc_info=True)

                        # Update order in database
                        if order_id:
                            orders_crud.close_order(
                                order_id=order_id,
                                exit_price=sell_price,
                                pnl=pnl,
                                reason=exit_reason,
                                db=db
                            )
                            logger.debug(f"Updated order {order_id} as closed with P&L: {pnl:.2f}")

                    except Exception as e:
                        logger.error(f"[EXIT] Failed to process order {order.get('id', 'unknown')}: {e}", exc_info=True)

                logger.info(f"[EXIT] Completed exit for {state.current_position}. Reason: {exit_reason}")
                state.previous_position = state.current_position

                # Feature 4: Send Telegram notification
                if self.notifier and state.current_buy_price:
                    self.notifier.notify_exit(
                        symbol=state.current_trading_symbol,
                        direction=state.current_position,
                        entry_price=state.current_buy_price,
                        exit_price=sell_price,
                        pnl=total_pnl,
                        reason=exit_reason or 'Signal'
                    )

                # Feature 5: Call trade closed callback for DailyPnLWidget
                if self.on_trade_closed_callback and total_qty > 0:
                    try:
                        self.on_trade_closed_callback(total_pnl, total_pnl > 0)
                    except Exception as e:
                        logger.error(f"[EXIT] Trade closed callback failed: {e}", exc_info=True)

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

    def confirm_order(self, order_id: int, broker_order_id: str = None) -> bool:
        """
        Confirm an order in the database.

        Args:
            order_id: Database order ID
            broker_order_id: Optional broker order ID

        Returns:
            bool: True if successful
        """
        try:
            db = get_db()
            return orders_crud.confirm(order_id, broker_order_id, db)
        except Exception as e:
            logger.error(f"[confirm_order] Failed for order {order_id}: {e}", exc_info=True)
            return False

    def cancel_order(self, order_id: int, reason: str = None) -> bool:
        """
        Cancel an order in the database.

        Args:
            order_id: Database order ID
            reason: Cancellation reason

        Returns:
            bool: True if successful
        """
        try:
            db = get_db()

            # Cancel with broker if live
            order = orders_crud.get(order_id, db)
            if order and order.get("broker_order_id") and self.api:
                try:
                    self.api.cancel_order(order_id=order["broker_order_id"])
                except Exception as e:
                    logger.error(f"Failed to cancel with broker: {e}", exc_info=True)

            return orders_crud.cancel(order_id, reason, db)
        except Exception as e:
            logger.error(f"[cancel_order] Failed for order {order_id}: {e}", exc_info=True)
            return False

    def update_stop_loss(self, order_id: int, stop_loss: float) -> bool:
        """
        Update stop loss for an order.

        Args:
            order_id: Database order ID
            stop_loss: New stop loss price

        Returns:
            bool: True if successful
        """
        try:
            db = get_db()
            return orders_crud.update_stop_loss(order_id, stop_loss, db)
        except Exception as e:
            logger.error(f"[update_stop_loss] Failed for order {order_id}: {e}", exc_info=True)
            return False

    def get_open_orders(self, session_id: int = None) -> List[Dict]:
        """
        Get all open orders.

        Args:
            session_id: Optional session ID to filter by

        Returns:
            List of open orders
        """
        try:
            db = get_db()
            return orders_crud.list_open(session_id, db)
        except Exception as e:
            logger.error(f"[get_open_orders] Failed: {e}", exc_info=True)
            return []

    def get_order(self, order_id: int) -> Optional[Dict]:
        """
        Get order by ID.

        Args:
            order_id: Database order ID

        Returns:
            Order dict or None
        """
        try:
            db = get_db()
            return orders_crud.get(order_id, db)
        except Exception as e:
            logger.error(f"[get_order] Failed for order {order_id}: {e}", exc_info=True)
            return None

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

            # Release lock if held
            if self._order_lock and self._order_lock.locked():
                try:
                    self._order_lock.release()
                except:
                    pass

            # Clear references
            self.api = None
            self.config = None
            self.notifier = None
            self.risk_manager = None
            self.on_trade_closed_callback = None

            logger.info("[OrderExecutor] Cleanup completed")

        except Exception as e:
            logger.error(f"[OrderExecutor.cleanup] Error: {e}", exc_info=True)