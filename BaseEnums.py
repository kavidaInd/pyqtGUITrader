import logging
import os
from typing import Dict, Set, List

logger = logging.getLogger(__name__)

# ============================================================================
# Bot Operation Modes
# ============================================================================
# Defines the operational modes for the trading bot system.
# These modes determine how the bot interacts with the market and processes trades.
# - BACK: Historical data analysis mode for strategy testing without real trading
# - SIM: Paper trading mode using real-time data but no actual money
# - LIVE: Production mode with real money trading on actual exchanges
# - OPTI: Parameter optimization mode for finding optimal strategy settings
# - PAPER: Alias for SIM mode for backward compatibility
# - BACKTEST: Alias for BACK mode for backward compatibility
BACK = "Backtest"
SIM = "Simulation"  # Paper trading
LIVE = "Live"
OPTI = "Optimizer"

# Add new enums
PAPER = "Paper"  # Alias for SIM
BACKTEST = "Backtest"

# Valid bot modes for validation
# Set of all allowed bot operation modes for input validation throughout the system
VALID_BOT_MODES: Set[str] = {BACK, SIM, LIVE, OPTI, PAPER, BACKTEST}

# ============================================================================
# Backtest Execution Status
# ============================================================================
# Represents the current state of a backtesting operation.
# Used to track and monitor backtest jobs through their lifecycle.
# - Pending: Backtest created but not yet started
# - Running: Backtest currently executing
# - Completed: Backtest finished successfully with results
# - Failed: Backtest encountered an error during execution
BACKTEST_PENDING = "Pending"
BACKTEST_RUNNING = "Running"
BACKTEST_COMPLETED = "Completed"
BACKTEST_FAILED = "Failed"
TRENDING = "Trending"
SIDEWAYS = "Sideways"

# Valid backtest statuses for validation and state machine transitions
VALID_BACKTEST_STATUSES: Set[str] = {
    BACKTEST_PENDING, BACKTEST_RUNNING, BACKTEST_COMPLETED, BACKTEST_FAILED
}

# ============================================================================
# Trading Strategy Types
# ============================================================================
# Classification of different trading approaches based on holding period and execution style.
# - Scalping: Ultra-short term trades (seconds to minutes) targeting small price movements
# - Normal: Standard trades based on technical/ fundamental analysis (minutes to hours)
# - Expiry: Options trades held until expiration date
TRADE_TYPE_SCALPING = "Scalping"
TRADE_TYPE_NORMAL = "Normal"
TRADE_TYPE_EXPIRY = "Expiry"

# Valid trade types for strategy configuration and validation
VALID_TRADE_TYPES: Set[str] = {TRADE_TYPE_SCALPING, TRADE_TYPE_NORMAL, TRADE_TYPE_EXPIRY}

# ============================================================================
# Market Trend Signals and Trade Instructions
# ============================================================================
# Comprehensive set of market sentiment indicators and trading commands.
# Used by the strategy engine to generate signals and by the execution module to process them.
# - Bullish/Bearish: General market direction sentiment
# - Enter/Exit Call/Put: Options-specific trading signals
# - Cancel commands: Signal cancellation instructions
# - Previous Trade: Reference to last trade for follow-up actions
# - RESET: Clear previous trade reference state
BULLISH = "Bullish"
BEARISH = "Bearish"
ENTER_CALL = "Enter Call"
EXIT_CALL = "Exit Call"
ENTER_PUT = "Enter Put"
EXIT_PUT = "Exit Put"
CANCEL_PUT = "Cancel Put"
CANCEL_CALL = "Cancel Call"
CANCEL_TRADE = "Cancel Trade"
PREVIOUS_TRADE = "Previous Trade"
RESET_PREVIOUS_TRADE = 'RESET'

# Collections for validation
# TRENDS: List of primary trading signals for options strategies
TRENDS: List[str] = [ENTER_CALL, EXIT_CALL, ENTER_PUT, EXIT_PUT]
# ALL_TRENDS: Complete set including market sentiment and control signals
ALL_TRENDS: Set[str] = {*TRENDS, BULLISH, BEARISH, CANCEL_PUT, CANCEL_CALL,
                        CANCEL_TRADE, PREVIOUS_TRADE, RESET_PREVIOUS_TRADE}

