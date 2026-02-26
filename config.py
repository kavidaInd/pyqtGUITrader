"""
Configuration Management Module
===============================
Database-backed configuration management system providing centralized access
to all trading bot settings with automatic default value initialization.

This module replaces traditional file-based configuration with a robust
database solution, enabling runtime configuration changes, persistence across
restarts, and multi-instance synchronization.

Key Features:
    - Database persistence for all configuration values
    - Automatic default initialization on first run
    - Type-safe get/set operations with error handling
    - Grouped configuration access for specific features
    - Context manager for temporary modifications
    - Singleton pattern for global configuration access
"""

import logging
from typing import Any, Dict, Optional

from db.config_crud import config_crud
from db.connector import get_db

logger = logging.getLogger(__name__)


class Config:
    """
    Database-backed configuration management singleton.

    Provides a unified interface for accessing and modifying all trading bot
    configuration settings. Values are stored in the database and automatically
    initialized with sensible defaults if not present.

    The configuration is organized by feature groups for better maintainability:
        - Risk Management: Daily loss limits, trade caps
        - Signal Processing: Confidence thresholds, filters
        - Notifications: Telegram integration settings
        - Trading Parameters: Market hours, position sizing
        - System Settings: Logging, retention policies

    All methods include comprehensive error handling to prevent crashes,
    logging errors and returning safe defaults when database operations fail.

    Default Configuration Values:
    -----------------------------
    FEATURE 1 - Risk Manager:
        max_daily_loss: -5000        # Maximum daily loss before stopping (negative ₹)
        max_trades_per_day: 10       # Maximum trades per day

    FEATURE 3 - Signal Confidence:
        min_confidence: 0.6           # Minimum confidence threshold (0.0-1.0)

    FEATURE 4 - Telegram Notifications:
        telegram_bot_token: ''        # Bot token from @BotFather
        telegram_chat_id: ''           # Chat ID for notifications

    FEATURE 5 - Daily P&L Panel:
        daily_target: 5000             # Daily profit target

    FEATURE 6 - Multi-Timeframe Filter:
        use_mtf_filter: False          # Enable/disable MTF filter

    FEATURE 7 - Trade History:
        history_retention_days: 30     # Days to keep trade history

    MISC:
        market_open_time: "09:15"      # Market open time (was 09:30)
        market_close_time: "15:30"     # Market close time
    """

    def __init__(self):
        """
        Initialize the configuration manager.

        Sets up the CRUD interface and ensures all required configuration
        keys exist in the database with their default values.
        """
        self._config_crud = config_crud
        self._ensure_defaults()
        logger.info("Config (database) initialized")

    def _ensure_defaults(self) -> None:
        """
        Ensure all required configuration keys have default values.

        This method runs once at startup to populate any missing keys in the
        database with their predefined default values. Keys that already exist
        are preserved without modification.

        The method is idempotent - running multiple times only adds missing keys
        without overwriting existing values.

        Returns:
            None

        Note:
            Uses database transaction to ensure data consistency.
            Logs each default value insertion at DEBUG level.
        """
        try:
            defaults = {
                # Feature 1 - Risk Manager
                "max_daily_loss": -5000,
                "max_trades_per_day": 10,

                # Feature 3 - Signal Confidence
                "min_confidence": 0.6,

                # Feature 4 - Telegram Notifications
                "telegram_bot_token": "",
                "telegram_chat_id": "",

                # Feature 5 - Daily P&L Panel
                "daily_target": 5000,

                # Feature 6 - Multi-Timeframe Filter
                "use_mtf_filter": False,

                # Feature 7 - Trade History
                "history_retention_days": 30,

                # BUG #4 Fix - Market hours
                "market_open_time": "09:15",      # Changed from 09:30
                "market_close_time": "15:30",

                # Existing defaults (ensure they exist)
                "broker_api_key": "",
                "broker_secret": "",
                "broker_redirect_uri": "",
                "bot_type": "PAPER",               # PAPER or LIVE
                "log_level": "INFO",
                "log_retention_days": 7,
            }

            db = get_db()
            for key, default_value in defaults.items():
                # Only set if key doesn't exist
                existing = self._config_crud.get(key, None, db)
                if existing is None:
                    self._config_crud.set(key, default_value, db)
                    logger.debug(f"Set default config: {key} = {default_value}")

        except Exception as e:
            logger.error(f"[Config._ensure_defaults] Failed: {e}", exc_info=True)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert entire configuration to a dictionary.

        Retrieves all configuration key-value pairs from the database and
        returns them as a Python dictionary for serialization or display.

        Returns:
            Dict[str, Any]: Dictionary containing all configuration settings.
                           Returns empty dictionary if operation fails.

        Example:
            >>> config = Config()
            >>> all_settings = config.to_dict()
            >>> print(all_settings['max_daily_loss'])
            -5000
        """
        try:
            db = get_db()
            return self._config_crud.to_dict(db)
        except Exception as e:
            logger.error(f"[Config.to_dict] Failed: {e}", exc_info=True)
            return {}

    def from_dict(self, d: Optional[Dict[str, Any]]) -> None:
        """
        Load configuration from a dictionary.

        Updates the database with all key-value pairs from the provided
        dictionary. Existing keys are overwritten, new keys are added.

        Args:
            d: Optional[Dict[str, Any]]: Dictionary containing configuration
               settings to load. If None, method does nothing.

        Returns:
            None

        Example:
            >>> config = Config()
            >>> new_settings = {'max_daily_loss': -10000, 'log_level': 'DEBUG'}
            >>> config.from_dict(new_settings)
        """
        try:
            if d is None:
                return
            db = get_db()
            self._config_crud.from_dict(d, db)
        except Exception as e:
            logger.error(f"[Config.from_dict] Failed: {e}", exc_info=True)

    def save(self) -> bool:
        """
        Save configuration (database persistence).

        Database-backed configuration is automatically persisted, so this
        method always returns True for backward compatibility with file-based
        configuration interfaces.

        Returns:
            bool: Always returns True
        """
        return True

    def load(self) -> bool:
        """
        Load configuration (database retrieval).

        Database-backed configuration is always available, so this method
        always returns True for backward compatibility with file-based
        configuration interfaces.

        Returns:
            bool: Always returns True
        """
        return True

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Retrieves a single configuration value from the database. If the key
        doesn't exist or an error occurs, returns the provided default value.

        Args:
            key: str: Configuration key to retrieve
            default: Any: Default value to return if key not found or error occurs

        Returns:
            Any: Configuration value if found, otherwise default

        Example:
            >>> config = Config()
            >>> max_loss = config.get('max_daily_loss', -5000)
            >>> token = config.get('telegram_bot_token', '')
        """
        try:
            db = get_db()
            return self._config_crud.get(key, default, db)
        except Exception as e:
            logger.error(f"[Config.get] Failed for key '{key}': {e}", exc_info=True)
            return default

    def set(self, key: str, value: Any) -> bool:
        """
        Set configuration value.

        Stores a single configuration value in the database. The value is
        automatically persisted and available across application restarts.

        Args:
            key: str: Configuration key to set
            value: Any: Value to store (must be JSON-serializable)

        Returns:
            bool: True if operation successful, False otherwise

        Example:
            >>> config = Config()
            >>> success = config.set('max_daily_loss', -7500)
            >>> if success:
            ...     print("Risk limit updated")
        """
        try:
            db = get_db()
            return self._config_crud.set(key, value, db)
        except Exception as e:
            logger.error(f"[Config.set] Failed for key '{key}': {e}", exc_info=True)
            return False

    def update(self, data: Dict[str, Any]) -> bool:
        """
        Update multiple configuration values.

        Performs a batch update of multiple configuration settings in a single
        operation. All updates are attempted; if any fail, the method continues
        but returns False.

        Args:
            data: Dict[str, Any]: Dictionary of key-value pairs to update

        Returns:
            bool: True if all updates successful, False if any failed

        Example:
            >>> config = Config()
            >>> updates = {
            ...     'max_daily_loss': -10000,
            ...     'min_confidence': 0.7,
            ...     'log_level': 'DEBUG'
            ... }
            >>> all_success = config.update(updates)
        """
        try:
            db = get_db()
            success = True
            for key, value in data.items():
                if not self._config_crud.set(key, value, db):
                    success = False
            return success
        except Exception as e:
            logger.error(f"[Config.update] Failed: {e}", exc_info=True)
            return False

    def keys(self) -> list:
        """
        Get all configuration keys.

        Returns a list of all configuration keys currently stored in the database.

        Returns:
            list: List of configuration key strings. Empty list if error occurs.

        Example:
            >>> config = Config()
            >>> all_keys = config.keys()
            >>> print(f"Available settings: {', '.join(all_keys)}")
        """
        try:
            db = get_db()
            return self._config_crud.keys(db)
        except Exception as e:
            logger.error(f"[Config.keys] Failed: {e}", exc_info=True)
            return []

    def values(self) -> list:
        """
        Get all configuration values.

        Returns a list of all configuration values currently stored in the database,
        in the same order as keys().

        Returns:
            list: List of configuration values. Empty list if error occurs.

        Example:
            >>> config = Config()
            >>> all_values = config.values()
            >>> print(f"Current settings: {all_values}")
        """
        try:
            db = get_db()
            return self._config_crud.values(db)
        except Exception as e:
            logger.error(f"[Config.values] Failed: {e}", exc_info=True)
            return []

    def items(self) -> list:
        """
        Get all configuration items as (key, value) pairs.

        Returns a list of tuples containing all configuration key-value pairs.

        Returns:
            list: List of (key, value) tuples. Empty list if error occurs.

        Example:
            >>> config = Config()
            >>> for key, value in config.items():
            ...     print(f"{key}: {value}")
        """
        try:
            db = get_db()
            return self._config_crud.items(db)
        except Exception as e:
            logger.error(f"[Config.items] Failed: {e}", exc_info=True)
            return []

    def clear(self) -> None:
        """
        Clear all configuration data.

        Removes all configuration entries from the database. Use with caution -
        this will delete all settings. Default values will be recreated on
        next access.

        Returns:
            None

        Warning:
            This operation cannot be undone. Consider using reset_to_defaults()
            for a safer alternative.
        """
        try:
            db = get_db()
            self._config_crud.clear(db)
        except Exception as e:
            logger.error(f"[Config.clear] Failed: {e}", exc_info=True)

    def reload(self) -> bool:
        """
        Reload configuration (no-op for database).

        Database-backed configuration is always up-to-date, so this method
        does nothing but returns True for interface compatibility.

        Returns:
            bool: Always returns True
        """
        return True

    def get_risk_config(self) -> Dict[str, Any]:
        """
        Get all risk-related configuration in one dictionary.

        Convenience method that aggregates all risk management settings
        for easy access by the risk manager module.

        Returns:
            Dict[str, Any]: Dictionary containing:
                - max_daily_loss: Maximum allowed daily loss (negative value)
                - max_trades_per_day: Maximum number of trades per day
                - daily_target: Daily profit target

        Example:
            >>> config = Config()
            >>> risk_settings = config.get_risk_config()
            >>> if current_loss < risk_settings['max_daily_loss']:
            ...     trading_disabled()
        """
        try:
            return {
                'max_daily_loss': self.get('max_daily_loss', -5000),
                'max_trades_per_day': self.get('max_trades_per_day', 10),
                'daily_target': self.get('daily_target', 5000),
            }
        except Exception as e:
            logger.error(f"[Config.get_risk_config] Failed: {e}", exc_info=True)
            return {
                'max_daily_loss': -5000,
                'max_trades_per_day': 10,
                'daily_target': 5000,
            }

    def get_telegram_config(self) -> Dict[str, str]:
        """
        Get all Telegram-related configuration.

        Convenience method that aggregates all Telegram notification settings
        for easy access by the notification service.

        Returns:
            Dict[str, str]: Dictionary containing:
                - telegram_bot_token: Bot authentication token
                - telegram_chat_id: Target chat ID for notifications

        Example:
            >>> config = Config()
            >>> telegram = config.get_telegram_config()
            >>> if telegram['telegram_bot_token']:
            ...     send_notification("Trade executed")
        """
        try:
            return {
                'telegram_bot_token': self.get('telegram_bot_token', ''),
                'telegram_chat_id': self.get('telegram_chat_id', ''),
            }
        except Exception as e:
            logger.error(f"[Config.get_telegram_config] Failed: {e}", exc_info=True)
            return {'telegram_bot_token': '', 'telegram_chat_id': ''}

    def get_mtf_config(self) -> Dict[str, Any]:
        """
        Get multi-timeframe filter configuration.

        Convenience method that aggregates multi-timeframe filter settings
        for easy access by the signal filtering module.

        Returns:
            Dict[str, Any]: Dictionary containing:
                - use_mtf_filter: Boolean flag to enable/disable MTF filtering

        Example:
            >>> config = Config()
            >>> mtf = config.get_mtf_config()
            >>> if mtf['use_mtf_filter']:
            ...     apply_multi_timeframe_validation(signal)
        """
        try:
            return {
                'use_mtf_filter': self.get('use_mtf_filter', False),
            }
        except Exception as e:
            logger.error(f"[Config.get_mtf_config] Failed: {e}", exc_info=True)
            return {'use_mtf_filter': False}

    def get_signal_config(self) -> Dict[str, Any]:
        """
        Get signal engine configuration.

        Convenience method that aggregates signal processing settings
        for easy access by the signal generation engine.

        Returns:
            Dict[str, Any]: Dictionary containing:
                - min_confidence: Minimum confidence threshold (0.0-1.0)

        Example:
            >>> config = Config()
            >>> signal_config = config.get_signal_config()
            >>> if signal.confidence >= signal_config['min_confidence']:
            ...     execute_trade(signal)
        """
        try:
            return {
                'min_confidence': self.get('min_confidence', 0.6),
            }
        except Exception as e:
            logger.error(f"[Config.get_signal_config] Failed: {e}", exc_info=True)
            return {'min_confidence': 0.6}

    def is_market_open(self, current_time=None) -> bool:
        """
        Check if market is currently open for trading.

        Evaluates whether the current time falls within market trading hours
        as defined in configuration. Used by trading engines to prevent
        out-of-hours order placement.

        Args:
            current_time: Optional datetime to check (defaults to now).
                         Useful for testing or historical checks.

        Returns:
            bool: True if market is open, False if closed or error occurs.

        Market Hours:
            Open: 9:15 AM (configurable via 'market_open_time')
            Close: 3:30 PM (configurable via 'market_close_time')

        Example:
            >>> config = Config()
            >>> if config.is_market_open():
            ...     place_order(signal)
            ... else:
            ...     logger.info("Market closed - order queued for next day")
        """
        try:
            from datetime import datetime, time

            if current_time is None:
                current_time = datetime.now()

            # Get market hours from config
            open_str = self.get('market_open_time', '09:15')
            close_str = self.get('market_close_time', '15:30')

            # Parse times
            open_hour, open_min = map(int, open_str.split(':'))
            close_hour, close_min = map(int, close_str.split(':'))

            market_open = time(open_hour, open_min)
            market_close = time(close_hour, close_min)

            current_t = current_time.time()

            return market_open <= current_t <= market_close

        except Exception as e:
            logger.error(f"[Config.is_market_open] Failed: {e}", exc_info=True)
            # Default to conservative estimate (assume closed on error)
            return False

    def __repr__(self) -> str:
        """
        Get string representation of configuration.

        Returns a human-readable string showing all current configuration
        settings for debugging and logging purposes.

        Returns:
            str: String representation of Config object
        """
        try:
            return f"Config({self.to_dict()})"
        except Exception as e:
            logger.error(f"[Config.__repr__] Failed: {e}", exc_info=True)
            return "Config(Error)"

    def __contains__(self, key: str) -> bool:
        """
        Check if a configuration key exists.

        Enables the 'in' operator for configuration objects.

        Args:
            key: str: Configuration key to check

        Returns:
            bool: True if key exists in database, False otherwise

        Example:
            >>> config = Config()
            >>> if 'max_daily_loss' in config:
            ...     print("Risk limit configured")
        """
        try:
            db = get_db()
            return key in self._config_crud.keys(db)
        except Exception as e:
            logger.error(f"[Config.__contains__] Failed: {e}", exc_info=True)
            return False

    def __getitem__(self, key: str) -> Any:
        """
        Dictionary-style access to configuration values.

        Enables bracket notation for retrieving configuration values.
        Raises KeyError if key doesn't exist.

        Args:
            key: str: Configuration key to retrieve

        Returns:
            Any: Configuration value

        Raises:
            KeyError: If key doesn't exist or error occurs

        Example:
            >>> config = Config()
            >>> max_loss = config['max_daily_loss']
        """
        try:
            db = get_db()
            return self._config_crud.get(key, db=db)
        except Exception as e:
            logger.error(f"[Config.__getitem__] Failed: {e}", exc_info=True)
            raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """
        Dictionary-style assignment to configuration values.

        Enables bracket notation for setting configuration values.

        Args:
            key: str: Configuration key to set
            value: Any: Value to store

        Raises:
            Exception: If database operation fails

        Example:
            >>> config = Config()
            >>> config['max_daily_loss'] = -10000
        """
        try:
            db = get_db()
            self._config_crud.set(key, value, db)
        except Exception as e:
            logger.error(f"[Config.__setitem__] Failed: {e}", exc_info=True)
            raise


