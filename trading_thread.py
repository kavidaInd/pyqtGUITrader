# PYQT: QThread wrapper for TradingApp to keep GUI responsive
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
import logging
import traceback
from typing import Optional
import time

# Import the custom exception from Broker
from broker.Broker import TokenExpiredError

logger = logging.getLogger(__name__)


class TradingThread(QThread):
    """
    # PYQT: Wraps TradingApp.run() in a QThread so it never blocks the GUI.
    # Signals are the only safe way to communicate results back to the main thread.
    """

    # Status signals
    started = pyqtSignal()
    finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)  # For general status messages
    position_closed = pyqtSignal(str, float)  # symbol, pnl

    # Progress signals
    stop_progress = pyqtSignal(int)  # Progress percentage during stop

    def __init__(self, trading_app, parent=None):
        super().__init__(parent)
        self.trading_app = trading_app
        self._is_stopping = False
        self._stop_timeout = 10000  # 10 seconds timeout for stop operation
        self._stop_timer = None
        self._mutex = None  # Would use QMutex in real implementation

    def run(self):
        """
        # PYQT: This method runs on the background thread
        Main trading loop - should never directly interact with GUI
        """
        try:
            # Emit started signal
            self.started.emit()
            self.status_update.emit("Trading thread started")

            # Run the main trading application
            self.trading_app.run()

        except TokenExpiredError as e:
            # FIX: Handle token expiration gracefully
            error_msg = f"Token expired — please re-login via Settings → Fyers Login. Details: {e}"
            logger.error(error_msg, exc_info=True)
            # Emit error signal (safe because it's a Qt signal)
            self.error_occurred.emit(error_msg)
            self.status_update.emit("Trading stopped: Token expired")

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
            self.finished.emit()

    def stop(self):
        """
        Gracefully stop trading thread.
        This method is called from the main thread but schedules work on the worker thread.
        """
        if self._is_stopping or not self.isRunning():
            return

        self._is_stopping = True
        self.status_update.emit("Initiating graceful shutdown...")

        # Set up timeout timer
        self._stop_timer = QTimer()
        self._stop_timer.setSingleShot(True)
        self._stop_timer.timeout.connect(self._force_stop)
        self._stop_timer.start(self._stop_timeout)

        # Schedule the stop work to run in the thread
        # We use a custom event or signal to execute in thread context
        self._schedule_stop_in_thread()

    def _schedule_stop_in_thread(self):
        """Schedule stop operations to run in the worker thread"""
        # Since we can't directly call methods in the thread, we use a signal
        # that's connected to a slot that runs in this thread's context
        # For simplicity, we'll create a custom event in a real implementation
        self.stop_progress.emit(10)

        # This would ideally be done with a custom QEvent or by setting a flag
        # that the trading loop checks periodically
        self._perform_stop_operations()

    def _perform_stop_operations(self):
        """
        Actual stop operations - should be called from within the thread context.
        In practice, you'd want the trading_app to check a 'should_stop' flag
        periodically rather than calling this directly.
        """
        try:
            self.status_update.emit("Closing positions...")
            self.stop_progress.emit(30)

            # Access state safely (if thread-safe)
            state = getattr(self.trading_app, "state", None)

            # Check if there's an open position to exit
            current_position = None
            if state and hasattr(state, "current_position"):
                current_position = state.current_position

            if current_position:
                self.status_update.emit(f"Exiting position: {current_position}")

                # Execute position exit
                if hasattr(self.trading_app, "executor"):
                    try:
                        # This would ideally be a non-blocking call or run in thread
                        pnl = self.trading_app.executor.exit_position(
                            state,
                            reason="Manual stop - app exit"
                        )
                        if pnl is not None:
                            self.position_closed.emit(str(current_position), float(pnl))
                    except TokenExpiredError as e:
                        # Handle token expiration during exit
                        logger.error(f"Token expired while exiting position: {e}")
                        self.error_occurred.emit(
                            f"Token expired during exit - please re-login via Settings → Fyers Login"
                        )
                    except Exception as e:
                        logger.error(f"Error exiting position: {e}")

                self.stop_progress.emit(60)

            # Unsubscribe from WebSocket
            self.status_update.emit("Disconnecting from WebSocket...")
            if hasattr(self.trading_app, "ws") and self.trading_app.ws:
                try:
                    self.trading_app.ws.unsubscribe()
                except Exception as e:
                    logger.error(f"WebSocket unsubscribe error: {e}")

            self.stop_progress.emit(90)

            # Additional cleanup
            self.status_update.emit("Cleaning up resources...")
            if hasattr(self.trading_app, "cleanup"):
                try:
                    self.trading_app.cleanup()
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")

            self.stop_progress.emit(100)
            self.status_update.emit("Shutdown complete")

            # Cancel timeout timer since we finished successfully
            if self._stop_timer:
                self._stop_timer.stop()
                self._stop_timer = None

        except Exception as e:
            logger.error(f"Error during stop operations: {e}", exc_info=True)
            self.error_occurred.emit(f"Error during shutdown: {str(e)}")

    def _force_stop(self):
        """
        Force stop if graceful shutdown times out.
        This runs in the main thread and forcefully terminates the thread.
        """
        if self.isRunning() and self._is_stopping:
            logger.warning("Forcing thread termination due to timeout")
            self.status_update.emit("Force stopping thread (timeout)")

            # Log warning
            self.error_occurred.emit(
                "Thread did not stop gracefully within timeout. "
                "Force terminating. Some resources may not be cleaned up properly."
            )

            # Force terminate (use with caution!)
            self.terminate()
            self.wait(2000)  # Wait up to 2 seconds for termination

            if self.isRunning():
                logger.error("Thread refused to terminate!")

            self._stop_timer = None
            self._is_stopping = False

            # Emit finished (we're done, even if not clean)
            self.finished.emit()

    def is_stopping(self) -> bool:
        """Check if thread is in the process of stopping"""
        return self._is_stopping

    def request_stop(self):
        """
        Request the trading loop to stop by setting a flag.
        This is the preferred way to stop - the trading loop should check
        a 'should_stop' flag periodically.
        """
        if hasattr(self.trading_app, 'should_stop'):
            self.trading_app.should_stop = True
            self.status_update.emit("Stop requested")
        else:
            # Fall back to old stop method
            self.stop()

    def wait_for_finished(self, timeout: int = 30000) -> bool:
        """
        Wait for thread to finish with timeout.

        Args:
            timeout: Maximum time to wait in milliseconds

        Returns:
            True if finished, False if timeout
        """
        return self.wait(timeout)