# ============================================================================
# OHLCV Price Types for Analysis
# ============================================================================
# Standard price data points used in technical analysis and strategy calculations.
# Includes individual prices and composite ranges for volatility assessment.
# - Open/Close: Average or range between open and close prices
# - High/Low: Average or range between high and low prices
PRICE_TYPES: List[str] = ['Open', 'High', 'Low', 'Close', 'Open/Close', 'High/Low']
VALID_PRICE_TYPES: Set[str] = set(PRICE_TYPES)

# ============================================================================
# Comparison Operators for Conditional Logic
# ============================================================================
# Standard mathematical comparison operators used in strategy conditions,
# entry/exit rules, and filter criteria throughout the system.
OPERATORS: List[str] = ['>', '<', '>=', '<=', '==', '!=']
VALID_OPERATORS: Set[str] = set(OPERATORS)

# ============================================================================
# Options Contract Types
# ============================================================================
# Basic classification of options contracts.
# - Call: Right to buy underlying asset at strike price
# - Put: Right to sell underlying asset at strike price
CALL = "Call"
PUT = "Put"

VALID_OPTION_TYPES: Set[str] = {CALL, PUT}

# ============================================================================
# Stop Loss Mechanism Types
# ============================================================================
# Defines how stop losses behave during trade execution.
# - TRAILING: Dynamic stop that moves with favorable price movements
# - STOP: Fixed price level that triggers exit regardless of market movement
TRAILING = "TRAILING"
STOP = "STOP"

VALID_STOP_TYPES: Set[str] = {TRAILING, STOP}

# ============================================================================
# API Response Status Indicators
# ============================================================================
# Standardized response statuses for API calls and internal function returns.
# Used throughout the system to indicate operation success or failure.
OK = 'ok'
ERROR = 'error'

VALID_RESPONSE_STATUSES: Set[str] = {OK, ERROR}

# ============================================================================
# Order Direction/Side Constants
# ============================================================================
# Numeric representation of trade direction for order processing.
# Using +1/-1 allows for mathematical operations like position calculation.
# - SIDE_BUY (+1): Long position, purchasing asset
# - SIDE_SELL (-1): Short position, selling asset
SIDE_BUY = 1
SIDE_SELL = -1

VALID_ORDER_SIDES: Set[int] = {SIDE_BUY, SIDE_SELL}

# ============================================================================
# Order Type Classifications
# ============================================================================
# Numeric identifiers for different order types supported by the trading system.
# Maps to broker/platform order type codes for consistent handling.
# - LIMIT: Execute at specified price or better
# - MARKET: Execute immediately at current market price
# - STOPLOSS_MARKET: Market order when stop price is triggered
# - STOPLOSS_LIMIT: Limit order when stop price is triggered
LIMIT_ORDER_TYPE = 1
MARKET_ORDER_TYPE = 2
STOPLOSS_MARKET_ORDER_TYPE = 3
STOPLOSS_LIMIT_ORDER_TYPE = 4

VALID_ORDER_TYPES: Set[int] = {
    LIMIT_ORDER_TYPE, MARKET_ORDER_TYPE,
    STOPLOSS_MARKET_ORDER_TYPE, STOPLOSS_LIMIT_ORDER_TYPE
}

# ============================================================================
# Product Type Classifications
# ============================================================================
# Defines the trading product categories based on settlement and margin requirements.
# - CNC: Cash N Carry - Delivery-based trading (equity)
# - INTRADAY: Same-day squared-off positions
# - MARGIN: Leveraged trading with collateral
PRODUCT_TYPE_CNC = 'CNC'
PRODUCT_TYPE_INTRADAY = 'INTRADAY'
PRODUCT_TYPE_MARGIN = 'MARGIN'

VALID_PRODUCT_TYPES: Set[str] = {PRODUCT_TYPE_CNC, PRODUCT_TYPE_INTRADAY, PRODUCT_TYPE_MARGIN}

# ============================================================================
# HTTP Status Code Constants
# ============================================================================
# Commonly used HTTP status code for successful requests.
CODE_OK = 200

