"""
backtest/backtest_candle_debugger.py
=====================================
Per-candle debug data collector for the BacktestEngine.

Usage
-----
1.  Instantiate CandleDebugger at the start of a backtest replay.
2.  Call  debugger.record(...)  once per bar inside _replay().
3.  Call  debugger.save(path)   after replay finishes.
4.  Open the resulting JSON in any viewer, or load it in the
    BacktestWindow debug tab (see BacktestCandleDebugWidget).

The JSON schema is intentionally flat so it can be pasted into
any JSON viewer or imported into Excel / Pandas for analysis.

Schema (per entry)
------------------
{
  "bar_index"     : int,
  "time"          : "2024-01-15 09:25:00",   // ISO-ish string
  "spot": {
    "open": 21500.0, "high": 21520.0,
    "low": 21490.0,  "close": 21505.0
  },
  "option": {                                 // null when no position
    "symbol": "NIFTY21500CE",
    "open": 180.0, "high": 185.0,
    "low": 178.0,  "close": 182.0,
    "price_source": "REAL"                    // "REAL" | "SYNTHETIC"
  },
  "indicators": {                             // flat key → value map
    "RSI_14": 54.32,
    "EMA_20": 21480.5,
    "MACD_12_26_9": 12.3,
    ...
  },
  "signal_groups": {                          // one entry per group
    "BUY_CALL": {
      "confidence": 0.67,
      "threshold":  0.60,
      "fired":      true,
      "rules": [
        {
          "index":   0,
          "rule":    "RSI_14 > 50",
          "passed":  true,
          "weight":  1.0,
          "lhs":     54.32,
          "rhs":     50.0,
          "detail":  "54.3200 > 50.0000",
          "error":   null
        },
        ...
      ]
    },
    ...
  },
  "resolved_signal" : "BUY_CALL",
  "bt_override"     : "flat:exit→BUY_CALL(conf=67%)",   // "" when none
  "explanation"     : "BUY_CALL fired with 67% confidence",
  "action"          : "BUY_CALL",                        // what engine did
  "position": {
    "current"       : null,                              // "CALL"|"PUT"|null
    "entry_time"    : null,
    "entry_spot"    : null,
    "entry_option"  : null,
    "strike"        : null,
    "bars_in_trade" : 0,
    "buy_price"     : null,
    "trailing_high" : null
  },
  "skip_reason"     : null,     // "SIDEWAY"|"MARKET_CLOSED"|"WARMUP"|null
  "tp_sl": {
    "tp_price"           : null,
    "sl_price"           : null,
    "trailing_sl_price"  : null,
    "index_sl_level"     : null,
    "current_option_price": null,
    "tp_hit"             : false,
    "sl_hit"             : false,
    "trailing_sl_hit"    : false,
    "index_sl_hit"       : false
  }
}
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


class CandleDebugger:
    """
    Collects per-candle evaluation data during a backtest replay.

    Designed for zero-impact when disabled (debug_mode=False):
    all record() calls return immediately without allocating anything.
    """

    def __init__(self, debug_mode: bool = True, max_candles: int = 50_000):
        """
        Parameters
        ----------
        debug_mode  : If False, all calls are no-ops (zero overhead).
        max_candles : Safety cap — prevents OOM on very long backtests.
                      Oldest entries are dropped once the cap is reached.
        """
        self.debug_mode = debug_mode
        self.max_candles = max_candles
        self._entries: List[Dict[str, Any]] = []
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
        state,                          # TradeState
        bars_in_trade: int,
        trailing_sl_high: Optional[float],
        skip_reason: Optional[str] = None,
        option_bar: Optional[Dict] = None,   # resolved option bar for this candle
        tp_sl_info: Optional[Dict] = None,   # TP/SL check results
    ) -> None:
        """Record one candle's worth of debug data."""
        if not self.debug_mode:
            return

        try:
            entry = self._build_entry(
                bar_time=bar_time,
                o=o, h=h, l=l, c=c,
                sig_result=sig_result,
                action=action,
                state=state,
                bars_in_trade=bars_in_trade,
                trailing_sl_high=trailing_sl_high,
                skip_reason=skip_reason,
                option_bar=option_bar,
                tp_sl_info=tp_sl_info,
            )

            if len(self._entries) >= self.max_candles:
                self._entries = self._entries[-(self.max_candles - 1):]

            self._entries.append(entry)
            self._bar_index += 1

        except Exception as e:
            logger.debug(f"[CandleDebugger.record] skipped due to error: {e}")

    def save(self, path: str) -> bool:
        """
        Save all recorded entries as a JSON file.

        Returns True on success, False on failure.
        """
        if not self.debug_mode:
            return False

        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "meta": {
                            "total_candles": len(self._entries),
                            "generated_at": datetime.now().isoformat(timespec="seconds"),
                        },
                        "candles": self._entries,
                    },
                    f,
                    indent=2,
                    default=_json_default,
                )
            logger.info(f"[CandleDebugger] Saved {len(self._entries)} candle records → {path}")
            return True

        except Exception as e:
            logger.error(f"[CandleDebugger.save] Failed to write {path}: {e}", exc_info=True)
            return False

    def get_entries(self) -> List[Dict]:
        """Return a shallow copy of all recorded entries (for in-memory use)."""
        return list(self._entries)

    @classmethod
    def load_from_json(cls, path: str) -> "CandleDebugger":
        """
        Load a previously saved JSON debug file into a new CandleDebugger instance.
        Useful for loading old backtest files into the new CandleDebugTab UI.

        Returns a CandleDebugger whose get_entries() can be fed straight into
        CandleDebugTab.load().
        """
        obj = cls(debug_mode=True)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            candles = data.get("candles", data) if isinstance(data, dict) else data
            obj._entries = candles if isinstance(candles, list) else []
            obj._bar_index = len(obj._entries)
            logger.info(f"[CandleDebugger] Loaded {len(obj._entries)} records from {path}")
        except Exception as e:
            logger.error(f"[CandleDebugger.load_from_json] Failed to load {path}: {e}", exc_info=True)
        return obj

    def clear(self):
        """Reset all recorded data."""
        self._entries.clear()
        self._bar_index = 0

    def __len__(self):
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
        """Build the per-candle dict from all available context."""

        # ── Spot OHLC ─────────────────────────────────────────────────────────
        spot = {"open": _r(o), "high": _r(h), "low": _r(l), "close": _r(c)}

        # ── Option bar ────────────────────────────────────────────────────────
        opt_block = None
        if option_bar:
            opt_block = {
                "symbol":       option_bar.get("symbol", ""),
                "open":         _r(option_bar.get("open")),
                "high":         _r(option_bar.get("high")),
                "low":          _r(option_bar.get("low")),
                "close":        _r(option_bar.get("close")),
                "price_source": str(option_bar.get("source", "UNKNOWN")),
            }

        # ── Indicators ───────────────────────────────────────────────────────
        indicators: Dict[str, Any] = {}
        if sig_result:
            raw_ind = sig_result.get("indicator_values", {})
            for key, vals in raw_ind.items():
                if isinstance(vals, dict):
                    last = vals.get("last")
                    prev = vals.get("prev")
                    indicators[key] = {
                        "last": _r(last),
                        "prev": _r(prev),
                    }
                else:
                    indicators[key] = _r(vals)

        # ── Signal groups ─────────────────────────────────────────────────────
        signal_groups: Dict[str, Any] = {}
        if sig_result and sig_result.get("available", False):
            fired_map      = sig_result.get("fired", {})
            confidence_map = sig_result.get("confidence", {})
            rule_results   = sig_result.get("rule_results", {})
            threshold      = sig_result.get("threshold", 0.6)

            for grp in ("BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"):
                grp_rules = rule_results.get(grp, [])
                if not grp_rules:
                    continue

                rules_list = []
                for idx, rr in enumerate(grp_rules):
                    lhs = rr.get("lhs_value")
                    rhs = rr.get("rhs_value")
                    # Extract shift values if available
                    lhs_shift = rr.get("lhs_shift", 0)
                    rhs_shift = rr.get("rhs_shift", 0)

                    rules_list.append({
                        "index":  idx,
                        "rule":   rr.get("rule", "?"),
                        "passed": bool(rr.get("result", False)),
                        "weight": _r(rr.get("weight", 1.0)),
                        "lhs":    _r(lhs),
                        "rhs":    _r(rhs),
                        "lhs_shift": lhs_shift,
                        "rhs_shift": rhs_shift,
                        "detail": rr.get("detail", ""),
                        "error":  rr.get("error") or None,
                    })

                signal_groups[grp] = {
                    "confidence": round(float(confidence_map.get(grp, 0.0)), 4),
                    "threshold":  round(float(threshold), 4),
                    "fired":      bool(fired_map.get(grp, False)),
                    "rules":      rules_list,
                }

        # ── Position context ──────────────────────────────────────────────────
        import BaseEnums  # noqa: F401 — import inside function to avoid circular imports at module level
        _cur = getattr(state, "current_position", None)
        if _cur == BaseEnums.CALL:
            cur_str = "CALL"
        elif _cur == BaseEnums.PUT:
            cur_str = "PUT"
        else:
            cur_str = None

        position = {
            "current":       cur_str,
            "entry_time":    _dt_str(getattr(state, "_bt_entry_time", None)),
            "entry_spot":    _r(getattr(state, "_bt_spot_entry", None)),
            "entry_option":  _r(getattr(state, "_bt_entry_price", None)),
            "strike":        getattr(state, "_bt_strike", None),
            "bars_in_trade": bars_in_trade,
            "buy_price":     _r(getattr(state, "current_buy_price", None)),
            "trailing_high": _r(trailing_sl_high),
        }

        # ── TP/SL info ────────────────────────────────────────────────────────
        tp_sl_block = {
            "tp_price":             None,
            "sl_price":             None,
            "trailing_sl_price":    None,
            "index_sl_level":       None,
            "current_option_price": None,
            "tp_hit":               False,
            "sl_hit":               False,
            "trailing_sl_hit":      False,
            "index_sl_hit":         False,
        }
        if tp_sl_info:
            tp_sl_block.update({k: _r(v) if isinstance(v, float) else v
                                 for k, v in tp_sl_info.items()})

        # ── Resolved signal ───────────────────────────────────────────────────
        resolved = "WAIT"
        bt_override = ""
        explanation = ""
        if sig_result:
            resolved    = sig_result.get("signal_value", "WAIT")
            bt_override = sig_result.get("_bt_override", "")
            explanation = sig_result.get("explanation", "")

        return {
            "bar_index":        self._bar_index,
            "time":             _dt_str(bar_time),
            "spot":             spot,
            "option":           opt_block,
            "indicators":       indicators,
            "signal_groups":    signal_groups,
            "resolved_signal":  resolved,
            "bt_override":      bt_override,
            "explanation":      explanation,
            "action":           action,
            "position":         position,
            "skip_reason":      skip_reason,
            "tp_sl":            tp_sl_block,
        }


# ── Utility helpers ────────────────────────────────────────────────────────────

def _r(v) -> Optional[float]:
    """Round a float to 4 decimals; return None for non-numeric."""
    if v is None:
        return None
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def _dt_str(dt) -> Optional[str]:
    """Convert datetime to string, preserving timezone if present."""
    if dt is None:
        return None
    try:
        # If datetime is timezone-aware, keep the timezone info in the string
        if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
            # Format with timezone offset
            return dt.strftime("%Y-%m-%d %H:%M:%S%z")
        else:
            # Naive datetime
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt)


def _json_default(obj):
    """
    JSON serializer fallback for non-standard types.
    FIX #3: Enhanced to handle Enums, pandas objects, and more types.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()

    # Handle Enum types (like PriceSource)
    if hasattr(obj, 'value'):
        return obj.value

    # Handle pandas Series/DataFrame
    if isinstance(obj, (pd.Series, pd.DataFrame)):
        return obj.to_dict()

    # Handle custom objects with __dict__
    if hasattr(obj, '__dict__'):
        return str(obj)

    try:
        return str(obj)
    except Exception:
        return None