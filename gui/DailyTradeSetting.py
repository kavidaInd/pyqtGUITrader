import json
import os
import logging

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
        "sideway_zone_trade": False  # Added new checkmark option
    }

    def __init__(self, json_file='config/daily_trade_setting.json'):
        self.json_file = json_file
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r") as f:
                    loaded = json.load(f)
                # Fill missing keys with defaults for backward compatibility
                for k, v in self.DEFAULTS.items():
                    self.data[k] = loaded.get(k, v)
            except Exception as e:
                logger.error(f"Failed to load daily trade settings: {e}")
        else:
            logger.info(f"Daily trade settings file not found at {self.json_file}. Using defaults.")

    def save(self):
        os.makedirs(os.path.dirname(self.json_file), exist_ok=True)
        try:
            with open(self.json_file, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save daily trade settings: {e}")

    # Property accessors
    @property
    def exchange(self):
        return self.data["exchange"]

    @exchange.setter
    def exchange(self, value):
        self.data["exchange"] = value

    @property
    def week(self):
        return self.data["week"]

    @week.setter
    def week(self, value):
        self.data["week"] = int(value)

    @property
    def derivative(self):
        return self.data["derivative"]

    @derivative.setter
    def derivative(self, value):
        self.data["derivative"] = value

    @property
    def lot_size(self):
        return self.data["lot_size"]

    @lot_size.setter
    def lot_size(self, value):
        self.data["lot_size"] = int(value)

    @property
    def call_lookback(self):
        return self.data["call_lookback"]

    @call_lookback.setter
    def call_lookback(self, value):
        self.data["call_lookback"] = int(value)

    @property
    def put_lookback(self):
        return self.data["put_lookback"]

    @put_lookback.setter
    def put_lookback(self, value):
        self.data["put_lookback"] = int(value)

    @property
    def history_interval(self):
        return self.data["history_interval"]

    @history_interval.setter
    def history_interval(self, value):
        self.data["history_interval"] = value

    @property
    def max_num_of_option(self):
        return self.data["max_num_of_option"]

    @max_num_of_option.setter
    def max_num_of_option(self, value):
        self.data["max_num_of_option"] = int(value)

    @property
    def lower_percentage(self):
        return self.data["lower_percentage"]

    @lower_percentage.setter
    def lower_percentage(self, value):
        self.data["lower_percentage"] = float(value)

    @property
    def cancel_after(self):
        return self.data["cancel_after"]

    @cancel_after.setter
    def cancel_after(self, value):
        self.data["cancel_after"] = int(value)

    @property
    def capital_reserve(self):
        return self.data["capital_reserve"]

    @capital_reserve.setter
    def capital_reserve(self, value):
        self.data["capital_reserve"] = int(value)

    @property
    def sideway_zone_trade(self):
        return self.data["sideway_zone_trade"]

    @sideway_zone_trade.setter
    def sideway_zone_trade(self, value):
        self.data["sideway_zone_trade"] = bool(value)

    def to_dict(self):
        return dict(self.data)

    def from_dict(self, d):
        for k in self.DEFAULTS:
            self.data[k] = d.get(k, self.DEFAULTS[k])

    def __repr__(self):
        return f"<DailyTradeSetting {self.data}>"