import json
import os


class BrokerageSetting:
    REQUIRED_FIELDS = ["client_id", "secret_key", "redirect_uri"]

    def __init__(self, json_file='config/brokerage_setting.json'):
        self.json_file = json_file
        self.data = {k: "" for k in self.REQUIRED_FIELDS}
        self.load()

    def load(self):
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r") as f:
                    loaded = json.load(f)
                # Fill all required fields, even if file is missing some keys
                for k in self.REQUIRED_FIELDS:
                    self.data[k] = loaded.get(k, "")
            except Exception as e:
                print(f"Failed to load brokerage settings: {e}")
        else:
            print(f"Brokerage settings file not found at {self.json_file}. Using defaults.")

    def save(self):
        os.makedirs(os.path.dirname(self.json_file), exist_ok=True)
        tmpfile = self.json_file + ".tmp"
        try:
            with open(tmpfile, "w") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmpfile, self.json_file)
        except Exception as e:
            print(f"Failed to save brokerage settings: {e}")

    def to_dict(self):
        return dict(self.data)

    def from_dict(self, d):
        for k in self.REQUIRED_FIELDS:
            self.data[k] = d.get(k, "")

    def __repr__(self):
        safe = {k: (v if k != "secret_key" else "***") for k, v in self.data.items()}
        return f"<BrokerageSetting {safe}>"

    @property
    def client_id(self):
        return self.data["client_id"]

    @client_id.setter
    def client_id(self, value):
        self.data["client_id"] = value

    @property
    def secret_key(self):
        return self.data["secret_key"]

    @secret_key.setter
    def secret_key(self, value):
        self.data["secret_key"] = value

    @property
    def redirect_uri(self):
        return self.data["redirect_uri"]

    @redirect_uri.setter
    def redirect_uri(self, value):
        self.data["redirect_uri"] = value
