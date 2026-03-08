# candle_store_manager.py (fixed)
"""
data/candle_store_manager.py
============================
Centralized manager for CandleStore instances across the application.

This module provides a thread-safe singleton manager for all CandleStore
objects, ensuring a single source of truth for OHLCV data across all symbols.

Uses the existing CandleStore implementation from candle_store.py.
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any

import pandas as pd

from Utils.safe_getattr import safe_hasattr
from broker.BaseBroker import TokenExpiredError
from data.candle_store import CandleStore, resample_df, convert_timezone

logger = logging.getLogger(__name__)


class CandleStoreManager:
    """
    Thread-safe singleton manager for all CandleStore instances.

    This manager ensures that:
    1. Each symbol has exactly one CandleStore instance
    2. Stores are created lazily when first requested
    3. Access is thread-safe across all threads
    4. Memory is managed by cleaning up unused stores
    5. Broker instance is shared across all stores

    Uses the existing CandleStore implementation from candle_store.py.
    """

    _instance = None
    _singleton_lock = threading.RLock()
    _initialized = False

    def __new__(cls):
        """Thread-safe singleton instantiation."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initialize the manager with empty stores dict.
        This runs only once due to the _initialized flag.
        """
        if self._initialized:
            return

        with self._singleton_lock:
            if self._initialized:
                return

            try:
                # Main lock for thread safety
                object.__setattr__(self, "_lock", threading.RLock())

                # Dictionary of symbol -> CandleStore
                self._stores: Dict[str, CandleStore] = {}

                # Broker instance (shared across all stores)
                self._broker = None

                # Whether we're in backtest mode (no broker needed)
                self._backtest_mode = False

                # Last access time for each store (for cleanup)
                self._last_access: Dict[str, datetime] = {}

                # Default max bars for new stores
                self._default_max_bars = 2000

                self._initialized = True
                logger.info("CandleStoreManager initialized")

            except Exception as e:
                logger.critical(f"[CandleStoreManager.__init__] Failed: {e}", exc_info=True)
                object.__setattr__(self, "_lock", threading.RLock())
                self._initialized = True

    # ------------------------------------------------------------------
    # Initialization Methods
    # ------------------------------------------------------------------

    def initialize(self, broker, backtest_mode: bool = False) -> None:
        """
        Initialize the manager with a broker instance.

        Args:
            broker: Broker instance for fetching historical data
            backtest_mode: If True, stores can be created without broker

        Note on re-initialization:
            This method may be called twice: once at GUI startup with broker=None
            (before TradingApp.initialize() runs) and again from
            TradingGUI._on_trading_app_initialized() once the broker is live.
            The second call also pushes the broker into all already-created
            CandleStore instances, so they can fetch data without being recreated.
        """
        with self._lock:
            self._broker = broker
            self._backtest_mode = backtest_mode
            logger.info(f"CandleStoreManager initialized with broker: {broker.__class__.__name__ if broker else 'None'}")

            # Push broker into pre-existing stores so they can fetch immediately.
            # This handles the race where get_store() was called before initialize(broker)
            # had a live broker (e.g. during chart setup at GUI startup).
            if broker is not None:
                updated = 0
                for store in self._stores.values():
                    if safe_hasattr(store, 'broker') and store.broker is None:
                        store.broker = broker
                        updated += 1
                if updated:
                    logger.info(f"CandleStoreManager: broker injected into {updated} pre-existing store(s)")

    def initialize_for_backtest(self) -> None:
        """Initialize the manager for backtest mode (no broker needed)."""
        with self._lock:
            self._broker = None
            self._backtest_mode = True
            logger.info("CandleStoreManager initialized for backtest mode")

    # ------------------------------------------------------------------
    # Store Management
    # ------------------------------------------------------------------

    def get_store(self, symbol: str, max_bars: Optional[int] = None, broker_type: Optional[str] = None) -> CandleStore:
        """
        Get or create a CandleStore for a symbol.

        Args:
            symbol: Trading symbol (e.g., "NIFTY", "BANKNIFTY")
            max_bars: Maximum number of 1-min bars to keep (uses default if None)
            broker_type: Broker type for symbol translation (e.g., "fyers", "zerodha")

        Returns:
            CandleStore instance for the symbol
        """
        try:
            with self._lock:
                # Update last access time
                self._last_access[symbol] = datetime.now()

                # Return existing store if available
                if symbol in self._stores:
                    store = self._stores[symbol]
                    logger.debug(f"Returning existing CandleStore for {symbol}")
                    return store

                # Create new store
                if max_bars is None:
                    max_bars = self._default_max_bars

                logger.info(f"Creating new CandleStore for {symbol} with max_bars={max_bars}")

                # Pass max_bars to constructor consistently
                store = CandleStore(
                    symbol=symbol,
                    broker=self._broker if not self._backtest_mode else None,
                    max_bars=max_bars
                )

                self._stores[symbol] = store

                return store
        except TokenExpiredError as e:
            logger.error(f"Token expired during get_store: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.critical(f"Unhandled exception during get_store: {e!r}", exc_info=True)
            raise

    def create_from_dataframe(self, symbol: str, df: pd.DataFrame, max_bars: Optional[int] = None) -> CandleStore:
        """
        Create a CandleStore from an existing DataFrame (for backtesting).

        Uses the CandleStore.from_dataframe class method.

        Args:
            symbol: Trading symbol
            df: DataFrame with 1-min OHLCV data
            max_bars: Maximum number of bars to keep

        Returns:
            CandleStore instance populated with the DataFrame
        """
        try:
            with self._lock:
                # Ensure we're in backtest mode
                if not self._backtest_mode and self._broker is not None:
                    logger.warning("Creating store from DataFrame in non-backtest mode - this may indicate an issue")

                # Pass max_bars to from_dataframe constructor
                if max_bars is None:
                    max_bars = self._default_max_bars

                # Use the existing from_dataframe class method with max_bars
                store = CandleStore.from_dataframe(df, symbol=symbol, max_bars=max_bars)

                # Store it
                self._stores[symbol] = store
                self._last_access[symbol] = datetime.now()

                logger.info(f"Created CandleStore for {symbol} from DataFrame with {len(df)} bars")
                return store
        except TokenExpiredError as e:
            logger.error(f"Token expired during create_from_dataframe: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.critical(f"Unhandled exception during create_from_dataframe: {e!r}", exc_info=True)
            raise

    def has_store(self, symbol: str) -> bool:
        """Check if a store exists for the given symbol."""
        with self._lock:
            return symbol in self._stores

    def remove_store(self, symbol: str) -> bool:
        """
        Remove a store for a symbol.

        Returns:
            bool: True if store was removed, False if it didn't exist
        """
        try:
            with self._lock:
                if symbol in self._stores:
                    del self._stores[symbol]
                    if symbol in self._last_access:
                        del self._last_access[symbol]
                    logger.info(f"Removed CandleStore for {symbol}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error removing store for {symbol}: {e}", exc_info=True)
            return False

    def get_all_symbols(self) -> List[str]:
        """Get list of all symbols with active stores."""
        with self._lock:
            return list(self._stores.keys())

    def get_store_count(self) -> int:
        """Get number of active stores."""
        with self._lock:
            return len(self._stores)

    # ------------------------------------------------------------------
    # Batch Operations
    # ------------------------------------------------------------------

    def fetch_all(self, days: int = 2, symbols: Optional[List[str]] = None, broker_type: Optional[str] = None) -> Dict[str, bool]:
        """
        Fetch historical data for multiple symbols.

        Args:
            days: Number of calendar days to fetch
            symbols: List of symbols to fetch (None = fetch all active)
            broker_type: Broker type for symbol translation

        Returns:
            Dict mapping symbol -> success boolean

        Raises:
            TokenExpiredError: If token is expired during fetch
        """
        results = {}
        symbols_to_fetch = symbols or self.get_all_symbols()
        token_expired_error = None

        for symbol in symbols_to_fetch:
            try:
                store = self.get_store(symbol)
                # Use the existing fetch method with broker_type
                success = store.fetch(days=days, broker_type=broker_type)
                results[symbol] = success
                if not success:
                    logger.warning(f"Failed to fetch data for {symbol}")
            except TokenExpiredError as e:
                logger.error(f"Token expired while fetching data for {symbol}: {e}", exc_info=True)
                token_expired_error = e
                results[symbol] = False
                # Break early on token expiry - no point continuing
                break
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}", exc_info=True)
                results[symbol] = False

        # If we encountered a token expiry, raise it after logging all results
        if token_expired_error:
            raise token_expired_error

        return results

    def push_tick(self, symbol: str, ltp: float, volume: float = 0.0, timestamp: Optional[datetime] = None) -> bool:
        """
        Push a tick to the store for a symbol.

        Uses the existing push_tick method.

        Args:
            symbol: Trading symbol
            ltp: Last traded price
            volume: Traded quantity for this tick
            timestamp: Tick timestamp (defaults to now)

        Returns:
            bool: True if bar was completed, False otherwise
        """
        try:
            store = self.get_store(symbol)
            return store.push_tick(ltp, volume, timestamp)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error pushing tick to {symbol}: {e}", exc_info=True)
            return False

    def resample(self, symbol: str, minutes: int) -> Optional[pd.DataFrame]:
        """
        Get resampled data for a symbol.

        Uses the existing resample method.

        Args:
            symbol: Trading symbol
            minutes: Target candle width in minutes

        Returns:
            Resampled DataFrame or None if error

        Raises:
            TokenExpiredError: If token is expired during data access
        """
        try:
            store = self.get_store(symbol)
            return store.resample(minutes)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error resampling data for {symbol}: {e}", exc_info=True)
            return None

    def get_1min(self, symbol: str) -> Optional[pd.DataFrame]:
        """Get raw 1-min data for a symbol."""
        try:
            store = self.get_store(symbol)
            return store.resample(1)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error getting 1min data for {symbol}: {e}", exc_info=True)
            return None

    def last_bar_time(self, symbol: str) -> Optional[datetime]:
        """Get timestamp of last completed bar for a symbol."""
        try:
            store = self.get_store(symbol)
            return store.last_bar_time()
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error getting last bar time for {symbol}: {e}", exc_info=True)
            return None

    def is_empty(self, symbol: str) -> bool:
        """Check if store for symbol is empty."""
        try:
            store = self.get_store(symbol)
            return store.is_empty()
        except TokenExpiredError:
            raise
        except Exception:
            return True

    def bar_count(self, symbol: str) -> int:
        """Get number of bars in store for symbol."""
        try:
            store = self.get_store(symbol)
            return store.bar_count()
        except TokenExpiredError:
            raise
        except Exception:
            return 0

    def get_data_in_timezone(self, symbol: str, minutes: int, tz: str = 'Asia/Kolkata') -> Optional[pd.DataFrame]:
        """
        Get resampled data converted to a specific timezone.

        Uses the existing get_data_in_timezone method.

        Args:
            symbol: Trading symbol
            minutes: Target candle width
            tz: Target timezone

        Returns DataFrame with time column converted to target timezone.

        Raises:
            TokenExpiredError: If token is expired during data access
        """
        try:
            store = self.get_store(symbol)
            return store.get_data_in_timezone(minutes, tz)
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error getting data in timezone for {symbol}: {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Memory Management
    # ------------------------------------------------------------------

    def cleanup_unused(self, max_idle_minutes: int = 30) -> int:
        """
        Remove stores that haven't been accessed for a while.

        Args:
            max_idle_minutes: Maximum idle time before removal

        Returns:
            int: Number of stores removed
        """
        try:
            with self._lock:
                cutoff = datetime.now() - timedelta(minutes=max_idle_minutes)
                to_remove = []

                for symbol, last_access in self._last_access.items():
                    if last_access < cutoff:
                        to_remove.append(symbol)

                for symbol in to_remove:
                    self.remove_store(symbol)

                if to_remove:
                    logger.info(f"Cleaned up {len(to_remove)} unused stores")

                return len(to_remove)
        except Exception as e:
            logger.error(f"Error during cleanup_unused: {e}", exc_info=True)
            return 0

    def set_default_max_bars(self, max_bars: int) -> None:
        """Set default max_bars for new stores."""
        with self._lock:
            self._default_max_bars = max_bars

    def clear(self) -> None:
        """Remove all stores (use with caution)."""
        with self._lock:
            store_count = len(self._stores)
            self._stores.clear()
            self._last_access.clear()
            logger.info(f"Cleared all {store_count} stores")

    # ------------------------------------------------------------------
    # Utility Methods
    # ------------------------------------------------------------------

    def get_store_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get information about a store.

        Returns:
            Dict with store metadata or empty dict if not found
        """
        try:
            store = self.get_store(symbol)
            return {
                'symbol': symbol,
                'bar_count': store.bar_count(),
                'last_bar_time': store.last_bar_time(),
                'is_empty': store.is_empty(),
                'max_bars': store.max_bars,
                'cached_timeframes': list(store._resample_cache.keys()) if safe_hasattr(store, '_resample_cache') else []
            }
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Error getting store info for {symbol}: {e}", exc_info=True)
            return {}

    def get_all_store_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all stores."""
        with self._lock:
            return {symbol: self.get_store_info(symbol) for symbol in self._stores}

    def __repr__(self) -> str:
        """String representation."""
        with self._lock:
            return (f"<CandleStoreManager stores={len(self._stores)} "
                    f"backtest_mode={self._backtest_mode} "
                    f"broker={'Yes' if self._broker else 'No'}>")


# ------------------------------------------------------------------
# Global instance for easy import
# ------------------------------------------------------------------

candle_store_manager = CandleStoreManager()