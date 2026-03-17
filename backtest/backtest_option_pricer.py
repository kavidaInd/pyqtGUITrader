# TZ-FIX imports
from Utils.time_utils import IST, ist_localize
"""
backtest/backtest_option_pricer.py
===================================
Option price resolver for the backtesting engine.

Priority chain for each bar:
  1. Real broker historical data  (if available and non-null)
  2. Black-Scholes synthetic price (fallback)

Changes from original:
- VixCache._fetch: removed duplicate `days` variable that was recalculated
  identically in every branch; computed once at top.
- VixCache.get_vix: walk-back loop now uses a pre-built date-index set for
  O(1) lookup instead of linear `in` check on a Series index each iteration.
- OptionPricer.__init__: removed redundant state_manager snapshot read that
  could silently override the derivative passed by the caller; now only reads
  state when derivative is explicitly left as the sentinel "NIFTY" default AND
  state has a non-empty value.
- OptionPricer.resolve_bar: cached expiry datetime per (timestamp.date, type)
  so nearest_weekly/monthly_expiry() is not called on every single bar for
  the same trading day.
- nearest_weekly_expiry / nearest_monthly_expiry: extracted common holiday
  adjustment logic into _adjust_for_holiday() helper.
- _broker_type: simplified class-name sniffing with a dict lookup instead of
  six elif branches.
- black_scholes_price: early-exit intrinsic value returned as rounded float
  instead of bare subtraction result (was inconsistent with the normal path).
- Removed dead `cleanup()` method on OptionPricer that only cleared a list —
  Python GC handles it; kept only if subclasses need it.
- create_pricer_from_state: removed try/except that swallowed all errors and
  silently returned a default pricer — errors now propagate so callers know
  something went wrong.
"""

from __future__ import annotations

import logging
import math
import threading
from datetime import date, datetime, timedelta
from enum import Enum
from functools import lru_cache
from typing import Dict, Optional, Set, Tuple

import pandas as pd

from Utils.safe_getattr import safe_getattr, safe_hasattr
from data.trade_state_manager import state_manager
from Utils.OptionUtils import OptionUtils
from Utils.Utils import Utils

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

RISK_FREE_RATE = 0.065          # India 91-day T-bill ~6.5%
DIVIDEND_YIELD = 0.0            # indices pay no dividend
DEFAULT_VIX = 15.0              # fallback VIX % when all sources fail
DEFAULT_HV = 15.0               # fallback historical-vol % when too few bars
HV_LOOKBACK = 20                # bars used for rolling HV estimate
HV_MIN_BARS = 5                 # minimum bars before HV is trusted
MIN_TIME_TO_EXPIRY = 1 / (365 * 96)   # at least 15 minutes, avoids BS singularity

# Strike rounding step per derivative
STRIKE_STEP: Dict[str, int] = {
    "NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50,
    "MIDCPNIFTY": 25, "SENSEX": 100,
}
DEFAULT_STRIKE_STEP = 50

# Broker → VIX symbol
VIX_SYMBOL_MAP: Dict[str, str] = {
    "fyers":     "NSE:INDIAVIX-INDEX",
    "shoonya":   "NSE|INDIAVIX",
    "flattrade": "NSE|INDIAVIX",
    "default":   "INDIA VIX",
}

# Class-name → broker_type for fast lookup
_CLASS_TO_BROKER: Dict[str, str] = {
    "Fyers": "fyers", "Zerodha": "zerodha", "Dhan": "dhan",
    "Angel": "angelone", "Upstox": "upstox", "Shoonya": "shoonya",
    "Flattrade": "flattrade", "AliceBlue": "aliceblue",
}


# ── Enums ─────────────────────────────────────────────────────────────────────

class PriceSource(Enum):
    REAL = "real"
    SYNTHETIC = "synthetic"