# Common HTTP status codes for reference
# Comprehensive mapping for error handling and logging throughout the system.
HTTP_STATUS_CODES: Dict[int, str] = {
    200: "OK - Request successful",
    201: "Created - Resource successfully created",
    204: "No Content - Request successful but no content to return",
    400: "Bad Request - Invalid syntax or parameters",
    401: "Unauthorized - Authentication required or failed",
    403: "Forbidden - Authenticated but not authorized",
    404: "Not Found - Resource does not exist",
    429: "Too Many Requests - Rate limit exceeded",
    500: "Internal Server Error - Server-side error",
    502: "Bad Gateway - Invalid response from upstream server",
    503: "Service Unavailable - Temporarily overloaded or down",
    504: "Gateway Timeout - Upstream server timeout"
}

# ============================================================================
# Default Bot Operation Type
# ============================================================================
# Default operational mode for the bot. Can be overridden via configuration.
# Set to LIVE as production default, but typically overridden in development.
BOT_TYPE = LIVE  # Default to LIVE, but can be overridden

# ============================================================================
# Order Lifecycle Status
# ============================================================================
# Represents the current state of an order in the system.
# Used for order tracking and position management.
# - OPEN: Order submitted but not yet filled/completed
# - CLOSED: Order fully executed and position closed
# - REJECTED: Order failed validation or was rejected by broker
ORDER_OPEN = 'OPEN'
ORDER_CLOSED = 'CLOSED'
ORDER_REJECTED = 'REJECTED'

VALID_ORDER_STATUSES: Set[str] = {ORDER_OPEN, ORDER_CLOSED, ORDER_REJECTED}

# ============================================================================
# Price Movement Directions
# ============================================================================
# Symbolic representation of price direction for signal generation and analysis.
# - POSITIVE (+): Upward price movement / Bullish signal
# - NEGATIVE (-): Downward price movement / Bearish signal
POSITIVE = '+'
NEGATIVE = '-'

VALID_PRICE_DIRECTIONS: Set[str] = {POSITIVE, NEGATIVE}

# ============================================================================
# Trade Execution Actions
# ============================================================================
# Core trading actions for position management.
# Used by the execution engine to process trading signals.
# - Enter Long: Open a new long (buy) position
# - Exit Long: Close an existing long position
# - Enter Short: Open a new short (sell) position
# - Exit Short: Close an existing short position
ENTER_LONG = "Enter Long"
EXIT_LONG = "Exit Long"
ENTER_SHORT = "Enter Short"
EXIT_SHORT = "Exit Short"

VALID_TRADE_ACTIONS: Set[str] = {ENTER_LONG, EXIT_LONG, ENTER_SHORT, EXIT_SHORT}

# ============================================================================
# Log File Directory Configuration
# ============================================================================
# Defines the directory path for application log files.
# Attempts to create 'Data' directory in current working directory.
# Falls back to current directory if creation fails to maintain functionality.
try:
    LOG_PATH = os.path.join(os.getcwd(), 'Data')
    # Ensure the directory exists (optional, but helpful)
    os.makedirs(LOG_PATH, exist_ok=True)
except Exception as e:
    # Rule 1: Log errors but don't crash
    logger.error(f"Failed to create LOG_PATH directory: {e}", exc_info=True)
    # Fallback to current directory
    LOG_PATH = os.getcwd()

# ============================================================================
# Configuration File Directory
# ============================================================================
# Defines the directory path for configuration files.
# Creates 'config' directory if it doesn't exist.
# Falls back to current directory if creation fails to prevent application crash.
try:
    CONFIG_PATH = os.path.join(os.getcwd(), 'config')
    os.makedirs(CONFIG_PATH, exist_ok=True)
except Exception as e:
    # Rule 1: Log errors but don't crash
    logger.error(f"Failed to create CONFIG_PATH directory: {e}", exc_info=True)
    # Fallback to current directory
    CONFIG_PATH = os.getcwd()

# ============================================================================
# Order Status Numeric Constants
# ============================================================================
# Numeric code for confirmed order status used in order processing.
ORDER_STATUS_CONFIRMED = 2

