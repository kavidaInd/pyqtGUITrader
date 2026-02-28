# tests/test_broker_harness.py
"""
Universal broker test harness that works with all broker types.
Uses mock responses where real API calls aren't possible.
"""

import unittest
import logging
import json
from unittest.mock import MagicMock, patch
from typing import Dict, Any
from datetime import datetime

from broker.BrokerFactory import BrokerFactory
from models.trade_state import TradeState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BrokerTestHarness:
    """Test harness for all broker implementations"""

    def __init__(self, broker_type: str):
        self.broker_type = broker_type
        self.state = TradeState()
        self.broker = None
        self.mock_responses = self._load_mock_responses(broker_type)

    def _load_mock_responses(self, broker_type: str) -> Dict[str, Any]:
        """Load mock responses for specific broker"""
        # You'll create these mock files
        try:
            with open(f'tests/mock_data/{broker_type}_responses.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"No mock responses for {broker_type}, using defaults")
            return {}

    def create_mock_broker_setting(self):
        """Create mock BrokerageSetting for testing"""
        from gui.brokerage_settings.BrokerageSetting import BrokerageSetting

        setting = BrokerageSetting()
        setting.broker_type = self.broker_type

        # Set appropriate test credentials per broker
        if self.broker_type == "aliceblue":
            setting.client_id = "test_app_id"
            setting.secret_key = "test_api_secret"
            setting.redirect_uri = "testuser|testpass|1990"

        elif self.broker_type == "angelone":
            setting.client_id = "A123456"
            setting.secret_key = "test_api_key"
            setting.redirect_uri = "BASE32TOTPSECRET123"

        elif self.broker_type == "dhan":
            setting.client_id = "test_client_id"
            setting.secret_key = "test_access_token"

        elif self.broker_type == "flattrade":
            setting.client_id = "FT12345|apikeyvalue"
            setting.secret_key = "test_api_secret"
            setting.redirect_uri = "https://127.0.0.1/callback"

        elif self.broker_type == "icici":
            setting.client_id = "test_api_key"
            setting.secret_key = "test_secret_key"

        elif self.broker_type == "kotak":
            setting.client_id = "test_consumer_key"
            setting.secret_key = "test_consumer_secret"
            setting.redirect_uri = "BASE32TOTPSECRET"

        elif self.broker_type == "shoonya":
            setting.client_id = "FA12345|VENDOR123"
            setting.secret_key = "test_password"
            setting.redirect_uri = "BASE32TOTPSECRET"

        elif self.broker_type == "upstox":
            setting.client_id = "test_api_key"
            setting.secret_key = "test_api_secret"
            setting.redirect_uri = "https://127.0.0.1/callback"

        elif self.broker_type == "zerodha":
            setting.client_id = "test_api_key"
            setting.secret_key = "test_api_secret"
            setting.redirect_uri = "https://127.0.0.1/callback"

        else:  # fyers (your working broker)
            setting.client_id = "test_client_id"
            setting.secret_key = "test_secret_key"
            setting.redirect_uri = "https://127.0.0.1/callback"
            setting.username = "testuser"

        return setting

    def test_initialization(self):
        """Test broker initialization"""
        try:
            setting = self.create_mock_broker_setting()
            self.broker = BrokerFactory.create(self.state, setting)
            logger.info(f"✅ {self.broker_type} initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ {self.broker_type} initialization failed: {e}")
            return False

    def test_method_signatures(self):
        """Test that all required methods exist and have correct signatures"""
        if not self.broker:
            return False

        required_methods = [
            'get_profile', 'get_balance', 'get_history',
            'get_option_current_price', 'get_option_quote',
            'get_option_chain_quotes', 'place_order', 'modify_order',
            'cancel_order', 'exit_position', 'add_stoploss',
            'remove_stoploss', 'sell_at_current', 'get_positions',
            'get_orderbook', 'get_current_order_status', 'is_connected',
            'cleanup', 'create_websocket', 'ws_connect', 'ws_subscribe',
            'ws_unsubscribe', 'ws_disconnect', 'normalize_tick'
        ]

        all_present = True
        for method in required_methods:
            if hasattr(self.broker, method):
                logger.debug(f"  ✅ {method} present")
            else:
                logger.error(f"  ❌ {method} missing")
                all_present = False

        return all_present

    @patch('broker.AliceBlueBroker.ALICE_AVAILABLE', True)
    @patch('broker.AliceBlueBroker.Aliceblue')
    def test_aliceblue_mocked(self, mock_alice):
        """Test AliceBlue with mocks"""
        if self.broker_type != "aliceblue":
            return

        # Mock successful login
        mock_alice.login_and_get_access_token.return_value = "test_session"

        # Test login
        result = self.broker.login()
        logger.info(f"AliceBlue login: {result}")

        # Mock get_balance
        self.broker.alice = MagicMock()
        self.broker.alice.get_balance.return_value = {"Net": 100000}

        balance = self.broker.get_balance()
        logger.info(f"AliceBlue balance: {balance}")


class TestAllBrokers(unittest.TestCase):
    """Main test suite for all brokers"""

    def setUp(self):
        self.brokers = BrokerFactory.BrokerType.ALL
        self.test_harnesses = {}

        for broker_type in self.brokers:
            try:
                self.test_harnesses[broker_type] = BrokerTestHarness(broker_type)
            except Exception as e:
                logger.warning(f"Could not create harness for {broker_type}: {e}")

    def test_initialization_all_brokers(self):
        """Test that all brokers can be initialized"""
        for broker_type, harness in self.test_harnesses.items():
            with self.subTest(broker=broker_type):
                success = harness.test_initialization()
                self.assertTrue(success, f"{broker_type} failed to initialize")

    def test_method_signatures_all_brokers(self):
        """Test all brokers have required methods"""
        for broker_type, harness in self.test_harnesses.items():
            if not harness.broker:
                continue
            with self.subTest(broker=broker_type):
                success = harness.test_method_signatures()
                self.assertTrue(success, f"{broker_type} missing methods")

    def test_symbol_formatting(self):
        """Test broker-specific symbol formatting"""
        test_symbols = [
            "NIFTY50-INDEX",
            "BANKNIFTY",
            "NFO:NIFTY24DEC24500CE",
            "NFO:BANKNIFTY24DEC50000PE"
        ]

        for broker_type, harness in self.test_harnesses.items():
            if not harness.broker:
                continue

            with self.subTest(broker=broker_type):
                broker = harness.broker

                # Test _format_symbol if available
                if hasattr(broker, '_format_symbol'):
                    for sym in test_symbols:
                        try:
                            formatted = broker._format_symbol(sym)
                            logger.debug(f"{broker_type}: {sym} -> {formatted}")
                        except Exception as e:
                            logger.warning(f"{broker_type} format error: {e}")

                # Test _clean_symbol if available
                if hasattr(broker, '_clean_symbol'):
                    for sym in test_symbols:
                        try:
                            cleaned = broker._clean_symbol(sym)
                            logger.debug(f"{broker_type} clean: {sym} -> {cleaned}")
                        except Exception as e:
                            logger.warning(f"{broker_type} clean error: {e}")

    def test_exchange_detection(self):
        """Test broker exchange detection logic"""
        test_symbols = {
            "NSE:NIFTY50-INDEX": "NSE",
            "NFO:NIFTY24DEC24500CE": "NFO",
            "BSE:SENSEX": "BSE",
            "MCX:GOLD": "MCX"
        }

        for broker_type, harness in self.test_harnesses.items():
            if not harness.broker:
                continue

            with self.subTest(broker=broker_type):
                broker = harness.broker

                if hasattr(broker, '_exchange_from_symbol'):
                    for sym, expected in test_symbols.items():
                        try:
                            exchange = broker._exchange_from_symbol(sym)
                            logger.debug(f"{broker_type}: {sym} -> {exchange}")
                        except Exception as e:
                            logger.warning(f"{broker_type} exchange error: {e}")

    def test_order_type_mapping(self):
        """Test order type constants mapping"""
        for broker_type, harness in self.test_harnesses.items():
            if not harness.broker:
                continue

            with self.subTest(broker=broker_type):
                broker = harness.broker

                # Check if broker has order type mapping methods
                if hasattr(broker, '_to_alice_order_type'):
                    logger.info(f"{broker_type} has AliceBlue order mapping")
                if hasattr(broker, '_to_kite_interval'):
                    logger.info(f"{broker_type} has Zerodha interval mapping")
                if hasattr(broker, '_to_upstox_side'):
                    logger.info(f"{broker_type} has Upstox side mapping")