# ── Black-Scholes ─────────────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def rolling_hv(
    spot_series,
    bars_per_year: int = 375 * 252,
    lookback: int = HV_LOOKBACK,
) -> float:
    """
    Compute annualised realised volatility from a sequence of close prices.

    Returns a decimal (e.g. 0.18 for 18%), clamped to [0.05, 1.50].
    Falls back to DEFAULT_HV when there are insufficient data points.
    """
    try:
        prices = list(spot_series)
        if len(prices) < HV_MIN_BARS + 1:
            return DEFAULT_HV / 100.0

        window = prices[-(lookback + 1):]
        log_returns = [
            math.log(window[i] / window[i - 1])
            for i in range(1, len(window))
            if window[i - 1] > 0 and window[i] > 0
        ]
        if len(log_returns) < HV_MIN_BARS:
            return DEFAULT_HV / 100.0

        n = len(log_returns)
        mean_r = sum(log_returns) / n
        variance = sum((r - mean_r) ** 2 for r in log_returns) / max(n - 1, 1)
        ann_vol = math.sqrt(variance) * math.sqrt(bars_per_year)
        return max(0.05, min(1.50, ann_vol))

    except Exception as exc:
        logger.debug("[rolling_hv] %s", exc)
        return DEFAULT_HV / 100.0