# Order status mapping for better readability
# Maps broker/platform numeric status codes to human-readable descriptions.
# Used for logging, display, and debugging purposes.
ORDER_STATUS_MAP: Dict[int, str] = {
    0: "Pending - Order received but not yet processed",
    1: "Open - Order placed and waiting for execution",
    2: "Confirmed - Order executed and confirmed",
    3: "Rejected - Order rejected by broker/system",
    4: "Cancelled - Order cancelled before execution",
    5: "Completed - Order fully processed and settled"
}


# ============================================================================
# Validation Functions
# ============================================================================
# Comprehensive validation functions for all enum types.
# Each function includes error handling to prevent crashes from invalid inputs.
# Returns boolean indicating validity status.

def is_valid_bot_mode(mode: str) -> bool:
    """
    Validate bot operation mode string.

    Checks if the provided mode matches any of the predefined bot operation modes
    (BACK, SIM, LIVE, OPTI, PAPER, BACKTEST).

    Args:
        mode: Bot mode string to validate

    Returns:
        bool: True if mode is valid, False otherwise

    Example:
        >>> is_valid_bot_mode("Live")
        True
        >>> is_valid_bot_mode("Invalid")
        False
    """
    try:
        return mode in VALID_BOT_MODES
    except Exception as e:
        logger.error(f"[is_valid_bot_mode] Failed to validate {mode}: {e}", exc_info=True)
        return False


def is_valid_option_type(opt_type: str) -> bool:
    """
    Validate options contract type.

    Checks if the provided option type is either CALL or PUT.

    Args:
        opt_type: Option type to validate (CALL/PUT)

    Returns:
        bool: True if valid option type, False otherwise

    Example:
        >>> is_valid_option_type("Call")
        True
        >>> is_valid_option_type("Future")
        False
    """
    try:
        return opt_type in VALID_OPTION_TYPES
    except Exception as e:
        logger.error(f"[is_valid_option_type] Failed to validate {opt_type}: {e}", exc_info=True)
        return False


def is_valid_trend(trend: str) -> bool:
    """
    Validate market trend or signal string.

    Checks if the provided trend matches any predefined trend indicators
    including Bullish, Bearish, Enter/Exit signals, and control commands.

    Args:
        trend: Trend string to validate

    Returns:
        bool: True if valid trend, False otherwise

    Example:
        >>> is_valid_trend("Bullish")
        True
        >>> is_valid_trend("Neutral")
        False
    """
    try:
        return trend in ALL_TRENDS
    except Exception as e:
        logger.error(f"[is_valid_trend] Failed to validate {trend}: {e}", exc_info=True)
        return False


def is_valid_operator(op: str) -> bool:
    """
    Validate comparison operator.

    Checks if the provided operator is one of the standard mathematical
    comparison operators (>, <, >=, <=, ==, !=).

    Args:
        op: Operator string to validate

    Returns:
        bool: True if valid operator, False otherwise

    Example:
        >>> is_valid_operator(">=")
        True
        >>> is_valid_operator("<>")
        False
    """
    try:
        return op in VALID_OPERATORS
    except Exception as e:
        logger.error(f"[is_valid_operator] Failed to validate {op}: {e}", exc_info=True)
        return False


def is_valid_price_type(price_type: str) -> bool:
    """
    Validate OHLCV price type.

    Checks if the provided price type is one of the standard price data points
    (Open, High, Low, Close, Open/Close, High/Low).

    Args:
        price_type: Price type to validate

    Returns:
        bool: True if valid price type, False otherwise

    Example:
        >>> is_valid_price_type("Close")
        True
        >>> is_valid_price_type("Volume")
        False
    """
    try:
        return price_type in VALID_PRICE_TYPES
    except Exception as e:
        logger.error(f"[is_valid_price_type] Failed to validate {price_type}: {e}", exc_info=True)
        return False


def is_valid_order_side(side: int) -> bool:
    """
    Validate order side/direction.

    Checks if the provided side value is either 1 (BUY) or -1 (SELL).

    Args:
        side: Order side integer to validate

    Returns:
        bool: True if valid order side, False otherwise

    Example:
        >>> is_valid_order_side(1)
        True
        >>> is_valid_order_side(0)
        False
    """
    try:
        return side in VALID_ORDER_SIDES
    except Exception as e:
        logger.error(f"[is_valid_order_side] Failed to validate {side}: {e}", exc_info=True)
        return False


