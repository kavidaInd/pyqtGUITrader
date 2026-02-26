"""
Strategy CRUD Module
====================
Enhanced CRUD operations for trading strategies with full metadata support.

This module extends the basic StrategiesCRUD from crud.py to provide a richer
interface for managing trading strategies. It adds functionality for:
    - Strategy creation with automatic slug generation
    - Duplication (cloning) of existing strategies
    - Metadata management (name, description)
    - Active strategy tracking
    - Feature-specific configuration access (FEATURE 3)

Architecture:
    This module builds upon the base StrategiesCRUD class, adding:
        1. **Business Logic**: Slug generation, name validation, collision handling
        2. **Convenience Methods**: get_active_*, get_active_min_confidence, etc.
        3. **Safety Checks**: Cannot delete last strategy, active strategy protection
        4. **Integration**: Links with config_crud for fallback values

Key Features:
    - Automatic slug generation from strategy names
    - Duplicate detection and automatic slug modification (name-2, name-3, etc.)
    - Protection against deleting the last strategy
    - Automatic active strategy reassignment when deleting active strategy
    - FEATURE 3: Min confidence threshold retrieval (strategy-specific or global)
    - Comprehensive error handling with tuple returns (bool, message)

Dependencies:
    - db.crud.strategies: Base CRUD operations
    - db.config_crud: For fallback configuration values
    - db.connector: Database connection management

Usage:
    from db.strategy_crud import strategy_crud

    # Create a new strategy
    success, slug = strategy_crud.create(
        name="My Strategy",
        description="Awesome trading strategy",
        indicators={"rsi_period": 14},
        engine={"min_confidence": 0.7}
    )

    # Duplicate an existing strategy
    success, new_slug = strategy_crud.duplicate("my-strategy", "My Strategy Copy")

    # Get active strategy's min confidence
    confidence = strategy_crud.get_active_min_confidence()

    # Delete a strategy (safely)
    success, message = strategy_crud.delete("old-strategy")

Version: 1.0.0
"""

import logging
from typing import Dict, List, Optional, Tuple, Any

from db.connector import DatabaseConnector, get_db
from db.crud import strategies  # Import base strategies CRUD

logger = logging.getLogger(__name__)


