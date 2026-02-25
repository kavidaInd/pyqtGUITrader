"""
BrokerageSetting_db.py
======================
Database-backed brokerage settings using the SQLite database.

Enhanced with support for:
- FEATURE 4: Telegram notification settings
- Token management and expiry tracking
- Connection status monitoring
"""

import logging
import logging.handlers
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from db.connector import get_db
from db.crud import brokerage, tokens
from db.config_crud import config_crud

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class BrokerageSetting:
    """
    Database-backed brokerage settings using the brokerage_setting table.

    Enhanced with token management and Telegram settings support.
    This is a drop-in replacement for the JSON-based BrokerageSetting class,
    maintaining the same interface while using the database.
    """

    REQUIRED_FIELDS = ["client_id", "secret_key", "redirect_uri"]

    # FEATURE 4: Telegram settings
    TELEGRAM_FIELDS = ["telegram_bot_token", "telegram_chat_id"]

    def __init__(self):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Load from database
            self.load()

            # FEATURE 4: Load Telegram settings
            self._load_telegram_settings()

            # Load token information
            self._load_token_info()

            logger.info("BrokerageSetting (database) initialized")

        except Exception as e:
            logger.critical(f"[BrokerageSetting.__init__] Failed: {e}", exc_info=True)
            # Still set basic attributes to prevent crashes
            self._data = {k: "" for k in self.REQUIRED_FIELDS}
            self._telegram_data = {k: "" for k in self.TELEGRAM_FIELDS}
            self._token_data = {}

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._data: Dict[str, str] = {k: "" for k in self.REQUIRED_FIELDS}
        self._telegram_data: Dict[str, str] = {k: "" for k in self.TELEGRAM_FIELDS}
        self._token_data: Dict[str, Any] = {
            "access_token": "",
            "refresh_token": "",
            "issued_at": None,
            "expires_at": None,
            "is_valid": False
        }
        self._loaded = False
        self._token_loaded = False
        self._telegram_loaded = False

    def load(self) -> bool:
        """
        Load brokerage settings from database.

        Returns:
            bool: True if load successful, False otherwise
        """
        try:
            db = get_db()
            data = brokerage.get(db)

            if data:
                for k in self.REQUIRED_FIELDS:
                    self._data[k] = str(data.get(k, ""))
            else:
                # No data found, use defaults
                for k in self.REQUIRED_FIELDS:
                    self._data[k] = ""

            self._loaded = True
            logger.debug("Brokerage settings loaded from database")
            return True

        except Exception as e:
            logger.error(f"[BrokerageSetting.load] Failed: {e}", exc_info=True)
            return False

    def _load_telegram_settings(self):
        """
        FEATURE 4: Load Telegram settings from config.
        """
        try:
            db = get_db()

            # Load from config_crud (app_kv table)
            self._telegram_data["telegram_bot_token"] = config_crud.get("telegram_bot_token", "", db)
            self._telegram_data["telegram_chat_id"] = config_crud.get("telegram_chat_id", "", db)

            self._telegram_loaded = True
            logger.debug("Telegram settings loaded from database")

        except Exception as e:
            logger.error(f"[BrokerageSetting._load_telegram_settings] Failed: {e}", exc_info=True)

    def _load_token_info(self):
        """
        Load token information from broker_tokens table.
        """
        try:
            db = get_db()
            token_data = tokens.get(db)

            if token_data:
                self._token_data["access_token"] = token_data.get("access_token", "")
                self._token_data["refresh_token"] = token_data.get("refresh_token", "")
                self._token_data["issued_at"] = token_data.get("issued_at")
                self._token_data["expires_at"] = token_data.get("expires_at")

                # Check if token is valid
                self._token_data["is_valid"] = self._check_token_valid()
            else:
                # No token data
                self._token_data = {
                    "access_token": "",
                    "refresh_token": "",
                    "issued_at": None,
                    "expires_at": None,
                    "is_valid": False
                }

            self._token_loaded = True
            logger.debug("Token info loaded from database")

        except Exception as e:
            logger.error(f"[BrokerageSetting._load_token_info] Failed: {e}", exc_info=True)

    def _check_token_valid(self) -> bool:
        """Check if current token is valid and not expired."""
        try:
            if not self._token_data.get("access_token"):
                return False

            # Check expiry if available
            expires_at = self._token_data.get("expires_at")
            if expires_at:
                try:
                    # Parse expiry string
                    if isinstance(expires_at, str):
                        expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    else:
                        expiry_time = expires_at

                    # Check if expired (with 5 minute buffer)
                    if datetime.now() > (expiry_time - timedelta(minutes=5)):
                        return False
                except Exception as e:
                    logger.warning(f"Failed to parse expiry time: {e}")

            return True

        except Exception as e:
            logger.error(f"[BrokerageSetting._check_token_valid] Failed: {e}", exc_info=True)
            return False

    def save(self) -> bool:
        """
        Save brokerage settings to database.

        Returns:
            bool: True if save successful, False otherwise
        """
        try:
            db = get_db()

            # Save brokerage settings
            success = brokerage.save(self._data, db)

            if success:
                logger.debug("Brokerage settings saved to database")

                # FEATURE 4: Save Telegram settings
                self._save_telegram_settings()
            else:
                logger.error("Failed to save brokerage settings to database")

            return success

        except Exception as e:
            logger.error(f"[BrokerageSetting.save] Failed: {e}", exc_info=True)
            return False

    def _save_telegram_settings(self):
        """
        FEATURE 4: Save Telegram settings to config.
        """
        try:
            db = get_db()

            # Save to config_crud (app_kv table)
            config_crud.set("telegram_bot_token", self._telegram_data.get("telegram_bot_token", ""), db)
            config_crud.set("telegram_chat_id", self._telegram_data.get("telegram_chat_id", ""), db)

            logger.debug("Telegram settings saved to database")

        except Exception as e:
            logger.error(f"[BrokerageSetting._save_telegram_settings] Failed: {e}", exc_info=True)

    def save_token(self, access_token: str, refresh_token: str = "",
                   issued_at: str = None, expires_at: str = None) -> bool:
        """
        Save token information to database.

        Args:
            access_token: Access token
            refresh_token: Refresh token
            issued_at: Token issue timestamp
            expires_at: Token expiry timestamp

        Returns:
            bool: True if successful
        """
        try:
            db = get_db()
            success = tokens.save_token(access_token, refresh_token, issued_at, expires_at, db)

            if success:
                # Update local cache
                self._token_data["access_token"] = access_token
                self._token_data["refresh_token"] = refresh_token
                self._token_data["issued_at"] = issued_at
                self._token_data["expires_at"] = expires_at
                self._token_data["is_valid"] = True

                logger.info("Token saved successfully")
            else:
                logger.error("Failed to save token")

            return success

        except Exception as e:
            logger.error(f"[BrokerageSetting.save_token] Failed: {e}", exc_info=True)
            return False

    def clear_token(self) -> bool:
        """
        Clear token information.

        Returns:
            bool: True if successful
        """
        try:
            db = get_db()
            success = tokens.save_token("", "", db=db)

            if success:
                self._token_data = {
                    "access_token": "",
                    "refresh_token": "",
                    "issued_at": None,
                    "expires_at": None,
                    "is_valid": False
                }
                logger.info("Token cleared")

            return success

        except Exception as e:
            logger.error(f"[BrokerageSetting.clear_token] Failed: {e}", exc_info=True)
            return False

    def to_dict(self) -> Dict[str, str]:
        """
        Convert settings to dictionary.

        Returns:
            Dict[str, str]: Settings as dictionary
        """
        try:
            # Combine all settings
            result = dict(self._data)

            # FEATURE 4: Add Telegram settings
            result.update(self._telegram_data)

            # Add token status
            result["has_token"] = str(self._token_data.get("is_valid", False))
            result["token_expiry"] = str(self._token_data.get("expires_at", ""))

            return result
        except Exception as e:
            logger.error(f"[BrokerageSetting.to_dict] Failed: {e}", exc_info=True)
            return {k: "" for k in self.REQUIRED_FIELDS}

    def from_dict(self, d: Optional[Dict[str, Any]]) -> None:
        """
        Load settings from dictionary.

        Args:
            d: Dictionary containing setting values
        """
        try:
            # Rule 6: Input validation
            if d is None:
                logger.warning("from_dict called with None, using defaults")
                self._data = {k: "" for k in self.REQUIRED_FIELDS}
                self._telegram_data = {k: "" for k in self.TELEGRAM_FIELDS}
                return

            if not isinstance(d, dict):
                logger.error(f"from_dict expected dict, got {type(d)}. Using defaults.")
                self._data = {k: "" for k in self.REQUIRED_FIELDS}
                self._telegram_data = {k: "" for k in self.TELEGRAM_FIELDS}
                return

            # Update brokerage data with validated values
            for k in self.REQUIRED_FIELDS:
                value = d.get(k, "")
                self._data[k] = str(value) if value is not None else ""

            # FEATURE 4: Update Telegram data
            for k in self.TELEGRAM_FIELDS:
                value = d.get(k, "")
                self._telegram_data[k] = str(value) if value is not None else ""

            logger.debug("Brokerage settings loaded from dict")

        except Exception as e:
            logger.error(f"[BrokerageSetting.from_dict] Failed: {e}", exc_info=True)
            self._data = {k: "" for k in self.REQUIRED_FIELDS}
            self._telegram_data = {k: "" for k in self.TELEGRAM_FIELDS}

    def get(self, key: str, default: str = "") -> str:
        """
        Get setting value by key with safe default.

        Args:
            key: Setting key
            default: Default value if key not found

        Returns:
            str: Setting value or default
        """
        try:
            # Rule 6: Input validation
            if not isinstance(key, str):
                logger.warning(f"get() called with non-string key: {key}")
                return default

            # Check in brokerage data first
            if key in self._data:
                value = self._data.get(key, default)
                return str(value) if value is not None else default

            # FEATURE 4: Check in Telegram data
            if key in self._telegram_data:
                value = self._telegram_data.get(key, default)
                return str(value) if value is not None else default

            # Special token keys
            if key == "has_token":
                return str(self._token_data.get("is_valid", False))
            if key == "token_expiry":
                expiry = self._token_data.get("expires_at", "")
                return str(expiry) if expiry else ""

            return default

        except Exception as e:
            logger.error(f"[BrokerageSetting.get] Failed for key '{key}': {e}", exc_info=True)
            return default

    def set(self, key: str, value: str) -> bool:
        """
        Set setting value.

        Args:
            key: Setting key
            value: Value to set

        Returns:
            bool: True if successful
        """
        try:
            # Rule 6: Input validation
            if not isinstance(key, str):
                logger.warning(f"set() called with non-string key: {key}")
                return False

            if not key.strip():
                logger.warning("set() called with empty key")
                return False

            # Determine which data dict to update
            if key in self.REQUIRED_FIELDS:
                self._data[key] = str(value) if value is not None else ""
                logger.debug(f"Brokerage setting '{key}' updated")
                return True

            # FEATURE 4: Handle Telegram settings
            if key in self.TELEGRAM_FIELDS:
                self._telegram_data[key] = str(value) if value is not None else ""
                logger.debug(f"Telegram setting '{key}' updated")
                return True

            logger.warning(f"set() called with unknown key '{key}'")
            return False

        except Exception as e:
            logger.error(f"[BrokerageSetting.set] Failed for key '{key}': {e}", exc_info=True)
            return False

    def validate(self) -> Dict[str, bool]:
        """
        Validate that all required fields are present and non-empty.

        Returns:
            Dict[str, bool]: Dictionary with validation results per field
        """
        try:
            results = {}
            for field in self.REQUIRED_FIELDS:
                value = self._data.get(field, "")
                results[field] = bool(value and str(value).strip())
            return results
        except Exception as e:
            logger.error(f"[BrokerageSetting.validate] Failed: {e}", exc_info=True)
            return {field: False for field in self.REQUIRED_FIELDS}

    def is_valid(self) -> bool:
        """
        Check if all required fields are present and non-empty.

        Returns:
            bool: True if all required fields are valid
        """
        try:
            validation = self.validate()
            return all(validation.values())
        except Exception as e:
            logger.error(f"[BrokerageSetting.is_valid] Failed: {e}", exc_info=True)
            return False

    def is_telegram_configured(self) -> bool:
        """
        FEATURE 4: Check if Telegram is properly configured.

        Returns:
            bool: True if both bot token and chat ID are set
        """
        try:
            bot_token = self._telegram_data.get("telegram_bot_token", "")
            chat_id = self._telegram_data.get("telegram_chat_id", "")
            return bool(bot_token and chat_id)
        except Exception as e:
            logger.error(f"[BrokerageSetting.is_telegram_configured] Failed: {e}", exc_info=True)
            return False

    def get_telegram_config(self) -> Dict[str, str]:
        """
        FEATURE 4: Get Telegram configuration.

        Returns:
            Dict with bot_token and chat_id
        """
        try:
            return {
                "bot_token": self._telegram_data.get("telegram_bot_token", ""),
                "chat_id": self._telegram_data.get("telegram_chat_id", "")
            }
        except Exception as e:
            logger.error(f"[BrokerageSetting.get_telegram_config] Failed: {e}", exc_info=True)
            return {"bot_token": "", "chat_id": ""}

    def get_token_info(self) -> Dict[str, Any]:
        """
        Get token information.

        Returns:
            Dict with token details
        """
        try:
            return dict(self._token_data)
        except Exception as e:
            logger.error(f"[BrokerageSetting.get_token_info] Failed: {e}", exc_info=True)
            return {
                "access_token": "",
                "refresh_token": "",
                "issued_at": None,
                "expires_at": None,
                "is_valid": False
            }

    def reload_token(self) -> bool:
        """
        Reload token information from database.

        Returns:
            bool: True if successful
        """
        try:
            self._load_token_info()
            return self._token_loaded
        except Exception as e:
            logger.error(f"[BrokerageSetting.reload_token] Failed: {e}", exc_info=True)
            return False

    def __repr__(self) -> str:
        """Safe string representation (hides secret_key)."""
        try:
            safe = {k: (v if k != "secret_key" else "***") for k, v in self._data.items()}

            # Add Telegram status without exposing tokens
            safe["telegram"] = "configured" if self.is_telegram_configured() else "not configured"
            safe["token_valid"] = self._token_data.get("is_valid", False)

            return f"<BrokerageSetting {safe}>"
        except Exception as e:
            logger.error(f"[BrokerageSetting.__repr__] Failed: {e}", exc_info=True)
            return "<BrokerageSetting Error>"

    # Property accessors with error handling
    @property
    def client_id(self) -> str:
        """Get client ID."""
        try:
            return str(self._data.get("client_id", ""))
        except Exception as e:
            logger.error(f"[BrokerageSetting.client_id getter] Failed: {e}", exc_info=True)
            return ""

    @client_id.setter
    def client_id(self, value: str) -> None:
        """Set client ID."""
        try:
            self._data["client_id"] = str(value) if value is not None else ""
        except Exception as e:
            logger.error(f"[BrokerageSetting.client_id setter] Failed: {e}", exc_info=True)

    @property
    def secret_key(self) -> str:
        """Get secret key."""
        try:
            return str(self._data.get("secret_key", ""))
        except Exception as e:
            logger.error(f"[BrokerageSetting.secret_key getter] Failed: {e}", exc_info=True)
            return ""

    @secret_key.setter
    def secret_key(self, value: str) -> None:
        """Set secret key."""
        try:
            self._data["secret_key"] = str(value) if value is not None else ""
        except Exception as e:
            logger.error(f"[BrokerageSetting.secret_key setter] Failed: {e}", exc_info=True)

    @property
    def redirect_uri(self) -> str:
        """Get redirect URI."""
        try:
            return str(self._data.get("redirect_uri", ""))
        except Exception as e:
            logger.error(f"[BrokerageSetting.redirect_uri getter] Failed: {e}", exc_info=True)
            return ""

    @redirect_uri.setter
    def redirect_uri(self, value: str) -> None:
        """Set redirect URI."""
        try:
            self._data["redirect_uri"] = str(value) if value is not None else ""
        except Exception as e:
            logger.error(f"[BrokerageSetting.redirect_uri setter] Failed: {e}", exc_info=True)

    # FEATURE 4: Telegram properties
    @property
    def telegram_bot_token(self) -> str:
        """Get Telegram bot token."""
        try:
            return str(self._telegram_data.get("telegram_bot_token", ""))
        except Exception as e:
            logger.error(f"[BrokerageSetting.telegram_bot_token getter] Failed: {e}", exc_info=True)
            return ""

    @telegram_bot_token.setter
    def telegram_bot_token(self, value: str) -> None:
        """Set Telegram bot token."""
        try:
            self._telegram_data["telegram_bot_token"] = str(value) if value is not None else ""
        except Exception as e:
            logger.error(f"[BrokerageSetting.telegram_bot_token setter] Failed: {e}", exc_info=True)

    @property
    def telegram_chat_id(self) -> str:
        """Get Telegram chat ID."""
        try:
            return str(self._telegram_data.get("telegram_chat_id", ""))
        except Exception as e:
            logger.error(f"[BrokerageSetting.telegram_chat_id getter] Failed: {e}", exc_info=True)
            return ""

    @telegram_chat_id.setter
    def telegram_chat_id(self, value: str) -> None:
        """Set Telegram chat ID."""
        try:
            self._telegram_data["telegram_chat_id"] = str(value) if value is not None else ""
        except Exception as e:
            logger.error(f"[BrokerageSetting.telegram_chat_id setter] Failed: {e}", exc_info=True)

    @property
    def has_valid_token(self) -> bool:
        """Check if a valid token exists."""
        try:
            return self._token_data.get("is_valid", False)
        except Exception as e:
            logger.error(f"[BrokerageSetting.has_valid_token] Failed: {e}", exc_info=True)
            return False

    @property
    def token_expiry(self) -> Optional[str]:
        """Get token expiry timestamp."""
        try:
            expiry = self._token_data.get("expires_at")
            return str(expiry) if expiry else None
        except Exception as e:
            logger.error(f"[BrokerageSetting.token_expiry] Failed: {e}", exc_info=True)
            return None

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        try:
            logger.info("[BrokerageSetting] Starting cleanup")
            # Clear data
            self._data.clear()
            self._telegram_data.clear()
            self._token_data.clear()
            logger.info("[BrokerageSetting] Cleanup completed")
        except Exception as e:
            logger.error(f"[BrokerageSetting.cleanup] Error: {e}", exc_info=True)


