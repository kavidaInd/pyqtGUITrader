"""
multi_tf_filter.py
==================
Multi-Timeframe Filter for the Algo Trading Dashboard.

FEATURE 6: Uses EMA crossovers across multiple timeframes to confirm trend.
Now derives higher timeframe data from 1-minute data for consistency and efficiency.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from Utils.Utils import Utils, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Set, Callable
from functools import lru_cache
from contextlib import contextmanager
from collections import defaultdict
import numpy as np

import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


class TrendDirection(Enum):
    """Enum for trend directions to avoid string literals."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

    @classmethod
    def from_trade_direction(cls, trade_direction: str) -> "TrendDirection":
        """Convert trade direction to trend direction."""
        if not trade_direction:
            return cls.NEUTRAL
        direction = trade_direction.upper()
        if direction == "CALL":
            return cls.BULLISH
        elif direction == "PUT":
            return cls.BEARISH
        return cls.NEUTRAL

    @classmethod
    def from_ema_crossover(cls, fast_ema: float, slow_ema: float, close: float) -> "TrendDirection":
        """Determine trend direction from EMA crossover."""
        if pd.isna(fast_ema) or pd.isna(slow_ema) or pd.isna(close):
            return cls.NEUTRAL
        if slow_ema < fast_ema < close:
            return cls.BULLISH
        elif slow_ema > fast_ema > close:
            return cls.BEARISH
        return cls.NEUTRAL


@dataclass
class EMAData:
    """Container for EMA calculation results."""
    fast_ema: float
    slow_ema: float
    close: float
    timestamp: Optional[datetime] = None
    timeframe: Optional[str] = None
    data_points: int = 0

    def __post_init__(self):
        """Validate and round values after initialization."""
        self.fast_ema = round(float(self.fast_ema), 4) if not pd.isna(self.fast_ema) else 0.0
        self.slow_ema = round(float(self.slow_ema), 4) if not pd.isna(self.slow_ema) else 0.0
        self.close = round(float(self.close), 4) if not pd.isna(self.close) else 0.0

    @property
    def direction(self) -> TrendDirection:
        """Get trend direction from EMA data."""
        return TrendDirection.from_ema_crossover(self.fast_ema, self.slow_ema, self.close)

    @property
    def is_valid(self) -> bool:
        """Check if EMA data is valid."""
        return (not pd.isna(self.fast_ema) and not pd.isna(self.slow_ema) and
                not pd.isna(self.close) and self.fast_ema > 0 and self.slow_ema > 0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "fast_ema": self.fast_ema,
            "slow_ema": self.slow_ema,
            "close": self.close,
            "direction": self.direction.value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "timeframe": self.timeframe,
            "data_points": self.data_points
        }


@dataclass
class TimeframeResult:
    """Container for timeframe analysis results."""
    direction: TrendDirection
    ema_data: Optional[EMAData] = None
    cached: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None
    data_points: int = 0
    derived_from: Optional[str] = None  # Which timeframe this was derived from

    @property
    def is_valid(self) -> bool:
        """Check if result is valid (no error and has data)."""
        return self.error is None and self.data_points > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "direction": self.direction.value,
            "ema_data": self.ema_data.to_dict() if self.ema_data else None,
            "cached": self.cached,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
            "data_points": self.data_points,
            "derived_from": self.derived_from
        }


@dataclass
class MTFDecision:
    """Container for multi-timeframe filter decision."""
    allowed: bool
    summary: str
    matches: int
    total: int
    results: Dict[str, TimeframeResult]
    agreement_percentage: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "allowed": self.allowed,
            "summary": self.summary,
            "matches": self.matches,
            "total": self.total,
            "agreement_percentage": self.agreement_percentage,
            "timestamp": self.timestamp.isoformat(),
            "results": {tf: r.to_dict() for tf, r in self.results.items()}
        }


