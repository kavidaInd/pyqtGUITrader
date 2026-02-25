"""
BrokerageSetting_db.py
======================
Database-backed brokerage settings using the SQLite database.
"""

import logging
import logging.handlers
from typing import Dict, Any, Optional

from db.connector import get_db
from db.crud import brokerage

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class BrokerageSetting:
    """
    Database-backed brokerage settings using the brokerage_setting table.

    This is a drop-in replacement for the JSON-based BrokerageSetting class,
    maintaining the same interface while using the database.
    """

    REQUIRED_FIELDS = ["client_id", "secret_key", "redirect_uri"]

    def __init__(self):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Load from database
            self.load()
            logger.info("BrokerageSetting (database) initialized")

        except Exception as e:
            logger.critical(f"[BrokerageSetting.__init__] Failed: {e}", exc_info=True)
            # Still set basic attributes to prevent crashes
            self._data = {k: "" for k in self.REQUIRED_FIELDS}

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._data: Dict[str, str] = {k: "" for k in self.REQUIRED_FIELDS}
        self._loaded = False

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

    def save(self) -> bool:
        """
        Save brokerage settings to database.

        Returns:
            bool: True if save successful, False otherwise
        """
        try:
            db = get_db()
            success = brokerage.save(self._data, db)

            if success:
                logger.debug("Brokerage settings saved to database")
            else:
                logger.error("Failed to save brokerage settings to database")

            return success

        except Exception as e:
            logger.error(f"[BrokerageSetting.save] Failed: {e}", exc_info=True)
            return False

    def to_dict(self) -> Dict[str, str]:
        """
        Convert settings to dictionary.

        Returns:
            Dict[str, str]: Settings as dictionary
        """
        try:
            # Return a copy to prevent external modification
            return dict(self._data)
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
                return

            if not isinstance(d, dict):
                logger.error(f"from_dict expected dict, got {type(d)}. Using defaults.")
                self._data = {k: "" for k in self.REQUIRED_FIELDS}
                return

            # Update data with validated values
            for k in self.REQUIRED_FIELDS:
                value = d.get(k, "")
                self._data[k] = str(value) if value is not None else ""

            logger.debug("Brokerage settings loaded from dict")

        except Exception as e:
            logger.error(f"[BrokerageSetting.from_dict] Failed: {e}", exc_info=True)
            self._data = {k: "" for k in self.REQUIRED_FIELDS}

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

            value = self._data.get(key, default)
            return str(value) if value is not None else default

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

            # Ensure key is in REQUIRED_FIELDS
            if key not in self.REQUIRED_FIELDS:
                logger.warning(f"set() called with non-standard key '{key}'")
                # Still allow it, but log warning

            self._data[key] = str(value) if value is not None else ""
            logger.debug(f"Setting '{key}' updated")
            return True

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

    def __repr__(self) -> str:
        """Safe string representation (hides secret_key)."""
        try:
            safe = {k: (v if k != "secret_key" else "***") for k, v in self._data.items()}
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

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        try:
            logger.info("[BrokerageSetting] Starting cleanup")
            # Clear data
            self._data.clear()
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