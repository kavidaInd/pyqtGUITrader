"""
dynamic_signal_engine_db.py
============================
Database-backed DynamicSignalEngine for option trading that works with StrategyManager.
Signals: BUY_CALL, BUY_PUT, EXIT_CALL, EXIT_PUT, HOLD, WAIT
"""

from __future__ import annotations
import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

try:
    import pandas_ta as ta
    _TA_AVAILABLE = True
except ImportError:
    ta = None
    _TA_AVAILABLE = False
    logger.warning("pandas_ta not installed — pip install pandas_ta")


class OptionSignal(str, Enum):
    BUY_CALL = "BUY_CALL"
    BUY_PUT = "BUY_PUT"
    EXIT_CALL = "EXIT_CALL"
    EXIT_PUT = "EXIT_PUT"
    HOLD = "HOLD"
    WAIT = "WAIT"

    @classmethod
    def _missing_(cls, value):
        """Handle missing enum values gracefully."""
        try:
            logger.warning(f"Unknown OptionSignal value: {value}, defaulting to WAIT")
            return cls.WAIT
        except Exception as e:
            logger.error(f"[OptionSignal._missing_] Failed: {e}", exc_info=True)
            return cls.WAIT


SIGNAL_GROUPS = [OptionSignal.BUY_CALL, OptionSignal.BUY_PUT,
                 OptionSignal.EXIT_CALL, OptionSignal.EXIT_PUT,
                 OptionSignal.HOLD]

SIGNAL_LABELS: Dict[str, str] = {
    "BUY_CALL": "📈  Buy Call", "BUY_PUT": "📉  Buy Put",
    "EXIT_CALL": "🔴  Exit Call", "EXIT_PUT": "🔵  Exit Put", "HOLD": "⏸   Hold",
}
SIGNAL_COLORS: Dict[str, str] = {
    "BUY_CALL": "#a6e3a1", "BUY_PUT": "#89b4fa", "EXIT_CALL": "#f38ba8",
    "EXIT_PUT": "#fab387", "HOLD": "#f9e2af", "WAIT": "#585b70",
}

OPERATORS = [">", "<", ">=", "<=", "==", "!=", "crosses_above", "crosses_below"]

INDICATOR_MAP: Dict[str, str] = {
    "rsi": "rsi", "ema": "ema", "sma": "sma", "wma": "wma", "macd": "macd", "bbands": "bbands",
    "atr": "atr", "adx": "adx", "cci": "cci", "stoch": "stoch", "roc": "roc", "mom": "mom",
    "willr": "willr", "obv": "obv", "vwap": "vwap", "supertrend": "supertrend", "kc": "kc",
    "donchian": "donchian", "psar": "psar", "tema": "tema", "dema": "dema", "hma": "hma",
    "zlma": "zlma", "slope": "slope", "linreg": "linreg",
}
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
INDICATOR_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "rsi": {"length": 14}, "ema": {"length": 20}, "sma": {"length": 20}, "wma": {"length": 20},
    "macd": {"fast": 12, "slow": 26, "signal": 9}, "bbands": {"length": 20, "std": 2.0},
    "atr": {"length": 14}, "adx": {"length": 14}, "cci": {"length": 20},
    "stoch": {"k": 14, "d": 3, "smooth_k": 3},
    "roc": {"length": 10}, "mom": {"length": 10}, "willr": {"length": 14}, "obv": {}, "vwap": {},
    "supertrend": {"length": 7, "multiplier": 3.0}, "kc": {"length": 20, "scalar": 1.5},
    "donchian": {"lower_length": 20, "upper_length": 20},
    "psar": {"af0": 0.02, "af": 0.02, "max_af": 0.2},
    "tema": {"length": 20}, "dema": {"length": 20}, "hma": {"length": 20}, "zlma": {"length": 20},
    "slope": {"length": 1}, "linreg": {"length": 14},
}
INDICATOR_COLUMN_HINTS: Dict[str, str] = {
    "macd": "MACD_12_26_9", "bbands": "BBM_20_2.0", "stoch": "STOCHk_14_3_3",
    "supertrend": "SUPERT_7_3.0", "kc": "KCBe_20_1.5", "donchian": "DCM_20_20", "adx": "ADX_14",
}


