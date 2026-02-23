import os
import json
import logging
import logging.handlers
import urllib.parse
from typing import Optional, Dict, Any
import traceback

from fyers_apiv3 import fyersModel

import BaseEnums

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


def write_file(token: str) -> bool:
    """
    Write token to file.

    Args:
        token: Token string to write

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if token is None:
            logger.error("write_file called with None token")
            return False

        file_path = os.path.join(BaseEnums.CONFIG_PATH, "fyers_token.json")

        # Ensure directory exists
        try:
            os.makedirs(BaseEnums.CONFIG_PATH, exist_ok=True)
        except PermissionError as e:
            logger.error(f"Permission denied creating directory {BaseEnums.CONFIG_PATH}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to create directory {BaseEnums.CONFIG_PATH}: {e}", exc_info=True)
            return False

        # Write token atomically
        temp_file = file_path + ".tmp"
        try:
            with open(temp_file, "w", encoding='utf-8') as f:
                f.write(token)
            os.replace(temp_file, file_path)
            logger.info(f"Token written to {file_path}")
            return True
        except IOError as e:
            logger.error(f"Failed to write token file: {e}", exc_info=True)
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            return False
        except Exception as e:
            logger.error(f"Unexpected error writing token file: {e}", exc_info=True)
            return False

    except Exception as e:
        logger.error(f"[write_file] Failed: {e}", exc_info=True)
        return False


class FyersManualLoginHelper:
    def __init__(
            self,
            client_id: str,
            secret_key: str,
            redirect_uri: str,
            token_file: str = f"{BaseEnums.LOG_PATH}/fyers_token.json"
    ):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if not client_id:
                logger.error("client_id is required")
                client_id = ""

            if not secret_key:
                logger.error("secret_key is required")
                secret_key = ""

            if not redirect_uri:
                logger.error("redirect_uri is required")
                redirect_uri = ""

            self.client_id = client_id
            self.secret_key = secret_key
            self.redirect_uri = redirect_uri
            self.token_file = token_file
            self.access_token: Optional[str] = None

            if os.path.exists(token_file):
                try:
                    self._load_token()
                    logger.info("Loaded token from file.")
                except Exception as e:
                    logger.error(f"Error loading token file: {e}", exc_info=True)
                    self.access_token = None

            logger.debug("FyersManualLoginHelper initialized")

        except Exception as e:
            logger.critical(f"[FyersManualLoginHelper.__init__] Failed: {e}", exc_info=True)
            self.client_id = client_id or ""
            self.secret_key = secret_key or ""
            self.redirect_uri = redirect_uri or ""
            self.token_file = token_file
            self.access_token = None

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.client_id = ""
        self.secret_key = ""
        self.redirect_uri = ""
        self.token_file = ""
        self.access_token = None

    def _load_token(self) -> None:
        """
        Load token from file.
        Flexible loading for both txt and json token files.
        """
        try:
            if not self.token_file:
                raise ValueError("token_file is not set")

            if not os.path.exists(self.token_file):
                logger.warning(f"Token file not found: {self.token_file}")
                return

            if self.token_file.endswith(".json"):
                try:
                    with open(self.token_file, "r", encoding='utf-8') as f:
                        data = json.load(f)

                    # Try known key locations
                    if isinstance(data, dict):
                        if "access_token" in data:
                            self.access_token = data["access_token"]
                        elif "token" in data:
                            self.access_token = data["token"]
                        else:
                            # Try to find any string value that looks like a token
                            for key, value in data.items():
                                if isinstance(value, str) and len(value) > 50:
                                    self.access_token = value
                                    logger.debug(f"Found token in key '{key}'")
                                    break
                            else:
                                logger.warning("No access_token found in JSON file")
                    elif isinstance(data, str):
                        self.access_token = data
                    else:
                        logger.error(f"Unexpected data type in token file: {type(data)}")
                        raise ValueError("Malformed token file (json).")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON token file: {e}", exc_info=True)
                    raise
            else:
                try:
                    with open(self.token_file, "r", encoding='utf-8') as f:
                        self.access_token = f.read().strip()
                except IOError as e:
                    logger.error(f"Failed to read token file: {e}", exc_info=True)
                    raise

            if self.access_token:
                logger.debug(f"Token loaded successfully (length: {len(self.access_token)})")
            else:
                logger.warning("Token file contained empty token")

        except PermissionError as e:
            logger.error(f"Permission denied reading token file: {e}")
            raise
        except Exception as e:
            logger.error(f"Error reading token file: {e}", exc_info=True)
            raise

    def generate_login_url(self, state: str = "STATE123") -> str:
        """
        Generate Fyers login URL.

        Args:
            state: State parameter for OAuth

        Returns:
            Login URL string
        """
        try:
            # Rule 6: Input validation
            if not self.client_id:
                logger.error("Cannot generate login URL: client_id is missing")
                return ""

            if not self.redirect_uri:
                logger.error("Cannot generate login URL: redirect_uri is missing")
                return ""

            params = {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "state": state or "STATE123"
            }

            url = f"https://api-t1.fyers.in/api/v3/generate-authcode?{urllib.parse.urlencode(params)}"
            logger.debug(f"Generated login URL: {url}")
            return url

        except Exception as e:
            logger.error(f"Failed to generate login URL: {e}", exc_info=True)
            return ""

    def exchange_code_for_token(self, auth_code: str) -> Optional[str]:
        """
        Exchange authorization code for access token.

        Args:
            auth_code: Authorization code from Fyers

        Returns:
            Access token or None if failed
        """
        try:
            # Rule 6: Input validation
            if not auth_code:
                logger.error("exchange_code_for_token called with empty auth_code")
                return None

            if not self.client_id:
                logger.error("Cannot exchange token: client_id is missing")
                return None

            if not self.secret_key:
                logger.error("Cannot exchange token: secret_key is missing")
                return None

            if not self.redirect_uri:
                logger.error("Cannot exchange token: redirect_uri is missing")
                return None

            # Create session
            try:
                session = fyersModel.SessionModel(
                    client_id=self.client_id,
                    secret_key=self.secret_key,
                    redirect_uri=self.redirect_uri,
                    response_type="code",
                    grant_type="authorization_code"
                )
            except Exception as e:
                logger.error(f"Failed to create SessionModel: {e}", exc_info=True)
                return None

            # Set token and generate
            try:
                session.set_token(auth_code)
                response = session.generate_token()
            except Exception as e:
                logger.error(f"Token exchange API call failed: {e}", exc_info=True)
                return None

            # Process response
            if isinstance(response, dict):
                if "access_token" in response and response["access_token"]:
                    self.access_token = response["access_token"]

                    # Save token to file
                    try:
                        token_file = os.path.join(BaseEnums.CONFIG_PATH, "fyers_token.json")

                        # Ensure directory exists
                        os.makedirs(BaseEnums.CONFIG_PATH, exist_ok=True)

                        # Write atomically
                        temp_file = token_file + ".tmp"
                        with open(temp_file, "w", encoding='utf-8') as f:
                            json.dump(response, f, indent=2)
                        os.replace(temp_file, token_file)

                        logger.info("Token received and saved successfully")

                    except PermissionError as e:
                        logger.error(f"Permission denied saving token file: {e}")
                    except IOError as e:
                        logger.error(f"Failed to save token file: {e}", exc_info=True)
                    except Exception as e:
                        logger.error(f"Unexpected error saving token: {e}", exc_info=True)

                    return self.access_token
                else:
                    error_msg = f"Token exchange failed. Response missing access_token: {response}"
                    logger.error(error_msg)
                    return None
            else:
                error_msg = f"Unexpected response type from generate_token: {type(response)}"
                logger.error(error_msg)
                return None

        except Exception as e:
            logger.error(f"Exception during token exchange: {e}", exc_info=True)
            return None

    def get_access_token(self) -> Optional[str]:
        """Get the current access token."""
        try:
            return self.access_token
        except Exception as e:
            logger.error(f"[get_access_token] Failed: {e}", exc_info=True)
            return None

    def is_authenticated(self) -> bool:
        """Check if helper has a valid access token."""
        try:
            return bool(self.access_token and len(self.access_token) > 50)
        except Exception as e:
            logger.error(f"[is_authenticated] Failed: {e}", exc_info=True)
            return False

    def clear_token(self) -> None:
        """Clear the current token and optionally delete token file."""
        try:
            self.access_token = None
            logger.info("Token cleared from memory")
        except Exception as e:
            logger.error(f"[clear_token] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown."""
        try:
            logger.info("[FyersManualLoginHelper] Starting cleanup")
            self.clear_token()
            logger.info("[FyersManualLoginHelper] Cleanup completed")
        except Exception as e:
            logger.error(f"[FyersManualLoginHelper.cleanup] Error: {e}", exc_info=True)