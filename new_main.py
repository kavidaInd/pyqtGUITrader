#!/usr/bin/env python3
"""
Main trading application with support for LIVE, PAPER, and BACKTEST modes.
"""
import concurrent.futures
import logging
import logging.handlers
import threading
from typing import Optional, Any, Dict, List, Union
from datetime import datetime

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

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


def safe_last(val):
    """Return last element if val is list/tuple and not empty, else just val or None."""
    try:
        if isinstance(val, (list, tuple)) and val:
            return val[-1]
        return val
    except Exception as e:
        logger.error(f"[safe_last] Error processing {val!r}: {e}", exc_info=True)
        return None


class TradingApp:
    # Rule 3: Define signals if this were a QObject (for future compatibility)
    # error_occurred = pyqtSignal(str)
    # status_updated = pyqtSignal(str)
    # trade_executed = pyqtSignal(dict)

    def __init__(self, config: Any, trading_mode_var: Optional[Any] = None, broker_setting: Optional[Any] = None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if config is None:
                logger.warning("config is None in TradingApp.__init__")

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

            # Safe WebSocket initialization
            client_id = ""
            if broker_setting and hasattr(broker_setting, "client_id"):
                client_id = broker_setting.client_id

            self.ws = WebSocketManager(
                token=getattr(self.state, "token", None),
                client_id=client_id,
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

            # Add should_stop flag and event for graceful shutdown
            self.should_stop = False
            self._stop_event = threading.Event()

            logger.info("TradingApp initialized successfully")

        except Exception as e:
            logger.critical(f"[TradingApp.__init__] Initialization failed: {e}", exc_info=True)
            # Re-raise to ensure caller knows initialization failed
            raise

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.state = None
        self.config = None
        self.broker = None
        self.trade_config = None
        self.profit_loss_config = None
        self.strategy_manager = None
        self.signal_engine = None
        self.detector = None
        self.executor = None
        self.monitor = None
        self.ws = None
        self._fetch_executor = None
        self._history_fetch_in_progress = None
        self._processing_in_progress = None
        self._option_chain_lock = None
        self._chain_itm = 5
        self._chain_otm = 5
        self.should_stop = False
        self._stop_event = threading.Event()
        self._cleanup_done = False

    def _create_signal_engine(self) -> DynamicSignalEngine:
        """Create signal engine with active strategy config"""
        try:
            engine = DynamicSignalEngine()

            # Rule 6: Safe access to strategy manager
            if self.strategy_manager:
                active_config = self.strategy_manager.get_active_engine_config()
                if active_config:
                    engine.from_dict(active_config)
                    # logger.info(f"Loaded signal engine config from active strategy: {self.strategy_manager.get_active_name()}")
            return engine

        except Exception as e:
            logger.error(f"[TradingApp._create_signal_engine] Failed: {e}", exc_info=True)
            # Return default engine on failure
            return DynamicSignalEngine()

    def reload_signal_engine(self):
        """Reload signal engine from active strategy (called when strategy changes)"""
        try:
            if not self.strategy_manager:
                logger.warning("Cannot reload signal engine: strategy_manager is None")
                return

            if not self.signal_engine:
                logger.warning("Cannot reload signal engine: signal_engine is None")
                return

            new_config = self.strategy_manager.get_active_engine_config()
            if new_config:
                self.signal_engine.from_dict(new_config)
                # Update trend detector's signal engine
                if hasattr(self.detector, 'set_signal_engine') and self.detector:
                    self.detector.set_signal_engine(self.signal_engine)
                # logger.info(f"Signal engine reloaded with strategy: {self.strategy_manager.get_active_name()}")

        except Exception as e:
            logger.error(f"[TradingApp.reload_signal_engine] Failed: {e}", exc_info=True)

    def run(self) -> None:
        # logger.info("Starting trading app with dynamic signals...")
        try:
            # Check if we should stop before starting
            if self.should_stop:
                logger.info("Stop requested before run, exiting")
                return

            self.initialize_market_state()
            self.subscribe_market_data()

            # Keep the trading thread alive while WebSocket runs in background.
            # The WebSocket connect() is non-blocking, so without this loop the
            # thread would exit immediately, causing the app to auto-stop.
            logger.info("Trading thread entering keep-alive loop (WebSocket running in background)")
            while not self.should_stop:
                self._stop_event.wait(timeout=1.0)

            logger.info("Trading thread keep-alive loop exited (should_stop=True)")

        except TokenExpiredError as e:
            logger.error(f"Token expired during run: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.critical(f"Unhandled exception during run: {e!r}", exc_info=True)
            raise

    def initialize_market_state(self) -> None:
        try:
            self.apply_settings_to_state()

            # Get initial price for derivative
            if self.broker and hasattr(self.broker, 'get_option_current_price'):
                try:
                    self.state.derivative_current_price = self.broker.get_option_current_price(
                        getattr(self.state, "derivative", None)
                    )
                    # logger.info(f"Initial price for {self.state.derivative}: {self.state.derivative_current_price}")
                except Exception as price_error:
                    logger.error(f"Failed to get initial price: {price_error!r}", exc_info=True)
            else:
                logger.warning("Broker doesn't support get_option_current_price")

        except Exception as e:
            logger.error(f"[TradingApp.initialize_market_state] Failed: {e!r}", exc_info=True)

    def subscribe_market_data(self) -> None:
        try:
            # Rule 6: Validate required attributes
            if self.state.derivative_current_price is None:
                logger.warning("derivative_current_price is None, cannot subscribe to market data")
                return

            spot = self.state.derivative_current_price
            expiry = getattr(self.state, "expiry", 0)
            derivative = getattr(self.state, "derivative", None)

            if not derivative:
                logger.warning(f"Missing derivative ({derivative})")
                return

            # ATM options (used for trade execution & history)
            self.state.put_option = OptionUtils.get_option_at_price(
                spot, op_type="PE", expiry=expiry,
                lookback=getattr(self.state, "put_lookback", 0),
                derivative_name=derivative)

            self.state.call_option = OptionUtils.get_option_at_price(
                spot, op_type="CE", expiry=expiry,
                lookback=getattr(self.state, "call_lookback", 0),
                derivative_name=derivative)

            # Build option chain: _chain_itm ITM + ATM + _chain_otm OTM on each side
            call_chain = OptionUtils.get_all_option(
                expiry=expiry, symbol=derivative, strike=spot,
                itm=self._chain_itm, otm=self._chain_otm, putorcall="CE")

            put_chain = OptionUtils.get_all_option(
                expiry=expiry, symbol=derivative, strike=spot,
                itm=self._chain_itm, otm=self._chain_otm, putorcall="PE")

            # Initialize chain storage with zero-state entries
            if self._option_chain_lock:
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
            chain_symbols = list(self.state.option_chain.keys()) if self.state.option_chain else []
            self.state.all_symbols = list(filter(None, [
                self.symbol_full(self.state.derivative),
                *chain_symbols
            ]))
            # Connect WebSocket
            if self.ws:
                self.ws.symbols = self.state.all_symbols
                self.ws.connect()
            else:
                logger.error("WebSocket manager not initialized")

        except Exception as ws_error:
            logger.error(f"WebSocket connection/subscription failed: {ws_error!r}", exc_info=True)

    def on_message(self, message: dict) -> None:
        """
        Two-stage message processing:
        Stage 1 (fast): Update market state immediately on WS thread
        Stage 2 (slow): Submit remaining processing to thread pool
        """
        try:
            # Rule 6: Input validation
            if not message:
                logger.warning("Empty message received")
                return

            if not isinstance(message, dict):
                logger.warning(f"Message is not a dict: {type(message)}")
                return

            symbol = message.get("symbol")
            if not symbol:
                logger.warning(f"Message missing symbol: {message}")
                return

            ltp = message.get("ltp")
            ask_price = message.get("ask_price")
            bid_price = message.get("bid_price")

            if ltp is None:
                logger.warning(f"LTP missing for symbol {symbol}. Message: {message}")
                return

            # Stage 1: Fast update - write LTP to state immediately
            self.update_market_state(symbol, ltp, ask_price, bid_price)

            # Stage 2: Slow processing - submit to thread pool if not already processing
            if self._processing_in_progress and not self._processing_in_progress.is_set():
                self._processing_in_progress.set()
                if self._fetch_executor:
                    self._fetch_executor.submit(self._process_message_stage2)
                else:
                    logger.error("Thread pool not available for stage 2 processing")
                    self._processing_in_progress.clear()

        except Exception as e:
            logger.error(f"Exception in on_message stage 1: {e!r}, Message: {message}", exc_info=True)

    def _process_message_stage2(self) -> None:
        """
        Stage 2 message processing - runs in thread pool.
        Contains all slower operations that shouldn't block the WebSocket thread.
        """
        try:
            # Check if we should stop
            if self.should_stop:
                logger.debug("Stop requested, skipping stage 2 processing")
                return

            # Run all monitoring and decision logic
            if hasattr(self, 'monitor') and self.monitor:
                try:
                    self.monitor.update_trailing_sl_tp(self.broker, self.state)
                except Exception as monitor_error:
                    logger.error(f"Error in monitor.update_trailing_sl_tp: {monitor_error}", exc_info=True)

            try:
                self.evaluate_trend_and_decision()
            except Exception as trend_error:
                logger.error(f"Error in evaluate_trend_and_decision: {trend_error}", exc_info=True)

            try:
                self.monitor_active_trade_status()
            except Exception as trade_error:
                logger.error(f"Error in monitor_active_trade_status: {trade_error}", exc_info=True)

            try:
                self.monitor_profit_loss_status()
            except Exception as pnl_error:
                logger.error(f"Error in monitor_profit_loss_status: {pnl_error}", exc_info=True)

        except TokenExpiredError:
            logger.critical("Token expired in stage 2 processing")
            # Re-raise to be handled by caller
            raise
        except Exception as e:
            logger.error(f"Exception in message stage 2 processing: {e!r}", exc_info=True)
        finally:
            if self._processing_in_progress:
                self._processing_in_progress.clear()

    def update_market_state(self, symbol: str, ltp: float, ask_price: float, bid_price: float) -> None:
        try:
            # Rule 6: Input validation
            if not symbol or ltp is None:
                logger.warning(f"Invalid update_market_state params: symbol={symbol}, ltp={ltp}")
                return

            if symbol == self.symbol_full(getattr(self.state, "derivative", None)):
                self.state.derivative_current_price = ltp
                return

            # --- Option chain tick ---
            if self._option_chain_lock and hasattr(self.state, "option_chain"):
                with self._option_chain_lock:
                    if symbol in self.state.option_chain:
                        self.state.option_chain[symbol] = {
                            "ltp": ltp,
                            "ask": ask_price,
                            "bid": bid_price,
                        }

            # --- ATM option convenience state ---
            use_ask = bool(getattr(self.state, "current_position", None))

            atm_put_sym = self.symbol_full(getattr(self.state, "put_option", None))
            atm_call_sym = self.symbol_full(getattr(self.state, "call_option", None))

            if symbol == atm_put_sym:
                self.state.put_current_close = ask_price if use_ask else bid_price
            elif symbol == atm_call_sym:
                self.state.call_current_close = ask_price if use_ask else bid_price

            # Update current_price for open position P&L tracking
            if self.state.current_position:
                cp = self.state.current_position
                self.state.current_price = self.state.call_current_close \
                    if cp == BaseEnums.CALL else self.state.put_current_close

        except Exception as e:
            logger.error(f"[TradingApp.update_market_state] Failed for symbol {symbol}: {e}", exc_info=True)

    def evaluate_trend_and_decision(self) -> None:
        try:
            # Check if we should stop
            if self.should_stop:
                return

            if not Utils.is_history_updated(
                    last_updated=getattr(self.state, "last_index_updated", None),
                    interval=getattr(self.state, "interval", None)
            ):
                if self._history_fetch_in_progress and not self._history_fetch_in_progress.is_set():
                    self._history_fetch_in_progress.set()
                    if self._fetch_executor:
                        self._fetch_executor.submit(self._fetch_history_and_detect)
                    else:
                        logger.error("Thread pool not available for history fetch")
                        self._history_fetch_in_progress.clear()

            self.state.trend = self.determine_trend_from_signals()

            # Execute based on trend (only for algo trading)
            if hasattr(self, 'executor') and self.executor:
                self.execute_based_on_trend()

        except Exception as trend_error:
            logger.info(f"Trend detection or decision logic error: {trend_error!r}", exc_info=True)

    def _fetch_history_and_detect(self) -> None:
        """Runs on thread pool — fetches history and updates trend state."""
        try:
            # Check if we should stop
            if self.should_stop:
                logger.debug("Stop requested, skipping history fetch")
                return

            # Fetch derivative history
            if self.broker and hasattr(self.broker, 'get_history'):
                try:
                    self.state.derivative_history_df = self.broker.get_history(
                        symbol=getattr(self.state, "derivative", None),
                        interval=getattr(self.state, "interval", None)
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch derivative history: {e}", exc_info=True)

                try:
                    self.state.current_call_data = self.broker.get_history(
                        symbol=getattr(self.state, "call_option", None),
                        interval=getattr(self.state, "interval", None)
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch call data: {e}", exc_info=True)

                try:
                    self.state.current_put_data = self.broker.get_history(
                        symbol=getattr(self.state, "put_option", None),
                        interval=getattr(self.state, "interval", None)
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch put data: {e}", exc_info=True)

                if self.state.derivative_history_df is not None and \
                        not self.state.derivative_history_df.empty:

                    try:
                        self.state.last_index_updated = \
                            self.state.derivative_history_df["time"].iloc[-1]
                    except (KeyError, IndexError, AttributeError) as e:
                        logger.error(f"Failed to get last index time: {e}", exc_info=True)

                    # Run trend detection with signal engine
                    if self.detector:
                        try:
                            self.state.derivative_trend = self.detector.detect(
                                self.state.derivative_history_df, self.state, getattr(self.state, "derivative", None))
                        except Exception as e:
                            logger.error(f"Derivative trend detection failed: {e}", exc_info=True)

                        try:
                            self.state.call_trend = self.detector.detect(
                                self.state.current_call_data, self.state, getattr(self.state, "call_option", None))
                        except Exception as e:
                            logger.error(f"Call trend detection failed: {e}", exc_info=True)

                        try:
                            self.state.put_trend = self.detector.detect(
                                self.state.current_put_data, self.state, getattr(self.state, "put_option", None))
                        except Exception as e:
                            logger.error(f"Put trend detection failed: {e}", exc_info=True)

                    if getattr(self.state, "dynamic_signals_active", False):
                        logger.info(f"📊 Dynamic signal: {getattr(self.state, 'option_signal', None)}")

                        if getattr(self.state, "signal_conflict", False):
                            logger.warning("⚠️ Signal conflict detected - BUY_CALL and BUY_PUT both true")

                        if logger.isEnabledFor(logging.DEBUG):
                            self._log_signal_details()

        except Exception as e:
            logger.error(f"Error in _fetch_history_and_detect: {e!r}", exc_info=True)
        finally:
            if self._history_fetch_in_progress:
                self._history_fetch_in_progress.clear()

    def _log_signal_details(self):
        """Log detailed signal information using state properties."""
        try:
            if not getattr(self.state, "option_signal_result", None):
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
            if not getattr(self.state, "dynamic_signals_active", False):
                return None

            signal_value = getattr(self.state, "option_signal", None)
            signal_conflict = getattr(self.state, "signal_conflict", False)

            current_pos = getattr(self.state, "current_position", None)
            previous_pos = getattr(self.state, "previous_position", None)

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
                if getattr(self.state, "should_buy_call", False):
                    trend = BaseEnums.ENTER_CALL
                    self.state.reason_to_exit = "BUY_CALL signal triggered"

                elif getattr(self.state, "should_buy_put", False):
                    trend = BaseEnums.ENTER_PUT
                    self.state.reason_to_exit = "BUY_PUT signal triggered"

                elif getattr(self.state, "should_hold", False):
                    logger.debug("HOLD signal - no entry")

                elif getattr(self.state, "should_wait", False):
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
                logger.info(f"📈 Determined trend: {trend} | Reason: {getattr(self.state, 'reason_to_exit', None)}")

            return trend

        except Exception as e:
            logger.error(f"Error determining trend from signals: {e}", exc_info=True)
            return None

    def _get_exit_reason(self, position_type: str) -> str:
        """Extract exit reason from signal results."""
        try:
            if not getattr(self.state, "option_signal_result", None):
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
            # Check if we should stop
            if self.should_stop:
                return

            if not getattr(self.state, "current_trade_confirmed", False):
                return

            index_stop_loss = getattr(self.state, "index_stop_loss", None)
            current_derivative_price = getattr(self.state, "derivative_current_price", None)

            if self.state.current_trade_confirmed:
                if Utils.is_near_market_close(buffer_minutes=5):
                    if self.state.current_position:
                        logger.info("Market close approaching. Exiting active position.")
                        self.state.reason_to_exit = "Auto-exit before market close."
                        if hasattr(self, 'executor') and self.executor:
                            try:
                                success = self.executor.exit_position(self.state)
                                if not success:
                                    logger.error("Exit failed near market close")
                            except Exception as e:
                                logger.error(f"Exit error near market close: {e}", exc_info=True)
                        return

                # Use dynamic signals for exit
                if self.state.current_position == BaseEnums.PUT:
                    if getattr(self.state, "should_sell_put", False) or getattr(self.state, "should_buy_call", False):
                        self.state.reason_to_exit = f"PUT exit: {getattr(self.state, 'option_signal', None)}"
                        if hasattr(self, 'executor') and self.executor:
                            try:
                                success = self.executor.exit_position(self.state)
                                if not success:
                                    logger.error("Exit failed for PUT")
                            except Exception as e:
                                logger.error(f"PUT exit error: {e}", exc_info=True)

                    elif index_stop_loss is not None and current_derivative_price is not None and current_derivative_price >= index_stop_loss:
                        self.state.reason_to_exit = "PUT exit: Derivative crossed above ST (safety)"
                        if hasattr(self, 'executor') and self.executor:
                            try:
                                success = self.executor.exit_position(self.state)
                                if not success:
                                    logger.error("Exit failed for PUT (safety)")
                            except Exception as e:
                                logger.error(f"PUT safety exit error: {e}", exc_info=True)

                elif self.state.current_position == BaseEnums.CALL:
                    if getattr(self.state, "should_sell_call", False) or getattr(self.state, "should_buy_put", False):
                        self.state.reason_to_exit = f"CALL exit: {getattr(self.state, 'option_signal', None)}"
                        if hasattr(self, 'executor') and self.executor:
                            try:
                                success = self.executor.exit_position(self.state)
                                if not success:
                                    logger.error("Exit failed for CALL")
                            except Exception as e:
                                logger.error(f"CALL exit error: {e}", exc_info=True)

                    elif index_stop_loss is not None and current_derivative_price is not None and current_derivative_price <= index_stop_loss:
                        self.state.reason_to_exit = "CALL exit: Derivative dropped below ST (safety)"
                        if hasattr(self, 'executor') and self.executor:
                            try:
                                success = self.executor.exit_position(self.state)
                                if not success:
                                    logger.error("Exit failed for CALL (safety)")
                            except Exception as e:
                                logger.error(f"CALL safety exit error: {e}", exc_info=True)

            else:
                # Unconfirmed trade - check for cancellation signals
                if Utils.is_near_market_close(buffer_minutes=5):
                    if self.state.current_position:
                        logger.info("Market close approaching. Canceling pending position.")
                        self.cancel_pending_trade()
                        return

                if self.state.current_position == BaseEnums.PUT:
                    if getattr(self.state, "should_buy_call", False) or getattr(self.state, "should_sell_call", False):
                        logger.info(f"Cancel pending PUT - {getattr(self.state, 'option_signal', None)}")
                        self.cancel_pending_trade()

                elif self.state.current_position == BaseEnums.CALL:
                    if getattr(self.state, "should_buy_put", False) or getattr(self.state, "should_sell_put", False):
                        logger.info(f"Cancel pending CALL - {getattr(self.state, 'option_signal', None)}")
                        self.cancel_pending_trade()

        except Exception as e:
            logger.error(f"Error monitoring active trade status: {e!r}", exc_info=True)

    def monitor_profit_loss_status(self) -> None:
        try:
            # Check if we should stop
            if self.should_stop:
                return

            if not getattr(self.state, "current_trade_confirmed", False):
                return

            stop_loss = getattr(self.state, "stop_loss", None)
            tp_point = getattr(self.state, "tp_point", None)
            current_price = getattr(self.state, "current_price", None)

            if stop_loss is not None and current_price is not None and current_price <= stop_loss:
                self.state.reason_to_exit = f"{self.state.current_position} exit: Option price below stop loss."
                if hasattr(self, 'executor') and self.executor:
                    try:
                        success = self.executor.exit_position(self.state)
                        if not success:
                            logger.error(f"Exit failed for stop loss at {stop_loss}")
                    except Exception as e:
                        logger.error(f"Stop loss exit error: {e}", exc_info=True)

            elif tp_point is not None and current_price is not None and current_price >= tp_point:
                self.state.reason_to_exit = f"{self.state.current_position} exit: Target profit hit."
                if hasattr(self, 'executor') and self.executor:
                    try:
                        success = self.executor.exit_position(self.state)
                        if not success:
                            logger.error(f"Exit failed for take profit at {tp_point}")
                    except Exception as e:
                        logger.error(f"Take profit exit error: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error monitoring profit/loss status: {e!r}", exc_info=True)

    def execute_based_on_trend(self) -> None:
        try:
            # Check if we should stop
            if self.should_stop:
                return

            if Utils.check_sideway_time() and not getattr(self.state, "sideway_zone_trade", False):
                logger.info("Sideways period (12:00–2:00). Skipping trading decision.")
                return

            if not Utils.is_market_open():
                logger.info("Market is closed. Skipping trading execution.")
                return

            if Utils.is_near_market_close(buffer_minutes=5):
                logger.info("Too close to market close. Skipping trading decision.")
                return

            trend = getattr(self.state, "trend", None)

            if self.state.current_position is None:
                if trend == BaseEnums.ENTER_CALL and getattr(self.state, "should_buy_call", False):
                    logger.info("🎯 ENTER_CALL confirmed by BUY_CALL")
                    try:
                        success = self.executor.buy_option(self.state, option_type=BaseEnums.CALL)
                        if success and self.state.call_option not in (self.state.all_symbols or []):
                            self.subscribe_market_data()
                    except Exception as e:
                        logger.error(f"Failed to execute CALL: {e}", exc_info=True)

                elif trend == BaseEnums.ENTER_PUT and getattr(self.state, "should_buy_put", False):
                    logger.info("🎯 ENTER_PUT confirmed by BUY_PUT")
                    try:
                        success = self.executor.buy_option(self.state, option_type=BaseEnums.PUT)
                        if success and self.state.put_option not in (self.state.all_symbols or []):
                            self.subscribe_market_data()
                    except Exception as e:
                        logger.error(f"Failed to execute PUT: {e}", exc_info=True)

                elif trend == BaseEnums.RESET_PREVIOUS_TRADE:
                    logger.info("🔄 Resetting previous trade flag")
                    self.state.previous_position = None

            else:
                if self.state.current_position == BaseEnums.CALL:
                    if getattr(self.state, "should_buy_put", False) or getattr(self.state, "should_sell_call", False):
                        logger.warning(
                            f"Position CALL but signal is {getattr(self.state, 'option_signal', None)} - will exit soon")

                elif self.state.current_position == BaseEnums.PUT:
                    if getattr(self.state, "should_buy_call", False) or getattr(self.state, "should_sell_put", False):
                        logger.warning(
                            f"Position PUT but signal is {getattr(self.state, 'option_signal', None)} - will exit soon")

        except Exception as exec_error:
            logger.error(f"Order execution failed: {exec_error!r}", exc_info=True)

    def cancel_pending_trade(self) -> None:
        try:
            if not getattr(self.state, "orders", None):
                logger.info("No pending orders to cancel.")
                return

            logger.info(f"Cancelling {len(self.state.orders)} pending order(s).")

            remaining_orders = []
            confirmed_orders = []
            confirmed_found = False

            for order in self.state.orders:
                order_id = order.get("id")
                try:
                    if self.broker and hasattr(self.broker, 'get_current_order_status'):
                        status_list = self.broker.get_current_order_status(order_id)
                        if status_list and len(status_list) > 0:
                            order_status = status_list[0].get("status")
                            if order_status == BaseEnums.ORDER_STATUS_CONFIRMED:
                                confirmed_found = True
                                confirmed_orders.append(order)
                                logger.info(f"✅ Order {order_id} confirmed. Will not cancel.")
                                continue

                    if self.broker and hasattr(self.broker, 'cancel_order'):
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
        try:
            if not symbol:
                return None
            return f"NSE:{symbol}" if not symbol.startswith("NSE:") else symbol
        except Exception as e:
            logger.error(f"[symbol_full] Error processing {symbol}: {e}", exc_info=True)
            return symbol  # Return original on error

    def refresh_settings_live(self) -> None:
        """Refresh settings from config files."""
        try:
            if self.trade_config:
                self.trade_config.load()
            if self.profit_loss_config:
                self.profit_loss_config.load()
            self.apply_settings_to_state()

            self.reload_signal_engine()
            logger.info("Signal engine configuration reloaded")

        except Exception as e:
            logger.error(f"[TradingApp.refresh_settings_live] Failed: {e}", exc_info=True)

    def apply_settings_to_state(self) -> None:
        """Apply settings to state object."""
        try:
            # Apply trade_config settings
            if self.trade_config:
                self.state.capital_reserve = getattr(self.trade_config, "capital_reserve", 0)

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

            # Get balance from broker
            if self.broker:
                try:
                    balance = self.broker.get_balance(getattr(self.state, "capital_reserve", 0))
                    if balance and balance > 0:
                        self.state.account_balance = balance
                    else:
                        logger.warning(
                            f"Balance returned {balance}. Keeping existing value: {self.state.account_balance}")
                except Exception as e:
                    logger.error(f"Failed to get balance: {e}", exc_info=True)

            # Apply profit/loss settings
            if self.profit_loss_config:
                plc = self.profit_loss_config
                self.state.tp_percentage = self.state.original_profit_per = getattr(plc, "tp_percentage", 0)
                self.state.stoploss_percentage = self.state.original_stoploss_per = getattr(plc, "stoploss_percentage",
                                                                                            0)
                self.state.trailing_first_profit = getattr(plc, "trailing_first_profit", 0)
                self.state.max_profit = getattr(plc, "max_profit", 0)
                self.state.profit_step = getattr(plc, "profit_step", 0)
                self.state.loss_step = getattr(plc, "loss_step", 0)
                self.state.take_profit_type = getattr(plc, "profit_type", "absolute")

            logger.info(f"[Settings] Applied trade and P/L configs - Capital: {self.state.capital_reserve}, "
                        f"Lot size: {self.state.lot_size}, TP: {self.state.tp_percentage}%, "
                        f"SL: {self.state.stoploss_percentage}%")

        except Exception as e:
            logger.error(f"[TradingApp.apply_settings_to_state] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        try:
            # Prevent multiple cleanup calls
            if self._cleanup_done:
                return

            logger.info("Cleaning up TradingApp resources...")
            self.should_stop = True
            if hasattr(self, '_stop_event') and self._stop_event:
                self._stop_event.set()  # Wake up the keep-alive loop immediately

            # WebSocket cleanup
            if hasattr(self, 'ws') and self.ws:
                try:
                    if hasattr(self.ws, 'unsubscribe'):
                        self.ws.unsubscribe()
                    logger.info("WebSocket disconnected")
                except Exception as e:
                    logger.error(f"Error disconnecting WebSocket: {e}", exc_info=True)

            # Thread pool shutdown
            if hasattr(self, '_fetch_executor') and self._fetch_executor:
                try:
                    self._fetch_executor.shutdown(wait=False)
                    logger.info("Thread pool shut down")
                except Exception as e:
                    logger.error(f"Error shutting down thread pool: {e}", exc_info=True)

            # Broker cleanup if needed
            if hasattr(self, 'broker') and self.broker:
                try:
                    if hasattr(self.broker, 'cleanup'):
                        self.broker.cleanup()
                except Exception as e:
                    logger.error(f"Broker cleanup error: {e}", exc_info=True)

            self._cleanup_done = True
            logger.info("TradingApp cleanup completed")

        except Exception as e:
            logger.error(f"[TradingApp.cleanup] Error: {e}", exc_info=True)
            self._cleanup_done = True
