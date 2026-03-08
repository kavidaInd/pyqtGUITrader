"""
trading_thread.py
=================
QThread wrapper for TradingApp with safe shutdown and correct timer ownership.

FIXES APPLIED
=============
FIX-3a  [CRITICAL] stop() called _perform_stop_operations() synchronously on the
         main thread, which issued broker API calls (exit_position, WS unsubscribe)
         blocking the GUI.  Fixed: stop() now ONLY sets the should_stop flag and
         arms the force-stop timer.  All cleanup runs inside TradingThread.run()'s
         finally block on the worker thread.

FIX-3b  [CRITICAL] QTimer() was constructed inside stop(), which may be called
         from any thread (e.g. risk_breach signal chain).  QTimers must be created
         on the GUI/main thread.  Fixed: replaced QTimer() construction with the
         thread-safe QTimer.singleShot() class method which is safe to call from
         any thread.

FIX-11a [LOW]     CooperativeTradingApp example class and __main__ test block
         removed — dead illustration code inflated the file and could confuse
         readers.
"""

import logging
import traceback
from typing import Any, Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal, QTimer, QMutex, QMutexLocker

from Utils.safe_getattr import safe_getattr, safe_hasattr
from broker.BaseBroker import TokenExpiredError
from data.trade_state_manager import state_manager

logger = logging.getLogger(__name__)


