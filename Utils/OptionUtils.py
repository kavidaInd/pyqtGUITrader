# OptionUtils.py - All option-related methods consolidated here
import calendar
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Any

import BaseEnums
from Utils.Utils import Utils

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
        return cls.SYMBOL_MAP.get(symbol, symbol)

    @classmethod
    def get_multiplier(cls, symbol: str) -> int:
        """Get strike multiplier for symbol"""
        exchange_symbol = cls.get_exchange_symbol(symbol)
        return cls.MULTIPLIER_MAP.get(exchange_symbol, 50)

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
    def get_last_thursday_of_month(cls, year: int, month: int) -> datetime:
        """Get the last Thursday of a given month"""
        last_day = calendar.monthrange(year, month)[1]
        date = datetime(year, month, last_day)
        # Thursday is 3 (Monday=0, Tuesday=1, Wednesday=2, Thursday=3)
        while date.weekday() != 3:
            date -= timedelta(days=1)
        return date

    @classmethod
    def get_monthly_expiry_date(cls, year: int, month: int) -> datetime:
        """Get the monthly expiry date (last Thursday of month) with holiday adjustment"""
        expiry = cls.get_last_thursday_of_month(year, month)
        # Adjust for holidays if needed
        while Utils.is_holiday(expiry):
            expiry -= timedelta(days=1)
        return Utils.get_time_of_day(0, 0, 0, expiry)

    @classmethod
    def get_current_weekly_expiry_date(cls, derivative: str = "NIFTY") -> datetime:
        """Get the current week's expiry date based on derivative"""
        exchange_symbol = cls.get_exchange_symbol(derivative)
        target_weekday = cls.EXPIRY_WEEKDAY_MAP.get(exchange_symbol, 3)

        today = datetime.now()
        # Calculate days until next target weekday
        days_to_add = (target_weekday - today.weekday() + 7) % 7
        if days_to_add == 0:
            days_to_add = 7  # Next week, not today

        expiry = today + timedelta(days=days_to_add)

        # Adjust for holidays
        while Utils.is_holiday(expiry):
            expiry -= timedelta(days=1)

        return Utils.get_time_of_day(0, 0, 0, expiry)

    @classmethod
    def is_monthly_expiry_week(cls, derivative: str = "NIFTY") -> bool:
        """Check if current week contains the monthly expiry"""
        today = datetime.now()
        monthly_expiry = cls.get_monthly_expiry_date(today.year, today.month)

        # Get start of week (Monday)
        start_of_week = today - timedelta(days=today.weekday())
        # Get end of week (Sunday)
        end_of_week = start_of_week + timedelta(days=6)

        return start_of_week.date() <= monthly_expiry.date() <= end_of_week.date()

    @classmethod
    def is_monthly_expiry_today(cls, derivative: str = "NIFTY") -> bool:
        """Check if today is the monthly expiry day"""
        today = datetime.now()
        monthly_expiry = cls.get_monthly_expiry_date(today.year, today.month)
        return today.date() == monthly_expiry.date()

    @classmethod
    def should_use_monthly_format(cls, derivative: str = "NIFTY") -> bool:
        """
        Determine if we should use monthly option format.
        Returns True only during the monthly expiry week (last week of month)
        """
        try:
            exchange_symbol = cls.get_exchange_symbol(derivative)

            # SENSEX always uses monthly format
            if exchange_symbol == "SENSEX":
                return True

            today = datetime.now()

            # Get monthly expiry for current month
            monthly_expiry = cls.get_monthly_expiry_date(today.year, today.month)

            # Get start of current week (Monday)
            start_of_week = today - timedelta(days=today.weekday())

            # If we're before the monthly expiry week, use weekly format
            if today.date() < start_of_week.date():
                return False

            # If we're after the monthly expiry, check if we're in the last week of month
            if today.date() > monthly_expiry.date():
                # Check if this is the last week of month
                last_day_of_month = datetime(today.year, today.month,
                                             calendar.monthrange(today.year, today.month)[1])
                last_monday_of_month = last_day_of_month - timedelta(days=last_day_of_month.weekday())
                return today.date() >= last_monday_of_month.date()

            # We're in the month, check if current week contains monthly expiry
            return cls.is_monthly_expiry_week(derivative)

        except Exception as e:
            logger.error(f"[should_use_monthly_format] Error: {e}")
            return False

    # --- Option Symbol Generation ---

    @classmethod
    def prepare_monthly_expiry_symbol(cls, input_symbol: str, strike: Any, option_type: str, num_weeks_plus: int = 0) -> \
    Optional[str]:
        """
        Prepare monthly expiry option symbol
        Format: {UnderlyingSymbol}{YY}{MMM}{Strike}{Opt_Type}
        Example: NIFTY26FEB25550CE
        """
        try:
            expiry_date = cls.get_monthly_expiry_date(
                datetime.now().year,
                datetime.now().month
            )
            if num_weeks_plus:
                expiry_date += timedelta(weeks=num_weeks_plus)

            year2d = str(expiry_date.year)[2:]
            month_code = cls.MONTHLY_MONTH_CODES.get(expiry_date.month, "JAN")

            option_type = option_type.upper()
            if option_type not in ['CE', 'PE']:
                logger.warning(f"Invalid option type: {option_type}. Defaulting to 'CE'.")
                option_type = 'CE'

            # Format strike as integer without decimal
            strike_int = int(float(strike))

            symbol = f"{input_symbol}{year2d}{month_code}{strike_int}{option_type}"
            logger.info(f"[prepare_monthly_expiry_symbol] {symbol}")
            return symbol
        except Exception as e:
            logger.error(f"[prepare_monthly_expiry_symbol] Error: {e}", exc_info=True)
            return None

    @classmethod
    def prepare_weekly_options_symbol(cls, input_symbol: str, strike: Any, option_type: str, num_weeks_plus: int = 0) -> \
    Optional[str]:
        """
        Prepare weekly expiry option symbol
        Format: {UnderlyingSymbol}{YY}{M}{dd}{Strike}{Opt_Type}
        Example: NIFTY2631225500CE (for 12th March 2026, strike 25500)
        Note: Month code: 1-9, O=Oct, N=Nov, D=Dec
        """
        try:
            expiry_date = cls.get_current_weekly_expiry_date(derivative=input_symbol)

            if num_weeks_plus:
                expiry_date += timedelta(days=num_weeks_plus * 7)
                expiry_date = cls.get_current_weekly_expiry_date(expiry_date)

            year2d = str(expiry_date.year)[2:]
            option_type = option_type.upper()

            # Format strike as integer without decimal
            strike_int = int(float(strike))

            # Weekly format with month code (1-9, O, N, D) and day
            month_code = cls.WEEKLY_MONTH_CODES.get(expiry_date.month, str(expiry_date.month))
            day_str = f"{expiry_date.day:02d}"
            symbol = f"{input_symbol}{year2d}{month_code}{day_str}{strike_int}{option_type}"
            logger.info(f"[prepare_weekly_options_symbol] Weekly format: {symbol}")

            return symbol
        except Exception as e:
            logger.error(f"[prepare_weekly_options_symbol] Error: {e}", exc_info=True)
            return None

    @classmethod
    def get_option_symbol(cls, exchange_symbol: str, strike: float, option_type: str, expiry: int = 0) -> Optional[str]:
        """
        Get option symbol using appropriate format based on expiry timing
        """
        try:
            # Determine which format to use
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
            input_price = int(round(price))
            remainder = input_price % nearest_multiple

            if remainder < nearest_multiple / 2:
                return input_price - remainder
            else:
                return input_price + (nearest_multiple - remainder)
        except Exception as e:
            logger.error(f"[get_nearest_strike_price] Error: {e}", exc_info=True)
            return int(price)

    @classmethod
    def get_all_option(cls, expiry: int = 0, symbol: str = "NIFTY50", strike: Optional[float] = None, number: int = 2,
                       multiplier: int = 50, putorcall: str = "CE") -> List[str]:
        """Get multiple option symbols around a strike price"""
        try:
            if strike is None:
                raise ValueError("Strike price is required")

            exchange_symbol = cls.get_exchange_symbol(symbol)
            multiplier = cls.get_multiplier(exchange_symbol)

            options = []
            strike_price = cls.get_nearest_strike_price(strike, multiplier)

            # Determine which format to use
            use_monthly = cls.should_use_monthly_format(exchange_symbol)

            # Adjust starting strike based on option type
            if putorcall.upper() == 'CE':
                current_strike = strike_price - multiplier
            else:
                current_strike = strike_price + multiplier

            for i in range(number * 2):
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

                # Move to next strike
                if putorcall.upper() == 'CE':
                    current_strike += multiplier
                else:
                    current_strike -= multiplier

            return options
        except Exception as e:
            logger.error(f"[get_all_option] Error: {e}", exc_info=True)
            return []

    @classmethod
    def get_option_at_price(cls, derivative_price: float = 0, lookback: float = 0, op_type: str = 'CE',
                            derivative_name: str = 'NIFTY', expiry: int = 0) -> Optional[str]:
        """
        Get option symbol for given price and lookback

        Example: For NIFTY at 25571.25, lookback=0, op_type='CE' on 20th Feb 2026
        Should return: NIFTY2631225550CE (weekly format for March expiry)
        """
        try:
            if not derivative_price:
                raise ValueError("Invalid derivative price provided.")
            if op_type not in ['CE', 'PE']:
                raise ValueError("Option type must be 'CE' or 'PE'.")
            if not derivative_name:
                raise ValueError("Derivative name is required.")

            exchange_symbol = cls.get_exchange_symbol(derivative_name)
            multiplier = cls.get_multiplier(exchange_symbol)

            # Calculate strike price
            nearest_strike = cls.get_nearest_strike_price(derivative_price, multiplier)

            if op_type == 'CE':
                # For Call options, subtract lookback from nearest strike
                lookback_strikes = int(lookback / multiplier) if lookback else 0
                strike = nearest_strike - (lookback_strikes * multiplier)
            else:
                # For Put options, add lookback to nearest strike
                lookback_strikes = int(lookback / multiplier) if lookback else 0
                strike = nearest_strike + (lookback_strikes * multiplier)

            logger.info(f"[get_option_at_price] Price: {derivative_price}, Nearest strike: {nearest_strike}, "
                        f"Lookback: {lookback}, Calculated strike: {strike}")

            # Get option symbol using the appropriate format
            option = cls.get_option_symbol(exchange_symbol, strike, op_type, expiry)

            logger.info(f"[get_option_at_price] Generated option: {option}")
            return option

        except Exception as e:
            logger.error(f"[get_option_at_price] Error: {e}", exc_info=True)
            return None

    # --- Utility Methods ---

    @classmethod
    def get_weekly_expiry_day_date(cls, date_time_obj: Optional[datetime] = None,
                                   derivative: str = "NIFTY") -> datetime:
        """Alias for get_current_weekly_expiry_date - kept for backward compatibility"""
        return cls.get_current_weekly_expiry_date(derivative)

    @classmethod
    def get_monthly_expiry_day_date(cls, datetime_obj: Optional[datetime] = None,
                                    derivative: str = "NIFTY") -> datetime:
        """Alias for get_monthly_expiry_date - kept for backward compatibility"""
        if datetime_obj is None:
            datetime_obj = datetime.now()
        return cls.get_monthly_expiry_date(datetime_obj.year, datetime_obj.month)

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
        """Prepare futures symbol"""
        try:
            expiry_date = cls.get_monthly_expiry_day_date(derivative=input_symbol)
            if datetime.now() > Utils.get_market_end_time(expiry_date):
                expiry_date = cls.get_monthly_expiry_day_date(datetime.now() + timedelta(days=20))
            year2d = str(expiry_date.year)[2:]
            month_short = calendar.month_name[expiry_date.month].upper()[:3]
            symbol = cls.get_exchange_symbol(input_symbol) + year2d + month_short + 'FUT'
            logger.info(f'[prepare_monthly_expiry_futures_symbol] {input_symbol} => {symbol}')
            return symbol
        except Exception as e:
            logger.error(f"[prepare_monthly_expiry_futures_symbol] Error: {e}", exc_info=True)
            return None