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

    # Default configuration values
    DEFAULTS: Dict[str, Any] = {}

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


# Singleton instance
config_crud = ConfigCRUD()