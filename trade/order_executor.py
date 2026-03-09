"""
order_executor.py
=================
Database-backed order executor with thread safety and idempotent order submission.

FIXED: Added proper locking, idempotency keys, and order state machine.
"""

import logging.handlers
import random
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Set
from enum import Enum, auto

import BaseEnums
from Utils.OptionUtils import OptionUtils
from Utils.Utils import Utils
from Utils.safe_getattr import safe_getattr, safe_hasattr
from db.connector import get_db
from db.crud import orders as orders_crud

# Import state manager for state access
from data.trade_state_manager import state_manager
from data.candle_store_manager import candle_store_manager

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order state machine states."""
    PENDING = auto()      # Created but not submitted
    SUBMITTED = auto()    # Submitted to broker
    PARTIAL = auto()      # Partially filled
    FILLED = auto()       # Fully filled
    CANCELLED = auto()    # Cancelled
    REJECTED = auto()     # Rejected by broker


class Order:
    """Order model with state machine."""

    def __init__(self, order_id: str, symbol: str, quantity: int, order_type: str,
                 price: Optional[float] = None, stop_price: Optional[float] = None):
        self.id = order_id
        self.symbol = symbol
        self.quantity = quantity
        self.filled_quantity = 0
        self.order_type = order_type
        self.price = price
        self.stop_price = stop_price
        self.status = OrderStatus.PENDING
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.broker_order_id: Optional[str] = None
        self.fills: list = []
        self.error: Optional[str] = None

    def submit(self, broker_order_id: str) -> bool:
        """Transition from PENDING to SUBMITTED."""
        if self.status != OrderStatus.PENDING:
            logger.warning(f"Cannot submit order {self.id} in state {self.status}")
            return False
        self.status = OrderStatus.SUBMITTED
        self.broker_order_id = broker_order_id
        self.updated_at = datetime.now()
        return True

    def fill(self, quantity: int, price: float) -> bool:
        """Process a fill (partial or full)."""
        if self.status not in [OrderStatus.SUBMITTED, OrderStatus.PARTIAL]:
            logger.warning(f"Cannot fill order {self.id} in state {self.status}")
            return False

        self.filled_quantity += quantity
        self.fills.append({
            'quantity': quantity,
            'price': price,
            'time': datetime.now()
        })

        if self.filled_quantity >= self.quantity:
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PARTIAL

        self.updated_at = datetime.now()
        return True

    def cancel(self) -> bool:
        """Cancel the order."""
        if self.status not in [OrderStatus.SUBMITTED, OrderStatus.PARTIAL, OrderStatus.PENDING]:
            logger.warning(f"Cannot cancel order {self.id} in state {self.status}")
            return False
        self.status = OrderStatus.CANCELLED
        self.updated_at = datetime.now()
        return True

    def reject(self, reason: str) -> bool:
        """Reject the order."""
        if self.status != OrderStatus.SUBMITTED:
            logger.warning(f"Cannot reject order {self.id} in state {self.status}")
            return False
        self.status = OrderStatus.REJECTED
        self.error = reason
        self.updated_at = datetime.now()
        return True

    @property
    def is_active(self) -> bool:
        """Check if order is still active (not terminal)."""
        return self.status in [OrderStatus.SUBMITTED, OrderStatus.PARTIAL]

    @property
    def is_terminal(self) -> bool:
        """Check if order is in terminal state."""
        return self.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]

    @property
    def average_fill_price(self) -> Optional[float]:
        """Calculate average fill price."""
        if not self.fills:
            return None
        total_value = sum(f['quantity'] * f['price'] for f in self.fills)
        return total_value / self.filled_quantity if self.filled_quantity > 0 else None


class OrderExecutor:
    """Database-backed order executor — places, confirms, cancels, and closes orders."""

    def __init__(self, broker_api, config):
        self._safe_defaults_init()
        try:
            self.api = broker_api
            self.config = config
            self._order_lock = threading.RLock()  # Reentrant for nested calls
            self.notifier = None
            self.risk_manager = None
            self.on_trade_closed_callback = None

            # FIX: Idempotency tracking
            self._submitted_order_ids: Set[str] = set()
            self._idempotency_keys: Dict[str, str] = {}  # idempotency_key -> order_id

            logger.info("OrderExecutor initialized with thread safety and idempotency")
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
        self._submitted_order_ids = set()
        self._idempotency_keys = {}

    # ------------------------------------------------------------------
    # Mode helper
    # ------------------------------------------------------------------

    def _is_paper_mode(self) -> bool:
        """
        Single source of truth for paper/live mode inside OrderExecutor.

        Reads state.is_paper_mode which is set by TradingApp._apply_trading_mode_to_executor()
        via state.trading_mode = mode_str.  Defaults to True (PAPER) on any error
        so we never accidentally send live orders in an unknown state.
        """
        try:
            state = state_manager.get_state()
            if state is None:
                logger.warning("[OrderExecutor._is_paper_mode] state is None — defaulting to PAPER")
                return True
            if safe_hasattr(state, 'is_paper_mode'):
                return bool(state.is_paper_mode)
            # Legacy fallback: compare trading_mode string
            if safe_hasattr(state, 'trading_mode'):
                return state.trading_mode != BaseEnums.LIVE
            logger.warning("[OrderExecutor._is_paper_mode] state has no mode attrs — defaulting to PAPER")
            return True
        except Exception as e:
            logger.error(f"[OrderExecutor._is_paper_mode] {e} — defaulting to PAPER")
            return True  # fail-safe: never go live on error

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def buy_option(self, option_type):
        """
        Thread-safe buy option with proper locking.

        Args:
            option_type: BaseEnums.CALL or BaseEnums.PUT
        """
        with self._order_lock:
            return self._buy_option_locked(option_type)

    def _buy_option_locked(self, option_type):
        """
        Actual implementation - called with lock held.
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
                allowed, reason = self.risk_manager.should_allow_trade()
                if not allowed:
                    logger.warning(f"[RiskManager] Trade blocked: {reason}")
                    return False

            if state.current_position is not None:
                logger.info("[BUY] Position already open.")
                return False

            if state.order_pending:
                logger.warning("Order already pending")
                return False

            # Claim the pending slot
            state.order_pending = True

            try:
                option_name = (
                    state.call_option if option_type == BaseEnums.CALL
                    else state.put_option
                )

                if not option_name:
                    logger.error(
                        f"[BUY] option_name is None for {option_type}. "
                        "Option chain may not be loaded yet."
                    )
                    return False

                market_price = (
                    state.call_current_close if option_type == BaseEnums.CALL
                    else state.put_current_close
                )

                if market_price is None:
                    market_price = self._fetch_live_price(option_name)
                    if market_price is None:
                        logger.error(f"Failed to fetch live price for {option_name}")
                        return False

                # ── Lot size resolution ────────────────────────────────────────
                lot_size = OptionUtils.get_lot_size(
                    state.derivative, fallback=state.lot_size
                )

                if lot_size <= 0:
                    logger.error(
                        f"[BUY] Could not determine lot size for "
                        f"'{state.derivative}' (fallback={state.lot_size}). "
                        f"Aborting order to prevent zero-quantity trade."
                    )
                    return False

                try:
                    shares = Utils.calculate_shares_to_buy(
                        price=market_price,
                        balance=state.account_balance,
                        lot_size=lot_size,
                    )
                except Exception as e:
                    logger.error(f"Failed to calculate shares: {e}", exc_info=True)
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
                        return False

                if shares < lot_size:
                    logger.warning("Insufficient balance even after adjusting positions.")
                    return False

                success = self._smart_order_execution(
                    state, option_type, option_name, shares, market_price
                )
                if success:
                    logger.info(f"{option_type} position entered successfully.")
                return success

            finally:
                # Always clear pending flag
                state.order_pending = False

        except Exception as e:
            logger.exception(f"Exception in buy_option: {e}")
            return False

    def _fetch_live_price(self, option_name: Optional[str]) -> Optional[float]:
        """
        Return the current price for *option_name*.

        Source priority (CandleStore is always the primary source):
        1. candle_store_manager.get_current_price() — populated by WS ticks
           via push_tick().  Zero broker API calls, always consistent with
           what the signal engine and SL/TP logic see.
        2. broker REST API (get_option_current_price) — used only when the
           CandleStore has no price yet (symbol just subscribed, store cold
           at startup).  The returned price is also pushed into the store so
           subsequent calls hit path 1 instead.
        """
        if not option_name:
            return None

        # ── Path 1: CandleStore (preferred) ──────────────────────────────────
        try:
            price = candle_store_manager.get_current_price(option_name)
            if price is not None and price > 0:
                logger.debug(f"[_fetch_live_price] {option_name}: {price:.2f} (CandleStore)")
                return price
        except Exception as e:
            logger.debug(f"[_fetch_live_price] CandleStore lookup failed for {option_name}: {e}")

        # ── Path 2: Broker REST fallback ──────────────────────────────────────
        if not self.api:
            logger.warning(f"[_fetch_live_price] No price in CandleStore and no api for {option_name}")
            return None
        try:
            price = self.api.get_option_current_price(option_name)
            if price is not None and price > 0:
                logger.debug(
                    f"[_fetch_live_price] {option_name}: {price:.2f} "
                    f"(broker REST fallback — CandleStore was empty)"
                )
                # Seed the store so future calls use path 1
                try:
                    candle_store_manager.push_tick(option_name, price)
                except Exception:
                    pass
                return price
        except Exception as e:
            logger.error(f"[_fetch_live_price] Broker REST also failed for {option_name}: {e}", exc_info=True)

        return None

    # ------------------------------------------------------------------
    # Smart order execution (Feature 2)
    # ------------------------------------------------------------------

    def _smart_order_execution(self, state, option_type, option_name, shares, market_price):
        try:
            mid_price = self._calculate_mid_price(state, option_name, market_price)

            logger.info(f"[ORDER] Attempt 1/3: LIMIT at mid-price Rs{mid_price:.2f}")
            orders = self.place_orders(option_name, shares, mid_price, state, option_type=option_type)
            if not orders:
                return False

            if self._wait_for_fill(orders, state, timeout_seconds=3):
                fill_price = state.current_buy_price or mid_price
                self.record_trade_state(state, option_type, option_name, fill_price, shares, orders)
                slippage = fill_price - mid_price
                logger.info(f'[FILL] Mid-price fill. Slippage: Rs{slippage:+.2f}')
                state.last_slippage = slippage
                self._notify_entry(state, option_type, option_name)
                return True

            logger.warning("[ORDER] Attempt 1 failed. Retrying at LTP.")
            self._cancel_unconfirmed_orders(orders, state)
            ltp_price = Utils.round_to_nse_price(market_price)
            logger.info(f"[ORDER] Attempt 2/3: LIMIT at LTP Rs{ltp_price:.2f}")
            orders = self.place_orders(option_name, shares, ltp_price, state, option_type=option_type)
            if not orders:
                return False

            if self._wait_for_fill(orders, state, timeout_seconds=3):
                fill_price = state.current_buy_price or ltp_price
                self.record_trade_state(state, option_type, option_name, fill_price, shares, orders)
                slippage = fill_price - mid_price
                logger.info(f'[FILL] LTP retry fill. Slippage: Rs{slippage:+.2f}')
                state.last_slippage = slippage
                self._notify_entry(state, option_type, option_name)
                return True

            logger.warning("[ORDER] Attempt 2 failed. Trying MARKET order.")
            self._cancel_unconfirmed_orders(orders, state)

            is_live = not self._is_paper_mode()

            if is_live and self.api:
                logger.info(f"[ORDER] Attempt 3/3: MARKET order for {shares} shares")
                try:
                    side_buy = safe_getattr(self.api, 'SIDE_BUY', 1)
                    mkt_type = safe_getattr(self.api, 'MARKET_ORDER_TYPE', 2)
                    broker_id = self.api.place_order(
                        symbol=option_name, qty=shares, side=side_buy, order_type=mkt_type
                    )
                    if broker_id:
                        session_id = safe_getattr(state, 'session_id', None)
                        position_type = str(option_type) if option_type else "UNKNOWN"
                        oid = 0
                        try:
                            from db.connector import get_db
                            from db.crud import orders as orders_crud
                            oid = orders_crud.create(
                                session_id=session_id,
                                symbol=option_name,
                                position_type=position_type,
                                quantity=shares,
                                broker_order_id=broker_id,
                                entry_price=ltp_price,
                                stop_loss=state.stop_loss,
                                take_profit=state.tp_point,
                                db=get_db(),
                            )
                        except Exception as db_err:
                            logger.error(f"[ORDER] MARKET order DB record failed: {db_err}", exc_info=True)

                        mkt_orders = [{'id': oid, 'broker_id': broker_id,
                                       'qty': shares, 'symbol': option_name, 'price': ltp_price}]
                        self.record_trade_state(
                            state, option_type, option_name, ltp_price, shares, mkt_orders
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
        if not orders:
            return False

        live_orders = [o for o in orders if o.get('broker_id')]
        if not live_orders:
            if not state.current_buy_price:
                state.current_buy_price = orders[0].get('price')
            return True

        if not self.api:
            return False

        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                all_filled = all(
                    self.api.get_current_order_status(o.get('broker_id')) == 2
                    for o in live_orders
                )
                if all_filled:
                    if not state.current_buy_price:
                        state.current_buy_price = live_orders[0].get('price')
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
    # Order placement with idempotency
    # ------------------------------------------------------------------

    def place_order_with_idempotency(self, symbol: str, quantity: int, price: float,
                                     idempotency_key: str, state, option_type=None) -> Optional[str]:
        """
        Place order with idempotency key to prevent duplicates.
        """
        # Check if we've already processed this key
        if idempotency_key in self._idempotency_keys:
            existing_order_id = self._idempotency_keys[idempotency_key]
            logger.info(f"Duplicate submission detected for key {idempotency_key}, returning {existing_order_id}")
            return existing_order_id

        # Generate a unique client order ID
        client_order_id = f"ORD_{int(time.time()*1000)}_{random.randint(1000, 9999)}"
        try:
            broker_order_id = self.api.place_order(
                symbol=symbol,
                qty=quantity,
                limitPrice=price,
                client_order_id=client_order_id  # Pass to broker if supported
            )

            if broker_order_id:
                # Store mapping — caller uses this to write the single DB record
                self._idempotency_keys[idempotency_key] = broker_order_id
                self._submitted_order_ids.add(broker_order_id)
                return broker_order_id

        except Exception as e:
            logger.error(f"Order submission failed: {e}", exc_info=True)
            return None

    def place_orders(self, symbol: str, shares: int, price: float, state,
                     option_type=None) -> List[Dict]:
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
            position_type = str(option_type) if option_type else (state.current_position or "UNKNOWN")

            # Check if we're in paper mode (reads state.is_paper_mode set by TradingApp)
            is_live = not self._is_paper_mode()

            if is_live and self.api:
                chunks = OptionUtils.split_order_quantities(state.derivative, shares)

                logger.info(
                    f"[place_orders] {symbol}: {shares} shares split into "
                    f"{len(chunks)} order(s) {chunks} "
                    f"(freeze limit: {OptionUtils.get_freeze_size(state.derivative)})"
                )

                for i, qty in enumerate(chunks, start=1):
                    idempotency_key = f"{symbol}_{qty}_{price}_{i}_{int(time.time()*1000)}"

                    try:
                        # Use idempotent order placement
                        broker_id = self.place_order_with_idempotency(
                            symbol=symbol,
                            quantity=qty,
                            price=price,
                            idempotency_key=idempotency_key,
                            state=state,
                            option_type=option_type
                        )

                        if broker_id:
                            oid = orders_crud.create(
                                session_id=session_id,
                                symbol=symbol,
                                position_type=position_type,
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
                        position_type=position_type,
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
        Step further OTM (cheaper strikes) until balance is sufficient for one lot.

        Each iteration increments the lookback by 1 strike.  The same
        ``broker.build_option_symbol(lookback_strikes=N)`` call used in
        ``subscribe_market_data()`` is used here so the strike-count semantics
        are identical throughout:

            lookback_strikes = 0   → ATM
            lookback_strikes = 1   → one strike OTM
            lookback_strikes = 2   → two strikes OTM  … etc.

        The broker translates the count to the correct price offset using its
        own multiplier (50 pts for NIFTY, 100 pts for BANKNIFTY, etc.).

        ``state.call_lookback`` / ``state.put_lookback`` are updated in place so
        the caller can read back the final adjusted symbol.
        """
        try:
            state = state_manager.get_state()
            if state is None:
                return shares or 0

            lot_size = OptionUtils.get_lot_size(
                state.derivative, fallback=state.lot_size
            )

            for attempt in range(10):
                try:
                    if shares >= lot_size:
                        break

                    if side == BaseEnums.CALL:
                        state.call_lookback = state.call_lookback + 1
                        new_symbol = self.api.build_option_symbol(
                            underlying=state.derivative,
                            spot_price=state.derivative_current_price,
                            option_type="CE",
                            weeks_offset=state.expiry,
                            lookback_strikes=state.call_lookback,
                        ) if self.api else None
                        if new_symbol:
                            state.call_option = new_symbol
                        option_name = state.call_option
                    else:
                        # Move one strike further OTM for puts
                        state.put_lookback = state.put_lookback + 1
                        new_symbol = self.api.build_option_symbol(
                            underlying=state.derivative,
                            spot_price=state.derivative_current_price,
                            option_type="PE",
                            weeks_offset=state.expiry,
                            lookback_strikes=state.put_lookback,
                        ) if self.api else None
                        if new_symbol:
                            state.put_option = new_symbol
                        option_name = state.put_option

                    if not option_name:
                        logger.warning(f"[ADJUST] Attempt {attempt+1}: no symbol built, skipping")
                        continue

                    price = self._fetch_live_price(option_name)
                    if price is None:
                        logger.warning(f"[ADJUST] Attempt {attempt+1}: no price for {option_name}")
                        continue

                    shares = Utils.calculate_shares_to_buy(
                        price=price,
                        balance=state.account_balance,
                        lot_size=lot_size,
                    )
                    logger.info(
                        f"[ADJUST] Attempt {attempt+1}: {option_name} "
                        f"@ {price:.2f}, shares={shares}, lot={lot_size}"
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
        Thread-safe exit with proper locking.
        """
        with self._order_lock:
            return self._exit_position_locked(reason)

    def _exit_position_locked(self, reason=None):
        """
        Actual implementation - called with lock held.
        """
        state = state_manager.get_state()
        if state is None:
            return False

        if state.current_position not in {BaseEnums.CALL, BaseEnums.PUT}:
            logger.warning(f"[EXIT] Not in CALL or PUT. Current: {state.current_position}")
            return False
        if state.order_pending:
            logger.warning("[EXIT] Order already pending")
            return False

        # BUG 3 FIX: set pending flag before the try block so the finally
        # clause is always responsible for clearing it.
        state.order_pending = True
        _exit_succeeded = False

        try:
            sell_price = state.current_price
            if sell_price is None:
                return False

            exit_reason = reason or state.reason_to_exit
            orders = state.orders
            db = get_db()
            total_pnl = 0.0
            total_qty = 0
            failed_orders = []  # track orders whose broker sell failed

            # Use single source of truth for mode (reads state.is_paper_mode)
            is_live = not self._is_paper_mode()

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
                return False

            logger.info(f"[EXIT] Completed exit for {state.current_position}. Reason: {exit_reason}")

            # BUG 2 FIX: Capture the closing position BEFORE reset_trade_attributes
            closed_position = state.current_position

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
            # BUG 2 FIX: pass the captured position directly
            state.reset_trade_attributes(current_position=closed_position)

            # Invalidate risk manager cache so the next should_allow_trade() call
            # immediately re-queries the DB for updated daily PnL and trade count.
            if self.risk_manager:
                try:
                    self.risk_manager.invalidate_cache()
                except Exception as e:
                    logger.warning(f"[EXIT] Risk manager cache invalidation failed: {e}")

            _exit_succeeded = True
            return True

        except Exception as e:
            logger.exception(f"[EXIT] Exception: {e}")
            return False

        finally:
            try:
                state.order_pending = False
            except Exception as e:
                logger.error(f"[EXIT] Failed to clear order_pending in finally: {e}", exc_info=True)

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
        """
        try:
            db = get_db()
            order = orders_crud.get(order_id, db)
            if order and order.get("broker_order_id") and self.api:
                try:
                    # FIX: Pass broker_order_id, not order_id
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
            self.api = None
            self.config = None
            self.notifier = None
            self.risk_manager = None
            self.on_trade_closed_callback = None
            self._submitted_order_ids.clear()
            self._idempotency_keys.clear()
            logger.info("[OrderExecutor] Cleanup completed")
        except Exception as e:
            logger.error(f"[OrderExecutor.cleanup] Error: {e}", exc_info=True)