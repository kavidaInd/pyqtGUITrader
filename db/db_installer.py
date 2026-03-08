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
4. Seeds all settings defaults into app_kv (INSERT OR IGNORE — never
   overwrites user data).
5. Runs a column-level health-check on every expected table.
6. Returns an InstallResult the caller can inspect or show in a dialog.

Architecture (v3.0)
───────────────────
Settings-like singletons are stored in app_kv using namespaced keys.
The following tables were removed and their data moved to app_kv:

  Removed tables             → app_kv namespace
  ─────────────────────────────────────────────
  brokerage_setting          → brokerage:<field>
  daily_trade_setting        → daily_trade:<field>
  profit_stoploss_setting    → profit_stoploss:<field>
  trading_mode_setting       → trading_mode:<field>
  strategy_active            → strategy:active_slug
  broker_tokens              → token:<field>
  license_activations        → license:<field>   (already in kv in license_manager)
  risk_settings              → (direct kv keys)
  signal_settings            → (direct kv keys)
  telegram_settings          → (direct kv keys)
  mtf_settings               → (direct kv keys)

  Remaining full tables (relational / time-series data)
  ──────────────────────────────────────────────────────
  strategies      — strategy definitions
  trade_sessions  — one row per session
  orders          — individual orders
  daily_pnl       — daily P&L cache
  ws_stats        — WebSocket monitoring
  app_kv          — generic key-value store

Usage
──────────────────────────────────────────────────────────
    from db.db_installer import run_startup_check
    result = run_startup_check()
    if not result.ok:
        print(result.summary())
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

DEFAULT_DB_PATH: str = os.environ.get("TRADING_DB_PATH", "config/trading.db")


# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDED SCHEMA  (v3.0 — settings singletons removed, only full tables kept)
# ─────────────────────────────────────────────────────────────────────────────
SCHEMA_SQL: str = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- 1. Strategies  (relational — slug is the primary key)
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

-- ============================================================
-- 2. Trade sessions  (one row per trading session / day run)
-- ============================================================
CREATE TABLE IF NOT EXISTS trade_sessions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    ended_at       TEXT,
    mode           TEXT    NOT NULL DEFAULT 'PAPER',
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
-- 3. Orders  (one row per individual order placed)
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
                     CHECK (status IN ('PENDING','CONFIRMED','OPEN','CLOSED','CANCELLED','REJECTED')),
    is_confirmed     INTEGER NOT NULL DEFAULT 0,
    entered_at       TEXT,
    exited_at        TEXT,
    confirmed_at     TEXT,
    cancelled_at     TEXT,
    reason_to_exit   TEXT,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    updated_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_orders_session    ON orders(session_id);
CREATE INDEX IF NOT EXISTS idx_orders_status     ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_exited_at  ON orders(exited_at);

