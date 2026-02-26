"""
Database Migration Module
=========================
One-shot migration tool for moving from JSON configuration files to SQLite database.

This module provides a comprehensive migration system that reads all existing
JSON configuration files and migrates their data into the new SQLite database
schema. It is designed to be run once during the transition from file-based
to database-backed configuration.

Purpose:
    To seamlessly migrate all existing configuration data from the old
    JSON file system to the new SQLite database without data loss.

Design Philosophy:
    - **Idempotent**: Safe to run multiple times - uses upsert operations
    - **Non-destructive**: Original JSON files are never modified or deleted
    - **Comprehensive**: Migrates all configuration types in one pass
    - **Graceful**: Handles missing files gracefully, continues on errors
    - **Auditable**: Detailed logging of all migration steps

What gets migrated:
    ┌─────────────────────────┬─────────────────────────┬─────────────────┐
    │ JSON Source             │ Target Table            │ CRUD Module     │
    ├─────────────────────────┼─────────────────────────┼─────────────────┤
    │ brokerage_setting.json  │ brokerage_setting       │ brokerage       │
    │ daily_trade_setting.json│ daily_trade_setting     │ daily_trade     │
    │ profit_stoploss_setting.│ profit_stoploss_setting │ profit_stoploss │
    │ trading_mode.json       │ trading_mode_setting    │ trading_mode    │
    │ strategy_setting.json   │ app_kv                  │ kv              │
    │ strategies/*.json       │ strategies              │ strategies      │
    │ _active.json            │ strategy_active         │ strategies      │
    │ fyers_token.json        │ broker_tokens           │ tokens          │
    │ app_kv entries          │ risk_settings           │ (direct SQL)    │
    │ app_kv entries          │ signal_settings         │ (direct SQL)    │
    │ app_kv entries          │ telegram_settings       │ (direct SQL)    │
    │ app_kv entries          │ mtf_settings            │ (direct SQL)    │
    └─────────────────────────┴─────────────────────────┴─────────────────┘

Usage:
    # Command line
    python -m db.migrate

    # From code
    from db.migrate import migrate_all
    success = migrate_all()
    if success:
        print("Migration completed successfully")

Features:
    - Reads all JSON files from config/ and config/strategies/
    - Uses CRUD modules for structured tables
    - Uses direct SQL for feature-specific tables
    - Handles missing files gracefully
    - Detailed logging of each step
    - Option to stop on first error (for testing)

Dependencies:
    - BaseEnums: For CONFIG_PATH constant
    - db.connector: Database connection
    - db.crud: CRUD operations for all tables

Version: 2.0.0
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

from BaseEnums import CONFIG_PATH
from db.connector import get_db
from db import crud

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Dict[str, Any]:
    """
    Load JSON from path with error handling.

    Safely loads a JSON file, returning an empty dictionary on any error
    rather than raising exceptions.

    Args:
        path: Path object pointing to the JSON file

    Returns:
        Dict[str, Any]: Parsed JSON data as dictionary, or empty dict on error

    Note:
        Logs success at INFO level, warnings for non-dict JSON, errors for
        file access issues.
    """
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                logger.info(f"  Loaded: {path}")
                return data
            logger.warning(f"  {path} is not a JSON object — skipping")
    except Exception as e:
        logger.error(f"  Failed to load {path}: {e}")
    return {}


def _load_text(path: Path) -> str:
    """
    Load raw text from path with error handling.

    Args:
        path: Path object pointing to the text file

    Returns:
        str: File contents as string, or empty string on error

    Note:
        Used for loading raw token files that aren't JSON.
    """
    try:
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            logger.info(f"  Loaded: {path}")
            return text
    except Exception as e:
        logger.error(f"  Failed to read {path}: {e}")
    return ""


# ---------------------------------------------------------------------------
# Per-table migration functions
# ---------------------------------------------------------------------------

def migrate_brokerage(db=None) -> bool:
    """
    Migrate brokerage_setting.json to brokerage_setting table.

    Reads the JSON file and uses brokerage CRUD to save the data.

    Args:
        db: Optional database connector

    Returns:
        bool: True if migration successful (or file missing), False on error
    """
    path = Path(CONFIG_PATH) / "brokerage_setting.json"
    data = _load_json(path)
    if not data:
        logger.info("  brokerage_setting: no JSON found, keeping defaults")
        return True
    ok = crud.brokerage.save(data, db)
    logger.info(f"  brokerage_setting: {'OK' if ok else 'FAILED'}")
    return ok


def migrate_daily_trade(db=None) -> bool:
    """
    Migrate daily_trade_setting.json to daily_trade_setting table.

    Args:
        db: Optional database connector

    Returns:
        bool: True if migration successful (or file missing), False on error
    """
    path = Path(CONFIG_PATH) / "daily_trade_setting.json"
    data = _load_json(path)
    if not data:
        logger.info("  daily_trade_setting: no JSON found, keeping defaults")
        return True
    ok = crud.daily_trade.save(data, db)
    logger.info(f"  daily_trade_setting: {'OK' if ok else 'FAILED'}")
    return ok


def migrate_profit_stoploss(db=None) -> bool:
    """
    Migrate profit_stoploss_setting.json to profit_stoploss_setting table.

    Args:
        db: Optional database connector

    Returns:
        bool: True if migration successful (or file missing), False on error
    """
    path = Path(CONFIG_PATH) / "profit_stoploss_setting.json"
    data = _load_json(path)
    if not data:
        logger.info("  profit_stoploss_setting: no JSON found, keeping defaults")
        return True
    ok = crud.profit_stoploss.save(data, db)
    logger.info(f"  profit_stoploss_setting: {'OK' if ok else 'FAILED'}")
    return ok


def migrate_trading_mode(db=None) -> bool:
    """
    Migrate trading_mode.json to trading_mode_setting table.

    Args:
        db: Optional database connector

    Returns:
        bool: True if migration successful (or file missing), False on error
    """
    path = Path(CONFIG_PATH) / "trading_mode.json"
    data = _load_json(path)
    if not data:
        logger.info("  trading_mode_setting: no JSON found, keeping defaults")
        return True
    ok = crud.trading_mode.save(data, db)
    logger.info(f"  trading_mode_setting: {'OK' if ok else 'FAILED'}")
    return ok


def migrate_strategy_config(db=None) -> bool:
    """
    Migrate strategy_setting.json to app_kv table.

    This file contains generic key-value configuration for strategies.

    Args:
        db: Optional database connector

    Returns:
        bool: True if migration successful (or file missing), False on error
    """
    path = Path(CONFIG_PATH) / "strategy_setting.json"
    data = _load_json(path)
    if not data:
        logger.info("  app_kv (strategy_setting): no JSON found, skipping")
        return True
    ok = crud.kv.update_many(data, db)
    logger.info(f"  app_kv (strategy_setting): {'OK' if ok else 'FAILED'}")
    return ok


def migrate_strategies(db=None) -> bool:
    """
    Migrate all per-slug JSON files in config/strategies/ to strategies table.

    This function:
        1. Reads all .json files in the strategies directory (except _active.json)
        2. Extracts metadata, indicators, and engine configuration
        3. Uses upsert to create/update strategy records
        4. Reads _active.json to set the active strategy pointer

    Args:
        db: Optional database connector

    Returns:
        bool: True if all strategies migrated successfully, False if any failed
    """
    strategies_dir = Path(CONFIG_PATH) / "strategies"
    if not strategies_dir.is_dir():
        logger.info("  strategies: directory not found, skipping")
        return True

    success = True
    migrated = 0

    for json_path in sorted(strategies_dir.glob("*.json")):
        if json_path.name.startswith("_"):
            continue  # skip _active.json here
        data = _load_json(json_path)
        if not data:
            continue

        meta = data.get("meta", {})
        slug = meta.get("slug") or json_path.stem
        name = meta.get("name") or slug
        description = meta.get("description", "")
        indicators = data.get("indicators", {})
        engine = data.get("engine", {})

        ok = crud.strategies.upsert(
            slug=slug,
            name=name,
            description=description,
            indicators=indicators,
            engine=engine,
            db=db,
        )
        if ok:
            migrated += 1
        else:
            success = False
            logger.error(f"  strategies: failed to migrate {slug}")

    # Migrate active pointer
    active_path = strategies_dir / "_active.json"
    active_data = _load_json(active_path)
    if active_data:
        active_slug = active_data.get("active_slug")
        if active_slug:
            crud.strategies.set_active(active_slug, db)
            logger.info(f"  strategies: active slug set to {active_slug!r}")

    logger.info(f"  strategies: migrated {migrated} strategy file(s)")
    return success


def migrate_token(db=None) -> bool:
    """
    Migrate raw access_token file to broker_tokens table.

    Looks for fyers_token.json and extracts access_token and refresh_token.

    Args:
        db: Optional database connector

    Returns:
        bool: True if migration successful (or file missing), False on error
    """
    # Try common locations
    path = Path(CONFIG_PATH) / "fyers_token.json"
    data = _load_json(path)
    if data:
        ok = crud.tokens.save_token(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            db=db
        )
        logger.info(f"  broker_tokens: {'OK' if ok else 'FAILED'} (from {data})")
        return ok
    logger.info("  broker_tokens: no token file found, skipping")
    return True


# ---------------------------------------------------------------------------
# NEW: Migration functions for feature-specific tables
# These tables were added after the initial migration and need data from app_kv
# ---------------------------------------------------------------------------

def migrate_risk_settings(db=None) -> bool:
    """
    Migrate risk settings from app_kv to dedicated risk_settings table.

    Reads the following keys from app_kv:
        - max_daily_loss (default: -5000.0)
        - max_trades_per_day (default: 10)
        - daily_target (default: 5000.0)

    Args:
        db: Optional database connector

    Returns:
        bool: True if migration successful, False on error
    """
    db = db or get_db()

    # Check if we have existing settings in app_kv
    max_daily_loss = crud.kv.get("max_daily_loss", -5000.0, db)
    max_trades_per_day = crud.kv.get("max_trades_per_day", 10, db)
    daily_target = crud.kv.get("daily_target", 5000.0, db)

    # Update risk_settings table
    try:
        db.execute("""
            UPDATE risk_settings 
            SET max_daily_loss = ?, max_trades_per_day = ?, daily_target = ?, updated_at = ?
            WHERE id = 1
        """, (max_daily_loss, max_trades_per_day, daily_target, crud._NOW()))
        logger.info("  risk_settings: migrated from app_kv")
        return True
    except Exception as e:
        logger.error(f"  risk_settings migration failed: {e}")
        return False


def migrate_signal_settings(db=None) -> bool:
    """
    Migrate signal settings from app_kv to dedicated signal_settings table.

    Reads the following keys from app_kv:
        - min_confidence (default: 0.6)

    Args:
        db: Optional database connector

    Returns:
        bool: True if migration successful, False on error
    """
    db = db or get_db()

    min_confidence = crud.kv.get("min_confidence", 0.6, db)

    try:
        db.execute("""
            UPDATE signal_settings 
            SET min_confidence = ?, updated_at = ?
            WHERE id = 1
        """, (min_confidence, crud._NOW()))
        logger.info("  signal_settings: migrated from app_kv")
        return True
    except Exception as e:
        logger.error(f"  signal_settings migration failed: {e}")
        return False


def migrate_telegram_settings(db=None) -> bool:
    """
    Migrate telegram settings from app_kv to dedicated telegram_settings table.

    Reads the following keys from app_kv:
        - telegram_bot_token (default: "")
        - telegram_chat_id (default: "")

    Also sets enabled flag if both token and chat_id are present.

    Args:
        db: Optional database connector

    Returns:
        bool: True if migration successful, False on error
    """
    db = db or get_db()

    bot_token = crud.kv.get("telegram_bot_token", "", db)
    chat_id = crud.kv.get("telegram_chat_id", "", db)
    enabled = 1 if bot_token and chat_id else 0

    try:
        db.execute("""
            UPDATE telegram_settings 
            SET bot_token = ?, chat_id = ?, enabled = ?, updated_at = ?
            WHERE id = 1
        """, (bot_token, chat_id, enabled, crud._NOW()))
        logger.info("  telegram_settings: migrated from app_kv")
        return True
    except Exception as e:
        logger.error(f"  telegram_settings migration failed: {e}")
        return False


def migrate_mtf_settings(db=None) -> bool:
    """
    Migrate Multi-Timeframe Filter settings from app_kv to mtf_settings table.

    Reads the following keys from app_kv:
        - use_mtf_filter (default: False)

    Args:
        db: Optional database connector

    Returns:
        bool: True if migration successful, False on error
    """
    db = db or get_db()

    enabled = 1 if crud.kv.get("use_mtf_filter", False, db) else 0

    try:
        db.execute("""
            UPDATE mtf_settings 
            SET enabled = ?, updated_at = ?
            WHERE id = 1
        """, (enabled, crud._NOW()))
        logger.info("  mtf_settings: migrated from app_kv")
        return True
    except Exception as e:
        logger.error(f"  mtf_settings migration failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Master migration runner
# ---------------------------------------------------------------------------

def migrate_all(db=None, stop_on_error: bool = False) -> bool:
    """
    Run all migrations in order.

    This is the main entry point for the migration process. It executes each
    migration step sequentially, logging progress and collecting results.

    Args:
        db: Optional database connector (useful for tests). If None, uses default.
        stop_on_error: If True, raises exception on first failure instead of continuing.
                      Useful for testing to ensure all migrations work.

    Returns:
        bool: True if all migrations succeeded, False if any failed

    Example:
        success = migrate_all()
        if not success:
            print("Some migrations failed - check logs for details")

    Note:
        Even if some migrations fail, the process continues to attempt all steps.
        This ensures maximum data migration even with partial failures.
    """
    db = db or get_db()
    logger.info("=" * 60)
    logger.info("Starting JSON → SQLite migration")
    logger.info("=" * 60)
    steps = [
        ("brokerage",        migrate_brokerage),
        ("daily_trade",      migrate_daily_trade),
        ("profit_stoploss",  migrate_profit_stoploss),
        ("trading_mode",     migrate_trading_mode),
        ("strategy_config",  migrate_strategy_config),
        ("strategies",       migrate_strategies),
        ("token",            migrate_token),
        ("risk_settings",    migrate_risk_settings),
        ("signal_settings",  migrate_signal_settings),
        ("telegram_settings", migrate_telegram_settings),
        ("mtf_settings",     migrate_mtf_settings),
    ]

    all_ok = True
    for name, fn in steps:
        logger.info(f"\n[{name}]")
        try:
            ok = fn(db)
            if not ok:
                all_ok = False
                if stop_on_error:
                    raise RuntimeError(f"Migration step '{name}' failed")
        except Exception as e:
            logger.error(f"[{name}] Exception: {e}", exc_info=True)
            all_ok = False
            if stop_on_error:
                raise

    logger.info("\n" + "=" * 60)
    logger.info(f"Migration {'COMPLETE ✓' if all_ok else 'FINISHED WITH ERRORS ✗'}")
    logger.info("=" * 60)
    return all_ok


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Command-line interface for running the migration.
    
    Usage:
        python -m db.migrate
    
    Exit codes:
        0: All migrations successful
        1: One or more migrations failed
    """
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    success = migrate_all()
    sys.exit(0 if success else 1)