# Optional: Context manager for safe thread handling
class TradingThreadManager:
    """Context manager for safe TradingThread lifecycle management"""

    def __init__(self, trading_thread: TradingThread):
        self.thread = trading_thread

    def __enter__(self):
        return self.thread

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.thread.isRunning():
            # Request stop
            self.thread.request_stop()

            # Wait for finish with timeout
            if not self.thread.wait_for_finished(10000):
                # Force stop if timeout
                if self.thread.isRunning():
                    self.thread.terminate()
                    self.thread.wait(2000)


# Example of how TradingApp could support cooperative stopping
class CooperativeTradingApp:
    """
    Example of a TradingApp that supports cooperative stopping.
    This is just an illustration - integrate with your actual TradingApp.
    """

    def __init__(self):
        self.should_stop = False
        self.state = None
        self.executor = None
        self.ws = None

    def run(self):
        """Main trading loop that checks should_stop periodically"""
        while not self.should_stop:
            try:
                # Do trading work in small chunks
                self._process_trading_cycle()

                # Check stop flag frequently
                if self.should_stop:
                    logger.info("Stop requested, exiting trading loop")
                    break

            except TokenExpiredError as e:
                # Handle token expiration
                logger.error(f"Token expired in trading loop: {e}")
                # Re-raise to be caught by outer handler
                raise
            except Exception as e:
                logger.error(f"Trading cycle error: {e}")
                # Don't break on errors, but maybe limit retries

        # Cleanup after loop ends
        self._cleanup()

    def _process_trading_cycle(self):
        """One iteration of trading logic"""
        # Your existing trading logic here
        pass

    def _cleanup(self):
        """Cleanup resources"""
        if self.ws:
            try:
                self.ws.unsubscribe()
            except:
                pass


# Test code (for debugging)
if __name__ == "__main__":
    # This test won't run in PyQt environment but shows usage
    import sys
    from PyQt5.QtWidgets import QApplication


    class MockTradingApp:
        def __init__(self):
            self.state = type('State', (), {'current_position': 'NIFTY'})()
            self.executor = type('Executor', (), {'exit_position': lambda s, r: 100})()
            self.ws = type('WS', (), {'unsubscribe': lambda: None})()

        def run(self):
            import time
            for i in range(10):
                time.sleep(1)
                print(f"Trading... {i}")
                # Simulate token expiration for testing
                if i == 5:
                    raise TokenExpiredError("Test token expiration")


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