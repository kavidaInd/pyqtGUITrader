"""
BaseEnums.py
============
Centralised constants and enumerations for the Trading Assistant.

Changes from original:
- Replaced 15+ loose string/int constants with proper Python Enum classes
  (BotMode, BacktestStatus, TradeType, Signal, OptionType, StopType, TradeAction)
  for type-safety and IDE auto-complete.
- Removed 12 near-identical single-line validation functions; each Enum now
  exposes .is_valid(value) classmethod — one place to update.
- Removed unused HTTP_STATUS_CODES dict (never called outside this file).
- Removed duplicate ORDER_STATUS_MAP (broker responses carry their own codes).
- Consolidated LOG_PATH / CONFIG_PATH creation into _ensure_dir() helper so
  directory-creation errors are handled once.
- All backward-compat module-level names (LIVE, PAPER, CALL, etc.) preserved —
  zero breaking changes for existing imports.
"""

from __future__ import annotations

import logging
import os
from enum import Enum, unique
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Directory helpers ─────────────────────────────────────────────────────────

def _ensure_dir(name: str) -> str:
    """Create *name* subdirectory under cwd and return its absolute path."""
    try:
        p = Path.cwd() / name
        p.mkdir(parents=True, exist_ok=True)
        return str(p)
    except Exception as exc:
        logger.error("Failed to create directory %r: %s", name, exc)
        return str(Path.cwd())


LOG_PATH: str = _ensure_dir("Data")
CONFIG_PATH: str = _ensure_dir("config")


# ── Bot Modes ─────────────────────────────────────────────────────────────────

@unique
class BotMode(str, Enum):
    LIVE = "Live"
    PAPER = "Paper"
    BACKTEST = "Backtest"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls._value2member_map_


LIVE = BotMode.LIVE.value
PAPER = BotMode.PAPER.value
BACKTEST = BotMode.BACKTEST.value
VALID_BOT_MODES = {m.value for m in BotMode}
BOT_TYPE = LIVE


# ── Backtest Status ───────────────────────────────────────────────────────────

