"""
ReEntrySetting.py
=================
Database-backed re-entry settings.

Re-entry governs what happens AFTER a position is closed (by SL, TP, or signal)
before the engine is allowed to open a new position in the same direction.

Settings:
  allow_reentry          — master switch: if False, re-entry is never attempted.
  min_candles_after_sl   — candles to wait after a stop-loss exit.
  min_candles_after_tp   — candles to wait after a take-profit exit.
  min_candles_after_signal — candles to wait after a signal-based exit.
  min_candles_default    — fallback if exit reason is unknown.
  same_direction_only    — if True, only block re-entry in the same direction
                           (e.g. CALL→CALL); opposite direction (CALL→PUT) is
                           always allowed immediately.
  require_new_signal     — require a fresh BUY_CALL / BUY_PUT signal after the
                           wait, not just the old signal still being active.
  price_filter_enabled   — if True, also apply the re-entry price filter.
  price_filter_pct       — block re-entry if current price is worse than entry
                           price by more than this % (avoids chasing).
  max_reentries_per_day  — max number of re-entries allowed per day (0 = unlimited).
"""

import logging
from typing import Any, Dict

from data.trade_state_manager import state_manager
from db.crud import reentry as reentry_crud

logger = logging.getLogger(__name__)


class ReEntrySetting:
    """
    Database-backed re-entry guard settings.

    Follows the same pattern as DailyTradeSetting / ProfitStoplossSetting:
      - DEFAULTS dict defines every field and its default value.
      - load()  reads from app_kv via ReEntryCRUD.
      - save()  writes to app_kv and applies to trading state.
      - Property accessors for every field.
    """

    DEFAULTS: Dict[str, Any] = {
        # Master switch
        "allow_reentry": True,

        # Candle wait per exit reason
        "min_candles_after_sl": 3,
        "min_candles_after_tp": 1,
        "min_candles_after_signal": 2,
        "min_candles_default": 2,

        # Direction control
        "same_direction_only": False,

        # Signal freshness
        "require_new_signal": True,

        # Price filter
        "price_filter_enabled": True,
        "price_filter_pct": 5.0,

        # Daily re-entry cap (0 = unlimited)
        "max_reentries_per_day": 0,
    }

    FIELD_TYPES: Dict[str, type] = {
        "allow_reentry": bool,
        "min_candles_after_sl": int,
        "min_candles_after_tp": int,
        "min_candles_after_signal": int,
        "min_candles_default": int,
        "same_direction_only": bool,
        "require_new_signal": bool,
        "price_filter_enabled": bool,
        "price_filter_pct": float,
        "max_reentries_per_day": int,
    }

    def __init__(self):
        self._safe_defaults_init()
        try:
            self.load()
            logger.info("ReEntrySetting initialized")
        except Exception as e:
            logger.critical(f"[ReEntrySetting.__init__] Failed: {e}", exc_info=True)
            self.data = dict(self.DEFAULTS)

    # ── Safe defaults ─────────────────────────────────────────────────────────

    def _safe_defaults_init(self):
        self.data: Dict[str, Any] = dict(self.DEFAULTS)
        self._loaded = False

    # ── Type coercion ─────────────────────────────────────────────────────────

    def _coerce(self, key: str, value: Any) -> Any:
        expected = self.FIELD_TYPES.get(key, str)
        if value is None:
            return self.DEFAULTS[key]
        try:
            if expected is bool:
                if isinstance(value, str):
                    return value.lower() in ('true', '1', 'yes', 'on')
                return bool(value)
            if expected is int:
                return int(float(value)) if isinstance(value, str) else int(value)
            if expected is float:
                return float(value)
            return str(value)
        except (ValueError, TypeError):
            return self.DEFAULTS[key]

    # ── Persistence ───────────────────────────────────────────────────────────

    def load(self) -> bool:
        try:
            data = reentry_crud.get()
            self.data = dict(self.DEFAULTS)
            for k, v in data.items():
                if k in self.DEFAULTS:
                    self.data[k] = self._coerce(k, v)
            self._loaded = True
            logger.debug("Re-entry settings loaded from database")
            return True
        except Exception as e:
            logger.error(f"[ReEntrySetting.load] {e}", exc_info=True)
            self.data = dict(self.DEFAULTS)
            return False

    def save(self) -> bool:
        try:
            success = reentry_crud.save(self.data)
            if success:
                logger.debug("Re-entry settings saved to database")
                self._apply_to_state()
            else:
                logger.error("Failed to save re-entry settings")
            return success
        except Exception as e:
            logger.error(f"[ReEntrySetting.save] {e}", exc_info=True)
            return False

    def _apply_to_state(self):
        """Push settings into trade state so the engine picks them up live."""
        try:
            state = state_manager.get_state()
            state.reentry_allow                = self.allow_reentry
            state.reentry_min_candles_sl       = self.min_candles_after_sl
            state.reentry_min_candles_tp       = self.min_candles_after_tp
            state.reentry_min_candles_signal   = self.min_candles_after_signal
            state.reentry_min_candles_default  = self.min_candles_default
            state.reentry_same_direction_only  = self.same_direction_only
            state.reentry_require_new_signal   = self.require_new_signal
            state.reentry_price_filter_enabled = self.price_filter_enabled
            state.reentry_price_filter_pct     = self.price_filter_pct
            state.reentry_max_per_day          = self.max_reentries_per_day
            logger.debug("[ReEntrySetting] Applied to trade state")
        except Exception as e:
            logger.error(f"[ReEntrySetting._apply_to_state] {e}", exc_info=True)

    # ── Property accessors ────────────────────────────────────────────────────

    @property
    def allow_reentry(self) -> bool:
        return bool(self.data.get("allow_reentry", self.DEFAULTS["allow_reentry"]))

    @allow_reentry.setter
    def allow_reentry(self, v: bool):
        self.data["allow_reentry"] = bool(v)

    @property
    def min_candles_after_sl(self) -> int:
        return int(self.data.get("min_candles_after_sl", self.DEFAULTS["min_candles_after_sl"]))

    @min_candles_after_sl.setter
    def min_candles_after_sl(self, v: int):
        self.data["min_candles_after_sl"] = max(0, int(v))

    @property
    def min_candles_after_tp(self) -> int:
        return int(self.data.get("min_candles_after_tp", self.DEFAULTS["min_candles_after_tp"]))

    @min_candles_after_tp.setter
    def min_candles_after_tp(self, v: int):
        self.data["min_candles_after_tp"] = max(0, int(v))

    @property
    def min_candles_after_signal(self) -> int:
        return int(self.data.get("min_candles_after_signal", self.DEFAULTS["min_candles_after_signal"]))

    @min_candles_after_signal.setter
    def min_candles_after_signal(self, v: int):
        self.data["min_candles_after_signal"] = max(0, int(v))

    @property
    def min_candles_default(self) -> int:
        return int(self.data.get("min_candles_default", self.DEFAULTS["min_candles_default"]))

    @min_candles_default.setter
    def min_candles_default(self, v: int):
        self.data["min_candles_default"] = max(0, int(v))

    @property
    def same_direction_only(self) -> bool:
        return bool(self.data.get("same_direction_only", self.DEFAULTS["same_direction_only"]))

    @same_direction_only.setter
    def same_direction_only(self, v: bool):
        self.data["same_direction_only"] = bool(v)

    @property
    def require_new_signal(self) -> bool:
        return bool(self.data.get("require_new_signal", self.DEFAULTS["require_new_signal"]))

    @require_new_signal.setter
    def require_new_signal(self, v: bool):
        self.data["require_new_signal"] = bool(v)

    @property
    def price_filter_enabled(self) -> bool:
        return bool(self.data.get("price_filter_enabled", self.DEFAULTS["price_filter_enabled"]))

    @price_filter_enabled.setter
    def price_filter_enabled(self, v: bool):
        self.data["price_filter_enabled"] = bool(v)

    @property
    def price_filter_pct(self) -> float:
        return float(self.data.get("price_filter_pct", self.DEFAULTS["price_filter_pct"]))

    @price_filter_pct.setter
    def price_filter_pct(self, v: float):
        self.data["price_filter_pct"] = max(0.0, float(v))

    @property
    def max_reentries_per_day(self) -> int:
        return int(self.data.get("max_reentries_per_day", self.DEFAULTS["max_reentries_per_day"]))

    @max_reentries_per_day.setter
    def max_reentries_per_day(self, v: int):
        self.data["max_reentries_per_day"] = max(0, int(v))