"""
db — SQLite persistence layer for the trading app.

Quick start:
    from db import brokerage, daily_trade, profit_stoploss, trading_mode
    from db import strategies, tokens, sessions, orders, kv

    # Read settings
    creds  = brokerage.get()
    ts     = daily_trade.get()
    ps     = profit_stoploss.get()
    mode   = trading_mode.get()

    # Write settings
    brokerage.save({"client_id": "...", "secret_key": "...", "redirect_uri": "..."})
    daily_trade.save({"lot_size": 75, "exchange": "NSE"})

    # Strategies
    strategies.upsert("my-strat", "My Strategy", indicators={...}, engine={...})
    strategies.set_active("my-strat")

    # Trade lifecycle
    sid = sessions.create("SIM", exchange="NSE", derivative="NIFTY50")
    oid = orders.create(sid, "NIFTY50_CE", "BUY_CALL", 75, entry_price=150.0)
    orders.confirm(oid, broker_order_id="B001")
    orders.close_order(oid, exit_price=170.0, pnl=1500.0, reason="TP hit")
    sessions.close(sid, total_pnl=1500.0, total_trades=1, winning_trades=1)

Migration (run once):
    python -m db.migrate
"""

from db.crud import (
    brokerage,
    daily_trade,
    profit_stoploss,
    trading_mode,
    strategies,
    tokens,
    sessions,
    orders,
    kv,
)
from db.connector import get_db, reset_db

__all__ = [
    "brokerage",
    "daily_trade",
    "profit_stoploss",
    "trading_mode",
    "strategies",
    "tokens",
    "sessions",
    "orders",
    "kv",
    "get_db",
    "reset_db",
]