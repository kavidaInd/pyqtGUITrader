# websocket_manager.py (fixed)
"""
websocket_manager.py
====================
Broker-agnostic WebSocket manager with improved reconnect logic and error handling.

FIXED: Added max retry limits, exponential backoff with jitter, and proper cleanup.
"""

import logging
import threading
import time
import socket
import requests
import random
from enum import Enum
from functools import wraps
from typing import Callable, List, Optional, Dict, Any

from broker.BaseBroker import BaseBroker

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSING = "closing"


class WebSocketManager:
    """
    Broker-agnostic WebSocket manager with improved reconnect logic.

    FIXED: Added max retry limits, exponential backoff with jitter, and proper cleanup.
    """

    def __init__(
            self,
            broker: BaseBroker,
            on_message_callback: Callable,
            symbols: Optional[List[str]] = None,
            max_retries: int = 5,
            retry_delay: int = 5,
            heartbeat_interval: int = 30,
            connection_timeout: int = 10,
    ):
        self._safe_defaults_init()
        try:
            if broker is None:
                logger.error("WebSocketManager: broker is required")
                return

            if not callable(on_message_callback):
                logger.error("WebSocketManager: on_message_callback must be callable")
                on_message_callback = self._dummy_callback

            self.broker = broker
            self.on_message_callback = self._wrap_callback(on_message_callback)
            self.symbols = symbols if symbols else []
            self.max_retries = max_retries
            self.retry_delay = retry_delay
            self.heartbeat_interval = heartbeat_interval
            self.connection_timeout = connection_timeout

            # Additional callbacks for state manager
            self.on_connected_callback = None
            self.on_disconnected_callback = None
            self.on_reconnected_callback = None

            self._max_reconnect_attempts = 10
            self._reconnect_attempts = 0
            self._base_delay = 1
            self._max_delay = 60

            self._stop_heartbeat = threading.Event()
            self._stop_network_monitor = threading.Event()
            self._stop_reconnect = threading.Event()

            logger.info(f"WebSocketManager initialized for {broker!r}")

        except Exception as e:
            logger.critical(f"[WebSocketManager.__init__] Failed: {e}", exc_info=True)
            self._safe_defaults_init()

    # ── Safe defaults ──────────────────────────────────────────────────────────

    def _safe_defaults_init(self):
        self.broker = None
        self.on_message_callback = self._dummy_callback
        self.symbols = []
        self.max_retries = 5
        self.retry_delay = 5
        self.heartbeat_interval = 30
        self.connection_timeout = 10

        self._state = ConnectionState.DISCONNECTED
        self._retries = 0
        self._manual_stop = False
        self._connection_lock = threading.RLock()

        self._max_reconnect_attempts = 10
        self._reconnect_attempts = 0
        self._base_delay = 1
        self._max_delay = 60

        self._stop_heartbeat = threading.Event()
        self._stop_network_monitor = threading.Event()
        self._stop_reconnect = threading.Event()

        # Additional callbacks
        self.on_connected_callback = None
        self.on_disconnected_callback = None
        self.on_reconnected_callback = None

        self._connect_thread = None
        self._heartbeat_thread = None
        self._network_monitor_thread = None
        self._reconnect_thread = None

        self._last_message_time = time.time()
        self._network_check_interval = 5

        self._ws_obj = None

        # Statistics
        self._message_count = 0
        self._error_count = 0
        self._reconnect_count = 0
        self._cleanup_done = False

        # Legacy callbacks
        self.on_disconnect_callback = None
        self.on_reconnect_callback = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_state_callbacks(self, on_connected=None, on_disconnected=None, on_reconnected=None):
        """
        Set callbacks for connection state changes.
        """
        with self._connection_lock:
            self.on_connected_callback = on_connected
            self.on_disconnected_callback = on_disconnected
            self.on_reconnected_callback = on_reconnected

    def connect(self):
        """Connect to the broker's WebSocket and start monitoring threads."""
        with self._connection_lock:
            try:
                if self._state in (ConnectionState.CONNECTING, ConnectionState.CONNECTED):
                    logger.info(f"Already {self._state.value}. Skipping.")
                    return

                self._manual_stop = False
                self._reconnect_attempts = 0
                self._stop_heartbeat.clear()
                self._stop_network_monitor.clear()
                self._stop_reconnect.clear()
                self._state = ConnectionState.CONNECTING

                for attempt in range(1, self.max_retries + 1):
                    if self._manual_stop:
                        break
                    try:
                        logger.info(f"Connecting to broker WebSocket (attempt {attempt})")

                        # Clean up any stale socket
                        if self._ws_obj is not None:
                            self._cleanup_socket()

                        if self.broker is None:
                            logger.error("WebSocketManager.connect: no broker set")
                            self._state = ConnectionState.DISCONNECTED
                            return

                        # Create the broker-native socket object
                        self._ws_obj = self.broker.create_websocket(
                            on_tick=self.on_message_callback,
                            on_connect=self._on_connect,
                            on_close=self._on_close,
                            on_error=self._on_error,
                        )

                        if self._ws_obj is None:
                            logger.error("broker.create_websocket() returned None")
                            self._retries += 1
                            self._state = ConnectionState.DISCONNECTED
                            if attempt < self.max_retries:
                                time.sleep(self.retry_delay)
                            continue

                        # Run ws_connect in a daemon thread (handles blocking SDKs)
                        self._connect_thread = threading.Thread(
                            target=self._run_broker_connect,
                            daemon=True,
                            name=f"WS-Connect-{self.broker.__class__.__name__}",
                        )
                        self._connect_thread.start()

                        self._retries = 0
                        self._start_monitoring_threads()
                        logger.info("WebSocket connection initiated")
                        break

                    except Exception as e:
                        logger.error(f"Connection attempt {attempt} failed: {e!r}", exc_info=True)
                        self._retries += 1
                        self._error_count += 1
                        self._state = ConnectionState.DISCONNECTED
                        if self._retries >= self.max_retries:
                            logger.critical("Max retries reached; could not connect WebSocket")
                            return
                        if attempt < self.max_retries:
                            time.sleep(self.retry_delay)

            except Exception as e:
                logger.error(f"[WebSocketManager.connect] Unexpected: {e}", exc_info=True)
                self._state = ConnectionState.DISCONNECTED

    def subscribe(self, symbols: Optional[List[str]] = None):
        """Subscribe to symbols via the broker's ws_subscribe()."""
        with self._connection_lock:
            try:
                if symbols:
                    if not isinstance(symbols, list):
                        logger.error("symbols must be a list")
                        return
                    self.symbols = symbols

                if not self.symbols:
                    logger.warning("No symbols to subscribe to")
                    return

                if self._state != ConnectionState.CONNECTED:
                    logger.warning("Not connected; attempting connect before subscribe")
                    self.connect()
                    time.sleep(2)

                if self._ws_obj is None:
                    logger.error("ws_obj unavailable after connect attempt")
                    return

                self.broker.ws_subscribe(self._ws_obj, self.symbols)
                logger.info(f"Subscribed to {len(self.symbols)} symbols")

            except Exception as e:
                logger.error(f"[WebSocketManager.subscribe] {e!r}", exc_info=True)
                self._state = ConnectionState.DISCONNECTED

    def unsubscribe(self, symbols: Optional[List[str]] = None):
        """Unsubscribe from symbols via the broker's ws_unsubscribe()."""
        with self._connection_lock:
            try:
                if self._state != ConnectionState.CONNECTED or self._ws_obj is None:
                    logger.warning("Not connected; nothing to unsubscribe")
                    return
                target = symbols or self.symbols
                if target:
                    self.broker.ws_unsubscribe(self._ws_obj, target)
            except Exception as e:
                logger.error(f"[WebSocketManager.unsubscribe] {e!r}", exc_info=True)

    def disconnect(self):
        """Disconnect and clean up all resources with timeout protection."""
        with self._connection_lock:
            try:
                logger.info("Initiating WebSocket disconnect...")
                self._manual_stop = True
                # Bug #7 & #15 fix: Signal threads to stop
                self._stop_heartbeat.set()
                self._stop_network_monitor.set()
                self._stop_reconnect.set()

                old_state = self._state
                self._state = ConnectionState.CLOSING

                if self._ws_obj is not None and self.broker is not None:
                    try:
                        # Try to unsubscribe first
                        if self.symbols:
                            try:
                                self.broker.ws_unsubscribe(self._ws_obj, self.symbols)
                                logger.debug("Unsubscribed from symbols")
                            except Exception as e:
                                logger.warning(f"Unsubscribe error (continuing): {e}")

                        # Run disconnect in a separate thread with timeout
                        disconnect_complete = threading.Event()

                        def _do_disconnect():
                            try:
                                self.broker.ws_disconnect(self._ws_obj)
                                logger.debug("ws_disconnect completed")
                            except Exception as e:
                                logger.error(f"ws_disconnect error: {e}")
                            finally:
                                disconnect_complete.set()

                        disconnect_thread = threading.Thread(target=_do_disconnect, daemon=True)
                        disconnect_thread.start()

                        # Wait for disconnect with timeout
                        if not disconnect_complete.wait(timeout=3.0):
                            logger.warning("ws_disconnect timed out after 3 seconds")

                    except Exception as e:
                        logger.error(f"Error during disconnect: {e}", exc_info=True)
                    finally:
                        self._ws_obj = None

                # Wait for monitoring threads to finish (with timeout)
                self._join_threads()

                self._state = ConnectionState.DISCONNECTED
                logger.info(f"WebSocket disconnected — messages={self._message_count}, "
                            f"errors={self._error_count}, reconnects={self._reconnect_count}")

            except Exception as e:
                logger.error(f"[WebSocketManager.disconnect] {e!r}", exc_info=True)
                self._state = ConnectionState.DISCONNECTED

    def _join_threads(self, timeout: float = 2.0):
        """Helper to join monitoring threads with timeout."""
        threads = [
            (self._heartbeat_thread, "heartbeat"),
            (self._network_monitor_thread, "network"),
            (self._reconnect_thread, "reconnect"),
        ]
        for thread, name in threads:
            if thread and thread.is_alive():
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.warning(f"{name} thread did not terminate within {timeout}s")

    # ── Broker WebSocket callbacks ─────────────────────────────────────────────

    def _on_connect(self):
        """Called by the broker's WebSocket when connection is established."""
        with self._connection_lock:
            try:
                logger.info("WebSocket connected")
                self._state = ConnectionState.CONNECTED
                self._retries = 0
                self._reconnect_attempts = 0
                self._last_message_time = time.time()

                if self._ws_obj and self.symbols:
                    try:
                        self.broker.ws_subscribe(self._ws_obj, self.symbols)
                        logger.info(f"Re-subscribed {len(self.symbols)} symbols")
                    except Exception as e:
                        logger.error(f"Re-subscribe failed: {e}", exc_info=True)

                if self.on_connected_callback:
                    try:
                        self.on_connected_callback()
                    except Exception as e:
                        logger.error(f"on_connected_callback error: {e}", exc_info=True)

                if self.on_reconnect_callback:
                    try:
                        self.on_reconnect_callback()
                    except Exception as e:
                        logger.error(f"on_reconnect_callback error: {e}", exc_info=True)

                # Call reconnected callback
                if self.on_reconnected_callback:
                    try:
                        self.on_reconnected_callback()
                    except Exception as e:
                        logger.error(f"on_reconnected_callback error: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"[WebSocketManager._on_connect] {e}", exc_info=True)

    def _on_close(self, message=""):
        """Called by the broker's WebSocket when connection closes."""
        with self._connection_lock:
            try:
                logger.warning(f"WebSocket closed: {message}")

                # Bug #3 fix: Only change state if not already CLOSING
                if self._state != ConnectionState.CLOSING:
                    self._state = ConnectionState.DISCONNECTED

                # Call state manager callback
                if self.on_disconnected_callback:
                    try:
                        self.on_disconnected_callback()
                    except Exception as e:
                        logger.error(f"on_disconnected_callback error: {e}", exc_info=True)

                # Bug #3 fix: Only schedule reconnect if not manual stop and not CLOSING
                if not self._manual_stop and self._state != ConnectionState.CLOSING:
                    if self.on_disconnect_callback:
                        try:
                            self.on_disconnect_callback()
                        except Exception as e:
                            logger.error(f"on_disconnect_callback error: {e}", exc_info=True)
                    self._schedule_reconnect()
                else:
                    logger.info("WebSocket closed intentionally; no reconnect")

            except Exception as e:
                logger.error(f"[WebSocketManager._on_close] {e}", exc_info=True)

    def _on_error(self, message=""):
        """Called by the broker's WebSocket on errors."""
        with self._connection_lock:
            try:
                self._error_count += 1
                logger.error(f"WebSocket error: {message}")

                # Bug #3 fix: Only change state if not already CLOSING
                if self._state != ConnectionState.CLOSING:
                    self._state = ConnectionState.DISCONNECTED

                # Call state manager callback
                if self.on_disconnected_callback:
                    try:
                        self.on_disconnected_callback()
                    except Exception as e:
                        logger.error(f"on_disconnected_callback error: {e}", exc_info=True)

                if not self._manual_stop and self._state != ConnectionState.CLOSING:
                    if self.on_disconnect_callback:
                        try:
                            self.on_disconnect_callback()
                        except Exception:
                            pass
                    self._schedule_reconnect()

            except Exception as e:
                logger.error(f"[WebSocketManager._on_error] {e}", exc_info=True)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _run_broker_connect(self):
        """Run broker.ws_connect() in a daemon thread (handles blocking SDKs)."""
        try:
            if self.broker and self._ws_obj is not None:
                self.broker.ws_connect(self._ws_obj)
        except Exception as e:
            logger.error(f"[WebSocketManager._run_broker_connect] {e}", exc_info=True)
            if not self._manual_stop:
                with self._connection_lock:
                    self._state = ConnectionState.DISCONNECTED

    def _start_monitoring_threads(self):
        """Start heartbeat and network monitoring threads."""
        try:
            if not self._heartbeat_thread or not self._heartbeat_thread.is_alive():
                self._heartbeat_thread = threading.Thread(
                    target=self._heartbeat_monitor,
                    daemon=True,
                    name="WS-Heartbeat",
                )
                self._heartbeat_thread.start()

            if not self._network_monitor_thread or not self._network_monitor_thread.is_alive():
                self._network_monitor_thread = threading.Thread(
                    target=self._network_monitor,
                    daemon=True,
                    name="WS-NetworkMonitor",
                )
                self._network_monitor_thread.start()

        except Exception as e:
            logger.error(f"Failed to start monitoring threads: {e}", exc_info=True)

    def _heartbeat_monitor(self):
        """Detect stale connections by watching message timestamps."""
        # Bug #15 fix: Use stop event
        while not self._manual_stop and not self._stop_heartbeat.is_set():
            try:
                if self._state == ConnectionState.CONNECTED:
                    age = time.time() - self._last_message_time
                    if age > self.heartbeat_interval:
                        logger.warning(f"No messages for {age:.1f}s — connection may be stale")
                        if age > self.heartbeat_interval * 2:
                            logger.error("Connection appears dead; triggering reconnect")
                            self._handle_stale_connection()
                # Bug #15 fix: Use shorter sleep to check stop event more frequently
                for _ in range(self.heartbeat_interval // 2):
                    if self._stop_heartbeat.is_set() or self._manual_stop:
                        return
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Heartbeat monitor error: {e!r}", exc_info=True)
                time.sleep(5)

    def _network_monitor(self):
        """Detect network failures and trigger reconnect."""
        consecutive_failures = 0
        max_failures = 3
        # Bug #15 fix: Use stop event
        while not self._manual_stop and not self._stop_network_monitor.is_set():
            try:
                if self._state == ConnectionState.CONNECTED:
                    if self._check_network():
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                        logger.warning(f"Network check failed ({consecutive_failures}/{max_failures})")
                        if consecutive_failures >= max_failures:
                            logger.error("Network down; triggering reconnect")
                            self._handle_network_disconnection()
                            consecutive_failures = 0
                # Bug #15 fix: Use shorter sleep to check stop event
                for _ in range(self._network_check_interval):
                    if self._stop_network_monitor.is_set() or self._manual_stop:
                        return
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Network monitor error: {e!r}", exc_info=True)
                time.sleep(5)

    def _check_network(self) -> bool:
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            return True
        except (socket.error, socket.timeout):
            try:
                requests.get("https://httpbin.org/status/200", timeout=5)
                return True
            except Exception:
                return False

    def _handle_stale_connection(self):
        with self._connection_lock:
            try:
                if self._state == ConnectionState.CONNECTED and not self._manual_stop:
                    self._state = ConnectionState.DISCONNECTED
                    if self.on_disconnected_callback:
                        try:
                            self.on_disconnected_callback()
                        except Exception:
                            pass
                    if self.on_disconnect_callback:
                        try:
                            self.on_disconnect_callback()
                        except Exception:
                            pass
                    # Bug #13 fix: Check if reconnect already scheduled
                    if not self._reconnect_thread or not self._reconnect_thread.is_alive():
                        self._schedule_reconnect()
            except Exception as e:
                logger.error(f"_handle_stale_connection: {e}", exc_info=True)

    def _handle_network_disconnection(self):
        with self._connection_lock:
            try:
                if self._state == ConnectionState.CONNECTED and not self._manual_stop:
                    self._state = ConnectionState.DISCONNECTED
                    if self.on_disconnected_callback:
                        try:
                            self.on_disconnected_callback()
                        except Exception:
                            pass
                    if self.on_disconnect_callback:
                        try:
                            self.on_disconnect_callback()
                        except Exception:
                            pass
                    # Bug #13 fix: Check if reconnect already scheduled
                    if not self._reconnect_thread or not self._reconnect_thread.is_alive():
                        self._schedule_reconnect()
            except Exception as e:
                logger.error(f"_handle_network_disconnection: {e}", exc_info=True)

    def _schedule_reconnect(self):
        """Schedule reconnect with exponential backoff and max attempts."""
        with self._connection_lock:
            if self._reconnect_attempts >= self._max_reconnect_attempts:
                logger.critical(f"Max reconnect attempts ({self._max_reconnect_attempts}) reached. Giving up.")
                self._state = ConnectionState.DISCONNECTED
                return

            if self._state == ConnectionState.RECONNECTING:
                logger.info("Reconnect already in progress")
                return

            self._state = ConnectionState.RECONNECTING
            self._reconnect_attempts += 1

            # Exponential backoff with jitter
            delay = min(self._base_delay * (2 ** (self._reconnect_attempts - 1)), self._max_delay)
            jitter = random.uniform(0.8, 1.2)
            delay = delay * jitter

            logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})...")

            # Bug #13 & #16 fix: Check if reconnect thread exists and is alive
            if self._reconnect_thread and self._reconnect_thread.is_alive():
                logger.info("Reconnect thread already running")
                return

            self._stop_reconnect.clear()
            self._reconnect_thread = threading.Thread(
                target=self._reconnect_with_delay,
                args=(delay,),
                daemon=True,
                name="WS-Reconnect",
            )
            self._reconnect_thread.start()

    def _reconnect_with_delay(self, delay: float):
        """Reconnect after delay with stop event support."""
        try:
            # Sleep in small increments to check stop event
            slept = 0
            interval = 0.5
            while slept < delay and not self._manual_stop and not self._stop_reconnect.is_set():
                time.sleep(interval)
                slept += interval

            if not self._manual_stop and not self._stop_reconnect.is_set():
                self._reconnect_count += 1
                self.connect()
        except Exception as e:
            logger.error(f"_reconnect_with_delay: {e}", exc_info=True)

    def _wait_for_network_recovery(self) -> bool:
        try:
            max_wait = 300
            wait_step = 10
            waited = 0
            logger.info("Waiting for network recovery...")
            while waited < max_wait and not self._manual_stop and not self._stop_reconnect.is_set():
                if self._check_network():
                    logger.info("Network restored")
                    return True
                time.sleep(wait_step)
                waited += wait_step
            return False
        except Exception as e:
            logger.error(f"_wait_for_network_recovery: {e}", exc_info=True)
            return False

    def _cleanup_socket(self):
        """Destroy the current broker socket object with timeout."""
        if self._ws_obj is not None and self.broker is not None:
            try:
                # Try to disconnect with timeout
                disconnect_complete = threading.Event()

                def _do_disconnect():
                    try:
                        self.broker.ws_disconnect(self._ws_obj)
                    except Exception as e:
                        logger.error(f"ws_disconnect in cleanup: {e}")
                    finally:
                        disconnect_complete.set()

                cleanup_thread = threading.Thread(target=_do_disconnect, daemon=True)
                cleanup_thread.start()
                disconnect_complete.wait(timeout=2.0)

            except Exception as e:
                logger.error(f"_cleanup_socket error: {e!r}", exc_info=True)
            finally:
                self._ws_obj = None

    # ── Callback wrapper ───────────────────────────────────────────────────────

    def _wrap_callback(self, callback: Callable) -> Callable:
        """Wrap the user's on_message callback to normalize ticks and track stats."""

        @wraps(callback)
        def safe_callback(raw_tick):
            try:
                self._last_message_time = time.time()

                if raw_tick is None:
                    return

                # Normalize via broker
                if self.broker is not None:
                    normalized = self.broker.normalize_tick(raw_tick)
                else:
                    normalized = raw_tick if isinstance(raw_tick, dict) else None

                if normalized is None:
                    return  # heartbeat / unparseable frame — silently skip

                self._message_count += 1
                callback(normalized)

            except Exception as e:
                logger.error(f"on_message_callback exception: {e!r}", exc_info=True)
                self._error_count += 1

        return safe_callback

    def _dummy_callback(self, message=None):
        pass

    # ── Public status helpers ──────────────────────────────────────────────────

    def is_connected(self) -> bool:
        try:
            return self._state == ConnectionState.CONNECTED
        except Exception:
            return False

    def get_connection_state(self) -> ConnectionState:
        try:
            return self._state
        except Exception:
            return ConnectionState.DISCONNECTED

    def get_statistics(self) -> Dict[str, Any]:
        try:
            return {
                "message_count": self._message_count,
                "error_count": self._error_count,
                "reconnect_count": self._reconnect_count,
                "state": self._state.value if self._state else "unknown",
                "retries": self._retries,
                "reconnect_attempts": self._reconnect_attempts,
                "symbols_count": len(self.symbols),
                "broker": repr(self.broker),
            }
        except Exception:
            return {}

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def cleanup(self, timeout: float = 3.0):
        """Release all resources with timeout (safe to call multiple times)."""
        try:
            if self._cleanup_done:
                return
            logger.info("[WebSocketManager] Starting cleanup")

            disconnect_complete = threading.Event()

            def _do_cleanup():
                try:
                    self.disconnect()
                except Exception as e:
                    logger.error(f"Error in disconnect during cleanup: {e}")
                finally:
                    disconnect_complete.set()

            cleanup_thread = threading.Thread(target=_do_cleanup, daemon=True)
            cleanup_thread.start()

            # Wait for disconnect to complete with timeout
            if not disconnect_complete.wait(timeout=timeout):
                logger.warning(f"Cleanup timed out after {timeout}s, forcing completion")

            self.broker = None
            self._ws_obj = None
            self._connect_thread = None
            self._heartbeat_thread = None
            self._network_monitor_thread = None
            self._reconnect_thread = None
            self.on_disconnect_callback = None
            self.on_reconnect_callback = None
            self.on_connected_callback = None
            self.on_disconnected_callback = None
            self.on_reconnected_callback = None

            self._cleanup_done = True
            logger.info("[WebSocketManager] Cleanup completed")

        except Exception as e:
            logger.error(f"[WebSocketManager.cleanup] {e}", exc_info=True)
            self._cleanup_done = True