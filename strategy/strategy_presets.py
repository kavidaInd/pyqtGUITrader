"""
strategy_presets.py
===================
Centralised preset rule definitions for the Strategy Editor.

Structure
---------
PRESETS is a dict keyed by signal type:
    "BUY_CALL" | "BUY_PUT" | "EXIT_CALL" | "EXIT_PUT" | "HOLD"

Each value is a list of preset dicts:
    {
        "name":  str,           # label shown in the dropdown
        "rules": List[dict],    # list of rule dicts consumed by _add_rule()
    }

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


def _rule(lhs: dict, op: str, rhs: dict) -> dict:
    """Assemble a single rule dict."""
    return {"lhs": lhs, "op": op, "rhs": rhs}


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
                _rule(_ind("rsi", {"length": 14}), "<", _scalar(30)),
                _rule(_ind("rsi", {"length": 14}), "crosses_above", _scalar(30)),
            ],
        },

        {
            "name": "MACD Crossover",
            "rules": [
                _rule(_ind("macd", {"fast": 12, "slow": 26, "signal": 9}),
                      "crosses_above", _scalar(0)),
                _rule(_ind("macd", {"fast": 12, "slow": 26, "signal": 9}),
                      ">", _ind("macd", {"signal": 9})),
            ],
        },

        {
            "name": "BB Squeeze",
            "rules": [
                _rule(_ind("bbands", {"length": 20, "std": 2}), ">", _col("close")),
                _rule(_ind("bbands", {"length": 20, "std": 2}), "crosses_above", _col("close")),
            ],
        },

        {
            "name": "EMA Cross",
            "rules": [
                _rule(_ind("ema", {"length": 9}), "crosses_above", _ind("ema", {"length": 21})),
                _rule(_ind("ema", {"length": 9}), ">", _ind("ema", {"length": 21})),
            ],
        },

        {
            "name": "Stochastic Bull",
            "rules": [
                _rule(_ind("stoch", {"k": 14, "d": 3, "smooth_k": 3}), "crosses_above", _scalar(20)),
                _rule(_ind("stoch", {"k": 14, "d": 3, "smooth_k": 3}), "<", _scalar(80)),
            ],
        },

        {
            "name": "ADX Strong Trend",
            "rules": [
                _rule(_ind("adx", {"length": 14}), ">", _scalar(25)),
                _rule(_ind("dm", {"length": 14}), "crosses_above", _ind("dm", {"length": 14})),
            ],
        },

        {
            "name": "Ichimoku Breakout",
            "rules": [
                _rule(_col("close"),
                      "crosses_above",
                      _ind("ichimoku", {"tenkan": 9, "kijun": 26, "senkou": 52})),
                _rule(_ind("ichimoku", {"tenkan": 9, "kijun": 26, "senkou": 52}),
                      ">",
                      _ind("ichimoku", {"tenkan": 9, "kijun": 26, "senkou": 52})),
            ],
        },

        {
            "name": "Volume Breakout",
            "rules": [
                _rule(_ind("obv", {}), "crosses_above", _ind("sma", {"length": 20})),
                _rule(_col("volume"), ">", _ind("sma", {"length": 20})),
                _rule(_col("close"), ">", _ind("ema", {"length": 50})),
            ],
        },

        {
            "name": "Triple Confirmation",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(50)),
                _rule(_ind("macd", {"fast": 12, "slow": 26, "signal": 9}), ">", _scalar(0)),
                _rule(_col("close"), ">", _ind("ema", {"length": 200})),
            ],
        },

        {
            "name": "Bullish Engulfing",
            "rules": [
                _rule(_col("close"), ">", _col("open")),
                _rule(_col("open"), "<", _col("close", shift=1)),
                _rule(_col("close"), ">", _col("open", shift=1)),
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
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(70)),
                _rule(_ind("rsi", {"length": 14}), "crosses_below", _scalar(70)),
            ],
        },

        {
            "name": "MACD Bear Cross",
            "rules": [
                _rule(_ind("macd", {"fast": 12, "slow": 26, "signal": 9}),
                      "crosses_below", _scalar(0)),
                _rule(_ind("macd", {"fast": 12, "slow": 26, "signal": 9}),
                      "<", _ind("macd", {"signal": 9})),
            ],
        },

        {
            "name": "Death Cross",
            "rules": [
                _rule(_ind("sma", {"length": 50}), "crosses_below", _ind("sma", {"length": 200})),
                _rule(_ind("sma", {"length": 50}), "<", _ind("sma", {"length": 200})),
            ],
        },

        {
            "name": "BB Top Rejection",
            "rules": [
                _rule(_col("close"), ">", _ind("bbands", {"length": 20, "std": 2})),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(70)),
            ],
        },

        {
            "name": "Bearish Divergence",
            "rules": [
                _rule(_col("close"), ">", _col("close", shift=5)),
                _rule(_ind("rsi", {"length": 14}), "<", _ind("rsi", {"length": 14}, shift=5)),
            ],
        },

        # ------------------------------------------------------------------ #
        # Add more BUY_PUT presets below                                      #
        # ------------------------------------------------------------------ #
    ],

    # =========================================================================
    # SELL CALL  (Bearish — premium selling)
    # =========================================================================
    "EXIT_CALL": [

        {
            "name": "RSI Overbought",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(75)),
                _rule(_ind("rsi", {"length": 14}), "crosses_below", _scalar(70)),
            ],
        },

        {
            "name": "Resistance Test",
            "rules": [
                _rule(_col("close"), ">", _ind("kc", {"length": 20, "scalar": 2})),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(70)),
            ],
        },

        # ------------------------------------------------------------------ #
        # Add more EXIT_CALL presets below                                    #
        # ------------------------------------------------------------------ #
    ],

    # =========================================================================
    # SELL PUT  (Bullish — premium selling)
    # =========================================================================
    "EXIT_PUT": [

        {
            "name": "RSI Oversold",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), "<", _scalar(25)),
                _rule(_ind("rsi", {"length": 14}), "crosses_above", _scalar(30)),
            ],
        },

        {
            "name": "Support Bounce",
            "rules": [
                _rule(_col("close"),
                      "<",
                      _ind("bbands", {"length": 20, "std": 2})),
                _rule(_ind("stoch", {"k": 14, "d": 3, "smooth_k": 3}),
                      "crosses_above",
                      _scalar(20)),
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
                _rule(_ind("adx", {"length": 14}), ">", _scalar(25)),
                _rule(_ind("adx", {"length": 14}), ">", _ind("adx", {"length": 14}, shift=1)),
            ],
        },

        {
            "name": "Low Volatility",
            "rules": [
                _rule(_ind("atr", {"length": 14}), "<", _ind("sma", {"length": 20})),
                _rule(_ind("bbands", {"length": 20, "std": 2}), "<", _ind("bbands", {"length": 20, "std": 2})),
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
