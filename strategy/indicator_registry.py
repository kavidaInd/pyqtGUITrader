"""
Indicator Registry Module
=========================
Registry of all available pandas_ta indicators with their parameters and metadata.

This module provides a single source of truth for indicator definitions used
throughout the application. It centralizes:
    - Indicator names and categories
    - Default parameters for each indicator
    - Parameter types and descriptions
    - Validation logic for parameters
    - FEATURE 3: Confidence scoring metadata and helper functions

Architecture:
    The registry serves as a metadata repository for technical indicators:

    1. **Indicator Categories**: Organizes indicators by type (Momentum, Trend, etc.)
    2. **Default Parameters**: Standard parameters for each indicator
    3. **Parameter Metadata**: Types, descriptions, and validation rules
    4. **FEATURE 3**: Weight suggestions and confidence scoring utilities

Key Features:
    - **Centralized Definitions**: Single source of truth for all indicators
    - **Parameter Validation**: Type checking and range validation
    - **Category Organization**: Indicators grouped by functional category
    - **Help System**: Comprehensive indicator help with parameter descriptions
    - **FEATURE 3**: Confidence scoring infrastructure:
        - Suggested weights for each indicator based on reliability
        - Signal group importance weights
        - Confidence threshold profiles
        - Utility functions for confidence calculation

Dependencies:
    - pandas_ta: Optional, for runtime indicator availability
    - logging: For structured logging

Usage:
    from indicator_registry import (
        get_all_indicators,
        get_indicator_params,
        validate_parameters,
        get_suggested_weight  # FEATURE 3
    )

    # Get default parameters for RSI
    params = get_indicator_params("rsi")

    # Validate user-provided parameters
    errors = validate_parameters("macd", {"fast": 12, "slow": 26})

    # FEATURE 3: Get suggested weight
    weight = get_suggested_weight("adx")  # Returns 2.0

    # FEATURE 3: Calculate confidence from rule results
    confidence = calculate_rule_confidence(rule_results)

Version: 2.0.0 (with FEATURE 3 enhancements)
"""

import logging.handlers
from typing import Dict, List, Any, Optional

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
    """
    Return list of all available indicator names from pandas_ta.

    This function dynamically inspects the pandas_ta module to get all
    callable functions that don't start with underscore.

    Returns:
        List[str]: Sorted list of indicator names, or empty list if pandas_ta not available

    Note:
        This provides runtime discovery of indicators, complementing the
        static registry with any indicators that might be added to pandas_ta.
    """
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
# Organized by functional category for easier navigation
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
# These are the recommended starting parameters for each indicator
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
# Maps parameter names to their expected Python types for UI validation
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
# Human-readable explanations for each parameter
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

# ==================================================================
# FEATURE 3: Confidence Scoring Metadata
# ==================================================================

# Recommended weights for different indicator types
# Higher weights for more reliable indicators
# These values are used in confidence scoring calculations
INDICATOR_WEIGHT_SUGGESTIONS = {
    # Momentum (medium-high reliability)
    "rsi": 1.5,
    "stoch": 1.2,
    "macd": 1.8,
    "cci": 1.3,
    "tsi": 1.4,
    "uo": 1.3,
    "ao": 1.1,
    "kama": 1.2,
    "roc": 1.1,
    "rvi": 1.4,
    "trix": 1.3,
    "willr": 1.2,
    "dm": 1.2,
    "psl": 1.1,

    # Trend (high reliability for trend-following)
    "ema": 1.5,
    "sma": 1.5,
    "wma": 1.5,
    "hma": 1.6,
    "dema": 1.6,
    "tema": 1.7,
    "trima": 1.5,
    "vidya": 1.4,
    "adx": 2.0,  # High reliability for trend strength
    "aroon": 1.8,
    "amat": 1.7,
    "chop": 1.4,
    "cksp": 1.3,
    "psar": 1.6,
    "qstick": 1.2,
    "supertrend": 2.0,  # High reliability
    "trendflex": 1.4,

    # Volatility (medium reliability)
    "bbands": 1.5,
    "kc": 1.4,
    "dona": 1.3,
    "atr": 1.5,
    "natr": 1.5,
    "massi": 1.3,

    # Volume (low-medium reliability, depends on market)
    "ad": 1.2,
    "adosc": 1.3,
    "obv": 1.4,
    "cmf": 1.4,
    "efi": 1.3,
    "eom": 1.2,
    "kvo": 1.3,
    "mfi": 1.5,
    "nvi": 1.2,
    "pvi": 1.2,
    "pvt": 1.3,

    # Default weight for unspecified indicators
    "default": 1.0,
}

