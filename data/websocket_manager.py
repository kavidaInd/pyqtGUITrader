import logging
import logging.handlers
import threading
import time
import socket
import requests
from typing import Callable, List, Optional, Dict, Any
from enum import Enum
from functools import wraps

from fyers_apiv3.FyersWebsocket import data_ws

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSING = "closing"


class WebSocketManager:
    # Rule 3: Define signals for future PyQt integration
    # error_occurred = pyqtSignal(str)
    # connection_state_changed = pyqtSignal(str)
    # message_received = pyqtSignal(dict)

    def __init__(
            self,
            token: str,
            client_id: str,
            on_message_callback: Callable,
            symbols: Optional[List[str]] = None,
            max_retries: int = 5,
            retry_delay: int = 5,
            heartbeat_interval: int = 30,
            connection_timeout: int = 10
    ):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if not token:
                logger.error("token is required for WebSocketManager")
                token = ""  # Will cause connection failure, but won't crash

            if not client_id:
                logger.error("client_id is required for WebSocketManager")
                client_id = ""  # Will cause connection failure, but won't crash

            if not on_message_callback:
                logger.error("on_message_callback is required for WebSocketManager")
                # Provide a dummy callback to prevent crashes
                on_message_callback = self._dummy_callback

            self.token = token
            self.client_id = client_id
            self.on_message_callback = self._wrap_callback(on_message_callback)
            self.symbols = symbols if symbols else ["NSE:NIFTY50-INDEX"]
            self.max_retries = max_retries
            self.retry_delay = retry_delay
            self.heartbeat_interval = heartbeat_interval
            self.connection_timeout = connection_timeout

            # Connection management
            self._state = ConnectionState.DISCONNECTED
            self._retries = 0
            self._manual_stop = False
            self._connection_lock = threading.RLock()  # Reentrant lock for thread safety
            self._keep_running_thread = None
            self._heartbeat_thread = None
            self._last_message_time = time.time()

            # Network monitoring
            self._network_check_interval = 5  # Check network every 5 seconds
            self._network_monitor_thread = None
            self._reconnect_thread = None

            # Single socket instance
            self.socket = None

            # Statistics
            self._message_count = 0
            self._error_count = 0
            self._reconnect_count = 0

            # FEATURE 4: Callbacks for Telegram notifications
            self.on_disconnect_callback = None
            self.on_reconnect_callback = None

            logger.info("WebSocketManager initialized")

        except Exception as e:
            logger.critical(f"[WebSocketManager.__init__] Failed: {e}", exc_info=True)
            # Don't raise - try to continue with minimal functionality
            self._safe_defaults_init()

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.token = ""
        self.client_id = ""
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
        self._keep_running_thread = None
        self._heartbeat_thread = None
        self._last_message_time = 0
        self._network_check_interval = 5
        self._network_monitor_thread = None
        self._reconnect_thread = None
        self.socket = None
        self._message_count = 0
        self._error_count = 0
        self._reconnect_count = 0
        self._cleanup_done = False
        self.on_disconnect_callback = None
        self.on_reconnect_callback = None

    def _dummy_callback(self, message):
        """Dummy callback to prevent crashes when no callback provided"""
        pass

    def connect(self):
        """Connect to WebSocket with proper state management"""
        with self._connection_lock:
            try:
                # Prevent multiple simultaneous connections
                if self._state in [ConnectionState.CONNECTING, ConnectionState.CONNECTED]:
                    logger.info(f"Already {self._state.value}. Skipping connection attempt.")
                    return

                self._manual_stop = False
                self._state = ConnectionState.CONNECTING

                for attempt in range(1, self.max_retries + 1):
                    try:
                        logger.info(f"Attempting to connect to WebSocket (Attempt {attempt})")

                        # Clean up any existing socket before creating new one
                        if self.socket:
                            self._cleanup_socket()

                        # Validate required attributes
                        if not self.client_id or not self.token:
                            error_msg = f"Cannot connect: missing client_id ({bool(self.client_id)}) or token ({bool(self.token)})"
                            logger.error(error_msg)
                            self._state = ConnectionState.DISCONNECTED
                            return

                        # Create access token
                        access_token = f"{self.client_id}:{self.token}"

                        self.socket = data_ws.FyersDataSocket(
                            access_token=access_token,
                            log_path="",
                            litemode=False,
                            write_to_file=False,
                            reconnect=False,
                            on_connect=self.on_connect,
                            on_close=self.on_close,
                            on_error=self.on_error,
                            on_message=self.on_message_callback
                        )

                        self.socket.connect()
                        logger.info("WebSocket connection initiated")
                        self._retries = 0

                        # Start monitoring threads after successful connection
                        self._start_monitoring_threads()

                        # State will be set to CONNECTED in on_connect callback
                        break

                    except AttributeError as e:
                        logger.error(f"WebSocket attribute error: {e}", exc_info=True)
                        self._retries += 1
                        self._state = ConnectionState.DISCONNECTED

                    except Exception as e:
                        logger.error(f"WebSocket connection failed: {e!r}", exc_info=True)
                        self._retries += 1
                        self._error_count += 1
                        self._state = ConnectionState.DISCONNECTED

                        if self._retries >= self.max_retries:
                            logger.critical("Max retries reached, could not connect to WebSocket")
                            return

                        if attempt < self.max_retries:  # Don't sleep on last attempt
                            time.sleep(self.retry_delay)

            except Exception as e:
                logger.error(f"[WebSocketManager.connect] Unexpected error: {e}", exc_info=True)
                self._state = ConnectionState.DISCONNECTED

    def subscribe(self, symbols: Optional[List[str]] = None):
        """Subscribe to symbols with connection state validation"""
        with self._connection_lock:
            try:
                # Validate symbols
                if symbols is not None:
                    if not isinstance(symbols, list):
                        logger.error(f"symbols must be a list, got {type(symbols)}")
                        return
                    if symbols:
                        self.symbols = symbols

                if not self.symbols:
                    logger.warning("No symbols to subscribe to")
                    return

                # Ensure we're connected
                if self._state != ConnectionState.CONNECTED:
                    logger.warning("WebSocket not connected. Connecting now.")
                    self.connect()
                    # Wait a bit for connection to establish
                    time.sleep(2)

                if not self.socket:
                    logger.error("Socket not available after connection attempt")
                    return

                logger.info(f"Subscribing to symbols: {self.symbols}")

                # Subscribe with error handling for each subscription
                try:
                    self.socket.subscribe(symbols=self.symbols, data_type="OnOrders")
                except Exception as e:
                    logger.error(f"Failed to subscribe to OnOrders: {e}", exc_info=True)

                try:
                    self.socket.subscribe(symbols=self.symbols, data_type="SymbolUpdate")
                except Exception as e:
                    logger.error(f"Failed to subscribe to SymbolUpdate: {e}", exc_info=True)

                # Start keep_running thread only if not already running
                if not self._keep_running_thread or not self._keep_running_thread.is_alive():
                    self._keep_running_thread = threading.Thread(
                        target=self._keep_running_wrapper,
                        daemon=True,
                        name="WebSocket-KeepRunning"
                    )
                    self._keep_running_thread.start()
                    logger.info("Started keep_running thread")

            except Exception as e:
                logger.error(f"Failed to subscribe: {e!r}", exc_info=True)
                self._state = ConnectionState.DISCONNECTED

    def _start_monitoring_threads(self):
        """Start heartbeat and network monitoring threads"""
        try:
            # Start heartbeat monitoring
            if not self._heartbeat_thread or not self._heartbeat_thread.is_alive():
                self._heartbeat_thread = threading.Thread(
                    target=self._heartbeat_monitor,
                    daemon=True,
                    name="WebSocket-Heartbeat"
                )
                self._heartbeat_thread.start()
                logger.info("Started heartbeat monitoring thread")

            # Start network monitoring
            if not self._network_monitor_thread or not self._network_monitor_thread.is_alive():
                self._network_monitor_thread = threading.Thread(
                    target=self._network_monitor,
                    daemon=True,
                    name="WebSocket-NetworkMonitor"
                )
                self._network_monitor_thread.start()
                logger.info("Started network monitoring thread")

        except Exception as e:
            logger.error(f"Failed to start monitoring threads: {e}", exc_info=True)

    def _heartbeat_monitor(self):
        """Monitor connection health using heartbeat"""
        while not self._manual_stop:
            try:
                if self._state == ConnectionState.CONNECTED:
                    current_time = time.time()
                    time_since_last_message = current_time - self._last_message_time

                    if time_since_last_message > self.heartbeat_interval:
                        logger.warning(
                            f"No messages received for {time_since_last_message:.1f} seconds. Connection might be stale.")

                        # Check if connection is actually dead
                        if time_since_last_message > (self.heartbeat_interval * 2):
                            logger.error("Connection appears to be dead. Triggering reconnection.")
                            self._handle_stale_connection()

                time.sleep(self.heartbeat_interval // 2)  # Check more frequently than heartbeat interval

            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e!r}", exc_info=True)
                time.sleep(5)

    def _network_monitor(self):
        """Monitor network connectivity"""
        consecutive_failures = 0
        max_consecutive_failures = 3

        while not self._manual_stop:
            try:
                if self._state == ConnectionState.CONNECTED:
                    if self._check_network_connectivity():
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                        logger.warning(
                            f"Network connectivity check failed ({consecutive_failures}/{max_consecutive_failures})")

                        if consecutive_failures >= max_consecutive_failures:
                            logger.error("Network appears to be down. Triggering reconnection.")
                            self._handle_network_disconnection()
                            consecutive_failures = 0

                time.sleep(self._network_check_interval)

            except Exception as e:
                logger.error(f"Error in network monitor: {e!r}", exc_info=True)
                time.sleep(5)

    def _check_network_connectivity(self) -> bool:
        """Check if network is available"""
        try:
            # Try to connect to a reliable endpoint
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            return True
        except (socket.error, socket.timeout):
            try:
                # Fallback: try HTTP request
                response = requests.get("https://httpbin.org/status/200", timeout=5)
                return response.status_code == 200
            except requests.RequestException as e:
                logger.debug(f"HTTP connectivity check failed: {e}")
                return False
            except Exception as e:
                logger.debug(f"Network check failed: {e}")
                return False

    def _handle_stale_connection(self):
        """Handle stale connection detected by heartbeat"""
        with self._connection_lock:
            try:
                if self._state == ConnectionState.CONNECTED and not self._manual_stop:
                    logger.info("Handling stale connection...")
                    self._state = ConnectionState.DISCONNECTED

                    # FEATURE 4: Call disconnect callback
                    if self.on_disconnect_callback:
                        try:
                            self.on_disconnect_callback()
                        except Exception as e:
                            logger.error(f"Error in disconnect callback: {e}", exc_info=True)

                    self._schedule_reconnect()
            except Exception as e:
                logger.error(f"Error handling stale connection: {e}", exc_info=True)

    def _handle_network_disconnection(self):
        """Handle network disconnection"""
        with self._connection_lock:
            try:
                if self._state == ConnectionState.CONNECTED and not self._manual_stop:
                    logger.info("Handling network disconnection...")
                    self._state = ConnectionState.DISCONNECTED

                    # FEATURE 4: Call disconnect callback
                    if self.on_disconnect_callback:
                        try:
                            self.on_disconnect_callback()
                        except Exception as e:
                            logger.error(f"Error in disconnect callback: {e}", exc_info=True)

                    self._schedule_reconnect()
            except Exception as e:
                logger.error(f"Error handling network disconnection: {e}", exc_info=True)

    def _wait_for_network_recovery(self) -> bool:
        """Wait for network to recover before attempting reconnection"""
        try:
            logger.info("Waiting for network recovery...")
            max_wait_time = 300  # 5 minutes
            wait_interval = 10  # Check every 10 seconds
            waited_time = 0

            while waited_time < max_wait_time and not self._manual_stop:
                if self._check_network_connectivity():
                    logger.info("Network connectivity restored")
                    return True

                time.sleep(wait_interval)
                waited_time += wait_interval
                logger.info(f"Still waiting for network recovery... ({waited_time}s/{max_wait_time}s)")

            logger.warning("Network recovery timeout")
            return False

        except Exception as e:
            logger.error(f"Error in network recovery wait: {e}", exc_info=True)
            return False

    def _keep_running_wrapper(self):
        """Wrapper for keep_running with proper exception handling"""
        try:
            if self.socket:
                self.socket.keep_running()
        except AttributeError as e:
            logger.error(f"Socket attribute error in keep_running: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error in keep_running: {e!r}", exc_info=True)
            if not self._manual_stop:
                with self._connection_lock:
                    self._state = ConnectionState.DISCONNECTED

    def unsubscribe(self, symbols: Optional[List[str]] = None):
        """Unsubscribe from symbols"""
        with self._connection_lock:
            try:
                if self._state != ConnectionState.CONNECTED or not self.socket:
                    logger.warning("WebSocket not connected. Nothing to unsubscribe.")
                    return

                symbols_to_unsubscribe = symbols or self.symbols
                if not symbols_to_unsubscribe:
                    logger.warning("No symbols to unsubscribe")
                    return

                logger.info(f"Unsubscribing from symbols: {symbols_to_unsubscribe}")

                try:
                    self.socket.unsubscribe(symbols=symbols_to_unsubscribe, data_type="OnOrders")
                except Exception as e:
                    logger.error(f"Failed to unsubscribe from OnOrders: {e}", exc_info=True)

                try:
                    self.socket.unsubscribe(symbols=symbols_to_unsubscribe, data_type="SymbolUpdate")
                except Exception as e:
                    logger.error(f"Failed to unsubscribe from SymbolUpdate: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Failed to unsubscribe: {e!r}", exc_info=True)

    def on_connect(self):
        """
        BUG #5 FIX: Handle successful connection and force re-subscription.
        Called by FyersDataSocket when connection is established.
        """
        with self._connection_lock:
            try:
                logger.info("WebSocket connected.")
                self._state = ConnectionState.CONNECTED
                self._retries = 0
                self._last_message_time = time.time()

                # BUG #5 FIX: Always force re-subscription on connect
                if self.socket and self.symbols:
                    for data_type in ['SymbolUpdate', 'OnOrders']:
                        try:
                            self.socket.subscribe(symbols=self.symbols, data_type=data_type)
                            logger.info(f"Re-subscribed {len(self.symbols)} symbols ({data_type})")
                        except Exception as e:
                            logger.error(f"Re-subscribe failed {data_type}: {e}", exc_info=True)
                else:
                    logger.warning("No symbols to subscribe after connect")

                # FEATURE 4: Call reconnect callback
                if self.on_reconnect_callback:
                    try:
                        self.on_reconnect_callback()
                    except Exception as e:
                        logger.error(f"Error in reconnect callback: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error in on_connect handler: {e}", exc_info=True)

    def on_close(self, message):
        """Handle connection close"""
        with self._connection_lock:
            try:
                logger.warning(f"WebSocket closed: {message}")

                if self._state != ConnectionState.CLOSING:
                    self._state = ConnectionState.DISCONNECTED

                if not self._manual_stop and self._state != ConnectionState.CLOSING:
                    logger.info("Connection closed unexpectedly. Will attempt to reconnect.")

                    # FEATURE 4: Call disconnect callback
                    if self.on_disconnect_callback:
                        try:
                            self.on_disconnect_callback()
                        except Exception as e:
                            logger.error(f"Error in disconnect callback: {e}", exc_info=True)

                    self._schedule_reconnect()
                else:
                    logger.info("WebSocket closed intentionally by user. No reconnection.")

            except Exception as e:
                logger.error(f"Error in on_close handler: {e}", exc_info=True)

    def on_error(self, message):
        """Handle connection error"""
        with self._connection_lock:
            try:
                self._error_count += 1
                logger.error(f"WebSocket error: {message}")

                if self._state != ConnectionState.CLOSING:
                    self._state = ConnectionState.DISCONNECTED

                if not self._manual_stop:

                    # FEATURE 4: Call disconnect callback
                    if self.on_disconnect_callback:
                        try:
                            self.on_disconnect_callback()
                        except Exception as e:
                            logger.error(f"Error in disconnect callback: {e}", exc_info=True)

                    self._schedule_reconnect()

            except Exception as e:
                logger.error(f"Error in on_error handler: {e}", exc_info=True)

    def _schedule_reconnect(self):
        """Schedule reconnection in a separate thread to avoid blocking"""
        try:
            if self._state == ConnectionState.RECONNECTING:
                logger.info("Reconnection already in progress")
                return

            self._state = ConnectionState.RECONNECTING

            # Don't create a new thread if one is already running
            if self._reconnect_thread and self._reconnect_thread.is_alive():
                logger.info("Reconnect thread already running")
                return

            self._reconnect_thread = threading.Thread(
                target=self._reconnect_with_backoff,
                daemon=True,
                name="WebSocket-Reconnect"
            )
            self._reconnect_thread.start()

        except Exception as e:
            logger.error(f"Error scheduling reconnect: {e}", exc_info=True)
            self._state = ConnectionState.DISCONNECTED

    def _reconnect_with_backoff(self):
        """Reconnect with exponential backoff and network recovery wait"""
        try:
            self._reconnect_count += 1
            self._retries += 1

            if self._retries > self.max_retries:
                logger.critical("Max retries reached. Not reconnecting.")
                self._state = ConnectionState.DISCONNECTED
                return

            # Wait for network recovery first
            if not self._wait_for_network_recovery():
                logger.error("Network recovery timeout. Scheduling next retry.")
                self._state = ConnectionState.DISCONNECTED
                return

            delay = min(self.retry_delay * self._retries, 60)  # Cap at 60 seconds
            logger.info(f"Reconnecting in {delay} seconds... (Attempt {self._retries})")

            # Check for stop during wait
            for _ in range(int(delay)):
                if self._manual_stop:
                    logger.info("Stop requested during reconnect wait")
                    return
                time.sleep(1)

            if not self._manual_stop:
                self.connect()

        except Exception as e:
            logger.error(f"Error in reconnect with backoff: {e}", exc_info=True)
            self._state = ConnectionState.DISCONNECTED

    def _cleanup_socket(self):
        """Clean up existing socket connection"""
        if self.socket:
            try:
                if hasattr(self.socket, 'close_connection'):
                    self.socket.close_connection()
            except Exception as e:
                logger.error(f"Error closing existing socket: {e!r}", exc_info=True)
            finally:
                self.socket = None

    def disconnect(self):
        """Properly disconnect and cleanup"""
        with self._connection_lock:
            try:
                logger.info("Initiating WebSocket disconnect...")
                self._manual_stop = True
                self._state = ConnectionState.CLOSING

                # Clean up socket
                if self.socket:
                    try:
                        if hasattr(self.socket, 'close_connection'):
                            self.socket.close_connection()
                    except Exception as e:
                        logger.error(f"Error closing socket: {e}", exc_info=True)
                    finally:
                        self.socket = None

                # Wait for monitoring threads to finish
                threads_to_wait = [
                    ('keep_running', self._keep_running_thread),
                    ('heartbeat', self._heartbeat_thread),
                    ('network_monitor', self._network_monitor_thread),
                    ('reconnect', self._reconnect_thread)
                ]

                for thread_name, thread in threads_to_wait:
                    if thread and thread.is_alive():
                        try:
                            thread.join(timeout=3)
                        except Exception as e:
                            logger.warning(f"Error waiting for {thread_name} thread: {e}")

                logger.info("WebSocket disconnected successfully.")
                self._state = ConnectionState.DISCONNECTED

                # Log statistics
                logger.info(f"WebSocket stats - Messages: {self._message_count}, "
                            f"Errors: {self._error_count}, Reconnects: {self._reconnect_count}")

            except Exception as e:
                logger.error(f"Failed to disconnect WebSocket: {e!r}", exc_info=True)
                self._state = ConnectionState.DISCONNECTED

    def get_connection_state(self) -> ConnectionState:
        """Get current connection state"""
        try:
            return self._state
        except Exception as e:
            logger.error(f"Error getting connection state: {e}", exc_info=True)
            return ConnectionState.DISCONNECTED

    def is_connected(self) -> bool:
        """Check if currently connected"""
        try:
            return self._state == ConnectionState.CONNECTED
        except Exception as e:
            logger.error(f"Error checking connection status: {e}", exc_info=True)
            return False

    def _wrap_callback(self, callback: Callable) -> Callable:
        """Wrap callback with error handling and message tracking"""

        @wraps(callback)
        def safe_callback(message):
            try:
                # Update last message time for heartbeat monitoring
                self._last_message_time = time.time()

                # Validate message
                if message is None:
                    logger.warning("Received None message")
                    return

                if not isinstance(message, dict):
                    logger.warning(f"Received non-dict message: {type(message)}")
                    return

                # Increment message counter
                self._message_count += 1

                # Call the original callback
                callback(message)

            except Exception as e:
                logger.error(f"Exception in on_message_callback: {e!r}", exc_info=True)
                self._error_count += 1

        return safe_callback

    @staticmethod
    def handle_message(data: Dict[str, Any]) -> None:
        """Handle incoming WebSocket messages"""
        try:
            # Rule 6: Input validation
            if data is None:
                logger.warning("handle_message called with None data")
                return

            if not isinstance(data, dict):
                logger.warning(f"handle_message expected dict, got {type(data)}")
                return

            # Validate expected keys
            symbol = data.get("symbol")
            ltp = data.get("ltp")

            if symbol is None:
                logger.warning("Missing symbol in data")
                return

            if ltp is None:
                logger.warning(f"Missing ltp for symbol {symbol}")
                return

            # Example: interpret and act
            logger.info(f"Received data for {symbol}: LTP={ltp}")

        except Exception as e:
            logger.error(f"Error processing data: {e!r}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown"""
        try:
            if self._cleanup_done:
                return

            logger.info("[WebSocketManager] Starting cleanup")

            # Disconnect WebSocket
            self.disconnect()

            # Clear references
            self.socket = None
            self._keep_running_thread = None
            self._heartbeat_thread = None
            self._network_monitor_thread = None
            self._reconnect_thread = None
            self.on_disconnect_callback = None
            self.on_reconnect_callback = None

            self._cleanup_done = True
            logger.info("[WebSocketManager] Cleanup completed")

        except Exception as e:
            logger.error(f"[WebSocketManager.cleanup] Error: {e}", exc_info=True)
            self._cleanup_done = True

    def get_statistics(self) -> Dict[str, Any]:
        """Get connection statistics"""
        try:
            return {
                'message_count': self._message_count,
                'error_count': self._error_count,
                'reconnect_count': self._reconnect_count,
                'state': self._state.value if self._state else 'unknown',
                'retries': self._retries,
                'symbols_count': len(self.symbols) if self.symbols else 0
            }
        except Exception as e:
            logger.error(f"Error getting statistics: {e}", exc_info=True)
            return {
                'message_count': 0,
                'error_count': 0,
                'reconnect_count': 0,
                'state': 'unknown',
                'retries': 0,
                'symbols_count': 0
            }