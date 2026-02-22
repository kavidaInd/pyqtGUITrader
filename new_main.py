#!/usr/bin/env python3
"""
Main trading application with support for LIVE, PAPER, and BACKTEST modes.
"""
import concurrent.futures
import logging
import threading
from typing import Optional, Any, Dict

import BaseEnums
from Utils.OptionUtils import OptionUtils
from Utils.Utils import Utils
from broker.Broker import Broker, TokenExpiredError
from data.websocket_manager import WebSocketManager
from gui.DailyTradeSetting import DailyTradeSetting
from gui.ProfitStoplossSetting import ProfitStoplossSetting
from models.trade_state import TradeState
from strategy.dynamic_signal_engine import DynamicSignalEngine
from strategy.strategy_manager import StrategyManager
from strategy.trend_detector import TrendDetector
from trade.order_executor import OrderExecutor
from trade.position_monitor import PositionMonitor

logger = logging.getLogger(__name__)


def safe_last(val):
    """Return last element if val is list/tuple and not empty, else just val or None."""
    if isinstance(val, (list, tuple)) and val:
        return val[-1]
    return val


class TradingApp:
    def __init__(self, config: Any, trading_mode_var: Optional[Any] = None, broker_setting: Optional[Any] = None):

        self.state = TradeState()
        self.config = config
        self.broker = Broker(state=self.state, broker_setting=broker_setting)
        self.trade_config = DailyTradeSetting()
        self.profit_loss_config = ProfitStoplossSetting()
        self.state.cancel_pending_trade = self.cancel_pending_trade
        self.strategy_manager = StrategyManager()
        self.signal_engine = self._create_signal_engine()
        self.detector = TrendDetector(config=self.config, signal_engine=self.signal_engine)
        self.executor = OrderExecutor(broker_api=self.broker, config=self.config)
        self.monitor = PositionMonitor()
        self.ws = WebSocketManager(
            token=self.state.token,
            client_id=getattr(broker_setting, "client_id", "") if broker_setting else "",
            on_message_callback=self.on_message
        )

        # Thread pool for non-blocking operations
        self._fetch_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="TradingApp"
        )

        # Events for tracking async operations
        self._history_fetch_in_progress = threading.Event()
        self._processing_in_progress = threading.Event()

        # Option chain: stores live tick data for all subscribed options
        self._option_chain_lock = threading.Lock()
        self.state.option_chain: Dict[str, Dict[str, Optional[float]]] = {}

        # Number of ITM and OTM strikes to subscribe on each side of ATM
        self._chain_itm = 5
        self._chain_otm = 5

        # Ensure confirmed_orders is always a list
        if not hasattr(self.state, "confirmed_orders"):
            self.state.confirmed_orders = []

        # logger.info("🚀 TradingApp initialized with dynamic signal engine")

    def _create_signal_engine(self) -> DynamicSignalEngine:
        """Create signal engine with active strategy config"""
        engine = DynamicSignalEngine()
        active_config = self.strategy_manager.get_active_engine_config()
        if active_config:
            engine.from_dict(active_config)
            # logger.info(f"Loaded signal engine config from active strategy: {self.strategy_manager.get_active_name()}")
        return engine

    def reload_signal_engine(self):
        """Reload signal engine from active strategy (called when strategy changes)"""
        new_config = self.strategy_manager.get_active_engine_config()
        if new_config and self.signal_engine:
            self.signal_engine.from_dict(new_config)
            # Update trend detector's signal engine
            if hasattr(self.detector, 'set_signal_engine'):
                self.detector.set_signal_engine(self.signal_engine)
            # logger.info(f"Signal engine reloaded with strategy: {self.strategy_manager.get_active_name()}")

    def run(self) -> None:
        # logger.info("Starting trading app with dynamic signals...")
        try:
            self.initialize_market_state()
            self.subscribe_market_data()
        except Exception as e:
            logger.critical(f"Unhandled exception during run: {e!r}", exc_info=True)

    def initialize_market_state(self) -> None:
        try:
            self.apply_settings_to_state()

            # Get initial price for derivative
            if hasattr(self.broker, 'get_option_current_price'):
                self.state.derivative_current_price = self.broker.get_option_current_price(self.state.derivative)
                # logger.info(f"Initial price for {self.state.derivative}: {self.state.derivative_current_price}")
            else:
                logger.warning("Broker doesn't support get_option_current_price")

        except Exception as price_error:
            logger.error(f"Failed to get initial price: {price_error!r}", exc_info=True)

    def subscribe_market_data(self) -> None:
        try:
            if self.state.derivative_current_price is not None:
                spot = self.state.derivative_current_price
                expiry = self.state.expiry
                derivative = self.state.derivative

                # ATM options (used for trade execution & history)
                self.state.put_option = OptionUtils.get_option_at_price(
                    spot, op_type="PE", expiry=expiry,
                    lookback=self.state.put_lookback,
                    derivative_name=derivative)

                self.state.call_option = OptionUtils.get_option_at_price(
                    spot, op_type="CE", expiry=expiry,
                    lookback=self.state.call_lookback,
                    derivative_name=derivative)

                # Build option chain: _chain_itm ITM + ATM + _chain_otm OTM on each side
                call_chain = OptionUtils.get_all_option(
                    expiry=expiry, symbol=derivative, strike=spot,
                    itm=self._chain_itm, otm=self._chain_otm, putorcall="CE")

                put_chain = OptionUtils.get_all_option(
                    expiry=expiry, symbol=derivative, strike=spot,
                    itm=self._chain_itm, otm=self._chain_otm, putorcall="PE")

                # Initialize chain storage with zero-state entries
                with self._option_chain_lock:
                    new_chain: Dict[str, Dict[str, Optional[float]]] = {}
                    for sym in call_chain + put_chain:
                        full_sym = self.symbol_full(sym)
                        if full_sym:
                            new_chain[full_sym] = self.state.option_chain.get(
                                full_sym, {"ltp": None, "ask": None, "bid": None}
                            )
                    self.state.option_chain = new_chain

                logger.info(
                    f"[subscribe_market_data] Chain built: {len(call_chain)} CE + {len(put_chain)} PE "
                    f"| ATM CE: {self.state.call_option} | ATM PE: {self.state.put_option}"
                )

            # Compose full symbol list: derivative + all chain symbols
            chain_symbols = list(self.state.option_chain.keys())
            self.state.all_symbols = list(filter(None, [
                self.symbol_full(self.state.derivative),
                *chain_symbols
            ]))

            self.ws.symbols = self.state.all_symbols
            self.ws.connect()

        except Exception as ws_error:
            logger.error(f"WebSocket connection/subscription failed: {ws_error!r}", exc_info=True)

    def on_message(self, message: dict) -> None:
        """
        Two-stage message processing:
        Stage 1 (fast): Update market state immediately on WS thread
        Stage 2 (slow): Submit remaining processing to thread pool
        """
        try:
            if not (message and isinstance(message, dict) and message.get("symbol")):
                logger.warning(f"Malformed or empty message received: {message}")
                return

            symbol = message.get("symbol")
            ltp = message.get("ltp")
            ask_price = message.get("ask_price")
            bid_price = message.get("bid_price")

            if ltp is None:
                logger.warning(f"LTP missing for symbol {symbol}. Message: {message}")
                return

            # Stage 1: Fast update - write LTP to state immediately
            self.update_market_state(symbol, ltp, ask_price, bid_price)

            # Stage 2: Slow processing - submit to thread pool if not already processing
            if not self._processing_in_progress.is_set():
                self._processing_in_progress.set()
                self._fetch_executor.submit(self._process_message_stage2)

        except Exception as e:
            logger.error(f"Exception in on_message stage 1: {e!r}, Message: {message}", exc_info=True)

    def _process_message_stage2(self) -> None:
        """
        Stage 2 message processing - runs in thread pool.
        Contains all slower operations that shouldn't block the WebSocket thread.
        """
        try:
            # Run all monitoring and decision logic
            if hasattr(self, 'monitor') and self.monitor:
                self.monitor.update_trailing_sl_tp(self.broker, self.state)

            self.evaluate_trend_and_decision()
            self.monitor_active_trade_status()
            self.monitor_profit_loss_status()

        except TokenExpiredError:
            logger.critical("Token expired in stage 2 processing")
            raise
        except Exception as e:
            logger.error(f"Exception in message stage 2 processing: {e!r}", exc_info=True)
        finally:
            self._processing_in_progress.clear()

    def update_market_state(self, symbol: str, ltp: float, ask_price: float, bid_price: float) -> None:
        if symbol == self.symbol_full(self.state.derivative):
            self.state.derivative_current_price = ltp
            return

        # --- Option chain tick ---
        with self._option_chain_lock:
            if symbol in self.state.option_chain:
                self.state.option_chain[symbol] = {
                    "ltp": ltp,
                    "ask": ask_price,
                    "bid": bid_price,
                }

        # --- ATM option convenience state ---
        use_ask = bool(self.state.current_position)

        atm_put_sym = self.symbol_full(self.state.put_option)
        atm_call_sym = self.symbol_full(self.state.call_option)

        if symbol == atm_put_sym:
            self.state.put_current_close = ask_price if use_ask else bid_price
        elif symbol == atm_call_sym:
            self.state.call_current_close = ask_price if use_ask else bid_price

        # Update current_price for open position P&L tracking
        if self.state.current_position:
            cp = self.state.current_position
            self.state.current_price = self.state.call_current_close \
                if cp == BaseEnums.CALL else self.state.put_current_close

    def evaluate_trend_and_decision(self) -> None:
        try:
            if not Utils.is_history_updated(last_updated=self.state.last_index_updated, interval=self.state.interval):
                if not self._history_fetch_in_progress.is_set():
                    self._history_fetch_in_progress.set()
                    self._fetch_executor.submit(self._fetch_history_and_detect)

            self.state.trend = self.determine_trend_from_signals()

            # Execute based on trend (only for algo trading)
            if hasattr(self, 'executor') and self.executor:
                self.execute_based_on_trend()

        except Exception as trend_error:
            logger.info(f"Trend detection or decision logic error: {trend_error!r}", exc_info=True)

    def _fetch_history_and_detect(self) -> None:
        """Runs on thread pool — fetches history and updates trend state."""
        try:
            # Fetch derivative history
            if hasattr(self.broker, 'get_history'):
                self.state.derivative_history_df = self.broker.get_history(
                    symbol=self.state.derivative, interval=self.state.interval)

                self.state.current_call_data = self.broker.get_history(
                    symbol=self.state.call_option, interval=self.state.interval)

                self.state.current_put_data = self.broker.get_history(
                    symbol=self.state.put_option, interval=self.state.interval)

                if self.state.derivative_history_df is not None and \
                        not self.state.derivative_history_df.empty:

                    self.state.last_index_updated = \
                        self.state.derivative_history_df["Time"].iloc[-1]

                    # Run trend detection with signal engine
                    self.state.derivative_trend = self.detector.detect(
                        self.state.derivative_history_df, self.state, self.state.derivative)

                    self.state.call_trend = self.detector.detect(
                        self.state.current_call_data, self.state, self.state.call_option)

                    self.state.put_trend = self.detector.detect(
                        self.state.current_put_data, self.state, self.state.put_option)

                    if self.state.dynamic_signals_active:
                        logger.info(f"📊 Dynamic signal: {self.state.option_signal}")

                        if self.state.signal_conflict:
                            logger.warning("⚠️ Signal conflict detected - BUY_CALL and BUY_PUT both true")

                        if logger.isEnabledFor(logging.DEBUG):
                            self._log_signal_details()

        except Exception as e:
            logger.error(f"Error in _fetch_history_and_detect: {e!r}", exc_info=True)
        finally:
            self._history_fetch_in_progress.clear()

    def _log_signal_details(self):
        """Log detailed signal information using state properties."""
        try:
            if not self.state.option_signal_result:
                return

            snapshot = self.state.get_option_signal_snapshot()
            logger.debug(f"Signal snapshot - Value: {snapshot.get('signal_value')}")
            logger.debug(f"Fired signals: {snapshot.get('fired', {})}")

            rule_results = snapshot.get('rule_results', {})
            for signal_name, rules in rule_results.items():
                triggered = [r for r in rules if r.get('result')]
                if triggered:
                    logger.debug(f"  {signal_name} triggered by {len(triggered)} rule(s)")
                    for rule in triggered[:2]:
                        logger.debug(f"    - {rule.get('rule', 'Unknown rule')}")

        except Exception as e:
            logger.debug(f"Error logging signal details: {e}")

    def determine_trend_from_signals(self) -> Optional[tuple]:
        """
        Determine trend direction based on dynamic option signals.
        Returns trend enum values (ENTER_CALL, ENTER_PUT, EXIT_CALL, EXIT_PUT, RESET_PREVIOUS_TRADE)
        """
        try:
            if not self.state.dynamic_signals_active:
                return None

            signal_value = self.state.option_signal
            signal_conflict = self.state.signal_conflict

            current_pos = self.state.current_position
            previous_pos = self.state.previous_position

            trend = None

            logger.debug(f"Option signal: {signal_value}, conflict={signal_conflict}")

            # === EXIT Conditions ===
            if current_pos == BaseEnums.CALL:
                if signal_value in ['SELL_CALL', 'BUY_PUT']:
                    trend = BaseEnums.EXIT_CALL
                    self.state.reason_to_exit = self._get_exit_reason('CALL')

            elif current_pos == BaseEnums.PUT:
                if signal_value in ['SELL_PUT', 'BUY_CALL']:
                    trend = BaseEnums.EXIT_PUT
                    self.state.reason_to_exit = self._get_exit_reason('PUT')

            # === ENTRY Conditions ===
            elif current_pos is None and previous_pos is None:
                if self.state.should_buy_call:
                    trend = BaseEnums.ENTER_CALL
                    self.state.reason_to_exit = "BUY_CALL signal triggered"

                elif self.state.should_buy_put:
                    trend = BaseEnums.ENTER_PUT
                    self.state.reason_to_exit = "BUY_PUT signal triggered"

                elif self.state.should_hold:
                    logger.debug("HOLD signal - no entry")

                elif self.state.should_wait:
                    logger.debug("WAIT signal - no entry")

            # === RESET Condition ===
            elif current_pos is None and previous_pos in {BaseEnums.CALL, BaseEnums.PUT}:
                if previous_pos == BaseEnums.CALL and signal_value in ['BUY_PUT', 'SELL_PUT']:
                    trend = BaseEnums.RESET_PREVIOUS_TRADE
                    logger.info("Reset previous CALL trade flag - opposite signal detected")

                elif previous_pos == BaseEnums.PUT and signal_value in ['BUY_CALL', 'SELL_CALL']:
                    trend = BaseEnums.RESET_PREVIOUS_TRADE
                    logger.info("Reset previous PUT trade flag - opposite signal detected")

            if trend:
                logger.info(f"📈 Determined trend: {trend} | Reason: {self.state.reason_to_exit}")

            return trend

        except Exception as e:
            logger.error(f"Error determining trend from signals: {e}", exc_info=True)
            return None

    def _get_exit_reason(self, position_type: str) -> str:
        """Extract exit reason from signal results."""
        try:
            if not self.state.option_signal_result:
                return f"Exit triggered for {position_type}"

            rule_results = self.state.option_signal_result.get('rule_results', {})

            sell_signal = 'SELL_CALL' if position_type == 'CALL' else 'SELL_PUT'
            if sell_signal in rule_results:
                for rule in rule_results[sell_signal]:
                    if rule.get('result'):
                        return f"{sell_signal}: {rule.get('rule', 'Unknown rule')}"

            opposite = 'BUY_PUT' if position_type == 'CALL' else 'BUY_CALL'
            if opposite in rule_results:
                for rule in rule_results[opposite]:
                    if rule.get('result'):
                        return f"Trend reversal - {opposite}: {rule.get('rule', 'Unknown rule')}"

            return f"Exit triggered for {position_type}"

        except Exception as e:
            logger.error(f"Error getting exit reason: {e}")
            return f"Exit triggered for {position_type}"

    def monitor_active_trade_status(self) -> None:
        try:
            if not self.state.current_trade_confirmed:
                return

            index_stop_loss = getattr(self.state, "index_stop_loss", None)
            current_derivative_price = self.state.derivative_current_price

            if self.state.current_trade_confirmed:
                if Utils.is_near_market_close(buffer_minutes=5):
                    if self.state.current_position:
                        logger.info("Market close approaching. Exiting active position.")
                        self.state.reason_to_exit = "Auto-exit before market close."
                        if hasattr(self, 'executor') and self.executor:
                            success = self.executor.exit_position(self.state)
                            if not success:
                                logger.error("Exit failed near market close")
                        return

                # Use dynamic signals for exit
                if self.state.current_position == BaseEnums.PUT:
                    if self.state.should_sell_put or self.state.should_buy_call:
                        self.state.reason_to_exit = f"PUT exit: {self.state.option_signal}"
                        if hasattr(self, 'executor') and self.executor:
                            success = self.executor.exit_position(self.state)
                            if not success:
                                logger.error("Exit failed for PUT")

                    elif index_stop_loss is not None and current_derivative_price >= index_stop_loss:
                        self.state.reason_to_exit = "PUT exit: Derivative crossed above ST (safety)"
                        if hasattr(self, 'executor') and self.executor:
                            success = self.executor.exit_position(self.state)
                            if not success:
                                logger.error("Exit failed for PUT (safety)")

                elif self.state.current_position == BaseEnums.CALL:
                    if self.state.should_sell_call or self.state.should_buy_put:
                        self.state.reason_to_exit = f"CALL exit: {self.state.option_signal}"
                        if hasattr(self, 'executor') and self.executor:
                            success = self.executor.exit_position(self.state)
                            if not success:
                                logger.error("Exit failed for CALL")

                    elif index_stop_loss is not None and current_derivative_price <= index_stop_loss:
                        self.state.reason_to_exit = "CALL exit: Derivative dropped below ST (safety)"
                        if hasattr(self, 'executor') and self.executor:
                            success = self.executor.exit_position(self.state)
                            if not success:
                                logger.error("Exit failed for CALL (safety)")

            else:
                # Unconfirmed trade - check for cancellation signals
                if Utils.is_near_market_close(buffer_minutes=5):
                    if self.state.current_position:
                        logger.info("Market close approaching. Canceling pending position.")
                        self.cancel_pending_trade()
                        return

                if self.state.current_position == BaseEnums.PUT:
                    if self.state.should_buy_call or self.state.should_sell_call:
                        logger.info(f"Cancel pending PUT - {self.state.option_signal}")
                        self.cancel_pending_trade()

                elif self.state.current_position == BaseEnums.CALL:
                    if self.state.should_buy_put or self.state.should_sell_put:
                        logger.info(f"Cancel pending CALL - {self.state.option_signal}")
                        self.cancel_pending_trade()

        except Exception as e:
            logger.error(f"Error monitoring active trade status: {e!r}", exc_info=True)

    def monitor_profit_loss_status(self) -> None:
        try:
            if not self.state.current_trade_confirmed:
                return

            stop_loss = getattr(self.state, "stop_loss", None)
            tp_point = getattr(self.state, "tp_point", None)
            current_price = getattr(self.state, "current_price", None)

            if stop_loss is not None and current_price is not None and current_price <= stop_loss:
                self.state.reason_to_exit = f"{self.state.current_position} exit: Option price below stop loss."
                if hasattr(self, 'executor') and self.executor:
                    success = self.executor.exit_position(self.state)
                    if not success:
                        logger.error(f"Exit failed for stop loss at {stop_loss}")

            elif tp_point is not None and current_price is not None and current_price >= tp_point:
                self.state.reason_to_exit = f"{self.state.current_position} exit: Target profit hit."
                if hasattr(self, 'executor') and self.executor:
                    success = self.executor.exit_position(self.state)
                    if not success:
                        logger.error(f"Exit failed for take profit at {tp_point}")

        except Exception as e:
            logger.error(f"Error monitoring profit/loss status: {e!r}", exc_info=True)

    def execute_based_on_trend(self) -> None:
        try:
            if Utils.check_sideway_time() and not self.state.sideway_zone_trade:
                logger.info("Sideways period (12:00–2:00). Skipping trading decision.")
                return

            if not Utils.is_market_open():
                logger.info("Market is closed. Skipping trading execution.")
                return

            if Utils.is_near_market_close(buffer_minutes=5):
                logger.info("Too close to market close. Skipping trading decision.")
                return

            trend = self.state.trend

            if self.state.current_position is None:
                if trend == BaseEnums.ENTER_CALL and self.state.should_buy_call:
                    logger.info("🎯 ENTER_CALL confirmed by BUY_CALL")
                    success = self.executor.buy_option(self.state, option_type=BaseEnums.CALL)
                    if success and self.state.call_option not in self.state.all_symbols:
                        self.subscribe_market_data()

                elif trend == BaseEnums.ENTER_PUT and self.state.should_buy_put:
                    logger.info("🎯 ENTER_PUT confirmed by BUY_PUT")
                    success = self.executor.buy_option(self.state, option_type=BaseEnums.PUT)
                    if success and self.state.put_option not in self.state.all_symbols:
                        self.subscribe_market_data()

                elif trend == BaseEnums.RESET_PREVIOUS_TRADE:
                    logger.info("🔄 Resetting previous trade flag")
                    self.state.previous_position = None

            else:
                if self.state.current_position == BaseEnums.CALL:
                    if self.state.should_buy_put or self.state.should_sell_call:
                        logger.warning(f"Position CALL but signal is {self.state.option_signal} - will exit soon")

                elif self.state.current_position == BaseEnums.PUT:
                    if self.state.should_buy_call or self.state.should_sell_put:
                        logger.warning(f"Position PUT but signal is {self.state.option_signal} - will exit soon")

        except Exception as exec_error:
            logger.error(f"Order execution failed: {exec_error!r}", exc_info=True)

    def cancel_pending_trade(self) -> None:
        try:
            if not self.state.orders:
                logger.info("No pending orders to cancel.")
                return

            logger.info(f"Cancelling {len(self.state.orders)} pending order(s).")

            remaining_orders = []
            confirmed_orders = []
            confirmed_found = False

            for order in self.state.orders:
                order_id = order.get("id")
                try:
                    if hasattr(self.broker, 'get_current_order_status'):
                        status_list = self.broker.get_current_order_status(order_id)
                        if status_list:
                            order_status = status_list[0].get("status")
                            if order_status == BaseEnums.ORDER_STATUS_CONFIRMED:
                                confirmed_found = True
                                confirmed_orders.append(order)
                                logger.info(f"✅ Order {order_id} confirmed. Will not cancel.")
                                continue

                    if hasattr(self.broker, 'cancel_order'):
                        self.broker.cancel_order(order_id=order_id)
                        logger.info(f"Cancelled order ID: {order_id}")

                except Exception as e:
                    logger.error(f"❌ Failed to cancel order ID {order_id}: {e}", exc_info=True)
                    remaining_orders.append(order)

            self.state.orders = remaining_orders

            if not hasattr(self.state, "confirmed_orders"):
                self.state.confirmed_orders = []
            if confirmed_orders:
                self.state.confirmed_orders.extend(confirmed_orders)

            if confirmed_found:
                self.state.current_trade_confirmed = True
                logger.info("✔️ Trade marked as confirmed due to confirmed orders.")
            else:
                self.state.reset_trade_attributes(current_position=None)

            logger.info("🧹 Pending order cancellation process complete.")

        except Exception as e:
            logger.error(f"🔥 Error in cancel_pending_trade: {e}", exc_info=True)

    @staticmethod
    def symbol_full(symbol: Optional[str]) -> Optional[str]:
        return f"NSE:{symbol}" if symbol and not symbol.startswith("NSE:") else symbol

    def refresh_settings_live(self) -> None:
        """Refresh settings from config files."""
        self.trade_config.load()
        self.profit_loss_config.load()
        self.apply_settings_to_state()

        self.reload_signal_engine()
        logger.info("Signal engine configuration reloaded")

    def apply_settings_to_state(self) -> None:
        """Apply settings to state object."""
        self.state.capital_reserve = getattr(self.trade_config, "capital_reserve", 0)

        if hasattr(self, 'broker') and self.broker:
            balance = self.broker.get_balance(getattr(self.state, "capital_reserve", 0))
            if balance and balance > 0:
                self.state.account_balance = balance
            else:
                logger.warning(f"Balance returned {balance}. Keeping existing value: {self.state.account_balance}")

        self.state.derivative = getattr(self.trade_config, "derivative", "")
        self.state.expiry = getattr(self.trade_config, "week", "")
        self.state.lot_size = getattr(self.trade_config, "lot_size", 0)
        self.state.call_lookback = getattr(self.trade_config, "call_lookback", 0)
        self.state.put_lookback = getattr(self.trade_config, "put_lookback", 0)
        self.state.original_call_lookback = self.state.call_lookback
        self.state.original_put_lookback = self.state.put_lookback
        self.state.interval = getattr(self.trade_config, "history_interval", "")
        self.state.max_num_of_option = getattr(self.trade_config, "max_num_of_option", 0)
        self.state.lower_percentage = getattr(self.trade_config, "lower_percentage", 0)
        self.state.cancel_after = getattr(self.trade_config, "cancel_after", 0)
        self.state.sideway_zone_trade = getattr(self.trade_config, "sideway_zone_trade", False)

        plc = self.profit_loss_config
        self.state.tp_percentage = self.state.original_profit_per = getattr(plc, "tp_percentage", 0)
        self.state.stoploss_percentage = self.state.original_stoploss_per = getattr(plc, "stoploss_percentage", 0)
        self.state.trailing_first_profit = getattr(plc, "trailing_first_profit", 0)
        self.state.max_profit = getattr(plc, "max_profit", 0)
        self.state.profit_step = getattr(plc, "profit_step", 0)
        self.state.loss_step = getattr(plc, "loss_step", 0)
        self.state.take_profit_type = getattr(plc, "profit_type", "absolute")

        logger.info(f"[Settings] Applied trade and P/L configs - Capital: {self.state.capital_reserve}, "
                    f"Lot size: {self.state.lot_size}, TP: {self.state.tp_percentage}%, "
                    f"SL: {self.state.stoploss_percentage}%")

    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        logger.info("Cleaning up TradingApp resources...")
        self.should_stop = True

        if hasattr(self, 'ws') and self.ws:
            try:
                self.ws.unsubscribe()
                logger.info("WebSocket disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting WebSocket: {e}")

        if hasattr(self, '_fetch_executor'):
            self._fetch_executor.shutdown(wait=False)
            logger.info("Thread pool shut down")