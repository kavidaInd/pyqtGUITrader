# OptionSymbolBuilder.py (fixed)
"""
Utils/OptionSymbolBuilder.py
============================
Pure date-and-strike mathematics for NSE/BSE option contracts.

DESIGN PRINCIPLE
----------------
This module is BROKER-AGNOSTIC.  It produces *core* option parameters
(expiry date, strike, option type, date-code string) but does NOT format a
final tradeable symbol string.  That last step belongs to each broker's
``build_option_symbol()`` method, because every broker API accepts a
different format:

    Broker          Format expected
    ──────────────  ────────────────────────────────────────────────────────
    Fyers           NSE:NIFTY25031825000CE   (NSE: prefix + compact string)
    Zerodha         NFO:NIFTY2531825000CE    (NFO: prefix + compact string)
    Shoonya         NFO|NIFTY2531825000CE    (NFO| prefix + compact string)
    FlatTrade       NFO|NIFTY2531825000CE    (same as Shoonya)
    AliceBlue       NFO:NIFTY2531825000CE    (NFO: prefix + compact string)
    AngelOne        NIFTY2531825000CE        (no prefix, numeric token lookup)
    Dhan            numeric security_id      (instrument master lookup)
    Upstox          NSE_FO|<ISIN>            (instrument_key lookup)
PUBLIC API
----------
``OptionSymbolBuilder.get_option_params(...)``
    Returns an ``OptionParams`` dataclass with every piece of information a
    broker needs to build its own symbol string or look up an instrument ID.

``OptionSymbolBuilder.compact_core(params)``
    Returns the NSE compact core string (no prefix), e.g.
    ``"NIFTY2531825000CE"`` or ``"NIFTY25MAR25000CE"`` for monthly.
    Brokers that only need a prefix prepended can call this directly.

``OptionSymbolBuilder.get_all_option_params(...)``
    Returns a list of ``OptionParams`` objects covering ITM → ATM → OTM
    strikes for building an option chain.

EXPIRY RULES (SEBI circular effective November 20, 2024)
---------------------------------------------------------
    NSE  → only NIFTY 50 retains weekly expiry.
    BSE  → only SENSEX retains weekly expiry.
    BANKNIFTY / FINNIFTY / MIDCPNIFTY → monthly only from Nov 20, 2024.

LOT SIZES (NSE Circular 176/2025, effective January 2026)
---------------------------------------------------------
    NIFTY=65, BANKNIFTY=30, FINNIFTY=60, MIDCPNIFTY=120, SENSEX=20.
"""

import calendar
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# ── Canonical symbol aliases ─────────────────────────────────────────────────

SYMBOL_MAP: Dict[str, str] = {
    "NIFTY50": "NIFTY",
    "NIFTY50-INDEX": "NIFTY",
    "FINNIFTY": "FINNIFTY",
    "FINNIFTY-INDEX": "FINNIFTY",
    "NIFTYBANK": "BANKNIFTY",
    "NIFTYBANK-INDEX": "BANKNIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "SENSEX": "SENSEX",
    "SENSEX-INDEX": "SENSEX",
    "MIDCPNIFTY": "MIDCPNIFTY",
    "MIDCPNIFTY-INDEX": "MIDCPNIFTY",
}

# ── Strike-rounding multiplier (NOT lot size) ────────────────────────────────

MULTIPLIER_MAP: Dict[str, int] = {
    "NIFTY": 50,
    "FINNIFTY": 50,
    "BANKNIFTY": 100,
    "SENSEX": 100,
    "MIDCPNIFTY": 25,
}

# ── Lot sizes (Jan 2026 SEBI revision) ──────────────────────────────────────

LOT_SIZE_MAP: Dict[str, int] = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "FINNIFTY": 60,
    "MIDCPNIFTY": 120,
    "SENSEX": 20,
}

# ── Expiry type per index ────────────────────────────────────────────────────

EXPIRY_TYPE_MAP: Dict[str, str] = {
    "NIFTY": "weekly",
    "SENSEX": "weekly",
    "BANKNIFTY": "monthly",
    "FINNIFTY": "monthly",
    "MIDCPNIFTY": "monthly",
}