class MultiTimeframeFilter:
    """
    FEATURE 6: Multi-Timeframe Filter for trade entry confirmation.

    Derives all timeframes from 1-minute data for consistency and efficiency.
    Uses EMA 9/21 crossovers across 1min, 5min, and 15min timeframes.
    Requires at least 2 of 3 timeframes to agree with trade direction.

    Key Improvements:
    - Single source of truth: All timeframes derived from 1-minute data
    - Efficient caching: Base data cached separately from analysis results
    - Consistent resampling: Proper OHLC resampling for higher timeframes
    - Comprehensive error handling: Graceful degradation on data issues
    - Performance optimized: LRU cache, batch operations, minimal lock contention
    """

    # Configuration constants
    BASE_TIMEFRAME: str = '1'  # Base timeframe (1 minute)
    DERIVED_TIMEFRAMES: List[str] = ['5', '15']  # Timeframes to derive
    ALL_TIMEFRAMES: List[str] = ['1', '5', '15']  # All available timeframes

    # EMA parameters
    EMA_FAST: int = 9
    EMA_SLOW: int = 21
    MIN_DATA_POINTS: int = 30  # Minimum data points needed for reliable EMAs

    # Cache settings
    DEFAULT_TTL_SECONDS: int = 60
    MAX_CACHE_SIZE: int = 1000
    MAX_BASE_CACHE_SIZE: int = 100

    # Decision threshold
    REQUIRED_AGREEMENT: int = 2  # Number of timeframes that must agree

    # Data fetch settings
    BASE_DATA_DAYS: int = 2  # Days of 1-minute data needed for all timeframes
    BASE_DATA_LOOKBACK: Dict[str, int] = {
        '1': 2,    # 2 days for 1min
        '5': 3,    # 3 days for 5min
        '15': 5    # 5 days for 15min
    }

    def __init__(self, broker_api, cache_ttl_seconds: int = DEFAULT_TTL_SECONDS):
        """
        Initialize MultiTimeframeFilter.

        Args:
            broker_api: Broker instance with get_history_for_timeframe method
            cache_ttl_seconds: How long to cache results (default: 60)

        Raises:
            ValueError: If cache_ttl_seconds is negative
        """
        if cache_ttl_seconds < 0:
            raise ValueError(f"cache_ttl_seconds must be >= 0, got {cache_ttl_seconds}")

        # Core dependencies
        self._broker = broker_api

        # Cache management
        self._cache: Dict[str, Tuple[TimeframeResult, float]] = {}  # Analysis cache
        self._base_data_cache: Dict[str, Tuple[pd.DataFrame, float]] = {}  # Base 1min data cache
        self._lock = threading.RLock()
        self._stats_lock = threading.RLock()
        self._ttl = cache_ttl_seconds

        # Performance statistics
        self._stats = {
            "hits": 0,
            "misses": 0,
            "errors": 0,
            "total_requests": 0,
            "derivations": 0,
            "cache_cleanups": 0
        }

        logger.info(f"MultiTimeframeFilter initialized (TTL: {cache_ttl_seconds}s, "
                   f"agreement: {self.REQUIRED_AGREEMENT}/{len(self.ALL_TIMEFRAMES)})")

    @contextmanager
    def _cache_lock(self, timeout: float = 5.0):
        """Context manager for cache operations with timeout."""
        acquired = self._lock.acquire(timeout=timeout)
        if not acquired:
            logger.warning(f"Could not acquire cache lock within {timeout}s timeout")
            yield False
        else:
            try:
                yield True
            finally:
                self._lock.release()

    def _update_stats(self, hit: bool = False, error: bool = False, derived: bool = False):
        """Update performance statistics."""
        with self._stats_lock:
            self._stats["total_requests"] += 1
            if hit:
                self._stats["hits"] += 1
            else:
                self._stats["misses"] += 1
            if error:
                self._stats["errors"] += 1
            if derived:
                self._stats["derivations"] += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        with self._stats_lock:
            total = self._stats["total_requests"]
            hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
            derivation_rate = (self._stats["derivations"] / total * 100) if total > 0 else 0

            return {
                **self._stats,
                "hit_rate_percent": Utils.round_off(hit_rate),
                "derivation_rate_percent": Utils.round_off(derivation_rate),
                "cache_size": len(self._cache),
                "base_data_cache_size": len(self._base_data_cache)
            }

    def _fetch_base_data(self, symbol: str, force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        Fetch base (1-minute) data for a symbol.

        Args:
            symbol: Symbol to fetch data for
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            DataFrame with 1-minute data or None if failed
        """
        if not symbol or not symbol.strip():
            logger.warning("fetch_base_data called with empty symbol")
            return None

        symbol = symbol.strip().upper()
        cache_key = f"{symbol}_base"

        # Check cache unless force refresh
        if not force_refresh:
            with self._cache_lock() as locked:
                if locked and cache_key in self._base_data_cache:
                    cached_df, timestamp = self._base_data_cache[cache_key]
                    if (time.time() - timestamp) < self._ttl:
                        logger.debug(f"Using cached base data for {symbol}")
                        return cached_df.copy()  # Return copy to prevent modification

        # Fetch from broker with retry logic
        max_retries = 3
        retry_delay = 1
        last_error = None

        for attempt in range(max_retries):
            try:
                # Determine how many days of data to fetch based on symbol type
                # Options need more data for proper resampling
                days_to_fetch = self.BASE_DATA_DAYS
                if any(x in symbol for x in ['CE', 'PE', 'FUT']):
                    days_to_fetch = max(days_to_fetch, 5)  # Options need more data

                df = self._broker.get_history_for_timeframe(
                    symbol=symbol,
                    interval=self.BASE_TIMEFRAME,
                    days=days_to_fetch
                )

                if df is None or df.empty:
                    last_error = f"No data returned for {symbol}"
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    break

                # Validate required columns
                required_cols = ['open', 'high', 'low', 'close']
                if not all(col in df.columns for col in required_cols):
                    missing = [col for col in required_cols if col not in df.columns]
                    last_error = f"Missing required columns: {missing}"
                    logger.error(f"DataFrame missing columns for {symbol}: {missing}")
                    return None

                # Ensure datetime index
                if not isinstance(df.index, pd.DatetimeIndex):
                    if 'timestamp' in df.columns:
                        df.set_index('timestamp', inplace=True)
                    elif 'time' in df.columns:
                        df.set_index('time', inplace=True)
                    else:
                        # Try to convert index to datetime
                        try:
                            df.index = pd.to_datetime(df.index)
                        except:
                            last_error = "Could not convert index to datetime"
                            logger.error(last_error)
                            return None

                # Sort index and remove duplicates
                df = df[~df.index.duplicated(keep='first')]
                df.sort_index(inplace=True)

                # Ensure we have enough data
                if len(df) < self.EMA_SLOW * 2:
                    logger.warning(f"Limited base data for {symbol}: {len(df)} bars")
                    # Still return the data, but log warning

                # Cache the base data with size limit
                with self._cache_lock() as locked:
                    if locked:
                        # Implement LRU-like behavior
                        if len(self._base_data_cache) >= self.MAX_BASE_CACHE_SIZE:
                            # Remove oldest entry
                            oldest_key = min(self._base_data_cache.keys(),
                                           key=lambda k: self._base_data_cache[k][1])
                            del self._base_data_cache[oldest_key]
                            self._stats["cache_cleanups"] += 1

                        self._base_data_cache[cache_key] = (df.copy(), time.time())

                logger.debug(f"Fetched {len(df)} 1-minute bars for {symbol}")
                return df

            except Exception as e:
                last_error = str(e)
                logger.error(f"Attempt {attempt + 1}/{max_retries} failed for {symbol}: {e}")
                if attempt == max_retries - 1:
                    break
                time.sleep(retry_delay)
                retry_delay *= 2

        logger.error(f"Failed to fetch base data for {symbol} after {max_retries} attempts: {last_error}")
        return None

    def _resample_to_timeframe(self, df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
        """
        Resample 1-minute data to target timeframe with proper OHLC.

        Args:
            df: DataFrame with 1-minute data and datetime index
            target_tf: Target timeframe ('5' or '15')

        Returns:
            Resampled DataFrame with OHLC data
        """
        if df is None or df.empty:
            return pd.DataFrame()

        # Define resampling rules
        resample_map = {
            '5': '5min',
            '15': '15min',
            '30': '30min',
            '60': '1h'
        }

        if target_tf not in resample_map:
            logger.warning(f"Unknown target timeframe: {target_tf}")
            return df

        rule = resample_map[target_tf]

        try:
            # Ensure we have a datetime index
            if not isinstance(df.index, pd.DatetimeIndex):
                logger.error("DataFrame index is not DatetimeIndex, cannot resample")
                return pd.DataFrame()

            # Define aggregation functions for OHLCV
            agg_dict = {
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last'
            }

            # Add volume if present
            if 'volume' in df.columns:
                agg_dict['volume'] = 'sum'

            # Resample to target timeframe
            resampled = df.resample(rule).agg(agg_dict)

            # Drop rows with NaN values (incomplete periods)
            resampled = resampled.dropna()

            # Validate resampled data
            if len(resampled) < self.EMA_SLOW:
                logger.warning(f"Resampled {target_tf}m data has only {len(resampled)} bars")

            logger.debug(f"Resampled {len(df)} 1min bars to {len(resampled)} {target_tf}min bars")
            return resampled

        except Exception as e:
            logger.error(f"Error resampling to {target_tf}m: {e}", exc_info=True)
            return pd.DataFrame()

    def _calculate_emas(self, df: pd.DataFrame, tf: str) -> Optional[EMAData]:
        """
        Calculate EMAs from DataFrame.

        Args:
            df: DataFrame with OHLC data
            tf: Timeframe for logging

        Returns:
            EMAData object or None if calculation fails
        """
        try:
            if df is None or df.empty:
                logger.debug(f"No data for EMA calculation on {tf}m")
                return None

            if len(df) < self.EMA_SLOW:
                logger.debug(f"Insufficient data for EMA calculation on {tf}m: {len(df)} < {self.EMA_SLOW}")
                return None

            # Calculate EMAs using pandas_ta
            ema_fast = ta.ema(df['close'], length=self.EMA_FAST)
            ema_slow = ta.ema(df['close'], length=self.EMA_SLOW)

            if ema_fast is None or ema_slow is None:
                logger.warning(f"EMA calculation returned None for {tf}m")
                return None

            # Drop NaN values
            ema_fast = ema_fast.dropna()
            ema_slow = ema_slow.dropna()

            if ema_fast.empty or ema_slow.empty:
                logger.warning(f"EMA calculation returned empty for {tf}m")
                return None

            # Get latest values
            ef = float(ema_fast.iloc[-1])
            es = float(ema_slow.iloc[-1])
            lc = float(df['close'].iloc[-1])

            # Validate values
            if any(pd.isna([ef, es, lc])):
                logger.warning(f"Invalid EMA values for {tf}m")
                return None

            return EMAData(
                fast_ema=ef,
                slow_ema=es,
                close=lc,
                timestamp=datetime.now(),
                timeframe=tf,
                data_points=len(df)
            )

        except Exception as e:
            logger.error(f"Error calculating EMAs for {tf}m: {e}", exc_info=True)
            return None

    def analyze_timeframe(self, symbol: str, tf: str) -> TimeframeResult:
        """
        Analyze a single timeframe with detailed results.
        Derives higher timeframes from 1-minute data.

        Args:
            symbol: Symbol to analyze
            tf: Timeframe to analyze

        Returns:
            TimeframeResult with direction and metadata
        """
        # Input validation
        if not symbol or not symbol.strip():
            return TimeframeResult(
                direction=TrendDirection.NEUTRAL,
                error="Empty symbol provided"
            )

        symbol = symbol.strip().upper()

        if tf not in self.ALL_TIMEFRAMES:
            logger.warning(f"Invalid timeframe: {tf}, expected one of {self.ALL_TIMEFRAMES}")
            return TimeframeResult(
                direction=TrendDirection.NEUTRAL,
                error=f"Invalid timeframe: {tf}"
            )

        cache_key = f'{symbol}_{tf}'

        # Check cache
        try:
            with self._cache_lock() as locked:
                if locked and cache_key in self._cache:
                    cached_result, timestamp = self._cache[cache_key]
                    if (time.time() - timestamp) < self._ttl:
                        self._update_stats(hit=True)
                        cached_result.cached = True
                        return cached_result
        except Exception as e:
            logger.warning(f"Cache access error: {e}", exc_info=True)

        self._update_stats(hit=False)

        # Fetch base 1-minute data
        base_df = self._fetch_base_data(symbol)
        if base_df is None or base_df.empty:
            return TimeframeResult(
                direction=TrendDirection.NEUTRAL,
                error="Failed to fetch base 1-minute data",
                data_points=0
            )

        # Get data for requested timeframe
        if tf == self.BASE_TIMEFRAME:
            # Use base data directly
            df = base_df
            derived = False
            derived_from = None
        else:
            # Resample to target timeframe
            df = self._resample_to_timeframe(base_df, tf)
            derived = True
            derived_from = self.BASE_TIMEFRAME
            self._update_stats(derived=True)

        if df is None or df.empty:
            return TimeframeResult(
                direction=TrendDirection.NEUTRAL,
                error=f"Resampling to {tf}m produced no data",
                data_points=0,
                derived_from=derived_from
            )

        if len(df) < self.EMA_SLOW:
            return TimeframeResult(
                direction=TrendDirection.NEUTRAL,
                error=f"Insufficient data: {len(df)} bars (need {self.EMA_SLOW})",
                data_points=len(df),
                derived_from=derived_from
            )

        # Calculate EMAs
        ema_data = self._calculate_emas(df, tf)
        if ema_data is None or not ema_data.is_valid:
            return TimeframeResult(
                direction=TrendDirection.NEUTRAL,
                error="EMA calculation failed",
                data_points=len(df),
                derived_from=derived_from
            )

        # Create result
        result = TimeframeResult(
            direction=ema_data.direction,
            ema_data=ema_data,
            cached=False,
            data_points=len(df),
            derived_from=derived_from
        )

        # Update cache
        with self._cache_lock() as locked:
            if locked:
                # Implement LRU-like behavior
                if len(self._cache) >= self.MAX_CACHE_SIZE:
                    oldest_key = min(self._cache.keys(),
                                   key=lambda k: self._cache[k][1])
                    del self._cache[oldest_key]

                self._cache[cache_key] = (result, time.time())

        logger.debug(f"MTF {symbol} {tf}m: {result.direction.value} "
                   f"(EMA9={ema_data.fast_ema:.2f}, EMA21={ema_data.slow_ema:.2f}, "
                   f"LTP={ema_data.close:.2f}, derived={derived}, points={len(df)})")

        return result

    def get_direction(self, symbol: str, tf: str) -> str:
        """
        Get trend direction for a symbol on a specific timeframe.

        Args:
            symbol: Symbol to analyze
            tf: Timeframe ('1', '5', '15')

        Returns:
            'BULLISH', 'BEARISH', or 'NEUTRAL'
        """
        result = self.analyze_timeframe(symbol, tf)
        return result.direction.value if result.is_valid else 'NEUTRAL'

    def analyze_entry(self, symbol: str, trade_direction: str) -> MTFDecision:
        """
        Detailed analysis of entry conditions.

        Args:
            symbol: Symbol to analyze
            trade_direction: 'CALL' or 'PUT'

        Returns:
            MTFDecision with detailed results
        """
        if not symbol or not symbol.strip():
            return MTFDecision(
                allowed=True,
                summary='MTF: No symbol (bypassed)',
                matches=0,
                total=0,
                results={},
                agreement_percentage=0.0
            )

        symbol = symbol.strip().upper()
        target = TrendDirection.from_trade_direction(trade_direction)

        # Get results for all timeframes
        results = {}
        valid_count = 0
        matches = 0

        for tf in self.ALL_TIMEFRAMES:
            result = self.analyze_timeframe(symbol, tf)
            results[tf] = result

            if result.is_valid:
                valid_count += 1
                if result.direction == target:
                    matches += 1

        # Calculate agreement percentage
        agreement_pct = (matches / valid_count * 100) if valid_count > 0 else 0.0

        # Build summary string with visual indicators
        ticks = {}
        for tf in self.ALL_TIMEFRAMES:
            result = results[tf]
            if not result.is_valid:
                ticks[tf] = '!'  # Error
            elif result.direction == target:
                ticks[tf] = '✓'  # Match
            elif result.direction == TrendDirection.NEUTRAL:
                ticks[tf] = '○'  # Neutral
            else:
                ticks[tf] = '✗'  # Opposite

        summary = 'MTF: ' + ' '.join(f'{tf}m{ticks[tf]}' for tf in self.ALL_TIMEFRAMES)

        # Add data quality indicator
        if valid_count < len(self.ALL_TIMEFRAMES):
            summary += f' ({len(self.ALL_TIMEFRAMES) - valid_count} invalid)'

        # Decision: require at least REQUIRED_AGREEMENT of valid results to agree
        allowed = matches >= self.REQUIRED_AGREEMENT if valid_count >= self.REQUIRED_AGREEMENT else False
        summary += f' -> {"ALLOWED" if allowed else "BLOCKED"} ({matches}/{valid_count} agree, {agreement_pct:.0f}%)'

        logger.info(f'[MTF] {summary}')

        return MTFDecision(
            allowed=allowed,
            summary=summary,
            matches=matches,
            total=valid_count,
            results=results,
            agreement_percentage=Utils.round_off(agreement_pct)
        )

    def should_allow_entry(self, symbol: str, trade_direction: str) -> Tuple[bool, str]:
        """
        Check if entry should be allowed based on multi-timeframe agreement.

        Args:
            symbol: Symbol to analyze
            trade_direction: 'CALL' or 'PUT'

        Returns:
            Tuple[bool, str]: (allowed, summary_string)
        """
        decision = self.analyze_entry(symbol, trade_direction)
        return decision.allowed, decision.summary

    def get_detailed_results(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        """
        Get detailed results for all timeframes (for GUI display).

        Args:
            symbol: Symbol to analyze

        Returns:
            Dict mapping timeframe to direction and details
        """
        try:
            results = {}
            for tf in self.ALL_TIMEFRAMES:
                result = self.analyze_timeframe(symbol, tf)
                results[tf] = result.to_dict()

            return results

        except Exception as e:
            logger.error(f"[MTF.get_detailed_results] Failed: {e}", exc_info=True)
            return {}

    def get_confluence_score(self, symbol: str, trade_direction: str) -> float:
        """
        Get confluence score (0-100%) for entry signal.

        Args:
            symbol: Symbol to analyze
            trade_direction: 'CALL' or 'PUT'

        Returns:
            Confluence score as percentage
        """
        decision = self.analyze_entry(symbol, trade_direction)
        return decision.agreement_percentage

    def get_timeframe_alignment(self, symbol: str) -> Dict[str, Any]:
        """
        Get alignment status across all timeframes.

        Args:
            symbol: Symbol to analyze

        Returns:
            Dictionary with alignment information
        """
        results = {}
        directions = {}
        data_quality = {}

        for tf in self.ALL_TIMEFRAMES:
            result = self.analyze_timeframe(symbol, tf)
            results[tf] = result
            if result.is_valid:
                directions[tf] = result.direction.value
                data_quality[tf] = {
                    "data_points": result.data_points,
                    "derived": result.derived_from is not None
                }

        # Count directions
        bullish_count = sum(1 for r in results.values() if r.is_valid and r.direction == TrendDirection.BULLISH)
        bearish_count = sum(1 for r in results.values() if r.is_valid and r.direction == TrendDirection.BEARISH)
        neutral_count = sum(1 for r in results.values() if r.is_valid and r.direction == TrendDirection.NEUTRAL)
        invalid_count = sum(1 for r in results.values() if not r.is_valid)

        # Determine overall bias
        if bullish_count > bearish_count and bullish_count > neutral_count:
            overall_bias = "BULLISH"
            bias_strength = bullish_count / len(self.ALL_TIMEFRAMES) * 100
        elif bearish_count > bullish_count and bearish_count > neutral_count:
            overall_bias = "BEARISH"
            bias_strength = bearish_count / len(self.ALL_TIMEFRAMES) * 100
        else:
            overall_bias = "NEUTRAL"
            bias_strength = 0.0

        return {
            "directions": directions,
            "data_quality": data_quality,
            "counts": {
                "bullish": bullish_count,
                "bearish": bearish_count,
                "neutral": neutral_count,
                "invalid": invalid_count,
                "valid": len(self.ALL_TIMEFRAMES) - invalid_count
            },
            "overall_bias": overall_bias,
            "bias_strength": Utils.round_off(bias_strength),
            "alignment_score": round(max(bullish_count, bearish_count) / len(self.ALL_TIMEFRAMES) * 100, 2),
            "timestamp": datetime.now().isoformat()
        }

    def invalidate_cache(self, symbol: Optional[str] = None):
        """
        Clear the cache.

        Args:
            symbol: If provided, only clear cache for this symbol
        """
        try:
            with self._cache_lock() as locked:
                if not locked:
                    logger.warning("Could not acquire cache lock for invalidation")
                    return

                if symbol:
                    symbol = symbol.strip().upper()
                    # Clear analysis cache for symbol
                    keys_to_delete = [k for k in self._cache if k.startswith(f'{symbol}_')]
                    for key in keys_to_delete:
                        del self._cache[key]

                    # Clear base data cache for symbol
                    base_key = f"{symbol}_base"
                    if base_key in self._base_data_cache:
                        del self._base_data_cache[base_key]

                    logger.info(f"MTF cache invalidated for symbol {symbol} "
                              f"({len(keys_to_delete)} entries)")
                else:
                    # Clear all caches
                    cache_size = len(self._cache)
                    base_size = len(self._base_data_cache)
                    self._cache.clear()
                    self._base_data_cache.clear()
                    logger.info(f"MTF cache fully invalidated ({cache_size} analysis, "
                              f"{base_size} base entries)")

        except Exception as e:
            logger.error(f"[MTF.invalidate_cache] Failed: {e}", exc_info=True)

    def refresh_base_data(self, symbol: str) -> bool:
        """
        Force refresh of base 1-minute data for a symbol.

        Args:
            symbol: Symbol to refresh

        Returns:
            bool: True if refresh successful
        """
        try:
            df = self._fetch_base_data(symbol, force_refresh=True)
            if df is not None and not df.empty:
                logger.info(f"Successfully refreshed base data for {symbol}")
                return True
            return False
        except Exception as e:
            logger.error(f"[MTF.refresh_base_data] Failed for {symbol}: {e}", exc_info=True)
            return False

    @lru_cache(maxsize=128)
    def get_supported_timeframes(self) -> Tuple[str, ...]:
        """Get supported timeframes as tuple (cached)."""
        return tuple(self.ALL_TIMEFRAMES)

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return {
            "base_timeframe": self.BASE_TIMEFRAME,
            "derived_timeframes": self.DERIVED_TIMEFRAMES,
            "all_timeframes": self.ALL_TIMEFRAMES,
            "ema_fast": self.EMA_FAST,
            "ema_slow": self.EMA_SLOW,
            "ttl_seconds": self._ttl,
            "max_cache_size": self.MAX_CACHE_SIZE,
            "max_base_cache_size": self.MAX_BASE_CACHE_SIZE,
            "required_agreement": self.REQUIRED_AGREEMENT,
            "min_data_points": self.MIN_DATA_POINTS,
            "base_data_days": self.BASE_DATA_DAYS,
            "base_data_lookback": self.BASE_DATA_LOOKBACK
        }

    def update_config(self, **kwargs):
        """
        Update configuration parameters.

        Args:
            **kwargs: Configuration parameters to update
        """
        valid_params = {
            'ttl_seconds': int,
            'max_cache_size': int,
            'max_base_cache_size': int,
            'required_agreement': int,
            'min_data_points': int,
            'base_data_days': int
        }

        with self._lock:
            for key, value in kwargs.items():
                if key in valid_params:
                    # Validate parameter
                    if key == 'ttl_seconds' and value < 0:
                        logger.warning(f"Invalid ttl_seconds: {value}, must be >= 0")
                        continue
                    if key in ['max_cache_size', 'max_base_cache_size',
                              'required_agreement', 'min_data_points', 'base_data_days']:
                        if value <= 0:
                            logger.warning(f"Invalid {key}: {value}, must be > 0")
                            continue

                    # Update parameter
                    if key == 'base_data_days':
                        self.BASE_DATA_DAYS = value
                    elif key == 'max_base_cache_size':
                        self.MAX_BASE_CACHE_SIZE = value
                    else:
                        setattr(self, f"_{key}", value)

                    logger.info(f"Updated config: {key} = {value}")

                    # Invalidate cache if relevant parameters changed
                    if key in ['ttl_seconds', 'base_data_days']:
                        self.invalidate_cache()

    def cleanup(self):
        """Clean up resources properly."""
        try:
            logger.info("[MultiTimeframeFilter] Starting cleanup")

            # Clear caches
            self.invalidate_cache()

            # Clear stats
            with self._stats_lock:
                self._stats.clear()

            # Clear broker reference
            self._broker = None

            logger.info("[MultiTimeframeFilter] Cleanup completed")

        except Exception as e:
            logger.error(f"[MultiTimeframeFilter.cleanup] Error: {e}", exc_info=True)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()