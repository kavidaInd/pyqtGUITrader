import json
import os
import logging
import logging.handlers
from typing import Any, Dict, Optional, Tuple
import traceback

from BaseEnums import STOP, TRAILING

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class ProfitStoplossSetting:
    DEFAULTS = {
        "profit_type": STOP,
        "tp_percentage": 15.0,
        "stoploss_percentage": 7.0,  # Changed to positive value
        "trailing_first_profit": 3.0,
        "max_profit": 30.0,
        "profit_step": 2.0,
        "loss_step": 2.0
    }

    # Type mapping for validation
    FIELD_TYPES = {
        "profit_type": str,
        "tp_percentage": float,
        "stoploss_percentage": float,
        "trailing_first_profit": float,
        "max_profit": float,
        "profit_step": float,
        "loss_step": float
    }

    # Validation ranges
    VALIDATION_RANGES = {
        "tp_percentage": (0.1, 100.0),
        "stoploss_percentage": (0.1, 50.0),
        "trailing_first_profit": (0.1, 50.0),
        "max_profit": (0.1, 200.0),
        "profit_step": (0.1, 20.0),
        "loss_step": (0.1, 20.0)
    }

    def __init__(self, json_file: str = "config/profit_stoploss_setting.json"):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if not isinstance(json_file, str):
                logger.error(f"json_file must be string, got {type(json_file)}. Using default.")
                json_file = "config/profit_stoploss_setting.json"

            self.json_file = json_file
            self.data = dict(self.DEFAULTS)
            self.load()

            logger.info(f"ProfitStoplossSetting initialized with file: {self.json_file}")

        except Exception as e:
            logger.critical(f"[ProfitStoplossSetting.__init__] Failed: {e}", exc_info=True)
            # Still set basic attributes to prevent crashes
            self.json_file = json_file if isinstance(json_file, str) else "config/profit_stoploss_setting.json"
            self.data = dict(self.DEFAULTS)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.json_file = "config/profit_stoploss_setting.json"
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
                if expected_type == float:
                    # Handle various numeric formats
                    if isinstance(value, (int, float)):
                        val = float(value)
                    elif isinstance(value, str):
                        # Remove any whitespace and convert
                        clean_value = value.strip()
                        if not clean_value:
                            return self.DEFAULTS[key]
                        val = float(clean_value)
                    else:
                        # Try to convert through string
                        val = float(str(value))

                    # Apply range validation if defined
                    if key in self.VALIDATION_RANGES:
                        min_val, max_val = self.VALIDATION_RANGES[key]
                        val = max(min_val, min(max_val, val))
                        logger.debug(f"Validated {key}: {val} in range [{min_val}, {max_val}]")
                    return val

                else:  # str type
                    # For profit_type, ensure it's a valid value
                    if key == "profit_type":
                        str_value = str(value)
                        if str_value not in [STOP, TRAILING]:
                            logger.warning(f"Invalid profit_type '{str_value}', using default")
                            return self.DEFAULTS[key]
                        return str_value
                    return str(value)

            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(f"Failed to convert {key}={value!r} to {expected_type}: {e}")
                return self.DEFAULTS[key]

        except Exception as e:
            logger.error(f"[ProfitStoplossSetting._validate_and_convert] Failed for key={key}: {e}", exc_info=True)
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
                logger.info(f"Profit/stoploss settings file not found at {self.json_file}. Using defaults.")
                self.data = dict(self.DEFAULTS)
                return False

            # Read and parse file
            try:
                with open(self.json_file, "r", encoding='utf-8') as f:
                    loaded = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse profit/stoploss settings JSON in {self.json_file}: {e}")
                # Try to create backup of corrupted file
                self._backup_corrupted_file()
                self.data = dict(self.DEFAULTS)
                return False
            except IOError as e:
                logger.error(f"Failed to read profit/stoploss settings file {self.json_file}: {e}")
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
            logger.info(f"Profit/stoploss settings loaded successfully from {self.json_file}")
            return True

        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.load] Unexpected error: {e}", exc_info=True)
            self.data = dict(self.DEFAULTS)
            return False

    def _backup_corrupted_file(self) -> None:
        """Create a backup of corrupted config file."""
        try:
            if os.path.exists(self.json_file):
                backup_file = f"{self.json_file}.corrupted.{self._load_attempts}"
                import shutil
                shutil.copy2(self.json_file, backup_file)
                logger.info(f"Corrupted profit/stoploss settings backed up to {backup_file}")
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

            # Handle directory creation
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
                logger.info(f"Profit/stoploss settings saved successfully to {self.json_file}")
                return True
            except OSError as e:
                logger.error(f"Failed to replace profit/stoploss settings file: {e}")
                self._safe_remove(temp_file)
                return False

        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.save] Unexpected error: {e}", exc_info=True)
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        try:
            return dict(self.data)
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.to_dict] Failed: {e}", exc_info=True)
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
            logger.error(f"[ProfitStoplossSetting.from_dict] Failed: {e}", exc_info=True)
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
            logger.error(f"[ProfitStoplossSetting.get] Failed for key '{key}': {e}", exc_info=True)
            return default

    def __repr__(self) -> str:
        """String representation of ProfitStoplossSetting."""
        try:
            safe_data = dict(self.data)
            return f"<ProfitStoplossSetting {safe_data}>"
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.__repr__] Failed: {e}", exc_info=True)
            return "<ProfitStoplossSetting Error>"

    # Property accessors with validation and error handling
    @property
    def tp_percentage(self) -> float:
        """Get take profit percentage."""
        try:
            val = self.data.get("tp_percentage", self.DEFAULTS["tp_percentage"])
            return float(val) if val is not None else self.DEFAULTS["tp_percentage"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.tp_percentage getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["tp_percentage"]

    @tp_percentage.setter
    def tp_percentage(self, value):
        try:
            if value is None:
                self.data["tp_percentage"] = self.DEFAULTS["tp_percentage"]
            else:
                val = float(value)
                min_val, max_val = self.VALIDATION_RANGES["tp_percentage"]
                self.data["tp_percentage"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid tp_percentage value {value!r}: {e}")
            self.data["tp_percentage"] = self.DEFAULTS["tp_percentage"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.tp_percentage setter] Failed: {e}", exc_info=True)

    @property
    def stoploss_percentage(self) -> float:
        """Get stop loss percentage."""
        try:
            val = self.data.get("stoploss_percentage", self.DEFAULTS["stoploss_percentage"])
            return float(val) if val is not None else self.DEFAULTS["stoploss_percentage"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.stoploss_percentage getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["stoploss_percentage"]

    @stoploss_percentage.setter
    def stoploss_percentage(self, value):
        try:
            if value is None:
                self.data["stoploss_percentage"] = self.DEFAULTS["stoploss_percentage"]
            else:
                val = abs(float(value))  # Ensure positive
                min_val, max_val = self.VALIDATION_RANGES["stoploss_percentage"]
                self.data["stoploss_percentage"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid stoploss_percentage value {value!r}: {e}")
            self.data["stoploss_percentage"] = self.DEFAULTS["stoploss_percentage"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.stoploss_percentage setter] Failed: {e}", exc_info=True)

    @property
    def trailing_first_profit(self) -> float:
        """Get trailing first profit percentage."""
        try:
            val = self.data.get("trailing_first_profit", self.DEFAULTS["trailing_first_profit"])
            return float(val) if val is not None else self.DEFAULTS["trailing_first_profit"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.trailing_first_profit getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["trailing_first_profit"]

    @trailing_first_profit.setter
    def trailing_first_profit(self, value):
        try:
            if value is None:
                self.data["trailing_first_profit"] = self.DEFAULTS["trailing_first_profit"]
            else:
                val = float(value)
                min_val, max_val = self.VALIDATION_RANGES["trailing_first_profit"]
                self.data["trailing_first_profit"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid trailing_first_profit value {value!r}: {e}")
            self.data["trailing_first_profit"] = self.DEFAULTS["trailing_first_profit"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.trailing_first_profit setter] Failed: {e}", exc_info=True)

    @property
    def max_profit(self) -> float:
        """Get maximum profit percentage."""
        try:
            val = self.data.get("max_profit", self.DEFAULTS["max_profit"])
            return float(val) if val is not None else self.DEFAULTS["max_profit"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.max_profit getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["max_profit"]

    @max_profit.setter
    def max_profit(self, value):
        try:
            if value is None:
                self.data["max_profit"] = self.DEFAULTS["max_profit"]
            else:
                val = float(value)
                min_val, max_val = self.VALIDATION_RANGES["max_profit"]
                self.data["max_profit"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid max_profit value {value!r}: {e}")
            self.data["max_profit"] = self.DEFAULTS["max_profit"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.max_profit setter] Failed: {e}", exc_info=True)

    @property
    def profit_step(self) -> float:
        """Get profit step percentage."""
        try:
            val = self.data.get("profit_step", self.DEFAULTS["profit_step"])
            return float(val) if val is not None else self.DEFAULTS["profit_step"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.profit_step getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["profit_step"]

    @profit_step.setter
    def profit_step(self, value):
        try:
            if value is None:
                self.data["profit_step"] = self.DEFAULTS["profit_step"]
            else:
                val = float(value)
                min_val, max_val = self.VALIDATION_RANGES["profit_step"]
                self.data["profit_step"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid profit_step value {value!r}: {e}")
            self.data["profit_step"] = self.DEFAULTS["profit_step"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.profit_step setter] Failed: {e}", exc_info=True)

    @property
    def loss_step(self) -> float:
        """Get loss step percentage."""
        try:
            val = self.data.get("loss_step", self.DEFAULTS["loss_step"])
            return float(val) if val is not None else self.DEFAULTS["loss_step"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.loss_step getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["loss_step"]

    @loss_step.setter
    def loss_step(self, value):
        try:
            if value is None:
                self.data["loss_step"] = self.DEFAULTS["loss_step"]
            else:
                val = float(value)
                min_val, max_val = self.VALIDATION_RANGES["loss_step"]
                self.data["loss_step"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid loss_step value {value!r}: {e}")
            self.data["loss_step"] = self.DEFAULTS["loss_step"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.loss_step setter] Failed: {e}", exc_info=True)

    @property
    def profit_type(self) -> str:
        """Get profit type (STOP or TRAILING)."""
        try:
            val = self.data.get("profit_type", self.DEFAULTS["profit_type"])
            return str(val) if val is not None else self.DEFAULTS["profit_type"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.profit_type getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["profit_type"]

    @profit_type.setter
    def profit_type(self, value):
        try:
            if value is None:
                self.data["profit_type"] = self.DEFAULTS["profit_type"]
            elif value in [STOP, TRAILING]:
                self.data["profit_type"] = value
            else:
                logger.warning(f"Invalid profit_type value {value!r}, using default")
                self.data["profit_type"] = self.DEFAULTS["profit_type"]
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.profit_type setter] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        try:
            logger.info("[ProfitStoplossSetting] Starting cleanup")
            # Clear data
            self.data.clear()
            logger.info("[ProfitStoplossSetting] Cleanup completed")
        except Exception as e:
            logger.error(f"[ProfitStoplossSetting.cleanup] Error: {e}", exc_info=True)


# Optional: Context manager for temporary settings changes
class ProfitStoplossSettingContext:
    """
    Context manager for temporarily modifying profit/stoploss settings.

    Example:
        with ProfitStoplossSettingContext(settings) as psl:
            psl.tp_percentage = 20.0
            # ... do something with temp settings
        # Settings automatically revert
    """

    def __init__(self, settings: ProfitStoplossSetting):
        # Rule 2: Safe defaults
        self.settings = None
        self._backup = None

        try:
            # Rule 6: Input validation
            if not isinstance(settings, ProfitStoplossSetting):
                raise ValueError(f"Expected ProfitStoplossSetting instance, got {type(settings)}")

            self.settings = settings
            self._backup = settings.to_dict()
            logger.debug("ProfitStoplossSettingContext initialized")

        except Exception as e:
            logger.error(f"[ProfitStoplossSettingContext.__init__] Failed: {e}", exc_info=True)
            raise

    def __enter__(self) -> ProfitStoplossSetting:
        return self.settings

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            # Restore backup
            if self.settings and self._backup is not None:
                self.settings.from_dict(self._backup)
                logger.debug("ProfitStoplossSettingContext restored backup")

        except Exception as e:
            logger.error(f"[ProfitStoplossSettingContext.__exit__] Failed: {e}", exc_info=True)
            # Log but don't re-raise to avoid masking original exception
            if exc_type:
                logger.error(f"Original exception: {exc_type.__name__}: {exc_val}")