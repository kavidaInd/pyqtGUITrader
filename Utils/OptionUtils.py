import calendar
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Any

import BaseEnums
from Utils.Utils import Utils

logger = logging.getLogger(__name__)


class OptionUtils:
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
        "NIFTY": 50, "FINNIFTY": 50, "BANKNIFTY": 100, "SENSEX": 100, "MIDCPNIFTY": 25
    }

    @classmethod
    def lookbacks(cls, derivative: str = 'NIFTY', side: str = BaseEnums.CALL, lookback: int = 0) -> int:
        try:
            derivative = cls.SYMBOL_MAP.get(derivative, 'NIFTY')
            if side not in {BaseEnums.CALL, BaseEnums.PUT}:
                logger.warning(f"Invalid side: {side}. Defaulting to {BaseEnums.CALL}.")
                side = BaseEnums.CALL

            if derivative in {"NIFTY", "FINNIFTY"}:
                return lookback + 50 if side == BaseEnums.CALL else lookback - 50
            elif derivative in {"BANKNIFTY", "SENSEX"}:
                return lookback + 100 if side == BaseEnums.CALL else lookback - 100
            elif derivative == "MIDCPNIFTY":
                return lookback + 25 if side == BaseEnums.CALL else lookback - 25
            return lookback
        except Exception as e:
            logger.error(f"[lookbacks] Error: {e}", exc_info=True)
            return lookback

    @classmethod
    def get_exchange_name(cls, symbol: str) -> str:
        return cls.SYMBOL_MAP.get(symbol, symbol)

    @classmethod
    def prepare_monthly_expiry_futures_symbol(cls, input_symbol: str) -> Optional[str]:
        try:
            expiry_date = cls.get_monthly_expiry_day_date(derivative=input_symbol)
            if datetime.now() > Utils.get_market_end_time(expiry_date):
                expiry_date = cls.get_monthly_expiry_day_date(datetime.now() + timedelta(days=20))
            year2d = str(expiry_date.year)[2:]
            month_short = calendar.month_name[expiry_date.month].upper()[:3]
            symbol = cls.get_exchange_name(input_symbol) + year2d + month_short + 'FUT'
            logger.info(f'[prepare_monthly_expiry_futures_symbol] {input_symbol} => {symbol}')
            return symbol
        except Exception as e:
            logger.error(f"[prepare_monthly_expiry_futures_symbol] Error: {e}", exc_info=True)
            return None

    @classmethod
    def prepare_monthly_expiry_symbol(cls, input_symbol: str, strike: Any, option_type: str, num_weeks_plus: int = 0) \
            -> Optional[str]:
        try:
            expiry_date = cls.get_monthly_expiry_day_date(derivative=input_symbol)
            if num_weeks_plus:
                expiry_date += timedelta(weeks=num_weeks_plus)
            year2d = str(expiry_date.year)[2:]
            month_short = calendar.month_name[expiry_date.month].upper()[:3]
            option_type = option_type.upper()
            if option_type not in ['CE', 'PE']:
                logger.warning(f"Invalid option type: {option_type}. Defaulting to 'CE'.")
                option_type = 'CE'

            symbol = f"{input_symbol}{year2d}{month_short}{strike}{option_type}"
            logger.info(f"[prepare_monthly_expiry_symbol] {symbol}")
            return symbol
        except Exception as e:
            logger.error(f"[prepare_monthly_expiry_symbol] Error: {e}", exc_info=True)
            return None

    @classmethod
    def prepare_weekly_options_symbol(cls, input_symbol: str, strike: Any, option_type: str, num_weeks_plus: int = 0) \
            -> Optional[str]:
        try:
            expiry_date = cls.get_weekly_expiry_day_date(derivative=input_symbol)
            if num_weeks_plus:
                expiry_date += timedelta(days=num_weeks_plus * 7)
                expiry_date = cls.get_weekly_expiry_day_date(expiry_date, derivative=input_symbol)
            if Utils.get_market_start_time() > Utils.get_market_end_time(expiry_date):
                expiry_date += timedelta(days=6)
                expiry_date = cls.get_weekly_expiry_day_date(expiry_date, derivative=input_symbol)

            monthly_expiry = cls.get_monthly_expiry_day_date(derivative=input_symbol)
            same_expiry = expiry_date == monthly_expiry
            year2d = str(expiry_date.year)[2:]
            option_type = option_type.upper()
            if same_expiry:
                month_short = calendar.month_name[expiry_date.month].upper()[:3]
                symbol = f"{input_symbol}{year2d}{month_short}{strike}{option_type}"
            else:
                month_map = {10: "O", 11: "N", 12: "D"}
                month_short = month_map.get(expiry_date.month, str(expiry_date.month))
                day_str = f"{expiry_date.day:02}"
                symbol = f"{input_symbol}{year2d}{month_short}{day_str}{strike}{option_type}"
            logger.info(f"[prepare_weekly_options_symbol] {symbol}")
            return symbol
        except Exception as e:
            logger.error(f"[prepare_weekly_options_symbol] Error: {e}", exc_info=True)
            return None

    @classmethod
    def get_monthly_expiry_day_date(cls, datetime_obj: Optional[datetime] = None, derivative: str = "NIFTY") \
            -> datetime:
        try:
            if datetime_obj is None:
                datetime_obj = datetime.now()
            year, month = datetime_obj.year, datetime_obj.month
            last_day = calendar.monthrange(year, month)[1]
            expiry_day = datetime(year, month, last_day)
            weekday_map = {
                "NIFTY": "Thursday",
                "BANKNIFTY": "Wednesday",
                "MIDCPNIFTY": "Monday",
                "FINNIFTY": "Tuesday",
                "SENSEX": "Friday"
            }
            target_day = weekday_map.get(derivative, "Thursday")
            expiry_day = cls.adjust_to_weekday(expiry_day, target_day)
            while Utils.is_holiday(expiry_day):
                expiry_day -= timedelta(days=1)
            return Utils.get_time_of_day(0, 0, 0, expiry_day)
        except Exception as e:
            logger.error(f"[get_monthly_expiry_day_date] Error: {e}", exc_info=True)
            return datetime.now()

    @staticmethod
    def adjust_to_weekday(expiry_day: datetime, target_day: str) -> datetime:
        target_weekday = list(calendar.day_name).index(target_day)
        while expiry_day.weekday() != target_weekday:
            expiry_day -= timedelta(days=1)
        return expiry_day

    @classmethod
    def get_weekly_expiry_day_date(cls, date_time_obj: Optional[datetime] = None, derivative: str = "NIFTY") \
            -> datetime:
        try:
            if date_time_obj is None:
                date_time_obj = datetime.now()
            weekday_map = {
                "NIFTY": 3, "NIFTY50": 3, "NIFTY50-INDEX": 3,
                "NIFTYBANK": 2, "BANKNIFTY": 2, "NIFTYBANK-INDEX": 2,
                "FINNIFTY": 1, "FINNIFTY-INDEX": 1,
                "MIDCPNIFTY": 1, "MIDCPNIFTY-INDEX": 1,
                "SENSEX": 4
            }
            target_day = weekday_map.get(derivative, 3)
            days_to_add = (target_day - date_time_obj.weekday() + 7) % 7
            expiry_day = date_time_obj + timedelta(days=days_to_add)
            while Utils.is_holiday(expiry_day):
                expiry_day -= timedelta(days=1)
            return Utils.get_time_of_day(0, 0, 0, expiry_day)
        except Exception as e:
            logger.error(f"[get_weekly_expiry_day_date] Error: {e}", exc_info=True)
            return datetime.now()

    @classmethod
    def is_today_weekly_expiry_day(cls, derivative: str = "NIFTY50") -> bool:
        try:
            expiry_date = cls.get_weekly_expiry_day_date(derivative=derivative)
            today = Utils.get_time_of_day(0, 0, 0)
            return expiry_date == today
        except Exception as e:
            logger.error(f"[is_today_weekly_expiry_day] Error: {e}", exc_info=True)
            return False

    @classmethod
    def is_today_one_day_before_weekly_expiry_day(cls, derivative: str = "NIFTY50") -> bool:
        try:
            expiry_date = cls.get_weekly_expiry_day_date(derivative=derivative)
            today = Utils.get_time_of_day(0, 0, 0)
            return expiry_date - timedelta(days=1) == today
        except Exception as e:
            logger.error(f"[is_today_one_day_before_weekly_expiry_day] Error: {e}", exc_info=True)
            return False

    @classmethod
    def get_nearest_strike_price(cls, price: float, nearest_multiple: int = 50) -> int:
        try:
            input_price = int(round(price))
            remainder = input_price % nearest_multiple
            return input_price - remainder if remainder < nearest_multiple / 2 \
                else input_price + (nearest_multiple - remainder)
        except Exception as e:
            logger.error(f"[get_nearest_strike_price] Error: {e}", exc_info=True)
            return int(price)

    @classmethod
    def get_all_option(cls, expiry: int = 0, symbol: str = "NIFTY50", strike: Optional[float] = None, number: int = 2,
                       multiplier: int = 50, putorcall: str = "CE") -> List[str]:
        try:
            if strike is None:
                raise ValueError("Strike price is required")
            symbol = cls.SYMBOL_MAP.get(symbol, symbol)
            multiplier = multiplier
            options = []
            strike = cls.get_nearest_strike_price(strike, multiplier)
            if putorcall.upper() == 'CE':
                strike -= multiplier
            else:
                strike += multiplier

            for _ in range(number * 2):
                if symbol in {'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY'}:
                    option = cls.prepare_monthly_expiry_symbol(symbol, strike, putorcall, expiry)
                else:
                    option = cls.prepare_weekly_options_symbol(symbol, strike, putorcall, expiry)
                options.append(option)
                strike = strike + multiplier if putorcall.upper() == 'CE' else strike - multiplier
            return options
        except Exception as e:
            logger.error(f"[get_all_option] Error: {e}", exc_info=True)
            return []

    @classmethod
    def get_option_at_price(cls, derivative_price: float = 0, lookback: float = 0, op_type: str = 'CE',
                            derivative_name: str = 'NIFTY', expiry: int = 0) -> Optional[str]:
        try:
            if not derivative_price:
                raise ValueError("Invalid derivative price provided.")
            if op_type not in ['CE', 'PE']:
                raise ValueError("Option type must be 'CE' or 'PE'.")
            if not derivative_name:
                raise ValueError("Derivative name is required.")

            strike = derivative_price - lookback if op_type == 'CE' else derivative_price + lookback
            options = cls.get_all_option(
                strike=strike, number=1, symbol=derivative_name, expiry=expiry, putorcall=op_type
            )
            return options[-1] if options else None
        except Exception as e:
            logger.error(f"[get_option_at_price] Error: {e}", exc_info=True)
            return None
