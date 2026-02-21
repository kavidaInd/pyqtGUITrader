import json
import os
import logging
from typing import Any, Dict
from BaseEnums import STOP, TRAILING

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

    def __init__(self, json_file="config/profit_stoploss_setting.json"):
        self.json_file = json_file
        self.data = dict(self.DEFAULTS)
        self.load()

    def _validate_and_convert(self, key: str, value: Any) -> Any:
        """Validate and convert value to the correct type"""
        expected_type = self.FIELD_TYPES.get(key, str)

        if value is None:
            return self.DEFAULTS[key]

        try:
            if expected_type == float:
                val = float(value)
                # Apply range validation if defined
                if key in self.VALIDATION_RANGES:
                    min_val, max_val = self.VALIDATION_RANGES[key]
                    val = max(min_val, min(max_val, val))
                return val
            else:
                # For profit_type, ensure it's a valid value
                if key == "profit_type":
                    if value not in [STOP, TRAILING]:
                        return self.DEFAULTS[key]
                return str(value)
        except (ValueError, TypeError):
            logger.warning(f"Failed to convert {key}={value} to {expected_type}, using default")
            return self.DEFAULTS[key]

    def load(self):
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r") as f:
                    loaded = json.load(f)

                if not isinstance(loaded, dict):
                    logger.error(f"Invalid data format in {self.json_file}. Using defaults.")
                    return

                # Fill missing keys with defaults, validate existing values
                for k, default_value in self.DEFAULTS.items():
                    if k in loaded:
                        self.data[k] = self._validate_and_convert(k, loaded[k])
                    else:
                        self.data[k] = default_value

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse profit/stoploss settings JSON: {e}")
            except Exception as e:
                logger.error(f"Failed to load profit/stoploss settings: {e}")
        else:
            logger.info(f"Profit/stoploss settings file not found at {self.json_file}. Using defaults.")

    def save(self) -> bool:
        """Save settings atomically"""
        dir_path = os.path.dirname(self.json_file)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        tmpfile = self.json_file + ".tmp"
        try:
            with open(tmpfile, "w") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmpfile, self.json_file)
            return True
        except Exception as e:
            logger.error(f"Failed to save profit/stoploss settings: {e}")
            if os.path.exists(tmpfile):
                try:
                    os.remove(tmpfile)
                except:
                    pass
            return False

    def to_dict(self):
        return dict(self.data)

    def from_dict(self, d):
        if not isinstance(d, dict):
            return
        for k in self.DEFAULTS:
            if k in d:
                self.data[k] = self._validate_and_convert(k, d[k])

    def __repr__(self):
        safe_data = dict(self.data)
        return f"<ProfitStoplossSetting {safe_data}>"

    @property
    def tp_percentage(self):
        return self.data["tp_percentage"]

    @tp_percentage.setter
    def tp_percentage(self, value):
        try:
            val = float(value)
            min_val, max_val = self.VALIDATION_RANGES["tp_percentage"]
            self.data["tp_percentage"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["tp_percentage"] = self.DEFAULTS["tp_percentage"]

    @property
    def stoploss_percentage(self):
        return self.data["stoploss_percentage"]

    @stoploss_percentage.setter
    def stoploss_percentage(self, value):
        try:
            val = abs(float(value))  # Ensure positive
            min_val, max_val = self.VALIDATION_RANGES["stoploss_percentage"]
            self.data["stoploss_percentage"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["stoploss_percentage"] = self.DEFAULTS["stoploss_percentage"]

    @property
    def trailing_first_profit(self):
        return self.data["trailing_first_profit"]

    @trailing_first_profit.setter
    def trailing_first_profit(self, value):
        try:
            val = float(value)
            min_val, max_val = self.VALIDATION_RANGES["trailing_first_profit"]
            self.data["trailing_first_profit"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["trailing_first_profit"] = self.DEFAULTS["trailing_first_profit"]

    @property
    def max_profit(self):
        return self.data["max_profit"]

    @max_profit.setter
    def max_profit(self, value):
        try:
            val = float(value)
            min_val, max_val = self.VALIDATION_RANGES["max_profit"]
            self.data["max_profit"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["max_profit"] = self.DEFAULTS["max_profit"]

    @property
    def profit_step(self):
        return self.data["profit_step"]

    @profit_step.setter
    def profit_step(self, value):
        try:
            val = float(value)
            min_val, max_val = self.VALIDATION_RANGES["profit_step"]
            self.data["profit_step"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["profit_step"] = self.DEFAULTS["profit_step"]

    @property
    def loss_step(self):
        return self.data["loss_step"]

    @loss_step.setter
    def loss_step(self, value):
        try:
            val = float(value)
            min_val, max_val = self.VALIDATION_RANGES["loss_step"]
            self.data["loss_step"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["loss_step"] = self.DEFAULTS["loss_step"]

    @property
    def profit_type(self):
        return self.data["profit_type"]

    @profit_type.setter
    def profit_type(self, value):
        if value in [STOP, TRAILING]:
            self.data["profit_type"] = value