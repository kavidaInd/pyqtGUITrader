"""
DynamicSignalEngine for option trading.
Signals: BUY_CALL, BUY_PUT, SELL_CALL, SELL_PUT, HOLD, WAIT
"""
from __future__ import annotations
import json, logging, os
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
except ImportError:
    ta = None
    logging.getLogger(__name__).warning("pandas_ta not installed — pip install pandas_ta")

logger = logging.getLogger(__name__)


class OptionSignal(str, Enum):
    BUY_CALL = "BUY_CALL"
    BUY_PUT = "BUY_PUT"
    SELL_CALL = "SELL_CALL"
    SELL_PUT = "SELL_PUT"
    HOLD = "HOLD"
    WAIT = "WAIT"


SIGNAL_GROUPS = [OptionSignal.BUY_CALL, OptionSignal.BUY_PUT, OptionSignal.SELL_CALL, OptionSignal.SELL_PUT,
                 OptionSignal.HOLD]

SIGNAL_LABELS: Dict[str, str] = {
    "BUY_CALL": "📈  Buy Call", "BUY_PUT": "📉  Buy Put",
    "SELL_CALL": "🔴  Sell Call", "SELL_PUT": "🔵  Sell Put", "HOLD": "⏸   Hold",
}
SIGNAL_COLORS: Dict[str, str] = {
    "BUY_CALL": "#a6e3a1", "BUY_PUT": "#89b4fa", "SELL_CALL": "#f38ba8",
    "SELL_PUT": "#fab387", "HOLD": "#f9e2af", "WAIT": "#585b70",
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
    "atr": {"length": 14}, "adx": {"length": 14}, "cci": {"length": 20}, "stoch": {"k": 14, "d": 3, "smooth_k": 3},
    "roc": {"length": 10}, "mom": {"length": 10}, "willr": {"length": 14}, "obv": {}, "vwap": {},
    "supertrend": {"length": 7, "multiplier": 3.0}, "kc": {"length": 20, "scalar": 1.5},
    "donchian": {"lower_length": 20, "upper_length": 20}, "psar": {"af0": 0.02, "af": 0.02, "max_af": 0.2},
    "tema": {"length": 20}, "dema": {"length": 20}, "hma": {"length": 20}, "zlma": {"length": 20},
    "slope": {"length": 1}, "linreg": {"length": 14},
}
INDICATOR_COLUMN_HINTS: Dict[str, str] = {
    "macd": "MACD_12_26_9", "bbands": "BBM_20_2.0", "stoch": "STOCHk_14_3_3",
    "supertrend": "SUPERT_7_3.0", "kc": "KCBe_20_1.5", "donchian": "DCM_20_20", "adx": "ADX_14",
}


def _compute_indicator(df, indicator, params):
    if ta is None: return None
    ind_name = INDICATOR_MAP.get(indicator.lower(), indicator.lower())
    try:
        method = getattr(ta, ind_name, None)
        if not method: return None
        result = method(high=df.get("high"), low=df.get("low"), close=df.get("close"),
                        open=df.get("open"), volume=df.get("volume"), **params)
        if result is None: return None
        if isinstance(result, pd.DataFrame):
            hint = INDICATOR_COLUMN_HINTS.get(indicator.lower())
            if hint and hint in result.columns: return result[hint]
            for col in result.columns:
                if ind_name.upper() in col.upper() or indicator.upper() in col.upper(): return result[col]
            return result.iloc[:, 0]
        if isinstance(result, pd.Series): return result
        return None
    except Exception as e:
        logger.error(f"Error computing '{indicator}': {e}", exc_info=True)
        return None


def _resolve_side(df, side_def, cache):
    t = side_def.get("type", "indicator")
    if t == "scalar":
        return pd.Series([float(side_def.get("value", 0))] * len(df), index=df.index)
    if t == "column":
        col = side_def.get("column", "close")
        return df[col].astype(float) if col in df.columns else None
    indicator = side_def.get("indicator", "").lower()
    params = side_def.get("params", INDICATOR_DEFAULTS.get(indicator, {}))
    cache_key = f"{indicator}_{json.dumps(params, sort_keys=True)}"
    if cache_key not in cache:
        cache[cache_key] = _compute_indicator(df, indicator, params)
    return cache[cache_key]


def _apply_operator(lhs, op, rhs):
    """Returns (result: bool, lhs_val: float|None, rhs_val: float|None)."""
    try:
        if op == "crosses_above":
            if len(lhs) < 2 or len(rhs) < 2: return False, None, None
            pl, cl = float(lhs.iloc[-2]), float(lhs.iloc[-1])
            pr, cr = float(rhs.iloc[-2]), float(rhs.iloc[-1])
            return (pl <= pr) and (cl > cr), round(cl, 6), round(cr, 6)
        if op == "crosses_below":
            if len(lhs) < 2 or len(rhs) < 2: return False, None, None
            pl, cl = float(lhs.iloc[-2]), float(lhs.iloc[-1])
            pr, cr = float(rhs.iloc[-2]), float(rhs.iloc[-1])
            return (pl >= pr) and (cl < cr), round(cl, 6), round(cr, 6)
        lv, rv = float(lhs.iloc[-1]), float(rhs.iloc[-1])
        if np.isnan(lv) or np.isnan(rv): return False, None, None
        result = bool({">": lv > rv, "<": lv < rv, ">=": lv >= rv, "<=": lv <= rv,
                       "==": abs(lv - rv) < 1e-9, "!=": abs(lv - rv) >= 1e-9}.get(op, False))
        return result, round(lv, 6), round(rv, 6)
    except Exception as e:
        logger.error(f"Operator error '{op}': {e}", exc_info=True)
        return False, None, None


