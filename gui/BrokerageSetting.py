import json
import logging.handlers
import os
from typing import Dict, Any, Optional

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class BrokerageSetting:
    REQUIRED_FIELDS = ["client_id", "secret_key", "redirect_uri"]

    # Rule 2: Class-level constants for defaults
    DEFAULT_DATA: Dict[str, str] = {k: "" for k in REQUIRED_FIELDS}

    def __init__(self, json_file: str = 'config/brokerage_setting.json'):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if not isinstance(json_file, str):
                logger.error(f"json_file must be string, got {type(json_file)}. Using default.")
                json_file = 'config/brokerage_setting.json'

            self.json_file = json_file
            self.data = {k: "" for k in self.REQUIRED_FIELDS}
            self.load()

            logger.info(f"BrokerageSetting initialized with file: {self.json_file}")

        except Exception as e:
            logger.critical(f"[BrokerageSetting.__init__] Failed: {e}", exc_info=True)
            # Still set basic attributes to prevent crashes
            self.json_file = json_file if isinstance(json_file, str) else 'config/brokerage_setting.json'
            self.data = {k: "" for k in self.REQUIRED_FIELDS}

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.json_file = 'config/brokerage_setting.json'
        self.data: Dict[str, str] = {}
        self._loaded = False
        self._load_attempts = 0
        self.MAX_LOAD_ATTEMPTS = 3

    def load(self) -> bool:
        """
        Load brokerage settings from JSON file.

        Returns:
            bool: True if load successful, False otherwise
        """
        try:
            # Rule 6: Validate file path
            if not self.json_file:
                logger.error("Cannot load: json_file is None or empty")
                return False

            # Check if file exists
            if not os.path.exists(self.json_file):
                logger.warning(f"Brokerage settings file not found at {self.json_file}. Using defaults.")
                self.data = dict(self.DEFAULT_DATA)
                return False

            # Read and parse file
            try:
                with open(self.json_file, "r", encoding='utf-8') as f:
                    loaded = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse brokerage settings JSON in {self.json_file}: {e}")
                # Try to create backup of corrupted file
                self._backup_corrupted_file()
                self.data = dict(self.DEFAULT_DATA)
                return False
            except IOError as e:
                logger.error(f"Failed to read brokerage settings file {self.json_file}: {e}")
                self.data = dict(self.DEFAULT_DATA)
                return False

            # Validate that loaded data is a dictionary
            if not isinstance(loaded, dict):
                logger.error(
                    f"Invalid data format in {self.json_file}. Expected dict, got {type(loaded)}. Using defaults.")
                self.data = dict(self.DEFAULT_DATA)
                return False

            # Fill all required fields, even if file is missing some keys
            for k in self.REQUIRED_FIELDS:
                value = loaded.get(k, "")
                # Ensure value is string
                self.data[k] = str(value) if value is not None else ""

            self._loaded = True
            logger.info(f"Brokerage settings loaded successfully from {self.json_file}")
            return True

        except Exception as e:
            logger.error(f"[BrokerageSetting.load] Unexpected error: {e}", exc_info=True)
            self.data = dict(self.DEFAULT_DATA)
            return False

    def _backup_corrupted_file(self) -> None:
        """Create a backup of corrupted config file."""
        try:
            if os.path.exists(self.json_file):
                backup_file = f"{self.json_file}.corrupted.{self._load_attempts}"
                import shutil
                shutil.copy2(self.json_file, backup_file)
                logger.info(f"Corrupted brokerage settings backed up to {backup_file}")
        except Exception as e:
            logger.warning(f"Failed to backup corrupted file: {e}")

    def save(self) -> bool:
        """
        Save brokerage settings to file with atomic write.

        Returns:
            bool: True if save successful, False otherwise
        """
        tmpfile = None
        try:
            # Rule 6: Validate file path
            if not self.json_file:
                logger.error("Cannot save: json_file is None or empty")
                return False

            # Handle case where file is in current directory
            dir_path = os.path.dirname(self.json_file)
            if dir_path:  # Only create directories if there's a path
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    logger.debug(f"Ensured directory exists: {dir_path}")
                except PermissionError as e:
                    logger.error(f"Permission denied creating directory {dir_path}: {e}")
                    return False
                except Exception as e:
                    logger.error(f"Failed to create directory {dir_path}: {e}")
                    return False

            # Atomic write using temporary file
            tmpfile = self.json_file + ".tmp"

            # Prepare data for saving (ensure all values are strings)
            save_data = {}
            for k in self.REQUIRED_FIELDS:
                value = self.data.get(k, "")
                save_data[k] = str(value) if value is not None else ""

            # Write to temporary file
            try:
                with open(tmpfile, "w", encoding='utf-8') as f:
                    json.dump(save_data, f, indent=2)
            except IOError as e:
                logger.error(f"Failed to write temporary file {tmpfile}: {e}")
                return False
            except TypeError as e:
                logger.error(f"Data contains non-serializable values: {e}")
                return False

            # Atomic replace
            try:
                os.replace(tmpfile, self.json_file)
                logger.info(f"Brokerage settings saved successfully to {self.json_file}")
                return True
            except OSError as e:
                logger.error(f"Failed to replace brokerage settings file: {e}")
                self._safe_remove(tmpfile)
                return False

        except Exception as e:
            logger.error(f"[BrokerageSetting.save] Unexpected error: {e}", exc_info=True)
            if tmpfile:
                self._safe_remove(tmpfile)
            return False

    def _safe_remove(self, filepath: str) -> None:
        """Safely remove a file, ignoring errors."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.debug(f"Removed temporary file: {filepath}")
        except Exception as e:
            logger.warning(f"Failed to remove temporary file {filepath}: {e}")

    def to_dict(self) -> Dict[str, str]:
        """
        Convert settings to dictionary.

        Returns:
            Dict[str, str]: Settings as dictionary
        """
        try:
            # Return a copy to prevent external modification
            return dict(self.data)
        except Exception as e:
            logger.error(f"[BrokerageSetting.to_dict] Failed: {e}", exc_info=True)
            return dict(self.DEFAULT_DATA)

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
                self.data = dict(self.DEFAULT_DATA)
                return

            if not isinstance(d, dict):
                logger.error(f"from_dict expected dict, got {type(d)}. Using defaults.")
                self.data = dict(self.DEFAULT_DATA)
                return

            # Update data with validated values
            for k in self.REQUIRED_FIELDS:
                value = d.get(k, "")
                self.data[k] = str(value) if value is not None else ""

            logger.debug(f"Brokerage settings loaded from dict with {len(self.data)} keys")

        except Exception as e:
            logger.error(f"[BrokerageSetting.from_dict] Failed: {e}", exc_info=True)
            self.data = dict(self.DEFAULT_DATA)

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

            value = self.data.get(key, default)
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

            self.data[key] = str(value) if value is not None else ""
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
                value = self.data.get(field, "")
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
            safe = {k: (v if k != "secret_key" else "***") for k, v in self.data.items()}
            return f"<BrokerageSetting {safe}>"
        except Exception as e:
            logger.error(f"[BrokerageSetting.__repr__] Failed: {e}", exc_info=True)
            return "<BrokerageSetting Error>"

    # Property accessors with error handling
    @property
    def client_id(self) -> str:
        """Get client ID."""
        try:
            return str(self.data.get("client_id", ""))
        except Exception as e:
            logger.error(f"[BrokerageSetting.client_id getter] Failed: {e}", exc_info=True)
            return ""

    @client_id.setter
    def client_id(self, value: str) -> None:
        """Set client ID."""
        try:
            self.data["client_id"] = str(value) if value is not None else ""
        except Exception as e:
            logger.error(f"[BrokerageSetting.client_id setter] Failed: {e}", exc_info=True)

    @property
    def secret_key(self) -> str:
        """Get secret key."""
        try:
            return str(self.data.get("secret_key", ""))
        except Exception as e:
            logger.error(f"[BrokerageSetting.secret_key getter] Failed: {e}", exc_info=True)
            return ""

    @secret_key.setter
    def secret_key(self, value: str) -> None:
        """Set secret key."""
        try:
            self.data["secret_key"] = str(value) if value is not None else ""
        except Exception as e:
            logger.error(f"[BrokerageSetting.secret_key setter] Failed: {e}", exc_info=True)

    @property
    def redirect_uri(self) -> str:
        """Get redirect URI."""
        try:
            return str(self.data.get("redirect_uri", ""))
        except Exception as e:
            logger.error(f"[BrokerageSetting.redirect_uri getter] Failed: {e}", exc_info=True)
            return ""

    @redirect_uri.setter
    def redirect_uri(self, value: str) -> None:
        """Set redirect URI."""
        try:
            self.data["redirect_uri"] = str(value) if value is not None else ""
        except Exception as e:
            logger.error(f"[BrokerageSetting.redirect_uri setter] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        try:
            logger.info("[BrokerageSetting] Starting cleanup")
            # Clear data
            self.data.clear()
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
            # Restore backup - FIXED: Use explicit None check
            if self.settings is not None and self._backup is not None:
                self.settings.from_dict(self._backup)
                logger.debug("BrokerageSettingContext restored backup")

        except Exception as e:
            logger.error(f"[BrokerageSettingContext.__exit__] Failed: {e}", exc_info=True)
            # Log but don't re-raise to avoid masking original exception
            if exc_type:
                logger.error(f"Original exception: {exc_type.__name__}: {exc_val}")