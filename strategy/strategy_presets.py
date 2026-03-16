"""
strategy_presets.py
===================
Centralised preset rule definitions for the Strategy Editor.

Two tiers of presets
────────────────────
1. GENERAL PRESETS  — suitable for 5m / 15m / 1h timeframes.
   Classic cross/oscillator setups.

2. 1-MINUTE SCALPING PRESETS  (⚡ prefix in every name)
   All indicator parameters tuned for 1-minute bars:

   Indicator    Params          Rationale
   ──────────── ─────────────── ────────────────────────────────────────
   EMA          3/8/13/21       Micro-ribbon — reacts within 3-4 seconds
   RSI          5/7             Twice as fast as RSI-14
   MACD         5/13/3          Fast MACD; picks up 1-min impulse
   MACD         3/10/16         Ultra-fast MACD for breakout confirmation
   Stoch        5/3/3           Aggressive stoch — reversal within 2 bars
   SuperTrend   3/1.5           Tight; flips in 2-3 candles
   SuperTrend   2/1.0           Ultra-tight for pure momentum scalps
   ADX          7               Fast trend-strength
   ATR          7 vs 14         Volatility expansion filter
   VWAP         —               Intraday institutional reference price
   CCI          14              Oversold/overbought on 1-min
   MFI          7               Money-flow with short look-back
   WillR        9               Ultra-fast Williams %R
   OBV          —               Raw accumulation / distribution

   Strategy families added:
     1. EMA Ribbon           — Full micro-trend alignment (3/8/13/21)
     2. VWAP Momentum        — Institutional price as bias anchor
     3. MACD Impulse         — Histogram acceleration confirmation
     4. Stochastic Reversal  — Exhaustion scalp entries
     5. SuperTrend Flip      — Trend-following with tight trailing
     6. ADX Directional      — Trend-strength filtered entries
     7. Squeeze Breakout     — Volatility compression/expansion
     8. OBV Flow             — Volume-driven accumulation/distribution
     9. RSI Momentum         — Dual-RSI speed-optimised setups
    10. Triple Confluence    — Three independent signals aligned
    11. Opening Drive        — First 15-30 candle directional bias
    12. CCI Momentum         — Deep extreme reversal scalp
    13. Ultra-Fast           — 2-3 candle micro-trade (tightest)
"""

from __future__ import annotations
from typing import Dict, List, Union


# ─────────────────────────────────────────────────────────────────────────────
# DSL helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ind(indicator: str, params: dict = None, shift: int = None,
         sub_col: str = None) -> dict:
    """Indicator side with sub_col support for all multi-output indicators."""
    clean_params = {}
    inferred_sub_col = sub_col

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
                        inferred_sub_col = "D" if ("STOCHRSID" in v_up or "STOCHD" in v_up) else "K"
                    elif ind_lo == "kvo":
                        inferred_sub_col = "SIGNAL" if v_up.startswith("KVOS") else "KVO"
                    elif ind_lo == "adx":
                        if v_up.startswith("DMP"):   inferred_sub_col = "PLUS_DI"
                        elif v_up.startswith("DMN"): inferred_sub_col = "MINUS_DI"
                        else:                        inferred_sub_col = "ADX"
                    elif ind_lo == "dm":
                        inferred_sub_col = "MINUS_DM" if v_up.startswith("DMN") else "PLUS_DM"
                    elif ind_lo == "aroon":
                        inferred_sub_col = "AROON_DOWN" if "AROOND" in v_up else "AROON_UP"
                    elif ind_lo == "supertrend":
                        if "SUPERTD" in v_up:   inferred_sub_col = "DIRECTION"
                        elif "SUPERTL" in v_up: inferred_sub_col = "LONG"
                        elif "SUPERTS" in v_up: inferred_sub_col = "SHORT"
                        else:                   inferred_sub_col = "TREND"
                    elif ind_lo == "ichimoku":
                        for prefix, col in [("ISA","ISA"),("ISB","ISB"),("ITS","ITS"),
                                             ("IKS","IKS"),("ICS","ICS")]:
                            if v_up.startswith(prefix):
                                inferred_sub_col = col; break
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
                        inferred_sub_col = ("AD"
                                            if v_up.startswith("AD") and not v_up.startswith("ADOSC")
                                            else "ADOSC")
                continue
            clean_params[k] = v

    d: dict = {"type": "indicator", "indicator": indicator, "params": clean_params}
    if inferred_sub_col:
        d["sub_col"] = inferred_sub_col
    if shift is not None:
        d["shift"] = shift
    return d


def _scalar(value: float) -> dict:
    return {"type": "scalar", "value": value}


def _col(column: str, shift: int = None) -> dict:
    d: dict = {"type": "column", "column": column}
    if shift is not None:
        d["shift"] = shift
    return d


def _rule(lhs: dict, op: str, rhs, weight: float = 1.0) -> dict:
    return {"lhs": lhs, "op": op, "rhs": rhs, "weight": weight}


def _between(lhs: dict, lower: dict, upper: dict, weight: float = 1.0) -> dict:
    return {"lhs": lhs, "op": "between", "rhs": [lower, upper], "weight": weight}


# ─────────────────────────────────────────────────────────────────────────────
# Fast shorthand aliases (keeps 1-min rules concise)
# ─────────────────────────────────────────────────────────────────────────────

def _ema(n, shift=None):   return _ind("ema",   {"length": n}, shift=shift)
def _rsi(n, shift=None):   return _ind("rsi",   {"length": n}, shift=shift)
def _sma(n, shift=None):   return _ind("sma",   {"length": n}, shift=shift)
def _atr(n, shift=None):   return _ind("atr",   {"length": n, "mamode": "ema"}, shift=shift)
def _cci(n, shift=None):   return _ind("cci",   {"length": n}, shift=shift)
def _mfi(n, shift=None):   return _ind("mfi",   {"length": n}, shift=shift)
def _willr(n, shift=None): return _ind("willr", {"length": n}, shift=shift)
def _obv(shift=None):      return _ind("obv",   {}, shift=shift)
def _vwap(shift=None):     return _ind("vwap",  {}, shift=shift)

def _macd_hist(fast=5, slow=13, sig=3, shift=None):
    return _ind("macd", {"fast": fast, "slow": slow, "signal": sig},
                sub_col="HIST", shift=shift)

def _macd_line(fast=5, slow=13, sig=3, shift=None):
    return _ind("macd", {"fast": fast, "slow": slow, "signal": sig},
                sub_col="MACD", shift=shift)

def _macd_sig(fast=5, slow=13, sig=3, shift=None):
    return _ind("macd", {"fast": fast, "slow": slow, "signal": sig},
                sub_col="SIGNAL", shift=shift)

def _stoch_k(k=5, d=3, sk=3, shift=None):
    return _ind("stoch", {"k": k, "d": d, "smooth_k": sk, "ma_method": "sma"},
                sub_col="K", shift=shift)

def _stoch_d(k=5, d=3, sk=3, shift=None):
    return _ind("stoch", {"k": k, "d": d, "smooth_k": sk, "ma_method": "sma"},
                sub_col="D", shift=shift)

def _supertrend(length=3, mult=1.5, shift=None):
    return _ind("supertrend", {"length": length, "multiplier": mult},
                sub_col="TREND", shift=shift)

def _adx_val(n=7, shift=None):
    return _ind("adx", {"length": n}, sub_col="ADX", shift=shift)

def _plus_di(n=7, shift=None):
    return _ind("adx", {"length": n}, sub_col="PLUS_DI", shift=shift)

def _minus_di(n=7, shift=None):
    return _ind("adx", {"length": n}, sub_col="MINUS_DI", shift=shift)

def _bb_upper(n=20, std=2.0, shift=None):
    return _ind("bbands", {"length": n, "std": std}, sub_col="UPPER", shift=shift)

def _bb_lower(n=20, std=2.0, shift=None):
    return _ind("bbands", {"length": n, "std": std}, sub_col="LOWER", shift=shift)

def _bb_mid(n=20, std=2.0, shift=None):
    return _ind("bbands", {"length": n, "std": std}, sub_col="MIDDLE", shift=shift)

def _bb_bw(n=20, std=2.0, shift=None):
    return _ind("bbands", {"length": n, "std": std}, sub_col="BANDWIDTH", shift=shift)

def _kc_upper(n=20, sc=1.5, shift=None):
    return _ind("kc", {"length": n, "scalar": sc}, sub_col="UPPER", shift=shift)

def _kc_lower(n=20, sc=1.5, shift=None):
    return _ind("kc", {"length": n, "scalar": sc}, sub_col="LOWER", shift=shift)


