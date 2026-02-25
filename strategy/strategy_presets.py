"""
strategy_presets.py
===================
Centralised preset rule definitions for the Strategy Editor.

FEATURE 3: Added rule weights for confidence scoring.

Structure
---------
PRESETS is a dict keyed by signal type:
    "BUY_CALL" | "BUY_PUT" | "EXIT_CALL" | "EXIT_PUT" | "HOLD"

Each value is a list of preset dicts:
    {
        "name":  str,           # label shown in the dropdown
        "rules": List[dict],    # list of rule dicts consumed by _add_rule()
    }

Each rule dict now includes a "weight" field (default 1.0) for confidence scoring.

Adding a new preset
-------------------
Just append a new entry to the appropriate signal list below.
The dropdown in the editor will pick it up automatically — no other
file needs to change.
"""

from __future__ import annotations

from typing import Dict, List


# ---------------------------------------------------------------------------
# Helper shortcuts to make rule dicts more readable
# ---------------------------------------------------------------------------

def _ind(indicator: str, params: dict = None, shift: int = None) -> dict:
    """Indicator side."""
    d: dict = {"type": "indicator", "indicator": indicator, "params": params or {}}
    if shift is not None:
        d["shift"] = shift
    return d


def _scalar(value: float) -> dict:
    """Scalar (constant number) side."""
    return {"type": "scalar", "value": value}


def _col(column: str, shift: int = None) -> dict:
    """Price column side."""
    d: dict = {"type": "column", "column": column}
    if shift is not None:
        d["shift"] = shift
    return d


def _rule(lhs: dict, op: str, rhs: dict, weight: float = 1.0) -> dict:
    """
    Assemble a single rule dict with optional weight.

    FEATURE 3: Added weight parameter for confidence scoring.

    Args:
        lhs: Left-hand side definition
        op: Operator string
        rhs: Right-hand side definition
        weight: Rule weight (higher = more important in confidence calculation)

    Returns:
        Rule dictionary
    """
    return {
        "lhs": lhs,
        "op": op,
        "rhs": rhs,
        "weight": weight
    }


# ---------------------------------------------------------------------------
# PRESETS REGISTRY
# ---------------------------------------------------------------------------

