"""
backtest/backtest_option_pricer.py
===================================
Option price resolver for the backtesting engine.

Priority chain for each bar:
  1. Real broker historical data  (if available and non-null)
  2. Black-Scholes synthetic price (fallback)

Black-Scholes inputs:
  S  — spot price at the bar's timestamp
  K  — ATM strike (rounded to nearest 50 for NIFTY, 100 for BANKNIFTY)
  T  — time to nearest expiry in years
  r  — Indian risk-free rate (91-day T-bill ≈ 6.5%)
  σ  — India VIX / √252 (annualised → per-bar)
  q  — dividend yield (0 for indices)

VIX source:
  The India VIX historical series is fetched from broker's API or public endpoints.
  A fallback constant (15%) is used when data is unavailable.

Each resolved price carries a PriceSource enum so the GUI can render
synthetic bars in a distinct colour and show a disclaimer.

Uses state_manager to access broker type and other configuration that
affects option pricing and symbol generation.
"""

from __future__ import annotations

import logging
import math
import threading
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Tuple

import pandas as pd

from models.trade_state_manager import state_manager
from Utils.OptionUtils import OptionUtils
from Utils.Utils import Utils

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
RISK_FREE_RATE = 0.065  # 6.5% — India 91-day T-bill approximate
DIVIDEND_YIELD = 0.0  # indices pay no dividend
DEFAULT_VIX = 15.0  # fallback when VIX data unavailable (%)
DEFAULT_HV = 15.0  # fallback historical volatility when insufficient bars (%)
HV_LOOKBACK = 20  # bars of log-returns used for rolling HV estimate
HV_MIN_BARS = 5  # minimum bars before HV is trusted over the default
HV_ANNUALISE = 252 * 375  # trading minutes per year (1-min bars) — rescaled per interval
MIN_TIME_TO_EXPIRY = 1 / (365 * 96)  # at least 15 minutes to avoid singularity
NSE_VIX_URL = (
    "https://www.nseindia.com/api/historical/vixhistory"
    "?from={from_date}&to={to_date}"
)

# Strike rounding by derivative
STRIKE_STEP: Dict[str, int] = {
    "NIFTY": 50,
    "BANKNIFTY": 100,
    "FINNIFTY": 50,
    "MIDCPNIFTY": 25,
    "SENSEX": 100,
}
DEFAULT_STRIKE_STEP = 50


class PriceSource(Enum):
    """Tracks whether an option bar price came from real data or BS model."""
    REAL = "real"  # broker-provided historical data
    SYNTHETIC = "synthetic"  # Black-Scholes calculated


# ── Black-Scholes ──────────────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    """Standard normal CDF using math.erfc for numerical stability."""
    return 0.5 * math.erfc(-x / math.sqrt(2))


