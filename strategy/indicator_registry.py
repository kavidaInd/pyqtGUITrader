"""
indicator_registry.py
=====================
Registry of all available pandas_ta indicators with their parameters and metadata.
This provides a single source of truth for indicator definitions used throughout the app.
"""

from typing import Dict, List, Any, Optional
import pandas_ta as ta


# Get all available indicators from pandas_ta
def get_all_indicators() -> List[str]:
    """Return list of all available indicator names from pandas_ta"""
    return sorted([name for name in dir(ta) if not name.startswith('_') and callable(getattr(ta, name))])


# Core indicators with their typical parameters
INDICATOR_CATEGORIES = {
    "Momentum": [
        "rsi", "stoch", "stochrsi", "macd", "cci", "tsi", "uo", "ao",
        "kama", "roc", "rvi", "trix", "willr", "dm", "psl"
    ],
    "Trend": [
        "ema", "sma", "wma", "hma", "dema", "tema", "trima", "vidya",
        "adx", "aroon", "amat", "chop", "cksp", "decay", "decreasing",
        "increasing", "long_run", "psar", "qstick", "short_run", "trendflex",
        "tsignals", "ttm_trend", "vhf", "vortex", "supertrend"
    ],
    "Volatility": [
        "bbands", "kc", "dona", "atr", "natr", "hwc", "true_range", "massi"
    ],
    "Volume": [
        "ad", "adosc", "obv", "cmf", "efi", "eom", "kvo", "mfi",
        "nvi", "pvi", "pvol", "pvr", "pvt", "vp"
    ],
    "Statistic": [
        "entropy", "kurtosis", "mad", "median", "quantile", "skew", "stdev",
        "tos_stdevall", "variance", "zscore"
    ],
    "Others": [
        "above", "below", "cross", "above_value", "below_value", "crossover",
        "cross_value", "fisher", "ha", "hl2", "hlc3", "hwma", "linreg",
        "log_return", "mcgd", "ohlc4", "percent_return", "ppo", "slope",
        "squeeze", "xsignals"
    ]
}

# Flatten the categories for easier lookup
ALL_INDICATORS = []
for indicators in INDICATOR_CATEGORIES.values():
    ALL_INDICATORS.extend(indicators)
ALL_INDICATORS = sorted(list(set(ALL_INDICATORS)))

# Default parameters for each indicator
INDICATOR_DEFAULT_PARAMS: Dict[str, Dict[str, Any]] = {
    # Momentum
    "rsi": {"length": 14, "scalar": 100, "drift": 1},
    "stoch": {"k": 14, "d": 3, "smooth_k": 3, "ma_method": "sma", "drift": 1},
    "stochrsi": {"length": 14, "rsi_length": 14, "k": 3, "d": 3},
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "cci": {"length": 20, "c": 0.015, "drift": 1},
    "tsi": {"fast": 13, "slow": 25, "drift": 1},
    "uo": {"fast": 7, "medium": 14, "slow": 28, "fast_w": 4.0, "medium_w": 2.0, "slow_w": 1.0, "drift": 1},
    "ao": {"fast": 5, "slow": 34},
    "kama": {"length": 10, "fast": 2, "slow": 30, "drift": 1},
    "roc": {"length": 10, "scalar": 100},
    "rvi": {"length": 14, "scalar": 100, "drift": 1, "offset": 0},
    "trix": {"length": 15, "scalar": 100, "drift": 1},
    "willr": {"length": 14, "scalar": -100, "drift": 1},
    "dm": {"length": 14, "drift": 1},
    "psl": {"length": 12, "drift": 1},

    # Trend
    "ema": {"length": 10, "offset": 0},
    "sma": {"length": 10, "offset": 0},
    "wma": {"length": 10, "offset": 0},
    "hma": {"length": 10, "offset": 0},
    "dema": {"length": 10, "offset": 0},
    "tema": {"length": 10, "offset": 0},
    "trima": {"length": 10, "offset": 0},
    "vidya": {"length": 14, "alpha": None, "drift": 1, "offset": 0},
    "adx": {"length": 14, "drift": 1},
    "aroon": {"length": 14, "scalar": 100},
    "amat": {"fast": 8, "slow": 21, "lookback": 2, "drift": 1},
    "chop": {"length": 14, "atr_length": 1, "drift": 1, "scalar": 100},
    "cksp": {"length": 10, "ma": "sma", "drift": 1},
    "psar": {"af0": 0.02, "af": 0.02, "max_af": 0.2},
    "qstick": {"length": 10, "offset": 0},
    "supertrend": {"length": 7, "multiplier": 3.0, "drift": 1},
    "trendflex": {"length": 20, "flex": None, "drift": 1, "offset": 0},

    # Volatility
    "bbands": {"length": 20, "std": 2, "ddof": 0, "offset": 0},
    "kc": {"length": 20, "scalar": 2, "tr": True, "offset": 0},
    "dona": {"lower_length": 10, "upper_length": 15, "offset": 0},
    "atr": {"length": 14, "mamode": "ema", "drift": 1, "offset": 0},
    "natr": {"length": 14, "mamode": "ema", "drift": 1, "offset": 0},
    "hwc": {},
    "true_range": {"drift": 1},
    "massi": {"fast": 9, "slow": 25},

    # Volume
    "ad": {},
    "adosc": {"fast": 3, "slow": 10, "offset": 0},
    "obv": {},
    "cmf": {"length": 20, "offset": 0},
    "efi": {"length": 13, "ma": "ema", "drift": 1, "offset": 0},
    "eom": {"length": 14, "divisor": 100000000, "drift": 1, "offset": 0},
    "kvo": {"fast": 34, "slow": 55, "signal": 13, "drift": 1},
    "mfi": {"length": 14, "drift": 1},
    "nvi": {"length": 1, "initial": 1000, "offset": 0},
    "pvi": {"length": 1, "initial": 1000, "offset": 0},
    "pvr": {},
    "pvt": {"drift": 1, "offset": 0},
    "vp": {"width": None, "sort": None},

    # Statistic
    "entropy": {"length": 10, "base": 2},
    "kurtosis": {"length": 30},
    "mad": {"length": 30},
    "median": {"length": 30},
    "quantile": {"length": 30, "q": 0.5},
    "skew": {"length": 30},
    "stdev": {"length": 30, "ddof": 0},
    "tos_stdevall": {"length": 30, "std": 1},
    "variance": {"length": 30, "ddof": 0},
    "zscore": {"length": 30, "ddof": 0},

    # Others
    "fisher": {"length": 9, "signal": 1, "offset": 0},
    "ha": {},
    "hwma": {"na": None, "nb": None, "nc": None, "offset": 0},
    "linreg": {"length": 14, "offset": 0},
    "log_return": {"length": 1, "cumulative": False, "percent": True},
    "mcgd": {"length": 10, "offset": 0},
    "percent_return": {"length": 1, "cumulative": False},
    "ppo": {"fast": 12, "slow": 26, "signal": 9, "ma": "ema", "drift": 1},
    "slope": {"length": 1, "offset": 0},
    "squeeze": {"bb_length": 20, "bb_std": 2, "kc_length": 20, "kc_scalar": 1.5, "mom_length": 12, "mom_smooth": 6},
}

