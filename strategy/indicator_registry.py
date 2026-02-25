"""
indicator_registry.py
=====================
Registry of all available pandas_ta indicators with their parameters and metadata.
This provides a single source of truth for indicator definitions used throughout the app.
"""

import logging.handlers
from typing import Dict, List, Any

try:
    import pandas_ta as ta
    _TA_AVAILABLE = True
except ImportError:
    ta = None
    _TA_AVAILABLE = False

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


# Get all available indicators from pandas_ta
def get_all_indicators() -> List[str]:
    """Return list of all available indicator names from pandas_ta"""
    try:
        if ta is None:
            logger.warning("pandas_ta not available")
            return []

        indicators = [name for name in dir(ta) if not name.startswith('_') and callable(getattr(ta, name))]
        return sorted(indicators)
    except Exception as e:
        logger.error(f"[get_all_indicators] Failed: {e}", exc_info=True)
        return []


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
try:
    for indicators in INDICATOR_CATEGORIES.values():
        ALL_INDICATORS.extend(indicators)
    ALL_INDICATORS = sorted(list(set(ALL_INDICATORS)))
except Exception as e:
    logger.error(f"Failed to build ALL_INDICATORS: {e}", exc_info=True)
    ALL_INDICATORS = []

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
            "bb_length", "kc_length", "mom_length", "mom_smooth", "rsi_length"],
    "float": ["std", "scalar", "multiplier", "c", "af0", "af", "max_af", "divisor",
              "fast_w", "medium_w", "slow_w", "alpha", "flex", "q", "bb_std", "kc_scalar"],
    "bool": ["tr", "cumulative", "percent", "full_output"],
    "string": ["ma_method", "mamode", "sort", "ma"],
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
    "bb_length": "Bollinger Bands length",
    "bb_std": "Bollinger Bands standard deviation",
    "kc_length": "Keltner Channel length",
    "kc_scalar": "Keltner Channel multiplier",
    "mom_length": "Momentum length",
    "mom_smooth": "Momentum smoothing",
}


def get_indicator_params(indicator: str) -> Dict[str, Any]:
    """Get default parameters for an indicator"""
    try:
        if indicator is None:
            logger.warning("get_indicator_params called with None indicator")
            return {}

        params = INDICATOR_DEFAULT_PARAMS.get(indicator.lower(), {})
        # Return a copy to prevent modification
        return dict(params)
    except Exception as e:
        logger.error(f"[get_indicator_params] Failed for {indicator}: {e}", exc_info=True)
        return {}


def get_param_type(param: str) -> str:
    """Determine the type of a parameter for UI validation"""
    try:
        if param is None:
            logger.warning("get_param_type called with None param")
            return "string"

        if param in PARAMETER_TYPES["int"]:
            return "int"
        elif param in PARAMETER_TYPES["float"]:
            return "float"
        elif param in PARAMETER_TYPES["bool"]:
            return "bool"
        elif param in PARAMETER_TYPES["string"]:
            return "string"
        return "string"  # default
    except Exception as e:
        logger.error(f"[get_param_type] Failed for {param}: {e}", exc_info=True)
        return "string"


def get_param_description(param: str) -> str:
    """Get description for a parameter"""
    try:
        if param is None:
            logger.warning("get_param_description called with None param")
            return "No description available"

        return PARAMETER_DESCRIPTIONS.get(param, "No description available")
    except Exception as e:
        logger.error(f"[get_param_description] Failed for {param}: {e}", exc_info=True)
        return "No description available"


def get_indicators_by_category() -> Dict[str, List[str]]:
    """Return indicators organized by category"""
    try:
        # Return a deep copy to prevent modification
        result = {}
        for category, indicators in INDICATOR_CATEGORIES.items():
            result[category] = list(indicators)
        return result
    except Exception as e:
        logger.error(f"[get_indicators_by_category] Failed: {e}", exc_info=True)
        return {}


def get_indicator_display_name(indicator: str) -> str:
    """Get a display name with proper formatting"""
    try:
        if indicator is None:
            logger.warning("get_indicator_display_name called with None indicator")
            return ""

        return indicator.upper()
    except Exception as e:
        logger.error(f"[get_indicator_display_name] Failed for {indicator}: {e}", exc_info=True)
        return indicator if indicator else ""


