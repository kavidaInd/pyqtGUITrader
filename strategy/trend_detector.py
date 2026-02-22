from __future__ import annotations
import logging
import pandas as pd
import numpy as np
from Utils.Quants import Quants
from strategy.dynamic_signal_engine import DynamicSignalEngine

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
    if not result or not result.get("available"):
        logger.debug("[SignalEngine] No result / engine not available.")
        return

    lines = []
    signal_val = result.get("signal_value", "WAIT")
    lines.append(f"┌─ SIGNAL: {signal_val} " + "─" * max(0, 45 - len(signal_val)))

    # ── Indicator snapshot ────────────────────────────────────────────────────
    ind_vals = result.get("indicator_values", {})
    if ind_vals:
        lines.append("│ Indicator snapshot:")
        for key, val in ind_vals.items():
            last = f"{val['last']:.4f}" if val.get("last") is not None else "N/A "
            prev = f"{val['prev']:.4f}" if val.get("prev") is not None else "N/A "
            lines.append(f"│   {key:<40}  last={last}  prev={prev}")
        lines.append("│")

    # ── Per-group rule breakdown ──────────────────────────────────────────────
    rule_results = result.get("rule_results", {})
    fired = result.get("fired", {})

    for group, rules in rule_results.items():
        if not rules:
            continue
        logic = "AND"  # default; AND is the common path shown in logs
        group_fired = fired.get(group, False)
        status = "FIRED ✓" if group_fired else "MISS  ✗"
        lines.append(f"│ {group:<12} [{logic}] → {status}")

        # Find the AND-chain blocker (first False in AND mode)
        first_false_found = False
        for r in rules:
            res = r.get("result", False)
            lv = r.get("lhs_value")
            rv = r.get("rhs_value")
            detail = r.get("detail", "")
            rule_s = r.get("rule", "?")
            tick = "✓" if res else "✗"

            # Flag the first blocker in an AND chain
            blocker_note = ""
            if not res and not first_false_found and not group_fired:
                blocker_note = "  ← BLOCKER"
                first_false_found = True

            # Flag obvious self-compare bug: same lhs_value == rhs_value for < or > ops
            if lv is not None and rv is not None and lv == rv and "MACD < MACD" in rule_s:
                blocker_note = "  ← SELF-COMPARE BUG"

            lines.append(f"│   {tick}  {rule_s:<35}  {detail}{blocker_note}")

        lines.append("│")

    lines.append("└" + "─" * 52)
    logger.debug("\n".join(lines))


def to_native(value):
    """Convert numpy or pandas objects to native Python types and round floats."""
    if isinstance(value, (np.generic, float)):
        return round(value.item(), 2)
    elif isinstance(value, (int,)):
        return int(value)
    return value


def round_series(series):
    if isinstance(series, (float, int, np.float64, np.int64)):
        return round(series, 2)
    if isinstance(series, pd.Series):
        return series.round(2).tolist()
    return [round(x, 2) if x is not None else None for x in series]


class TrendDetector:
    def __init__(self, config: object, signal_engine: DynamicSignalEngine = None):
        self.config = config
        self.signal_engine = signal_engine
        self._last_cache = {}  # Store last indicator cache for debugging

    def set_signal_engine(self, signal_engine: DynamicSignalEngine):
        """Set or update the signal engine"""
        self.signal_engine = signal_engine

    def detect(self, df: pd.DataFrame, state: object, symbol: str) -> dict | None:
        try:
            if df is None or df.empty:
                logger.warning(f"Empty or None DataFrame for symbol {symbol}")
                return None

            required_cols = {'open', 'high', 'low', 'close', 'volume'}
            missing = required_cols - set(df.columns)
            if missing:
                logger.error(f"DataFrame for {symbol} missing required columns: {missing}")
                return None

            results = {
                'name': symbol,
                'close': round_series(df['close']),
                'open': round_series(df['open']),
                'high': round_series(df['high']),
                'low': round_series(df['low']),
                'volume': df['volume'].tolist() if 'volume' in df else [],
            }
            # Store timestamps so the chart can show real times (HH:MM)
            if "Time" in df.columns:
                results["timestamps"] = df["Time"].tolist()
            elif df.index.name == "Time" or hasattr(df.index, 'to_list'):
                try:
                    results["timestamps"] = df.index.to_list()
                except Exception:
                    pass

            # Evaluate dynamic signals if engine is available
            option_signal_result = None
            if self.signal_engine is not None:
                try:
                    option_signal_result = self.signal_engine.evaluate(df)
                    # ── Structured debug log ──────────────────────────────────
                    _debug_signal_result(option_signal_result)
                    # ─────────────────────────────────────────────────────────
                    if hasattr(self.signal_engine, '_last_cache'):
                        self._last_cache = self.signal_engine.last_cache
                except Exception as e:
                    logger.error(f"Error evaluating dynamic signals: {e}", exc_info=True)
                    option_signal_result = None

            # Add the signal result to the trend data
            results['option_signal'] = option_signal_result

            return results

        except Exception as e:
            logger.error(f"Trend detection error for {symbol}: {e}", exc_info=True)
            return None

    def get_indicator_cache(self) -> dict:
        """Return the last indicator cache for debugging"""
        return self._last_cache.copy() if self._last_cache else {}
