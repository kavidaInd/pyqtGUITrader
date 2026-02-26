"""
Database CRUD Module
====================
Comprehensive CRUD (Create, Read, Update, Delete) operations for all database tables.

This module provides a complete set of database operations organized by table,
replacing the previous JSON file-based configuration storage with a robust
relational database backend. Each CRUD class corresponds to a specific table
and provides type-safe operations with comprehensive error handling.

Architecture:
    The module is organized into separate CRUD classes, each responsible for
    a specific table in the database:

    1. **BrokerageCRUD**: Broker connection settings (replaces brokerage_setting.json)
    2. **DailyTradeCRUD**: Daily trading parameters (replaces daily_trade_setting.json)
    3. **ProfitStoplossCRUD**: P&L configuration (replaces profit_stoploss_setting.json)
    4. **TradingModeCRUD**: Trading mode settings (replaces trading_mode.json)
    5. **StrategiesCRUD**: Strategy definitions (replaces strategies/*.json)
    6. **TokenCRUD**: Broker authentication tokens (replaces access_token file)
    7. **SessionCRUD**: Trading session tracking
    8. **OrderCRUD**: Individual order management
    9. **KVCRUD**: Generic key-value store (for miscellaneous config)

Key Features:
    - **Stateless Design**: All functions accept optional database connector
    - **Type Safety**: Proper type conversion for boolean and numeric fields
    - **JSON Serialization**: Automatic handling of complex data structures
    - **Error Handling**: Comprehensive error logging with fallback defaults
    - **Transaction Support**: Batch operations use proper transactions
    - **Singleton Pattern**: Pre-configured instances for each CRUD class

Design Principles:
    - Each CRUD class is independent and focused on one table
    - All methods return bool for write operations, proper types for reads
    - Default values ensure application works even if DB not yet initialized
    - Testability: optional db parameter allows injection of test connector

Usage:
    from db.crud import (
        brokerage, daily_trade, profit_stoploss,
        trading_mode, strategies, tokens, sessions, orders, kv
    )

    # Get current settings
    config = brokerage.get()

    # Update settings
    success = trading_mode.set_mode("LIVE")

    # List strategies
    all_strategies = strategies.list_all()

    # Create a new session
    session_id = sessions.create(mode="PAPER", derivative="NIFTY")

    # Store key-value pairs
    kv.set("last_updated", datetime.now().isoformat())

Version: 1.0.0
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from db.connector import DatabaseConnector, get_db

logger = logging.getLogger(__name__)

# Helper for consistent timestamp formatting across all CRUD operations
_NOW = lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ══════════════════════════════════════════════════════════════════════════════
# Helper
# ══════════════════════════════════════════════════════════════════════════════

def _row_to_dict(row: Optional[sqlite3.Row]) -> Dict[str, Any]:
    """
    Convert a sqlite3.Row (or None) to a plain Python dictionary.

    Args:
        row: SQLite row object or None

    Returns:
        Dict[str, Any]: Dictionary representation of the row, or empty dict if None
    """
    if row is None:
        return {}
    return dict(row)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Brokerage Setting  (replaces config/brokerage_setting.json)
# ══════════════════════════════════════════════════════════════════════════════

class BrokerageCRUD:
    """
    CRUD operations for broker connection settings.

    This class manages the singleton brokerage_setting table which stores
    credentials and configuration for the selected broker. It handles:
        - Broker type selection (fyers, zerodha, dhan, etc.)
        - API credentials (client_id, secret_key)
        - OAuth redirect URI

    The table contains exactly one row (id=1) that is updated in place.
    """

    TABLE = "brokerage_setting"
    FIELDS = ("broker_type", "client_id", "secret_key", "redirect_uri")

    def get(self, db: DatabaseConnector = None) -> Dict[str, str]:
        """
        Return the current brokerage credentials.

        Args:
            db: Optional database connector. If None, uses global singleton.

        Returns:
            Dict[str, str]: Dictionary with keys: broker_type, client_id,
                           secret_key, redirect_uri. Missing keys default to empty strings.
        """
        db = db or get_db()
        row = db.fetchone(f"SELECT * FROM {self.TABLE} WHERE id = 1")
        return _row_to_dict(row)

    def update(
            self,
            broker_type: str = None,
            client_id: str = None,
            secret_key: str = None,
            redirect_uri: str = None,
            db: DatabaseConnector = None,
    ) -> bool:
        """
        Update one or more credential fields.

        This method performs a partial update - only provided fields are changed.
        Fields not provided retain their current values.

        Args:
            broker_type: Broker identifier (e.g., "fyers", "zerodha")
            client_id: API client ID / key
            secret_key: API secret key
            redirect_uri: OAuth redirect URI
            db: Optional database connector

        Returns:
            bool: True if update successful, False otherwise
        """
        db = db or get_db()
        current = self.get(db)
        data = {
            "broker_type": broker_type if broker_type is not None else current.get("broker_type", "fyers"),
            "client_id": client_id if client_id is not None else current.get("client_id", ""),
            "secret_key": secret_key if secret_key is not None else current.get("secret_key", ""),
            "redirect_uri": redirect_uri if redirect_uri is not None else current.get("redirect_uri", ""),
            "updated_at": _NOW(),
        }
        try:
            db.execute(
                f"""UPDATE {self.TABLE}
                    SET broker_type=?, client_id=?, secret_key=?,
                        redirect_uri=?, updated_at=?
                    WHERE id = 1""",
                (data["broker_type"], data["client_id"], data["secret_key"],
                 data["redirect_uri"], data["updated_at"]),
            )
            return True
        except Exception as e:
            logger.error(f"[BrokerageCRUD.update] {e}", exc_info=True)
            return False

    def save(self, data: Dict[str, str], db: DatabaseConnector = None) -> bool:
        """
        Overwrite all credential fields from a dictionary.

        This method mirrors the from_dict/save behavior from the old
        JSON-based configuration.

        Args:
            data: Dictionary containing all credential fields
            db: Optional database connector

        Returns:
            bool: True if save successful, False otherwise
        """
        return self.update(
            broker_type=data.get("broker_type", "fyers"),
            client_id=data.get("client_id", ""),
            secret_key=data.get("secret_key", ""),
            redirect_uri=data.get("redirect_uri", ""),
            db=db,
        )

    def validate(self, db: DatabaseConnector = None) -> Dict[str, bool]:
        """
        Return a per-field validity map.

        Checks which credential fields are present (non-empty). Useful for
        UI validation to show which fields still need configuration.

        Args:
            db: Optional database connector

        Returns:
            Dict[str, bool]: True for fields that have non-empty values
        """
        row = self.get(db)
        return {f: bool(row.get(f)) for f in self.FIELDS}

    def is_complete(self, db: DatabaseConnector = None) -> bool:
        """
        Check if all required credential fields are present.

        broker_type has a default so only the three credential fields are required.

        Args:
            db: Optional database connector

        Returns:
            bool: True if client_id, secret_key, and redirect_uri are all non-empty
        """
        v = self.validate(db)
        # broker_type has a default so only the three credential fields are required
        return all(v.get(f, False) for f in ("client_id", "secret_key", "redirect_uri"))

    def clear(self, db: DatabaseConnector = None) -> bool:
        """
        Reset all credentials to empty/default values.

        Args:
            db: Optional database connector

        Returns:
            bool: True if clear successful, False otherwise
        """
        return self.save({"broker_type": "fyers", "client_id": "", "secret_key": "", "redirect_uri": ""}, db)


# Singleton instance for global use
brokerage = BrokerageCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 2. Daily Trade Setting  (replaces config/daily_trade_setting.json)
# ══════════════════════════════════════════════════════════════════════════════

class DailyTradeCRUD:
    """
    CRUD operations for daily trading parameters.

    Manages the daily_trade_setting table which contains configuration for:
        - Trading symbol and exchange
        - Contract expiry and lot size
        - Historical data intervals
        - Risk parameters (capital reserve, cancellation timeout)
        - Sideways zone trading flag
    """

    TABLE = "daily_trade_setting"
    DEFAULTS = {
        "exchange": "NSE",
        "week": 0,
        "derivative": "NIFTY50",
        "lot_size": 75,
        "call_lookback": 0,
        "put_lookback": 0,
        "history_interval": "2m",
        "max_num_of_option": 1800,
        "lower_percentage": 0.0,
        "cancel_after": 5,
        "capital_reserve": 0,
        "sideway_zone_trade": False,
    }

    def get(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """
        Get current daily trade settings.

        Args:
            db: Optional database connector

        Returns:
            Dict[str, Any]: Current settings merged with defaults if not found
        """
        db = db or get_db()
        row = db.fetchone(f"SELECT * FROM {self.TABLE} WHERE id = 1")
        d = _row_to_dict(row)
        if d:
            # Convert integer 0/1 to boolean for easier use in Python
            d["sideway_zone_trade"] = bool(d.get("sideway_zone_trade", 0))
        return d or dict(self.DEFAULTS)

    def save(self, data: Dict[str, Any], db: DatabaseConnector = None) -> bool:
        """
        Overwrite all fields (mirrors from_dict / save behaviour).

        Args:
            data: Dictionary containing all settings (missing keys use defaults)
            db: Optional database connector

        Returns:
            bool: True if save successful, False otherwise
        """
        db = db or get_db()
        merged = {**self.DEFAULTS, **data}
        try:
            db.execute(
                f"""UPDATE {self.TABLE} SET
                    exchange=?, week=?, derivative=?, lot_size=?,
                    call_lookback=?, put_lookback=?, history_interval=?,
                    max_num_of_option=?, lower_percentage=?, cancel_after=?,
                    capital_reserve=?, sideway_zone_trade=?, updated_at=?
                    WHERE id = 1""",
                (
                    merged["exchange"],
                    int(merged["week"]),
                    merged["derivative"],
                    int(merged["lot_size"]),
                    int(merged["call_lookback"]),
                    int(merged["put_lookback"]),
                    merged["history_interval"],
                    int(merged["max_num_of_option"]),
                    float(merged["lower_percentage"]),
                    int(merged["cancel_after"]),
                    int(merged["capital_reserve"]),
                    1 if merged["sideway_zone_trade"] else 0,  # Convert bool to int for SQLite
                    _NOW(),
                ),
            )
            return True
        except Exception as e:
            logger.error(f"[DailyTradeCRUD.save] {e}", exc_info=True)
            return False

    def update_field(self, field: str, value: Any, db: DatabaseConnector = None) -> bool:
        """
        Update a single field by name.

        Args:
            field: Name of the field to update
            value: New value for the field
            db: Optional database connector

        Returns:
            bool: True if update successful, False if field unknown or error
        """
        if field not in self.DEFAULTS:
            logger.warning(f"[DailyTradeCRUD.update_field] Unknown field: {field}")
            return False
        current = self.get(db)
        current[field] = value
        return self.save(current, db)

    def reset(self, db: DatabaseConnector = None) -> bool:
        """
        Reset all settings to default values.

        Args:
            db: Optional database connector

        Returns:
            bool: True if reset successful, False otherwise
        """
        return self.save(self.DEFAULTS, db)


# Singleton instance for global use
daily_trade = DailyTradeCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 3. Profit / Stoploss Setting  (replaces config/profit_stoploss_setting.json)
# ══════════════════════════════════════════════════════════════════════════════

class ProfitStoplossCRUD:
    """
    CRUD operations for profit and stoploss configuration.

    Manages the profit_stoploss_setting table which contains parameters for:
        - Take profit percentage and type
        - Stop loss percentage
        - Trailing stop parameters
        - Profit/loss step increments
    """

    TABLE = "profit_stoploss_setting"
    DEFAULTS = {
        "profit_type": "STOP",
        "tp_percentage": 15.0,
        "stoploss_percentage": 7.0,
        "trailing_first_profit": 3.0,
        "max_profit": 30.0,
        "profit_step": 2.0,
        "loss_step": 2.0,
    }

    def get(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """
        Get current profit/stoploss settings.

        Args:
            db: Optional database connector

        Returns:
            Dict[str, Any]: Current settings merged with defaults if not found
        """
        db = db or get_db()
        row = db.fetchone(f"SELECT * FROM {self.TABLE} WHERE id = 1")
        return _row_to_dict(row) or dict(self.DEFAULTS)

    def save(self, data: Dict[str, Any], db: DatabaseConnector = None) -> bool:
        """
        Overwrite all fields (mirrors from_dict / save behaviour).

        Args:
            data: Dictionary containing all settings
            db: Optional database connector

        Returns:
            bool: True if save successful, False otherwise
        """
        db = db or get_db()
        merged = {**self.DEFAULTS, **data}
        try:
            db.execute(
                f"""UPDATE {self.TABLE} SET
                    profit_type=?, tp_percentage=?, stoploss_percentage=?,
                    trailing_first_profit=?, max_profit=?, profit_step=?,
                    loss_step=?, updated_at=?
                    WHERE id = 1""",
                (
                    str(merged["profit_type"]),
                    float(merged["tp_percentage"]),
                    float(merged["stoploss_percentage"]),
                    float(merged["trailing_first_profit"]),
                    float(merged["max_profit"]),
                    float(merged["profit_step"]),
                    float(merged["loss_step"]),
                    _NOW(),
                ),
            )
            return True
        except Exception as e:
            logger.error(f"[ProfitStoplossCRUD.save] {e}", exc_info=True)
            return False

    def update_field(self, field: str, value: Any, db: DatabaseConnector = None) -> bool:
        """
        Update a single field by name.

        Args:
            field: Name of the field to update
            value: New value for the field
            db: Optional database connector

        Returns:
            bool: True if update successful, False otherwise
        """
        if field not in self.DEFAULTS:
            logger.warning(f"[ProfitStoplossCRUD.update_field] Unknown field: {field}")
            return False
        current = self.get(db)
        current[field] = value
        return self.save(current, db)

    def reset(self, db: DatabaseConnector = None) -> bool:
        """
        Reset all settings to default values.

        Args:
            db: Optional database connector

        Returns:
            bool: True if reset successful, False otherwise
        """
        return self.save(self.DEFAULTS, db)


# Singleton instance for global use
profit_stoploss = ProfitStoplossCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 4. Trading Mode Setting  (replaces config/trading_mode.json)
# ══════════════════════════════════════════════════════════════════════════════

class TradingModeCRUD:
    """
    CRUD operations for trading mode configuration.

    Manages the trading_mode_setting table which controls:
        - Trading mode (SIM/PAPER/LIVE)
        - Paper trading balance
        - Live trading confirmation settings
        - Simulation parameters (slippage, delay)
    """

    TABLE = "trading_mode_setting"
    VALID_MODES = {"SIM", "PAPER", "LIVE"}
    BOOL_FIELDS = {"allow_live_trading", "confirm_live_trades", "simulate_slippage", "simulate_delay"}
    DEFAULTS = {
        "mode": "SIM",
        "paper_balance": 100000.0,
        "allow_live_trading": False,
        "confirm_live_trades": True,
        "simulate_slippage": True,
        "slippage_percent": 0.05,
        "simulate_delay": True,
        "delay_ms": 500,
    }

    def get(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """
        Get current trading mode settings.

        Args:
            db: Optional database connector

        Returns:
            Dict[str, Any]: Current settings merged with defaults if not found,
                           with boolean fields properly converted.
        """
        db = db or get_db()
        row = db.fetchone(f"SELECT * FROM {self.TABLE} WHERE id = 1")
        d = _row_to_dict(row) or dict(self.DEFAULTS)
        # Convert integer 0/1 to boolean for easier use
        for bf in self.BOOL_FIELDS:
            if bf in d:
                d[bf] = bool(d[bf])
        return d

    def save(self, data: Dict[str, Any], db: DatabaseConnector = None) -> bool:
        """
        Overwrite all fields (mirrors from_dict / save behaviour).

        Args:
            data: Dictionary containing all settings
            db: Optional database connector

        Returns:
            bool: True if save successful, False otherwise
        """
        db = db or get_db()
        merged = {**self.DEFAULTS, **data}
        mode = str(merged.get("mode", "SIM")).upper()
        if mode not in self.VALID_MODES:
            logger.warning(f"[TradingModeCRUD.save] Invalid mode {mode!r}, defaulting to SIM")
            mode = "SIM"
        try:
            db.execute(
                f"""UPDATE {self.TABLE} SET
                    mode=?, paper_balance=?, allow_live_trading=?,
                    confirm_live_trades=?, simulate_slippage=?,
                    slippage_percent=?, simulate_delay=?, delay_ms=?,
                    updated_at=?
                    WHERE id = 1""",
                (
                    mode,
                    float(merged["paper_balance"]),
                    1 if merged["allow_live_trading"] else 0,  # Convert bool to int
                    1 if merged["confirm_live_trades"] else 0,
                    1 if merged["simulate_slippage"] else 0,
                    float(merged["slippage_percent"]),
                    1 if merged["simulate_delay"] else 0,
                    int(merged["delay_ms"]),
                    _NOW(),
                ),
            )
            return True
        except Exception as e:
            logger.error(f"[TradingModeCRUD.save] {e}", exc_info=True)
            return False

    def set_mode(self, mode: str, db: DatabaseConnector = None) -> bool:
        """
        Convenience method to change only the trading mode.

        Args:
            mode: New trading mode (SIM/PAPER/LIVE)
            db: Optional database connector

        Returns:
            bool: True if mode change successful, False otherwise
        """
        current = self.get(db)
        current["mode"] = mode
        return self.save(current, db)

    def update_field(self, field: str, value: Any, db: DatabaseConnector = None) -> bool:
        """
        Update a single field by name.

        Args:
            field: Name of the field to update
            value: New value for the field
            db: Optional database connector

        Returns:
            bool: True if update successful, False otherwise
        """
        if field not in self.DEFAULTS:
            logger.warning(f"[TradingModeCRUD.update_field] Unknown field: {field}")
            return False
        current = self.get(db)
        current[field] = value
        return self.save(current, db)

    def reset(self, db: DatabaseConnector = None) -> bool:
        """
        Reset all settings to default values.

        Args:
            db: Optional database connector

        Returns:
            bool: True if reset successful, False otherwise
        """
        return self.save(self.DEFAULTS, db)


# Singleton instance for global use
trading_mode = TradingModeCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 5. Strategies  (replaces config/strategies/<slug>.json + _active.json)
# ══════════════════════════════════════════════════════════════════════════════

class StrategiesCRUD:
    """
    CRUD operations for trading strategies.

    Manages the strategies table which stores:
        - Strategy metadata (name, description)
        - Indicator parameters (JSON blob)
        - Signal engine configuration (JSON blob)
        - Active strategy pointer

    This class replaces the file-based strategy storage where each strategy
    was stored as a separate JSON file.
    """

    def list_all(self, db: DatabaseConnector = None) -> List[Dict[str, Any]]:
        """
        Return all strategy metadata rows (excluding blob fields).

        Args:
            db: Optional database connector

        Returns:
            List[Dict[str, Any]]: List of strategy metadata dictionaries
        """
        db = db or get_db()
        rows = db.fetchall(
            "SELECT slug, name, description, created_at, updated_at FROM strategies ORDER BY name"
        )
        return [_row_to_dict(r) for r in rows]

    def get(self, slug: str, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        """
        Return a full strategy dict (indicators + engine decoded from JSON).

        Args:
            slug: Strategy unique identifier
            db: Optional database connector

        Returns:
            Optional[Dict[str, Any]]: Full strategy data including indicators and engine,
                                     or None if strategy not found.
        """
        db = db or get_db()
        row = db.fetchone("SELECT * FROM strategies WHERE slug = ?", (slug,))
        if row is None:
            return None
        d = _row_to_dict(row)
        # Decode JSON blobs
        try:
            d["indicators"] = json.loads(d.get("indicators") or "{}")
        except json.JSONDecodeError:
            d["indicators"] = {}
        try:
            d["engine"] = json.loads(d.get("engine") or "{}")
        except json.JSONDecodeError:
            d["engine"] = {}
        return d

    def create(
            self,
            slug: str,
            name: str,
            description: str = "",
            indicators: Dict = None,
            engine: Dict = None,
            db: DatabaseConnector = None,
    ) -> bool:
        """
        Insert a new strategy. Returns False if slug already exists.

        Args:
            slug: Unique strategy identifier
            name: Display name for the strategy
            description: Optional description
            indicators: Dictionary of indicator parameters
            engine: Dictionary of signal engine configuration
            db: Optional database connector

        Returns:
            bool: True if creation successful, False if slug exists or error
        """
        db = db or get_db()
        if self.exists(slug, db):
            logger.warning(f"[StrategiesCRUD.create] slug already exists: {slug}")
            return False
        now = _NOW()
        try:
            db.execute(
                """INSERT INTO strategies
                   (slug, name, description, indicators, engine, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    slug, name, description,
                    json.dumps(indicators or {}),
                    json.dumps(engine or {}),
                    now, now,
                ),
            )
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.create] {e}", exc_info=True)
            return False

    def upsert(
            self,
            slug: str,
            name: str,
            description: str = "",
            indicators: Dict = None,
            engine: Dict = None,
            db: DatabaseConnector = None,
    ) -> bool:
        """
        Create or fully overwrite a strategy (mirrors StrategyManager.save).

        This method uses SQLite's ON CONFLICT clause to either insert a new
        strategy or replace an existing one with the same slug.

        Args:
            slug: Unique strategy identifier
            name: Display name for the strategy
            description: Optional description
            indicators: Dictionary of indicator parameters
            engine: Dictionary of signal engine configuration
            db: Optional database connector

        Returns:
            bool: True if upsert successful, False otherwise
        """
        db = db or get_db()
        now = _NOW()
        try:
            db.execute(
                """INSERT INTO strategies
                       (slug, name, description, indicators, engine, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(slug) DO UPDATE SET
                       name=excluded.name,
                       description=excluded.description,
                       indicators=excluded.indicators,
                       engine=excluded.engine,
                       updated_at=excluded.updated_at""",
                (
                    slug, name, description,
                    json.dumps(indicators or {}),
                    json.dumps(engine or {}),
                    now, now,
                ),
            )
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.upsert] {e}", exc_info=True)
            return False

    def update_indicators(self, slug: str, indicators: Dict, db: DatabaseConnector = None) -> bool:
        """
        Update only the indicator parameters of a strategy.

        Args:
            slug: Strategy identifier
            indicators: New indicator parameters
            db: Optional database connector

        Returns:
            bool: True if update successful, False otherwise
        """
        db = db or get_db()
        try:
            db.execute(
                "UPDATE strategies SET indicators=?, updated_at=? WHERE slug=?",
                (json.dumps(indicators), _NOW(), slug),
            )
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.update_indicators] {e}", exc_info=True)
            return False

    def update_engine(self, slug: str, engine: Dict, db: DatabaseConnector = None) -> bool:
        """
        Update only the signal engine configuration of a strategy.

        Args:
            slug: Strategy identifier
            engine: New engine configuration
            db: Optional database connector

        Returns:
            bool: True if update successful, False otherwise
        """
        db = db or get_db()
        try:
            db.execute(
                "UPDATE strategies SET engine=?, updated_at=? WHERE slug=?",
                (json.dumps(engine), _NOW(), slug),
            )
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.update_engine] {e}", exc_info=True)
            return False

    def rename(self, slug: str, new_name: str, db: DatabaseConnector = None) -> bool:
        """
        Change the display name of a strategy.

        Args:
            slug: Strategy identifier
            new_name: New display name
            db: Optional database connector

        Returns:
            bool: True if rename successful, False otherwise
        """
        db = db or get_db()
        try:
            db.execute(
                "UPDATE strategies SET name=?, updated_at=? WHERE slug=?",
                (new_name, _NOW(), slug),
            )
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.rename] {e}", exc_info=True)
            return False

    def delete(self, slug: str, db: DatabaseConnector = None) -> bool:
        """
        Delete a strategy by slug.

        If the deleted strategy is currently active, the active pointer
        is cleared.

        Args:
            slug: Strategy identifier to delete
            db: Optional database connector

        Returns:
            bool: True if deletion successful, False otherwise
        """
        db = db or get_db()
        try:
            # Clear active pointer if needed
            active = self.get_active_slug(db)
            if active == slug:
                self.set_active(None, db)
            db.execute("DELETE FROM strategies WHERE slug=?", (slug,))
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.delete] {e}", exc_info=True)
            return False

    def exists(self, slug: str, db: DatabaseConnector = None) -> bool:
        """
        Check if a strategy with the given slug exists.

        Args:
            slug: Strategy identifier to check
            db: Optional database connector

        Returns:
            bool: True if strategy exists, False otherwise
        """
        db = db or get_db()
        row = db.fetchone("SELECT 1 FROM strategies WHERE slug=?", (slug,))
        return row is not None

    # ── Active pointer ─────────────────────────────────────────────────

    def get_active_slug(self, db: DatabaseConnector = None) -> Optional[str]:
        """
        Get the slug of the currently active strategy.

        Args:
            db: Optional database connector

        Returns:
            Optional[str]: Active strategy slug, or None if none active
        """
        db = db or get_db()
        row = db.fetchone("SELECT active_slug FROM strategy_active WHERE id=1")
        return row["active_slug"] if row else None

    def get_active(self, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        """
        Get the full data of the currently active strategy.

        Args:
            db: Optional database connector

        Returns:
            Optional[Dict[str, Any]]: Full strategy data, or None if none active
        """
        slug = self.get_active_slug(db)
        if not slug:
            return None
        return self.get(slug, db)

    def set_active(self, slug: Optional[str], db: DatabaseConnector = None) -> bool:
        """
        Set the active strategy.

        Args:
            slug: Strategy slug to activate, or None to deactivate
            db: Optional database connector

        Returns:
            bool: True if activation successful, False if slug not found
        """
        db = db or get_db()
        if slug is not None and not self.exists(slug, db):
            logger.warning(f"[StrategiesCRUD.set_active] slug not found: {slug}")
            return False
        try:
            db.execute(
                "UPDATE strategy_active SET active_slug=?, updated_at=? WHERE id=1",
                (slug, _NOW()),
            )
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.set_active] {e}", exc_info=True)
            return False


