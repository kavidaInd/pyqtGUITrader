"""
data/history_manager.py
=======================
Periodic history fetcher for CandleStores.

Reconstructed from compiled bytecode (history_manager.cpython-313.pyc).
The source file was absent from the repository while the .pyc was present,
causing ModuleNotFoundError on any import.

Responsibilities
----------------
- Periodically fetch OHLCV history for derivative, call, and put symbols.
- Push fetched bars into the appropriate CandleStore via resample_df.
- Emit Qt signals for chart updates and status reporting.
- Support one-shot fetch on startup via fetch_initial_and_update().

Thread safety
-------------
All periodic fetching runs on a QTimer (GUI thread) or a background thread
started by start().  CandleStore.push_tick() is internally thread-safe.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
# TZ-FIX: elapsed-time / cache comparisons must use ist_now() to match IST DB timestamps.
from Utils.time_utils import ist_now
from typing import Any, Dict, Optional

import pandas as pd
from PyQt5.QtCore import QObject, pyqtSignal, QTimer

from data.candle_store import CandleStore, resample_df
from broker.BaseBroker import TokenExpiredError

logger = logging.getLogger(__name__)


class HistoryManager(QObject):
    """
    Manages periodic history fetching for all subscribed symbols.

    Signals
    -------
    history_updated(str, object)
        Emitted when new data is available; carries (symbol, DataFrame).
    status_updated(str)
        Human-readable status messages for the status bar.
    error_occurred(str)
        Emitted on non-fatal errors.
    """

    history_updated = pyqtSignal(str, object)  # symbol, DataFrame
    status_updated  = pyqtSignal(str)
    error_occurred  = pyqtSignal(str)

    def __init__(self, broker: Any, config: Any):
        super().__init__()
        self.broker        = broker
        self.config        = config
        self._stop_flag    = False
        self._fetch_thread: Optional[threading.Thread] = None
        self._timer: Optional[QTimer] = None
        self._candle_stores: Dict[str, CandleStore] = {}
        self._last_fetch:    Dict[str, datetime]    = {}

        # Symbol tracking
        self.symbols: list         = []
        self.derivative: str       = ""
        self.call_option: str      = ""
        self.put_option:  str      = ""
        self.fetch_interval: int   = 60  # seconds

        logger.info("HistoryManager initialized")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, interval_seconds: int = 60) -> None:
        """Start automatic history fetching on a QTimer."""
        self.fetch_interval = interval_seconds
        self._stop_flag = False

        self._timer = QTimer()
        self._timer.timeout.connect(self._fetch_all_history)
        self._timer.start(interval_seconds * 1000)

        logger.info(f"HistoryManager started with {interval_seconds}s interval")
        self.status_updated.emit(f"History fetching started (every {interval_seconds}s)")

    def stop(self) -> None:
        """Stop all fetching activity."""
        self._stop_flag = True

        if self._timer and self._timer.isActive():
            self._timer.stop()
            self._timer = None

        if self._fetch_thread and self._fetch_thread.is_alive():
            self._fetch_thread.join(timeout=5.0)

        logger.info("HistoryManager stopped")
        self.status_updated.emit("History fetching stopped")

    def cleanup(self) -> None:
        """Alias for stop() to match the standard cleanup contract."""
        self.stop()

    # ------------------------------------------------------------------
    # Symbol management
    # ------------------------------------------------------------------

    def update_symbols(
        self,
        derivative: str,
        call_option: str = "",
        put_option:  str = "",
    ) -> None:
        """Update the set of symbols to track."""
        self.derivative  = derivative  or ""
        self.call_option = call_option or ""
        self.put_option  = put_option  or ""

        current_symbols = [s for s in (derivative, call_option, put_option) if s]
        self.symbols = current_symbols
        logger.info(f"HistoryManager symbols updated: {current_symbols}")

    # ------------------------------------------------------------------
    # Fetch helpers
    # ------------------------------------------------------------------

    def _fetch_all_history(self) -> None:
        """Fetch history for all tracked symbols (called by QTimer)."""
        if self._stop_flag:
            return

        for symbol in self.symbols:
            if self._stop_flag:
                break
            try:
                is_derivative = (symbol == self.derivative)
                self._fetch_symbol_history(symbol, is_derivative)
            except TokenExpiredError:
                raise
            except Exception as e:
                logger.error(f"Error fetching history for {symbol}: {e}", exc_info=True)
                self.error_occurred.emit(f"Error fetching history for {symbol}: {e}")

    def _fetch_symbol_history(
        self,
        symbol: str,
        is_derivative: bool,
        last_fetch: Optional[datetime] = None,
        target_interval: Optional[str] = None,
        target_minutes: Optional[int]  = None,
        store: Optional[CandleStore]   = None,
        broker_type: Optional[str]     = None,
        success: bool = False,
        df: Optional[pd.DataFrame] = None,
        e: Optional[Exception] = None,
    ) -> bool:
        """Fetch history for a single symbol."""
        try:
            last_fetch = self._last_fetch.get(symbol, ist_now() - timedelta(seconds=10))

            # Throttle: skip if fetched recently
            elapsed = (ist_now() - last_fetch).total_seconds()
            if elapsed < 10:
                return False

            try:
                target_interval = '1'  # Always fetch 1m candles from broker; resampling is handled by candle manager
                target_minutes  = 1
            except (TypeError, ValueError):
                target_minutes  = 1

            if symbol not in self._candle_stores:
                self._candle_stores[symbol] = CandleStore(symbol)

            store = self._candle_stores[symbol]

            # Determine broker type for fetch call
            broker_type = None
            if self.broker and hasattr(self.broker, 'broker_setting'):
                broker_type = getattr(self.broker.broker_setting, 'broker_type', None)

            try:
                df = self.broker.fetch(
                    symbol=symbol,
                    interval=target_interval,
                    limit=1000,
                )
            except TokenExpiredError:
                raise
            except Exception:
                df = None

            if df is None or df.empty:
                return False

            if store.is_empty():
                store.get_1min()  # initialise store

            resample_df(store, df)

            self._last_fetch[symbol] = ist_now()
            self.history_updated.emit(symbol, df)
            logger.debug(f"Fetched {len(df)} bars for {symbol}")
            return True

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error fetching history for {symbol}: {e}", exc_info=True)
            return False

    def fetch_initial_and_update(self, callback=None) -> None:
        """
        Fetch initial data and trigger an immediate update when complete.
        Ensures the chart loads immediately on startup.
        """
        try:
            self._fetch_all_history()

            store = self._candle_stores.get(self.derivative)
            if store is None:
                return

            try:
                target_interval = '1'  # Always fetch 1m candles from broker; resampling is handled by candle manager
                target_minutes  = 1
            except (TypeError, ValueError):
                target_minutes = 1

            df = store.get_1min()
            if df is not None and not df.empty:
                resampled = resample_df(store, df)
                if resampled is not None:
                    self.history_updated.emit(self.derivative, resampled)

            if callback is not None:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in fetch_initial_and_update callback: {e}", exc_info=True)

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error in fetch_initial_and_update: {e}", exc_info=True)
            self.error_occurred.emit(f"Error in fetch_initial_and_update: {e}")

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_latest_data(
        self,
        symbol: str,
        interval_minutes: int = 1,
    ) -> Optional[pd.DataFrame]:
        """Return the latest resampled DataFrame for *symbol*, or None."""
        try:
            store = self._candle_stores.get(symbol)
            if store is None or store.is_empty():
                return None
            return store.resample(interval_minutes)
        except Exception as e:
            logger.error(f"get_latest_data error for {symbol}: {e}", exc_info=True)
            return None