-- ============================================================
-- 4. Generic key-value store  (all settings live here)
-- ============================================================
CREATE TABLE IF NOT EXISTS app_kv (
    key        TEXT    PRIMARY KEY,
    value      TEXT    NOT NULL DEFAULT '',
    updated_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

-- ============================================================
-- 5. Daily P&L tracking  (time-series cache)
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_pnl (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    date           TEXT    NOT NULL UNIQUE,
    realized_pnl   REAL    NOT NULL DEFAULT 0.0,
    unrealized_pnl REAL    NOT NULL DEFAULT 0.0,
    trades_count   INTEGER NOT NULL DEFAULT 0,
    winners_count  INTEGER NOT NULL DEFAULT 0,
    max_drawdown   REAL    NOT NULL DEFAULT 0.0,
    peak           REAL    NOT NULL DEFAULT 0.0,
    updated_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_daily_pnl_date ON daily_pnl(date);

-- ============================================================
-- 6. WebSocket connection stats  (monitoring)
-- ============================================================
CREATE TABLE IF NOT EXISTS ws_stats (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER REFERENCES trade_sessions(id) ON DELETE CASCADE,
    connected_at      TEXT,
    disconnected_at   TEXT,
    messages_received INTEGER NOT NULL DEFAULT 0,
    errors_count      INTEGER NOT NULL DEFAULT 0,
    reconnects_count  INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);
"""

# ─────────────────────────────────────────────────────────────────────────────
# app_kv default seeds
#
# All settings-like singletons are stored here.  INSERT OR IGNORE means
# existing user values are never overwritten.
#
# Namespaces
#   brokerage:*        — broker credentials
#   daily_trade:*      — daily trade config
#   profit_stoploss:*  — TP/SL settings
#   trading_mode:*     — paper / live / backtest
#   token:*            — broker auth tokens
#   strategy:*         — active strategy pointer
#   license:*          — license activation record
#   (bare keys)        — risk, signal, telegram, mtf (legacy flat names kept)
# ─────────────────────────────────────────────────────────────────────────────
_KV_SEEDS: Dict[str, str] = {
    # ── Brokerage credentials ──────────────────────────────────────────────
    "brokerage:broker_type":   '"fyers"',
    "brokerage:client_id":     '""',
    "brokerage:secret_key":    '""',
    "brokerage:redirect_uri":  '""',

    # ── Daily trade settings ───────────────────────────────────────────────
    "daily_trade:exchange":           '"NSE"',
    "daily_trade:week":               "0",
    "daily_trade:derivative":         '"NIFTY50"',
    "daily_trade:lot_size":           "75",
    "daily_trade:call_lookback":      "0",
    "daily_trade:put_lookback":       "0",
    "daily_trade:history_interval":   '"2m"',
    "daily_trade:max_num_of_option":  "1800",
    "daily_trade:lower_percentage":   "0.0",
    "daily_trade:cancel_after":       "5",
    "daily_trade:capital_reserve":    "0",
    "daily_trade:sideway_zone_trade": "false",

    # ── Profit / Stoploss settings ─────────────────────────────────────────
    "profit_stoploss:profit_type":           '"STOP"',
    "profit_stoploss:tp_percentage":         "15.0",
    "profit_stoploss:stoploss_percentage":   "7.0",
    "profit_stoploss:trailing_first_profit": "3.0",
    "profit_stoploss:max_profit":            "30.0",
    "profit_stoploss:profit_step":           "2.0",
    "profit_stoploss:loss_step":             "2.0",

    # ── Trading mode settings ──────────────────────────────────────────────
    "trading_mode:mode":               '"Paper"',
    "trading_mode:paper_balance":      "100000.0",
    "trading_mode:allow_live_trading": "false",
    "trading_mode:confirm_live_trades":"true",
    "trading_mode:simulate_slippage":  "true",
    "trading_mode:slippage_percent":   "0.05",
    "trading_mode:simulate_delay":     "true",
    "trading_mode:delay_ms":           "500",

    # ── Broker auth tokens ─────────────────────────────────────────────────
    "token:access_token":  '""',
    "token:refresh_token": '""',
    "token:issued_at":     '""',
    "token:expires_at":    '""',

    # ── Active strategy pointer ────────────────────────────────────────────
    "strategy:active_slug": '""',

    # ── License activation record ──────────────────────────────────────────
    "license:license_key":    '""',
    "license:order_id":       '""',
    "license:email":          '""',
    "license:machine_id":     '""',
    "license:plan":           '""',
    "license:customer_name":  '""',
    "license:expires_at":     '""',
    "license:last_verify_at": '""',
    "license:last_verify_ok": "false",
    "license:days_remaining": "0",

    # ── Risk Manager (Feature 1) ───────────────────────────────────────────
    "max_daily_loss":        "-5000",
    "max_trades_per_day":    "10",
    "daily_target":          "5000",

    # ── Signal Engine (Feature 3) ──────────────────────────────────────────
    "min_confidence":        "0.6",

    # ── Telegram Notifier (Feature 4) ─────────────────────────────────────
    "telegram_bot_token":    '""',
    "telegram_chat_id":      '""',
    "telegram_enabled":      "false",

    # ── Multi-Timeframe Filter (Feature 6) ────────────────────────────────
    "use_mtf_filter":         "false",
    "mtf_timeframes":         '["1","5","15"]',
    "mtf_ema_fast":           "9",
    "mtf_ema_slow":           "21",
    "mtf_agreement_required": "2",
}

# ─────────────────────────────────────────────────────────────────────────────
# Legacy tables to drop on upgrade
# All of these have been replaced by app_kv entries above.
# ─────────────────────────────────────────────────────────────────────────────
_LEGACY_TABLES: List[str] = [
    "brokerage_setting",
    "daily_trade_setting",
    "profit_stoploss_setting",
    "trading_mode_setting",
    "strategy_active",
    "broker_tokens",
    "license_activations",
    "risk_settings",
    "signal_settings",
    "telegram_settings",
    "mtf_settings",
]

# ─────────────────────────────────────────────────────────────────────────────
# Health-check manifest  (only the tables that still exist)
# ─────────────────────────────────────────────────────────────────────────────
EXPECTED_TABLES: Dict[str, List[str]] = {
    "strategies": [
        "slug", "name", "description", "indicators", "engine",
        "created_at", "updated_at",
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
        "is_confirmed", "entered_at", "exited_at", "confirmed_at",
        "cancelled_at", "reason_to_exit", "created_at", "updated_at",
    ],
    "app_kv":    ["key", "value", "updated_at"],
    "daily_pnl": [
        "id", "date", "realized_pnl", "unrealized_pnl",
        "trades_count", "winners_count", "max_drawdown", "peak", "updated_at",
    ],
    "ws_stats": [
        "id", "session_id", "connected_at", "disconnected_at",
        "messages_received", "errors_count", "reconnects_count", "created_at",
    ],
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

    def run(self) -> InstallResult:
        result = InstallResult(db_path=self.db_path)
        try:
            self._ensure_directory(result)
            self._open_connection(result)

            if self._conn is None:
                result.ok = False
                return result

            self._apply_schema(result)
            self._drop_legacy_tables(result)
            self._seed_kv(result)
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

    # ── Pipeline steps ────────────────────────────────────────────────────

    def _ensure_directory(self, result: InstallResult) -> None:
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
        """Execute the embedded SCHEMA_SQL (all IF NOT EXISTS — always safe)."""
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

    def _drop_legacy_tables(self, result: InstallResult) -> None:
        """
        Drop tables that have been superseded by app_kv.
        This migration is applied once to existing databases; it is a no-op
        when the tables do not exist.
        """
        existing = self._existing_tables()
        for tbl in _LEGACY_TABLES:
            if tbl not in existing:
                continue
            try:
                self._conn.execute(f"DROP TABLE IF EXISTS {tbl}")
                self._conn.commit()
                result.warnings.append(
                    f"Dropped legacy table '{tbl}' (data now in app_kv)."
                )
                logger.info(f"[DB Installer] Dropped legacy table: {tbl}")
            except Exception as exc:
                logger.warning(
                    f"[DB Installer] Could not drop legacy table '{tbl}': {exc}"
                )

    def _seed_kv(self, result: InstallResult) -> None:
        """
        Guarantee all default app_kv entries exist.
        INSERT OR IGNORE — never overwrites existing user values.
        """
        for key, default_value in _KV_SEEDS.items():
            try:
                self._conn.execute(
                    "INSERT OR IGNORE INTO app_kv (key, value, updated_at) "
                    "VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%S', 'now'))",
                    (key, default_value),
                )
            except Exception as exc:
                msg = f"Could not seed app_kv key '{key}': {exc}"
                result.warnings.append(msg)
                logger.warning(f"[DB Installer] {msg}")
        try:
            self._conn.commit()
        except Exception as exc:
            logger.warning(f"[DB Installer] Commit after seeding failed: {exc}")

    def _health_check(self, result: InstallResult) -> None:
        """Verify every expected table and its required columns exist."""
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

        if result.ok:
            logger.info(
                f"[DB Installer] Health-check passed — "
                f"{len(EXPECTED_TABLES)} tables verified"
            )

    # ── Introspection helpers ─────────────────────────────────────────────

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
            return {r[1] for r in rows}
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
    (no I/O).  Call reset_startup_check() to force a re-run (useful in tests).
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