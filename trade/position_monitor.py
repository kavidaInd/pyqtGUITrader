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
from Utils.safe_getattr import safe_getattr, safe_hasattr

from db.connector import get_db
from db.crud import orders as orders_crud
from data.trade_state_manager import state_manager

logger = logging.getLogger(__name__)

ORDER_STATUS_EXECUTED = 2


class PositionMonitor:
    """
    Position monitor that works with database-backed orders.
    Monitors positions, updates trailing stops, and confirms/cancels orders.

    Fully uses state_manager for state access. The legacy ``state`` parameter
    in method signatures is deprecated and ignored everywhere.
    """

    def update_trailing_sl_tp(self, trading: Any, state: Any = None) -> None:
        """
        Update trailing stop-loss and take-profit levels based on price movement.

        BUG #4 FIX: SL (and TP) are now calculated from highest_current_price,
        not from buy_price, so the stop actually trails the price peak.

        BUG #5 FIX: SL/TP point recalculation runs on every tick, not only
        when price is making a new high.
        """
        try:
            state = state_manager.get_state()

            if state.current_position is None:
                logger.debug("No current position. Skipping trailing SL/TP update.")
                return

            if not safe_getattr(state, "current_trade_confirmed", False):
                self.confirm_trade(trading)
                return

            current_price = safe_getattr(state, "current_price", None)
            buy_price = safe_getattr(state, "current_buy_price", None)

            if buy_price is None or current_price is None:
                logger.info("Cannot update trailing SL/TP: Missing buy/current price.")
                return

            # Calculate percentage change from entry
            try:
                if buy_price == 0:
                    logger.warning("Buy price is zero. Cannot calculate percentage change.")
                    state.percentage_change = 0
                    return
                change = ((current_price - buy_price) / buy_price) * 100
                state.percentage_change = round(change, 2)
            except ZeroDivisionError:
                state.percentage_change = 0
                logger.warning("Buy price is zero. Cannot calculate percentage change.")
                return
            except Exception as e:
                logger.error(f"Error calculating percentage change: {e}", exc_info=True)
                state.percentage_change = 0

            if safe_getattr(state, "highest_current_price", None) is None:
                state.highest_current_price = buy_price

            try:
                price_increased = current_price > state.highest_current_price
                tp_point = safe_getattr(state, "tp_point", float("inf"))
                crossed_tp = (current_price >= tp_point) if tp_point is not None else False

                # ── Update the all-time high for this trade ────────────────────
                if price_increased:
                    state.highest_current_price = current_price

                # ── Adjust trailing percentages when in profit ─────────────────
                if price_increased and crossed_tp and safe_getattr(state, "take_profit_type", None) == TRAILING:
                    original_profit = safe_getattr(state, "original_profit_per", 0)
                    max_profit = safe_getattr(state, "max_profit", 100)
                    change_pct = safe_getattr(state, "percentage_change", 0)

                    if original_profit <= change_pct <= max_profit:
                        if state.stoploss_percentage == safe_getattr(state, "original_stoploss_per", 0):
                            state.stoploss_percentage = safe_getattr(state, "trailing_first_profit", 3.0)
                        else:
                            state.stoploss_percentage += safe_getattr(state, "loss_step", 2.0)
                        state.tp_percentage += safe_getattr(state, "profit_step", 2.0)

                    elif change_pct > max_profit and safe_getattr(state, "trail_after_max_profit", False):
                        profit_step = safe_getattr(state, "profit_step", 2.0)
                        state.stoploss_percentage += round(profit_step * 0.66, 2)
                        if state.stoploss_percentage < max_profit:
                            state.stoploss_percentage = max(state.stoploss_percentage, max_profit - 5)
                        state.tp_percentage += profit_step

                try:
                    peak_price = state.highest_current_price

                    state.stop_loss = Utils.percentage_above_or_below(
                        price=peak_price,
                        side=NEGATIVE,
                        percentage=state.stoploss_percentage,
                    )

                    state.tp_point = Utils.percentage_above_or_below(
                        price=peak_price,
                        side=POSITIVE,
                        percentage=state.tp_percentage,
                    )

                    self._update_orders_stop_loss(state.stop_loss)

                    logger.info(
                        f"Trailing update: peak={peak_price:.2f}, "
                        f"stop_loss={state.stop_loss:.2f}, "
                        f"tp_point={state.tp_point:.2f}, "
                        f"sl_pct={state.stoploss_percentage}, "
                        f"tp_pct={state.tp_percentage}"
                    )
                except Exception as e:
                    logger.error(f"Failed to update SL/TP points: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error in trailing logic: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Exception in update_trailing_sl_tp: {e}", exc_info=True)

    def _update_orders_stop_loss(self, stop_loss: float) -> None:
        """Update stop loss in the database for all open orders."""
        try:
            state = state_manager.get_state()
            orders = safe_getattr(state, "orders", [])
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

    def confirm_trade(self, trading: Any, state: Any = None) -> None:
        """
        Confirm executed orders; cancel pending ones on price drift or timeout.
        """
        try:
            state = state_manager.get_state()

            if trading is None:
                logger.warning("confirm_trade called with None trading")
                return

            if safe_getattr(state, "current_position", None) is None:
                return

            current_price = safe_getattr(state, "current_price", None)
            buy_price = safe_getattr(state, "current_buy_price", None)

            if current_price is None or buy_price is None:
                logger.warning("Price data missing during trade confirmation.")
                return

            now = datetime.now()

            # Throttle polling to once every 3 seconds
            if not safe_hasattr(state, "last_status_check") or state.last_status_check is None:
                state.last_status_check = datetime.min
            if (now - state.last_status_check).total_seconds() < 3:
                return
            state.last_status_check = now

            order_list = safe_getattr(state, "orders", [])
            if not order_list:
                logger.info("No orders to confirm.")
                state.current_trade_confirmed = True
                return

            db = get_db()
            confirmed = []
            unconfirmed = []

            for order in order_list:
                try:
                    if not isinstance(order, dict):
                        logger.warning(f"Order is not a dict: {order}")
                        unconfirmed.append(order)
                        continue

                    order_id = order.get("id")
                    broker_id = order.get("broker_id")

                    if not order_id:
                        logger.warning("Order missing 'id'; skipping.")
                        continue

                    # BUG FIX: Auto-confirm paper orders. broker_id is None for paper
                    # orders created via place_orders(), but is_paper_mode is the
                    # authoritative check — if mode is paper we must never call the
                    # broker's status API regardless of what broker_id contains.
                    is_paper = safe_getattr(state, "is_paper_mode", True)
                    if broker_id is None or is_paper:
                        orders_crud.confirm(order_id, db=db)
                        confirmed.append(order)
                        logger.debug(f"Paper order {order_id} auto-confirmed.")
                        continue

                    status = None
                    try:
                        status = trading.get_current_order_status(broker_id)
                    except Exception as e:
                        logger.error(
                            f"Failed to get order status for broker_id={broker_id}: {e}",
                            exc_info=True,
                        )

                    logger.debug(f"Order {order_id} (broker={broker_id}): status={status}")

                    if status == ORDER_STATUS_EXECUTED:
                        orders_crud.confirm(order_id, broker_id, db)
                        confirmed.append(order)
                    else:
                        unconfirmed.append(order)

                except Exception as e:
                    logger.error(
                        f"Error processing order {order.get('id', 'unknown')}: {e}",
                        exc_info=True,
                    )
                    unconfirmed.append(order)

            state.confirmed_orders = confirmed

            if confirmed:
                logger.info(f"✅ Confirmed {len(confirmed)} order(s).")

            if not unconfirmed:
                state.current_trade_confirmed = True
                logger.info("✅ All orders confirmed.")
                # BUG FIX: Only set current_trade_started_time when it hasn't been set yet.
                # record_trade_state() already initialises it at entry; overwriting it here
                # would reset the cancel_after deadline every time a partial confirmation
                # arrives, making it impossible for the timeout to ever fire.
                if state.current_trade_started_time is None:
                    state.current_trade_started_time = now
                return

            # Cancel if price has drifted too far (in either direction) or order has timed out.
            # BUG FIX 1: Use abs(change) so a rapidly falling price also triggers cancellation.
            # BUG FIX 2: lower_percentage is stored as a decimal fraction (e.g. 0.01 = 1%).
            #            Convert to percentage points before comparing against the 3% threshold.
            try:
                change = ((current_price - buy_price) / buy_price) * 100 if buy_price else 0
            except ZeroDivisionError:
                change = 0

            trade_start_time = safe_getattr(state, "current_trade_started_time", now) or now
            cancel_after = safe_getattr(state, "cancel_after", 5)
            deadline = trade_start_time + timedelta(seconds=cancel_after)
            lower_per = safe_getattr(state, "lower_percentage", 0)
            drift_threshold = 3 + (lower_per * 100)  # convert fraction → percentage points

            if now > deadline or abs(change) > drift_threshold:
                logger.warning(
                    f"❌ Trade not confirmed in time or price drifted. "
                    f"Change: {change:.2f}%, Deadline: {deadline}"
                )
                self.cancel_pending_trade(trading)
                if safe_hasattr(state, "reset_trade_attributes"):
                    try:
                        state.reset_trade_attributes(current_position=None)
                    except Exception as e:
                        logger.error(f"Failed to reset trade attributes: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Exception in confirm_trade: {e}", exc_info=True)

    def cancel_pending_trade(self, trading: Any, state: Any = None) -> None:
        """
        Cancel all unconfirmed orders in state.orders.
        """
        try:
            state = state_manager.get_state()

            if trading is None:
                logger.warning("cancel_pending_trade called with None trading")
                return

            # Only cancel orders that are NOT yet confirmed
            all_orders = safe_getattr(state, "orders", [])
            confirmed_ids = {o.get("id") for o in safe_getattr(state, "confirmed_orders", []) if isinstance(o, dict)}
            pending_orders = [o for o in all_orders if isinstance(o, dict) and o.get("id") not in confirmed_ids]

            if not pending_orders:
                logger.info("No pending (unconfirmed) orders to cancel.")
                return

            has_confirmed = bool(safe_getattr(state, "confirmed_orders", []))
            if has_confirmed:
                logger.info("Confirmed order(s) present — cancelling only unconfirmed orders.")

            logger.info(f"Attempting to cancel {len(pending_orders)} unconfirmed order(s)...")

            remaining_orders = []
            db = get_db()

            for order in pending_orders:
                try:
                    order_id = order.get("id")
                    broker_id = order.get("broker_id")  # BUG #7 FIX

                    if not order_id:
                        logger.warning("Pending order missing 'id'; skipping cancel.")
                        remaining_orders.append(order)
                        continue

                    # ── BUG #7 FIX: cancel at broker using broker_id ───────────
                    broker_cancelled = True
                    if broker_id and safe_hasattr(trading, "cancel_order") and callable(trading.cancel_order):
                        try:
                            trading.cancel_order(order_id=broker_id)  # broker-side ID
                            logger.info(f"Broker cancel sent for broker_id={broker_id} (db_id={order_id})")
                        except Exception as e:
                            logger.error(
                                f"Failed to cancel broker order {broker_id}: {e}",
                                exc_info=True,
                            )
                            broker_cancelled = False
                    elif broker_id is None:
                        # Paper order — no broker call needed
                        logger.debug(f"Paper order {order_id} — skipping broker cancel.")
                    else:
                        logger.warning("Trading object has no cancel_order method.")
                        broker_cancelled = False

                    if broker_cancelled:
                        # Update DB status
                        orders_crud.cancel(order_id, "Trade not confirmed - cancelled", db)
                        logger.info(f"DB order {order_id} marked cancelled.")
                    else:
                        remaining_orders.append(order)  # keep for retry

                except Exception as e:
                    logger.error(f"Error processing order for cancellation: {e}", exc_info=True)
                    remaining_orders.append(order)

            # Remove successfully cancelled orders from state.orders
            cancelled_ids = {o.get("id") for o in pending_orders} - {o.get("id") for o in remaining_orders}
            state.orders = [o for o in all_orders if o.get("id") not in cancelled_ids]

            if has_confirmed:
                try:
                    state.current_trade_confirmed = True
                    logger.info("Trade confirmed due to presence of confirmed order(s).")
                except Exception as e:
                    logger.error(f"Failed to set trade confirmed flag: {e}", exc_info=True)

            if not remaining_orders:
                logger.info("All pending orders successfully cancelled.")
            else:
                logger.warning(
                    f"{len(remaining_orders)} pending order(s) could not be cancelled. "
                    "Manual intervention may be required."
                )

        except Exception as e:
            logger.error(f"Exception in cancel_pending_trade: {e}", exc_info=True)

    def get_open_orders_count(self) -> int:
        """Return count of open orders from state."""
        try:
            state = state_manager.get_state()
            return len(safe_getattr(state, "orders", []))
        except Exception as e:
            logger.error(f"[get_open_orders_count] Failed: {e}", exc_info=True)
            return 0

    def has_confirmed_orders(self) -> bool:
        """Return True if there are any confirmed orders."""
        try:
            state = state_manager.get_state()
            return bool(safe_getattr(state, "confirmed_orders", []))
        except Exception as e:
            logger.error(f"[has_confirmed_orders] Failed: {e}", exc_info=True)
            return False

    def cleanup(self):
        """Clean up resources before shutdown."""
        try:
            logger.info("[PositionMonitor] Starting cleanup")
            logger.info("[PositionMonitor] Cleanup completed")
        except Exception as e:
            logger.error(f"[PositionMonitor.cleanup] Error: {e}", exc_info=True)