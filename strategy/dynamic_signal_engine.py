"""
Dynamic Signal Engine Module
=============================
Database-backed DynamicSignalEngine for option trading that works with StrategyManager.

This module provides a flexible, rule-based signal generation engine for option trading.
It evaluates multiple technical indicators against configurable rules to produce
trading signals: BUY_CALL, BUY_PUT, EXIT_CALL, EXIT_PUT, HOLD, or WAIT.

FEATURE 3: Signal Confidence Voting System
------------------------------------------
The engine implements a sophisticated voting system:
    - Each rule has a weight (default 1.0)
    - Confidence = sum(passed_weights) / sum(total_weights) per signal group
    - Minimum confidence threshold (configurable) suppresses weak signals
    - Human-readable explanations of evaluation results

Version: 2.5.0 (Fixed position-based signal resolution with conflict handling)
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

# Import the centralized column generator
from strategy.indicator_columns import get_indicator_column, get_all_indicator_columns


class OptionSignal(str, Enum):
    """
    Enumeration of all possible trading signals.
    """
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


# List of all signal groups that can fire
SIGNAL_GROUPS = [OptionSignal.BUY_CALL, OptionSignal.BUY_PUT,
                 OptionSignal.EXIT_CALL, OptionSignal.EXIT_PUT,
                 OptionSignal.HOLD]

# Human-readable labels for UI display
SIGNAL_LABELS: Dict[str, str] = {
    "BUY_CALL": "📈  Buy Call", "BUY_PUT": "📉  Buy Put",
    "EXIT_CALL": "🔴  Exit Call", "EXIT_PUT": "🔵  Exit Put", "HOLD": "⏸   Hold",
}

# Color codes for UI theming
SIGNAL_COLORS: Dict[str, str] = {
    "BUY_CALL": "#a6e3a1", "BUY_PUT": "#89b4fa", "EXIT_CALL": "#f38ba8",
    "EXIT_PUT": "#fab387", "HOLD": "#f9e2af", "WAIT": "#585b70",
}

# Signal priorities for resolution (lower number = higher priority)
SIGNAL_PRIORITY = {
    "EXIT_CALL": 1,   # Highest priority when in CALL position
    "EXIT_PUT": 1,    # Highest priority when in PUT position
    "HOLD": 2,        # Hold has medium priority
    "BUY_CALL": 3,    # Entry signals have lowest priority when in position
    "BUY_PUT": 3,     # Entry signals have lowest priority when in position
    "WAIT": 4,        # Wait is lowest priority
}

# Supported operators for rule conditions
OPERATORS = [">", "<", ">=", "<=", "==", "!=", "crosses_above", "crosses_below"]

# Mapping from indicator names to pandas_ta function names
INDICATOR_MAP: Dict[str, str] = {
    "rsi": "rsi", "ema": "ema", "sma": "sma", "wma": "wma", "macd": "macd", "bbands": "bbands",
    "atr": "atr", "adx": "adx", "cci": "cci", "stoch": "stoch", "roc": "roc", "mom": "mom",
    "willr": "willr", "obv": "obv", "vwap": "vwap", "supertrend": "supertrend", "kc": "kc",
    "donchian": "donchian", "psar": "psar", "tema": "tema", "dema": "dema", "hma": "hma",
    "zlma": "zlma", "slope": "slope", "linreg": "linreg", "stochrsi": "stochrsi",
    "aroon": "aroon", "adosc": "adosc", "kvo": "kvo", "mfi": "mfi", "tsi": "tsi",
    "uo": "uo", "ao": "ao", "kama": "kama", "rvi": "rvi", "trix": "trix",
    "dm": "dm", "psl": "psl", "natr": "natr", "true_range": "true_range",
    "massi": "massi", "cmf": "cmf", "efi": "efi", "eom": "eom", "nvi": "nvi",
    "pvi": "pvi", "pvt": "pvt", "entropy": "entropy", "kurtosis": "kurtosis",
    "mad": "mad", "median": "median", "quantile": "quantile", "skew": "skew",
    "stdev": "stdev", "variance": "variance", "zscore": "zscore", "ichimoku": "ichimoku"
}

# Standard OHLCV column names expected in DataFrames
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

# Default parameters for each indicator type
INDICATOR_DEFAULTS: Dict[str, Dict[str, Any]] = {
    # Each entry must include ALL params the UI exposes so that the
    # type-coercion pass in _compute_indicator has a reference type.
    # Missing entries cause string params to slip through as-is → TypeError.
    "rsi":       {"length": 14, "scalar": 100.0, "drift": 1},
    "ema":       {"length": 20, "offset": 0},
    "sma":       {"length": 20, "offset": 0},
    "wma":       {"length": 20, "offset": 0},
    "hma":       {"length": 20, "offset": 0},
    "dema":      {"length": 20, "offset": 0},
    "tema":      {"length": 20, "offset": 0},
    "zlma":      {"length": 20, "offset": 0},
    "macd":      {"fast": 12, "slow": 26, "signal": 9},
    "bbands":    {"length": 20, "std": 2.0, "ddof": 0, "offset": 0},
    "atr":       {"length": 14, "drift": 1, "offset": 0},
    "natr":      {"length": 14, "drift": 1, "offset": 0},
    "adx":       {"length": 14, "drift": 1},
    "cci":       {"length": 20, "c": 0.015, "drift": 1},
    "stoch":     {"k": 14, "d": 3, "smooth_k": 3, "drift": 1},
    "stochrsi":  {"length": 14, "rsi_length": 14, "k": 3, "d": 3},
    "roc":       {"length": 10},
    "mom":       {"length": 10, "drift": 1},
    "willr":     {"length": 14},
    "obv":       {},
    "vwap":      {},
    "supertrend":{"length": 7, "multiplier": 3.0, "drift": 1},
    "kc":        {"length": 20, "scalar": 1.5, "tr": True, "offset": 0},
    "donchian":  {"lower_length": 20, "upper_length": 20, "offset": 0},
    "psar":      {"af0": 0.02, "af": 0.02, "max_af": 0.2},
    "slope":     {"length": 1, "offset": 0},
    "linreg":    {"length": 14, "offset": 0},
    "aroon":     {"length": 14, "offset": 0},
    "adosc":     {"fast": 3, "slow": 10, "offset": 0},
    "kvo":       {"fast": 34, "slow": 55, "signal": 13},
    "mfi":       {"length": 14, "drift": 1},
    "tsi":       {"fast": 13, "slow": 25, "drift": 1},
    "uo":        {"fast": 7, "medium": 14, "slow": 28, "fast_w": 4.0, "medium_w": 2.0, "slow_w": 1.0, "drift": 1},
    "ao":        {"fast": 5, "slow": 34},
    "kama":      {"length": 10, "fast": 2, "slow": 30, "drift": 1},
    "rvi":       {"length": 14, "scalar": 100.0, "drift": 1, "offset": 0},
    "trix":      {"length": 15, "scalar": 100.0, "drift": 1},
    "dm":        {"length": 14, "drift": 1},
    "psl":       {"length": 12, "drift": 1},
    "true_range":{},
    "massi":     {"fast": 9, "slow": 25},
    "cmf":       {"length": 20, "offset": 0},
    "efi":       {"length": 13, "drift": 1, "offset": 0},
    "eom":       {"length": 14, "divisor": 100000000, "drift": 1, "offset": 0},
    "nvi":       {"length": 1, "initial": 1000, "offset": 0},
    "pvi":       {"length": 1, "initial": 1000, "offset": 0},
    "pvt":       {"drift": 1, "offset": 0},
    "entropy":   {"length": 10, "offset": 0},
    "kurtosis":  {"length": 30, "offset": 0},
    "mad":       {"length": 30, "offset": 0},
    "median":    {"length": 30, "offset": 0},
    "quantile":  {"length": 30, "q": 0.5, "offset": 0},
    "skew":      {"length": 30, "offset": 0},
    "stdev":     {"length": 30, "ddof": 1, "offset": 0},
    "variance":  {"length": 30, "ddof": 1, "offset": 0},
    "zscore":    {"length": 30, "ddof": 1, "offset": 0},
    "ichimoku":  {"tenkan": 9, "kijun": 26, "senkou": 52},
}

# Minimum required data points for each indicator type
INDICATOR_MIN_PERIODS: Dict[str, int] = {
    "rsi": 14, "ema": 1, "sma": 1, "wma": 1, "macd": 33,
    "bbands": 20, "atr": 14, "adx": 14, "cci": 20,
    "stoch": 14, "roc": 10, "mom": 10, "willr": 14,
    "supertrend": 10, "kc": 20, "donchian": 20,
    "psar": 2, "tema": 20, "dema": 20, "hma": 20,
    "zlma": 20, "linreg": 14, "stochrsi": 14,
    "aroon": 14, "adosc": 10, "kvo": 55,
    "mfi": 14, "tsi": 25, "uo": 28, "ao": 34,
    "kama": 30, "rvi": 14, "trix": 15, "dm": 14,
    "psl": 12, "natr": 14, "massi": 25,
    "cmf": 20, "efi": 13, "eom": 14,
    "entropy": 10, "kurtosis": 30, "mad": 30,
    "median": 30, "quantile": 30, "skew": 30,
    "stdev": 30, "variance": 30, "zscore": 30,
    "ichimoku": 52,
}

# Multi-column indicators that need special handling
MULTI_COLUMN_INDICATORS = [
    'macd', 'bbands', 'stoch', 'stochrsi', 'supertrend', 'kc', 'donchian',
    'adx', 'aroon', 'dm', 'adosc', 'kvo', 'ichimoku'
]

# Indicator categories for column requirements
NEEDS_CLOSE_ONLY = ['rsi', 'ema', 'sma', 'wma', 'tema', 'dema', 'hma', 'zlma',
                    'roc', 'mom', 'willr', 'linreg', 'slope', 'kama', 'rvi', 'trix']
NEEDS_HIGH_LOW = ['atr', 'natr', 'true_range', 'massi']
NEEDS_HIGH_LOW_CLOSE = ['adx', 'supertrend', 'kc', 'donchian', 'stoch', 'stochrsi',
                        'aroon', 'dm', 'uo', 'ao', 'psar', 'vwap']
NEEDS_VOLUME = ['obv', 'ad', 'adosc', 'cmf', 'efi', 'eom', 'kvo', 'mfi', 'nvi', 'pvi', 'pvt']


def _get_required_columns(indicator: str) -> List[str]:
    """
    Get the required OHLCV columns for an indicator.

    Args:
        indicator: Indicator name

    Returns:
        List of required column names
    """
    indicator_lower = indicator.lower()

    if indicator_lower in NEEDS_CLOSE_ONLY:
        return ['close']
    elif indicator_lower in NEEDS_HIGH_LOW:
        return ['high', 'low']
    elif indicator_lower in NEEDS_HIGH_LOW_CLOSE:
        return ['high', 'low', 'close']
    elif indicator_lower in NEEDS_VOLUME:
        if indicator_lower == 'obv':
            return ['close', 'volume']
        elif indicator_lower in ['ad', 'adosc']:
            return ['high', 'low', 'close', 'volume']
        else:
            return ['close', 'volume']
    elif indicator_lower == 'macd':
        return ['close']
    elif indicator_lower == 'bbands':
        return ['close']
    elif indicator_lower == 'ichimoku':
        return ['high', 'low', 'close']
    elif indicator_lower == 'psar':
        return ['high', 'low']
    elif indicator_lower == 'cci':
        return ['high', 'low', 'close']
    else:
        # Default to close for unknown indicators
        return ['close']


def _get_min_periods(indicator: str, params: Dict[str, Any]) -> int:
    """
    Get the minimum number of data points required for an indicator.

    Args:
        indicator: Indicator name
        params: Indicator parameters

    Returns:
        Minimum required periods
    """
    indicator_lower = indicator.lower()

    # Check if we have a specific min periods defined
    if indicator_lower in INDICATOR_MIN_PERIODS:
        base_periods = INDICATOR_MIN_PERIODS[indicator_lower]
    else:
        base_periods = 1

    # Adjust based on parameters
    if 'length' in params:
        return max(base_periods, params['length'] + 5)  # Add buffer for stability
    elif 'slow' in params:
        return max(base_periods, params['slow'] + 5)  # Add buffer for stability
    elif 'kijun' in params:  # Ichimoku
        return max(base_periods, params.get('senkou', 52) + 5)
    else:
        return base_periods + 5  # Add buffer for all indicators


def _extract_indicator_column(result_df: pd.DataFrame, indicator: str, params: Dict[str, Any]) -> Optional[pd.Series]:
    """
    Extract the appropriate column from a multi-column indicator result with dynamic column names.

    Args:
        result_df: DataFrame returned by pandas_ta
        indicator: Original indicator name
        params: Indicator parameters used for calculation

    Returns:
        Optional[pd.Series]: Extracted series or None
    """
    try:
        indicator_lower = indicator.lower()

        # For multi-column indicators, get all possible column names
        if indicator_lower in MULTI_COLUMN_INDICATORS:
            columns = get_all_indicator_columns(indicator, params)

            # Try each column type in order of preference
            preferred_order = {
                'macd': ['MACD', 'SIGNAL', 'HIST'],
                'bbands': ['MIDDLE', 'UPPER', 'LOWER', 'BANDWIDTH', 'PERCENT'],
                'stoch': ['K', 'D'],
                'stochrsi': ['K', 'D'],
                'supertrend': ['TREND', 'DIRECTION', 'LONG', 'SHORT'],
                'kc': ['MIDDLE', 'UPPER', 'LOWER'],
                'donchian': ['MIDDLE', 'UPPER', 'LOWER'],
                'adx': ['ADX', 'PLUS_DI', 'MINUS_DI'],
                'aroon': ['AROON_UP', 'AROON_DOWN'],
                'dm': ['PLUS_DM', 'MINUS_DM'],
                'adosc': ['ADOSC', 'AD'],
                'kvo': ['KVO', 'SIGNAL'],
                'ichimoku': ['ISA', 'ISB', 'ITS', 'IKS', 'ICS'],
            }

            order = preferred_order.get(indicator_lower, [])
            for col_type in order:
                col_name = columns.get(col_type)
                if col_name and col_name in result_df.columns:
                    series = result_df[col_name]
                    # Check if the series has any non-NaN values
                    if series is not None and not series.isna().all():
                        return series

            # If preferred not found, try any column that exists
            for col_name in columns.values():
                if col_name in result_df.columns:
                    series = result_df[col_name]
                    if series is not None and not series.isna().all():
                        return series

        # For single column indicators, try the generated name
        col_name = get_indicator_column(indicator, params)
        if col_name in result_df.columns:
            series = result_df[col_name]
            if series is not None and not series.isna().all():
                return series

        # Fallback to pattern matching
        for col in result_df.columns:
            col_upper = col.upper()
            series = result_df[col]
            if series is None or series.isna().all():
                continue

            if indicator_lower == 'macd' and ('MACD' in col_upper) and ('SIGNAL' not in col_upper) and ('HIST' not in col_upper):
                return series
            elif indicator_lower == 'bbands' and ('BBM' in col_upper or 'MID' in col_upper):
                return series
            elif indicator_lower == 'stoch' and ('STOCHK' in col_upper or '%K' in col_upper):
                return series
            elif indicator_lower == 'supertrend' and ('SUPERT' in col_upper) and ('d' not in col_upper):
                return series
            elif indicator_lower == 'kc' and ('KCB' in col_upper or 'MID' in col_upper):
                return series
            elif indicator_lower == 'donchian' and ('DCM' in col_upper or 'MID' in col_upper):
                return series
            elif indicator_lower == 'adx' and ('ADX' in col_upper) and ('DMP' not in col_upper) and ('DMN' not in col_upper):
                return series
            elif indicator_lower == 'aroon' and ('AROONU' in col_upper):
                return series
            elif indicator_lower == 'adosc' and ('ADOSC' in col_upper):
                return series
            elif indicator_lower == 'kvo' and ('KVO' in col_upper) and ('S' not in col_upper):
                return series
            elif indicator_lower == 'ichimoku' and ('ISA' in col_upper):
                return series

        # Last resort: return first numeric column with non-NaN values
        for col in result_df.columns:
            if pd.api.types.is_numeric_dtype(result_df[col]):
                series = result_df[col]
                if not series.isna().all():
                    return series

        return None

    except Exception as e:
        logger.error(f"[_extract_indicator_column] Failed for {indicator}: {e}", exc_info=True)
        return None


def _compute_indicator(df: pd.DataFrame, indicator: str, params: Dict[str, Any]) -> Optional[pd.Series]:
    """
    Compute technical indicator with comprehensive error handling.

    Args:
        df: OHLCV DataFrame
        indicator: Indicator name (e.g., "rsi", "ema")
        params: Parameters for the indicator

    Returns:
        Optional[pd.Series]: Indicator values, or None if computation fails
    """
    try:
        if ta is None:
            logger.warning("pandas_ta not available, cannot compute indicator")
            return None

        if df is None or df.empty:
            logger.warning(f"Cannot compute {indicator}: DataFrame is None or empty")
            return None

        # ── FIX 1: merge caller params with INDICATOR_DEFAULTS ──────────
        # Ensures pandas_ta always gets a complete parameter set even when
        # the strategy JSON was saved with params={} (empty dict).
        _defaults = INDICATOR_DEFAULTS.get(indicator.lower(), {})
        params = {**_defaults, **params} if params is not None else dict(_defaults)

        # ── FIX 2: coerce string param values to their correct types ─────
        # The UI stores params as strings when get_param_type() falls back
        # to 'string' (e.g. ddof='0', drift='1', offset='0'). pandas_ta
        # expects native int/float — str causes TypeError on >= comparisons.
        _coerced = {}
        for _k, _v in params.items():
            _dv = _defaults.get(_k)
            if _v is None or _dv is None or not isinstance(_v, str) or isinstance(_dv, str):
                _coerced[_k] = _v
            else:
                try:
                    if isinstance(_dv, bool):   _coerced[_k] = _v.lower() in ('true','1','yes')
                    elif isinstance(_dv, int):  _coerced[_k] = int(float(_v))
                    elif isinstance(_dv, float):_coerced[_k] = float(_v)
                    else:                        _coerced[_k] = _v
                except (ValueError, TypeError):
                    logger.warning(f"[_compute_indicator] Cannot coerce '{_k}'={_v!r} "
                                   f"to {type(_dv).__name__} for '{indicator}' — using default {_dv!r}")
                    _coerced[_k] = _dv
        params = _coerced

        # Check if we have required columns
        required_cols = _get_required_columns(indicator)
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.warning(f"Cannot compute {indicator}: Missing required columns {missing_cols}")
            return None

        # Check if we have enough data for this indicator
        min_periods = _get_min_periods(indicator, params)
        if len(df) < min_periods:
            logger.debug(f"Insufficient data for {indicator}: need {min_periods}, have {len(df)} - returning None during warmup")
            return None

        ind_name = INDICATOR_MAP.get(indicator.lower(), indicator.lower())

        try:
            method = getattr(ta, ind_name, None)
            if not method:
                logger.warning(f"Indicator method '{ind_name}' not found in pandas_ta")
                return None

            # Prepare kwargs based on indicator requirements
            kwargs = {}

            # ── FIX 3: pass full series (index intact) to pandas_ta ───────
            # dropna() breaks index continuity, causing pandas_ta internal
            # arithmetic (e.g. macd - signalma) to produce scalar None
            # instead of NaN → TypeError. Validate count without stripping.
            required_cols = _get_required_columns(indicator)
            for col in required_cols:
                if col in df.columns:
                    series = df[col]
                    non_nan_count = series.notna().sum()
                    if non_nan_count < min_periods:
                        logger.debug(f"Insufficient clean data for {indicator} column {col}: "
                                     f"need {min_periods}, have {non_nan_count}")
                        return None
                    kwargs[col] = series

            # Add parameters
            kwargs.update(params)

            # Remove None values
            kwargs = {k: v for k, v in kwargs.items() if v is not None}

            # Validate we have required data
            if 'close' in required_cols and 'close' not in kwargs:
                logger.warning(f"Cannot compute {indicator}: close price required but not available")
                return None

            # Compute indicator
            result = method(**kwargs)

            if result is None:
                logger.debug(f"Indicator {indicator} returned None - insufficient data during warmup")
                return None

            # Extract appropriate column from multi-column result
            if isinstance(result, pd.DataFrame):
                series = _extract_indicator_column(result, indicator, params)
                if series is not None and not series.isna().all():
                    series = series.reindex(df.index)
                    return series
                else:
                    logger.debug(f"Indicator {indicator} returned all NaN values - still in warmup period")
                    return None

            elif isinstance(result, pd.Series):
                if not result.isna().all():
                    # Reindex to match original DataFrame index
                    result = result.reindex(df.index)
                    return result
                else:
                    logger.debug(f"Indicator {indicator} returned all NaN values - still in warmup period")
                    return None

            else:
                logger.warning(f"Unexpected result type from {indicator}: {type(result)}")
                return None

        except AttributeError as e:
            logger.error(f"Attribute error computing '{indicator}': {e}", exc_info=True)
            return None
        except TypeError as e:
            logger.error(f"Type error computing '{indicator}': {e}. This often indicates missing required price data or NaN values.", exc_info=True)
            return None
        except ValueError as e:
            logger.error(f"Value error computing '{indicator}': {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Error computing '{indicator}': {e}", exc_info=True)
            return None

    except Exception as e:
        logger.error(f"[_compute_indicator] Failed for {indicator}: {e}", exc_info=True)
        return None


def _resolve_side(df: pd.DataFrame, side_def: Dict[str, Any], cache: Dict[str, Any]) -> Optional[pd.Series]:
    """
    Resolve a side (LHS/RHS) of a rule to a pandas Series with shift support.

    Side definitions can be:
        - Scalar: Constant value
        - Column: Direct column from DataFrame
        - Indicator: Computed technical indicator

    Args:
        df: OHLCV DataFrame
        side_def: Side definition dictionary
        cache: Cache for computed indicators to avoid recalculation

    Returns:
        Optional[pd.Series]: Series of values, or None if resolution fails
    """
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
            shift = side_def.get("shift", 0)

            if col not in df.columns:
                logger.warning(f"Column '{col}' not found in DataFrame")
                return None

            try:
                series = df[col].astype(float)
                if shift > 0:
                    series = series.shift(shift)
                return series
            except Exception as e:
                logger.warning(f"Error processing column {col}: {e}")
                return None

        # Indicator type
        indicator = side_def.get("indicator", "").lower()
        if not indicator:
            logger.warning("Indicator side definition missing 'indicator' field")
            return None

        # Merge saved params with defaults — dict.get() returns {} when the
        # key exists but is empty, so the fallback never fires without this.
        _saved = side_def.get("params", {})
        _defs  = INDICATOR_DEFAULTS.get(indicator, {})
        params = {**_defs, **_saved} if _saved else dict(_defs)
        shift = side_def.get("shift", 0)

        # Create cache key for performance
        try:
            cache_key = f"{indicator}_{json.dumps(params, sort_keys=True)}_{shift}"
        except Exception as e:
            logger.warning(f"Failed to create cache key: {e}")
            cache_key = f"{indicator}_{str(params)}_{shift}"

        if cache_key not in cache:
            cache[cache_key] = _compute_indicator(df, indicator, params)

        series = cache.get(cache_key)
        if series is not None and shift > 0:
            series = series.shift(shift)

        return series

    except Exception as e:
        logger.error(f"[_resolve_side] Failed: {e}", exc_info=True)
        return None


def _apply_operator(lhs: pd.Series, op: str, rhs: pd.Series) -> Tuple[bool, Optional[float], Optional[float]]:
    """
    Apply comparison operator to two series with NaN handling.

    Args:
        lhs: Left-hand side series
        op: Operator string (>, <, >=, <=, ==, !=, crosses_above, crosses_below)
        rhs: Right-hand side series

    Returns:
        Tuple[bool, Optional[float], Optional[float]]:
            - Result of comparison (False if any value is NaN)
            - Last value of LHS (if available)
            - Last value of RHS (if available)
    """
    try:
        if lhs is None or rhs is None:
            logger.warning(f"Operator '{op}' called with None series")
            return False, None, None

        # Ensure we have enough data
        if len(lhs) < 1 or len(rhs) < 1:
            return False, None, None

        # Handle crossover operators which need 2 bars
        if op == "crosses_above":
            if len(lhs) < 2 or len(rhs) < 2:
                return False, None, None
            try:
                # Get last two values, checking for NaN
                lhs_prev = lhs.iloc[-2] if not pd.isna(lhs.iloc[-2]) else None
                lhs_curr = lhs.iloc[-1] if not pd.isna(lhs.iloc[-1]) else None
                rhs_prev = rhs.iloc[-2] if not pd.isna(rhs.iloc[-2]) else None
                rhs_curr = rhs.iloc[-1] if not pd.isna(rhs.iloc[-1]) else None

                # If any value is NaN, cannot determine crossover
                if None in [lhs_prev, lhs_curr, rhs_prev, rhs_curr]:
                    return False, lhs_curr, rhs_curr

                # Convert to float
                lhs_prev_f = float(lhs_prev)
                lhs_curr_f = float(lhs_curr)
                rhs_prev_f = float(rhs_prev)
                rhs_curr_f = float(rhs_curr)

                result = (lhs_prev_f <= rhs_prev_f) and (lhs_curr_f > rhs_curr_f)
                return result, round(lhs_curr_f, 6), round(rhs_curr_f, 6)
            except (ValueError, TypeError, IndexError) as e:
                logger.warning(f"Error in crosses_above: {e}")
                return False, None, None

        if op == "crosses_below":
            if len(lhs) < 2 or len(rhs) < 2:
                return False, None, None
            try:
                lhs_prev = lhs.iloc[-2] if not pd.isna(lhs.iloc[-2]) else None
                lhs_curr = lhs.iloc[-1] if not pd.isna(lhs.iloc[-1]) else None
                rhs_prev = rhs.iloc[-2] if not pd.isna(rhs.iloc[-2]) else None
                rhs_curr = rhs.iloc[-1] if not pd.isna(rhs.iloc[-1]) else None

                if None in [lhs_prev, lhs_curr, rhs_prev, rhs_curr]:
                    return False, lhs_curr, rhs_curr

                lhs_prev_f = float(lhs_prev)
                lhs_curr_f = float(lhs_curr)
                rhs_prev_f = float(rhs_prev)
                rhs_curr_f = float(rhs_curr)

                result = (lhs_prev_f >= rhs_prev_f) and (lhs_curr_f < rhs_curr_f)
                return result, round(lhs_curr_f, 6), round(rhs_curr_f, 6)
            except (ValueError, TypeError, IndexError) as e:
                logger.warning(f"Error in crosses_below: {e}")
                return False, None, None

        # Handle regular comparison operators
        try:
            lhs_val = lhs.iloc[-1] if not pd.isna(lhs.iloc[-1]) else None
            rhs_val = rhs.iloc[-1] if not pd.isna(rhs.iloc[-1]) else None
        except (ValueError, TypeError, IndexError) as e:
            logger.warning(f"Failed to get last values: {e}")
            return False, None, None

        # If either value is NaN, comparison is False
        if lhs_val is None or rhs_val is None:
            return False, lhs_val, rhs_val

        # Convert to float for comparison
        try:
            lhs_float = float(lhs_val)
            rhs_float = float(rhs_val)
        except (ValueError, TypeError):
            return False, lhs_val, rhs_val

        if np.isnan(lhs_float) or np.isnan(rhs_float):
            return False, lhs_val, rhs_val

        operators = {
            ">": lhs_float > rhs_float,
            "<": lhs_float < rhs_float,
            ">=": lhs_float >= rhs_float,
            "<=": lhs_float <= rhs_float,
            "==": abs(lhs_float - rhs_float) < 1e-9,
            "!=": abs(lhs_float - rhs_float) >= 1e-9
        }

        result = operators.get(op, False)
        return result, round(lhs_float, 6), round(rhs_float, 6)

    except Exception as e:
        logger.error(f"Operator error '{op}': {e}", exc_info=True)
        return False, None, None


def _rule_to_string(rule: Dict[str, Any]) -> str:
    """
    Convert rule dictionary to human-readable string.

    FEATURE 3: Includes rule weight in string representation.

    Args:
        rule: Rule dictionary with lhs, op, rhs, and optional weight

    Returns:
        str: Human-readable rule description
    """
    try:
        if rule is None:
            return "Invalid rule"

        def s(d):
            if d is None:
                return "?"
            t = d.get("type", "indicator")
            if t == "scalar":
                val = d.get("value", "?")
                return f"{val}"
            if t == "column":
                col = d.get("column", "?")
                shift = d.get("shift", 0)
                return f"{col.upper()}" + (f"[{shift}]" if shift > 0 else "")
            ind = d.get("indicator", "?")
            p = ", ".join(f"{k}={v}" for k, v in d.get("params", {}).items())
            shift = d.get("shift", 0)
            base = f"{ind.upper()}({p})" if p else ind.upper()
            return base + (f"[{shift}]" if shift > 0 else "")

        lhs = s(rule.get('lhs', {}))
        op = rule.get('op', '?')
        rhs = s(rule.get('rhs', {}))

        # FEATURE 3: Add weight to string representation
        weight = rule.get('weight', 1.0)
        if weight != 1.0:
            return f"{lhs} {op} {rhs} (w={weight:.1f})"
        return f"{lhs} {op} {rhs}"

    except Exception as e:
        logger.error(f"[_rule_to_string] Failed: {e}", exc_info=True)
        return "Error parsing rule"


class DynamicSignalEngine:
    """
    Dynamic signal engine that uses strategy configuration from StrategyManager.

    Each instance is tied to a specific strategy slug and evaluates rules against
    OHLCV data to generate trading signals. The engine supports:
        - Multiple signal groups (BUY_CALL, BUY_PUT, etc.)
        - Configurable rules with logical operators (AND/OR)
        - Technical indicators from pandas_ta
        - FEATURE 3: Rule weights and confidence scoring
        - FEATURE 3: Minimum confidence threshold
        - FEATURE 3: Human-readable explanations
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

            # FEATURE 3: Default confidence threshold
            self.min_confidence = 0.6

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
            self.min_confidence = 0.6

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._last_cache = None
        self.strategy_slug = None
        self.conflict_resolution = "WAIT"
        self.min_confidence = 0.6
        self.config = {}
        self._manager = None

    def _key(self, signal: Union[str, OptionSignal]) -> str:
        """
        Get configuration key for a signal.

        Args:
            signal: Signal as string or OptionSignal enum

        Returns:
            str: String key for config dictionary
        """
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

                        # FEATURE 3: Ensure each rule has a weight
                        for rule in rules:
                            if "weight" not in rule:
                                rule["weight"] = 1.0

                        self.config[k]["rules"] = list(rules) if isinstance(rules, list) else []
                        self.config[k]["enabled"] = bool(engine_config[k].get("enabled", True))
                    except Exception as e:
                        logger.warning(f"Failed to load config for {k}: {e}")

            # Load conflict resolution
            if "conflict_resolution" in engine_config:
                self.conflict_resolution = str(engine_config["conflict_resolution"]).upper()

            # FEATURE 3: Load min confidence
            if "min_confidence" in engine_config:
                try:
                    self.min_confidence = float(engine_config["min_confidence"])
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid min_confidence value: {e}")

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
            strategy["engine"]["min_confidence"] = self.min_confidence

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
        """
        Convert configuration to dictionary.

        Returns:
            Dict[str, Any]: Configuration dictionary suitable for saving
        """
        try:
            return {k: {"logic": v["logic"], "rules": list(v["rules"]), "enabled": v["enabled"]}
                    for k, v in self.config.items()}
        except Exception as e:
            logger.error(f"[to_dict] Failed: {e}", exc_info=True)
            return {}

    def from_dict(self, d: Dict[str, Any]) -> None:
        """
        Load configuration from dictionary.

        Args:
            d: Configuration dictionary
        """
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

                        # FEATURE 3: Ensure each rule has a weight
                        for rule in rules:
                            if "weight" not in rule:
                                rule["weight"] = 1.0

                        self.config[k]["rules"] = list(rules) if isinstance(rules, list) else []
                        self.config[k]["enabled"] = bool(d[k].get("enabled", True))
                    except Exception as e:
                        logger.warning(f"Failed to load config for {k}: {e}")

            if "conflict_resolution" in d:
                self.conflict_resolution = str(d["conflict_resolution"]).upper()

            # FEATURE 3: Load min confidence
            if "min_confidence" in d:
                try:
                    self.min_confidence = float(d["min_confidence"])
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid min_confidence value: {e}")

        except Exception as e:
            logger.error(f"[from_dict] Failed: {e}", exc_info=True)

    def add_rule(self, signal: Union[str, OptionSignal], rule: Dict[str, Any]) -> bool:
        """
        Add a rule to a signal group.

        Args:
            signal: Target signal group
            rule: Rule dictionary with lhs, op, rhs, and optional weight

        Returns:
            bool: True if rule added successfully
        """
        try:
            k = self._key(signal)
            if k not in self.config:
                logger.warning(f"Signal {k} not found in config")
                return False

            if rule is None:
                logger.warning("Cannot add None rule")
                return False

            # FEATURE 3: Ensure rule has weight
            if "weight" not in rule:
                rule["weight"] = 1.0

            self.config[k]["rules"].append(rule)
            logger.debug(f"Added rule to {k}")
            return True

        except Exception as e:
            logger.error(f"[add_rule] Failed for {signal}: {e}", exc_info=True)
            return False

    def remove_rule(self, signal: Union[str, OptionSignal], index: int) -> bool:
        """
        Remove a rule by index.

        Args:
            signal: Target signal group
            index: Rule index to remove

        Returns:
            bool: True if rule removed successfully
        """
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
        """
        Update a rule by index.

        Args:
            signal: Target signal group
            index: Rule index to update
            rule: New rule definition

        Returns:
            bool: True if rule updated successfully
        """
        try:
            k = self._key(signal)
            rules = self.config.get(k, {}).get("rules", [])
            if 0 <= index < len(rules) and rule is not None:
                # FEATURE 3: Preserve weight if not specified
                if "weight" not in rule and "weight" in rules[index]:
                    rule["weight"] = rules[index]["weight"]
                elif "weight" not in rule:
                    rule["weight"] = 1.0

                rules[index] = rule
                logger.debug(f"Updated rule {index} in {k}")
                return True
            return False

        except Exception as e:
            logger.error(f"[update_rule] Failed for {signal}: {e}", exc_info=True)
            return False

    def get_rules(self, signal: Union[str, OptionSignal]) -> List[Dict[str, Any]]:
        """
        Get all rules for a signal.

        Args:
            signal: Target signal group

        Returns:
            List[Dict[str, Any]]: List of rule dictionaries
        """
        try:
            k = self._key(signal)
            return list(self.config.get(k, {}).get("rules", []))
        except Exception as e:
            logger.error(f"[get_rules] Failed for {signal}: {e}", exc_info=True)
            return []

    def set_logic(self, signal: Union[str, OptionSignal], logic: str) -> None:
        """
        Set logic (AND/OR) for a signal group.

        Args:
            signal: Target signal group
            logic: "AND" or "OR"
        """
        try:
            k = self._key(signal)
            if k in self.config and logic.upper() in ("AND", "OR"):
                self.config[k]["logic"] = logic.upper()
                logger.debug(f"Set logic for {k} to {logic}")
        except Exception as e:
            logger.error(f"[set_logic] Failed for {signal}: {e}", exc_info=True)

    def get_logic(self, signal: Union[str, OptionSignal]) -> str:
        """
        Get logic for a signal group.

        Args:
            signal: Target signal group

        Returns:
            str: "AND" or "OR"
        """
        try:
            k = self._key(signal)
            return self.config.get(k, {}).get("logic", "AND")
        except Exception as e:
            logger.error(f"[get_logic] Failed for {signal}: {e}", exc_info=True)
            return "AND"

    def set_enabled(self, signal: Union[str, OptionSignal], enabled: bool) -> None:
        """
        Enable/disable a signal group.

        Args:
            signal: Target signal group
            enabled: True to enable, False to disable
        """
        try:
            k = self._key(signal)
            if k in self.config:
                self.config[k]["enabled"] = bool(enabled)
                logger.debug(f"Set enabled for {k} to {enabled}")
        except Exception as e:
            logger.error(f"[set_enabled] Failed for {signal}: {e}", exc_info=True)

    def is_enabled(self, signal: Union[str, OptionSignal]) -> bool:
        """
        Check if a signal group is enabled.

        Args:
            signal: Target signal group

        Returns:
            bool: True if enabled
        """
        try:
            k = self._key(signal)
            return bool(self.config.get(k, {}).get("enabled", True))
        except Exception as e:
            logger.error(f"[is_enabled] Failed for {signal}: {e}", exc_info=True)
            return True

    # FEATURE 3: Rule weight management
    def set_rule_weight(self, signal: Union[str, OptionSignal], index: int, weight: float) -> bool:
        """
        Set weight for a specific rule.

        Args:
            signal: Target signal group
            index: Rule index
            weight: New weight value

        Returns:
            bool: True if weight set successfully
        """
        try:
            k = self._key(signal)
            rules = self.config.get(k, {}).get("rules", [])
            if 0 <= index < len(rules):
                rules[index]["weight"] = float(weight)
                logger.debug(f"Set weight for rule {index} in {k} to {weight}")
                return True
            return False
        except Exception as e:
            logger.error(f"[set_rule_weight] Failed for {signal}: {e}", exc_info=True)
            return False

    def get_rule_weight(self, signal: Union[str, OptionSignal], index: int) -> float:
        """
        Get weight for a specific rule.

        Args:
            signal: Target signal group
            index: Rule index

        Returns:
            float: Rule weight (default 1.0)
        """
        try:
            k = self._key(signal)
            rules = self.config.get(k, {}).get("rules", [])
            if 0 <= index < len(rules):
                return float(rules[index].get("weight", 1.0))
            return 1.0
        except Exception as e:
            logger.error(f"[get_rule_weight] Failed for {signal}: {e}", exc_info=True)
            return 1.0

    def rule_descriptions(self, signal: Union[str, OptionSignal]) -> List[str]:
        """
        Get human-readable rule descriptions with weights.

        Args:
            signal: Target signal group

        Returns:
            List[str]: List of rule descriptions
        """
        try:
            k = self._key(signal)
            return [_rule_to_string(r) for r in self.config.get(k, {}).get("rules", [])]
        except Exception as e:
            logger.error(f"[rule_descriptions] Failed for {signal}: {e}", exc_info=True)
            return []

    def _evaluate_group(self, signal: Union[str, OptionSignal], df: pd.DataFrame,
                        cache: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]], float, float]:
        """
        Evaluate a single signal group.

        FEATURE 3: Returns confidence score and total weight.

        Args:
            signal: Signal group to evaluate
            df: OHLCV DataFrame
            cache: Indicator cache

        Returns:
            Tuple[bool, List[Dict], float, float]:
                - fired: Whether group fired
                - rule_results: Detailed results per rule
                - confidence: Confidence score (0-1)
                - total_weight: Sum of all rule weights
        """
        try:
            k = self._key(signal)
            group = self.config.get(k, {})

            if not group.get("enabled", True):
                return False, [], 0.0, 0.0

            logic = group.get("logic", "AND").upper()
            rules = group.get("rules", [])

            if not rules:
                return False, [], 0.0, 0.0

            # For AND logic, start with True; for OR logic, start with False
            group_result = (logic == "AND")
            rule_results = []

            total_weight = 0.0
            passed_weight = 0.0
            rules_evaluated = 0

            for rule in rules:
                try:
                    # Get rule weight (FEATURE 3)
                    weight = float(rule.get("weight", 1.0))
                    total_weight += weight

                    rule_str = _rule_to_string(rule)

                    lhs_series = _resolve_side(df, rule.get("lhs", {}), cache)
                    rhs_series = _resolve_side(df, rule.get("rhs", {}), cache)

                    if lhs_series is None or rhs_series is None:
                        result, lhs_val, rhs_val = False, None, None
                        logger.debug(f"Rule {rule_str}: failed to resolve sides")
                    else:
                        result, lhs_val, rhs_val = _apply_operator(lhs_series, rule.get("op", ">"), rhs_series)
                        rules_evaluated += 1

                    if result:
                        passed_weight += weight

                    def _fmt(v):
                        if v is None: return "N/A"
                        return f"{v:.4f}" if isinstance(v, float) else str(v)

                    entry = {
                        "rule": rule_str,
                        "result": result,
                        "lhs_value": lhs_val,
                        "rhs_value": rhs_val,
                        "weight": weight,
                        "detail": f"{_fmt(lhs_val)} {rule.get('op', '?')} {_fmt(rhs_val)} → {'✓' if result else '✗'}",
                    }
                    rule_results.append(entry)

                    # Update group result based on logic
                    if logic == "AND":
                        group_result = group_result and result
                    else:  # OR logic
                        group_result = group_result or result

                except Exception as e:
                    logger.error(f"Rule eval error: {e}", exc_info=True)
                    rule_results.append({
                        "rule": _rule_to_string(rule),
                        "result": False,
                        "lhs_value": None,
                        "rhs_value": None,
                        "weight": rule.get("weight", 1.0),
                        "detail": f"ERROR: {e}",
                        "error": str(e)
                    })
                    # For AND logic, any error means group doesn't fire
                    if logic == "AND":
                        group_result = False

            # Calculate confidence based on successfully evaluated rules
            if rules_evaluated > 0:
                confidence = passed_weight / total_weight if total_weight > 0 else 0.0
            else:
                confidence = 0.0
                group_result = False  # No rules could be evaluated

            return group_result, rule_results, confidence, total_weight

        except Exception as e:
            logger.error(f"[_evaluate_group] Failed for {signal}: {e}", exc_info=True)
            return False, [], 0.0, 0.0

    def evaluate(self, df: pd.DataFrame, current_position: Optional[str] = None) -> Dict[str, Any]:
        """
        FEATURE 3: Enhanced evaluation with confidence scoring and position-based resolution.

        Evaluates all signal groups against the provided data and returns
        a comprehensive result dictionary.

        Args:
            df: OHLCV DataFrame with at least 2 rows for crossover detection
            current_position: Optional — pass "CALL", "PUT", or None so the
                engine can prioritise EXIT signals when in a trade.

        Returns:
            Dict[str, Any]: Result dictionary containing:
                - signal: OptionSignal enum value
                - signal_value: String signal value
                - fired: Dict of which groups fired
                - rule_results: Detailed results per rule per group
                - indicator_values: Last and previous values for computed indicators
                - conflict: Whether BUY_CALL and BUY_PUT both fired
                - available: Whether evaluation was possible
                - confidence: Confidence scores per group (FEATURE 3)
                - threshold: Minimum confidence threshold (FEATURE 3)
                - explanation: Human-readable explanation (FEATURE 3)
                - position_context: The current_position passed in (for debug)
        """
        neutral = self._neutral_result()

        try:
            if df is None or df.empty or len(df) < 2:
                logger.debug("DataFrame insufficient for evaluation")
                return neutral

            cache = {}
            fired = {}
            rule_results = {}
            confidences = {}
            has_any_rules = False

            # Normalise position context
            pos = None
            if current_position is not None:
                pos = str(current_position).upper().strip()
                if pos not in ["CALL", "PUT"]:
                    pos = None

            # First, evaluate all signal groups
            for sig in SIGNAL_GROUPS:
                gf, rd, conf, _ = self._evaluate_group(sig, df, cache)
                fired[sig.value] = gf
                rule_results[sig.value] = rd
                confidences[sig.value] = conf
                if rd:
                    has_any_rules = True

            self._last_cache = cache

            # Build indicator snapshot
            indicator_values = {}
            for cache_key, series in cache.items():
                if series is not None and hasattr(series, "iloc") and len(series) > 0:
                    try:
                        # Get last non-NaN value
                        last_valid_idx = series.last_valid_index()
                        if last_valid_idx is not None:
                            last_val = series.loc[last_valid_idx]
                            # Find previous valid index
                            valid_indices = series.dropna().index
                            if len(valid_indices) >= 2:
                                prev_val = series.loc[valid_indices[-2]]
                            else:
                                prev_val = None
                        else:
                            last_val = None
                            prev_val = None

                        last_clean = None
                        if last_val is not None and not pd.isna(last_val) and not np.isnan(float(last_val)):
                            last_clean = round(float(last_val), 6)
                        prev_clean = None
                        if prev_val is not None and not pd.isna(prev_val) and not np.isnan(float(prev_val)):
                            prev_clean = round(float(prev_val), 6)
                        indicator_values[cache_key] = {"last": last_clean, "prev": prev_clean}
                    except Exception as e:
                        logger.warning(f"Failed to process indicator {cache_key}: {e}")
                        indicator_values[cache_key] = {"last": None, "prev": None}

            if not has_any_rules:
                return neutral

            # Apply confidence threshold to determine which groups actually fired
            fired_after_threshold = {}
            for sig in SIGNAL_GROUPS:
                sig_val = sig.value
                if fired.get(sig_val, False) and confidences.get(sig_val, 0) >= self.min_confidence:
                    fired_after_threshold[sig_val] = True
                    logger.debug(f"Signal {sig_val} passed threshold: {confidences[sig_val]:.2f} >= {self.min_confidence}")
                else:
                    fired_after_threshold[sig_val] = False
                    if fired.get(sig_val, False):
                        logger.debug(f"Signal {sig_val} suppressed - confidence {confidences[sig_val]:.2f} < {self.min_confidence}")

            # Now resolve the final signal based on position context
            resolved = self._resolve_with_position(fired_after_threshold, pos)

            # Generate explanation
            explanation = self._generate_explanation(fired_after_threshold, confidences, pos)

            return {
                "signal": resolved,
                "signal_value": resolved.value if resolved else "WAIT",
                "fired": fired_after_threshold,  # Return post-threshold firing status
                "raw_fired": fired,  # Include raw firing status for debugging
                "rule_results": rule_results,
                "indicator_values": indicator_values,
                "conflict": fired.get("BUY_CALL", False) and fired.get("BUY_PUT", False),
                "available": True,
                "confidence": confidences,
                "threshold": self.min_confidence,
                "explanation": explanation,
                "position_context": pos,
            }

        except Exception as e:
            logger.error(f"[evaluate] Failed: {e}", exc_info=True)
            return neutral

    def _generate_explanation(self, fired: Dict[str, bool], confidences: Dict[str, float], position: Optional[str] = None) -> str:
        """
        FEATURE 3: Generate human-readable explanation of last evaluation.

        Args:
            fired: Dict of which groups fired after threshold
            confidences: Dict of confidence scores per group
            position: Current position context

        Returns:
            str: Human-readable explanation string
        """
        try:
            parts = []
            if position:
                parts.append(f"📊 Position: {position}")

            for sig, is_fired in fired.items():
                conf = confidences.get(sig, 0)
                if conf >= self.min_confidence:
                    status = "✅ FIRED" if is_fired else "⚠️ SUPPRESSED"
                else:
                    status = "❌ BLOCKED"
                parts.append(f"{sig}: {conf:.0%} {status}")

            # Add conflict info if both BUY signals are high
            if confidences.get("BUY_CALL", 0) >= self.min_confidence and confidences.get("BUY_PUT", 0) >= self.min_confidence:
                parts.append("⚖️ Conflict: Both BUY signals high - waiting for resolution")

            return " | ".join(parts)
        except Exception as e:
            logger.error(f"[_generate_explanation] Failed: {e}", exc_info=True)
            return "No explanation available"

    def _resolve_with_position(self, fired: Dict[str, bool], position: Optional[str] = None) -> OptionSignal:
        """
        Resolve final signal from fired groups with position context.

        Priority rules:
        1. If in a position, EXIT signals for that position have highest priority
        2. HOLD signals prevent new entries but don't force exit
        3. Entry signals (BUY_CALL/BUY_PUT) are only considered when flat
        4. When both entry signals fire in flat position, use conflict_resolution
        5. Default to WAIT if nothing appropriate fires

        Args:
            fired: Dict of which groups fired (after threshold)
            position: Current position ("CALL", "PUT", or None)

        Returns:
            OptionSignal: Resolved final signal
        """
        try:
            # If we have a position, prioritize exits for that position
            if position == "CALL":
                if fired.get("EXIT_CALL", False) or fired.get("BUY_PUT", False):
                    logger.debug(f"Position CALL: EXIT_CALL or BUY_PUT fired - exiting")
                    return OptionSignal.EXIT_CALL
                # If no exit signal, consider HOLD
                if fired.get("HOLD", False):
                    logger.debug(f"Position CALL: HOLD fired - holding")
                    return OptionSignal.HOLD
                # Otherwise WAIT
                logger.debug(f"Position CALL: No exit or hold - waiting")
                return OptionSignal.WAIT

            elif position == "PUT":
                if fired.get("EXIT_PUT", False) or fired.get("BUY_CALL", False):
                    logger.debug(f"Position PUT: EXIT_PUT fired - exiting")
                    return OptionSignal.EXIT_PUT
                if fired.get("HOLD", False):
                    logger.debug(f"Position PUT: HOLD fired - holding")
                    return OptionSignal.HOLD
                logger.debug(f"Position PUT: No exit or hold - waiting")
                return OptionSignal.WAIT

            # No position - consider entries
            else:
                bc = fired.get("BUY_CALL", False)
                bp = fired.get("BUY_PUT", False)

                # If both entry signals fire
                if bc and bp:
                    logger.debug(f"Flat position: Both BUY signals fired - using conflict_resolution={self.conflict_resolution}")
                    if self.conflict_resolution == "PRIORITY":
                        # In PRIORITY mode, default to BUY_CALL
                        return OptionSignal.BUY_CALL
                    else:
                        # WAIT mode - wait for clearer signal
                        return OptionSignal.WAIT

                # Single entry signal
                if bc:
                    logger.debug(f"Flat position: BUY_CALL fired")
                    return OptionSignal.BUY_CALL
                if bp:
                    logger.debug(f"Flat position: BUY_PUT fired")
                    return OptionSignal.BUY_PUT

                # No entry signals
                logger.debug(f"Flat position: No entry signals - waiting")
                return OptionSignal.WAIT

        except Exception as e:
            logger.error(f"[_resolve_with_position] Failed: {e}", exc_info=True)
            return OptionSignal.WAIT

    def _resolve(self, fired: Dict[str, bool]) -> OptionSignal:
        """
        Legacy resolve method - maintained for backward compatibility.
        Use _resolve_with_position instead for position-aware resolution.
        """
        return self._resolve_with_position(fired, None)

    @staticmethod
    def _neutral_result() -> Dict[str, Any]:
        """
        Return neutral result when evaluation is not possible.

        Returns:
            Dict[str, Any]: Neutral result with available=False
        """
        try:
            return {
                "signal": OptionSignal.WAIT,
                "signal_value": "WAIT",
                "fired": {s.value: False for s in SIGNAL_GROUPS},
                "raw_fired": {s.value: False for s in SIGNAL_GROUPS},
                "rule_results": {s.value: [] for s in SIGNAL_GROUPS},
                "indicator_values": {},
                "conflict": False,
                "available": False,
                "confidence": {s.value: 0.0 for s in SIGNAL_GROUPS},
                "threshold": 0.6,
                "explanation": "No data available for evaluation",
                "position_context": None,
            }
        except Exception as e:
            logger.error(f"[_neutral_result] Failed: {e}", exc_info=True)
            return {}

    @property
    def last_cache(self) -> Optional[Dict[str, Any]]:
        """
        Get last evaluation cache.

        Returns:
            Optional[Dict[str, Any]]: Cache from most recent evaluation
        """
        try:
            return self._last_cache
        except Exception as e:
            logger.error(f"[last_cache] Failed: {e}", exc_info=True)
            return None

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """
        Clean up resources before shutdown.

        Rule 8: Proper resource cleanup to prevent memory leaks.
        """
        try:
            logger.info("[DynamicSignalEngine] Starting cleanup")
            self._last_cache = None
            self.config.clear()
            self._manager = None
            logger.info("[DynamicSignalEngine] Cleanup completed")
        except Exception as e:
            logger.error(f"[DynamicSignalEngine.cleanup] Error: {e}", exc_info=True)


