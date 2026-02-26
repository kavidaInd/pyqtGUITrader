"""
Database Configuration CRUD Module
==================================
Database-backed configuration management replacing JSON file storage.

This module provides a robust CRUD (Create, Read, Update, Delete) interface for
application configuration using the app_kv table in the database. It replaces
traditional file-based configuration with a database solution, enabling:
    - Runtime configuration changes without restart
    - Centralized configuration for multi-instance deployments
    - Automatic default value initialization
    - Transaction-safe updates
    - Feature-specific configuration grouping

Architecture:
    The ConfigCRUD class acts as a facade over the kv (key-value) store,
    providing:
        - Type-safe configuration access
        - Default value management
        - Feature-specific convenience methods
        - Comprehensive error handling
        - Database-agnostic interface (via DatabaseConnector)

Key Features:
    - Automatic default initialization for all configuration keys
    - Grouped access for related configuration (risk, telegram, etc.)
    - Market hours utility function
    - Thread-safe operations (via underlying kv store)
    - Graceful error handling with fallback defaults

Configuration Categories:
    1. Risk Management: max_daily_loss, max_trades_per_day, daily_target
    2. Signal Processing: min_confidence, use_mtf_filter
    3. Notifications: telegram_bot_token, telegram_chat_id
    4. Market Hours: market_open_time, market_close_time
    5. System: broker_* settings, log_level, retention
    6. Trade History: history_retention_days

Dependencies:
    - db.kv: Key-value store implementation
    - db.connector: Database connection management

Version: 1.0.0
"""

import logging
import json
from typing import Any, Dict, Optional

from db import kv
from db.connector import DatabaseConnector, get_db

logger = logging.getLogger(__name__)


