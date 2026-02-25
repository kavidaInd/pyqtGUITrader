"""
config_db.py
============
Database-backed configuration management.
"""

import logging
from typing import Any, Dict, Optional

from db.config_crud import config_crud
from db.connector import get_db

logger = logging.getLogger(__name__)


class Config:
    """
    Database-backed configuration management.
    """

    def __init__(self):
        self._config_crud = config_crud
        logger.info("Config (database) initialized")

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
        """Get configuration value by key."""
        try:
            db = get_db()
            return self._config_crud.get(key, default, db)
        except Exception as e:
            logger.error(f"[Config.get] Failed for key '{key}': {e}", exc_info=True)
            return default

    def set(self, key: str, value: Any) -> bool:
        """Set configuration value."""
        try:
            db = get_db()
            return self._config_crud.set(key, value, db)
        except Exception as e:
            logger.error(f"[Config.set] Failed for key '{key}': {e}", exc_info=True)
            return False

    def update(self, data: Dict[str, Any]) -> bool:
        """Update multiple configuration values."""
        try:
            db = get_db()
            return self._config_crud.update(data, db)
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