import json
import os
import logging
import logging.handlers
from typing import Any, Dict, Optional
import traceback

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class DailyTradeSetting:
    DEFAULTS = {
        "exchange": "NSE",
        "week": 0,
        "derivative": "NIFTY50",
        "lot_size": 75,
        "call_lookback": 0,
        "put_lookback": 0,
        "history_interval": "2m",
        "max_num_of_option": 1800,
        "lower_percentage": 0,
        "cancel_after": 5,
        "capital_reserve": 0,
        "sideway_zone_trade": False
    }

    # Type mapping for validation
    FIELD_TYPES = {
        "exchange": str,
        "week": int,
        "derivative": str,
        "lot_size": int,
        "call_lookback": int,
        "put_lookback": int,
        "history_interval": str,
        "max_num_of_option": int,
        "lower_percentage": float,
        "cancel_after": int,
        "capital_reserve": int,
        "sideway_zone_trade": bool
    }

    def __init__(self, json_file: str = 'config/daily_trade_setting.json'):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if not isinstance(json_file, str):
                logger.error(f"json_file must be string, got {type(json_file)}. Using default.")
                json_file = 'config/daily_trade_setting.json'

            self.json_file = json_file
            self.data = dict(self.DEFAULTS)
            self.load()

            logger.info(f"DailyTradeSetting initialized with file: {self.json_file}")

        except Exception as e:
            logger.critical(f"[DailyTradeSetting.__init__] Failed: {e}", exc_info=True)
            # Still set basic attributes to prevent crashes
            self.json_file = json_file if isinstance(json_file, str) else 'config/daily_trade_setting.json'
            self.data = dict(self.DEFAULTS)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.json_file = 'config/daily_trade_setting.json'
        self.data: Dict[str, Any] = {}
        self._loaded = False
        self._load_attempts = 0
        self.MAX_LOAD_ATTEMPTS = 3

    def _validate_and_convert(self, key: str, value: Any) -> Any:
        """Validate and convert value to the correct type"""
        try:
            # Rule 6: Input validation
            if not isinstance(key, str):
                logger.warning(f"_validate_and_convert called with non-string key: {key}")
                return self.DEFAULTS.get(key, None) if key in self.DEFAULTS else None

            expected_type = self.FIELD_TYPES.get(key, str)

            if value is None:
                logger.debug(f"Value for {key} is None, using default")
                return self.DEFAULTS[key]

            try:
                if expected_type == bool:
                    # Handle various boolean representations
                    if isinstance(value, str):
                        return value.lower() in ('true', '1', 'yes', 'on')
                    return bool(value)

                elif expected_type == int:
                    # Handle both int and float strings
                    if isinstance(value, (int, float)):
                        return int(value)
                    elif isinstance(value, str):
                        # Try to convert string to int, handle floats in strings
                        try:
                            return int(float(value.strip()))
                        except (ValueError, TypeError):
                            return self.DEFAULTS[key]
                    else:
                        return self.DEFAULTS[key]

                elif expected_type == float:
                    if isinstance(value, (int, float)):
                        return float(value)
                    elif isinstance(value, str):
                        try:
                            return float(value.strip())
                        except (ValueError, TypeError):
                            return self.DEFAULTS[key]
                    else:
                        return self.DEFAULTS[key]

                else:  # str
                    return str(value) if value is not None else self.DEFAULTS[key]

            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(f"Failed to convert {key}={value!r} to {expected_type}: {e}")
                return self.DEFAULTS[key]

        except Exception as e:
            logger.error(f"[DailyTradeSetting._validate_and_convert] Failed for key={key}: {e}", exc_info=True)
            return self.DEFAULTS.get(key, None) if key in self.DEFAULTS else None

    def load(self) -> bool:
        """
        Load settings from JSON file.

        Returns:
            bool: True if load successful, False otherwise
        """
        try:
            # Rule 6: Validate file path
            if not self.json_file:
                logger.error("Cannot load: json_file is None or empty")
                return False

            # Check if file exists
            if not os.path.exists(self.json_file):
                logger.info(f"Daily trade settings file not found at {self.json_file}. Using defaults.")
                self.data = dict(self.DEFAULTS)
                return False

            # Read and parse file
            try:
                with open(self.json_file, "r", encoding='utf-8') as f:
                    loaded = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse daily trade settings JSON in {self.json_file}: {e}")
                # Try to create backup of corrupted file
                self._backup_corrupted_file()
                self.data = dict(self.DEFAULTS)
                return False
            except IOError as e:
                logger.error(f"Failed to read daily trade settings file {self.json_file}: {e}")
                self.data = dict(self.DEFAULTS)
                return False

            if not isinstance(loaded, dict):
                logger.error(
                    f"Invalid data format in {self.json_file}. Expected dict, got {type(loaded)}. Using defaults.")
                self.data = dict(self.DEFAULTS)
                return False

            # Fill missing keys with defaults, validate existing values
            for k, default_value in self.DEFAULTS.items():
                if k in loaded:
                    self.data[k] = self._validate_and_convert(k, loaded[k])
                else:
                    self.data[k] = default_value

            self._loaded = True
            logger.info(f"Daily trade settings loaded successfully from {self.json_file}")
            return True

        except Exception as e:
            logger.error(f"[DailyTradeSetting.load] Unexpected error: {e}", exc_info=True)
            self.data = dict(self.DEFAULTS)
            return False

    def _backup_corrupted_file(self) -> None:
        """Create a backup of corrupted config file."""
        try:
            if os.path.exists(self.json_file):
                backup_file = f"{self.json_file}.corrupted.{self._load_attempts}"
                import shutil
                shutil.copy2(self.json_file, backup_file)
                logger.info(f"Corrupted daily trade settings backed up to {backup_file}")
        except Exception as e:
            logger.warning(f"Failed to backup corrupted file: {e}")

    def save(self) -> bool:
        """Save settings atomically"""
        temp_file = None
        try:
            # Rule 6: Validate file path
            if not self.json_file:
                logger.error("Cannot save: json_file is None or empty")
                return False

            # Handle case where file is in current directory
            dir_path = os.path.dirname(self.json_file)
            if dir_path:
                try:
                    os.makedirs(dir_path, exist_ok=True)
                except PermissionError as e:
                    logger.error(f"Permission denied creating directory {dir_path}: {e}")
                    return False
                except Exception as e:
                    logger.error(f"Failed to create directory {dir_path}: {e}")
                    return False

            # Atomic write using temporary file
            temp_file = self.json_file + ".tmp"

            # Prepare data for saving (ensure all values are serializable)
            save_data = {}
            for k, v in self.data.items():
                try:
                    # Ensure value is JSON serializable
                    if isinstance(v, (str, int, float, bool, type(None))):
                        save_data[k] = v
                    else:
                        save_data[k] = str(v)
                        logger.warning(f"Converted non-serializable value for {k} to string")
                except Exception as e:
                    logger.warning(f"Failed to prepare {k} for saving: {e}")
                    save_data[k] = self.DEFAULTS.get(k, None)

            # Write to temporary file
            try:
                with open(temp_file, "w", encoding='utf-8') as f:
                    json.dump(save_data, f, indent=2)
            except IOError as e:
                logger.error(f"Failed to write temporary file {temp_file}: {e}")
                return False
            except TypeError as e:
                logger.error(f"Data contains non-serializable values: {e}")
                return False

            # Atomic replace
            try:
                os.replace(temp_file, self.json_file)
                logger.info(f"Daily trade settings saved successfully to {self.json_file}")
                return True
            except OSError as e:
                logger.error(f"Failed to replace daily trade settings file: {e}")
                self._safe_remove(temp_file)
                return False

        except Exception as e:
            logger.error(f"[DailyTradeSetting.save] Unexpected error: {e}", exc_info=True)
            if temp_file:
                self._safe_remove(temp_file)
            return False

    def _safe_remove(self, filepath: str) -> None:
        """Safely remove a file, ignoring errors."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.debug(f"Removed temporary file: {filepath}")
        except Exception as e:
            logger.warning(f"Failed to remove temporary file {filepath}: {e}")

    # Property accessors with validation and error handling
    @property
    def exchange(self) -> str:
        """Get exchange setting."""
        try:
            return str(self.data.get("exchange", self.DEFAULTS["exchange"]))
        except Exception as e:
            logger.error(f"[DailyTradeSetting.exchange getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["exchange"]

    @exchange.setter
    def exchange(self, value):
        try:
            self.data["exchange"] = str(value) if value is not None else self.DEFAULTS["exchange"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.exchange setter] Failed: {e}", exc_info=True)

    @property
    def week(self) -> int:
        """Get week setting."""
        try:
            val = self.data.get("week", self.DEFAULTS["week"])
            return int(val) if val is not None else self.DEFAULTS["week"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.week getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["week"]

    @week.setter
    def week(self, value):
        try:
            if value is None:
                self.data["week"] = self.DEFAULTS["week"]
            else:
                self.data["week"] = int(float(str(value)))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid week value {value!r}: {e}")
            self.data["week"] = self.DEFAULTS["week"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.week setter] Failed: {e}", exc_info=True)

    @property
    def derivative(self) -> str:
        """Get derivative setting."""
        try:
            return str(self.data.get("derivative", self.DEFAULTS["derivative"]))
        except Exception as e:
            logger.error(f"[DailyTradeSetting.derivative getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["derivative"]

    @derivative.setter
    def derivative(self, value):
        try:
            self.data["derivative"] = str(value) if value is not None else self.DEFAULTS["derivative"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.derivative setter] Failed: {e}", exc_info=True)

    @property
    def lot_size(self) -> int:
        """Get lot size setting."""
        try:
            val = self.data.get("lot_size", self.DEFAULTS["lot_size"])
            return int(val) if val is not None else self.DEFAULTS["lot_size"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.lot_size getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["lot_size"]

    @lot_size.setter
    def lot_size(self, value):
        try:
            if value is None:
                self.data["lot_size"] = self.DEFAULTS["lot_size"]
            else:
                val = int(float(str(value)))
                self.data["lot_size"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid lot_size value {value!r}: {e}")
            self.data["lot_size"] = self.DEFAULTS["lot_size"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.lot_size setter] Failed: {e}", exc_info=True)

    @property
    def call_lookback(self) -> int:
        """Get call lookback setting."""
        try:
            val = self.data.get("call_lookback", self.DEFAULTS["call_lookback"])
            return int(val) if val is not None else self.DEFAULTS["call_lookback"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.call_lookback getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["call_lookback"]

    @call_lookback.setter
    def call_lookback(self, value):
        try:
            if value is None:
                self.data["call_lookback"] = self.DEFAULTS["call_lookback"]
            else:
                self.data["call_lookback"] = int(float(str(value)))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid call_lookback value {value!r}: {e}")
            self.data["call_lookback"] = self.DEFAULTS["call_lookback"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.call_lookback setter] Failed: {e}", exc_info=True)

    @property
    def put_lookback(self) -> int:
        """Get put lookback setting."""
        try:
            val = self.data.get("put_lookback", self.DEFAULTS["put_lookback"])
            return int(val) if val is not None else self.DEFAULTS["put_lookback"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.put_lookback getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["put_lookback"]

    @put_lookback.setter
    def put_lookback(self, value):
        try:
            if value is None:
                self.data["put_lookback"] = self.DEFAULTS["put_lookback"]
            else:
                self.data["put_lookback"] = int(float(str(value)))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid put_lookback value {value!r}: {e}")
            self.data["put_lookback"] = self.DEFAULTS["put_lookback"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.put_lookback setter] Failed: {e}", exc_info=True)

    @property
    def history_interval(self) -> str:
        """Get history interval setting."""
        try:
            return str(self.data.get("history_interval", self.DEFAULTS["history_interval"]))
        except Exception as e:
            logger.error(f"[DailyTradeSetting.history_interval getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["history_interval"]

    @history_interval.setter
    def history_interval(self, value):
        try:
            self.data["history_interval"] = str(value) if value is not None else self.DEFAULTS["history_interval"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.history_interval setter] Failed: {e}", exc_info=True)

    @property
    def max_num_of_option(self) -> int:
        """Get max number of option setting."""
        try:
            val = self.data.get("max_num_of_option", self.DEFAULTS["max_num_of_option"])
            return int(val) if val is not None else self.DEFAULTS["max_num_of_option"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.max_num_of_option getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["max_num_of_option"]

    @max_num_of_option.setter
    def max_num_of_option(self, value):
        try:
            if value is None:
                self.data["max_num_of_option"] = self.DEFAULTS["max_num_of_option"]
            else:
                val = int(float(str(value)))
                self.data["max_num_of_option"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid max_num_of_option value {value!r}: {e}")
            self.data["max_num_of_option"] = self.DEFAULTS["max_num_of_option"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.max_num_of_option setter] Failed: {e}", exc_info=True)

    @property
    def lower_percentage(self) -> float:
        """Get lower percentage setting."""
        try:
            val = self.data.get("lower_percentage", self.DEFAULTS["lower_percentage"])
            return float(val) if val is not None else self.DEFAULTS["lower_percentage"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.lower_percentage getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["lower_percentage"]

    @lower_percentage.setter
    def lower_percentage(self, value):
        try:
            if value is None:
                self.data["lower_percentage"] = self.DEFAULTS["lower_percentage"]
            else:
                val = float(value)
                self.data["lower_percentage"] = max(0, min(100, val))  # Clamp between 0-100
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid lower_percentage value {value!r}: {e}")
            self.data["lower_percentage"] = self.DEFAULTS["lower_percentage"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.lower_percentage setter] Failed: {e}", exc_info=True)

    @property
    def cancel_after(self) -> int:
        """Get cancel after setting."""
        try:
            val = self.data.get("cancel_after", self.DEFAULTS["cancel_after"])
            return int(val) if val is not None else self.DEFAULTS["cancel_after"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.cancel_after getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["cancel_after"]

    @cancel_after.setter
    def cancel_after(self, value):
        try:
            if value is None:
                self.data["cancel_after"] = self.DEFAULTS["cancel_after"]
            else:
                val = int(float(str(value)))
                self.data["cancel_after"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid cancel_after value {value!r}: {e}")
            self.data["cancel_after"] = self.DEFAULTS["cancel_after"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.cancel_after setter] Failed: {e}", exc_info=True)

    @property
    def capital_reserve(self) -> int:
        """Get capital reserve setting."""
        try:
            val = self.data.get("capital_reserve", self.DEFAULTS["capital_reserve"])
            return int(val) if val is not None else self.DEFAULTS["capital_reserve"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.capital_reserve getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["capital_reserve"]

    @capital_reserve.setter
    def capital_reserve(self, value):
        try:
            if value is None:
                self.data["capital_reserve"] = self.DEFAULTS["capital_reserve"]
            else:
                val = int(float(str(value)))
                self.data["capital_reserve"] = max(0, val)  # Ensure non-negative
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid capital_reserve value {value!r}: {e}")
            self.data["capital_reserve"] = self.DEFAULTS["capital_reserve"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.capital_reserve setter] Failed: {e}", exc_info=True)

    @property
    def sideway_zone_trade(self) -> bool:
        """Get sideway zone trade setting."""
        try:
            val = self.data.get("sideway_zone_trade", self.DEFAULTS["sideway_zone_trade"])
            return bool(val) if val is not None else self.DEFAULTS["sideway_zone_trade"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.sideway_zone_trade getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["sideway_zone_trade"]

    @sideway_zone_trade.setter
    def sideway_zone_trade(self, value):
        try:
            self.data["sideway_zone_trade"] = bool(value)
        except Exception as e:
            logger.error(f"[DailyTradeSetting.sideway_zone_trade setter] Failed: {e}", exc_info=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        try:
            return dict(self.data)
        except Exception as e:
            logger.error(f"[DailyTradeSetting.to_dict] Failed: {e}", exc_info=True)
            return dict(self.DEFAULTS)

    def from_dict(self, d: Optional[Dict[str, Any]]) -> None:
        """Load settings from dictionary."""
        try:
            # Rule 6: Input validation
            if d is None:
                logger.warning("from_dict called with None, using defaults")
                self.data = dict(self.DEFAULTS)
                return

            if not isinstance(d, dict):
                logger.error(f"from_dict expected dict, got {type(d)}. Using defaults.")
                self.data = dict(self.DEFAULTS)
                return

            for k in self.DEFAULTS:
                if k in d:
                    self.data[k] = self._validate_and_convert(k, d[k])

        except Exception as e:
            logger.error(f"[DailyTradeSetting.from_dict] Failed: {e}", exc_info=True)
            self.data = dict(self.DEFAULTS)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get setting value by key with safe default.

        Args:
            key: Setting key
            default: Default value if key not found

        Returns:
            Setting value or default
        """
        try:
            # Rule 6: Input validation
            if not isinstance(key, str):
                logger.warning(f"get() called with non-string key: {key}")
                return default

            if key in self.FIELD_TYPES:
                return self.data.get(key, default)
            else:
                logger.warning(f"get() called with unknown key: {key}")
                return default

        except Exception as e:
            logger.error(f"[DailyTradeSetting.get] Failed for key '{key}': {e}", exc_info=True)
            return default

    def __repr__(self) -> str:
        """String representation of DailyTradeSetting."""
        try:
            return f"<DailyTradeSetting {self.data}>"
        except Exception as e:
            logger.error(f"[DailyTradeSetting.__repr__] Failed: {e}", exc_info=True)
            return "<DailyTradeSetting Error>"

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        try:
            logger.info("[DailyTradeSetting] Starting cleanup")
            # Clear data
            self.data.clear()
            logger.info("[DailyTradeSetting] Cleanup completed")
        except Exception as e:
            logger.error(f"[DailyTradeSetting.cleanup] Error: {e}", exc_info=True)


