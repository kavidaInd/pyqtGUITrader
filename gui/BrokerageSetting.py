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
                # Validate that loaded data is a dictionary
                if not isinstance(loaded, dict):
                    print(f"Invalid data format in {self.json_file}. Using defaults.")
                    return

                # Fill all required fields, even if file is missing some keys
                for k in self.REQUIRED_FIELDS:
                    self.data[k] = loaded.get(k, "")
            except json.JSONDecodeError as e:
                print(f"Failed to parse brokerage settings JSON: {e}")
            except Exception as e:
                print(f"Failed to load brokerage settings: {e}")
        else:
            print(f"Brokerage settings file not found at {self.json_file}. Using defaults.")

    def save(self):
        # Handle case where file is in current directory
        dir_path = os.path.dirname(self.json_file)
        if dir_path:  # Only create directories if there's a path
            os.makedirs(dir_path, exist_ok=True)

        tmpfile = self.json_file + ".tmp"
        try:
            with open(tmpfile, "w") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmpfile, self.json_file)
            return True
        except Exception as e:
            print(f"Failed to save brokerage settings: {e}")
            return False

    def to_dict(self):
        return dict(self.data)

    def from_dict(self, d):
        if not isinstance(d, dict):
            return
        for k in self.REQUIRED_FIELDS:
            self.data[k] = d.get(k, "")

    def __repr__(self):
        safe = {k: (v if k != "secret_key" else "***") for k, v in self.data.items()}
        return f"<BrokerageSetting {safe}>"

    @property
    def client_id(self):
        return self.data.get("client_id", "")

    @client_id.setter
    def client_id(self, value):
        self.data["client_id"] = str(value) if value else ""

    @property
    def secret_key(self):
        return self.data.get("secret_key", "")

    @secret_key.setter
    def secret_key(self, value):
        self.data["secret_key"] = str(value) if value else ""

    @property
    def redirect_uri(self):
        return self.data.get("redirect_uri", "")

    @redirect_uri.setter
    def redirect_uri(self, value):
        self.data["redirect_uri"] = str(value) if value else ""