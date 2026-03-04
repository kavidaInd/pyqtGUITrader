"""
risk_manager.py
===============
Risk Manager for the Algo Trading Dashboard.

FEATURE 1: Implements daily loss limits and trade count limits.
UPDATED: Now uses state_manager for state access.

BUG FIXES
---------
Bug #3 (HIGH) — should_allow_trade: risk limits read from state, not config
    max_trades and max_loss were read from the state snapshot using keys
    'max_trades_per_day' and 'max_daily_loss'. Those are not standard trade
    state fields — they live in the config object that is explicitly passed
    as a parameter. When absent from state the code silently fell back to
    hardcoded defaults (10 trades, ₹-5000) regardless of what the user
    configured.
    Fix: read both limits directly from the config parameter via
    _get_config_value(), consistent with how get_risk_summary() already
    worked when config was not None.

Bug #4 (HIGH) — get_risk_summary: config treated as dict, not object
    get_risk_summary called config.get('max_daily_loss') assuming a plain
    dict, while should_allow_trade received a config that could be a
    dataclass or custom object. Passing the same config to both would crash
    get_risk_summary with AttributeError.
    Fix: introduced _get_config_value(config, key, default) that tries
    getattr first (object/dataclass) then falls back to dict.get so both
    methods use the same accessor regardless of config type.

Bug #1 (MEDIUM) — _count_trades_today / _get_pnl_today: cache read outside lock
    Cache reads happened outside self._lock while writes were protected.
    Two threads could simultaneously pass the TTL check and both hit the DB.
    Fix: entire check-query-write sequence is now inside the lock.

Bug #6 (LOW) — cache TTL: negative timedelta on clock skew
    If the system clock moved backward (DST, NTP sync) the timedelta was
    negative, always < TTL, making the cache immortal for that session.
    Fix: use abs() on the elapsed seconds before comparing to TTL.

Bug #5 (LOW) — should_allow_trade: risk_breach not emitted for market-closed
    risk_breach signal was emitted for trade-count and daily-loss blocks but
    not for the market-closed check, leaving the GUI unaware of that block.
    Fix: emit risk_breach for market-closed too.

Bug #2 (LOW) — _count_trades_today: dead today_str variable
    today_str = date.today().isoformat() was computed but never used; the SQL
    uses DATE('now', 'localtime') directly.
    Fix: removed the dead assignment.

Bug #7 (MEDIUM) — raw SQL bypasses orders_crud, risks connection leak
    Both DB methods used raw db.execute() strings instead of orders_crud
    helpers, bypassing the established data-access pattern and potentially
    leaking connections if get_db() creates a new connection per call.
    Fix: extracted the two queries into private helpers that mirror the
    orders_crud pattern. If orders_crud grows count_closed_today() and
    sum_pnl_today() they can be swapped in as one-liners.

Note (Bug #8 — INFO): should_allow_trade snapshot-then-query race
    The position snapshot is taken at method entry but DB queries run after.
    This is safe in practice because buy_option holds _order_lock while
    calling should_allow_trade, serialising concurrent entry attempts.
    No code change required.
"""

import logging
import threading
from datetime import datetime, date
from typing import Tuple, Dict, Any, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from db.connector import get_db
from db.crud import orders as orders_crud

from data.trade_state_manager import state_manager

logger = logging.getLogger(__name__)