def _compute_indicator(df: pd.DataFrame, indicator: str, params: Dict[str, Any]) -> Optional[pd.Series]:
    """Compute indicator with error handling"""
    try:
        if ta is None:
            logger.warning("pandas_ta not available, cannot compute indicator")
            return None

        if df is None or df.empty:
            logger.warning(f"Cannot compute {indicator}: DataFrame is None or empty")
            return None

        ind_name = INDICATOR_MAP.get(indicator.lower(), indicator.lower())

        try:
            method = getattr(ta, ind_name, None)
            if not method:
                logger.warning(f"Indicator method '{ind_name}' not found in pandas_ta")
                return None

            # Prepare kwargs safely
            kwargs = {}
            for col in OHLCV_COLUMNS:
                if col in df.columns:
                    kwargs[col] = df[col]
                else:
                    kwargs[col] = None

            # Add parameters
            kwargs.update(params)

            # Remove None values
            kwargs = {k: v for k, v in kwargs.items() if v is not None}

            result = method(**kwargs)

            if result is None:
                return None

            if isinstance(result, pd.DataFrame):
                hint = INDICATOR_COLUMN_HINTS.get(indicator.lower())
                if hint and hint in result.columns:
                    return result[hint]
                for col in result.columns:
                    if ind_name.upper() in col.upper() or indicator.upper() in col.upper():
                        return result[col]
                if len(result.columns) > 0:
                    return result.iloc[:, 0]
                return None

            if isinstance(result, pd.Series):
                return result

            return None

        except AttributeError as e:
            logger.error(f"Attribute error computing '{indicator}': {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Error computing '{indicator}': {e}", exc_info=True)
            return None

    except Exception as e:
        logger.error(f"[_compute_indicator] Failed for {indicator}: {e}", exc_info=True)
        return None


def _resolve_side(df: pd.DataFrame, side_def: Dict[str, Any], cache: Dict[str, Any]) -> Optional[pd.Series]:
    """Resolve a side (LHS/RHS) to a pandas Series"""
    try:
        if df is None:
            logger.warning("_resolve_side called with None df")
            return None

        if side_def is None:
            logger.warning("_resolve_side called with None side_def")
            return None

        t = side_def.get("type", "indicator")

        if t == "scalar":
            try:
                value = float(side_def.get("value", 0))
                return pd.Series([value] * len(df), index=df.index)
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid scalar value: {e}")
                return None

        if t == "column":
            col = side_def.get("column", "close")
            if col in df.columns:
                return df[col].astype(float)
            logger.warning(f"Column '{col}' not found in DataFrame")
            return None

        # Indicator type
        indicator = side_def.get("indicator", "").lower()
        params = side_def.get("params", INDICATOR_DEFAULTS.get(indicator, {}))

        # Create cache key
        try:
            cache_key = f"{indicator}_{json.dumps(params, sort_keys=True)}"
        except Exception as e:
            logger.warning(f"Failed to create cache key: {e}")
            cache_key = f"{indicator}_{str(params)}"

        if cache_key not in cache:
            cache[cache_key] = _compute_indicator(df, indicator, params)

        return cache.get(cache_key)

    except Exception as e:
        logger.error(f"[_resolve_side] Failed: {e}", exc_info=True)
        return None