def get_indicator_category(indicator: str) -> str:
    """Get the category of an indicator"""
    try:
        if indicator is None:
            logger.warning("get_indicator_category called with None indicator")
            return "Others"

        indicator_lower = indicator.lower()
        for category, indicators in INDICATOR_CATEGORIES.items():
            if indicator_lower in indicators:
                return category
        return "Others"
    except Exception as e:
        logger.error(f"[get_indicator_category] Failed for {indicator}: {e}", exc_info=True)
        return "Others"


def validate_indicator(indicator: str) -> bool:
    """Validate if an indicator exists in the registry"""
    try:
        if indicator is None:
            return False
        return indicator.lower() in ALL_INDICATORS
    except Exception as e:
        logger.error(f"[validate_indicator] Failed for {indicator}: {e}", exc_info=True)
        return False


def validate_parameters(indicator: str, params: Dict[str, Any]) -> Dict[str, str]:
    """
    Validate parameters for an indicator.
    Returns a dict of parameter_name -> error_message for invalid parameters.
    """
    errors = {}
    try:
        if indicator is None:
            errors["indicator"] = "Indicator name is required"
            return errors

        if params is None:
            return errors

        default_params = get_indicator_params(indicator)

        for param_name, param_value in params.items():
            try:
                expected_type = get_param_type(param_name)

                # Skip validation for None values (may be optional)
                if param_value is None:
                    continue

                # Type validation
                if expected_type == "int":
                    try:
                        int_val = int(param_value)
                        # Range validation for common parameters
                        if param_name in ["length", "fast", "slow", "signal"]:
                            if int_val <= 0:
                                errors[param_name] = f"{param_name} must be positive"
                            elif int_val > 1000:
                                errors[param_name] = f"{param_name} is unusually large (max 1000)"
                    except (ValueError, TypeError):
                        errors[param_name] = f"{param_name} must be an integer"

                elif expected_type == "float":
                    try:
                        float_val = float(param_value)
                        if param_name in ["std", "multiplier", "scalar"]:
                            if float_val <= 0:
                                errors[param_name] = f"{param_name} must be positive"
                            elif float_val > 100:
                                errors[param_name] = f"{param_name} is unusually large (max 100)"
                    except (ValueError, TypeError):
                        errors[param_name] = f"{param_name} must be a number"

                elif expected_type == "bool":
                    if not isinstance(param_value, bool):
                        # Try to convert
                        try:
                            bool(param_value)
                        except:
                            errors[param_name] = f"{param_name} must be true/false"

            except Exception as e:
                logger.warning(f"Error validating parameter {param_name}: {e}")
                errors[param_name] = f"Validation error: {e}"

        return errors

    except Exception as e:
        logger.error(f"[validate_parameters] Failed: {e}", exc_info=True)
        return {"_global": f"Validation error: {e}"}


def get_indicator_help(indicator: str) -> Dict[str, Any]:
    """Get comprehensive help information for an indicator"""
    try:
        if indicator is None:
            logger.warning("get_indicator_help called with None indicator")
            return {}

        indicator_lower = indicator.lower()
        return {
            "name": indicator_lower,
            "display_name": get_indicator_display_name(indicator_lower),
            "category": get_indicator_category(indicator_lower),
            "default_params": get_indicator_params(indicator_lower),
            "description": f"Default parameters for {indicator_lower}",
            "parameters": [
                {
                    "name": param,
                    "type": get_param_type(param),
                    "description": get_param_description(param),
                    "default": value
                }
                for param, value in get_indicator_params(indicator_lower).items()
            ]
        }
    except Exception as e:
        logger.error(f"[get_indicator_help] Failed for {indicator}: {e}", exc_info=True)
        return {}


# Rule 8: Cleanup function
def cleanup():
    """Clean up resources (minimal for this module)"""
    try:
        logger.info("[indicator_registry] Cleanup completed")
    except Exception as e:
        logger.error(f"[cleanup] Failed: {e}", exc_info=True)