class StrategyCRUD:
    """
    Enhanced CRUD for strategies with full metadata support.

    This class provides a higher-level interface for strategy management,
    building upon the basic StrategiesCRUD. It handles business logic such as:
        - Automatic slug generation from display names
        - Name collision resolution (adding -2, -3, etc.)
        - Strategy duplication (cloning)
        - Safe deletion with active strategy protection
        - Convenient access to active strategy properties

    The class maintains backward compatibility with the base CRUD while
    adding these enhanced features.

    Attributes:
        ENGINE_PREFIX: Prefix for storing engine config in KV store (fallback)
    """

    # Prefix for storing engine config in KV store (fallback)
    # This is kept for backward compatibility with older storage methods
    ENGINE_PREFIX = "strategy_engine_"

    def list_all(self, db: DatabaseConnector = None) -> List[Dict[str, Any]]:
        """
        Return all strategy metadata rows.

        Args:
            db: Optional database connector

        Returns:
            List[Dict[str, Any]]: List of strategy metadata dictionaries
        """
        return strategies.list_all(db)

    def get(self, slug: str, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        """
        Return a full strategy dict (indicators + engine decoded).

        Args:
            slug: Strategy unique identifier
            db: Optional database connector

        Returns:
            Optional[Dict[str, Any]]: Full strategy data if found, None otherwise
        """
        return strategies.get(slug, db)

    def create(
            self,
            name: str,
            description: str = "",
            indicators: Dict = None,
            engine: Dict = None,
            db: DatabaseConnector = None,
    ) -> Tuple[bool, str]:
        """
        Create a new strategy.

        This method handles the complete creation process:
            1. Validates strategy name (cannot be empty)
            2. Generates a URL-safe slug from the name
            3. Handles slug collisions by appending numbers (name-2, name-3, etc.)
            4. Creates the strategy in the database

        Args:
            name: Display name for the strategy (required)
            description: Optional strategy description
            indicators: Dictionary of indicator parameters
            engine: Dictionary of signal engine configuration
            db: Optional database connector

        Returns:
            Tuple[bool, str]:
                - First element: True if creation successful, False otherwise
                - Second element: On success, the generated slug; on failure, error message

        Example:
            success, result = strategy_crud.create(
                name="RSI Strategy",
                description="Uses RSI for entries",
                indicators={"rsi_period": 14, "overbought": 70},
                engine={"min_confidence": 0.65}
            )
            if success:
                print(f"Created strategy with slug: {result}")
            else:
                print(f"Failed: {result}")
        """
        db = db or get_db()

        try:
            if not name or not name.strip():
                return False, "Strategy name cannot be empty"

            # Generate slug from name
            slug = self._slugify(name)

            # Handle collisions by appending numbers
            base, n = slug, 2
            while strategies.exists(slug, db):
                slug = f"{base}-{n}"
                n += 1

            # Create strategy in database
            ok = strategies.create(
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
        """
        Clone an existing strategy under a new name.

        This method copies all data (description, indicators, engine) from the
        source strategy to a new strategy with the given name. It handles slug
        generation and collision resolution automatically.

        Args:
            source_slug: Slug of the strategy to duplicate
            new_name: Name for the new strategy copy
            db: Optional database connector

        Returns:
            Tuple[bool, str]:
                - First element: True if duplication successful, False otherwise
                - Second element: On success, the new slug; on failure, error message

        Example:
            success, new_slug = strategy_crud.duplicate(
                "my-best-strategy",
                "My Best Strategy Copy"
            )
            if success:
                print(f"Created copy with slug: {new_slug}")
        """
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
        """
        Overwrite strategy data (must contain meta/indicators/engine).

        This method expects a complete strategy data structure with:
            - meta: {name, description}
            - indicators: {}
            - engine: {}

        FEATURE 3: Ensures engine has min_confidence, falling back to global config.

        Args:
            slug: Strategy identifier
            data: Complete strategy data dictionary
            db: Optional database connector

        Returns:
            bool: True if save successful, False otherwise
        """
        db = db or get_db()

        try:
            if not slug:
                logger.warning("save called with empty slug")
                return False

            # Extract data components
            meta = data.get("meta", {})
            name = meta.get("name", slug)
            description = meta.get("description", "")
            indicators = data.get("indicators", {})
            engine = data.get("engine", {})

            # FEATURE 3: Ensure engine has confidence threshold
            if engine and "min_confidence" not in engine:
                # Get from global config or use default
                from db.config_crud import config_crud
                engine["min_confidence"] = config_crud.get("min_confidence", 0.6, db)

            # Use upsert to create or replace
            return strategies.upsert(
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
        """
        Update strategy metadata (name and/or description).

        Args:
            slug: Strategy identifier
            name: New display name (optional)
            description: New description (optional)
            db: Optional database connector

        Returns:
            bool: True if update successful, False otherwise
        """
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
        """
        Delete a strategy with safety checks.

        This method implements several safety measures:
            1. Cannot delete the last remaining strategy
            2. If deleting the active strategy, automatically switches to another
            3. Returns informative messages about success/failure

        Args:
            slug: Strategy identifier to delete
            db: Optional database connector

        Returns:
            Tuple[bool, str]:
                - First element: True if deletion successful, False otherwise
                - Second element: Success or error message

        Example:
            success, message = strategy_crud.delete("old-strategy")
            if success:
                print(f"Deleted: {message}")
            else:
                print(f"Failed: {message}")
        """
        db = db or get_db()

        try:
            # Check if it's the only strategy
            all_strategies = self.list_all(db)
            if len(all_strategies) <= 1:
                return False, "Cannot delete the last strategy"

            # Check if it's active
            active_slug = self.get_active_slug(db)
            if active_slug == slug:
                # Need to switch active to another strategy
                other_slugs = [s["slug"] for s in all_strategies if s["slug"] != slug]
                if other_slugs:
                    self.set_active(other_slugs[0], db)
                    logger.info(f"Active strategy switched from {slug} to {other_slugs[0]}")

            # Delete the strategy
            ok = strategies.delete(slug, db)
            if ok:
                logger.info(f"Deleted strategy: {slug}")
                return True, "Deleted"
            else:
                return False, "Failed to delete strategy"

        except Exception as e:
            logger.error(f"[StrategyCRUD.delete] Failed for {slug}: {e}", exc_info=True)
            return False, f"Delete failed: {e}"

    def activate(self, slug: str, db: DatabaseConnector = None) -> bool:
        """
        Set a strategy as active.

        Args:
            slug: Strategy identifier to activate
            db: Optional database connector

        Returns:
            bool: True if activation successful, False otherwise
        """
        db = db or get_db()
        return strategies.set_active(slug, db)

    def get_active_slug(self, db: DatabaseConnector = None) -> Optional[str]:
        """
        Get the slug of the active strategy.

        Args:
            db: Optional database connector

        Returns:
            Optional[str]: Active strategy slug, or None if none active
        """
        db = db or get_db()
        return strategies.get_active_slug(db)

    def get_active(self, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        """
        Return the currently active strategy's full data.

        Args:
            db: Optional database connector

        Returns:
            Optional[Dict[str, Any]]: Full strategy data, or None if none active
        """
        db = db or get_db()
        return strategies.get_active(db)

    def get_active_name(self, db: DatabaseConnector = None) -> str:
        """
        Get the display name of the active strategy.

        Args:
            db: Optional database connector

        Returns:
            str: Strategy name, or "None" if no active strategy
        """
        db = db or get_db()
        active = self.get_active(db)
        return active.get("name", "None") if active else "None"

    def get_active_indicator_params(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """
        Return indicator parameters of the active strategy.

        Args:
            db: Optional database connector

        Returns:
            Dict[str, Any]: Indicator parameters dictionary, empty if none active
        """
        db = db or get_db()
        active = self.get_active(db)
        return active.get("indicators", {}) if active else {}

    def get_active_engine_config(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """
        Return engine configuration of the active strategy.

        Args:
            db: Optional database connector

        Returns:
            Dict[str, Any]: Engine configuration dictionary, empty if none active
        """
        db = db or get_db()
        active = self.get_active(db)
        return active.get("engine", {}) if active else {}

    def get_active_min_confidence(self, db: DatabaseConnector = None) -> float:
        """
        FEATURE 3: Get min_confidence from active strategy or global config.

        This method implements a hierarchical confidence threshold lookup:
            1. First, check if active strategy has a strategy-specific min_confidence
            2. If not, fall back to global configuration via config_crud
            3. Default to 0.6 if neither exists

        Args:
            db: Optional database connector

        Returns:
            float: Minimum confidence threshold (0.0-1.0)

        Example:
            min_conf = strategy_crud.get_active_min_confidence()
            if signal.confidence >= min_conf:
                execute_trade()
        """
        db = db or get_db()
        engine = self.get_active_engine_config(db)

        # Try strategy-specific first (FEATURE 3 - strategy-specific threshold)
        if engine and "min_confidence" in engine:
            return float(engine["min_confidence"])

        # Fall back to global config
        from db.config_crud import config_crud
        return config_crud.get("min_confidence", 0.6, db)

    def count(self, db: DatabaseConnector = None) -> int:
        """
        Get number of strategies.

        Args:
            db: Optional database connector

        Returns:
            int: Total number of strategies
        """
        db = db or get_db()
        return len(self.list_all(db))

    def _slugify(self, name: str) -> str:
        """
        Convert a display name to a URL-safe slug.

        Slug generation rules:
            1. Convert to lowercase
            2. Remove any non-alphanumeric characters (except spaces and hyphens)
            3. Replace spaces and underscores with hyphens
            4. Remove multiple consecutive hyphens
            5. Trim hyphens from start and end

        Args:
            name: Display name to convert

        Returns:
            str: URL-safe slug (e.g., "My Strategy" → "my-strategy")

        Example:
            >>> _slugify("RSI + MACD Strategy!")
            "rsi-macd-strategy"
        """
        import re
        try:
            if not name:
                return "strategy"

            s = name.lower().strip()
            s = re.sub(r"[^\w\s-]", "", s)  # Remove special characters
            s = re.sub(r"[\s_]+", "-", s)   # Replace spaces/underscores with hyphens
            s = re.sub(r"-+", "-", s)       # Replace multiple hyphens with single
            s = s.strip("-")                 # Remove leading/trailing hyphens
            return s or "strategy"
        except Exception as e:
            logger.error(f"[_slugify] Failed for {name}: {e}", exc_info=True)
            return "strategy"


# Singleton instance for global use
# This provides a single, shared strategy CRUD instance throughout the application
strategy_crud = StrategyCRUD()