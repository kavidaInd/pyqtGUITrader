"""
risk_manager.py
===============
Risk Manager for the Algo Trading Dashboard.

FEATURE 1: Implements daily loss limits and trade count limits.
UPDATED: Now uses CRUD modules for all database access.
"""

import logging
import threading
from datetime import datetime, date
from typing import Tuple, Dict, Any, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from Utils.safe_getattr import safe_getattr
from db.crud import orders as orders_crud
from db.config_crud import config_crud
from data.trade_state_manager import state_manager

logger = logging.getLogger(__name__)


class RiskManager(QObject):
    """
    FEATURE 1: Risk Manager with daily loss and trade count limits.

    Risk limits are read from:
        1. TradeState (runtime values)
        2. ConfigCRUD (persisted configuration)

    Trade counts and P&L are read from OrderCRUD (database).

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

        # Cache for daily P&L
        self._cache_pnl_today: Optional[float] = None
        self._cache_pnl_timestamp: Optional[datetime] = None

        self._cache_ttl_seconds: int = 5

        logger.info("RiskManager initialised with CRUD integration")

    # ── Public API ─────────────────────────────────────────────────────────────

    def should_allow_trade(self) -> Tuple[bool, str]:
        """
        Return (True, '') if a new trade is permitted, or (False, reason) if
        any risk limit would be breached.

        Checks in priority order:
          1. Position already open
          2. Order already pending
          3. Market closed
          4. Max trades per day reached (from TradeState)
          5. Daily loss limit reached (from TradeState)

        Returns:
            Tuple[bool, str]: (allowed, reason_if_blocked)
        """
        try:
            position_snapshot = state_manager.get_position_snapshot()
            full_snapshot = state_manager.get_snapshot()  # For risk limits

            # 1. Position already open
            current_pos = position_snapshot.get("current_position")
            if current_pos is not None:
                return False, f"Position already open: {current_pos}"

            # 2. Order already pending
            if position_snapshot.get("order_pending", False):
                return False, "Order already pending"

            # 3. Market closed - use config_crud for market hours
            if not config_crud.is_market_open():
                reason = "Market is closed"
                self.risk_breach.emit(reason)
                return False, reason

            # 4. Max trades per day — read from TradeState
            max_trades = full_snapshot.get("max_trades_per_day", 10)
            trades_today = self._count_trades_today()
            if trades_today >= max_trades:
                reason = f"Max trades/day reached ({trades_today}/{max_trades})"
                self.risk_breach.emit(reason)
                return False, reason

            # 5. Daily loss limit — read from TradeState
            max_loss = full_snapshot.get("max_daily_loss", -5000.0)
            pnl_today = self._get_pnl_today()
            if pnl_today <= max_loss:
                reason = f"Daily loss limit hit (₹{pnl_today:.2f} ≤ ₹{max_loss:.2f})"
                self.risk_breach.emit(reason)
                return False, reason

            return True, ""

        except Exception as e:
            logger.error(f"[RiskManager.should_allow_trade] Failed: {e}", exc_info=True)
            return False, f"Risk check error: {e}"

    def get_risk_summary(self) -> Dict[str, Any]:
        """
        Return a risk summary dict for GUI display.

        All limits are read from:
            - TradeState (runtime values)
            - ConfigCRUD (persisted configuration as fallback)

        Returns:
            Dict[str, Any]: Risk summary with keys:
                - trades_today: Number of trades today
                - pnl_today: Current P&L for today
                - max_loss_remaining: How much more loss allowed
                - max_trades_remaining: How many more trades allowed
                - is_blocked: Whether trading is blocked
                - block_reason: Reason if blocked
                - max_loss: Maximum daily loss limit
                - max_trades: Maximum trades per day limit
                - daily_target: Daily profit target
        """
        try:
            trades_today = self._count_trades_today()
            pnl_today = self._get_pnl_today()

            # Read limits from TradeState first, fall back to config_crud
            snapshot = state_manager.get_snapshot()
            max_loss = snapshot.get("max_daily_loss", config_crud.get("max_daily_loss", -5000.0))
            max_trades = snapshot.get("max_trades_per_day", config_crud.get("max_trades_per_day", 10))
            daily_target = snapshot.get("daily_target", config_crud.get("daily_target", 5000.0))

            blocked = False
            block_reason = ""

            if pnl_today <= max_loss:
                blocked = True
                block_reason = f"Daily loss limit hit (₹{pnl_today:.2f} ≤ ₹{max_loss:.2f})"
            elif trades_today >= max_trades:
                blocked = True
                block_reason = f"Max trades/day reached ({trades_today}/{max_trades})"

            # loss_remaining = how much more loss is permitted (positive = headroom)
            # e.g. pnl=-3000, max_loss=-5000 → -3000 - (-5000) = +2000 headroom
            loss_remaining = pnl_today - max_loss
            trades_remaining = max(0, max_trades - trades_today)

            return {
                "trades_today": trades_today,
                "pnl_today": pnl_today,
                "max_loss_remaining": loss_remaining,
                "max_trades_remaining": trades_remaining,
                "is_blocked": blocked,
                "block_reason": block_reason,
                "max_loss": max_loss,
                "max_trades": max_trades,
                "daily_target": daily_target,
                "progress_to_target": (pnl_today / daily_target * 100) if daily_target > 0 else 0,
            }

        except Exception as e:
            logger.error(f"[RiskManager.get_risk_summary] Failed: {e}", exc_info=True)
            return {
                "trades_today": 0,
                "pnl_today": 0.0,
                "max_loss_remaining": 0.0,
                "max_trades_remaining": 0,
                "is_blocked": False,
                "block_reason": "",
                "max_loss": -5000.0,
                "max_trades": 10,
                "daily_target": 5000.0,
                "progress_to_target": 0.0,
            }

    def invalidate_cache(self) -> None:
        """Force the next DB query to bypass the cache (called after every exit)."""
        try:
            with self._lock:
                self._cache_trades_timestamp = None
                self._cache_pnl_timestamp = None
                self._cache_trades_today = -1
                self._cache_pnl_today = None
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

    # ── Private methods using CRUD ─────────────────────────────────────────────

    def _count_trades_today(self) -> int:
        """
        Return the number of orders closed today, with a 5-second cache.
        Uses OrderCRUD for database access.
        """
        with self._lock:
            now = datetime.now()
            if (self._cache_trades_timestamp is not None
                    and abs((now - self._cache_trades_timestamp).total_seconds())
                    < self._cache_ttl_seconds
                    and self._cache_trades_today >= 0):
                return self._cache_trades_today

            # Use OrderCRUD to get today's closed orders
            try:
                today_orders = orders_crud.get_by_period('today')
                count = len(today_orders)
            except Exception as e:
                logger.error(f"[RiskManager] Failed to get today's orders: {e}", exc_info=True)
                count = 0

            self._cache_trades_today = count
            self._cache_trades_timestamp = now
            logger.debug(f"Trades today (via OrderCRUD): {count}")
            return count

    def _get_pnl_today(self) -> float:
        """
        Return total closed P&L for today, with a 5-second cache.
        Uses OrderCRUD for database access.
        """
        with self._lock:
            now = datetime.now()
            if (self._cache_pnl_timestamp is not None
                    and abs((now - self._cache_pnl_timestamp).total_seconds())
                    < self._cache_ttl_seconds
                    and self._cache_pnl_today is not None):
                return self._cache_pnl_today

            # Use OrderCRUD to calculate today's P&L
            try:
                today_orders = orders_crud.get_by_period('today')
                pnl = sum(order.get('pnl', 0.0) for order in today_orders if order.get('pnl') is not None)
            except Exception as e:
                logger.error(f"[RiskManager] Failed to calculate today's P&L: {e}", exc_info=True)
                pnl = 0.0

            self._cache_pnl_today = pnl
            self._cache_pnl_timestamp = now
            logger.debug(f"P&L today (via OrderCRUD): ₹{pnl:.2f}")
            return pnl


# Singleton instance for global use
risk_manager = RiskManager()