# Utils.py - Cleaned up version with option methods removed
import asyncio
import calendar
import csv
import inspect
import json
import logging
import math
import os
import subprocess
import time
import urllib.request
from datetime import datetime, time as dt_time, timezone, timedelta
from pathlib import Path
from sys import platform
from typing import Optional, Union, List, Dict, Tuple, Any

import dateutil.parser
import pytz

from BaseEnums import POSITIVE, NEGATIVE

# Directories
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
STRATEGIES_DIR = BASE_DIR / 'Strategies'
LOG_DIR = BASE_DIR / 'Logs'
REC_DIR = BASE_DIR / 'Record'

logger = logging.getLogger(__name__)


class Utils:
    """# REFACTORED: All option-related methods moved to OptionUtils.py"""

    DATE_FORMAT = "%Y-%m-%d"
    TIME_FORMAT = "%H:%M:%S"
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    # --- Config loading ---
    @staticmethod
    def get_config(file_path: Union[str, Path]) -> Optional[dict]:
        """Load a JSON config file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config file {file_path}: {e}")
            return None

    @classmethod
    def get_holidays(cls) -> Optional[List[str]]:
        return cls.get_config(BASE_DIR / 'Config' / 'holidays.json')

    # --- Date/Time Utilities ---
    @staticmethod
    def round_off(price: float) -> float:
        """Round a price to 2 decimal places."""
        return round(price, 2)

    @staticmethod
    def round_to_nse_price(price: float) -> Optional[float]:
        """Round price to nearest 0.05 as per NSE rules."""
        try:
            if price is None or not isinstance(price, (int, float)):
                logger.error(f"Invalid price: {price}")
                return None
            return math.ceil(round(price, 2) * 20) / 20
        except Exception as e:
            logger.error(f"Error rounding to NSE price: {e}")
            return None

    @classmethod
    def is_holiday(cls, dt_obj: datetime) -> bool:
        """Check if a given date is a holiday."""
        try:
            if calendar.day_name[dt_obj.weekday()] in ('Saturday', 'Sunday'):
                return True
            holidays = cls.get_holidays() or []
            return cls.to_date_str(dt_obj) in holidays
        except Exception as e:
            logger.error(f"Error checking holiday: {e}")
            return False

    @classmethod
    def is_today_holiday(cls) -> bool:
        return cls.is_holiday(datetime.now())

    @classmethod
    def is_market_open(cls) -> bool:
        try:
            if cls.is_today_holiday():
                return False
            now = datetime.now()
            return cls.get_market_start_time() <= now <= cls.get_market_end_time()
        except Exception as e:
            logger.error(f"Error checking if market is open: {e}")
            return False

    @classmethod
    def is_market_closed_for_the_day(cls) -> bool:
        try:
            if cls.is_today_holiday():
                return True
            now = datetime.now()
            return now > cls.get_market_end_time()
        except Exception as e:
            logger.error(f"Error checking if market is closed: {e}")
            return True

    @classmethod
    def wait_till_market_opens(cls, wait: Optional[int] = None):
        """Sleep until market opens. If `wait` is set, sleep for that many seconds instead."""
        try:
            now = datetime.now()
            start_epoch = cls.get_epoch(cls.get_market_start_time())
            now_epoch = cls.get_epoch(now)
            wait_seconds = start_epoch - now_epoch
            if wait_seconds > 0:
                logger.info(f"Waiting {wait_seconds} seconds for market to open...")
                time.sleep(wait if wait is not None else wait_seconds)
        except Exception as e:
            logger.error(f"Error waiting for market to open: {e}")

    @staticmethod
    def get_epoch(dt_obj: Optional[datetime] = None) -> Optional[int]:
        """Convert datetime to epoch seconds."""
        try:
            dt_obj = dt_obj or datetime.now()
            return int(dt_obj.timestamp())
        except Exception as e:
            logger.error(f"Error converting to epoch: {e}")
            return None

    @classmethod
    def get_market_start_time(cls, dt_obj: Optional[datetime] = None) -> datetime:
        """Market opens at 9:15 AM."""
        if dt_obj is None:
            dt_obj = datetime.now()
        if not cls.is_market_closed_for_the_day():
            return cls.get_time_of_day(9, 30, 0, dt_obj)
        next_day = dt_obj + timedelta(days=1)
        while cls.is_holiday(next_day):
            next_day += timedelta(days=1)
        return cls.get_time_of_day(9, 30, 0, next_day)

    @staticmethod
    def get_market_end_time(dt_obj: Optional[datetime] = None) -> datetime:
        """Market closes at 3:29 PM."""
        dt_obj = dt_obj or datetime.now()
        return Utils.get_time_of_day(15, 25, 0, dt_obj)

    @staticmethod
    def is_near_market_close(buffer_minutes=10) -> bool:
        """
        Returns True if current time is within `buffer_minutes` of market close.
        """
        try:
            now = datetime.now().time()
            return now >= (dt_time(15, 30 - buffer_minutes // 1))
        except Exception as e:
            logger.error(f"Error in is_near_market_close: {e}")
            return False

    @staticmethod
    def get_time_of_day(hours: int, minutes: int, seconds: int, dt_obj: Optional[datetime] = None) -> datetime:
        """Return datetime at given hours/minutes/seconds for the day of dt_obj."""
        dt_obj = dt_obj or datetime.now()
        return dt_obj.replace(hour=hours, minute=minutes, second=seconds, microsecond=0)

    @staticmethod
    def to_date_str(dt_obj: datetime) -> str:
        """Convert datetime to date string."""
        return dt_obj.strftime(Utils.DATE_FORMAT)

    @staticmethod
    def to_datetime(date_str: str, time_str: str = "00:00:00") -> datetime:
        """Convert date string and optional time string to datetime."""
        try:
            return datetime.strptime(f"{date_str} {time_str}", f"{Utils.DATE_FORMAT} {Utils.TIME_FORMAT}")
        except Exception as e:
            logger.error(f"Error converting to datetime: {e}")
            return datetime.now()

    @staticmethod
    def is_debug() -> bool:
        return os.getenv('DEBUG', '').lower() in {'1', 'true', 'yes'}

    # --- File and Logging Utilities ---
    @classmethod
    def open_folder(cls, folder: str):
        target_path = cls.create_folder(folder)
        cls.open_file_or_folder(target_path)

    @staticmethod
    def create_folder(folder: str) -> Path:
        target_path = ROOT_DIR / folder
        target_path.mkdir(parents=True, exist_ok=True)
        return target_path

    @staticmethod
    def open_file_or_folder(target_path: Union[str, Path]):
        target_path = str(target_path)
        if platform == "win32":
            os.startfile(target_path)
        elif platform == "darwin":
            subprocess.Popen(["open", target_path])
        else:
            subprocess.Popen(["xdg-open", target_path])

    @classmethod
    def setup_and_return_log_path(cls, file_name: str) -> Path:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        today_folder = LOG_DIR / datetime.today().strftime('%Y-%m-%d')
        today_folder.mkdir(parents=True, exist_ok=True)
        log_file_name = f"{datetime.now().strftime('%H')}-{file_name}.log"
        return today_folder / log_file_name

    @classmethod
    def get_logger(cls, log_file: str, logger_name: str) -> logging.Logger:
        logger_i = logging.getLogger(logger_name)
        logger_i.setLevel(logging.DEBUG)
        if not logger_i.handlers:
            handler = logging.FileHandler(cls.setup_and_return_log_path(log_file), delay=True)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            logger_i.addHandler(handler)
        return logger_i

    @staticmethod
    def is_number(x: Any) -> bool:
        try:
            float(x)
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def convert_str_to_utc_datetime(str_datetime: str) -> datetime:
        return dateutil.parser.parse(str_datetime).replace(tzinfo=timezone.utc)

    @staticmethod
    def epoch_to_human_readable(epoch: int, str_format: str = "%Y-%m-%d %H:%M:%S") -> str:
        return datetime.fromtimestamp(epoch).strftime(str_format)

    @staticmethod
    def convert_all_dates_to_datetime(data: List[Dict[str, Any]]):
        if isinstance(data[0]['date_utc'], datetime):
            return
        for entry in data:
            entry['date_utc'] = dateutil.parser.parse(entry['date_utc'])

    @staticmethod
    def write_json_file(file_path: Union[str, Path] = 'secret.json', **kwargs):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(kwargs, f, indent=4)
        except Exception as e:
            logger.error(f"Error writing JSON file {file_path}: {e}")

    @staticmethod
    def load_json_file(json_file: Union[str, Path]) -> dict:
        try:
            with open(json_file, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading JSON file {json_file}: {e}")
            return {}

    @staticmethod
    def create_csv_if_not_exists(file_path: Union[str, Path], headers: Optional[List[str]] = None):
        file_path = Path(file_path)
        if not file_path.exists():
            try:
                with open(file_path, 'w', newline='') as file:
                    writer = csv.writer(file)
                    if headers:
                        writer.writerow(headers)
                logger.info(f"{file_path} created with headers: {headers}")
            except Exception as e:
                logger.error(f"Error creating CSV file {file_path}: {e}")

    @staticmethod
    def append_to_csv(df, file: Union[str, Path]):
        try:
            Utils.create_csv_if_not_exists(file, headers=list(df.columns))
            with open(file, 'r') as f:
                header = next(csv.reader(f))
            columns = list(df.columns)
            for column in set(header) - set(columns):
                df[column] = ''
            df = df[header]
            df.to_csv(file, index=False, header=False, mode='a')
        except Exception as e:
            logger.error(f"Error appending to CSV file {file}: {e}")

    # --- Trading Calculations ---
    @staticmethod
    def get_interval_unit_and_measurement(interval: str) -> tuple[str, int]:
        """
        Extracts the unit (e.g., 's', 'm', 'h', 'd') and the numeric value from an interval string like '30s', '5m'.
        """
        try:
            if not interval or len(interval) < 2:
                raise ValueError(f"Invalid interval string: '{interval}'")

            unit = interval[-1]
            measurement = int(interval[:-1])

            if unit not in {'S', 's', 'M', 'm', 'H', 'h', 'D', 'd'}:
                raise ValueError(f"Unsupported interval unit: '{unit}'")

            return unit, measurement

        except Exception as e:
            logger.error(f"Error parsing interval '{interval}': {e}", exc_info=True)
            raise

    @staticmethod
    def get_interval_minutes(interval_unit: str, interval_measurement: int) -> int:
        try:
            if interval_unit.lower() == 's':
                return interval_measurement // 60
            if interval_unit.lower() == 'h':
                return interval_measurement * 60
            if interval_unit.lower() == 'm':
                return interval_measurement
            if interval_unit.lower() == 'd':
                return interval_measurement * 24 * 60
            raise ValueError("Invalid interval unit.")
        except Exception as e:
            logger.error(f"Error getting interval minutes: {e}")
            return 0

    @staticmethod
    def is_latest_date(minutes: int, latest_date: datetime) -> bool:
        current_date = latest_date + timedelta(minutes=minutes)
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        return current_date >= now - timedelta(minutes=minutes)

    @staticmethod
    def calculate_shares_to_buy(balance: float, price: float, lot_size: int = 75) -> int:
        """
        Calculate the number of shares to buy based on balance, price, and lot size.
        :return: Total shares to buy (in multiples of lot_size), or 0 if not enough balance.
        """
        try:
            if balance is None or price is None or lot_size is None:
                logger.warning(
                    f"Missing one or more required inputs: balance={balance}, price={price}, lot_size={lot_size}.")
                return 0

            if balance <= 0 or price <= 0 or lot_size <= 0:
                logger.warning(
                    f"Invalid input values: balance={balance}, price={price}, lot_size={lot_size}")
                return 0

            lot_cost = price * lot_size
            lots_may_buy = int(balance // lot_cost)
            total_shares = lots_may_buy * lot_size

            logger.info(f"Balance: {balance}, Price: {price}, Lot Size: {lot_size}, Shares to Buy: {total_shares}")
            return total_shares

        except Exception as e:
            logger.error(f"Error calculating shares to buy: {e}", exc_info=True)
            return 0

    @staticmethod
    def percentage_above_or_below(price: float, percentage: float = 1, side: str = POSITIVE) -> float:
        """
        Return price adjusted by a given percentage above or below, rounded to NSE price.
        """
        try:
            if price is None or not isinstance(price, (int, float)):
                raise ValueError("Invalid price")
            if side == POSITIVE:
                adjusted = price * (1 + (percentage / 100))
            elif side == NEGATIVE:
                adjusted = price * (1 - (percentage / 100))
            else:
                adjusted = price
            return Utils.round_to_nse_price(adjusted) or 0
        except Exception as e:
            logger.error(f"Error calculating percentage above or below: {e}")
            return price

    @staticmethod
    def check_sideway_time() -> bool:
        """
        Check if the current time is between 12:00 and 14:00.
        """
        try:
            now = datetime.now().time()
            start_time = dt_time(12, 0, 0)
            end_time = dt_time(14, 0, 0)
            return start_time <= now <= end_time
        except Exception as e:
            logger.error(f"Error in check sideways time: {e}")
            return False

    @staticmethod
    def maybe_await(coro):
        if inspect.iscoroutine(coro):
            try:
                loop = asyncio.get_running_loop()
                return loop.run_until_complete(coro)
            except RuntimeError:
                return asyncio.run(coro)
        return coro

    @staticmethod
    def is_history_updated(last_updated, interval) -> bool:
        try:
            if last_updated:
                unit, measurement = Utils.get_interval_unit_and_measurement(interval)
                if unit.lower() == 's':
                    updated_upto = last_updated + measurement
                elif unit.lower() == 'm':
                    interval_minutes = Utils.get_interval_minutes(unit, measurement)
                    updated_upto = last_updated + (interval_minutes * 60)
                else:
                    updated_upto = 0

                return Utils.get_epoch() < updated_upto
            return False
        except Exception as e:
            logger.error(f"Error in is_history_updated: {e}")
            return False

    @staticmethod
    def log_trade_to_csv(trade_data: dict, file_path="trade_log.csv"):
        file_exists = os.path.isfile(file_path)
        try:
            with open(file_path, mode='a', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=trade_data.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(trade_data)
        except Exception as e:
            logger.error(f"Error logging trade to CSV {file_path}: {e}")

    @staticmethod
    def is_internet_available(timeout=3):
        try:
            urllib.request.urlopen("https://www.google.com", timeout=timeout)
            return True
        except Exception:
            return False

    @staticmethod
    def load_access_token(token_path=None):
        """
        Loads the Fyers API access token from the given file.
        Returns the token string, or None if not found.
        """
        CONFIG_PATH = os.getenv("CONFIG_PATH", "config")
        token_path = token_path or os.path.join(CONFIG_PATH, "fyers_token.json")
        try:
            with open(token_path, "r") as f:
                try:
                    token_obj = json.load(f)
                    token = token_obj.get("access_token")
                except Exception:
                    f.seek(0)
                    token_raw = f.read().strip()
                    try:
                        data = json.loads(token_raw)
                        token = data.get("access_token")
                    except Exception:
                        token = token_raw
            if not token:
                logger.error("Token not found! Please check token file or authentication flow.")
                return None
            return token
        except FileNotFoundError:
            logger.error(f"Token file not found at: {token_path}")
            return None
        except Exception as e:
            logger.error(f"Error reading access token: {e!r}", exc_info=True)
            return None