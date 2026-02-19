import json
import os
import logging
from BaseEnums import STOP

logger = logging.getLogger(__name__)


class ProfitStoplossSetting:
    DEFAULTS = {
        "profit_type": STOP,
        "tp_percentage": 15.0,
        "stoploss_percentage": -7.0,
        "trailing_first_profit": 3.0,
        "max_profit": 30.0,
        "profit_step": 2.0,
        "loss_step": 2.0
    }

    def __init__(self, json_file="config/profit_stoploss_setting.json"):
        self.json_file = json_file
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r") as f:
                    loaded = json.load(f)
                # Fill with defaults for missing fields
                for k, v in self.DEFAULTS.items():
                    self.data[k] = loaded.get(k, v)
            except Exception as e:
                logger.error(f"Failed to load profit/stoploss settings: {e}")
        else:
            logger.info(f"Profit/stoploss settings file not found at {self.json_file}. Using defaults.")

    def save(self):
        os.makedirs(os.path.dirname(self.json_file), exist_ok=True)
        tmpfile = self.json_file + ".tmp"
        try:
            with open(tmpfile, "w") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmpfile, self.json_file)
        except Exception as e:
            logger.error(f"Failed to save profit/stoploss settings: {e}")

    def to_dict(self):
        return dict(self.data)

    def from_dict(self, d):
        for k in self.DEFAULTS:
            self.data[k] = d.get(k, self.DEFAULTS[k])

    def __repr__(self):
        return f"<ProfitStoplossSetting {self.data}>"

    @property
    def tp_percentage(self):
        return self.data["tp_percentage"]

    @tp_percentage.setter
    def tp_percentage(self, value):
        self.data["tp_percentage"] = float(value)

    @property
    def stoploss_percentage(self):
        return self.data["stoploss_percentage"]

    @stoploss_percentage.setter
    def stoploss_percentage(self, value):
        self.data["stoploss_percentage"] = float(value)

    @property
    def trailing_first_profit(self):
        return self.data["trailing_first_profit"]

    @trailing_first_profit.setter
    def trailing_first_profit(self, value):
        self.data["trailing_first_profit"] = float(value)

    @property
    def max_profit(self):
        return self.data["max_profit"]

    @max_profit.setter
    def max_profit(self, value):
        self.data["max_profit"] = float(value)

    @property
    def profit_step(self):
        return self.data["profit_step"]

    @profit_step.setter
    def profit_step(self, value):
        self.data["profit_step"] = float(value)

    @property
    def loss_step(self):
        return self.data["loss_step"]

    @loss_step.setter
    def loss_step(self, value):
        self.data["loss_step"] = float(value)

    @property
    def profit_type(self):
        return self.data["profit_type"]

    @profit_type.setter
    def profit_type(self, value):
        self.data["profit_type"] = value
