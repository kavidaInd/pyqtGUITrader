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
  The India VIX historical series is fetched from NSE's public CSV endpoint.
  A fallback constant (15%) is used when the network is unavailable.

Each resolved price carries a PriceSource enum so the GUI can render
synthetic bars in a distinct colour and show a disclaimer.
"""

from __future__ import annotations

import logging
import math
import threading
from datetime import date, datetime, timedelta
from enum import Enum
from functools import lru_cache
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
RISK_FREE_RATE = 0.065  # 6.5% — India 91-day T-bill approximate
DIVIDEND_YIELD = 0.0  # indices pay no dividend
DEFAULT_VIX = 15.0  # fallback when VIX data unavailable (%)
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

        return max(0.0, round(price, 2))

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
    delta = (expiry_dt - current_dt).total_seconds()
    if delta <= 0:
        return MIN_TIME_TO_EXPIRY
    # Convert seconds → trading-year fraction (≈252 days/year, 6.25 hours/day)
    trading_seconds_per_year = 252 * 6.25 * 3600
    return max(delta / trading_seconds_per_year, MIN_TIME_TO_EXPIRY)


# ── VIX Data ───────────────────────────────────────────────────────────────────

class VixCache:
    """
    Fetches and caches India VIX daily close values.

    Primary source : NSE historical VIX API
    Secondary source: yfinance ^INDIAVIX  (if nse fails)
    Fallback        : DEFAULT_VIX constant

    Thread-safe; fetched once per session.
    """

    def __init__(self):
        self._data: Optional[pd.Series] = None  # index = date, value = VIX %
        self._lock = threading.Lock()
        self._fetched = False

    def ensure_loaded(self, start: date, end: date):
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
            return DEFAULT_VIX / 100.0, False

        target = dt.date()
        # Look for exact date, then walk backwards up to 5 trading days
        for delta in range(6):
            candidate = target - timedelta(days=delta)
            if candidate in self._data.index:
                return float(self._data[candidate]) / 100.0, True
        return DEFAULT_VIX / 100.0, False

    @staticmethod
    def _fetch(start: date, end: date) -> Optional[pd.Series]:
        # ── Attempt 1: NSE historical VIX ────────────────────────────────────
        try:
            import requests
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Referer": "https://www.nseindia.com/",
            }
            session = requests.Session()
            # Prime cookies
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

        # ── Attempt 2: yfinance ───────────────────────────────────────────────
        try:
            import yfinance as yf
            ticker = yf.Ticker("^INDIAVIX")
            df = ticker.history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat())
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
    NSE weekly options expire on Thursdays at 15:30 IST.
    BANKNIFTY moves to Wednesday for monthly on last week.
    For simplicity: Thursdays for all (closest approximation).
    """
    target_weekday = 3  # Thursday = 3 (Monday = 0)
    current = dt.date()
    days_ahead = (target_weekday - current.weekday()) % 7
    if days_ahead == 0 and dt.hour >= 15 and dt.minute >= 30:
        days_ahead = 7  # already expired today
    expiry_date = current + timedelta(days=days_ahead)
    return datetime(expiry_date.year, expiry_date.month, expiry_date.day, 15, 30)


def nearest_monthly_expiry(dt: datetime) -> datetime:
    """Last Thursday of the current (or next) month at 15:30."""
    d = dt.date()
    # Find last Thursday of this month
    last_day = date(d.year + (d.month // 12), (d.month % 12) + 1, 1) - timedelta(days=1)
    offset = (last_day.weekday() - 3) % 7
    last_thu = last_day - timedelta(days=offset)
    exp_dt = datetime(last_thu.year, last_thu.month, last_thu.day, 15, 30)
    if exp_dt <= dt:
        # Move to next month
        if d.month == 12:
            last_day2 = date(d.year + 1, 2, 1) - timedelta(days=1)
        else:
            last_day2 = date(d.year, d.month + 2, 1) - timedelta(days=1)
        offset2 = (last_day2.weekday() - 3) % 7
        last_thu2 = last_day2 - timedelta(days=offset2)
        exp_dt = datetime(last_thu2.year, last_thu2.month, last_thu2.day, 15, 30)
    return exp_dt


# ── Main Resolver ──────────────────────────────────────────────────────────────

class OptionPricer:
    """
    Resolves option OHLCV prices for a given timestamp + spot price.

    Usage
    -----
    pricer = OptionPricer(derivative="NIFTY", expiry_type="weekly")
    pricer.load_vix(start_date, end_date)

    price, source = pricer.resolve(
        timestamp=datetime(2024, 1, 15, 10, 0),
        spot=21800.0,
        option_type="CE",
        real_price=None,   # None → use BS; float → use real
    )
    """

    def __init__(
            self,
            derivative: str = "NIFTY",
            expiry_type: str = "weekly",  # "weekly" | "monthly"
            risk_free: float = RISK_FREE_RATE,
            div_yield: float = DIVIDEND_YIELD,
    ):
        self.derivative = derivative.upper()
        self.expiry_type = expiry_type
        self.risk_free = risk_free
        self.div_yield = div_yield
        self._vix = VixCache()

    def load_vix(self, start: date, end: date):
        """Pre-fetch VIX data for the backtest date range."""
        self._vix.ensure_loaded(start, end)

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
            expiry_dt = nearest_monthly_expiry(timestamp)

        T = time_to_expiry_years(timestamp, expiry_dt)

        # If all four real OHLC prices are present and positive
        if (real_price is not None and real_price > 0 and
                real_open is not None and real_high is not None and real_low is not None):
            return real_open, real_high, real_low, real_price, PriceSource.REAL

        # Fall back to Black-Scholes
        sigma, _ = self._vix.get_vix(timestamp)
        sigma = max(sigma, 0.05)  # floor at 5% to avoid degenerate pricing

        close = black_scholes_price(spot, strike, T, self.risk_free, sigma, option_type, self.div_yield)

        # Approximate OHLC from close using typical intraday range heuristic
        # (VIX-derived expected move over one bar)
        minutes_per_bar = 5  # default; overridden by caller if needed
        bar_fraction = minutes_per_bar / (252 * 375)  # fraction of trading year
        bar_sigma = sigma * math.sqrt(bar_fraction)
        spread = close * bar_sigma * 0.5

        open_ = max(0.05, round(close * (1 + (0.3 - 0.6) * bar_sigma), 2))
        high = max(close, round(close + spread, 2))
        low = max(0.05, round(close - spread, 2))

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
        strike = atm_strike(spot_close, self.derivative)
        sigma, vix_real = self._vix.get_vix(timestamp)
        sigma = max(sigma, 0.05)

        if self.expiry_type == "weekly":
            expiry_dt = nearest_weekly_expiry(timestamp, self.derivative)
        else:
            expiry_dt = nearest_monthly_expiry(timestamp)

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

        # Synthetic pricing for each OHLC component using the corresponding spot
        T_close = time_to_expiry_years(timestamp, expiry_dt)
        T_open = min(T_close + minutes_per_bar / (252 * 375), T_close + 0.001)

        c_close = black_scholes_price(spot_close, strike, T_close, self.risk_free, sigma, option_type)
        c_open = black_scholes_price(spot_open, strike, T_open, self.risk_free, sigma, option_type)
        c_high = black_scholes_price(
            spot_high if option_type == "CE" else spot_low,
            strike, (T_close + T_open) / 2, self.risk_free, sigma, option_type
        )
        c_low = black_scholes_price(
            spot_low if option_type == "CE" else spot_high,
            strike, (T_close + T_open) / 2, self.risk_free, sigma, option_type
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
