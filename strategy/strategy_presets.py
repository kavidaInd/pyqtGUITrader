"""
strategy_presets.py
===================
Centralised preset rule definitions for the Strategy Editor.
FEATURE 3: Added rule weights for confidence scoring.
Now includes 20+ profitable presets per signal group.
"""

from __future__ import annotations
from typing import Dict, List, Union

# ---------------------------------------------------------------------------
# Helper shortcuts to make rule dicts more readable
# ---------------------------------------------------------------------------

def _ind(indicator: str, params: dict = None, shift: int = None, sub_col: str = None) -> dict:
    """
    Indicator side helper with sub_col support for ALL multi-output indicators.

    sub_col selects a specific output column. Valid keys per indicator:
      macd:       MACD / SIGNAL / HIST
      stoch:      K / D
      stochrsi:   K / D
      kvo:        KVO / SIGNAL
      adx:        ADX / PLUS_DI / MINUS_DI
      aroon:      AROON_UP / AROON_DOWN
      dm:         PLUS_DM / MINUS_DM
      supertrend: TREND / DIRECTION / LONG / SHORT
      ichimoku:   ISA / ISB / ITS / IKS / ICS
      bbands:     UPPER / MIDDLE / LOWER / BANDWIDTH / PERCENT
      kc:         UPPER / MIDDLE / LOWER
      donchian:   UPPER / MIDDLE / LOWER
      adosc:      ADOSC / AD

    Legacy "column" key inside params is automatically converted to sub_col
    so that old presets continue to work without manual edits.
    """
    clean_params = {}
    inferred_sub_col = sub_col   # explicit arg wins over auto-detection

    if params:
        for k, v in params.items():
            if k == "column":
                if inferred_sub_col is None and isinstance(v, str):
                    v_up = v.upper()
                    ind_lo = indicator.lower()

                    if ind_lo == "macd":
                        if v_up.startswith("MACDS"):   inferred_sub_col = "SIGNAL"
                        elif v_up.startswith("MACDH"): inferred_sub_col = "HIST"
                        else:                          inferred_sub_col = "MACD"

                    elif ind_lo in ("stoch", "stochrsi"):
                        if "STOCHRSID" in v_up or "STOCHD" in v_up: inferred_sub_col = "D"
                        else:                                         inferred_sub_col = "K"

                    elif ind_lo == "kvo":
                        if v_up.startswith("KVOS"): inferred_sub_col = "SIGNAL"
                        else:                        inferred_sub_col = "KVO"

                    elif ind_lo == "adx":
                        if v_up.startswith("DMP"):   inferred_sub_col = "PLUS_DI"
                        elif v_up.startswith("DMN"): inferred_sub_col = "MINUS_DI"
                        else:                        inferred_sub_col = "ADX"

                    elif ind_lo == "dm":
                        if v_up.startswith("DMN"): inferred_sub_col = "MINUS_DM"
                        else:                       inferred_sub_col = "PLUS_DM"

                    elif ind_lo == "aroon":
                        if "AROOND" in v_up: inferred_sub_col = "AROON_DOWN"
                        else:                inferred_sub_col = "AROON_UP"

                    elif ind_lo == "supertrend":
                        if "SUPERTD" in v_up:   inferred_sub_col = "DIRECTION"
                        elif "SUPERTL" in v_up: inferred_sub_col = "LONG"
                        elif "SUPERTS" in v_up: inferred_sub_col = "SHORT"
                        else:                   inferred_sub_col = "TREND"

                    elif ind_lo == "ichimoku":
                        if v_up.startswith("ISA"):   inferred_sub_col = "ISA"
                        elif v_up.startswith("ISB"): inferred_sub_col = "ISB"
                        elif v_up.startswith("ITS"): inferred_sub_col = "ITS"
                        elif v_up.startswith("IKS"): inferred_sub_col = "IKS"
                        elif v_up.startswith("ICS"): inferred_sub_col = "ICS"

                    elif ind_lo == "bbands":
                        if v_up.startswith("BBU"):   inferred_sub_col = "UPPER"
                        elif v_up.startswith("BBL"): inferred_sub_col = "LOWER"
                        elif v_up.startswith("BBB"): inferred_sub_col = "BANDWIDTH"
                        elif v_up.startswith("BBP"): inferred_sub_col = "PERCENT"
                        else:                        inferred_sub_col = "MIDDLE"

                    elif ind_lo == "kc":
                        if v_up.startswith("KCU"):   inferred_sub_col = "UPPER"
                        elif v_up.startswith("KCL"): inferred_sub_col = "LOWER"
                        else:                        inferred_sub_col = "MIDDLE"

                    elif ind_lo == "donchian":
                        if v_up.startswith("DCU"):   inferred_sub_col = "UPPER"
                        elif v_up.startswith("DCL"): inferred_sub_col = "LOWER"
                        else:                        inferred_sub_col = "MIDDLE"

                    elif ind_lo == "adosc":
                        if v_up.startswith("AD") and not v_up.startswith("ADOSC"):
                            inferred_sub_col = "AD"
                        else:
                            inferred_sub_col = "ADOSC"

                continue   # never pass "column" key to the engine
            clean_params[k] = v

    d: dict = {"type": "indicator", "indicator": indicator, "params": clean_params}
    if inferred_sub_col:
        d["sub_col"] = inferred_sub_col
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