def rolling_hv(
        spot_series,
        bars_per_year: int = 375 * 252,
        lookback: int = HV_LOOKBACK,
) -> float:
    """
    Compute realised (historical) volatility from a sequence of spot prices.

    Parameters
    ----------
    spot_series  : list or array of close prices, most-recent last
    bars_per_year: total number of bars in a trading year.
                   For 1-min bars: 252 * 375 = 94,500
                   For 5-min bars: 252 * 75  = 18,900
                   For 15-min bars:252 * 25  = 6,300
    lookback     : number of bars to use (default HV_LOOKBACK=20)

    Returns
    -------
    float : annualised volatility as a decimal (e.g. 0.18 for 18%)
    """
    try:
        prices = list(spot_series)
        if len(prices) < HV_MIN_BARS + 1:
            return DEFAULT_HV / 100.0

        # Use the last `lookback+1` prices to compute `lookback` log-returns
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
        bar_vol = math.sqrt(variance)

        # Annualise
        ann_vol = bar_vol * math.sqrt(bars_per_year)
        # Clamp to a sensible range: 5%–150%
        return max(0.05, min(1.50, ann_vol))

    except Exception as e:
        logger.debug(f"[rolling_hv] error: {e}")
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

    Parameters
    ----------
    S           : spot price
    K           : strike price
    T           : time to expiry in years  (must be > 0)
    r           : risk-free rate (annualised, e.g. 0.065)
    sigma       : implied volatility (annualised, e.g. 0.15 for 15%)
    option_type : "CE" (call) or "PE" (put)
    q           : continuous dividend yield

    Returns
    -------
    float : option premium
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(0.0, (S - K) if option_type == "CE" else (K - S))

    T = max(T, MIN_TIME_TO_EXPIRY)

    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if option_type == "CE":
            price = (S * math.exp(-q * T) * _norm_cdf(d1)
                     - K * math.exp(-r * T) * _norm_cdf(d2))
        else:  # PE
            price = (K * math.exp(-r * T) * _norm_cdf(-d2)
                     - S * math.exp(-q * T) * _norm_cdf(-d1))

        return max(0.0, Utils.round_off(price))

    except (ValueError, OverflowError, ZeroDivisionError) as e:
        logger.warning(f"[BS] Math error S={S} K={K} T={T} σ={sigma}: {e}")
        return max(0.0, (S - K) if option_type == "CE" else (K - S))


def atm_strike(spot: float, derivative: str) -> float:
    """Round spot to the nearest ATM strike for the given derivative."""
    step = STRIKE_STEP.get(derivative.upper(), DEFAULT_STRIKE_STEP)
    return round(spot / step) * step


def time_to_expiry_years(current_dt: datetime, expiry_dt: datetime) -> float:
    """
    Calculate T (time to expiry in calendar years).
    Uses trading-day fraction: 252 trading days / year.
    """
    # Normalise: both must be tz-naive
    if hasattr(current_dt, "tzinfo") and current_dt.tzinfo is not None:
        current_dt = current_dt.replace(tzinfo=None)
    if hasattr(expiry_dt, "tzinfo") and expiry_dt.tzinfo is not None:
        expiry_dt = expiry_dt.replace(tzinfo=None)
    delta = (expiry_dt - current_dt).total_seconds()
    if delta <= 0:
        return MIN_TIME_TO_EXPIRY
    # Convert seconds → trading-year fraction
    trading_seconds_per_year = 252 * 6.25 * 3600
    return max(delta / trading_seconds_per_year, MIN_TIME_TO_EXPIRY)


# ── VIX Data ───────────────────────────────────────────────────────────────────

# Broker-specific VIX symbol map
VIX_SYMBOL_MAP: Dict[str, str] = {
    "dhan": "INDIA VIX",
    "zerodha": "INDIA VIX",
    "angelone": "INDIA VIX",
    "upstox": "INDIA VIX",
    "fyers": "NSE:INDIAVIX-INDEX",
    "shoonya": "NSE|INDIAVIX",
    "flattrade": "NSE|INDIAVIX",
    "icici": "INDIA VIX",
    "default": "INDIA VIX",
}


def _broker_type(broker) -> str:
    """
    Best-effort extraction of broker type string (lowercase).
    Uses state_manager if broker is not available.
    """
    try:
        # Try to get from broker object first
        bt = getattr(getattr(broker, "broker_setting", None), "broker_type", None)
        if bt:
            return str(bt).lower()

        # Try to get broker_type directly from broker
        bt = getattr(broker, "broker_type", None)
        if bt:
            return str(bt).lower()

        # Try to get broker name/type from broker class name
        broker_class = broker.__class__.__name__ if broker else ""
        if "Fyers" in broker_class:
            return "fyers"
        elif "Zerodha" in broker_class:
            return "zerodha"
        elif "Dhan" in broker_class:
            return "dhan"
        elif "Angel" in broker_class:
            return "angelone"
        elif "Upstox" in broker_class:
            return "upstox"
        elif "Shoonya" in broker_class:
            return "shoonya"
        elif "Flattrade" in broker_class:
            return "flattrade"
        elif "ICICI" in broker_class:
            return "icici"

        # Fallback to state manager for broker type
        snapshot = state_manager.get_snapshot()
        if snapshot and "broker_type" in snapshot:
            return str(snapshot["broker_type"]).lower()

    except Exception as e:
        logger.debug(f"[_broker_type] Error: {e}")

    return "default"


