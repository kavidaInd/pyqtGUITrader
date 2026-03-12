"""
backtest/backtest_candle_debugger.py
=====================================
Per-candle debug data collector for the BacktestEngine.

Changes from original:
- _build_entry: split into focused helpers (_build_spot, _build_option_block,
  _build_indicators, _build_signal_groups, _build_position, _build_tpsl)
  so each is independently testable and easier to follow.
- Cap enforcement changed from slicing to collections.deque(maxlen=) so the
  O(n) list-copy on every append is gone.
- load_from_json: "candles" key lookup now accepts both the wrapped format
  {meta, candles:[...]} and the raw list format in one clean branch.
- _json_default: checks for Enum via isinstance(obj, Enum) instead of
  hasattr(obj, 'value') which matched too many non-Enum objects.
- _dt_str: consolidated tz-aware / tz-naive paths into one format string.
- _r: early return for int avoids needless float() round-trip.
- record(): guard moved before the try-block so debug_mode=False exits
  with zero overhead (no exception machinery overhead).
- Removed dead `import BaseEnums` inside _build_entry — moved to module level
  with a lazy fallback so the circular-import risk is handled cleanly.
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from datetime import datetime
from Utils.time_utils import IST, ist_now, fmt_display, fmt_stamp
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

import pandas as pd

from Utils.safe_getattr import safe_getattr, safe_hasattr

logger = logging.getLogger(__name__)

# Lazy import so circular-import between backtest ↔ BaseEnums can't occur at
# module load time; resolved once on first candle record.
_BaseEnums = None

def _get_base_enums():
    global _BaseEnums
    if _BaseEnums is None:
        try:
            import BaseEnums as _be
            _BaseEnums = _be
        except ImportError:
            pass
    return _BaseEnums


class CandleDebugger:
    """
    Collects per-candle evaluation data during a backtest replay.

    Zero overhead when disabled (debug_mode=False): record() returns
    immediately before any allocation.
    """

    def __init__(self, debug_mode: bool = True, max_candles: int = 50_000):
        """
        Parameters
        ----------
        debug_mode  : If False, all calls are no-ops.
        max_candles : OOM safety cap.  Oldest entries are evicted when full.
        """
        self.debug_mode = debug_mode
        self.max_candles = max_candles
        # deque(maxlen) enforces the cap with O(1) appends, no slicing needed
        self._entries: Deque[Dict[str, Any]] = deque(maxlen=max_candles)
        self._bar_index = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def record(
        self,
        *,
        bar_time: datetime,
        o: float,
        h: float,
        l: float,
        c: float,
        sig_result: Optional[Dict],
        action: str,
        state,
        bars_in_trade: int,
        trailing_sl_high: Optional[float],
        skip_reason: Optional[str] = None,
        option_bar: Optional[Dict] = None,
        tp_sl_info: Optional[Dict] = None,
    ) -> None:
        """Record one candle's worth of debug data."""
        # Guard BEFORE try so debug_mode=False is truly zero-cost
        if not self.debug_mode:
            return

        try:
            entry = self._build_entry(
                bar_time=bar_time, o=o, h=h, l=l, c=c,
                sig_result=sig_result, action=action, state=state,
                bars_in_trade=bars_in_trade, trailing_sl_high=trailing_sl_high,
                skip_reason=skip_reason, option_bar=option_bar, tp_sl_info=tp_sl_info,
            )
            self._entries.append(entry)
            self._bar_index += 1
        except Exception as exc:
            logger.debug("[CandleDebugger.record] skipped: %s", exc)

    def save(self, path: str) -> bool:
        """Persist all recorded entries as a JSON file. Returns True on success."""
        if not self.debug_mode:
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            entries = list(self._entries)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "meta": {
                            "total_candles": len(entries),
                            "generated_at": ist_now().isoformat(timespec="seconds"),
                        },
                        "candles": entries,
                    },
                    f,
                    indent=2,
                    default=_json_default,
                )
            logger.info("[CandleDebugger] Saved %d records → %s", len(entries), path)
            return True
        except Exception as exc:
            logger.error("[CandleDebugger.save] Failed to write %s: %s", path, exc, exc_info=True)
            return False

    def get_entries(self) -> List[Dict]:
        """Return a list copy of all recorded entries."""
        return list(self._entries)

    @classmethod
    def load_from_json(cls, path: str) -> "CandleDebugger":
        """
        Load a previously saved JSON debug file into a new CandleDebugger.
        Accepts both the wrapped {meta, candles:[...]} format and a raw list.
        """
        obj = cls(debug_mode=True)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            candles = (
                data.get("candles", []) if isinstance(data, dict) else data
            )
            if isinstance(candles, list):
                obj._entries = deque(candles, maxlen=obj.max_candles)
                obj._bar_index = len(obj._entries)
            logger.info("[CandleDebugger] Loaded %d records from %s", len(obj._entries), path)
        except Exception as exc:
            logger.error("[CandleDebugger.load_from_json] %s: %s", path, exc, exc_info=True)
        return obj

    def clear(self) -> None:
        """Reset all recorded data."""
        self._entries.clear()
        self._bar_index = 0

    def __len__(self) -> int:
        return len(self._entries)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_entry(
        self,
        *,
        bar_time: datetime,
        o: float, h: float, l: float, c: float,
        sig_result: Optional[Dict],
        action: str,
        state,
        bars_in_trade: int,
        trailing_sl_high: Optional[float],
        skip_reason: Optional[str],
        option_bar: Optional[Dict],
        tp_sl_info: Optional[Dict],
    ) -> Dict[str, Any]:
        resolved, bt_override, explanation = _extract_signal_meta(sig_result)
        return {
            "bar_index":       self._bar_index,
            "time":            _dt_str(bar_time),
            "spot":            {"open": _r(o), "high": _r(h), "low": _r(l), "close": _r(c)},
            "option":          _build_option_block(option_bar),
            "indicators":      _build_indicators(sig_result),
            "signal_groups":   _build_signal_groups(sig_result),
            "resolved_signal": resolved,
            "bt_override":     bt_override,
            "explanation":     explanation,
            "action":          action,
            "position":        _build_position(state, bars_in_trade, trailing_sl_high),
            "skip_reason":     skip_reason,
            "tp_sl":           _build_tpsl(tp_sl_info),
        }


