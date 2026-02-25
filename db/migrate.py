"""
db/migrate.py
-------------
One-shot migration from JSON config files → SQLite.

Run once:
    python -m db.migrate

Or call from code:
    from db.migrate import migrate_all
    migrate_all()

The script is idempotent — re-running it will overwrite the DB rows
with whatever is currently in the JSON files, but will NOT duplicate
strategy rows (it uses upsert).

JSON files read:
    config/brokerage_setting.json
    config/daily_trade_setting.json
    config/profit_stoploss_setting.json
    config/trading_mode.json
    config/strategy_setting.json   (generic KV)
    config/strategies/*.json       (strategy files, skips _active.json)
    config/strategies/_active.json (active pointer)
    config/access_token            (raw token string)
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
    """Load JSON from path. Returns {} on any error."""
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
    """Load raw text from path. Returns '' on error."""
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
    path = Path(CONFIG_PATH) / "brokerage_setting.json"
    data = _load_json(path)
    if not data:
        logger.info("  brokerage_setting: no JSON found, keeping defaults")
        return True
    ok = crud.brokerage.save(data, db)
    logger.info(f"  brokerage_setting: {'OK' if ok else 'FAILED'}")
    return ok


def migrate_daily_trade(db=None) -> bool:
    path = Path(CONFIG_PATH) / "daily_trade_setting.json"
    data = _load_json(path)
    if not data:
        logger.info("  daily_trade_setting: no JSON found, keeping defaults")
        return True
    ok = crud.daily_trade.save(data, db)
    logger.info(f"  daily_trade_setting: {'OK' if ok else 'FAILED'}")
    return ok


def migrate_profit_stoploss(db=None) -> bool:
    path = Path(CONFIG_PATH) / "profit_stoploss_setting.json"
    data = _load_json(path)
    if not data:
        logger.info("  profit_stoploss_setting: no JSON found, keeping defaults")
        return True
    ok = crud.profit_stoploss.save(data, db)
    logger.info(f"  profit_stoploss_setting: {'OK' if ok else 'FAILED'}")
    return ok


def migrate_trading_mode(db=None) -> bool:
    path = Path(CONFIG_PATH) / "trading_mode.json"
    data = _load_json(path)
    if not data:
        logger.info("  trading_mode_setting: no JSON found, keeping defaults")
        return True
    ok = crud.trading_mode.save(data, db)
    logger.info(f"  trading_mode_setting: {'OK' if ok else 'FAILED'}")
    return ok


def migrate_strategy_config(db=None) -> bool:
    """Migrate strategy_setting.json → app_kv table."""
    path = Path(CONFIG_PATH) / "strategy_setting.json"
    data = _load_json(path)
    if not data:
        logger.info("  app_kv (strategy_setting): no JSON found, skipping")
        return True
    ok = crud.kv.update_many(data, db)
    logger.info(f"  app_kv (strategy_setting): {'OK' if ok else 'FAILED'}")
    return ok


def migrate_strategies(db=None) -> bool:
    """Migrate all per-slug JSON files in config/strategies/."""
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
    """Migrate raw access_token file → broker_tokens table."""
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
# ---------------------------------------------------------------------------

def migrate_risk_settings(db=None) -> bool:
    """Migrate risk settings from app_kv or create defaults."""
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
    """Migrate signal settings from app_kv or create defaults."""
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
    """Migrate telegram settings from app_kv or create defaults."""
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
    """Migrate MTF settings from app_kv or create defaults."""
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
    Run all migrations in order. Returns True if all succeeded.

    Args:
        db:            Pass a specific DatabaseConnector (useful for tests).
        stop_on_error: If True, raise on first failure instead of continuing.
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
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    success = migrate_all()
    sys.exit(0 if success else 1)