# ── Weekly expiry weekday (NSE→Tuesday=1, BSE→Thursday=3) ───────────────────

EXPIRY_WEEKDAY_MAP: Dict[str, int] = {
    "NIFTY": 1,       # Tuesday
    "BANKNIFTY": 1,   # Tuesday (monthly)
    "FINNIFTY": 1,    # Tuesday (monthly)
    "MIDCPNIFTY": 1,  # Tuesday (monthly)
    "SENSEX": 3,      # Thursday
}

# ── Date-code look-up tables ─────────────────────────────────────────────────

WEEKLY_MONTH_CODES: Dict[int, str] = {
    1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
    7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D",
}

MONTHLY_MONTH_CODES: Dict[int, str] = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class OptionParams:
    """
    All parameters needed by any broker to construct its option symbol/order.

    Fields
    ------
    underlying  : Canonical index name, e.g. "NIFTY", "BANKNIFTY".
    strike      : Strike price as int, e.g. 25000.
    option_type : "CE" or "PE".
    expiry_date : The expiry date as a ``datetime`` object.
    is_monthly  : True if this is a monthly expiry contract.
    year2d      : Two-digit year string, e.g. "25".
    month_code_weekly  : Single-char month code for weekly format, e.g. "3".
    month_code_monthly : Three-letter month code, e.g. "MAR".
    day_str     : Zero-padded day string, e.g. "18".
    compact_core: The NSE compact symbol core (no broker prefix),
                  e.g. "NIFTY2531825000CE" or "NIFTY25MAR25000CE".
    expiry_str_ddmmmyyyy: Human-readable, e.g. "18MAR2025".
    """
    underlying: str
    strike: int
    option_type: str           # "CE" or "PE"
    expiry_date: datetime
    is_monthly: bool

    # Derived convenience fields (populated automatically)
    year2d: str = field(init=False)
    month_code_weekly: str = field(init=False)
    month_code_monthly: str = field(init=False)
    day_str: str = field(init=False)
    compact_core: str = field(init=False)
    expiry_str_ddmmmyyyy: str = field(init=False)  # "18MAR2025"    (generic)

    def __post_init__(self):
        self.year2d = str(self.expiry_date.year)[2:]
        self.month_code_weekly = WEEKLY_MONTH_CODES.get(
            self.expiry_date.month, str(self.expiry_date.month)
        )
        self.month_code_monthly = MONTHLY_MONTH_CODES.get(
            self.expiry_date.month, "JAN"
        )
        self.day_str = f"{self.expiry_date.day:02d}"

        if self.is_monthly:
            self.compact_core = (
                f"{self.underlying}"
                f"{self.year2d}"
                f"{self.month_code_monthly}"
                f"{self.strike}"
                f"{self.option_type}"
            )
        else:
            self.compact_core = (
                f"{self.underlying}"
                f"{self.year2d}"
                f"{self.month_code_weekly}"
                f"{self.day_str}"
                f"{self.strike}"
                f"{self.option_type}"
            )

        self.expiry_str_breeze = (
            f"{self.day_str}-{self.month_code_monthly}-20{self.year2d}"
        )
        self.expiry_str_ddmmmyyyy = (
            f"{self.day_str}{self.month_code_monthly}20{self.year2d}"
        )


# ── Core builder ─────────────────────────────────────────────────────────────