# Optional: Context manager for temporary settings changes
class BrokerageSettingContext:
    """
    Context manager for temporarily modifying brokerage settings.

    Example:
        with BrokerageSettingContext(settings) as bs:
            bs.client_id = "temp_id"
            # ... do something with temp settings
        # Settings automatically revert
    """

    def __init__(self, settings: BrokerageSetting):
        # Rule 2: Safe defaults
        self.settings = None
        self._backup = None

        try:
            # Rule 6: Input validation
            if not isinstance(settings, BrokerageSetting):
                raise ValueError(f"Expected BrokerageSetting instance, got {type(settings)}")

            self.settings = settings
            self._backup = settings.to_dict()
            logger.debug("BrokerageSettingContext initialized")

        except Exception as e:
            logger.error(f"[BrokerageSettingContext.__init__] Failed: {e}", exc_info=True)
            raise

    def __enter__(self) -> BrokerageSetting:
        return self.settings

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            # Restore backup
            if self.settings is not None and self._backup is not None:
                self.settings.from_dict(self._backup)
                # Save to database to persist the restoration
                self.settings.save()
                logger.debug("BrokerageSettingContext restored backup")

        except Exception as e:
            logger.error(f"[BrokerageSettingContext.__exit__] Failed: {e}", exc_info=True)
            # Log but don't re-raise to avoid masking original exception
            if exc_type:
                logger.error(f"Original exception: {exc_type.__name__}: {exc_val}")