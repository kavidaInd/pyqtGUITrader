"""
Broker Factory Module
=====================
Factory pattern implementation for creating broker instances dynamically.

This module provides a centralized factory class that instantiates the appropriate
broker implementation based on the broker type specified in the configuration.
It supports all ten broker integrations and provides metadata about each broker's
capabilities.

Architecture:
    The BrokerFactory follows the Factory Method design pattern:
        - Encapsulates object creation logic
        - Allows runtime selection of broker implementation
        - Centralizes broker metadata (display names, auth methods, capabilities)

    The BrokerType class acts as an enum-like container for:
        - Broker identifiers (used in configuration)
        - Display names (for UI dropdowns)
        - Authentication methods (for login flow selection)
        - Historical data support (for enabling/disabling features)

Supported Brokers (10 total):
    ┌────────────┬─────────────────┬───────────────┬───────────────┐
    │ Identifier │ Display Name    │ Auth Method   │ Has History   │
    ├────────────┼─────────────────┼───────────────┼───────────────┤
    │ fyers      │ Fyers           │ oauth         │ Yes           │
    │ zerodha    │ Zerodha (Kite)  │ oauth         │ Yes           │
    │ dhan       │ Dhan            │ static        │ Yes           │
    │ angelone   │ Angel One       │ totp          │ Yes           │
    │ upstox     │ Upstox          │ oauth         │ Yes           │
    │ shoonya    │ Shoonya/Finvasia│ totp          │ Yes           │
    │ kotak      │ Kotak Neo       │ totp          │ No            │
    │ icici      │ ICICI Breeze    │ session       │ Yes           │
    │ aliceblue  │ Alice Blue      │ password      │ No            │
    │ flattrade  │ FlatTrade (Pi)  │ oauth         │ Yes           │
    └────────────┴─────────────────┴───────────────┴───────────────┘

Usage:
    broker = BrokerFactory.create(state, broker_setting)
    broker.login()  # Use the created broker instance

Thread Safety:
    The factory itself is stateless and thread-safe. However, the created
    broker instances may have their own thread-safety considerations.
"""

import logging

# Import all broker implementations
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
    """
    Broker type constants and metadata.

    This class serves as an enum-like container for broker identifiers and
    their associated metadata. It centralizes all broker-specific information
    that the application needs to know without instantiating the actual brokers.

    Attributes:
        FYERS, ZERODHA, etc.: String constants for each broker identifier
        ALL: List of all supported broker identifiers
        DISPLAY_NAMES: Mapping from identifier to human-readable name
        AUTH_METHOD: Authentication method used by each broker
        SUPPORTS_HISTORY: Whether broker provides historical data API
    """

    # ── Broker identifiers (used in configuration) ────────────────────────────
    FYERS = "fyers"
    ZERODHA = "zerodha"
    DHAN = "dhan"
    ANGELONE = "angelone"
    UPSTOX = "upstox"
    SHOONYA = "shoonya"
    KOTAK = "kotak"
    ICICI = "icici"
    ALICEBLUE = "aliceblue"
    FLATTRADE = "flattrade"

    # ── Complete list of supported brokers ────────────────────────────────────
    ALL = [
        FYERS, ZERODHA, DHAN,
        ANGELONE, UPSTOX, SHOONYA,
        KOTAK, ICICI, ALICEBLUE, FLATTRADE,
    ]

    # ── Human-readable display names for UI components ────────────────────────
    # Used in dropdown menus, settings dialogs, and status displays
    DISPLAY_NAMES = {
        FYERS: "Fyers",
        ZERODHA: "Zerodha (Kite)",
        DHAN: "Dhan",
        ANGELONE: "Angel One (SmartAPI)",
        UPSTOX: "Upstox",
        SHOONYA: "Shoonya / Finvasia",
        KOTAK: "Kotak Neo",
        ICICI: "ICICI Breeze",
        ALICEBLUE: "Alice Blue",
        FLATTRADE: "FlatTrade (Pi)",
    }

    # ── Authentication method types ───────────────────────────────────────────
    # Each method requires a different login flow in the UI
    # oauth: OAuth2 redirect flow with request_token/access_token
    # static: Static API tokens that don't expire
    # totp: TOTP + MPIN based authentication
    # session: Session token from browser login
    # password: Direct username/password authentication
    AUTH_METHOD = {
        FYERS: "oauth",
        ZERODHA: "oauth",
        DHAN: "static",
        ANGELONE: "totp",
        UPSTOX: "oauth",
        SHOONYA: "totp",
        KOTAK: "totp",
        ICICI: "session",
        ALICEBLUE: "password",
        FLATTRADE: "oauth",
    }

    # ── Historical data support ───────────────────────────────────────────────
    # True: Broker provides get_history() API for backtesting/charting
    # False: Broker does not support historical data (use alternative source)
    SUPPORTS_HISTORY = {
        FYERS: True,
        ZERODHA: True,
        DHAN: True,
        ANGELONE: True,
        UPSTOX: True,
        SHOONYA: True,
        KOTAK: False,  # Kotak Neo API does not provide historical data
        ICICI: True,
        ALICEBLUE: False,  # Alice Blue SDK lacks historical data
        FLATTRADE: True,
    }