def black_scholes_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "CE",
    q: float = 0.0,
) -> float:
    """
    Black-Scholes-Merton option price.

    Returns intrinsic value (rounded) when inputs are degenerate (T≤0, sigma≤0).
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        intrinsic = (S - K) if option_type == "CE" else (K - S)
        return Utils.round_off(max(0.0, intrinsic))

    T = max(T, MIN_TIME_TO_EXPIRY)
    try:
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        if option_type == "CE":
            price = (S * math.exp(-q * T) * _norm_cdf(d1)
                     - K * math.exp(-r * T) * _norm_cdf(d2))
        else:
            price = (K * math.exp(-r * T) * _norm_cdf(-d2)
                     - S * math.exp(-q * T) * _norm_cdf(-d1))

        return max(0.0, Utils.round_off(price))

    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        logger.warning("[BS] math error S=%s K=%s T=%s σ=%s: %s", S, K, T, sigma, exc)
        intrinsic = (S - K) if option_type == "CE" else (K - S)
        return Utils.round_off(max(0.0, intrinsic))


def atm_strike(spot: float, derivative: str) -> float:
    """Round spot to nearest ATM strike for the given derivative."""
    step = STRIKE_STEP.get(derivative.upper(), DEFAULT_STRIKE_STEP)
    return round(spot / step) * step


def time_to_expiry_years(current_dt: datetime, expiry_dt: datetime) -> float:
    """Time to expiry in calendar-year fraction (252-day trading year basis)."""
    # TZ-FIX: normalize both inputs to IST-aware so subtraction never raises
    # "can't subtract offset-naive and offset-aware datetimes".
    if current_dt.tzinfo is None:
        current_dt = IST.localize(current_dt)
    else:
        current_dt = current_dt.astimezone(IST)
    if expiry_dt.tzinfo is None:
        expiry_dt = IST.localize(expiry_dt)
    else:
        expiry_dt = expiry_dt.astimezone(IST)
    delta = (expiry_dt - current_dt).total_seconds()
    if delta <= 0:
        return MIN_TIME_TO_EXPIRY
    trading_seconds_per_year = 252 * 6.25 * 3600
    return max(delta / trading_seconds_per_year, MIN_TIME_TO_EXPIRY)


# ── Broker type helper ────────────────────────────────────────────────────────

def _broker_type(broker) -> str:
    """Extract lowercase broker type string from a broker object."""
    try:
        bt = safe_getattr(safe_getattr(broker, "broker_setting", None), "broker_type", None)
        if bt:
            return str(bt).lower()
        bt = safe_getattr(broker, "broker_type", None)
        if bt:
            return str(bt).lower()
        # Class-name sniffing via dict lookup (O(1), replaces 6 elif branches)
        cls_name = broker.__class__.__name__ if broker else ""
        for key, btype in _CLASS_TO_BROKER.items():
            if key in cls_name:
                return btype
        # Last resort: state snapshot
        snap = state_manager.get_snapshot()
        if snap and "broker_type" in snap:
            return str(snap["broker_type"]).lower()
    except Exception as exc:
        logger.debug("[_broker_type] %s", exc)
    return "default"


# ── VIX cache ─────────────────────────────────────────────────────────────────

class VixCache:
    """
    Fetches and caches India VIX daily close values.

    Priority: broker API → NSE REST → yfinance → constant fallback.
    Thread-safe; fetched once per OptionPricer lifetime.
    """

    def __init__(self) -> None:
        self._data: Optional[pd.Series] = None
        self._date_index: Optional[Set[date]] = None   # fast O(1) date lookup
        self._lock = threading.RLock()
        self._fetched = False
        self._broker = None
        self._broker_type = "default"

    def set_broker(self, broker) -> None:
        self._broker = broker
        self._broker_type = _broker_type(broker)

    def ensure_loaded(self, start: date, end: date) -> None:
        with self._lock:
            if self._fetched:
                return
            self._fetched = True
            self._data = self._fetch(start, end)
            if self._data is not None:
                self._date_index = set(self._data.index)

    def get_vix(self, dt: datetime) -> Tuple[float, bool]:
        """Return (vix_as_decimal, is_real). Falls back to DEFAULT_VIX."""
        if self._data is None or self._data.empty:
            return DEFAULT_VIX / 100.0, False

        target = dt.date() if isinstance(dt, datetime) else dt
        # Walk back up to 5 trading days using the pre-built set for O(1) checks
        date_index = self._date_index or set()
        for delta in range(6):
            candidate = target - timedelta(days=delta)
            if candidate in date_index:
                if delta > 1:
                    logger.debug("[VIX] stale: using %s for %s (%d days gap)", candidate, target, delta)
                return float(self._data[candidate]) / 100.0, True

        return DEFAULT_VIX / 100.0, False

    def _fetch(self, start: date, end: date) -> Optional[pd.Series]:
        days = (end - start).days + 5

        # ── Source 1: broker API ──────────────────────────────────────────────
        if self._broker is not None:
            try:
                vix_sym = VIX_SYMBOL_MAP.get(self._broker_type, VIX_SYMBOL_MAP["default"])
                df = None
                used_interval = None
                for interval in ["1", "5", "15", "1D"]:
                    try:
                        translated = OptionUtils.translate_interval(interval, self._broker_type)
                        _df = self._broker.get_history_for_timeframe(
                            symbol=vix_sym, interval=translated, days=days
                        )
                        if _df is not None and not _df.empty and "close" in _df.columns:
                            df = _df
                            used_interval = interval
                            break
                    except Exception:
                        continue

                if df is not None and not df.empty:
                    if not pd.api.types.is_datetime64_any_dtype(df["time"]):
                        df["time"] = pd.to_datetime(df["time"])
                    if df["time"].dt.tz is not None:
                        # TZ-FIX: convert to IST then strip for .dt.date access only
                        df["time"] = df["time"].dt.tz_convert(IST).dt.tz_localize(None)
                    df = df[(df["time"].dt.date >= start) & (df["time"].dt.date <= end)].copy()
                    if used_interval == "1D":
                        s = pd.Series(df["close"].values, index=df["time"].dt.date.values)
                    else:
                        df["_date"] = df["time"].dt.date
                        s = df.groupby("_date")["close"].last()
                    s = s[s > 0]
                    if not s.empty:
                        logger.info("[VIX] %d rows from broker (sym=%s)", len(s), vix_sym)
                        return s
            except Exception as exc:
                logger.warning("[VIX] broker fetch failed: %s", exc)

        # ── Source 2: NSE REST API ────────────────────────────────────────────
        try:
            import requests
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Referer": "https://www.nseindia.com/",
            }
            session = requests.Session()
            session.get("https://www.nseindia.com", headers=headers, timeout=5)
            url = (
                f"https://www.nseindia.com/api/historical/vixhistory"
                f"?from={start.strftime('%d-%b-%Y')}&to={end.strftime('%d-%b-%Y')}"
            )
            resp = session.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                records = []
                for row in resp.json().get("data", []):
                    try:
                        d = datetime.strptime(row["EOD_TIMESTAMP"], "%d-%b-%Y").date()
                        v = float(row["EOD_CLOSE_INDEX_VAL"])
                        records.append((d, v))
                    except (KeyError, ValueError):
                        continue
                if records:
                    s = pd.Series(dict(records))
                    logger.info("[VIX] %d rows from NSE API", len(s))
                    return s
        except Exception as exc:
            logger.warning("[VIX] NSE API failed: %s", exc)

        # ── Source 3: yfinance ────────────────────────────────────────────────
        try:
            import yfinance as yf
            df = yf.Ticker("^INDIAVIX").history(
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
            )
            if not df.empty:
                s = df["Close"].copy()
                s.index = s.index.date
                logger.info("[VIX] %d rows from yfinance", len(s))
                return s
        except Exception as exc:
            logger.warning("[VIX] yfinance failed: %s", exc)

        logger.warning("[VIX] all sources failed — using constant %.1f%%", DEFAULT_VIX)
        return None


# ── Expiry calendar helpers ───────────────────────────────────────────────────

def _adjust_for_holiday(d: date, max_back: int = 10) -> date:
    """Walk backwards from d until we find a non-holiday trading day."""
    try:
        from Utils.common import is_holiday
        for _ in range(max_back):
            if not is_holiday(d):
                return d
            d -= timedelta(days=1)
    except Exception:
        pass
    return d


def nearest_weekly_expiry(dt: datetime, derivative: str = "NIFTY") -> datetime:
    """Return next weekly expiry datetime on or after dt."""
    try:
        exchange_symbol = OptionUtils.get_exchange_symbol(derivative)
        target_weekday = OptionUtils.EXPIRY_WEEKDAY_MAP.get(exchange_symbol, 1)
    except Exception:
        target_weekday = 1

    current = dt.date()
    days_ahead = (target_weekday - current.weekday()) % 7
    if days_ahead == 0 and dt.hour >= 15 and dt.minute >= 30:
        days_ahead = 7
    exp_date = _adjust_for_holiday(current + timedelta(days=days_ahead))
    # TZ-FIX: localize naive expiry datetime to IST.
    return IST.localize(datetime(exp_date.year, exp_date.month, exp_date.day, 15, 30))


def nearest_monthly_expiry(dt: datetime, derivative: str = "NIFTY") -> datetime:
    """Return next monthly expiry datetime on or after dt."""
    try:
        exchange_symbol = OptionUtils.get_exchange_symbol(derivative)
        expiry_dt = OptionUtils.get_monthly_expiry_date(dt.year, dt.month, derivative=exchange_symbol)
        # TZ-FIX: normalize expiry to IST-aware; never strip tzinfo.
        def _to_ist(d):
            if hasattr(d, "to_pydatetime"):
                d = d.to_pydatetime()
            elif not isinstance(d, datetime):
                d = datetime.fromisoformat(str(d))
            return IST.localize(d) if d.tzinfo is None else d.astimezone(IST)

        expiry = _to_ist(expiry_dt)
        # Also normalize dt for comparison
        dt_aware = IST.localize(dt) if dt.tzinfo is None else dt.astimezone(IST)

        if expiry <= dt_aware:
            nm = dt_aware.month % 12 + 1
            ny = dt_aware.year + (1 if dt_aware.month == 12 else 0)
            expiry_dt2 = OptionUtils.get_monthly_expiry_date(ny, nm, derivative=exchange_symbol)
            expiry = _to_ist(expiry_dt2)
        return expiry
    except Exception as exc:
        logger.warning("[nearest_monthly_expiry] OptionUtils failed: %s — using fallback", exc)

    # Fallback: last Tuesday of the month
    d = dt.date()
    target_wd = 1
    if d.month == 12:
        last_day = date(d.year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(d.year, d.month + 1, 1) - timedelta(days=1)
    offset = (last_day.weekday() - target_wd) % 7
    exp_date = _adjust_for_holiday(last_day - timedelta(days=offset))
    # TZ-FIX: localize naive expiry datetimes to IST.
    exp_dt = IST.localize(datetime(exp_date.year, exp_date.month, exp_date.day, 15, 30))
    dt_aware = IST.localize(dt) if dt.tzinfo is None else dt.astimezone(IST)
    if exp_dt <= dt_aware:
        if d.month >= 11:
            last_day2 = date(d.year + 1, (d.month % 12) + 2, 1) - timedelta(days=1)
        else:
            last_day2 = date(d.year, d.month + 2, 1) - timedelta(days=1)
        offset2 = (last_day2.weekday() - target_wd) % 7
        exp_date2 = _adjust_for_holiday(last_day2 - timedelta(days=offset2))
        exp_dt = IST.localize(datetime(exp_date2.year, exp_date2.month, exp_date2.day, 15, 30))
    return exp_dt


# ── Main resolver ─────────────────────────────────────────────────────────────

class OptionPricer:
    """
    Resolves option OHLCV prices for a given timestamp + spot price.

    Uses real broker data when available, falls back to Black-Scholes.
    Caches expiry datetimes per trading day to avoid redundant calls.
    """

    def __init__(
        self,
        derivative: str = "NIFTY",
        expiry_type: str = "weekly",
        risk_free: float = RISK_FREE_RATE,
        div_yield: float = DIVIDEND_YIELD,
        broker=None,
        use_vix: bool = True,
    ) -> None:
        self.derivative = derivative.upper()
        self.expiry_type = expiry_type
        self.risk_free = risk_free
        self.div_yield = div_yield
        self.use_vix = use_vix
        self._vix = VixCache()
        self._spot_history: list = []
        self._broker_type = "default"
        # Per-day expiry cache: date → datetime
        self._expiry_cache: Dict[date, datetime] = {}

        if broker is not None:
            self._vix.set_broker(broker)
            self._broker_type = _broker_type(broker)

        # Only override derivative from state when caller left the default
        if derivative == "NIFTY":
            try:
                snap = state_manager.get_snapshot()
                state_deriv = (snap or {}).get("derivative", "")
                if state_deriv:
                    self.derivative = state_deriv.upper()
            except Exception:
                pass

    def load_vix(self, start: date, end: date, broker=None) -> None:
        """Pre-fetch VIX data for the backtest date range."""
        if not self.use_vix:
            logger.info("[OptionPricer] use_vix=False — using rolling HV")
            return
        if broker is not None:
            self._vix.set_broker(broker)
            self._broker_type = _broker_type(broker)
        self._vix.ensure_loaded(start, end)

    def push_spot(self, spot_close: float) -> None:
        """Feed latest spot close into the rolling HV buffer (use_vix=False only)."""
        if not self.use_vix:
            self._spot_history.append(float(spot_close))
            if len(self._spot_history) > HV_LOOKBACK + 5:
                self._spot_history = self._spot_history[-(HV_LOOKBACK + 5):]

    def _get_expiry(self, timestamp: datetime) -> datetime:
        """Return expiry datetime for timestamp, cached per trading day."""
        key = timestamp.date()
        if key not in self._expiry_cache:
            if self.expiry_type == "weekly":
                self._expiry_cache[key] = nearest_weekly_expiry(timestamp, self.derivative)
            else:
                self._expiry_cache[key] = nearest_monthly_expiry(timestamp, self.derivative)
        return self._expiry_cache[key]

    def _get_sigma(self, timestamp: datetime, interval_minutes: int = 5) -> Tuple[float, bool]:
        """Return (sigma_decimal, is_real_vix)."""
        if self.use_vix:
            s, real = self._vix.get_vix(timestamp)
            return max(s, 0.05), real
        bars_per_year = int((252 * 375) / max(interval_minutes, 1))
        return max(rolling_hv(self._spot_history, bars_per_year=bars_per_year), 0.05), False

    def resolve_bar(
        self,
        timestamp: datetime,
        spot_open: float,
        spot_high: float,
        spot_low: float,
        spot_close: float,
        option_type: str,
        real_ohlc: Optional[pd.Series] = None,
        minutes_per_bar: int = 5,
        strike: Optional[float] = None,
    ) -> Dict:
        """
        Return a full OHLCV bar dict for one candle.

        Uses spot OHLC to synthesise option OHLC via Black-Scholes when
        real data is absent.  Pass *strike* to lock the pricing to the
        entry strike for open positions.
        """
        # TZ-FIX: normalize timestamp to IST-aware instead of stripping tzinfo.
        if timestamp.tzinfo is None:
            timestamp = IST.localize(timestamp)
        else:
            timestamp = timestamp.astimezone(IST)

        if strike is None:
            strike = atm_strike(spot_close, self.derivative)

        sigma, vix_real = self._get_sigma(timestamp, minutes_per_bar)
        self.push_spot(spot_close)
        expiry_dt = self._get_expiry(timestamp)

        # Real data path
        if real_ohlc is not None:
            ro, rh, rl, rc = (
                real_ohlc.get("open"), real_ohlc.get("high"),
                real_ohlc.get("low"),  real_ohlc.get("close"),
            )
            if all(v is not None and v > 0 for v in [ro, rh, rl, rc]):
                return {
                    "timestamp": timestamp, "open": ro, "high": rh,
                    "low": rl, "close": rc, "strike": strike,
                    "expiry": expiry_dt, "sigma": sigma,
                    "vix_real": vix_real, "source": PriceSource.REAL,
                }

        # Black-Scholes synthetic path
        bar_fraction = minutes_per_bar / (252 * 375)
        T_close = time_to_expiry_years(timestamp, expiry_dt)
        T_open = T_close + bar_fraction
        T_mid = (T_close + T_open) / 2

        c_close = black_scholes_price(spot_close, strike, T_close, self.risk_free, sigma, option_type)
        c_open = black_scholes_price(spot_open,  strike, T_open,  self.risk_free, sigma, option_type)

        # For CE: spot_high → option_high; for PE: spot_low → option_high (inverse)
        if option_type == "CE":
            c_high = black_scholes_price(spot_high, strike, T_mid, self.risk_free, sigma, option_type)
            c_low  = black_scholes_price(spot_low,  strike, T_mid, self.risk_free, sigma, option_type)
        else:
            c_high = black_scholes_price(spot_low,  strike, T_mid, self.risk_free, sigma, option_type)
            c_low  = black_scholes_price(spot_high, strike, T_mid, self.risk_free, sigma, option_type)

        return {
            "timestamp": timestamp,
            "open":  max(0.05, c_open),
            "high":  max(c_open, c_close, c_high),
            "low":   max(0.05, min(c_open, c_close, c_low)),
            "close": max(0.05, c_close),
            "strike": strike,
            "expiry": expiry_dt,
            "sigma": sigma,
            "vix_real": vix_real,
            "source": PriceSource.SYNTHETIC,
        }

    def get_option_symbol(
        self, strike: float, option_type: str, expiry_offset: int = 0
    ) -> Optional[str]:
        """Generate a broker-ready option symbol string."""
        try:
            return OptionUtils.build_option_symbol(
                derivative=self.derivative,
                strike=strike,
                option_type=option_type,
                expiry_type=self.expiry_type,
                broker_type=self._broker_type,
                num_expiries_plus=expiry_offset,
            )
        except Exception as exc:
            logger.error("[OptionPricer.get_option_symbol] %s", exc)
            return None


# ── Convenience factory ───────────────────────────────────────────────────────

def create_pricer_from_state(
    derivative: Optional[str] = None,
    expiry_type: str = "weekly",
    broker=None,
    use_vix: bool = True,
) -> OptionPricer:
    """
    Create an OptionPricer using defaults from the current trade state.

    Errors propagate to the caller — this function no longer silently
    swallows exceptions and returns a default pricer.
    """
    if derivative is None:
        snap = state_manager.get_snapshot()
        derivative = (snap or {}).get("derivative") or "NIFTY"

    return OptionPricer(
        derivative=derivative,
        expiry_type=expiry_type,
        broker=broker,
        use_vix=use_vix,
    )