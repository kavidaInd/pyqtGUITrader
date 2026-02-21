import json
import os
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class StrategySetting:
    DEFAULTS = {
        "long_st_length": 10,
        "long_st_multi": 1.5,
        "short_st_length": 7,
        "short_st_multi": 1.2,
        "bb_exit": False,
        "bb_entry": False,
        "use_short_st": False,
        "use_short_st_entry": False,
        "use_short_st_exit": False,
        "use_long_st": False,
        "use_long_st_entry": False,
        "use_long_st_exit": False,
        "use_macd": False,
        "use_macd_entry": False,
        "use_macd_exit": False,
        "use_rsi": False,
        "use_rsi_entry": False,
        "use_rsi_exit": False,
        "rsi_length": 14,
        "bb_length": 20,
        "bb_std": 2.0,
        "macd_fast": 10,
        "macd_slow": 20,
        "macd_signal": 7
    }

    # Type mapping for validation
    FIELD_TYPES = {
        "long_st_length": int,
        "long_st_multi": float,
        "short_st_length": int,
        "short_st_multi": float,
        "bb_exit": bool,
        "bb_entry": bool,
        "use_short_st": bool,
        "use_short_st_entry": bool,
        "use_short_st_exit": bool,
        "use_long_st": bool,
        "use_long_st_entry": bool,
        "use_long_st_exit": bool,
        "use_macd": bool,
        "use_macd_entry": bool,
        "use_macd_exit": bool,
        "use_rsi": bool,
        "use_rsi_entry": bool,
        "use_rsi_exit": bool,
        "rsi_length": int,
        "bb_length": int,
        "bb_std": float,
        "macd_fast": int,
        "macd_slow": int,
        "macd_signal": int
    }

    # Validation ranges
    VALIDATION_RANGES = {
        "long_st_length": (1, 100),
        "long_st_multi": (0.1, 10.0),
        "short_st_length": (1, 100),
        "short_st_multi": (0.1, 10.0),
        "rsi_length": (2, 50),
        "bb_length": (2, 100),
        "bb_std": (0.1, 5.0),
        "macd_fast": (1, 50),
        "macd_slow": (2, 100),
        "macd_signal": (1, 50)
    }

    def __init__(self, json_file="config/strategy_setting.json"):
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
                val = int(float(str(value)))
                # Apply range validation if defined
                if key in self.VALIDATION_RANGES:
                    min_val, max_val = self.VALIDATION_RANGES[key]
                    val = max(min_val, min(max_val, val))
                return val
            elif expected_type == float:
                val = float(value)
                # Apply range validation if defined
                if key in self.VALIDATION_RANGES:
                    min_val, max_val = self.VALIDATION_RANGES[key]
                    val = max(min_val, min(max_val, val))
                return val
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

                # Validate logical relationships
                self._validate_logical_relationships()

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse strategy settings JSON: {e}")
            except Exception as e:
                logger.error(f"Failed to load strategy settings: {e}")
        else:
            logger.info(f"Strategy settings file not found at {self.json_file}. Using defaults.")

    def _validate_logical_relationships(self):
        """Validate logical relationships between settings"""
        # Ensure MACD fast < slow
        if self.data["macd_fast"] >= self.data["macd_slow"]:
            logger.warning("MACD fast period must be less than slow period. Adjusting.")
            self.data["macd_fast"] = min(self.data["macd_fast"], self.data["macd_slow"] - 1)
            if self.data["macd_fast"] < 1:
                self.data["macd_fast"] = 1
                self.data["macd_slow"] = self.data["macd_fast"] + 1

    def save(self) -> bool:
        """Save settings atomically"""
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
            logger.error(f"Failed to save strategy settings: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
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
        self._validate_logical_relationships()

    def __repr__(self):
        return f"<StrategySetting {self.data}>"

    # Long Supertrend Properties
    @property
    def long_st_length(self):
        return self.data["long_st_length"]

    @long_st_length.setter
    def long_st_length(self, value):
        try:
            val = int(float(str(value)))
            min_val, max_val = self.VALIDATION_RANGES["long_st_length"]
            self.data["long_st_length"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["long_st_length"] = self.DEFAULTS["long_st_length"]

    @property
    def long_st_multi(self):
        return self.data["long_st_multi"]

    @long_st_multi.setter
    def long_st_multi(self, value):
        try:
            val = float(value)
            min_val, max_val = self.VALIDATION_RANGES["long_st_multi"]
            self.data["long_st_multi"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["long_st_multi"] = self.DEFAULTS["long_st_multi"]

    @property
    def use_long_st(self):
        return self.data["use_long_st_entry"] or self.data["use_long_st_exit"]

    @use_long_st.setter
    def use_long_st(self, value):
        # This is a computed property, so setter just updates both
        bool_val = bool(value)
        self.data["use_long_st_entry"] = bool_val
        self.data["use_long_st_exit"] = bool_val

    @property
    def use_long_st_entry(self):
        return self.data["use_long_st_entry"]

    @use_long_st_entry.setter
    def use_long_st_entry(self, value):
        self.data["use_long_st_entry"] = bool(value)

    @property
    def use_long_st_exit(self):
        return self.data["use_long_st_exit"]

    @use_long_st_exit.setter
    def use_long_st_exit(self, value):
        self.data["use_long_st_exit"] = bool(value)

    # Short Supertrend Properties
    @property
    def short_st_length(self):
        return self.data["short_st_length"]

    @short_st_length.setter
    def short_st_length(self, value):
        try:
            val = int(float(str(value)))
            min_val, max_val = self.VALIDATION_RANGES["short_st_length"]
            self.data["short_st_length"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["short_st_length"] = self.DEFAULTS["short_st_length"]

    @property
    def short_st_multi(self):
        return self.data["short_st_multi"]

    @short_st_multi.setter
    def short_st_multi(self, value):
        try:
            val = float(value)
            min_val, max_val = self.VALIDATION_RANGES["short_st_multi"]
            self.data["short_st_multi"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["short_st_multi"] = self.DEFAULTS["short_st_multi"]

    @property
    def use_short_st(self):
        return self.data["use_short_st_entry"] or self.data["use_short_st_exit"]

    @use_short_st.setter
    def use_short_st(self, value):
        bool_val = bool(value)
        self.data["use_short_st_entry"] = bool_val
        self.data["use_short_st_exit"] = bool_val

    @property
    def use_short_st_entry(self):
        return self.data["use_short_st_entry"]

    @use_short_st_entry.setter
    def use_short_st_entry(self, value):
        self.data["use_short_st_entry"] = bool(value)

    @property
    def use_short_st_exit(self):
        return self.data["use_short_st_exit"]

    @use_short_st_exit.setter
    def use_short_st_exit(self, value):
        self.data["use_short_st_exit"] = bool(value)

    # Bollinger Bands Properties
    @property
    def bb_length(self):
        return self.data["bb_length"]

    @bb_length.setter
    def bb_length(self, value):
        try:
            val = int(float(str(value)))
            min_val, max_val = self.VALIDATION_RANGES["bb_length"]
            self.data["bb_length"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["bb_length"] = self.DEFAULTS["bb_length"]

    @property
    def bb_std(self):
        return self.data["bb_std"]

    @bb_std.setter
    def bb_std(self, value):
        try:
            val = float(value)
            min_val, max_val = self.VALIDATION_RANGES["bb_std"]
            self.data["bb_std"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["bb_std"] = self.DEFAULTS["bb_std"]

    @property
    def bb_entry(self):
        return self.data["bb_entry"]

    @bb_entry.setter
    def bb_entry(self, value):
        self.data["bb_entry"] = bool(value)

    @property
    def bb_exit(self):
        return self.data["bb_exit"]

    @bb_exit.setter
    def bb_exit(self, value):
        self.data["bb_exit"] = bool(value)

    # MACD Properties
    @property
    def macd_fast(self):
        return self.data["macd_fast"]

    @macd_fast.setter
    def macd_fast(self, value):
        try:
            val = int(float(str(value)))
            min_val, max_val = self.VALIDATION_RANGES["macd_fast"]
            val = max(min_val, min(max_val, val))
            # Ensure fast < slow
            if val >= self.data["macd_slow"]:
                self.data["macd_slow"] = val + 1
            self.data["macd_fast"] = val
        except (ValueError, TypeError):
            self.data["macd_fast"] = self.DEFAULTS["macd_fast"]

    @property
    def macd_slow(self):
        return self.data["macd_slow"]

    @macd_slow.setter
    def macd_slow(self, value):
        try:
            val = int(float(str(value)))
            min_val, max_val = self.VALIDATION_RANGES["macd_slow"]
            val = max(min_val, min(max_val, val))
            # Ensure fast < slow
            if val <= self.data["macd_fast"]:
                self.data["macd_fast"] = val - 1
                if self.data["macd_fast"] < 1:
                    self.data["macd_fast"] = 1
                    val = 2
            self.data["macd_slow"] = val
        except (ValueError, TypeError):
            self.data["macd_slow"] = self.DEFAULTS["macd_slow"]

    @property
    def macd_signal(self):
        return self.data["macd_signal"]

    @macd_signal.setter
    def macd_signal(self, value):
        try:
            val = int(float(str(value)))
            min_val, max_val = self.VALIDATION_RANGES["macd_signal"]
            self.data["macd_signal"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["macd_signal"] = self.DEFAULTS["macd_signal"]

    @property
    def use_macd(self):
        return self.data["use_macd_entry"] or self.data["use_macd_exit"]

    @use_macd.setter
    def use_macd(self, value):
        bool_val = bool(value)
        self.data["use_macd_entry"] = bool_val
        self.data["use_macd_exit"] = bool_val

    @property
    def use_macd_entry(self):
        return self.data["use_macd_entry"]

    @use_macd_entry.setter
    def use_macd_entry(self, value):
        self.data["use_macd_entry"] = bool(value)

    @property
    def use_macd_exit(self):
        return self.data["use_macd_exit"]

    @use_macd_exit.setter
    def use_macd_exit(self, value):
        self.data["use_macd_exit"] = bool(value)

    # RSI Properties
    @property
    def rsi_length(self):
        return self.data["rsi_length"]

    @rsi_length.setter
    def rsi_length(self, value):
        try:
            val = int(float(str(value)))
            min_val, max_val = self.VALIDATION_RANGES["rsi_length"]
            self.data["rsi_length"] = max(min_val, min(max_val, val))
        except (ValueError, TypeError):
            self.data["rsi_length"] = self.DEFAULTS["rsi_length"]

    @property
    def use_rsi(self):
        return self.data["use_rsi_entry"] or self.data["use_rsi_exit"]

    @use_rsi.setter
    def use_rsi(self, value):
        bool_val = bool(value)
        self.data["use_rsi_entry"] = bool_val
        self.data["use_rsi_exit"] = bool_val

    @property
    def use_rsi_entry(self):
        return self.data["use_rsi_entry"]

    @use_rsi_entry.setter
    def use_rsi_entry(self, value):
        self.data["use_rsi_entry"] = bool(value)

    @property
    def use_rsi_exit(self):
        return self.data["use_rsi_exit"]

    @use_rsi_exit.setter
    def use_rsi_exit(self, value):
        self.data["use_rsi_exit"] = bool(value)