def _s(*rules):
    """Sugar: pack rules into a list."""
    return list(rules)


# ─────────────────────────────────────────────────────────────────────────────
# PRESETS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

PRESETS: Dict[str, List[Dict]] = {

    # =========================================================================
    # BUY_CALL — General multi-timeframe bullish presets
    # =========================================================================
    "BUY_CALL": [
        {
            "name": "RSI Oversold Bounce",
            "rules": [
                _rule(_rsi(14), "<", _scalar(30), weight=1.5),
                _rule(_col("close"), ">", _ema(20), weight=1.2),
            ],
        },
        {
            "name": "MACD Bullish Crossover",
            "rules": [
                _rule(_macd_hist(12,26,9), ">", _scalar(0), weight=1.5),
                _rule(_rsi(14), ">", _scalar(40), weight=1.0),
            ],
        },
        {
            "name": "Golden Cross EMA",
            "rules": [
                _rule(_ema(21), ">", _ema(50), weight=1.8),
                _rule(_col("close"), ">", _ema(21), weight=1.5),
            ],
        },
        {
            "name": "ADX Strong Uptrend",
            "rules": [
                _rule(_adx_val(14), ">", _scalar(25), weight=2.0),
                _rule(_plus_di(14), ">", _minus_di(14), weight=1.8),
            ],
        },
        {
            "name": "Supertrend Buy",
            "rules": [
                _rule(_supertrend(7, 3.0), "<", _col("close"), weight=2.5),
                _rule(_supertrend(7, 3.0, shift=1), ">", _col("close", shift=1), weight=2.0),
                _rule(_col("close"), ">", _ema(20), weight=1.5),
            ],
        },
        {
            "name": "Bollinger Lower Bounce",
            "rules": [
                _rule(_col("close"), "<", _bb_lower(20, 2.0), weight=1.5),
                _rule(_col("close"), ">", _col("close", shift=1), weight=1.3),
                _rule(_rsi(14), ">", _scalar(30), weight=1.2),
            ],
        },
        {
            "name": "VWAP Bounce Long",
            "rules": [
                _rule(_col("close"), ">", _vwap(), weight=2.0),
                _rule(_col("low"), "<=", _vwap(), weight=1.5),
                _rule(_col("close"), ">", _col("open"), weight=1.2),
            ],
        },
        {
            "name": "Volume Spike Price Up",
            "rules": [
                _rule(_col("volume"), ">", _sma(20), weight=1.8),
                _rule(_col("close"), ">", _col("open"), weight=1.5),
                _rule(_col("close"), ">", _ema(9), weight=1.3),
            ],
        },
        {
            "name": "Triple Bullish Confirmation",
            "rules": [
                _rule(_rsi(14), ">", _scalar(50), weight=1.5),
                _rule(_macd_hist(12,26,9), ">", _scalar(0), weight=1.8),
                _rule(_col("close"), ">", _ema(20), weight=2.0),
                _rule(_adx_val(14), ">", _scalar(20), weight=1.5),
            ],
        },
        {
            "name": "Stochastic Bullish Cross",
            "rules": [
                _rule(_stoch_k(14,3,3), ">", _stoch_d(14,3,3), weight=1.5),
                _rule(_stoch_k(14,3,3), "<", _scalar(80), weight=1.2),
                _rule(_col("close"), ">", _sma(50), weight=1.3),
            ],
        },
    ],

    # =========================================================================
    # BUY_PUT — General multi-timeframe bearish presets
    # =========================================================================
    "BUY_PUT": [
        {
            "name": "RSI Overbought Reversal",
            "rules": [
                _rule(_rsi(14), ">", _scalar(70), weight=1.5),
                _rule(_col("close"), "<", _ema(20), weight=1.2),
            ],
        },
        {
            "name": "MACD Bearish Crossover",
            "rules": [
                _rule(_macd_hist(12,26,9), "<", _scalar(0), weight=1.5),
                _rule(_rsi(14), "<", _scalar(60), weight=1.0),
            ],
        },
        {
            "name": "Death Cross EMA",
            "rules": [
                _rule(_ema(21), "<", _ema(50), weight=1.8),
                _rule(_col("close"), "<", _ema(21), weight=1.5),
            ],
        },
        {
            "name": "ADX Strong Downtrend",
            "rules": [
                _rule(_adx_val(14), ">", _scalar(25), weight=2.0),
                _rule(_minus_di(14), ">", _plus_di(14), weight=1.8),
            ],
        },
        {
            "name": "Supertrend Sell",
            "rules": [
                _rule(_supertrend(7, 3.0), ">", _col("close"), weight=2.5),
                _rule(_supertrend(7, 3.0, shift=1), "<", _col("close", shift=1), weight=2.0),
                _rule(_col("close"), "<", _ema(20), weight=1.5),
            ],
        },
        {
            "name": "Bollinger Upper Rejection",
            "rules": [
                _rule(_col("close"), ">", _bb_upper(20, 2.0), weight=1.8),
                _rule(_col("close"), "<", _col("close", shift=1), weight=1.5),
                _rule(_rsi(14), ">", _scalar(70), weight=2.0),
            ],
        },
        {
            "name": "VWAP Breakdown Short",
            "rules": [
                _rule(_col("close"), "<", _vwap(), weight=2.0),
                _rule(_col("high"), ">=", _vwap(), weight=1.5),
                _rule(_col("close"), "<", _col("open"), weight=1.2),
            ],
        },
        {
            "name": "Volume Spike Price Down",
            "rules": [
                _rule(_col("volume"), ">", _sma(20), weight=1.8),
                _rule(_col("close"), "<", _col("open"), weight=1.5),
                _rule(_col("close"), "<", _ema(9), weight=1.3),
            ],
        },
        {
            "name": "Triple Bearish Confirmation",
            "rules": [
                _rule(_rsi(14), "<", _scalar(50), weight=1.5),
                _rule(_macd_hist(12,26,9), "<", _scalar(0), weight=1.8),
                _rule(_col("close"), "<", _ema(20), weight=2.0),
                _rule(_adx_val(14), ">", _scalar(20), weight=1.5),
            ],
        },
        {
            "name": "Stochastic Bearish Cross",
            "rules": [
                _rule(_stoch_k(14,3,3), "<", _stoch_d(14,3,3), weight=1.5),
                _rule(_stoch_k(14,3,3), ">", _scalar(20), weight=1.2),
                _rule(_col("close"), "<", _sma(50), weight=1.3),
            ],
        },
    ],

    # =========================================================================
    # EXIT_CALL — General exit from long / call
    # =========================================================================
    "EXIT_CALL": [
        {
            "name": "RSI Overbought Exit",
            "rules": [
                _rule(_rsi(14), ">", _scalar(75), weight=1.5),
                _rule(_col("close"), "<", _ema(9), weight=1.3),
            ],
        },
        {
            "name": "MACD Bearish Cross Exit",
            "rules": [
                _rule(_macd_hist(12,26,9), "<", _scalar(0), weight=1.8),
            ],
        },
        {
            "name": "EMA Death Cross Exit",
            "rules": [
                _rule(_ema(21), "<", _ema(50), weight=1.8),
            ],
        },
        {
            "name": "Triple Bearish Exit",
            "rules": [
                _rule(_rsi(14), "<", _scalar(50), weight=1.5),
                _rule(_macd_hist(12,26,9), "<", _scalar(0), weight=1.8),
                _rule(_col("close"), "<", _ema(20), weight=2.0),
            ],
        },
        {
            "name": "Supertrend Flips Bearish",
            "rules": [
                _rule(_supertrend(7, 3.0), ">", _col("close"), weight=2.5),
            ],
        },
        {
            "name": "VWAP Loss Exit",
            "rules": [
                _rule(_col("close"), "<", _vwap(), weight=2.0),
                _rule(_ema(9), "<", _ema(21), weight=1.8),
            ],
        },
        {
            "name": "ADX Weakening",
            "rules": [
                _rule(_adx_val(14), "<", _adx_val(14, shift=1), weight=1.8),
                _rule(_adx_val(14), "<", _scalar(25), weight=1.5),
                _rule(_minus_di(14), ">", _plus_di(14), weight=2.0),
            ],
        },
        {
            "name": "Bollinger Top Exit",
            "rules": [
                _rule(_col("close"), ">", _bb_upper(20, 2.0), weight=2.0),
                _rule(_rsi(14), ">", _scalar(75), weight=1.8),
                _rule(_col("close"), "<", _col("close", shift=1), weight=1.5),
            ],
        },
    ],

    # =========================================================================
    # EXIT_PUT — General exit from short / put
    # =========================================================================
    "EXIT_PUT": [
        {
            "name": "RSI Oversold Exit",
            "rules": [
                _rule(_rsi(14), "<", _scalar(25), weight=1.5),
                _rule(_col("close"), ">", _ema(9), weight=1.3),
            ],
        },
        {
            "name": "MACD Bullish Cross Exit",
            "rules": [
                _rule(_macd_hist(12,26,9), ">", _scalar(0), weight=1.8),
            ],
        },
        {
            "name": "EMA Golden Cross Exit",
            "rules": [
                _rule(_ema(21), ">", _ema(50), weight=1.8),
            ],
        },
        {
            "name": "Triple Bullish Exit",
            "rules": [
                _rule(_rsi(14), ">", _scalar(50), weight=1.5),
                _rule(_macd_hist(12,26,9), ">", _scalar(0), weight=1.8),
                _rule(_col("close"), ">", _ema(20), weight=2.0),
            ],
        },
        {
            "name": "Supertrend Flips Bullish",
            "rules": [
                _rule(_supertrend(7, 3.0), "<", _col("close"), weight=2.5),
            ],
        },
        {
            "name": "VWAP Reclaim Exit",
            "rules": [
                _rule(_col("close"), ">", _vwap(), weight=2.0),
                _rule(_ema(9), ">", _ema(21), weight=1.8),
            ],
        },
        {
            "name": "Bollinger Bottom Exit",
            "rules": [
                _rule(_col("close"), "<", _bb_lower(20, 2.0), weight=2.0),
                _rule(_rsi(14), "<", _scalar(25), weight=1.8),
                _rule(_col("close"), ">", _col("close", shift=1), weight=1.5),
            ],
        },
    ],

    # =========================================================================
    # HOLD — Range / no-trade / continuation conditions
    # =========================================================================
    "HOLD": [
        {
            "name": "ADX Weak Trend",
            "rules": [
                _rule(_adx_val(14), "<", _scalar(20), weight=2.0),
            ],
        },
        {
            "name": "EMA Aligned Bullish",
            "rules": [
                _rule(_ema(9), ">", _ema(21), weight=1.8),
                _rule(_ema(21), ">", _ema(50), weight=1.8),
                _rule(_rsi(14), ">", _scalar(55), weight=1.5),
            ],
        },
        {
            "name": "EMA Aligned Bearish",
            "rules": [
                _rule(_ema(9), "<", _ema(21), weight=1.8),
                _rule(_ema(21), "<", _ema(50), weight=1.8),
                _rule(_rsi(14), "<", _scalar(45), weight=1.5),
            ],
        },
        {
            "name": "VWAP Hold Bullish",
            "rules": [
                _rule(_col("close"), ">", _vwap(), weight=1.8),
                _rule(_adx_val(14), ">", _scalar(20), weight=1.5),
                _rule(_plus_di(14), ">", _minus_di(14), weight=1.5),
            ],
        },
    ],
}


