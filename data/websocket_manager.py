import logging
import threading
import time
import socket
import requests
from typing import Callable, List, Optional
from enum import Enum
from fyers_apiv3.FyersWebsocket import data_ws

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSING = "closing"


class WebSocketManager:
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

        # Single socket instance
        self.socket = None

    def connect(self):
        """Connect to WebSocket with proper state management"""
        with self._connection_lock:
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

                    self.socket = data_ws.FyersDataSocket(
                        access_token=f"{self.client_id}:{self.token}",
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
                    # State will be set to CONNECTED in on_connect callback
                    break

                except Exception as e:
                    logger.error(f"WebSocket connection failed: {e!r}")
                    self._retries += 1
                    self._state = ConnectionState.DISCONNECTED

                    if self._retries >= self.max_retries:
                        logger.critical("Max retries reached, could not connect to WebSocket")
                        raise

                    if attempt < self.max_retries:  # Don't sleep on last attempt
                        time.sleep(self.retry_delay)

    def subscribe(self, symbols: Optional[List[str]] = None):
        """Subscribe to symbols with connection state validation"""
        with self._connection_lock:
            try:
                # Ensure we're connected
                if self._state != ConnectionState.CONNECTED:
                    logger.warning("WebSocket not connected. Connecting now.")
                    self.connect()

                if not self.socket:
                    raise Exception("Socket not available after connection attempt")

                if symbols:
                    self.symbols = symbols

                logger.info(f"Subscribing to symbols: {self.symbols}")
                self.socket.subscribe(symbols=self.symbols, data_type="OnOrders")
                self.socket.subscribe(symbols=self.symbols, data_type="SymbolUpdate")

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
                logger.error(f"Failed to subscribe: {e!r}")
                self._state = ConnectionState.DISCONNECTED

    def _start_monitoring_threads(self):
        """Start heartbeat and network monitoring threads"""
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
                logger.error(f"Error in heartbeat monitor: {e!r}")
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
                logger.error(f"Error in network monitor: {e!r}")
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
            except:
                return False

    def _handle_stale_connection(self):
        """Handle stale connection detected by heartbeat"""
        with self._connection_lock:
            if self._state == ConnectionState.CONNECTED and not self._manual_stop:
                logger.info("Handling stale connection...")
                self._state = ConnectionState.DISCONNECTED
                self._schedule_reconnect()

    def _handle_network_disconnection(self):
        """Handle network disconnection"""
        with self._connection_lock:
            if self._state == ConnectionState.CONNECTED and not self._manual_stop:
                logger.info("Handling network disconnection...")
                self._state = ConnectionState.DISCONNECTED
                self._schedule_reconnect()

    def _wait_for_network_recovery(self):
        """Wait for network to recover before attempting reconnection"""
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

        return False
        """Wrapper for keep_running with proper exception handling"""
        try:
            if self.socket:
                self.socket.keep_running()
        except Exception as e:
            logger.error(f"Error in keep_running: {e!r}")
            if not self._manual_stop:
                self._state = ConnectionState.DISCONNECTED

    def unsubscribe(self, symbols: List[str] = None):
        """Unsubscribe from symbols"""
        with self._connection_lock:
            try:
                if self._state != ConnectionState.CONNECTED or not self.socket:
                    logger.warning("WebSocket not connected. Nothing to unsubscribe.")
                    return

                symbols = symbols or self.symbols
                logger.info(f"Unsubscribing from symbols: {symbols}")
                self.socket.unsubscribe(symbols=symbols, data_type="OnOrders")
                self.socket.unsubscribe(symbols=symbols, data_type="SymbolUpdate")

            except Exception as e:
                logger.error(f"Failed to unsubscribe: {e!r}")

    def on_connect(self):
        """Handle successful connection"""
        with self._connection_lock:
            logger.info("WebSocket connected successfully.")
            self._state = ConnectionState.CONNECTED
            self._retries = 0
            self._last_message_time = time.time()  # Reset message timer

            try:
                # Auto-subscribe to symbols
                self.socket.subscribe(symbols=self.symbols, data_type="OnOrders")
                self.socket.subscribe(symbols=self.symbols, data_type="SymbolUpdate")
            except Exception as e:
                logger.error(f"Subscription during on_connect failed: {e!r}")

    def on_close(self, message):
        """Handle connection close"""
        with self._connection_lock:
            logger.warning(f"WebSocket closed: {message}")

            if self._state != ConnectionState.CLOSING:
                self._state = ConnectionState.DISCONNECTED

            if not self._manual_stop and self._state != ConnectionState.CLOSING:
                logger.info("Connection closed unexpectedly. Will attempt to reconnect.")
                self._schedule_reconnect()
            else:
                logger.info("WebSocket closed intentionally by user. No reconnection.")

    def on_error(self, message):
        """Handle connection error"""
        with self._connection_lock:
            logger.error(f"WebSocket error: {message}")

            if self._state != ConnectionState.CLOSING:
                self._state = ConnectionState.DISCONNECTED

            if not self._manual_stop:
                self._schedule_reconnect()

    def _schedule_reconnect(self):
        """Schedule reconnection in a separate thread to avoid blocking"""
        if self._state == ConnectionState.RECONNECTING:
            logger.info("Reconnection already in progress")
            return

        self._state = ConnectionState.RECONNECTING
        reconnect_thread = threading.Thread(
            target=self._reconnect_with_backoff,
            daemon=True,
            name="WebSocket-Reconnect"
        )
        reconnect_thread.start()

    def _reconnect_with_backoff(self):
        """Reconnect with exponential backoff and network recovery wait"""
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
        time.sleep(delay)

        if not self._manual_stop:
            self.connect()

    def _cleanup_socket(self):
        """Clean up existing socket connection"""
        if self.socket:
            try:
                self.socket.close_connection()
            except Exception as e:
                logger.error(f"Error closing existing socket: {e!r}")
            finally:
                self.socket = None

    def disconnect(self):
        """Properly disconnect and cleanup"""
        with self._connection_lock:
            logger.info("Initiating WebSocket disconnect...")
            self._manual_stop = True
            self._state = ConnectionState.CLOSING

            try:
                if self.socket:
                    self.socket.close_connection()
                    self.socket = None

                # Wait for monitoring threads to finish
                for thread in [self._keep_running_thread, self._heartbeat_thread, self._network_monitor_thread]:
                    if thread and thread.is_alive():
                        thread.join(timeout=5)

                logger.info("WebSocket disconnected successfully.")
                self._state = ConnectionState.DISCONNECTED

            except Exception as e:
                logger.error(f"Failed to disconnect WebSocket: {e!r}")
                self._state = ConnectionState.DISCONNECTED

    def get_connection_state(self):
        """Get current connection state"""
        return self._state

    def is_connected(self):
        """Check if currently connected"""
        return self._state == ConnectionState.CONNECTED

    def _wrap_callback(self, callback):
        """Wrap callback with error handling and message tracking"""

        def safe_callback(message):
            try:
                # Update last message time for heartbeat monitoring
                self._last_message_time = time.time()

                if not isinstance(message, dict):
                    logger.warning(f"Received non-dict message: {message}")
                    return
                callback(message)
            except Exception as e:
                logger.error(f"Exception in on_message_callback: {e!r}")

        return safe_callback

    @staticmethod
    def handle_message(data):
        """Handle incoming WebSocket messages"""
        try:
            # Validate expected keys
            symbol = data.get("symbol")
            ltp = data.get("ltp")
            if symbol is None or ltp is None:
                logger.warning("Missing symbol or ltp in data")
                return

            # Example: interpret and act
            logger.info(f"Received data for {symbol}: LTP={ltp}")

        except Exception as e:
            logger.error(f"Error processing data: {e!r}")