# Parameter types for UI
PARAMETER_TYPES = {
    "int": ["length", "fast", "slow", "signal", "k", "d", "smooth_k", "lookback",
            "lower_length", "upper_length", "fast_period", "slow_period", "signal_period",
            "bb_length", "kc_length", "mom_length", "mom_smooth"],
    "float": ["std", "scalar", "multiplier", "c", "af0", "af", "max_af", "divisor",
              "fast_w", "medium_w", "slow_w", "alpha", "flex", "q"],
    "bool": ["tr", "cumulative", "percent", "full_output"],
    "string": ["ma_method", "mamode", "sort"],
}

# Parameter descriptions for tooltips
PARAMETER_DESCRIPTIONS = {
    "length": "Number of periods",
    "fast": "Fast period length",
    "slow": "Slow period length",
    "signal": "Signal period length",
    "std": "Standard deviation multiplier",
    "multiplier": "Multiplier for calculation",
    "drift": "Lookback period for difference",
    "offset": "Number of periods to offset",
    "scalar": "Scalar multiplier",
    "k": "Stochastic %K period",
    "d": "Stochastic %D period",
    "smooth_k": "Smoothing factor for %K",
    "ma_method": "Moving average method (sma, ema, wma)",
    "mamode": "Moving average mode",
    "af0": "Initial acceleration factor",
    "af": "Acceleration factor",
    "max_af": "Maximum acceleration factor",
    "tr": "Use True Range for KC",
    "cumulative": "Calculate cumulative returns",
    "percent": "Show as percentage",
}


def get_indicator_params(indicator: str) -> Dict[str, Any]:
    """Get default parameters for an indicator"""
    return INDICATOR_DEFAULT_PARAMS.get(indicator.lower(), {}).copy()


def get_param_type(param: str) -> str:
    """Determine the type of a parameter for UI validation"""
    if param in PARAMETER_TYPES["int"]:
        return "int"
    elif param in PARAMETER_TYPES["float"]:
        return "float"
    elif param in PARAMETER_TYPES["bool"]:
        return "bool"
    elif param in PARAMETER_TYPES["string"]:
        return "string"
    return "string"  # default


def get_param_description(param: str) -> str:
    """Get description for a parameter"""
    return PARAMETER_DESCRIPTIONS.get(param, "No description available")


def get_indicators_by_category() -> Dict[str, List[str]]:
    """Return indicators organized by category"""
    return INDICATOR_CATEGORIES.copy()


def get_indicator_display_name(indicator: str) -> str:
    """Get a display name with proper formatting"""
    return indicator.upper()


def get_indicator_category(indicator: str) -> str:
    """Get the category of an indicator"""
    indicator_lower = indicator.lower()
    for category, indicators in INDICATOR_CATEGORIES.items():
        if indicator_lower in indicators:
            return category
    return "Others"