# =============================================================================
# ⚡ FAMILY 1 — EMA RIBBON  (3 / 8 / 13 / 21)
# All four EMAs must be in order — eliminates choppy interleaved signals.
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [Ribbon] EMA Ribbon Bullish",
    "rules": _s(
        _rule(_ema(3),  ">", _ema(8),   weight=2.0),
        _rule(_ema(8),  ">", _ema(13),  weight=2.0),
        _rule(_ema(13), ">", _ema(21),  weight=2.0),
        _rule(_ema(3),  ">", _ema(3,  shift=1), weight=1.5),
        _rule(_ema(8),  ">", _ema(8,  shift=1), weight=1.5),
        _rule(_rsi(7),  ">", _scalar(52),        weight=1.8),
        _rule(_rsi(7),  ">", _rsi(7, shift=1),  weight=1.3),
        _rule(_col("close"), ">", _vwap(),        weight=1.8),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [Ribbon] EMA Ribbon Bearish",
    "rules": _s(
        _rule(_ema(3),  "<", _ema(8),   weight=2.0),
        _rule(_ema(8),  "<", _ema(13),  weight=2.0),
        _rule(_ema(13), "<", _ema(21),  weight=2.0),
        _rule(_ema(3),  "<", _ema(3,  shift=1), weight=1.5),
        _rule(_ema(8),  "<", _ema(8,  shift=1), weight=1.5),
        _rule(_rsi(7),  "<", _scalar(48),        weight=1.8),
        _rule(_rsi(7),  "<", _rsi(7, shift=1),  weight=1.3),
        _rule(_col("close"), "<", _vwap(),        weight=1.8),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [Ribbon] EMA Ribbon Breaks Down",
    "rules": _s(
        _rule(_ema(3),  "<", _ema(8),             weight=2.5),
        _rule(_rsi(7),  ">", _scalar(72),          weight=2.0),
        _rule(_rsi(7),  "<", _rsi(7, shift=1),    weight=1.5),
        _rule(_macd_hist(5,13,3), "<", _scalar(0), weight=2.0),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [Ribbon] EMA Ribbon Breaks Up",
    "rules": _s(
        _rule(_ema(3),  ">", _ema(8),             weight=2.5),
        _rule(_rsi(7),  "<", _scalar(28),          weight=2.0),
        _rule(_rsi(7),  ">", _rsi(7, shift=1),    weight=1.5),
        _rule(_macd_hist(5,13,3), ">", _scalar(0), weight=2.0),
    ),
})


# =============================================================================
# ⚡ FAMILY 2 — VWAP MOMENTUM  (institutional bias anchor)
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [VWAP] VWAP Momentum Long",
    "rules": _s(
        _rule(_col("close"), ">",  _vwap(),          weight=2.0),
        _rule(_col("low"),   ">",  _vwap(),           weight=1.5),
        _rule(_ema(9),       ">",  _vwap(),           weight=1.5),
        _rule(_rsi(7),       ">",  _scalar(52),       weight=1.8),
        _rule(_rsi(7),       "<",  _scalar(72),       weight=1.3),
        _rule(_macd_hist(5,13,3), ">", _scalar(0),   weight=2.0),
        _rule(_stoch_k(5,3,3), "<", _scalar(78),     weight=1.3),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [VWAP] VWAP Momentum Short",
    "rules": _s(
        _rule(_col("close"), "<",  _vwap(),           weight=2.0),
        _rule(_col("high"),  "<",  _vwap(),            weight=1.5),
        _rule(_ema(9),       "<",  _vwap(),            weight=1.5),
        _rule(_rsi(7),       "<",  _scalar(48),        weight=1.8),
        _rule(_rsi(7),       ">",  _scalar(28),        weight=1.3),
        _rule(_macd_hist(5,13,3), "<", _scalar(0),    weight=2.0),
        _rule(_stoch_k(5,3,3), ">", _scalar(22),      weight=1.3),
    ),
})