# ── Module-level helpers ───────────────────────────────────────────────────────

def _extract_signal_meta(sig_result: Optional[Dict]):
    if not sig_result:
        return "WAIT", "", ""
    return (
        sig_result.get("signal_value", "WAIT"),
        sig_result.get("_bt_override", ""),
        sig_result.get("explanation", ""),
    )


def _build_option_block(option_bar: Optional[Dict]) -> Optional[Dict]:
    if not option_bar:
        return None
    src = option_bar.get("source", "UNKNOWN")
    return {
        "symbol":       option_bar.get("symbol", ""),
        "open":         _r(option_bar.get("open")),
        "high":         _r(option_bar.get("high")),
        "low":          _r(option_bar.get("low")),
        "close":        _r(option_bar.get("close")),
        "price_source": src.value if isinstance(src, Enum) else str(src),
    }


def _build_indicators(sig_result: Optional[Dict]) -> Dict[str, Any]:
    if not sig_result:
        return {}
    indicators: Dict[str, Any] = {}
    for key, vals in sig_result.get("indicator_values", {}).items():
        if isinstance(vals, dict):
            indicators[key] = {"last": _r(vals.get("last")), "prev": _r(vals.get("prev"))}
        else:
            indicators[key] = _r(vals)
    return indicators


def _build_signal_groups(sig_result: Optional[Dict]) -> Dict[str, Any]:
    if not sig_result or not sig_result.get("available", False):
        return {}

    fired_map      = sig_result.get("fired", {})
    confidence_map = sig_result.get("confidence", {})
    rule_results   = sig_result.get("rule_results", {})
    threshold      = sig_result.get("threshold", 0.6)
    groups: Dict[str, Any] = {}

    for grp in ("BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"):
        grp_rules = rule_results.get(grp, [])
        if not grp_rules:
            continue
        rules_list = [
            {
                "index":     idx,
                "rule":      rr.get("rule", "?"),
                "passed":    bool(rr.get("result", False)),
                "weight":    _r(rr.get("weight", 1.0)),
                "lhs":       _r(rr.get("lhs_value")),
                "rhs":       _r(rr.get("rhs_value")),
                "lhs_shift": rr.get("lhs_shift", 0),
                "rhs_shift": rr.get("rhs_shift", 0),
                "detail":    rr.get("detail", ""),
                "error":     rr.get("error") or None,
            }
            for idx, rr in enumerate(grp_rules)
        ]
        groups[grp] = {
            "confidence": round(float(confidence_map.get(grp, 0.0)), 4),
            "threshold":  round(float(threshold), 4),
            "fired":      bool(fired_map.get(grp, False)),
            "rules":      rules_list,
        }
    return groups


def _build_position(state, bars_in_trade: int, trailing_sl_high: Optional[float]) -> Dict:
    be = _get_base_enums()
    cur = safe_getattr(state, "current_position", None)
    if be is not None:
        cur_str = "CALL" if cur == be.CALL else ("PUT" if cur == be.PUT else None)
    else:
        cur_str = str(cur) if cur is not None else None

    return {
        "current":       cur_str,
        "entry_time":    _dt_str(safe_getattr(state, "_bt_entry_time", None)),
        "entry_spot":    _r(safe_getattr(state, "_bt_spot_entry", None)),
        "entry_option":  _r(safe_getattr(state, "_bt_entry_price", None)),
        "strike":        safe_getattr(state, "_bt_strike", None),
        "bars_in_trade": bars_in_trade,
        "buy_price":     _r(safe_getattr(state, "current_buy_price", None)),
        "trailing_high": _r(trailing_sl_high),
    }


def _build_tpsl(tp_sl_info: Optional[Dict]) -> Dict:
    block: Dict[str, Any] = {
        "tp_price": None, "sl_price": None,
        "trailing_sl_price": None, "index_sl_level": None,
        "current_option_price": None,
        "tp_hit": False, "sl_hit": False,
        "trailing_sl_hit": False, "index_sl_hit": False,
    }
    if tp_sl_info:
        for k, v in tp_sl_info.items():
            block[k] = _r(v) if isinstance(v, (float, int)) and not isinstance(v, bool) else v
    return block


# ── Serialisation helpers ──────────────────────────────────────────────────────

def _r(v) -> Optional[float]:
    """Round a value to 4 decimal places; return None for non-numeric."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return float(v)
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def _dt_str(dt) -> Optional[str]:
    """Convert datetime to ISO-ish string, preserving tz offset if present."""
    if dt is None:
        return None
    try:
        fmt = "%Y-%m-%d %H:%M:%S%z" if (safe_hasattr(dt, "tzinfo") and dt.tzinfo) else "%Y-%m-%d %H:%M:%S"
        return dt.strftime(fmt)
    except Exception:
        return str(dt)


def _json_default(obj: Any) -> Any:
    """JSON serialiser fallback for non-standard types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (pd.Series, pd.DataFrame)):
        return obj.to_dict()
    return str(obj)