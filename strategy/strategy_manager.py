"""
strategy/strategy_manager_db.py
================================
Database-backed strategy manager using the SQLite database instead of JSON files.
"""

from __future__ import annotations

import logging
import threading
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from db.connector import get_db
from db.strategy_crud import strategy_crud

logger = logging.getLogger(__name__)

# Defaults (mirroring your existing structure)
SIGNAL_GROUPS = ["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]

ENGINE_DEFAULTS: Dict[str, Any] = {
    sig: {"logic": "AND", "rules": [], "enabled": True}
    for sig in SIGNAL_GROUPS
}
ENGINE_DEFAULTS["conflict_resolution"] = "WAIT"


class StrategyManager:
    """
    Database-backed strategy manager.

    Thread-safety: all public methods are guarded by a re-entrant lock.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._ensure_defaults()
        logger.info("StrategyManager (database) initialized")

    def _ensure_defaults(self):
        """Ensure at least one strategy exists."""
        with self._lock:
            try:
                db = get_db()
                if strategy_crud.count(db) == 0:
                    # Create default strategy
                    ok, slug = strategy_crud.create(
                        name="Default Strategy",
                        description="Default trading strategy",
                        db=db
                    )
                    if ok:
                        strategy_crud.activate(slug, db)
                        logger.info("Created default strategy")
            except Exception as e:
                logger.error(f"[_ensure_defaults] Failed: {e}", exc_info=True)

    # ── Public API ─────────────────────────────────────────────────────

    def list_strategies(self) -> List[Dict[str, str]]:
        """Return list of {slug, name, description, updated_at, is_active} dicts."""
        with self._lock:
            try:
                db = get_db()
                strategies = strategy_crud.list_all(db)
                active_slug = strategy_crud.get_active_slug(db)

                result = []
                for s in strategies:
                    result.append({
                        "slug": s.get("slug", ""),
                        "name": s.get("name", ""),
                        "description": s.get("description", ""),
                        "created_at": s.get("created_at", ""),
                        "updated_at": s.get("updated_at", ""),
                        "is_active": s.get("slug") == active_slug,
                    })
                return result
            except Exception as e:
                logger.error(f"[list_strategies] Failed: {e}", exc_info=True)
                return []

    def get(self, slug: str) -> Optional[Dict]:
        """Return a deep copy of the strategy dict, or None."""
        with self._lock:
            try:
                if not slug:
                    return None
                db = get_db()
                strategy = strategy_crud.get(slug, db)
                return deepcopy(strategy) if strategy else None
            except Exception as e:
                logger.error(f"[get] Failed for {slug}: {e}", exc_info=True)
                return None

    def get_active(self) -> Optional[Dict]:
        """Return a deep copy of the currently active strategy."""
        with self._lock:
            try:
                db = get_db()
                strategy = strategy_crud.get_active(db)
                return deepcopy(strategy) if strategy else None
            except Exception as e:
                logger.error(f"[get_active] Failed: {e}", exc_info=True)
                return None

    def get_active_slug(self) -> Optional[str]:
        """Get the slug of the active strategy."""
        with self._lock:
            try:
                db = get_db()
                return strategy_crud.get_active_slug(db)
            except Exception as e:
                logger.error(f"[get_active_slug] Failed: {e}", exc_info=True)
                return None

    def get_active_name(self) -> str:
        """Get the name of the active strategy."""
        with self._lock:
            try:
                db = get_db()
                return strategy_crud.get_active_name(db)
            except Exception as e:
                logger.error(f"[get_active_name] Failed: {e}", exc_info=True)
                return "None"

    def create(self, name: str, description: str = "") -> Tuple[bool, str]:
        """Create a new strategy. Returns (ok, slug_or_error)."""
        with self._lock:
            try:
                db = get_db()
                return strategy_crud.create(name, description, db=db)
            except Exception as e:
                logger.error(f"[create] Failed for {name}: {e}", exc_info=True)
                return False, f"Creation failed: {e}"

    def duplicate(self, source_slug: str, new_name: str) -> Tuple[bool, str]:
        """Clone an existing strategy under a new name."""
        with self._lock:
            try:
                db = get_db()
                return strategy_crud.duplicate(source_slug, new_name, db)
            except Exception as e:
                logger.error(f"[duplicate] Failed for {source_slug}: {e}", exc_info=True)
                return False, f"Duplicate failed: {e}"

    def save(self, slug: str, data: Dict) -> bool:
        """Overwrite strategy data (must contain meta/indicators/engine)."""
        with self._lock:
            try:
                db = get_db()
                return strategy_crud.save(slug, data, db)
            except Exception as e:
                logger.error(f"[save] Failed for {slug}: {e}", exc_info=True)
                return False

    def update_meta(self, slug: str, name: str = None, description: str = None) -> bool:
        """Update strategy metadata."""
        with self._lock:
            try:
                db = get_db()
                return strategy_crud.update_meta(slug, name, description, db)
            except Exception as e:
                logger.error(f"[update_meta] Failed for {slug}: {e}", exc_info=True)
                return False

    def delete(self, slug: str) -> Tuple[bool, str]:
        """Delete a strategy."""
        with self._lock:
            try:
                db = get_db()
                return strategy_crud.delete(slug, db)
            except Exception as e:
                logger.error(f"[delete] Failed for {slug}: {e}", exc_info=True)
                return False, f"Delete failed: {e}"

    def activate(self, slug: str) -> bool:
        """Set a strategy as active. Returns True on success."""
        with self._lock:
            try:
                db = get_db()
                return strategy_crud.activate(slug, db)
            except Exception as e:
                logger.error(f"[activate] Failed for {slug}: {e}", exc_info=True)
                return False

    def get_active_indicator_params(self) -> Dict[str, Any]:
        """Return indicator params of the active strategy."""
        with self._lock:
            try:
                db = get_db()
                return strategy_crud.get_active_indicator_params(db)
            except Exception as e:
                logger.error(f"[get_active_indicator_params] Failed: {e}", exc_info=True)
                return {}

    def get_active_engine_config(self) -> Dict[str, Any]:
        """Return engine config of the active strategy."""
        with self._lock:
            try:
                db = get_db()
                return strategy_crud.get_active_engine_config(db)
            except Exception as e:
                logger.error(f"[get_active_engine_config] Failed: {e}", exc_info=True)
                return deepcopy(ENGINE_DEFAULTS)

    def count(self) -> int:
        """Get number of strategies."""
        with self._lock:
            try:
                db = get_db()
                return strategy_crud.count(db)
            except Exception as e:
                logger.error(f"[count] Failed: {e}", exc_info=True)
                return 0

    def cleanup(self):
        """Clean up resources before shutdown."""
        try:
            logger.info("[StrategyManager] Cleanup completed (no-op for database)")
        except Exception as e:
            logger.error(f"[StrategyManager.cleanup] Error: {e}", exc_info=True)


# Singleton instance
strategy_manager = StrategyManager()


# Context manager (unchanged)
class StrategyContext:
    """Context manager for temporarily modifying the active strategy."""

    def __init__(self, manager: StrategyManager):
        self.manager = manager
        self._original_active = None
        try:
            self._original_active = manager.get_active_slug()
        except Exception as e:
            logger.error(f"[StrategyContext.__init__] Failed: {e}", exc_info=True)

    def __enter__(self) -> StrategyManager:
        return self.manager

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.manager and self._original_active:
                self.manager.activate(self._original_active)
        except Exception as e:
            logger.error(f"[StrategyContext.__exit__] Failed: {e}", exc_info=True)