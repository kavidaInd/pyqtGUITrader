import json
import os


class Config:
    def __init__(self, config_file="config/strategy_setting.json"):
        self.config_file = config_file
        # Default values
        self.long_st_length = 10
        self.long_st_multi = 1.5
        self.short_st_length = 7
        self.short_st_multi = 1.1
        self.bb_exit = True
        self.bb_entry = False
        self.use_short_st = False
        self.use_short_st_entry =  False
        self.use_short_st_exit = False
        self.use_long_st = False
        self.use_long_st_entry = False
        self.use_long_st_exit = False
        self.use_macd = False
        self.use_macd_entry = False
        self.use_macd_exit = False
        self.use_rsi = False
        self.use_rsi_entry = False
        self.use_rsi_exit = False
        self.use_long_st = True
        self.use_short_st = True
        self.use_macd = True
        self.use_rsi = False
        self.rsi_length = 14
        self.bb_length = 14
        self.bb_std = 3.0
        self.macd_fast = 10
        self.macd_slow = 20
        self.macd_signal = 7
        # Try to load saved config
        self.load()

    def to_dict(self):
        return {
            "long_st_length": self.long_st_length,
            "long_st_multi": self.long_st_multi,
            "short_st_length": self.short_st_length,
            "short_st_multi": self.short_st_multi,
            "use_long_st": self.use_long_st,
            "use_short_st": self.use_short_st,
            "use_macd": self.use_macd,
            "use_rsi": self.use_rsi,
            "rsi_length": self.rsi_length,
            "bb_length": self.bb_length,
            "bb_std": self.bb_std,
            "macd_fast": self.macd_fast,
            "macd_slow": self.macd_slow,
            "macd_signal": self.macd_signal,
            "bb_entry": self.bb_entry,
            "bb_exit": self.bb_exit,
            "use_short_st_entry": self.use_short_st_entry,
            "use_short_st_exit": self.use_short_st_exit,
            "use_long_st_entry": self.use_long_st_entry,
            "use_long_st_exit": self.use_long_st_exit,
            "use_macd_entry": self.use_macd_entry,
            "use_macd_exit": self.use_macd_exit,
            "use_rsi_entry": self.use_rsi_entry,
            "use_rsi_exit": self.use_rsi_exit,
        }

    def from_dict(self, d):
        self.long_st_length = d.get("long_st_length", self.long_st_length)
        self.long_st_multi = d.get("long_st_multi", self.long_st_multi)
        self.short_st_length = d.get("short_st_length", self.short_st_length)
        self.short_st_multi = d.get("short_st_multi", self.short_st_multi)
        self.bb_exit = d.get("bb_exit", self.bb_exit)
        self.use_short_st = d.get("use_short_st", self.use_short_st)
        self.use_long_st = d.get("use_long_st", self.use_long_st)
        self.use_macd = d.get("use_macd", self.use_macd)
        self.use_rsi = d.get("use_rsi", self.use_rsi)
        self.rsi_length = d.get("rsi_length", self.rsi_length)
        self.bb_length = d.get("bb_length", self.bb_length)
        self.bb_std = d.get("bb_std", self.bb_std)
        self.macd_fast = d.get("macd_fast", self.macd_fast)
        self.macd_slow = d.get("macd_slow", self.macd_slow)
        self.macd_signal = d.get("macd_signal", self.macd_signal)
        self.bb_entry = d.get("bb_entry", self.bb_entry)
        self.use_short_st_entry = d.get("use_short_st_entry", self.use_short_st_entry)
        self.use_short_st_exit = d.get("use_short_st_exit", self.use_short_st_exit)
        self.use_long_st_entry = d.get("use_long_st_entry", self.use_long_st_entry)
        self.use_long_st_exit = d.get("use_long_st_exit", self.use_long_st_exit)
        self.use_macd_entry = d.get("use_macd_entry", self.use_macd_entry)
        self.use_macd_exit = d.get("use_macd_exit", self.use_macd_exit)
        self.use_rsi_entry = d.get("use_rsi_entry", self.use_rsi_entry)
        self.use_rsi_exit = d.get("use_rsi_exit", self.use_rsi_exit)


    def save(self):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(self.to_dict(), f, indent=4)

    def load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    self.from_dict(data)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Failed to load config: {e}. Using defaults.")
        else:
            print(f"Config file not found at {self.config_file}. Using default settings.")

    def __repr__(self):
        return f"Config({self.to_dict()})"
