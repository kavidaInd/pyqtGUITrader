"""
db/strategy_crud.py
-------------------
Enhanced CRUD for strategies with metadata and engine config.
Extends the basic StrategiesCRUD in crud.py.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any

from db.connector import DatabaseConnector, get_db
from db.crud import strategies as base_strategies

logger = logging.getLogger(__name__)


class StrategyCRUD:
    """Enhanced CRUD for strategies with full metadata support."""

    # Prefix for storing engine config in KV store (fallback)
    ENGINE_PREFIX = "strategy_engine_"

    def list_all(self, db: DatabaseConnector = None) -> List[Dict[str, Any]]:
        """Return all strategy metadata rows."""
        return base_strategies.list_all(db)

    def get(self, slug: str, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        """Return a full strategy dict (indicators + engine decoded)."""
        return base_strategies.get(slug, db)

    def create(
            self,
            name: str,
            description: str = "",
            indicators: Dict = None,
            engine: Dict = None,
            db: DatabaseConnector = None,
    ) -> Tuple[bool, str]:
        """Create a new strategy. Returns (ok, slug_or_error)."""
        db = db or get_db()

        try:
            if not name or not name.strip():
                return False, "Strategy name cannot be empty"

            # Generate slug from name
            slug = self._slugify(name)

            # Handle collisions
            base, n = slug, 2
            while base_strategies.exists(slug, db):
                slug = f"{base}-{n}"
                n += 1

            # Create strategy
            ok = base_strategies.create(
                slug=slug,
                name=name,
                description=description,
                indicators=indicators or {},
                engine=engine or {},
                db=db
            )

            if ok:
                logger.info(f"Created strategy '{name}' → {slug}")
                return True, slug
            else:
                return False, "Failed to create strategy"

        except Exception as e:
            logger.error(f"[StrategyCRUD.create] Failed for {name}: {e}", exc_info=True)
            return False, f"Creation failed: {e}"

    def duplicate(self, source_slug: str, new_name: str, db: DatabaseConnector = None) -> Tuple[bool, str]:
        """Clone an existing strategy under a new name."""
        db = db or get_db()

        try:
            if not source_slug:
                return False, "Source slug is empty"

            source = self.get(source_slug, db)
            if not source:
                return False, f"Source strategy '{source_slug}' not found"

            if not new_name or not new_name.strip():
                return False, "New name cannot be empty"

            return self.create(
                name=new_name,
                description=source.get("description", ""),
                indicators=source.get("indicators", {}),
                engine=source.get("engine", {}),
                db=db
            )

        except Exception as e:
            logger.error(f"[StrategyCRUD.duplicate] Failed for {source_slug}: {e}", exc_info=True)
            return False, f"Duplicate failed: {e}"

    def save(self, slug: str, data: Dict, db: DatabaseConnector = None) -> bool:
        """Overwrite strategy data (must contain meta/indicators/engine)."""
        db = db or get_db()

        try:
            if not slug:
                logger.warning("save called with empty slug")
                return False

            # Extract data
            meta = data.get("meta", {})
            name = meta.get("name", slug)
            description = meta.get("description", "")
            indicators = data.get("indicators", {})
            engine = data.get("engine", {})

            # Use upsert
            return base_strategies.upsert(
                slug=slug,
                name=name,
                description=description,
                indicators=indicators,
                engine=engine,
                db=db
            )

        except Exception as e:
            logger.error(f"[StrategyCRUD.save] Failed for {slug}: {e}", exc_info=True)
            return False

    def update_meta(self, slug: str, name: str = None, description: str = None, db: DatabaseConnector = None) -> bool:
        """Update strategy metadata."""
        db = db or get_db()

        try:
            strategy = self.get(slug, db)
            if not strategy:
                return False

            if name is not None:
                strategy["name"] = name
            if description is not None:
                strategy["description"] = description

            return self.save(slug, strategy, db)

        except Exception as e:
            logger.error(f"[StrategyCRUD.update_meta] Failed for {slug}: {e}", exc_info=True)
            return False

    def delete(self, slug: str, db: DatabaseConnector = None) -> Tuple[bool, str]:
        """Delete a strategy."""
        db = db or get_db()

        try:
            # Check if it's the only strategy
            all_strategies = self.list_all(db)
            if len(all_strategies) <= 1:
                return False, "Cannot delete the last strategy"

            # Check if it's active
            active_slug = self.get_active_slug(db)
            if active_slug == slug:
                # Need to switch active
                other_slugs = [s["slug"] for s in all_strategies if s["slug"] != slug]
                if other_slugs:
                    self.set_active(other_slugs[0], db)

            # Delete
            ok = base_strategies.delete(slug, db)
            if ok:
                logger.info(f"Deleted strategy: {slug}")
                return True, "Deleted"
            else:
                return False, "Failed to delete strategy"

        except Exception as e:
            logger.error(f"[StrategyCRUD.delete] Failed for {slug}: {e}", exc_info=True)
            return False, f"Delete failed: {e}"

    def activate(self, slug: str, db: DatabaseConnector = None) -> bool:
        """Set a strategy as active."""
        db = db or get_db()
        return base_strategies.set_active(slug, db)

    def get_active_slug(self, db: DatabaseConnector = None) -> Optional[str]:
        """Get the slug of the active strategy."""
        db = db or get_db()
        return base_strategies.get_active_slug(db)

    def get_active(self, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        """Return the currently active strategy."""
        db = db or get_db()
        return base_strategies.get_active(db)

    def get_active_name(self, db: DatabaseConnector = None) -> str:
        """Get the name of the active strategy."""
        db = db or get_db()
        active = self.get_active(db)
        return active.get("name", "None") if active else "None"

    def get_active_indicator_params(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """Return indicator params of the active strategy."""
        db = db or get_db()
        active = self.get_active(db)
        return active.get("indicators", {}) if active else {}

    def get_active_engine_config(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """Return engine config of the active strategy."""
        db = db or get_db()
        active = self.get_active(db)
        return active.get("engine", {}) if active else {}

    def count(self, db: DatabaseConnector = None) -> int:
        """Get number of strategies."""
        db = db or get_db()
        return len(self.list_all(db))

    def _slugify(self, name: str) -> str:
        """Convert a display name to a safe slug."""
        import re
        try:
            if not name:
                return "strategy"

            s = name.lower().strip()
            s = re.sub(r"[^\w\s-]", "", s)
            s = re.sub(r"[\s_]+", "-", s)
            s = re.sub(r"-+", "-", s).strip("-")
            return s or "strategy"
        except Exception as e:
            logger.error(f"[_slugify] Failed for {name}: {e}", exc_info=True)
            return "strategy"


# Singleton instance
strategy_crud = StrategyCRUD()