def _rule_to_string(rule):
    def s(d):
        t = d.get("type", "indicator")
        if t == "scalar": return str(d.get("value", "?"))
        if t == "column": return d.get("column", "?").upper()
        ind = d.get("indicator", "?")
        p = ", ".join(f"{k}={v}" for k, v in d.get("params", {}).items())
        return f"{ind.upper()}({p})" if p else ind.upper()

    return f"{s(rule.get('lhs', {}))} {rule.get('op', '?')} {s(rule.get('rhs', {}))}"


class DynamicSignalEngine:
    DEFAULT_CONFIG: Dict[str, Any] = {
        sig.value: {"logic": "AND", "rules": [], "enabled": True} for sig in SIGNAL_GROUPS
    }

    def __init__(self, config_file="config/dynamic_signals.json", conflict_resolution="WAIT"):
        self._last_cache = None
        self.config_file = config_file
        self.conflict_resolution = conflict_resolution.upper()
        self.config = {k: {"logic": v["logic"], "rules": list(v["rules"]), "enabled": v["enabled"]}
                       for k, v in self.DEFAULT_CONFIG.items()}
        self.load()

    def _key(self, signal):
        return signal.value if isinstance(signal, OptionSignal) else str(signal)

    def load(self):
        if not os.path.exists(self.config_file):
            logger.info(f"No dynamic signal config at {self.config_file}. Using defaults.")
            return False
        try:
            with open(self.config_file, "r") as f:
                data = json.load(f)
            for sig in SIGNAL_GROUPS:
                k = sig.value
                if k in data:
                    self.config[k]["logic"] = data[k].get("logic", "AND").upper()
                    self.config[k]["rules"] = list(data[k].get("rules", []))
                    self.config[k]["enabled"] = bool(data[k].get("enabled", True))
            self.conflict_resolution = data.get("conflict_resolution", self.conflict_resolution).upper()
            return True
        except Exception as e:
            logger.error(f"Failed to load config: {e}", exc_info=True)
            return False

    def save(self):
        dir_path = os.path.dirname(self.config_file)
        if dir_path: os.makedirs(dir_path, exist_ok=True)
        tmp = self.config_file + ".tmp"
        try:
            payload = self.to_dict()
            payload["conflict_resolution"] = self.conflict_resolution
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, self.config_file)
            return True
        except Exception as e:
            logger.error(f"Failed to save: {e}", exc_info=True)
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except:
                    pass
            return False

    def to_dict(self):
        return {k: {"logic": v["logic"], "rules": list(v["rules"]), "enabled": v["enabled"]}
                for k, v in self.config.items()}

    def from_dict(self, d):
        for sig in SIGNAL_GROUPS:
            k = sig.value
            if k in d:
                self.config[k]["logic"] = d[k].get("logic", "AND").upper()
                self.config[k]["rules"] = list(d[k].get("rules", []))
                self.config[k]["enabled"] = bool(d[k].get("enabled", True))
        if "conflict_resolution" in d:
            self.conflict_resolution = str(d["conflict_resolution"]).upper()

    def add_rule(self, signal, rule):
        k = self._key(signal)
        if k not in self.config: return False
        self.config[k]["rules"].append(rule);
        return True

    def remove_rule(self, signal, index):
        k = self._key(signal)
        rules = self.config.get(k, {}).get("rules", [])
        if 0 <= index < len(rules): rules.pop(index); return True
        return False

    def update_rule(self, signal, index, rule):
        k = self._key(signal)
        rules = self.config.get(k, {}).get("rules", [])
        if 0 <= index < len(rules): rules[index] = rule; return True
        return False

    def get_rules(self, signal):
        return list(self.config.get(self._key(signal), {}).get("rules", []))

    def set_logic(self, signal, logic):
        k = self._key(signal)
        if k in self.config and logic.upper() in ("AND", "OR"):
            self.config[k]["logic"] = logic.upper()

    def get_logic(self, signal):
        return self.config.get(self._key(signal), {}).get("logic", "AND")

    def set_enabled(self, signal, enabled):
        k = self._key(signal)
        if k in self.config: self.config[k]["enabled"] = bool(enabled)

    def is_enabled(self, signal):
        return bool(self.config.get(self._key(signal), {}).get("enabled", True))

    def rule_descriptions(self, signal):
        return [_rule_to_string(r) for r in self.get_rules(signal)]

    def _evaluate_group(self, signal, df, cache):
        k = self._key(signal)
        group = self.config.get(k, {})
        if not group.get("enabled", True): return False, []
        logic = group.get("logic", "AND").upper()
        rules = group.get("rules", [])
        if not rules: return False, []
        group_result = (logic == "AND")
        rule_results = []
        for rule in rules:
            rule_str = _rule_to_string(rule)
            try:
                lhs_series = _resolve_side(df, rule.get("lhs", {}), cache)
                rhs_series = _resolve_side(df, rule.get("rhs", {}), cache)
                if lhs_series is None or rhs_series is None:
                    result, lhs_val, rhs_val = False, None, None
                else:
                    result, lhs_val, rhs_val = _apply_operator(lhs_series, rule.get("op", ">"), rhs_series)

                # Build a human-readable value string, e.g. "47.23 > 50.0 → False"
                def _fmt(v):
                    if v is None: return "N/A"
                    return f"{v:.4f}" if isinstance(v, float) else str(v)

                entry = {
                    "rule":      rule_str,
                    "result":    result,
                    "lhs_value": lhs_val,
                    "rhs_value": rhs_val,
                    "detail":    f"{_fmt(lhs_val)} {rule.get('op','?')} {_fmt(rhs_val)} → {'✓' if result else '✗'}",
                }
                rule_results.append(entry)

                if logic == "AND":
                    group_result = group_result and result
                else:
                    group_result = group_result or result
            except Exception as e:
                logger.error(f"Rule eval error '{rule_str}': {e}", exc_info=True)
                rule_results.append({"rule": rule_str, "result": False, "lhs_value": None, "rhs_value": None,
                                     "detail": f"ERROR: {e}", "error": str(e)})
                if logic == "AND": group_result = False
        return group_result, rule_results

    def evaluate(self, df):
        """
        Returns:
          {
            "signal":           OptionSignal,
            "signal_value":     str,
            "fired":            {group: bool, ...},
            "rule_results":     {group: [{rule, result, lhs_value, rhs_value, detail},...], ...},
            "indicator_values": {cache_key: last_value, ...},   # ← NEW: actual computed values
            "conflict":         bool,
            "available":        bool,
          }
        """
        neutral = self._neutral_result()
        if df is None or df.empty or len(df) < 2:
            return neutral
        cache = {}
        fired = {}
        rule_results = {}
        has_any_rules = False
        for sig in SIGNAL_GROUPS:
            gf, rd = self._evaluate_group(sig, df, cache)
            fired[sig.value] = gf
            rule_results[sig.value] = rd
            if rd: has_any_rules = True

        self._last_cache = cache

        # Build a flat {label: value} dict from the cache for easy reading
        indicator_values = {}
        for cache_key, series in cache.items():
            if series is not None and hasattr(series, "iloc") and len(series) > 0:
                try:
                    last_val = series.iloc[-1]
                    prev_val = series.iloc[-2] if len(series) > 1 else None
                    indicator_values[cache_key] = {
                        "last":  round(float(last_val), 6) if not np.isnan(float(last_val)) else None,
                        "prev":  round(float(prev_val), 6) if prev_val is not None and not np.isnan(float(prev_val)) else None,
                    }
                except Exception:
                    indicator_values[cache_key] = {"last": None, "prev": None}

        if not has_any_rules: return neutral
        resolved = self._resolve(fired)
        return {
            "signal":           resolved,
            "signal_value":     resolved.value,
            "fired":            fired,
            "rule_results":     rule_results,
            "indicator_values": indicator_values,
            "conflict":         fired.get("BUY_CALL", False) and fired.get("BUY_PUT", False),
            "available":        True,
        }

    def _resolve(self, fired):
        bc = fired.get("BUY_CALL", False)
        bp = fired.get("BUY_PUT", False)
        sc = fired.get("SELL_CALL", False)
        sp = fired.get("SELL_PUT", False)
        h = fired.get("HOLD", False)
        if sc and sp: return OptionSignal.SELL_CALL
        if sc: return OptionSignal.SELL_CALL
        if sp: return OptionSignal.SELL_PUT
        if h:  return OptionSignal.HOLD
        if bc and bp:
            return OptionSignal.BUY_CALL if self.conflict_resolution == "PRIORITY" else OptionSignal.WAIT
        if bc: return OptionSignal.BUY_CALL
        if bp: return OptionSignal.BUY_PUT
        return OptionSignal.WAIT

    @staticmethod
    def _neutral_result():
        return {
            "signal":           OptionSignal.WAIT,
            "signal_value":     "WAIT",
            "fired":            {s.value: False for s in SIGNAL_GROUPS},
            "rule_results":     {s.value: [] for s in SIGNAL_GROUPS},
            "indicator_values": {},
            "conflict":         False,
            "available":        False,
        }

    @property
    def last_cache(self):
        return self._last_cache


def build_example_config():
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
        "SELL_CALL": {"logic": "OR", "enabled": True, "rules": [
            {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}}, "op": ">",
             "rhs": {"type": "scalar", "value": 75}},
            {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}}, "op": "crosses_below",
             "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}}},
        ]},
        "SELL_PUT": {"logic": "OR", "enabled": True, "rules": [
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