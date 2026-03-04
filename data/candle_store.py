"""
data/candle_store.py
====================
Single source of truth for OHLCV candle data.

Design
------
Always fetch and store at 1-minute resolution.  Any higher timeframe
(5m, 15m, 30m, 60m …) is produced by resampling in-process — no extra
broker calls required.

Why this is better than fetching at the target interval directly
---------------------------------------------------------------
1. **One API call instead of N** — broker rate limits hit per call, not
   per candle.  A 400-bar 5-minute fetch costs the same rate-limit slot
   as a 400-bar 1-minute fetch, but the 1-minute fetch gives you 5×
   the resolution.
2. **Change timeframe without re-fetching** — switching from 5m to 15m
   analysis mid-session is instant; just call resample(15).
3. **Broker interval incompatibility vanishes** — many brokers don't
   support 2-min or 3-min natively (Dhan, ICICI).  Fetch 1-min,
   resample to any minute count you like.
4. **MTF from one dataset** — multi-timeframe analysis (1m + 5m + 15m)
   uses the same underlying 1-min store; results are always perfectly
   aligned.
5. **Backtest accuracy** — the backtest engine can replay 1-min bars
   and produce any higher-TF view without fetching separate datasets.

Thread safety
-------------
All mutations go through a single RLock.  Read-only callers (resample,
get_1min) receive copies so the caller can never accidentally mutate
the store.

Timezone Handling
-----------------
All timestamps are stored as timezone-aware IST (Asia/Kolkata) to ensure
consistent market hours filtering and resampling. The Indian market opens
at 9:15 AM and closes at 3:30 PM IST.

BUG FIXES (vs original)
-----------------------
1. _ensure_ist / _ensure_index_ist: Used `tzinfo.zone` which is pytz-only
   and crashes with stdlib `datetime.timezone` or `zoneinfo`. Replaced with
   a safe `_tz_name()` helper that works with any tzinfo implementation.

2. _do_resample partial last bar: A 30-min bar labelled 15:15 spans
   15:15–15:44, but the market closes at 15:30, so only 15 minutes of
   data fill it. The bar appeared complete but was silently truncated.
   Fixed by dropping bars whose label + interval > MARKET_CLOSE.

3. push_tick volume: `_tick_volume += 1` counted ticks, not real traded
   volume. Added a `volume` parameter so callers can pass actual traded
   quantity from the WebSocket tick.

4. _do_resample rename no-op: `rename(columns={"index": "time"})` was
   dead code — after `reset_index()` the column is already named "time"
   because the index was named "time" by `_ingest`. Removed the no-op.

5. create_from_dataframe max_bars timing: `store.max_bars = max_bars`
   was set AFTER `from_dataframe()` had already run `_ingest()` with the
   default 2000-bar limit, so the custom limit was never applied to the
   initial data. Fixed by passing max_bars to the constructor directly.

6. _ingest uses `df[\"time\"].dt.tz.zone` (pytz-only). Fixed with the same
   safe `_tz_name()` helper used in _ensure_ist.

Usage
-----
    # --- live ---
    store = CandleStore(symbol="NIFTY", broker=broker)
    store.fetch(days=10)                    # loads 1-min bars from broker
    df_5m  = store.resample(5)              # → 5-min OHLCV DataFrame
    df_15m = store.resample(15)             # → 15-min OHLCV DataFrame

    # Tick-by-tick update (call on every WS tick):
    store.push_tick(ltp=24750.0, volume=10, ts=datetime.now())
    df_5m = store.resample(5)              # always up-to-date

    # --- backtest ---
    store = CandleStore.from_dataframe(df_1min, symbol="NIFTY")
    df_5m = store.resample(5)
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, Optional

import pandas as pd
from pytz import timezone

from Utils.OptionUtils import OptionUtils
from Utils.common import MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE
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

    FIX: The original code used ``tzinfo.zone`` which is pytz-only.
    Any timezone coming from stdlib (``datetime.timezone.utc``) or from
    a broker SDK that uses ``dateutil`` or ``zoneinfo`` would raise
    ``AttributeError``, silently swallowed inside ``_ensure_ist`` and
    then the datetime would be returned without conversion.
    """
    if tzinfo is None:
        return ""
    # pytz
    if hasattr(tzinfo, "zone"):
        return tzinfo.zone
    # zoneinfo (Python 3.9+)
    if hasattr(tzinfo, "key"):
        return tzinfo.key
    # dateutil / stdlib — use string representation as last resort
    return str(tzinfo)


