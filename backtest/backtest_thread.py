"""
backtest/backtest_thread.py
============================
QThread wrapper for BacktestEngine so the GUI stays responsive.

Uses state_manager to ensure consistent state across threads and proper
state restoration after backtest completion.

Signals
-------
progress(float, str)   — 0–100 percent + status message
finished(object)       — BacktestResult on completion
error(str)             — error message string
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from models.trade_state_manager import state_manager

if TYPE_CHECKING:
    from backtest.backtest_engine import BacktestConfig, BacktestResult
    from broker.BaseBroker import BaseBroker

logger = logging.getLogger(__name__)


class BacktestThread(QThread):
    """
    QThread wrapper for running backtests in the background.

    This thread manages the BacktestEngine lifecycle and ensures that
    the trade state is properly saved before the backtest and restored
    after completion, regardless of success or failure.

    Signals:
        progress: Emitted with (percentage, message) during backtest
        finished: Emitted with BacktestResult when backtest completes
        error: Emitted with error message string when backtest fails
    """

    progress = pyqtSignal(float, str)  # pct, message
    finished = pyqtSignal(object)  # BacktestResult
    error = pyqtSignal(str)

    def __init__(self, brok: "BaseBroker", conf: "BacktestConfig", parent=None):
        """
        Initialize the backtest thread.

        Args:
            broker: BaseBroker instance for fetching historical data
            config: BacktestConfig with backtest parameters
            parent: Parent QObject (usually the BacktestWindow)
        """
        super().__init__(parent)
        self._broker = brok
        self._config = conf
        self._engine = None
        self._is_running = False
        # Save the current state before backtest
        # This ensures we can restore the live trading state after backtest
        try:
            self._saved_state = state_manager.save_state()
            logger.debug(f"[BacktestThread] Saved pre-backtest state with {len(self._saved_state)} fields")
        except Exception as e:
            logger.error(f"[BacktestThread] Failed to save pre-backtest state: {e}", exc_info=True)
            self._saved_state = None

    def run(self):
        """
        Run the backtest in a background thread.

        This method is called automatically when the thread starts.
        It creates the BacktestEngine, runs the backtest, and emits
        the appropriate signals based on the outcome.
        """
        self._is_running = True
        result = None

        try:
            from backtest.backtest_engine import BacktestEngine

            logger.info(f"[BacktestThread] Starting backtest: {self._config.derivative} "
                        f"{self._config.start_date.date()} → {self._config.end_date.date()}")

            # Create and configure the engine
            self._engine = BacktestEngine(self._broker, self._config)
            self._engine.progress_callback = self._on_engine_progress

            # Run the backtest
            result = self._engine.run()

            # Emit success signal
            self.finished.emit(result)
            logger.info(f"[BacktestThread] Backtest completed: {result.total_trades} trades, "
                        f"PnL: ₹{result.total_net_pnl:,.2f}")

        except Exception as e:
            logger.error(f"[BacktestThread] Backtest failed: {e}", exc_info=True)
            self.error.emit(str(e))

        finally:
            self._is_running = False
            self._cleanup()

    def _on_engine_progress(self, pct: float, msg: str):
        """
        Forward progress updates from the engine to the GUI.

        Args:
            pct: Progress percentage (0-100)
            msg: Status message
        """
        if self._is_running:
            self.progress.emit(pct, msg)

    def stop(self):
        """
        Request the backtest engine to stop gracefully.

        This method is thread-safe and can be called from the main thread.
        The engine will check for stop requests during its replay loop
        and exit cleanly.
        """
        if self._engine and self._is_running:
            logger.info("[BacktestThread] Stop requested")
            self._engine.stop()
        else:
            logger.debug("[BacktestThread] Stop called but engine not running")

    def _cleanup(self):
        """
        Clean up resources and restore original state.

        This is called automatically when the thread finishes, regardless
        of success or failure. It ensures that:
        1. The engine is properly cleaned up
        2. The original trade state is restored
        3. Resources are freed
        """
        try:
            # Restore the original state that was saved before backtest
            if self._saved_state is not None:
                logger.debug("[BacktestThread] Restoring pre-backtest state")
                state_manager.restore_state(self._saved_state)
                logger.debug("[BacktestThread] Restored pre-backtest state")

            # Clean up engine if it exists
            if self._engine and hasattr(self._engine, 'cleanup'):
                try:
                    self._engine.cleanup()
                except Exception as e:
                    logger.error(f"[BacktestThread] Engine cleanup error: {e}", exc_info=True)

            self._engine = None
            logger.debug("[BacktestThread] Cleanup completed")

        except Exception as e:
            logger.error(f"[BacktestThread] Cleanup error: {e}", exc_info=True)

    def is_running(self) -> bool:
        """Return True if the backtest is currently running."""
        return self._is_running

    def get_config(self) -> Optional["BacktestConfig"]:
        """Return the backtest configuration."""
        return self._config

    def wait_for_finished(self, timeout: int = 30000) -> bool:
        """
        Wait for the thread to finish with timeout.

        Args:
            timeout: Maximum time to wait in milliseconds (default: 30000)

        Returns:
            True if thread finished, False if timeout occurred
        """
        return self.wait(timeout)


class BacktestThreadManager:
    """
    Context manager for safe BacktestThread lifecycle management.

    Ensures proper cleanup even if an exception occurs.

    Usage:
        with BacktestThreadManager(thread) as manager:
            thread.start()
            # ... do other things ...
            thread.wait()
        # Thread is automatically cleaned up
    """

    def __init__(self, thread: BacktestThread):
        """
        Initialize the manager with a BacktestThread.

        Args:
            thread: BacktestThread instance to manage
        """
        self.thread = thread
        self._started = False

    def __enter__(self):
        """Enter the context - return self for method chaining."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the context - ensure thread is properly stopped and cleaned up.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        try:
            if self.thread and self.thread.isRunning():
                logger.debug("[BacktestThreadManager] Cleaning up running thread")
                self.thread.stop()

                # Wait for thread to finish (max 5 seconds)
                if not self.thread.wait(5000):
                    logger.warning("[BacktestThreadManager] Thread did not stop gracefully, terminating")
                    self.thread.terminate()
                    self.thread.wait(2000)

        except Exception as e:
            logger.error(f"[BacktestThreadManager] Cleanup error: {e}", exc_info=True)

        # Log any exception that occurred in the context
        if exc_type:
            logger.error(f"[BacktestThreadManager] Exception in context: {exc_type.__name__}: {exc_val}")

    def start(self):
        """Start the thread if not already running."""
        if not self._started and self.thread and not self.thread.isRunning():
            self.thread.start()
            self._started = True
            logger.debug("[BacktestThreadManager] Thread started")
        return self


