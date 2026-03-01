"""
strategy/strategy_manager_db.py
================================
Database-backed strategy manager using the SQLite database instead of JSON files.

FEATURE 3: Added support for confidence thresholds and rule weights.
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
ENGINE_DEFAULTS["min_confidence"] = 0.6  # FEATURE 3: Default confidence threshold


class StrategyManager:
    """
    Database-backed strategy manager.

    Thread-safety: all public methods are guarded by a re-entrant lock.

    FEATURE 3: Supports confidence thresholds and rule weights.
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
                        # FEATURE 3: Ensure default strategy has confidence threshold
                        strategy = self.get(slug)
                        if strategy and "engine" in strategy:
                            strategy["engine"]["min_confidence"] = 0.6
                            self.save(slug, strategy)

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

                # FEATURE 3: Ensure engine config has min_confidence
                if strategy and "engine" in strategy and strategy["engine"]:
                    if "min_confidence" not in strategy["engine"]:
                        strategy["engine"]["min_confidence"] = 0.6

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

                # FEATURE 3: Ensure engine config has min_confidence
                if strategy and "engine" in strategy and strategy["engine"]:
                    if "min_confidence" not in strategy["engine"]:
                        strategy["engine"]["min_confidence"] = 0.6

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
                ok, slug = strategy_crud.create(name, description, db=db)

                # FEATURE 3: Initialize with default confidence threshold
                if ok:
                    strategy = self.get(slug)
                    if strategy:
                        if "engine" not in strategy:
                            strategy["engine"] = {}
                        strategy["engine"]["min_confidence"] = 0.6
                        self.save(slug, strategy)

                return ok, slug
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

                # FEATURE 3: Validate confidence threshold if present
                if "engine" in data and data["engine"]:
                    if "min_confidence" in data["engine"]:
                        try:
                            conf = float(data["engine"]["min_confidence"])
                            # Clamp between 0 and 1
                            data["engine"]["min_confidence"] = max(0.0, min(1.0, conf))
                        except (ValueError, TypeError):
                            data["engine"]["min_confidence"] = 0.6
                    else:
                        data["engine"]["min_confidence"] = 0.6

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
                config = strategy_crud.get_active_engine_config(db)

                # FEATURE 3: Ensure min_confidence is present
                if config and "min_confidence" not in config:
                    config["min_confidence"] = 0.6

                return deepcopy(config) if config else deepcopy(ENGINE_DEFAULTS)
            except Exception as e:
                logger.error(f"[get_active_engine_config] Failed: {e}", exc_info=True)
                return deepcopy(ENGINE_DEFAULTS)

    # ==================================================================
    # FEATURE 3: New methods for confidence scoring
    # ==================================================================

    def get_active_min_confidence(self) -> float:
        """
        Get minimum confidence threshold from active strategy.

        Returns:
            Confidence threshold (0.0-1.0)
        """
        with self._lock:
            try:
                engine = self.get_active_engine_config()
                return float(engine.get("min_confidence", 0.6))
            except Exception as e:
                logger.error(f"[get_active_min_confidence] Failed: {e}", exc_info=True)
                return 0.6

    def set_active_min_confidence(self, threshold: float) -> bool:
        """
        Set minimum confidence threshold for active strategy.

        Args:
            threshold: New threshold (0.0-1.0)

        Returns:
            True if successful
        """
        with self._lock:
            try:
                active_slug = self.get_active_slug()
                if not active_slug:
                    return False

                strategy = self.get(active_slug)
                if not strategy:
                    return False

                if "engine" not in strategy:
                    strategy["engine"] = {}

                # Clamp threshold
                strategy["engine"]["min_confidence"] = max(0.0, min(1.0, float(threshold)))

                return self.save(active_slug, strategy)
            except Exception as e:
                logger.error(f"[set_active_min_confidence] Failed: {e}", exc_info=True)
                return False

    def get_rule_weights(self, slug: str = None) -> Dict[str, List[float]]:
        """
        Get all rule weights for a strategy.

        Args:
            slug: Strategy slug (uses active if None)

        Returns:
            Dict mapping signal group to list of weights
        """
        with self._lock:
            try:
                if slug is None:
                    slug = self.get_active_slug()

                if not slug:
                    return {}

                strategy = self.get(slug)
                if not strategy or "engine" not in strategy:
                    return {}

                result = {}
                engine = strategy["engine"]

                for signal in SIGNAL_GROUPS:
                    group = engine.get(signal, {})
                    rules = group.get("rules", [])
                    weights = [float(r.get("weight", 1.0)) for r in rules]
                    result[signal] = weights

                return result
            except Exception as e:
                logger.error(f"[get_rule_weights] Failed: {e}", exc_info=True)
                return {}

    def validate_strategy(self, strategy: Dict) -> Tuple[bool, List[str]]:
        """
        Validate a strategy dictionary.

        Args:
            strategy: Strategy dict to validate

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        try:
            # Check required fields
            if not strategy:
                errors.append("Strategy is empty")
                return False, errors

            if "name" not in strategy or not strategy["name"]:
                errors.append("Strategy name is required")

            # Validate engine
            engine = strategy.get("engine", {})

            # Check confidence threshold
            min_conf = engine.get("min_confidence", 0.6)
            try:
                conf = float(min_conf)
                if not (0.0 <= conf <= 1.0):
                    errors.append(f"Min confidence must be between 0.0 and 1.0, got {conf}")
            except (ValueError, TypeError):
                errors.append(f"Invalid min confidence value: {min_conf}")

            # Validate each signal group
            for signal in SIGNAL_GROUPS:
                group = engine.get(signal, {})

                # Check logic
                logic = group.get("logic", "AND")
                if logic not in ["AND", "OR"]:
                    errors.append(f"{signal}: Invalid logic '{logic}', must be AND/OR")

                # Validate rules
                rules = group.get("rules", [])
                for i, rule in enumerate(rules):
                    self._validate_rule(rule, signal, i, errors)

            return len(errors) == 0, errors

        except Exception as e:
            logger.error(f"[validate_strategy] Failed: {e}", exc_info=True)
            errors.append(f"Validation error: {e}")
            return False, errors

    def _validate_rule(self, rule: Dict, signal: str, rule_index: int, errors: List[str]):
        """Validate a single rule."""
        try:
            # Check required fields
            if "lhs" not in rule:
                errors.append(f"{signal} rule {rule_index}: Missing LHS")
            if "op" not in rule:
                errors.append(f"{signal} rule {rule_index}: Missing operator")
            if "rhs" not in rule:
                errors.append(f"{signal} rule {rule_index}: Missing RHS")

            # Validate operator
            op = rule.get("op", "")
            valid_ops = [">", "<", ">=", "<=", "==", "!="]
            if op and op not in valid_ops:
                errors.append(f"{signal} rule {rule_index}: Invalid operator '{op}'")

            # FEATURE 3: Validate weight
            weight = rule.get("weight", 1.0)
            try:
                w = float(weight)
                if w <= 0:
                    errors.append(f"{signal} rule {rule_index}: Weight must be positive, got {w}")
                elif w > 10:
                    errors.append(f"{signal} rule {rule_index}: Weight unusually large ({w})")
            except (ValueError, TypeError):
                errors.append(f"{signal} rule {rule_index}: Invalid weight value '{weight}'")

            # Validate LHS
            lhs = rule.get("lhs", {})
            lhs_type = lhs.get("type", "")
            if lhs_type not in ["indicator", "scalar", "column"]:
                errors.append(f"{signal} rule {rule_index}: Invalid LHS type '{lhs_type}'")

            # Validate RHS
            rhs = rule.get("rhs", {})
            rhs_type = rhs.get("type", "")
            if rhs_type not in ["indicator", "scalar", "column"]:
                errors.append(f"{signal} rule {rule_index}: Invalid RHS type '{rhs_type}'")

        except Exception as e:
            errors.append(f"{signal} rule {rule_index}: Validation error: {e}")

    def get_statistics(self, slug: str = None) -> Dict[str, Any]:
        """
        Get statistics for a strategy.

        Args:
            slug: Strategy slug (uses active if None)

        Returns:
            Dict with total_rules, unique_indicators, enabled_groups, etc.
        """
        with self._lock:
            try:
                if slug is None:
                    slug = self.get_active_slug()

                if not slug:
                    return {}

                strategy = self.get(slug)
                if not strategy:
                    return {}

                engine = strategy.get("engine", {})

                total_rules = 0
                indicators = set()
                enabled_count = 0
                total_weight = 0.0
                avg_weight = 0.0

                for signal in SIGNAL_GROUPS:
                    group = engine.get(signal, {})
                    rules = group.get("rules", [])
                    total_rules += len(rules)

                    if group.get("enabled", True):
                        enabled_count += 1

                    for rule in rules:
                        # Count indicators
                        for side in ["lhs", "rhs"]:
                            side_data = rule.get(side, {})
                            if side_data.get("type") == "indicator":
                                indicators.add(side_data.get("indicator", "").lower())

                        # Sum weights
                        weight = rule.get("weight", 1.0)
                        try:
                            total_weight += float(weight)
                        except (ValueError, TypeError):
                            total_weight += 1.0

                avg_weight = total_weight / total_rules if total_rules > 0 else 0

                return {
                    "total_rules": total_rules,
                    "unique_indicators": len(indicators),
                    "enabled_groups": enabled_count,
                    "total_groups": len(SIGNAL_GROUPS),
                    "total_weight": round(total_weight, 2),
                    "avg_weight": round(avg_weight, 2),
                    "min_confidence": engine.get("min_confidence", 0.6),
                }
            except Exception as e:
                logger.error(f"[get_statistics] Failed: {e}", exc_info=True)
                return {}

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