def _vix_symbol_for_broker(broker) -> str:
    """Return the VIX symbol string appropriate for this broker."""
    bt = _broker_type(broker)
    return VIX_SYMBOL_MAP.get(bt, VIX_SYMBOL_MAP["default"])


class VixCache:
    """
    Fetches and caches India VIX daily close values.

    Priority chain
    --------------
    1. Broker  — via get_history_for_timeframe
    2. NSE API — public REST endpoint
    3. yfinance — ^INDIAVIX via Yahoo Finance
    4. Constant — DEFAULT_VIX (15 %) when every other source fails

    Thread-safe; fetched once per OptionPricer lifetime.
    Uses state_manager for broker type and other configuration.
    """

    def __init__(self):
        self._data: Optional[pd.Series] = None  # index = date, value = VIX %
        self._lock = threading.RLock()
        self._fetched = False
        self._broker = None  # set via set_broker() before ensure_loaded()
        self._broker_type = "default"

    def set_broker(self, broker) -> None:
        """Attach the broker instance so VIX can be fetched from it."""
        self._broker = broker
        self._broker_type = _broker_type(broker)

    def ensure_loaded(self, start: date, end: date) -> None:
        """Ensure VIX data is loaded for the date range."""
        with self._lock:
            if self._fetched:
                return
            self._fetched = True
            self._data = self._fetch(start, end)

    def get_vix(self, dt: datetime) -> Tuple[float, bool]:
        """
        Return (vix_annualised_decimal, is_real).
        Falls back to DEFAULT_VIX if date not in cache.
        """
        if self._data is None or self._data.empty:
            logger.debug(f"[VIX] No VIX data available, using default {DEFAULT_VIX}%")
            return DEFAULT_VIX / 100.0, False

        target = dt.date() if isinstance(dt, datetime) else dt
        # Exact match first, then walk back up to 5 trading days
        for delta in range(6):
            candidate = target - timedelta(days=delta)
            if candidate in self._data.index:
                if delta > 1:
                    logger.debug(
                        f"[VIX] Using stale VIX from {candidate} for requested date {target} "
                        f"({delta} calendar days gap)"
                    )
                return float(self._data[candidate]) / 100.0, True

        logger.debug(f"[VIX] No VIX data for {target}, using default {DEFAULT_VIX}%")
        return DEFAULT_VIX / 100.0, False

    def _fetch(self, start: date, end: date) -> Optional[pd.Series]:
        """Fetch VIX data from various sources."""
        days = (end - start).days + 5

        if self._broker is not None:
            try:
                vix_sym = _vix_symbol_for_broker(self._broker)
                _tried_intervals = ["1", "5", "15", "1D"]
                df = None
                used_interval = None

                logger.debug(f"[VIX] Fetching from broker {self._broker_type} with symbol {vix_sym}")

                for interval in _tried_intervals:
                    try:
                        translated_interval = OptionUtils.translate_interval(
                            interval, self._broker_type
                        )
                        _df = self._broker.get_history_for_timeframe(
                            symbol=vix_sym,
                            interval=translated_interval,
                            days=days,
                        )
                        if _df is not None and not _df.empty and "close" in _df.columns:
                            df = _df
                            used_interval = interval
                            logger.debug(f"[VIX] Got data with interval {interval}")
                            break
                    except Exception as e:
                        logger.debug(f"[VIX] Interval {interval} failed: {e}")
                        continue

                if df is not None and not df.empty and "close" in df.columns:
                    if not pd.api.types.is_datetime64_any_dtype(df["time"]):
                        df["time"] = pd.to_datetime(df["time"])
                    # Strip tz so .date() works uniformly
                    if df["time"].dt.tz is not None:
                        df["time"] = df["time"].dt.tz_localize(None)
                    df = df[
                        (df["time"].dt.date >= start) &
                        (df["time"].dt.date <= end)
                        ].copy()
                    if used_interval == "1D":
                        # Daily: one value per date
                        s = pd.Series(
                            df["close"].values,
                            index=df["time"].dt.date.values,
                        )
                    else:
                        # Intraday: keep the last close per day as representative
                        df["_date"] = df["time"].dt.date
                        daily = df.groupby("_date")["close"].last()
                        s = daily
                    s = s[s > 0]
                    if not s.empty:
                        logger.info(
                            f"[VIX] Loaded {len(s)} rows from broker "
                            f"(symbol={vix_sym}, interval={used_interval}, {start}→{end})"
                        )
                        return s
                    logger.warning(f"[VIX] Broker returned empty/zero VIX data for {vix_sym}")
            except Exception as e:
                logger.warning(f"[VIX] Broker fetch failed: {e}")

        # ── Attempt 2: NSE historical VIX REST API ────────────────────────────
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
                data = resp.json().get("data", [])
                if data:
                    records = []
                    for row in data:
                        try:
                            d = datetime.strptime(row["EOD_TIMESTAMP"], "%d-%b-%Y").date()
                            v = float(row["EOD_CLOSE_INDEX_VAL"])
                            records.append((d, v))
                        except (KeyError, ValueError):
                            continue
                    if records:
                        s = pd.Series(dict(records))
                        logger.info(f"[VIX] Loaded {len(s)} rows from NSE ({start}→{end})")
                        return s
        except Exception as e:
            logger.warning(f"[VIX] NSE fetch failed: {e}")

        # ── Attempt 3: yfinance ───────────────────────────────────────────────
        try:
            import yfinance as yf
            ticker = yf.Ticker("^INDIAVIX")
            df = ticker.history(
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
            )
            if not df.empty:
                s = df["Close"]
                s.index = s.index.date
                logger.info(f"[VIX] Loaded {len(s)} rows from yfinance ({start}→{end})")
                return s
        except Exception as e:
            logger.warning(f"[VIX] yfinance fetch failed: {e}")

        logger.warning(f"[VIX] All sources failed — using default {DEFAULT_VIX}%")
        return None


