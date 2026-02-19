import os
import json
import urllib.parse
from typing import Optional

from fyers_apiv3 import fyersModel

import BaseEnums


def write_file(token: str):
    try:
        with open(BaseEnums.CONFIG_PATH + "/fyers_token.json", "w") as f:
            f.write(token)
    except Exception as e:
        print(f"Error writing token file: {e}")


class FyersManualLoginHelper:
    def __init__(
            self,
            client_id: str,
            secret_key: str,
            redirect_uri: str,
            token_file: str = f"{BaseEnums.LOG_PATH}/fyers_token.json"
    ):
        self.client_id = client_id
        self.secret_key = secret_key
        self.redirect_uri = redirect_uri
        self.token_file = token_file
        self.access_token: Optional[str] = None

        if os.path.exists(token_file):
            try:
                self._load_token()
                print("Loaded token from file.")
            except Exception as e:
                print(f"Error loading token file: {e}")
                self.access_token = None

    def _load_token(self):
        # Flexible loading for both txt and json token files
        try:
            if self.token_file.endswith(".json"):
                with open(self.token_file, "r") as f:
                    data = json.load(f)
                    # Try known key locations
                    if isinstance(data, dict) and "access_token" in data:
                        self.access_token = data["access_token"]
                    elif isinstance(data, str):
                        self.access_token = data
                    else:
                        raise ValueError("Malformed token file (json).")
            else:
                with open(self.token_file, "r") as f:
                    self.access_token = f.read().strip()
        except Exception as e:
            print(f"Error reading token file: {e}")
            raise

    def generate_login_url(self, state: str = "STATE123") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": state
        }
        return f"https://api-t1.fyers.in/api/v3/generate-authcode?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, auth_code: str) -> Optional[str]:
        try:
            session = fyersModel.SessionModel(
                client_id=self.client_id,
                secret_key=self.secret_key,
                redirect_uri=self.redirect_uri,
                response_type="code",
                grant_type="authorization_code"
            )
            session.set_token(auth_code)
            response = session.generate_token()
            if isinstance(response, dict) and "access_token" in response and response["access_token"]:
                self.access_token = response["access_token"]
                try:
                    with open(BaseEnums.CONFIG_PATH + "/fyers_token.json", "w") as f:
                        json.dump(response, f, indent=2)
                except Exception as file_e:
                    print(f"Error saving token to file: {file_e}")
                print("Token received and saved.")
                return self.access_token
            else:
                print(f"Token exchange failed. Response: {response}")
                return None
        except Exception as e:
            print(f"Exception during token exchange: {e}")
            return None