class CandleStore:
    """
    In-memory 1-minute candle store with on-demand resampling.

    Parameters
    ----------
    symbol      : canonical derivative name, e.g. "NIFTY"
    broker      : BaseBroker instance (used only for fetch(); may be None
                  when constructing from an existing DataFrame via from_dataframe)
    max_bars    : maximum 1-min bars to keep in memory (rolling window)
                  Default 2000 ≈ ~5.3 trading days at 375 bars/day
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
        self._resample_cache: Dict[int, pd.DataFrame] = {}

        # Tick accumulator for the current live 1-min candle
        self._tick_open: Optional[float] = None
        self._tick_high: Optional[float] = None
        self._tick_low: Optional[float] = None
        self._tick_close: Optional[float] = None
        self._tick_volume: float = 0.0
        self._tick_bar_start: Optional[datetime] = None

    # ── Timezone helpers ───────────────────────────────────────────────────

    def _ensure_ist(self, dt: Optional[datetime]) -> Optional[datetime]:
        """
        Ensure *dt* is timezone-aware IST.

        FIX: Original used ``dt.tzinfo.zone`` (pytz-only). Now uses
        ``_tz_name()`` which handles any tzinfo implementation.
        """
        if dt is None:
            return None
        if dt.tzinfo is None:
            return IST.localize(dt)
        if _tz_name(dt.tzinfo) != "Asia/Kolkata":
            return dt.astimezone(IST)
        return dt

    def _ensure_index_ist(self, index: pd.DatetimeIndex) -> pd.DatetimeIndex:
        """
        Ensure *index* is timezone-aware IST.

        FIX: Original used ``index.tz.zone`` (pytz-only). Now uses
        ``_tz_name()`` which handles any tzinfo implementation.
        """
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

        The DataFrame must have columns: time, open, high, low, close, volume
        (volume may be 0 if unavailable).

        FIX: Added ``max_bars`` parameter so callers can pass a custom limit
        that is honoured during the initial ``_ingest()`` call.  Previously,
        ``CandleStoreManager.create_from_dataframe()`` set ``store.max_bars``
        AFTER construction, meaning ``_ingest()`` had already run with the
        default 2000-bar limit and the custom limit was silently ignored.
        """
        store = cls(symbol=symbol, broker=None, max_bars=max_bars)
        store._ingest(df)
        return store

    # ── Public API ─────────────────────────────────────────────────────────────

    def fetch(self, days: int = 2, broker_type: Optional[str] = None) -> bool:
        """
        Fetch 1-minute data from the broker and populate the store.

        Parameters
        ----------
        days        : how many calendar days of history to request
        broker_type : broker identifier for symbol/interval translation
                      (e.g. "fyers", "zerodha").  When None, no translation
                      is applied and the broker is assumed to accept plain
                      symbol strings and "1" as the interval.

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
            if df is None or (hasattr(df, "empty") and df.empty):
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

            if df is None or (hasattr(df, "empty") and df.empty):
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

        Call this on every tick from on_message().  When the minute
        boundary rolls over, the completed candle is appended to the store
        and the resample cache is invalidated.

        Parameters
        ----------
        ltp    : last traded price
        volume : traded quantity for this tick
        ts     : tick timestamp (defaults to datetime.now(IST) if None)

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

            elif bar_start > self._tick_bar_start:
                # Minute rolled — flush the completed candle
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
                self._tick_volume += float(volume)  # FIX: accumulate real volume

        return bar_completed

    def resample(self, minutes: int) -> Optional[pd.DataFrame]:
        """
        Return an OHLCV DataFrame at the requested candle interval.

        1-minute data is resampled using standard OHLCV aggregation:
            open   → first
            high   → max
            low    → min
            close  → last
            volume → sum

        The result is cached; the cache is invalidated when new 1-min
        bars are appended.

        Parameters
        ----------
        minutes : target candle width in minutes.  1 returns the raw
                  1-min DataFrame unchanged.

        Returns a copy (safe to mutate by callers) with time column in IST.
        """
        with self._lock:
            if self._df is None or self._df.empty:
                return None

            if minutes <= 1:
                df_copy = self._df.reset_index().copy()
                if df_copy["time"].dt.tz is None:
                    df_copy["time"] = df_copy["time"].dt.tz_localize(IST)
                return df_copy

            if minutes in self._resample_cache:
                return self._resample_cache[minutes].copy()

            resampled = self._do_resample(self._df, minutes)
            if resampled is not None and not resampled.empty:
                self._resample_cache[minutes] = resampled
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

    def is_stale(self, max_gap_minutes: int = 5) -> bool:
        """
        Return True if the most recent completed bar is older than
        *max_gap_minutes* during market hours.

        Useful for triggering a re-fetch when data has gaps.

        New method — was not in the original.
        """
        last = self.last_bar_time()
        if last is None:
            return True
        now = self._now_ist()
        now_t = now.time()
        if not (_MARKET_OPEN <= now_t <= _MARKET_CLOSE):
            return False
        return (now - last) > timedelta(minutes=max_gap_minutes)

    def get_data_in_timezone(self, minutes: int,
                             tz: str = "Asia/Kolkata") -> Optional[pd.DataFrame]:
        """
        Get resampled data converted to a specific timezone.

        Parameters
        ----------
        minutes : target candle width
        tz      : target timezone (e.g., 'UTC', 'America/New_York')

        Returns DataFrame with time column converted to target timezone.
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

        Uses pandas offset aliases so bars always align to the start of the
        Indian trading session (09:15) regardless of the requested interval.
        This means a 5-min bar always starts at :15, :20, :25 … and a 15-min
        bar at :15, :30, :45 … matching NSE exchange candle boundaries.
        Removed.
        """
        try:
            df = df_1min.copy()

            # Ensure index is timezone-aware IST
            if df.index.tz is None:
                df.index = df.index.tz_localize(IST)
            elif _tz_name(df.index.tz) != "Asia/Kolkata":
                df.index = df.index.tz_convert(IST)

            rule = f"{minutes}min"

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

            # Drop bars outside market open
            ohlcv = ohlcv[ohlcv.index.time >= _MARKET_OPEN]
            last_full_bar_label = (
                    datetime.combine(datetime.today(), _MARKET_CLOSE)
                    - timedelta(minutes=minutes - 1)
            ).time()
            ohlcv = ohlcv[ohlcv.index.time <= last_full_bar_label]

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
        # FIX: Use _tz_name() instead of .dt.tz.zone (pytz-only)
        if df["time"].dt.tz is None:
            df["time"] = df["time"].dt.tz_localize(IST)
        elif _tz_name(df["time"].dt.tz) != "Asia/Kolkata":
            df["time"] = df["time"].dt.tz_convert(IST)

        if "volume" not in df.columns:
            df["volume"] = 0

        df = df.sort_values("time").set_index("time")

        if minutes <= 1:
            return df.reset_index()

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
