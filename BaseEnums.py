import os
import logging
from pathlib import Path
from typing import Dict, Any, Set, List, Optional

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

# ============================================================================
# Bot Modes
# ============================================================================
# Add after existing bot modes
# Bot Modes
BACK = "Backtest"
SIM = "Simulation"  # Paper trading
LIVE = "Live"
OPTI = "Optimizer"

# Add new enums
PAPER = "Paper"  # Alias for SIM
BACKTEST = "Backtest"

# Valid bot modes for validation
VALID_BOT_MODES: Set[str] = {BACK, SIM, LIVE, OPTI, PAPER, BACKTEST}

# ============================================================================
# Backtest status
# ============================================================================
BACKTEST_PENDING = "Pending"
BACKTEST_RUNNING = "Running"
BACKTEST_COMPLETED = "Completed"
BACKTEST_FAILED = "Failed"
TRENDING = "Trending"
SIDEWAYS = "Sideways"

VALID_BACKTEST_STATUSES: Set[str] = {
    BACKTEST_PENDING, BACKTEST_RUNNING, BACKTEST_COMPLETED, BACKTEST_FAILED
}

# ============================================================================
# Trade Types
# ============================================================================
TRADE_TYPE_SCALPING = "Scalping"
TRADE_TYPE_NORMAL = "Normal"
TRADE_TYPE_EXPIRY = "Expiry"

VALID_TRADE_TYPES: Set[str] = {TRADE_TYPE_SCALPING, TRADE_TYPE_NORMAL, TRADE_TYPE_EXPIRY}

# ============================================================================
# Trend Indicators
# ============================================================================
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
TRENDS: List[str] = [ENTER_CALL, EXIT_CALL, ENTER_PUT, EXIT_PUT]
ALL_TRENDS: Set[str] = {*TRENDS, BULLISH, BEARISH, CANCEL_PUT, CANCEL_CALL,
                        CANCEL_TRADE, PREVIOUS_TRADE, RESET_PREVIOUS_TRADE}

# ============================================================================
# Price Types
# ============================================================================
PRICE_TYPES: List[str] = ['Open', 'High', 'Low', 'Close', 'Open/Close', 'High/Low']
VALID_PRICE_TYPES: Set[str] = set(PRICE_TYPES)

# ============================================================================
# Operators for Conditions
# ============================================================================
OPERATORS: List[str] = ['>', '<', '>=', '<=', '==', '!=']
VALID_OPERATORS: Set[str] = set(OPERATORS)

# ============================================================================
# Option Types
# ============================================================================
CALL = "Call"
PUT = "Put"

VALID_OPTION_TYPES: Set[str] = {CALL, PUT}

# ============================================================================
# Stop Loss and Trailing Types
# ============================================================================
TRAILING = "TRAILING"
STOP = "STOP"

VALID_STOP_TYPES: Set[str] = {TRAILING, STOP}

# ============================================================================
# Response Status
# ============================================================================
OK = 'ok'
ERROR = 'error'

VALID_RESPONSE_STATUSES: Set[str] = {OK, ERROR}

# ============================================================================
# Order Sides
# ============================================================================
SIDE_BUY = 1
SIDE_SELL = -1

VALID_ORDER_SIDES: Set[int] = {SIDE_BUY, SIDE_SELL}

# ============================================================================
# Order Types
# ============================================================================
LIMIT_ORDER_TYPE = 1
MARKET_ORDER_TYPE = 2
STOPLOSS_MARKET_ORDER_TYPE = 3
STOPLOSS_LIMIT_ORDER_TYPE = 4

VALID_ORDER_TYPES: Set[int] = {
    LIMIT_ORDER_TYPE, MARKET_ORDER_TYPE,
    STOPLOSS_MARKET_ORDER_TYPE, STOPLOSS_LIMIT_ORDER_TYPE
}

# ============================================================================
# Product Types
# ============================================================================
PRODUCT_TYPE_CNC = 'CNC'
PRODUCT_TYPE_INTRADAY = 'INTRADAY'
PRODUCT_TYPE_MARGIN = 'MARGIN'

VALID_PRODUCT_TYPES: Set[str] = {PRODUCT_TYPE_CNC, PRODUCT_TYPE_INTRADAY, PRODUCT_TYPE_MARGIN}

# ============================================================================
# HTTP Status Codes
# ============================================================================
CODE_OK = 200

# Common HTTP status codes for reference
HTTP_STATUS_CODES: Dict[int, str] = {
    200: "OK",
    201: "Created",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout"
}

# ============================================================================
# Bot Operation Type
# ============================================================================
BOT_TYPE = LIVE  # Default to LIVE, but can be overridden

# ============================================================================
# Order Status
# ============================================================================
ORDER_OPEN = 'OPEN'
ORDER_CLOSED = 'CLOSED'
ORDER_REJECTED = 'REJECTED'

VALID_ORDER_STATUSES: Set[str] = {ORDER_OPEN, ORDER_CLOSED, ORDER_REJECTED}

# ============================================================================
# Price Directions
# ============================================================================
POSITIVE = '+'
NEGATIVE = '-'

VALID_PRICE_DIRECTIONS: Set[str] = {POSITIVE, NEGATIVE}

# ============================================================================
# Trade Actions
# ============================================================================
ENTER_LONG = "Enter Long"
EXIT_LONG = "Exit Long"
ENTER_SHORT = "Enter Short"
EXIT_SHORT = "Exit Short"

