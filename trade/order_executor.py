"""
order_executor.py
=================
Database-backed order executor.

State access rules
------------------
  * The `state` parameter received by every public method IS the singleton
    TradeState returned by `state_manager.get_state()`.  We never hold a
    long-lived reference to the state here; we only act on the object passed
    to us so the caller controls the lifetime.
  * `record_trade_state` writes multiple fields atomically — callers should
    always call this immediately after a fill is confirmed.
  * Historical / candle data is NEVER fetched or stored by this class.
    CandleStore ownership lives exclusively in TradingApp._candle_stores.

FREEZE-SIZE CHANGES
-------------------
  place_orders:
    Previously split orders by `state.max_num_of_option` (a manually-entered
    GUI value). Replaced with `OptionUtils.split_order_quantities()` which
    derives the correct per-order chunk size from the exchange freeze limit
    for the specific index (NIFTY=1800, BANKNIFTY=900, etc.) so no manual
    configuration is required and the split stays correct after SEBI lot-size
    revisions.

  exit_position:
    Sell orders for each position are now also split by freeze size. Each
    position's quantity is passed through `OptionUtils.split_order_quantities()`
    so a single large position is exited via multiple sell orders that each
    stay within the exchange freeze limit. Previously there was no splitting
    on the sell side — large positions would be rejected by the exchange.

  adjust_positions:
    `calculate_shares_to_buy` was called with `state.lot_size` (the manually-
    entered value). Now uses `OptionUtils.get_lot_size(state.derivative,
    fallback=state.lot_size)` — consistent with buy_option.
"""

import logging.handlers
import random
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

import BaseEnums
from Utils.OptionUtils import OptionUtils
from Utils.Utils import Utils
from db.connector import get_db
from db.crud import orders as orders_crud

