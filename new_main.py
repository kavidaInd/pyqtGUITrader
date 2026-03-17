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
from Utils.time_utils import ist_now
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
        self._last_bar_completed = None
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if config is None:
                logger.warning("config is None in TradingApp.__init__")

            self.config = config
            self.trading_mode_setting = trading_mode_var
            self._broker_setting = broker_setting  # stored for initialize()

            self._tick_queue = queue.Queue(maxsize=500)
            self._stage2_thread = threading.Thread(
                target=self._stage2_worker,
                daemon=True,
                name='Stage2Worker'
            )
            self._stage2_thread.start()

            self._option_chain_lock = threading.Lock()

            # Initialize option chain in state
            with self._option_chain_lock:
                state = state_manager.get_state()
                if not safe_hasattr(state, "option_chain") or state.option_chain is None:
                    state.option_chain = {}

            # Number of ITM and OTM strikes to subscribe on each side of ATM
            self._chain_itm = 2
            self._chain_otm = 2

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
        self._last_bar_completed = False

        # FIX: Tick validation
        self._last_tick_seq = {}
        self._last_tick_time = {}

        # FIX: Indicator cache
        self._indicator_cache = {}
        self._last_bar_times = {}

        # BUG-A / ENHANCEMENT-1: Tick heartbeat and GUI price callback
        self._last_tick_received: Optional[datetime] = None
        self._price_cb_ref = None  # weakref to GUI price callback

        # Re-entry guard runtime state
        self._reentry_exit_time: Optional[datetime] = None        # wall-clock time of last exit
        self._reentry_exit_bars: int = 0                          # closed bars since last exit
        self._reentry_exit_reason: str = "default"                # "sl" | "tp" | "signal" | "default"
        self._reentry_exit_price: float = 0.0                     # entry price of the closed trade
        self._reentry_exit_direction: Optional[Any] = None        # BaseEnums.CALL or PUT
        self._reentry_count_today: int = 0                        # re-entries taken today
        self._reentry_signal_seen: bool = False                   # fresh signal observed after wait

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

            # Re-entry guard settings
            from gui.re_entry.ReEntrySetting import ReEntrySetting
            self.reentry_setting = ReEntrySetting()
            self.reentry_setting._apply_to_state()  # push into trade state immediately

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

            # DATA-3 fix: Create a trade session row in the DB so order history
            # and stats popups have a valid session to query against.
            try:
                from db.connector import get_db
                from db.crud import sessions as sessions_crud
                state = state_manager.get_state()
                mode_str = "PAPER"
                if self.trading_mode_setting:
                    import BaseEnums as _BE
                    from gui.trading_mode.TradingModeSetting import TradingMode as _TM
                    _mode = getattr(self.trading_mode_setting, 'mode', None)
                    if _mode == _TM.LIVE:
                        mode_str = "LIVE"
                    elif _mode == _TM.BACKTEST:
                        mode_str = "BACKTEST"
                active_slug = None
                if self.strategy_manager:
                    try:
                        active_slug = self.strategy_manager.get_active_slug()
                    except Exception:
                        pass
                session_id = sessions_crud.create(
                    mode=mode_str,
                    derivative=getattr(state, 'derivative', None),
                    strategy_slug=active_slug,
                    db=get_db(),
                )
                state.session_id = session_id
                logger.info(f"[TradingApp.initialize] Created trade session id={session_id} mode={mode_str}")
            except Exception as _sess_err:
                logger.error(f"[TradingApp.initialize] Session creation failed: {_sess_err}", exc_info=True)

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
                state.trading_mode = mode_str  # sets _trading_mode + _is_paper_mode atomically
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
            # BUG FIX: self.strategy_manager is None until initialize() runs, but
            # the strategy editor can fire strategy_saved at any time (even before
            # trading is started).  The module-level singleton is always available
            # and backed by the same database, so use it as a fallback instead of
            # bailing out with a warning that silently drops the user's save.
            from strategy.strategy_manager import get_strategy_manager
            mgr = self.strategy_manager or get_strategy_manager()

            if not self.signal_engine:
                # signal_engine is None before initialize() — the strategy has been
                # saved to the DB already (strategy_manager.save() succeeded), so
                # the new timeframe/rules will be picked up automatically when
                # initialize() runs.  No further action needed here.
                logger.debug(
                    "[reload_signal_engine] signal_engine not yet initialised — "
                    "updated strategy will be loaded on next trading start."
                )
                return

            active_slug = mgr.get_active_slug()
            new_config = mgr.get_active_engine_config()
            if new_config:
                self.signal_engine.from_dict(new_config)
                # Re-link the updated engine into the detector so detect() uses new rules
                if self.detector and safe_hasattr(self.detector, 'set_signal_engine'):
                    self.detector.set_signal_engine(self.signal_engine)
                logger.info(
                    f"[TradingApp.reload_signal_engine] Engine reloaded from strategy "
                    f"'{active_slug}' — "
                    f"{sum(len(v.get('rules', [])) for v in new_config.values() if isinstance(v, dict))} "
                    f"rules loaded"
                )
                # Force immediate re-evaluation so the dynamic signal debug popup
                # reflects the new rules within 1 second of saving, without
                # waiting for the next live market tick.
                self._force_signal_evaluation()
                # BUG FIX: Also sync state.interval with the strategy's (possibly
                # updated) timeframe.  reload_signal_engine() was previously called
                # only from _on_strategy_saved, which does NOT call
                # refresh_settings_live.  Without this block, editing a strategy's
                # timeframe and saving it updates the engine rules but leaves
                # state.interval (and therefore candle resampling) on the old value.
                try:
                    new_tf = mgr.get_active_timeframe()
                    if new_tf:
                        state = state_manager.get_state()
                        old_interval = state.interval
                        if old_interval != new_tf:
                            state.interval = new_tf
                            # Candle stores must be cleared so they rebuild at the
                            # new bar-size; stale bars at the old interval would
                            # produce nonsense signals on the very first tick.
                            from data.candle_store_manager import candle_store_manager
                            candle_store_manager.clear()
                            logger.info(
                                f"[TradingApp.reload_signal_engine] state.interval updated: "
                                f"{old_interval!r} → {new_tf!r}; candle stores cleared"
                            )
                except Exception as _tf_e:
                    logger.warning(
                        f"[TradingApp.reload_signal_engine] Could not sync timeframe: {_tf_e}"
                    )
            else:
                logger.warning(
                    f"[TradingApp.reload_signal_engine] No engine config found for "
                    f"strategy '{active_slug}' — engine unchanged"
                )

        except Exception as e:
            logger.error(f"[TradingApp.reload_signal_engine] Failed: {e}", exc_info=True)

    def _force_signal_evaluation(self):
        """
        Re-evaluate the signal engine immediately using the latest candle data.

        Called right after reload_signal_engine() so that state.option_signal_result
        is updated with the new rules before the next live tick arrives.  Without
        this, the dynamic signal debug popup would keep showing stale pre-save
        evaluation results until a real market tick triggers a new evaluation.
        """
        try:
            state = state_manager.get_state()
            if not state or not self.signal_engine:
                return

            derivative = getattr(state, 'derivative', None)
            if not derivative:
                logger.debug("[_force_signal_evaluation] No derivative in state — skipping")
                return

            store = candle_store_manager.get_store(derivative)
            if store is None or store.is_empty():
                logger.debug("[_force_signal_evaluation] No candle data yet — skipping")
                return

            try:
                _raw = str(state.interval or "1").strip().rstrip("mM")
                target_minutes = int(_raw)
            except (TypeError, ValueError):
                target_minutes = 1

            df = store.resample(target_minutes)
            if df is None or df.empty:
                logger.debug("[_force_signal_evaluation] Resampled df is empty — skipping")
                return

            result = self.signal_engine.evaluate(df, state.current_position)
            if result and result.get('available'):
                if self.detector and safe_hasattr(self.detector, '_update_state_with_signal_result'):
                    self.detector._update_state_with_signal_result(result)
                else:
                    state.option_signal_result = result
                logger.info(
                    f"[TradingApp._force_signal_evaluation] Re-evaluated after reload: "
                    f"signal={result.get('signal_value')}"
                )
            else:
                logger.debug("[_force_signal_evaluation] Engine returned no result or not available")

        except Exception as e:
            logger.debug(f"[TradingApp._force_signal_evaluation] {e}", exc_info=True)

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
                self._stop_event.wait(timeout=.1)

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

    def set_price_callback(self, cb) -> None:
        """
        ENHANCEMENT-1: Register a GUI callback to receive real-time price updates.
        Stored as a weakref so this does not prevent GUI garbage-collection.
        Safe to call from the GUI thread before or after the engine starts.
        """
        import weakref
        try:
            self._price_cb_ref = weakref.ref(cb)
            logger.debug("[TradingApp.set_price_callback] Price callback registered")
        except Exception as e:
            logger.error(f"[TradingApp.set_price_callback] {e}", exc_info=True)

    def initialize_market_state(self) -> None:
        try:
            self.apply_settings_to_state()
            # Re-apply trading mode AFTER apply_settings_to_state() so state is
            # fully initialised before we write trading_mode into it.
            self._apply_trading_mode_to_executor()
            state = state_manager.get_state()

            # Get initial price for derivative and seed the CandleStore.
            # All subsequent reads (subscribe_market_data, signal engine, etc.)
            # will then use candle_store_manager.get_current_price() rather than
            # issuing a second broker REST call.
            if self.broker and safe_hasattr(self.broker, 'get_option_current_price'):
                try:
                    bootstrap_price = self.broker.get_option_current_price(
                        state.derivative
                    )
                    if bootstrap_price is not None and bootstrap_price > 0:
                        # 1. Push into CandleStore — becomes the authoritative price
                        candle_store_manager.push_tick(state.derivative, bootstrap_price)
                        # 2. Read back through the store so state is consistent
                        store = candle_store_manager.get_store(state.derivative)
                        state.derivative_current_price = (
                                store.get_current_close() or bootstrap_price
                        )
                        logger.info(
                            f"[initialize_market_state] Bootstrap derivative price "
                            f"{state.derivative_current_price:.2f} seeded into CandleStore"
                        )
                    else:
                        logger.warning(
                            "[initialize_market_state] Bootstrap price was None/zero; CandleStore stays empty until first WS tick")
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
            now = ist_now()
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

    def ensure_symbol_subscribed(self, symbol: str) -> bool:
        """
        Guarantee that *symbol* is receiving live WebSocket ticks.

        Called BEFORE an order is placed whenever a lookback adjustment or a
        user-configured deep ITM/OTM lookback may have chosen a strike that
        sits outside the initial ±3 strike chain window.

        Strategy
        --------
        1. If the symbol is already in the subscribed chain → nothing to do.
        2. If it is missing:
           a. Add it to state.option_chain so tick routing will accept it.
           b. Append it to ws.symbols and call ws_subscribe() with ONLY the
              new symbol — this avoids tearing down and rebuilding the entire
              subscription (which would cause a momentary data blackout for all
              other symbols and trigger a heavy re-subscribe_market_data()).
           c. If the incremental subscribe fails, fall back to a full
              subscribe_market_data() rebuild so we never silently trade a
              symbol with no live price feed.

        Returns True if the symbol is (or becomes) subscribed, False on error.
        """
        try:
            if not symbol:
                logger.warning("[ensure_symbol_subscribed] called with empty symbol")
                return False

            full_sym = self.symbol_full(symbol)
            if not full_sym:
                logger.warning(f"[ensure_symbol_subscribed] symbol_full() returned None for {symbol!r}")
                return False

            state = state_manager.get_state()
            all_syms = state.all_symbols or []

            # ── Already subscribed ────────────────────────────────────────────
            if full_sym in all_syms:
                logger.debug(f"[ensure_symbol_subscribed] {full_sym} already subscribed")
                return True

            logger.info(
                f"[ensure_symbol_subscribed] {full_sym} NOT in subscription "
                f"(chain has {len(all_syms)} symbols). Subscribing incrementally."
            )

            # ── Step 1: Register symbol in option_chain so ticks are routed ──
            with self._option_chain_lock:
                current_chain = state.option_chain or {}
                if full_sym not in current_chain:
                    current_chain[full_sym] = {"ltp": None, "ask": None, "bid": None}
                    state.option_chain = current_chain

            # ── Step 2: Add to ws.symbols list ───────────────────────────────
            updated_syms = list(all_syms)
            if full_sym not in updated_syms:
                updated_syms.append(full_sym)
            state.all_symbols = updated_syms

            if self.ws:
                self.ws.symbols = updated_syms

            # ── Step 3: Incremental broker subscribe (single symbol) ──────────
            incremental_ok = False
            if self.ws and self.ws.is_connected() and self.ws._ws_obj is not None:
                try:
                    self.broker.ws_subscribe(self.ws._ws_obj, [full_sym])
                    incremental_ok = True
                    logger.info(
                        f"[ensure_symbol_subscribed] ✅ Incremental subscribe OK: {full_sym}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[ensure_symbol_subscribed] Incremental subscribe failed ({e}); "
                        "falling back to full subscribe_market_data()"
                    )

            # ── Step 4: Full fallback if incremental subscribe failed ─────────
            if not incremental_ok:
                logger.info("[ensure_symbol_subscribed] Triggering full subscribe_market_data()")
                self.subscribe_market_data()
                # Verify the symbol made it in after the rebuild
                if full_sym not in (state.all_symbols or []):
                    logger.error(
                        f"[ensure_symbol_subscribed] {full_sym} still missing after "
                        "full subscribe_market_data() — live price feed unavailable!"
                    )
                    return False

            return True

        except Exception as e:
            logger.error(f"[ensure_symbol_subscribed] Unexpected error: {e}", exc_info=True)
            return False

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

            # BUG-A fix: Record tick heartbeat timestamp for connection monitoring
            self._last_tick_received = ist_now()

            # ENHANCEMENT-1: Propagate price to GUI immediately via callback
            cb_ref = getattr(self, '_price_cb_ref', None)
            if cb_ref is not None:
                try:
                    cb = cb_ref()
                    if cb is not None and callable(cb):
                        cb(symbol, ltp)
                except Exception:
                    pass  # Never let GUI callback crash the WS thread

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
            now = ist_now()
            last_time = self._last_tick_time.get(symbol)
            if last_time and (now - last_time).total_seconds() > 5:
                logger.warning(f"Large tick gap for {symbol}: {(now - last_time).total_seconds():.1f}s")

            self._last_tick_time[symbol] = now

            # Price sanity check (can't move >20% in one tick)
            state = state_manager.get_state()
            if OptionUtils.symbols_match(symbol, self.symbol_full(state.derivative)):
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
        Update unrealized P&L and percentage_change every tick.

        FIX: Do NOT gate on positions_hold > 0 — after broker reconciliation,
        positions_hold is set correctly but there is a window where it may be
        0 if record_trade_state hasn't run yet. Guard on current_position and
        buy_price instead, which are set atomically by record_trade_state.
        Also always update percentage_change so the status bar P&L% card
        reflects real-time movement, not just the last new-high tick.
        """
        try:
            current_position = snapshot.get('current_position')
            buy_price = snapshot.get('current_buy_price')
            current_price = snapshot.get('current_price')

            if current_position is None or buy_price is None or current_price is None:
                return
            if buy_price == 0:
                return

            positions_hold = snapshot.get('positions_hold', 0) or 0
            unrealized = (current_price - buy_price) * positions_hold
            pct_change = round(((current_price - buy_price) / buy_price) * 100, 4)

            state = state_manager.get_state()
            state.current_pnl = unrealized
            state.percentage_change = pct_change
        except Exception as e:
            logger.error(f"Error updating unrealized P&L: {e}", exc_info=True)

    def _on_trade_closed(self, pnl: float, is_winner: bool):
        """
        FEATURE 5: Callback for DailyPnLWidget when a trade is closed.
        Also records re-entry guard state.
        """
        try:
            logger.info(f"Trade closed - P&L: ₹{pnl:.2f}, Winner: {is_winner}")
            self._record_reentry_exit()
        except Exception as e:
            logger.error(f"Error in _on_trade_closed: {e}", exc_info=True)

    def _record_reentry_exit(self):
        """
        Capture everything needed by the re-entry guard at the moment a
        position closes.  Called immediately after the trade exits.
        """
        try:
            state = state_manager.get_state()
            self._reentry_exit_time = ist_now()
            # BUG FIX (off-by-one): The bar-close event that triggers an SL/TP
            # exit also fires _on_bar_closed_reentry_tick on the same iteration,
            # incrementing the counter from 0 to 1 before a single full wait-bar
            # has actually elapsed.  Starting at -1 neutralises that spurious
            # increment so bar #1 is the first COMPLETE bar after the exit bar.
            self._reentry_exit_bars = -1
            self._reentry_signal_seen = False
            # Exit direction
            self._reentry_exit_direction = getattr(state, 'previous_position', None)
            # Entry price of the closed trade
            self._reentry_exit_price = float(getattr(state, 'current_buy_price', 0.0) or 0.0)
            # Exit reason classification
            reason = (getattr(state, 'reason_to_exit', '') or '').lower()
            if 'stop' in reason or 'sl' in reason:
                self._reentry_exit_reason = 'sl'
            elif 'target' in reason or 'tp' in reason or 'profit' in reason:
                self._reentry_exit_reason = 'tp'
            elif 'signal' in reason or 'exit' in reason or 'buy_' in reason:
                self._reentry_exit_reason = 'signal'
            else:
                self._reentry_exit_reason = 'default'
            logger.info(
                f"[ReEntry] Exit recorded — reason={self._reentry_exit_reason!r}, "
                f"direction={self._reentry_exit_direction!r}, "
                f"price={self._reentry_exit_price:.2f}"
            )
        except Exception as e:
            logger.error(f"[_record_reentry_exit] {e}", exc_info=True)

    def _on_bar_closed_reentry_tick(self):
        """
        Called once each time a bar completes (from evaluate_trend_from_snapshot).
        Increments the bar counter used by the re-entry guard.
        Also marks whether a fresh signal has been seen since the exit.
        """
        try:
            if self._reentry_exit_time is None:
                return  # no exit has occurred yet this session
            self._reentry_exit_bars += 1
            logger.debug(
                f"[ReEntry] Bar #{self._reentry_exit_bars} elapsed since exit "
                f"(reason={self._reentry_exit_reason!r})"
            )
            # BUG FIX: Do NOT check option_signal here for fresh-signal detection.
            # _on_bar_closed_reentry_tick() runs BEFORE the async history fetch
            # (_fetch_history_and_detect) has recomputed indicators for the new
            # bar.  state.option_signal still holds the STALE result from the
            # previous bar, so marking _reentry_signal_seen=True here would fire
            # immediately on bar N+1 using the pre-exit signal — defeating the
            # 'require fresh signal' guard entirely.
            # The fresh-signal check now lives in _check_reentry_allowed, where
            # it is evaluated only after _fetch_history_and_detect has produced
            # a genuinely new option_signal value.
        except Exception as e:
            logger.error(f"[_on_bar_closed_reentry_tick] {e}", exc_info=True)

    def _check_reentry_allowed(self, direction: Any, state: Any) -> bool:
        """
        Returns True if a new entry in *direction* is permitted under the
        re-entry guard settings.  Returns False (with a log message) if blocked.

        This is called ONLY when current_position is None — i.e. a fresh entry
        is about to be attempted.  The first entry of the day (no prior exit
        this session) always returns True immediately.
        """
        try:
            # ── No previous exit this session → first trade, always allowed ──
            if self._reentry_exit_time is None:
                return True

            # ── Load settings from state (applied by ReEntrySetting.save()) ──
            allow = getattr(state, 'reentry_allow', True)
            if not allow:
                logger.info("[ReEntry] Re-entry disabled by settings — blocking entry")
                return False

            same_dir_only = getattr(state, 'reentry_same_direction_only', False)

            # ── Direction check ───────────────────────────────────────────────
            is_same_direction = (direction == self._reentry_exit_direction)
            if same_dir_only and not is_same_direction:
                # Opposite direction re-entry — allowed immediately
                logger.debug("[ReEntry] Opposite direction — re-entry allowed immediately")
                return True

            # ── Daily cap ─────────────────────────────────────────────────────
            max_per_day = getattr(state, 'reentry_max_per_day', 0)
            if max_per_day > 0 and self._reentry_count_today >= max_per_day:
                logger.info(
                    f"[ReEntry] Daily cap reached ({self._reentry_count_today}/{max_per_day}) — blocking entry"
                )
                return False

            # ── Candle wait ───────────────────────────────────────────────────
            wait_map = {
                'sl':      getattr(state, 'reentry_min_candles_sl', 3),
                'tp':      getattr(state, 'reentry_min_candles_tp', 1),
                'signal':  getattr(state, 'reentry_min_candles_signal', 2),
                'default': getattr(state, 'reentry_min_candles_default', 2),
            }
            required_bars = wait_map.get(self._reentry_exit_reason, wait_map['default'])

            if self._reentry_exit_bars < required_bars:
                logger.info(
                    f"[ReEntry] Waiting for candles — bars elapsed: {self._reentry_exit_bars}, "
                    f"required: {required_bars} (reason: {self._reentry_exit_reason}) — blocking"
                )
                return False

            # ── Fresh signal requirement ──────────────────────────────────────
            # BUG FIX: Check option_signal HERE (after _fetch_history_and_detect
            # has run) rather than in _on_bar_closed_reentry_tick (where it was
            # still the stale pre-exit value).  This guarantees we only mark the
            # signal as fresh when the post-exit computation produced it.
            require_new = getattr(state, 'reentry_require_new_signal', True)
            if require_new:
                # Mark seen if the fresh (just-computed) signal matches the
                # ENTRY direction being requested (not the exit direction).
                # Using exit direction here was the bug: entering a PUT after
                # a CALL exit would require 'BUY_CALL' (exit direction match)
                # which can never be satisfied, permanently blocking re-entry.
                if not self._reentry_signal_seen:
                    live_signal = getattr(state, 'option_signal', None)
                    if direction == BaseEnums.CALL and live_signal == 'BUY_CALL':
                        self._reentry_signal_seen = True
                        logger.debug("[ReEntry] Fresh BUY_CALL confirmed at entry check")
                    elif direction == BaseEnums.PUT and live_signal == 'BUY_PUT':
                        self._reentry_signal_seen = True
                        logger.debug("[ReEntry] Fresh BUY_PUT confirmed at entry check")
                if not self._reentry_signal_seen:
                    logger.info(
                        "[ReEntry] Waiting for fresh signal after exit — current signal is stale — blocking"
                    )
                    return False

            # ── Price filter ──────────────────────────────────────────────────
            price_filter = getattr(state, 'reentry_price_filter_enabled', True)
            if price_filter and self._reentry_exit_price > 0:
                pct_threshold = getattr(state, 'reentry_price_filter_pct', 5.0)
                current_price = float(getattr(state, 'current_price', 0.0) or 0.0)
                if current_price > 0:
                    price_change_pct = ((current_price - self._reentry_exit_price)
                                        / self._reentry_exit_price * 100.0)
                    if price_change_pct > pct_threshold:
                        logger.info(
                            f"[ReEntry] Price filter blocked — current ₹{current_price:.2f}, "
                            f"original entry ₹{self._reentry_exit_price:.2f}, "
                            f"change +{price_change_pct:.1f}% > threshold {pct_threshold:.1f}%"
                        )
                        return False

            logger.info(
                f"[ReEntry] ✅ Re-entry ALLOWED — bars waited: {self._reentry_exit_bars}, "
                f"reason: {self._reentry_exit_reason}, direction: {direction!r}"
            )
            # Reset ALL exit-context fields so the NEXT exit starts a completely
            # fresh count.  Previously only 3 of the 6 fields were cleared, leaving
            # _reentry_exit_reason, _reentry_exit_price, and _reentry_exit_direction
            # stale -- which could incorrectly influence the guard after the new
            # position closes.
            self._reentry_exit_time = None
            self._reentry_exit_bars = 0
            self._reentry_exit_reason = "default"
            self._reentry_exit_price = 0.0
            self._reentry_exit_direction = None
            self._reentry_signal_seen = False
            return True

        except Exception as e:
            logger.error(f"[_check_reentry_allowed] {e}", exc_info=True)
            return True  # fail open — never silently block trading on an exception

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
            # Use OptionUtils.symbols_match() which normalises both sides to a
            # canonical form, handling all broker prefix variants across Fyers,
            # Zerodha, Upstox, Dhan, AngelOne, Shoonya, Flattrade, etc.
            # After WebSocketManager remaps tick symbols, this will be a plain ==
            # in the common case; symbols_match() is the safety net for any tick
            # that bypasses the WebSocket remapping path.
            if OptionUtils.symbols_match(full_symbol, self.symbol_full(state.derivative)):
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
                        try:
                            candle_store_manager.push_tick(derivative, ltp)
                            store = candle_store_manager.get_store(derivative)
                            state.derivative_current_price = store.get_current_close() or ltp
                        except Exception:
                            # Last resort only — store is completely broken
                            state.derivative_current_price = ltp
                return

            # ── Option chain tick ──────────────────────────────────────────────
            if self._option_chain_lock and safe_hasattr(state, "option_chain"):
                with self._option_chain_lock:
                    # Fast path: exact key match (works after WebSocketManager remapping)
                    chain_key = full_symbol if full_symbol in state.option_chain else None
                    # Fallback: broker-format mismatch — scan using symbols_match()
                    if chain_key is None:
                        for k in state.option_chain:
                            if OptionUtils.symbols_match(full_symbol, k):
                                chain_key = k
                                break
                    if chain_key is not None:
                        state.update_option_chain_symbol(chain_key, {
                            "ltp": ltp,
                            "ask": ask_price,
                            "bid": bid_price,
                        })
                        logger.debug(f"✅ Updated option chain for {chain_key}: LTP={ltp}")
                    else:
                        logger.debug(
                            f"Symbol {full_symbol} not in option chain. "
                            f"Available: {list(state.option_chain.keys())}"
                        )

            # ── ATM call / put option ticks ────────────────────────────────────
            use_ask = not bool(state.current_position)
            atm_put_sym = self.symbol_full(state.put_option)
            atm_call_sym = self.symbol_full(state.call_option)

            option_price = ask_price if use_ask else bid_price

            if OptionUtils.symbols_match(full_symbol, atm_put_sym) and state.put_option:
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
                    try:
                        recovered = candle_store_manager.get_current_price(state.put_option)
                        if recovered is not None:
                            state.put_current_close = recovered
                        elif option_price is not None:
                            state.put_current_close = option_price
                    except Exception:
                        if option_price is not None:
                            state.put_current_close = option_price

            elif OptionUtils.symbols_match(full_symbol, atm_call_sym) and state.call_option:
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
                    try:
                        recovered = candle_store_manager.get_current_price(state.call_option)
                        if recovered is not None:
                            state.call_current_close = recovered
                        elif option_price is not None:
                            state.call_current_close = option_price
                    except Exception:
                        if option_price is not None:
                            state.call_current_close = option_price

            # ── Sync current_price for open position P&L ──────────────────────
            # current_price is always sourced from the relevant option store,
            # already updated above.
            #
            # BUG FIX: Do NOT overwrite current_price while the trade is still
            # unconfirmed.  record_trade_state() sets current_price = fill_price
            # (e.g. 41.75 mid-price).  The very first WS tick that arrives after
            # entry often carries the pre-entry ask/LTP (e.g. 83.45) still queued
            # in the candle store, because the store hasn't received a post-fill
            # tick yet.  Writing that stale value here would make the trailing-SL
            # logic think the position is already +99 % in profit, immediately
            # activating the trail and then hitting TP — all within 200 ms of
            # entry.  We hold off until current_trade_confirmed=True, at which
            # point the broker has acknowledged the fill and the WS stream has had
            # at least one clean post-fill tick.
            if state.current_position and state.current_trade_confirmed:
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

                # Advance re-entry candle counter
                self._on_bar_closed_reentry_tick()

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

        FIX — Timeframe-correct indicator evaluation
        ─────────────────────────────────────────────
        Previously this method called signal_engine.evaluate(df) which
        recomputed ALL indicators from scratch on the partially-formed last
        candle.  That meant:

          • On a 5-min strategy the RSI was recalculated every 1-min tick
            using a close value that may be mid-bar, producing RSI values
            that never existed on a genuine 5-min chart.
          • Any comparison like "close > RSI(14)" was therefore comparing the
            live close against an artificially-updated RSI, not the completed
            5-min RSI.

        The fix uses signal_engine.evaluate_tick(current_close) instead.
        That method re-uses the *frozen* indicator cache from the last Tier-1
        bar-close computation and only injects the live close price for
        column-type rule sides, so:

          • Indicators (RSI, EMA, MACD …) remain anchored to the last
            *completed* X-minute bar and do not move mid-bar.
          • Column comparisons (e.g. "close > RSI") update on every tick.
          • No pandas_ta work happens here — the tick gate is pure arithmetic.
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

            # Use evaluate_tick() — frozen indicators + live close price only.
            # This is the correct Tier-2 path: indicators are X-min values
            # computed during the last Tier-1 bar-close; only the close column
            # is updated to reflect the current tick.
            result = self.signal_engine.evaluate_tick(
                current_close=current_close,
                current_position=state.current_position,
            )

            if result and result.get("available"):
                # Update state — the detector method handles all state fields.
                # We deliberately do NOT overwrite indicator_values in state
                # because evaluate_tick() returns an empty dict there; the
                # authoritative indicator snapshot lives in the Tier-1 result.
                if hasattr(self.detector, '_update_state_with_signal_result'):
                    self.detector._update_state_with_signal_result(result)
                else:
                    state.option_signal_result = result
                logger.debug(
                    f"[TickGate] signal={result.get('signal_value')} "
                    f"close={current_close:.2f} "
                    f"(frozen indicators from last {state.interval or '1'} bar)"
                )
            elif result is None:
                # evaluate_tick returned None — no frozen cache yet (startup)
                # or invalid close.  Leave state unchanged; Tier-1 will update
                # on the next completed bar.
                logger.debug(
                    "[TickGate] evaluate_tick returned None — "
                    "awaiting first Tier-1 bar completion."
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
                # state.interval is stored as e.g. "2m" or "5m"; strip the
                # trailing 'm' before converting to int.
                target_minutes = int(str(interval).strip().rstrip("mM"))
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

                # NOTE: Option (CE/PE) historical OHLC is intentionally NOT fetched
                # here via the broker REST API.  Option prices are received
                # exclusively from live WebSocket ticks (push_tick → CandleStore).
                # Fetching historical bars for short-lived option contracts is
                # unreliable (many brokers return sparse/empty data intraday) and
                # the signal engine only consumes *derivative* (index) OHLC anyway.

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

                        # NOTE: call_trend / put_trend detection via option OHLC has
                        # been removed.  The signal engine is designed exclusively for
                        # derivative (index) OHLC.  Running it against option candles
                        # produced by sparse intraday WS ticks yielded noisy, incorrect
                        # signals and — critically — overwrote state.option_signal_result
                        # (the authoritative derivative-based signal) with option-based
                        # results, corrupting trade decisions.
                        # state.call_trend and state.put_trend remain in TradeState for
                        # any future display use but are no longer computed here.

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
                logger.debug(
                    "[determine_trend] dynamic_signals_active=False — "
                    "signal engine result not yet available (waiting for first bar fetch). "
                    "No trend will be computed until the first history+indicator run completes."
                )
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
                        logger.debug(
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

                # Same-direction BUY signal: mark fresh signal seen so require_new_signal
                # is satisfied, then check if the candle wait has elapsed.
                # Only enter (unblock) if the re-entry guard allows it; otherwise keep
                # previous_pos set so this branch runs again on the next tick.
                elif previous_pos == BaseEnums.CALL and signal_value == 'BUY_CALL':
                    self._reentry_signal_seen = True
                    if self._check_reentry_allowed(BaseEnums.CALL, state):
                        trend = BaseEnums.ENTER_CALL
                        logger.info("Re-entry CALL allowed - same-direction BUY_CALL after wait")
                    else:
                        logger.info("Re-entry CALL blocked - candle wait not yet elapsed")

                elif previous_pos == BaseEnums.PUT and signal_value == 'BUY_PUT':
                    self._reentry_signal_seen = True
                    if self._check_reentry_allowed(BaseEnums.PUT, state):
                        trend = BaseEnums.ENTER_PUT
                        logger.info("Re-entry PUT allowed - same-direction BUY_PUT after wait")
                    else:
                        logger.info("Re-entry PUT blocked - candle wait not yet elapsed")

                # EXIT signal matching the previous position: the market may still be trending
                # against re-entry — reset the block so the next BUY_* can trigger fresh entry.
                # Without this, a repeated EXIT_CALL after closing a CALL would permanently
                # block new entries because no other branch would ever return RESET.
                elif previous_pos == BaseEnums.CALL and signal_value == 'EXIT_CALL':
                    trend = BaseEnums.RESET_PREVIOUS_TRADE
                    logger.info("Reset previous CALL trade flag - EXIT_CALL signal (unblocking entry)")

                elif previous_pos == BaseEnums.PUT and signal_value == 'EXIT_PUT':
                    trend = BaseEnums.RESET_PREVIOUS_TRADE
                    logger.info("Reset previous PUT trade flag - EXIT_PUT signal (unblocking entry)")

                # Neutral signal (HOLD/WAIT) → reset to unblock fresh entry
                elif signal_value in ['HOLD', 'WAIT']:
                    trend = BaseEnums.RESET_PREVIOUS_TRADE
                    logger.info(
                        f"Reset previous {previous_pos} trade flag - neutral {signal_value} signal "
                        "(unblocking entry)"
                    )
                else:
                    # No matching RESET condition — previous_pos still blocking entry.
                    logger.debug(
                        f"[determine_trend] Entry blocked: previous_pos={previous_pos!r}, "
                        f"signal={signal_value!r}. No RESET branch matched — "
                        "waiting for an opposite/reversal/neutral signal to unblock."
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

            # BUG-I fix: Use candle_store_manager as primary price source,
            # fall back to state.derivative_current_price when WS drops
            derivative = snapshot.get('derivative') or getattr(state, 'derivative', None)
            current_derivative_price = None
            if derivative:
                try:
                    current_derivative_price = candle_store_manager.get_current_price(derivative)
                except Exception:
                    pass
            if not current_derivative_price:
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

            # Sideways zone: skip auto entries during lunch-hour chop (12:00-14:00 IST)
            # unless the user has explicitly enabled sideways-zone trading.
            # NOTE: only applied in live/paper mode — backtest runs the full session.
            if not self._backtest_mode and Utils.check_sideway_time() and not state.sideway_zone_trade:
                logger.info(
                    "Sideways period (12:00–14:00 IST): auto entry blocked. "
                    "Enable 'Sideways Zone Trade' in Daily settings to trade this window."
                )
                return

            # NOTE: Utils.is_market_open() removed — it duplicated the broker-backed
            # _check_market_status() check above and incorrectly blocked backtest runs
            # (backtest does not guard that call with _backtest_mode).

            if not self._backtest_mode and Utils.is_near_market_close(buffer_minutes=5):
                logger.info("Too close to market close (≤5 min). Skipping trading decision.")
                return

            trend = state.trend

            if trend is None:
                # No actionable trend — signal not yet available or guard filtered it.
                # This is normal on every tick between bar completions.
                logger.debug(
                    f"[execute_based_on_trend] trend=None, signal={state.option_signal!r}, "
                    f"dynamic_active={state.dynamic_signals_active}, "
                    f"pos={state.current_position!r}, prev={state.previous_position!r}"
                )
                return

            if state.current_position is None:
                if trend == BaseEnums.ENTER_CALL and state.should_buy_call:
                    logger.info("🎯 ENTER_CALL confirmed by BUY_CALL")

                    # ── Re-entry guard ────────────────────────────────────────
                    _was_reentry = getattr(self, '_reentry_exit_time', None) is None
                    if not _was_reentry and not self._check_reentry_allowed(BaseEnums.CALL, state):
                        return
                    # ─────────────────────────────────────────────────────────

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
                        self.ensure_symbol_subscribed(state.call_option)
                        success = self.executor.buy_option(option_type=BaseEnums.CALL)
                        if success:
                            self.ensure_symbol_subscribed(state.call_option)
                            # Only count as re-entry if there was a prior exit this session
                            if self._reentry_exit_time is not None:
                                self._reentry_count_today += 1
                    except TokenExpiredError:
                        raise
                    except Exception as e:
                        logger.error(f"Failed to execute CALL: {e}", exc_info=True)

                elif trend == BaseEnums.ENTER_PUT and state.should_buy_put:
                    logger.info("🎯 ENTER_PUT confirmed by BUY_PUT")

                    # ── Re-entry guard ────────────────────────────────────────
                    _was_reentry = getattr(self, '_reentry_exit_time', None) is None
                    if not _was_reentry and not self._check_reentry_allowed(BaseEnums.PUT, state):
                        return
                    # ─────────────────────────────────────────────────────────

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
                        self.ensure_symbol_subscribed(state.put_option)
                        success = self.executor.buy_option(option_type=BaseEnums.PUT)
                        if success:
                            self.ensure_symbol_subscribed(state.put_option)
                            if self._reentry_exit_time is not None:
                                self._reentry_count_today += 1
                    except TokenExpiredError:
                        raise
                    except Exception as e:
                        logger.error(f"Failed to execute PUT: {e}", exc_info=True)

                elif trend == BaseEnums.RESET_PREVIOUS_TRADE:
                    logger.info(
                        f"🔄 RESET_PREVIOUS_TRADE: cleared previous_position={state.previous_position!r}. "
                        "Re-entry will be evaluated on the next signal tick."
                    )
                    state.previous_position = None

            else:
                # Position is open — handle exits driven by state.trend
                if state.current_position == BaseEnums.CALL:
                    if trend == BaseEnums.EXIT_CALL:
                        logger.info("🚪 EXIT_CALL confirmed — exiting CALL position")
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
                        logger.info("🚪 EXIT_PUT confirmed — exiting PUT position")
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

            # Sync state.interval from the active strategy's timeframe so that
            # candle resampling (and bar-completion logic) uses the correct
            # bar-size immediately after a strategy switch.
            if self.strategy_manager:
                try:
                    active_tf = self.strategy_manager.get_active_timeframe()
                    if active_tf:
                        state = state_manager.get_state()
                        old_interval = state.interval
                        state.interval = active_tf
                        if old_interval != active_tf:
                            logger.info(
                                f"[refresh_settings_live] state.interval updated: "
                                f"{old_interval!r} → {active_tf!r} (from active strategy)"
                            )
                except Exception as _tf_err:
                    logger.warning(f"[refresh_settings_live] Could not sync timeframe: {_tf_err}")

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
                state.max_num_of_option = safe_getattr(self.trade_config, "max_num_of_option", 0)

            if self.strategy_manager:
                try:
                    strategy_tf = self.strategy_manager.get_active_timeframe()
                    if strategy_tf:
                        old_tf = state.interval
                        state.interval = strategy_tf
                        if old_tf != strategy_tf:
                            logger.info(
                                f"[apply_settings_to_state] state.interval overridden by "
                                f"active strategy timeframe: {old_tf!r} → {strategy_tf!r}"
                            )
                        else:
                            logger.debug(
                                f"[apply_settings_to_state] state.interval confirmed "
                                f"from strategy: {strategy_tf!r}"
                            )
                except Exception as _tf_e:
                    logger.warning(
                        f"[apply_settings_to_state] Could not read strategy timeframe "
                        f"(using trade_config value): {_tf_e}"
                    )

            # FIX: lower_percentage/cancel_after/sideway_zone_trade must always run
            # under the trade_config guard — NOT inside if self.strategy_manager: block.
            # Previously they were inside strategy_manager block so when trading started
            # with no active strategy these critical values were never set.
            if self.trade_config:
                # lower_percentage is stored in DailyTradeSetting as a whole-number
                # percentage (e.g. 5 = 5%).  The engine (order_executor,
                # position_monitor) expects it as a decimal fraction (e.g. 0.05 = 5%).
                # Divide by 100 here so downstream code always receives a fraction.
                _raw_lower = float(safe_getattr(self.trade_config, "lower_percentage", 0) or 0)
                state.lower_percentage = _raw_lower / 100.0
                state.cancel_after = safe_getattr(self.trade_config, "cancel_after", 0)
                state.sideway_zone_trade = safe_getattr(self.trade_config, "sideway_zone_trade", False)

                # Risk limits — these are stored in DailyTradeSetting but were
                # never propagated to state at startup, so RiskManager was always
                # using the hardcoded TradeState defaults (-5000 / 10 / 5000)
                # instead of the user's saved values.
                state.max_daily_loss    = safe_getattr(self.trade_config, "max_daily_loss",    -5000.0)
                state.max_trades_per_day = safe_getattr(self.trade_config, "max_trades_per_day", 10)
                state.daily_target      = safe_getattr(self.trade_config, "daily_target",       5000.0)

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
                _tp = safe_getattr(plc, "tp_percentage", None)
                _sl = safe_getattr(plc, "stoploss_percentage", None)
                if _tp is not None: state.tp_percentage = state.original_profit_per = float(_tp)
                if _sl is not None: state.stoploss_percentage = state.original_stoploss_per = float(_sl)
                if _tp is None:
                    logger.warning("[apply_settings_to_state] tp_percentage missing from config — "
                                   f"keeping state default {state.tp_percentage}%")
                if _sl is None:
                    logger.warning("[apply_settings_to_state] stoploss_percentage missing from config — "
                                   f"keeping state default {state.stoploss_percentage}%")
                state.trailing_first_profit = safe_getattr(plc, "trailing_first_profit", state.trailing_first_profit)
                state.max_profit = safe_getattr(plc, "max_profit", state.max_profit)
                state.profit_step = safe_getattr(plc, "profit_step", state.profit_step)
                state.loss_step = safe_getattr(plc, "loss_step", state.loss_step)
                state.take_profit_type = safe_getattr(plc, "profit_type", state.take_profit_type)

            logger.info(f"[Settings] Applied trade and P/L configs - Capital: {state.capital_reserve}, "
                        f"Lot size: {state.lot_size}, TP: {state.tp_percentage}%, "
                        f"SL: {state.stoploss_percentage}%, "
                        f"MaxLoss: ₹{state.max_daily_loss:.0f}, MaxTrades: {state.max_trades_per_day}, "
                        f"Target: ₹{state.daily_target:.0f}")

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

            # DATA-3 fix: Close the trade session row in the DB
            try:
                state = state_manager.get_state()
                session_id = getattr(state, 'session_id', None)
                if session_id:
                    from db.connector import get_db
                    from db.crud import sessions as sessions_crud, orders as orders_crud
                    db = get_db()
                    today_orders = orders_crud.get_by_period('today', db=db)
                    total_pnl = sum(float(o.get('pnl') or 0) for o in today_orders)
                    total_trades = len(today_orders)
                    winning = sum(1 for o in today_orders if float(o.get('pnl') or 0) > 0)
                    losing = total_trades - winning
                    sessions_crud.close(
                        session_id=session_id,
                        total_pnl=total_pnl,
                        total_trades=total_trades,
                        winning_trades=winning,
                        losing_trades=losing,
                        db=db,
                    )
                    logger.info(f"[TradingApp.cleanup] Closed session id={session_id} pnl={total_pnl:.2f}")
            except Exception as _sess_err:
                logger.error(f"[TradingApp.cleanup] Session close failed: {_sess_err}", exc_info=True)

            # Clear caches
            self._indicator_cache.clear()
            self._last_bar_times.clear()

            self._cleanup_done = True
            logger.info("TradingApp cleanup completed")

        except Exception as e:
            logger.error(f"[TradingApp.cleanup] Error: {e}", exc_info=True)
            self._cleanup_done = True