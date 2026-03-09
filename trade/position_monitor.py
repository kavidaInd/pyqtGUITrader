"""
position_monitor_db.py
======================
Position monitor that works with database-backed orders.
Monitors positions, updates trailing stops, and confirms/cancels orders.

"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

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
        Update trailing stop-loss and take-profit based on price movement.

        DESIGN (entry-price anchored):
        ─────────────────────────────
        All SL / TP levels are expressed as a fixed % of the original entry
        price (current_buy_price), NOT of the current peak.  This means a
        "5% SL" always means entry × 1.05 regardless of how far price has run.

        Phase 1 – Pre-activation  (price < entry × (1 + activation_pct)):
            SL stays at entry × (1 - initial_sl_pct)   (e.g. entry × 0.93)
            TP stays at entry × (1 + tp_pct)            (e.g. entry × 1.15)

        Phase 2 – Activation  (price first crosses entry × (1 + activation_pct)):
            SL jumps immediately to entry × (1 + sl_at_activation)
                                              (e.g. entry × 1.05  → locks in profit)
            TP advances to entry × (1 + tp_pct + profit_step)

        Phase 3 – Stepping  (each further profit_step % above the last step):
            Every time price makes a new high that is ≥ previous_step + profit_step
            above entry, BOTH SL and TP are bumped up by profit_step % of entry.
            This continues until stoploss_pct_from_entry ≥ max_profit.

        Invariants enforced on every tick:
            • SL is only recalculated when price makes a new all-time high.
            • SL never moves lower than its current value.
            • All arithmetic uses entry_price as the sole anchor.
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

            if buy_price is None or current_price is None or buy_price == 0:
                logger.info("Cannot update trailing SL/TP: Missing buy/current price.")
                return

            # ── % change from entry (informational) ───────────────────────────
            change_pct = round(((current_price - buy_price) / buy_price) * 100, 4)
            state.percentage_change = change_pct

            # ── Track all-time high for this trade ────────────────────────────
            if safe_getattr(state, "highest_current_price", None) is None:
                state.highest_current_price = buy_price

            price_is_new_high = current_price > state.highest_current_price
            if price_is_new_high:
                state.highest_current_price = current_price

            # ── Only adjust levels when price is at a new high ─────────────────
            if not price_is_new_high:
                # No new high — keep existing SL/TP, never lower them
                return

            take_profit_type = safe_getattr(state, "take_profit_type", None)

            if take_profit_type != TRAILING:
                # ── Non-trailing modes: recompute SL/TP from new peak ─────────
                sl_pct = safe_getattr(state, "stoploss_percentage", 7.0)
                tp_pct = safe_getattr(state, "tp_percentage", 15.0)

                new_sl = Utils.percentage_above_or_below(
                    price=state.highest_current_price, side=NEGATIVE, percentage=sl_pct
                )
                new_tp = Utils.percentage_above_or_below(
                    price=state.highest_current_price, side=POSITIVE, percentage=tp_pct
                )

                # Never lower SL
                old_sl = safe_getattr(state, "stop_loss", None)
                if old_sl is None or new_sl > old_sl:
                    state.stop_loss = new_sl
                    self._update_orders_stop_loss(state.stop_loss)

                state.tp_point = new_tp

                logger.info(
                    f"SL/TP update (non-trailing): peak={state.highest_current_price:.2f}, "
                    f"sl={state.stop_loss:.2f}, tp={state.tp_point:.2f}"
                )
                return

            # ══════════════════════════════════════════════════════════════════
            # TRAILING MODE — entry-price anchored logic
            # ══════════════════════════════════════════════════════════════════
            activation_pct = safe_getattr(state, "trailing_activation_pct", 10.0)
            sl_at_activation = safe_getattr(state, "trailing_sl_at_activation", 5.0)
            profit_step = safe_getattr(state, "profit_step", 2.0)
            max_profit = safe_getattr(state, "max_profit", 30.0)
            activated = safe_getattr(state, "trailing_activated", False)
            last_step_pct = safe_getattr(state, "trailing_last_step_pct", 0.0)

            # Current SL/TP expressed as % above entry (positive = above entry)
            # Before activation: stoploss_percentage is the initial -SL% stored as positive
            initial_sl_pct = safe_getattr(state, "original_stoploss_per", 7.0)
            initial_tp_pct = safe_getattr(state, "original_profit_per", 15.0)

            # current_sl_pct_from_entry: positive = above entry, negative = below
            # We track this in stoploss_percentage after activation (it becomes positive)
            # Before activation it represents -initial_sl_pct
            current_sl_pct = safe_getattr(state, "stoploss_percentage", initial_sl_pct)
            current_tp_pct = safe_getattr(state, "tp_percentage", initial_tp_pct)

            if not activated:
                # ── Phase 1 → 2: Check if activation threshold is hit ─────────
                if change_pct >= activation_pct:
                    # Activate trailing
                    state.trailing_activated = True
                    activated = True

                    # SL jumps to sl_at_activation % above entry
                    new_sl_pct = sl_at_activation  # e.g. +5% above entry
                    new_tp_pct = initial_tp_pct + profit_step  # advance TP by one step

                    state.stoploss_percentage = new_sl_pct
                    state.tp_percentage = new_tp_pct

                    # Record the activation point as the first "step"
                    state.trailing_last_step_pct = activation_pct
                    last_step_pct = activation_pct

                    # Compute actual price levels from entry
                    new_sl_price = Utils.percentage_above_or_below(
                        price=buy_price, side=POSITIVE, percentage=new_sl_pct
                    )
                    new_tp_price = Utils.percentage_above_or_below(
                        price=buy_price, side=POSITIVE, percentage=new_tp_pct
                    )

                    # Safety: never lower existing SL
                    old_sl = safe_getattr(state, "stop_loss", None)
                    if old_sl is None or new_sl_price > old_sl:
                        state.stop_loss = new_sl_price
                        self._update_orders_stop_loss(state.stop_loss)

                    state.tp_point = new_tp_price

                    logger.info(
                        f"🚀 Trailing ACTIVATED: entry={buy_price:.2f}, "
                        f"current={current_price:.2f} (+{change_pct:.1f}%), "
                        f"sl → {new_sl_pct:+.1f}% of entry = {state.stop_loss:.2f}, "
                        f"tp → {new_tp_pct:.1f}% of entry = {state.tp_point:.2f}"
                    )
                # Before activation: SL/TP stay put (no update on pre-activation new-high)
                return

            # ── Phase 3: Post-activation stepping ─────────────────────────────
            # Every profit_step % above the last step triggers another raise.
            next_step_trigger = last_step_pct + profit_step

            if change_pct >= next_step_trigger:
                # How many full steps have been completed above the last recorded step?
                steps_available = int((change_pct - last_step_pct) / profit_step)

                if steps_available > 0 and current_sl_pct < max_profit:
                    new_sl_pct = min(
                        current_sl_pct + (steps_available * profit_step),
                        max_profit,
                    )
                    new_tp_pct = current_tp_pct + (steps_available * profit_step)

                    state.stoploss_percentage = new_sl_pct
                    state.tp_percentage = new_tp_pct
                    state.trailing_last_step_pct = last_step_pct + (steps_available * profit_step)

                    # Prices anchored to entry
                    new_sl_price = Utils.percentage_above_or_below(
                        price=buy_price, side=POSITIVE, percentage=new_sl_pct
                    )
                    new_tp_price = Utils.percentage_above_or_below(
                        price=buy_price, side=POSITIVE, percentage=new_tp_pct
                    )

                    # Invariant: SL never moves down
                    old_sl = safe_getattr(state, "stop_loss", None)
                    if old_sl is None or new_sl_price > old_sl:
                        state.stop_loss = new_sl_price
                        self._update_orders_stop_loss(state.stop_loss)

                    state.tp_point = new_tp_price

                    logger.info(
                        f"📈 Trailing STEP ×{steps_available}: "
                        f"entry={buy_price:.2f}, current={current_price:.2f} (+{change_pct:.1f}%), "
                        f"sl → {new_sl_pct:+.1f}% of entry = {state.stop_loss:.2f}, "
                        f"tp → {new_tp_pct:.1f}% of entry = {state.tp_point:.2f}"
                    )

        except Exception as e:
            logger.error(f"Exception in update_trailing_sl_tp: {e}", exc_info=True)

    def update_trailing_sl_tp_from_snapshot(self, trading: Any, snapshot: Dict[str, Any]) -> None:
        """
        Snapshot-safe variant of update_trailing_sl_tp.

        Reads all price/position inputs from the immutable *snapshot* dict
        (lock-free).  All mutations are written to the live state object so
        they persist across ticks.

        Implements the same entry-price-anchored trailing logic as
        update_trailing_sl_tp — see that method's docstring for the full spec.
        """
        try:
            # ── Guard: only run when there is an open confirmed position ──────
            current_position = snapshot.get('current_position')
            if current_position is None:
                logger.debug("No current position in snapshot. Skipping trailing SL/TP update.")
                return

            if not snapshot.get('current_trade_confirmed', False):
                self.confirm_trade(trading)
                return

            current_price = snapshot.get('current_price')
            buy_price = snapshot.get('current_buy_price')

            if buy_price is None or current_price is None or buy_price == 0:
                logger.info("Cannot update trailing SL/TP: Missing buy/current price in snapshot.")
                return

            # ── All mutations go to live state ─────────────────────────────────
            state = state_manager.get_state()

            # % change from entry
            change_pct = round(((current_price - buy_price) / buy_price) * 100, 4)
            state.percentage_change = change_pct

            # All-time high tracking
            if safe_getattr(state, 'highest_current_price', None) is None:
                state.highest_current_price = buy_price

            price_is_new_high = current_price > state.highest_current_price
            if price_is_new_high:
                state.highest_current_price = current_price

            # Only adjust when price is at a new high
            if not price_is_new_high:
                return

            take_profit_type = snapshot.get('take_profit_type') or safe_getattr(state, 'take_profit_type', None)

            if take_profit_type != TRAILING:
                # Non-trailing: trail SL/TP off the new peak
                sl_pct = snapshot.get('stoploss_percentage') or safe_getattr(state, 'stoploss_percentage', 7.0)
                tp_pct = snapshot.get('tp_percentage') or safe_getattr(state, 'tp_percentage', 15.0)

                new_sl = Utils.percentage_above_or_below(
                    price=state.highest_current_price, side=NEGATIVE, percentage=sl_pct
                )
                new_tp = Utils.percentage_above_or_below(
                    price=state.highest_current_price, side=POSITIVE, percentage=tp_pct
                )

                old_sl = safe_getattr(state, 'stop_loss', None)
                if old_sl is None or new_sl > old_sl:
                    state.stop_loss = new_sl
                    self._update_orders_stop_loss(state.stop_loss)

                state.tp_point = new_tp
                logger.info(
                    f"SL/TP update (non-trailing, snapshot): peak={state.highest_current_price:.2f}, "
                    f"sl={state.stop_loss:.2f}, tp={state.tp_point:.2f}"
                )
                return

            # ══════════════════════════════════════════════════════════════════
            # TRAILING MODE — entry-price anchored
            # ══════════════════════════════════════════════════════════════════
            activation_pct = safe_getattr(state, 'trailing_activation_pct', 10.0)
            sl_at_activation = safe_getattr(state, 'trailing_sl_at_activation', 5.0)
            profit_step = safe_getattr(state, 'profit_step', 2.0)
            max_profit = safe_getattr(state, 'max_profit', 30.0)
            activated = safe_getattr(state, 'trailing_activated', False)
            last_step_pct = safe_getattr(state, 'trailing_last_step_pct', 0.0)
            initial_sl_pct = safe_getattr(state, 'original_stoploss_per', 7.0)
            initial_tp_pct = safe_getattr(state, 'original_profit_per', 15.0)
            current_sl_pct = safe_getattr(state, 'stoploss_percentage', initial_sl_pct)
            current_tp_pct = safe_getattr(state, 'tp_percentage', initial_tp_pct)

            if not activated:
                if change_pct >= activation_pct:
                    state.trailing_activated = True
                    new_sl_pct = sl_at_activation
                    new_tp_pct = initial_tp_pct + profit_step

                    state.stoploss_percentage = new_sl_pct
                    state.tp_percentage = new_tp_pct
                    state.trailing_last_step_pct = activation_pct

                    new_sl_price = Utils.percentage_above_or_below(
                        price=buy_price, side=POSITIVE, percentage=new_sl_pct
                    )
                    new_tp_price = Utils.percentage_above_or_below(
                        price=buy_price, side=POSITIVE, percentage=new_tp_pct
                    )

                    old_sl = safe_getattr(state, 'stop_loss', None)
                    if old_sl is None or new_sl_price > old_sl:
                        state.stop_loss = new_sl_price
                        self._update_orders_stop_loss(state.stop_loss)

                    state.tp_point = new_tp_price

                    logger.info(
                        f"🚀 Trailing ACTIVATED (snapshot): entry={buy_price:.2f}, "
                        f"current={current_price:.2f} (+{change_pct:.1f}%), "
                        f"sl → {new_sl_pct:+.1f}% of entry = {state.stop_loss:.2f}, "
                        f"tp → {new_tp_pct:.1f}% of entry = {state.tp_point:.2f}"
                    )
                return

            # Phase 3: stepping
            if change_pct >= last_step_pct + profit_step:
                steps_available = int((change_pct - last_step_pct) / profit_step)

                if steps_available > 0 and current_sl_pct < max_profit:
                    new_sl_pct = min(
                        current_sl_pct + (steps_available * profit_step),
                        max_profit,
                    )
                    new_tp_pct = current_tp_pct + (steps_available * profit_step)

                    state.stoploss_percentage = new_sl_pct
                    state.tp_percentage = new_tp_pct
                    state.trailing_last_step_pct = last_step_pct + (steps_available * profit_step)

                    new_sl_price = Utils.percentage_above_or_below(
                        price=buy_price, side=POSITIVE, percentage=new_sl_pct
                    )
                    new_tp_price = Utils.percentage_above_or_below(
                        price=buy_price, side=POSITIVE, percentage=new_tp_pct
                    )

                    old_sl = safe_getattr(state, 'stop_loss', None)
                    if old_sl is None or new_sl_price > old_sl:
                        state.stop_loss = new_sl_price
                        self._update_orders_stop_loss(state.stop_loss)

                    state.tp_point = new_tp_price

                    logger.info(
                        f"📈 Trailing STEP ×{steps_available} (snapshot): "
                        f"entry={buy_price:.2f}, current={current_price:.2f} (+{change_pct:.1f}%), "
                        f"sl → {new_sl_pct:+.1f}% of entry = {state.stop_loss:.2f}, "
                        f"tp → {new_tp_pct:.1f}% of entry = {state.tp_point:.2f}"
                    )

        except Exception as e:
            logger.error(f"Exception in update_trailing_sl_tp_from_snapshot: {e}", exc_info=True)

    def _update_orders_stop_loss(self, stop_loss: float) -> None:
        """Update stop loss in the database for all open orders."""
        try:
            state = state_manager.get_state()
            order_list = safe_getattr(state, "orders", [])
            if not order_list:
                return

            db = get_db()
            for order in order_list:
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
                order_list = safe_getattr(state, "orders", [])
                any_broker_filled = False
                if trading is not None:
                    for _ord in order_list:
                        if not isinstance(_ord, dict):
                            continue
                        _bid = _ord.get("broker_id")
                        if not _bid:
                            continue  # paper order — not filled via broker
                        try:
                            _status = trading.get_current_order_status(_bid)
                            if _status == ORDER_STATUS_EXECUTED:
                                any_broker_filled = True
                                logger.warning(
                                    f"[confirm_trade] Deadline triggered but broker reports "
                                    f"order broker_id={_bid} as FILLED — forcing confirmation "
                                    "instead of cancelling."
                                )
                                # Update DB record and mark confirmed
                                try:
                                    orders_crud.confirm(_ord.get("id"), _bid, get_db())
                                except Exception as _db_e:
                                    logger.error(f"[confirm_trade] DB confirm failed: {_db_e}")
                                break
                        except Exception as _se:
                            logger.debug(f"[confirm_trade] Status check failed for {_bid}: {_se}")

                if any_broker_filled:
                    state.current_trade_confirmed = True
                    logger.info("[confirm_trade] Position confirmed via broker status check.")
                    return

                # No filled order found on broker — safe to cancel
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