# Example usage for testing
if __name__ == "__main__":
    """
    Test the BacktestThread with a mock broker and config.
    This is for development/debugging only - not used in production.
    """
    import sys
    from PyQt5.QtWidgets import QApplication
    from datetime import datetime, timedelta

    # Set up logging for test
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


    # Create a mock broker for testing
    class MockBroker:
        class MockBrokerSetting:
            broker_type = "mock"

        broker_setting = MockBrokerSetting()

        def get_history_for_timeframe(self, symbol, interval, days):
            import pandas as pd
            import numpy as np

            # Generate mock data
            end = datetime.now()
            start = end - timedelta(days=days)
            times = pd.date_range(start=start, end=end, freq=f"{interval}min")

            # Generate random OHLC data
            base = 17000
            df = pd.DataFrame({
                'time': times,
                'open': base + np.random.randn(len(times)) * 10,
                'high': base + np.random.randn(len(times)) * 15,
                'low': base + np.random.randn(len(times)) * 15,
                'close': base + np.random.randn(len(times)) * 10,
                'volume': np.random.randint(100, 1000, len(times))
            })
            return df


    # Create a mock config
    class MockConfig:
        derivative = "NIFTY"
        expiry_type = "weekly"
        lot_size = 50
        num_lots = 1
        tp_pct = 0.30
        sl_pct = 0.25
        slippage_pct = 0.0025
        brokerage_per_lot = 40.0
        capital = 100000.0
        interval_minutes = 5
        sideway_zone_skip = True
        use_vix = True
        strategy_slug = "test_strategy"
        signal_engine_cfg = {}
        debug_candles = True

        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now() - timedelta(days=1)
        analysis_timeframes = ["5m", "15m", "30m"]


    # Create Qt application
    app = QApplication(sys.argv)

    # Create thread
    broker = MockBroker()
    config = MockConfig()
    thread = BacktestThread(broker, config)


    # Connect signals
    def on_progress(pct, msg):
        print(f"Progress: {pct:.1f}% - {msg}")


    def on_finished(result):
        print(f"Backtest finished: {result.total_trades} trades")
        print(f"Net P&L: ₹{result.total_net_pnl:,.2f}")
        print(f"Win Rate: {result.win_rate:.1f}%")
        QApplication.quit()


    def on_error(msg):
        print(f"Backtest error: {msg}")
        QApplication.quit()


    thread.progress.connect(on_progress)
    thread.finished.connect(on_finished)
    thread.error.connect(on_error)

    # Start thread with context manager
    with BacktestThreadManager(thread) as manager:
        manager.start()
        sys.exit(app.exec_())
