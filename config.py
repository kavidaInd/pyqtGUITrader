"""
config_db.py
============
Database-backed configuration management with default values for all features.
"""

import logging
from typing import Any, Dict, Optional

from db.config_crud import config_crud
from db.connector import get_db

logger = logging.getLogger(__name__)


class Config:
    """
    Database-backed configuration management.

    All configurable values are stored in the database with these defaults:

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
        self._config_crud = config_crud
        self._ensure_defaults()
        logger.info("Config (database) initialized")

    def _ensure_defaults(self) -> None:
        """
        Ensure all required configuration keys have default values.
        This runs once at startup to populate missing keys.
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
        """Convert config to dictionary."""
        try:
            db = get_db()
            return self._config_crud.to_dict(db)
        except Exception as e:
            logger.error(f"[Config.to_dict] Failed: {e}", exc_info=True)
            return {}

    def from_dict(self, d: Optional[Dict[str, Any]]) -> None:
        """Load configuration from dictionary."""
        try:
            if d is None:
                return
            db = get_db()
            self._config_crud.from_dict(d, db)
        except Exception as e:
            logger.error(f"[Config.from_dict] Failed: {e}", exc_info=True)

    def save(self) -> bool:
        """Save configuration (always returns True for database)."""
        return True

    def load(self) -> bool:
        """Load configuration (always returns True for database)."""
        return True

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
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

        Args:
            key: Configuration key
            value: Value to set

        Returns:
            True if successful
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

        Args:
            data: Dictionary of key-value pairs to update

        Returns:
            True if all updates successful
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
        """Get all configuration keys."""
        try:
            db = get_db()
            return self._config_crud.keys(db)
        except Exception as e:
            logger.error(f"[Config.keys] Failed: {e}", exc_info=True)
            return []

    def values(self) -> list:
        """Get all configuration values."""
        try:
            db = get_db()
            return self._config_crud.values(db)
        except Exception as e:
            logger.error(f"[Config.values] Failed: {e}", exc_info=True)
            return []

    def items(self) -> list:
        """Get all configuration items as (key, value) pairs."""
        try:
            db = get_db()
            return self._config_crud.items(db)
        except Exception as e:
            logger.error(f"[Config.items] Failed: {e}", exc_info=True)
            return []

    def clear(self) -> None:
        """Clear all configuration data."""
        try:
            db = get_db()
            self._config_crud.clear(db)
        except Exception as e:
            logger.error(f"[Config.clear] Failed: {e}", exc_info=True)

    def reload(self) -> bool:
        """Reload configuration (no-op for database)."""
        return True

    def get_risk_config(self) -> Dict[str, Any]:
        """
        Get all risk-related configuration in one dict.

        Returns:
            Dictionary with risk config keys
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

        Returns:
            Dictionary with telegram_bot_token and telegram_chat_id
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

        Returns:
            Dictionary with use_mtf_filter flag
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

        Returns:
            Dictionary with min_confidence
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
        Check if market is currently open (9:15 AM to 3:30 PM).

        Args:
            current_time: Optional datetime to check (defaults to now)

        Returns:
            True if market is open
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
        try:
            return f"Config({self.to_dict()})"
        except Exception as e:
            logger.error(f"[Config.__repr__] Failed: {e}", exc_info=True)
            return "Config(Error)"

    def __contains__(self, key: str) -> bool:
        try:
            db = get_db()
            return key in self._config_crud.keys(db)
        except Exception as e:
            logger.error(f"[Config.__contains__] Failed: {e}", exc_info=True)
            return False

    def __getitem__(self, key: str) -> Any:
        try:
            db = get_db()
            return self._config_crud.get(key, db=db)
        except Exception as e:
            logger.error(f"[Config.__getitem__] Failed: {e}", exc_info=True)
            raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        try:
            db = get_db()
            self._config_crud.set(key, value, db)
        except Exception as e:
            logger.error(f"[Config.__setitem__] Failed: {e}", exc_info=True)
            raise


class ConfigContext:
    """Context manager for temporarily modifying config."""

    def __init__(self, config: Config):
        self.config = config
        self._backup = None
        try:
            self._backup = config.to_dict()
        except Exception as e:
            logger.error(f"[ConfigContext.__init__] Failed: {e}", exc_info=True)

    def __enter__(self):
        return self.config

    def __exit__(self, exc_type, exc_val, exc_tb):
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
    """Get the global Config instance (singleton pattern)."""
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

    Args:
        config_dict: Dictionary of key-value pairs

    Returns:
        True if all updates successful
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

    Returns:
        True if successful
    """
    try:
        config = get_config()
        config.clear()
        # _ensure_defaults will run on next access
        return True
    except Exception as e:
        logger.error(f"[reset_to_defaults] Failed: {e}", exc_info=True)
        return False