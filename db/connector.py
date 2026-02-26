"""
Database Connector Module
=========================
Thread-safe SQLite connector for the trading application.

This module provides a robust, thread-safe interface to SQLite database operations,
designed specifically for multi-threaded trading applications. It manages connection
lifecycles, ensures schema initialization, and provides convenient CRUD operations.

Architecture:
    The module implements a singleton pattern with thread-local connections:

    1. **Singleton Pattern**: `get_db()` returns a single DatabaseConnector instance
       shared across the application, ensuring consistent database access.

    2. **Thread-Local Connections**: Each thread gets its own SQLite connection
       via `threading.local()`, since SQLite connections cannot be shared safely
       across threads.

    3. **Context Manager**: `connection()` context manager provides automatic
       commit/rollback semantics for transaction management.

    4. **Schema Management**: Automatic schema application on first connection
       using embedded SQL from db_installer.

Key Features:
    - Thread-safe connection management with thread-local storage
    - Automatic schema initialization (CREATE IF NOT EXISTS)
    - WAL (Write-Ahead Logging) mode for better concurrency
    - Foreign key constraint enforcement
    - Busy timeout for handling contention
    - Context manager for safe transaction handling
    - Convenience methods for common CRUD operations
    - Database maintenance utilities (vacuum, backup, size check)

Thread Safety:
    SQLite connections are NOT thread-safe. This module solves this by:
        - Using `threading.local()` to give each thread its own connection
        - Setting `check_same_thread=False` and managing safety ourselves
        - Using locks only for schema initialization (shared across threads)

    The result is safe concurrent access from multiple threads.

Usage:
    from db.connector import get_db

    # Get singleton instance
    db = get_db()

    # Use context manager for transactions
    with db.connection() as conn:
        conn.execute("INSERT INTO trades VALUES (?, ?)", (symbol, price))

    # Use convenience methods
    db.execute("UPDATE config SET value = ? WHERE key = ?", ("new_value", "setting"))
    rows = db.fetchall("SELECT * FROM positions")

    # Check table existence
    if db.table_exists("orders"):
        print("Orders table exists")

Dependencies:
    - sqlite3: Built-in Python SQLite module
    - threading: For thread-local storage and locks
    - contextlib: For context manager decorator

Version: 1.0.0
"""

import sqlite3
import threading
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default database path — change via DB_PATH env var or get_db(path=...)
# ---------------------------------------------------------------------------
_DEFAULT_DB_PATH = os.environ.get("TRADING_DB_PATH", "config/trading.db")

# Module-level singleton
_instance: Optional["DatabaseConnector"] = None
_instance_lock = threading.Lock()


def get_db(path: str = _DEFAULT_DB_PATH) -> "DatabaseConnector":
    """
    Return the global DatabaseConnector singleton (thread-safe).

    This function implements the singleton pattern with double-checked locking
    to ensure only one DatabaseConnector instance exists throughout the application.

    Args:
        path: Database file path. Defaults to environment variable TRADING_DB_PATH
              or "config/trading.db".

    Returns:
        DatabaseConnector: The singleton database connector instance.

    Thread Safety:
        Uses double-checked locking with _instance_lock to ensure thread-safe
        singleton initialization.

    Example:
        db = get_db()
        db.execute("INSERT INTO ...")
    """
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DatabaseConnector(path)
    return _instance


def reset_db() -> None:
    """
    Tear down the singleton instance (useful for testing).

    This function closes the current database connection and resets the
    singleton to None, allowing a new instance to be created. Primarily
    used in test fixtures to ensure a clean database state between tests.

    Thread Safety:
        Uses _instance_lock to prevent race conditions during reset.
    """
    global _instance
    with _instance_lock:
        if _instance is not None:
            _instance.close()
            _instance = None


