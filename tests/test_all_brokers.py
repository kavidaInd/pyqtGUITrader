# tests/test_brokers_no_gui.py
"""
Test brokers without PyQt5 dependency
Run with: python -m pytest tests/test_brokers_no_gui.py -v
"""

import pytest
import logging
from unittest.mock import MagicMock, patch
from typing import Dict, Any

from broker.BrokerFactory import BrokerFactory
from models.trade_state import TradeState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BrokerTester:
    """Test brokers without GUI dependencies"""

    def __init__(self, broker_type: str):
        self.broker_type = broker_type
        self.state = TradeState()
        self.broker = None

    def create_mock_setting(self):
        """Create mock brokerage setting"""
        from gui.brokerage_settings.BrokerageSetting import BrokerageSetting

        setting = BrokerageSetting()
        setting.broker_type = self.broker_type

        # Set test credentials
        creds = {
            "aliceblue": ("test_app_id", "test_secret", "user|pass|1990"),
            "angelone": ("A123456", "test_key", "BASE32SECRET"),
            "dhan": ("test_client", "test_token", ""),
            "flattrade": ("FT12345|key", "test_secret", "https://callback"),
            "icici": ("test_key", "test_secret", ""),
            "kotak": ("test_key", "test_secret", "BASE32SECRET"),
            "shoonya": ("FA12345|vendor", "test_pass", "BASE32SECRET"),
            "upstox": ("test_key", "test_secret", "https://callback"),
            "zerodha": ("test_key", "test_secret", "https://callback"),
            "fyers": ("test_id", "test_secret", "https://callback"),
        }

        if self.broker_type in creds:
            client_id, secret, redirect = creds[self.broker_type]
            setting.client_id = client_id
            setting.secret_key = secret
            setting.redirect_uri = redirect

        return setting

    def test_initialization(self):
        """Test broker initialization"""
        try:
            setting = self.create_mock_setting()
            self.broker = BrokerFactory.create(self.state, setting)
            logger.info(f"✅ {self.broker_type} initialized")
            return True
        except Exception as e:
            logger.error(f"❌ {self.broker_type} init failed: {e}")
            return False

    def test_methods_exist(self):
        """Test all required methods exist"""
        if not self.broker:
            return False

        required = [
            'get_profile', 'get_balance', 'get_history',
            'get_option_current_price', 'get_option_quote',
            'place_order', 'modify_order', 'cancel_order',
            'get_positions', 'get_orderbook', 'is_connected',
            'cleanup', 'create_websocket', 'normalize_tick'
        ]

        for method in required:
            if not hasattr(self.broker, method):
                logger.error(f"❌ Missing method: {method}")
                return False

        logger.info(f"✅ All methods present")
        return True

    def test_constants(self):
        """Test broker constants"""
        if not self.broker:
            return False

        # Check side constants
        assert hasattr(self.broker, 'SIDE_BUY')
        assert hasattr(self.broker, 'SIDE_SELL')

        # Check order type constants
        assert hasattr(self.broker, 'MARKET_ORDER_TYPE')
        assert hasattr(self.broker, 'LIMIT_ORDER_TYPE')

        logger.info(f"✅ Constants present")
        return True


@pytest.mark.parametrize("broker_type", BrokerFactory.BrokerType.ALL)
def test_broker_initialization(broker_type):
    """Test each broker can be initialized"""
    tester = BrokerTester(broker_type)
    assert tester.test_initialization()


@pytest.mark.parametrize("broker_type", BrokerFactory.BrokerType.ALL)
def test_broker_methods(broker_type):
    """Test each broker has required methods"""
    tester = BrokerTester(broker_type)
    if tester.test_initialization():
        assert tester.test_methods_exist()


@pytest.mark.parametrize("broker_type", BrokerFactory.BrokerType.ALL)
def test_broker_constants(broker_type):
    """Test each broker has required constants"""
    tester = BrokerTester(broker_type)
    if tester.test_initialization():
        assert tester.test_constants()


if __name__ == "__main__":
    # Manual testing
    for broker_type in BrokerFactory.BrokerType.ALL:
        print(f"\n{'=' * 50}")
        print(f"Testing {broker_type}")
        print('=' * 50)

        tester = BrokerTester(broker_type)
        if tester.test_initialization():
            tester.test_methods_exist()
            tester.test_constants()