class ConfigCRUD:
    """
    CRUD operations for application configuration stored in app_kv table.

    This class provides a comprehensive interface for managing all application
    configuration settings. It ensures that all required configuration keys
    exist with appropriate default values and provides type-safe access methods.

    The class is designed to be used as a singleton (via config_crud instance)
    but can also be instantiated multiple times if needed.

    Thread Safety:
        All methods are thread-safe as they delegate to the underlying kv store
        which implements proper database transaction semantics.

    Usage:
        config = ConfigCRUD()

        # Get individual values
        max_loss = config.get('max_daily_loss', -5000)

        # Set values
        config.set('min_confidence', 0.7)

        # Get grouped configuration
        risk_config = config.get_risk_config()
        telegram_config = config.get_telegram_config()

        # Check market hours
        if config.is_market_open():
            place_order()

    Note:
        All methods accept an optional db parameter for dependency injection,
        which is useful for testing and transaction management.
    """

    # Default configuration values with all new features
    # These defaults are used when a configuration key is first accessed
    # and ensure the application works out-of-the-box.
    DEFAULTS: Dict[str, Any] = {
        # Feature 1 - Risk Manager
        # Controls daily loss limits and trade frequency
        "max_daily_loss": -5000,          # Maximum allowed daily loss (negative value)
        "max_trades_per_day": 10,          # Maximum number of trades per day

        # Feature 3 - Signal Confidence
        # Minimum confidence threshold for trade signals (0.0-1.0)
        "min_confidence": 0.6,

        # Feature 4 - Telegram Notifications
        # Credentials for Telegram bot integration
        "telegram_bot_token": "",          # Bot token from @BotFather
        "telegram_chat_id": "",            # Target chat ID for notifications

        # Feature 5 - Daily P&L Panel
        # Daily profit target for monitoring
        "daily_target": 5000,               # Daily profit target in rupees

        # Feature 6 - Multi-Timeframe Filter
        # Enable/disable MTF signal validation
        "use_mtf_filter": False,

        # Feature 7 - Trade History
        # Data retention policy for historical trades
        "history_retention_days": 30,       # Days to keep trade history

        # Bug #4 Fix - Market hours
        # Trading session timings (IST)
        "market_open_time": "09:15",        # Market open time (HH:MM)
        "market_close_time": "15:30",       # Market close time (HH:MM)

        # Existing defaults (legacy settings)
        "broker_api_key": "",                # Broker API key
        "broker_secret": "",                 # Broker secret key
        "broker_redirect_uri": "",           # OAuth redirect URI
        "bot_type": "PAPER",                 # Trading mode (PAPER/LIVE)
        "log_level": "INFO",                  # Logging verbosity
        "log_retention_days": 7,              # Log file retention period
    }

    def __init__(self):
        """
        Initialize the configuration CRUD instance.

        On initialization, ensures that all default configuration keys exist
        in the database. This prevents missing key errors during application
        operation.
        """
        self._ensure_defaults()

    def _ensure_defaults(self, db: DatabaseConnector = None) -> None:
        """
        Ensure all default configuration keys exist in the database.

        This method checks for the presence of each default key and creates
        any missing keys with their default values. It is idempotent - running
        multiple times only adds missing keys without overwriting existing values.

        Args:
            db: Optional database connector instance. If None, uses default.

        Note:
            This method is called during initialization and can also be called
            manually to reset missing keys after a schema update.
        """
        db = db or get_db()
        try:
            # Get all existing keys
            existing = kv.all(db)

            # Add any missing defaults
            for key, value in self.DEFAULTS.items():
                if key not in existing:
                    kv.set(key, value, db)
                    logger.debug(f"Set default config: {key} = {value}")
        except Exception as e:
            logger.error(f"[ConfigCRUD._ensure_defaults] Failed: {e}", exc_info=True)

    def to_dict(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """
        Convert all configuration keys to a dictionary.

        Returns a complete snapshot of the current configuration state.
        Useful for serialization, backup, or displaying all settings.

        Args:
            db: Optional database connector instance.

        Returns:
            Dict[str, Any]: Dictionary containing all configuration key-value pairs.
                           Returns empty dictionary on error.
        """
        db = db or get_db()
        try:
            return kv.all(db)
        except Exception as e:
            logger.error(f"[ConfigCRUD.to_dict] Failed: {e}", exc_info=True)
            return {}

    def from_dict(self, data: Optional[Dict[str, Any]], db: DatabaseConnector = None) -> None:
        """
        Load configuration from a dictionary.

        Updates the database with all key-value pairs from the provided dictionary.
        Existing keys are overwritten, new keys are added. Keys not in the dictionary
        remain unchanged.

        Args:
            data: Dictionary containing configuration settings to load.
                  If None, loads the default configuration.
            db: Optional database connector instance.

        Note:
            This method does not delete existing keys that are not in the input.
            For a complete reset, use clear() followed by from_dict().
        """
        db = db or get_db()
        try:
            if data is None:
                logger.warning("from_dict called with None, using defaults")
                data = dict(self.DEFAULTS)

            if not isinstance(data, dict):
                logger.error(f"from_dict expected dict, got {type(data)}")
                return

            kv.update_many(data, db)
            logger.debug(f"Config loaded from dict with {len(data)} keys")

        except Exception as e:
            logger.error(f"[ConfigCRUD.from_dict] Failed: {e}", exc_info=True)

    def get(self, key: str, default: Any = None, db: DatabaseConnector = None) -> Any:
        """
        Get configuration value by key.

        Retrieves a single configuration value from the database.

        Args:
            key: Configuration key to retrieve.
            default: Default value to return if key not found or error occurs.
            db: Optional database connector instance.

        Returns:
            Any: Configuration value if found, otherwise default.

        Example:
            max_loss = config.get('max_daily_loss', -5000)
            if max_loss < current_loss:
                stop_trading()
        """
        db = db or get_db()
        try:
            return kv.get(key, default, db)
        except Exception as e:
            logger.error(f"[ConfigCRUD.get] Failed for key '{key}': {e}", exc_info=True)
            return default

    def set(self, key: str, value: Any, db: DatabaseConnector = None) -> bool:
        """
        Set configuration value.

        Stores a single configuration value in the database.

        Args:
            key: Configuration key to set.
            value: Value to store (must be JSON-serializable).
            db: Optional database connector instance.

        Returns:
            bool: True if operation successful, False otherwise.

        Example:
            success = config.set('min_confidence', 0.7)
            if not success:
                logger.error("Failed to update confidence threshold")
        """
        db = db or get_db()
        try:
            return kv.set(key, value, db)
        except Exception as e:
            logger.error(f"[ConfigCRUD.set] Failed for key '{key}': {e}", exc_info=True)
            return False

    def update(self, data: Dict[str, Any], db: DatabaseConnector = None) -> bool:
        """
        Update multiple configuration values in a single transaction.

        Performs a batch update of multiple configuration settings.
        All updates are atomic - either all succeed or none are applied.

        Args:
            data: Dictionary of key-value pairs to update.
            db: Optional database connector instance.

        Returns:
            bool: True if all updates successful, False otherwise.

        Example:
            updates = {
                'max_daily_loss': -10000,
                'max_trades_per_day': 15,
                'min_confidence': 0.65
            }
            success = config.update(updates)
        """
        db = db or get_db()
        try:
            return kv.update_many(data, db)
        except Exception as e:
            logger.error(f"[ConfigCRUD.update] Failed: {e}", exc_info=True)
            return False

    def clear(self, db: DatabaseConnector = None) -> bool:
        """
        Clear all non-default configuration data.

        Removes all configuration keys except the defaults. This provides
        a way to reset to factory settings while preserving the default values.

        Args:
            db: Optional database connector instance.

        Returns:
            bool: True if operation successful, False otherwise.

        Note:
            Default keys are preserved to ensure the application remains
            in a working state after clear.
        """
        db = db or get_db()
        try:
            # Don't clear defaults - preserve them
            current = kv.get_all(db)
            to_delete = [k for k in current.keys() if k not in self.DEFAULTS]
            for key in to_delete:
                kv.delete(key, db)
            return True
        except Exception as e:
            logger.error(f"[ConfigCRUD.clear] Failed: {e}", exc_info=True)
            return False

    def keys(self, db: DatabaseConnector = None) -> list:
        """
        Get all configuration keys.

        Returns a list of all configuration keys currently stored in the database.

        Args:
            db: Optional database connector instance.

        Returns:
            list: List of configuration key strings. Empty list on error.
        """
        db = db or get_db()
        try:
            return list(kv.get_all(db).keys())
        except Exception as e:
            logger.error(f"[ConfigCRUD.keys] Failed: {e}", exc_info=True)
            return []

    def values(self, db: DatabaseConnector = None) -> list:
        """
        Get all configuration values.

        Returns a list of all configuration values currently stored in the database,
        in the same order as keys().

        Args:
            db: Optional database connector instance.

        Returns:
            list: List of configuration values. Empty list on error.
        """
        db = db or get_db()
        try:
            return list(kv.get_all(db).values())
        except Exception as e:
            logger.error(f"[ConfigCRUD.values] Failed: {e}", exc_info=True)
            return []

    def items(self, db: DatabaseConnector = None) -> list:
        """
        Get all configuration items as (key, value) pairs.

        Returns a list of tuples containing all configuration key-value pairs.

        Args:
            db: Optional database connector instance.

        Returns:
            list: List of (key, value) tuples. Empty list on error.
        """
        db = db or get_db()
        try:
            return list(kv.get_all(db).items())
        except Exception as e:
            logger.error(f"[ConfigCRUD.items] Failed: {e}", exc_info=True)
            return []

    def reload(self, db: DatabaseConnector = None) -> bool:
        """
        Reload configuration (no-op for database).

        This method exists for interface compatibility with file-based config.
        Database-backed configuration is always up-to-date, so no reload needed.

        Args:
            db: Optional database connector instance (ignored).

        Returns:
            bool: Always returns True.
        """
        return True

    # ------------------------------------------------------------------
    # NEW: Convenience methods for feature-specific config
    # These methods provide grouped access to related configuration settings,
    # making it easier to work with feature-specific configuration bundles.
    # ------------------------------------------------------------------

    def get_risk_config(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """
        Get all risk-related configuration in one dictionary.

        Aggregates settings used by the RiskManager feature:
            - max_daily_loss: Maximum allowed daily loss
            - max_trades_per_day: Maximum trades per day
            - daily_target: Daily profit target

        Args:
            db: Optional database connector instance.

        Returns:
            Dict[str, Any]: Dictionary containing risk configuration keys.
                           Returns defaults on error.

        Example:
            risk_config = config.get_risk_config()
            if current_loss < risk_config['max_daily_loss']:
                risk_manager.stop_trading()
        """
        try:
            return {
                'max_daily_loss': self.get('max_daily_loss', -5000, db),
                'max_trades_per_day': self.get('max_trades_per_day', 10, db),
                'daily_target': self.get('daily_target', 5000, db),
            }
        except Exception as e:
            logger.error(f"[ConfigCRUD.get_risk_config] Failed: {e}", exc_info=True)
            return {
                'max_daily_loss': -5000,
                'max_trades_per_day': 10,
                'daily_target': 5000,
            }

    def get_telegram_config(self, db: DatabaseConnector = None) -> Dict[str, str]:
        """
        Get all Telegram-related configuration.

        Aggregates settings used by the Notifier feature for Telegram integration:
            - telegram_bot_token: Bot authentication token
            - telegram_chat_id: Target chat ID for notifications

        Args:
            db: Optional database connector instance.

        Returns:
            Dict[str, str]: Dictionary containing Telegram configuration.
                           Returns empty strings on error.

        Example:
            telegram = config.get_telegram_config()
            if telegram['telegram_bot_token']:
                notifier.send_message("Trade executed")
        """
        try:
            return {
                'telegram_bot_token': self.get('telegram_bot_token', '', db),
                'telegram_chat_id': self.get('telegram_chat_id', '', db),
            }
        except Exception as e:
            logger.error(f"[ConfigCRUD.get_telegram_config] Failed: {e}", exc_info=True)
            return {'telegram_bot_token': '', 'telegram_chat_id': ''}

    def get_mtf_config(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """
        Get multi-timeframe filter configuration.

        Aggregates settings for the MultiTimeframeFilter feature:
            - use_mtf_filter: Boolean flag to enable/disable MTF filtering

        Args:
            db: Optional database connector instance.

        Returns:
            Dict[str, Any]: Dictionary containing MTF configuration.
                           Returns default (False) on error.

        Example:
            mtf = config.get_mtf_config()
            if mtf['use_mtf_filter']:
                signal = mtf_filter.validate(signal)
        """
        try:
            return {
                'use_mtf_filter': self.get('use_mtf_filter', False, db),
            }
        except Exception as e:
            logger.error(f"[ConfigCRUD.get_mtf_config] Failed: {e}", exc_info=True)
            return {'use_mtf_filter': False}

    def get_signal_config(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """
        Get signal engine configuration.

        Aggregates settings for the DynamicSignalEngine feature:
            - min_confidence: Minimum confidence threshold for signals

        Args:
            db: Optional database connector instance.

        Returns:
            Dict[str, Any]: Dictionary containing signal configuration.
                           Returns default (0.6) on error.

        Example:
            signal_config = config.get_signal_config()
            if signal.confidence >= signal_config['min_confidence']:
                execute_trade(signal)
        """
        try:
            return {
                'min_confidence': self.get('min_confidence', 0.6, db),
            }
        except Exception as e:
            logger.error(f"[ConfigCRUD.get_signal_config] Failed: {e}", exc_info=True)
            return {'min_confidence': 0.6}

    def is_market_open(self, current_time=None, db: DatabaseConnector = None) -> bool:
        """
        Check if market is currently open based on configured hours.

        Evaluates whether the current time falls within market trading hours
        as defined in configuration. Used by trading engines to prevent
        out-of-hours order placement.

        Args:
            current_time: Optional datetime to check (defaults to now).
                         Useful for testing or historical checks.
            db: Optional database connector instance.

        Returns:
            bool: True if market is open, False if closed or error occurs.

        Market Hours (default):
            Open: 9:15 AM (configurable via 'market_open_time')
            Close: 3:30 PM (configurable via 'market_close_time')

        Example:
            if config.is_market_open():
                place_order(signal)
            else:
                logger.info("Market closed - order queued for next day")
        """
        try:
            from datetime import datetime, time

            if current_time is None:
                current_time = datetime.now()

            # Get market hours from config
            open_str = self.get('market_open_time', '09:15', db)
            close_str = self.get('market_close_time', '15:30', db)

            # Parse times
            open_hour, open_min = map(int, open_str.split(':'))
            close_hour, close_min = map(int, close_str.split(':'))

            market_open = time(open_hour, open_min)
            market_close = time(close_hour, close_min)

            current_t = current_time.time()

            return market_open <= current_t <= market_close

        except Exception as e:
            logger.error(f"[ConfigCRUD.is_market_open] Failed: {e}", exc_info=True)
            # Conservative default - assume closed on error
            return False


# Singleton instance for global use
# This provides a single, shared configuration instance throughout the application
config_crud = ConfigCRUD()