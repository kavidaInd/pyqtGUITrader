# OptionUtils.py - All option-related methods consolidated here
# Updated: Full broker-aware symbol generation and interval translation

import calendar
import logging.handlers
from datetime import datetime, timedelta
from typing import Optional, List, Any, Dict, Tuple

import BaseEnums
from Utils.common import (
    is_holiday, is_market_closed_for_the_day, get_market_end_time,
    get_time_of_day, to_date_str, get_epoch
)

logger = logging.getLogger(__name__)

# ── Broker identifier constants (mirrors BrokerFactory.BrokerType) ─────────────
BROKER_FYERS = "fyers"
BROKER_ZERODHA = "zerodha"
BROKER_DHAN = "dhan"
BROKER_ANGELONE = "angelone"
BROKER_UPSTOX = "upstox"
BROKER_SHOONYA = "shoonya"
BROKER_KOTAK = "kotak"
BROKER_ICICI = "icici"
BROKER_ALICEBLUE = "aliceblue"
BROKER_FLATTRADE = "flattrade"


class OptionUtils:
    """All option-related methods consolidated here.

    FEATURE 6: Added helper methods for Multi-Timeframe Filter.
    BROKER UPDATE: Full broker-aware symbol and interval translation added.
    """

    SYMBOL_MAP = {
        "NIFTY50": "NIFTY",
        "NIFTY50-INDEX": "NIFTY",
        "FINNIFTY": "FINNIFTY",
        "FINNIFTY-INDEX": "FINNIFTY",
        "NIFTYBANK": "BANKNIFTY",
        "NIFTYBANK-INDEX": "BANKNIFTY",
        "SENSEX": "SENSEX",
        "SENSEX-INDEX": "SENSEX",
        "MIDCPNIFTY": "MIDCPNIFTY",
        "MIDCPNIFTY-INDEX": "MIDCPNIFTY"
    }

    MULTIPLIER_MAP = {
        "NIFTY": 50,
        "FINNIFTY": 50,
        "BANKNIFTY": 100,
        "SENSEX": 100,
        "MIDCPNIFTY": 25
    }

    # Month codes for weekly options: 1-9, O=Oct, N=Nov, D=Dec
    WEEKLY_MONTH_CODES = {
        1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
        7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D"
    }

    # Month codes for monthly options: Three-letter month code
    MONTHLY_MONTH_CODES = {
        1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
        7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
    }

    # NSE circular effective September 2, 2025:
    # All NSE indices now expire Tuesday; SENSEX (BSE) on Thursday.
    EXPIRY_WEEKDAY_MAP = {
        "NIFTY": 1,  # Tuesday
        "BANKNIFTY": 1,  # Tuesday
        "FINNIFTY": 1,  # Tuesday
        "MIDCPNIFTY": 1,  # Tuesday
        "SENSEX": 3  # Thursday
    }

    # ── Index symbol maps per broker ────────────────────────────────────────────
    # Key = canonical exchange symbol (NIFTY / BANKNIFTY / FINNIFTY / MIDCPNIFTY / SENSEX)
    # Value = string the broker's API expects for history calls

    _INDEX_SYMBOL_MAP: Dict[str, Dict[str, str]] = {
        BROKER_FYERS: {
            "NIFTY": "NSE:NIFTY50-INDEX",
            "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
            "FINNIFTY": "NSE:FINNIFTY-INDEX",
            "MIDCPNIFTY": "NSE:MIDCPNIFTY-INDEX",
            "SENSEX": "BSE:SENSEX-INDEX",
        },
        BROKER_ZERODHA: {
            "NIFTY": "NSE:NIFTY 50",
            "BANKNIFTY": "NSE:NIFTY BANK",
            "FINNIFTY": "NSE:FINNIFTY",
            "MIDCPNIFTY": "NSE:MIDCPNIFTY",
            "SENSEX": "BSE:SENSEX",
        },
        BROKER_DHAN: {
            "NIFTY": "NIFTY",
            "BANKNIFTY": "BANKNIFTY",
            "FINNIFTY": "FINNIFTY",
            "MIDCPNIFTY": "MIDCPNIFTY",
            "SENSEX": "SENSEX",
        },
        BROKER_ANGELONE: {
            "NIFTY": "NIFTY",
            "BANKNIFTY": "BANKNIFTY",
            "FINNIFTY": "FINNIFTY",
            "MIDCPNIFTY": "MIDCPNIFTY",
            "SENSEX": "SENSEX",
        },
        BROKER_UPSTOX: {
            "NIFTY": "NSE_INDEX|Nifty 50",
            "BANKNIFTY": "NSE_INDEX|Nifty Bank",
            "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
            "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
            "SENSEX": "BSE_INDEX|SENSEX",
        },
        BROKER_SHOONYA: {
            "NIFTY": "NSE|NIFTY-INDEX",
            "BANKNIFTY": "NSE|BANKNIFTY-INDEX",
            "FINNIFTY": "NSE|FINNIFTY-INDEX",
            "MIDCPNIFTY": "NSE|MIDCPNIFTY-INDEX",
            "SENSEX": "BSE|SENSEX-INDEX",
        },
        BROKER_FLATTRADE: {
            "NIFTY": "NSE|NIFTY-INDEX",
            "BANKNIFTY": "NSE|BANKNIFTY-INDEX",
            "FINNIFTY": "NSE|FINNIFTY-INDEX",
            "MIDCPNIFTY": "NSE|MIDCPNIFTY-INDEX",
            "SENSEX": "BSE|SENSEX-INDEX",
        },
        BROKER_ICICI: {
            "NIFTY": "NIFTY",
            "BANKNIFTY": "BANKNIFTY",
            "FINNIFTY": "FINNIFTY",
            "MIDCPNIFTY": "MIDCPNIFTY",
            "SENSEX": "SENSEX",
        },
    }

    # ── Option symbol prefix per broker ─────────────────────────────────────────
    _OPTION_PREFIX: Dict[str, str] = {
        BROKER_FYERS: "NSE:",
        BROKER_ZERODHA: "NFO:",
        BROKER_DHAN: "",
        BROKER_ANGELONE: "",
        BROKER_UPSTOX: "NSE_FO|",
        BROKER_SHOONYA: "NFO|",
        BROKER_FLATTRADE: "NFO|",
        BROKER_ICICI: "",
        BROKER_KOTAK: "",
        BROKER_ALICEBLUE: "",
    }

    # ── Interval translation maps ────────────────────────────────────────────────
    _INTERVAL_MAP: Dict[str, Dict[str, str]] = {
        BROKER_FYERS: {
            "1": "1", "2": "2", "3": "3", "5": "5", "10": "10",
            "15": "15", "20": "20", "30": "30", "60": "60",
            "120": "120", "240": "240", "D": "D", "W": "W", "M": "M",
        },
        BROKER_ZERODHA: {
            "1": "minute",
            "3": "3minute",
            "5": "5minute",
            "10": "10minute",
            "15": "15minute",
            "30": "30minute",
            "60": "60minute",
            "D": "day",
        },
        BROKER_DHAN: {
            "1": "1",
            "2": "5",
            "3": "5",
            "5": "5",
            "10": "15",
            "15": "15",
            "25": "25",
            "30": "60",
            "60": "60",
            "D": "D",
        },
        BROKER_ANGELONE: {
            "1": "ONE_MINUTE",
            "3": "THREE_MINUTE",
            "5": "FIVE_MINUTE",
            "10": "TEN_MINUTE",
            "15": "FIFTEEN_MINUTE",
            "30": "THIRTY_MINUTE",
            "60": "ONE_HOUR",
            "D": "ONE_DAY",
        },
        BROKER_UPSTOX: {
            "1": "1minute",
            "2": "2minute",
            "3": "3minute",
            "5": "5minute",
            "10": "10minute",
            "15": "15minute",
            "30": "30minute",
            "60": "1hour",
            "120": "2hour",
            "240": "4hour",
            "D": "1day",
            "W": "1week",
            "M": "1month",
        },
        BROKER_SHOONYA: {
            "1": "1", "3": "3", "5": "5", "10": "10",
            "15": "15", "30": "30", "60": "60",
            "120": "120", "240": "240", "D": "D", "W": "W",
        },
        BROKER_FLATTRADE: {
            "1": "1", "3": "3", "5": "5", "10": "10",
            "15": "15", "30": "30", "60": "60",
            "120": "120", "240": "240", "D": "D", "W": "W",
        },
        BROKER_ICICI: {
            "1": "1minute",
            "5": "5minute",
            "10": "10minute",
            "30": "30minute",
            "60": "1hour",
            "D": "1day",
            "2": "5minute",
            "3": "5minute",
            "15": "30minute",
        },
    }

    # ==================================================================
    # FEATURE 6: Multi-Timeframe Filter helpers
    # ==================================================================

    MTF_TIMEFRAMES = ["1", "5", "15"]
    MTF_REQUIRED_BARS = {"1": 100, "5": 100, "15": 100}
    MTF_HISTORY_DAYS = {"1": 2, "5": 5, "15": 15}

    # ==========================================================================
    # Broker-aware symbol translation
    # ==========================================================================

    @classmethod
    def get_index_symbol_for_broker(cls, derivative: str, broker_type: str) -> str:
        """Translate a canonical derivative name to the symbol string expected by a specific broker."""
        try:
            canonical = cls.get_exchange_symbol(derivative)
            broker_map = cls._INDEX_SYMBOL_MAP.get(broker_type.lower(), {})
            return broker_map.get(canonical, canonical)
        except Exception as e:
            logger.error(f"[get_index_symbol_for_broker] Failed for {derivative}/{broker_type}: {e}", exc_info=True)
            return derivative

    @classmethod
    def get_option_symbol_for_broker(cls, core_symbol: str, broker_type: str) -> str:
        """Add the exchange prefix required by the given broker to a core option symbol string."""
        try:
            if not core_symbol:
                return core_symbol
            prefix = cls._OPTION_PREFIX.get(broker_type.lower(), "")
            return f"{prefix}{core_symbol}"
        except Exception as e:
            logger.error(f"[get_option_symbol_for_broker] Failed for {core_symbol}/{broker_type}: {e}", exc_info=True)
            return core_symbol

    @classmethod
    def translate_interval(cls, interval: str, broker_type: str) -> str:
        """Translate the app's canonical interval string to the format expected by the given broker."""
        try:
            broker_map = cls._INTERVAL_MAP.get(broker_type.lower(), {})
            return broker_map.get(str(interval), str(interval))
        except Exception as e:
            logger.error(f"[translate_interval] Failed for {interval}/{broker_type}: {e}", exc_info=True)
            return str(interval)

    @classmethod
    def get_supported_intervals(cls, broker_type: str) -> List[str]:
        """Return the list of canonical interval strings supported by the given broker."""
        _NO_HISTORY = {BROKER_KOTAK, BROKER_ALICEBLUE}
        if broker_type.lower() in _NO_HISTORY:
            return []

        broker_map = cls._INTERVAL_MAP.get(broker_type.lower(), {})
        seen = set()
        result = []
        for canonical, broker_val in broker_map.items():
            if broker_val not in seen:
                seen.add(broker_val)
                result.append(canonical)
        if not result:
            result = ["1", "5", "15", "30", "60", "D"]
        return result

    @classmethod
    def build_option_symbol(
            cls,
            derivative: str,
            strike: Any,
            option_type: str,
            expiry_type: str = "weekly",
            broker_type: Optional[str] = None,
            num_expiries_plus: int = 0,
    ) -> Optional[str]:
        """High-level convenience method: build a complete, broker-ready option symbol in one call."""
        try:
            exchange_symbol = cls.get_exchange_symbol(derivative)

            if expiry_type == "monthly":
                core = cls.prepare_monthly_expiry_symbol(
                    exchange_symbol, strike, option_type, num_expiries_plus
                )
            else:
                core = cls.prepare_weekly_options_symbol(
                    exchange_symbol, strike, option_type, num_expiries_plus
                )

            if core is None:
                return None

            if broker_type:
                return cls.get_option_symbol_for_broker(core, broker_type)
            return core

        except Exception as e:
            logger.error(f"[build_option_symbol] Failed: {e}", exc_info=True)
            return None

    # ==========================================================================
    # Existing public API
    # ==========================================================================

    @classmethod
    def get_exchange_symbol(cls, symbol: str) -> str:
        """Convert input symbol to canonical exchange symbol"""
        try:
            if symbol is None:
                logger.warning("get_exchange_symbol called with None symbol")
                return ""
            return cls.SYMBOL_MAP.get(symbol, symbol)
        except Exception as e:
            logger.error(f"[get_exchange_symbol] Failed for {symbol}: {e}", exc_info=True)
            return symbol if symbol else ""

    @classmethod
    def get_multiplier(cls, symbol: str) -> int:
        """Get strike multiplier for symbol"""
        try:
            exchange_symbol = cls.get_exchange_symbol(symbol)
            return cls.MULTIPLIER_MAP.get(exchange_symbol, 50)
        except Exception as e:
            logger.error(f"[get_multiplier] Failed for {symbol}: {e}", exc_info=True)
            return 50

    @classmethod
    def lookbacks(cls, derivative: str = 'NIFTY', side: str = BaseEnums.CALL, lookback: int = 0) -> int:
        """Calculate strike price adjustment based on lookback"""
        try:
            derivative = cls.get_exchange_symbol(derivative)
            if side not in {BaseEnums.CALL, BaseEnums.PUT}:
                logger.warning(f"Invalid side: {side}. Defaulting to {BaseEnums.CALL}.")
                side = BaseEnums.CALL

            multiplier = cls.get_multiplier(derivative)

            if side == BaseEnums.CALL:
                return lookback + multiplier
            else:
                return lookback - multiplier
        except Exception as e:
            logger.error(f"[lookbacks] Error: {e}", exc_info=True)
            return lookback

    # --- Expiry Date Calculations ---

    @classmethod
    def get_last_expiry_weekday_of_month(cls, year: int, month: int, target_weekday: int) -> datetime:
        """Get the last occurrence of a given weekday in a month."""
        try:
            if year < 2000 or year > 2100:
                logger.warning(f"Year {year} out of reasonable range, using current year")
                year = datetime.now().year
            if month < 1 or month > 12:
                logger.warning(f"Month {month} out of range, using current month")
                month = datetime.now().month
            if target_weekday < 0 or target_weekday > 4:
                logger.warning(f"target_weekday {target_weekday} out of range, defaulting to Thursday")
                target_weekday = 3

            last_day = calendar.monthrange(year, month)[1]
            date = datetime(year, month, last_day)
            while date.weekday() != target_weekday:
                date -= timedelta(days=1)
            return date
        except ValueError as e:
            logger.error(f"Invalid date parameters: year={year}, month={month}: {e}", exc_info=True)
            return datetime.now()
        except Exception as e:
            logger.error(f"[get_last_expiry_weekday_of_month] Failed: {e}", exc_info=True)
            return datetime.now()

    @classmethod
    def get_last_thursday_of_month(cls, year: int, month: int) -> datetime:
        """Get the last Thursday of a given month (kept for backward compatibility)"""
        try:
            return cls.get_last_expiry_weekday_of_month(year, month, target_weekday=3)
        except Exception as e:
            logger.error(f"[get_last_thursday_of_month] Failed: {e}", exc_info=True)
            return datetime.now()

    @classmethod
    def get_monthly_expiry_date(cls, year: int, month: int, derivative: str = "NIFTY") -> datetime:
        """Get the monthly expiry date for the given derivative with holiday adjustment."""
        try:
            exchange_symbol = cls.get_exchange_symbol(derivative)
            target_weekday = cls.EXPIRY_WEEKDAY_MAP.get(exchange_symbol, 3)
            expiry = cls.get_last_expiry_weekday_of_month(year, month, target_weekday)

            max_adjustments = 10
            adjustments = 0
            while is_holiday(expiry) and adjustments < max_adjustments:
                expiry -= timedelta(days=1)
                adjustments += 1

            return get_time_of_day(0, 0, 0, expiry)
        except Exception as e:
            logger.error(f"[get_monthly_expiry_date] Failed for {derivative}: {e}", exc_info=True)
            return datetime.now()

    @classmethod
    def get_current_weekly_expiry_date(cls, derivative: str = "NIFTY") -> datetime:
        """Get the current (or next upcoming) weekly expiry date."""
        try:
            exchange_symbol = cls.get_exchange_symbol(derivative)
            target_weekday = cls.EXPIRY_WEEKDAY_MAP.get(exchange_symbol, 1)

            today = datetime.now()
            days_to_add = (target_weekday - today.weekday() + 7) % 7

            if days_to_add == 0 and is_market_closed_for_the_day():
                days_to_add = 7

            expiry = today + timedelta(days=days_to_add)

            max_adjustments = 10
            adjustments = 0
            while is_holiday(expiry) and adjustments < max_adjustments:
                expiry -= timedelta(days=1)
                adjustments += 1

            if expiry.date() < today.date():
                expiry = today + timedelta(days=(target_weekday - today.weekday() + 7) % 7 + 7)
                adjustments = 0
                while is_holiday(expiry) and adjustments < max_adjustments:
                    expiry -= timedelta(days=1)
                    adjustments += 1

            return get_time_of_day(0, 0, 0, expiry)
        except Exception as e:
            logger.error(f"[get_current_weekly_expiry_date] Failed for {derivative}: {e}", exc_info=True)
            return datetime.now()

    @classmethod
    def is_monthly_expiry_week(cls, derivative: str = "NIFTY") -> bool:
        """Check if the current week contains the monthly expiry."""
        try:
            today = datetime.now()
            exchange_symbol = cls.get_exchange_symbol(derivative)

            monthly_expiry = cls.get_monthly_expiry_date(today.year, today.month, derivative=exchange_symbol)

            if monthly_expiry.date() < today.date() or (
                    monthly_expiry.date() == today.date() and is_market_closed_for_the_day()
            ):
                next_month = today.month + 1
                next_year = today.year + (1 if next_month > 12 else 0)
                next_month = ((next_month - 1) % 12) + 1
                monthly_expiry = cls.get_monthly_expiry_date(next_year, next_month, derivative=exchange_symbol)

            start_of_week = today - timedelta(days=today.weekday())
            end_of_week = start_of_week + timedelta(days=6)

            return start_of_week.date() <= monthly_expiry.date() <= end_of_week.date()
        except Exception as e:
            logger.error(f"[is_monthly_expiry_week] Failed for {derivative}: {e}", exc_info=True)
            return False

    @classmethod
    def is_monthly_expiry_today(cls, derivative: str = "NIFTY") -> bool:
        """Check if today is the monthly expiry day."""
        try:
            today = datetime.now()
            exchange_symbol = cls.get_exchange_symbol(derivative)
            monthly_expiry = cls.get_monthly_expiry_date(today.year, today.month, derivative=exchange_symbol)
            return today.date() == monthly_expiry.date()
        except Exception as e:
            logger.error(f"[is_monthly_expiry_today] Failed for {derivative}: {e}", exc_info=True)
            return False

    @classmethod
    def should_use_monthly_format(cls, derivative: str = "NIFTY") -> bool:
        """Determine if we should use monthly option format."""
        try:
            exchange_symbol = cls.get_exchange_symbol(derivative)

            if exchange_symbol == "SENSEX":
                return True

            next_expiry = cls.get_current_weekly_expiry_date(derivative=exchange_symbol)
            monthly_expiry = cls.get_monthly_expiry_date(
                next_expiry.year, next_expiry.month, derivative=exchange_symbol
            )
            return next_expiry.date() == monthly_expiry.date()
        except Exception as e:
            logger.error(f"[should_use_monthly_format] Error: {e}", exc_info=True)
            return False

    # --- Option Symbol Generation ---

    @classmethod
    def prepare_monthly_expiry_symbol(cls, input_symbol: str, strike: Any, option_type: str,
                                      num_months_plus: int = 0) -> Optional[str]:
        """Prepare monthly expiry option symbol (core NSE compact format, no broker prefix)."""
        try:
            if not input_symbol:
                logger.warning("prepare_monthly_expiry_symbol called with empty input_symbol")
                return None
            if strike is None:
                logger.warning("prepare_monthly_expiry_symbol called with None strike")
                return None

            today = datetime.now()
            exchange_symbol = cls.get_exchange_symbol(input_symbol)

            current_month_expiry = cls.get_monthly_expiry_date(today.year, today.month, derivative=exchange_symbol)
            market_end_today = get_market_end_time(current_month_expiry)

            if datetime.now() > market_end_today:
                base_month = today.month + 1
                base_year = today.year + (1 if base_month > 12 else 0)
                base_month = ((base_month - 1) % 12) + 1
            else:
                base_month = today.month
                base_year = today.year

            target_month = base_month + num_months_plus
            target_year = base_year + (target_month - 1) // 12
            target_month = ((target_month - 1) % 12) + 1

            expiry_date = cls.get_monthly_expiry_date(target_year, target_month, derivative=exchange_symbol)

            year2d = str(expiry_date.year)[2:]
            month_code = cls.MONTHLY_MONTH_CODES.get(expiry_date.month, "JAN")
            option_type = option_type.upper()
            if option_type not in ['CE', 'PE']:
                logger.warning(f"Invalid option type: {option_type}. Defaulting to 'CE'.")
                option_type = 'CE'

            try:
                strike_int = int(float(strike))
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to convert strike {strike} to int: {e}")
                return None

            symbol = f"{exchange_symbol}{year2d}{month_code}{strike_int}{option_type}"
            logger.debug(f"[prepare_monthly_expiry_symbol] {input_symbol} => {symbol}")
            return symbol
        except Exception as e:
            logger.error(f"[prepare_monthly_expiry_symbol] Error: {e}", exc_info=True)
            return None

    @classmethod
    def prepare_weekly_options_symbol(cls, input_symbol: str, strike: Any, option_type: str,
                                      num_weeks_plus: int = 0) -> Optional[str]:
        """Prepare weekly expiry option symbol (core NSE compact format, no broker prefix)."""
        try:
            if not input_symbol:
                logger.warning("prepare_weekly_options_symbol called with empty input_symbol")
                return None
            if strike is None:
                logger.warning("prepare_weekly_options_symbol called with None strike")
                return None

            expiry_date = cls.get_current_weekly_expiry_date(derivative=input_symbol)

            if num_weeks_plus:
                expiry_date += timedelta(weeks=num_weeks_plus)
                max_adjustments = 10
                adjustments = 0
                while is_holiday(expiry_date) and adjustments < max_adjustments:
                    expiry_date -= timedelta(days=1)
                    adjustments += 1

            year2d = str(expiry_date.year)[2:]
            option_type = option_type.upper()
            if option_type not in ['CE', 'PE']:
                logger.warning(f"Invalid option type: {option_type}. Defaulting to 'CE'.")
                option_type = 'CE'

            try:
                strike_int = int(float(strike))
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to convert strike {strike} to int: {e}")
                return None

            month_code = cls.WEEKLY_MONTH_CODES.get(expiry_date.month, str(expiry_date.month))
            day_str = f"{expiry_date.day:02d}"
            symbol = f"{input_symbol}{year2d}{month_code}{day_str}{strike_int}{option_type}"
            logger.debug(f"[prepare_weekly_options_symbol] Weekly format: {symbol}")
            return symbol
        except Exception as e:
            logger.error(f"[prepare_weekly_options_symbol] Error: {e}", exc_info=True)
            return None

    @classmethod
    def get_option_symbol(cls, exchange_symbol: str, strike: float, option_type: str,
                          expiry: int = 0) -> Optional[str]:
        """Get option symbol using appropriate format based on expiry timing (no broker prefix)."""
        try:
            if not exchange_symbol:
                logger.warning("get_option_symbol called with empty exchange_symbol")
                return None

            use_monthly = cls.should_use_monthly_format(exchange_symbol)

            if use_monthly:
                return cls.prepare_monthly_expiry_symbol(exchange_symbol, strike, option_type, expiry)
            else:
                return cls.prepare_weekly_options_symbol(exchange_symbol, strike, option_type, expiry)
        except Exception as e:
            logger.error(f"[get_option_symbol] Error: {e}", exc_info=True)
            return None

    # --- Strike Price Calculations ---

    @classmethod
    def get_nearest_strike_price(cls, price: float, nearest_multiple: int = 50) -> int:
        """Round price to nearest strike multiple"""
        try:
            if price is None:
                logger.warning("get_nearest_strike_price called with None price")
                return 0
            if nearest_multiple <= 0:
                logger.warning(f"Invalid nearest_multiple {nearest_multiple}, using 50")
                nearest_multiple = 50

            input_price = int(round(price))
            remainder = input_price % nearest_multiple

            if remainder < nearest_multiple / 2:
                return input_price - remainder
            else:
                return input_price + (nearest_multiple - remainder)
        except Exception as e:
            logger.error(f"[get_nearest_strike_price] Error: {e}", exc_info=True)
            try:
                return int(price)
            except:
                return 0

    @classmethod
    def get_all_option(cls, expiry: int = 0, symbol: str = "NIFTY50", strike: Optional[float] = None,
                       itm: int = 5, otm: int = 5, putorcall: str = "CE",
                       broker_type: Optional[str] = None) -> List[str]:
        """Get option symbols centred around the ATM strike."""
        try:
            if strike is None:
                logger.error("get_all_option called with None strike")
                return []
            if not symbol:
                logger.warning("get_all_option called with empty symbol")
                symbol = "NIFTY50"

            exchange_symbol = cls.get_exchange_symbol(symbol)
            multiplier = cls.get_multiplier(exchange_symbol)
            atm_strike = cls.get_nearest_strike_price(strike, multiplier)
            use_monthly = cls.should_use_monthly_format(exchange_symbol)

            start_strike = atm_strike - (itm * multiplier)
            total_strikes = itm + 1 + otm

            options = []
            for i in range(total_strikes):
                current_strike = start_strike + i * multiplier
                try:
                    if use_monthly:
                        core = cls.prepare_monthly_expiry_symbol(
                            exchange_symbol, current_strike, putorcall, expiry
                        )
                    else:
                        core = cls.prepare_weekly_options_symbol(
                            exchange_symbol, current_strike, putorcall, expiry
                        )
                    if core:
                        option = (
                            cls.get_option_symbol_for_broker(core, broker_type)
                            if broker_type else core
                        )
                        options.append(option)
                except Exception as e:
                    logger.warning(f"Failed to generate option for strike {current_strike}: {e}")
                    continue

            return options

        except Exception as e:
            logger.error(f"[get_all_option] Error: {e}", exc_info=True)
            return []

    @classmethod
    def get_option_at_price(cls, derivative_price: float = 0, lookback: float = 0, op_type: str = 'CE',
                            derivative_name: str = 'NIFTY', expiry: int = 0,
                            broker_type: Optional[str] = None) -> Optional[str]:
        """Get option symbol for given price and lookback."""
        try:
            if not derivative_price or derivative_price <= 0:
                logger.error(f"Invalid derivative price: {derivative_price}")
                return None
            if op_type not in ['CE', 'PE']:
                logger.error(f"Option type must be 'CE' or 'PE', got {op_type}")
                return None
            if not derivative_name:
                logger.error("Derivative name is required")
                return None

            exchange_symbol = cls.get_exchange_symbol(derivative_name)
            multiplier = cls.get_multiplier(exchange_symbol)

            nearest_strike = cls.get_nearest_strike_price(derivative_price, multiplier)

            if op_type == 'CE':
                lookback_strikes = int(lookback / multiplier) if lookback else 0
                strike = nearest_strike - (lookback_strikes * multiplier)
            else:
                lookback_strikes = int(lookback / multiplier) if lookback else 0
                strike = nearest_strike + (lookback_strikes * multiplier)

            core = cls.get_option_symbol(exchange_symbol, strike, op_type, expiry)
            if core is None:
                return None

            if broker_type:
                return cls.get_option_symbol_for_broker(core, broker_type)
            return core

        except Exception as e:
            logger.error(f"[get_option_at_price] Error: {e}", exc_info=True)
            return None

    # ==================================================================
    # FEATURE 6: Multi-Timeframe Filter helpers
    # ==================================================================

    @classmethod
    def get_mtf_timeframes(cls) -> List[str]:
        try:
            return cls.MTF_TIMEFRAMES.copy()
        except Exception as e:
            logger.error(f"[get_mtf_timeframes] Failed: {e}", exc_info=True)
            return ["1", "5", "15"]

    @classmethod
    def get_mtf_required_bars(cls, timeframe: str) -> int:
        try:
            return cls.MTF_REQUIRED_BARS.get(timeframe, 100)
        except Exception as e:
            logger.error(f"[get_mtf_required_bars] Failed for {timeframe}: {e}", exc_info=True)
            return 100

    @classmethod
    def get_mtf_history_days(cls, timeframe: str) -> int:
        try:
            return cls.MTF_HISTORY_DAYS.get(timeframe, 5)
        except Exception as e:
            logger.error(f"[get_mtf_history_days] Failed for {timeframe}: {e}", exc_info=True)
            return 5

    @classmethod
    def parse_mtf_timeframes(cls, timeframe_str: str) -> List[str]:
        try:
            if not timeframe_str:
                return cls.get_mtf_timeframes()
            parts = [t.strip() for t in timeframe_str.split(',') if t.strip()]
            valid = [t for t in parts if t.isdigit()]
            return valid if valid else cls.get_mtf_timeframes()
        except Exception as e:
            logger.error(f"[parse_mtf_timeframes] Failed for {timeframe_str}: {e}", exc_info=True)
            return cls.get_mtf_timeframes()

    @classmethod
    def format_mtf_timeframes(cls, timeframes: List[str]) -> str:
        try:
            return ','.join(str(t) for t in timeframes if t)
        except Exception as e:
            logger.error(f"[format_mtf_timeframes] Failed: {e}", exc_info=True)
            return "1,5,15"

    @classmethod
    def validate_mtf_timeframes(cls, timeframes: List[str]) -> Tuple[bool, str]:
        try:
            if not timeframes:
                return False, "No timeframes specified"
            if len(timeframes) < 2:
                return False, f"Need at least 2 timeframes, got {len(timeframes)}"
            for tf in timeframes:
                if not tf.isdigit():
                    return False, f"Invalid timeframe '{tf}' - must be numeric"
                tf_int = int(tf)
                if tf_int <= 0:
                    return False, f"Invalid timeframe '{tf}' - must be positive"
                if tf_int > 1440:
                    return False, f"Invalid timeframe '{tf}' - must be <= 1440 (daily)"
            return True, "Valid"
        except Exception as e:
            logger.error(f"[validate_mtf_timeframes] Failed: {e}", exc_info=True)
            return False, f"Validation error: {e}"

    @classmethod
    def get_mtf_display_name(cls, timeframe: str) -> str:
        try:
            return f"{timeframe}min"
        except Exception as e:
            logger.error(f"[get_mtf_display_name] Failed for {timeframe}: {e}", exc_info=True)
            return f"{timeframe}m"

    # --- Utility Methods ---

    @classmethod
    def get_weekly_expiry_day_date(cls, date_time_obj: Optional[datetime] = None,
                                   derivative: str = "NIFTY") -> datetime:
        """Alias for get_current_weekly_expiry_date"""
        try:
            return cls.get_current_weekly_expiry_date(derivative)
        except Exception as e:
            logger.error(f"[get_weekly_expiry_day_date] Failed: {e}", exc_info=True)
            return datetime.now()

    @classmethod
    def get_monthly_expiry_day_date(cls, datetime_obj: Optional[datetime] = None,
                                    derivative: str = "NIFTY") -> datetime:
        """Get the next upcoming monthly expiry date."""
        try:
            if datetime_obj is None:
                datetime_obj = datetime.now()
            exchange_symbol = cls.get_exchange_symbol(derivative)

            expiry = cls.get_monthly_expiry_date(datetime_obj.year, datetime_obj.month, derivative=exchange_symbol)

            if datetime.now() > get_market_end_time(expiry):
                next_month = datetime_obj.month + 1
                next_year = datetime_obj.year + (1 if next_month > 12 else 0)
                next_month = ((next_month - 1) % 12) + 1
                expiry = cls.get_monthly_expiry_date(next_year, next_month, derivative=exchange_symbol)

            return expiry
        except Exception as e:
            logger.error(f"[get_monthly_expiry_day_date] Failed: {e}", exc_info=True)
            return datetime.now()

    @classmethod
    def is_today_weekly_expiry_day(cls, derivative: str = "NIFTY50") -> bool:
        """Check if today is weekly expiry day"""
        try:
            expiry_date = cls.get_current_weekly_expiry_date(derivative=derivative)
            today = get_time_of_day(0, 0, 0)
            return expiry_date.date() == today.date()
        except Exception as e:
            logger.error(f"[is_today_weekly_expiry_day] Error: {e}", exc_info=True)
            return False

    @classmethod
    def is_today_one_day_before_weekly_expiry_day(cls, derivative: str = "NIFTY50") -> bool:
        """Check if tomorrow is weekly expiry day"""
        try:
            expiry_date = cls.get_current_weekly_expiry_date(derivative=derivative)
            today = get_time_of_day(0, 0, 0)
            return (expiry_date - timedelta(days=1)).date() == today.date()
        except Exception as e:
            logger.error(f"[is_today_one_day_before_weekly_expiry_day] Error: {e}", exc_info=True)
            return False

    @classmethod
    def prepare_monthly_expiry_futures_symbol(cls, input_symbol: str) -> Optional[str]:
        """Prepare futures symbol for the current or next monthly expiry."""
        try:
            if not input_symbol:
                logger.warning("prepare_monthly_expiry_futures_symbol called with empty input_symbol")
                return None

            exchange_symbol = cls.get_exchange_symbol(input_symbol)
            expiry_date = cls.get_monthly_expiry_day_date(derivative=input_symbol)

            year2d = str(expiry_date.year)[2:]
            month_short = calendar.month_name[expiry_date.month].upper()[:3]
            symbol = exchange_symbol + year2d + month_short + 'FUT'
            logger.debug(f'[prepare_monthly_expiry_futures_symbol] {input_symbol} => {symbol}')
            return symbol
        except Exception as e:
            logger.error(f"[prepare_monthly_expiry_futures_symbol] Error: {e}", exc_info=True)
            return None

    @classmethod
    def get_interval_minutes(cls, interval: str) -> int:
        """Convert interval string to integer minutes."""
        try:
            if interval == "D":
                return 375
            return int(interval)
        except Exception:
            return 5

    # Rule 8: Cleanup method
    @classmethod
    def cleanup(cls):
        """Clean up resources"""
        try:
            logger.info("[OptionUtils] Cleanup completed")
        except Exception as e:
            logger.error(f"[OptionUtils.cleanup] Error: {e}", exc_info=True)