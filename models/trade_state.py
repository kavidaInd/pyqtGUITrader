from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Union
from datetime import datetime
import pandas as pd

from BaseEnums import STOP
from models.Candle import Candle

try:
    from dynamic_signal_engine import OptionSignal
    _OPTION_SIGNAL_AVAILABLE = True
except ImportError:
    _OPTION_SIGNAL_AVAILABLE = False


@dataclass
class TradeState:
    """
    Persistent state object for option algo trading.
    Includes dynamic option signal result (BUY_CALL/BUY_PUT/SELL_CALL/SELL_PUT/HOLD/WAIT).
    """

    option_trend: Dict[str, Any] = field(default_factory=lambda: {
        'name': None, 'close': None,
        'super_trend_short': {'trend': None, 'direction': None},
        'super_trend_long':  {'trend': None, 'direction': None},
        'macd': {'histo': None, 'macd': None, 'signal': None, 'direction': None},
        'bb':   {'lower': None, 'middle': None, 'upper': None},
        'rsi': None,
        'macd_bottoming': False, 'macd_topping': False,
        'macd_cross_up': False, 'macd_cross_down': False,
        'rsi_bottoming': False, 'rsi_topping': False,
    })

    derivative_trend: Dict[str, Any] = field(default_factory=lambda: {
        'name': None, 'close': None,
        'super_trend_short': {'trend': None, 'direction': None},
        'super_trend_long':  {'trend': None, 'direction': None},
        'macd': {'histo': None, 'macd': None, 'signal': None, 'direction': None},
        'bb':   {'lower': None, 'middle': None, 'upper': None},
        'rsi': None,
        'macd_bottoming': False, 'macd_topping': False,
        'macd_cross_up': False, 'macd_cross_down': False,
        'rsi_bottoming': False, 'rsi_topping': False,
    })

    token: Optional[str] = field(default=None)
    current_index_data: Candle = field(default_factory=Candle)
    current_put_data:   Candle = field(default_factory=Candle)
    current_call_data:  Candle = field(default_factory=Candle)

    call_option: Optional[str] = field(default=None)
    put_option:  Optional[str] = field(default=None)
    current_trading_symbol: Optional[str] = field(default=None)
    derivative: str = field(default='NIFTY50-INDEX')
    derivative_current_price: float = field(default=0.0)
    derivative_history_df: Optional[pd.DataFrame] = field(default=None)
    option_history_df:     Optional[pd.DataFrame] = field(default=None)
    last_index_updated: Optional[float] = field(default=None)

    orders: List[Dict[str, Any]] = field(default_factory=list)
    confirmed_orders: List[Dict[str, Any]] = field(default_factory=list)

    current_position:   Optional[str] = field(default=None)
    previous_position:  Optional[str] = field(default=None)
    current_order_id:   Dict[str, int] = field(default_factory=dict)
    current_buy_price:  Optional[float] = field(default=None)
    current_price:      Optional[float] = field(default=None)
    highest_current_price: Optional[float] = field(default=None)
    positions_hold: int  = field(default=0)
    order_pending:  bool = field(default=False)
    take_profit_type: Optional[str] = field(default=STOP)

    index_stop_loss:        Optional[float] = field(default=None)
    stop_loss:              Optional[float] = field(default=None)
    tp_point:               Optional[float] = field(default=None)
    tp_percentage:          float = field(default=15.0)
    stoploss_percentage:    float = field(default=-7.0)
    original_profit_per:    float = field(default=15.0)
    original_stoploss_per:  float = field(default=-7.0)
    trailing_first_profit:  float = field(default=3.0)
    max_profit:             float = field(default=30.0)
    profit_step:            float = field(default=2.0)
    loss_step:              float = field(default=2.0)
    interval: Optional[str] = field(default="2m")

    current_trade_started_time: Optional[datetime] = field(default=None)
    last_status_check:   Optional[datetime] = field(default=None)
    current_trade_confirmed: bool = field(default=False)
    percentage_change:   Optional[float] = field(default=None)
    put_current_close:   Optional[float] = field(default=None)
    call_current_close:  Optional[float] = field(default=None)
    sideway_zone_trade:  bool = field(default=False)

    expiry:            int   = field(default=0)
    lot_size:          int   = field(default=75)
    account_balance:   float = field(default=0.0)
    max_num_of_option: int   = field(default=7500)
    lower_percentage:  float = field(default=0.01)
    cancel_after:      int   = field(default=10)

    call_lookback:          int = field(default=0)
    put_lookback:           int = field(default=0)
    original_call_lookback: int = field(default=0)
    original_put_lookback:  int = field(default=0)

    market_trend:        Optional[int]          = field(default=None)
    supertrend_reset:    Optional[Dict[str,Any]] = field(default=None)
    b_band:              Optional[Dict[str,Any]] = field(default=None)
    all_symbols:         List[str]               = field(default_factory=list)
    option_price_update: Optional[bool]          = field(default=None)
    calculated_pcr:      Optional[float]         = field(default=None)
    current_pcr:         float                   = field(default=0.0)
    trend:               Optional[int]           = field(default=None)
    current_pcr_vol:     Optional[float]         = field(default=None)

    current_pnl:     Optional[float] = field(default=None)
    reason_to_exit:  Optional[str]   = field(default=None)
    capital_reserve: float           = field(default=0.0)

    cancel_pending_trade: Optional[Any] = field(default=None)

    # ──────────────────────────────────────────────────────────────────
    # Dynamic option signal result
    # Updated every bar by TrendDetector._evaluate_option_signal().
    #
    # Schema:
    #   {
    #     "signal":       OptionSignal   BUY_CALL | BUY_PUT | SELL_CALL | SELL_PUT | HOLD | WAIT
    #     "signal_value": str            human-readable string
    #     "fired": {
    #         "BUY_CALL":  bool,
    #         "BUY_PUT":   bool,
    #         "SELL_CALL": bool,
    #         "SELL_PUT":  bool,
    #         "HOLD":      bool,
    #     },
    #     "rule_results": { group: [{rule: str, result: bool}, ...], ... }
    #     "conflict":  bool   — BUY_CALL and BUY_PUT both fired
    #     "available": bool   — False when no rules are configured
    #   }
    # ──────────────────────────────────────────────────────────────────
    option_signal_result: Optional[Dict[str, Any]] = field(default=None)

    # ── Convenience properties ─────────────────────────────────────────

    @property
    def option_signal(self) -> str:
        """Current resolved option signal string (e.g. 'BUY_CALL')."""
        if self.option_signal_result and self.option_signal_result.get("available"):
            return self.option_signal_result.get("signal_value", "WAIT")
        return "WAIT"

    @property
    def should_buy_call(self) -> bool:
        return self.option_signal == "BUY_CALL"

    @property
    def should_buy_put(self) -> bool:
        return self.option_signal == "BUY_PUT"

    @property
    def should_sell_call(self) -> bool:
        return self.option_signal == "SELL_CALL"

    @property
    def should_sell_put(self) -> bool:
        return self.option_signal == "SELL_PUT"

    @property
    def should_hold(self) -> bool:
        return self.option_signal == "HOLD"

    @property
    def should_wait(self) -> bool:
        return self.option_signal == "WAIT"

    @property
    def signal_conflict(self) -> bool:
        """True when BUY_CALL and BUY_PUT both fired simultaneously."""
        return bool(self.option_signal_result and self.option_signal_result.get("conflict", False))

    @property
    def dynamic_signals_active(self) -> bool:
        return bool(self.option_signal_result and self.option_signal_result.get("available", False))

    def get_option_signal_snapshot(self) -> Dict[str, Any]:
        """Thread-safe shallow copy of option_signal_result for GUI reads."""
        if not self.option_signal_result:
            return {"signal_value":"WAIT","fired":{},"rule_results":{},"conflict":False,"available":False}
        return dict(self.option_signal_result)

    # ──────────────────────────────────────────────────────────────────

    def reset_trade_attributes(self, current_position: Optional[str], logger=None) -> None:
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
                "reason_to_exit": self.reason_to_exit,
            }
            if logger:
                filtered = {k: v for k, v in trade_log.items() if v is not None}
                logger.info(f"Trade logged: {filtered}")

            self.previous_position = current_position
            self.orders = []; self.confirmed_orders = []
            self.current_position = None
            self.positions_hold = 0
            self.current_trading_symbol = None
            self.current_buy_price = None; self.current_price = None
            self.stop_loss = None; self.index_stop_loss = None; self.tp_point = None
            self.last_status_check = None
            self.stoploss_percentage = self.original_stoploss_per
            self.tp_percentage = self.original_profit_per
            self.call_lookback = self.original_call_lookback
            self.put_lookback  = self.original_put_lookback
            self.current_trade_confirmed = False
            self.current_trade_started_time = None
            self.highest_current_price = None
            self.current_pnl = None; self.percentage_change = None
            self.reason_to_exit = None
            # option_signal_result is refreshed every bar — do NOT reset here

            if logger:
                logger.info("Trade attributes reset.")
        except Exception as e:
            if logger: logger.error(f"Error resetting trade attributes: {e}", exc_info=True)
            else: print(f"Error resetting trade attributes: {e}")

    def to_snapshot(self) -> Dict[str, Any]:
        exclude = {
            'option_trend','derivative_trend','current_index_data',
            'current_put_data','current_call_data','derivative_history_df',
            'option_history_df','orders','confirmed_orders','current_order_id',
            'all_symbols','supertrend_reset','b_band','cancel_pending_trade',
            'option_signal_result',
        }
        snapshot = {}
        for field_name in self.__dataclass_fields__.keys():
            if field_name in exclude: continue
            value = getattr(self, field_name)
            if isinstance(value, (str, int, float, bool, type(None), datetime)):
                snapshot[field_name] = value
            elif isinstance(value, list) and field_name == 'all_symbols':
                snapshot[field_name] = value.copy()
        # Attach option signal summary
        snapshot["option_signal"]   = self.option_signal
        snapshot["signal_conflict"] = self.signal_conflict
        return snapshot

    def __post_init__(self):
        assert self.lot_size > 0, "lot_size must be positive"
        assert self.max_num_of_option >= self.lot_size, "max_num_of_option should not be less than lot_size"