def is_valid_order_type(order_type: int) -> bool:
    """
    Validate order type.

    Checks if the provided order type matches predefined numeric codes
    for LIMIT, MARKET, STOPLOSS_MARKET, or STOPLOSS_LIMIT orders.

    Args:
        order_type: Order type integer to validate

    Returns:
        bool: True if valid order type, False otherwise

    Example:
        >>> is_valid_order_type(1)  # LIMIT_ORDER_TYPE
        True
        >>> is_valid_order_type(5)
        False
    """
    try:
        return order_type in VALID_ORDER_TYPES
    except Exception as e:
        logger.error(f"[is_valid_order_type] Failed to validate {order_type}: {e}", exc_info=True)
        return False


def is_valid_product_type(product_type: str) -> bool:
    """
    Validate trading product type.

    Checks if the provided product type is one of CNC, INTRADAY, or MARGIN.

    Args:
        product_type: Product type string to validate

    Returns:
        bool: True if valid product type, False otherwise

    Example:
        >>> is_valid_product_type("INTRADAY")
        True
        >>> is_valid_product_type("FUTURE")
        False
    """
    try:
        return product_type in VALID_PRODUCT_TYPES
    except Exception as e:
        logger.error(f"[is_valid_product_type] Failed to validate {product_type}: {e}", exc_info=True)
        return False


def is_valid_trade_action(action: str) -> bool:
    """
    Validate trade execution action.

    Checks if the provided action is one of the core trading commands
    (Enter Long, Exit Long, Enter Short, Exit Short).

    Args:
        action: Trade action string to validate

    Returns:
        bool: True if valid trade action, False otherwise

    Example:
        >>> is_valid_trade_action("Enter Long")
        True
        >>> is_valid_trade_action("Hold")
        False
    """
    try:
        return action in VALID_TRADE_ACTIONS
    except Exception as e:
        logger.error(f"[is_valid_trade_action] Failed to validate {action}: {e}", exc_info=True)
        return False


def is_valid_backtest_status(status: str) -> bool:
    """
    Validate backtest execution status.

    Checks if the provided status matches one of the backtest lifecycle states
    (Pending, Running, Completed, Failed).

    Args:
        status: Backtest status string to validate

    Returns:
        bool: True if valid backtest status, False otherwise

    Example:
        >>> is_valid_backtest_status("Running")
        True
        >>> is_valid_backtest_status("Paused")
        False
    """
    try:
        return status in VALID_BACKTEST_STATUSES
    except Exception as e:
        logger.error(f"[is_valid_backtest_status] Failed to validate {status}: {e}", exc_info=True)
        return False


def is_valid_trade_type(trade_type: str) -> bool:
    """
    Validate trading strategy type.

    Checks if the provided trade type is one of the predefined strategy
    classifications (Scalping, Normal, Expiry).

    Args:
        trade_type: Trade type string to validate

    Returns:
        bool: True if valid trade type, False otherwise

    Example:
        >>> is_valid_trade_type("Scalping")
        True
        >>> is_valid_trade_type("Swing")
        False
    """
    try:
        return trade_type in VALID_TRADE_TYPES
    except Exception as e:
        logger.error(f"[is_valid_trade_type] Failed to validate {trade_type}: {e}", exc_info=True)
        return False


def get_http_status_description(status_code: int) -> str:
    """
    Get human-readable description for HTTP status code.

    Retrieves the standardized description for common HTTP status codes.
    Used for logging, error messages, and debugging.

    Args:
        status_code: HTTP status code integer

    Returns:
        str: Human-readable description or "Unknown" if not found

    Example:
        >>> get_http_status_description(404)
        "Not Found - Resource does not exist"
    """
    try:
        return HTTP_STATUS_CODES.get(status_code, f"Unknown status code {status_code}")
    except Exception as e:
        logger.error(f"[get_http_status_description] Failed for {status_code}: {e}", exc_info=True)
        return f"Unknown status code {status_code}"