@unique
class BacktestStatus(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls._value2member_map_


BACKTEST_PENDING = BacktestStatus.PENDING.value
BACKTEST_RUNNING = BacktestStatus.RUNNING.value
BACKTEST_COMPLETED = BacktestStatus.COMPLETED.value
BACKTEST_FAILED = BacktestStatus.FAILED.value
VALID_BACKTEST_STATUSES = {s.value for s in BacktestStatus}

TRENDING = "Trending"
SIDEWAYS = "Sideways"


# ── Trade Types ───────────────────────────────────────────────────────────────

@unique
class TradeType(str, Enum):
    SCALPING = "Scalping"
    NORMAL = "Normal"
    EXPIRY = "Expiry"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls._value2member_map_


TRADE_TYPE_SCALPING = TradeType.SCALPING.value
TRADE_TYPE_NORMAL = TradeType.NORMAL.value
TRADE_TYPE_EXPIRY = TradeType.EXPIRY.value
VALID_TRADE_TYPES = {t.value for t in TradeType}


# ── Signal / Trend Values ─────────────────────────────────────────────────────

@unique
class Signal(str, Enum):
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
    RESET_PREVIOUS_TRADE = "RESET"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls._value2member_map_


BULLISH = Signal.BULLISH.value
BEARISH = Signal.BEARISH.value
ENTER_CALL = Signal.ENTER_CALL.value
EXIT_CALL = Signal.EXIT_CALL.value
ENTER_PUT = Signal.ENTER_PUT.value
EXIT_PUT = Signal.EXIT_PUT.value
CANCEL_PUT = Signal.CANCEL_PUT.value
CANCEL_CALL = Signal.CANCEL_CALL.value
CANCEL_TRADE = Signal.CANCEL_TRADE.value
PREVIOUS_TRADE = Signal.PREVIOUS_TRADE.value
RESET_PREVIOUS_TRADE = Signal.RESET_PREVIOUS_TRADE.value

# Ordered list for iteration (entry/exit only)
TRENDS = [ENTER_CALL, EXIT_CALL, ENTER_PUT, EXIT_PUT]
ALL_TRENDS = {s.value for s in Signal}


# ── OHLCV Price Types ─────────────────────────────────────────────────────────

PRICE_TYPES = ["Open", "High", "Low", "Close", "Open/Close", "High/Low"]
VALID_PRICE_TYPES = set(PRICE_TYPES)


# ── Comparison Operators ──────────────────────────────────────────────────────

OPERATORS = [">", "<", ">=", "<=", "==", "!="]
VALID_OPERATORS = set(OPERATORS)


# ── Option Types ──────────────────────────────────────────────────────────────

@unique
class OptionType(str, Enum):
    CALL = "Call"
    PUT = "Put"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls._value2member_map_


CALL = OptionType.CALL.value
PUT = OptionType.PUT.value
VALID_OPTION_TYPES = {o.value for o in OptionType}


# ── Stop Loss Types ───────────────────────────────────────────────────────────

@unique
class StopType(str, Enum):
    TRAILING = "TRAILING"
    STOP = "STOP"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls._value2member_map_


TRAILING = StopType.TRAILING.value
STOP = StopType.STOP.value
VALID_STOP_TYPES = {s.value for s in StopType}


# ── API Response Status ───────────────────────────────────────────────────────

OK = "ok"
ERROR = "error"
VALID_RESPONSE_STATUSES = {OK, ERROR}


# ── Order Direction ───────────────────────────────────────────────────────────

SIDE_BUY = 1
SIDE_SELL = -1
VALID_ORDER_SIDES = {SIDE_BUY, SIDE_SELL}


# ── Order Types ───────────────────────────────────────────────────────────────

LIMIT_ORDER_TYPE = 1
MARKET_ORDER_TYPE = 2
STOPLOSS_MARKET_ORDER_TYPE = 3
STOPLOSS_LIMIT_ORDER_TYPE = 4
VALID_ORDER_TYPES = {
    LIMIT_ORDER_TYPE, MARKET_ORDER_TYPE,
    STOPLOSS_MARKET_ORDER_TYPE, STOPLOSS_LIMIT_ORDER_TYPE,
}


# ── Product Types ─────────────────────────────────────────────────────────────

PRODUCT_TYPE_CNC = "CNC"
PRODUCT_TYPE_INTRADAY = "INTRADAY"
PRODUCT_TYPE_MARGIN = "MARGIN"
VALID_PRODUCT_TYPES = {PRODUCT_TYPE_CNC, PRODUCT_TYPE_INTRADAY, PRODUCT_TYPE_MARGIN}


# ── HTTP ──────────────────────────────────────────────────────────────────────

CODE_OK = 200


# ── Order Lifecycle ───────────────────────────────────────────────────────────

ORDER_OPEN = "OPEN"
ORDER_CLOSED = "CLOSED"
ORDER_REJECTED = "REJECTED"
VALID_ORDER_STATUSES = {ORDER_OPEN, ORDER_CLOSED, ORDER_REJECTED}
ORDER_STATUS_CONFIRMED = 2


# ── Price Directions ──────────────────────────────────────────────────────────

POSITIVE = "+"
NEGATIVE = "-"
VALID_PRICE_DIRECTIONS = {POSITIVE, NEGATIVE}


# ── Trade Actions ─────────────────────────────────────────────────────────────

@unique
class TradeAction(str, Enum):
    ENTER_LONG = "Enter Long"
    EXIT_LONG = "Exit Long"
    ENTER_SHORT = "Enter Short"
    EXIT_SHORT = "Exit Short"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls._value2member_map_


ENTER_LONG = TradeAction.ENTER_LONG.value
EXIT_LONG = TradeAction.EXIT_LONG.value
ENTER_SHORT = TradeAction.ENTER_SHORT.value
EXIT_SHORT = TradeAction.EXIT_SHORT.value
VALID_TRADE_ACTIONS = {a.value for a in TradeAction}


# ── Backward-compat validation helpers ───────────────────────────────────────
# Kept so any existing code calling is_valid_*() still works unchanged.

def is_valid_bot_mode(mode: str) -> bool:
    return BotMode.is_valid(mode)

def is_valid_option_type(opt_type: str) -> bool:
    return OptionType.is_valid(opt_type)

def is_valid_trend(trend: str) -> bool:
    return trend in ALL_TRENDS

def is_valid_operator(op: str) -> bool:
    return op in VALID_OPERATORS

def is_valid_price_type(price_type: str) -> bool:
    return price_type in VALID_PRICE_TYPES

def is_valid_order_side(side: int) -> bool:
    return side in VALID_ORDER_SIDES

def is_valid_order_type(order_type: int) -> bool:
    return order_type in VALID_ORDER_TYPES

def is_valid_product_type(product_type: str) -> bool:
    return product_type in VALID_PRODUCT_TYPES

def is_valid_trade_action(action: str) -> bool:
    return TradeAction.is_valid(action)

def is_valid_backtest_status(status: str) -> bool:
    return BacktestStatus.is_valid(status)

def is_valid_trade_type(trade_type: str) -> bool:
    return TradeType.is_valid(trade_type)

def get_order_status_description(status_code: int) -> str:
    return {
        0: "Pending", 1: "Open", 2: "Confirmed",
        3: "Rejected", 4: "Cancelled", 5: "Completed",
    }.get(status_code, f"Unknown ({status_code})")

def get_http_status_description(status_code: int) -> str:
    return {
        200: "OK", 201: "Created", 204: "No Content",
        400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
        404: "Not Found", 429: "Too Many Requests",
        500: "Internal Server Error", 502: "Bad Gateway",
        503: "Service Unavailable", 504: "Gateway Timeout",
    }.get(status_code, f"Unknown ({status_code})")


# ── Public API ────────────────────────────────────────────────────────────────

__all__ = [
    "BotMode", "BacktestStatus", "TradeType", "Signal",
    "OptionType", "StopType", "TradeAction",
    "LIVE", "PAPER", "BACKTEST", "BOT_TYPE", "VALID_BOT_MODES",
    "BACKTEST_PENDING", "BACKTEST_RUNNING", "BACKTEST_COMPLETED", "BACKTEST_FAILED",
    "VALID_BACKTEST_STATUSES",
    "TRADE_TYPE_SCALPING", "TRADE_TYPE_NORMAL", "TRADE_TYPE_EXPIRY", "VALID_TRADE_TYPES",
    "BULLISH", "BEARISH", "ENTER_CALL", "EXIT_CALL", "ENTER_PUT", "EXIT_PUT",
    "CANCEL_PUT", "CANCEL_CALL", "CANCEL_TRADE", "PREVIOUS_TRADE", "RESET_PREVIOUS_TRADE",
    "TRENDING", "SIDEWAYS", "TRENDS", "ALL_TRENDS",
    "PRICE_TYPES", "VALID_PRICE_TYPES", "OPERATORS", "VALID_OPERATORS",
    "CALL", "PUT", "VALID_OPTION_TYPES",
    "TRAILING", "STOP", "VALID_STOP_TYPES",
    "OK", "ERROR", "VALID_RESPONSE_STATUSES",
    "SIDE_BUY", "SIDE_SELL", "VALID_ORDER_SIDES",
    "LIMIT_ORDER_TYPE", "MARKET_ORDER_TYPE",
    "STOPLOSS_MARKET_ORDER_TYPE", "STOPLOSS_LIMIT_ORDER_TYPE", "VALID_ORDER_TYPES",
    "PRODUCT_TYPE_CNC", "PRODUCT_TYPE_INTRADAY", "PRODUCT_TYPE_MARGIN", "VALID_PRODUCT_TYPES",
    "CODE_OK",
    "ORDER_OPEN", "ORDER_CLOSED", "ORDER_REJECTED", "VALID_ORDER_STATUSES",
    "ORDER_STATUS_CONFIRMED",
    "POSITIVE", "NEGATIVE", "VALID_PRICE_DIRECTIONS",
    "ENTER_LONG", "EXIT_LONG", "ENTER_SHORT", "EXIT_SHORT", "VALID_TRADE_ACTIONS",
    "LOG_PATH", "CONFIG_PATH",
    "is_valid_bot_mode", "is_valid_option_type", "is_valid_trend", "is_valid_operator",
    "is_valid_price_type", "is_valid_order_side", "is_valid_order_type",
    "is_valid_product_type", "is_valid_trade_action", "is_valid_backtest_status",
    "is_valid_trade_type", "get_order_status_description", "get_http_status_description",
]