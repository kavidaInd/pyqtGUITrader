"""
position_monitor_db.py
======================
Position monitor that works with database-backed orders.
Monitors positions, updates trailing stops, and confirms/cancels orders.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from BaseEnums import *
from Utils.Utils import Utils

from db.connector import get_db
from db.crud import orders as orders_crud

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

ORDER_STATUS_EXECUTED = 2


class PositionMonitor:
    """
    Position monitor that works with database-backed orders.
    Monitors positions, updates trailing stops, and confirms/cancels orders.
    """

    def update_trailing_sl_tp(self, trading: Any, state: Any) -> None:
        """
        Update the trailing stop-loss and take-profit levels based on price movement and strategy.
        """
        try:
            # Rule 6: Input validation
            if state is None:
                logger.debug("update_trailing_sl_tp called with None state")
                return

            if state.current_position is None:
                logger.debug("No current position. Skipping trailing SL/TP update.")
                return

            if not getattr(state, "current_trade_confirmed", False):
                self.confirm_trade(trading, state)
                return

            current_price = getattr(state, "current_price", None)
            buy_price = getattr(state, "current_buy_price", None)

            if buy_price is None or current_price is None:
                logger.info("Cannot update trailing SL/TP: Missing buy/current price.")
                return

            # Calculate and update percentage change
            try:
                if buy_price == 0:
                    change = 0
                    logger.warning("Buy price is zero. Cannot calculate percentage change.")
                else:
                    change = ((current_price - buy_price) / buy_price) * 100
                state.percentage_change = round(change, 2)
            except ZeroDivisionError:
                state.percentage_change = 0
                logger.warning("Buy price is zero. Cannot calculate percentage change.")
                return
            except Exception as e:
                logger.error(f"Error calculating percentage change: {e}", exc_info=True)
                state.percentage_change = 0

            if getattr(state, "highest_current_price", None) is None:
                state.highest_current_price = buy_price

            # FIX: Safely extract supertrend trend list
            try:
                derivative_trend = getattr(state, "derivative_trend", {})
                if not isinstance(derivative_trend, dict):
                    logger.warning("derivative_trend is not a dict")
                    return

                supertrend_data = derivative_trend.get("super_trend_short", {})
                if not isinstance(supertrend_data, dict):
                    logger.warning("super_trend_short is not a dict")
                    return

                trend_list = supertrend_data.get("trend") or []
                if not isinstance(trend_list, (list, tuple)):
                    logger.warning("trend_list is not a list/tuple")
                    return

                if not trend_list:
                    logger.warning("Supertrend SL not available — skipping SL update.")
                    return

                try:
                    supertrend_sl = float(trend_list[-1])
                except (ValueError, TypeError, IndexError) as e:
                    logger.warning(f"Failed to convert supertrend SL: {e}")
                    return
            except Exception as e:
                logger.warning(f"Error accessing supertrend data: {e}")
                return

            derivative_price = getattr(state, "derivative_current_price", 'N/A')

            if state.current_position == CALL:
                if state.index_stop_loss is None or supertrend_sl > state.index_stop_loss:
                    prev = state.index_stop_loss
                    state.index_stop_loss = supertrend_sl

                    # Update stop loss in database for all open orders
                    self._update_orders_stop_loss(state, supertrend_sl)

                    logger.info(f"[CALL] SL updated from {prev} to {supertrend_sl}, "
                                f"LTP: {derivative_price}")
            elif state.current_position == PUT:
                if state.index_stop_loss is None or supertrend_sl < state.index_stop_loss:
                    prev = state.index_stop_loss
                    state.index_stop_loss = supertrend_sl

                    # Update stop loss in database for all open orders
                    self._update_orders_stop_loss(state, supertrend_sl)

                    logger.info(f"[PUT] SL updated from {prev} to {supertrend_sl}, "
                                f"LTP: {derivative_price}")

            # Check if price crossed TP and increased further
            try:
                price_increased = current_price > state.highest_current_price
                tp_point = getattr(state, "tp_point", float('inf'))
                crossed_tp = current_price >= tp_point if tp_point is not None else False

                if price_increased:
                    state.highest_current_price = current_price

                    if crossed_tp and getattr(state, "take_profit_type", None) == TRAILING:
                        # Within profit range
                        original_profit = getattr(state, "original_profit_per", 0)
                        max_profit = getattr(state, "max_profit", 100)
                        change_pct = getattr(state, "percentage_change", 0)

                        if original_profit <= change_pct <= max_profit:
                            if state.stoploss_percentage == getattr(state, "original_stoploss_per", 0):
                                state.stoploss_percentage = getattr(state, "trailing_first_profit", 3.0)
                            else:
                                state.stoploss_percentage += getattr(state, "loss_step", 2.0)
                            state.tp_percentage += getattr(state, "profit_step", 2.0)

                        # Beyond max profit, trail harder if allowed
                        elif change_pct > max_profit and getattr(state, "trail_after_max_profit", False):
                            profit_step = getattr(state, "profit_step", 2.0)
                            state.stoploss_percentage += round(profit_step * 0.66, 2)
                            # Bound stoploss below max profit
                            if state.stoploss_percentage < max_profit:
                                state.stoploss_percentage = max(state.stoploss_percentage, max_profit - 5)
                            state.tp_percentage += profit_step

                        # Update SL and TP points
                        try:
                            state.stop_loss = Utils.percentage_above_or_below(
                                price=buy_price, side=POSITIVE, percentage=state.stoploss_percentage
                            )
                            state.tp_point = Utils.percentage_above_or_below(
                                price=buy_price, side=POSITIVE, percentage=state.tp_percentage
                            )

                            # Update stop loss in database
                            self._update_orders_stop_loss(state, state.stop_loss)

                            logger.info(f"Trailing update: stop_loss={state.stop_loss}, tp_point={state.tp_point}, "
                                        f"stoploss_percentage={state.stoploss_percentage}, tp_percentage={state.tp_percentage}")
                        except Exception as e:
                            logger.error(f"Failed to update SL/TP points: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Error in trailing logic: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Exception in update_trailing_sl_tp: {e}", exc_info=True)

    def _update_orders_stop_loss(self, state: Any, stop_loss: float) -> None:
        """
        Update stop loss in database for all open orders.

        Args:
            state: Trading state object
            stop_loss: New stop loss value
        """
        try:
            orders = getattr(state, "orders", [])
            if not orders:
                return

            db = get_db()
            for order in orders:
                if isinstance(order, dict) and order.get("id"):
                    order_id = order["id"]
                    orders_crud.update_stop_loss(order_id, stop_loss, db)
                    logger.debug(f"Updated stop loss for order {order_id} to {stop_loss}")
        except Exception as e:
            logger.error(f"Failed to update orders stop loss: {e}", exc_info=True)

    def confirm_trade(self, trading: Any, state: Any) -> None:
        """
        Confirms executed orders and cancels pending ones if price drifts or timeout.
        Updates order status in database.
        """
        try:
            # Rule 6: Input validation
            if state is None:
                logger.warning("confirm_trade called with None state")
                return

            if trading is None:
                logger.warning("confirm_trade called with None trading")
                return

            if getattr(state, "current_position", None) is None:
                return

            current_price = getattr(state, "current_price", None)
            buy_price = getattr(state, "current_buy_price", None)

            if current_price is None or buy_price is None:
                logger.warning("Price data missing during trade confirmation.")
                return

            now = datetime.now()
            # Avoid too frequent polling
            if not hasattr(state, "last_status_check") or state.last_status_check is None:
                state.last_status_check = datetime.min

            time_diff = (now - state.last_status_check).total_seconds()
            if time_diff < 3:
                return
            state.last_status_check = now

            confirmed = []
            unconfirmed = []
            order_list = getattr(state, "orders", [])

            if not order_list:
                logger.info("No orders to confirm.")
                state.current_trade_confirmed = True
                return

            db = get_db()
            for order in order_list:
                try:
                    if not isinstance(order, dict):
                        logger.warning(f"Order is not a dict: {order}")
                        unconfirmed.append(order)
                        continue

                    order_id = order.get("id")
                    if not order_id:
                        logger.warning("Order missing 'id'; skipping.")
                        continue

                    status_list = None
                    broker_order_id = order.get("broker_id")

                    try:
                        status_list = trading.get_current_order_status(order_id)
                    except Exception as e:
                        logger.error(f"Failed to get order status for {order_id}: {e}", exc_info=True)

                    if status_list and isinstance(status_list, list) and len(status_list) > 0:
                        order_status = status_list[0].get("status")
                        logger.debug(f"Polling Order ID {order_id}: Status = {order_status}")

                        if order_status == ORDER_STATUS_EXECUTED:
                            # Confirm order in database
                            if broker_order_id:
                                orders_crud.confirm(order_id, broker_order_id, db)
                            else:
                                orders_crud.confirm(order_id, db=db)
                            confirmed.append(order)
                        else:
                            unconfirmed.append(order)
                    else:
                        unconfirmed.append(order)
                except Exception as e:
                    logger.error(f"Error processing order {order.get('id', 'unknown')}: {e}", exc_info=True)
                    unconfirmed.append(order)

            # Save confirmed orders and update state
            try:
                state.confirmed_orders = confirmed
                state.orders = unconfirmed
            except Exception as e:
                logger.error(f"Failed to update order lists: {e}", exc_info=True)

            if confirmed:
                logger.info(f"✅ Confirmed {len(confirmed)} order(s).")

            if not unconfirmed:
                state.current_trade_confirmed = True
                logger.info("✅ All orders confirmed.")
                state.current_trade_started_time = now
                return

            # Cancel if price drifted too far or timed out
            try:
                if buy_price == 0:
                    change = 0
                else:
                    change = ((current_price - buy_price) / buy_price) * 100
            except ZeroDivisionError:
                change = 0

            trade_start_time = getattr(state, "current_trade_started_time", now)
            if trade_start_time is None:
                trade_start_time = now

            cancel_after = getattr(state, "cancel_after", 5)
            deadline = trade_start_time + timedelta(minutes=cancel_after)

            lower_per = getattr(state, "lower_percentage", 0)

            if now > deadline or change > (3 + lower_per):
                logger.warning(
                    f"❌ Trade not confirmed in time or price drifted. Change: {change:.2f}%, Deadline: {deadline}")
                self.cancel_pending_trade(trading, state)
                if hasattr(state, 'reset_trade_attributes'):
                    try:
                        state.reset_trade_attributes(current_position=None)
                    except Exception as e:
                        logger.error(f"Failed to reset trade attributes: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Exception in confirm_trade: {e}", exc_info=True)

    def cancel_pending_trade(self, trading: Any, state: Any) -> None:
        """
        Cancel all un-executed (unconfirmed) orders in `state.orders`.
        Updates order status in database.
        If any orders have already been confirmed, mark trade as confirmed.
        """
        try:
            # Rule 6: Input validation
            if state is None:
                logger.warning("cancel_pending_trade called with None state")
                return

            if trading is None:
                logger.warning("cancel_pending_trade called with None trading")
                return

            order_list = getattr(state, "orders", [])
            if not order_list:
                logger.info("No pending orders to cancel.")
                return

            has_confirmed_order = bool(getattr(state, "confirmed_orders", []))
            if has_confirmed_order:
                logger.info("Confirmed order(s) present — proceeding to cancel all unconfirmed orders.")

            logger.info(f"Attempting to cancel {len(order_list)} unconfirmed order(s)...")
            remaining_orders = []
            db = get_db()

            for order in order_list:
                try:
                    if not isinstance(order, dict):
                        logger.warning(f"Pending order is not a dict: {order}")
                        remaining_orders.append(order)
                        continue

                    order_id = order.get("id")
                    if not order_id:
                        logger.warning("Pending order missing 'id'; skipping cancel.")
                        remaining_orders.append(order)
                        continue

                    # Cancel with broker
                    try:
                        if hasattr(trading, 'cancel_order') and callable(trading.cancel_order):
                            trading.cancel_order(order_id=order_id)

                            # Update order status in database
                            orders_crud.cancel(order_id, "Trade not confirmed - cancelled", db)

                            logger.info(f"Cancelled order ID: {order_id}")
                        else:
                            logger.warning(f"Trading object has no cancel_order method")
                            remaining_orders.append(order)
                    except Exception as e:
                        logger.error(f"Failed to cancel order {order_id}: {e}", exc_info=True)
                        remaining_orders.append(order)  # If cancel fails, keep the order
                except Exception as e:
                    logger.error(f"Error processing order for cancellation: {e}", exc_info=True)
                    remaining_orders.append(order)

            # Update state with only remaining (not canceled) orders
            try:
                state.orders = remaining_orders
            except Exception as e:
                logger.error(f"Failed to update orders list: {e}", exc_info=True)

            # If at least one order was confirmed, mark trade as confirmed
            if has_confirmed_order:
                try:
                    state.current_trade_confirmed = True
                    logger.info("Trade confirmed due to presence of confirmed order(s).")
                except Exception as e:
                    logger.error(f"Failed to set trade confirmed flag: {e}", exc_info=True)

            if not state.orders:
                logger.info("All pending orders successfully cancelled.")
            else:
                logger.warning(f"{len(state.orders)} pending order(s) could not be cancelled. "
                               f"Manual intervention may be required.")

        except Exception as e:
            logger.error(f"Exception in cancel_pending_trade: {e}", exc_info=True)

    def get_open_orders_count(self, state: Any) -> int:
        """
        Get count of open orders from state.

        Args:
            state: Trading state object

        Returns:
            Number of open orders
        """
        try:
            return len(getattr(state, "orders", []))
        except Exception as e:
            logger.error(f"[get_open_orders_count] Failed: {e}", exc_info=True)
            return 0

    def has_confirmed_orders(self, state: Any) -> bool:
        """
        Check if there are any confirmed orders.

        Args:
            state: Trading state object

        Returns:
            True if there are confirmed orders
        """
        try:
            return bool(getattr(state, "confirmed_orders", []))
        except Exception as e:
            logger.error(f"[has_confirmed_orders] Failed: {e}", exc_info=True)
            return False

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown."""
        try:
            logger.info("[PositionMonitor] Starting cleanup")
            # No resources to clean up currently
            logger.info("[PositionMonitor] Cleanup completed")
        except Exception as e:
            logger.error(f"[PositionMonitor.cleanup] Error: {e}", exc_info=True)