def get_order_status_description(status_code: int) -> str:
    """
    Get human-readable description for order status code.

    Maps numeric order status codes from broker/platform to descriptive text.
    Used for order tracking, display, and debugging.

    Args:
        status_code: Order status code integer

    Returns:
        str: Human-readable description or "Unknown" if not found

    Example:
        >>> get_order_status_description(2)
        "Confirmed - Order executed and confirmed"
    """
    try:
        return ORDER_STATUS_MAP.get(status_code, f"Unknown order status {status_code}")
    except Exception as e:
        logger.error(f"[get_order_status_description] Failed for {status_code}: {e}", exc_info=True)
        return f"Unknown order status {status_code}"


# ============================================================================
# Backward Compatibility Exports
# ============================================================================
# Maintains all original constants and functions for backward compatibility.
# Existing imports from this module will continue to work without modification.
# Re-export all original constants (already defined above)
__all__ = [
    # Bot Modes
    'BACK', 'SIM', 'LIVE', 'OPTI', 'PAPER', 'BACKTEST',

    # Backtest Status
    'BACKTEST_PENDING', 'BACKTEST_RUNNING', 'BACKTEST_COMPLETED', 'BACKTEST_FAILED',

    # Trade Types
    'TRADE_TYPE_SCALPING', 'TRADE_TYPE_NORMAL', 'TRADE_TYPE_EXPIRY',

    # Trend Indicators
    'BULLISH', 'BEARISH', 'ENTER_CALL', 'EXIT_CALL', 'ENTER_PUT', 'EXIT_PUT',
    'CANCEL_PUT', 'CANCEL_CALL', 'CANCEL_TRADE', 'PREVIOUS_TRADE', 'RESET_PREVIOUS_TRADE',

    # Market Conditions
    'TRENDING', 'SIDEWAYS', 'TRENDS', 'ALL_TRENDS', 'PRICE_TYPES',

    # Operators
    'OPERATORS',

    # Option Types
    'CALL', 'PUT',

    # Stop Loss Types
    'TRAILING', 'STOP',

    # Response Status
    'OK', 'ERROR',

    # Order Sides
    'SIDE_BUY', 'SIDE_SELL',

    # Order Types
    'LIMIT_ORDER_TYPE', 'MARKET_ORDER_TYPE', 'STOPLOSS_MARKET_ORDER_TYPE',
    'STOPLOSS_LIMIT_ORDER_TYPE',

    # Product Types
    'PRODUCT_TYPE_CNC', 'PRODUCT_TYPE_INTRADAY', 'PRODUCT_TYPE_MARGIN',

    # HTTP Status
    'CODE_OK',

    # Bot Type
    'BOT_TYPE',

    # Order Status
    'ORDER_OPEN', 'ORDER_CLOSED', 'ORDER_REJECTED',

    # Price Directions
    'POSITIVE', 'NEGATIVE',

    # Trade Actions
    'ENTER_LONG', 'EXIT_LONG', 'ENTER_SHORT', 'EXIT_SHORT',

    # Paths
    'LOG_PATH', 'CONFIG_PATH',

    # Order Status Constants
    'ORDER_STATUS_CONFIRMED',

    # Validation Functions
    'is_valid_bot_mode', 'is_valid_option_type', 'is_valid_trend', 'is_valid_operator',
    'is_valid_price_type', 'is_valid_order_side', 'is_valid_order_type', 'is_valid_product_type',
    'is_valid_trade_action', 'is_valid_backtest_status', 'is_valid_trade_type',
    'get_http_status_description', 'get_order_status_description',

    # Validation Sets
    'VALID_BOT_MODES', 'VALID_BACKTEST_STATUSES', 'VALID_TRADE_TYPES', 'VALID_PRICE_TYPES',
    'VALID_OPERATORS', 'VALID_OPTION_TYPES', 'VALID_STOP_TYPES', 'VALID_RESPONSE_STATUSES',
    'VALID_ORDER_SIDES', 'VALID_ORDER_TYPES', 'VALID_PRODUCT_TYPES', 'VALID_TRADE_ACTIONS',
    'HTTP_STATUS_CODES', 'ORDER_STATUS_MAP'
]