class BrokerFactory:
    """
    Factory class for creating broker instances dynamically.

    This factory encapsulates the logic for instantiating the appropriate
    broker implementation based on the broker type specified in the
    brokerage settings. It allows the application to work with any broker
    without hardcoding dependencies.

    The factory is stateless and all methods are static, making it easy to
    use anywhere in the application.

    Example:
        # Create broker from settings
        broker = BrokerFactory.create(state, brokerage_setting)

        # Use broker methods
        if broker:
            profile = broker.get_profile()
            balance = broker.get_balance()

    Note:
        The factory does not handle authentication - the created broker
        instance may require login() or generate_session() to be called
        before it can be used for trading.
    """

    @staticmethod
    def create(state, broker_setting=None):
        """
        Create and return an instance of the appropriate broker class.

        This method examines the broker_type attribute from the broker_setting
        (defaulting to "fyers") and instantiates the corresponding broker class.

        Args:
            state: Shared application state object (TradeState instance)
            broker_setting: BrokerageSetting object containing configuration
                           including broker_type, client_id, secret_key, etc.
                           If None, defaults to Fyers broker.

        Returns:
            An instance of one of the broker classes (FyersBroker, ZerodhaBroker, etc.)

        Raises:
            ValueError: If the specified broker_type is not supported

        Example:
            # From brokerage settings
            broker = BrokerFactory.create(state, settings)

            # With default broker (Fyers)
            broker = BrokerFactory.create(state)

        Note:
            The returned broker instance may not be authenticated. Call
            login() or generate_session() as appropriate for the broker type.
        """
        broker_type = "fyers"
        if broker_setting is not None:
            broker_type = getattr(broker_setting, 'broker_type', 'fyers') or 'fyers'
        broker_type = broker_type.strip().lower()

        logger.info(f"BrokerFactory: creating broker '{broker_type}'")

        # Route to appropriate broker implementation
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
        """
        Get the human-readable display name for a broker type.

        Args:
            broker_type: Broker identifier string (e.g., "fyers", "zerodha")

        Returns:
            str: Human-readable display name, or the original string if not found

        Example:
            >>> BrokerFactory.get_display_name("angelone")
            "Angel One (SmartAPI)"
        """
        return BrokerType.DISPLAY_NAMES.get(broker_type.lower(), broker_type)

    @staticmethod
    def supports_history(broker_type: str) -> bool:
        """
        Check if a broker provides historical data API.

        This is used to enable/disable backtesting and charting features
        that depend on historical data.

        Args:
            broker_type: Broker identifier string

        Returns:
            bool: True if the broker supports historical data, False otherwise

        Example:
            >>> BrokerFactory.supports_history("kotak")
            False
            >>> BrokerFactory.supports_history("fyers")
            True

        Note:
            Brokers without historical data support (Kotak, Alice Blue) will
            need an alternative data source for backtesting and charting.
        """
        return BrokerType.SUPPORTS_HISTORY.get(broker_type.lower(), False)

    @staticmethod
    def get_auth_method(broker_type: str) -> str:
        """
        Get the authentication method used by a broker.

        This information is used by the UI to present the appropriate
        login dialog and flow to the user.

        Args:
            broker_type: Broker identifier string

        Returns:
            str: Authentication method - one of:
                - "oauth": OAuth2 redirect flow
                - "static": Static API token
                - "totp": TOTP + MPIN
                - "session": Session token from browser
                - "password": Direct username/password
                Defaults to "oauth" if broker not found.

        Example:
            >>> BrokerFactory.get_auth_method("dhan")
            "static"
            >>> BrokerFactory.get_auth_method("angelone")
            "totp"
        """
        return BrokerType.AUTH_METHOD.get(broker_type.lower(), "oauth")