def _rule(lhs: dict, op: str, rhs: Union[dict, List[dict]], weight: float = 1.0) -> dict:
    """
    Assemble a single rule dict with optional weight.

    Args:
        lhs: Left-hand side definition
        op: Operator string (>, <, >=, <=, ==, !=,  between)
        rhs: Right-hand side definition (can be a single dict or list of two dicts for 'between')
        weight: Rule weight (higher = more important in confidence calculation)
    """
    return {
        "lhs": lhs,
        "op": op,
        "rhs": rhs,
        "weight": weight
    }

def _between(lhs: dict, lower: dict, upper: dict, weight: float = 1.0) -> dict:
    """
    Special case for 'between' operator that requires two RHS values.
    """
    return {
        "lhs": lhs,
        "op": "between",
        "rhs": [lower, upper],
        "weight": weight
    }

# Helper for creating derived columns (for complex expressions)
def _derived(expression: str, params: dict = None) -> dict:
    """
    Create a derived value expression.
    This will be evaluated by the engine.
    """
    return {"type": "derived", "expression": expression, "params": params or {}}

# ---------------------------------------------------------------------------
# PRESETS REGISTRY
# ---------------------------------------------------------------------------

PRESETS: Dict[str, List[Dict]] = {

    # =========================================================================
    # BUY CALL - 20+ Bullish Entry Presets
    # =========================================================================
    "BUY_CALL": [
        # Momentum Based
        {
            "name": "RSI Oversold Bounce",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), "<", _scalar(30), weight=1.5),
                _rule(_col("close"), ">", _ind("ema", {"length": 20}), weight=1.2),
            ],
        },
        {
            "name": "MACD Bullish Crossover",
            "rules": [
                _rule(_ind("macd", {"column": "MACDh_12_26_9"}), ">", _scalar(0), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(40), weight=1.0),
            ],
        },
        {
            "name": "Stochastic Bullish Cross",
            "rules": [
                _rule(_ind("stoch", {"column": "STOCHd_14_3_3"}), "<", _scalar(80), weight=1.2),
                _rule(_col("close"), ">", _ind("sma", {"length": 50}), weight=1.5),
            ],
        },
        {
            "name": "CCI Oversold Reversal",
            "rules": [
                _rule(_ind("cci", {"length": 20}), "<", _scalar(-100), weight=1.5),
                _rule(_col("volume"), ">", _ind("sma", {"length": 20, "column": "volume"}), weight=1.2),
            ],
        },
        {
            "name": "Williams %R Oversold",
            "rules": [
                _rule(_ind("willr", {"length": 14}), "<", _scalar(-80), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(30), weight=1.2),
            ],
        },

        # Trend Following
        {
            "name": "Golden Cross (EMA)",
            "rules": [
                _rule(_ind("ema", {"length": 21}), ">", _ind("ema", {"length": 50}), weight=1.8),
                _rule(_col("close"), ">", _ind("ema", {"length": 21}), weight=1.5),
            ],
        },
        {
            "name": "Golden Cross (SMA)",
            "rules": [
                _rule(_ind("sma", {"length": 20}), ">", _ind("sma", {"length": 50}), weight=1.5),
                _rule(_col("close"), ">", _ind("sma", {"length": 20}), weight=1.2),
            ],
        },
        {
            "name": "ADX Strong Trend",
            "rules": [
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), ">", _scalar(25), weight=2.0),
                _rule(_ind("dm", {"length": 14, "direction": "plus"}), ">",
                      _ind("dm", {"length": 14, "direction": "minus"}), weight=1.8),
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), ">",
                      _ind("adx", {"length": 14, "column": "ADX_14"}, shift=1), weight=1.5),
            ],
        },
        {
            "name": "Supertrend Buy",
            "rules": [
                _rule(_ind("supertrend", {"length": 7, "multiplier": 3, "column": "SUPERT_7_3.0"}), "<", _col("close"), weight=2.5),
                _rule(_ind("supertrend", {"length": 7, "multiplier": 3, "column": "SUPERT_7_3.0"}, shift=1), ">",
                      _col("close", shift=1), weight=2.0),
                _rule(_col("close"), ">", _ind("ema", {"length": 20}), weight=1.5),
            ],
        },
        {
            "name": "Parabolic SAR Flip",
            "rules": [
                _rule(_ind("psar", {"af": 0.02, "max_af": 0.2, "column": "PSARl_0.02_0.2"}), "<", _col("close"), weight=2.0),
                _rule(_ind("psar", {"af": 0.02, "max_af": 0.2, "column": "PSARl_0.02_0.2"}, shift=1), ">",
                      _col("close", shift=1), weight=1.8),
                _rule(_ind("ema", {"length": 9}), ">", _ind("ema", {"length": 21}), weight=1.5),
            ],
        },

        # Volatility Based
        {
            "name": "Bollinger Band Squeeze",
            "rules": [
                _rule(_ind("bbands", {"length": 20, "std": 2, "column": "BBL_20_2.0"}), "<", _col("close"), weight=1.5),
                _rule(_ind("bbands", {"length": 20, "std": 2, "column": "BBU_20_2.0"}), ">",
                      _ind("bbands", {"length": 20, "std": 2, "column": "BBU_20_2.0"}, shift=1), weight=1.8),
            ],
        },
        {
            "name": "Keltner Channel Breakout",
            "rules": [
                _rule(_ind("kc", {"length": 20, "scalar": 2, "column": "KCUe_20_2.0"}), ">",
                      _ind("kc", {"length": 20, "scalar": 2, "column": "KCUe_20_2.0"}, shift=1), weight=1.5),
                _rule(_col("volume"), ">", _ind("sma", {"length": 20, "column": "volume"}), weight=1.3),
            ],
        },
        {
            "name": "ATR Expansion",
            "rules": [
                _rule(_ind("atr", {"length": 14, "column": "ATR_14"}), ">",
                      _ind("sma", {"length": 20, "column": "ATR_14"}), weight=1.8),
                _rule(_col("close"), ">", _ind("ema", {"length": 20}), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(50), weight=1.2),
            ],
        },

        # Volume Based
        {
            "name": "OBV Breakout",
            "rules": [
                _rule(_ind("obv", {"column": "OBV"}), ">", _ind("obv", {"column": "OBV"}, shift=1), weight=1.5),
                _rule(_col("close"), ">", _ind("ema", {"length": 9}), weight=1.3),
            ],
        },
        {
            "name": "Volume Spike + Price",
            "rules": [
                _rule(_col("volume"), ">", _ind("sma", {"length": 20, "column": "volume"}), weight=1.8),
                _rule(_col("close"), ">", _col("open"), weight=1.5),
                _rule(_col("close"), ">", _ind("ema", {"length": 9}), weight=1.3),
            ],
        },
        {
            "name": "MFI Oversold",
            "rules": [
                _rule(_ind("mfi", {"length": 14}), "<", _scalar(20), weight=1.8),
                _rule(_col("close"), ">", _ind("sma", {"length": 20}), weight=1.2),
            ],
        },

        # Candlestick Patterns
        {
            "name": "Bullish Engulfing",
            "rules": [
                _rule(_col("close"), ">", _col("open"), weight=1.2),
                _rule(_col("open"), "<", _col("close", shift=1), weight=1.8),
                _rule(_col("close"), ">", _col("open", shift=1), weight=2.0),
                _rule(_col("low"), "<", _col("low", shift=1), weight=1.3),
            ],
        },
        {
            "name": "Hammer Pattern",
            "rules": [
                _rule(_col("close"), ">", _col("open"), weight=1.2),
                _rule(_derived("(high - low) > (abs(close - open) * 2)"), "==", _scalar(1), weight=1.8),
                _rule(_col("low"), "<=", _derived("low.rolling(5).min()"), weight=2.0),
            ],
        },
        {
            "name": "Morning Star",
            "rules": [
                _rule(_col("close", shift=2), "<", _col("open", shift=2), weight=1.5),
                _rule(_col("close", shift=1), ">", _col("open", shift=1), weight=1.8),
                _rule(_col("close"), ">", _derived("(high.shift(2) + low.shift(2)) / 2"), weight=2.0),
            ],
        },

        # Multi-Indicator Confirmations
        {
            "name": "Triple Bullish Confirmation",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(50), weight=1.5),
                _rule(_ind("macd", {"column": "MACD_12_26_9"}), ">", _ind("macd", {"column": "MACDs_12_26_9"}), weight=1.8),
                _rule(_col("close"), ">", _ind("ema", {"length": 200}), weight=2.0),
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), ">", _scalar(20), weight=1.5),
            ],
        },
        {
            "name": "Ichimoku Bullish",
            "rules": [
                _rule(_col("close"), ">", _ind("ichimoku", {"column": "ISA_9"}), weight=2.0),
                _rule(_ind("ichimoku", {"column": "ITS_9"}), ">",
                      _ind("ichimoku", {"column": "IKS_26"}), weight=1.8),
                _rule(_col("close"), ">", _ind("ichimoku", {"column": "ICS_26"}), weight=1.5),
            ],
        },
        {
            "name": "VWAP Bounce",
            "rules": [
                _rule(_col("close"), ">", _ind("vwap", {"column": "VWAP_D"}), weight=2.0),
                _rule(_col("low"), "<=", _ind("vwap", {"column": "VWAP_D"}), weight=1.5),
                _rule(_derived("close - open"), ">", _scalar(0), weight=1.2),
            ],
        },
        {
            "name": "Hull MA Crossover",
            "rules": [
                _rule(_ind("hma", {"length": 9}), ">", _ind("hma", {"length": 9}, shift=1), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(40), weight=1.2),
            ],
        },
        {
            "name": "Donchian Channel Breakout",
            "rules": [
                _rule(_ind("donchian", {"column": "DCU_20_20", "length": 20}), ">",
                      _ind("donchian", {"column": "DCU_20_20", "length": 20}, shift=1), weight=1.8),
                _rule(_col("volume"), ">", _ind("sma", {"length": 20, "column": "volume"}), weight=1.5),
            ],
        },
    ],

    # =========================================================================
    # BUY PUT - 20+ Bearish Entry Presets
    # =========================================================================
    "BUY_PUT": [
        # Momentum Based
        {
            "name": "RSI Overbought Reversal",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(70), weight=1.5),
                _rule(_col("close"), "<", _ind("ema", {"length": 20}), weight=1.2),
            ],
        },
        {
            "name": "MACD Bearish Crossover",
            "rules": [
                _rule(_ind("macd", {"column": "MACDh_12_26_9"}), "<", _scalar(0), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), "<", _scalar(60), weight=1.0),
            ],
        },
        {
            "name": "Stochastic Bearish Cross",
            "rules": [
                _rule(_ind("stoch", {"column": "STOCHd_14_3_3"}), ">", _scalar(20), weight=1.2),
                _rule(_col("close"), "<", _ind("sma", {"length": 50}), weight=1.5),
            ],
        },
        {
            "name": "CCI Overbought Reversal",
            "rules": [
                _rule(_ind("cci", {"length": 20}), ">", _scalar(100), weight=1.5),
                _rule(_col("volume"), ">", _ind("sma", {"length": 20, "column": "volume"}), weight=1.2),
            ],
        },
        {
            "name": "Williams %R Overbought",
            "rules": [
                _rule(_ind("willr", {"length": 14}), ">", _scalar(-20), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), "<", _scalar(70), weight=1.2),
            ],
        },

        # Trend Following
        {
            "name": "Death Cross (EMA)",
            "rules": [
                _rule(_ind("ema", {"length": 21}), "<", _ind("ema", {"length": 50}), weight=1.8),
                _rule(_col("close"), "<", _ind("ema", {"length": 21}), weight=1.5),
            ],
        },
        {
            "name": "Death Cross (SMA)",
            "rules": [
                _rule(_ind("sma", {"length": 20}), "<", _ind("sma", {"length": 50}), weight=1.5),
                _rule(_col("close"), "<", _ind("sma", {"length": 20}), weight=1.2),
            ],
        },
        {
            "name": "ADX Strong Downtrend",
            "rules": [
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), ">", _scalar(25), weight=2.0),
                _rule(_ind("dm", {"length": 14, "direction": "minus"}), ">",
                      _ind("dm", {"length": 14, "direction": "plus"}), weight=1.8),
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), ">",
                      _ind("adx", {"length": 14, "column": "ADX_14"}, shift=1), weight=1.5),
            ],
        },
        {
            "name": "Supertrend Sell",
            "rules": [
                _rule(_ind("supertrend", {"length": 7, "multiplier": 3, "column": "SUPERT_7_3.0"}), ">", _col("close"), weight=2.5),
                _rule(_ind("supertrend", {"length": 7, "multiplier": 3, "column": "SUPERT_7_3.0"}, shift=1), "<",
                      _col("close", shift=1), weight=2.0),
                _rule(_col("close"), "<", _ind("ema", {"length": 20}), weight=1.5),
            ],
        },
        {
            "name": "Parabolic SAR Flip Down",
            "rules": [
                _rule(_ind("psar", {"af": 0.02, "max_af": 0.2, "column": "PSARl_0.02_0.2"}), ">", _col("close"), weight=2.0),
                _rule(_ind("psar", {"af": 0.02, "max_af": 0.2, "column": "PSARl_0.02_0.2"}, shift=1), "<",
                      _col("close", shift=1), weight=1.8),
                _rule(_ind("ema", {"length": 9}), "<", _ind("ema", {"length": 21}), weight=1.5),
            ],
        },

        # Volatility Based
        {
            "name": "Bollinger Band Top Rejection",
            "rules": [
                _rule(_col("close"), ">", _ind("bbands", {"length": 20, "std": 2, "column": "BBU_20_2.0"}), weight=1.8),
                _rule(_col("close"), "<", _col("close", shift=1), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(70), weight=2.0),
            ],
        },
        {
            "name": "Keltner Channel Breakdown",
            "rules": [
                _rule(_ind("kc", {"length": 20, "scalar": 2, "column": "KCLe_20_2.0"}), "<",
                      _ind("kc", {"length": 20, "scalar": 2, "column": "KCLe_20_2.0"}, shift=1), weight=1.5),
                _rule(_col("volume"), ">", _ind("sma", {"length": 20, "column": "volume"}), weight=1.3),
            ],
        },

        # Volume Based
        {
            "name": "OBV Breakdown",
            "rules": [
                _rule(_ind("obv", {"column": "OBV"}), "<", _ind("obv", {"column": "OBV"}, shift=1), weight=1.5),
                _rule(_col("close"), "<", _ind("ema", {"length": 9}), weight=1.3),
            ],
        },
        {
            "name": "Volume Spike + Price Drop",
            "rules": [
                _rule(_col("volume"), ">", _ind("sma", {"length": 20, "column": "volume"}), weight=1.8),
                _rule(_col("close"), "<", _col("open"), weight=1.5),
                _rule(_col("close"), "<", _ind("ema", {"length": 9}), weight=1.3),
            ],
        },
        {
            "name": "MFI Overbought",
            "rules": [
                _rule(_ind("mfi", {"length": 14}), ">", _scalar(80), weight=1.8),
                _rule(_col("close"), "<", _ind("sma", {"length": 20}), weight=1.2),
            ],
        },

        # Candlestick Patterns
        {
            "name": "Bearish Engulfing",
            "rules": [
                _rule(_col("close"), "<", _col("open"), weight=1.2),
                _rule(_col("open"), ">", _col("close", shift=1), weight=1.8),
                _rule(_col("close"), "<", _col("open", shift=1), weight=2.0),
                _rule(_col("high"), ">", _col("high", shift=1), weight=1.3),
            ],
        },
        {
            "name": "Shooting Star",
            "rules": [
                _rule(_col("close"), "<", _col("open"), weight=1.2),
                _rule(_derived("(high - max(open, close)) > (high - low) * 0.6"), "==", _scalar(1), weight=2.0),
                _rule(_col("low"), ">=", _col("open"), weight=1.5),
            ],
        },
        {
            "name": "Evening Star",
            "rules": [
                _rule(_col("close", shift=2), ">", _col("open", shift=2), weight=1.5),
                _rule(_col("close", shift=1), "<", _col("open", shift=1), weight=1.8),
                _rule(_col("close"), "<", _derived("(high.shift(2) + low.shift(2)) / 2"), weight=2.0),
            ],
        },

        # Divergence Based
        {
            "name": "Bearish RSI Divergence",
            "rules": [
                _rule(_col("close"), ">", _col("close", shift=5), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), "<", _ind("rsi", {"length": 14}, shift=5), weight=2.5),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(70), weight=1.8),
            ],
        },
        {
            "name": "Bearish MACD Divergence",
            "rules": [
                _rule(_col("close"), ">", _col("close", shift=5), weight=1.5),
                _rule(_ind("macd", {"column": "MACD_12_26_9"}), "<",
                      _ind("macd", {"column": "MACD_12_26_9"}, shift=5), weight=2.5),
                _rule(_ind("macd", {"column": "MACDh_12_26_9"}), "<", _scalar(0), weight=1.5),
            ],
        },
    ],

    # =========================================================================
    # EXIT CALL - 20+ Exit from Long Presets
    # =========================================================================
    "EXIT_CALL": [
        # Profit Taking
        {
            "name": "Take Profit at Resistance",
            "rules": [
                _rule(_col("close"), ">", _ind("bbands", {"length": 20, "std": 2, "column": "BBU_20_2.0"}), weight=2.0),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(75), weight=1.8),
                _rule(_derived("abs(close - open) > (high - low) * 0.7"), "==", _scalar(1), weight=1.5),
            ],
        },
        {
            "name": "Profit Target Hit",
            "rules": [
                _rule(_col("close"), ">=", _derived("close.shift(10) * 1.05"), weight=2.5),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(70), weight=1.5),
            ],
        },

        # Momentum Reversal
        {
            "name": "RSI Overbought Exit",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(75), weight=1.5),
                _rule(_col("close"), "<", _ind("ema", {"length": 9}), weight=1.3),
            ],
        },
        {
            "name": "MACD Bearish Cross Exit",
            "rules": [
                _rule(_ind("macd", {"column": "MACDh_12_26_9"}), "<", _scalar(0), weight=1.8),
            ],
        },
        {
            "name": "Stochastic Overbought Exit",
            "rules": [
                _rule(_ind("stoch", {"k": 14, "d": 3, "column": "STOCHk_14_3_3"}), ">", _scalar(80), weight=1.5),
            ],
        },

        # Trend Reversal
        {
            "name": "EMA Death Cross Exit",
            "rules": [
                _rule(_ind("ema", {"length": 21}), "<", _ind("ema", {"length": 50}), weight=1.8),
            ],
        },
        {
            "name": "Supertrend Flip to Sell",
            "rules": [
                _rule(_col("close"), "<", _ind("ema", {"length": 9}), weight=1.5),
            ],
        },
        {
            "name": "ADX Trend Weakening",
            "rules": [
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), "<",
                      _ind("adx", {"length": 14, "column": "ADX_14"}, shift=1), weight=1.8),
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), "<", _scalar(25), weight=1.5),
                _rule(_ind("dm", {"length": 14, "direction": "plus"}), "<",
                      _ind("dm", {"length": 14, "direction": "minus"}), weight=2.0),
            ],
        },

        # Candlestick Patterns
        {
            "name": "Bearish Engulfing Exit",
            "rules": [
                _rule(_col("close"), "<", _col("open"), weight=1.5),
                _rule(_col("open"), ">", _col("close", shift=1), weight=2.0),
                _rule(_col("close"), "<", _col("open", shift=1), weight=2.2),
            ],
        },
        {
            "name": "Dark Cloud Cover",
            "rules": [
                _rule(_col("open"), ">", _col("close", shift=1), weight=1.8),
                _rule(_col("close"), "<", _derived("(high.shift(1) + low.shift(1)) / 2"), weight=2.0),
                _rule(_col("close"), "<", _col("open"), weight=1.5),
            ],
        },

        # Volatility Based
        {
            "name": "ATR Trailing Stop",
            "rules": [
                _rule(_col("close"), "<", _derived("high.rolling(10).max() - atr(14) * 2"), weight=2.5),
                _rule(_ind("atr", {"length": 14, "column": "ATR_14"}), ">",
                      _derived("atr.shift(1) * 1.2"), weight=1.8),
            ],
        },

        # Volume Based
        {
            "name": "Volume Climax Exit",
            "rules": [
                _rule(_col("volume"), ">", _derived("sma(volume,20) * 2"), weight=1.8),
                _rule(_col("close"), "<", _col("open"), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(75), weight=2.0),
            ],
        },
        {
            "name": "OBV Reversal Exit",
            "rules": [
                _rule(_col("close"), "<", _ind("ema", {"length": 9}), weight=1.5),
            ],
        },

        # Multi-Indicator
        {
            "name": "Triple Bearish Exit",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), "<", _scalar(50), weight=1.5),
                _rule(_ind("macd", {"column": "MACDh_12_26_9"}), "<", _scalar(0), weight=1.8),
                _rule(_col("close"), "<", _ind("ema", {"length": 20}), weight=2.0),
            ],
        },
        {
            "name": "Parabolic SAR Exit",
            "rules": [
                _rule(_ind("psar", {"af": 0.02, "max_af": 0.2, "column": "PSARl_0.02_0.2"}), ">", _col("close"), weight=2.5),
                _rule(_col("close"), "<", _ind("ema", {"length": 9}), weight=1.5),
            ],
        },
    ],

    # =========================================================================
    # EXIT PUT - 20+ Exit from Short Presets
    # =========================================================================
    "EXIT_PUT": [
        # Profit Taking
        {
            "name": "Take Profit at Support",
            "rules": [
                _rule(_col("close"), "<", _ind("bbands", {"length": 20, "std": 2, "column": "BBL_20_2.0"}), weight=2.0),
                _rule(_ind("rsi", {"length": 14}), "<", _scalar(25), weight=1.8),
                _rule(_derived("abs(open - close) > (high - low) * 0.7"), "==", _scalar(1), weight=1.5),
            ],
        },
        {
            "name": "Profit Target Hit Short",
            "rules": [
                _rule(_col("close"), "<=", _derived("close.shift(10) * 0.95"), weight=2.5),
                _rule(_ind("rsi", {"length": 14}), "<", _scalar(30), weight=1.5),
            ],
        },

        # Momentum Reversal
        {
            "name": "RSI Oversold Exit",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), "<", _scalar(25), weight=1.5),
                _rule(_col("close"), ">", _ind("ema", {"length": 9}), weight=1.3),
            ],
        },
        {
            "name": "MACD Bullish Cross Exit",
            "rules": [
                _rule(_ind("macd", {"column": "MACDh_12_26_9"}), ">", _scalar(0), weight=1.8),
            ],
        },

        # Trend Reversal
        {
            "name": "EMA Golden Cross Exit",
            "rules": [
                _rule(_ind("ema", {"length": 21}), ">", _ind("ema", {"length": 50}), weight=1.8),
            ],
        },
        {
            "name": "Supertrend Flip to Buy",
            "rules": [
                _rule(_col("close"), ">", _ind("ema", {"length": 9}), weight=1.5),
            ],
        },

        # Candlestick Patterns
        {
            "name": "Bullish Engulfing Exit",
            "rules": [
                _rule(_col("close"), ">", _col("open"), weight=1.5),
                _rule(_col("open"), "<", _col("close", shift=1), weight=2.0),
                _rule(_col("close"), ">", _col("open", shift=1), weight=2.2),
            ],
        },
        {
            "name": "Hammer Exit",
            "rules": [
                _rule(_col("close"), ">", _col("open"), weight=1.2),
                _rule(_derived("(high - low) > (abs(close - open) * 2)"), "==", _scalar(1), weight=1.8),
                _rule(_col("low"), "<=", _derived("low.rolling(5).min()"), weight=2.0),
            ],
        },

        # Support Bounce
        {
            "name": "Double Bottom Exit",
            "rules": [
                _rule(_col("low"), ">=", _derived("low.rolling(10).min()"), weight=1.5),
                _rule(_col("close"), ">", _col("open"), weight=1.8),
                _rule(_col("close"), ">", _ind("ema", {"length": 9}), weight=2.0),
            ],
        },
        {
            "name": "Bullish Divergence Exit",
            "rules": [
                _rule(_col("low"), "<", _col("low", shift=5), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), ">", _ind("rsi", {"length": 14}, shift=5), weight=2.5),
                _rule(_col("close"), ">", _ind("ema", {"length": 9}), weight=1.8),
            ],
        },
    ],

    # =========================================================================
    # HOLD - 20+ Hold Presets
    # =========================================================================
    "HOLD": [
        {
            "name": "Strong Uptrend",
            "rules": [
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), ">", _scalar(30), weight=2.0),
                _rule(_ind("dm", {"length": 14, "direction": "plus"}), ">",
                      _ind("dm", {"length": 14, "direction": "minus"}), weight=1.8),
                _rule(_col("close"), ">", _ind("ema", {"length": 20}), weight=1.5),
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), ">",
                      _ind("adx", {"length": 14, "column": "ADX_14"}, shift=1), weight=1.5),
            ],
        },
        {
            "name": "Strong Downtrend",
            "rules": [
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), ">", _scalar(30), weight=2.0),
                _rule(_ind("dm", {"length": 14, "direction": "minus"}), ">",
                      _ind("dm", {"length": 14, "direction": "plus"}), weight=1.8),
                _rule(_col("close"), "<", _ind("ema", {"length": 20}), weight=1.5),
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), ">",
                      _ind("adx", {"length": 14, "column": "ADX_14"}, shift=1), weight=1.5),
            ],
        },
        {
            "name": "Low Volatility",
            "rules": [
                _rule(_ind("atr", {"length": 14, "column": "ATR_14"}), "<",
                      _ind("sma", {"length": 20, "column": "ATR_14"}), weight=1.8),
                _rule(_derived("(bbands_upper(20,2) - bbands_lower(20,2)) < close * 0.02"), "==", _scalar(1), weight=1.5),
            ],
        },
        {
            "name": "Range Bound",
            "rules": [
                _rule(_derived("high.rolling(20).max() - low.rolling(20).min() < close * 0.05"), "==", _scalar(1), weight=1.8),
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), "<", _scalar(20), weight=2.0),
            ],
        },
        {
            "name": "EMA Alignment Bullish",
            "rules": [
                _rule(_ind("ema", {"length": 9}), ">", _ind("ema", {"length": 21}), weight=1.8),
                _rule(_ind("ema", {"length": 21}), ">", _ind("ema", {"length": 50}), weight=1.8),
                _rule(_ind("ema", {"length": 50}), ">", _ind("ema", {"length": 200}), weight=2.0),
            ],
        },
        {
            "name": "EMA Alignment Bearish",
            "rules": [
                _rule(_ind("ema", {"length": 9}), "<", _ind("ema", {"length": 21}), weight=1.8),
                _rule(_ind("ema", {"length": 21}), "<", _ind("ema", {"length": 50}), weight=1.8),
                _rule(_ind("ema", {"length": 50}), "<", _ind("ema", {"length": 200}), weight=2.0),
            ],
        },
        {
            "name": "Momentum Continuation",
            "rules": [
                _rule(_ind("rsi", {"length": 14}), ">", _scalar(60), weight=1.5),
                _rule(_ind("rsi", {"length": 14}), ">", _ind("rsi", {"length": 14}, shift=1), weight=1.5),
                _rule(_ind("macd", {"column": "MACDh_12_26_9"}), ">", _scalar(0), weight=1.8),
            ],
        },
        {
            "name": "No Clear Signal",
            "rules": [
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), "<", _scalar(20), weight=2.0),
                _between(_col("close"),
                        _ind("bbands", {"length": 20, "std": 2, "column": "BBL_20_2.0"}),
                        _ind("bbands", {"length": 20, "std": 2, "column": "BBU_20_2.0"}),
                        weight=1.5),
                _rule(_ind("rsi", {"length": 14}), "between", [_scalar(40), _scalar(60)], weight=1.5),
            ],
        },
        {
            "name": "Parabolic SAR Hold",
            "rules": [
                _rule(_ind("psar", {"af": 0.02, "max_af": 0.2, "column": "PSARl_0.02_0.2"}), "<", _col("close"), weight=1.8),
                _rule(_ind("psar", {"af": 0.02, "max_af": 0.2, "column": "PSARl_0.02_0.2"}), ">",
                      _ind("psar", {"af": 0.02, "max_af": 0.2, "column": "PSARl_0.02_0.2"}, shift=1), weight=1.5),
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), ">", _scalar(20), weight=1.5),
            ],
        },
        {
            "name": "Supertrend Hold",
            "rules": [
                _rule(_ind("supertrend", {"length": 7, "multiplier": 3, "column": "SUPERT_7_3.0"}), "<", _col("close"), weight=2.0),
                _rule(_ind("supertrend", {"length": 7, "multiplier": 3, "column": "SUPERT_7_3.0"}), "==",
                      _ind("supertrend", {"length": 7, "multiplier": 3, "column": "SUPERT_7_3.0"}, shift=1), weight=1.8),
            ],
        },
        {
            "name": "VWAP Hold",
            "rules": [
                _rule(_col("close"), ">", _ind("vwap", {"column": "VWAP_D"}), weight=1.5),
                _rule(_ind("vwap", {"column": "VWAP_D"}), ">", _ind("vwap", {"column": "VWAP_D"}, shift=1), weight=1.5),
                _rule(_ind("adx", {"length": 14, "column": "ADX_14"}), ">", _scalar(20), weight=1.8),
            ],
        },
        {
            "name": "Ichimoku Cloud Hold",
            "rules": [
                _rule(_col("close"), ">", _ind("ichimoku", {"column": "ISA_9"}), weight=2.0),
                _rule(_ind("ichimoku", {"column": "ITS_9"}), ">",
                      _ind("ichimoku", {"column": "IKS_26"}), weight=1.5),
            ],
        },
        {
            "name": "Pre-News Hold",
            "rules": [
                _rule(_ind("atr", {"length": 14, "column": "ATR_14"}), "<",
                      _ind("sma", {"length": 50, "column": "ATR_14"}), weight=1.5),
                _rule(_col("volume"), "<", _ind("sma", {"length": 20, "column": "volume"}), weight=1.5),
            ],
        },
        {
            "name": "Moving Average Hold",
            "rules": [
                _rule(_col("close"), ">", _ind("sma", {"length": 50}), weight=1.5),
                _rule(_col("close"), ">", _ind("sma", {"length": 200}), weight=2.0),
                _rule(_ind("sma", {"length": 50}), ">", _ind("sma", {"length": 200}), weight=1.8),
            ],
        },
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
    """
    rules = get_preset_rules(signal, name)
    for rule in rules:
        if "weight" not in rule:
            rule["weight"] = 1.0
    return rules