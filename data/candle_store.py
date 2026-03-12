# candle_store.py (fixed)
"""
data/candle_store.py
====================
Single source of truth for OHLCV candle data with improved cache invalidation.

FIXED: Resample cache invalidation, timestamp validation, and memory management.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, time as dt_time, timedelta
from Utils.time_utils import IST, ist_now, fmt_display, fmt_stamp
from typing import Dict, Optional, Tuple

import pandas as pd
from pytz import timezone

from Utils.OptionUtils import OptionUtils
from Utils.common import MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE
from Utils.safe_getattr import safe_hasattr
from broker.BaseBroker import TokenExpiredError

logger = logging.getLogger(__name__)

# Timezone constants
IST = timezone('Asia/Kolkata')

# NSE market session (IST)
_MARKET_OPEN = dt_time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)
_MARKET_CLOSE = dt_time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)

# Required OHLCV columns (lowercase, matching every broker normalisation)
_OHLCV = ["time", "open", "high", "low", "close", "volume"]


# ── Timezone utility ──────────────────────────────────────────────────────────

def _tz_name(tzinfo) -> str:
    """
    Return the IANA zone name for any tzinfo object.

    Works with pytz, dateutil, stdlib datetime.timezone, and Python 3.9+
    zoneinfo.  Never raises AttributeError regardless of tzinfo source.
    """
    if tzinfo is None:
        return ""
    # pytz
    if safe_hasattr(tzinfo, "zone"):
        return tzinfo.zone
    # zoneinfo (Python 3.9+)
    if safe_hasattr(tzinfo, "key"):
        return tzinfo.key
    # dateutil / stdlib — use string representation as last resort
    return str(tzinfo)


# ── Convenience factory used by backtest engine ────────────────────────────────

def resample_df(df_1min: pd.DataFrame, minutes: int) -> Optional[pd.DataFrame]:
    """
    Standalone function: resample any 1-min DataFrame to a higher timeframe.

    Parameters
    ----------
    df_1min : DataFrame with columns [time, open, high, low, close, volume]
              time must be parseable to datetime.
    minutes : target candle width

    Returns resampled DataFrame or None on error.

    Example
    -------
        df_5m  = resample_df(df_1min, 5)
        df_15m = resample_df(df_1min, 15)
    """
    try:
        if df_1min is None or df_1min.empty:
            return None

        df = df_1min.copy()
        df.columns = [c.lower() for c in df.columns]

        if not pd.api.types.is_datetime64_any_dtype(df["time"]):
            df["time"] = pd.to_datetime(df["time"])

        # Make timezone-aware (assume IST if naive)
        if df["time"].dt.tz is None:
            df["time"] = df["time"].dt.tz_localize(IST)
        elif _tz_name(df["time"].dt.tz) != "Asia/Kolkata":
            df["time"] = df["time"].dt.tz_convert(IST)

        if "volume" not in df.columns:
            df["volume"] = 0

        df = df.sort_values("time").set_index("time")

        if minutes <= 1:
            return df.reset_index()

        # Reuse the existing resampling logic
        return CandleStore._do_resample(df, minutes)

    except Exception as e:
        logger.error(f"[resample_df] {e}", exc_info=True)
        return None


def convert_timezone(df: pd.DataFrame, time_col: str = "time",
                     from_tz: Optional[str] = None,
                     to_tz: str = "Asia/Kolkata") -> pd.DataFrame:
    """
    Convert timezone of a DataFrame's time column.

    Parameters
    ----------
    df       : DataFrame with time column
    time_col : name of the time column
    from_tz  : source timezone (if None, assume IST for naive, or use existing)
    to_tz    : target timezone

    Returns DataFrame with converted time column.
    """
    if df is None or df.empty or time_col not in df.columns:
        return df

    result = df.copy()

    if result[time_col].dt.tz is None:
        source = from_tz if from_tz else "Asia/Kolkata"
        result[time_col] = result[time_col].dt.tz_localize(source)

    result[time_col] = result[time_col].dt.tz_convert(to_tz)
    return result


class CandleStore:
    """
    In-memory 1-minute candle store with on-demand resampling.

    FIXED: Resample cache with timestamp validation to ensure fresh data.
    """

    def __init__(
            self,
            symbol: str,
            broker=None,
            max_bars: int = 2000,
    ):
        self.symbol = symbol
        self.broker = broker
        self.max_bars = max_bars

        self._lock: threading.RLock = threading.RLock()
        self._df: Optional[pd.DataFrame] = None  # 1-min bars, time-indexed (IST-aware)
        self._resample_cache: Dict[int, Tuple[pd.DataFrame, datetime]] = {}

        # Tick accumulator for the current live 1-min candle
        self._tick_open: Optional[float] = None
        self._tick_high: Optional[float] = None
        self._tick_low: Optional[float] = None
        self._tick_close: Optional[float] = None
        self._tick_volume: float = 0.0
        self._tick_bar_start: Optional[datetime] = None
        # BUG-C fix: track last flush timestamp to invalidate stale cache entries
        self._last_flush_ts: Optional[datetime] = None

    # ── Timezone helpers ───────────────────────────────────────────────────

    def _ensure_ist(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Ensure *dt* is timezone-aware IST."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return IST.localize(dt)
        if _tz_name(dt.tzinfo) != "Asia/Kolkata":
            return dt.astimezone(IST)
        return dt

    def _ensure_index_ist(self, index: pd.DatetimeIndex) -> pd.DatetimeIndex:
        """Ensure *index* is timezone-aware IST."""
        if index.tz is None:
            return index.tz_localize(IST)
        if _tz_name(index.tz) != "Asia/Kolkata":
            return index.tz_convert(IST)
        return index

    def _now_ist(self) -> datetime:
        """Return current time in IST."""
        return datetime.now(IST)

    # ── Construction helpers ───────────────────────────────────────────────────

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, symbol: str = "",
                       max_bars: int = 2000) -> "CandleStore":
        """
        Build a CandleStore from an already-fetched 1-min DataFrame.
        Used by the backtest engine so it doesn't need a live broker.
        """
        store = cls(symbol=symbol, broker=None, max_bars=max_bars)
        store._ingest(df)
        return store

    # ── Public API ─────────────────────────────────────────────────────────────

    def fetch(self, days: int = 2, broker_type: Optional[str] = None) -> bool:
        """
        Fetch 1-minute data from the broker and populate the store.

        Returns True on success, False on failure.
        """
        if self.broker is None:
            logger.error("[CandleStore.fetch] No broker configured.")
            return False

        try:
            broker_sym = self._translate_symbol(broker_type)
            broker_int = self._translate_interval("1", broker_type)

            logger.info(
                f"[CandleStore] Fetching 1-min data: symbol='{broker_sym}' "
                f"days={days} broker={broker_type or 'generic'}"
            )

            df = None

            # Primary: get_history_for_timeframe
            try:
                df = self.broker.get_history_for_timeframe(
                    symbol=broker_sym,
                    interval=broker_int,
                    days=days,
                )
            except TokenExpiredError:
                raise
            except Exception as e:
                logger.warning(
                    f"[CandleStore] get_history_for_timeframe failed: {e}  "
                    f"— falling back to get_history()"
                )

            # Fallback: get_history with estimated length
            if df is None or (safe_hasattr(df, "empty") and df.empty):
                try:
                    length = min(days * 375 + 50, 5000)  # 375 bars/day
                    df = self.broker.get_history(
                        symbol=broker_sym,
                        interval=broker_int,
                        length=length,
                    )
                except TokenExpiredError:
                    raise
                except Exception as e:
                    logger.error(f"[CandleStore] get_history fallback also failed: {e}")
                    return False

            if df is None or (safe_hasattr(df, "empty") and df.empty):
                logger.warning(f"[CandleStore] Broker returned empty 1-min data for '{broker_sym}'")
                return False

            self._ingest(df)
            logger.info(
                f"[CandleStore] Loaded {len(self._df)} 1-min bars for '{self.symbol}'"
            )
            return True

        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[CandleStore.fetch] {e}", exc_info=True)
            return False

    def push_tick(self, ltp: float, volume: float = 0.0,
                  ts: Optional[datetime] = None) -> bool:
        """
        Incorporate a live WebSocket tick into the current 1-minute candle.

        Returns True if a new bar was completed (useful for triggering
        signal re-evaluation), False otherwise.

        """
        if ltp is None:
            return False

        ts = self._ensure_ist(ts) if ts is not None else self._now_ist()
        t = ts.time()

        # Ignore ticks outside market hours
        if not (_MARKET_OPEN <= t <= _MARKET_CLOSE):
            return False

        # Truncate to the current 1-min bar start (preserve timezone)
        bar_start = ts.replace(second=0, microsecond=0)
        bar_completed = False

        with self._lock:
            if self._tick_bar_start is None:
                # First tick ever
                self._tick_bar_start = bar_start
                self._tick_open = ltp
                self._tick_high = ltp
                self._tick_low = ltp
                self._tick_close = ltp
                self._tick_volume = float(volume)

            # Bug #5 fix: Use >= and check time difference to handle clock jumps
            elif bar_start > self._tick_bar_start or (bar_start - self._tick_bar_start).total_seconds() >= 60:
                self._flush_tick_bar()
                bar_completed = True
                self._tick_bar_start = bar_start
                self._tick_open = ltp
                self._tick_high = ltp
                self._tick_low = ltp
                self._tick_close = ltp
                self._tick_volume = float(volume)

            else:
                # Update running OHLC for the current bar
                if self._tick_high is not None:
                    self._tick_high = max(self._tick_high, ltp)
                else:
                    self._tick_high = ltp
                if self._tick_low is not None:
                    self._tick_low = min(self._tick_low, ltp)
                else:
                    self._tick_low = ltp
                self._tick_close = ltp
                self._tick_volume += float(volume)

        return bar_completed

    def resample(self, minutes: int) -> Optional[pd.DataFrame]:
        """
        Return an OHLCV DataFrame at the requested candle interval.

        FIXED: Cache with timestamp validation - cache invalidated after 5 seconds
        or when new bars are added.
        """
        with self._lock:
            if self._df is None or self._df.empty:
                return None

            if minutes <= 1:
                if 1 not in self._resample_cache:
                    df_1min = self._df.reset_index().copy()
                    if df_1min["time"].dt.tz is None:
                        df_1min["time"] = df_1min["time"].dt.tz_localize(IST)
                    self._resample_cache[1] = (df_1min, ist_now())
                return self._resample_cache[1][0].copy()

            # Check cache with timestamp validation
            now = ist_now()
            if minutes in self._resample_cache:
                cached_df, cached_time = self._resample_cache[minutes]
                # BUG-C fix: invalidate cache immediately if a bar was flushed after cache was built
                last_flush = self._last_flush_ts
                cache_is_stale = (last_flush is not None and last_flush > cached_time)
                if not cache_is_stale and (now - cached_time).total_seconds() < 5:
                    return cached_df.copy()

            resampled = self._do_resample(self._df, minutes)
            if resampled is not None and not resampled.empty:
                self._resample_cache[minutes] = (resampled, now)
                return resampled.copy()

            return None

    def get_1min(self) -> Optional[pd.DataFrame]:
        """Return the raw 1-min DataFrame (copy). Equivalent to resample(1)."""
        return self.resample(1)

    def last_bar_time(self) -> Optional[datetime]:
        """Return the timestamp of the most recent completed 1-min bar (IST)."""
        with self._lock:
            if self._df is None or self._df.empty:
                return None
            return self._df.index[-1].to_pydatetime()

    def is_empty(self) -> bool:
        with self._lock:
            return self._df is None or self._df.empty

    def bar_count(self) -> int:
        with self._lock:
            return 0 if self._df is None else len(self._df)

    def get_current_close(self) -> Optional[float]:
        """
        Single source of truth for the current price of this symbol.
        """
        with self._lock:
            if self._tick_close is not None:
                return float(self._tick_close)
            if self._df is not None and not self._df.empty:
                return float(self._df["close"].iloc[-1])
            return None

    def get_current_index_price(self) -> Optional[float]:
        """Alias for get_current_close() — clearer name when the store holds index data."""
        return self.get_current_close()

    def is_stale(self, max_gap_minutes: int = 5) -> bool:
        """
        Return True if the most recent completed bar is older than
        *max_gap_minutes* during market hours.
        """
        last = self.last_bar_time()
        if last is None:
            return True
        now = self._now_ist()
        now_t = now.time()
        if not (_MARKET_OPEN <= now_t <= _MARKET_CLOSE):
            return False
        return (now - last) > timedelta(minutes=max_gap_minutes)

    def needs_update(self, interval_minutes: int, max_gap_minutes: int = 1) -> bool:
        """
        Check if the store needs to fetch updated history.
        """
        with self._lock:
            if self.is_empty():
                return True

            last_bar = self.last_bar_time()
            if last_bar is None:
                return True

            now = datetime.now(IST)
            now_t = now.time()

            # Only check during market hours
            if not (_MARKET_OPEN <= now_t <= _MARKET_CLOSE):
                return False

            next_bar_time = last_bar + timedelta(minutes=interval_minutes)
            time_until_next = (next_bar_time - now).total_seconds() / 60

            # If we're past the next expected bar time, we need an update
            return time_until_next < -max_gap_minutes

    def get_data_in_timezone(self, minutes: int,
                             tz: str = "Asia/Kolkata") -> Optional[pd.DataFrame]:
        """
        Get resampled data converted to a specific timezone.
        """
        df = self.resample(minutes)
        if df is None or df.empty:
            return None
        target_tz = timezone(tz)
        df = df.copy()
        df["time"] = df["time"].dt.tz_convert(target_tz)
        return df

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _ingest(self, df: pd.DataFrame) -> None:
        """Validate, normalise and store a raw broker DataFrame."""
        with self._lock:
            try:
                df = df.copy()

                # Normalise column names to lowercase
                df.columns = [c.lower() for c in df.columns]

                # Ensure 'time' column exists
                if "time" not in df.columns:
                    for alt in ("datetime", "date", "timestamp", "ts"):
                        if alt in df.columns:
                            df = df.rename(columns={alt: "time"})
                            break
                    else:
                        logger.error("[CandleStore._ingest] No time column found.")
                        return

                # Parse timestamps
                if not pd.api.types.is_datetime64_any_dtype(df["time"]):
                    df["time"] = pd.to_datetime(df["time"])

                # Make timezone-aware (assume IST if naive)
                if df["time"].dt.tz is None:
                    df["time"] = df["time"].dt.tz_localize(IST)
                elif _tz_name(df["time"].dt.tz) != "Asia/Kolkata":
                    df["time"] = df["time"].dt.tz_convert(IST)

                # Add missing volume column
                if "volume" not in df.columns:
                    df["volume"] = 0

                # Drop rows missing critical OHLC
                df = df.dropna(subset=["open", "high", "low", "close"])

                # Filter to market hours only
                df = df[df["time"].dt.time.between(_MARKET_OPEN, _MARKET_CLOSE)]

                # Sort and index by time
                df = df.sort_values("time").drop_duplicates(subset="time")
                df = df.set_index("time")
                df.index = self._ensure_index_ist(df.index)

                # Rolling window — keep only the most recent max_bars
                if len(df) > self.max_bars:
                    df = df.iloc[-self.max_bars:]

                self._df = df
                self._resample_cache.clear()

            except Exception as e:
                logger.error(f"[CandleStore._ingest] {e}", exc_info=True)

    def _flush_tick_bar(self) -> None:
        """
        Append the accumulated tick OHLC as a new 1-min row.
        Must be called with self._lock held.
        """
        if self._tick_bar_start is None or self._tick_open is None:
            return

        bar_start = self._ensure_ist(self._tick_bar_start)

        index = pd.DatetimeIndex([bar_start], name="time")
        index = self._ensure_index_ist(index)

        new_row = pd.DataFrame([{
            "open": self._tick_open,
            "high": self._tick_high,
            "low": self._tick_low,
            "close": self._tick_close,
            "volume": self._tick_volume,
        }], index=index)

        if self._df is None:
            self._df = new_row
        else:
            self._df = pd.concat([self._df, new_row])
            self._df = self._df[~self._df.index.duplicated(keep="last")]
            if len(self._df) > self.max_bars:
                self._df = self._df.iloc[-self.max_bars:]

        # Invalidate resample cache — new data arrived
        self._resample_cache.clear()
        # BUG-C fix: record flush timestamp so resample() can detect stale cache entries
        self._last_flush_ts = ist_now()

        # Reset tick accumulators (bar_start reset handled by push_tick)
        self._tick_open = None
        self._tick_high = None
        self._tick_low = None
        self._tick_close = None
        self._tick_volume = 0.0
        self._tick_bar_start = None

    @staticmethod
    def _do_resample(df_1min: pd.DataFrame, minutes: int) -> Optional[pd.DataFrame]:
        """
        Core resampling logic.
        """
        try:
            df = df_1min.copy()

            # Ensure index is timezone-aware IST
            if df.index.tz is None:
                df.index = df.index.tz_localize(IST)
            elif _tz_name(df.index.tz) != "Asia/Kolkata":
                df.index = df.index.tz_convert(IST)

            rule = f"{minutes}min"

            # label="left": each bar is stamped with its OPEN time — the standard
            # convention for Indian markets (Zerodha/Kite, Fyers, Dhan, etc.).
            # The 5-min bar covering 15:25–15:30 is shown as "15:25".
            # closed="left" + offset="9h15min" anchors bins at 09:15 so the first
            # bar of the session is always 09:15 and the last aligns to market close.
            ohlcv = df.resample(
                rule,
                closed="left",
                label="left",
                offset="9h15min",
            ).agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            })

            # Drop bars with no data (gaps / holidays)
            ohlcv = ohlcv.dropna(subset=["open", "close"])

            # Keep only bars fully within the trading session.
            # bar_time = bar OPEN time (label="left").
            # bar end  = bar_time + (minutes - 1) minutes (last 1-min bar in this bucket).
            #
            # IMPORTANT: use .time() for comparison — never datetime.combine(tzinfo=pytz_tz)
            # because pytz uses the historical LMT offset (+5:53:20) instead of IST (+5:30)
            # when tzinfo= is passed directly to datetime.combine(), causing bars after
            # ~15:06 IST to be incorrectly dropped (manifests as last bar = 15:03/15:05).
            def bar_ends_after_close(bar_time):
                """True if this left-labelled bar fits within the trading session."""
                bar_open_t = bar_time.time()
                # Last 1-min bar inside this N-min bucket ends (minutes-1) later
                bar_end_t  = (bar_time + timedelta(minutes=minutes - 1)).time()
                return bar_open_t >= _MARKET_OPEN and bar_end_t <= _MARKET_CLOSE

            ohlcv = ohlcv[ohlcv.index.time >= _MARKET_OPEN]  # fast pre-filter
            mask = [bar_ends_after_close(idx) for idx in ohlcv.index]
            ohlcv = ohlcv[mask]

            ohlcv = ohlcv.reset_index()

            # Ensure time column is timezone-aware IST
            if ohlcv["time"].dt.tz is None:
                ohlcv["time"] = ohlcv["time"].dt.tz_localize(IST)

            return ohlcv

        except Exception as e:
            logger.error(f"[CandleStore._do_resample] {e}", exc_info=True)
            return None

    def _translate_symbol(self, broker_type: Optional[str]) -> str:
        """Convert canonical derivative name to broker-specific index symbol."""
        if not broker_type:
            return self.symbol
        try:
            return OptionUtils.get_index_symbol_for_broker(self.symbol, broker_type)
        except Exception:
            return self.symbol

    def _translate_interval(self, interval: str, broker_type: Optional[str]) -> str:
        """Convert app interval string to broker-specific format."""
        if not broker_type:
            return interval
        try:
            return OptionUtils.translate_interval(interval, broker_type)
        except Exception:
            return interval

    def __repr__(self) -> str:
        return (
            f"<CandleStore symbol={self.symbol!r} "
            f"bars={self.bar_count()} "
            f"cached_timeframes={list(self._resample_cache.keys())}>"
        )