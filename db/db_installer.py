"""
db/db_installer.py
------------------
Self-contained database installer for the Trading App.

The full SQLite schema is embedded directly in this file — no external
schema.sql is required.  This is the **single entry-point** that must be
called before any other database activity.  It is completely safe to call
on every app start; all operations are idempotent.

What it does on each startup
─────────────────────────────
1. Ensures the config/ directory (or wherever the DB lives) exists.
2. Opens (or creates) trading.db.
3. Applies the embedded schema — every statement uses IF NOT EXISTS,
   so existing tables and data are never touched or dropped.
4. Seeds default singleton rows for settings tables (INSERT OR IGNORE).
5. Runs a column-level health-check on every expected table.
6. Returns an InstallResult the caller can inspect or show in a dialog.

Usage (add to the very top of your main / GUI entry-point)
──────────────────────────────────────────────────────────
    from db.db_installer import run_startup_check

    result = run_startup_check()
    if not result.ok:
        print(result.summary())   # or show a QMessageBox
        sys.exit(1)

CLI
───
    python -m db.db_installer
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Database path — override via env var or pass explicitly to run_startup_check
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_DB_PATH: str = os.environ.get("TRADING_DB_PATH", "config/trading.db")


# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDED SCHEMA
# All CREATE TABLE / CREATE INDEX statements use IF NOT EXISTS so this block
# is always safe to execute against an existing database.
# ─────────────────────────────────────────────────────────────────────────────
SCHEMA_SQL: str = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- 1. Brokerage credentials (Fyers)
-- ============================================================
CREATE TABLE IF NOT EXISTS brokerage_setting (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    client_id    TEXT    NOT NULL DEFAULT '',
    secret_key   TEXT    NOT NULL DEFAULT '',
    redirect_uri TEXT    NOT NULL DEFAULT '',
    updated_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

-- ============================================================
-- 2. Daily trade settings
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_trade_setting (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    exchange           TEXT    NOT NULL DEFAULT 'NSE',
    week               INTEGER NOT NULL DEFAULT 0,
    derivative         TEXT    NOT NULL DEFAULT 'NIFTY50',
    lot_size           INTEGER NOT NULL DEFAULT 75,
    call_lookback      INTEGER NOT NULL DEFAULT 0,
    put_lookback       INTEGER NOT NULL DEFAULT 0,
    history_interval   TEXT    NOT NULL DEFAULT '2m',
    max_num_of_option  INTEGER NOT NULL DEFAULT 1800,
    lower_percentage   REAL    NOT NULL DEFAULT 0.0,
    cancel_after       INTEGER NOT NULL DEFAULT 5,
    capital_reserve    INTEGER NOT NULL DEFAULT 0,
    sideway_zone_trade INTEGER NOT NULL DEFAULT 0,
    updated_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

-- ============================================================
-- 3. Profit / Stoploss settings
-- ============================================================
CREATE TABLE IF NOT EXISTS profit_stoploss_setting (
    id                     INTEGER PRIMARY KEY CHECK (id = 1),
    profit_type            TEXT    NOT NULL DEFAULT 'STOP',
    tp_percentage          REAL    NOT NULL DEFAULT 15.0,
    stoploss_percentage    REAL    NOT NULL DEFAULT 7.0,
    trailing_first_profit  REAL    NOT NULL DEFAULT 3.0,
    max_profit             REAL    NOT NULL DEFAULT 30.0,
    profit_step            REAL    NOT NULL DEFAULT 2.0,
    loss_step              REAL    NOT NULL DEFAULT 2.0,
    updated_at             TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

-- ============================================================
-- 4. Trading mode settings
-- ============================================================
CREATE TABLE IF NOT EXISTS trading_mode_setting (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),
    mode                 TEXT    NOT NULL DEFAULT 'SIM'
                         CHECK (mode IN ('SIM', 'PAPER', 'LIVE')),
    paper_balance        REAL    NOT NULL DEFAULT 100000.0,
    allow_live_trading   INTEGER NOT NULL DEFAULT 0,
    confirm_live_trades  INTEGER NOT NULL DEFAULT 1,
    simulate_slippage    INTEGER NOT NULL DEFAULT 1,
    slippage_percent     REAL    NOT NULL DEFAULT 0.05,
    simulate_delay       INTEGER NOT NULL DEFAULT 1,
    delay_ms             INTEGER NOT NULL DEFAULT 500,
    updated_at           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

-- ============================================================
-- 5. Strategies  (replaces per-slug JSON files)
-- ============================================================
CREATE TABLE IF NOT EXISTS strategies (
    slug         TEXT    PRIMARY KEY,
    name         TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',
    indicators   TEXT    NOT NULL DEFAULT '{}',
    engine       TEXT    NOT NULL DEFAULT '{}',
    created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    updated_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

-- Active strategy pointer
CREATE TABLE IF NOT EXISTS strategy_active (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    active_slug  TEXT    REFERENCES strategies(slug) ON DELETE SET NULL,
    updated_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

-- ============================================================
-- 6. Broker auth tokens  (replaces config/access_token file)
-- ============================================================
CREATE TABLE IF NOT EXISTS broker_tokens (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    access_token    TEXT    NOT NULL DEFAULT '',
    refresh_token   TEXT,
    issued_at       TEXT,
    expires_at      TEXT,
    updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

-- ============================================================
-- 7. Trade sessions  (one row per trading session / day run)
-- ============================================================
CREATE TABLE IF NOT EXISTS trade_sessions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    ended_at       TEXT,
    mode           TEXT    NOT NULL DEFAULT 'SIM',
    exchange       TEXT,
    derivative     TEXT,
    lot_size       INTEGER,
    interval       TEXT,
    total_pnl      REAL,
    total_trades   INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades  INTEGER DEFAULT 0,
    strategy_slug  TEXT    REFERENCES strategies(slug) ON DELETE SET NULL,
    notes          TEXT
);

-- ============================================================
-- 8. Orders  (one row per individual order placed)
-- ============================================================
CREATE TABLE IF NOT EXISTS orders (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER NOT NULL REFERENCES trade_sessions(id) ON DELETE CASCADE,
    broker_order_id  TEXT,
    symbol           TEXT    NOT NULL,
    position_type    TEXT    NOT NULL,
    quantity         INTEGER NOT NULL DEFAULT 0,
    entry_price      REAL,
    exit_price       REAL,
    stop_loss        REAL,
    take_profit      REAL,
    pnl              REAL,
    status           TEXT    NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','OPEN','CLOSED','CANCELLED','REJECTED')),
    is_confirmed     INTEGER NOT NULL DEFAULT 0,
    entered_at       TEXT,
    exited_at        TEXT,
    reason_to_exit   TEXT,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id);
CREATE INDEX IF NOT EXISTS idx_orders_status  ON orders(status);

-- ============================================================
-- 9. Generic key-value store  (replaces Config / strategy_setting.json)
-- ============================================================
CREATE TABLE IF NOT EXISTS app_kv (
    key        TEXT    PRIMARY KEY,
    value      TEXT    NOT NULL DEFAULT '',
    updated_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);
"""

