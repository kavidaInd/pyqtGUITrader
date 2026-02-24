"""
db/connector.py
---------------
Thread-safe SQLite connector for the trading app.

Usage:
    from db.connector import get_db

    db = get_db()                  # returns the singleton DatabaseConnector
    with db.connection() as conn:  # context manager — auto-commits or rolls back
        conn.execute(...)
"""

import sqlite3
import threading
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default database path — change via DB_PATH env var or get_db(path=...)
# ---------------------------------------------------------------------------
_DEFAULT_DB_PATH = os.environ.get("TRADING_DB_PATH", "config/trading.db")

# Module-level singleton
_instance: Optional["DatabaseConnector"] = None
_instance_lock = threading.Lock()


def get_db(path: str = _DEFAULT_DB_PATH) -> "DatabaseConnector":
    """Return the global DatabaseConnector singleton (thread-safe)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DatabaseConnector(path)
    return _instance


def reset_db() -> None:
    """Tear down the singleton (useful for tests)."""
    global _instance
    with _instance_lock:
        if _instance is not None:
            _instance.close()
            _instance = None


class DatabaseConnector:
    """
    Thread-safe SQLite connector.

    • Uses a per-thread connection (threading.local) so each thread gets its
      own sqlite3 connection — SQLite connections must not be shared.
    • WAL mode is enabled for better read/write concurrency.
    • Schema is applied automatically on first connect (idempotent DDL).
    """

    def __init__(self, db_path: str):
        if not isinstance(db_path, str) or not db_path:
            raise ValueError(f"Invalid db_path: {db_path!r}")

        self.db_path = db_path
        self._local = threading.local()   # per-thread storage
        self._schema_applied = False
        self._schema_lock = threading.Lock()

        # Ensure directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir:
            Path(db_dir).mkdir(parents=True, exist_ok=True)

        # Warm up on the current thread and apply schema
        self._get_conn()
        logger.info(f"DatabaseConnector initialised → {self.db_path}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return (or create) the connection for the current thread."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            try:
                conn = sqlite3.connect(
                    self.db_path,
                    check_same_thread=False,  # we manage thread-safety ourselves
                    detect_types=sqlite3.PARSE_DECLTYPES,
                )
                conn.row_factory = sqlite3.Row   # rows behave like dicts
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA foreign_keys = ON;")
                conn.execute("PRAGMA busy_timeout = 5000;")
                self._local.conn = conn
                self._apply_schema(conn)
                logger.debug(f"New SQLite connection for thread {threading.current_thread().name}")
            except Exception as e:
                logger.critical(f"[DatabaseConnector] Cannot open {self.db_path}: {e}", exc_info=True)
                raise
        return self._local.conn

    def _apply_schema(self, conn: sqlite3.Connection) -> None:
        """Apply schema DDL if not already done (idempotent CREATE IF NOT EXISTS).
        Uses the embedded SCHEMA_SQL from db_installer — no external file needed.
        """
        with self._schema_lock:
            if self._schema_applied:
                return
            try:
                from db.db_installer import SCHEMA_SQL
                conn.executescript(SCHEMA_SQL)
                conn.commit()
                self._schema_applied = True
                logger.info("Database schema applied successfully.")
            except Exception as e:
                logger.error(f"[_apply_schema] Failed: {e}", exc_info=True)
                raise

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @contextmanager
    def connection(self):
        """
        Context manager that yields a raw sqlite3.Connection.
        Commits on clean exit, rolls back on exception.

        Usage::
            with db.connection() as conn:
                conn.execute("INSERT INTO ...")
        """
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"[connection] SQLite error — rolled back: {e}", exc_info=True)
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"[connection] Unexpected error — rolled back: {e}", exc_info=True)
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a single statement and commit (for one-liners)."""
        conn = self._get_conn()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur
        except Exception as e:
            conn.rollback()
            logger.error(f"[execute] Failed: {e}\nSQL: {sql}\nParams: {params}", exc_info=True)
            raise

    def fetchall(self, sql: str, params: tuple = ()) -> list:
        """Execute a SELECT and return all rows as list of sqlite3.Row."""
        conn = self._get_conn()
        try:
            return conn.execute(sql, params).fetchall()
        except Exception as e:
            logger.error(f"[fetchall] Failed: {e}\nSQL: {sql}", exc_info=True)
            return []

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Execute a SELECT and return a single row or None."""
        conn = self._get_conn()
        try:
            return conn.execute(sql, params).fetchone()
        except Exception as e:
            logger.error(f"[fetchone] Failed: {e}\nSQL: {sql}", exc_info=True)
            return None

    def close(self) -> None:
        """Close the current thread's connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.close()
                self._local.conn = None
                logger.debug("SQLite connection closed.")
            except Exception as e:
                logger.warning(f"[close] Error closing connection: {e}")

    def close_all(self) -> None:
        """Best-effort — closes the current thread's connection only."""
        self.close()