# Signal group importance (for overall confidence)
# Some signal groups are more important than others
SIGNAL_GROUP_WEIGHTS = {
    "BUY_CALL": 1.0,
    "BUY_PUT": 1.0,
    "EXIT_CALL": 1.2,  # Exits slightly more important
    "EXIT_PUT": 1.2,
    "HOLD": 0.8,  # Hold signals less important
}

# Confidence threshold suggestions for different risk profiles
CONFIDENCE_THRESHOLD_SUGGESTIONS = {
    "conservative": 0.7,
    "moderate": 0.6,
    "aggressive": 0.5,
    "very_aggressive": 0.4,
}


def get_indicator_params(indicator: str) -> Dict[str, Any]:
    """
    Get default parameters for an indicator.

    Args:
        indicator: Indicator name (case-insensitive)

    Returns:
        Dict[str, Any]: Dictionary of parameter names and default values.
                       Empty dict if indicator not found.
    """
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
    """
    Determine the type of a parameter for UI validation.

    Args:
        param: Parameter name

    Returns:
        str: Type name: "int", "float", "bool", or "string"
    """
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
    """
    Get description for a parameter (for tooltips).

    Args:
        param: Parameter name

    Returns:
        str: Human-readable description
    """
    try:
        if param is None:
            logger.warning("get_param_description called with None param")
            return "No description available"

        return PARAMETER_DESCRIPTIONS.get(param, "No description available")
    except Exception as e:
        logger.error(f"[get_param_description] Failed for {param}: {e}", exc_info=True)
        return "No description available"


def get_indicators_by_category() -> Dict[str, List[str]]:
    """
    Return indicators organized by category.

    Returns:
        Dict[str, List[str]]: Dictionary mapping category names to lists of indicators
    """
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
    """
    Get a display name with proper formatting (uppercase).

    Args:
        indicator: Indicator name

    Returns:
        str: Formatted display name
    """
    try:
        if indicator is None:
            logger.warning("get_indicator_display_name called with None indicator")
            return ""

        return indicator.upper()
    except Exception as e:
        logger.error(f"[get_indicator_display_name] Failed for {indicator}: {e}", exc_info=True)
        return indicator if indicator else ""


def get_indicator_category(indicator: str) -> str:
    """
    Get the category of an indicator.

    Args:
        indicator: Indicator name

    Returns:
        str: Category name ("Momentum", "Trend", etc.) or "Others" if not found
    """
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
    """
    Validate if an indicator exists in the registry.

    Args:
        indicator: Indicator name

    Returns:
        bool: True if indicator exists, False otherwise
    """
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

    This function performs comprehensive validation:
        - Type checking (int, float, bool, string)
        - Range validation for common parameters
        - Reasonable value bounds

    Args:
        indicator: Indicator name
        params: Dictionary of parameter names and values to validate

    Returns:
        Dict[str, str]: Dictionary mapping parameter names to error messages.
                       Empty dict if no errors.
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
    """
    Get comprehensive help information for an indicator.

    Returns a dictionary containing:
        - name: Indicator name
        - display_name: Formatted display name
        - category: Indicator category
        - default_params: Default parameters
        - description: Brief description
        - parameters: List of parameter info with name, type, description, default

    Args:
        indicator: Indicator name

    Returns:
        Dict[str, Any]: Comprehensive help information
    """
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


# ==================================================================
# FEATURE 3: New helper functions for confidence scoring
# ==================================================================

def get_suggested_weight(indicator: str) -> float:
    """
    Get suggested weight for an indicator based on its reliability.

    Higher weights for more reliable indicators (e.g., ADX, Supertrend).
    Used in confidence scoring calculations.

    Args:
        indicator: Indicator name

    Returns:
        float: Suggested weight (default 1.0)

    Example:
        weight = get_suggested_weight("adx")  # Returns 2.0
    """
    try:
        if indicator is None:
            return 1.0
        return INDICATOR_WEIGHT_SUGGESTIONS.get(indicator.lower(),
                                                INDICATOR_WEIGHT_SUGGESTIONS.get("default", 1.0))
    except Exception as e:
        logger.error(f"[get_suggested_weight] Failed for {indicator}: {e}", exc_info=True)
        return 1.0


def get_signal_group_weight(signal_group: str) -> float:
    """
    Get weight for a signal group (for overall confidence calculation).

    Args:
        signal_group: Signal group name (BUY_CALL, BUY_PUT, EXIT_CALL, etc.)

    Returns:
        float: Signal group weight (default 1.0)
    """
    try:
        return SIGNAL_GROUP_WEIGHTS.get(signal_group, 1.0)
    except Exception as e:
        logger.error(f"[get_signal_group_weight] Failed for {signal_group}: {e}", exc_info=True)
        return 1.0