PRESETS: Dict[str, List[Dict]] = {

    # =========================================================================
    # BUY CALL  (Bullish signals — go long via calls)
    # =========================================================================
    "BUY_CALL": [

        {
            "name": "RSI Oversold",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), "<", _scalar(30), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), "crosses_above", _scalar(30), weight=2.0),
            ],
        },

        {
            "name": "MACD Crossover",
            "rules": [
                _rule(_ind("macd", {"fast": 12, "slow": 26, "signal": 9}),
                      "crosses_above", _scalar(0), weight=2.0),
                _rule(_ind("macd", {"fast": 12, "slow": 26, "signal": 9}),
                      ">", _ind("macd", {"signal": 9}), weight=1.5),
            ],
        },

        {
            "name": "BB Squeeze",
            "rules": [
                _rule(_ind("bbands", {"length": 20, "std": 2}), ">", _col("close"), weight=1.2),
                _rule(_ind("bbands", {"length": 20, "std": 2}), "crosses_above", _col("close"), weight=1.8),
            ],
        },

        {
            "name": "EMA Cross",
            "rules": [
                _rule(_ind("ema", {"length": 9}), "crosses_above", _ind("ema", {"length": 21}), weight=2.0),
                _rule(_ind("ema", {"length": 9}), ">", _ind("ema", {"length": 21}), weight=1.5),
            ],
        },

        {
            "name": "Stochastic Bull",
            "rules": [
                _rule(_ind("stoch", {"k": 14, "d": 3, "smooth_k": 3}), "crosses_above", _scalar(20), weight=1.8),
                _rule(_ind("stoch", {"k": 14, "d": 3, "smooth_k": 3}), "<", _scalar(80), weight=1.2),
            ],
        },

        {
            "name": "ADX Strong Trend",
            "rules": [
                _rule(_ind("adx", {"length": 14}), ">", _scalar(25), weight=2.0),
                _rule(_ind("dm", {"length": 14}), "crosses_above", _ind("dm", {"length": 14}), weight=1.5),
            ],
        },

        {
            "name": "Ichimoku Breakout",
            "rules": [
                _rule(_col("close"),
                      "crosses_above",
                      _ind("ichimoku", {"tenkan": 9, "kijun": 26, "senkou": 52}), weight=2.0),
                _rule(_ind("ichimoku", {"tenkan": 9, "kijun": 26, "senkou": 52}),
                      ">",
                      _ind("ichimoku", {"tenkan": 9, "kijun": 26, "senkou": 52}), weight=1.5),
            ],
        },

        {
            "name": "Volume Breakout",
            "rules": [
                _rule(_ind("obv", {}), "crosses_above", _ind("sma", {"length": 20}), weight=1.8),
                _rule(_col("volume"), ">", _ind("sma", {"length": 20}), weight=1.2),
                _rule(_col("close"), ">", _ind("ema", {"length": 50}), weight=1.5),
            ],
        },

        {
            "name": "Triple Confirmation",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(50), weight=1.2),
                _rule(_ind("macd", {"fast": 12, "slow": 26, "signal": 9}), ">", _scalar(0), weight=1.5),
                _rule(_col("close"), ">", _ind("ema", {"length": 200}), weight=2.0),
            ],
        },

        {
            "name": "Bullish Engulfing",
            "rules": [
                _rule(_col("close"), ">", _col("open"), weight=1.2),
                _rule(_col("open"), "<", _col("close", shift=1), weight=1.5),
                _rule(_col("close"), ">", _col("open", shift=1), weight=2.0),
            ],
        },

        # ------------------------------------------------------------------ #
        # Add more BUY_CALL presets below                                     #
        # ------------------------------------------------------------------ #
    ],

    # =========================================================================
    # BUY PUT  (Bearish signals — go long via puts)
    # =========================================================================
    "BUY_PUT": [

        {
            "name": "RSI Overbought",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(70), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), "crosses_below", _scalar(70), weight=2.0),
            ],
        },

        {
            "name": "MACD Bear Cross",
            "rules": [
                _rule(_ind("macd", {"fast": 12, "slow": 26, "signal": 9}),
                      "crosses_below", _scalar(0), weight=2.0),
                _rule(_ind("macd", {"fast": 12, "slow": 26, "signal": 9}),
                      "<", _ind("macd", {"signal": 9}), weight=1.5),
            ],
        },

        {
            "name": "Death Cross",
            "rules": [
                _rule(_ind("sma", {"length": 50}), "crosses_below", _ind("sma", {"length": 200}), weight=2.0),
                _rule(_ind("sma", {"length": 50}), "<", _ind("sma", {"length": 200}), weight=1.5),
            ],
        },

        {
            "name": "BB Top Rejection",
            "rules": [
                _rule(_col("close"), ">", _ind("bbands", {"length": 20, "std": 2}), weight=1.8),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(70), weight=1.5),
            ],
        },

        {
            "name": "Bearish Divergence",
            "rules": [
                _rule(_col("close"), ">", _col("close", shift=5), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), "<", _ind("rsi", {"length": 14}, shift=5), weight=2.0),
            ],
        },

        # ------------------------------------------------------------------ #
        # Add more BUY_PUT presets below                                      #
        # ------------------------------------------------------------------ #
    ],

    # =========================================================================
    # EXIT CALL  (Bearish — premium selling)
    # =========================================================================
    "EXIT_CALL": [

        {
            "name": "RSI Overbought",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(75), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), "crosses_below", _scalar(70), weight=2.0),
            ],
        },

        {
            "name": "Resistance Test",
            "rules": [
                _rule(_col("close"), ">", _ind("kc", {"length": 20, "scalar": 2}), weight=1.8),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(70), weight=1.5),
            ],
        },

        # ------------------------------------------------------------------ #
        # Add more EXIT_CALL presets below                                    #
        # ------------------------------------------------------------------ #
    ],

    # =========================================================================
    # EXIT PUT  (Bullish — premium selling)
    # =========================================================================
    "EXIT_PUT": [

        {
            "name": "RSI Oversold",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), "<", _scalar(25), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), "crosses_above", _scalar(30), weight=2.0),
            ],
        },

        {
            "name": "Support Bounce",
            "rules": [
                _rule(_col("close"),
                      "<",
                      _ind("bbands", {"length": 20, "std": 2}), weight=1.5),
                _rule(_ind("stoch", {"k": 14, "d": 3, "smooth_k": 3}),
                      "crosses_above",
                      _scalar(20), weight=2.0),
            ],
        },

        # ------------------------------------------------------------------ #
        # Add more EXIT_PUT presets below                                     #
        # ------------------------------------------------------------------ #
    ],

    # =========================================================================
    # HOLD
    # =========================================================================
    "HOLD": [

        {
            "name": "Strong Trend",
            "rules": [
                _rule(_ind("adx", {"length": 14}), ">", _scalar(25), weight=2.0),
                _rule(_ind("adx", {"length": 14}), ">", _ind("adx", {"length": 14}, shift=1), weight=1.5),
            ],
        },

        {
            "name": "Low Volatility",
            "rules": [
                _rule(_ind("atr", {"length": 14}), "<", _ind("sma", {"length": 20}), weight=1.8),
                _rule(_ind("bbands", {"length": 20, "std": 2}), "<", _ind("bbands", {"length": 20, "std": 2}), weight=1.5),
            ],
        },

        # ------------------------------------------------------------------ #
        # Add more HOLD presets below                                         #
        # ------------------------------------------------------------------ #
    ],
}


def get_preset_names(signal: str) -> List[str]:
    """Return a list of preset names for the given signal type."""
    return [p["name"] for p in PRESETS.get(signal, [])]


def get_preset_rules(signal: str, name: str) -> List[dict]:
    """Return the rules list for a named preset, or [] if not found."""
    for p in PRESETS.get(signal, []):
        if p["name"] == name:
            return p["rules"]
    return []


def get_preset_with_weights(signal: str, name: str) -> List[dict]:
    """
    FEATURE 3: Get preset rules with explicit weight information.
    Same as get_preset_rules but ensures all rules have weights.

    Args:
        signal: Signal group name
        name: Preset name

    Returns:
        List of rule dicts with weight fields
    """
    rules = get_preset_rules(signal, name)

    # Ensure all rules have weight (should already have from _rule helper)
    for rule in rules:
        if "weight" not in rule:
            rule["weight"] = 1.0

    return rules