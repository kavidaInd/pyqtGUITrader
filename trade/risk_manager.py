"""
risk_manager.py
===============
Risk Manager for the Algo Trading Dashboard.

FEATURE 1: Implements daily loss limits and trade count limits.
UPDATED: Now uses state_manager for state access.
"""

import logging
import threading
from datetime import datetime, date
from typing import Tuple, Dict, Any, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from db.connector import get_db
from db.crud import orders as orders_crud

# Import state manager for state access
from data.trade_state_manager import state_manager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class RiskManager(QObject):
    """
    FEATURE 1: Risk Manager with daily loss and trade count limits.

    Signals:
        risk_breach: Emitted when any risk limit is hit (reason string)
    """

    # Rule 3: Qt signals
    risk_breach = pyqtSignal(str)

    def __init__(self):
        """Initialize Risk Manager with safe defaults."""
        # Rule 2: Safe defaults
        super().__init__()
        self._lock = threading.RLock()
        self._cache_trades_today = -1
        self._cache_pnl_today = None
        # BUG FIX: Use two independent timestamps so that a fresh query for one
        # value does not accidentally mark the other value as "recently cached".
        # Previously a single _cache_timestamp was shared, meaning whichever
        # method ran first would stamp it and the second would return its stale
        # value without hitting the DB.
        self._cache_trades_timestamp = None
        self._cache_pnl_timestamp = None
        self._cache_ttl_seconds = 5  # Cache for 5 seconds

        logger.info("RiskManager initialized with state_manager integration")

    def should_allow_trade(self, config) -> Tuple[bool, str]:
        """
        Check if a new trade should be allowed based on risk limits.

        Args:
            config: Config object with risk settings

        Returns:
            Tuple[bool, str]: (allowed, reason_string)
            - True, '' if allowed
            - False, 'reason' if blocked
        """
        try:
            # Rule 6: Input validation
            if config is None:
                logger.error("should_allow_trade called with None config")
                return False, "Internal error: Config is None"

            # Get state snapshot for position check
            position_snapshot = state_manager.get_position_snapshot()
            full_snapshot = state_manager.get_snapshot()

            # Check in order of importance

            # 1. Position already open
            if position_snapshot.get('current_position') is not None:
                return False, f"Position already open: {position_snapshot.get('current_position')}"

            # 2. Order already pending
            if position_snapshot.get('order_pending', False):
                return False, "Order already pending"

            # 3. Market is closed
            from Utils.Utils import Utils
            if not Utils.is_market_open():
                return False, "Market is closed"

            # 4. Max trades per day
            max_trades = full_snapshot.get('max_trades_per_day', 10)
            trades_today = self._count_trades_today()
            if trades_today >= max_trades:
                self.risk_breach.emit(f"Max trades/day reached ({trades_today}/{max_trades})")
                return False, f"Max trades/day reached ({trades_today}/{max_trades})"

            # 5. Max daily loss
            max_loss = full_snapshot.get('max_daily_loss', -5000)
            pnl_today = self._get_pnl_today()
            if pnl_today <= max_loss:
                self.risk_breach.emit(f"Daily loss limit hit (₹{pnl_today:.2f} ≤ ₹{max_loss:.2f})")
                return False, f"Daily loss limit hit (₹{pnl_today:.2f} ≤ ₹{max_loss:.2f})"

            return True, ""

        except Exception as e:
            logger.error(f"[RiskManager.should_allow_trade] Failed: {e}", exc_info=True)
            return False, f"Risk check error: {e}"

    def _count_trades_today(self) -> int:
        """
        Count number of closed trades today.

        Returns:
            int: Number of trades closed today
        """
        try:
            # BUG FIX: Use the trades-specific timestamp (not a shared one) and
            # compare with .total_seconds() — .seconds only returns the 0-59
            # component of the timedelta, so a cache older than 60 s would
            # wrongly appear fresh when .seconds wraps back to a small value.
            now = datetime.now()
            if (self._cache_trades_timestamp and
                    (now - self._cache_trades_timestamp).total_seconds() < self._cache_ttl_seconds and
                    self._cache_trades_today >= 0):
                return self._cache_trades_today

            # Query database
            db = get_db()
            today_str = date.today().isoformat()

            # This would need to be implemented in orders_crud
            # For now, we'll implement a simple query
            query = """
                SELECT COUNT(*) FROM orders 
                WHERE DATE(exited_at) = DATE('now', 'localtime')
                AND status = 'CLOSED'
            """

            cursor = db.execute(query)
            result = cursor.fetchone()
            count = result[0] if result else 0

            # Update cache with the trades-specific timestamp
            with self._lock:
                self._cache_trades_today = count
                self._cache_trades_timestamp = now

            logger.debug(f"Trades today: {count}")
            return count

        except Exception as e:
            logger.error(f"[RiskManager._count_trades_today] Failed: {e}", exc_info=True)
            return 0

    def _get_pnl_today(self) -> float:
        """
        Get total P&L for today.

        Returns:
            float: Total P&L for today (negative = loss)
        """
        try:
            # BUG FIX: Use the PnL-specific timestamp and .total_seconds() for the
            # same reasons as _count_trades_today above.
            now = datetime.now()
            if (self._cache_pnl_timestamp and
                    (now - self._cache_pnl_timestamp).total_seconds() < self._cache_ttl_seconds and
                    self._cache_pnl_today is not None):
                return self._cache_pnl_today

            # Query database
            db = get_db()

            # This would need to be implemented in orders_crud
            query = """
                SELECT COALESCE(SUM(pnl), 0.0) FROM orders 
                WHERE DATE(exited_at) = DATE('now', 'localtime')
                AND status = 'CLOSED'
            """

            cursor = db.execute(query)
            result = cursor.fetchone()
            pnl = float(result[0]) if result and result[0] is not None else 0.0

            # Update cache with the PnL-specific timestamp
            with self._lock:
                self._cache_pnl_today = pnl
                self._cache_pnl_timestamp = now

            logger.debug(f"P&L today: ₹{pnl:.2f}")
            return pnl

        except Exception as e:
            logger.error(f"[RiskManager._get_pnl_today] Failed: {e}", exc_info=True)
            return 0.0

    def get_risk_summary(self, config=None) -> Dict[str, Any]:
        """
        Get risk summary for GUI display.

        Args:
            config: Optional config object with risk settings (if None, uses state)

        Returns:
            Dict with risk summary
        """
        try:
            trades_today = self._count_trades_today()
            pnl_today = self._get_pnl_today()

            # Get limits from config or state
            if config is not None:
                max_loss = config.get('max_daily_loss', -5000)
                max_trades = config.get('max_trades_per_day', 10)
            else:
                # Fallback to state
                snapshot = state_manager.get_snapshot()
                max_loss = snapshot.get('max_daily_loss', -5000)
                max_trades = snapshot.get('max_trades_per_day', 10)

            # Check if blocked
            blocked = False
            block_reason = ""

            if pnl_today <= max_loss:
                blocked = True
                block_reason = f"Daily loss limit hit (₹{pnl_today:.2f} ≤ ₹{max_loss:.2f})"
            elif trades_today >= max_trades:
                blocked = True
                block_reason = f"Max trades/day reached ({trades_today}/{max_trades})"

            # BUG FIX: Express remaining loss headroom as a positive "room left"
            # value.  Previously:  max_loss - pnl_today  e.g. (-5000) - (-3000) = -2000
            # which is a confusing negative "remaining" amount.
            # Correct:  pnl_today - max_loss  e.g. (-3000) - (-5000) = +2000
            # meaning "you can lose ₹2000 more before hitting the limit".
            loss_remaining = pnl_today - max_loss
            trades_remaining = max(0, max_trades - trades_today)

            return {
                'trades_today': trades_today,
                'pnl_today': pnl_today,
                'max_loss_remaining': loss_remaining,
                'max_trades_remaining': trades_remaining,
                'is_blocked': blocked,
                'block_reason': block_reason,
                'max_loss': max_loss,
                'max_trades': max_trades,
            }

        except Exception as e:
            logger.error(f"[RiskManager.get_risk_summary] Failed: {e}", exc_info=True)
            return {
                'trades_today': 0,
                'pnl_today': 0.0,
                'max_loss_remaining': 0.0,
                'max_trades_remaining': 0,
                'is_blocked': False,
                'block_reason': "",
                'max_loss': -5000,
                'max_trades': 10,
            }

    def invalidate_cache(self):
        """Invalidate cached values (both trades count and PnL caches)."""
        try:
            with self._lock:
                self._cache_trades_timestamp = None
                self._cache_pnl_timestamp = None
                self._cache_trades_today = -1
                self._cache_pnl_today = None
            logger.debug("RiskManager cache invalidated")
        except Exception as e:
            logger.error(f"[RiskManager.invalidate_cache] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources."""
        try:
            logger.info("[RiskManager] Starting cleanup")
            self.invalidate_cache()
            logger.info("[RiskManager] Cleanup completed")
        except Exception as e:
            logger.error(f"[RiskManager.cleanup] Error: {e}", exc_info=True)