# ─────────────────────────────────────────────────────────────────────────────
# Seed statements — INSERT OR IGNORE so user data is never overwritten
# ─────────────────────────────────────────────────────────────────────────────
_SINGLETON_SEEDS: Dict[str, str] = {
    "brokerage_setting":
        "INSERT OR IGNORE INTO brokerage_setting (id) VALUES (1)",
    "daily_trade_setting":
        "INSERT OR IGNORE INTO daily_trade_setting (id) VALUES (1)",
    "profit_stoploss_setting":
        "INSERT OR IGNORE INTO profit_stoploss_setting (id) VALUES (1)",
    "trading_mode_setting":
        "INSERT OR IGNORE INTO trading_mode_setting (id) VALUES (1)",
    "strategy_active":
        "INSERT OR IGNORE INTO strategy_active (id, active_slug) VALUES (1, NULL)",
    "broker_tokens":
        "INSERT OR IGNORE INTO broker_tokens (id) VALUES (1)",
}

# ─────────────────────────────────────────────────────────────────────────────
# Health-check manifest  (table -> minimum expected columns)
# ─────────────────────────────────────────────────────────────────────────────
EXPECTED_TABLES: Dict[str, List[str]] = {
    "brokerage_setting": [
        "id", "client_id", "secret_key", "redirect_uri", "updated_at",
    ],
    "daily_trade_setting": [
        "id", "exchange", "week", "derivative", "lot_size",
        "call_lookback", "put_lookback", "history_interval",
        "max_num_of_option", "lower_percentage", "cancel_after",
        "capital_reserve", "sideway_zone_trade", "updated_at",
    ],
    "profit_stoploss_setting": [
        "id", "profit_type", "tp_percentage", "stoploss_percentage",
        "trailing_first_profit", "max_profit", "profit_step",
        "loss_step", "updated_at",
    ],
    "trading_mode_setting": [
        "id", "mode", "paper_balance", "allow_live_trading",
        "confirm_live_trades", "simulate_slippage", "slippage_percent",
        "simulate_delay", "delay_ms", "updated_at",
    ],
    "strategies": [
        "slug", "name", "description", "indicators", "engine",
        "created_at", "updated_at",
    ],
    "strategy_active": ["id", "active_slug", "updated_at"],
    "broker_tokens": [
        "id", "access_token", "issued_at", "expires_at", "updated_at",
    ],
    "trade_sessions": [
        "id", "started_at", "ended_at", "mode", "exchange",
        "derivative", "lot_size", "interval", "total_pnl",
        "total_trades", "winning_trades", "losing_trades",
        "strategy_slug", "notes",
    ],
    "orders": [
        "id", "session_id", "broker_order_id", "symbol",
        "position_type", "quantity", "entry_price", "exit_price",
        "stop_loss", "take_profit", "pnl", "status",
        "is_confirmed", "entered_at", "exited_at",
        "reason_to_exit", "created_at",
    ],
    "app_kv": ["key", "value", "updated_at"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InstallResult:
    ok: bool = True
    db_path: str = DEFAULT_DB_PATH
    db_created: bool = False
    tables_created: List[str] = field(default_factory=list)
    missing_tables: List[str] = field(default_factory=list)
    missing_columns: Dict[str, List[str]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Database : {self.db_path}",
            f"Status   : {'OK' if self.ok else 'FAILED'}",
        ]
        if self.db_created:
            lines.append("  -> Fresh database created.")
        if self.tables_created:
            lines.append(f"  -> Tables installed : {', '.join(self.tables_created)}")
        if self.missing_tables:
            lines.append(f"  X Still missing     : {', '.join(self.missing_tables)}")
        if self.missing_columns:
            for tbl, cols in self.missing_columns.items():
                lines.append(f"  X {tbl}: missing columns {cols}")
        for w in self.warnings:
            lines.append(f"  ! {w}")
        for e in self.errors:
            lines.append(f"  X {e}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Core installer
# ─────────────────────────────────────────────────────────────────────────────

class DatabaseInstaller:
    """
    Handles first-time installation and every-startup health-check.
    Entirely self-contained — uses only the Python stdlib.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ── Public ───────────────────────────────────────────────────────────────

    def run(self) -> InstallResult:
        """
        Execute the full install + health-check pipeline.
        Always returns an InstallResult — never raises.
        """
        result = InstallResult(db_path=self.db_path)
        try:
            self._ensure_directory(result)
            self._open_connection(result)

            if self._conn is None:
                result.ok = False
                return result

            self._apply_schema(result)
            self._seed_singletons(result)
            self._health_check(result)

        except Exception as exc:
            msg = f"Unexpected installer error: {exc}"
            logger.critical(f"[DB Installer] {msg}", exc_info=True)
            result.errors.append(msg)
            result.ok = False

        finally:
            self._close_connection()

        if result.ok:
            logger.info(f"[DB Installer] Database ready -> {self.db_path}")
        else:
            logger.error(
                f"[DB Installer] Problems detected -> {self.db_path}\n"
                f"{result.summary()}"
            )

        return result

    # ── Pipeline steps ────────────────────────────────────────────────────────

    def _ensure_directory(self, result: InstallResult) -> None:
        """Create parent directory for the DB file if it does not exist."""
        db_dir = Path(self.db_path).parent
        try:
            if db_dir and not db_dir.exists():
                db_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"[DB Installer] Created directory: {db_dir}")
        except Exception as exc:
            msg = f"Cannot create DB directory '{db_dir}': {exc}"
            result.errors.append(msg)
            result.ok = False
            logger.error(f"[DB Installer] {msg}")

    def _open_connection(self, result: InstallResult) -> None:
        """Open (or create) the SQLite file and configure pragmas."""
        db_file = Path(self.db_path)
        result.db_created = not db_file.exists()
        try:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            for pragma in (
                "PRAGMA journal_mode = WAL;",
                "PRAGMA foreign_keys = ON;",
                "PRAGMA busy_timeout = 5000;",
            ):
                self._conn.execute(pragma)
            label = "New database created" if result.db_created else "Opened existing database"
            logger.info(f"[DB Installer] {label}: {self.db_path}")
        except Exception as exc:
            msg = f"Cannot open database '{self.db_path}': {exc}"
            result.errors.append(msg)
            result.ok = False
            logger.critical(f"[DB Installer] {msg}", exc_info=True)
            self._conn = None

    def _apply_schema(self, result: InstallResult) -> None:
        """
        Execute the embedded SCHEMA_SQL against the open connection.

        Every statement uses IF NOT EXISTS — running this against a database
        that already has tables is completely safe; no data is lost.
        """
        before = self._existing_tables()
        try:
            self._conn.executescript(SCHEMA_SQL)
            self._conn.commit()
            logger.info("[DB Installer] Schema applied.")
        except Exception as exc:
            msg = f"Failed to apply schema: {exc}"
            result.errors.append(msg)
            result.ok = False
            logger.error(f"[DB Installer] {msg}", exc_info=True)
            return

        after = self._existing_tables()
        new_tables = sorted((after - before) - {"sqlite_sequence"})
        result.tables_created = new_tables
        if new_tables:
            logger.info(f"[DB Installer] New tables installed: {new_tables}")

    def _seed_singletons(self, result: InstallResult) -> None:
        """
        Guarantee exactly one row exists in each singleton settings table.
        INSERT OR IGNORE — never overwrites existing user data.
        """
        for table, sql in _SINGLETON_SEEDS.items():
            try:
                self._conn.execute(sql)
            except Exception as exc:
                msg = f"Could not seed singleton row in '{table}': {exc}"
                result.warnings.append(msg)
                logger.warning(f"[DB Installer] {msg}")
        try:
            self._conn.commit()
        except Exception as exc:
            logger.warning(f"[DB Installer] Commit after seeding failed: {exc}")

    def _health_check(self, result: InstallResult) -> None:
        """
        Verify every expected table and its required columns exist.
        Also confirms singleton rows are present in settings tables.
        """
        existing_tables = self._existing_tables()

        for table, expected_cols in EXPECTED_TABLES.items():
            if table not in existing_tables:
                result.missing_tables.append(table)
                result.ok = False
                logger.error(f"[DB Installer] Missing table: {table}")
                continue

            actual_cols = self._existing_columns(table)
            missing = [c for c in expected_cols if c not in actual_cols]
            if missing:
                result.missing_columns[table] = missing
                result.ok = False
                logger.error(f"[DB Installer] '{table}' missing columns: {missing}")
            else:
                logger.debug(f"[DB Installer] OK: {table}")

        for table in _SINGLETON_SEEDS:
            if table not in existing_tables:
                continue
            try:
                row = self._conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE id = 1"
                ).fetchone()
                if row and row[0] == 0:
                    msg = f"Singleton row missing in '{table}' (id=1)"
                    result.warnings.append(msg)
                    logger.warning(f"[DB Installer] {msg}")
            except Exception as exc:
                logger.warning(
                    f"[DB Installer] Could not verify singleton in '{table}': {exc}"
                )

        if result.ok:
            logger.info(
                f"[DB Installer] Health-check passed - "
                f"{len(EXPECTED_TABLES)} tables verified"
            )

    # ── Introspection helpers ─────────────────────────────────────────────────

    def _existing_tables(self) -> set:
        try:
            rows = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            return {r[0] for r in rows}
        except Exception as exc:
            logger.error(f"[DB Installer] _existing_tables failed: {exc}")
            return set()

    def _existing_columns(self, table: str) -> set:
        try:
            rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            return {r[1] for r in rows}   # index 1 = column name
        except Exception as exc:
            logger.error(
                f"[DB Installer] _existing_columns failed for '{table}': {exc}"
            )
            return set()

    def _close_connection(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            finally:
                self._conn = None


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton + public API
# ─────────────────────────────────────────────────────────────────────────────

_startup_result: Optional[InstallResult] = None


def run_startup_check(db_path: str = DEFAULT_DB_PATH) -> InstallResult:
    """
    Run the installer / health-check and cache the result.

    Subsequent calls within the same process return the cached result
    immediately (no I/O).  Call reset_startup_check() to force a re-run
    (useful in tests).

    Args:
        db_path: Path to the SQLite file.  Defaults to config/trading.db
                 or the TRADING_DB_PATH environment variable.

    Returns:
        InstallResult with .ok, .summary(), and detailed diagnostic fields.
    """
    global _startup_result
    if _startup_result is not None:
        logger.debug("[DB Installer] Returning cached startup result.")
        return _startup_result

    _startup_result = DatabaseInstaller(db_path).run()
    return _startup_result


def reset_startup_check() -> None:
    """Clear the cached result so run_startup_check() will execute again."""
    global _startup_result
    _startup_result = None


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry-point:  python -m db.db_installer
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    res = run_startup_check()
    print()
    print(res.summary())
    sys.exit(0 if res.ok else 1)