PRESETS["BUY_CALL"].append({
    "name": "⚡ [VWAP] VWAP Reclaim Long",
    "rules": _s(
        _rule(_col("close"), ">",  _vwap(),            weight=2.5),
        _rule(_col("close", shift=1), "<", _vwap(),    weight=2.5),
        _rule(_rsi(7),  ">", _scalar(45),              weight=1.5),
        _rule(_rsi(7),  "<", _scalar(68),              weight=1.3),
        _rule(_ema(9),  ">", _ema(9, shift=1),         weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [VWAP] VWAP Breakdown Short",
    "rules": _s(
        _rule(_col("close"), "<",  _vwap(),            weight=2.5),
        _rule(_col("close", shift=1), ">", _vwap(),    weight=2.5),
        _rule(_rsi(7),  "<", _scalar(55),              weight=1.5),
        _rule(_rsi(7),  ">", _scalar(32),              weight=1.3),
        _rule(_ema(9),  "<", _ema(9, shift=1),         weight=1.5),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [VWAP] Close Below VWAP",
    "rules": _s(
        _rule(_col("close"), "<", _vwap(), weight=2.5),
        _rule(_ema(9), "<", _ema(21),      weight=2.0),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [VWAP] Close Above VWAP",
    "rules": _s(
        _rule(_col("close"), ">", _vwap(), weight=2.5),
        _rule(_ema(9), ">", _ema(21),      weight=2.0),
    ),
})


# =============================================================================
# ⚡ FAMILY 3 — MACD IMPULSE  (histogram acceleration)
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [MACD] Fast Histogram Impulse Long",
    "rules": _s(
        _rule(_macd_hist(5,13,3), ">", _scalar(0),                  weight=2.0),
        _rule(_macd_hist(5,13,3), ">", _macd_hist(5,13,3, shift=1), weight=2.0),
        _rule(_macd_hist(5,13,3, shift=1), ">", _macd_hist(5,13,3, shift=2), weight=1.5),
        _rule(_macd_line(5,13,3), ">", _macd_sig(5,13,3),           weight=1.8),
        _rule(_ema(9),  ">", _ema(21),                               weight=1.5),
        _rule(_rsi(7),  ">", _rsi(7, shift=1),                     weight=1.3),
        _rule(_rsi(7),  "<", _scalar(72),                           weight=1.2),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [MACD] Fast Histogram Impulse Short",
    "rules": _s(
        _rule(_macd_hist(5,13,3), "<", _scalar(0),                  weight=2.0),
        _rule(_macd_hist(5,13,3), "<", _macd_hist(5,13,3, shift=1), weight=2.0),
        _rule(_macd_hist(5,13,3, shift=1), "<", _macd_hist(5,13,3, shift=2), weight=1.5),
        _rule(_macd_line(5,13,3), "<", _macd_sig(5,13,3),           weight=1.8),
        _rule(_ema(9),  "<", _ema(21),                               weight=1.5),
        _rule(_rsi(7),  "<", _rsi(7, shift=1),                     weight=1.3),
        _rule(_rsi(7),  ">", _scalar(28),                           weight=1.2),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [MACD] Histogram Turns Negative",
    "rules": _s(
        _rule(_macd_hist(5,13,3), "<", _scalar(0),            weight=2.5),
        _rule(_macd_hist(5,13,3, shift=1), ">", _scalar(0),   weight=2.0),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [MACD] Histogram Turns Positive",
    "rules": _s(
        _rule(_macd_hist(5,13,3), ">", _scalar(0),            weight=2.5),
        _rule(_macd_hist(5,13,3, shift=1), "<", _scalar(0),   weight=2.0),
    ),
})


# =============================================================================
# ⚡ FAMILY 4 — STOCHASTIC REVERSAL  (exhaustion scalp)
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [Stoch] Oversold Reversal Long",
    "rules": _s(
        _rule(_stoch_k(5,3,3), "<", _scalar(30),              weight=1.8),
        _rule(_stoch_k(5,3,3), ">", _stoch_k(5,3,3, shift=1), weight=2.0),
        _rule(_stoch_k(5,3,3), ">", _stoch_d(5,3,3),         weight=1.8),
        _rule(_rsi(7), ">", _rsi(7, shift=1),                 weight=1.5),
        _rule(_rsi(7), ">", _scalar(32),                      weight=1.3),
        _rule(_ema(9), ">", _ema(21),                         weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [Stoch] Overbought Reversal Short",
    "rules": _s(
        _rule(_stoch_k(5,3,3), ">", _scalar(70),              weight=1.8),
        _rule(_stoch_k(5,3,3), "<", _stoch_k(5,3,3, shift=1), weight=2.0),
        _rule(_stoch_k(5,3,3), "<", _stoch_d(5,3,3),          weight=1.8),
        _rule(_rsi(7), "<", _rsi(7, shift=1),                 weight=1.5),
        _rule(_rsi(7), "<", _scalar(68),                      weight=1.3),
        _rule(_ema(9), "<", _ema(21),                         weight=1.5),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [Stoch] Overbought + Falling",
    "rules": _s(
        _rule(_stoch_k(5,3,3), ">", _scalar(80),               weight=2.0),
        _rule(_stoch_k(5,3,3), "<", _stoch_k(5,3,3, shift=1),  weight=2.0),
        _rule(_rsi(7), ">", _scalar(72),                       weight=1.8),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [Stoch] Oversold + Rising",
    "rules": _s(
        _rule(_stoch_k(5,3,3), "<", _scalar(20),               weight=2.0),
        _rule(_stoch_k(5,3,3), ">", _stoch_k(5,3,3, shift=1),  weight=2.0),
        _rule(_rsi(7), "<", _scalar(28),                       weight=1.8),
    ),
})


# =============================================================================
# ⚡ FAMILY 5 — SUPERTREND FLIP  (tight trend-following)
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [ST] SuperTrend Flip to Bull",
    "rules": _s(
        _rule(_supertrend(3, 1.5),          ">", _scalar(0), weight=3.0),
        _rule(_supertrend(3, 1.5, shift=1), "<", _scalar(0), weight=3.0),
        _rule(_ema(9),  ">", _ema(21),                       weight=1.5),
        _rule(_col("close"), ">", _vwap(),                   weight=1.5),
        _rule(_rsi(7), ">", _scalar(45),                     weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [ST] SuperTrend Flip to Bear",
    "rules": _s(
        _rule(_supertrend(3, 1.5),          "<", _scalar(0), weight=3.0),
        _rule(_supertrend(3, 1.5, shift=1), ">", _scalar(0), weight=3.0),
        _rule(_ema(9),  "<", _ema(21),                       weight=1.5),
        _rule(_col("close"), "<", _vwap(),                   weight=1.5),
        _rule(_rsi(7), "<", _scalar(55),                     weight=1.5),
    ),
})

PRESETS["BUY_CALL"].append({
    "name": "⚡ [ST] SuperTrend Continuation Long",
    "rules": _s(
        _rule(_supertrend(3, 1.5),          ">", _scalar(0), weight=2.5),
        _rule(_supertrend(3, 1.5, shift=1), ">", _scalar(0), weight=2.0),
        _rule(_ema(9),  ">", _ema(21),                       weight=1.5),
        _rule(_ema(21), ">", _ema(21, shift=1),              weight=1.3),
        _rule(_macd_hist(5,13,3), ">", _scalar(0),           weight=1.8),
        _rule(_col("close"), ">", _vwap(),                   weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [ST] SuperTrend Continuation Short",
    "rules": _s(
        _rule(_supertrend(3, 1.5),          "<", _scalar(0), weight=2.5),
        _rule(_supertrend(3, 1.5, shift=1), "<", _scalar(0), weight=2.0),
        _rule(_ema(9),  "<", _ema(21),                       weight=1.5),
        _rule(_ema(21), "<", _ema(21, shift=1),              weight=1.3),
        _rule(_macd_hist(5,13,3), "<", _scalar(0),           weight=1.8),
        _rule(_col("close"), "<", _vwap(),                   weight=1.5),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [ST] SuperTrend Flips Bear",
    "rules": _s(
        _rule(_supertrend(3, 1.5), "<", _scalar(0), weight=3.0),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [ST] SuperTrend Flips Bull",
    "rules": _s(
        _rule(_supertrend(3, 1.5), ">", _scalar(0), weight=3.0),
    ),
})


# =============================================================================
# ⚡ FAMILY 6 — ADX DIRECTIONAL  (trend-strength filter)
# Uses ADX(7) — fast enough to react to 1-min trend changes.
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [ADX] Directional Trend Long",
    "rules": _s(
        _rule(_adx_val(7), ">", _scalar(20),       weight=2.0),
        _rule(_adx_val(7), ">", _adx_val(7, shift=1), weight=1.5),
        _rule(_plus_di(7), ">", _minus_di(7),      weight=2.5),
        _rule(_ema(9),  ">", _ema(21),             weight=1.5),
        _rule(_col("close"), ">", _vwap(),         weight=1.5),
        _rule(_rsi(7), ">", _scalar(52),           weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [ADX] Directional Trend Short",
    "rules": _s(
        _rule(_adx_val(7), ">", _scalar(20),       weight=2.0),
        _rule(_adx_val(7), ">", _adx_val(7, shift=1), weight=1.5),
        _rule(_minus_di(7), ">", _plus_di(7),      weight=2.5),
        _rule(_ema(9),  "<", _ema(21),             weight=1.5),
        _rule(_col("close"), "<", _vwap(),         weight=1.5),
        _rule(_rsi(7), "<", _scalar(48),           weight=1.5),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [ADX] Trend Weakens DI Flip",
    "rules": _s(
        _rule(_adx_val(7), "<", _adx_val(7, shift=1), weight=2.0),
        _rule(_minus_di(7), ">", _plus_di(7),          weight=2.5),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [ADX] Trend Weakens DI Flip",
    "rules": _s(
        _rule(_adx_val(7), "<", _adx_val(7, shift=1), weight=2.0),
        _rule(_plus_di(7), ">", _minus_di(7),          weight=2.5),
    ),
})


# =============================================================================
# ⚡ FAMILY 7 — SQUEEZE BREAKOUT  (BB inside KC = compression → expansion)
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [Squeeze] BB Breakout Long",
    "rules": _s(
        _rule(_bb_upper(20, 2.0), ">", _kc_upper(20, 1.5),          weight=2.5),
        _rule(_bb_upper(20, 2.0), ">", _bb_upper(20, 2.0, shift=1), weight=1.8),
        _rule(_col("close"), ">", _bb_upper(20, 2.0),                weight=1.5),
        _rule(_macd_hist(5,13,3), ">", _scalar(0),                   weight=2.0),
        _rule(_rsi(7), ">", _scalar(55),                             weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [Squeeze] BB Breakdown Short",
    "rules": _s(
        _rule(_bb_lower(20, 2.0), "<", _kc_lower(20, 1.5),          weight=2.5),
        _rule(_bb_lower(20, 2.0), "<", _bb_lower(20, 2.0, shift=1), weight=1.8),
        _rule(_col("close"), "<", _bb_lower(20, 2.0),                weight=1.5),
        _rule(_macd_hist(5,13,3), "<", _scalar(0),                   weight=2.0),
        _rule(_rsi(7), "<", _scalar(45),                             weight=1.5),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [Squeeze] BW Contracting Exit",
    "rules": _s(
        _rule(_bb_bw(20, 2.0), "<", _bb_bw(20, 2.0, shift=1), weight=2.0),
        _rule(_bb_bw(20, 2.0), "<", _bb_bw(20, 2.0, shift=2), weight=1.8),
        _rule(_rsi(7), ">", _scalar(70),                        weight=1.8),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [Squeeze] BW Contracting Exit",
    "rules": _s(
        _rule(_bb_bw(20, 2.0), "<", _bb_bw(20, 2.0, shift=1), weight=2.0),
        _rule(_bb_bw(20, 2.0), "<", _bb_bw(20, 2.0, shift=2), weight=1.8),
        _rule(_rsi(7), "<", _scalar(30),                        weight=1.8),
    ),
})


# =============================================================================
# ⚡ FAMILY 8 — OBV FLOW  (accumulation / distribution)
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [OBV] Accumulation Long",
    "rules": _s(
        _rule(_obv(), ">", _obv(shift=1),               weight=2.0),
        _rule(_obv(shift=1), ">", _obv(shift=2),        weight=1.5),
        _rule(_col("close"), ">", _col("close", shift=1), weight=1.5),
        _rule(_col("close"), ">", _ema(9),              weight=1.5),
        _rule(_ema(9), ">", _ema(21),                   weight=1.8),
        _rule(_mfi(7), ">", _scalar(40),                weight=1.3),
        _rule(_mfi(7), "<", _scalar(80),                weight=1.3),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [OBV] Distribution Short",
    "rules": _s(
        _rule(_obv(), "<", _obv(shift=1),               weight=2.0),
        _rule(_obv(shift=1), "<", _obv(shift=2),        weight=1.5),
        _rule(_col("close"), "<", _col("close", shift=1), weight=1.5),
        _rule(_col("close"), "<", _ema(9),              weight=1.5),
        _rule(_ema(9), "<", _ema(21),                   weight=1.8),
        _rule(_mfi(7), "<", _scalar(60),                weight=1.3),
        _rule(_mfi(7), ">", _scalar(20),                weight=1.3),
    ),
})


# =============================================================================
# ⚡ FAMILY 9 — RSI MOMENTUM  (dual-RSI speed-optimised)
# RSI(5) for fastest reaction + RSI(7) for confirmation.
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [RSI] Dual RSI Oversold Bounce",
    "rules": _s(
        _rule(_rsi(5), "<", _scalar(28),               weight=2.0),
        _rule(_rsi(5), ">", _rsi(5, shift=1),          weight=2.0),
        _rule(_rsi(7), ">", _rsi(7, shift=1),          weight=1.8),
        _rule(_rsi(7), ">", _scalar(32),               weight=1.5),
        _rule(_rsi(7), ">", _rsi(5),                   weight=1.3),
        _rule(_ema(9), ">", _ema(21, shift=2),         weight=1.3),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [RSI] Dual RSI Overbought Reversal",
    "rules": _s(
        _rule(_rsi(5), ">", _scalar(72),               weight=2.0),
        _rule(_rsi(5), "<", _rsi(5, shift=1),          weight=2.0),
        _rule(_rsi(7), "<", _rsi(7, shift=1),          weight=1.8),
        _rule(_rsi(7), "<", _scalar(68),               weight=1.5),
        _rule(_rsi(7), "<", _rsi(5),                   weight=1.3),
        _rule(_ema(9), "<", _ema(21, shift=2),         weight=1.3),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [RSI] RSI5 Overbought Falling",
    "rules": _s(
        _rule(_rsi(5), ">", _scalar(78),               weight=2.5),
        _rule(_rsi(5), "<", _rsi(5, shift=1),          weight=2.0),
        _rule(_rsi(7), ">", _scalar(72),               weight=1.8),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [RSI] RSI5 Oversold Rising",
    "rules": _s(
        _rule(_rsi(5), "<", _scalar(22),               weight=2.5),
        _rule(_rsi(5), ">", _rsi(5, shift=1),          weight=2.0),
        _rule(_rsi(7), "<", _scalar(28),               weight=1.8),
    ),
})


# =============================================================================
# ⚡ FAMILY 10 — TRIPLE CONFLUENCE  (highest probability 1-min entry)
# Three independently-computed signals must all agree.
# Rare but very high quality.
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [Triple] Triple Confluence Long",
    "rules": _s(
        # Pillar 1: SuperTrend bullish
        _rule(_supertrend(3, 1.5), ">", _scalar(0),   weight=2.5),
        # Pillar 2: VWAP bullish bias
        _rule(_col("close"), ">", _vwap(),             weight=2.0),
        _rule(_ema(9),       ">", _vwap(),             weight=1.5),
        # Pillar 3: MACD + RSI both bullish
        _rule(_macd_hist(5,13,3), ">", _scalar(0),    weight=2.0),
        _rule(_rsi(7), ">", _scalar(52),              weight=1.8),
        # Ribbon confirmation
        _rule(_ema(3),  ">", _ema(8),                 weight=1.5),
        _rule(_ema(8),  ">", _ema(13),                weight=1.5),
        # Trend strength > noise
        _rule(_adx_val(7), ">", _scalar(18),          weight=1.5),
        # Volatility expanding = real move
        _rule(_atr(7), ">", _atr(14),                 weight=1.3),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [Triple] Triple Confluence Short",
    "rules": _s(
        _rule(_supertrend(3, 1.5), "<", _scalar(0),   weight=2.5),
        _rule(_col("close"), "<", _vwap(),             weight=2.0),
        _rule(_ema(9),       "<", _vwap(),             weight=1.5),
        _rule(_macd_hist(5,13,3), "<", _scalar(0),    weight=2.0),
        _rule(_rsi(7), "<", _scalar(48),              weight=1.8),
        _rule(_ema(3),  "<", _ema(8),                 weight=1.5),
        _rule(_ema(8),  "<", _ema(13),                weight=1.5),
        _rule(_adx_val(7), ">", _scalar(18),          weight=1.5),
        _rule(_atr(7), ">", _atr(14),                 weight=1.3),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [Triple] Confluence Breaks Down",
    "rules": _s(
        _rule(_supertrend(3, 1.5), "<", _scalar(0),    weight=3.0),
        _rule(_macd_hist(5,13,3),  "<", _scalar(0),    weight=2.5),
        _rule(_rsi(7), ">", _scalar(74),               weight=2.0),
        _rule(_rsi(7), "<", _rsi(7, shift=1),          weight=1.5),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [Triple] Confluence Breaks Up",
    "rules": _s(
        _rule(_supertrend(3, 1.5), ">", _scalar(0),    weight=3.0),
        _rule(_macd_hist(5,13,3),  ">", _scalar(0),    weight=2.5),
        _rule(_rsi(7), "<", _scalar(26),               weight=2.0),
        _rule(_rsi(7), ">", _rsi(7, shift=1),          weight=1.5),
    ),
})


# =============================================================================
# ⚡ FAMILY 11 — OPENING DRIVE  (first 15-30 candle directional setup)
# Indian markets: 09:15 IST. Opening candles set intraday bias.
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [Open] Opening Drive Long",
    "rules": _s(
        _rule(_col("close"), ">", _ema(3),             weight=2.0),
        _rule(_ema(3),  ">", _ema(8),                  weight=1.8),
        _rule(_ema(8),  ">", _ema(21),                 weight=1.8),
        _rule(_rsi(5), ">", _scalar(55),               weight=1.8),
        _rule(_supertrend(2, 1.0), ">", _scalar(0),   weight=2.5),
        _rule(_rsi(7), "<", _scalar(72),              weight=1.3),
        _rule(_col("volume"), ">", _sma(5),            weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [Open] Opening Drive Short",
    "rules": _s(
        _rule(_col("close"), "<", _ema(3),             weight=2.0),
        _rule(_ema(3),  "<", _ema(8),                  weight=1.8),
        _rule(_ema(8),  "<", _ema(21),                 weight=1.8),
        _rule(_rsi(5), "<", _scalar(45),               weight=1.8),
        _rule(_supertrend(2, 1.0), "<", _scalar(0),   weight=2.5),
        _rule(_rsi(7), ">", _scalar(28),              weight=1.3),
        _rule(_col("volume"), ">", _sma(5),            weight=1.5),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [Open] Opening Drive Fades",
    "rules": _s(
        _rule(_col("close"), "<", _ema(3),             weight=2.5),
        _rule(_ema(3),  "<", _ema(8),                  weight=2.0),
        _rule(_supertrend(2, 1.0), "<", _scalar(0),   weight=2.5),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [Open] Opening Drive Fades",
    "rules": _s(
        _rule(_col("close"), ">", _ema(3),             weight=2.5),
        _rule(_ema(3),  ">", _ema(8),                  weight=2.0),
        _rule(_supertrend(2, 1.0), ">", _scalar(0),   weight=2.5),
    ),
})


# =============================================================================
# ⚡ FAMILY 12 — CCI MOMENTUM  (deep extreme reversal scalp)
# CCI(14) on 1-min reacts quickly. Extremes ±150 are high-probability.
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [CCI] Deep Oversold Bounce",
    "rules": _s(
        _rule(_cci(14, shift=1), "<", _scalar(-150),   weight=2.0),
        _rule(_cci(14), ">", _cci(14, shift=1),        weight=2.5),
        _rule(_cci(14), ">", _scalar(-100),            weight=1.8),
        _rule(_col("close"), ">", _ema(9),             weight=1.5),
        _rule(_rsi(7), ">", _rsi(7, shift=1),          weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [CCI] Deep Overbought Reversal",
    "rules": _s(
        _rule(_cci(14, shift=1), ">", _scalar(150),    weight=2.0),
        _rule(_cci(14), "<", _cci(14, shift=1),        weight=2.5),
        _rule(_cci(14), "<", _scalar(100),             weight=1.8),
        _rule(_col("close"), "<", _ema(9),             weight=1.5),
        _rule(_rsi(7), "<", _rsi(7, shift=1),          weight=1.5),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [CCI] Overbought Exhaustion",
    "rules": _s(
        _rule(_cci(14), ">", _scalar(150),             weight=2.5),
        _rule(_cci(14), "<", _cci(14, shift=1),        weight=2.0),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [CCI] Oversold Exhaustion",
    "rules": _s(
        _rule(_cci(14), "<", _scalar(-150),            weight=2.5),
        _rule(_cci(14), ">", _cci(14, shift=1),        weight=2.0),
    ),
})


# =============================================================================
# ⚡ FAMILY 13 — ULTRA-FAST  (2-3 candle micro-trades)
# Only 4-5 rules. Highest speed — tightest SL (use 2-3× ATR).
# Best for experienced traders who can override manually.
# =============================================================================

PRESETS["BUY_CALL"].append({
    "name": "⚡ [Ultra] Ultra-Fast Micro Long",
    "rules": _s(
        _rule(_col("close"), ">", _ema(3),             weight=2.0),
        _rule(_ema(3), ">", _ema(3, shift=1),          weight=2.0),
        _rule(_supertrend(2, 1.0), ">", _scalar(0),   weight=3.0),
        _rule(_rsi(5), ">", _scalar(52),              weight=1.8),
        _rule(_rsi(5), "<", _scalar(78),              weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [Ultra] Ultra-Fast Micro Short",
    "rules": _s(
        _rule(_col("close"), "<", _ema(3),             weight=2.0),
        _rule(_ema(3), "<", _ema(3, shift=1),          weight=2.0),
        _rule(_supertrend(2, 1.0), "<", _scalar(0),   weight=3.0),
        _rule(_rsi(5), "<", _scalar(48),              weight=1.8),
        _rule(_rsi(5), ">", _scalar(22),              weight=1.5),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [Ultra] Ultra-Fast Exit Long",
    "rules": _s(
        _rule(_col("close"), "<", _ema(3),             weight=3.0),
        _rule(_supertrend(2, 1.0), "<", _scalar(0),   weight=3.0),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [Ultra] Ultra-Fast Exit Short",
    "rules": _s(
        _rule(_col("close"), ">", _ema(3),             weight=3.0),
        _rule(_supertrend(2, 1.0), ">", _scalar(0),   weight=3.0),
    ),
})


# =============================================================================
# ⚡ HOLD conditions — 1-min specific
# =============================================================================

PRESETS["HOLD"].extend([
    {
        "name": "⚡ [Hold] Strong Uptrend Stay Long",
        "rules": _s(
            _rule(_supertrend(3, 1.5), ">", _scalar(0),    weight=2.5),
            _rule(_adx_val(7), ">", _scalar(20),           weight=1.8),
            _rule(_plus_di(7), ">", _minus_di(7),          weight=1.8),
            _rule(_ema(9), ">", _ema(21),                  weight=1.5),
            _rule(_col("close"), ">", _vwap(),             weight=1.5),
        ),
    },
    {
        "name": "⚡ [Hold] Strong Downtrend Stay Short",
        "rules": _s(
            _rule(_supertrend(3, 1.5), "<", _scalar(0),    weight=2.5),
            _rule(_adx_val(7), ">", _scalar(20),           weight=1.8),
            _rule(_minus_di(7), ">", _plus_di(7),          weight=1.8),
            _rule(_ema(9), "<", _ema(21),                  weight=1.5),
            _rule(_col("close"), "<", _vwap(),             weight=1.5),
        ),
    },
    {
        "name": "⚡ [Hold] ATR Expanding Momentum",
        "rules": _s(
            _rule(_atr(7), ">", _atr(14),                  weight=2.0),
            _rule(_atr(7), ">", _atr(7, shift=2),          weight=1.5),
            _rule(_adx_val(7), ">", _scalar(22),           weight=1.8),
        ),
    },
    {
        "name": "⚡ [Hold] Low Volatility Wait",
        "rules": _s(
            _rule(_atr(7), "<", _atr(14),                  weight=2.0),
            _rule(_adx_val(7), "<", _scalar(18),           weight=2.0),
            _rule(_bb_bw(20, 2.0), "<",
                  _bb_bw(20, 2.0, shift=3),                weight=1.5),
        ),
    },
])



# =============================================================================
# ⚡ FAMILY 14 — MARKET STRUCTURE  (HH/HL and LL/LH detection)
# =============================================================================
#
# Market structure is the backbone of price action trading. It determines
# whether the market is in an uptrend (Higher Highs + Higher Lows) or a
# downtrend (Lower Lows + Lower Highs).
#
# How it works on 1-min bars:
# ─────────────────────────────────────────────────────────────────────────────
#
#  BULLISH STRUCTURE — BUY CALL
#  ────────────────────────────
#  Higher High (HH):  high > high[shift=N]
#    → The current candle's high is above the swing high N bars ago.
#    → Price is making progressively higher peaks.
#
#  Higher Low  (HL):  low > low[shift=N]
#    → The most recent pullback low is above the previous pullback low.
#    → Buyers are stepping in at higher prices on every dip.
#
#  Combined HH + HL  =  intact bullish market structure
#
#  BEARISH STRUCTURE — BUY PUT
#  ────────────────────────────
#  Lower Low  (LL):  low < low[shift=N]
#    → Price is making progressively lower troughs.
#
#  Lower High (LH):  high < high[shift=N]
#    → Each rally is reaching a lower peak than the last.
#    → Sellers are dominating every bounce.
#
#  Combined LL + LH  =  intact bearish market structure
#
# Lookback tiers used:
#   Short  (shift=3)  — catches 3-bar micro-structure (best for 1-min scalps)
#   Medium (shift=5)  — 5-bar swing — good balance of speed vs noise
#   Long   (shift=8)  — 8-bar swing — more reliable, fewer but higher-quality signals
#
# Every MS preset is combined with at least one momentum/trend filter to
# prevent false signals during flat/choppy periods.
# =============================================================================

# ── Shorthand for price columns ───────────────────────────────────────────────
def _high(shift=None): return _col("high", shift=shift)
def _low(shift=None):  return _col("low",  shift=shift)
def _close(shift=None): return _col("close", shift=shift)
def _open(shift=None):  return _col("open",  shift=shift)


# ─── BUY_CALL — Bullish Market Structure (HH + HL) ───────────────────────────

PRESETS["BUY_CALL"].append({
    "name": "⚡ [MS] Basic HH+HL Long (3-bar)",
    "rules": _s(
        # Higher High: current high > high 3 bars ago
        _rule(_high(), ">", _high(shift=3),       weight=2.5),
        # Higher Low: current low > low 3 bars ago
        _rule(_low(),  ">", _low(shift=3),         weight=2.5),
        # Bullish close: close above open (confirming candle)
        _rule(_close(), ">", _open(),              weight=1.5),
        # EMA9 rising — micro-trend aligned
        _rule(_ema(9), ">", _ema(9, shift=1),      weight=1.5),
        # RSI(7) above midline — momentum supporting
        _rule(_rsi(7), ">", _scalar(50),           weight=1.5),
    ),
})

PRESETS["BUY_CALL"].append({
    "name": "⚡ [MS] Swing HH+HL Long (5-bar)",
    "rules": _s(
        # Higher High across 5-bar swing
        _rule(_high(), ">", _high(shift=5),        weight=2.5),
        # Higher Low across 5-bar swing
        _rule(_low(),  ">", _low(shift=5),          weight=2.5),
        # Intermediate bar also showing HL: bar-2 low > bar-5 low
        _rule(_low(shift=2), ">", _low(shift=5),   weight=1.8),
        # EMA9 > EMA21 — higher-level trend aligned
        _rule(_ema(9), ">", _ema(21),               weight=1.8),
        # Price above VWAP — institutional bias up
        _rule(_close(), ">", _vwap(),               weight=1.8),
        # MACD histogram positive
        _rule(_macd_hist(5,13,3), ">", _scalar(0),  weight=1.5),
    ),
})

PRESETS["BUY_CALL"].append({
    "name": "⚡ [MS] Multi-Swing HH+HL Long (8-bar)",
    "rules": _s(
        # Confirm two consecutive HH: current > 4 bars > 8 bars
        _rule(_high(),         ">", _high(shift=4), weight=2.5),
        _rule(_high(shift=4),  ">", _high(shift=8), weight=2.0),
        # Confirm two consecutive HL: current > 4 bars > 8 bars
        _rule(_low(),          ">", _low(shift=4),  weight=2.5),
        _rule(_low(shift=4),   ">", _low(shift=8),  weight=2.0),
        # SuperTrend(3,1.5) bullish
        _rule(_supertrend(3, 1.5), ">", _scalar(0), weight=2.0),
        # VWAP bullish
        _rule(_close(), ">", _vwap(),               weight=1.5),
    ),
})

PRESETS["BUY_CALL"].append({
    "name": "⚡ [MS] HH+HL + EMA Trend Long",
    "rules": _s(
        # HH: 5-bar lookback
        _rule(_high(), ">", _high(shift=5),         weight=2.5),
        # HL: 5-bar lookback
        _rule(_low(),  ">", _low(shift=5),           weight=2.5),
        # Full EMA stack bullish (trend context)
        _rule(_ema(9),  ">", _ema(21),               weight=2.0),
        _rule(_ema(21), ">", _ema(21, shift=1),      weight=1.5),
        # Ribbon: EMA3 > EMA8
        _rule(_ema(3),  ">", _ema(8),                weight=1.5),
        # RSI(7) above 52 and rising
        _rule(_rsi(7),  ">", _scalar(52),            weight=1.5),
        _rule(_rsi(7),  ">", _rsi(7, shift=1),      weight=1.3),
    ),
})

PRESETS["BUY_CALL"].append({
    "name": "⚡ [MS] HH+HL + VWAP Confluence Long",
    "rules": _s(
        # HH: 5-bar
        _rule(_high(), ">", _high(shift=5),          weight=2.5),
        # HL: 5-bar
        _rule(_low(),  ">", _low(shift=5),            weight=2.5),
        # Price and EMA9 both above VWAP
        _rule(_close(), ">", _vwap(),                 weight=2.0),
        _rule(_ema(9),  ">", _vwap(),                 weight=1.5),
        # MACD histogram positive and expanding
        _rule(_macd_hist(5,13,3), ">", _scalar(0),   weight=2.0),
        _rule(_macd_hist(5,13,3), ">",
              _macd_hist(5,13,3, shift=1),            weight=1.5),
    ),
})

PRESETS["BUY_CALL"].append({
    "name": "⚡ [MS] HH+HL + SuperTrend Long",
    "rules": _s(
        # HH: 3-bar — fast signal
        _rule(_high(), ">", _high(shift=3),           weight=2.5),
        # HL: 3-bar
        _rule(_low(),  ">", _low(shift=3),             weight=2.5),
        # SuperTrend(3,1.5) bullish
        _rule(_supertrend(3, 1.5), ">", _scalar(0),   weight=2.5),
        # ADX(7) > 18 — there is an actual trend (not chop)
        _rule(_adx_val(7), ">", _scalar(18),           weight=1.8),
        _rule(_plus_di(7), ">", _minus_di(7),          weight=1.8),
    ),
})

PRESETS["BUY_CALL"].append({
    "name": "⚡ [MS] HL Bounce Entry Long",
    "rules": _s(
        # Price just pulled back to — and bounced from — a Higher Low level
        # HL confirmed: current low > low 5 bars ago
        _rule(_low(),  ">", _low(shift=5),             weight=2.5),
        # The candle low touched close to previous low (bounce from HL zone)
        _rule(_low(),  ">", _low(shift=3),             weight=2.0),
        # Close recovering above EMA8 after the pullback
        _rule(_close(), ">", _ema(8),                  weight=2.0),
        # EMA8 still above EMA21 — uptrend intact
        _rule(_ema(8),  ">", _ema(21),                 weight=1.8),
        # RSI(7) recovering from 40-55 zone (pulled back but not oversold)
        _rule(_rsi(7),  ">", _scalar(40),              weight=1.5),
        _rule(_rsi(7),  "<", _scalar(65),              weight=1.3),
        _rule(_rsi(7),  ">", _rsi(7, shift=1),        weight=1.5),
    ),
})

PRESETS["BUY_CALL"].append({
    "name": "⚡ [MS] Structure Break + Momentum Long",
    "rules": _s(
        # Price breaking above the most recent swing high (HH forming)
        _rule(_high(), ">", _high(shift=3),            weight=2.5),
        _rule(_high(), ">", _high(shift=5),            weight=2.0),
        # Close above previous swing high (not just wick)
        _rule(_close(), ">", _high(shift=3),           weight=2.0),
        # Volume expanding on the break
        _rule(_col("volume"), ">", _sma(10),           weight=1.5),
        # RSI(7) > 55 — momentum confirmed
        _rule(_rsi(7),  ">", _scalar(55),              weight=1.8),
        # MACD histogram growing
        _rule(_macd_hist(5,13,3), ">",
              _macd_hist(5,13,3, shift=1),             weight=1.5),
    ),
})


# ─── BUY_PUT — Bearish Market Structure (LL + LH) ────────────────────────────

PRESETS["BUY_PUT"].append({
    "name": "⚡ [MS] Basic LL+LH Short (3-bar)",
    "rules": _s(
        # Lower Low: current low < low 3 bars ago
        _rule(_low(),  "<", _low(shift=3),             weight=2.5),
        # Lower High: current high < high 3 bars ago
        _rule(_high(), "<", _high(shift=3),            weight=2.5),
        # Bearish close: close below open
        _rule(_close(), "<", _open(),                  weight=1.5),
        # EMA9 falling
        _rule(_ema(9), "<", _ema(9, shift=1),          weight=1.5),
        # RSI(7) below midline
        _rule(_rsi(7), "<", _scalar(50),               weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [MS] Swing LL+LH Short (5-bar)",
    "rules": _s(
        # Lower Low across 5-bar swing
        _rule(_low(),  "<", _low(shift=5),             weight=2.5),
        # Lower High across 5-bar swing
        _rule(_high(), "<", _high(shift=5),            weight=2.5),
        # Intermediate bar also showing LH: bar-2 high < bar-5 high
        _rule(_high(shift=2), "<", _high(shift=5),    weight=1.8),
        # EMA9 < EMA21 — higher-level trend aligned down
        _rule(_ema(9), "<", _ema(21),                  weight=1.8),
        # Price below VWAP — institutional bias down
        _rule(_close(), "<", _vwap(),                  weight=1.8),
        # MACD histogram negative
        _rule(_macd_hist(5,13,3), "<", _scalar(0),     weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [MS] Multi-Swing LL+LH Short (8-bar)",
    "rules": _s(
        # Confirm two consecutive LL
        _rule(_low(),          "<", _low(shift=4),     weight=2.5),
        _rule(_low(shift=4),   "<", _low(shift=8),     weight=2.0),
        # Confirm two consecutive LH
        _rule(_high(),         "<", _high(shift=4),    weight=2.5),
        _rule(_high(shift=4),  "<", _high(shift=8),    weight=2.0),
        # SuperTrend(3,1.5) bearish
        _rule(_supertrend(3, 1.5), "<", _scalar(0),    weight=2.0),
        # VWAP bearish
        _rule(_close(), "<", _vwap(),                  weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [MS] LL+LH + EMA Trend Short",
    "rules": _s(
        # LL: 5-bar
        _rule(_low(),  "<", _low(shift=5),             weight=2.5),
        # LH: 5-bar
        _rule(_high(), "<", _high(shift=5),            weight=2.5),
        # Full EMA stack bearish
        _rule(_ema(9),  "<", _ema(21),                 weight=2.0),
        _rule(_ema(21), "<", _ema(21, shift=1),        weight=1.5),
        # Ribbon: EMA3 < EMA8
        _rule(_ema(3),  "<", _ema(8),                  weight=1.5),
        # RSI(7) below 48 and falling
        _rule(_rsi(7),  "<", _scalar(48),              weight=1.5),
        _rule(_rsi(7),  "<", _rsi(7, shift=1),        weight=1.3),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [MS] LL+LH + VWAP Confluence Short",
    "rules": _s(
        # LL: 5-bar
        _rule(_low(),  "<", _low(shift=5),             weight=2.5),
        # LH: 5-bar
        _rule(_high(), "<", _high(shift=5),            weight=2.5),
        # Price and EMA9 both below VWAP
        _rule(_close(), "<", _vwap(),                  weight=2.0),
        _rule(_ema(9),  "<", _vwap(),                  weight=1.5),
        # MACD histogram negative and expanding downward
        _rule(_macd_hist(5,13,3), "<", _scalar(0),    weight=2.0),
        _rule(_macd_hist(5,13,3), "<",
              _macd_hist(5,13,3, shift=1),             weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [MS] LL+LH + SuperTrend Short",
    "rules": _s(
        # LL: 3-bar — fast signal
        _rule(_low(),  "<", _low(shift=3),             weight=2.5),
        # LH: 3-bar
        _rule(_high(), "<", _high(shift=3),            weight=2.5),
        # SuperTrend(3,1.5) bearish
        _rule(_supertrend(3, 1.5), "<", _scalar(0),    weight=2.5),
        # ADX(7) > 18 — actual trend, not chop
        _rule(_adx_val(7), ">", _scalar(18),           weight=1.8),
        _rule(_minus_di(7), ">", _plus_di(7),          weight=1.8),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [MS] LH Rejection Entry Short",
    "rules": _s(
        # Price rallied to — and got rejected from — a Lower High level
        # LH confirmed: current high < high 5 bars ago
        _rule(_high(), "<", _high(shift=5),            weight=2.5),
        _rule(_high(), "<", _high(shift=3),            weight=2.0),
        # Close breaking below EMA8 after the rejection
        _rule(_close(), "<", _ema(8),                  weight=2.0),
        # EMA8 still below EMA21 — downtrend intact
        _rule(_ema(8),  "<", _ema(21),                 weight=1.8),
        # RSI(7) in 35-60 zone (rallied but not overbought)
        _rule(_rsi(7),  "<", _scalar(60),              weight=1.5),
        _rule(_rsi(7),  ">", _scalar(35),              weight=1.3),
        _rule(_rsi(7),  "<", _rsi(7, shift=1),        weight=1.5),
    ),
})

PRESETS["BUY_PUT"].append({
    "name": "⚡ [MS] Structure Break + Momentum Short",
    "rules": _s(
        # Price breaking below the most recent swing low (LL forming)
        _rule(_low(),  "<", _low(shift=3),             weight=2.5),
        _rule(_low(),  "<", _low(shift=5),             weight=2.0),
        # Close below previous swing low (not just wick)
        _rule(_close(), "<", _low(shift=3),            weight=2.0),
        # Volume expanding on the breakdown
        _rule(_col("volume"), ">", _sma(10),           weight=1.5),
        # RSI(7) < 45 — bearish momentum confirmed
        _rule(_rsi(7),  "<", _scalar(45),              weight=1.8),
        # MACD histogram deteriorating
        _rule(_macd_hist(5,13,3), "<",
              _macd_hist(5,13,3, shift=1),             weight=1.5),
    ),
})


# ─── EXIT_CALL — Bullish structure breaking down ──────────────────────────────

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [MS] Structure Breaks Down Exit",
    "rules": _s(
        # Price making a Lower Low — structure is cracking
        _rule(_low(),  "<", _low(shift=3),             weight=3.0),
        # And/or the previous Higher Low is violated
        _rule(_low(),  "<", _low(shift=5),             weight=2.5),
        # Close below EMA9 — micro-trend lost
        _rule(_close(), "<", _ema(9),                  weight=2.0),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [MS] HH Fails + Close Below HL Exit",
    "rules": _s(
        # Current high failed to make a new HH (Lower High forming)
        _rule(_high(), "<", _high(shift=3),            weight=2.5),
        # Close drops below the most recent Higher Low level
        _rule(_close(), "<", _low(shift=3),            weight=2.5),
        # RSI(7) rolling over
        _rule(_rsi(7), "<", _rsi(7, shift=1),         weight=1.5),
    ),
})

PRESETS["EXIT_CALL"].append({
    "name": "⚡ [MS] HL Violated Exit",
    "rules": _s(
        # Current low breaks below the previous Higher Low = HL violated
        _rule(_low(),  "<", _low(shift=5),             weight=3.0),
        # EMA9 crossed below EMA21
        _rule(_ema(9), "<", _ema(21),                  weight=2.5),
        # MACD turned negative
        _rule(_macd_hist(5,13,3), "<", _scalar(0),     weight=2.0),
    ),
})


# ─── EXIT_PUT — Bearish structure breaking down ───────────────────────────────

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [MS] Structure Breaks Up Exit",
    "rules": _s(
        # Price making a Higher High — structure is cracking
        _rule(_high(), ">", _high(shift=3),            weight=3.0),
        # And/or the previous Lower High is violated
        _rule(_high(), ">", _high(shift=5),            weight=2.5),
        # Close above EMA9 — micro-trend reversing
        _rule(_close(), ">", _ema(9),                  weight=2.0),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [MS] LL Fails + Close Above LH Exit",
    "rules": _s(
        # Current low failed to make a new LL (Higher Low forming)
        _rule(_low(),  ">", _low(shift=3),             weight=2.5),
        # Close bounces above the most recent Lower High level
        _rule(_close(), ">", _high(shift=3),           weight=2.5),
        # RSI(7) turning up
        _rule(_rsi(7), ">", _rsi(7, shift=1),         weight=1.5),
    ),
})

PRESETS["EXIT_PUT"].append({
    "name": "⚡ [MS] LH Violated Exit",
    "rules": _s(
        # Current high breaks above the previous Lower High = LH violated
        _rule(_high(), ">", _high(shift=5),            weight=3.0),
        # EMA9 crossed above EMA21
        _rule(_ema(9), ">", _ema(21),                  weight=2.5),
        # MACD turned positive
        _rule(_macd_hist(5,13,3), ">", _scalar(0),     weight=2.0),
    ),
})


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_preset_names(signal: str) -> List[str]:
    """Return all preset names for *signal*."""
    return [p["name"] for p in PRESETS.get(signal, [])]


def get_preset_rules(signal: str, name: str) -> List[dict]:
    """Return the rules list for a named preset ([] if not found)."""
    for p in PRESETS.get(signal, []):
        if p["name"] == name:
            return p["rules"]
    return []


def get_preset_with_weights(signal: str, name: str) -> List[dict]:
    """Return preset rules with guaranteed weight keys on every rule."""
    rules = get_preset_rules(signal, name)
    for rule in rules:
        rule.setdefault("weight", 1.0)
    return rules