class RiskManager(QObject):
    """
    FEATURE 1: Risk Manager with daily loss and trade count limits.

    Signals:
        risk_breach: Emitted when any risk limit is breached (reason string).
    """

    risk_breach = pyqtSignal(str)

    def __init__(self):
        """Initialise Risk Manager with safe defaults."""
        super().__init__()
        self._lock = threading.RLock()

        # Cache for trades count
        self._cache_trades_today: int = -1
        self._cache_trades_timestamp: Optional[datetime] = None

        # Cache for daily P&L (independent timestamp — Bug #1 fix)
        self._cache_pnl_today: Optional[float] = None
        self._cache_pnl_timestamp: Optional[datetime] = None

        self._cache_ttl_seconds: int = 5

        logger.info("RiskManager initialised with state_manager integration")

    # ── Config accessor ────────────────────────────────────────────────────────

    @staticmethod
    def _get_config_value(config, key: str, default):
        """
        Read *key* from *config* regardless of whether it is a plain dict,
        a dataclass, or any other object.

        Bug #4 fix: get_risk_summary used config.get() (dict API) while
        should_allow_trade received an object — using the same accessor in
        both methods prevents an AttributeError when config is not a dict.
        """
        if config is None:
            return default
        # dict / dict-like (has .get)
        if isinstance(config, dict):
            return config.get(key, default)
        # dataclass / object / namedtuple
        return getattr(config, key, default)

    # ── Public API ─────────────────────────────────────────────────────────────

    def should_allow_trade(self, config) -> Tuple[bool, str]:
        """
        Return (True, '') if a new trade is permitted, or (False, reason) if
        any risk limit would be breached.

        Checks in priority order:
          1. Position already open
          2. Order already pending
          3. Market closed
          4. Max trades per day reached
          5. Daily loss limit reached

        Bug #3 fix: limits are now read from *config* (the explicit parameter)
        instead of the state snapshot, so user-configured values are always used.
        """
        try:
            if config is None:
                logger.error("should_allow_trade called with None config")
                return False, "Internal error: Config is None"

            position_snapshot = state_manager.get_position_snapshot()

            # 1. Position already open
            current_pos = position_snapshot.get("current_position")
            if current_pos is not None:
                return False, f"Position already open: {current_pos}"

            # 2. Order already pending
            if position_snapshot.get("order_pending", False):
                return False, "Order already pending"

            # 3. Market closed
            from Utils.Utils import Utils
            if not Utils.is_market_open():
                reason = "Market is closed"
                self.risk_breach.emit(reason)   # Bug #5 fix: emit for market-closed too
                return False, reason

            # 4. Max trades per day — read from config, not state (Bug #3 fix)
            max_trades   = self._get_config_value(config, "max_trades_per_day", 10)
            trades_today = self._count_trades_today()
            if trades_today >= max_trades:
                reason = f"Max trades/day reached ({trades_today}/{max_trades})"
                self.risk_breach.emit(reason)
                return False, reason

            # 5. Daily loss limit — read from config, not state (Bug #3 fix)
            max_loss   = self._get_config_value(config, "max_daily_loss", -5000)
            pnl_today  = self._get_pnl_today()
            if pnl_today <= max_loss:
                reason = f"Daily loss limit hit (₹{pnl_today:.2f} ≤ ₹{max_loss:.2f})"
                self.risk_breach.emit(reason)
                return False, reason

            return True, ""

        except Exception as e:
            logger.error(f"[RiskManager.should_allow_trade] Failed: {e}", exc_info=True)
            return False, f"Risk check error: {e}"

    def get_risk_summary(self, config=None) -> Dict[str, Any]:
        """
        Return a risk summary dict for GUI display.

        Bug #4 fix: config is accessed via _get_config_value() which handles
        both dict and object/dataclass without crashing.
        """
        try:
            trades_today = self._count_trades_today()
            pnl_today    = self._get_pnl_today()

            if config is not None:
                max_loss   = self._get_config_value(config, "max_daily_loss",    -5000)
                max_trades = self._get_config_value(config, "max_trades_per_day", 10)
            else:
                snapshot   = state_manager.get_snapshot()
                max_loss   = snapshot.get("max_daily_loss",    -5000)
                max_trades = snapshot.get("max_trades_per_day", 10)

            blocked      = False
            block_reason = ""

            if pnl_today <= max_loss:
                blocked      = True
                block_reason = f"Daily loss limit hit (₹{pnl_today:.2f} ≤ ₹{max_loss:.2f})"
            elif trades_today >= max_trades:
                blocked      = True
                block_reason = f"Max trades/day reached ({trades_today}/{max_trades})"

            # loss_remaining = how much more loss is permitted (positive = headroom)
            # e.g. pnl=-3000, max_loss=-5000 → -3000 - (-5000) = +2000 headroom
            loss_remaining   = pnl_today - max_loss
            trades_remaining = max(0, max_trades - trades_today)

            return {
                "trades_today":         trades_today,
                "pnl_today":            pnl_today,
                "max_loss_remaining":   loss_remaining,
                "max_trades_remaining": trades_remaining,
                "is_blocked":           blocked,
                "block_reason":         block_reason,
                "max_loss":             max_loss,
                "max_trades":           max_trades,
            }

        except Exception as e:
            logger.error(f"[RiskManager.get_risk_summary] Failed: {e}", exc_info=True)
            return {
                "trades_today":         0,
                "pnl_today":            0.0,
                "max_loss_remaining":   0.0,
                "max_trades_remaining": 0,
                "is_blocked":           False,
                "block_reason":         "",
                "max_loss":             -5000,
                "max_trades":           10,
            }

    def invalidate_cache(self) -> None:
        """Force the next DB query to bypass the cache (called after every exit)."""
        try:
            with self._lock:
                self._cache_trades_timestamp = None
                self._cache_pnl_timestamp    = None
                self._cache_trades_today     = -1
                self._cache_pnl_today        = None
            logger.debug("RiskManager cache invalidated")
        except Exception as e:
            logger.error(f"[RiskManager.invalidate_cache] Failed: {e}", exc_info=True)

    def cleanup(self) -> None:
        """Release resources before shutdown."""
        try:
            logger.info("[RiskManager] Starting cleanup")
            self.invalidate_cache()
            logger.info("[RiskManager] Cleanup completed")
        except Exception as e:
            logger.error(f"[RiskManager.cleanup] Error: {e}", exc_info=True)

    # ── Private DB helpers ─────────────────────────────────────────────────────

    def _count_trades_today(self) -> int:
        """
        Return the number of orders closed today, with a 5-second cache.

        Bug #1 fix: the entire check-query-write sequence runs inside the lock
        so two threads cannot both pass the TTL check and double-hit the DB.

        Bug #2 fix: removed the unused today_str dead variable.

        Bug #6 fix: abs() guards against negative timedelta on clock skew.
        """
        with self._lock:
            now = datetime.now()
            if (self._cache_trades_timestamp is not None
                    and abs((now - self._cache_trades_timestamp).total_seconds())
                    < self._cache_ttl_seconds
                    and self._cache_trades_today >= 0):
                return self._cache_trades_today

            count = self._query_count_closed_today()
            self._cache_trades_today     = count
            self._cache_trades_timestamp = now
            logger.debug(f"Trades today (DB): {count}")
            return count

    def _get_pnl_today(self) -> float:
        """
        Return total closed P&L for today, with a 5-second cache.

        Bug #1 fix: full check-query-write under the lock.
        Bug #6 fix: abs() guard on timedelta.
        """
        with self._lock:
            now = datetime.now()
            if (self._cache_pnl_timestamp is not None
                    and abs((now - self._cache_pnl_timestamp).total_seconds())
                    < self._cache_ttl_seconds
                    and self._cache_pnl_today is not None):
                return self._cache_pnl_today

            pnl = self._query_pnl_today()
            self._cache_pnl_today     = pnl
            self._cache_pnl_timestamp = now
            logger.debug(f"P&L today (DB): ₹{pnl:.2f}")
            return pnl

    # ── Raw DB queries (Bug #7 fix: isolated here, mirroring orders_crud style)

    @staticmethod
    def _query_count_closed_today() -> int:
        """
        Count orders with status='CLOSED' and exited_at = today (local time).

        Bug #7 fix: raw SQL is isolated in one place. When orders_crud grows a
        count_closed_today() helper this method becomes a one-line delegate.
        """
        try:
            db = get_db()
            query = """
                SELECT COUNT(*)
                FROM orders
                WHERE DATE(exited_at, 'localtime') = DATE('now', 'localtime')
                  AND status = 'CLOSED'
            """
            result = db.execute(query).fetchone()
            return int(result[0]) if result else 0
        except Exception as e:
            logger.error(f"[RiskManager._query_count_closed_today] {e}", exc_info=True)
            return 0

    @staticmethod
    def _query_pnl_today() -> float:
        """
        Sum pnl for orders with status='CLOSED' and exited_at = today (local time).

        Bug #7 fix: raw SQL isolated here; easy to replace with an orders_crud call.
        """
        try:
            db = get_db()
            query = """
                SELECT COALESCE(SUM(pnl), 0.0)
                FROM orders
                WHERE DATE(exited_at, 'localtime') = DATE('now', 'localtime')
                  AND status = 'CLOSED'
            """
            result = db.execute(query).fetchone()
            return float(result[0]) if result and result[0] is not None else 0.0
        except Exception as e:
            logger.error(f"[RiskManager._query_pnl_today] {e}", exc_info=True)
            return 0.0