from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Union
from datetime import datetime
import pandas as pd

from BaseEnums import STOP
from models.Candle import Candle


@dataclass
class TradeState:
    """
    Persistent state object for option algo trading, tracking market, order,
    risk, and configuration parameters.
    """

    # Trend data structures
    option_trend: Dict[str, Any] = field(default_factory=lambda: {
        'name': None,
        'close': None,
        'super_trend_short': {'trend': None, 'direction': None},
        'super_trend_long': {'trend': None, 'direction': None},
        'macd': {'histo': None, 'macd': None, 'signal': None, 'direction': None},
        'bb': {'lower': None, 'middle': None, 'upper': None},
        'rsi': None,
        'macd_bottoming': False,
        'macd_topping': False,
        'macd_cross_up': False,
        'macd_cross_down': False,
        'rsi_bottoming': False,
        'rsi_topping': False
    })

    derivative_trend: Dict[str, Any] = field(default_factory=lambda: {
        'name': None,
        'close': None,
        'super_trend_short': {'trend': None, 'direction': None},
        'super_trend_long': {'trend': None, 'direction': None},
        'macd': {'histo': None, 'macd': None, 'signal': None, 'direction': None},
        'bb': {'lower': None, 'middle': None, 'upper': None},
        'rsi': None,
        'macd_bottoming': False,
        'macd_topping': False,
        'macd_cross_up': False,
        'macd_cross_down': False,
        'rsi_bottoming': False,
        'rsi_topping': False
    })

    # Authentication
    token: Optional[str] = field(default=None)

    # Current candle data
    current_index_data: Candle = field(default_factory=Candle)
    current_put_data: Candle = field(default_factory=Candle)
    current_call_data: Candle = field(default_factory=Candle)

    # Market and option data
    call_option: Optional[str] = field(default=None)
    put_option: Optional[str] = field(default=None)
    current_trading_symbol: Optional[str] = field(default=None)
    derivative: str = field(default='NIFTY50-INDEX')
    derivative_current_price: float = field(default=0.0)
    derivative_history_df: Optional[pd.DataFrame] = field(default=None)
    option_history_df: Optional[pd.DataFrame] = field(default=None)
    last_index_updated: Optional[float] = field(default=None)

    # Order management
    orders: List[Dict[str, Any]] = field(default_factory=list)
    confirmed_orders: List[Dict[str, Any]] = field(default_factory=list)

    # Position state
    current_position: Optional[str] = field(default=None)
    previous_position: Optional[str] = field(default=None)
    current_order_id: Dict[str, int] = field(default_factory=dict)
    current_buy_price: Optional[float] = field(default=None)
    current_price: Optional[float] = field(default=None)
    highest_current_price: Optional[float] = field(default=None)
    positions_hold: int = field(default=0)
    order_pending: bool = field(default=False)
    take_profit_type: Optional[str] = field(default=STOP)

    # Risk and reward tracking
    index_stop_loss: Optional[float] = field(default=None)
    stop_loss: Optional[float] = field(default=None)
    tp_point: Optional[float] = field(default=None)
    tp_percentage: float = field(default=15.0)
    stoploss_percentage: float = field(default=-7.0)
    original_profit_per: float = field(default=15.0)
    original_stoploss_per: float = field(default=-7.0)
    trailing_first_profit: float = field(default=3.0)
    max_profit: float = field(default=30.0)
    profit_step: float = field(default=2.0)
    loss_step: float = field(default=2.0)
    interval: Optional[str] = field(default="2m")

    # Trade confirmation
    current_trade_started_time: Optional[datetime] = field(default=None)
    last_status_check: Optional[datetime] = field(default=None)
    current_trade_confirmed: bool = field(default=False)
    percentage_change: Optional[float] = field(default=None)
    put_current_close: Optional[float] = field(default=None)
    call_current_close: Optional[float] = field(default=None)

    # FIX: Changed from bare class attribute to proper dataclass field
    sideway_zone_trade: bool = field(default=False)

    # Config values
    expiry: int = field(default=0)
    lot_size: int = field(default=75)
    account_balance: float = field(default=0.0)
    max_num_of_option: int = field(default=7500)
    lower_percentage: float = field(default=0.01)
    cancel_after: int = field(default=10)  # minutes

    # Lookbacks
    call_lookback: int = field(default=0)
    put_lookback: int = field(default=0)
    original_call_lookback: int = field(default=0)
    original_put_lookback: int = field(default=0)

    # Optional trend & data
    market_trend: Optional[int] = field(default=None)
    supertrend_reset: Optional[Dict[str, Any]] = field(default=None)
    b_band: Optional[Dict[str, Any]] = field(default=None)
    all_symbols: List[str] = field(default_factory=list)
    option_price_update: Optional[bool] = field(default=None)
    calculated_pcr: Optional[float] = field(default=None)
    current_pcr: float = field(default=0.0)
    trend: Optional[int] = field(default=None)
    current_pcr_vol: Optional[float] = field(default=None)

    # Financial metrics
    current_pnl: Optional[float] = field(default=None)
    reason_to_exit: Optional[str] = field(default=None)

    # FIX: Added capital_reserve as proper field
    capital_reserve: float = field(default=0.0)

    # Method to be injected externally
    cancel_pending_trade: Optional[Any] = field(default=None)  # Callable type

    def reset_trade_attributes(self, current_position: Optional[str], logger=None) -> None:
        """
        Reset all the trade-related attributes to their default values and log the trade information, if logger passed.

        :param current_position: The position to store as previous after reset.
        :param logger: Optional logger for info/error.
        """
        try:
            trade_log = {
                "order_id": self.current_order_id,
                "position": self.current_position,
                "symbol": self.current_trading_symbol,
                "start_time": self.current_trade_started_time,
                "end_time": datetime.now(),
                "buy_price": self.current_buy_price,
                "sell_price": self.current_price,
                "highest_price": self.highest_current_price,
                "pnl": self.current_pnl,
                "percentage_change": self.percentage_change,
                "status": self.current_trade_confirmed,
                "reason_to_exit": self.reason_to_exit
            }
            if logger:
                filtered_log = {k: v for k, v in trade_log.items() if v is not None}
                logger.info(f"Trade information logged: {filtered_log}")

            # Reset order and position-related attributes
            self.previous_position = current_position
            self.orders = []
            self.confirmed_orders = []
            self.current_position = None
            self.positions_hold = 0
            self.current_trading_symbol = None
            self.current_buy_price = None
            self.current_price = None
            self.stop_loss = None
            self.index_stop_loss = None
            self.tp_point = None
            self.last_status_check = None
            self.stoploss_percentage = self.original_stoploss_per
            self.tp_percentage = self.original_profit_per

            # Reset lookback periods to original values
            self.call_lookback = self.original_call_lookback
            self.put_lookback = self.original_put_lookback

            # Reset trade status and timing
            self.current_trade_confirmed = False
            self.current_trade_started_time = None
            self.highest_current_price = None

            # Reset financial and performance metrics
            self.current_pnl = None
            self.percentage_change = None

            # Reset the reason for exiting the trade
            self.reason_to_exit = None

            if logger:
                logger.info("Trade attributes have been successfully reset.")

        except Exception as e:
            if logger:
                logger.error(f"Error resetting trade attributes: {e}", exc_info=True)
            else:
                print(f"Error resetting trade attributes: {e}")

    def to_snapshot(self) -> Dict[str, Any]:
        """
        Returns a shallow copy of all scalar fields as a dictionary.
        This is safe for GUI reading without holding locks.

        :return: Dictionary containing a snapshot of the current state
        """
        # List of fields to exclude from snapshot (non-scalar or large objects)
        exclude_fields = {
            'option_trend', 'derivative_trend', 'current_index_data',
            'current_put_data', 'current_call_data', 'derivative_history_df',
            'option_history_df', 'orders', 'confirmed_orders', 'current_order_id',
            'all_symbols', 'supertrend_reset', 'b_band', 'cancel_pending_trade'
        }

        snapshot = {}

        # Get all field names from the dataclass
        for field_name in self.__dataclass_fields__.keys():
            # Skip excluded fields
            if field_name in exclude_fields:
                continue

            value = getattr(self, field_name)

            # Only include scalar values and simple types
            if isinstance(value, (str, int, float, bool, type(None), datetime)):
                snapshot[field_name] = value
            # Include lists only if they contain simple types (for all_symbols etc.)
            elif isinstance(value, list) and field_name == 'all_symbols':
                snapshot[field_name] = value.copy()

        return snapshot

    def __post_init__(self):
        assert self.lot_size > 0, "lot_size must be positive"
        assert self.max_num_of_option >= self.lot_size, "max_num_of_option should not be less than lot_size"
        # Add more invariants as needed