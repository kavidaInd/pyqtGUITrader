import json
import os
import logging
from typing import Any, Dict

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

    def __init__(self, json_file='config/daily_trade_setting.json'):
        self.json_file = json_file
        self.data = dict(self.DEFAULTS)
        self.load()

    def _validate_and_convert(self, key: str, value: Any) -> Any:
        """Validate and convert value to the correct type"""
        expected_type = self.FIELD_TYPES.get(key, str)

        if value is None:
            return self.DEFAULTS[key]

        try:
            if expected_type == bool:
                return bool(value)
            elif expected_type == int:
                return int(float(str(value)))  # Handle both int and float strings
            elif expected_type == float:
                return float(value)
            else:
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
                logger.error(f"Failed to parse daily trade settings JSON: {e}")
            except Exception as e:
                logger.error(f"Failed to load daily trade settings: {e}")
        else:
            logger.info(f"Daily trade settings file not found at {self.json_file}. Using defaults.")

    def save(self) -> bool:
        """Save settings atomically"""
        # Handle case where file is in current directory
        dir_path = os.path.dirname(self.json_file)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        temp_file = self.json_file + ".tmp"
        try:
            with open(temp_file, "w") as f:
                json.dump(self.data, f, indent=2)
            os.replace(temp_file, self.json_file)
            return True
        except Exception as e:
            logger.error(f"Failed to save daily trade settings: {e}")
            # Clean up temp file if it exists
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            return False

    # Property accessors with validation
    @property
    def exchange(self):
        return self.data["exchange"]

    @exchange.setter
    def exchange(self, value):
        self.data["exchange"] = str(value) if value else self.DEFAULTS["exchange"]

    @property
    def week(self):
        return self.data["week"]

    @week.setter
    def week(self, value):
        try:
            self.data["week"] = int(float(str(value)))
        except (ValueError, TypeError):
            self.data["week"] = self.DEFAULTS["week"]

    @property
    def derivative(self):
        return self.data["derivative"]

    @derivative.setter
    def derivative(self, value):
        self.data["derivative"] = str(value) if value else self.DEFAULTS["derivative"]

    @property
    def lot_size(self):
        return self.data["lot_size"]

    @lot_size.setter
    def lot_size(self, value):
        try:
            val = int(float(str(value)))
            self.data["lot_size"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError):
            self.data["lot_size"] = self.DEFAULTS["lot_size"]

    @property
    def call_lookback(self):
        return self.data["call_lookback"]

    @call_lookback.setter
    def call_lookback(self, value):
        try:
            self.data["call_lookback"] = int(float(str(value)))
        except (ValueError, TypeError):
            self.data["call_lookback"] = self.DEFAULTS["call_lookback"]

    @property
    def put_lookback(self):
        return self.data["put_lookback"]

    @put_lookback.setter
    def put_lookback(self, value):
        try:
            self.data["put_lookback"] = int(float(str(value)))
        except (ValueError, TypeError):
            self.data["put_lookback"] = self.DEFAULTS["put_lookback"]

    @property
    def history_interval(self):
        return self.data["history_interval"]

    @history_interval.setter
    def history_interval(self, value):
        self.data["history_interval"] = str(value) if value else self.DEFAULTS["history_interval"]

    @property
    def max_num_of_option(self):
        return self.data["max_num_of_option"]

    @max_num_of_option.setter
    def max_num_of_option(self, value):
        try:
            val = int(float(str(value)))
            self.data["max_num_of_option"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError):
            self.data["max_num_of_option"] = self.DEFAULTS["max_num_of_option"]

    @property
    def lower_percentage(self):
        return self.data["lower_percentage"]

    @lower_percentage.setter
    def lower_percentage(self, value):
        try:
            val = float(value)
            self.data["lower_percentage"] = max(0, min(100, val))  # Clamp between 0-100
        except (ValueError, TypeError):
            self.data["lower_percentage"] = self.DEFAULTS["lower_percentage"]

    @property
    def cancel_after(self):
        return self.data["cancel_after"]

    @cancel_after.setter
    def cancel_after(self, value):
        try:
            val = int(float(str(value)))
            self.data["cancel_after"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError):
            self.data["cancel_after"] = self.DEFAULTS["cancel_after"]

    @property
    def capital_reserve(self):
        return self.data["capital_reserve"]

    @capital_reserve.setter
    def capital_reserve(self, value):
        try:
            val = int(float(str(value)))
            self.data["capital_reserve"] = max(0, val)  # Ensure non-negative
        except (ValueError, TypeError):
            self.data["capital_reserve"] = self.DEFAULTS["capital_reserve"]

    @property
    def sideway_zone_trade(self):
        return self.data["sideway_zone_trade"]

    @sideway_zone_trade.setter
    def sideway_zone_trade(self, value):
        self.data["sideway_zone_trade"] = bool(value)

    def to_dict(self):
        return dict(self.data)

    def from_dict(self, d):
        if not isinstance(d, dict):
            return
        for k in self.DEFAULTS:
            if k in d:
                self.data[k] = self._validate_and_convert(k, d[k])

    def __repr__(self):
        return f"<DailyTradeSetting {self.data}>"