# Singleton instance for global use
strategies = StrategiesCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 6. Broker Tokens  (replaces config/access_token file)
# ══════════════════════════════════════════════════════════════════════════════

class TokenCRUD:
    """
    CRUD operations for broker authentication tokens.

    Manages the broker_tokens table which stores OAuth access tokens and
    refresh tokens for broker authentication. This replaces the old
    file-based token storage.
    """

    TABLE = "broker_tokens"

    def get(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """
        Get the current token data.

        Args:
            db: Optional database connector

        Returns:
            Dict[str, Any]: Token data including access_token, refresh_token,
                           issued_at, expires_at
        """
        db = db or get_db()
        row = db.fetchone(f"SELECT * FROM {self.TABLE} WHERE id=1")
        return _row_to_dict(row)

    def get_access_token(self, db: DatabaseConnector = None) -> str:
        """
        Convenience method to get just the access token.

        Args:
            db: Optional database connector

        Returns:
            str: Access token, or empty string if not found
        """
        return self.get(db).get("access_token", "")

    def save_token(
            self,
            access_token: str,
            refresh_token: str,
            issued_at: str = None,
            expires_at: str = None,
            db: DatabaseConnector = None,
    ) -> bool:
        """
        Save token data to database.

        Args:
            access_token: OAuth access token
            refresh_token: OAuth refresh token (if applicable)
            issued_at: ISO timestamp when token was issued
            expires_at: ISO timestamp when token expires
            db: Optional database connector

        Returns:
            bool: True if save successful, False otherwise
        """
        db = db or get_db()
        now = _NOW()
        try:
            db.execute(
                f"""UPDATE {self.TABLE}
                    SET access_token=?, refresh_token=?, issued_at=?, expires_at=?, updated_at=?
                    WHERE id=1""",
                (access_token, refresh_token, issued_at or now, expires_at, now),
            )
            return True
        except Exception as e:
            logger.error(f"[TokenCRUD.save_token] {e}", exc_info=True)
            return False

    def clear(self, db: DatabaseConnector = None) -> bool:
        """
        Clear all token data.

        Args:
            db: Optional database connector

        Returns:
            bool: True if clear successful, False otherwise
        """
        return self.save_token("", refresh_token="", db=db)


# Singleton instance for global use
tokens = TokenCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 7. Trade Sessions
# ══════════════════════════════════════════════════════════════════════════════

class SessionCRUD:
    """
    CRUD operations for trading sessions.

    Manages the trade_sessions table which tracks individual trading sessions:
        - Session start/end times
        - Trading parameters used
        - Performance summary (PnL, trade counts)
        - Notes and metadata

    A session typically corresponds to a continuous trading period,
    such as a day's trading activity.
    """

    TABLE = "trade_sessions"

    def create(
            self,
            mode: str,
            exchange: str = None,
            derivative: str = None,
            lot_size: int = None,
            interval: str = None,
            strategy_slug: str = None,
            db: DatabaseConnector = None,
    ) -> int:
        """
        Insert a new session and return its id.

        Args:
            mode: Trading mode (SIM/PAPER/LIVE)
            exchange: Exchange being traded
            derivative: Underlying instrument
            lot_size: Contract lot size
            interval: Timeframe interval
            strategy_slug: Active strategy identifier
            db: Optional database connector

        Returns:
            int: New session ID, or -1 on error
        """
        db = db or get_db()
        try:
            cur = db.execute(
                f"""INSERT INTO {self.TABLE}
                    (mode, exchange, derivative, lot_size, interval, strategy_slug, started_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (mode, exchange, derivative, lot_size, interval, strategy_slug, _NOW()),
            )
            return cur.lastrowid
        except Exception as e:
            logger.error(f"[SessionCRUD.create] {e}", exc_info=True)
            return -1

    def close(
            self,
            session_id: int,
            total_pnl: float = None,
            total_trades: int = None,
            winning_trades: int = None,
            losing_trades: int = None,
            notes: str = None,
            db: DatabaseConnector = None,
    ) -> bool:
        """
        Close a session and record final statistics.

        Args:
            session_id: ID of session to close
            total_pnl: Final profit/loss amount
            total_trades: Total number of trades
            winning_trades: Number of profitable trades
            losing_trades: Number of losing trades
            notes: Optional closing notes
            db: Optional database connector

        Returns:
            bool: True if close successful, False otherwise
        """
        db = db or get_db()
        try:
            db.execute(
                f"""UPDATE {self.TABLE} SET
                    ended_at=?, total_pnl=?, total_trades=?,
                    winning_trades=?, losing_trades=?, notes=?
                    WHERE id=?""",
                (
                    _NOW(), total_pnl, total_trades,
                    winning_trades, losing_trades, notes,
                    session_id,
                ),
            )
            return True
        except Exception as e:
            logger.error(f"[SessionCRUD.close] {e}", exc_info=True)
            return False

    def get(self, session_id: int, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        """
        Get session details by ID.

        Args:
            session_id: Session ID to retrieve
            db: Optional database connector

        Returns:
            Optional[Dict[str, Any]]: Session data, or None if not found
        """
        db = db or get_db()
        row = db.fetchone(f"SELECT * FROM {self.TABLE} WHERE id=?", (session_id,))
        return _row_to_dict(row)

    def list_recent(self, limit: int = 50, db: DatabaseConnector = None) -> List[Dict[str, Any]]:
        """
        List most recent sessions.

        Args:
            limit: Maximum number of sessions to return
            db: Optional database connector

        Returns:
            List[Dict[str, Any]]: List of session dictionaries, newest first
        """
        db = db or get_db()
        rows = db.fetchall(
            f"SELECT * FROM {self.TABLE} ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        return [_row_to_dict(r) for r in rows]

    def delete(self, session_id: int, db: DatabaseConnector = None) -> bool:
        """
        Delete a session by ID.

        Args:
            session_id: Session ID to delete
            db: Optional database connector

        Returns:
            bool: True if deletion successful, False otherwise
        """
        db = db or get_db()
        try:
            db.execute(f"DELETE FROM {self.TABLE} WHERE id=?", (session_id,))
            return True
        except Exception as e:
            logger.error(f"[SessionCRUD.delete] {e}", exc_info=True)
            return False


# Singleton instance for global use
sessions = SessionCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 8. Orders
# ══════════════════════════════════════════════════════════════════════════════

class OrderCRUD:
    """
    CRUD operations for individual orders.

    Manages the orders table which tracks every order placed:
        - Order lifecycle (PENDING → OPEN → CLOSED/CANCELLED)
        - Entry and exit prices
        - Stop loss and take profit levels
        - Broker order IDs for reconciliation
        - P&L calculation
        - Exit reasons

    This table provides comprehensive audit trail and performance analysis.
    """

    TABLE = "orders"

    def create(
            self,
            session_id: int,
            symbol: str,
            position_type: str,
            quantity: int,
            broker_order_id: str = None,
            entry_price: float = None,
            stop_loss: float = None,
            take_profit: float = None,
            db: DatabaseConnector = None,
    ) -> int:
        """
        Create a new order record with PENDING status.

        Args:
            session_id: Parent session ID
            symbol: Trading symbol
            position_type: CALL or PUT
            quantity: Order quantity
            broker_order_id: External broker order ID (if known)
            entry_price: Entry price (for limit orders)
            stop_loss: Stop loss price
            take_profit: Take profit price
            db: Optional database connector

        Returns:
            int: New order ID, or -1 on error
        """
        db = db or get_db()
        try:
            cur = db.execute(
                f"""INSERT INTO {self.TABLE}
                    (session_id, broker_order_id, symbol, position_type,
                     quantity, entry_price, stop_loss, take_profit,
                     status, entered_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
                (
                    session_id, broker_order_id, symbol, position_type,
                    quantity, entry_price, stop_loss, take_profit,
                    _NOW(), _NOW(),
                ),
            )
            return cur.lastrowid
        except Exception as e:
            logger.error(f"[OrderCRUD.create] {e}", exc_info=True)
            return -1

    def confirm(self, order_id: int, broker_order_id: str = None, db: DatabaseConnector = None) -> bool:
        """
        Mark an order as confirmed (OPEN status).

        Called when broker confirms order execution.

        Args:
            order_id: Internal order ID
            broker_order_id: Broker's order ID (if not already set)
            db: Optional database connector

        Returns:
            bool: True if confirmation successful, False otherwise
        """
        db = db or get_db()
        try:
            db.execute(
                f"""UPDATE {self.TABLE}
                    SET is_confirmed=1, broker_order_id=COALESCE(?, broker_order_id),
                        status='OPEN'
                    WHERE id=?""",
                (broker_order_id, order_id),
            )
            return True
        except Exception as e:
            logger.error(f"[OrderCRUD.confirm] {e}", exc_info=True)
            return False

    def close_order(
            self,
            order_id: int,
            exit_price: float,
            pnl: float,
            reason: str = None,
            db: DatabaseConnector = None,
    ) -> bool:
        """
        Close an order (CLOSED status) with exit details.

        Args:
            order_id: Internal order ID
            exit_price: Exit price
            pnl: Profit/loss amount
            reason: Reason for exit (e.g., "Target hit", "Stop loss")
            db: Optional database connector

        Returns:
            bool: True if close successful, False otherwise
        """
        db = db or get_db()
        try:
            db.execute(
                f"""UPDATE {self.TABLE}
                    SET exit_price=?, pnl=?, reason_to_exit=?,
                        status='CLOSED', exited_at=?
                    WHERE id=?""",
                (exit_price, pnl, reason, _NOW(), order_id),
            )
            return True
        except Exception as e:
            logger.error(f"[OrderCRUD.close_order] {e}", exc_info=True)
            return False

    def cancel(self, order_id: int, reason: str = None, db: DatabaseConnector = None) -> bool:
        """
        Cancel an order (CANCELLED status).

        Args:
            order_id: Internal order ID
            reason: Reason for cancellation
            db: Optional database connector

        Returns:
            bool: True if cancellation successful, False otherwise
        """
        db = db or get_db()
        try:
            db.execute(
                f"""UPDATE {self.TABLE}
                    SET status='CANCELLED', reason_to_exit=?, exited_at=?
                    WHERE id=?""",
                (reason, _NOW(), order_id),
            )
            return True
        except Exception as e:
            logger.error(f"[OrderCRUD.cancel] {e}", exc_info=True)
            return False

    def get(self, order_id: int, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        """
        Get order details by ID.

        Args:
            order_id: Internal order ID
            db: Optional database connector

        Returns:
            Optional[Dict[str, Any]]: Order data, or None if not found
        """
        db = db or get_db()
        row = db.fetchone(f"SELECT * FROM {self.TABLE} WHERE id=?", (order_id,))
        return _row_to_dict(row)

    def list_for_session(
            self, session_id: int, db: DatabaseConnector = None
    ) -> List[Dict[str, Any]]:
        """
        List all orders for a specific session.

        Args:
            session_id: Session ID
            db: Optional database connector

        Returns:
            List[Dict[str, Any]]: Orders in chronological order
        """
        db = db or get_db()
        rows = db.fetchall(
            f"SELECT * FROM {self.TABLE} WHERE session_id=? ORDER BY created_at", (session_id,)
        )
        return [_row_to_dict(r) for r in rows]

    def list_open(self, session_id: int = None, db: DatabaseConnector = None) -> List[Dict[str, Any]]:
        """
        List all open orders, optionally filtered by session.

        Args:
            session_id: Optional session ID to filter by
            db: Optional database connector

        Returns:
            List[Dict[str, Any]]: List of open orders
        """
        db = db or get_db()
        if session_id is not None:
            rows = db.fetchall(
                f"SELECT * FROM {self.TABLE} WHERE session_id=? AND status='OPEN'", (session_id,)
            )
        else:
            rows = db.fetchall(f"SELECT * FROM {self.TABLE} WHERE status='OPEN'")
        return [_row_to_dict(r) for r in rows]

    # FEATURE 7: Add get_by_period method for trade history filtering
    def get_by_period(self, period: str = 'today', db: DatabaseConnector = None) -> List[Dict[str, Any]]:
        """
        Get closed orders filtered by period.

        Supports different time periods for trade history display:
            - 'today': Orders closed today
            - 'this_week': Orders closed in the last 7 days
            - 'all': All closed orders

        Args:
            period: 'today', 'this_week', or 'all'
            db: Optional database connector

        Returns:
            List[Dict[str, Any]]: List of order dictionaries, newest first
        """
        db = db or get_db()

        try:
            if period == 'today':
                # Today's closed orders
                rows = db.fetchall(
                    f"""SELECT * FROM {self.TABLE} 
                        WHERE status = 'CLOSED' 
                        AND DATE(exited_at) = DATE('now', 'localtime')
                        ORDER BY exited_at DESC"""
                )
            elif period == 'this_week':
                # Last 7 days
                rows = db.fetchall(
                    f"""SELECT * FROM {self.TABLE} 
                        WHERE status = 'CLOSED' 
                        AND exited_at >= DATE('now', 'localtime', '-7 days')
                        ORDER BY exited_at DESC"""
                )
            else:  # 'all' or any other value
                # All closed orders
                rows = db.fetchall(
                    f"""SELECT * FROM {self.TABLE} 
                        WHERE status = 'CLOSED' 
                        ORDER BY exited_at DESC"""
                )

            return [_row_to_dict(r) for r in rows]

        except Exception as e:
            logger.error(f"[OrderCRUD.get_by_period] Failed: {e}", exc_info=True)
            return []

    def update_stop_loss(self, order_id: int, stop_loss: float, db: DatabaseConnector = None) -> bool:
        """
        Update stop loss price for an order.

        Used for trailing stop loss updates.

        Args:
            order_id: Internal order ID
            stop_loss: New stop loss price
            db: Optional database connector

        Returns:
            bool: True if update successful, False otherwise
        """
        db = db or get_db()
        try:
            db.execute(
                f"UPDATE {self.TABLE} SET stop_loss=? WHERE id=?", (stop_loss, order_id)
            )
            return True
        except Exception as e:
            logger.error(f"[OrderCRUD.update_stop_loss] {e}", exc_info=True)
            return False


# Singleton instance for global use
orders = OrderCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 9. Generic Key-Value Store  (replaces Config / strategy_setting.json)
# ══════════════════════════════════════════════════════════════════════════════

class KVCRUD:
    """
    Generic key-value store for miscellaneous configuration.

    This class provides a flexible storage mechanism for any configuration
    that doesn't fit into the structured tables. It's used for:
        - Application configuration (via config_crud)
        - Strategy-specific settings
        - Runtime state that needs persistence
        - Any other key-value data

    Values are automatically JSON serialized/deserialized, allowing storage
    of complex data types.
    """

    TABLE = "app_kv"

    def get(self, key: str, default: Any = None, db: DatabaseConnector = None) -> Any:
        """
        Get value by key, with optional default.

        Args:
            key: Configuration key
            default: Default value if key not found
            db: Optional database connector

        Returns:
            Any: Deserialized value, or default if not found
        """
        db = db or get_db()
        row = db.fetchone(f"SELECT value FROM {self.TABLE} WHERE key=?", (key,))
        if row is None:
            return default
        raw = row["value"]
        # Try JSON decode; fall back to raw string
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    def set(self, key: str, value: Any, db: DatabaseConnector = None) -> bool:
        """
        Set value by key (upsert semantics).

        Args:
            key: Configuration key
            value: Value to store (will be JSON serialized)
            db: Optional database connector

        Returns:
            bool: True if set successful, False otherwise
        """
        db = db or get_db()
        try:
            serialised = json.dumps(value) if not isinstance(value, str) else value
            db.execute(
                f"""INSERT INTO {self.TABLE} (key, value, updated_at) VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, serialised, _NOW()),
            )
            return True
        except Exception as e:
            logger.error(f"[KVCRUD.set] key={key!r}: {e}", exc_info=True)
            return False

    def delete(self, key: str, db: DatabaseConnector = None) -> bool:
        """
        Delete a key from the store.

        Args:
            key: Key to delete
            db: Optional database connector

        Returns:
            bool: True if deletion successful, False otherwise
        """
        db = db or get_db()
        try:
            db.execute(f"DELETE FROM {self.TABLE} WHERE key=?", (key,))
            return True
        except Exception as e:
            logger.error(f"[KVCRUD.delete] key={key!r}: {e}", exc_info=True)
            return False

    def all(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        """
        Return all key-value pairs as a dictionary.

        Returns:
            Dict[str, Any]: All stored keys with their deserialized values
        """
        db = db or get_db()
        rows = db.fetchall(f"SELECT key, value FROM {self.TABLE}")
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                result[r["key"]] = r["value"]
        return result

    def update_many(self, data: Dict[str, Any], db: DatabaseConnector = None) -> bool:
        """
        Batch set multiple keys in a single transaction.

        This method ensures all-or-nothing semantics - either all updates
        succeed or none are applied.

        Args:
            data: Dictionary of key-value pairs to set
            db: Optional database connector

        Returns:
            bool: True if all updates successful, False otherwise
        """
        db = db or get_db()
        now = _NOW()
        try:
            with db.connection() as conn:
                for key, value in data.items():
                    serialised = json.dumps(value) if not isinstance(value, str) else value
                    conn.execute(
                        f"""INSERT INTO {self.TABLE} (key, value, updated_at) VALUES (?, ?, ?)
                            ON CONFLICT(key) DO UPDATE SET
                                value=excluded.value, updated_at=excluded.updated_at""",
                        (key, serialised, now),
                    )
            return True
        except Exception as e:
            logger.error(f"[KVCRUD.update_many] {e}", exc_info=True)
            return False

    def clear(self, db: DatabaseConnector = None) -> bool:
        """
        Delete all keys from the store.

        Args:
            db: Optional database connector

        Returns:
            bool: True if clear successful, False otherwise
        """
        db = db or get_db()
        try:
            db.execute(f"DELETE FROM {self.TABLE}")
            return True
        except Exception as e:
            logger.error(f"[KVCRUD.clear] {e}", exc_info=True)
            return False


# Singleton instance for global use
kv = KVCRUD()