VALID_TRADE_ACTIONS: Set[str] = {ENTER_LONG, EXIT_LONG, ENTER_SHORT, EXIT_SHORT}

# ============================================================================
# Log Path
# ============================================================================
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
# Config Path
# ============================================================================
try:
    CONFIG_PATH = os.path.join(os.getcwd(), 'config')
    os.makedirs(CONFIG_PATH, exist_ok=True)
except Exception as e:
    # Rule 1: Log errors but don't crash
    logger.error(f"Failed to create CONFIG_PATH directory: {e}", exc_info=True)
    # Fallback to current directory
    CONFIG_PATH = os.getcwd()

# ============================================================================
# Order Status Constants
# ============================================================================
ORDER_STATUS_CONFIRMED = 2

# Order status mapping for better readability
ORDER_STATUS_MAP: Dict[int, str] = {
    0: "Pending",
    1: "Open",
    2: "Confirmed",
    3: "Rejected",
    4: "Cancelled",
    5: "Completed"
}


# ============================================================================
# Validation Functions
# ============================================================================

def is_valid_bot_mode(mode: str) -> bool:
    """
    Check if a bot mode is valid.

    Args:
        mode: Bot mode string to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return mode in VALID_BOT_MODES
    except Exception as e:
        logger.error(f"[is_valid_bot_mode] Failed to validate {mode}: {e}", exc_info=True)
        return False


def is_valid_option_type(opt_type: str) -> bool:
    """
    Check if an option type is valid.

    Args:
        opt_type: Option type to validate (CALL/PUT)

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return opt_type in VALID_OPTION_TYPES
    except Exception as e:
        logger.error(f"[is_valid_option_type] Failed to validate {opt_type}: {e}", exc_info=True)
        return False


def is_valid_trend(trend: str) -> bool:
    """
    Check if a trend value is valid.

    Args:
        trend: Trend string to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return trend in ALL_TRENDS
    except Exception as e:
        logger.error(f"[is_valid_trend] Failed to validate {trend}: {e}", exc_info=True)
        return False


def is_valid_operator(op: str) -> bool:
    """
    Check if an operator is valid.

    Args:
        op: Operator string to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return op in VALID_OPERATORS
    except Exception as e:
        logger.error(f"[is_valid_operator] Failed to validate {op}: {e}", exc_info=True)
        return False


def is_valid_price_type(price_type: str) -> bool:
    """
    Check if a price type is valid.

    Args:
        price_type: Price type to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return price_type in VALID_PRICE_TYPES
    except Exception as e:
        logger.error(f"[is_valid_price_type] Failed to validate {price_type}: {e}", exc_info=True)
        return False


def is_valid_order_side(side: int) -> bool:
    """
    Check if an order side is valid.

    Args:
        side: Order side to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return side in VALID_ORDER_SIDES
    except Exception as e:
        logger.error(f"[is_valid_order_side] Failed to validate {side}: {e}", exc_info=True)
        return False


def is_valid_order_type(order_type: int) -> bool:
    """
    Check if an order type is valid.

    Args:
        order_type: Order type to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return order_type in VALID_ORDER_TYPES
    except Exception as e:
        logger.error(f"[is_valid_order_type] Failed to validate {order_type}: {e}", exc_info=True)
        return False


def is_valid_product_type(product_type: str) -> bool:
    """
    Check if a product type is valid.

    Args:
        product_type: Product type to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return product_type in VALID_PRODUCT_TYPES
    except Exception as e:
        logger.error(f"[is_valid_product_type] Failed to validate {product_type}: {e}", exc_info=True)
        return False


def is_valid_trade_action(action: str) -> bool:
    """
    Check if a trade action is valid.

    Args:
        action: Trade action to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return action in VALID_TRADE_ACTIONS
    except Exception as e:
        logger.error(f"[is_valid_trade_action] Failed to validate {action}: {e}", exc_info=True)
        return False


def is_valid_backtest_status(status: str) -> bool:
    """
    Check if a backtest status is valid.

    Args:
        status: Backtest status to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return status in VALID_BACKTEST_STATUSES
    except Exception as e:
        logger.error(f"[is_valid_backtest_status] Failed to validate {status}: {e}", exc_info=True)
        return False


def is_valid_trade_type(trade_type: str) -> bool:
    """
    Check if a trade type is valid.

    Args:
        trade_type: Trade type to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return trade_type in VALID_TRADE_TYPES
    except Exception as e:
        logger.error(f"[is_valid_trade_type] Failed to validate {trade_type}: {e}", exc_info=True)
        return False


def get_http_status_description(status_code: int) -> str:
    """
    Get description for HTTP status code.

    Args:
        status_code: HTTP status code

    Returns:
        str: Description or "Unknown" if not found
    """
    try:
        return HTTP_STATUS_CODES.get(status_code, f"Unknown status code {status_code}")
    except Exception as e:
        logger.error(f"[get_http_status_description] Failed for {status_code}: {e}", exc_info=True)
        return f"Unknown status code {status_code}"


def get_order_status_description(status_code: int) -> str:
    """
    Get description for order status code.

    Args:
        status_code: Order status code

    Returns:
        str: Description or "Unknown" if not found
    """
    try:
        return ORDER_STATUS_MAP.get(status_code, f"Unknown order status {status_code}")
    except Exception as e:
        logger.error(f"[get_order_status_description] Failed for {status_code}: {e}", exc_info=True)
        return f"Unknown order status {status_code}"


# ============================================================================
# Ensure backwards compatibility with existing imports
# All original constants remain exactly as they were
# ============================================================================

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