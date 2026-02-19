import json
import os
import logging

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

    def __init__(self, json_file="config/strategy_setting.json"):
        print()
        self.json_file = json_file
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r") as f:
                    loaded = json.load(f)
                # Ensure all keys are present
                for k, v in self.DEFAULTS.items():
                    self.data[k] = loaded.get(k, v)
            except Exception as e:
                logger.error(f"Failed to load strategy settings: {e}")
        else:
            logger.info(f"Strategy settings file not found at {self.json_file}. Using defaults.")

    def save(self):
        os.makedirs(os.path.dirname(self.json_file), exist_ok=True)
        try:
            with open(self.json_file, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save strategy settings: {e}")

    def to_dict(self):
        return dict(self.data)

    def from_dict(self, d):
        for k in self.DEFAULTS:
            self.data[k] = d.get(k, self.DEFAULTS[k])

    def __repr__(self):
        return f"<StrategySetting {self.data}>"

    # Long Supertrend Properties
    @property
    def long_st_length(self):
        return self.data["long_st_length"]

    @long_st_length.setter
    def long_st_length(self, value):
        self.data["long_st_length"] = int(value)

    @property
    def long_st_multi(self):
        return self.data["long_st_multi"]

    @long_st_multi.setter
    def long_st_multi(self, value):
        self.data["long_st_multi"] = float(value)

    @property
    def use_long_st(self):
        return self.data["use_long_st"]

    @use_long_st.setter
    def use_long_st(self, value):
        self.data["use_long_st"] = bool(value)

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
        self.data["short_st_length"] = int(value)

    @property
    def short_st_multi(self):
        return self.data["short_st_multi"]

    @short_st_multi.setter
    def short_st_multi(self, value):
        self.data["short_st_multi"] = float(value)

    @property
    def use_short_st(self):
        return self.data["use_short_st"]

    @use_short_st.setter
    def use_short_st(self, value):
        self.data["use_short_st"] = bool(value)

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
        self.data["bb_length"] = int(value)

    @property
    def bb_std(self):
        return self.data["bb_std"]

    @bb_std.setter
    def bb_std(self, value):
        self.data["bb_std"] = float(value)

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
        self.data["macd_fast"] = int(value)

    @property
    def macd_slow(self):
        return self.data["macd_slow"]

    @macd_slow.setter
    def macd_slow(self, value):
        self.data["macd_slow"] = int(value)

    @property
    def macd_signal(self):
        return self.data["macd_signal"]

    @macd_signal.setter
    def macd_signal(self, value):
        self.data["macd_signal"] = int(value)

    @property
    def use_macd(self):
        return self.data["use_macd"]

    @use_macd.setter
    def use_macd(self, value):
        self.data["use_macd"] = bool(value)

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
        self.data["rsi_length"] = int(value)

    @property
    def use_rsi(self):
        return self.data["use_rsi"]

    @use_rsi.setter
    def use_rsi(self, value):
        self.data["use_rsi"] = bool(value)

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