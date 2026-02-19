from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
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

    option_trend: dict = field(default_factory=lambda: {
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

    derivative_trend: dict = field(default_factory=lambda: {
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
    token: str = None

    current_index_data: Candle = field(default_factory=Candle)
    current_put_data: Candle = field(default_factory=Candle)
    current_call_data: Candle = field(default_factory=Candle)

    # Market and option data
    call_option: Optional[str] = None
    put_option: Optional[str] = None
    current_trading_symbol: Optional[str] = None
    derivative: str = 'NIFTY50-INDEX'
    derivative_current_price: float = 0.0
    derivative_history_df: Optional[pd.DataFrame] = None
    option_history_df: Optional[pd.DataFrame] = None
    last_index_updated: Optional[float] = None

    orders: List[Dict[str, Any]] = field(default_factory=list)
    confirmed_orders: List[Dict[str, Any]] = field(default_factory=list)

    # Position state
    current_position: Optional[str] = None
    previous_position: Optional[str] = None
    current_order_id: Dict[str, int] = field(default_factory=dict)
    current_buy_price: Optional[float] = None
    current_price: Optional[float] = None
    highest_current_price: Optional[float] = None
    positions_hold: int = 0
    order_pending: bool = False
    take_profit_type: Optional[str] = STOP
    # Risk and reward tracking
    index_stop_loss: Optional[float] = None
    stop_loss: Optional[float] = None
    tp_point: Optional[float] = None
    tp_percentage: float = 15.0
    stoploss_percentage: float = -7.0
    original_profit_per: float = 15.0
    original_stoploss_per: float = -7.0
    trailing_first_profit: float = 3.0
    max_profit: float = 30.0
    profit_step: float = 2.0
    loss_step: float = 2.0
    interval: Optional[str] = "2m"
    # Trade confirmation
    current_trade_started_time: Optional[datetime] = None
    last_status_check: Optional[datetime] = None
    current_trade_confirmed: bool = False
    percentage_change: Optional[float] = None
    put_current_close: Optional[float] = None
    call_current_close: Optional[float] = None
    sideway_zone_trade = False
    # Config values
    expiry: int = 0
    lot_size: int = 75
    account_balance: float = 0.0
    max_num_of_option: int = 7500
    lower_percentage: float = 0.01
    cancel_after: int = 10  # minutes

    # Lookbacks
    call_lookback: int = 0
    put_lookback: int = 0
    original_call_lookback: int = 0
    original_put_lookback: int = 0

    # Optional trend & data
    market_trend: Optional[int] = None
    supertrend_reset: Optional[dict] = None
    b_band: Optional[dict] = None
    all_symbols: List[str] = field(default_factory=list)
    option_price_update: Optional[bool] = None
    calculated_pcr: Optional[float] = None
    current_pcr: float = 0.0
    trend: Optional[int] = None
    current_pcr_vol: Optional[float] = None

    # Methods to be injected externally (use Callable type hint)
    current_pnl: Optional[float] = None
    reason_to_exit: Optional[str] = None
    capital_reserve: float = 0

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

    def __post_init__(self):
        assert self.lot_size > 0, "lot_size must be positive"
        assert self.max_num_of_option >= self.lot_size, "max_num_of_option should not be less than lot_size"
        # Add more invariants as needed
