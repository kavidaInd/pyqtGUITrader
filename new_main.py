#!/usr/bin/env python3
"""
Main trading application with support for LIVE, PAPER, and BACKTEST modes.
REFACTORED: Thread-safe, snapshot-based processing, proper error handling.
"""

import concurrent.futures
import logging
import logging.handlers
import queue
import threading
import time
import random
from datetime import datetime
from typing import Optional, Any, Dict, List
from threading import Timer

import pandas as pd

import BaseEnums
from Utils.OptionUtils import OptionUtils
from Utils.Utils import Utils
from Utils.notifier import Notifier
from Utils.safe_getattr import safe_getattr, safe_hasattr
from broker.BaseBroker import TokenExpiredError
from broker.BrokerFactory import BrokerFactory
from data.candle_store_manager import candle_store_manager
from data.websocket_manager import WebSocketManager
from gui.daily_trade.DailyTradeSetting import DailyTradeSetting
from gui.profit_loss.ProfitStoplossSetting import ProfitStoplossSetting
from data.trade_state_manager import state_manager
from strategy.dynamic_signal_engine import DynamicSignalEngine
from strategy.multi_tf_filter import MultiTimeframeFilter
from strategy.strategy_manager import StrategyManager
from strategy.trend_detector import TrendDetector
from trade.order_executor import OrderExecutor
from trade.position_monitor import PositionMonitor
from trade.risk_manager import RiskManager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TradingApp:
    """
    Main trading application with thread-safe design.

    DESIGN PRINCIPLES:
    1. Use snapshots for cross-thread data access - never hold state lock in worker threads
    2. All long operations run in thread pool with timeouts
    3. UI updates via signals only
    4. Proper cleanup on shutdown
    """

    def __init__(self, config: Any, trading_mode_var: Optional[Any] = None, broker_setting: Optional[Any] = None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if config is None:
                logger.warning("config is None in TradingApp.__init__")

            # FIX-6: Store constructor args only — no network I/O in __init__.
            # BrokerFactory.create() performs network calls (token validation,
            # balance fetch) which previously blocked the GUI thread because
            # TradingApp() was constructed in TradingGUI._init_trading_app()
            # (main thread).  All heavy initialisation now runs in initialize(),
            # which TradingThread.run() calls on the worker thread.
            self.config = config
            self.trading_mode_setting = trading_mode_var
            self._broker_setting = broker_setting   # stored for initialize()

            # BUG #6 FIX: Replace Event with Queue + dedicated worker thread
            self._tick_queue = queue.Queue(maxsize=500)
            self._stage2_thread = threading.Thread(
                target=self._stage2_worker,
                daemon=True,
                name='Stage2Worker'
            )
            self._stage2_thread.start()

            # Thread pool and fetch-lock created in initialize() on the worker thread.

            # Option chain: stores live tick data for all subscribed options
            self._option_chain_lock = threading.Lock()

            # Initialize option chain in state
            with self._option_chain_lock:
                state = state_manager.get_state()
                if not safe_hasattr(state, "option_chain") or state.option_chain is None:
                    state.option_chain = {}

            # Number of ITM and OTM strikes to subscribe on each side of ATM
            self._chain_itm = 3
            self._chain_otm = 3

            # Add should_stop flag and event for graceful shutdown
            self.should_stop = False
            self._stop_event = threading.Event()

            # Add market status tracking
            self._market_status_check_interval = 60  # Check market status every 60 seconds
            self._last_market_status_check = 0
            self._market_is_open = None  # None = unknown, True/False = known
            self._backtest_mode = self._is_backtest_mode()

            # FIX: Add tick sequence validation
            self._last_tick_seq: Dict[str, int] = {}
            self._last_tick_time: Dict[str, datetime] = {}

            # FIX: Indicator cache to avoid recomputation on every tick
            self._indicator_cache: Dict[str, Dict[str, Any]] = {}
            self._last_bar_times: Dict[str, datetime] = {}

            logger.info("TradingApp initialized successfully with all features")

        except Exception as e:
            logger.critical(f"[TradingApp.__init__] Initialization failed: {e}", exc_info=True)
            # Re-raise to ensure caller knows initialization failed
            raise

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.config = None
        self.broker = None
        self.trade_config = None
        self.profit_loss_config = None
        self.strategy_manager = None
        self.signal_engine = None
        self.detector = None
        self.executor = None
        self.monitor = None
        self.risk_manager = None
        self.notifier = None
        self.mtf_filter = None
        self.ws = None
        self._fetch_executor = None
        self._fetch_lock = threading.Lock()
        self._fetch_in_progress: bool = False
        self._tick_queue = None
        self._stage2_thread = None
        self._option_chain_lock = None
        self._chain_itm = 5
        self._chain_otm = 5
        self.trading_mode_setting = None  # TradingModeSetting — holds paper/live/backtest flag
        self.should_stop = False
        self._stop_event = threading.Event()
        self._cleanup_done = False
        self._token_expired_error = None  # Set by thread-pool workers on TokenExpiredError

        # Market status tracking
        self._market_status_check_interval = 60
        self._last_market_status_check = 0
        self._market_is_open = None
        self._backtest_mode = False
        # Set to True by update_market_state when a 1-min bar is completed.
        # Consumed (reset to False) by evaluate_trend_and_decision to gate
        # the heavy (indicator) recomputation path.
        self._last_bar_completed = False

        # FIX: Tick validation
        self._last_tick_seq = {}
        self._last_tick_time = {}

        # FIX: Indicator cache
        self._indicator_cache = {}
        self._last_bar_times = {}

    def initialize(self) -> bool:
        """
        Perform all network/broker initialisation on the WORKER THREAD.

        FIX-6: BrokerFactory.create() and downstream objects (WebSocket,
        OrderExecutor, PositionMonitor, Notifier) are moved here from __init__
        so they run on TradingThread's worker thread, not on the GUI thread.

        Called by TradingThread.run() before self.trading_app.run().

        Returns:
            bool: True if initialisation succeeded, False on hard failure.
        """
        try:
            self.broker = BrokerFactory.create(
                state=state_manager.get_state(),
                broker_setting=self._broker_setting
            )

            self.trade_config = DailyTradeSetting()
            self.profit_loss_config = ProfitStoplossSetting()

            state_manager.get_state().cancel_pending_trade = self.cancel_pending_trade

            self.strategy_manager = StrategyManager()
            self.signal_engine = self._create_signal_engine()
            self.detector = TrendDetector(config=self.config, signal_engine=self.signal_engine)
            self.executor = OrderExecutor(broker_api=self.broker, config=self.config)
            self._apply_trading_mode_to_executor()
            self.monitor = PositionMonitor()
            self.notifier = Notifier(self.config)

            # FEATURE 1: Risk Manager
            self.risk_manager = RiskManager()
            self.risk_manager.risk_breach.connect(
                lambda reason: (
                    self.executor.exit_position() if (
                        self.executor and
                        state_manager.get_state().current_position is not None
                    ) else None,
                    self.stop(),
                    self.notifier.notify_risk_breach(reason),
                )
            )

            # FEATURE 6: Multi-Timeframe Filter
            self.mtf_filter = MultiTimeframeFilter(self.broker)

            # Inject dependencies into executor
            self.executor.risk_manager = self.risk_manager
            self.executor.notifier = self.notifier
            self.executor.on_trade_closed_callback = self._on_trade_closed

            # Thread pool for history fetching (kept separate from tick processing)
            self._fetch_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="TradingApp"
            )

            # Initialize candle store manager with broker
            candle_store_manager.initialize(self.broker)

            self.ws = WebSocketManager(
                broker=self.broker,
                on_message_callback=self.on_message,
                symbols=state_manager.get_state().all_symbols or [],
            )
            self.ws.on_disconnect_callback = lambda: self.notifier.notify_ws_disconnect()
            self.ws.on_reconnect_callback = lambda: self.notifier.notify_ws_reconnected()

            self._backtest_mode = self._is_backtest_mode()

            logger.info("TradingApp.initialize() completed successfully")
            return True

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.critical(f"[TradingApp.initialize] Failed: {e}", exc_info=True)
            raise

    def create_broker_only(self) -> bool:
        """
        Lightweight broker-only initialisation for pre-start chart loading.

        Creates the broker (token validation + session) without standing up
        WebSocket, OrderExecutor, RiskManager, or any other trading components.
        Safe to call on a background thread from _init_trading_app so the chart
        can display historical data before the user clicks Start.

        Called by TradingGUI._init_trading_app_bg() on a daemon thread.

        Returns:
            True on success.  Raises TokenExpiredError on expired token.
        """
        try:
            self.broker = BrokerFactory.create(
                state=state_manager.get_state(),
                broker_setting=self._broker_setting
            )
            # Minimal supporting objects needed by chart / candle store fetch
            candle_store_manager.initialize(self.broker)
            self._backtest_mode = self._is_backtest_mode()
            logger.info("TradingApp.create_broker_only() completed")
            return True
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[TradingApp.create_broker_only] Failed: {e}", exc_info=True)
            raise

    def _apply_trading_mode_to_executor(self) -> None:
        """
        Propagate the paper/live mode from TradingModeSetting into:
          1. state.trading_mode / state.is_paper_mode  — read by OrderExecutor
          2. broker.paper_mode                         — prevents live API calls in paper mode

        BUG-FIX A: The original code set executor.paper_mode which does not exist on
        OrderExecutor.  OrderExecutor reads state.is_paper_mode (via state_manager),
        so we must write the mode into the state object.

        BUG-FIX B: The original code defaulted is_paper=False (LIVE) when
        trading_mode_setting is None. Unknown state must default to PAPER (safe).

        BUG-FIX C: Called AFTER apply_settings_to_state() in initialize_market_state()
        so the state is already initialised — but also called here (in initialize())
        so the executor has the correct mode from the moment it is created.
        """
        try:
            import BaseEnums as _BE

            # Fail-safe default: PAPER (never accidentally go live)
            if self.trading_mode_setting is None:
                is_paper = True
                mode_str = _BE.PAPER
                logger.warning(
                    "[TradingApp] trading_mode_setting is None — defaulting to PAPER (safe). "
                    "Pass trading_mode_var to TradingApp() to enable live trading."
                )
            else:
                is_live = self.trading_mode_setting.is_live()
                is_paper = not is_live
                mode_str = _BE.LIVE if is_live else _BE.PAPER

            # ── 1. Write into TradeState so OrderExecutor reads the correct value ──
            state = state_manager.get_state()
            if state is not None:
                state.trading_mode = mode_str          # sets _trading_mode + _is_paper_mode atomically
                logger.info(
                    f"[TradingApp] state.trading_mode = {mode_str!r}, "
                    f"state.is_paper_mode = {state.is_paper_mode}"
                )

            # ── 2. Set broker paper_mode so it skips real API calls in paper mode ──
            if self.broker and safe_hasattr(self.broker, 'paper_mode'):
                self.broker.paper_mode = is_paper
                logger.info(f"[TradingApp] broker.paper_mode set to {is_paper}")

            logger.info(
                f"[TradingApp] Trading mode applied: {'PAPER' if is_paper else 'LIVE'} "
                f"(setting={safe_getattr(self.trading_mode_setting, 'mode', 'N/A')})"
            )
        except Exception as e:
            logger.error(f"[TradingApp._apply_trading_mode_to_executor] Failed: {e}", exc_info=True)

    @property
    def is_paper_mode(self) -> bool:
        """True when the app is running in paper or backtest mode."""
        try:
            if self.trading_mode_setting is None:
                return False
            return not self.trading_mode_setting.is_live()
        except Exception:
            return False

    def _is_backtest_mode(self) -> bool:
        """Check if we're in backtest mode."""
        if self.trading_mode_setting is None:
            return False
        from gui.trading_mode.TradingModeSetting import TradingMode
        _m = safe_getattr(self.trading_mode_setting, 'mode', None)
        return _m == TradingMode.BACKTEST

    def _check_market_status(self) -> bool:
        """
        Check if market is open, with caching to avoid repeated checks.
        Returns True if market is open, False otherwise.
        """
        try:
            # In backtest mode, always return True (simulate market open)
            if self._backtest_mode:
                return True

            now = time.time()

            # Refresh cache periodically
            if (self._last_market_status_check == 0 or
                    now - self._last_market_status_check > self._market_status_check_interval):

                # Use broker's market status check
                if safe_hasattr(self, 'broker') and self.broker:
                    self._market_is_open = self.broker.is_market_open()
                else:
                    # Fallback to Utils
                    from Utils.Utils import Utils
                    self._market_is_open = Utils.is_market_open()

                self._last_market_status_check = now
                logger.debug(f"Market status checked: {'OPEN' if self._market_is_open else 'CLOSED'}")

            return self._market_is_open if self._market_is_open is not None else False

        except Exception as e:
            logger.error(f"Error checking market status: {e}")
            return False

    def _create_signal_engine(self) -> DynamicSignalEngine:
        """Create signal engine with active strategy config"""
        try:
            engine = DynamicSignalEngine()

            # Rule 6: Safe access to strategy manager
            if self.strategy_manager:
                active_config = self.strategy_manager.get_active_engine_config()
                if active_config:
                    engine.from_dict(active_config)
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
                if safe_hasattr(self.detector, 'set_signal_engine') and self.detector:
                    self.detector.set_signal_engine(self.signal_engine)

        except Exception as e:
            logger.error(f"[TradingApp.reload_signal_engine] Failed: {e}", exc_info=True)

    def run(self) -> None:
        self._token_expired_error = None  # Reset on each run
        try:
            # Check if we should stop before starting
            if self.should_stop:
                logger.info("Stop requested before run, exiting")
                return

            self.initialize_market_state()
            self.subscribe_market_data()

            # Keep the trading thread alive while WebSocket runs in background.
            logger.info("Trading thread entering keep-alive loop (WebSocket running in background)")
            while not self.should_stop:
                self._stop_event.wait(timeout=1.0)

            logger.info("Trading thread keep-alive loop exited (should_stop=True)")

            # If a thread-pool worker set _token_expired_error, re-raise it
            if self._token_expired_error is not None:
                raise self._token_expired_error

        except TokenExpiredError as e:
            logger.error(f"Token expired during run: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.critical(f"Unhandled exception during run: {e!r}", exc_info=True)
            raise

    def stop(self):
        """Stop the trading app gracefully."""
        self.should_stop = True
        self._stop_event.set()
        logger.info("TradingApp stop requested")

    def initialize_market_state(self) -> None:
        try:
            self.apply_settings_to_state()
            # Re-apply trading mode AFTER apply_settings_to_state() so state is
            # fully initialised before we write trading_mode into it.
            self._apply_trading_mode_to_executor()
            state = state_manager.get_state()

            # Get initial price for derivative
            if self.broker and safe_hasattr(self.broker, 'get_option_current_price'):
                try:
                    state.derivative_current_price = self.broker.get_option_current_price(
                        state.derivative
                    )
                except TokenExpiredError:
                    raise
                except Exception as price_error:
                    logger.error(f"Failed to get initial price: {price_error!r}", exc_info=True)
            else:
                logger.warning("Broker doesn't support get_option_current_price")

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[TradingApp.initialize_market_state] Failed: {e!r}", exc_info=True)

    def _schedule_market_open_connection(self):
        """Schedule WebSocket connection for when market opens."""
        try:
            # Skip in backtest mode
            if self._backtest_mode:
                return

            # Calculate time until market opens
            now = datetime.now()
            market_open = self.broker.get_market_start_time() if safe_hasattr(self.broker,
                                                                              'get_market_start_time') else None

            if market_open and market_open > now:
                wait_seconds = (market_open - now).total_seconds()

                # Don't wait more than 12 hours
                if 0 < wait_seconds < 43200:  # 12 hours max
                    logger.info(f"Scheduling WebSocket connection in {wait_seconds:.0f} seconds (at market open)")
                    Timer(wait_seconds, self._connect_at_market_open).start()
                    return

            # If we can't schedule, just retry after a reasonable interval
            logger.info("Scheduling WebSocket connection retry in 5 minutes")
            Timer(300, self._connect_at_market_open).start()  # Retry in 5 minutes

        except Exception as e:
            logger.error(f"Error scheduling market open connection: {e}")

    def _connect_at_market_open(self):
        """Called when market opens or on retry schedule."""
        try:
            if self.should_stop:
                return

            # Re-check market status
            if self._check_market_status():
                logger.info("Market is now open - connecting WebSocket")
                self.subscribe_market_data()
            else:
                # Market still closed, reschedule
                logger.info("Market still closed - rescheduling connection check")
                self._schedule_market_open_connection()

        except Exception as e:
            logger.error(f"Error in scheduled connection: {e}")

    def subscribe_market_data(self) -> None:
        try:
            # Skip WebSocket connection in backtest mode
            if self._backtest_mode:
                logger.info("Backtest mode - skipping WebSocket connection")
                return

            # Check if market is open before connecting
            if not self._check_market_status():
                logger.info("Market is closed - WebSocket connection deferred until market opens")
                # Schedule a retry when market opens
                self._schedule_market_open_connection()
                return

            state = state_manager.get_state()
            # Rule 6: Validate required attributes
            if state.derivative_current_price is None:
                logger.warning("derivative_current_price is None, cannot subscribe to market data")
                return

            spot = state.derivative_current_price
            expiry = state.expiry
            derivative = state.derivative
            if not derivative:
                logger.warning(f"Missing derivative ({derivative})")
                return

            state.put_option = self.broker.build_option_symbol(
                underlying=derivative,
                spot_price=spot,
                option_type="PE",
                weeks_offset=expiry,
                lookback_strikes=state.put_lookback,
            )

            state.call_option = self.broker.build_option_symbol(
                underlying=derivative,
                spot_price=spot,
                option_type="CE",
                weeks_offset=expiry,
                lookback_strikes=state.call_lookback,
            )

            # Build option chain: _chain_itm ITM + ATM + _chain_otm OTM on each side
            call_chain = self.broker.build_option_chain(
                underlying=derivative, spot_price=spot,
                option_type="CE", weeks_offset=expiry,
                itm=self._chain_itm, otm=self._chain_otm)

            put_chain = self.broker.build_option_chain(
                underlying=derivative, spot_price=spot,
                option_type="PE", weeks_offset=expiry,
                itm=self._chain_itm, otm=self._chain_otm)

            # Initialize chain storage with zero-state entries
            if self._option_chain_lock:
                with self._option_chain_lock:
                    new_chain: Dict[str, Dict[str, Optional[float]]] = {}
                    for sym in call_chain + put_chain:
                        full_sym = self.symbol_full(sym)
                        if full_sym:
                            new_chain[full_sym] = state.option_chain.get(
                                full_sym, {"ltp": None, "ask": None, "bid": None}
                            )
                    state.option_chain = new_chain

            logger.info(
                f"[subscribe_market_data] Chain built: {len(call_chain)} CE + {len(put_chain)} PE "
                f"| ATM CE: {state.call_option} | ATM PE: {state.put_option}"
            )

            # Compose full symbol list: derivative + all chain symbols
            chain_symbols = list(state.option_chain.keys()) if state.option_chain else []
            state.all_symbols = list(filter(None, [
                self.symbol_full(state.derivative),
                *chain_symbols
            ]))

            # Connect WebSocket
            if self.ws:
                self.ws.symbols = state.all_symbols
                self.ws.connect()
            else:
                logger.error("WebSocket manager not initialized")

        except Exception as ws_error:
            logger.error(f"WebSocket connection/subscription failed: {ws_error!r}", exc_info=True)

    def on_message(self, message: dict) -> None:
        """
        Two-stage message processing:
        Stage 1 (fast): Update market state immediately on WS thread
        Stage 2 (slow): Push to queue for background processing
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
            ask_price = message.get("ask")
            bid_price = message.get("bid")
            sequence = message.get("sequence")  # If broker provides sequence numbers

            if ltp is None:
                logger.warning(f"LTP missing for symbol {symbol}. Message: {message}")
                return

            volume = message.get("ltq", 0) or 0

            # FIX: Validate tick before processing
            if not self._validate_tick(symbol, ltp, sequence):
                return

            self.update_market_state(symbol, ltp, ask_price, bid_price, volume, sequence)

            # Push to queue for Stage 2 processing (non-blocking)
            try:
                self._tick_queue.put_nowait('tick')
            except queue.Full:
                # Queue is bounded - if full, we drop the tick (oldest will be processed)
                logger.debug("Tick queue full, dropping tick")

        except Exception as e:
            logger.error(f"Exception in on_message stage 1: {e!r}, Message: {message}", exc_info=True)

    def _validate_tick(self, symbol: str, ltp: float, sequence: Optional[int] = None) -> bool:
        """
        Validate tick for out-of-order and stale data.
        Returns True if tick should be processed.
        """
        try:
            # Basic price validation
            if ltp <= 0:
                logger.debug(f"Invalid LTP: {ltp} for {symbol}")
                return False

            # Sequence validation (if provided)
            if sequence is not None:
                last_seq = self._last_tick_seq.get(symbol, -1)
                if sequence <= last_seq:
                    logger.debug(f"Out-of-order tick for {symbol}: {sequence} <= {last_seq}")
                    return False
                self._last_tick_seq[symbol] = sequence

            # Stale data detection (more than 5 seconds old)
            now = datetime.now()
            last_time = self._last_tick_time.get(symbol)
            if last_time and (now - last_time).total_seconds() > 5:
                logger.warning(f"Large tick gap for {symbol}: {(now - last_time).total_seconds():.1f}s")

            self._last_tick_time[symbol] = now

            # Price sanity check (can't move >20% in one tick)
            state = state_manager.get_state()
            if symbol == self.symbol_full(state.derivative):
                last_price = state.derivative_current_price
                if last_price > 0 and abs(ltp - last_price) / last_price > 0.2:
                    logger.warning(f"Price spike detected: {last_price:.2f} -> {ltp:.2f}")

            return True

        except Exception as e:
            logger.error(f"Tick validation error: {e}", exc_info=True)
            return True  # Process anyway on validation error

    def _stage2_worker(self):
        """
        Dedicated worker thread for Stage 2 processing.
        Uses snapshots to avoid holding state locks.
        """
        logger.info("Stage 2 worker thread started")

        # Track consecutive empty ticks for backtest/idle detection
        empty_tick_count = 0
        max_empty_ticks = 10  # After 10 empty ticks, slow down polling

        while not self.should_stop:
            try:
                # In backtest mode, slow down processing
                if self._backtest_mode:
                    time.sleep(0.5)  # Backtest mode - process slower

                # Wait for a tick with timeout (allows checking should_stop)
                tick_received = False
                try:
                    self._tick_queue.get(timeout=1.0)
                    tick_received = True
                    empty_tick_count = 0  # Reset counter on successful tick
                except queue.Empty:
                    empty_tick_count += 1

                    # If market is closed and we're getting no ticks, slow down polling
                    if not self._backtest_mode and not self._check_market_status() and empty_tick_count > max_empty_ticks:
                        time.sleep(5.0)  # Sleep longer when market closed and no data
                    continue

                # Drain any queued ticks - process only the latest state once
                drained = 0
                while not self._tick_queue.empty():
                    try:
                        self._tick_queue.get_nowait()
                        drained += 1
                    except queue.Empty:
                        break

                if drained > 0:
                    logger.debug(f"Drained {drained} queued ticks")

                # Skip processing if market is closed and we're not in backtest
                if not self._backtest_mode and not self._check_market_status():
                    logger.debug("Market closed - skipping stage 2 processing")
                    continue

                # FIX: Take a snapshot BEFORE any processing - this is the ONLY lock acquisition
                snapshot = state_manager.get_position_snapshot()

                # Process using snapshot (no locks needed)
                self._process_snapshot_stage2(snapshot)

            except queue.Empty:
                # Timeout - just continue loop
                continue
            except TokenExpiredError:
                logger.critical("Token expired in stage 2 worker")
                self._token_expired_error = TokenExpiredError("Token expired")
                self.should_stop = True
                self._stop_event.set()
                break
            except Exception as e:
                logger.error(f"Stage2Worker error: {e}", exc_info=True)
                # Brief pause to avoid tight error loop
                time.sleep(0.1)

        logger.info("Stage 2 worker thread stopped")

    def _process_snapshot_stage2(self, snapshot: Dict[str, Any]) -> None:
        """
        Process using a snapshot - no locks needed.
        """
        try:
            # Check if we should stop
            if self.should_stop:
                logger.debug("Stop requested, skipping stage 2 processing")
                return

            # FEATURE 5: Update unrealized P&L for DailyPnLWidget using snapshot
            self._update_unrealized_pnl_from_snapshot(snapshot)

            # Run all monitoring and decision logic with snapshot
            if safe_hasattr(self, 'monitor') and self.monitor:
                try:
                    self.monitor.update_trailing_sl_tp_from_snapshot(self.broker, snapshot)
                except TokenExpiredError:
                    raise
                except Exception as monitor_error:
                    logger.error(f"Error in monitor.update_trailing_sl_tp: {monitor_error}", exc_info=True)

            try:
                self.evaluate_trend_from_snapshot(snapshot)
            except Exception as trend_error:
                logger.error(f"Error in evaluate_trend_and_decision: {trend_error}", exc_info=True)

            try:
                self.monitor_active_trade_status_from_snapshot(snapshot)
            except Exception as trade_error:
                logger.error(f"Error in monitor_active_trade_status: {trade_error}", exc_info=True)

            try:
                self.monitor_profit_loss_status_from_snapshot(snapshot)
            except Exception as pnl_error:
                logger.error(f"Error in monitor_profit_loss_status: {pnl_error}", exc_info=True)

        except TokenExpiredError:
            logger.critical("Token expired in stage 2 processing")
            raise
        except Exception as e:
            logger.error(f"Exception in message stage 2 processing: {e!r}", exc_info=True)

    def _update_unrealized_pnl_from_snapshot(self, snapshot: Dict[str, Any]):
        """
        Update unrealized P&L using snapshot.
        """
        try:
            if (snapshot.get('current_position') is not None and
                    snapshot.get('current_buy_price') is not None and
                    snapshot.get('current_price') is not None and
                    snapshot.get('positions_hold', 0) > 0):
                unrealized = (snapshot['current_price'] - snapshot['current_buy_price']) * snapshot['positions_hold']

                # Update state directly (small, atomic operation)
                state = state_manager.get_state()
                state.current_pnl = unrealized
        except Exception as e:
            logger.error(f"Error updating unrealized P&L: {e}", exc_info=True)

    def _on_trade_closed(self, pnl: float, is_winner: bool):
        """
        FEATURE 5: Callback for DailyPnLWidget when a trade is closed.
        """
        try:
            logger.info(f"Trade closed - P&L: ₹{pnl:.2f}, Winner: {is_winner}")
        except Exception as e:
            logger.error(f"Error in _on_trade_closed: {e}", exc_info=True)

    def update_market_state(self, symbol: str, ltp: float, ask_price: float, bid_price: float,
                            volume: float = 0.0, sequence: Optional[int] = None) -> None:
        """
        Single source of truth: every price in state is read back from the
        CandleStore after the tick is pushed there.  Nothing reads raw ltp
        directly — the store is always authoritative.

        Flow per tick
        ─────────────
        1. Push the tick into the appropriate CandleStore.
        2. Read the current close back from that store.
        3. Write the store-sourced price into state.

        For option ticks the tick price used to push is the mid/ask/bid that
        the broker supplies (same as before), but state.put/call_current_close
        is then set from store.get_current_close(), keeping everything
        consistent with the OHLCV data that the signal engine sees.

        push_tick() returns bar_completed=True when a new 1-min bar is sealed.
        We surface this via _last_bar_completed so evaluate_trend_and_decision
        knows whether to schedule a heavy (indicator) recomputation.
        """
        try:
            state = state_manager.get_state()

            if not symbol or ltp is None:
                logger.warning(f"Invalid update_market_state params: symbol={symbol}, ltp={ltp}")
                return

            full_symbol = self.symbol_full(symbol)
            logger.debug(f"Tick received - Symbol: {full_symbol}, LTP: {ltp}, Ask: {ask_price}, Bid: {bid_price}")

            # ── Derivative (index) tick ────────────────────────────────────────
            deriv_full = self.symbol_full(state.derivative)
            if full_symbol == deriv_full:
                derivative = state.derivative
                if derivative:
                    try:
                        bar_completed = candle_store_manager.push_tick(
                            derivative, ltp, volume=volume
                        )
                        # Signal the evaluate loop that a new bar just closed
                        if bar_completed:
                            self._last_bar_completed = True

                        # Read authoritative price back from the store
                        store = candle_store_manager.get_store(derivative)
                        store_price = store.get_current_close()
                        old_price = state.derivative_current_price
                        state.derivative_current_price = store_price if store_price is not None else ltp
                        logger.debug(
                            f"✅ Derivative price (from store): {old_price} -> "
                            f"{state.derivative_current_price}"
                            + (" [BAR CLOSED]" if bar_completed else "")
                        )
                    except Exception as e:
                        logger.debug(f"CandleStore push/read error for derivative: {e}")
                        # Fallback: keep raw ltp so state is never stale
                        state.derivative_current_price = ltp
                return

            # ── Option chain tick ──────────────────────────────────────────────
            if self._option_chain_lock and safe_hasattr(state, "option_chain"):
                with self._option_chain_lock:
                    if full_symbol in state.option_chain:
                        state.update_option_chain_symbol(full_symbol, {
                            "ltp": ltp,
                            "ask": ask_price,
                            "bid": bid_price,
                        })
                        logger.debug(f"✅ Updated option chain for {full_symbol}: LTP={ltp}")
                    else:
                        logger.debug(
                            f"Symbol {full_symbol} not in option chain. "
                            f"Available: {list(state.option_chain.keys())}"
                        )

            # ── ATM call / put option ticks ────────────────────────────────────
            use_ask = not bool(state.current_position)
            atm_put_sym = self.symbol_full(state.put_option)
            atm_call_sym = self.symbol_full(state.call_option)

            # The price we push into the option's candle store is the
            # trade-relevant price: ask when flat (entry), bid when in position
            # (exit). This matches what was previously stored directly.
            option_price = ask_price if use_ask else bid_price

            if full_symbol == atm_put_sym and state.put_option:
                try:
                    tick_price = option_price if option_price is not None else ltp
                    candle_store_manager.push_tick(state.put_option, tick_price, volume=volume)
                    store = candle_store_manager.get_store(state.put_option)
                    store_price = store.get_current_close()
                    old_put = state.put_current_close
                    state.put_current_close = store_price if store_price is not None else tick_price
                    logger.debug(f"✅ PUT price (from store): {old_put} -> {state.put_current_close}")
                except Exception as e:
                    logger.debug(f"CandleStore push/read error for PUT: {e}")
                    if option_price is not None:
                        state.put_current_close = option_price

            elif full_symbol == atm_call_sym and state.call_option:
                try:
                    tick_price = option_price if option_price is not None else ltp
                    candle_store_manager.push_tick(state.call_option, tick_price, volume=volume)
                    store = candle_store_manager.get_store(state.call_option)
                    store_price = store.get_current_close()
                    old_call = state.call_current_close
                    state.call_current_close = store_price if store_price is not None else tick_price
                    logger.debug(f"✅ CALL price (from store): {old_call} -> {state.call_current_close}")
                except Exception as e:
                    logger.debug(f"CandleStore push/read error for CALL: {e}")
                    if option_price is not None:
                        state.call_current_close = option_price

            # ── Sync current_price for open position P&L ──────────────────────
            # current_price is always sourced from the relevant option store,
            # already updated above.
            if state.current_position:
                cp = state.current_position
                if cp == BaseEnums.CALL and state.call_current_close is not None:
                    old_current = state.current_price
                    state.current_price = state.call_current_close
                    if old_current != state.current_price:
                        logger.debug(f"current_price (CALL): {old_current} -> {state.current_price}")
                elif cp == BaseEnums.PUT and state.put_current_close is not None:
                    old_current = state.current_price
                    state.current_price = state.put_current_close
                    if old_current != state.current_price:
                        logger.debug(f"current_price (PUT): {old_current} -> {state.current_price}")

        except Exception as e:
            logger.error(f"[TradingApp.update_market_state] Failed for symbol {symbol}: {e}", exc_info=True)

    def evaluate_trend_and_decision(self) -> None:
        """
        Legacy method - maintained for compatibility.
        Now uses snapshot internally.
        """
        try:
            snapshot = state_manager.get_position_snapshot()
            self.evaluate_trend_from_snapshot(snapshot)
        except Exception as e:
            logger.error(f"Error in evaluate_trend_and_decision: {e}", exc_info=True)

    def evaluate_trend_from_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Two-tier evaluation strategy using snapshot.
        """
        try:
            if self.should_stop:
                return

            state = state_manager.get_state()

            # ── Tier 1: new bar just closed → schedule full recalculation ─────
            bar_just_completed = self._last_bar_completed
            if bar_just_completed:
                self._last_bar_completed = False  # consume the flag immediately

                # Also trigger if history is simply stale (handles startup / gaps)
                history_stale = not Utils.is_history_updated(
                    last_updated=state.last_index_updated,
                    interval=state.interval
                )

                # FIX-5: Atomic check-and-set with lock — prevents two concurrent
                # ticks from both submitting a fetch in the same millisecond.
                _submitted = False
                with self._fetch_lock:
                    if not self._fetch_in_progress and self._fetch_executor:
                        self._fetch_in_progress = True
                        _submitted = True
                if _submitted:
                    try:
                        position_at_submit = state.current_position
                        self._fetch_executor.submit(
                            self._fetch_history_and_detect, position_at_submit
                        )
                        logger.debug("Scheduled heavy indicator recomputation (bar completed)")
                    except Exception as submit_err:
                        logger.error(f"Failed to submit history fetch: {submit_err}", exc_info=True)
                        with self._fetch_lock:
                            self._fetch_in_progress = False
                elif not self._fetch_executor:
                    logger.error("Thread pool not available for history fetch")

            else:
                # Even without a new bar, schedule if history is stale
                # (covers app startup where no tick has completed a bar yet)
                if not Utils.is_history_updated(
                        last_updated=state.last_index_updated,
                        interval=state.interval
                ):
                    # FIX-5: same atomic check-and-set pattern
                    _submitted2 = False
                    with self._fetch_lock:
                        if not self._fetch_in_progress and self._fetch_executor:
                            self._fetch_in_progress = True
                            _submitted2 = True
                    if _submitted2:
                        try:
                            position_at_submit = state.current_position
                            self._fetch_executor.submit(
                                self._fetch_history_and_detect, position_at_submit
                            )
                        except Exception as submit_err:
                            logger.error(f"Failed to submit history fetch: {submit_err}", exc_info=True)
                            with self._fetch_lock:
                                self._fetch_in_progress = False

            # ── Tier 2: tick-level close-price gate ───────────────────────────
            # Re-evaluates column-type rule sides (e.g. "close") against the
            # current candle-store close on every tick, without recomputing
            # heavy indicator series.
            self._evaluate_tick_close_gate(state)

            state.trend = self.determine_trend_from_signals()

            if safe_hasattr(self, 'executor') and self.executor:
                self.execute_based_on_trend()

        except TokenExpiredError:
            raise
        except Exception as trend_error:
            logger.info(f"Trend detection or decision logic error: {trend_error!r}", exc_info=True)

    def _evaluate_tick_close_gate(self, state) -> None:
        """
        Tier 2: re-check only the rules that compare against a price column
        (type=='column', e.g. close) on every tick.
        """
        try:
            if not state.dynamic_signals_active:
                return
            if not self.signal_engine or not self.detector:
                return

            # Fast path: skip if no rules use a column comparison
            if not self._engine_has_column_rules():
                return

            derivative = state.derivative
            if not derivative:
                return

            store = candle_store_manager.get_store(derivative)
            current_close = store.get_current_close()
            if current_close is None:
                return

            # Get the cached resampled DF — no broker call, just from store
            try:
                target_minutes = int(state.interval or "1")
            except (TypeError, ValueError):
                target_minutes = 1

            df = store.resample(target_minutes)
            if df is None or df.empty:
                return

            # Patch only the last row's close with the live tick close so
            # column comparisons reflect the current price while completed-bar
            # indicator columns stay exactly as computed during Tier 1.
            df = df.copy()
            df.loc[df.index[-1], "close"] = current_close

            result = self.signal_engine.evaluate(df, state.current_position)
            if result and result.get("available"):
                # Update state — the detector method handles all state fields
                if hasattr(self.detector, '_update_state_with_signal_result'):
                    self.detector._update_state_with_signal_result(result)
                else:
                    state.option_signal_result = result
                logger.debug(
                    f"[TickGate] signal={result.get('signal_value')} "
                    f"close={current_close:.2f}"
                )

        except Exception as e:
            logger.debug(f"[_evaluate_tick_close_gate] {e}", exc_info=True)

    def _engine_has_column_rules(self) -> bool:
        """Return True if any rule side uses type=='column' (e.g. close price)."""
        try:
            if not self.signal_engine:
                return False
            for group_cfg in self.signal_engine.config.values():
                for rule in group_cfg.get("rules", []):
                    for side_key in ("lhs", "rhs"):
                        side = rule.get(side_key, {})
                        if isinstance(side, dict) and side.get("type") == "column":
                            return True
            return False
        except Exception:
            return False

    def _fetch_history_and_detect(self, position_at_submit=None) -> None:
        """
        Runs on thread pool — fetches history and updates trend state.
        Uses CandleStoreManager as the single source of truth for OHLCV data.

        FIX: Added timeout protection and caching.
        """
        try:
            if self.should_stop:
                logger.debug("Stop requested, skipping history fetch")
                return

            state = state_manager.get_state()
            derivative = state.derivative
            interval = state.interval or "1"

            # Use the snapshotted position for consistency.  Fall back to the
            # live value when called without a snapshot (e.g. from tests).
            eval_position = position_at_submit if position_at_submit is not None \
                else state.current_position

            try:
                target_minutes = int(interval)
            except (TypeError, ValueError):
                target_minutes = 1

            # Check cache before fetching
            cache_key = f"{derivative}_{interval}"
            last_bar_time = candle_store_manager.last_bar_time(derivative)
            last_compute = self._last_bar_times.get(cache_key)

            if last_compute == last_bar_time and cache_key in self._indicator_cache:
                # Use cached result
                state.derivative_trend = self._indicator_cache[cache_key]
                logger.debug(f"Using cached trend for {derivative}")
                return

            # Get stores from candle_store_manager
            def _fetch_and_resample(symbol: str) -> Optional[pd.DataFrame]:
                """Fetch 1-min bars into CandleStore and return resampled DataFrame."""
                if not symbol:
                    return None

                # Get or create store
                store = candle_store_manager.get_store(symbol)

                # Fetch data if store is empty
                if store.is_empty():
                    ok = store.fetch(days=5, broker_type=self.broker.broker_type)
                    if not ok or store.is_empty():
                        return None

                # Return resampled data
                return store.resample(target_minutes)

            # ── Fetch derivative (index) ───────────────────────────────────────
            if self.broker:
                try:
                    df = _fetch_and_resample(derivative)
                    if df is not None and not df.empty:
                        logger.debug(
                            f"[TradingApp] {derivative} history: "
                            f"{len(df)} bars at {target_minutes}-min "
                            f"(resampled from 1-min store)"
                        )
                except TokenExpiredError:
                    raise
                except Exception as e:
                    logger.error(f"Failed to fetch derivative history: {e}", exc_info=True)

                # ── Fetch call option ──────────────────────────────────────────
                try:
                    call_opt = state.call_option
                    _fetch_and_resample(call_opt)
                except TokenExpiredError:
                    raise
                except Exception as e:
                    logger.error(f"Failed to fetch call data: {e}", exc_info=True)

                # ── Fetch put option ───────────────────────────────────────────
                try:
                    put_opt = state.put_option
                    _fetch_and_resample(put_opt)
                except TokenExpiredError:
                    raise
                except Exception as e:
                    logger.error(f"Failed to fetch put data: {e}", exc_info=True)

                # ── Update last_index_updated from derivative CandleStore ──────
                deriv_store = candle_store_manager.get_store(derivative)
                deriv_df = deriv_store.resample(target_minutes) if not deriv_store.is_empty() else None

                if deriv_df is not None and not deriv_df.empty:
                    try:
                        state.last_index_updated = deriv_df["time"].iloc[-1]
                    except (KeyError, IndexError, AttributeError) as e:
                        logger.error(f"Failed to get last index time: {e}", exc_info=True)

                    # ── Run trend detection ───────────────────────────────────
                    # FIX-4: Call _run_trend_detection_safe() directly instead of
                    # submitting to _fetch_executor.  We are ALREADY running inside
                    # _fetch_executor (max_workers=2).  Submitting another task to
                    # the same pool and blocking on future.result() causes a
                    # deadlock when both workers are occupied: each waits for a
                    # slot that will never free because the other worker is also
                    # waiting.  The outer submit provides thread isolation; nesting
                    # is unnecessary and dangerous.
                    if self.detector:
                        try:
                            trend_result = self._run_trend_detection_safe(
                                deriv_df, derivative, eval_position
                            )
                            state.derivative_trend = trend_result

                            # Cache the result
                            if trend_result is not None:
                                self._indicator_cache[cache_key] = trend_result
                                self._last_bar_times[cache_key] = last_bar_time

                        except Exception as e:
                            logger.error(f"Derivative trend detection failed: {e}", exc_info=True)
                            state.derivative_trend = None

                        try:
                            call_opt_sym = state.call_option
                            if call_opt_sym:
                                call_store = candle_store_manager.get_store(call_opt_sym)
                                df_call = call_store.resample(target_minutes) if not call_store.is_empty() else None
                                state.call_trend = self.detector.detect(
                                    df_call, call_opt_sym, eval_position
                                )
                            else:
                                logger.debug("call_option not yet set — skipping call trend detection")
                        except Exception as e:
                            logger.error(f"Call trend detection failed: {e}", exc_info=True)

                        try:
                            put_opt_sym = state.put_option
                            if put_opt_sym:
                                put_store = candle_store_manager.get_store(put_opt_sym)
                                df_put = put_store.resample(target_minutes) if not put_store.is_empty() else None
                                state.put_trend = self.detector.detect(
                                    df_put, put_opt_sym, eval_position
                                )
                            else:
                                logger.debug("put_option not yet set — skipping put trend detection")
                        except Exception as e:
                            logger.error(f"Put trend detection failed: {e}", exc_info=True)

                        live_position = state.current_position
                        if live_position != eval_position:
                            logger.info(
                                f"[FetchDetect] Position changed during fetch: "
                                f"{eval_position!r} → {live_position!r}. "
                                f"Re-evaluating signal with new position."
                            )
                            try:
                                deriv_store2 = candle_store_manager.get_store(derivative)
                                df_reeval = deriv_store2.resample(target_minutes) \
                                    if not deriv_store2.is_empty() else None
                                if df_reeval is not None and not df_reeval.empty:
                                    state.derivative_trend = self.detector.detect(
                                        df_reeval, derivative, live_position
                                    )
                            except Exception as reeval_err:
                                logger.error(
                                    f"Re-evaluation after position change failed: {reeval_err}",
                                    exc_info=True
                                )

                    if state.dynamic_signals_active:
                        logger.info(f"📊 Dynamic signal: {state.option_signal}")

                        if state.signal_conflict:
                            logger.warning("⚠️ Signal conflict detected - BUY_CALL and BUY_PUT both true")

                        if logger.isEnabledFor(logging.DEBUG):
                            self._log_signal_details()

        except TokenExpiredError as e:
            logger.critical(f"Token expired in history fetch: {e}", exc_info=True)
            self._token_expired_error = e
            self.should_stop = True
            if safe_hasattr(self, '_stop_event') and self._stop_event:
                self._stop_event.set()
        except Exception as e:
            logger.error(f"Error in _fetch_history_and_detect: {e!r}", exc_info=True)
        finally:
            # FIX-5: Release the fetch lock so the next bar can schedule a fetch.
            with self._fetch_lock:
                self._fetch_in_progress = False

    def _run_trend_detection_safe(self, df, symbol, position):
        """Run trend detection in isolated context."""
        try:
            return self.detector.detect(df, symbol, position)
        except Exception as e:
            logger.error(f"Detector crashed for {symbol}: {e}", exc_info=True)
            return None

    def _log_signal_details(self):
        """Log detailed signal information using state properties."""
        try:
            state = state_manager.get_state()
            if not state.option_signal_result:
                return

            snapshot = state.get_option_signal_snapshot()
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
            state = state_manager.get_state()

            if not state.dynamic_signals_active:
                return None

            signal_value = state.option_signal
            current_pos = state.current_position
            previous_pos = state.previous_position

            # ── Position-consistency guard ────────────────────────────────────
            # Check the position context the signal was computed for.
            result = state.option_signal_result
            if result and isinstance(result, dict):
                signal_pos_ctx = result.get("position_context")  # "CALL", "PUT", or None

                if current_pos is None:
                    live_pos_str = None
                else:
                    raw = getattr(current_pos, 'value', str(current_pos))
                    live_pos_str = raw.split('.')[-1].upper().strip()

                if signal_pos_ctx != live_pos_str:
                    # EXIT signals are always safe to act on regardless
                    # of position context mismatch.
                    _exit_signals = ('EXIT_CALL', 'EXIT_PUT')
                    if signal_value not in _exit_signals:
                        logger.info(
                            f"[SignalGuard] Skipping stale entry signal '{signal_value}' — "
                            f"computed for pos={signal_pos_ctx!r}, "
                            f"live pos={live_pos_str!r}. "
                            f"Waiting for next evaluate() cycle."
                        )
                        return None
                    else:
                        logger.debug(
                            f"[SignalGuard] Allowing EXIT signal '{signal_value}' despite "
                            f"context mismatch (pos_ctx={signal_pos_ctx!r}, live={live_pos_str!r})."
                        )
            # ─────────────────────────────────────────────────────────────────

            signal_conflict = state.signal_conflict
            trend = None

            logger.debug(f"Option signal: {signal_value}, conflict={signal_conflict}")

            # === EXIT Conditions ===
            if current_pos == BaseEnums.CALL:
                if signal_value in ['EXIT_CALL', 'BUY_PUT']:
                    trend = BaseEnums.EXIT_CALL
                    state.reason_to_exit = self._get_exit_reason('CALL')

            elif current_pos == BaseEnums.PUT:
                if signal_value in ['EXIT_PUT', 'BUY_CALL']:
                    trend = BaseEnums.EXIT_PUT
                    state.reason_to_exit = self._get_exit_reason('PUT')

            # === ENTRY Conditions ===
            elif current_pos is None and previous_pos is None:
                if state.should_buy_call:
                    trend = BaseEnums.ENTER_CALL
                    state.reason_to_exit = "BUY_CALL signal triggered"

                elif state.should_buy_put:
                    trend = BaseEnums.ENTER_PUT
                    state.reason_to_exit = "BUY_PUT signal triggered"

                elif state.should_hold:
                    logger.debug("HOLD signal - no entry")

                elif state.should_wait:
                    logger.debug("WAIT signal - no entry")

            elif current_pos is None and previous_pos in {BaseEnums.CALL, BaseEnums.PUT}:
                if previous_pos == BaseEnums.CALL and signal_value in ['BUY_PUT', 'EXIT_PUT']:
                    trend = BaseEnums.RESET_PREVIOUS_TRADE
                    logger.info("Reset previous CALL trade flag - opposite/reversal signal detected")

                elif previous_pos == BaseEnums.PUT and signal_value in ['BUY_CALL', 'EXIT_CALL']:
                    trend = BaseEnums.RESET_PREVIOUS_TRADE
                    logger.info("Reset previous PUT trade flag - opposite/reversal signal detected")

                # Same-direction signal continues → also reset so re-entry is allowed
                elif previous_pos == BaseEnums.CALL and signal_value == 'BUY_CALL':
                    trend = BaseEnums.RESET_PREVIOUS_TRADE
                    logger.info("Reset previous CALL trade flag - same-direction BUY_CALL signal (re-entry allowed)")

                elif previous_pos == BaseEnums.PUT and signal_value == 'BUY_PUT':
                    trend = BaseEnums.RESET_PREVIOUS_TRADE
                    logger.info("Reset previous PUT trade flag - same-direction BUY_PUT signal (re-entry allowed)")

                # Neutral signal (HOLD/WAIT) → reset to unblock fresh entry
                elif signal_value in ['HOLD', 'WAIT']:
                    trend = BaseEnums.RESET_PREVIOUS_TRADE
                    logger.info(
                        f"Reset previous {previous_pos} trade flag - neutral {signal_value} signal "
                        "(unblocking entry)"
                    )

            if trend:
                logger.info(f"📈 Determined trend: {trend} | Reason: {state.reason_to_exit}")

            return trend

        except Exception as e:
            logger.error(f"Error determining trend from signals: {e}", exc_info=True)
            return None

    def _get_exit_reason(self, position_type: str) -> str:
        """Extract exit reason from signal results."""
        try:
            state = state_manager.get_state()
            if not state.option_signal_result:
                return f"Exit triggered for {position_type}"

            rule_results = state.option_signal_result.get('rule_results', {})

            sell_signal = 'EXIT_CALL' if position_type == 'CALL' else 'EXIT_PUT'
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

    def monitor_active_trade_status_from_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Monitor active trade status using snapshot.
        """
        try:
            # Check if we should stop
            if self.should_stop:
                return

            state = state_manager.get_state()

            index_stop_loss = snapshot.get('index_stop_loss')
            current_derivative_price = snapshot.get('derivative_current_price')
            current_position = snapshot.get('current_position')
            current_trade_confirmed = snapshot.get('current_trade_confirmed', False)

            if current_trade_confirmed:
                # ── Safety exit 1: market close approaching ────────────────────
                if Utils.is_near_market_close(buffer_minutes=5):
                    if current_position:
                        logger.info("Market close approaching. Exiting active position.")
                        state.reason_to_exit = "Auto-exit before market close."
                        if safe_hasattr(self, 'executor') and self.executor:
                            try:
                                success = self.executor.exit_position()
                                if not success:
                                    logger.error("Exit failed near market close")
                            except TokenExpiredError:
                                raise
                            except Exception as e:
                                logger.error(f"Exit error near market close: {e}", exc_info=True)
                        return

                # ── Safety exit 2: index stop-loss (derivative price) ──────────
                if current_position == BaseEnums.PUT:
                    if (index_stop_loss is not None
                            and current_derivative_price is not None
                            and current_derivative_price >= index_stop_loss):
                        state.reason_to_exit = "PUT exit: Derivative crossed above ST (safety)"
                        if safe_hasattr(self, 'executor') and self.executor:
                            try:
                                success = self.executor.exit_position()
                                if not success:
                                    logger.error("Exit failed for PUT (safety)")
                            except TokenExpiredError:
                                raise
                            except Exception as e:
                                logger.error(f"PUT safety exit error: {e}", exc_info=True)

                elif current_position == BaseEnums.CALL:
                    if (index_stop_loss is not None
                            and current_derivative_price is not None
                            and current_derivative_price <= index_stop_loss):
                        state.reason_to_exit = "CALL exit: Derivative dropped below ST (safety)"
                        if safe_hasattr(self, 'executor') and self.executor:
                            try:
                                success = self.executor.exit_position()
                                if not success:
                                    logger.error("Exit failed for CALL (safety)")
                            except TokenExpiredError:
                                raise
                            except Exception as e:
                                logger.error(f"CALL safety exit error: {e}", exc_info=True)

            else:
                # Unconfirmed trade - check for cancellation signals
                if Utils.is_near_market_close(buffer_minutes=5):
                    if current_position:
                        logger.info("Market close approaching. Canceling pending position.")
                        self.cancel_pending_trade()
                        return

                if current_position == BaseEnums.PUT:
                    if state.should_buy_call or state.should_sell_call:
                        logger.info(f"Cancel pending PUT - {state.option_signal}")
                        self.cancel_pending_trade()

                elif current_position == BaseEnums.CALL:
                    if state.should_buy_put or state.should_sell_put:
                        logger.info(f"Cancel pending CALL - {state.option_signal}")
                        self.cancel_pending_trade()

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error monitoring active trade status: {e!r}", exc_info=True)

    def monitor_profit_loss_status_from_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Monitor profit/loss status using snapshot.
        """
        try:
            # Check if we should stop
            if self.should_stop:
                return

            state = state_manager.get_state()

            if not snapshot.get('current_trade_confirmed', False):
                return

            stop_loss = snapshot.get('stop_loss')
            tp_point = snapshot.get('tp_point')
            current_price = snapshot.get('current_price')
            current_position = snapshot.get('current_position')

            if stop_loss is not None and current_price is not None and current_price <= stop_loss:
                state.reason_to_exit = f"{current_position} exit: Option price below stop loss."
                if safe_hasattr(self, 'executor') and self.executor:
                    try:
                        success = self.executor.exit_position()
                        if not success:
                            logger.error(f"Exit failed for stop loss at {stop_loss}")
                    except TokenExpiredError:
                        raise
                    except Exception as e:
                        logger.error(f"Stop loss exit error: {e}", exc_info=True)

            elif tp_point is not None and current_price is not None and current_price >= tp_point:
                state.reason_to_exit = f"{current_position} exit: Target profit hit."
                if safe_hasattr(self, 'executor') and self.executor:
                    try:
                        success = self.executor.exit_position()
                        if not success:
                            logger.error(f"Exit failed for take profit at {tp_point}")
                    except TokenExpiredError:
                        raise
                    except Exception as e:
                        logger.error(f"Take profit exit error: {e}", exc_info=True)

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error monitoring profit/loss status: {e!r}", exc_info=True)

    def monitor_active_trade_status(self) -> None:
        """
        Legacy method - maintained for compatibility.
        """
        try:
            snapshot = state_manager.get_position_snapshot()
            self.monitor_active_trade_status_from_snapshot(snapshot)
        except Exception as e:
            logger.error(f"Error in monitor_active_trade_status: {e}", exc_info=True)

    def monitor_profit_loss_status(self) -> None:
        """
        Legacy method - maintained for compatibility.
        """
        try:
            snapshot = state_manager.get_position_snapshot()
            self.monitor_profit_loss_status_from_snapshot(snapshot)
        except Exception as e:
            logger.error(f"Error in monitor_profit_loss_status: {e}", exc_info=True)

    def execute_based_on_trend(self) -> None:
        try:
            # Check if we should stop
            if self.should_stop:
                return

            state = state_manager.get_state()

            # Skip trading if market is closed (unless backtest mode)
            if not self._backtest_mode and not self._check_market_status():
                logger.info("Market closed - skipping trading decision")
                return

            if Utils.check_sideway_time() and not state.sideway_zone_trade:
                logger.info("Sideways period (12:00–2:00). Skipping trading decision.")
                return

            if not Utils.is_market_open():
                logger.info("Market is closed. Skipping trading execution.")
                return

            if Utils.is_near_market_close(buffer_minutes=5):
                logger.info("Too close to market close. Skipping trading decision.")
                return

            trend = state.trend

            if state.current_position is None:
                if trend == BaseEnums.ENTER_CALL and state.should_buy_call:
                    logger.info("🎯 ENTER_CALL confirmed by BUY_CALL")

                    # FEATURE 6: Multi-Timeframe Filter check
                    if self.config.get('use_mtf_filter', False):
                        allowed, summary = self.mtf_filter.should_allow_entry(
                            self.symbol_full(state.derivative), BaseEnums.CALL
                        )
                        state.last_mtf_summary = summary
                        if not allowed:
                            logger.info(f'[MTF] Entry blocked: {summary}')
                            return
                        logger.info(f'[MTF] Entry allowed: {summary}')

                    try:
                        success = self.executor.buy_option(option_type=BaseEnums.CALL)
                        if success and state.call_option not in (state.all_symbols or []):
                            self.subscribe_market_data()
                    except TokenExpiredError:
                        raise
                    except Exception as e:
                        logger.error(f"Failed to execute CALL: {e}", exc_info=True)

                elif trend == BaseEnums.ENTER_PUT and state.should_buy_put:
                    logger.info("🎯 ENTER_PUT confirmed by BUY_PUT")

                    # FEATURE 6: Multi-Timeframe Filter check
                    if self.config.get('use_mtf_filter', False):
                        allowed, summary = self.mtf_filter.should_allow_entry(
                            self.symbol_full(state.derivative), BaseEnums.PUT
                        )
                        state.last_mtf_summary = summary
                        if not allowed:
                            logger.info(f'[MTF] Entry blocked: {summary}')
                            return
                        logger.info(f'[MTF] Entry allowed: {summary}')

                    try:
                        success = self.executor.buy_option(option_type=BaseEnums.PUT)
                        if success and state.put_option not in (state.all_symbols or []):
                            self.subscribe_market_data()
                    except TokenExpiredError:
                        raise
                    except Exception as e:
                        logger.error(f"Failed to execute PUT: {e}", exc_info=True)

                elif trend == BaseEnums.RESET_PREVIOUS_TRADE:
                    logger.info("🔄 Resetting previous trade flag")
                    state.previous_position = None

            else:
                # Position is open — handle exits driven by state.trend
                if state.current_position == BaseEnums.CALL:
                    if trend == BaseEnums.EXIT_CALL:
                        logger.info(f"🚪 EXIT_CALL confirmed — exiting CALL position")
                        try:
                            success = self.executor.exit_position()
                            if not success:
                                logger.error("exit_position() returned False for EXIT_CALL")
                        except TokenExpiredError:
                            raise
                        except Exception as e:
                            logger.error(f"Exit CALL failed: {e}", exc_info=True)
                    elif state.should_buy_put or state.should_sell_call:
                        logger.warning(
                            f"Position CALL but signal is {state.option_signal} - will exit soon")

                elif state.current_position == BaseEnums.PUT:
                    if trend == BaseEnums.EXIT_PUT:
                        logger.info(f"🚪 EXIT_PUT confirmed — exiting PUT position")
                        try:
                            success = self.executor.exit_position()
                            if not success:
                                logger.error("exit_position() returned False for EXIT_PUT")
                        except TokenExpiredError:
                            raise
                        except Exception as e:
                            logger.error(f"Exit PUT failed: {e}", exc_info=True)
                    elif state.should_buy_call or state.should_sell_put:
                        logger.warning(
                            f"Position PUT but signal is {state.option_signal} - will exit soon")

        except TokenExpiredError:
            raise
        except Exception as exec_error:
            logger.error(f"Order execution failed: {exec_error!r}", exc_info=True)

    def cancel_pending_trade(self) -> None:
        try:
            state = state_manager.get_state()

            if not state.orders:
                logger.info("No pending orders to cancel.")
                return

            logger.info(f"Cancelling {len(state.orders)} pending order(s).")

            remaining_orders = []
            confirmed_orders = []
            confirmed_found = False

            for order in state.orders:
                order_id = order.get("id")
                broker_id = order.get("broker_id")
                try:
                    if self.broker and broker_id and safe_hasattr(self.broker, 'get_current_order_status'):
                        status = self.broker.get_current_order_status(broker_id)
                        if status == BaseEnums.ORDER_STATUS_CONFIRMED:
                            confirmed_found = True
                            confirmed_orders.append(order)
                            logger.info(f"✅ Order {order_id} (broker={broker_id}) confirmed. Will not cancel.")
                            continue

                    if broker_id is None:
                        logger.debug(f"Paper order {order_id} — skipping broker cancel.")
                        continue

                    if self.broker and safe_hasattr(self.broker, 'cancel_order'):
                        # FIX: Pass broker_id, not order_id
                        self.broker.cancel_order(order_id=broker_id)
                        logger.info(f"Cancelled broker order {broker_id} (db_id={order_id})")

                except TokenExpiredError:
                    raise
                except Exception as e:
                    logger.error(f"❌ Failed to cancel order ID {order_id}: {e}", exc_info=True)
                    remaining_orders.append(order)

            state.orders = remaining_orders

            if not safe_hasattr(state, "confirmed_orders"):
                state.confirmed_orders = []
            if confirmed_orders:
                state.confirmed_orders.extend(confirmed_orders)

            if confirmed_found:
                state.current_trade_confirmed = True
                logger.info("✔️ Trade marked as confirmed due to confirmed orders.")
            else:
                state.reset_trade_attributes(current_position=None)

            logger.info("🧹 Pending order cancellation process complete.")

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"🔥 Error in cancel_pending_trade: {e}", exc_info=True)

    def symbol_full(self, symbol: Optional[str]) -> Optional[str]:
        return symbol

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

            # Clear all candle stores - interval or symbol may have changed
            candle_store_manager.clear()
            logger.debug("CandleStore caches cleared on settings refresh")

            # FEATURE 6: Invalidate MTF cache on settings change
            if self.mtf_filter:
                self.mtf_filter.invalidate_cache()

            # Clear indicator cache
            self._indicator_cache.clear()
            self._last_bar_times.clear()

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[TradingApp.refresh_settings_live] Failed: {e}", exc_info=True)

    def apply_settings_to_state(self) -> None:
        """Apply settings to state object."""
        try:
            state = state_manager.get_state()

            # Apply trade_config settings
            if self.trade_config:
                state.capital_reserve = safe_getattr(self.trade_config, "capital_reserve", 0)
                state.derivative = self.symbol_full(safe_getattr(self.trade_config, "derivative", ""))
                state.expiry = safe_getattr(self.trade_config, "week", "")
                _config_lot_size = safe_getattr(self.trade_config, "lot_size", 0)
                state.lot_size = OptionUtils.get_lot_size(
                    state.derivative, fallback=_config_lot_size
                )
                state.call_lookback = safe_getattr(self.trade_config, "call_lookback", 0)
                state.put_lookback = safe_getattr(self.trade_config, "put_lookback", 0)
                state.original_call_lookback = state.call_lookback
                state.original_put_lookback = state.put_lookback
                state.interval = safe_getattr(self.trade_config, "history_interval", "")
                state.max_num_of_option = safe_getattr(self.trade_config, "max_num_of_option", 0)
                state.lower_percentage = safe_getattr(self.trade_config, "lower_percentage", 0)
                state.cancel_after = safe_getattr(self.trade_config, "cancel_after", 0)
                state.sideway_zone_trade = safe_getattr(self.trade_config, "sideway_zone_trade", False)

            # Get balance — paper mode uses the configured paper_balance from
            # TradingModeSetting instead of querying the real broker API.
            if self.trading_mode_setting and not self.trading_mode_setting.is_live():
                # Paper / Simulation / Backtest: use the paper balance from settings
                paper_bal = safe_getattr(self.trading_mode_setting, 'paper_balance', 100000.0) or 100000.0
                state.account_balance = float(paper_bal)
                logger.info(
                    f"[apply_settings_to_state] PAPER MODE — using paper balance: "
                    f"₹{state.account_balance:,.2f}"
                )
            elif self.broker:
                # Live mode: fetch real balance from broker
                try:
                    balance = self.broker.get_balance(state.capital_reserve)
                    if balance and balance > 0:
                        state.account_balance = balance
                    else:
                        logger.warning(
                            f"Balance returned {balance}. Keeping existing value: {state.account_balance}")
                except TokenExpiredError:
                    raise
                except Exception as e:
                    logger.error(f"Failed to get balance: {e}", exc_info=True)

            # Apply profit/loss settings
            if self.profit_loss_config:
                plc = self.profit_loss_config
                state.tp_percentage = state.original_profit_per = safe_getattr(plc, "tp_percentage", 0)
                state.stoploss_percentage = state.original_stoploss_per = safe_getattr(plc, "stoploss_percentage", 0)
                state.trailing_first_profit = safe_getattr(plc, "trailing_first_profit", 0)
                state.max_profit = safe_getattr(plc, "max_profit", 0)
                state.profit_step = safe_getattr(plc, "profit_step", 0)
                state.loss_step = safe_getattr(plc, "loss_step", 0)
                state.take_profit_type = safe_getattr(plc, "profit_type", "absolute")

            logger.info(f"[Settings] Applied trade and P/L configs - Capital: {state.capital_reserve}, "
                        f"Lot size: {state.lot_size}, TP: {state.tp_percentage}%, "
                        f"SL: {state.stoploss_percentage}%")

        except TokenExpiredError:
            raise
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
            if safe_hasattr(self, '_stop_event') and self._stop_event:
                self._stop_event.set()  # Wake up the keep-alive loop immediately

            # Wait for stage 2 worker thread to finish (with timeout)
            if safe_hasattr(self, '_stage2_thread') and self._stage2_thread and self._stage2_thread.is_alive():
                logger.info("Waiting for stage 2 worker thread to finish...")
                self._stage2_thread.join(timeout=2.0)

            # WebSocket cleanup
            if safe_hasattr(self, 'ws') and self.ws:
                try:
                    if safe_hasattr(self.ws, 'cleanup'):
                        self.ws.cleanup()
                    logger.info("WebSocket cleaned up")
                except Exception as e:
                    logger.error(f"Error cleaning up WebSocket: {e}", exc_info=True)

            # Thread pool shutdown
            if safe_hasattr(self, '_fetch_executor') and self._fetch_executor:
                try:
                    self._fetch_executor.shutdown(wait=False)
                    logger.info("Thread pool shut down")
                except Exception as e:
                    logger.error(f"Error shutting down thread pool: {e}", exc_info=True)

            # Feature cleanups
            if safe_hasattr(self, 'risk_manager') and self.risk_manager:
                try:
                    self.risk_manager.cleanup()
                except Exception as e:
                    logger.error(f"RiskManager cleanup error: {e}", exc_info=True)

            if safe_hasattr(self, 'notifier') and self.notifier:
                try:
                    self.notifier.cleanup()
                except Exception as e:
                    logger.error(f"Notifier cleanup error: {e}", exc_info=True)

            if safe_hasattr(self, 'mtf_filter') and self.mtf_filter:
                try:
                    self.mtf_filter.cleanup()
                except Exception as e:
                    logger.error(f"MTF filter cleanup error: {e}", exc_info=True)

            if safe_hasattr(self, 'executor') and self.executor:
                try:
                    self.executor.cleanup()
                except Exception as e:
                    logger.error(f"Executor cleanup error: {e}", exc_info=True)

            # Broker cleanup
            if safe_hasattr(self, 'broker') and self.broker:
                try:
                    if safe_hasattr(self.broker, 'cleanup'):
                        self.broker.cleanup()
                except Exception as e:
                    logger.error(f"Broker cleanup error: {e}", exc_info=True)

            # Clear candle store manager
            try:
                candle_store_manager.clear()
                logger.info("CandleStoreManager cleared")
            except Exception as e:
                logger.error(f"CandleStoreManager cleanup error: {e}", exc_info=True)

            # Clear caches
            self._indicator_cache.clear()
            self._last_bar_times.clear()

            self._cleanup_done = True
            logger.info("TradingApp cleanup completed")

        except Exception as e:
            logger.error(f"[TradingApp.cleanup] Error: {e}", exc_info=True)
            self._cleanup_done = True