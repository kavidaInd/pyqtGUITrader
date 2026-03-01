"""
Trade State Manager Module
==========================
Manages the TradeState singleton with thread-safe access and convenience methods
for different parts of the application.

This module provides a centralized manager for the TradeState singleton, making
it easy to access and update state from anywhere in the application, including
the backtest engine.

Usage:
    from models.trade_state_manager import state_manager

    # Get the current state
    state = state_manager.get_state()

    # Get a thread-safe snapshot
    snapshot = state_manager.get_snapshot()

    # Update from backtest
    state_manager.update_from_backtest(backtest_state)

    # Reset for clean backtest
    state_manager.reset_for_backtest()
"""

import threading
import logging
from typing import Optional, Dict, Any, List
from models.trade_state import TradeState

logger = logging.getLogger(__name__)


class TradeStateManager:
    """
    Manages the trade state singleton with thread-safe access and
    snapshot capabilities for different parts of the application.

    This manager provides:
    - Thread-safe access to the singleton TradeState
    - Snapshot creation and restoration
    - Safe state updates that handle computed properties
    - Backtest-specific operations (reset, restore)
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
        This allows the backtest engine to modify the singleton state.

        Args:
            backtest_state: Dictionary of state updates from backtest
        """
        if not backtest_state:
            logger.debug("[TradeStateManager] No backtest state to update")
            return

        with self._lock:
            try:
                # Use the update_from_dict method that handles computed properties
                self._state.update_from_dict(backtest_state)
                logger.debug(f"[TradeStateManager] Updated state from backtest with {len(backtest_state)} fields")
            except Exception as e:
                logger.error(f"[TradeStateManager] Failed to update from backtest: {e}", exc_info=True)

    def reset_for_backtest(self) -> None:
        """Reset the state for a new backtest run."""
        with self._lock:
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

        This method safely restores state by:
        1. Validating the input
        2. Using update_from_dict to handle computed properties
        3. Logging the operation for debugging

        Args:
            saved_state: State snapshot to restore
        """
        if not saved_state:
            logger.warning("[TradeStateManager] No saved state to restore")
            return

        with self._lock:
            try:
                # Use update_from_dict that handles computed properties
                self._state.update_from_dict(saved_state)
                logger.debug(f"[TradeStateManager] Restored state with {len(saved_state)} fields")
            except Exception as e:
                logger.error(f"[TradeStateManager] Failed to restore state: {e}", exc_info=True)

    def clear_state(self) -> None:
        """Clear all state (use with caution)."""
        with self._lock:
            self._state.cleanup()
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

        Note: This bypasses the update_from_dict method and may not handle
        computed properties correctly. Prefer restore_state for batch updates.

        Args:
            key: Attribute name to set
            value: Value to set

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with self._lock:
                if hasattr(self._state, key):
                    setattr(self._state, key, value)
                    return True
                return False
        except Exception as e:
            logger.error(f"[TradeStateManager] Failed to set {key}: {e}", exc_info=True)
            return False


# Global instance for easy import
state_manager = TradeStateManager()