# ── Expiry Calendar ────────────────────────────────────────────────────────────

def nearest_weekly_expiry(dt: datetime, derivative: str = "NIFTY") -> datetime:
    """
    Return the nearest weekly expiry date/time on or after dt.
    Uses OptionUtils for expiry weekday mapping.
    """
    # Try to get the correct weekday from OptionUtils
    try:
        exchange_symbol = OptionUtils.get_exchange_symbol(derivative)
        target_weekday = OptionUtils.EXPIRY_WEEKDAY_MAP.get(exchange_symbol, 1)
    except Exception:
        target_weekday = 1

    current = dt.date()
    days_ahead = (target_weekday - current.weekday()) % 7
    if days_ahead == 0 and dt.hour >= 15 and dt.minute >= 30:
        days_ahead = 7  # already expired today
    expiry_date = current + timedelta(days=days_ahead)
    return datetime(expiry_date.year, expiry_date.month, expiry_date.day, 15, 30)


def nearest_monthly_expiry(dt: datetime, derivative: str = "NIFTY") -> datetime:
    """Return the nearest monthly expiry date/time on or after dt."""
    try:
        exchange_symbol = OptionUtils.get_exchange_symbol(derivative)
        target_weekday = OptionUtils.EXPIRY_WEEKDAY_MAP.get(exchange_symbol, 1)
        expiry_dt = OptionUtils.get_monthly_expiry_date(dt.year, dt.month, derivative=exchange_symbol)
        if expiry_dt <= dt:
            # Roll to next month
            nm = dt.month + 1
            ny = dt.year + (1 if nm > 12 else 0)
            nm = ((nm - 1) % 12) + 1
            expiry_dt = OptionUtils.get_monthly_expiry_date(ny, nm, derivative=exchange_symbol)
        return expiry_dt
    except Exception:
        pass

    # Fallback: last Tuesday of the month
    target_weekday = 1
    d = dt.date()
    if d.month == 12:
        last_day = date(d.year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(d.year, d.month + 1, 1) - timedelta(days=1)
    offset = (last_day.weekday() - target_weekday) % 7
    last_exp = last_day - timedelta(days=offset)
    exp_dt = datetime(last_exp.year, last_exp.month, last_exp.day, 15, 30)
    if exp_dt <= dt:
        if d.month >= 11:
            last_day2 = date(d.year + 1, (d.month % 12) + 2, 1) - timedelta(days=1)
        else:
            last_day2 = date(d.year, d.month + 2, 1) - timedelta(days=1)
        offset2 = (last_day2.weekday() - target_weekday) % 7
        last_exp2 = last_day2 - timedelta(days=offset2)
        exp_dt = datetime(last_exp2.year, last_exp2.month, last_exp2.day, 15, 30)
    return exp_dt


# ── Main Resolver ──────────────────────────────────────────────────────────────

class OptionPricer:
    """
    Resolves option OHLCV prices for a given timestamp + spot price.

    Uses state_manager to access broker type and other configuration
    that affects option pricing.
    """

    def __init__(
            self,
            derivative: str = "NIFTY",
            expiry_type: str = "weekly",  # "weekly" | "monthly"
            risk_free: float = RISK_FREE_RATE,
            div_yield: float = DIVIDEND_YIELD,
            broker=None,
            use_vix: bool = True,
    ):
        self.derivative = derivative.upper()
        self.expiry_type = expiry_type
        self.risk_free = risk_free
        self.div_yield = div_yield
        self.use_vix = use_vix  # False → use rolling HV from spot prices
        self._vix = VixCache()
        self._spot_history: list = []  # rolling buffer for HV computation
        self._broker_type = "default"

        if broker is not None:
            self._vix.set_broker(broker)
            self._broker_type = _broker_type(broker)

        # Get additional config from state_manager if available
        try:
            snapshot = state_manager.get_snapshot()
            if snapshot and "derivative" in snapshot:
                # Use the derivative from state if not overridden
                if derivative == "NIFTY" and snapshot["derivative"]:
                    self.derivative = snapshot["derivative"].upper()
        except Exception as e:
            logger.debug(f"[OptionPricer] Failed to get state snapshot: {e}")

    def load_vix(self, start: date, end: date, broker=None) -> None:
        """
        Pre-fetch VIX data for the backtest date range.

        Parameters
        ----------
        start, end : date
            Inclusive date range.
        broker : optional
            If provided, VIX is fetched via the broker's API.
        """
        if not self.use_vix:
            logger.info("[OptionPricer] use_vix=False — skipping VIX fetch; using rolling HV")
            return
        if broker is not None:
            self._vix.set_broker(broker)
            self._broker_type = _broker_type(broker)
        self._vix.ensure_loaded(start, end)

    def push_spot(self, spot_close: float) -> None:
        """
        Feed the latest spot close into the rolling HV buffer.
        Call this once per bar from the replay loop so HV stays current.
        Only used when use_vix=False.
        """
        if not self.use_vix:
            self._spot_history.append(float(spot_close))
            if len(self._spot_history) > HV_LOOKBACK + 5:
                self._spot_history = self._spot_history[-(HV_LOOKBACK + 5):]

    def _get_sigma(self, timestamp: datetime, interval_minutes: int = 2) -> Tuple[float, bool]:
        """
        Return (sigma, is_real) for option pricing.

        When use_vix=True  → uses VixCache
        When use_vix=False → uses rolling_hv() from spot_history buffer
        """
        if self.use_vix:
            s, real = self._vix.get_vix(timestamp)
            return max(s, 0.05), real
        else:
            bars_per_year = int((252 * 375) / max(interval_minutes, 1))
            s = rolling_hv(self._spot_history, bars_per_year=bars_per_year)
            return max(s, 0.05), False

    def resolve(
            self,
            timestamp: datetime,
            spot: float,
            option_type: str,  # "CE" or "PE"
            real_price: Optional[float] = None,
            real_open: Optional[float] = None,
            real_high: Optional[float] = None,
            real_low: Optional[float] = None,
    ) -> Tuple[float, float, float, float, PriceSource]:
        """
        Resolve (open, high, low, close) for the option bar.

        Returns
        -------
        (open, high, low, close, PriceSource)
        """
        strike = atm_strike(spot, self.derivative)

        if self.expiry_type == "weekly":
            expiry_dt = nearest_weekly_expiry(timestamp, self.derivative)
        else:
            expiry_dt = nearest_monthly_expiry(timestamp, self.derivative)

        T = time_to_expiry_years(timestamp, expiry_dt)

        # If all four real OHLC prices are present and positive
        if (real_price is not None and real_price > 0 and
                real_open is not None and real_high is not None and real_low is not None):
            return real_open, real_high, real_low, real_price, PriceSource.REAL

        # Fall back to Black-Scholes
        sigma, _ = self._get_sigma(timestamp)
        sigma = max(sigma, 0.05)  # floor at 5% to avoid degenerate pricing

        close = black_scholes_price(spot, strike, T, self.risk_free, sigma, option_type, self.div_yield)

        # Approximate OHLC from close using typical intraday range heuristic
        minutes_per_bar = 5  # default; overridden by caller if needed
        bar_fraction = minutes_per_bar / (252 * 375)  # fraction of trading year
        bar_sigma = sigma * math.sqrt(bar_fraction)
        spread = close * bar_sigma * 0.5

        open_ = max(0.05, Utils.round_off(close))  # neutral: open ≈ close for synthetic bars
        high = max(close, Utils.round_off(close + spread))
        low = max(0.05, Utils.round_off(close - spread))

        return open_, high, low, close, PriceSource.SYNTHETIC

    def resolve_bar(
            self,
            timestamp: datetime,
            spot_open: float,
            spot_high: float,
            spot_low: float,
            spot_close: float,
            option_type: str,
            real_ohlc: Optional[pd.Series] = None,  # row with open/high/low/close
            minutes_per_bar: int = 5,
    ) -> Dict:
        """
        Full OHLCV bar for one candle.
        Uses spot OHLC to produce option OHLC via BS when real data absent.
        """
        # Strip tz so expiry arithmetic never raises
        if hasattr(timestamp, "tzinfo") and timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)

        strike = atm_strike(spot_close, self.derivative)
        sigma, vix_real = self._get_sigma(timestamp, minutes_per_bar)
        # Feed spot into HV buffer (no-op when use_vix=True)
        self.push_spot(spot_close)

        if self.expiry_type == "weekly":
            expiry_dt = nearest_weekly_expiry(timestamp, self.derivative)
        else:
            expiry_dt = nearest_monthly_expiry(timestamp, self.derivative)

        # Check real data
        if real_ohlc is not None:
            ro = real_ohlc.get("open")
            rh = real_ohlc.get("high")
            rl = real_ohlc.get("low")
            rc = real_ohlc.get("close")
            if all(v is not None and v > 0 for v in [ro, rh, rl, rc]):
                return {
                    "timestamp": timestamp,
                    "open": ro, "high": rh, "low": rl, "close": rc,
                    "strike": strike,
                    "expiry": expiry_dt,
                    "sigma": sigma,
                    "vix_real": vix_real,
                    "source": PriceSource.REAL,
                }

        bar_year_fraction = minutes_per_bar / (252 * 375)
        T_close = time_to_expiry_years(timestamp, expiry_dt)
        T_open = T_close + bar_year_fraction  # open is one bar earlier = more TTE

        c_close = black_scholes_price(spot_close, strike, T_close, self.risk_free, sigma, option_type)
        c_open = black_scholes_price(spot_open, strike, T_open, self.risk_free, sigma, option_type)

        # For high/low, use the appropriate spot price based on option type
        if option_type == "CE":
            c_high = black_scholes_price(
                spot_high, strike, (T_close + T_open) / 2, self.risk_free, sigma, option_type
            )
            c_low = black_scholes_price(
                spot_low, strike, (T_close + T_open) / 2, self.risk_free, sigma, option_type
            )
        else:  # PE - inverse relationship with spot
            c_high = black_scholes_price(
                spot_low, strike, (T_close + T_open) / 2, self.risk_free, sigma, option_type
            )
            c_low = black_scholes_price(
                spot_high, strike, (T_close + T_open) / 2, self.risk_free, sigma, option_type
            )

        return {
            "timestamp": timestamp,
            "open": max(0.05, c_open),
            "high": max(c_open, c_close, c_high),
            "low": max(0.05, min(c_open, c_close, c_low)),
            "close": max(0.05, c_close),
            "strike": strike,
            "expiry": expiry_dt,
            "sigma": sigma,
            "vix_real": vix_real,
            "source": PriceSource.SYNTHETIC,
        }

    def get_option_symbol(
            self,
            strike: float,
            option_type: str,
            expiry_offset: int = 0
    ) -> Optional[str]:
        """
        Generate a broker-ready option symbol.

        Uses OptionUtils with the stored broker type to generate
        the correct symbol format for the current broker.

        Args:
            strike: Strike price
            option_type: "CE" or "PE"
            expiry_offset: Number of expiries ahead (0 = current)

        Returns:
            Option symbol string or None if generation fails
        """
        try:
            return OptionUtils.build_option_symbol(
                derivative=self.derivative,
                strike=strike,
                option_type=option_type,
                expiry_type=self.expiry_type,
                broker_type=self._broker_type,
                num_expiries_plus=expiry_offset
            )
        except Exception as e:
            logger.error(f"[OptionPricer] Failed to generate option symbol: {e}")
            return None

    def cleanup(self):
        """Clean up resources."""
        try:
            self._spot_history.clear()
            logger.debug("[OptionPricer] Cleanup completed")
        except Exception as e:
            logger.error(f"[OptionPricer] Cleanup error: {e}", exc_info=True)


# ── Convenience factory function ───────────────────────────────────────────────

def create_pricer_from_state(
        derivative: Optional[str] = None,
        expiry_type: str = "weekly",
        broker=None,
        use_vix: bool = True
) -> OptionPricer:
    """
    Create an OptionPricer instance using configuration from the trade state.

    This is a convenience function that uses state_manager to get
    default values from the current trade state.

    Args:
        derivative: Override derivative name (defaults to state.derivative)
        expiry_type: "weekly" or "monthly"
        broker: Broker instance for VIX fetching
        use_vix: Whether to use VIX for volatility

    Returns:
        Configured OptionPricer instance
    """
    try:
        snapshot = state_manager.get_snapshot()

        if derivative is None and snapshot and "derivative" in snapshot:
            derivative = snapshot["derivative"]

        if derivative is None:
            derivative = "NIFTY"

        return OptionPricer(
            derivative=derivative,
            expiry_type=expiry_type,
            broker=broker,
            use_vix=use_vix
        )

    except Exception as e:
        logger.error(f"[create_pricer_from_state] Failed: {e}", exc_info=True)
        return OptionPricer(
            derivative=derivative or "NIFTY",
            expiry_type=expiry_type,
            broker=broker,
            use_vix=use_vix
        )