"""
Trade State Manager Module
==========================
Manages the TradeState singleton with thread-safe access and convenience methods
for different parts of the application.

FIXED: Eliminated lock-order inversion - never hold manager lock when calling state methods.
"""

import threading
import logging
from typing import Optional, Dict, Any, List

from Utils.safe_getattr import safe_setattr, safe_hasattr
from data.trade_state import TradeState

logger = logging.getLogger(__name__)


class TradeStateManager:
    """
    Manages the trade state singleton with thread-safe access and
    snapshot capabilities for different parts of the application.

    CRITICAL: This manager NEVER holds its own lock when calling state methods
    to prevent lock-order inversion deadlocks.
    """

    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        """Thread-safe singleton instantiation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._state = TradeState.get_instance()
                    cls._instance._initialized = True
        return cls._instance

    def get_state(self) -> TradeState:
        """
        Get the trade state instance.

        Returns:
            TradeState: The singleton trade state instance
        """
        return self._state

    def get_snapshot(self) -> Dict[str, Any]:
        """
        Get a snapshot of current state (thread-safe).

        Returns:
            Dict[str, Any]: Complete state snapshot
        """
        return self._state.get_snapshot()

    def get_position_snapshot(self) -> Dict[str, Any]:
        """
        Get a snapshot of position-related state (thread-safe).

        Returns:
            Dict[str, Any]: Position snapshot
        """
        return self._state.get_position_snapshot()

    def update_from_backtest(self, backtest_state: Dict[str, Any]) -> None:
        """
        Update the state from backtest results.

        IMPORTANT: This method does NOT hold the manager lock when calling
        state.update_from_dict() to avoid lock-order inversion.

        Args:
            backtest_state: Dictionary of state updates from backtest
        """
        if not backtest_state:
            logger.debug("[TradeStateManager] No backtest state to update")
            return

        # Get a local reference (safe even without lock)
        state = self._state

        # Call state method WITHOUT holding manager lock
        try:
            state.update_from_dict(backtest_state)
            logger.debug(f"[TradeStateManager] Updated state from backtest with {len(backtest_state)} fields")
        except Exception as e:
            logger.error(f"[TradeStateManager] Failed to update from backtest: {e}", exc_info=True)

    def reset_for_backtest(self) -> None:
        """Reset the state for a new backtest run."""
        # reset_trade_attributes() is internally thread-safe.
        self._state.reset_trade_attributes(None)
        logger.debug("[TradeStateManager] Reset state for backtest")

    def save_state(self) -> Dict[str, Any]:
        """
        Save current state (useful for restoring after backtest).

        Returns:
            Dict[str, Any]: Serializable state snapshot
        """
        return self.get_snapshot()

    def restore_state(self, saved_state: Dict[str, Any]) -> None:
        """
        Restore a previously saved state.

        Args:
            saved_state: State snapshot to restore
        """
        if not saved_state:
            logger.warning("[TradeStateManager] No saved state to restore")
            return

        # Call state method WITHOUT holding manager lock
        try:
            self._state.update_from_dict(saved_state)
            logger.debug(f"[TradeStateManager] Restored state with {len(saved_state)} fields")
        except Exception as e:
            logger.error(f"[TradeStateManager] Failed to restore state: {e}", exc_info=True)

    def clear_state(self) -> None:
        """Clear all state (use with caution)."""
        self._state.cleanup()  # cleanup() is internally thread-safe
        logger.debug("[TradeStateManager] State cleared")

    def get_value(self, key: str, default: Any = None) -> Any:
        """
        Get a specific value from state by key.

        Args:
            key: Attribute name to retrieve
            default: Default value if attribute doesn't exist

        Returns:
            Any: Attribute value or default
        """
        try:
            snapshot = self.get_snapshot()
            return snapshot.get(key, default)
        except Exception as e:
            logger.error(f"[TradeStateManager] Failed to get {key}: {e}", exc_info=True)
            return default

    def set_value(self, key: str, value: Any) -> bool:
        """
        Set a specific value in state by key.

        Does NOT hold manager lock to avoid inversion.

        Args:
            key: Attribute name to set
            value: Value to set

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if safe_hasattr(self._state, key):
                safe_setattr(self._state, key, value)
                return True
            return False
        except Exception as e:
            logger.error(f"[TradeStateManager] Failed to set {key}: {e}", exc_info=True)
            return False


# Global instance for easy import
state_manager = TradeStateManager()