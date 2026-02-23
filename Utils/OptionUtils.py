# OptionUtils.py - All option-related methods consolidated here
import calendar
import logging
import logging.handlers
from datetime import datetime, timedelta
from typing import Optional, List, Any, Dict
import traceback

import BaseEnums
from Utils.Utils import Utils

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class OptionUtils:
    """# REFACTORED: All option-related methods moved from Utils.py to here"""

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
        "FINNIFTY": 40,
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

    # Weekday map for expiry days (0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday)
    EXPIRY_WEEKDAY_MAP = {
        "NIFTY": 3,  # Thursday
        "BANKNIFTY": 2,  # Wednesday
        "FINNIFTY": 1,  # Tuesday
        "MIDCPNIFTY": 0,  # Monday
        "SENSEX": 4  # Friday
    }

    @classmethod
    def get_exchange_symbol(cls, symbol: str) -> str:
        """Convert input symbol to exchange symbol"""
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
        """
        Get the last occurrence of a given weekday in a month.
        target_weekday: 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday
        """
        try:
            # Input validation
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
        """
        Get the monthly expiry date for the given derivative with holiday adjustment.
        """
        try:
            exchange_symbol = cls.get_exchange_symbol(derivative)
            target_weekday = cls.EXPIRY_WEEKDAY_MAP.get(exchange_symbol, 3)  # default Thursday
            expiry = cls.get_last_expiry_weekday_of_month(year, month, target_weekday)

            # Adjust backwards for holidays
            max_adjustments = 10  # Prevent infinite loop
            adjustments = 0
            while Utils.is_holiday(expiry) and adjustments < max_adjustments:
                expiry -= timedelta(days=1)
                adjustments += 1

            return Utils.get_time_of_day(0, 0, 0, expiry)
        except Exception as e:
            logger.error(f"[get_monthly_expiry_date] Failed for {derivative}: {e}", exc_info=True)
            return datetime.now()

    @classmethod
    def get_current_weekly_expiry_date(cls, derivative: str = "NIFTY") -> datetime:
        """
        Get the current (or next upcoming) weekly expiry date for a derivative.
        """
        try:
            exchange_symbol = cls.get_exchange_symbol(derivative)
            target_weekday = cls.EXPIRY_WEEKDAY_MAP.get(exchange_symbol, 3)

            today = datetime.now()
            days_to_add = (target_weekday - today.weekday() + 7) % 7

            # FIX: If days_to_add == 0, today IS the expiry weekday.
            # Only roll forward to next week if the market has already closed today.
            if days_to_add == 0 and Utils.is_market_closed_for_the_day():
                days_to_add = 7

            expiry = today + timedelta(days=days_to_add)

            # Adjust backwards for holidays
            max_adjustments = 10
            adjustments = 0
            while Utils.is_holiday(expiry) and adjustments < max_adjustments:
                expiry -= timedelta(days=1)
                adjustments += 1

            return Utils.get_time_of_day(0, 0, 0, expiry)
        except Exception as e:
            logger.error(f"[get_current_weekly_expiry_date] Failed for {derivative}: {e}", exc_info=True)
            return datetime.now()

    @classmethod
    def is_monthly_expiry_week(cls, derivative: str = "NIFTY") -> bool:
        """Check if the current week contains the monthly expiry for the given derivative"""
        try:
            today = datetime.now()
            exchange_symbol = cls.get_exchange_symbol(derivative)
            monthly_expiry = cls.get_monthly_expiry_date(today.year, today.month, derivative=exchange_symbol)

            # Get start of week (Monday) and end of week (Sunday)
            start_of_week = today - timedelta(days=today.weekday())
            end_of_week = start_of_week + timedelta(days=6)

            return start_of_week.date() <= monthly_expiry.date() <= end_of_week.date()
        except Exception as e:
            logger.error(f"[is_monthly_expiry_week] Failed for {derivative}: {e}", exc_info=True)
            return False

    @classmethod
    def is_monthly_expiry_today(cls, derivative: str = "NIFTY") -> bool:
        """Check if today is the monthly expiry day for the given derivative"""
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
        """
        Determine if we should use monthly option format.
        """
        try:
            exchange_symbol = cls.get_exchange_symbol(derivative)

            # SENSEX only has monthly expiries
            if exchange_symbol == "SENSEX":
                return True

            target_weekday = cls.EXPIRY_WEEKDAY_MAP.get(exchange_symbol, 3)
            today = datetime.now()

            # Compute next expiry date
            days_to_add = (target_weekday - today.weekday() + 7) % 7
            if days_to_add == 0 and Utils.is_market_closed_for_the_day():
                days_to_add = 7

            next_expiry = today + timedelta(days=days_to_add)

            # Adjust backwards for holidays
            max_adjustments = 10
            adjustments = 0
            while Utils.is_holiday(next_expiry) and adjustments < max_adjustments:
                next_expiry -= timedelta(days=1)
                adjustments += 1

            # Get the monthly expiry for the month that next_expiry lands in
            monthly_expiry = cls.get_monthly_expiry_date(
                next_expiry.year, next_expiry.month, derivative=exchange_symbol
            )

            # Use monthly format only if the next expiry IS the monthly expiry
            return next_expiry.date() == monthly_expiry.date()

        except Exception as e:
            logger.error(f"[should_use_monthly_format] Error: {e}", exc_info=True)
            return False

    # --- Option Symbol Generation ---

    @classmethod
    def prepare_monthly_expiry_symbol(cls, input_symbol: str, strike: Any, option_type: str,
                                      num_months_plus: int = 0) -> Optional[str]:
        """
        Prepare monthly expiry option symbol.
        """
        try:
            if not input_symbol:
                logger.warning("prepare_monthly_expiry_symbol called with empty input_symbol")
                return None

            if strike is None:
                logger.warning("prepare_monthly_expiry_symbol called with None strike")
                return None

            today = datetime.now()
            # Advance by the requested number of months
            target_month = today.month + num_months_plus
            target_year = today.year + (target_month - 1) // 12
            target_month = ((target_month - 1) % 12) + 1

            expiry_date = cls.get_monthly_expiry_date(target_year, target_month, derivative=input_symbol)

            year2d = str(expiry_date.year)[2:]
            month_code = cls.MONTHLY_MONTH_CODES.get(expiry_date.month, "JAN")

            option_type = option_type.upper()
            if option_type not in ['CE', 'PE']:
                logger.warning(f"Invalid option type: {option_type}. Defaulting to 'CE'.")
                option_type = 'CE'

            # Format strike as integer without decimal
            try:
                strike_int = int(float(strike))
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to convert strike {strike} to int: {e}")
                return None

            symbol = f"{input_symbol}{year2d}{month_code}{strike_int}{option_type}"
            return symbol
        except Exception as e:
            logger.error(f"[prepare_monthly_expiry_symbol] Error: {e}", exc_info=True)
            return None

    @classmethod
    def prepare_weekly_options_symbol(cls, input_symbol: str, strike: Any, option_type: str,
                                      num_weeks_plus: int = 0) -> Optional[str]:
        """
        Prepare weekly expiry option symbol.
        """
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
                # Re-apply holiday adjustment for the new date
                max_adjustments = 10
                adjustments = 0
                while Utils.is_holiday(expiry_date) and adjustments < max_adjustments:
                    expiry_date -= timedelta(days=1)
                    adjustments += 1

            year2d = str(expiry_date.year)[2:]
            option_type = option_type.upper()

            if option_type not in ['CE', 'PE']:
                logger.warning(f"Invalid option type: {option_type}. Defaulting to 'CE'.")
                option_type = 'CE'

            # Format strike as integer without decimal
            try:
                strike_int = int(float(strike))
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to convert strike {strike} to int: {e}")
                return None

            # Weekly format with month code (1-9, O, N, D) and zero-padded day
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
        """
        Get option symbol using appropriate format based on expiry timing.
        """
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
                       itm: int = 5, otm: int = 5, putorcall: str = "CE") -> List[str]:
        """
        Get option symbols centred around the ATM strike.
        """
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
                        option = cls.prepare_monthly_expiry_symbol(
                            exchange_symbol, current_strike, putorcall, expiry
                        )
                    else:
                        option = cls.prepare_weekly_options_symbol(
                            exchange_symbol, current_strike, putorcall, expiry
                        )
                    if option:
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
                            derivative_name: str = 'NIFTY', expiry: int = 0) -> Optional[str]:
        """
        Get option symbol for given price and lookback.
        """
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

            # Calculate strike price
            nearest_strike = cls.get_nearest_strike_price(derivative_price, multiplier)

            if op_type == 'CE':
                lookback_strikes = int(lookback / multiplier) if lookback else 0
                strike = nearest_strike - (lookback_strikes * multiplier)
            else:
                lookback_strikes = int(lookback / multiplier) if lookback else 0
                strike = nearest_strike + (lookback_strikes * multiplier)

            logger.debug(f"[get_option_at_price] Price: {derivative_price}, Nearest strike: {nearest_strike}, "
                         f"Lookback: {lookback}, Calculated strike: {strike}")

            option = cls.get_option_symbol(exchange_symbol, strike, op_type, expiry)

            logger.debug(f"[get_option_at_price] Generated option: {option}")
            return option

        except Exception as e:
            logger.error(f"[get_option_at_price] Error: {e}", exc_info=True)
            return None

    # --- Utility Methods ---

    @classmethod
    def get_weekly_expiry_day_date(cls, date_time_obj: Optional[datetime] = None,
                                   derivative: str = "NIFTY") -> datetime:
        """Alias for get_current_weekly_expiry_date - kept for backward compatibility"""
        try:
            return cls.get_current_weekly_expiry_date(derivative)
        except Exception as e:
            logger.error(f"[get_weekly_expiry_day_date] Failed: {e}", exc_info=True)
            return datetime.now()

    @classmethod
    def get_monthly_expiry_day_date(cls, datetime_obj: Optional[datetime] = None,
                                    derivative: str = "NIFTY") -> datetime:
        """Alias for get_monthly_expiry_date - kept for backward compatibility"""
        try:
            if datetime_obj is None:
                datetime_obj = datetime.now()
            exchange_symbol = cls.get_exchange_symbol(derivative)
            return cls.get_monthly_expiry_date(datetime_obj.year, datetime_obj.month, derivative=exchange_symbol)
        except Exception as e:
            logger.error(f"[get_monthly_expiry_day_date] Failed: {e}", exc_info=True)
            return datetime.now()

    @classmethod
    def is_today_weekly_expiry_day(cls, derivative: str = "NIFTY50") -> bool:
        """Check if today is weekly expiry day"""
        try:
            expiry_date = cls.get_current_weekly_expiry_date(derivative=derivative)
            today = Utils.get_time_of_day(0, 0, 0)
            return expiry_date.date() == today.date()
        except Exception as e:
            logger.error(f"[is_today_weekly_expiry_day] Error: {e}", exc_info=True)
            return False

    @classmethod
    def is_today_one_day_before_weekly_expiry_day(cls, derivative: str = "NIFTY50") -> bool:
        """Check if tomorrow is weekly expiry day"""
        try:
            expiry_date = cls.get_current_weekly_expiry_date(derivative=derivative)
            today = Utils.get_time_of_day(0, 0, 0)
            return (expiry_date - timedelta(days=1)).date() == today.date()
        except Exception as e:
            logger.error(f"[is_today_one_day_before_weekly_expiry_day] Error: {e}", exc_info=True)
            return False

    @classmethod
    def prepare_monthly_expiry_futures_symbol(cls, input_symbol: str) -> Optional[str]:
        """Prepare futures symbol for the current or next monthly expiry"""
        try:
            if not input_symbol:
                logger.warning("prepare_monthly_expiry_futures_symbol called with empty input_symbol")
                return None

            exchange_symbol = cls.get_exchange_symbol(input_symbol)
            expiry_date = cls.get_monthly_expiry_day_date(derivative=input_symbol)

            if datetime.now() > Utils.get_market_end_time(expiry_date):
                # Roll to next month
                expiry_date = cls.get_monthly_expiry_day_date(
                    datetime.now() + timedelta(days=20),
                    derivative=input_symbol
                )

            year2d = str(expiry_date.year)[2:]
            month_short = calendar.month_name[expiry_date.month].upper()[:3]
            symbol = exchange_symbol + year2d + month_short + 'FUT'
            logger.debug(f'[prepare_monthly_expiry_futures_symbol] {input_symbol} => {symbol}')
            return symbol
        except Exception as e:
            logger.error(f"[prepare_monthly_expiry_futures_symbol] Error: {e}", exc_info=True)
            return None

    # Rule 8: Cleanup method
    @classmethod
    def cleanup(cls):
        """Clean up resources (minimal for this class)"""
        try:
            logger.info("[OptionUtils] Cleanup completed")
        except Exception as e:
            logger.error(f"[OptionUtils.cleanup] Error: {e}", exc_info=True)