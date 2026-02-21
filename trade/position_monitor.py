import logging
from datetime import datetime, timedelta
from typing import Any

from BaseEnums import *
from Utils.Utils import Utils

logger = logging.getLogger(__name__)
ORDER_STATUS_EXECUTED = 2


class PositionMonitor:
    def update_trailing_sl_tp(self, trading: Any, state: Any) -> None:
        """
        Update the trailing stop-loss and take-profit levels based on price movement and strategy.
        """
        try:
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
                change = ((current_price - buy_price) / buy_price) * 100
                state.percentage_change = round(change, 2)
            except ZeroDivisionError:
                state.percentage_change = 0
                logger.warning("Buy price is zero. Cannot calculate percentage change.")
                return

            if getattr(state, "highest_current_price", None) is None:
                state.highest_current_price = buy_price

            # FIX: Safely extract supertrend trend list
            supertrend_data = getattr(state, "derivative_trend", {}).get("super_trend_short", {})
            trend_list = supertrend_data.get("trend") or []

            if not trend_list:
                logger.warning("Supertrend SL not available — skipping SL update.")
                return

            supertrend_sl = float(trend_list[-1])

            if state.current_position == CALL:
                if state.index_stop_loss is None or supertrend_sl > state.index_stop_loss:
                    prev = state.index_stop_loss
                    state.index_stop_loss = supertrend_sl
                    logger.info(f"[CALL] SL updated from {prev} to {supertrend_sl}, "
                                f"LTP: {getattr(state, 'derivative_current_price', 'N/A')}")
            elif state.current_position == PUT:
                if state.index_stop_loss is None or supertrend_sl < state.index_stop_loss:
                    prev = state.index_stop_loss
                    state.index_stop_loss = supertrend_sl
                    logger.info(f"[PUT] SL updated from {prev} to {supertrend_sl}, "
                                f"LTP: {getattr(state, 'derivative_current_price', 'N/A')}")

            # Check if price crossed TP and increased further
            price_increased = current_price > state.highest_current_price
            crossed_tp = current_price >= getattr(state, "tp_point", float('inf'))

            if price_increased:
                state.highest_current_price = current_price

                if crossed_tp and getattr(state, "take_profit_type", None) == TRAILING:
                    # Within profit range
                    if state.original_profit_per <= state.percentage_change <= state.max_profit:
                        if state.stoploss_percentage == state.original_stoploss_per:
                            state.stoploss_percentage = state.trailing_first_profit
                        else:
                            state.stoploss_percentage += state.loss_step
                        state.tp_percentage += state.profit_step

                    # Beyond max profit, trail harder if allowed
                    elif state.percentage_change > state.max_profit and getattr(state, "trail_after_max_profit", False):
                        state.stoploss_percentage += round(state.profit_step * 0.66, 2)
                        # Bound stoploss below max profit
                        if state.stoploss_percentage < state.max_profit:
                            state.stoploss_percentage = max(state.stoploss_percentage, state.max_profit - 5)
                        state.tp_percentage += state.profit_step

                    # Update SL and TP points
                    state.stop_loss = Utils.percentage_above_or_below(
                        price=buy_price, side=POSITIVE, percentage=state.stoploss_percentage
                    )
                    state.tp_point = Utils.percentage_above_or_below(
                        price=buy_price, side=POSITIVE, percentage=state.tp_percentage
                    )
                    logger.info(f"Trailing update: stop_loss={state.stop_loss}, tp_point={state.tp_point}, "
                                f"stoploss_percentage={state.stoploss_percentage}, tp_percentage={state.tp_percentage}")

        except Exception as e:
            logger.error(f"Exception in update_trailing_sl_tp: {e}", exc_info=True)

    def confirm_trade(self, trading: Any, state: Any) -> None:
        """
        Confirms executed orders and cancels pending ones if price drifts or timeout.
        """
        if getattr(state, "current_position", None) is None:
            return

        if getattr(state, "current_price", None) is None or getattr(state, "current_buy_price", None) is None:
            logger.warning("Price data missing during trade confirmation.")
            return

        now = datetime.now()
        # Avoid too frequent polling
        if not hasattr(state, "last_status_check") or state.last_status_check is None:
            state.last_status_check = datetime.min
        if (now - state.last_status_check).total_seconds() < 3:
            return
        state.last_status_check = now

        confirmed = []
        unconfirmed = []
        order_list = getattr(state, "orders", [])
        if not order_list:
            logger.info("No orders to confirm.")
            state.current_trade_confirmed = True
            return

        for order in order_list:
            order_id = order.get("id")
            if not order_id:
                logger.warning("Order missing 'id'; skipping.")
                continue
            status_list = trading.get_current_order_status(order_id)
            if status_list:
                order_status = status_list[0].get("status")
                logger.debug(f"Polling Order ID {order_id}: Status = {order_status}")
                if order_status == ORDER_STATUS_EXECUTED:
                    confirmed.append(order)
                else:
                    unconfirmed.append(order)
            else:
                unconfirmed.append(order)

        # Save confirmed orders and update state
        state.confirmed_orders = confirmed
        state.orders = unconfirmed

        if confirmed:
            logger.info(f"✅ Confirmed {len(confirmed)} order(s).")
        if not unconfirmed:
            state.current_trade_confirmed = True
            logger.info("✅ All orders confirmed.")
            state.current_trade_started_time = now
            return

        # Cancel if price drifted too far or timed out
        try:
            change = ((state.current_price - state.current_buy_price) / state.current_buy_price) * 100
        except ZeroDivisionError:
            change = 0

        deadline = getattr(state, "current_trade_started_time", now) + timedelta(
            minutes=getattr(state, "cancel_after", 5)
        )
        lower_per = getattr(state, "lower_percentage", 0)
        if now > deadline or change > (3 + lower_per):
            logger.warning("❌ Trade not confirmed in time or price drifted. Cancelling unconfirmed orders...")
            self.cancel_pending_trade(trading, state)
            state.reset_trade_attributes(current_position=None)

    @staticmethod
    def cancel_pending_trade(trading: Any, state: Any) -> None:
        """
        Cancel all un-executed (unconfirmed) orders in `state.orders`.
        If any orders have already been confirmed, mark trade as confirmed.
        """
        try:
            order_list = getattr(state, "orders", [])
            if not order_list:
                logger.info("No pending orders to cancel.")
                return

            has_confirmed_order = bool(getattr(state, "confirmed_orders", []))
            if has_confirmed_order:
                logger.info("Confirmed order(s) present — proceeding to cancel all unconfirmed orders.")

            logger.info(f"Attempting to cancel {len(order_list)} unconfirmed order(s)...")
            remaining_orders = []
            for order in order_list:
                order_id = order.get("id")
                if not order_id:
                    logger.warning("Pending order missing 'id'; skipping cancel.")
                    remaining_orders.append(order)
                    continue
                try:
                    trading.cancel_order(order_id=order_id)
                    logger.info(f"Cancelled order ID: {order_id}")
                except Exception as e:
                    logger.error(f"Failed to cancel order {order_id}: {e}", exc_info=True)
                    remaining_orders.append(order)  # If cancel fails, keep the order

            # Update state with only remaining (not canceled) orders
            state.orders = remaining_orders

            # If at least one order was confirmed, mark trade as confirmed
            if has_confirmed_order:
                state.current_trade_confirmed = True
                logger.info("Trade confirmed due to presence of confirmed order(s).")

            if not state.orders:
                logger.info("All pending orders successfully cancelled.")
            else:
                logger.warning(f"{len(state.orders)} pending order(s) could not be cancelled. "
                               f"Manual intervention may be required.")

        except Exception as e:
            logger.error(f"Exception in cancel_pending_trade: {e}", exc_info=True)