def build_example_config() -> Dict[str, Any]:
    """
    Build an example configuration with weights.

    FEATURE 3: Includes rule weights.

    Returns:
        Dict[str, Any]: Example configuration dictionary with weighted rules
    """
    try:
        return {
            "BUY_CALL": {"logic": "AND", "enabled": True, "rules": [
                {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}}, "op": ">",
                 "rhs": {"type": "scalar", "value": 55}, "weight": 2.0},
                {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}}, "op": "crosses_above",
                 "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}}, "weight": 1.5},
                {"lhs": {"type": "indicator", "indicator": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
                 "op": ">", "rhs": {"type": "scalar", "value": 0}, "weight": 1.0},
            ]},
            "BUY_PUT": {"logic": "AND", "enabled": True, "rules": [
                {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}}, "op": "<",
                 "rhs": {"type": "scalar", "value": 45}, "weight": 2.0},
                {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}}, "op": "crosses_below",
                 "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}}, "weight": 1.5},
                {"lhs": {"type": "indicator", "indicator": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
                 "op": "<", "rhs": {"type": "scalar", "value": 0}, "weight": 1.0},
            ]},
            "EXIT_CALL": {"logic": "OR", "enabled": True, "rules": [
                {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}}, "op": ">",
                 "rhs": {"type": "scalar", "value": 75}, "weight": 1.0},
                {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}}, "op": "crosses_below",
                 "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}}, "weight": 1.0},
            ]},
            "EXIT_PUT": {"logic": "OR", "enabled": True, "rules": [
                {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}}, "op": "<",
                 "rhs": {"type": "scalar", "value": 25}, "weight": 1.0},
                {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}}, "op": "crosses_above",
                 "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}}, "weight": 1.0},
            ]},
            "HOLD": {"logic": "AND", "enabled": True, "rules": [
                {"lhs": {"type": "indicator", "indicator": "adx", "params": {"length": 14}}, "op": ">",
                 "rhs": {"type": "scalar", "value": 25}, "weight": 1.0},
            ]},
            "conflict_resolution": "WAIT",
            "min_confidence": 0.6,
        }
    except Exception as e:
        logger.error(f"[build_example_config] Failed: {e}", exc_info=True)
        return {}