class DatabaseConnector:
    """
    Thread-safe SQLite connector with connection pooling per thread.

    This class manages SQLite database connections in a multi-threaded environment.
    Each thread gets its own connection via thread-local storage, ensuring thread
    safety while maintaining connection pooling efficiency.

    Architecture:
        - Uses `threading.local()` to store thread-specific connections
        - Connections are created on-demand when first used in a thread
        - WAL mode enabled for better read/write concurrency
        - Schema applied automatically on first connection (idempotent DDL)
        - Context manager support for automatic transaction management

    Attributes:
        db_path (str): Path to the SQLite database file
        _local (threading.local): Thread-local storage for connections
        _schema_applied (bool): Whether schema has been initialized
        _schema_lock (threading.Lock): Lock for schema initialization

    Thread Safety:
        - Each thread has its own connection (via _local)
        - Schema initialization is protected by _schema_lock
        - Connection methods are thread-safe by design

    Example:
        db = DatabaseConnector("config/trading.db")

        # Using context manager (auto-commit/rollback)
        with db.connection() as conn:
            conn.execute("INSERT INTO trades VALUES (?, ?)", (symbol, price))

        # Using convenience methods
        result = db.fetchone("SELECT * FROM config WHERE key = ?", ("setting",))
    """

    def __init__(self, db_path: str):
        """
        Initialize the database connector.

        Args:
            db_path: Path to the SQLite database file.

        Raises:
            ValueError: If db_path is invalid.
            sqlite3.Error: If database cannot be opened or schema cannot be applied.

        Note:
            Creates the database directory if it doesn't exist.
            Automatically creates a connection on the current thread to warm up.
        """
        if not isinstance(db_path, str) or not db_path:
            raise ValueError(f"Invalid db_path: {db_path!r}")

        self.db_path = db_path
        self._local = threading.local()  # per-thread storage for connections
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
        """
        Return (or create) the connection for the current thread.

        This method implements thread-local connection pooling:
            - If the current thread already has a connection, return it
            - Otherwise, create a new connection, configure it, and store it

        Returns:
            sqlite3.Connection: SQLite connection for the current thread.

        Raises:
            sqlite3.Error: If connection cannot be established.

        Note:
            Configures the connection with:
                - row_factory = sqlite3.Row (dictionary-like rows)
                - WAL journal mode for concurrency
                - Foreign key constraints enabled
                - Busy timeout of 5 seconds
        """
        if not hasattr(self._local, "conn") or self._local.conn is None:
            try:
                conn = sqlite3.connect(
                    self.db_path,
                    check_same_thread=False,  # we manage thread-safety ourselves
                    detect_types=sqlite3.PARSE_DECLTYPES,
                )
                # Configure connection for optimal performance and safety
                conn.row_factory = sqlite3.Row  # rows behave like dictionaries
                conn.execute("PRAGMA journal_mode = WAL;")  # Write-Ahead Logging for concurrency
                conn.execute("PRAGMA foreign_keys = ON;")   # Enforce referential integrity
                conn.execute("PRAGMA busy_timeout = 5000;") # Wait up to 5 seconds when busy

                self._local.conn = conn
                self._apply_schema(conn)
                logger.debug(f"New SQLite connection for thread {threading.current_thread().name}")
            except Exception as e:
                logger.critical(f"[DatabaseConnector] Cannot open {self.db_path}: {e}", exc_info=True)
                raise
        return self._local.conn

    def _apply_schema(self, conn: sqlite3.Connection) -> None:
        """
        Apply database schema if not already done.

        This method executes the schema SQL from db_installer to create all
        required tables. It uses idempotent CREATE IF NOT EXISTS statements
        so it's safe to call multiple times.

        Args:
            conn: SQLite connection to apply schema on.

        Raises:
            Exception: If schema application fails.

        Thread Safety:
            Uses _schema_lock to ensure schema is applied only once
            across all threads.

        Note:
            The schema is applied only once per application lifecycle,
            regardless of how many threads connect.
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

        This is the primary way to perform database operations. It provides
        automatic transaction management:
            - On successful exit: commits the transaction
            - On exception: rolls back the transaction

        Yields:
            sqlite3.Connection: Database connection for the current thread.

        Raises:
            sqlite3.Error: If a database error occurs.
            Exception: Any other exception that occurs in the with block.

        Example:
            with db.connection() as conn:
                conn.execute("INSERT INTO trades VALUES (?, ?)", (symbol, price))
                # Auto-commit on successful exit
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
        """
        Execute a single statement and commit (for one-liners).

        Convenience method for simple INSERT/UPDATE/DELETE operations that
        don't require a full context manager.

        Args:
            sql: SQL statement to execute.
            params: Optional tuple of parameters for the SQL statement.

        Returns:
            sqlite3.Cursor: Cursor object from the execution.

        Raises:
            sqlite3.Error: If database error occurs.

        Example:
            cursor = db.execute("UPDATE config SET value = ? WHERE key = ?",
                               ("new_value", "setting"))
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur
        except Exception as e:
            conn.rollback()
            logger.error(f"[execute] Failed: {e}\nSQL: {sql}\nParams: {params}", exc_info=True)
            raise

    def fetchall(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """
        Execute a SELECT and return all rows as list of sqlite3.Row.

        Args:
            sql: SELECT statement to execute.
            params: Optional tuple of parameters for the SQL statement.

        Returns:
            List[sqlite3.Row]: List of rows (each row behaves like a dictionary).
                              Returns empty list on error.

        Example:
            rows = db.fetchall("SELECT * FROM trades WHERE symbol = ?", ("NIFTY",))
            for row in rows:
                print(row['price'], row['quantity'])
        """
        conn = self._get_conn()
        try:
            return conn.execute(sql, params).fetchall()
        except Exception as e:
            logger.error(f"[fetchall] Failed: {e}\nSQL: {sql}", exc_info=True)
            return []

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """
        Execute a SELECT and return a single row or None.

        Args:
            sql: SELECT statement to execute.
            params: Optional tuple of parameters for the SQL statement.

        Returns:
            Optional[sqlite3.Row]: First row of the result, or None if no results.

        Example:
            row = db.fetchone("SELECT * FROM config WHERE key = ?", ("setting",))
            if row:
                value = row['value']
        """
        conn = self._get_conn()
        try:
            return conn.execute(sql, params).fetchone()
        except Exception as e:
            logger.error(f"[fetchone] Failed: {e}\nSQL: {sql}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # NEW: Convenience methods for CRUD operations
    # These methods provide higher-level abstractions for common
    # database operations, reducing boilerplate code.
    # ------------------------------------------------------------------

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """
        Insert a row and return the last row id.

        Args:
            table: Table name.
            data: Dictionary mapping column names to values.

        Returns:
            int: Last inserted row ID, or -1 on error.

        Example:
            order_id = db.insert("orders", {
                'symbol': 'NIFTY',
                'quantity': 75,
                'price': 18500.50
            })
        """
        conn = self._get_conn()
        try:
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['?' for _ in data])
            sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            cur = conn.execute(sql, tuple(data.values()))
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            conn.rollback()
            logger.error(f"[insert] Failed into {table}: {e}", exc_info=True)
            return -1

    def update(self, table: str, data: Dict[str, Any], where: str, where_params: tuple) -> bool:
        """
        Update rows matching condition.

        Args:
            table: Table name.
            data: Dictionary of column -> value to update.
            where: WHERE clause (e.g., "id = ?").
            where_params: Parameters for WHERE clause.

        Returns:
            bool: True if successful, False otherwise.

        Example:
            success = db.update(
                "orders",
                {'status': 'COMPLETED', 'price': 18550.0},
                "order_id = ?",
                ("ORD12345",)
            )
        """
        conn = self._get_conn()
        try:
            set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
            sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
            params = tuple(data.values()) + where_params
            conn.execute(sql, params)
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"[update] Failed in {table}: {e}", exc_info=True)
            return False

    def delete(self, table: str, where: str, where_params: tuple) -> bool:
        """
        Delete rows matching condition.

        Args:
            table: Table name.
            where: WHERE clause.
            where_params: Parameters for WHERE clause.

        Returns:
            bool: True if successful, False otherwise.

        Example:
            success = db.delete("trades", "timestamp < ?",
                               (one_week_ago.isoformat(),))
        """
        conn = self._get_conn()
        try:
            sql = f"DELETE FROM {table} WHERE {where}"
            conn.execute(sql, where_params)
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"[delete] Failed in {table}: {e}", exc_info=True)
            return False

    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.

        Args:
            table_name: Name of the table to check.

        Returns:
            bool: True if table exists, False otherwise.

        Example:
            if db.table_exists("orders"):
                print("Orders table exists")
        """
        try:
            result = self.fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            return result is not None
        except Exception as e:
            logger.error(f"[table_exists] Failed for {table_name}: {e}", exc_info=True)
            return False

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get column information for a table.

        Uses SQLite's PRAGMA table_info to retrieve column metadata.

        Args:
            table_name: Name of the table.

        Returns:
            List[Dict[str, Any]]: List of column information dictionaries.
                                  Each dict contains: cid, name, type, notnull,
                                  dflt_value, pk.

        Example:
            columns = db.get_table_info("orders")
            for col in columns:
                print(f"{col['name']} ({col['type']})")
        """
        try:
            rows = self.fetchall(f"PRAGMA table_info({table_name})")
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[get_table_info] Failed for {table_name}: {e}", exc_info=True)
            return []

    def vacuum(self) -> bool:
        """
        Run VACUUM to optimize database.

        VACUUM rebuilds the database file, repacking it into a minimal
        amount of disk space. It's useful after large deletes or updates.

        Returns:
            bool: True if successful, False otherwise.

        Note:
            This operation requires exclusive access to the database and
            may take time on large databases.
        """
        try:
            conn = self._get_conn()
            conn.execute("VACUUM")
            logger.info("Database vacuum completed")
            return True
        except Exception as e:
            logger.error(f"[vacuum] Failed: {e}", exc_info=True)
            return False

    def backup(self, backup_path: str) -> bool:
        """
        Create a backup of the database.

        Args:
            backup_path: Path for backup file.

        Returns:
            bool: True if successful, False otherwise.

        Example:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            db.backup(f"backups/trading_{timestamp}.db")
        """
        try:
            import shutil
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"Database backed up to {backup_path}")
            return True
        except Exception as e:
            logger.error(f"[backup] Failed: {e}", exc_info=True)
            return False

    def get_size(self) -> int:
        """
        Get database file size in bytes.

        Returns:
            int: File size in bytes, or 0 on error.
        """
        try:
            return os.path.getsize(self.db_path)
        except Exception as e:
            logger.error(f"[get_size] Failed: {e}", exc_info=True)
            return 0

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """
        Close the current thread's connection.

        This method closes the SQLite connection for the current thread only.
        Other threads' connections remain open.

        Note:
            It's safe to call this method multiple times. After closing,
            the connection will be recreated if needed.
        """
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.close()
                self._local.conn = None
                logger.debug("SQLite connection closed.")
            except Exception as e:
                logger.warning(f"[close] Error closing connection: {e}")

    def close_all(self) -> None:
        """
        Best-effort — closes the current thread's connection only.

        Note:
            Due to the thread-local architecture, it's not possible to
            close connections from other threads. This method exists for
            interface compatibility and simply calls close().
        """
        self.close()