# Optional: Context manager for temporary settings changes
class DailyTradeSettingContext:
    """
    Context manager for temporarily modifying daily trade settings.

    Example:
        with DailyTradeSettingContext(settings) as dts:
            dts.lot_size = 100
            # ... do something with temp settings
        # Settings automatically revert
    """

    def __init__(self, settings: DailyTradeSetting):
        # Rule 2: Safe defaults
        self.settings = None
        self._backup = None

        try:
            # Rule 6: Input validation
            if not isinstance(settings, DailyTradeSetting):
                raise ValueError(f"Expected DailyTradeSetting instance, got {type(settings)}")

            self.settings = settings
            self._backup = settings.to_dict()
            logger.debug("DailyTradeSettingContext initialized")

        except Exception as e:
            logger.error(f"[DailyTradeSettingContext.__init__] Failed: {e}", exc_info=True)
            raise

    def __enter__(self) -> DailyTradeSetting:
        return self.settings

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            # Restore backup
            if self.settings and self._backup is not None:
                self.settings.from_dict(self._backup)
                logger.debug("DailyTradeSettingContext restored backup")

        except Exception as e:
            logger.error(f"[DailyTradeSettingContext.__exit__] Failed: {e}", exc_info=True)
            # Log but don't re-raise to avoid masking original exception
            if exc_type:
                logger.error(f"Original exception: {exc_type.__name__}: {exc_val}")