# Import state manager for state access
from data.trade_state_manager import state_manager

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Database-backed order executor — places, confirms, cancels, and closes orders."""

    def __init__(self, broker_api, config):
        self._safe_defaults_init()
        try:
            self.api = broker_api
            self.config = config
            self._order_lock = threading.Lock()
            self.notifier = None
            self.risk_manager = None
            self.on_trade_closed_callback = None
            logger.info("OrderExecutor (database) initialized with state_manager integration")
        except Exception as e:
            logger.critical(f"[OrderExecutor.__init__] Failed: {e}", exc_info=True)
            self.api = broker_api
            self.config = config

    def _safe_defaults_init(self):
        self.api = None
        self.config = None
        self._order_lock = None
        self.notifier = None
        self.risk_manager = None
        self.on_trade_closed_callback = None

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def buy_option(self, option_type):
        """
        Attempt to buy an option (CALL or PUT).
        Feature 2: Smart order execution.
        Feature 1: Risk manager pre-flight check.

        Lot size is resolved from OptionUtils.LOT_SIZE_MAP using the
        derivative index name at the time of the order, rather than
        relying on the manually-entered trade_config.lot_size value.
        state.lot_size is retained as a fallback for instruments that
        are not in the map (custom stock options, etc.).

        Args:
            option_type: BaseEnums.CALL or BaseEnums.PUT
        """
        try:
            state = state_manager.get_state()

            if state is None:
                logger.error("buy_option called with None state from manager")
                return False

            if option_type not in [BaseEnums.CALL, BaseEnums.PUT]:
                logger.error(f"Invalid option_type: {option_type}")
                return False

            # Risk manager pre-flight check
            if self.risk_manager:
                allowed, reason = self.risk_manager.should_allow_trade(self.config)
                if not allowed:
                    logger.warning(f"[RiskManager] Trade blocked: {reason}")
                    return False

            if self._order_lock and not self._order_lock.acquire(blocking=False):
                logger.warning('[BUY] Duplicate order attempt blocked by lock')
                return False

            try:
                if state.current_position is not None:
                    logger.info("[BUY] Position already open.")
                    return False

                if state.order_pending:
                    logger.warning("Order already pending")
                    return False

                # Claim the pending slot immediately — still within _order_lock
                state.order_pending = True

                option_name = (
                    state.call_option if option_type == BaseEnums.CALL
                    else state.put_option
                )

                if not option_name:
                    logger.error(
                        f"[BUY] option_name is None for {option_type}. "
                        "Option chain may not be loaded yet."
                    )
                    state.order_pending = False
                    return False

                market_price = (
                    state.call_current_close if option_type == BaseEnums.CALL
                    else state.put_current_close
                )

                if market_price is None:
                    market_price = self._fetch_live_price(option_name)
                    if market_price is None:
                        logger.error(f"Failed to fetch live price for {option_name}")
                        state.order_pending = False
                        return False

                # ── Lot size resolution ────────────────────────────────────────
                # Resolve from OptionUtils.LOT_SIZE_MAP using the canonical index
                # name. state.lot_size is the fallback for unknown instruments.
                lot_size = OptionUtils.get_lot_size(
                    state.derivative, fallback=state.lot_size
                )

                if lot_size <= 0:
                    logger.error(
                        f"[BUY] Could not determine lot size for "
                        f"'{state.derivative}' (fallback={state.lot_size}). "
                        f"Aborting order to prevent zero-quantity trade."
                    )
                    state.order_pending = False
                    return False
                # ── End lot size resolution ────────────────────────────────────

                try:
                    shares = Utils.calculate_shares_to_buy(
                        price=market_price,
                        balance=state.account_balance,
                        lot_size=lot_size,
                    )
                except Exception as e:
                    logger.error(f"Failed to calculate shares: {e}", exc_info=True)
                    state.order_pending = False
                    return False

                logger.info(
                    f"Buying {option_type}: {option_name}, "
                    f"Price: {market_price}, Shares: {shares}, "
                    f"Lot size: {lot_size} (index: {state.derivative})"
                )

                if shares < lot_size:
                    shares = self.adjust_positions(shares=shares, side=option_type)
                    # Refresh state and prices after position adjustment
                    state = state_manager.get_state()
                    option_name = (
                        state.call_option if option_type == BaseEnums.CALL
                        else state.put_option
                    )
                    market_price = self._fetch_live_price(option_name)
                    if market_price is None:
                        state.order_pending = False
                        return False

                if shares < lot_size:
                    logger.warning("Insufficient balance even after adjusting positions.")
                    state.order_pending = False
                    return False

                success = self._smart_order_execution(
                    state, option_type, option_name, shares, market_price
                )
                if success:
                    logger.info(f"{option_type} position entered successfully.")
                state.order_pending = False
                return success

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
                if self._order_lock and self._order_lock.locked():
                    self._order_lock.release()

        except Exception as e:
            logger.exception(f"Unhandled exception in buy_option: {e}")
            state = state_manager.get_state()
            if state:
                state.order_pending = False
            return False

    def _fetch_live_price(self, option_name: Optional[str]) -> Optional[float]:
        if not self.api or not option_name:
            return None
        try:
            return self.api.get_option_current_price(option_name)
        except Exception as e:
            logger.error(f"Failed to fetch live price for {option_name}: {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Smart order execution (Feature 2)
    # ------------------------------------------------------------------

    def _smart_order_execution(self, state, option_type, option_name, shares, market_price):
        try:
            mid_price = self._calculate_mid_price(state, option_name, market_price)

            logger.info(f"[ORDER] Attempt 1/3: LIMIT at mid-price Rs{mid_price:.2f}")
            orders = self.place_orders(option_name, shares, mid_price, state)
            if not orders:
                return False

            if self._wait_for_fill(orders, state, timeout_seconds=3):
                slippage = (state.current_buy_price or mid_price) - mid_price
                logger.info(f'[FILL] Mid-price fill. Slippage: Rs{slippage:+.2f}')
                state.last_slippage = slippage
                self._notify_entry(state, option_type, option_name)
                return True

            logger.warning("[ORDER] Attempt 1 failed. Retrying at LTP.")
            self._cancel_unconfirmed_orders(orders, state)
            ltp_price = Utils.round_to_nse_price(market_price)
            logger.info(f"[ORDER] Attempt 2/3: LIMIT at LTP Rs{ltp_price:.2f}")
            orders = self.place_orders(option_name, shares, ltp_price, state)
            if not orders:
                return False

            if self._wait_for_fill(orders, state, timeout_seconds=3):
                slippage = (state.current_buy_price or ltp_price) - mid_price
                logger.info(f'[FILL] LTP retry fill. Slippage: Rs{slippage:+.2f}')
                state.last_slippage = slippage
                self._notify_entry(state, option_type, option_name)
                return True

            logger.warning("[ORDER] Attempt 2 failed. Trying MARKET order.")
            self._cancel_unconfirmed_orders(orders, state)

            # FIX: Use state's trading mode instead of global BaseEnums.BOT_TYPE
            is_paper = False
            if safe_hasattr(state, 'is_paper_mode'):
                is_paper = state.is_paper_mode
            elif safe_hasattr(state, 'trading_mode'):
                is_paper = state.trading_mode != BaseEnums.LIVE

            is_live = not is_paper

            if is_live and self.api:
                logger.info(f"[ORDER] Attempt 3/3: MARKET order for {shares} shares")
                try:
                    side_buy = safe_getattr(self.api, 'SIDE_BUY', 1)
                    mkt_type = safe_getattr(self.api, 'MARKET_ORDER_TYPE', 2)
                    broker_id = self.api.place_order(
                        symbol=option_name, qty=shares, side=side_buy, order_type=mkt_type
                    )
                    if broker_id:
                        self.record_trade_state(
                            state, option_type, option_name, ltp_price, shares,
                            [{'id': 0, 'broker_id': broker_id,
                              'qty': shares, 'symbol': option_name, 'price': ltp_price}]
                        )
                        state.last_slippage = ltp_price - mid_price
                        logger.info(f'[FILL] MARKET fill. Slippage: Rs{state.last_slippage:+.2f}')
                        self._notify_entry(state, option_type, option_name, price=ltp_price)
                        return True
                except Exception as e:
                    logger.error(f"[ORDER] MARKET order failed: {e}", exc_info=True)
            else:
                logger.warning("[ORDER] MARKET order not available (paper or no API)")

            logger.error('[ORDER] All attempts failed.')
            return False

        except Exception as e:
            logger.exception(f"[_smart_order_execution] Failed: {e}")
            return False

    def _notify_entry(self, state, option_type, option_name, price=None):
        if not self.notifier:
            return
        try:
            self.notifier.notify_entry(
                symbol=option_name, direction=option_type,
                price=price or state.current_buy_price,
                sl=state.stop_loss or 0, tp=state.tp_point or 0,
            )
        except Exception as e:
            logger.error(f"[_notify_entry] Failed: {e}", exc_info=True)

    def _calculate_mid_price(self, state, option_name, market_price):
        try:
            chain_data = {}
            if safe_hasattr(state, 'option_chain') and state.option_chain:
                chain_data = state.option_chain.get(option_name, {})
            ask = chain_data.get('ask') or market_price
            bid = chain_data.get('bid')
            mid = Utils.round_off((ask + bid) / 2) if (bid and bid > 0) else Utils.round_off(market_price * 0.999)
            return max(Utils.round_to_nse_price(mid), 0.05)
        except Exception as e:
            logger.warning(f"[_calculate_mid_price] fallback: {e}")
            return Utils.round_to_nse_price(market_price * 0.999)

    def _wait_for_fill(self, orders, state, timeout_seconds=3) -> bool:
        if not orders or not self.api:
            return False
        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                all_filled = all(
                    self.api.get_current_order_status(o.get('broker_id')) == 2
                    for o in orders if o.get('broker_id')
                )
                if all_filled:
                    if orders and not state.current_buy_price:
                        state.current_buy_price = orders[0].get('price')
                    return True
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"[_wait_for_fill] poll error: {e}")
                time.sleep(0.5)
        return False

    def _cancel_unconfirmed_orders(self, orders, state):
        if not orders or not self.api:
            return
        for order in orders:
            try:
                broker_id = order.get('broker_id')
                order_id = order.get('id')
                if broker_id:
                    self.api.cancel_order(order_id=broker_id)
                    logger.info(f"[CANCEL] Cancelled order {broker_id}")
                if order_id:
                    orders_crud.cancel(order_id, "Unfilled - switched to better price", get_db())
            except Exception as e:
                logger.error(f"[_cancel_unconfirmed_orders] Failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    def place_orders(self, symbol: str, shares: int, price: float, state) -> List[Dict]:
        """
        Place one or more buy orders for *shares* at *price*, automatically
        splitting into child orders that each respect the exchange freeze limit.

        Returns:
            List of order dicts: [{id, broker_id, qty, symbol, price}, ...]
            Empty list on any fatal error.
        """
        orders = []
        try:
            if not symbol or shares <= 0 or price <= 0 or state is None:
                return []

            session_id = safe_getattr(state, 'session_id', None)

            # FIX: Use state's trading mode instead of global BaseEnums.BOT_TYPE
            # Check if we're in paper mode - either from state or from trading_mode_setting
            is_paper = False
            if safe_hasattr(state, 'is_paper_mode'):
                is_paper = state.is_paper_mode
            elif safe_hasattr(state, 'trading_mode'):
                is_paper = state.trading_mode != BaseEnums.LIVE

            is_live = not is_paper

            if is_live and self.api:
                chunks = OptionUtils.split_order_quantities(state.derivative, shares)

                logger.info(
                    f"[place_orders] {symbol}: {shares} shares split into "
                    f"{len(chunks)} order(s) {chunks} "
                    f"(freeze limit: {OptionUtils.get_freeze_size(state.derivative)})"
                )

                for i, qty in enumerate(chunks, start=1):
                    try:
                        broker_id = self.api.place_order(
                            symbol=symbol, qty=qty, limitPrice=price
                        )
                        if broker_id:
                            oid = orders_crud.create(
                                session_id=session_id,
                                symbol=symbol,
                                position_type=state.current_position or "UNKNOWN",
                                quantity=qty,
                                broker_order_id=broker_id,
                                entry_price=price,
                                stop_loss=state.stop_loss,
                                take_profit=state.tp_point,
                                db=get_db(),
                            )
                            if oid > 0:
                                orders.append({
                                    "id": oid,
                                    "broker_id": broker_id,
                                    "qty": qty,
                                    "symbol": symbol,
                                    "price": price,
                                })
                                logger.debug(
                                    f"[place_orders] Child order {i}/{len(chunks)}: "
                                    f"qty={qty} broker_id={broker_id}"
                                )
                        else:
                            logger.error(
                                f"[place_orders] Broker returned no ID for chunk "
                                f"{i}/{len(chunks)} qty={qty}"
                            )
                    except Exception as e:
                        logger.error(
                            f"[place_orders] Failed to place chunk {i}/{len(chunks)} "
                            f"qty={qty}: {e}",
                            exc_info=True,
                        )

            else:
                # Paper / simulation — single DB record, no broker call
                try:
                    oid = orders_crud.create(
                        session_id=session_id,
                        symbol=symbol,
                        position_type=state.current_position or "UNKNOWN",
                        quantity=shares,
                        broker_order_id=(
                            f"paper_{random.randint(10000, 99999)}_{Utils.get_epoch()}"
                        ),
                        entry_price=price,
                        stop_loss=state.stop_loss,
                        take_profit=state.tp_point,
                        db=get_db(),
                    )
                    if oid > 0:
                        orders.append({
                            "id": oid,
                            "broker_id": None,
                            "qty": shares,
                            "symbol": symbol,
                            "price": price,
                        })
                except Exception as e:
                    logger.error(f"[place_orders] Failed to create paper order: {e}", exc_info=True)

            return orders

        except Exception as e:
            logger.exception(f"[place_orders] Failed: {e}")
            return []

    # ------------------------------------------------------------------
    # State recording after fill
    # ------------------------------------------------------------------

    @staticmethod
    def record_trade_state(state, option_type, symbol, price, shares, orders):
        """
        Write entry fields into TradeState after a confirmed fill.
        BUG #1 FIX: SL is BELOW entry for long options.
        """
        try:
            if state is None or price <= 0:
                logger.error(f"[record_trade_state] Invalid state or price ({price})")
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
                # SL below entry (stoploss_percentage is stored as a negative value in state)
                state.stop_loss = price * (1 - abs(float(state.stoploss_percentage)) / 100)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to calculate SL point: {e}")
                state.stop_loss = None

            logger.info(
                f"[record_trade_state] Entry: {price:.2f}, "
                f"TP: {state.tp_point or 0:.2f} ({state.tp_percentage}%), "
                f"SL: {state.stop_loss or 0:.2f} ({state.stoploss_percentage}%)"
            )
            return True
        except Exception as e:
            logger.exception(f"[record_trade_state] Failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Adjustment helper
    # ------------------------------------------------------------------

    def adjust_positions(self, shares, side):
        """
        Try cheaper strikes when insufficient balance.

        FREEZE-SIZE CHANGE
        ------------------
        `calculate_shares_to_buy` was previously called with `state.lot_size`
        (the manually-entered GUI value). Now uses
        `OptionUtils.get_lot_size(state.derivative, fallback=state.lot_size)`
        — consistent with buy_option — so the lot size is always derived
        from the index.
        """
        try:
            state = state_manager.get_state()
            if state is None:
                return shares or 0

            # Resolve lot size from index (same logic as buy_option)
            lot_size = OptionUtils.get_lot_size(
                state.derivative, fallback=state.lot_size
            )

            for attempt in range(10):
                try:
                    if shares >= lot_size:
                        break
                    if side == BaseEnums.CALL:
                        state.call_lookback = OptionUtils.lookbacks(
                            derivative=state.derivative,
                            lookback=state.call_lookback,
                            side=side,
                        )
                        state.call_option = OptionUtils.get_option_at_price(
                            derivative_price=state.derivative_current_price,
                            lookback=state.call_lookback,
                            expiry=state.expiry,
                            op_type='CE',
                            derivative_name=state.derivative,
                        )
                        option_name = state.call_option
                    else:
                        state.put_lookback = OptionUtils.lookbacks(
                            derivative=state.derivative,
                            lookback=state.put_lookback,
                            side=side,
                        )
                        state.put_option = OptionUtils.get_option_at_price(
                            derivative_price=state.derivative_current_price,
                            lookback=state.put_lookback,
                            expiry=state.expiry,
                            op_type='PE',
                            derivative_name=state.derivative,
                        )
                        option_name = state.put_option

                    if not option_name:
                        continue
                    price = self._fetch_live_price(option_name)
                    if price is None:
                        continue

                    shares = Utils.calculate_shares_to_buy(
                        price=price,
                        balance=state.account_balance,
                        lot_size=lot_size,
                    )
                except Exception as e:
                    logger.warning(f"[ADJUST] Attempt {attempt + 1} failed: {e}")
            return shares
        except Exception as e:
            logger.exception(f"[ADJUST] Failed: {e}")
            return shares or 0

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------

    def exit_position(self, reason=None):
        """
        Sell all confirmed orders, cancel pending ones, persist to DB.
        Features 4 & 5: Telegram notification + trade-closed callback.

        FREEZE-SIZE CHANGE
        ------------------
        Each position's sell quantity is now split by the exchange freeze
        limit via `OptionUtils.split_order_quantities()` before being sent
        to the broker. Previously there was no splitting on the sell side,
        meaning a single large position would result in one oversized sell
        order that the exchange would reject.

        For paper orders (`broker_id` is None) the full quantity is passed
        through without splitting — the broker is never called in that case.
        """
        try:
            state = state_manager.get_state()
            if state is None:
                return False

            if state.current_position not in {BaseEnums.CALL, BaseEnums.PUT}:
                logger.warning(f"[EXIT] Not in CALL or PUT. Current: {state.current_position}")
                return False
            if state.order_pending:
                logger.warning("[EXIT] Order already pending")
                return False

            state.order_pending = True
            sell_price = state.current_price
            if sell_price is None:
                state.order_pending = False
                return False

            exit_reason = reason or state.reason_to_exit
            orders = state.orders
            db = get_db()
            total_pnl = 0.0
            total_qty = 0
            failed_orders = []  # track orders whose broker sell failed

            # FIX: Use state's trading mode instead of global BaseEnums.BOT_TYPE
            is_paper = False
            if safe_hasattr(state, 'is_paper_mode'):
                is_paper = state.is_paper_mode
            elif safe_hasattr(state, 'trading_mode'):
                is_paper = state.trading_mode != BaseEnums.LIVE

            is_live = not is_paper

            for order in orders:
                try:
                    if not isinstance(order, dict):
                        continue
                    order_id = order.get("id")
                    symbol = order.get("symbol")
                    qty = order.get("qty", 0)
                    broker_id = order.get("broker_id")

                    broker_sell_ok = True
                    if is_live and self.api and broker_id:
                        sell_chunks = OptionUtils.split_order_quantities(
                            state.derivative, qty
                        )
                        logger.info(
                            f"[EXIT] {symbol}: selling {qty} shares in "
                            f"{len(sell_chunks)} order(s) {sell_chunks}"
                        )
                        for chunk_qty in sell_chunks:
                            try:
                                self.api.sell_at_current(symbol=symbol, qty=chunk_qty)
                            except Exception as e:
                                logger.error(
                                    f"[EXIT] Broker sell failed for order {order_id} "
                                    f"chunk qty={chunk_qty} (broker_id={broker_id}): {e}",
                                    exc_info=True,
                                )
                                broker_sell_ok = False
                                break  # stop sending further chunks for this order

                    if not broker_sell_ok:
                        # Do NOT close this order in the DB — position is still open
                        # with the broker. Caller must retry.
                        failed_orders.append(order)
                        continue

                    # Attempt to get the actual broker fill price; fall back to
                    # the last tick price only when the API does not return one.
                    actual_exit_price = sell_price
                    if is_live and self.api and broker_id:
                        try:
                            fill = self.api.get_fill_price(broker_id)
                            if fill and fill > 0:
                                actual_exit_price = fill
                                logger.debug(
                                    f"[EXIT] Using broker fill price {fill:.2f} "
                                    f"(tick was {sell_price:.2f})"
                                )
                        except Exception:
                            pass  # API doesn't support fill price query — use tick price

                    pnl = (actual_exit_price - order.get("price", 0.0)) * qty
                    total_pnl += pnl
                    total_qty += qty

                    if order_id:
                        orders_crud.close_order(
                            order_id=order_id,
                            exit_price=actual_exit_price,
                            pnl=pnl,
                            reason=exit_reason,
                            db=db,
                        )
                except Exception as e:
                    logger.error(f"[EXIT] Order processing error: {e}", exc_info=True)

            # If any broker sell failed, keep the position open and return False
            # so the caller can retry rather than silently believing the exit succeeded.
            if failed_orders:
                logger.error(
                    f"[EXIT] {len(failed_orders)} order(s) failed to sell with broker. "
                    "Position NOT fully closed. Retaining state for retry."
                )
                # Update orders list to only the ones that failed so retry attempts
                # know exactly which positions are still open.
                state.orders = failed_orders
                state.order_pending = False
                return False

            logger.info(f"[EXIT] Completed exit for {state.current_position}. Reason: {exit_reason}")
            state.previous_position = state.current_position

            if self.notifier and state.current_buy_price:
                try:
                    self.notifier.notify_exit(
                        symbol=state.current_trading_symbol,
                        direction=state.current_position,
                        entry_price=state.current_buy_price,
                        exit_price=sell_price,
                        pnl=total_pnl,
                        reason=exit_reason or 'Signal',
                    )
                except Exception as e:
                    logger.error(f"[EXIT] Telegram notify failed: {e}", exc_info=True)

            if self.on_trade_closed_callback and total_qty > 0:
                try:
                    self.on_trade_closed_callback(total_pnl, total_pnl > 0)
                except Exception as e:
                    logger.error(f"[EXIT] Trade closed callback failed: {e}", exc_info=True)

            if is_live and self.api:
                try:
                    state.account_balance = self.api.get_balance(state.capital_reserve)
                except Exception as e:
                    logger.error(f"[EXIT] Balance update failed: {e}", exc_info=True)

            state.orders = []
            state.confirmed_orders = []
            state.reset_trade_attributes(current_position=state.previous_position)
            state.order_pending = False

            # Invalidate risk manager cache so the next should_allow_trade() call
            # immediately re-queries the DB for updated daily PnL and trade count.
            if self.risk_manager:
                try:
                    self.risk_manager.invalidate_cache()
                except Exception as e:
                    logger.warning(f"[EXIT] Risk manager cache invalidation failed: {e}")

            return True

        except Exception as e:
            logger.exception(f"[EXIT] Exception: {e}")
            state = state_manager.get_state()
            if state:
                state.order_pending = False
            return False
    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def confirm_order(self, order_id: int, broker_order_id: str = None) -> bool:
        try:
            return orders_crud.confirm(order_id, broker_order_id, get_db())
        except Exception as e:
            logger.error(f"[confirm_order] {e}", exc_info=True)
            return False

    def cancel_order(self, order_id: int, reason: str = None) -> bool:
        """
        Cancel a single order by DB id — broker cancel + DB update.

        No freeze-size change needed here: this method cancels an already-
        placed order by its ID, not a quantity. Each child order created by
        place_orders already has its own DB row and broker_order_id, so
        _cancel_unconfirmed_orders calls this correctly per-chunk.
        """
        try:
            db = get_db()
            order = orders_crud.get(order_id, db)
            if order and order.get("broker_order_id") and self.api:
                try:
                    self.api.cancel_order(order_id=order["broker_order_id"])
                except Exception as e:
                    logger.error(f"Broker cancel failed: {e}", exc_info=True)
            return orders_crud.cancel(order_id, reason, db)
        except Exception as e:
            logger.error(f"[cancel_order] {e}", exc_info=True)
            return False

    def update_stop_loss(self, order_id: int, stop_loss: float) -> bool:
        try:
            return orders_crud.update_stop_loss(order_id, stop_loss, get_db())
        except Exception as e:
            logger.error(f"[update_stop_loss] {e}", exc_info=True)
            return False

    def get_open_orders(self, session_id: int = None) -> List[Dict]:
        try:
            return orders_crud.list_open(session_id, get_db())
        except Exception as e:
            logger.error(f"[get_open_orders] {e}", exc_info=True)
            return []

    def get_order(self, order_id: int) -> Optional[Dict]:
        try:
            return orders_crud.get(order_id, get_db())
        except Exception as e:
            logger.error(f"[get_order] {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Cost calc
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_total_transaction_cost(quantity, buy_price, sell_price, broker_fee=20):
        try:
            if quantity <= 0 or buy_price <= 0 or sell_price <= 0:
                return 0.0
            buy_t = quantity * buy_price
            sell_t = quantity * sell_price
            b = broker_fee
            xch, sebi, stamp, stt, gst = 0.000495, 0.000001, 0.00003, 0.0001250, 0.18
            buy_tax = b + buy_t * (xch + sebi)
            buy_total = buy_tax + buy_tax * gst + buy_t * stamp
            sell_tax = b + sell_t * (xch + sebi)
            sell_total = sell_tax + sell_tax * gst + sell_t * stt
            return Utils.round_off(buy_total + sell_total)
        except Exception as e:
            logger.exception(f"Error calculating transaction cost: {e}")
            return 0.0

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        try:
            logger.info("[OrderExecutor] Starting cleanup")
            if self._order_lock and self._order_lock.locked():
                try:
                    self._order_lock.release()
                except Exception:
                    pass
            self.api = None
            self.config = None
            self.notifier = None
            self.risk_manager = None
            self.on_trade_closed_callback = None
            logger.info("[OrderExecutor] Cleanup completed")
        except Exception as e:
            logger.error(f"[OrderExecutor.cleanup] Error: {e}", exc_info=True)