"""
trend_detector_db.py
====================
Trend detector that works with database-backed dynamic signal engine.
Detects trends in market data and evaluates strategy signals.
"""

from __future__ import annotations
import logging.handlers
from typing import Dict, List, Optional, Any, Union
import pandas as pd
import numpy as np

from strategy.dynamic_signal_engine import DynamicSignalEngine

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


# ── Debug helper ──────────────────────────────────────────────────────────────

def _debug_signal_result(result: dict):
    """
    Pretty-prints a full signal evaluation result with actual indicator values.
    Replaces the old raw print(option_signal_result).

    Output example:
    ┌─ SIGNAL: WAIT ──────────────────────────────────────
    │ Indicator snapshot:
    │   rsi_{"length":14}        last=47.2300  prev=46.8100
    │   macd_{"fast":12,...}     last=-0.3100  prev=-0.2900
    │   ema_{"length":20}        last=244.8000 prev=244.5000
    │
    │ BUY_CALL  [AND] → MISS
    │   ✗  CLOSE > OPEN          47.2300 > 48.1000  → False
    │   ✓  CLOSE > EMA           247.300 > 244.800  → True
    │   ✗  RSI > 50.0            47.2300 > 50.0000  → False  ← BLOCKER
    │
    │ BUY_PUT   [AND] → MISS
    │   ✗  MACD < MACD           -0.3100 < -0.3100  → False  ← SELF-COMPARE BUG
    └─────────────────────────────────────────────────────
    """
    try:
        if not result or not result.get("available"):
            logger.debug("[SignalEngine] No result / engine not available.")
            return

        lines = []
        signal_val = result.get("signal_value", "WAIT")
        lines.append(f"┌─ SIGNAL: {signal_val} " + "─" * max(0, 45 - len(str(signal_val))))

        # ── Indicator snapshot ────────────────────────────────────────────────────
        ind_vals = result.get("indicator_values", {})
        if ind_vals and isinstance(ind_vals, dict):
            lines.append("│ Indicator snapshot:")
            for key, val in ind_vals.items():
                try:
                    if isinstance(val, dict):
                        last = f"{val.get('last', 0):.4f}" if val.get('last') is not None else "N/A "
                        prev = f"{val.get('prev', 0):.4f}" if val.get('prev') is not None else "N/A "
                    else:
                        last = "N/A "
                        prev = "N/A "
                    lines.append(f"│   {str(key)[:40]:<40}  last={last}  prev={prev}")
                except Exception as e:
                    logger.debug(f"Failed to format indicator {key}: {e}")
                    continue
            lines.append("│")

        # ── Per-group rule breakdown ──────────────────────────────────────────────
        rule_results = result.get("rule_results", {})
        fired = result.get("fired", {})

        if not isinstance(rule_results, dict) or not isinstance(fired, dict):
            logger.debug("Invalid rule_results or fired format")
            return

        for group, rules in rule_results.items():
            if not rules:
                continue
            logic = "AND"  # default; AND is the common path shown in logs
            group_fired = fired.get(group, False)
            status = "FIRED ✓" if group_fired else "MISS  ✗"
            lines.append(f"│ {str(group)[:12]:<12} [{logic}] → {status}")

            # Find the AND-chain blocker (first False in AND mode)
            first_false_found = False
            if isinstance(rules, list):
                for r in rules:
                    try:
                        res = r.get("result", False) if isinstance(r, dict) else False
                        lv = r.get("lhs_value") if isinstance(r, dict) else None
                        rv = r.get("rhs_value") if isinstance(r, dict) else None
                        detail = r.get("detail", "") if isinstance(r, dict) else ""
                        rule_s = r.get("rule", "?") if isinstance(r, dict) else "?"
                        tick = "✓" if res else "✗"

                        # Flag the first blocker in an AND chain
                        blocker_note = ""
                        if not res and not first_false_found and not group_fired:
                            blocker_note = "  ← BLOCKER"
                            first_false_found = True

                        # Flag obvious self-compare bug: same lhs_value == rhs_value for < or > ops
                        if lv is not None and rv is not None and lv == rv and "MACD < MACD" in str(rule_s):
                            blocker_note = "  ← SELF-COMPARE BUG"

                        lines.append(f"│   {tick}  {str(rule_s)[:35]:<35}  {detail}{blocker_note}")
                    except Exception as e:
                        logger.debug(f"Failed to process rule in {group}: {e}")
                        continue

            lines.append("│")

        lines.append("└" + "─" * 52)
        logger.debug("\n".join(lines))

    except Exception as e:
        logger.error(f"[_debug_signal_result] Failed: {e}", exc_info=True)


def to_native(value: Any) -> Any:
    """Convert numpy or pandas objects to native Python types and round floats."""
    try:
        if value is None:
            return None
        if isinstance(value, (np.generic, float, np.float64, np.float32)):
            try:
                return round(float(value), 2)
            except (ValueError, TypeError):
                return float(value) if value is not None else None
        elif isinstance(value, (int, np.integer)):
            return int(value)
        elif isinstance(value, (pd.Series, np.ndarray)):
            return str(value)  # Return string representation for complex types
        return value
    except Exception as e:
        logger.error(f"[to_native] Failed: {e}", exc_info=True)
        return value


