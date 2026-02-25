import logging.handlers
import traceback
from typing import Any, Dict

from PyQt5.QtCore import QThread, pyqtSignal, QTimer, QMutex, QMutexLocker

# Import the custom exception from Broker
from broker.Broker import TokenExpiredError

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TradingThread(QThread):
    """
    # PYQT: Wraps TradingApp.run() in a QThread so it never blocks the GUI.
    # Signals are the only safe way to communicate results back to the main thread.
    """

    # Status signals - Rule 3: Typed signals
    started = pyqtSignal()
    finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    token_expired = pyqtSignal(str)   # Dedicated signal: emitted ONLY on TokenExpiredError
    status_update = pyqtSignal(str)  # For general status messages
    position_closed = pyqtSignal(str, float)  # symbol, pnl

    # Progress signals
    stop_progress = pyqtSignal(int)  # Progress percentage during stop

    def __init__(self, trading_app, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.trading_app = trading_app
            self._is_stopping = False
            self._stop_timeout = 10000  # 10 seconds timeout for stop operation
            self._stop_timer = None
            # Rule 5: Thread safety with QMutex
            self._mutex = QMutex()
            self._shared_state: Dict[str, Any] = {}

            logger.info("TradingThread initialized")

        except Exception as e:
            logger.critical(f"[TradingThread.__init__] Failed: {e}", exc_info=True)
            # Still try to set up basic object
            super().__init__(parent)
            self.trading_app = trading_app
            self._is_stopping = False
            self._stop_timeout = 10000
            self._stop_timer = None
            self._mutex = QMutex()
            self._shared_state = {}

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.trading_app = None
        self._is_stopping = False
        self._stop_timeout = 10000
        self._stop_timer = None
        self._mutex = None
        self._shared_state = {}
        self._stop_attempts = 0
        self.MAX_STOP_ATTEMPTS = 3

    def run(self):
        """
        # PYQT: This method runs on the background thread
        Main trading loop - should never directly interact with GUI
        """
        try:
            # Validate trading_app exists
            if self.trading_app is None:
                error_msg = "Trading app is None, cannot run thread"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                self.finished.emit()
                return

            # Emit started signal
            self.started.emit()
            self.status_update.emit("Trading thread started")
            logger.info("Trading thread started")

            # Run the main trading application
            self.trading_app.run()

        except TokenExpiredError as e:
            # FIX: Emit dedicated token_expired signal so the GUI can open the
            # re-authentication popup directly, without fragile string-matching.
            error_msg = f"Token expired or invalid — re-authentication required. Details: {e}"
            logger.critical(error_msg, exc_info=True)
            self.token_expired.emit(error_msg)        # ← dedicated signal
            self.status_update.emit("Trading stopped: Token expired — please re-login")

        except AttributeError as e:
            error_msg = f"TradingThread attribute error: {e}"
            logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(f"Internal error in trading thread: {e}")

        except Exception as e:
            # Log full traceback for debugging
            error_msg = f"TradingThread crashed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            logger.error(traceback.format_exc())

            # Emit error signal (safe because it's a Qt signal)
            self.error_occurred.emit(f"{error_msg}\n\n{traceback.format_exc()}")

        finally:
            # Always emit finished signal
            self.status_update.emit("Trading thread finished")
            logger.info("Trading thread finished")
            self.finished.emit()

    def stop(self):
        """
        Gracefully stop trading thread.
        This method is called from the main thread but schedules work on the worker thread.
        """
        try:
            # Rule 6: Input validation
            if self._is_stopping or not self.isRunning():
                logger.debug(
                    f"Stop called but thread not running or already stopping. is_stopping={self._is_stopping}, isRunning={self.isRunning()}")
                return

            self._is_stopping = True
            self._stop_attempts = 0
            self.status_update.emit("Initiating graceful shutdown...")
            logger.info("Initiating graceful thread shutdown")

            # Set up timeout timer
            self._stop_timer = QTimer()
            self._stop_timer.setSingleShot(True)
            self._stop_timer.timeout.connect(self._force_stop)
            self._stop_timer.start(self._stop_timeout)

            # Schedule the stop work to run in the thread
            # We use a custom event or signal to execute in thread context
            self._schedule_stop_in_thread()

        except Exception as e:
            logger.error(f"[TradingThread.stop] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Failed to initiate stop: {e}")

    def _schedule_stop_in_thread(self):
        """Schedule stop operations to run in the worker thread"""
        try:
            # Since we can't directly call methods in the thread, we use a signal
            # that's connected to a slot that runs in this thread's context
            # For simplicity, we'll create a custom event in a real implementation
            self.stop_progress.emit(10)

            # This would ideally be done with a custom QEvent or by setting a flag
            # that the trading loop checks periodically
            self._perform_stop_operations()

        except Exception as e:
            logger.error(f"[TradingThread._schedule_stop_in_thread] Failed: {e}", exc_info=True)
            self.error_occurred.emit(f"Error scheduling stop operations: {e}")

    def _perform_stop_operations(self):
        """
        Actual stop operations - should be called from within the thread context.
        In practice, you'd want the trading_app to check a 'should_stop' flag
        periodically rather than calling this directly.
        """
        try:
            self.status_update.emit("Closing positions...")
            self.stop_progress.emit(30)

            # Rule 5: Thread-safe access to trading_app
            if self.trading_app is None:
                logger.warning("Trading app is None during stop operations")
                self.stop_progress.emit(100)
                return

            # Access state safely (if thread-safe)
            state = getattr(self.trading_app, "state", None)

            # Check if there's an open position to exit
            current_position = None
            if state and hasattr(state, "current_position"):
                current_position = state.current_position

            if current_position:
                self.status_update.emit(f"Exiting position: {current_position}")
                logger.info(f"Exiting position during shutdown: {current_position}")

                # Execute position exit
                if hasattr(self.trading_app, "executor") and self.trading_app.executor:
                    try:
                        # This would ideally be a non-blocking call or run in thread
                        pnl = self.trading_app.executor.exit_position(
                            state,
                            reason="Manual stop - app exit"
                        )
                        if pnl is not None:
                            self.position_closed.emit(str(current_position), float(pnl))
                            logger.info(f"Position closed with P&L: {pnl}")
                    except TokenExpiredError as e:
                        # Emit dedicated signal so GUI opens login popup immediately
                        logger.critical(f"Token expired while exiting position: {e}", exc_info=True)
                        self.token_expired.emit(
                            f"Token expired during position exit — re-authentication required. Details: {e}"
                        )
                    except AttributeError as e:
                        logger.error(f"Executor attribute error during exit: {e}", exc_info=True)
                    except Exception as e:
                        logger.error(f"Error exiting position: {e}", exc_info=True)
                        self.error_occurred.emit(f"Error during position exit: {e}")

                self.stop_progress.emit(60)

            # Unsubscribe from WebSocket
            self.status_update.emit("Disconnecting from WebSocket...")
            if hasattr(self.trading_app, "ws") and self.trading_app.ws:
                try:
                    if hasattr(self.trading_app.ws, "unsubscribe"):
                        self.trading_app.ws.unsubscribe()
                        logger.info("WebSocket unsubscribed")
                except AttributeError as e:
                    logger.warning(f"WebSocket unsubscribe method not available: {e}")
                except Exception as e:
                    logger.error(f"WebSocket unsubscribe error: {e}", exc_info=True)

            self.stop_progress.emit(90)

            # Additional cleanup
            self.status_update.emit("Cleaning up resources...")
            if hasattr(self.trading_app, "cleanup"):
                try:
                    self.trading_app.cleanup()
                    logger.info("Trading app cleanup completed")
                except Exception as e:
                    logger.error(f"Cleanup error: {e}", exc_info=True)

            self.stop_progress.emit(100)
            self.status_update.emit("Shutdown complete")
            logger.info("Graceful shutdown completed successfully")

            # Cancel timeout timer since we finished successfully
            if self._stop_timer:
                try:
                    self._stop_timer.stop()
                    self._stop_timer = None
                except Exception as e:
                    logger.warning(f"Timer cleanup error: {e}")

        except Exception as e:
            logger.error(f"Error during stop operations: {e}", exc_info=True)
            self.error_occurred.emit(f"Error during shutdown: {str(e)}")

    def _force_stop(self):
        """
        Force stop if graceful shutdown times out.
        This runs in the main thread and forcefully terminates the thread.
        """
        try:
            if self.isRunning() and self._is_stopping:
                self._stop_attempts += 1
                logger.warning(f"Forcing thread termination due to timeout (attempt {self._stop_attempts})")
                self.status_update.emit("Force stopping thread (timeout)")

                # Log warning
                self.error_occurred.emit(
                    "Thread did not stop gracefully within timeout. "
                    "Force terminating. Some resources may not be cleaned up properly."
                )

                # Force terminate (use with caution!)
                self.terminate()

                # Wait up to 2 seconds for termination
                if not self.wait(2000):
                    logger.error("Thread refused to terminate after force stop")

                    if self._stop_attempts < self.MAX_STOP_ATTEMPTS:
                        # Try again with shorter timeout
                        logger.info(f"Retrying force stop (attempt {self._stop_attempts + 1})")
                        QTimer.singleShot(100, self._force_stop)
                        return

                if self.isRunning():
                    logger.error("Thread still running after multiple termination attempts")

                self._stop_timer = None
                self._is_stopping = False

                # Emit finished (we're done, even if not clean)
                self.finished.emit()
                logger.warning("Thread force stop completed")

        except Exception as e:
            logger.error(f"[TradingThread._force_stop] Failed: {e}", exc_info=True)
            self._is_stopping = False
            self.finished.emit()

    def is_stopping(self) -> bool:
        """Check if thread is in the process of stopping"""
        try:
            return self._is_stopping
        except Exception as e:
            logger.error(f"[TradingThread.is_stopping] Failed: {e}", exc_info=True)
            return False

    def request_stop(self):
        """
        Request the trading loop to stop by setting a flag.
        This is the preferred way to stop - the trading loop should check
        a 'should_stop' flag periodically.
        """
        try:
            if self.trading_app and hasattr(self.trading_app, 'should_stop'):
                self.trading_app.should_stop = True
                self.status_update.emit("Stop requested")
                logger.info("Stop requested via should_stop flag")
            else:
                # Fall back to old stop method
                logger.warning("Trading app does not support should_stop flag, using fallback stop")
                self.stop()

        except AttributeError as e:
            logger.error(f"Attribute error in request_stop: {e}", exc_info=True)
            self.stop()
        except Exception as e:
            logger.error(f"[TradingThread.request_stop] Failed: {e}", exc_info=True)
            self.stop()

    def wait_for_finished(self, timeout: int = 30000) -> bool:
        """
        Wait for thread to finish with timeout.

        Args:
            timeout: Maximum time to wait in milliseconds

        Returns:
            True if finished, False if timeout
        """
        try:
            # Rule 6: Input validation
            if timeout <= 0:
                logger.warning(f"Invalid timeout value {timeout}, using default 30000")
                timeout = 30000

            return self.wait(timeout)

        except Exception as e:
            logger.error(f"[TradingThread.wait_for_finished] Failed: {e}", exc_info=True)
            return False

    # Rule 5: Thread-safe state access methods
    def set_shared_state(self, key: str, value: Any) -> None:
        """Thread-safe method to set shared state"""
        try:
            if self._mutex:
                locker = QMutexLocker(self._mutex)
                self._shared_state[key] = value
                logger.debug(f"Shared state updated: {key}={value}")
        except Exception as e:
            logger.error(f"[TradingThread.set_shared_state] Failed for key={key}: {e}", exc_info=True)

    def get_shared_state(self, key: str, default: Any = None) -> Any:
        """Thread-safe method to get shared state"""
        try:
            if self._mutex:
                locker = QMutexLocker(self._mutex)
                return self._shared_state.get(key, default)
            return default
        except Exception as e:
            logger.error(f"[TradingThread.get_shared_state] Failed for key={key}: {e}", exc_info=True)
            return default

    # Rule 8: Cleanup method
    def cleanup(self):
        """Graceful cleanup of resources"""
        try:
            logger.info("[TradingThread] Starting cleanup")

            # Stop timer if running
            if hasattr(self, '_stop_timer') and self._stop_timer:
                try:
                    if self._stop_timer.isActive():
                        self._stop_timer.stop()
                    self._stop_timer = None
                except Exception as e:
                    logger.warning(f"Timer cleanup error: {e}")

            # Request thread stop if running
            if self.isRunning():
                self.request_stop()
                if not self.wait(5000):  # Wait up to 5 seconds
                    logger.warning("Thread did not stop during cleanup, terminating")
                    self.terminate()
                    self.wait(2000)

            logger.info("[TradingThread] Cleanup completed")

        except Exception as e:
            logger.error(f"[TradingThread.cleanup] Error: {e}", exc_info=True)


# Optional: Context manager for safe thread handling
class TradingThreadManager:
    """Context manager for safe TradingThread lifecycle management"""

    def __init__(self, trading_thread: TradingThread):
        # Rule 2: Safe defaults
        self.thread = None

        try:
            # Rule 6: Input validation
            if trading_thread is None:
                raise ValueError("trading_thread cannot be None")
            self.thread = trading_thread
            logger.debug("TradingThreadManager initialized")
        except Exception as e:
            logger.error(f"[TradingThreadManager.__init__] Failed: {e}", exc_info=True)
            self.thread = trading_thread  # Still try to set it

    def __enter__(self):
        return self.thread

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.thread and self.thread.isRunning():
                logger.info("TradingThreadManager cleaning up thread")

                # Request stop
                self.thread.request_stop()

                # Wait for finish with timeout
                if not self.thread.wait_for_finished(10000):
                    # Force stop if timeout
                    if self.thread.isRunning():
                        logger.warning("Thread timeout in context manager, forcing termination")
                        self.thread.terminate()
                        self.thread.wait(2000)

            # Log any exception that occurred in the context
            if exc_type:
                logger.error(f"Exception in context: {exc_type.__name__}: {exc_val}", exc_info=exc_val)

        except Exception as e:
            logger.error(f"[TradingThreadManager.__exit__] Failed: {e}", exc_info=True)


# Example of how TradingApp could support cooperative stopping
class CooperativeTradingApp:
    """
    Example of a TradingApp that supports cooperative stopping.
    This is just an illustration - integrate with your actual TradingApp.
    """

    def __init__(self):
        # Rule 2: Safe defaults
        self._safe_defaults_init()

        try:
            self.should_stop = False
            self.state = None
            self.executor = None
            self.ws = None
            logger.info("CooperativeTradingApp initialized")
        except Exception as e:
            logger.error(f"[CooperativeTradingApp.__init__] Failed: {e}", exc_info=True)

    def _safe_defaults_init(self):
        """Initialize all attributes with safe defaults"""
        self.should_stop = False
        self.state = None
        self.executor = None
        self.ws = None
        self._cycle_count = 0
        self.MAX_CYCLES = 1000

    def run(self):
        """Main trading loop that checks should_stop periodically"""
        try:
            logger.info("CooperativeTradingApp run started")

            while not self.should_stop:
                try:
                    # Do trading work in small chunks
                    self._process_trading_cycle()

                    self._cycle_count += 1

                    # Prevent infinite loops
                    if self._cycle_count > self.MAX_CYCLES:
                        logger.warning(f"Reached max cycles ({self.MAX_CYCLES}), stopping")
                        break

                    # Check stop flag frequently
                    if self.should_stop:
                        logger.info("Stop requested, exiting trading loop")
                        break

                except TokenExpiredError as e:
                    # Handle token expiration
                    logger.error(f"Token expired in trading loop: {e}", exc_info=True)
                    # Re-raise to be caught by outer handler
                    raise
                except Exception as e:
                    logger.error(f"Trading cycle error: {e}", exc_info=True)
                    # Don't break on errors, but maybe limit retries

            # Cleanup after loop ends
            self._cleanup()

            logger.info("CooperativeTradingApp run finished")

        except Exception as e:
            logger.error(f"[CooperativeTradingApp.run] Failed: {e}", exc_info=True)
            raise

    def _process_trading_cycle(self):
        """One iteration of trading logic"""
        try:
            # Your existing trading logic here
            pass
        except Exception as e:
            logger.error(f"[CooperativeTradingApp._process_trading_cycle] Failed: {e}", exc_info=True)

    def _cleanup(self):
        """Cleanup resources"""
        try:
            if self.ws:
                try:
                    if hasattr(self.ws, "unsubscribe"):
                        self.ws.unsubscribe()
                    logger.info("WebSocket cleaned up")
                except Exception as e:
                    logger.warning(f"WebSocket cleanup error: {e}")
        except Exception as e:
            logger.error(f"[CooperativeTradingApp._cleanup] Failed: {e}", exc_info=True)


# Test code (for debugging)
if __name__ == "__main__":
    # This test won't run in PyQt environment but shows usage
    import sys
    from PyQt5.QtWidgets import QApplication


    class MockTradingApp:
        def __init__(self):
            # Rule 2: Safe defaults
            self.state = None
            self.executor = None
            self.ws = None
            self.should_stop = False

            try:
                self.state = type('State', (), {'current_position': 'NIFTY'})()
                self.executor = type('Executor', (), {'exit_position': lambda s, r: 100})()
                self.ws = type('WS', (), {'unsubscribe': lambda: None})()
            except Exception as e:
                logger.error(f"[MockTradingApp.__init__] Failed: {e}", exc_info=True)

        def run(self):
            try:
                import time
                for i in range(10):
                    if self.should_stop:
                        logger.info("Stop requested, breaking")
                        break
                    time.sleep(1)
                    print(f"Trading... {i}")
                    # Simulate token expiration for testing
                    if i == 5:
                        raise TokenExpiredError("Test token expiration")
            except Exception as e:
                logger.error(f"[MockTradingApp.run] Failed: {e}", exc_info=True)
                raise


    # Set up logging for test
    logging.basicConfig(level=logging.DEBUG)

    app = QApplication(sys.argv)

    # Create and start thread
    trading_app = MockTradingApp()
    thread = TradingThread(trading_app)

    # Connect signals
    thread.started.connect(lambda: print("Thread started"))
    thread.finished.connect(lambda: print("Thread finished"))
    thread.error_occurred.connect(lambda e: print(f"Error: {e}"))
    thread.status_update.connect(lambda s: print(f"Status: {s}"))

    # Start thread
    thread.start()

    # Stop after 3 seconds
    QTimer.singleShot(3000, thread.request_stop)

    sys.exit(app.exec_())