def get_threshold_suggestion(profile: str = "moderate") -> float:
    """
    Get confidence threshold suggestion based on risk profile.

    Args:
        profile: Risk profile string:
            - 'conservative': 0.7 (requires high confidence)
            - 'moderate': 0.6 (balanced)
            - 'aggressive': 0.5 (accepts moderate confidence)
            - 'very_aggressive': 0.4 (accepts low confidence)

    Returns:
        float: Suggested confidence threshold

    Example:
        threshold = get_threshold_suggestion("conservative")  # Returns 0.7
    """
    try:
        return CONFIDENCE_THRESHOLD_SUGGESTIONS.get(profile, 0.6)
    except Exception as e:
        logger.error(f"[get_threshold_suggestion] Failed for {profile}: {e}", exc_info=True)
        return 0.6


def calculate_rule_confidence(rule_results: List[Dict[str, Any]]) -> float:
    """
    Calculate confidence score from a list of rule results.

    Confidence = (sum of weights of passed rules) / (sum of total weights)

    Args:
        rule_results: List of rule result dicts with 'result' and 'weight' keys.
                     Each dict should have the structure returned by
                     DynamicSignalEngine._evaluate_group().

    Returns:
        float: Confidence score (0.0 to 1.0)

    Example:
        rules = [
            {"result": True, "weight": 2.0},
            {"result": False, "weight": 1.0},
            {"result": True, "weight": 1.5}
        ]
        confidence = calculate_rule_confidence(rules)  # Returns (2.0+1.5)/(2.0+1.0+1.5) = 0.7
    """
    try:
        if not rule_results:
            return 0.0

        total_weight = 0.0
        passed_weight = 0.0

        for rule in rule_results:
            weight = rule.get('weight', 1.0)
            total_weight += weight
            if rule.get('result', False):
                passed_weight += weight

        return passed_weight / total_weight if total_weight > 0 else 0.0

    except Exception as e:
        logger.error(f"[calculate_rule_confidence] Failed: {e}", exc_info=True)
        return 0.0


def get_rule_weight_range() -> Dict[str, Any]:
    """
    Get valid range for rule weights.

    Returns:
        Dict with min, max, default, step, and description:
            - min: Minimum allowed weight
            - max: Maximum allowed weight
            - default: Default weight
            - step: Increment step for UI sliders
            - description: Human-readable description
    """
    try:
        return {
            "min": 0.1,
            "max": 5.0,
            "default": 1.0,
            "step": 0.1,
            "description": "Rule weight (higher = more important in confidence calculation)"
        }
    except Exception as e:
        logger.error(f"[get_rule_weight_range] Failed: {e}", exc_info=True)
        return {"min": 0.1, "max": 5.0, "default": 1.0, "step": 0.1}


def get_confidence_display_info(confidence: float, threshold: float) -> Dict[str, Any]:
    """
    Get display information for a confidence value.

    Provides UI-friendly information for displaying confidence scores:
        - Color code based on confidence relative to threshold
        - Label (PASS/NEAR/FAIL)
        - Formatted percentage string

    Args:
        confidence: Confidence score (0.0 to 1.0)
        threshold: Confidence threshold

    Returns:
        Dict with keys:
            - color: Hex color code for UI
            - label: Status label ("PASS", "NEAR", "FAIL")
            - status: Machine-readable status ("passed", "near", "failed")
            - percent: Formatted percentage string (e.g., "75%")

    Example:
        info = get_confidence_display_info(0.75, 0.6)
        # Returns {"color": "#3fb950", "label": "PASS", "status": "passed", "percent": "75%"}
    """
    try:
        if confidence >= threshold:
            return {
                "color": "#3fb950",  # Green
                "label": "PASS",
                "status": "passed",
                "percent": f"{confidence*100:.0f}%"
            }
        elif confidence >= threshold * 0.7:
            return {
                "color": "#d29922",  # Yellow
                "label": "NEAR",
                "status": "near",
                "percent": f"{confidence*100:.0f}%"
            }
        else:
            return {
                "color": "#f85149",  # Red
                "label": "FAIL",
                "status": "failed",
                "percent": f"{confidence*100:.0f}%"
            }
    except Exception as e:
        logger.error(f"[get_confidence_display_info] Failed: {e}", exc_info=True)
        return {"color": "#8b949e", "label": "UNKNOWN", "status": "unknown", "percent": "0%"}


# Rule 8: Cleanup function
def cleanup():
    """Clean up resources (minimal for this module)."""
    try:
        logger.info("[indicator_registry] Cleanup completed")
    except Exception as e:
        logger.error(f"[cleanup] Failed: {e}", exc_info=True)