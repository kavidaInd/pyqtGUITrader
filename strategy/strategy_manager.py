"""
strategy_manager.py
===================
Backend for managing multiple named strategies.

Each strategy is a dict combining:
  - StrategySetting fields (supertrend, MACD, RSI, BB params)
  - DynamicSignalEngine rules (per-signal groups with logic + rules)
  - Metadata (name, description, created_at, updated_at)

Stored as:  config/strategies/<slug>.json
Active strategy pointer:  config/strategies/_active.json

Usage:
    from strategy.strategy_manager import StrategyManager

    mgr = StrategyManager()
    mgr.create("Momentum Play", description="EMA + RSI crossover")
    mgr.activate("momentum-play")

    # Get the active strategy's signal engine config:
    engine_cfg = mgr.get_active_engine_config()

    # Get the active strategy's indicator params:
    params = mgr.get_active_indicator_params()
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import time
import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import traceback

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────────────

INDICATOR_DEFAULTS = {
    # Empty dict is fine
}

SIGNAL_GROUPS = ["BUY_CALL", "BUY_PUT", "SELL_CALL", "SELL_PUT", "HOLD"]

ENGINE_DEFAULTS: Dict[str, Any] = {
    sig: {"logic": "AND", "rules": [], "enabled": True}
    for sig in SIGNAL_GROUPS
}
ENGINE_DEFAULTS["conflict_resolution"] = "WAIT"


def _slug(name: str) -> str:
    """Convert a display name to a safe filename slug."""
    try:
        if not name:
            logger.warning("_slug called with empty name")
            return "strategy"

        s = name.lower().strip()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s)
        s = re.sub(r"-+", "-", s).strip("-")
        return s or "strategy"
    except Exception as e:
        logger.error(f"[_slug] Failed for {name}: {e}", exc_info=True)
        return "strategy"


def _now_iso() -> str:
    """Get current ISO timestamp."""
    try:
        return datetime.now().isoformat(timespec="seconds")
    except Exception as e:
        logger.error(f"[_now_iso] Failed: {e}", exc_info=True)
        return "1970-01-01T00:00:00"


def _new_strategy(name: str, description: str = "") -> Dict[str, Any]:
    """Create a new strategy dictionary."""
    try:
        return {
            "meta": {
                "name":        name,
                "slug":        _slug(name),
                "description": description,
                "created_at":  _now_iso(),
                "updated_at":  _now_iso(),
            },
            "indicators": deepcopy(INDICATOR_DEFAULTS),
            "engine":     deepcopy(ENGINE_DEFAULTS),
        }
    except Exception as e:
        logger.error(f"[_new_strategy] Failed: {e}", exc_info=True)
        return {
            "meta": {"name": name, "slug": _slug(name), "description": description},
            "indicators": {},
            "engine": {}
        }


class StrategyManager:
    """
    Manages all strategies on disk and exposes the currently active one.

    Thread-safety: all public methods are guarded by a re-entrant lock so
    the GUI and trading thread can both call them safely.
    """

    def __init__(self, strategies_dir: str = "config/strategies"):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if not isinstance(strategies_dir, str):
                logger.error(f"strategies_dir must be string, got {type(strategies_dir)}. Using default.")
                strategies_dir = "config/strategies"

            self._lock = threading.RLock()
            self.strategies_dir = strategies_dir
            self._active_file = os.path.join(strategies_dir, "_active.json")
            self._active_slug: Optional[str] = None
            self._cache: Dict[str, Dict] = {}   # slug → strategy dict

            # Ensure directory exists
            try:
                os.makedirs(strategies_dir, exist_ok=True)
            except PermissionError as e:
                logger.error(f"Permission denied creating directory {strategies_dir}: {e}")
            except Exception as e:
                logger.error(f"Failed to create directory {strategies_dir}: {e}")

            self._load_all()
            self._load_active_pointer()

            # If nothing exists yet, seed a default strategy
            if not self._cache:
                ok, slug = self.create("Default Strategy", "Starting strategy — edit or replace it.")
                if ok:
                    self.activate(slug)

            logger.info(f"StrategyManager initialized with {self.count()} strategies")

        except Exception as e:
            logger.critical(f"[StrategyManager.__init__] Failed: {e}", exc_info=True)
            self._safe_defaults_init()

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._lock = threading.RLock()
        self.strategies_dir = "config/strategies"
        self._active_file = os.path.join("config/strategies", "_active.json")
        self._active_slug = None
        self._cache = {}

    # ── Persistence ───────────────────────────────────────────────────────────

    def _path(self, slug: str) -> str:
        """Get file path for a strategy."""
        try:
            if not slug:
                logger.warning("_path called with empty slug")
                return os.path.join(self.strategies_dir, "unknown.json")

            # Sanitize slug to prevent path traversal
            safe_slug = slug.replace("..", "").replace("/", "").replace("\\", "")
            return os.path.join(self.strategies_dir, f"{safe_slug}.json")
        except Exception as e:
            logger.error(f"[_path] Failed for {slug}: {e}", exc_info=True)
            return os.path.join(self.strategies_dir, "error.json")

    def _load_all(self):
        """Load all strategies from disk."""
        try:
            if not os.path.exists(self.strategies_dir):
                logger.warning(f"Strategies directory not found: {self.strategies_dir}")
                return

            for fname in os.listdir(self.strategies_dir):
                if fname.startswith("_") or not fname.endswith(".json"):
                    continue

                slug = fname[:-5]  # Remove .json
                try:
                    file_path = os.path.join(self.strategies_dir, fname)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # Validate data structure
                    if not isinstance(data, dict):
                        logger.warning(f"Strategy {fname} is not a dict, skipping")
                        continue

                    self._cache[slug] = data
                    logger.debug(f"Loaded strategy: {slug}")

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse strategy {fname}: {e}")
                except IOError as e:
                    logger.error(f"Failed to read strategy {fname}: {e}")
                except Exception as e:
                    logger.error(f"Failed to load strategy {fname}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[_load_all] Failed: {e}", exc_info=True)

    def _load_active_pointer(self):
        """Load the active strategy pointer."""
        try:
            if os.path.exists(self._active_file):
                try:
                    with open(self._active_file, 'r', encoding='utf-8') as f:
                        d = json.load(f)
                    self._active_slug = d.get("active_slug")
                except (json.JSONDecodeError, IOError) as e:
                    logger.error(f"Failed to load active pointer: {e}")

            # Validate the pointer still exists
            if self._active_slug and self._active_slug not in self._cache:
                logger.warning(f"Active slug {self._active_slug} not found in cache")
                self._active_slug = None

            # Auto-pick first available
            if self._active_slug is None and self._cache:
                first_key = next(iter(self._cache))
                self._active_slug = first_key
                logger.info(f"Auto-selected first strategy: {first_key}")

        except Exception as e:
            logger.error(f"[_load_active_pointer] Failed: {e}", exc_info=True)

    def _save_strategy(self, slug: str) -> bool:
        """Save a strategy to disk atomically."""
        if slug not in self._cache:
            logger.error(f"Cannot save unknown strategy: {slug}")
            return False

        path = self._path(slug)
        tmp = path + ".tmp"

        try:
            # Ensure directory exists
            dir_path = os.path.dirname(path)
            if dir_path:
                try:
                    os.makedirs(dir_path, exist_ok=True)
                except Exception as e:
                    logger.error(f"Failed to create directory {dir_path}: {e}")
                    return False

            # Write to temp file
            try:
                with open(tmp, "w", encoding='utf-8') as f:
                    json.dump(self._cache[slug], f, indent=2)
            except IOError as e:
                logger.error(f"Failed to write temp file for {slug}: {e}")
                return False
            except TypeError as e:
                logger.error(f"Data for {slug} is not JSON serializable: {e}")
                return False

            # Atomic replace
            try:
                os.replace(tmp, path)
                logger.debug(f"Saved strategy: {slug}")
                return True
            except OSError as e:
                logger.error(f"Failed to replace strategy file {slug}: {e}")
                self._safe_remove(tmp)
                return False

        except Exception as e:
            logger.error(f"[_save_strategy] Failed for {slug}: {e}", exc_info=True)
            self._safe_remove(tmp)
            return False

    def _safe_remove(self, filepath: str) -> None:
        """Safely remove a file, ignoring errors."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            logger.warning(f"Failed to remove {filepath}: {e}")

    def _save_active_pointer(self):
        """Save the active strategy pointer."""
        tmp = self._active_file + ".tmp"
        try:
            # Ensure directory exists
            dir_path = os.path.dirname(self._active_file)
            if dir_path:
                try:
                    os.makedirs(dir_path, exist_ok=True)
                except Exception as e:
                    logger.error(f"Failed to create directory {dir_path}: {e}")
                    return

            with open(tmp, "w", encoding='utf-8') as f:
                json.dump({"active_slug": self._active_slug}, f)

            os.replace(tmp, self._active_file)
            logger.debug(f"Saved active pointer: {self._active_slug}")

        except Exception as e:
            logger.error(f"Failed to save active pointer: {e}", exc_info=True)
            self._safe_remove(tmp)

    # ── Public API ────────────────────────────────────────────────────────────

    def list_strategies(self) -> List[Dict[str, str]]:
        """Return list of {slug, name, description, updated_at, is_active} dicts."""
        with self._lock:
            try:
                result = []
                for slug, data in self._cache.items():
                    try:
                        meta = data.get("meta", {}) if data else {}
                        result.append({
                            "slug":        slug,
                            "name":        str(meta.get("name", slug)),
                            "description": str(meta.get("description", "")),
                            "created_at":  str(meta.get("created_at", "")),
                            "updated_at":  str(meta.get("updated_at", "")),
                            "is_active":   slug == self._active_slug,
                        })
                    except Exception as e:
                        logger.warning(f"Failed to process strategy {slug}: {e}")
                        continue

                # Sort by name
                result.sort(key=lambda x: x["name"].lower())
                return result

            except Exception as e:
                logger.error(f"[list_strategies] Failed: {e}", exc_info=True)
                return []

    def get(self, slug: str) -> Optional[Dict]:
        """Return a deep copy of the strategy dict, or None."""
        with self._lock:
            try:
                if not slug:
                    logger.warning("get called with empty slug")
                    return None

                if slug in self._cache:
                    return deepcopy(self._cache[slug])
                return None
            except Exception as e:
                logger.error(f"[get] Failed for {slug}: {e}", exc_info=True)
                return None

    def get_active(self) -> Optional[Dict]:
        """Return a deep copy of the currently active strategy."""
        with self._lock:
            try:
                if self._active_slug:
                    return self.get(self._active_slug)
                return None
            except Exception as e:
                logger.error(f"[get_active] Failed: {e}", exc_info=True)
                return None

    def get_active_slug(self) -> Optional[str]:
        """Get the slug of the active strategy."""
        with self._lock:
            try:
                return self._active_slug
            except Exception as e:
                logger.error(f"[get_active_slug] Failed: {e}", exc_info=True)
                return None

    def get_active_name(self) -> str:
        """Get the name of the active strategy."""
        with self._lock:
            try:
                s = self.get_active()
                if s:
                    meta = s.get("meta", {})
                    return str(meta.get("name", "—"))
                return "None"
            except Exception as e:
                logger.error(f"[get_active_name] Failed: {e}", exc_info=True)
                return "None"

    def create(self, name: str, description: str = "") -> Tuple[bool, str]:
        """Create a new strategy. Returns (ok, slug_or_error)."""
        with self._lock:
            try:
                if not name or not name.strip():
                    logger.warning("create called with empty name")
                    return False, "Strategy name cannot be empty"

                slug = _slug(name)
                # Handle collisions
                base, n = slug, 2
                while slug in self._cache:
                    slug = f"{base}-{n}"
                    n += 1

                strategy = _new_strategy(name, description)
                strategy["meta"]["slug"] = slug
                self._cache[slug] = strategy
                ok = self._save_strategy(slug)

                if ok:
                    logger.info(f"Created strategy '{name}' → {slug}")
                else:
                    logger.error(f"Failed to save strategy '{name}'")

                return ok, slug if ok else "Failed to save"

            except Exception as e:
                logger.error(f"[create] Failed for {name}: {e}", exc_info=True)
                return False, f"Creation failed: {e}"

    def duplicate(self, source_slug: str, new_name: str) -> Tuple[bool, str]:
        """Clone an existing strategy under a new name."""
        with self._lock:
            try:
                if not source_slug:
                    return False, "Source slug is empty"

                if source_slug not in self._cache:
                    return False, f"Source strategy '{source_slug}' not found"

                if not new_name or not new_name.strip():
                    return False, "New name cannot be empty"

                data = deepcopy(self._cache[source_slug])
                new_slug = _slug(new_name)
                base, n = new_slug, 2
                while new_slug in self._cache:
                    new_slug = f"{base}-{n}"
                    n += 1

                data["meta"]["name"] = new_name
                data["meta"]["slug"] = new_slug
                data["meta"]["created_at"] = _now_iso()
                data["meta"]["updated_at"] = _now_iso()
                self._cache[new_slug] = data
                ok = self._save_strategy(new_slug)

                if ok:
                    logger.info(f"Duplicated {source_slug} → {new_slug}")
                else:
                    logger.error(f"Failed to save duplicated strategy {new_slug}")

                return ok, new_slug if ok else "Failed to save"

            except Exception as e:
                logger.error(f"[duplicate] Failed for {source_slug}: {e}", exc_info=True)
                return False, f"Duplicate failed: {e}"

    def save(self, slug: str, data: Dict) -> bool:
        """Overwrite strategy data (must contain meta/indicators/engine)."""
        with self._lock:
            try:
                if not slug:
                    logger.warning("save called with empty slug")
                    return False

                if slug not in self._cache:
                    logger.error(f"Cannot save unknown slug: {slug}")
                    return False

                if data is None:
                    logger.error(f"save called with None data for {slug}")
                    return False

                data = deepcopy(data)

                # Ensure required structure exists
                if "meta" not in data:
                    data["meta"] = {}
                if "indicators" not in data:
                    data["indicators"] = {}
                if "engine" not in data:
                    data["engine"] = {}

                data["meta"]["updated_at"] = _now_iso()
                data["meta"]["slug"] = slug  # prevent slug drift

                self._cache[slug] = data
                return self._save_strategy(slug)

            except Exception as e:
                logger.error(f"[save] Failed for {slug}: {e}", exc_info=True)
                return False

    def update_meta(self, slug: str, name: str = None, description: str = None) -> bool:
        """Update strategy metadata."""
        with self._lock:
            try:
                if not slug:
                    logger.warning("update_meta called with empty slug")
                    return False

                if slug not in self._cache:
                    logger.error(f"Cannot update unknown slug: {slug}")
                    return False

                if "meta" not in self._cache[slug]:
                    self._cache[slug]["meta"] = {}

                if name is not None:
                    self._cache[slug]["meta"]["name"] = str(name)
                if description is not None:
                    self._cache[slug]["meta"]["description"] = str(description)

                self._cache[slug]["meta"]["updated_at"] = _now_iso()
                return self._save_strategy(slug)

            except Exception as e:
                logger.error(f"[update_meta] Failed for {slug}: {e}", exc_info=True)
                return False

    def delete(self, slug: str) -> Tuple[bool, str]:
        """Delete a strategy. Cannot delete if it's the only one."""
        with self._lock:
            try:
                if not slug:
                    return False, "Slug is empty"

                if slug not in self._cache:
                    return False, f"Strategy '{slug}' not found"

                if len(self._cache) == 1:
                    return False, "Cannot delete the last strategy"

                del self._cache[slug]
                path = self._path(slug)
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        logger.info(f"Deleted strategy file: {path}")
                    except Exception as e:
                        logger.error(f"Could not delete file {path}: {e}")

                # Switch active if needed
                if self._active_slug == slug:
                    first_key = next(iter(self._cache), None)
                    self._active_slug = first_key
                    self._save_active_pointer()
                    logger.info(f"Switched active strategy to {first_key}")

                return True, "Deleted"

            except Exception as e:
                logger.error(f"[delete] Failed for {slug}: {e}", exc_info=True)
                return False, f"Delete failed: {e}"

    def activate(self, slug: str) -> bool:
        """Set a strategy as active. Returns True on success."""
        with self._lock:
            try:
                if not slug:
                    logger.error("activate called with empty slug")
                    return False

                if slug not in self._cache:
                    logger.error(f"Cannot activate unknown slug: {slug}")
                    return False

                self._active_slug = slug
                self._save_active_pointer()
                logger.info(f"Activated strategy: {slug} ({self.get_active_name()})")
                return True

            except Exception as e:
                logger.error(f"[activate] Failed for {slug}: {e}", exc_info=True)
                return False

    def get_active_indicator_params(self) -> Dict[str, Any]:
        """Return indicator params of the active strategy (for TrendDetector / StrategySetting)."""
        with self._lock:
            try:
                s = self.get_active()
                if s:
                    return deepcopy(s.get("indicators", deepcopy(INDICATOR_DEFAULTS)))
                return deepcopy(INDICATOR_DEFAULTS)
            except Exception as e:
                logger.error(f"[get_active_indicator_params] Failed: {e}", exc_info=True)
                return deepcopy(INDICATOR_DEFAULTS)

    def get_active_engine_config(self) -> Dict[str, Any]:
        """Return engine config of the active strategy (for DynamicSignalEngine.from_dict)."""
        with self._lock:
            try:
                s = self.get_active()
                if s:
                    return deepcopy(s.get("engine", deepcopy(ENGINE_DEFAULTS)))
                return deepcopy(ENGINE_DEFAULTS)
            except Exception as e:
                logger.error(f"[get_active_engine_config] Failed: {e}", exc_info=True)
                return deepcopy(ENGINE_DEFAULTS)

    def count(self) -> int:
        """Get number of strategies."""
        with self._lock:
            try:
                return len(self._cache)
            except Exception as e:
                logger.error(f"[count] Failed: {e}", exc_info=True)
                return 0

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown."""
        try:
            logger.info("[StrategyManager] Starting cleanup")

            # Save active pointer one last time
            self._save_active_pointer()

            # Clear cache
            self._cache.clear()
            self._active_slug = None

            logger.info("[StrategyManager] Cleanup completed")

        except Exception as e:
            logger.error(f"[StrategyManager.cleanup] Error: {e}", exc_info=True)


# Optional: Context manager for temporary strategy changes
class StrategyContext:
    """
    Context manager for temporarily modifying the active strategy.

    Example:
        with StrategyContext(manager) as mgr:
            mgr.activate("temp-strategy")
            # ... do something with temp strategy
        # Original active strategy is restored
    """

    def __init__(self, manager: StrategyManager):
        # Rule 2: Safe defaults
        self.manager = None
        self._original_active = None

        try:
            # Rule 6: Input validation
            if not isinstance(manager, StrategyManager):
                raise ValueError(f"Expected StrategyManager instance, got {type(manager)}")

            self.manager = manager
            self._original_active = manager.get_active_slug()
            logger.debug("StrategyContext initialized")

        except Exception as e:
            logger.error(f"[StrategyContext.__init__] Failed: {e}", exc_info=True)
            raise

    def __enter__(self) -> StrategyManager:
        return self.manager

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            # Restore original active strategy
            if self.manager and self._original_active:
                self.manager.activate(self._original_active)
                logger.debug("StrategyContext restored original active strategy")

        except Exception as e:
            logger.error(f"[StrategyContext.__exit__] Failed: {e}", exc_info=True)
            # Log but don't re-raise to avoid masking original exception
            if exc_type:
                logger.error(f"Original exception: {exc_type.__name__}: {exc_val}")