def _apply_operator(lhs: pd.Series, op: str, rhs: pd.Series) -> Tuple[bool, Optional[float], Optional[float]]:
    """Returns (result: bool, lhs_val: float|None, rhs_val: float|None)."""
    try:
        if lhs is None or rhs is None:
            logger.warning(f"Operator '{op}' called with None series")
            return False, None, None

        if op == "crosses_above":
            if len(lhs) < 2 or len(rhs) < 2:
                return False, None, None
            try:
                pl, cl = float(lhs.iloc[-2]), float(lhs.iloc[-1])
                pr, cr = float(rhs.iloc[-2]), float(rhs.iloc[-1])
                return (pl <= pr) and (cl > cr), round(cl, 6), round(cr, 6)
            except (ValueError, TypeError, IndexError) as e:
                logger.warning(f"Error in crosses_above: {e}")
                return False, None, None

        if op == "crosses_below":
            if len(lhs) < 2 or len(rhs) < 2:
                return False, None, None
            try:
                pl, cl = float(lhs.iloc[-2]), float(lhs.iloc[-1])
                pr, cr = float(rhs.iloc[-2]), float(rhs.iloc[-1])
                return (pl >= pr) and (cl < cr), round(cl, 6), round(cr, 6)
            except (ValueError, TypeError, IndexError) as e:
                logger.warning(f"Error in crosses_below: {e}")
                return False, None, None

        try:
            lv = float(lhs.iloc[-1])
            rv = float(rhs.iloc[-1])
        except (ValueError, TypeError, IndexError) as e:
            logger.warning(f"Failed to get last values: {e}")
            return False, None, None

        if np.isnan(lv) or np.isnan(rv):
            return False, None, None

        operators = {
            ">": lv > rv,
            "<": lv < rv,
            ">=": lv >= rv,
            "<=": lv <= rv,
            "==": abs(lv - rv) < 1e-9,
            "!=": abs(lv - rv) >= 1e-9
        }

        result = operators.get(op, False)
        return result, round(lv, 6), round(rv, 6)

    except Exception as e:
        logger.error(f"Operator error '{op}': {e}", exc_info=True)
        return False, None, None


def _rule_to_string(rule: Dict[str, Any]) -> str:
    """Convert rule dict to readable string"""
    try:
        if rule is None:
            return "Invalid rule"

        def s(d):
            if d is None:
                return "?"
            t = d.get("type", "indicator")
            if t == "scalar":
                return str(d.get("value", "?"))
            if t == "column":
                return d.get("column", "?").upper()
            ind = d.get("indicator", "?")
            p = ", ".join(f"{k}={v}" for k, v in d.get("params", {}).items())
            return f"{ind.upper()}({p})" if p else ind.upper()

        lhs = s(rule.get('lhs', {}))
        op = rule.get('op', '?')
        rhs = s(rule.get('rhs', {}))
        return f"{lhs} {op} {rhs}"

    except Exception as e:
        logger.error(f"[_rule_to_string] Failed: {e}", exc_info=True)
        return "Error parsing rule"


