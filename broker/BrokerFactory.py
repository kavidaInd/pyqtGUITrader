"""
brokers/BrokerFactory.py
========================
Factory for creating broker instances.

Supported brokers (10 total):
    fyers       → FyersBroker       (fyers_apiv3)
    zerodha     → ZerodhaBroker     (kiteconnect)
    dhan        → DhanBroker        (dhanhq)
    angelone    → AngelOneBroker    (smartapi-python + pyotp)
    upstox      → UpstoxBroker      (upstox-python-sdk)
    shoonya     → ShoonyaBroker     (NorenRestApiPy + pyotp)
    kotak       → KotakNeoBroker    (neo_api_client)
    icici       → IciciBroker       (breeze-connect)
    aliceblue   → AliceBlueBroker   (pya3)
    flattrade   → FlattradeBroker   (NorenRestApiPy)
"""

import logging

from broker.AliceBlueBroker import AliceBlueBroker
from broker.AngelOneBroker import AngelOneBroker
from broker.DhanBroker import DhanBroker
from broker.FlattradeBroker import FlattradeBroker
from broker.FyersBroker import FyersBroker
from broker.IciciBroker import IciciBroker
from broker.KotakNeoBroker import KotakNeoBroker
from broker.ShoonyaBroker import ShoonyaBroker
from broker.UpstoxBroker import UpstoxBroker
from broker.ZerodhaBroker import ZerodhaBroker

logger = logging.getLogger(__name__)


class BrokerType:
    FYERS      = "fyers"
    ZERODHA    = "zerodha"
    DHAN       = "dhan"
    ANGELONE   = "angelone"
    UPSTOX     = "upstox"
    SHOONYA    = "shoonya"
    KOTAK      = "kotak"
    ICICI      = "icici"
    ALICEBLUE  = "aliceblue"
    FLATTRADE  = "flattrade"

    ALL = [
        FYERS, ZERODHA, DHAN,
        ANGELONE, UPSTOX, SHOONYA,
        KOTAK, ICICI, ALICEBLUE, FLATTRADE,
    ]

    DISPLAY_NAMES = {
        FYERS:     "Fyers",
        ZERODHA:   "Zerodha (Kite)",
        DHAN:      "Dhan",
        ANGELONE:  "Angel One (SmartAPI)",
        UPSTOX:    "Upstox",
        SHOONYA:   "Shoonya / Finvasia",
        KOTAK:     "Kotak Neo",
        ICICI:     "ICICI Breeze",
        ALICEBLUE: "Alice Blue",
        FLATTRADE: "FlatTrade (Pi)",
    }

    AUTH_METHOD = {
        FYERS:     "oauth",
        ZERODHA:   "oauth",
        DHAN:      "static",
        ANGELONE:  "totp",
        UPSTOX:    "oauth",
        SHOONYA:   "totp",
        KOTAK:     "totp",
        ICICI:     "session",
        ALICEBLUE: "password",
        FLATTRADE: "oauth",
    }

    SUPPORTS_HISTORY = {
        FYERS:     True,
        ZERODHA:   True,
        DHAN:      True,
        ANGELONE:  True,
        UPSTOX:    True,
        SHOONYA:   True,
        KOTAK:     False,
        ICICI:     True,
        ALICEBLUE: False,
        FLATTRADE: True,
    }


class BrokerFactory:

    @staticmethod
    def create(state, broker_setting=None):
        broker_type = "fyers"
        if broker_setting is not None:
            broker_type = getattr(broker_setting, 'broker_type', 'fyers') or 'fyers'
        broker_type = broker_type.strip().lower()

        logger.info(f"BrokerFactory: creating broker '{broker_type}'")

        if broker_type == BrokerType.FYERS:
            return FyersBroker(state=state, broker_setting=broker_setting)
        elif broker_type == BrokerType.ZERODHA:
            return ZerodhaBroker(state=state, broker_setting=broker_setting)
        elif broker_type == BrokerType.DHAN:
            return DhanBroker(state=state, broker_setting=broker_setting)
        elif broker_type == BrokerType.ANGELONE:
            return AngelOneBroker(state=state, broker_setting=broker_setting)
        elif broker_type == BrokerType.UPSTOX:
            return UpstoxBroker(state=state, broker_setting=broker_setting)
        elif broker_type == BrokerType.SHOONYA:
            return ShoonyaBroker(state=state, broker_setting=broker_setting)
        elif broker_type == BrokerType.KOTAK:
            return KotakNeoBroker(state=state, broker_setting=broker_setting)
        elif broker_type == BrokerType.ICICI:
            return IciciBroker(state=state, broker_setting=broker_setting)
        elif broker_type == BrokerType.ALICEBLUE:
            return AliceBlueBroker(state=state, broker_setting=broker_setting)
        elif broker_type == BrokerType.FLATTRADE:
            return FlattradeBroker(state=state, broker_setting=broker_setting)
        else:
            raise ValueError(
                f"Unknown broker_type: '{broker_type}'. Supported: {BrokerType.ALL}"
            )

    @staticmethod
    def get_display_name(broker_type: str) -> str:
        return BrokerType.DISPLAY_NAMES.get(broker_type.lower(), broker_type)

    @staticmethod
    def supports_history(broker_type: str) -> bool:
        return BrokerType.SUPPORTS_HISTORY.get(broker_type.lower(), False)

    @staticmethod
    def get_auth_method(broker_type: str) -> str:
        return BrokerType.AUTH_METHOD.get(broker_type.lower(), "oauth")