class TradingThread(QThread):
    """
    QThread wrapper for TradingApp.run().

    THREADING CONTRACT
    ------------------
    - __init__  : called on the GUI thread
    - run()     : executes on the worker thread — no Qt widget access
    - stop()    : called from the GUI thread (or any thread) — only sets
                  flags, never does I/O or constructs QObjects
    - cleanup() : called from the GUI thread after the thread has stopped

    SHUTDOWN SEQUENCE
    -----------------
    1. Caller invokes stop() (GUI thread or any thread).
    2. stop() sets trading_app.should_stop = True and wakes _stop_event,
       then arms a QTimer.singleShot force-stop watchdog.
    3. TradingApp.run()'s keep-alive loop exits because should_stop=True.
    4. TradingThread.run() falls into its finally block which calls
       _do_worker_cleanup() on the worker thread.
    5. QThread.finished signal fires, GUI resets its state.
    6. If the thread has not finished within _stop_timeout ms the
       QTimer.singleShot watchdog fires _force_stop() on the GUI thread.
    """

    # Qt signals
    started = pyqtSignal()
    finished = pyqtSignal()
    initialized = pyqtSignal()    # emitted after TradingApp.initialize() succeeds
    error_occurred = pyqtSignal(str)
    token_expired = pyqtSignal(str)          # emitted ONLY on TokenExpiredError
    status_update = pyqtSignal(str)
    position_closed = pyqtSignal(str, float) # symbol, pnl
    risk_breach = pyqtSignal(str)
    telegram_status = pyqtSignal(str, bool)
    stop_progress = pyqtSignal(int)

    def __init__(self, trading_app, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)
            self.trading_app = trading_app
            self._is_stopping = False
            self._stop_timeout = 10_000   # ms before force-stop fires
            self._mutex = QMutex()
            self._shared_state: Dict[str, Any] = {}
            self._connect_risk_signals()
            self._mtf_enabled = False
            logger.info("TradingThread initialised")
        except Exception as e:
            logger.critical(f"[TradingThread.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self.trading_app = trading_app
            self._is_stopping = False
            self._stop_timeout = 10_000
            self._mutex = QMutex()
            self._shared_state = {}

    def _safe_defaults_init(self):
        self.trading_app = None
        self._is_stopping = False
        self._stop_timeout = 10_000
        self._mutex = None
        self._shared_state: Dict[str, Any] = {}
        self._stop_attempts = 0
        self.MAX_STOP_ATTEMPTS = 3
        self._mtf_enabled = False

    def _connect_risk_signals(self):
        try:
            if (self.trading_app and
                    safe_hasattr(self.trading_app, 'risk_manager') and
                    self.trading_app.risk_manager):
                self.trading_app.risk_manager.risk_breach.connect(self.risk_breach.emit)
                logger.debug("Risk manager signals connected")
        except Exception as e:
            logger.error(f"[TradingThread._connect_risk_signals] Failed: {e}", exc_info=True)

    # -------------------------------------------------------------------------
    # Worker thread entry point
    # -------------------------------------------------------------------------

    def run(self):
        """Runs on the background worker thread."""
        try:
            if self.trading_app is None:
                msg = "Trading app is None, cannot run thread"
                logger.error(msg)
                self.error_occurred.emit(msg)
                return

            self.started.emit()
            self.status_update.emit("Trading thread started")
            logger.info("Trading thread started")

            if safe_hasattr(self.trading_app, 'config'):
                self._mtf_enabled = self.trading_app.config.get('use_mtf_filter', False)
                if self._mtf_enabled:
                    self.status_update.emit("Multi-Timeframe Filter enabled")

            # FIX-6: Run broker/network initialisation on the worker thread
            # so TradingApp.__init__() (called on the GUI thread) stays fast.
            if safe_hasattr(self.trading_app, 'initialize'):
                self.trading_app.initialize()

            # Signal GUI that broker is now live — safe to re-inject into
            # candle_store_manager and trigger initial chart fetch.
            self.initialized.emit()

            self.trading_app.run()

        except TokenExpiredError as e:
            msg = f"Token expired or invalid — re-authentication required. Details: {e}"
            logger.critical(msg, exc_info=True)
            self.token_expired.emit(msg)
            self.status_update.emit("Trading stopped: Token expired — please re-login")

        except AttributeError as e:
            msg = f"TradingThread attribute error: {e}"
            logger.error(msg, exc_info=True)
            self.error_occurred.emit(f"Internal error in trading thread: {e}")

        except Exception as e:
            msg = f"TradingThread crashed: {e}"
            logger.error(msg, exc_info=True)
            self.error_occurred.emit(f"{msg}\n\n{traceback.format_exc()}")

        finally:
            # FIX-3a: All I/O cleanup runs HERE on the worker thread.
            self._do_worker_cleanup()
            self.status_update.emit("Trading thread finished")
            logger.info("Trading thread finished")
            self.finished.emit()

    def _do_worker_cleanup(self):
        """
        I/O cleanup on the WORKER THREAD inside run()'s finally block.

        This replaces the old _perform_stop_operations() which was incorrectly
        called from the GUI thread via stop() -> _schedule_stop_in_thread().
        """
        try:
            self.stop_progress.emit(30)

            if self.trading_app is None:
                self.stop_progress.emit(100)
                return

            # Exit any open position
            try:
                state = state_manager.get_state()
                current_position = getattr(state, 'current_position', None)
            except Exception:
                current_position = None

            if current_position:
                self.status_update.emit(f"Exiting position: {current_position}")
                logger.info(f"Exiting position during shutdown: {current_position}")
                executor = safe_getattr(self.trading_app, 'executor', None)
                if executor:
                    try:
                        pnl = executor.exit_position(reason="Manual stop - app exit")
                        if pnl is not None:
                            self.position_closed.emit(str(current_position), float(pnl))
                    except TokenExpiredError as e:
                        logger.critical(f"Token expired while exiting position: {e}", exc_info=True)
                        self.token_expired.emit(
                            f"Token expired during position exit — re-authentication required. Details: {e}"
                        )
                    except Exception as e:
                        logger.error(f"Error exiting position: {e}", exc_info=True)
                        self.error_occurred.emit(f"Error during position exit: {e}")

            self.stop_progress.emit(60)

            # Unsubscribe WebSocket
            self.status_update.emit("Disconnecting from WebSocket...")
            ws = safe_getattr(self.trading_app, 'ws', None)
            if ws and safe_hasattr(ws, 'unsubscribe'):
                try:
                    ws.unsubscribe()
                    logger.info("WebSocket unsubscribed")
                except Exception as e:
                    logger.error(f"WebSocket unsubscribe error: {e}", exc_info=True)

            self.stop_progress.emit(80)
            self._log_risk_summary()
            self._send_shutdown_notification()

            # Full app cleanup
            self.status_update.emit("Cleaning up resources...")
            if safe_hasattr(self.trading_app, 'cleanup'):
                try:
                    self.trading_app.cleanup()
                    logger.info("Trading app cleanup completed")
                except Exception as e:
                    logger.error(f"Cleanup error: {e}", exc_info=True)

            # Reset state manager
            self.status_update.emit("Resetting state manager...")
            try:
                state_manager.reset_for_backtest()
                logger.info("State manager reset completed")
            except Exception as e:
                logger.error(f"State manager reset error: {e}", exc_info=True)

            self.stop_progress.emit(100)
            self.status_update.emit("Shutdown complete")
            logger.info("Graceful shutdown completed")

        except Exception as e:
            logger.error(f"Error during worker cleanup: {e}", exc_info=True)
            self.error_occurred.emit(f"Error during shutdown: {e}")

    # -------------------------------------------------------------------------
    # Stop API (safe to call from any thread)
    # -------------------------------------------------------------------------

    def stop(self):
        """
        Request graceful shutdown.

        FIX-3a: Only sets flags — does NOT call broker APIs or do any I/O.
        FIX-3b: Uses QTimer.singleShot() (thread-safe) instead of
                constructing a QTimer() object (requires GUI thread).
        """
        try:
            if self._is_stopping or not self.isRunning():
                logger.debug(
                    f"Stop called but not applicable. "
                    f"is_stopping={self._is_stopping}, isRunning={self.isRunning()}"
                )
                return

            self._is_stopping = True
            self._stop_attempts = 0
            self.status_update.emit("Initiating graceful shutdown...")
            logger.info("Initiating graceful thread shutdown")

            # Signal TradingApp.run()'s keep-alive loop to exit.
            if self.trading_app is not None:
                self.trading_app.should_stop = True
                stop_event = safe_getattr(self.trading_app, '_stop_event', None)
                if stop_event is not None:
                    stop_event.set()

            # FIX-3b: QTimer.singleShot() is thread-safe; QTimer() is not.
            QTimer.singleShot(self._stop_timeout, self._force_stop)

        except Exception as e:
            logger.error(f"[TradingThread.stop] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to initiate stop: {e}")

    def request_stop(self):
        """Preferred stop entry point; sets should_stop flag then delegates to stop()."""
        try:
            if self.trading_app and safe_hasattr(self.trading_app, 'should_stop'):
                self.trading_app.should_stop = True
                self.status_update.emit("Stop requested")
                logger.info("Stop requested via should_stop flag")
                self._send_stop_notification()
            self.stop()
        except Exception as e:
            logger.error(f"[TradingThread.request_stop] Failed: {e}", exc_info=True)
            self.stop()

    def _force_stop(self):
        """
        Force-terminate if graceful shutdown exceeded _stop_timeout.
        Runs on the GUI thread (fired by QTimer.singleShot).
        """
        try:
            if not self.isRunning() or not self._is_stopping:
                return   # Thread already finished cleanly

            self._stop_attempts += 1
            logger.warning(
                f"Force-stopping thread (attempt {self._stop_attempts}): "
                f"did not finish within {self._stop_timeout}ms"
            )
            self.status_update.emit("Force stopping thread (timeout)")
            self.error_occurred.emit(
                "Thread did not stop gracefully within timeout. "
                "Force terminating. Some resources may not be cleaned up properly."
            )

            self.terminate()

            if not self.wait(2_000):
                logger.error("Thread refused to terminate after force stop")
                if self._stop_attempts < self.MAX_STOP_ATTEMPTS:
                    QTimer.singleShot(200, self._force_stop)
                    return

            self._is_stopping = False
            if not self.isRunning():
                self.finished.emit()

            logger.warning("Thread force stop completed")

        except Exception as e:
            logger.error(f"[TradingThread._force_stop] Failed: {e}", exc_info=True)
            self._is_stopping = False
            self.finished.emit()

    def is_stopping(self) -> bool:
        return self._is_stopping

    def wait_for_finished(self, timeout: int = 30_000) -> bool:
        try:
            if timeout <= 0:
                timeout = 30_000
            return self.wait(timeout)
        except Exception as e:
            logger.error(f"[TradingThread.wait_for_finished] Failed: {e}", exc_info=True)
            return False

    # -------------------------------------------------------------------------
    # Thread-safe shared state
    # -------------------------------------------------------------------------

    def set_shared_state(self, key: str, value: Any) -> None:
        try:
            if self._mutex:
                locker = QMutexLocker(self._mutex)
                self._shared_state[key] = value
        except Exception as e:
            logger.error(f"[TradingThread.set_shared_state] key={key}: {e}", exc_info=True)

    def get_shared_state(self, key: str, default: Any = None) -> Any:
        try:
            if self._mutex:
                locker = QMutexLocker(self._mutex)
                return self._shared_state.get(key, default)
            return default
        except Exception as e:
            logger.error(f"[TradingThread.get_shared_state] key={key}: {e}", exc_info=True)
            return default

    # -------------------------------------------------------------------------
    # Notification helpers
    # -------------------------------------------------------------------------

    def _log_risk_summary(self):
        try:
            risk_manager = safe_getattr(self.trading_app, 'risk_manager', None) if self.trading_app else None
            if risk_manager:
                summary = risk_manager.get_risk_summary(self.trading_app.config)
                logger.info(f"Risk summary at shutdown: {summary}")
                self.status_update.emit(
                    f"Daily P&L: ₹{summary.get('pnl_today', 0):.2f} | "
                    f"Trades: {summary.get('trades_today', 0)}"
                )
        except Exception as e:
            logger.error(f"[TradingThread._log_risk_summary] Failed: {e}", exc_info=True)

    def _send_shutdown_notification(self):
        try:
            notifier = safe_getattr(self.trading_app, 'notifier', None) if self.trading_app else None
            if not notifier:
                return
            try:
                state = state_manager.get_state()
                pnl = getattr(state, 'current_pnl', 0.0) or 0.0
            except Exception:
                pnl = 0.0
            emoji = '✅' if pnl >= 0 else '❌'
            msg = f"{emoji} *BOT SHUTDOWN*\nFinal P&L: ₹{pnl:.2f}"
            if safe_hasattr(notifier, 'notify_shutdown'):
                notifier.notify_shutdown(pnl)
            elif safe_hasattr(notifier, '_pool') and safe_hasattr(notifier, '_send'):
                notifier._pool.submit(notifier._send, msg)
        except Exception as e:
            logger.error(f"[TradingThread._send_shutdown_notification] Failed: {e}", exc_info=True)

    def _send_stop_notification(self):
        try:
            notifier = safe_getattr(self.trading_app, 'notifier', None) if self.trading_app else None
            if not notifier:
                return
            msg = "🛑 *STOP REQUESTED*\nBot is shutting down gracefully..."
            if safe_hasattr(notifier, '_pool') and safe_hasattr(notifier, '_send'):
                notifier._pool.submit(notifier._send, msg)
        except Exception as e:
            logger.error(f"[TradingThread._send_stop_notification] Failed: {e}", exc_info=True)

    # -------------------------------------------------------------------------
    # Cleanup (called from GUI thread after thread has stopped)
    # -------------------------------------------------------------------------

    def cleanup(self):
        """GUI-thread cleanup after the worker has already stopped."""
        try:
            logger.info("[TradingThread] Starting GUI-thread cleanup")
            if self.isRunning():
                self.request_stop()
                if not self.wait(5_000):
                    logger.warning("Thread did not stop during cleanup, terminating")
                    self.terminate()
                    self.wait(2_000)
            logger.info("[TradingThread] Cleanup completed")
        except Exception as e:
            logger.error(f"[TradingThread.cleanup] Error: {e}", exc_info=True)


# ── Context manager ───────────────────────────────────────────────────────────

class TradingThreadManager:
    """Context manager for safe TradingThread lifecycle management."""

    def __init__(self, trading_thread: TradingThread):
        self.thread: Optional[TradingThread] = None
        try:
            if trading_thread is None:
                raise ValueError("trading_thread cannot be None")
            self.thread = trading_thread
        except Exception as e:
            logger.error(f"[TradingThreadManager.__init__] Failed: {e}", exc_info=True)
            self.thread = trading_thread

    def __enter__(self):
        return self.thread

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.thread and self.thread.isRunning():
                logger.info("TradingThreadManager cleaning up thread")
                self.thread.request_stop()
                if not self.thread.wait_for_finished(10_000):
                    if self.thread.isRunning():
                        logger.warning("Thread timeout in context manager, forcing termination")
                        self.thread.terminate()
                        self.thread.wait(2_000)
            if exc_type:
                logger.error(
                    f"Exception in context: {exc_type.__name__}: {exc_val}",
                    exc_info=exc_val
                )
        except Exception as e:
            logger.error(f"[TradingThreadManager.__exit__] Failed: {e}", exc_info=True)