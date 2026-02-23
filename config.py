import json
import os


class Config:
    def __init__(self, config_file="config/strategy_setting.json"):
        self.config_file = config_file
        # Default values
        self.load()

    def to_dict(self):
        return {

        }

    def from_dict(self, d):
        pass

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