def round_series(series: Any) -> List[Optional[float]]:
    """Round a series of numbers to 2 decimal places."""
    try:
        if series is None:
            return []

        if isinstance(series, (float, int, np.float64, np.int64)):
            try:
                return [round(float(series), 2)]
            except (ValueError, TypeError):
                return [None]

        if isinstance(series, pd.Series):
            try:
                return [round(float(x), 2) if x is not None and not pd.isna(x) else None for x in series]
            except Exception:
                return [str(x) if x is not None else None for x in series]

        if isinstance(series, (list, tuple)):
            result = []
            for x in series:
                try:
                    if x is not None and not (isinstance(x, float) and np.isnan(x)):
                        result.append(round(float(x), 2))
                    else:
                        result.append(None)
                except (ValueError, TypeError):
                    result.append(None)
            return result

        return []

    except Exception as e:
        logger.error(f"[round_series] Failed: {e}", exc_info=True)
        return []


class TrendDetector:
    """
    Trend detector that works with database-backed signal engine.
    Detects trends in market data and evaluates strategy signals.
    """

    def __init__(self, config: object, signal_engine: DynamicSignalEngine = None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            self.config = config
            self.signal_engine = signal_engine
            self._last_cache = {}  # Store last indicator cache for debugging

            logger.debug("TrendDetector (database) initialized")

        except Exception as e:
            logger.critical(f"[TrendDetector.__init__] Failed: {e}", exc_info=True)
            self.config = config
            self.signal_engine = signal_engine

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.config = None
        self.signal_engine = None
        self._last_cache = {}

    def set_signal_engine(self, signal_engine: DynamicSignalEngine):
        """Set or update the signal engine"""
        try:
            self.signal_engine = signal_engine
            logger.debug("Signal engine updated")
        except Exception as e:
            logger.error(f"[TrendDetector.set_signal_engine] Failed: {e}", exc_info=True)

    def detect(self, df: pd.DataFrame, state: object, symbol: str) -> Optional[Dict]:
        """Detect trends in the provided dataframe"""
        try:
            # Rule 6: Input validation
            if df is None:
                logger.warning(f"detect called with None DataFrame for symbol {symbol}")
                return None

            if df.empty:
                logger.warning(f"Empty DataFrame for symbol {symbol}")
                return None

            if not isinstance(df, pd.DataFrame):
                logger.error(f"df must be a DataFrame, got {type(df)} for symbol {symbol}")
                return None

            required_cols = {'open', 'high', 'low', 'close', 'volume'}
            missing = required_cols - set(df.columns)
            if missing:
                logger.error(f"DataFrame for {symbol} missing required columns: {missing}")
                return None

            # Build results dictionary
            results = {
                'name': str(symbol) if symbol else "Unknown",
                'close': round_series(df['close']),
                'open': round_series(df['open']),
                'high': round_series(df['high']),
                'low': round_series(df['low']),
                'volume': df['volume'].tolist() if 'volume' in df and not df['volume'].empty else [],
            }

            # Store timestamps so the chart can show real times (HH:MM)
            try:
                if "time" in df.columns and not df["time"].empty:
                    results["timestamps"] = df["time"].tolist()
                elif df.index.name == "time" or hasattr(df.index, 'to_list'):
                    try:
                        results["timestamps"] = df.index.to_list()
                    except Exception as e:
                        logger.debug(f"Failed to convert index to list: {e}")
            except Exception as e:
                logger.debug(f"Failed to process timestamps: {e}")

            # Evaluate dynamic signals if engine is available
            option_signal_result = None
            if self.signal_engine is not None:
                try:
                    option_signal_result = self.signal_engine.evaluate(df)
                    # ── Structured debug log ──────────────────────────────────
                    _debug_signal_result(option_signal_result)
                    # ─────────────────────────────────────────────────────────
                    if hasattr(self.signal_engine, '_last_cache'):
                        try:
                            cache = self.signal_engine.last_cache
                            if cache is not None:
                                self._last_cache = cache
                        except Exception as e:
                            logger.debug(f"Failed to get last_cache: {e}")

                except AttributeError as e:
                    logger.error(f"Signal engine missing expected method: {e}", exc_info=True)
                    option_signal_result = None
                except Exception as e:
                    logger.error(f"Error evaluating dynamic signals: {e}", exc_info=True)
                    option_signal_result = None

            # Add the signal result to the trend data
            results['option_signal'] = option_signal_result

            return results

        except Exception as e:
            logger.error(f"Trend detection error for {symbol}: {e}", exc_info=True)
            return None

    def get_indicator_cache(self) -> Dict:
        """Return the last indicator cache for debugging"""
        try:
            return self._last_cache.copy() if self._last_cache else {}
        except Exception as e:
            logger.error(f"[TrendDetector.get_indicator_cache] Failed: {e}", exc_info=True)
            return {}

    def get_active_strategy_info(self) -> Dict[str, Any]:
        """Get information about the currently active strategy"""
        try:
            if self.signal_engine is None:
                return {"active": False, "message": "No signal engine configured"}

            # Get strategy slug from engine if available
            slug = getattr(self.signal_engine, 'strategy_slug', None)
            if slug:
                return {
                    "active": True,
                    "slug": slug,
                    "message": f"Using strategy: {slug}"
                }
            else:
                return {
                    "active": True,
                    "slug": None,
                    "message": "Using default strategy configuration"
                }
        except Exception as e:
            logger.error(f"[TrendDetector.get_active_strategy_info] Failed: {e}", exc_info=True)
            return {"active": False, "message": f"Error: {e}"}

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown."""
        try:
            logger.info("[TrendDetector] Starting cleanup")
            self._last_cache.clear()
            self.signal_engine = None
            self.config = None
            logger.info("[TrendDetector] Cleanup completed")
        except Exception as e:
            logger.error(f"[TrendDetector.cleanup] Error: {e}", exc_info=True)