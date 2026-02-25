"""
db/config_crud.py
-----------------
Database-backed configuration management replacing JSON file storage.
"""

import logging
import json
from typing import Any, Dict, Optional

from db import kv
from db.connector import DatabaseConnector, get_db

logger = logging.getLogger(__name__)


class ConfigCRUD:
    """CRUD for configuration stored in app_kv table."""

    # Default configuration values with all new features
    DEFAULTS: Dict[str, Any] = {
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

        # Bug #4 Fix - Market hours
        "market_open_time": "09:15",
        "market_close_time": "15:30",

        # Existing defaults
        "broker_api_key": "",
        "broker_secret": "",
        "broker_redirect_uri": "",
        "bot_type": "PAPER",
        "log_level": "INFO",
        "log_retention_days": 7,
    }

    def __init__(self):
        self._ensure_defaults()

    def _ensure_defaults(self, db: DatabaseConnector = None) -> None:
        """Ensure default config keys exist."""
        db = db or get_db()
        try:
            # Check if we need to seed defaults
            existing = kv.all(db)
            for key, value in self.DEFAULTS.items():
                if key not in existing:
                    kv.set(key, value, db)
                    logger.debug(f"Set default config: {key} = {value}")
        except Exception as e:
            logger.error(f"[ConfigCRUD._ensure_defaults] Failed: {e}", exc_info=True)

    def to_dict(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """Convert all config keys to dictionary."""
        db = db or get_db()
        try:
            return kv.all(db)
        except Exception as e:
            logger.error(f"[ConfigCRUD.to_dict] Failed: {e}", exc_info=True)
            return {}

    def from_dict(self, data: Optional[Dict[str, Any]], db: DatabaseConnector = None) -> None:
        """Load configuration from dictionary."""
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
        """Get configuration value by key."""
        db = db or get_db()
        try:
            return kv.get(key, default, db)
        except Exception as e:
            logger.error(f"[ConfigCRUD.get] Failed for key '{key}': {e}", exc_info=True)
            return default

    def set(self, key: str, value: Any, db: DatabaseConnector = None) -> bool:
        """Set configuration value."""
        db = db or get_db()
        try:
            return kv.set(key, value, db)
        except Exception as e:
            logger.error(f"[ConfigCRUD.set] Failed for key '{key}': {e}", exc_info=True)
            return False

    def update(self, data: Dict[str, Any], db: DatabaseConnector = None) -> bool:
        """Update multiple configuration values."""
        db = db or get_db()
        try:
            return kv.update_many(data, db)
        except Exception as e:
            logger.error(f"[ConfigCRUD.update] Failed: {e}", exc_info=True)
            return False

    def clear(self, db: DatabaseConnector = None) -> bool:
        """Clear all configuration data."""
        db = db or get_db()
        try:
            # Don't clear defaults
            current = kv.get_all(db)
            to_delete = [k for k in current.keys() if k not in self.DEFAULTS]
            for key in to_delete:
                kv.delete(key, db)
            return True
        except Exception as e:
            logger.error(f"[ConfigCRUD.clear] Failed: {e}", exc_info=True)
            return False

    def keys(self, db: DatabaseConnector = None) -> list:
        """Get all configuration keys."""
        db = db or get_db()
        try:
            return list(kv.get_all(db).keys())
        except Exception as e:
            logger.error(f"[ConfigCRUD.keys] Failed: {e}", exc_info=True)
            return []

    def values(self, db: DatabaseConnector = None) -> list:
        """Get all configuration values."""
        db = db or get_db()
        try:
            return list(kv.get_all(db).values())
        except Exception as e:
            logger.error(f"[ConfigCRUD.values] Failed: {e}", exc_info=True)
            return []

    def items(self, db: DatabaseConnector = None) -> list:
        """Get all configuration items as (key, value) pairs."""
        db = db or get_db()
        try:
            return list(kv.get_all(db).items())
        except Exception as e:
            logger.error(f"[ConfigCRUD.items] Failed: {e}", exc_info=True)
            return []

    def reload(self, db: DatabaseConnector = None) -> bool:
        """Reload configuration (no-op for database, just returns current state)."""
        return True

    # ------------------------------------------------------------------
    # NEW: Convenience methods for feature-specific config
    # ------------------------------------------------------------------

    def get_risk_config(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """Get all risk-related configuration in one dict."""
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
        """Get all Telegram-related configuration."""
        try:
            return {
                'telegram_bot_token': self.get('telegram_bot_token', '', db),
                'telegram_chat_id': self.get('telegram_chat_id', '', db),
            }
        except Exception as e:
            logger.error(f"[ConfigCRUD.get_telegram_config] Failed: {e}", exc_info=True)
            return {'telegram_bot_token': '', 'telegram_chat_id': ''}

    def get_mtf_config(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """Get multi-timeframe filter configuration."""
        try:
            return {
                'use_mtf_filter': self.get('use_mtf_filter', False, db),
            }
        except Exception as e:
            logger.error(f"[ConfigCRUD.get_mtf_config] Failed: {e}", exc_info=True)
            return {'use_mtf_filter': False}

    def get_signal_config(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """Get signal engine configuration."""
        try:
            return {
                'min_confidence': self.get('min_confidence', 0.6, db),
            }
        except Exception as e:
            logger.error(f"[ConfigCRUD.get_signal_config] Failed: {e}", exc_info=True)
            return {'min_confidence': 0.6}

    def is_market_open(self, current_time=None, db: DatabaseConnector = None) -> bool:
        """Check if market is currently open (9:15 AM to 3:30 PM)."""
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
            return False


# Singleton instance
config_crud = ConfigCRUD()