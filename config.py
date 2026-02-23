import json
import os
import logging
import logging.handlers
from typing import Dict, Any, Optional
import traceback

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class Config:
    """
    Configuration management class with robust error handling.
    Preserves all existing functionality while adding defensive programming.
    """

    # Rule 2: Class-level constants for defaults
    DEFAULT_CONFIG: Dict[str, Any] = {
        # Add your default configuration values here
        # This is a placeholder - populate with actual defaults
    }

    def __init__(self, config_file: str = "config/strategy_setting.json"):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if not isinstance(config_file, str):
                logger.error(f"config_file must be string, got {type(config_file)}. Using default.")
                config_file = "config/strategy_setting.json"

            self.config_file = config_file
            # Default values
            self.load()

            logger.info(f"Config initialized with file: {self.config_file}")

        except Exception as e:
            logger.critical(f"[Config.__init__] Failed: {e}", exc_info=True)
            # Still set basic attributes to prevent crashes
            self.config_file = config_file if isinstance(config_file, str) else "config/strategy_setting.json"
            self.load()  # Try loading again with defaults

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.config_file = "config/strategy_setting.json"
        self._config_data: Dict[str, Any] = {}
        self._loaded = False
        self._load_attempts = 0
        self.MAX_LOAD_ATTEMPTS = 3

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert config to dictionary.

        Returns:
            Dict[str, Any]: Configuration as dictionary
        """
        try:
            # Return a copy to prevent external modification
            return dict(self._config_data)

        except Exception as e:
            logger.error(f"[Config.to_dict] Failed: {e}", exc_info=True)
            return {}  # Return empty dict on error

    def from_dict(self, d: Optional[Dict[str, Any]]) -> None:
        """
        Load configuration from dictionary.

        Args:
            d: Dictionary containing configuration values
        """
        try:
            # Rule 6: Input validation
            if d is None:
                logger.warning("from_dict called with None, using defaults")
                self._config_data = dict(self.DEFAULT_CONFIG)
                return

            if not isinstance(d, dict):
                logger.error(f"from_dict expected dict, got {type(d)}. Using defaults.")
                self._config_data = dict(self.DEFAULT_CONFIG)
                return

            # Update config data with validated values
            validated_data = {}
            for key, value in d.items():
                try:
                    # You can add type validation here if needed
                    validated_data[key] = value
                except Exception as e:
                    logger.warning(f"Failed to validate config key {key}: {e}")
                    # Use default if available
                    if key in self.DEFAULT_CONFIG:
                        validated_data[key] = self.DEFAULT_CONFIG[key]

            self._config_data = validated_data
            self._loaded = True
            logger.debug(f"Config loaded from dict with {len(validated_data)} keys")

        except Exception as e:
            logger.error(f"[Config.from_dict] Failed: {e}", exc_info=True)
            self._config_data = dict(self.DEFAULT_CONFIG)

    def save(self) -> bool:
        """
        Save configuration to file with atomic write.

        Returns:
            bool: True if save successful, False otherwise
        """
        tmp_file = None
        try:
            # Rule 6: Validate config file path
            if not self.config_file:
                logger.error("Cannot save: config_file is None or empty")
                return False

            # Create directory if it doesn't exist
            config_dir = os.path.dirname(self.config_file)
            if config_dir:
                try:
                    os.makedirs(config_dir, exist_ok=True)
                    logger.debug(f"Ensured directory exists: {config_dir}")
                except PermissionError as e:
                    logger.error(f"Permission denied creating directory {config_dir}: {e}")
                    return False
                except Exception as e:
                    logger.error(f"Failed to create directory {config_dir}: {e}")
                    return False

            # Atomic write using temporary file
            tmp_file = f"{self.config_file}.tmp"

            # Get config data
            config_data = self.to_dict()

            # Write to temporary file
            try:
                with open(tmp_file, "w", encoding='utf-8') as f:
                    json.dump(config_data, f, indent=4, ensure_ascii=False)
            except IOError as e:
                logger.error(f"Failed to write temporary config file {tmp_file}: {e}")
                return False
            except TypeError as e:
                logger.error(f"Config data contains non-serializable values: {e}")
                return False

            # Atomic replace
            try:
                os.replace(tmp_file, self.config_file)
                logger.info(f"Config saved successfully to {self.config_file}")
                return True
            except OSError as e:
                logger.error(f"Failed to replace config file: {e}")
                # Try to clean up temp file
                self._safe_remove(tmp_file)
                return False

        except Exception as e:
            logger.error(f"[Config.save] Unexpected error: {e}", exc_info=True)
            # Clean up temp file if it exists
            if tmp_file:
                self._safe_remove(tmp_file)
            return False

    def _safe_remove(self, filepath: str) -> None:
        """Safely remove a file, ignoring errors."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            logger.warning(f"Failed to remove temporary file {filepath}: {e}")

    def load(self) -> bool:
        """
        Load configuration from file.

        Returns:
            bool: True if load successful, False otherwise
        """
        try:
            # Rule 6: Validate config file
            if not self.config_file:
                logger.error("Cannot load: config_file is None or empty")
                self._config_data = dict(self.DEFAULT_CONFIG)
                return False

            # Check if file exists
            if not os.path.exists(self.config_file):
                logger.warning(f"Config file not found at {self.config_file}. Using default settings.")
                self._config_data = dict(self.DEFAULT_CONFIG)
                return False

            # Read and parse file
            try:
                with open(self.config_file, "r", encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Config file {self.config_file} contains invalid JSON: {e}")
                # Try to create backup of corrupted file
                self._backup_corrupted_file()
                self._config_data = dict(self.DEFAULT_CONFIG)
                return False
            except IOError as e:
                logger.error(f"Failed to read config file {self.config_file}: {e}")
                self._config_data = dict(self.DEFAULT_CONFIG)
                return False

            # Validate loaded data
            if not isinstance(data, dict):
                logger.error(f"Config file must contain a JSON object, got {type(data)}")
                self._config_data = dict(self.DEFAULT_CONFIG)
                return False

            # Load data
            self.from_dict(data)
            logger.info(f"Config loaded successfully from {self.config_file}")
            return True

        except Exception as e:
            logger.error(f"[Config.load] Unexpected error: {e}", exc_info=True)
            self._config_data = dict(self.DEFAULT_CONFIG)
            return False

    def _backup_corrupted_file(self) -> None:
        """Create a backup of corrupted config file."""
        try:
            if os.path.exists(self.config_file):
                backup_file = f"{self.config_file}.corrupted.{self._load_attempts}"
                import shutil
                shutil.copy2(self.config_file, backup_file)
                logger.info(f"Corrupted config backed up to {backup_file}")
        except Exception as e:
            logger.warning(f"Failed to backup corrupted file: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key with safe default.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        try:
            # Rule 6: Input validation
            if not isinstance(key, str):
                logger.warning(f"get() called with non-string key: {key}")
                return default

            return self._config_data.get(key, default)

        except Exception as e:
            logger.error(f"[Config.get] Failed for key '{key}': {e}", exc_info=True)
            return default

    def set(self, key: str, value: Any) -> bool:
        """
        Set configuration value.

        Args:
            key: Configuration key
            value: Value to set

        Returns:
            bool: True if successful
        """
        try:
            # Rule 6: Input validation
            if not isinstance(key, str):
                logger.warning(f"set() called with non-string key: {key}")
                return False

            # Validate key (prevent empty keys)
            if not key.strip():
                logger.warning("set() called with empty key")
                return False

            self._config_data[key] = value
            logger.debug(f"Config key '{key}' set to {value}")
            return True

        except Exception as e:
            logger.error(f"[Config.set] Failed for key '{key}': {e}", exc_info=True)
            return False

    def update(self, data: Dict[str, Any]) -> bool:
        """
        Update multiple configuration values.

        Args:
            data: Dictionary of key-value pairs to update

        Returns:
            bool: True if successful
        """
        try:
            # Rule 6: Input validation
            if not isinstance(data, dict):
                logger.error(f"update() expected dict, got {type(data)}")
                return False

            # Update each key
            success = True
            for key, value in data.items():
                if not self.set(key, value):
                    logger.warning(f"Failed to update key '{key}'")
                    success = False

            return success

        except Exception as e:
            logger.error(f"[Config.update] Failed: {e}", exc_info=True)
            return False

    def keys(self) -> list:
        """Get all configuration keys."""
        try:
            return list(self._config_data.keys())
        except Exception as e:
            logger.error(f"[Config.keys] Failed: {e}", exc_info=True)
            return []

    def values(self) -> list:
        """Get all configuration values."""
        try:
            return list(self._config_data.values())
        except Exception as e:
            logger.error(f"[Config.values] Failed: {e}", exc_info=True)
            return []

    def items(self) -> list:
        """Get all configuration items as (key, value) pairs."""
        try:
            return list(self._config_data.items())
        except Exception as e:
            logger.error(f"[Config.items] Failed: {e}", exc_info=True)
            return []

    def clear(self) -> None:
        """Clear all configuration data."""
        try:
            self._config_data.clear()
            logger.debug("Config cleared")
        except Exception as e:
            logger.error(f"[Config.clear] Failed: {e}", exc_info=True)

    def reload(self) -> bool:
        """
        Reload configuration from file.

        Returns:
            bool: True if reload successful
        """
        try:
            logger.info("Reloading configuration from file")
            return self.load()
        except Exception as e:
            logger.error(f"[Config.reload] Failed: {e}", exc_info=True)
            return False

    def __repr__(self) -> str:
        """String representation of Config."""
        try:
            return f"Config({self._config_data})"
        except Exception as e:
            logger.error(f"[Config.__repr__] Failed: {e}", exc_info=True)
            return "Config(Error getting representation)"

    def __contains__(self, key: str) -> bool:
        """Check if key exists in config."""
        try:
            return key in self._config_data
        except Exception as e:
            logger.error(f"[Config.__contains__] Failed for key '{key}': {e}", exc_info=True)
            return False

    def __getitem__(self, key: str) -> Any:
        """Dictionary-style access."""
        try:
            return self._config_data[key]
        except KeyError:
            raise  # Re-raise KeyError as expected
        except Exception as e:
            logger.error(f"[Config.__getitem__] Failed for key '{key}': {e}", exc_info=True)
            raise KeyError(f"Error accessing key '{key}'") from e

    def __setitem__(self, key: str, value: Any) -> None:
        """Dictionary-style assignment."""
        try:
            self._config_data[key] = value
        except Exception as e:
            logger.error(f"[Config.__setitem__] Failed for key '{key}': {e}", exc_info=True)
            raise  # Re-raise to maintain expected behavior


# Optional: Context manager for temporary config changes
class ConfigContext:
    """
    Context manager for temporarily modifying config.

    Example:
        with ConfigContext(config) as cfg:
            cfg.set('key', 'temp_value')
            # ... do something with temp value
        # Config automatically reverts
    """

    def __init__(self, config: Config):
        # Rule 2: Safe defaults
        self.config = None
        self._backup = None

        try:
            # Rule 6: Input validation
            if not isinstance(config, Config):
                raise ValueError(f"Expected Config instance, got {type(config)}")

            self.config = config
            self._backup = config.to_dict()
            logger.debug("ConfigContext initialized")

        except Exception as e:
            logger.error(f"[ConfigContext.__init__] Failed: {e}", exc_info=True)
            raise

    def __enter__(self):
        return self.config

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            # Restore backup
            if self.config and self._backup is not None:
                self.config.clear()
                self.config.from_dict(self._backup)
                logger.debug("ConfigContext restored backup")

        except Exception as e:
            logger.error(f"[ConfigContext.__exit__] Failed: {e}", exc_info=True)
            # Log but don't re-raise to avoid masking original exception
            if exc_type:
                logger.error(f"Original exception: {exc_type.__name__}: {exc_val}")