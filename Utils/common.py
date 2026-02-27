# Utils/common.py
"""Common utilities shared between Utils and OptionUtils to avoid circular imports."""

import calendar
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union, List

# Configure logger
logger = logging.getLogger(__name__)

# Directory constants
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

# Date/Time constants
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M:%S"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# Market hours constants
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# Holidays cache
_holidays_cache = None
_holidays_last_loaded = None


def get_holidays() -> Optional[List[str]]:
    """Get list of holiday dates."""
    global _holidays_cache, _holidays_last_loaded

    try:
        # Reload cache every hour
        now = datetime.now()
        if _holidays_cache is None or _holidays_last_loaded is None or \
                (now - _holidays_last_loaded).seconds > 3600:

            holidays_file = BASE_DIR / 'Config' / 'holidays.json'
            if holidays_file.exists():
                import json
                with open(holidays_file, 'r', encoding='utf-8') as f:
                    _holidays_cache = json.load(f)
                _holidays_last_loaded = now
            else:
                _holidays_cache = []

        return _holidays_cache
    except Exception as e:
        logger.error(f"[get_holidays] Failed: {e}", exc_info=True)
        return []


def is_holiday(dt_obj: datetime) -> bool:
    """Check if a given date is a holiday."""
    try:
        if dt_obj is None:
            return False

        # Check weekend
        if calendar.day_name[dt_obj.weekday()] in ('Saturday', 'Sunday'):
            return True

        # Check holiday list
        holidays = get_holidays() or []
        return to_date_str(dt_obj) in holidays
    except Exception as e:
        logger.error(f"Error checking holiday: {e}", exc_info=True)
        return False


def is_market_closed_for_the_day(dt_obj: Optional[datetime] = None) -> bool:
    """Check if market has closed for the day."""
    try:
        if dt_obj is None:
            dt_obj = datetime.now()

        if is_holiday(dt_obj):
            return True
        return dt_obj > get_market_end_time(dt_obj)
    except Exception as e:
        logger.error(f"Error checking if market is closed: {e}", exc_info=True)
        return True


def get_market_end_time(dt_obj: Optional[datetime] = None) -> datetime:
    """Market closes at 3:30 PM."""
    try:
        dt_obj = dt_obj or datetime.now()
        return get_time_of_day(15, 30, 0, dt_obj)
    except Exception as e:
        logger.error(f"[get_market_end_time] Failed: {e}", exc_info=True)
        return datetime.now()


def get_time_of_day(hours: int, minutes: int, seconds: int, dt_obj: Optional[datetime] = None) -> datetime:
    """Return datetime at given hours/minutes/seconds for the day of dt_obj."""
    try:
        dt_obj = dt_obj or datetime.now()
        return dt_obj.replace(hour=hours, minute=minutes, second=seconds, microsecond=0)
    except ValueError as e:
        logger.error(f"Invalid time values: hours={hours}, minutes={minutes}, seconds={seconds}: {e}")
        return dt_obj or datetime.now()
    except Exception as e:
        logger.error(f"[get_time_of_day] Failed: {e}", exc_info=True)
        return dt_obj or datetime.now()


def to_date_str(dt_obj: datetime) -> str:
    """Convert datetime to date string."""
    try:
        if dt_obj is None:
            return ""
        return dt_obj.strftime(DATE_FORMAT)
    except Exception as e:
        logger.error(f"[to_date_str] Failed: {e}", exc_info=True)
        return ""


def get_epoch(dt_obj: Optional[datetime] = None) -> Optional[int]:
    """Convert datetime to epoch seconds."""
    try:
        dt_obj = dt_obj or datetime.now()
        return int(dt_obj.timestamp())
    except Exception as e:
        logger.error(f"Error converting to epoch: {e}", exc_info=True)
        return None