class OptionSymbolBuilder:
    """
    Broker-agnostic option parameter calculator.

    All methods are class-methods so the class never needs to be
    instantiated — callers use ``OptionSymbolBuilder.get_option_params(...)``.
    """

    # ── Public helpers ────────────────────────────────────────────────────────

    @classmethod
    def canonical(cls, symbol: str) -> str:
        """Resolve any derivative alias to the canonical exchange symbol."""
        return SYMBOL_MAP.get(symbol, symbol)

    @classmethod
    def multiplier(cls, symbol: str) -> int:
        """Strike-rounding interval for the given derivative."""
        return MULTIPLIER_MAP.get(cls.canonical(symbol), 50)

    @classmethod
    def lot_size(cls, symbol: str) -> int:
        """Lot size for the given derivative (Jan 2026 values)."""
        return LOT_SIZE_MAP.get(cls.canonical(symbol), 65)

    @classmethod
    def has_weekly_expiry(cls, symbol: str) -> bool:
        """True only if the index has weekly option contracts."""
        return EXPIRY_TYPE_MAP.get(cls.canonical(symbol), "monthly") == "weekly"

    @classmethod
    def nearest_strike(cls, price: float, symbol: str) -> int:
        """Round *price* to the nearest valid strike for *symbol*."""
        mult = cls.multiplier(symbol)
        if mult <= 0:
            return int(round(price))
        base = int(round(price))
        rem = base % mult
        if rem < mult / 2:
            return base - rem
        return base + (mult - rem)

    # ── Expiry date calculation ───────────────────────────────────────────────

    @classmethod
    def _last_weekday_of_month(cls, year: int, month: int, weekday: int) -> datetime:
        """Return the last occurrence of *weekday* in the given month."""
        last = calendar.monthrange(year, month)[1]
        dt = datetime(year, month, last)
        while dt.weekday() != weekday:
            dt -= timedelta(days=1)
        return dt

    @classmethod
    def _adjust_for_holiday(cls, dt: datetime) -> datetime:
        """Move *dt* backward until it is not a market holiday."""
        try:
            from Utils.common import is_holiday
            for _ in range(10):
                if not is_holiday(dt):
                    break
                dt -= timedelta(days=1)
        except ImportError:
            pass  # No holiday calendar available — use raw date
        return dt

    @classmethod
    def monthly_expiry(cls, year: int, month: int, underlying: str) -> datetime:
        """Return the monthly expiry date for *underlying* in the given month."""
        sym = cls.canonical(underlying)
        weekday = EXPIRY_WEEKDAY_MAP.get(sym, 1)
        dt = cls._last_weekday_of_month(year, month, weekday)
        return cls._adjust_for_holiday(dt)

    @classmethod
    def _next_monthly_expiry(cls, underlying: str, ref: Optional[datetime] = None) -> datetime:
        """Return the next upcoming monthly expiry on or after *ref*."""
        ref = ref or datetime.now()
        sym = cls.canonical(underlying)
        exp = cls.monthly_expiry(ref.year, ref.month, sym)
        if exp.date() < ref.date():
            # This month's expiry already passed — go to next month
            nm = ref.month + 1
            ny = ref.year + (1 if nm > 12 else 0)
            nm = ((nm - 1) % 12) + 1
            exp = cls.monthly_expiry(ny, nm, sym)
        return exp

    @classmethod
    def _next_weekly_expiry(cls, underlying: str, ref: Optional[datetime] = None) -> datetime:
        """Return the next upcoming weekly expiry on or after *ref*."""
        ref = ref or datetime.now()
        sym = cls.canonical(underlying)
        weekday = EXPIRY_WEEKDAY_MAP.get(sym, 1)
        days_ahead = (weekday - ref.weekday() + 7) % 7
        dt = ref + timedelta(days=days_ahead)
        return cls._adjust_for_holiday(dt)

    @classmethod
    def expiry_date(cls, underlying: str, weeks_offset: int = 0) -> datetime:
        """
        Return the expiry date for *underlying* with an optional week offset.

        For monthly-only indices, ``weeks_offset`` is interpreted as a
        month offset (0 = current month, 1 = next month, …).

        For weekly-capable indices (NIFTY / SENSEX):
            weeks_offset=0 → nearest upcoming weekly expiry
            weeks_offset=1 → the weekly expiry after that, etc.
            If the target date coincides with the monthly expiry, the
            monthly date-code format will be used automatically.
        """
        if weeks_offset < 0:
            logger.warning(f"Negative weeks_offset {weeks_offset} - using 0")
            weeks_offset = 0
        if weeks_offset > 52:
            logger.warning(f"weeks_offset {weeks_offset} > 52 (1 year) - limiting to 52")
            weeks_offset = 52

        sym = cls.canonical(underlying)
        if not cls.has_weekly_expiry(sym):
            # Monthly-only index
            ref = datetime.now()
            target_month = ref.month + weeks_offset
            target_year = ref.year + (target_month - 1) // 12
            target_month = ((target_month - 1) % 12) + 1
            return cls.monthly_expiry(target_year, target_month, sym)
        else:
            # Weekly-capable index
            base = cls._next_weekly_expiry(sym)
            if weeks_offset > 0:
                base = base + timedelta(weeks=weeks_offset)
                base = cls._adjust_for_holiday(base)
            return base

    @classmethod
    def _is_monthly_expiry(cls, dt: datetime, underlying: str) -> bool:
        """True if *dt* is the monthly expiry date for *underlying*."""
        sym = cls.canonical(underlying)
        monthly = cls.monthly_expiry(dt.year, dt.month, sym)
        return dt.date() == monthly.date()

    # ── Main public factory ───────────────────────────────────────────────────

    @classmethod
    def get_option_params(
        cls,
        underlying: str,
        spot_price: float,
        option_type: str,
        weeks_offset: int = 0,
        lookback_strikes: int = 0,
    ) -> Optional["OptionParams"]:
        """
        Compute all option parameters a broker needs to build its symbol.

        Parameters
        ----------
        underlying      : Derivative name in any recognised format.
        spot_price      : Current index spot price.
        option_type     : "CE" or "PE".
        weeks_offset    : Which expiry week/month (0 = current).
        lookback_strikes: Number of strikes to move away from ATM.
                          For CE: Positive = OTM, Negative = ITM.
                          For PE: Positive = ITM, Negative = OTM.

        Returns
        -------
        ``OptionParams`` or ``None`` on error.
        """
        try:
            sym = cls.canonical(underlying)
            mult = cls.multiplier(sym)
            opt = option_type.upper()
            if opt not in ("CE", "PE"):
                logger.warning(f"[OptionSymbolBuilder] Invalid option_type={option_type!r}, using CE")
                opt = "CE"

            atm = cls.nearest_strike(spot_price, sym)
            if opt == "CE":
                strike = atm + lookback_strikes * mult
            else:
                # For PE: Positive lookback = ITM (higher strike), Negative = OTM (lower strike)
                strike = atm - lookback_strikes * mult

            exp = cls.expiry_date(sym, weeks_offset)
            is_monthly = (
                not cls.has_weekly_expiry(sym)
                or cls._is_monthly_expiry(exp, sym)
            )
            return OptionParams(
                underlying=sym,
                strike=int(strike),
                option_type=opt,
                expiry_date=exp,
                is_monthly=is_monthly,
            )
        except Exception as e:
            logger.error(f"[OptionSymbolBuilder.get_option_params] {e}", exc_info=True)
            return None

    @classmethod
    def get_all_option_params(
        cls,
        underlying: str,
        spot_price: float,
        option_type: str,
        weeks_offset: int = 0,
        itm: int = 5,
        otm: int = 5,
    ) -> List["OptionParams"]:
        """
        Return a list of ``OptionParams`` for an option chain.

        Covers *itm* strikes below ATM through ATM through *otm* strikes
        above ATM (always relative to the canonical direction for the
        option_type — CE goes higher for OTM, PE goes lower).

        Parameters
        ----------
        itm : Number of in-the-money strikes to include.
        otm : Number of out-of-the-money strikes to include.

        Returns a list of len(itm + 1 + otm) OptionParams objects.
        """
        results = []
        try:
            sym = cls.canonical(underlying)
            mult = cls.multiplier(sym)
            opt = option_type.upper()
            if opt not in ("CE", "PE"):
                opt = "CE"

            atm = cls.nearest_strike(spot_price, sym)
            exp = cls.expiry_date(sym, weeks_offset)
            is_monthly = (
                not cls.has_weekly_expiry(sym)
                or cls._is_monthly_expiry(exp, sym)
            )

            low_strike = atm - itm * mult
            for i in range(itm + 1 + otm):
                strike = low_strike + i * mult
                try:
                    results.append(OptionParams(
                        underlying=sym,
                        strike=int(strike),
                        option_type=opt,
                        expiry_date=exp,
                        is_monthly=is_monthly,
                    ))
                except Exception as inner:
                    logger.warning(f"[get_all_option_params] Strike {strike}: {inner}")
        except Exception as e:
            logger.error(f"[OptionSymbolBuilder.get_all_option_params] {e}", exc_info=True)
        return results