class DynamicSignalEngine:
    """
    Dynamic signal engine that uses strategy configuration from StrategyManager.
    Each instance is tied to a specific strategy slug.
    """

    DEFAULT_CONFIG: Dict[str, Any] = {
        sig.value: {"logic": "AND", "rules": [], "enabled": True} for sig in SIGNAL_GROUPS
    }

    def __init__(self, strategy_slug: Optional[str] = None, conflict_resolution: str = "WAIT"):
        """
        Initialize the signal engine.

        Args:
            strategy_slug: Slug of the strategy to use (None for defaults)
            conflict_resolution: How to resolve conflicts ("WAIT" or "PRIORITY")
        """
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            self._last_cache = None
            self.strategy_slug = strategy_slug
            self.conflict_resolution = conflict_resolution.upper()
            self.config = {k: {"logic": v["logic"], "rules": list(v["rules"]), "enabled": v["enabled"]}
                           for k, v in self.DEFAULT_CONFIG.items()}

            # Import here to avoid circular imports
            from strategy.strategy_manager import strategy_manager
            self._manager = strategy_manager

            if strategy_slug:
                self.load_from_strategy()
            else:
                logger.info("DynamicSignalEngine initialized with defaults (no strategy)")

        except Exception as e:
            logger.critical(f"[DynamicSignalEngine.__init__] Failed: {e}", exc_info=True)
            self.config = dict(self.DEFAULT_CONFIG)
            self.conflict_resolution = "WAIT"

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._last_cache = None
        self.strategy_slug = None
        self.conflict_resolution = "WAIT"
        self.config = {}
        self._manager = None

    def _key(self, signal: Union[str, OptionSignal]) -> str:
        """Get config key for signal"""
        try:
            if signal is None:
                return ""
            return signal.value if isinstance(signal, OptionSignal) else str(signal)
        except Exception as e:
            logger.error(f"[_key] Failed: {e}", exc_info=True)
            return ""

    def load_from_strategy(self, strategy_slug: Optional[str] = None) -> bool:
        """
        Load configuration from a strategy.

        Args:
            strategy_slug: Slug of the strategy (uses current if None)

        Returns:
            bool: True if load successful
        """
        try:
            slug = strategy_slug or self.strategy_slug
            if not slug or not self._manager:
                logger.warning("No strategy slug or manager available")
                return False

            strategy = self._manager.get(slug)
            if not strategy:
                logger.warning(f"Strategy not found: {slug}")
                return False

            engine_config = strategy.get("engine", {})
            if not engine_config:
                logger.info(f"No engine config found for strategy {slug}, using defaults")
                return False

            # Load signal configurations
            for sig in SIGNAL_GROUPS:
                k = sig.value
                if k in engine_config and isinstance(engine_config[k], dict):
                    try:
                        self.config[k]["logic"] = str(engine_config[k].get("logic", "AND")).upper()
                        rules = engine_config[k].get("rules", [])
                        self.config[k]["rules"] = list(rules) if isinstance(rules, list) else []
                        self.config[k]["enabled"] = bool(engine_config[k].get("enabled", True))
                    except Exception as e:
                        logger.warning(f"Failed to load config for {k}: {e}")

            # Load conflict resolution
            if "conflict_resolution" in engine_config:
                self.conflict_resolution = str(engine_config["conflict_resolution"]).upper()

            self.strategy_slug = slug
            logger.info(f"Dynamic signal config loaded from strategy: {slug}")
            return True

        except Exception as e:
            logger.error(f"Failed to load config from strategy: {e}", exc_info=True)
            return False

    def save_to_strategy(self, strategy_slug: Optional[str] = None) -> bool:
        """
        Save current configuration to a strategy.

        Args:
            strategy_slug: Slug of the strategy (uses current if None)

        Returns:
            bool: True if save successful
        """
        try:
            slug = strategy_slug or self.strategy_slug
            if not slug or not self._manager:
                logger.warning("No strategy slug or manager available")
                return False

            strategy = self._manager.get(slug)
            if not strategy:
                logger.warning(f"Strategy not found: {slug}")
                return False

            # Update engine config
            strategy["engine"] = self.to_dict()
            strategy["engine"]["conflict_resolution"] = self.conflict_resolution

            success = self._manager.save(slug, strategy)
            if success:
                logger.info(f"Dynamic signal config saved to strategy: {slug}")
            else:
                logger.error(f"Failed to save config to strategy: {slug}")

            return success

        except Exception as e:
            logger.error(f"Failed to save config to strategy: {e}", exc_info=True)
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary"""
        try:
            return {k: {"logic": v["logic"], "rules": list(v["rules"]), "enabled": v["enabled"]}
                    for k, v in self.config.items()}
        except Exception as e:
            logger.error(f"[to_dict] Failed: {e}", exc_info=True)
            return {}

    def from_dict(self, d: Dict[str, Any]) -> None:
        """Load config from dictionary"""
        try:
            if d is None:
                logger.warning("from_dict called with None")
                return

            if not isinstance(d, dict):
                logger.warning(f"from_dict expected dict, got {type(d)}")
                return

            for sig in SIGNAL_GROUPS:
                k = sig.value
                if k in d and isinstance(d[k], dict):
                    try:
                        self.config[k]["logic"] = str(d[k].get("logic", "AND")).upper()
                        rules = d[k].get("rules", [])
                        self.config[k]["rules"] = list(rules) if isinstance(rules, list) else []
                        self.config[k]["enabled"] = bool(d[k].get("enabled", True))
                    except Exception as e:
                        logger.warning(f"Failed to load config for {k}: {e}")

            if "conflict_resolution" in d:
                self.conflict_resolution = str(d["conflict_resolution"]).upper()

        except Exception as e:
            logger.error(f"[from_dict] Failed: {e}", exc_info=True)

    def add_rule(self, signal: Union[str, OptionSignal], rule: Dict[str, Any]) -> bool:
        """Add a rule to a signal group"""
        try:
            k = self._key(signal)
            if k not in self.config:
                logger.warning(f"Signal {k} not found in config")
                return False

            if rule is None:
                logger.warning("Cannot add None rule")
                return False

            self.config[k]["rules"].append(rule)
            logger.debug(f"Added rule to {k}")
            return True

        except Exception as e:
            logger.error(f"[add_rule] Failed for {signal}: {e}", exc_info=True)
            return False

    def remove_rule(self, signal: Union[str, OptionSignal], index: int) -> bool:
        """Remove a rule by index"""
        try:
            k = self._key(signal)
            rules = self.config.get(k, {}).get("rules", [])
            if 0 <= index < len(rules):
                rules.pop(index)
                logger.debug(f"Removed rule {index} from {k}")
                return True
            return False

        except Exception as e:
            logger.error(f"[remove_rule] Failed for {signal}: {e}", exc_info=True)
            return False

    def update_rule(self, signal: Union[str, OptionSignal], index: int, rule: Dict[str, Any]) -> bool:
        """Update a rule by index"""
        try:
            k = self._key(signal)
            rules = self.config.get(k, {}).get("rules", [])
            if 0 <= index < len(rules) and rule is not None:
                rules[index] = rule
                logger.debug(f"Updated rule {index} in {k}")
                return True
            return False

        except Exception as e:
            logger.error(f"[update_rule] Failed for {signal}: {e}", exc_info=True)
            return False

    def get_rules(self, signal: Union[str, OptionSignal]) -> List[Dict[str, Any]]:
        """Get all rules for a signal"""
        try:
            k = self._key(signal)
            return list(self.config.get(k, {}).get("rules", []))
        except Exception as e:
            logger.error(f"[get_rules] Failed for {signal}: {e}", exc_info=True)
            return []

    def set_logic(self, signal: Union[str, OptionSignal], logic: str) -> None:
        """Set logic (AND/OR) for a signal group"""
        try:
            k = self._key(signal)
            if k in self.config and logic.upper() in ("AND", "OR"):
                self.config[k]["logic"] = logic.upper()
                logger.debug(f"Set logic for {k} to {logic}")
        except Exception as e:
            logger.error(f"[set_logic] Failed for {signal}: {e}", exc_info=True)

    def get_logic(self, signal: Union[str, OptionSignal]) -> str:
        """Get logic for a signal group"""
        try:
            k = self._key(signal)
            return self.config.get(k, {}).get("logic", "AND")
        except Exception as e:
            logger.error(f"[get_logic] Failed for {signal}: {e}", exc_info=True)
            return "AND"

    def set_enabled(self, signal: Union[str, OptionSignal], enabled: bool) -> None:
        """Enable/disable a signal group"""
        try:
            k = self._key(signal)
            if k in self.config:
                self.config[k]["enabled"] = bool(enabled)
                logger.debug(f"Set enabled for {k} to {enabled}")
        except Exception as e:
            logger.error(f"[set_enabled] Failed for {signal}: {e}", exc_info=True)

    def is_enabled(self, signal: Union[str, OptionSignal]) -> bool:
        """Check if a signal group is enabled"""
        try:
            k = self._key(signal)
            return bool(self.config.get(k, {}).get("enabled", True))
        except Exception as e:
            logger.error(f"[is_enabled] Failed for {signal}: {e}", exc_info=True)
            return True

    def rule_descriptions(self, signal: Union[str, OptionSignal]) -> List[str]:
        """Get human-readable rule descriptions"""
        try:
            return [_rule_to_string(r) for r in self.get_rules(signal)]
        except Exception as e:
            logger.error(f"[rule_descriptions] Failed for {signal}: {e}", exc_info=True)
            return []

    def _evaluate_group(self, signal: Union[str, OptionSignal], df: pd.DataFrame,
                       cache: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """Evaluate a single signal group"""
        try:
            k = self._key(signal)
            group = self.config.get(k, {})

            if not group.get("enabled", True):
                return False, []

            logic = group.get("logic", "AND").upper()
            rules = group.get("rules", [])

            if not rules:
                return False, []

            group_result = (logic == "AND")
            rule_results = []

            for rule in rules:
                try:
                    rule_str = _rule_to_string(rule)

                    lhs_series = _resolve_side(df, rule.get("lhs", {}), cache)
                    rhs_series = _resolve_side(df, rule.get("rhs", {}), cache)

                    if lhs_series is None or rhs_series is None:
                        result, lhs_val, rhs_val = False, None, None
                    else:
                        result, lhs_val, rhs_val = _apply_operator(lhs_series, rule.get("op", ">"), rhs_series)

                    def _fmt(v):
                        if v is None: return "N/A"
                        return f"{v:.4f}" if isinstance(v, float) else str(v)

                    entry = {
                        "rule": rule_str,
                        "result": result,
                        "lhs_value": lhs_val,
                        "rhs_value": rhs_val,
                        "detail": f"{_fmt(lhs_val)} {rule.get('op','?')} {_fmt(rhs_val)} → {'✓' if result else '✗'}",
                    }
                    rule_results.append(entry)

                    if logic == "AND":
                        group_result = group_result and result
                    else:
                        group_result = group_result or result

                except Exception as e:
                    logger.error(f"Rule eval error: {e}", exc_info=True)
                    rule_results.append({
                        "rule": _rule_to_string(rule),
                        "result": False,
                        "lhs_value": None,
                        "rhs_value": None,
                        "detail": f"ERROR: {e}",
                        "error": str(e)
                    })
                    if logic == "AND":
                        group_result = False

            return group_result, rule_results

        except Exception as e:
            logger.error(f"[_evaluate_group] Failed for {signal}: {e}", exc_info=True)
            return False, []

    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Returns:
          {
            "signal":           OptionSignal,
            "signal_value":     str,
            "fired":            {group: bool, ...},
            "rule_results":     {group: [{rule, result, lhs_value, rhs_value, detail},...], ...},
            "indicator_values": {cache_key: {"last": float, "prev": float}, ...},
            "conflict":         bool,
            "available":        bool,
          }
        """
        neutral = self._neutral_result()

        try:
            if df is None or df.empty or len(df) < 2:
                logger.debug("DataFrame insufficient for evaluation")
                return neutral

            cache = {}
            fired = {}
            rule_results = {}
            has_any_rules = False

            for sig in SIGNAL_GROUPS:
                gf, rd = self._evaluate_group(sig, df, cache)
                fired[sig.value] = gf
                rule_results[sig.value] = rd
                if rd:
                    has_any_rules = True

            self._last_cache = cache

            # Build a flat {label: value} dict from the cache for easy reading
            indicator_values = {}
            for cache_key, series in cache.items():
                if series is not None and hasattr(series, "iloc") and len(series) > 0:
                    try:
                        last_val = series.iloc[-1]
                        prev_val = series.iloc[-2] if len(series) > 1 else None

                        # Handle NaN values
                        last_clean = None
                        if last_val is not None and not pd.isna(last_val) and not np.isnan(float(last_val)):
                            last_clean = round(float(last_val), 6)

                        prev_clean = None
                        if prev_val is not None and not pd.isna(prev_val) and not np.isnan(float(prev_val)):
                            prev_clean = round(float(prev_val), 6)

                        indicator_values[cache_key] = {
                            "last": last_clean,
                            "prev": prev_clean,
                        }
                    except Exception as e:
                        logger.warning(f"Failed to process indicator {cache_key}: {e}")
                        indicator_values[cache_key] = {"last": None, "prev": None}

            if not has_any_rules:
                return neutral

            resolved = self._resolve(fired)

            return {
                "signal": resolved,
                "signal_value": resolved.value if resolved else "WAIT",
                "fired": fired,
                "rule_results": rule_results,
                "indicator_values": indicator_values,
                "conflict": fired.get("BUY_CALL", False) and fired.get("BUY_PUT", False),
                "available": True,
            }

        except Exception as e:
            logger.error(f"[evaluate] Failed: {e}", exc_info=True)
            return neutral

    def _resolve(self, fired: Dict[str, bool]) -> OptionSignal:
        """Resolve final signal from fired groups"""
        try:
            bc = fired.get("BUY_CALL", False)
            bp = fired.get("BUY_PUT", False)
            sc = fired.get("EXIT_CALL", False)
            sp = fired.get("EXIT_PUT", False)
            h = fired.get("HOLD", False)

            if sc and sp:
                return OptionSignal.EXIT_CALL
            if sc:
                return OptionSignal.EXIT_CALL
            if sp:
                return OptionSignal.EXIT_PUT
            if h:
                return OptionSignal.HOLD
            if bc and bp:
                return OptionSignal.BUY_CALL if self.conflict_resolution == "PRIORITY" else OptionSignal.WAIT
            if bc:
                return OptionSignal.BUY_CALL
            if bp:
                return OptionSignal.BUY_PUT
            return OptionSignal.WAIT

        except Exception as e:
            logger.error(f"[_resolve] Failed: {e}", exc_info=True)
            return OptionSignal.WAIT

    @staticmethod
    def _neutral_result() -> Dict[str, Any]:
        """Return neutral result when evaluation is not possible"""
        try:
            return {
                "signal": OptionSignal.WAIT,
                "signal_value": "WAIT",
                "fired": {s.value: False for s in SIGNAL_GROUPS},
                "rule_results": {s.value: [] for s in SIGNAL_GROUPS},
                "indicator_values": {},
                "conflict": False,
                "available": False,
            }
        except Exception as e:
            logger.error(f"[_neutral_result] Failed: {e}", exc_info=True)
            return {}

    @property
    def last_cache(self) -> Optional[Dict[str, Any]]:
        """Get last evaluation cache"""
        try:
            return self._last_cache
        except Exception as e:
            logger.error(f"[last_cache] Failed: {e}", exc_info=True)
            return None

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown"""
        try:
            logger.info("[DynamicSignalEngine] Starting cleanup")
            self._last_cache = None
            self.config.clear()
            self._manager = None
            logger.info("[DynamicSignalEngine] Cleanup completed")
        except Exception as e:
            logger.error(f"[DynamicSignalEngine.cleanup] Error: {e}", exc_info=True)


def build_example_config() -> Dict[str, Any]:
    """Build an example configuration"""
    try:
        return {
            "BUY_CALL": {"logic": "AND", "enabled": True, "rules": [
                {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}}, "op": ">",
                 "rhs": {"type": "scalar", "value": 55}},
                {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}}, "op": "crosses_above",
                 "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}}},
                {"lhs": {"type": "indicator", "indicator": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
                 "op": ">", "rhs": {"type": "scalar", "value": 0}},
            ]},
            "BUY_PUT": {"logic": "AND", "enabled": True, "rules": [
                {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}}, "op": "<",
                 "rhs": {"type": "scalar", "value": 45}},
                {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}}, "op": "crosses_below",
                 "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}}},
                {"lhs": {"type": "indicator", "indicator": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
                 "op": "<", "rhs": {"type": "scalar", "value": 0}},
            ]},
            "EXIT_CALL": {"logic": "OR", "enabled": True, "rules": [
                {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}}, "op": ">",
                 "rhs": {"type": "scalar", "value": 75}},
                {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}}, "op": "crosses_below",
                 "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}}},
            ]},
            "EXIT_PUT": {"logic": "OR", "enabled": True, "rules": [
                {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}}, "op": "<",
                 "rhs": {"type": "scalar", "value": 25}},
                {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}}, "op": "crosses_above",
                 "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}}},
            ]},
            "HOLD": {"logic": "AND", "enabled": True, "rules": [
                {"lhs": {"type": "indicator", "indicator": "adx", "params": {"length": 14}}, "op": ">",
                 "rhs": {"type": "scalar", "value": 25}},
            ]},
            "conflict_resolution": "WAIT",
        }
    except Exception as e:
        logger.error(f"[build_example_config] Failed: {e}", exc_info=True)
        return {}