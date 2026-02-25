"""
multi_tf_filter.py
==================
Multi-Timeframe Filter for the Algo Trading Dashboard.

FEATURE 6: Uses EMA crossovers across multiple timeframes to confirm trend.
"""

import logging
import threading
import time
from typing import Dict, Tuple

import pandas_ta as ta

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class MultiTimeframeFilter:
    """
    FEATURE 6: Multi-Timeframe Filter for trade entry confirmation.

    Uses EMA 9/21 crossovers across 1min, 5min, and 15min timeframes.
    Requires at least 2 of 3 timeframes to agree with trade direction.
    """

    TIMEFRAMES = ['1', '5', '15']  # Minute intervals
    EMA_FAST = 9
    EMA_SLOW = 21

    def __init__(self, broker_api, cache_ttl_seconds=60):
        """
        Initialize MultiTimeframeFilter.

        Args:
            broker_api: Broker instance with get_history method
            cache_ttl_seconds: How long to cache results (default: 60)
        """
        # Rule 2: Safe defaults
        self._broker = broker_api
        self._cache: Dict[str, Tuple[str, float]] = {}
        self._lock = threading.RLock()
        self._ttl = cache_ttl_seconds

        logger.info(f"MultiTimeframeFilter initialized (TTL: {cache_ttl_seconds}s)")

    def get_direction(self, symbol: str, tf: str) -> str:
        """
        Get trend direction for a symbol on a specific timeframe.

        Args:
            symbol: Symbol to analyze
            tf: Timeframe ('1', '5', '15')

        Returns:
            'BULLISH', 'BEARISH', or 'NEUTRAL'
        """
        try:
            # Rule 6: Input validation
            if not symbol:
                logger.warning("get_direction called with empty symbol")
                return 'NEUTRAL'

            if tf not in self.TIMEFRAMES:
                logger.warning(f"Invalid timeframe: {tf}, expected one of {self.TIMEFRAMES}")
                return 'NEUTRAL'

            cache_key = f'{symbol}_{tf}'

            # Check cache
            with self._lock:
                cached = self._cache.get(cache_key)
                if cached and (time.time() - cached[1]) < self._ttl:
                    return cached[0]

            # Fetch from broker (not in lock - may take time)
            df = self._broker.get_history_for_timeframe(
                symbol=symbol,
                interval=tf,
                days=30  # Get enough data for EMAs
            )

            if df is None or df.empty:
                logger.warning(f"No data for {symbol} on {tf}m")
                return 'NEUTRAL'

            if len(df) < self.EMA_SLOW:
                logger.debug(f"Not enough data for {symbol} on {tf}m: {len(df)} < {self.EMA_SLOW}")
                return 'NEUTRAL'

            # Calculate EMAs
            try:
                ema_fast = ta.ema(df['close'], length=self.EMA_FAST)
                ema_slow = ta.ema(df['close'], length=self.EMA_SLOW)
            except Exception as e:
                logger.error(f"Failed to calculate EMAs: {e}", exc_info=True)
                return 'NEUTRAL'

            if ema_fast is None or ema_slow is None:
                logger.warning(f"EMA calculation failed for {symbol} on {tf}m")
                return 'NEUTRAL'

            # Get latest values
            ef = ema_fast.iloc[-1]
            es = ema_slow.iloc[-1]
            lc = df['close'].iloc[-1]

            # Determine direction
            if ef > es and lc > ef:
                direction = 'BULLISH'
            elif ef < es and lc < ef:
                direction = 'BEARISH'
            else:
                direction = 'NEUTRAL'

            # Update cache
            with self._lock:
                self._cache[cache_key] = (direction, time.time())

            logger.debug(f"MTF {symbol} {tf}m: {direction} (EMA9={ef:.2f}, EMA21={es:.2f}, LTP={lc:.2f})")
            return direction

        except Exception as e:
            logger.error(f"[MTF.get_direction] Failed for {symbol} {tf}: {e}", exc_info=True)
            return 'NEUTRAL'

    def should_allow_entry(self, symbol: str, trade_direction: str) -> Tuple[bool, str]:
        """
        Check if entry should be allowed based on multi-timeframe agreement.

        Args:
            symbol: Symbol to analyze
            trade_direction: 'CALL' or 'PUT'

        Returns:
            Tuple[bool, str]: (allowed, summary_string)
        """
        try:
            # Rule 6: Input validation
            if not symbol:
                logger.warning("should_allow_entry called with empty symbol")
                return True, 'MTF: No symbol (bypassed)'

            target = 'BULLISH' if trade_direction == 'CALL' else 'BEARISH'

            # Get directions for all timeframes
            results = {}
            for tf in self.TIMEFRAMES:
                results[tf] = self.get_direction(symbol, tf)

            # Count matches
            matches = sum(1 for d in results.values() if d == target)
            total = len(results)

            # Build summary string
            ticks = {tf: '✓' if d == target else '✗' for tf, d in results.items()}
            summary = 'MTF: ' + ' '.join(f'{tf}m{ticks[tf]}' for tf in self.TIMEFRAMES)

            # Decision: require at least 2 of 3 to agree
            allowed = matches >= 2
            summary += f' -> {"ALLOWED" if allowed else "BLOCKED"} ({matches}/{total})'

            logger.info(f'[MTF] {summary}')
            return allowed, summary

        except Exception as e:
            logger.error(f"[MTF.should_allow_entry] Failed: {e}", exc_info=True)
            return True, 'MTF: ERROR (bypassed)'

    def get_detailed_results(self, symbol: str) -> Dict[str, Dict[str, any]]:
        """
        Get detailed results for all timeframes (for GUI display).

        Args:
            symbol: Symbol to analyze

        Returns:
            Dict mapping timeframe to direction and details
        """
        try:
            results = {}
            for tf in self.TIMEFRAMES:
                direction = self.get_direction(symbol, tf)

                # Get cached data for details
                cache_key = f'{symbol}_{tf}'
                with self._lock:
                    cached = self._cache.get(cache_key)

                results[tf] = {
                    'direction': direction,
                    'cached': cached is not None,
                    'timestamp': cached[1] if cached else None
                }

            return results

        except Exception as e:
            logger.error(f"[MTF.get_detailed_results] Failed: {e}", exc_info=True)
            return {}

    def invalidate_cache(self):
        """Clear the cache."""
        try:
            with self._lock:
                self._cache.clear()
            logger.info("MTF cache invalidated")
        except Exception as e:
            logger.error(f"[MTF.invalidate_cache] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources."""
        try:
            logger.info("[MultiTimeframeFilter] Starting cleanup")
            self.invalidate_cache()
            logger.info("[MultiTimeframeFilter] Cleanup completed")
        except Exception as e:
            logger.error(f"[MultiTimeframeFilter.cleanup] Error: {e}", exc_info=True)