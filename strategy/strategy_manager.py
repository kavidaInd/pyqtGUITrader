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
import os
import re
import time
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────────────

INDICATOR_DEFAULTS = {
}

SIGNAL_GROUPS = ["BUY_CALL", "BUY_PUT", "SELL_CALL", "SELL_PUT", "HOLD"]

ENGINE_DEFAULTS: Dict[str, Any] = {
    sig: {"logic": "AND", "rules": [], "enabled": True}
    for sig in SIGNAL_GROUPS
}
ENGINE_DEFAULTS["conflict_resolution"] = "WAIT"


def _slug(name: str) -> str:
    """Convert a display name to a safe filename slug."""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "strategy"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_strategy(name: str, description: str = "") -> Dict[str, Any]:
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


class StrategyManager:
    """
    Manages all strategies on disk and exposes the currently active one.

    Thread-safety: all public methods are guarded by a re-entrant lock so
    the GUI and trading thread can both call them safely.
    """

    def __init__(self, strategies_dir: str = "config/strategies"):
        import threading
        self._lock = threading.RLock()
        self.strategies_dir = strategies_dir
        self._active_file  = os.path.join(strategies_dir, "_active.json")
        self._active_slug: Optional[str] = None
        self._cache: Dict[str, Dict] = {}   # slug → strategy dict

        os.makedirs(strategies_dir, exist_ok=True)
        self._load_all()
        self._load_active_pointer()

        # If nothing exists yet, seed a default strategy
        if not self._cache:
            self.create("Default Strategy", "Starting strategy — edit or replace it.")
            self.activate("default-strategy")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _path(self, slug: str) -> str:
        return os.path.join(self.strategies_dir, f"{slug}.json")

    def _load_all(self):
        for fname in os.listdir(self.strategies_dir):
            if fname.startswith("_") or not fname.endswith(".json"):
                continue
            slug = fname[:-5]
            try:
                with open(os.path.join(self.strategies_dir, fname)) as f:
                    data = json.load(f)
                self._cache[slug] = data
            except Exception as e:
                logger.error(f"Failed to load strategy {fname}: {e}")

    def _load_active_pointer(self):
        if os.path.exists(self._active_file):
            try:
                with open(self._active_file) as f:
                    d = json.load(f)
                self._active_slug = d.get("active_slug")
            except Exception:
                pass

        # Validate the pointer still exists
        if self._active_slug and self._active_slug not in self._cache:
            self._active_slug = None

        # Auto-pick first available
        if self._active_slug is None and self._cache:
            self._active_slug = next(iter(self._cache))

    def _save_strategy(self, slug: str) -> bool:
        path = self._path(slug)
        tmp  = path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(self._cache[slug], f, indent=2)
            os.replace(tmp, path)
            return True
        except Exception as e:
            logger.error(f"Failed to save strategy {slug}: {e}")
            if os.path.exists(tmp):
                try: os.remove(tmp)
                except: pass
            return False

    def _save_active_pointer(self):
        tmp = self._active_file + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump({"active_slug": self._active_slug}, f)
            os.replace(tmp, self._active_file)
        except Exception as e:
            logger.error(f"Failed to save active pointer: {e}")

    # ── Public API ────────────────────────────────────────────────────────────

    def list_strategies(self) -> List[Dict[str, str]]:
        """Return list of {slug, name, description, updated_at, is_active} dicts."""
        with self._lock:
            result = []
            for slug, data in self._cache.items():
                meta = data.get("meta", {})
                result.append({
                    "slug":        slug,
                    "name":        meta.get("name", slug),
                    "description": meta.get("description", ""),
                    "created_at":  meta.get("created_at", ""),
                    "updated_at":  meta.get("updated_at", ""),
                    "is_active":   slug == self._active_slug,
                })
            # Sort by name
            result.sort(key=lambda x: x["name"].lower())
            return result

    def get(self, slug: str) -> Optional[Dict]:
        """Return a deep copy of the strategy dict, or None."""
        with self._lock:
            if slug in self._cache:
                return deepcopy(self._cache[slug])
            return None

    def get_active(self) -> Optional[Dict]:
        """Return a deep copy of the currently active strategy."""
        with self._lock:
            if self._active_slug:
                return self.get(self._active_slug)
            return None

    def get_active_slug(self) -> Optional[str]:
        with self._lock:
            return self._active_slug

    def get_active_name(self) -> str:
        with self._lock:
            s = self.get_active()
            if s:
                return s.get("meta", {}).get("name", "—")
            return "None"

    def create(self, name: str, description: str = "") -> Tuple[bool, str]:
        """Create a new strategy. Returns (ok, slug_or_error)."""
        with self._lock:
            slug = _slug(name)
            # Handle collisions
            base, n = slug, 2
            while slug in self._cache:
                slug = f"{base}-{n}"; n += 1

            strategy = _new_strategy(name, description)
            strategy["meta"]["slug"] = slug
            self._cache[slug] = strategy
            ok = self._save_strategy(slug)
            logger.info(f"Created strategy '{name}' → {slug}")
            return ok, slug

    def duplicate(self, source_slug: str, new_name: str) -> Tuple[bool, str]:
        """Clone an existing strategy under a new name."""
        with self._lock:
            if source_slug not in self._cache:
                return False, "Source strategy not found"
            data = deepcopy(self._cache[source_slug])
            new_slug = _slug(new_name)
            base, n = new_slug, 2
            while new_slug in self._cache:
                new_slug = f"{base}-{n}"; n += 1
            data["meta"]["name"]       = new_name
            data["meta"]["slug"]       = new_slug
            data["meta"]["created_at"] = _now_iso()
            data["meta"]["updated_at"] = _now_iso()
            self._cache[new_slug] = data
            ok = self._save_strategy(new_slug)
            return ok, new_slug

    def save(self, slug: str, data: Dict) -> bool:
        """Overwrite strategy data (must contain meta/indicators/engine)."""
        with self._lock:
            if slug not in self._cache:
                return False
            data = deepcopy(data)
            data["meta"]["updated_at"] = _now_iso()
            data["meta"]["slug"] = slug           # prevent slug drift
            self._cache[slug] = data
            return self._save_strategy(slug)

    def update_meta(self, slug: str, name: str = None, description: str = None) -> bool:
        with self._lock:
            if slug not in self._cache:
                return False
            if name is not None:
                self._cache[slug]["meta"]["name"] = name
            if description is not None:
                self._cache[slug]["meta"]["description"] = description
            self._cache[slug]["meta"]["updated_at"] = _now_iso()
            return self._save_strategy(slug)

    def delete(self, slug: str) -> Tuple[bool, str]:
        """Delete a strategy. Cannot delete if it's the only one."""
        with self._lock:
            if slug not in self._cache:
                return False, "Strategy not found"
            if len(self._cache) == 1:
                return False, "Cannot delete the last strategy"
            del self._cache[slug]
            path = self._path(slug)
            if os.path.exists(path):
                try: os.remove(path)
                except Exception as e:
                    logger.error(f"Could not delete file {path}: {e}")
            # Switch active if needed
            if self._active_slug == slug:
                self._active_slug = next(iter(self._cache), None)
                self._save_active_pointer()
            return True, "Deleted"

    def activate(self, slug: str) -> bool:
        """Set a strategy as active. Returns True on success."""
        with self._lock:
            if slug not in self._cache:
                logger.error(f"Cannot activate unknown slug: {slug}")
                return False
            self._active_slug = slug
            self._save_active_pointer()
            logger.info(f"Activated strategy: {slug} ({self.get_active_name()})")
            return True

    def get_active_indicator_params(self) -> Dict[str, Any]:
        """Return indicator params of the active strategy (for TrendDetector / StrategySetting)."""
        with self._lock:
            s = self.get_active()
            if s:
                return deepcopy(s.get("indicators", deepcopy(INDICATOR_DEFAULTS)))
            return deepcopy(INDICATOR_DEFAULTS)

    def get_active_engine_config(self) -> Dict[str, Any]:
        """Return engine config of the active strategy (for DynamicSignalEngine.from_dict)."""
        with self._lock:
            s = self.get_active()
            if s:
                return deepcopy(s.get("engine", deepcopy(ENGINE_DEFAULTS)))
            return deepcopy(ENGINE_DEFAULTS)

    def count(self) -> int:
        with self._lock:
            return len(self._cache)