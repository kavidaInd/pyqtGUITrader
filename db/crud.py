"""
Database CRUD Module
====================
CRUD operations for all database tables.

Architecture (v3.0)
───────────────────
Settings-like singletons are stored in app_kv using namespaced keys, while
transactional / relational data stays in proper tables:

  KV-backed (app_kv table)
  ─────────────────────────
  BrokerageCRUD        → keys  brokerage:<field>
  DailyTradeCRUD       → keys  daily_trade:<field>
  ProfitStoplossCRUD   → keys  profit_stoploss:<field>
  TradingModeCRUD      → keys  trading_mode:<field>
  TokenCRUD            → keys  token:<field>
  Active-strategy ptr  → key   strategy:active_slug

  Own tables (unchanged)
  ──────────────────────
  StrategiesCRUD       → strategies table
  SessionCRUD          → trade_sessions table
  OrderCRUD            → orders table
  KVCRUD               → app_kv table  (generic)

Every CRUD class keeps the same public interface it had before — all callers
(BrokerageSetting, DailyTradeSetting, TradingModeSetting, broker files, etc.)
work without any changes.
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from db.connector import DatabaseConnector, get_db

logger = logging.getLogger(__name__)

_NOW = lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════════

def _row_to_dict(row: Optional[sqlite3.Row]) -> Dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


def _kv_get(key: str, default: Any, db: DatabaseConnector) -> Any:
    """Read one key from app_kv, JSON-decode it."""
    row = db.fetchone("SELECT value FROM app_kv WHERE key=?", (key,))
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return row["value"]


def _kv_set(key: str, value: Any, db: DatabaseConnector) -> bool:
    """Write one key to app_kv (upsert)."""
    try:
        serialised = json.dumps(value) if not isinstance(value, str) else value
        db.execute(
            "INSERT INTO app_kv (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, serialised, _NOW()),
        )
        return True
    except Exception as e:
        logger.error(f"[_kv_set] key={key!r}: {e}", exc_info=True)
        return False


def _kv_get_ns(ns: str, defaults: Dict[str, Any], db: DatabaseConnector) -> Dict[str, Any]:
    """Read all keys for a namespace (ns:<field>) and return as dict."""
    result = dict(defaults)
    for field in defaults:
        result[field] = _kv_get(f"{ns}:{field}", defaults[field], db)
    return result


def _kv_set_ns(ns: str, data: Dict[str, Any], db: DatabaseConnector) -> bool:
    """Write all keys for a namespace."""
    ok = True
    for field, value in data.items():
        if not _kv_set(f"{ns}:{field}", value, db):
            ok = False
    return ok


# ══════════════════════════════════════════════════════════════════════════════
# 1. Brokerage Credentials  → app_kv  (brokerage:<field>)
# ══════════════════════════════════════════════════════════════════════════════

class BrokerageCRUD:
    """
    KV-backed brokerage credentials.
    Interface is identical to the old table-backed version.
    """

    NS = "brokerage"
    FIELDS = ("broker_type", "client_id", "secret_key", "redirect_uri")
    _DEFAULTS = {
        "broker_type": "fyers",
        "client_id": "",
        "secret_key": "",
        "redirect_uri": "",
    }

    def get(self, db: DatabaseConnector = None) -> Dict[str, str]:
        db = db or get_db()
        return _kv_get_ns(self.NS, self._DEFAULTS, db)

    def update(
            self,
            broker_type: str = None,
            client_id: str = None,
            secret_key: str = None,
            redirect_uri: str = None,
            db: DatabaseConnector = None,
    ) -> bool:
        db = db or get_db()
        current = self.get(db)
        data = {
            "broker_type": broker_type if broker_type is not None else current.get("broker_type", "fyers"),
            "client_id": client_id if client_id is not None else current.get("client_id", ""),
            "secret_key": secret_key if secret_key is not None else current.get("secret_key", ""),
            "redirect_uri": redirect_uri if redirect_uri is not None else current.get("redirect_uri", ""),
        }
        return _kv_set_ns(self.NS, data, db)

    def save(self, data: Dict[str, str], db: DatabaseConnector = None) -> bool:
        return self.update(
            broker_type=data.get("broker_type", "fyers"),
            client_id=data.get("client_id", ""),
            secret_key=data.get("secret_key", ""),
            redirect_uri=data.get("redirect_uri", ""),
            db=db,
        )

    def validate(self, db: DatabaseConnector = None) -> Dict[str, bool]:
        row = self.get(db)
        return {f: bool(row.get(f)) for f in self.FIELDS}

    def is_complete(self, db: DatabaseConnector = None) -> bool:
        v = self.validate(db)
        return all(v.get(f, False) for f in ("client_id", "secret_key", "redirect_uri"))

    def clear(self, db: DatabaseConnector = None) -> bool:
        return self.save({"broker_type": "fyers", "client_id": "", "secret_key": "", "redirect_uri": ""}, db)


brokerage = BrokerageCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 2. Daily Trade Settings  → app_kv  (daily_trade:<field>)
# ══════════════════════════════════════════════════════════════════════════════

class DailyTradeCRUD:
    """
    KV-backed daily trade settings.
    Interface is identical to the old table-backed version.
    """

    NS = "daily_trade"
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
        db = db or get_db()
        data = _kv_get_ns(self.NS, self.DEFAULTS, db)
        data["sideway_zone_trade"] = bool(data.get("sideway_zone_trade", False))
        return data

    def save(self, data: Dict[str, Any], db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        merged = {**self.DEFAULTS, **data}
        # Normalise types before storing
        normalised = {
            "exchange": str(merged["exchange"]),
            "week": int(merged["week"]),
            "derivative": str(merged["derivative"]),
            "lot_size": int(merged["lot_size"]),
            "call_lookback": int(merged["call_lookback"]),
            "put_lookback": int(merged["put_lookback"]),
            "history_interval": str(merged["history_interval"]),
            "max_num_of_option": int(merged["max_num_of_option"]),
            "lower_percentage": float(merged["lower_percentage"]),
            "cancel_after": int(merged["cancel_after"]),
            "capital_reserve": int(merged["capital_reserve"]),
            "sideway_zone_trade": bool(merged["sideway_zone_trade"]),
        }
        return _kv_set_ns(self.NS, normalised, db)

    def update_field(self, field: str, value: Any, db: DatabaseConnector = None) -> bool:
        if field not in self.DEFAULTS:
            logger.warning(f"[DailyTradeCRUD.update_field] Unknown field: {field}")
            return False
        current = self.get(db)
        current[field] = value
        return self.save(current, db)

    def reset(self, db: DatabaseConnector = None) -> bool:
        return self.save(self.DEFAULTS, db)


daily_trade = DailyTradeCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 3. Profit / Stoploss Settings  → app_kv  (profit_stoploss:<field>)
# ══════════════════════════════════════════════════════════════════════════════

class ProfitStoplossCRUD:
    """
    KV-backed profit / stoploss settings.
    Interface is identical to the old table-backed version.
    """

    NS = "profit_stoploss"
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
        db = db or get_db()
        return _kv_get_ns(self.NS, self.DEFAULTS, db)

    def save(self, data: Dict[str, Any], db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        merged = {**self.DEFAULTS, **data}
        normalised = {
            "profit_type": str(merged["profit_type"]),
            "tp_percentage": float(merged["tp_percentage"]),
            "stoploss_percentage": float(merged["stoploss_percentage"]),
            "trailing_first_profit": float(merged["trailing_first_profit"]),
            "max_profit": float(merged["max_profit"]),
            "profit_step": float(merged["profit_step"]),
            "loss_step": float(merged["loss_step"]),
        }
        return _kv_set_ns(self.NS, normalised, db)

    def update_field(self, field: str, value: Any, db: DatabaseConnector = None) -> bool:
        if field not in self.DEFAULTS:
            logger.warning(f"[ProfitStoplossCRUD.update_field] Unknown field: {field}")
            return False
        current = self.get(db)
        current[field] = value
        return self.save(current, db)

    def reset(self, db: DatabaseConnector = None) -> bool:
        return self.save(self.DEFAULTS, db)


profit_stoploss = ProfitStoplossCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 4. Trading Mode Settings  → app_kv  (trading_mode:<field>)
# ══════════════════════════════════════════════════════════════════════════════

class TradingModeCRUD:
    """
    KV-backed trading mode settings.
    Interface is identical to the old table-backed version.
    """

    NS = "trading_mode"
    VALID_MODES = {"Backtest", "Paper", "Live"}
    BOOL_FIELDS = {"allow_live_trading", "confirm_live_trades", "simulate_slippage", "simulate_delay"}
    DEFAULTS = {
        "mode": "Paper",
        "paper_balance": 100000.0,
        "allow_live_trading": False,
        "confirm_live_trades": True,
        "simulate_slippage": True,
        "slippage_percent": 0.05,
        "simulate_delay": True,
        "delay_ms": 500,
    }

    def get(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        db = db or get_db()
        data = _kv_get_ns(self.NS, self.DEFAULTS, db)
        for bf in self.BOOL_FIELDS:
            if bf in data:
                data[bf] = bool(data[bf])
        return data

    def save(self, data: Dict[str, Any], db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        merged = {**self.DEFAULTS, **data}
        _raw_mode = str(merged.get("mode", "Paper"))
        mode = _raw_mode.strip().title()
        if mode not in self.VALID_MODES:
            logger.warning(f"[TradingModeCRUD.save] Invalid mode {_raw_mode!r}, defaulting to Paper")
            mode = "Paper"
        normalised = {
            "mode": mode,
            "paper_balance": float(merged["paper_balance"]),
            "allow_live_trading": bool(merged["allow_live_trading"]),
            "confirm_live_trades": bool(merged["confirm_live_trades"]),
            "simulate_slippage": bool(merged["simulate_slippage"]),
            "slippage_percent": float(merged["slippage_percent"]),
            "simulate_delay": bool(merged["simulate_delay"]),
            "delay_ms": int(merged["delay_ms"]),
        }
        return _kv_set_ns(self.NS, normalised, db)

    def set_mode(self, mode: str, db: DatabaseConnector = None) -> bool:
        current = self.get(db)
        current["mode"] = mode
        return self.save(current, db)

    def update_field(self, field: str, value: Any, db: DatabaseConnector = None) -> bool:
        if field not in self.DEFAULTS:
            logger.warning(f"[TradingModeCRUD.update_field] Unknown field: {field}")
            return False
        current = self.get(db)
        current[field] = value
        return self.save(current, db)

    def reset(self, db: DatabaseConnector = None) -> bool:
        return self.save(self.DEFAULTS, db)


trading_mode = TradingModeCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 5. Strategies  (own table — unchanged, except active-slug uses app_kv)
# ══════════════════════════════════════════════════════════════════════════════

class StrategiesCRUD:
    """
    Strategies stay in their own table for relational integrity.
    The active-strategy pointer is moved to app_kv (key: strategy:active_slug)
    instead of the former strategy_active singleton table.
    """

    _ACTIVE_KEY = "strategy:active_slug"

    def list_all(self, db: DatabaseConnector = None) -> List[Dict[str, Any]]:
        db = db or get_db()
        rows = db.fetchall(
            "SELECT slug, name, description, created_at, updated_at FROM strategies ORDER BY name"
        )
        return [_row_to_dict(r) for r in rows]

    def get(self, slug: str, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        db = db or get_db()
        row = db.fetchone("SELECT * FROM strategies WHERE slug = ?", (slug,))
        if row is None:
            return None
        d = _row_to_dict(row)
        try:
            d["indicators"] = json.loads(d.get("indicators") or "{}")
        except json.JSONDecodeError:
            d["indicators"] = {}
        try:
            d["engine"] = json.loads(d.get("engine") or "{}")
        except json.JSONDecodeError:
            d["engine"] = {}
        return d

    def create(self, slug: str, name: str, description: str = "",
               indicators: Dict = None, engine: Dict = None,
               db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        if self.exists(slug, db):
            logger.warning(f"[StrategiesCRUD.create] slug already exists: {slug}")
            return False
        now = _NOW()
        try:
            db.execute(
                "INSERT INTO strategies (slug, name, description, indicators, engine, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (slug, name, description, json.dumps(indicators or {}), json.dumps(engine or {}), now, now),
            )
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.create] {e}", exc_info=True)
            return False

    def upsert(self, slug: str, name: str, description: str = "",
               indicators: Dict = None, engine: Dict = None,
               db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        now = _NOW()
        try:
            db.execute(
                "INSERT INTO strategies (slug, name, description, indicators, engine, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(slug) DO UPDATE SET name=excluded.name, description=excluded.description, "
                "indicators=excluded.indicators, engine=excluded.engine, updated_at=excluded.updated_at",
                (slug, name, description, json.dumps(indicators or {}), json.dumps(engine or {}), now, now),
            )
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.upsert] {e}", exc_info=True)
            return False

    def update_indicators(self, slug: str, indicators: Dict, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            db.execute("UPDATE strategies SET indicators=?, updated_at=? WHERE slug=?",
                       (json.dumps(indicators), _NOW(), slug))
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.update_indicators] {e}", exc_info=True)
            return False

    def update_engine(self, slug: str, engine: Dict, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            db.execute("UPDATE strategies SET engine=?, updated_at=? WHERE slug=?",
                       (json.dumps(engine), _NOW(), slug))
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.update_engine] {e}", exc_info=True)
            return False

    def rename(self, slug: str, new_name: str, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            db.execute("UPDATE strategies SET name=?, updated_at=? WHERE slug=?",
                       (new_name, _NOW(), slug))
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.rename] {e}", exc_info=True)
            return False

    def delete(self, slug: str, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            if self.get_active_slug(db) == slug:
                self.set_active(None, db)
            db.execute("DELETE FROM strategies WHERE slug=?", (slug,))
            return True
        except Exception as e:
            logger.error(f"[StrategiesCRUD.delete] {e}", exc_info=True)
            return False

    def exists(self, slug: str, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        row = db.fetchone("SELECT 1 FROM strategies WHERE slug=?", (slug,))
        return row is not None

    # ── Active pointer (now in app_kv) ────────────────────────────────────

    def get_active_slug(self, db: DatabaseConnector = None) -> Optional[str]:
        db = db or get_db()
        val = _kv_get(self._ACTIVE_KEY, None, db)
        return str(val) if val else None

    def get_active(self, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        slug = self.get_active_slug(db)
        return self.get(slug, db) if slug else None

    def set_active(self, slug: Optional[str], db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        if slug is not None and not self.exists(slug, db):
            logger.warning(f"[StrategiesCRUD.set_active] slug not found: {slug}")
            return False
        return _kv_set(self._ACTIVE_KEY, slug or "", db)


strategies = StrategiesCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 6. Broker Auth Tokens  → app_kv  (token:<field>)
# ══════════════════════════════════════════════════════════════════════════════

class TokenCRUD:
    """
    KV-backed broker authentication tokens.
    Interface is identical to the old table-backed version.
    """

    NS = "token"
    _DEFAULTS = {
        "access_token": "",
        "refresh_token": "",
        "issued_at": "",
        "expires_at": "",
    }

    def get(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        db = db or get_db()
        return _kv_get_ns(self.NS, self._DEFAULTS, db)

    def get_access_token(self, db: DatabaseConnector = None) -> str:
        return self.get(db).get("access_token", "")

    def save_token(self, access_token: str, refresh_token: str = "",
                   issued_at: str = None, expires_at: str = None,
                   db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        now = _NOW()
        data = {
            "access_token": access_token,
            "refresh_token": refresh_token or "",
            "issued_at": issued_at or now,
            "expires_at": expires_at or "",
        }
        return _kv_set_ns(self.NS, data, db)

    def clear(self, db: DatabaseConnector = None) -> bool:
        return self.save_token("", refresh_token="", db=db)


tokens = TokenCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 7. Trade Sessions  (own table — unchanged)
# ══════════════════════════════════════════════════════════════════════════════

class SessionCRUD:
    TABLE = "trade_sessions"

    def create(self, mode: str, exchange: str = None, derivative: str = None,
               lot_size: int = None, interval: str = None,
               strategy_slug: str = None, db: DatabaseConnector = None) -> int:
        db = db or get_db()
        try:
            cur = db.execute(
                f"INSERT INTO {self.TABLE} (mode, exchange, derivative, lot_size, interval, strategy_slug, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mode, exchange, derivative, lot_size, interval, strategy_slug, _NOW()),
            )
            return cur.lastrowid
        except Exception as e:
            logger.error(f"[SessionCRUD.create] {e}", exc_info=True)
            return -1

    def close(self, session_id: int, total_pnl: float = None, total_trades: int = None,
              winning_trades: int = None, losing_trades: int = None,
              notes: str = None, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            db.execute(
                f"UPDATE {self.TABLE} SET ended_at=?, total_pnl=?, total_trades=?, "
                "winning_trades=?, losing_trades=?, notes=? WHERE id=?",
                (_NOW(), total_pnl, total_trades, winning_trades, losing_trades, notes, session_id),
            )
            return True
        except Exception as e:
            logger.error(f"[SessionCRUD.close] {e}", exc_info=True)
            return False

    def get(self, session_id: int, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        db = db or get_db()
        row = db.fetchone(f"SELECT * FROM {self.TABLE} WHERE id=?", (session_id,))
        return _row_to_dict(row)

    def list_recent(self, limit: int = 50, db: DatabaseConnector = None) -> List[Dict[str, Any]]:
        db = db or get_db()
        rows = db.fetchall(f"SELECT * FROM {self.TABLE} ORDER BY started_at DESC LIMIT ?", (limit,))
        return [_row_to_dict(r) for r in rows]

    def delete(self, session_id: int, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            db.execute(f"DELETE FROM {self.TABLE} WHERE id=?", (session_id,))
            return True
        except Exception as e:
            logger.error(f"[SessionCRUD.delete] {e}", exc_info=True)
            return False


sessions = SessionCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 8. Orders  (own table — unchanged)
# ══════════════════════════════════════════════════════════════════════════════

class OrderCRUD:
    TABLE = "orders"

    def create(self, session_id: int, symbol: str, position_type: str,
               quantity: int, broker_order_id: str = None,
               entry_price: float = None, stop_loss: float = None,
               take_profit: float = None, db: DatabaseConnector = None) -> int:
        db = db or get_db()
        try:
            cur = db.execute(
                f"INSERT INTO {self.TABLE} "
                "(session_id, broker_order_id, symbol, position_type, quantity, "
                "entry_price, stop_loss, take_profit, status, entered_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)",
                (session_id, broker_order_id, symbol, position_type, quantity,
                 entry_price, stop_loss, take_profit, _NOW(), _NOW()),
            )
            return cur.lastrowid
        except Exception as e:
            logger.error(f"[OrderCRUD.create] {e}", exc_info=True)
            return -1

    def confirm(self, order_id: int, broker_order_id: str = None, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            db.execute(
                f"UPDATE {self.TABLE} SET is_confirmed=1, "
                "broker_order_id=COALESCE(?, broker_order_id), status='OPEN' WHERE id=?",
                (broker_order_id, order_id),
            )
            return True
        except Exception as e:
            logger.error(f"[OrderCRUD.confirm] {e}", exc_info=True)
            return False

    def close_order(self, order_id: int, exit_price: float, pnl: float,
                    reason: str = None, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            db.execute(
                f"UPDATE {self.TABLE} SET exit_price=?, pnl=?, reason_to_exit=?, "
                "status='CLOSED', exited_at=? WHERE id=?",
                (exit_price, pnl, reason, _NOW(), order_id),
            )
            return True
        except Exception as e:
            logger.error(f"[OrderCRUD.close_order] {e}", exc_info=True)
            return False

    def cancel(self, order_id: int, reason: str = None, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            db.execute(
                f"UPDATE {self.TABLE} SET status='CANCELLED', reason_to_exit=?, exited_at=? WHERE id=?",
                (reason, _NOW(), order_id),
            )
            return True
        except Exception as e:
            logger.error(f"[OrderCRUD.cancel] {e}", exc_info=True)
            return False

    def get(self, order_id: int, db: DatabaseConnector = None) -> Optional[Dict[str, Any]]:
        db = db or get_db()
        row = db.fetchone(f"SELECT * FROM {self.TABLE} WHERE id=?", (order_id,))
        return _row_to_dict(row)

    def list_for_session(self, session_id: int, db: DatabaseConnector = None) -> List[Dict[str, Any]]:
        db = db or get_db()
        rows = db.fetchall(f"SELECT * FROM {self.TABLE} WHERE session_id=? ORDER BY created_at", (session_id,))
        return [_row_to_dict(r) for r in rows]

    def list_open(self, session_id: int = None, db: DatabaseConnector = None) -> List[Dict[str, Any]]:
        db = db or get_db()
        if session_id is not None:
            rows = db.fetchall(f"SELECT * FROM {self.TABLE} WHERE session_id=? AND status='OPEN'", (session_id,))
        else:
            rows = db.fetchall(f"SELECT * FROM {self.TABLE} WHERE status='OPEN'")
        return [_row_to_dict(r) for r in rows]

    def get_by_period(self, period: str = "today", db: DatabaseConnector = None) -> List[Dict[str, Any]]:
        db = db or get_db()
        try:
            if period == "today":
                rows = db.fetchall(
                    f"SELECT * FROM {self.TABLE} WHERE status='CLOSED' "
                    "AND DATE(exited_at)=DATE('now','localtime') ORDER BY exited_at DESC"
                )
            elif period == "this_week":
                rows = db.fetchall(
                    f"SELECT * FROM {self.TABLE} WHERE status='CLOSED' "
                    "AND exited_at>=DATE('now','localtime','-7 days') ORDER BY exited_at DESC"
                )
            else:
                rows = db.fetchall(
                    f"SELECT * FROM {self.TABLE} WHERE status='CLOSED' ORDER BY exited_at DESC"
                )
            return [_row_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[OrderCRUD.get_by_period] {e}", exc_info=True)
            return []

    def update_stop_loss(self, order_id: int, stop_loss: float, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            db.execute(f"UPDATE {self.TABLE} SET stop_loss=? WHERE id=?", (stop_loss, order_id))
            return True
        except Exception as e:
            logger.error(f"[OrderCRUD.update_stop_loss] {e}", exc_info=True)
            return False


orders = OrderCRUD()


# ══════════════════════════════════════════════════════════════════════════════
# 9. Generic Key-Value Store  (app_kv table — unchanged)
# ══════════════════════════════════════════════════════════════════════════════

class KVCRUD:
    TABLE = "app_kv"

    def get(self, key: str, default: Any = None, db: DatabaseConnector = None) -> Any:
        db = db or get_db()
        return _kv_get(key, default, db)

    def set(self, key: str, value: Any, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        return _kv_set(key, value, db)

    def delete(self, key: str, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            db.execute(f"DELETE FROM {self.TABLE} WHERE key=?", (key,))
            return True
        except Exception as e:
            logger.error(f"[KVCRUD.delete] key={key!r}: {e}", exc_info=True)
            return False

    def all(self, db: DatabaseConnector = None) -> Dict[str, Any]:
        db = db or get_db()
        rows = db.fetchall(f"SELECT key, value FROM {self.TABLE}")
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                result[r["key"]] = r["value"]
        return result

    # alias used by config_crud
    get_all = all

    def update_many(self, data: Dict[str, Any], db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        now = _NOW()
        try:
            with db.connection() as conn:
                for key, value in data.items():
                    serialised = json.dumps(value) if not isinstance(value, str) else value
                    conn.execute(
                        f"INSERT INTO {self.TABLE} (key, value, updated_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                        (key, serialised, now),
                    )
            return True
        except Exception as e:
            logger.error(f"[KVCRUD.update_many] {e}", exc_info=True)
            return False

    def clear(self, db: DatabaseConnector = None) -> bool:
        db = db or get_db()
        try:
            db.execute(f"DELETE FROM {self.TABLE}")
            return True
        except Exception as e:
            logger.error(f"[KVCRUD.clear] {e}", exc_info=True)
            return False


kv = KVCRUD()