class ConfigContext:
    """
    Context manager for temporarily modifying configuration.

    Provides a safe way to make temporary configuration changes that are
    automatically reverted when the context block exits. Useful for testing,
    isolated operations, or temporary overrides.

    Usage:
        with ConfigContext(config) as cfg:
            cfg['max_daily_loss'] = -1000  # Temporary override
            # ... operations with temporary config ...
        # Original configuration automatically restored

    Attributes:
        config: The Config instance being managed
        _backup: Snapshot of original configuration for restoration
    """

    def __init__(self, config: Config):
        """
        Initialize context manager with configuration backup.

        Args:
            config: Config: The configuration instance to manage
        """
        self.config = config
        self._backup = None
        try:
            self._backup = config.to_dict()
        except Exception as e:
            logger.error(f"[ConfigContext.__init__] Failed: {e}", exc_info=True)

    def __enter__(self):
        """
        Enter the context block.

        Returns:
            Config: The managed configuration instance
        """
        return self.config

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the context block and restore original configuration.

        Regardless of whether an exception occurred, the original
        configuration is restored from the backup taken at initialization.

        Args:
            exc_type: Exception type if an exception was raised
            exc_val: Exception value if an exception was raised
            exc_tb: Exception traceback if an exception was raised
        """
        try:
            if self.config and self._backup is not None:
                self.config.clear()
                self.config.from_dict(self._backup)
        except Exception as e:
            logger.error(f"[ConfigContext.__exit__] Failed: {e}", exc_info=True)


# ============================================================================
# Convenience functions for common config operations
# ============================================================================

def get_config() -> Config:
    """
    Get the global Config instance (singleton pattern).

    Provides a simple singleton accessor for the configuration manager.
    In production, consider implementing a proper thread-safe singleton.

    Returns:
        Config: Global configuration instance

    Raises:
        Exception: If configuration initialization fails

    Example:
        >>> config = get_config()
        >>> bot_mode = config.get('bot_type', 'PAPER')
    """
    try:
        # This is a simple implementation - in practice you might want
        # a proper singleton with thread safety
        return Config()
    except Exception as e:
        logger.error(f"[get_config] Failed: {e}", exc_info=True)
        raise


def update_config_from_dict(config_dict: Dict[str, Any]) -> bool:
    """
    Update configuration from a dictionary.

    Convenience function for bulk configuration updates without
    explicitly getting the Config instance.

    Args:
        config_dict: Dict[str, Any]: Dictionary of key-value pairs to update

    Returns:
        bool: True if all updates successful, False otherwise

    Example:
        >>> updates = {'max_daily_loss': -7500, 'log_level': 'DEBUG'}
        >>> if update_config_from_dict(updates):
        ...     print("Configuration updated successfully")
    """
    try:
        config = get_config()
        return config.update(config_dict)
    except Exception as e:
        logger.error(f"[update_config_from_dict] Failed: {e}", exc_info=True)
        return False


def reset_to_defaults() -> bool:
    """
    Reset all configuration to default values.

    Clears all current configuration and triggers re-initialization with
    default values on next access. Safer than clear() as it ensures defaults
    will be recreated.

    Returns:
        bool: True if successful, False otherwise

    Example:
        >>> if reset_to_defaults():
        ...     print("Configuration reset to factory defaults")
    """
    try:
        config = get_config()
        config.clear()
        # _ensure_defaults will run on next access
        return True
    except Exception as e:
        logger.error(f"[reset_to_defaults] Failed: {e}", exc_info=True)
        return False