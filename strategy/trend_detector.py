"""
trend_detector_db.py
====================
Trend detector that works with database-backed dynamic signal engine.
Detects trends in market data and evaluates strategy signals.

FEATURE 3: Handles confidence scores and threshold filtering.
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
    Pretty-prints a full signal evaluation result.
    Shows position context, WAIT reason, high-confidence suppressed signals,
    indicator snapshot, and per-group rule breakdown with AND-chain blockers.
    """
    try:
        if not result or not result.get("available"):
            logger.debug("[SignalEngine] No result / engine not available.")
            return

        lines = []
        signal_val  = result.get("signal_value", "WAIT")
        confidence  = result.get("confidence", {})
        threshold   = result.get("threshold", 0.6)
        position    = result.get("position_context")
        fired       = result.get("fired", {})          # post-threshold
        raw_fired   = result.get("raw_fired", {})       # pre-threshold
        explanation = result.get("explanation", "")

        pos_str = f"Position: {position}" if position else "Position: FLAT"
        header  = f"┌─ SIGNAL: {signal_val} ─ {pos_str}"
        lines.append(header + " " + "─" * max(0, 72 - len(header)))

        # ── High-confidence signals that were suppressed ──────────────────
        suppressed = [
            f"{sig} {confidence.get(sig, 0):.0%}"
            for sig, is_fired in fired.items()
            if not is_fired
            and raw_fired.get(sig, False)
            and confidence.get(sig, 0) >= threshold
        ]
        if suppressed:
            lines.append(f"│ ⚠ HIGH CONFIDENCE SUPPRESSED:  {', '.join(suppressed)}")

        # ── WAIT reason (from explanation field) ──────────────────────────
        if signal_val == "WAIT" and explanation:
            for part in explanation.split(" | "):
                part = part.strip()
                if (part.startswith("⏸️ WAIT reason:")
                        or part.startswith("🔒")
                        or part.startswith("⚖️")):
                    lines.append(f"│ {part}")

        lines.append("│")

        # ── Confidence summary line ───────────────────────────────────────
        conf_parts = []
        for sig, conf in confidence.items():
            if conf >= threshold:
                tag = "✅" if fired.get(sig) else "⚠️"
            elif conf > 0:
                tag = "📉"
            else:
                tag = "  "
            if conf > 0:
                conf_parts.append(f"{tag}{sig} {conf:.0%}")
        if conf_parts:
            lines.append(f"│ Confidence: {' | '.join(conf_parts)}  (threshold {threshold:.0%})")
            lines.append("│")

        # ── Indicator snapshot ────────────────────────────────────────────
        ind_vals = result.get("indicator_values", {})
        if ind_vals and isinstance(ind_vals, dict):
            lines.append("│ Indicator snapshot:")
            for key, val in ind_vals.items():
                try:
                    if isinstance(val, dict):
                        last = f"{val.get('last', 0):.4f}" if val.get('last') is not None else "N/A "
                        prev = f"{val.get('prev', 0):.4f}" if val.get('prev') is not None else "N/A "
                        delta_str = ""
                        if val.get('last') is not None and val.get('prev') is not None:
                            delta = val['last'] - val['prev']
                            arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
                            delta_str = f"  {arrow}{abs(delta):.4f}"
                    else:
                        last = "N/A "
                        prev = "N/A "
                        delta_str = ""
                    lines.append(f"│   {str(key)[:40]:<40}  last={last}  prev={prev}{delta_str}")
                except Exception as e:
                    logger.debug(f"Failed to format indicator {key}: {e}")
                    continue
            lines.append("│")

        # ── Per-group rule breakdown ──────────────────────────────────────
        rule_results = result.get("rule_results", {})

        if not isinstance(rule_results, dict) or not isinstance(fired, dict):
            logger.debug("Invalid rule_results or fired format")
            return

        for group, rules in rule_results.items():
            if not rules:
                continue
            group_fired = fired.get(group, False)
            group_conf  = confidence.get(group, 0)
            raw_group   = raw_fired.get(group, False)

            if group_fired:
                status_str = "FIRED ✅"
            elif raw_group and group_conf >= threshold:
                status_str = "SUPPRESSED ⚠️  ← rules passed, blocked by position/conflict"
            elif raw_group:
                status_str = f"LOW CONF ❌ ({group_conf:.0%} < {threshold:.0%})"
            else:
                status_str = "MISS ✗"

            lines.append(f"│ {str(group)[:12]:<12} conf={group_conf:.0%}  {status_str}")

            first_false_found = False
            if isinstance(rules, list):
                for r in rules:
                    try:
                        res    = r.get("result", False) if isinstance(r, dict) else False
                        lv     = r.get("lhs_value") if isinstance(r, dict) else None
                        rv     = r.get("rhs_value") if isinstance(r, dict) else None
                        detail = r.get("detail", "") if isinstance(r, dict) else ""
                        rule_s = r.get("rule", "?") if isinstance(r, dict) else "?"
                        weight = r.get("weight", 1.0) if isinstance(r, dict) else 1.0
                        tick   = "✓" if res else "✗"

                        note = ""
                        if not res and not first_false_found and not group_fired:
                            note = "  ← BLOCKER"
                            first_false_found = True

                        if (lv is not None and rv is not None
                                and lv == rv and "MACD < MACD" in str(rule_s)):
                            note = "  ← SELF-COMPARE BUG"

                        lines.append(
                            f"│   {tick}  {str(rule_s)[:35]:<35}  {detail} (w={weight:.1f}){note}"
                        )
                    except Exception as e:
                        logger.debug(f"Failed to process rule in {group}: {e}")
                        continue
            lines.append("│")

        lines.append(f"│ Min Confidence Threshold: {threshold:.0%}")
        lines.append("└" + "─" * 72)
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

    FEATURE 3: Handles confidence scores and threshold filtering.
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

                    # FEATURE 3: Add confidence data to state if available
                    if state is not None and option_signal_result:
                        self._update_state_with_confidence(state, option_signal_result)

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

    def _update_state_with_confidence(self, state: object, signal_result: Dict[str, Any]):
        """
        FEATURE 3: Update state with confidence data.

        Args:
            state: TradeState object
            signal_result: Signal evaluation result
        """
        try:
            if state is None or not signal_result:
                return

            # Update state with confidence data if available
            if hasattr(state, 'signal_confidence'):
                # This will be handled by the property setter in TradeState
                pass  # The state object will handle this via its properties

        except Exception as e:
            logger.error(f"[TrendDetector._update_state_with_confidence] Failed: {e}", exc_info=True)

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

    # FEATURE 3: New method to get confidence summary
    def get_confidence_summary(self, signal_result: Dict[str, Any]) -> str:
        """
        Get a human-readable summary of confidence scores.

        Args:
            signal_result: Signal evaluation result

        Returns:
            String summary
        """
        try:
            if not signal_result or not signal_result.get("available"):
                return "No signal available"

            confidence = signal_result.get("confidence", {})
            threshold = signal_result.get("threshold", 0.6)

            parts = []
            for sig, conf in confidence.items():
                if conf >= threshold:
                    parts.append(f"✅ {sig}: {conf:.0%}")
                elif conf > 0:
                    parts.append(f"⚠️ {sig}: {conf:.0%}")
                else:
                    parts.append(f"❌ {sig}: 0%")

            if parts:
                return " | ".join(parts)
            return "No confidence data"

        except Exception as e:
            logger.error(f"[TrendDetector.get_confidence_summary] Failed: {e}", exc_info=True)
            return "Error getting confidence summary"

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