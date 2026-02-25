# Utils.py - Cleaned up version with option methods removed
import asyncio
import calendar
import csv
import inspect
import json
import logging
import logging.handlers
import math
import os
import subprocess
import time
import urllib.request
from datetime import datetime, time as dt_time, timezone, timedelta
from pathlib import Path
from sys import platform
from typing import Optional, Union, List, Dict, Tuple, Any
import traceback

import dateutil.parser
import pytz

from BaseEnums import POSITIVE, NEGATIVE

# Directories
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
STRATEGIES_DIR = BASE_DIR / 'Strategies'
LOG_DIR = BASE_DIR / 'Logs'
REC_DIR = BASE_DIR / 'Record'

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class Utils:
    """# REFACTORED: All option-related methods moved to OptionUtils.py

    BUG #4 FIX: Market start time corrected to 9:15 AM (was 9:30)
    FEATURE 1: Added risk management helpers
    FEATURE 4: Added notification helpers
    FEATURE 5: Added P&L tracking helpers
    FEATURE 6: Added MTF filter helpers
    """

    DATE_FORMAT = "%Y-%m-%d"
    TIME_FORMAT = "%H:%M:%S"
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    # Market hours constants (BUG #4 FIX)
    MARKET_OPEN_HOUR = 9
    MARKET_OPEN_MINUTE = 15
    MARKET_CLOSE_HOUR = 15
    MARKET_CLOSE_MINUTE = 30

    # --- Config loading ---
    @staticmethod
    def get_config(file_path: Union[str, Path]) -> Optional[dict]:
        """Load a JSON config file."""
        try:
            if file_path is None:
                logger.error("get_config called with None file_path")
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError as e:
            logger.error(f"Config file not found: {file_path}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file {file_path}: {e}")
            return None
        except PermissionError as e:
            logger.error(f"Permission denied reading config file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading config file {file_path}: {e}", exc_info=True)
            return None

    @classmethod
    def get_holidays(cls) -> Optional[List[str]]:
        """Get list of holiday dates."""
        try:
            return cls.get_config(BASE_DIR / 'Config' / 'holidays.json')
        except Exception as e:
            logger.error(f"[get_holidays] Failed: {e}", exc_info=True)
            return None

    # --- Date/Time Utilities ---
    @staticmethod
    def round_off(price: float) -> float:
        """Round a price to 2 decimal places."""
        try:
            if price is None:
                logger.warning("round_off called with None price")
                return 0.0
            return round(price, 2)
        except Exception as e:
            logger.error(f"[round_off] Failed: {e}", exc_info=True)
            return 0.0

    @staticmethod
    def round_to_nse_price(price: float) -> Optional[float]:
        """Round price to nearest 0.05 as per NSE rules."""
        try:
            if price is None or not isinstance(price, (int, float)):
                logger.error(f"Invalid price: {price}")
                return None
            return math.ceil(round(price, 2) * 20) / 20
        except Exception as e:
            logger.error(f"Error rounding to NSE price: {e}", exc_info=True)
            return None

    @classmethod
    def is_holiday(cls, dt_obj: datetime) -> bool:
        """Check if a given date is a holiday."""
        try:
            if dt_obj is None:
                logger.warning("is_holiday called with None dt_obj")
                return False

            if calendar.day_name[dt_obj.weekday()] in ('Saturday', 'Sunday'):
                return True
            holidays = cls.get_holidays() or []
            return cls.to_date_str(dt_obj) in holidays
        except Exception as e:
            logger.error(f"Error checking holiday: {e}", exc_info=True)
            return False

    @classmethod
    def is_today_holiday(cls) -> bool:
        """Check if today is a holiday."""
        try:
            return cls.is_holiday(datetime.now())
        except Exception as e:
            logger.error(f"[is_today_holiday] Failed: {e}", exc_info=True)
            return False

    @classmethod
    def is_market_open(cls) -> bool:
        """Check if market is currently open."""
        try:
            if cls.is_today_holiday():
                return False
            now = datetime.now()
            return cls.get_market_start_time() <= now <= cls.get_market_end_time()
        except Exception as e:
            logger.error(f"Error checking if market is open: {e}", exc_info=True)
            return False

    @classmethod
    def is_market_closed_for_the_day(cls) -> bool:
        """Check if market has closed for the day."""
        try:
            if cls.is_today_holiday():
                return True
            now = datetime.now()
            return now > cls.get_market_end_time()
        except Exception as e:
            logger.error(f"Error checking if market is closed: {e}", exc_info=True)
            return True

    @classmethod
    def wait_till_market_opens(cls, wait: Optional[int] = None):
        """Sleep until market opens. If `wait` is set, sleep for that many seconds instead."""
        try:
            now = datetime.now()
            start_epoch = cls.get_epoch(cls.get_market_start_time())
            now_epoch = cls.get_epoch(now)

            if start_epoch is None or now_epoch is None:
                logger.error("Failed to get epoch times")
                return

            wait_seconds = start_epoch - now_epoch
            if wait_seconds > 0:
                logger.info(f"Waiting {wait_seconds} seconds for market to open...")
                time.sleep(wait if wait is not None else wait_seconds)
        except Exception as e:
            logger.error(f"Error waiting for market to open: {e}", exc_info=True)

    @staticmethod
    def get_epoch(dt_obj: Optional[datetime] = None) -> Optional[int]:
        """Convert datetime to epoch seconds."""
        try:
            dt_obj = dt_obj or datetime.now()
            return int(dt_obj.timestamp())
        except Exception as e:
            logger.error(f"Error converting to epoch: {e}", exc_info=True)
            return None

    @classmethod
    def get_market_start_time(cls, dt_obj: Optional[datetime] = None) -> datetime:
        """
        BUG #4 FIX: Market opens at 9:15 AM (was 9:30)
        """
        try:
            if dt_obj is None:
                dt_obj = datetime.now()

            if not cls.is_market_closed_for_the_day():
                # BUG #4 FIX: Changed from 9:30 to 9:15
                return cls.get_time_of_day(cls.MARKET_OPEN_HOUR, cls.MARKET_OPEN_MINUTE, 0, dt_obj)

            next_day = dt_obj + timedelta(days=1)
            max_days = 30  # Prevent infinite loop
            days_checked = 0

            while cls.is_holiday(next_day) and days_checked < max_days:
                next_day += timedelta(days=1)
                days_checked += 1

            # BUG #4 FIX: Changed from 9:30 to 9:15
            return cls.get_time_of_day(cls.MARKET_OPEN_HOUR, cls.MARKET_OPEN_MINUTE, 0, next_day)
        except Exception as e:
            logger.error(f"[get_market_start_time] Failed: {e}", exc_info=True)
            return datetime.now()

    @staticmethod
    def get_market_end_time(dt_obj: Optional[datetime] = None) -> datetime:
        """Market closes at 3:30 PM."""
        try:
            dt_obj = dt_obj or datetime.now()
            return Utils.get_time_of_day(15, 30, 0, dt_obj)
        except Exception as e:
            logger.error(f"[get_market_end_time] Failed: {e}", exc_info=True)
            return datetime.now()

    @staticmethod
    def is_near_market_close(buffer_minutes=10) -> bool:
        """
        Returns True if current time is within `buffer_minutes` of market close.
        """
        try:
            now = datetime.now().time()
            close_time = dt_time(15, 30)
            buffer_time = (close_time.hour * 60 + close_time.minute - buffer_minutes)
            buffer_hour = buffer_time // 60
            buffer_min = buffer_time % 60
            buffer_dt = dt_time(buffer_hour, buffer_min)
            return now >= buffer_dt
        except Exception as e:
            logger.error(f"Error in is_near_market_close: {e}", exc_info=True)
            return False

    @staticmethod
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

    @staticmethod
    def to_date_str(dt_obj: datetime) -> str:
        """Convert datetime to date string."""
        try:
            if dt_obj is None:
                logger.warning("to_date_str called with None dt_obj")
                return ""
            return dt_obj.strftime(Utils.DATE_FORMAT)
        except Exception as e:
            logger.error(f"[to_date_str] Failed: {e}", exc_info=True)
            return ""

    @staticmethod
    def to_datetime(date_str: str, time_str: str = "00:00:00") -> datetime:
        """Convert date string and optional time string to datetime."""
        try:
            if not date_str:
                logger.warning("to_datetime called with empty date_str")
                return datetime.now()

            return datetime.strptime(f"{date_str} {time_str}", f"{Utils.DATE_FORMAT} {Utils.TIME_FORMAT}")
        except ValueError as e:
            logger.error(f"Invalid date/time format: date={date_str}, time={time_str}: {e}")
            return datetime.now()
        except Exception as e:
            logger.error(f"Error converting to datetime: {e}", exc_info=True)
            return datetime.now()

    @staticmethod
    def is_debug() -> bool:
        """Check if debug mode is enabled."""
        try:
            return os.getenv('DEBUG', '').lower() in {'1', 'true', 'yes'}
        except Exception as e:
            logger.error(f"[is_debug] Failed: {e}", exc_info=True)
            return False

    # --- File and Logging Utilities ---
    @classmethod
    def open_folder(cls, folder: str):
        """Open a folder in file explorer."""
        try:
            if not folder:
                logger.warning("open_folder called with empty folder")
                return

            target_path = cls.create_folder(folder)
            cls.open_file_or_folder(target_path)
        except Exception as e:
            logger.error(f"[open_folder] Failed for {folder}: {e}", exc_info=True)

    @staticmethod
    def create_folder(folder: str) -> Path:
        """Create a folder if it doesn't exist."""
        try:
            if not folder:
                logger.warning("create_folder called with empty folder")
                return ROOT_DIR

            target_path = ROOT_DIR / folder
            target_path.mkdir(parents=True, exist_ok=True)
            return target_path
        except PermissionError as e:
            logger.error(f"Permission denied creating folder {folder}: {e}")
            return ROOT_DIR
        except Exception as e:
            logger.error(f"[create_folder] Failed for {folder}: {e}", exc_info=True)
            return ROOT_DIR

    @staticmethod
    def open_file_or_folder(target_path: Union[str, Path]):
        """Open a file or folder with system default application."""
        try:
            if target_path is None:
                logger.warning("open_file_or_folder called with None target_path")
                return

            target_path = str(target_path)
            if platform == "win32":
                os.startfile(target_path)
            elif platform == "darwin":
                subprocess.Popen(["open", target_path])
            else:
                subprocess.Popen(["xdg-open", target_path])
        except FileNotFoundError as e:
            logger.error(f"File not found: {target_path}: {e}")
        except Exception as e:
            logger.error(f"[open_file_or_folder] Failed for {target_path}: {e}", exc_info=True)

    @classmethod
    def setup_and_return_log_path(cls, file_name: str) -> Path:
        """Setup log directory and return log file path."""
        try:
            if not file_name:
                logger.warning("setup_and_return_log_path called with empty file_name")
                file_name = "default.log"

            LOG_DIR.mkdir(parents=True, exist_ok=True)
            today_folder = LOG_DIR / datetime.today().strftime('%Y-%m-%d')
            today_folder.mkdir(parents=True, exist_ok=True)
            log_file_name = f"{datetime.now().strftime('%H')}-{file_name}.log"
            return today_folder / log_file_name
        except PermissionError as e:
            logger.error(f"Permission denied creating log directory: {e}")
            return LOG_DIR / f"fallback-{file_name}"
        except Exception as e:
            logger.error(f"[setup_and_return_log_path] Failed: {e}", exc_info=True)
            return LOG_DIR / f"error-{file_name}"

    @classmethod
    def get_logger(cls, log_file: str, logger_name: str) -> logging.Logger:
        """Get or create a logger with file handler."""
        try:
            if not log_file or not logger_name:
                logger.warning(f"get_logger called with empty params: log_file={log_file}, logger_name={logger_name}")
                return logging.getLogger(logger_name or "default")

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
        except Exception as e:
            logger.error(f"[get_logger] Failed: {e}", exc_info=True)
            return logging.getLogger(logger_name or "default")

    @staticmethod
    def is_number(x: Any) -> bool:
        """Check if value can be converted to a number."""
        try:
            if x is None:
                return False
            float(x)
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def convert_str_to_utc_datetime(str_datetime: str) -> datetime:
        """Convert string to UTC datetime."""
        try:
            if not str_datetime:
                logger.warning("convert_str_to_utc_datetime called with empty string")
                return datetime.now(timezone.utc)

            return dateutil.parser.parse(str_datetime).replace(tzinfo=timezone.utc)
        except Exception as e:
            logger.error(f"[convert_str_to_utc_datetime] Failed: {e}", exc_info=True)
            return datetime.now(timezone.utc)

    @staticmethod
    def epoch_to_human_readable(epoch: int, str_format: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Convert epoch to human readable string."""
        try:
            if epoch is None:
                logger.warning("epoch_to_human_readable called with None epoch")
                return ""

            return datetime.fromtimestamp(epoch).strftime(str_format)
        except ValueError as e:
            logger.error(f"Invalid epoch value {epoch}: {e}")
            return ""
        except Exception as e:
            logger.error(f"[epoch_to_human_readable] Failed: {e}", exc_info=True)
            return ""

    @staticmethod
    def convert_all_dates_to_datetime(data: List[Dict[str, Any]]):
        """Convert all date_utc fields in data list to datetime objects."""
        try:
            if not data:
                return

            if not isinstance(data, list):
                logger.warning(f"convert_all_dates_to_datetime called with non-list: {type(data)}")
                return

            if data and isinstance(data[0].get('date_utc'), datetime):
                return

            for entry in data:
                if isinstance(entry, dict) and 'date_utc' in entry:
                    try:
                        entry['date_utc'] = dateutil.parser.parse(entry['date_utc'])
                    except Exception as e:
                        logger.warning(f"Failed to parse date_utc: {e}")
                        continue
        except Exception as e:
            logger.error(f"[convert_all_dates_to_datetime] Failed: {e}", exc_info=True)

    @staticmethod
    def write_json_file(file_path: Union[str, Path] = 'secret.json', **kwargs):
        """Write kwargs to JSON file."""
        temp_file = None
        try:
            if file_path is None:
                logger.error("write_json_file called with None file_path")
                return

            file_path = Path(file_path)
            temp_file = file_path.with_suffix('.tmp')

            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(kwargs, f, indent=4)

            os.replace(temp_file, file_path)

        except PermissionError as e:
            logger.error(f"Permission denied writing JSON file {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error writing JSON file {file_path}: {e}", exc_info=True)
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass

    @staticmethod
    def load_json_file(json_file: Union[str, Path]) -> dict:
        """Load JSON file and return as dict."""
        try:
            if json_file is None:
                logger.error("load_json_file called with None json_file")
                return {}

            with open(json_file, encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"JSON file not found: {json_file}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in file {json_file}: {e}")
            return {}
        except PermissionError as e:
            logger.error(f"Permission denied reading JSON file {json_file}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading JSON file {json_file}: {e}", exc_info=True)
            return {}

    @staticmethod
    def create_csv_if_not_exists(file_path: Union[str, Path], headers: Optional[List[str]] = None):
        """Create CSV file with headers if it doesn't exist."""
        try:
            if file_path is None:
                logger.error("create_csv_if_not_exists called with None file_path")
                return

            file_path = Path(file_path)
            if not file_path.exists():
                # Ensure directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(file_path, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)
                    if headers:
                        writer.writerow(headers)
                logger.info(f"{file_path} created with headers: {headers}")
        except PermissionError as e:
            logger.error(f"Permission denied creating CSV file {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error creating CSV file {file_path}: {e}", exc_info=True)

    @staticmethod
    def append_to_csv(df, file: Union[str, Path]):
        """Append DataFrame to CSV file."""
        try:
            if df is None or df.empty:
                logger.warning("append_to_csv called with empty DataFrame")
                return

            if file is None:
                logger.error("append_to_csv called with None file")
                return

            Utils.create_csv_if_not_exists(file, headers=list(df.columns))

            with open(file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader) if reader else []

            columns = list(df.columns)
            for column in set(header) - set(columns):
                df[column] = ''

            # Reorder columns to match header
            df = df[header] if header else df

            df.to_csv(file, index=False, header=False, mode='a', encoding='utf-8')

        except Exception as e:
            logger.error(f"Error appending to CSV file {file}: {e}", exc_info=True)

    # --- Trading Calculations ---
    @staticmethod
    def get_interval_unit_and_measurement(interval: str) -> tuple[str, int]:
        """
        Extracts the unit (e.g., 's', 'm', 'h', 'd') and the numeric value from an interval string like '30s', '5m'.
        """
        try:
            if not interval or len(interval) < 2:
                logger.error(f"Invalid interval string: '{interval}'")
                return '', 0

            unit = interval[-1]
            measurement = int(interval[:-1])

            if unit.lower() not in {'s', 'm', 'h', 'd'}:
                logger.error(f"Unsupported interval unit: '{unit}'")
                return '', 0

            return unit, measurement

        except ValueError as e:
            logger.error(f"Invalid interval format '{interval}': {e}")
            return '', 0
        except Exception as e:
            logger.error(f"Error parsing interval '{interval}': {e}", exc_info=True)
            return '', 0

    @staticmethod
    def get_interval_minutes(interval_unit: str, interval_measurement: int) -> int:
        """Convert interval to minutes."""
        try:
            if not interval_unit:
                return 0

            unit = interval_unit.lower()
            if unit == 's':
                return interval_measurement // 60
            if unit == 'h':
                return interval_measurement * 60
            if unit == 'm':
                return interval_measurement
            if unit == 'd':
                return interval_measurement * 24 * 60
            return 0
        except Exception as e:
            logger.error(f"Error getting interval minutes: {e}", exc_info=True)
            return 0

    @staticmethod
    def is_latest_date(minutes: int, latest_date: datetime) -> bool:
        """Check if date is latest based on minutes."""
        try:
            if minutes is None or latest_date is None:
                return False

            current_date = latest_date + timedelta(minutes=minutes)
            now = datetime.now(pytz.timezone('Asia/Kolkata'))
            return current_date >= now - timedelta(minutes=minutes)
        except Exception as e:
            logger.error(f"[is_latest_date] Failed: {e}", exc_info=True)
            return False

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

            logger.debug(f"Balance: {balance}, Price: {price}, Lot Size: {lot_size}, Shares to Buy: {total_shares}")
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
                logger.warning(f"Invalid price: {price}")
                return price or 0

            if side == POSITIVE:
                adjusted = price * (1 + (percentage / 100))
            elif side == NEGATIVE:
                adjusted = price * (1 - (percentage / 100))
            else:
                adjusted = price

            rounded = Utils.round_to_nse_price(adjusted)
            return rounded if rounded is not None else adjusted

        except Exception as e:
            logger.error(f"Error calculating percentage above or below: {e}", exc_info=True)
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
            logger.error(f"Error in check sideways time: {e}", exc_info=True)
            return False

    # ==================================================================
    # FEATURE 1: Risk Management Helpers
    # ==================================================================

    @staticmethod
    def calculate_drawdown(peak: float, current: float) -> float:
        """
        Calculate drawdown percentage from peak.

        Args:
            peak: Peak value
            current: Current value

        Returns:
            Drawdown percentage (positive number)
        """
        try:
            if peak is None or current is None or peak == 0:
                return 0.0
            return max(0, (peak - current) / peak * 100)
        except Exception as e:
            logger.error(f"[calculate_drawdown] Failed: {e}", exc_info=True)
            return 0.0

    @staticmethod
    def calculate_risk_per_trade(account_balance: float, risk_percent: float, stop_loss_percent: float) -> float:
        """
        Calculate position size based on risk per trade.

        Args:
            account_balance: Total account balance
            risk_percent: Percentage of account to risk per trade (e.g., 2 for 2%)
            stop_loss_percent: Stop loss percentage (positive number)

        Returns:
            Position size in rupees
        """
        try:
            if account_balance <= 0 or risk_percent <= 0 or stop_loss_percent <= 0:
                return 0.0
            risk_amount = account_balance * (risk_percent / 100)
            return risk_amount / (stop_loss_percent / 100)
        except Exception as e:
            logger.error(f"[calculate_risk_per_trade] Failed: {e}", exc_info=True)
            return 0.0

    # ==================================================================
    # FEATURE 4: Notification Helpers
    # ==================================================================

    @staticmethod
    def format_currency(amount: float, include_symbol: bool = True) -> str:
        """
        Format amount as currency.

        Args:
            amount: Amount to format
            include_symbol: Whether to include ₹ symbol

        Returns:
            Formatted string (e.g., "₹1,234.56" or "1,234.56")
        """
        try:
            if amount is None:
                amount = 0.0

            if abs(amount) >= 1000:
                formatted = f"{amount:,.2f}"
            else:
                formatted = f"{amount:.2f}"

            return f"₹{formatted}" if include_symbol else formatted
        except Exception as e:
            logger.error(f"[format_currency] Failed: {e}", exc_info=True)
            return f"₹{amount:.2f}" if amount else "₹0.00"

    @staticmethod
    def format_percentage(value: float, include_sign: bool = True) -> str:
        """
        Format as percentage.

        Args:
            value: Value to format (e.g., 0.15 for 15%)
            include_sign: Whether to include +/-

        Returns:
            Formatted string (e.g., "+15.0%" or "15.0%")
        """
        try:
            percent = value * 100
            if include_sign and percent > 0:
                return f"+{percent:.1f}%"
            return f"{percent:.1f}%"
        except Exception as e:
            logger.error(f"[format_percentage] Failed: {e}", exc_info=True)
            return f"{value:.1f}%"

    # ==================================================================
    # FEATURE 5: P&L Tracking Helpers
    # ==================================================================

    @staticmethod
    def calculate_pnl(entry_price: float, exit_price: float, quantity: int) -> float:
        """
        Calculate profit/loss.

        Args:
            entry_price: Entry price
            exit_price: Exit price
            quantity: Quantity traded

        Returns:
            P&L amount
        """
        try:
            if entry_price is None or exit_price is None or quantity is None:
                return 0.0
            return (exit_price - entry_price) * quantity
        except Exception as e:
            logger.error(f"[calculate_pnl] Failed: {e}", exc_info=True)
            return 0.0

    @staticmethod
    def calculate_pnl_percentage(entry_price: float, exit_price: float) -> float:
        """
        Calculate P&L as percentage.

        Args:
            entry_price: Entry price
            exit_price: Exit price

        Returns:
            P&L percentage (e.g., 0.15 for 15%)
        """
        try:
            if entry_price is None or exit_price is None or entry_price == 0:
                return 0.0
            return (exit_price - entry_price) / entry_price
        except Exception as e:
            logger.error(f"[calculate_pnl_percentage] Failed: {e}", exc_info=True)
            return 0.0

    @staticmethod
    def get_trade_duration(start_time: datetime, end_time: Optional[datetime] = None) -> str:
        """
        Get human-readable trade duration.

        Args:
            start_time: Trade start time
            end_time: Trade end time (defaults to now)

        Returns:
            Duration string (e.g., "2h 15m")
        """
        try:
            if start_time is None:
                return "0m"

            end = end_time or datetime.now()
            duration = end - start_time

            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60

            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"
        except Exception as e:
            logger.error(f"[get_trade_duration] Failed: {e}", exc_info=True)
            return "0m"

    # ==================================================================
    # FEATURE 6: MTF Filter Helpers
    # ==================================================================

    @staticmethod
    def get_mtf_history_days(timeframe: str) -> int:
        """
        Get recommended history days for a timeframe.

        Args:
            timeframe: Timeframe string (e.g., "1", "5", "15")

        Returns:
            Number of days of history needed
        """
        try:
            # Default recommendations
            days_map = {
                "1": 2,
                "5": 5,
                "15": 15,
                "30": 30,
                "60": 60,
            }
            return days_map.get(str(timeframe), 30)
        except Exception as e:
            logger.error(f"[get_mtf_history_days] Failed: {e}", exc_info=True)
            return 30

    @staticmethod
    def validate_timeframe(timeframe: str) -> bool:
        """
        Validate a timeframe string.

        Args:
            timeframe: Timeframe to validate

        Returns:
            True if valid
        """
        try:
            if not timeframe:
                return False
            if timeframe.isdigit():
                tf_int = int(timeframe)
                return 1 <= tf_int <= 1440
            return False
        except Exception as e:
            logger.error(f"[validate_timeframe] Failed: {e}", exc_info=True)
            return False

    @staticmethod
    def maybe_await(coro):
        """Await coroutine if needed."""
        try:
            if inspect.iscoroutine(coro):
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        # Can't run coroutine in running loop
                        logger.warning("Cannot run coroutine in running loop")
                        return None
                    return loop.run_until_complete(coro)
                except RuntimeError:
                    return asyncio.run(coro)
            return coro
        except Exception as e:
            logger.error(f"[maybe_await] Failed: {e}", exc_info=True)
            return None

    @staticmethod
    def is_history_updated(last_updated, interval) -> bool:
        """Check if history has been updated."""
        try:
            if last_updated is None or interval is None:
                return False

            unit, measurement = Utils.get_interval_unit_and_measurement(interval)
            if not unit:
                return False

            if unit.lower() == 's':
                updated_upto = last_updated + measurement
            elif unit.lower() == 'm':
                interval_minutes = Utils.get_interval_minutes(unit, measurement)
                updated_upto = last_updated + (interval_minutes * 60)
            else:
                updated_upto = 0

            epoch = Utils.get_epoch()
            return epoch is not None and epoch < updated_upto if updated_upto else False

        except Exception as e:
            logger.error(f"Error in is_history_updated: {e}", exc_info=True)
            return False

    @staticmethod
    def log_trade_to_csv(trade_data: dict, file_path="trade_log.csv"):
        """Log trade data to CSV."""
        try:
            if trade_data is None:
                logger.warning("log_trade_to_csv called with None trade_data")
                return

            if not file_path:
                logger.warning("log_trade_to_csv called with empty file_path")
                return

            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_exists = file_path.is_file()

            with open(file_path, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=trade_data.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(trade_data)
        except Exception as e:
            logger.error(f"Error logging trade to CSV {file_path}: {e}", exc_info=True)

    @staticmethod
    def is_internet_available(timeout=3) -> bool:
        """Check if internet is available."""
        try:
            urllib.request.urlopen("https://www.google.com", timeout=timeout)
            return True
        except Exception:
            return False

    @staticmethod
    def load_access_token(token_path=None) -> Optional[str]:
        """
        Loads the Fyers API access token from the given file.
        Returns the token string, or None if not found.
        """
        try:
            CONFIG_PATH = os.getenv("CONFIG_PATH", "config")
            token_path = token_path or os.path.join(CONFIG_PATH, "fyers_token.json")

            if not os.path.exists(token_path):
                logger.error(f"Token file not found at: {token_path}")
                return None

            with open(token_path, "r", encoding='utf-8') as f:
                try:
                    token_obj = json.load(f)
                    token = token_obj.get("access_token")
                    if token:
                        return token
                except json.JSONDecodeError:
                    f.seek(0)
                    token_raw = f.read().strip()
                    # Try to parse as JSON again
                    try:
                        data = json.loads(token_raw)
                        token = data.get("access_token")
                        if token:
                            return token
                    except:
                        # Return raw if it looks like a token (no spaces, reasonable length)
                        if token_raw and len(token_raw) > 50 and ' ' not in token_raw:
                            return token_raw

            logger.error("Token not found! Please check token file or authentication flow.")
            return None

        except PermissionError as e:
            logger.error(f"Permission denied reading token file: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading access token: {e!r}", exc_info=True)
            return None

    # Rule 8: Cleanup method
    @classmethod
    def cleanup(cls):
        """Clean up resources (minimal for this class)."""
        try:
            logger.info("[Utils] Cleanup completed")
        except Exception as e:
            logger.error(f"[Utils.cleanup] Error: {e}", exc_info=True)