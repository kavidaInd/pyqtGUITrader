import logging
from typing import Optional, Any

import BaseEnums
from Broker import Broker
from Utils.OptionUtils import OptionUtils
from Utils.Utils import Utils
from data.websocket_manager import WebSocketManager
from gui.DailyTradeSetting import DailyTradeSetting
from gui.ProfitStoplossSetting import ProfitStoplossSetting
from models.trade_state import TradeState
from strategy.trend_detector import TrendDetector
from trade.order_executor import OrderExecutor
from trade.position_monitor import PositionMonitor

logger = logging.getLogger(__name__)


def safe_last(val):
    """Return last element if val is list/tuple and not empty, else just val or None."""
    if isinstance(val, (list, tuple)) and val:
        return val[-1]
    return val


class TradingApp:
    def __init__(self, config: Any, trading_mode_var: Optional[Any] = None, broker_setting: Optional[Any] = None):
        self.state = TradeState()
        self.config = config
        self.broker = Broker(state=self.state, broker_setting=broker_setting)
        self.trade_config = DailyTradeSetting()
        self.profit_loss_config = ProfitStoplossSetting()
        self.state.cancel_pending_trade = self.cancel_pending_trade

        self.detector = TrendDetector(config=self.config)
        self.executor = OrderExecutor(broker_api=self.broker, config=self.config)
        self.monitor = PositionMonitor()
        self.ws = WebSocketManager(
            token=self.state.token,
            client_id=getattr(broker_setting, "client_id", "") if broker_setting else "",
            on_message_callback=self.on_message
        )
        self.trading_mode_var = trading_mode_var

        # Ensure confirmed_orders is always a list
        if not hasattr(self.state, "confirmed_orders"):
            self.state.confirmed_orders = []

    def get_trading_mode(self) -> str:
        if self.trading_mode_var is None:
            return "algo"
        return self.trading_mode_var.get()

    def run(self) -> None:
        logger.info("Starting trading app...")
        try:
            self.initialize_market_state()
            self.subscribe_market_data()
        except Exception as e:
            logger.critical(f"Unhandled exception during run: {e!r}", exc_info=True)

    def initialize_market_state(self) -> None:
        try:
            self.apply_settings_to_state()
            self.state.derivative_current_price = self.broker.get_option_current_price(self.state.derivative)
            logger.info(f"Initial price for {self.state.derivative}: {self.state.derivative_current_price}")
        except Exception as price_error:
            logger.error(f"Failed to get initial price: {price_error!r}", exc_info=True)

    def subscribe_market_data(self) -> None:
        try:
            if self.state.derivative_current_price is not None:
                self.state.put_option = OptionUtils.get_option_at_price(
                    self.state.derivative_current_price,
                    op_type="PE", expiry=self.state.expiry,
                    lookback=self.state.put_lookback)

                self.state.call_option = OptionUtils.get_option_at_price(
                    self.state.derivative_current_price,
                    op_type="CE", expiry=self.state.expiry,
                    lookback=self.state.call_lookback)

            self.state.all_symbols = list(filter(None, [
                self.symbol_full(self.state.derivative),
                self.symbol_full(self.state.put_option),
                self.symbol_full(self.state.call_option)
            ]))

            self.ws.symbols = self.state.all_symbols
            self.ws.connect()
        except Exception as ws_error:
            logger.error(f"WebSocket connection/subscription failed: {ws_error!r}", exc_info=True)

    def on_message(self, message: dict) -> None:
        try:
            if message and isinstance(message, dict) and message.get("symbol"):
                symbol = message.get("symbol")
                ltp = message.get("ltp")
                ask_price = message.get("ask_price")
                bid_price = message.get("bid_price")
                if ltp is None:
                    logger.warning(f"LTP missing for symbol {symbol}. Message: {message}")
                    return

                self.update_market_state(symbol, ltp, ask_price, bid_price)
                self.monitor.update_trailing_sl_tp(self.broker, self.state)
                self.evaluate_trend_and_decision()
                self.monitor_active_trade_status()
                self.monitor_profit_loss_status()
            else:
                logger.warning(f"Malformed or empty message received: {message}")

        except Exception as e:
            logger.error(f"Exception in on_message: {e!r}, Message: {message}", exc_info=True)

    def update_market_state(self, symbol: str, ltp: float, ask_price: float, bid_price: float) -> None:
        if symbol == self.symbol_full(self.state.derivative):
            self.state.derivative_current_price = ltp
        elif symbol == self.symbol_full(self.state.put_option):
            self.state.put_current_close = ask_price if self.state.current_position else bid_price
        elif symbol == self.symbol_full(self.state.call_option):
            self.state.call_current_close = ask_price if self.state.current_position else bid_price

        if self.state.current_position:
            cp = self.state.current_position
            self.state.current_price = self.state.call_current_close \
                if cp == BaseEnums.CALL else self.state.put_current_close

    def evaluate_trend_and_decision(self) -> None:
        try:
            if not Utils.is_history_updated(last_updated=self.state.last_index_updated, interval=self.state.interval):
                if not self.state.order_pending:
                    self.state.order_pending = True
                    self.state.derivative_history_df = self.broker.get_history(symbol=self.state.derivative,
                                                                               interval=self.state.interval)
                    if self.state.derivative_history_df is not None and not self.state.derivative_history_df.empty:
                        self.state.last_index_updated = self.state.derivative_history_df["Time"].iloc[-1]
                        self.state.derivative_trend = self.detector.detect(
                            self.state.derivative_history_df, self.state, self.state.derivative)
                        if getattr(self.config, "use_long_st", False):
                            trend_data = self.state.derivative_trend.get('super_trend_long', {})
                        else:
                            trend_data = self.state.derivative_trend.get('super_trend_short', {})
                        trend = int(safe_last(trend_data.get('direction'))) \
                            if safe_last(trend_data.get('direction')) is not None else None

                        symbol = self.state.call_option if trend == 1 else self.state.put_option
                        self.state.option_history_df = self.broker.get_history(symbol=symbol,
                                                                               interval=self.state.interval)
                        if self.state.option_history_df is not None and not self.state.option_history_df.empty:
                            self.state.option_trend = self.detector.detect(self.state.option_history_df, self.state,
                                                                           symbol)
                    self.state.order_pending = False
                # print(self.state.derivative_trend)
            if self.get_trading_mode() == "algo":
                self.state.trend = self.determine_trend_logic()
                self.execute_based_on_trend()
        except Exception as trend_error:
            logger.info(f"Trend detection or decision logic error: {trend_error!r}", exc_info=True)

    def monitor_active_trade_status(self) -> None:
        try:
            if not self.state.current_trade_confirmed or self.get_trading_mode() != "algo":
                return

            index_stop_loss = getattr(self.state, "index_stop_loss", None)
            current_derivative_price = self.state.derivative_current_price
            trend = self.state.trend
            if self.state.current_trade_confirmed:
                if Utils.is_near_market_close(buffer_minutes=5):
                    if self.state.current_position:
                        logger.info("Market close approaching. Exiting active position.")
                        self.state.reason_to_exit = "Auto-exit before market close."
                        self.executor.exit_position(self.state)
                        return
                if self.state.current_position == BaseEnums.PUT:
                    if index_stop_loss is not None and current_derivative_price >= index_stop_loss:
                        self.state.reason_to_exit = "PUT exit: Derivative crossed above supertrend."
                        self.executor.exit_position(self.state)
                    elif trend in {BaseEnums.BULLISH, BaseEnums.ENTER_CALL, BaseEnums.EXIT_PUT}:
                        self.executor.exit_position(self.state)
                elif self.state.current_position == BaseEnums.CALL:
                    if index_stop_loss is not None and current_derivative_price <= index_stop_loss:
                        self.state.reason_to_exit = "CALL exit: Derivative dropped below ST."
                        self.executor.exit_position(self.state)
                    elif trend in {BaseEnums.BEARISH, BaseEnums.ENTER_PUT, BaseEnums.EXIT_CALL}:
                        self.executor.exit_position(self.state)
            else:
                if Utils.is_near_market_close(buffer_minutes=5):
                    if self.state.current_position:
                        logger.info("Market close approaching. Canceling active position.")
                        self.cancel_pending_trade()
                        return

                if self.state.current_position == BaseEnums.PUT:
                    if self.state.trend in {BaseEnums.BULLISH, BaseEnums.ENTER_CALL, BaseEnums.CANCEL_PUT}:
                        self.cancel_pending_trade()
                elif self.state.current_position == BaseEnums.CALL:
                    if self.state.trend in {BaseEnums.BEARISH, BaseEnums.ENTER_PUT, BaseEnums.CANCEL_CALL}:
                        self.cancel_pending_trade()
        except Exception as e:
            logger.error(f"Error monitoring active trade status: {e!r}", exc_info=True)

    def monitor_profit_loss_status(self) -> None:
        try:
            if not self.state.current_trade_confirmed:
                return

            stop_loss = getattr(self.state, "stop_loss", None)
            tp_point = getattr(self.state, "tp_point", None)
            current_price = getattr(self.state, "current_price", None)

            if stop_loss is not None and current_price is not None and current_price <= stop_loss:
                self.state.reason_to_exit = f"{self.state.current_position} exit: Option price is below the stop loss."
                self.executor.exit_position(self.state)
            elif tp_point is not None and current_price is not None and current_price >= tp_point:
                self.state.reason_to_exit = f"{self.state.current_position} exit: Target profit hit."
                self.executor.exit_position(self.state)
        except Exception as e:
            logger.error(f"Error monitoring profit/loss status: {e!r}", exc_info=True)

    def determine_trend_logic(self) -> Optional[tuple]:
        try:
            dc = self.state.derivative_current_price  # Current price
            trend = None
            dt = self.state.derivative_trend or {}

            # Extract trend data
            short_st = dt.get("super_trend_short", {})
            long_st = dt.get("super_trend_long", {})
            macd = dt.get("macd", {})
            bb = dt.get("bb", {})
            rsi = dt.get("rsi", {})

            # Configuration flags
            # logger.info(self.config)
            entry_use_short_st = getattr(self.config, "use_short_st_entry", False)
            entry_use_long_st = getattr(self.config, "use_long_st_entry", False)
            entry_use_macd = getattr(self.config, "use_macd_entry", False)
            entry_use_rsi = getattr(self.config, "use_rsi_entry", False)
            entry_use_bb_entry = getattr(self.config, "bb_entry", False)

            exit_use_short_st = getattr(self.config, "use_short_st_exit", False)
            exit_use_long_st = getattr(self.config, "use_long_st_exit", False)
            exit_use_macd = getattr(self.config, "use_macd_exit", False)
            exit_use_rsi = getattr(self.config, "use_rsi_exit", False)
            exit_use_bb_exit = getattr(self.config, "bb_exit", False)

            # logger.info(f"{entry_use_macd},{entry_use_rsi},{entry_use_short_st},{exit_use_long_st}")
            # === Extract and cast indicators safely ===
            short_st_d = safe_last(short_st.get("direction")) if entry_use_short_st else None
            short_st_t = safe_last(short_st.get("trend")) if entry_use_short_st else None
            long_st_d = safe_last(long_st.get("direction")) if entry_use_long_st else None
            macd_d = safe_last(macd.get("histogram")) if entry_use_macd else None
            bb_upper = safe_last(bb.get("upper")) if entry_use_bb_entry else None
            bb_lower = safe_last(bb.get("lower")) if entry_use_bb_entry else None
            rsi_data = safe_last(rsi) if entry_use_rsi else None

            # === Type casting ===
            try:
                short_st_d = int(short_st_d) if short_st_d is not None else None
                short_st_t = float(short_st_t) if short_st_t is not None else None
                long_st_d = int(long_st_d) if long_st_d is not None else None
                macd_d = float(macd_d) if macd_d is not None else None
                bb_upper = float(bb_upper) if bb_upper is not None else None
                bb_lower = float(bb_lower) if bb_lower is not None else None
                rsi_data = float(rsi_data) if rsi_data is not None else None
            except (ValueError, TypeError) as e:
                logger.warning(f"Type casting error: {e}")
            # === EXIT Conditions ===
            if self.state.current_position == BaseEnums.CALL:
                if exit_use_short_st and short_st_d == -1:
                    trend = BaseEnums.EXIT_CALL
                    self.state.reason_to_exit = "Short SuperTrend turned BEARISH"
                elif exit_use_macd and macd_d < 0:
                    trend = BaseEnums.EXIT_CALL
                    self.state.reason_to_exit = "MACD turned BEARISH"
                elif exit_use_rsi and rsi_data >= 90:
                    trend = BaseEnums.EXIT_CALL
                    self.state.reason_to_exit = "RSI value >= 90"
                elif exit_use_short_st and short_st_t and short_st_t > dc:
                    trend = BaseEnums.EXIT_CALL
                    self.state.reason_to_exit = "Short SuperTrend value > current price"
                elif exit_use_bb_exit and bb_upper and bb_upper <= dc:
                    trend = BaseEnums.EXIT_CALL
                    self.state.reason_to_exit = "Price >= Bollinger Upper Band"

            elif self.state.current_position == BaseEnums.PUT:
                if exit_use_short_st and short_st_d == 1:
                    trend = BaseEnums.EXIT_PUT
                    self.state.reason_to_exit = "Short SuperTrend turned BULLISH"
                elif exit_use_macd and macd_d > 0:
                    trend = BaseEnums.EXIT_PUT
                    self.state.reason_to_exit = "MACD turned BULLISH"
                elif exit_use_short_st and short_st_t and short_st_t < dc:
                    trend = BaseEnums.EXIT_PUT
                    self.state.reason_to_exit = "Short SuperTrend value < current price"
                elif exit_use_rsi and rsi_data <= 10:
                    trend = BaseEnums.EXIT_PUT
                    self.state.reason_to_exit = "RSI value <= 10"
                elif exit_use_bb_exit and bb_lower and bb_lower >= dc:
                    trend = BaseEnums.EXIT_PUT
                    self.state.reason_to_exit = "Price <= Bollinger Lower Band"

            # === ENTRY Conditions ===
            elif self.state.current_position is None and self.state.previous_position is None:
                bullish_signals = []
                bearish_signals = []

                if entry_use_short_st:
                    bullish_signals.append(short_st_d == 1)
                    bearish_signals.append(short_st_d == -1)

                if entry_use_long_st:
                    bullish_signals.append(long_st_d == 1)
                    bearish_signals.append(long_st_d == -1)

                if entry_use_macd:
                    bullish_signals.append(macd_d > 0)
                    bearish_signals.append(macd_d < 0)

                if entry_use_rsi:
                    bullish_signals.append(rsi_data >= 60)
                    bearish_signals.append(rsi_data <= 40)

                # logger.info(f"[DEBUG] Bullish: {bullish_signals}")
                # logger.info(f"[DEBUG] Bearish: {bearish_signals}")

                # Filter None values and evaluate
                bullish_signals = [bool(val) for val in bullish_signals if val is not None]
                bearish_signals = [bool(val) for val in bearish_signals if val is not None]

                if bullish_signals and all(bullish_signals):
                    trend = BaseEnums.ENTER_CALL
                elif bearish_signals and all(bearish_signals):
                    trend = BaseEnums.ENTER_PUT

            # === RESET Condition ===
            elif self.state.current_position is None and self.state.previous_position in {BaseEnums.CALL,
                                                                                          BaseEnums.PUT}:
                if self.state.previous_position == BaseEnums.CALL:
                    if (entry_use_short_st and short_st_d == -1) or (entry_use_macd and macd_d < 0):
                        trend = BaseEnums.RESET_PREVIOUS_TRADE
                elif self.state.previous_position == BaseEnums.PUT:
                    if (entry_use_short_st and short_st_d == 1) or (entry_use_macd and macd_d > 0):
                        trend = BaseEnums.RESET_PREVIOUS_TRADE

            # Final result
            if trend:
                logger.info(f"Determined trend: {trend} | Reason: {getattr(self.state, 'reason_to_exit', '')}")
            return trend

        except Exception as e:
            logger.error(f"Error determining trend logic: {e}", exc_info=True)
            return None

    def execute_based_on_trend(self) -> None:
        try:
            if self.get_trading_mode() != "algo":
                return

            if Utils.check_sideway_time() and not getattr(self.state, "sideway_zone_trade", False):
                logger.info("Sideways period (12:00–2:00). Skipping trading decision.")
                return

            if not Utils.is_market_open():
                logger.info("Market is closed. Skipping trading execution.")
                return

            if Utils.is_near_market_close(buffer_minutes=5):
                logger.info("Too close to market close. Skipping trading decision.")
                return

            trend = self.state.trend
            if self.state.current_position is None:
                if trend == BaseEnums.ENTER_CALL:
                    self.executor.buy_option(self.state, option_type=BaseEnums.CALL)
                    if self.state.call_option not in self.state.all_symbols:
                        self.subscribe_market_data()

                elif trend == BaseEnums.ENTER_PUT:
                    self.executor.buy_option(self.state, option_type=BaseEnums.PUT)
                    if self.state.put_option not in self.state.all_symbols:
                        self.subscribe_market_data()

                elif trend == BaseEnums.RESET_PREVIOUS_TRADE:
                    self.state.previous_position = None
        except Exception as exec_error:
            logger.error(f"Order execution failed: {exec_error!r}", exc_info=True)

    def cancel_pending_trade(self) -> None:
        try:
            if not self.state.orders:
                logger.info("No pending orders to cancel.")
                return

            logger.info(f"Cancelling {len(self.state.orders)} pending order(s).")

            remaining_orders = []
            confirmed_orders = []
            confirmed_found = False

            for order in self.state.orders:
                order_id = order.get("id")
                try:
                    status_list = self.broker.get_current_order_status(order_id)
                    if status_list:
                        order_status = status_list[0].get("status")
                        if order_status == BaseEnums.ORDER_STATUS_CONFIRMED:
                            confirmed_found = True
                            confirmed_orders.append(order)
                            logger.info(f"✅ Order {order_id} confirmed. Will not cancel.")
                            continue

                    self.broker.cancel_order(order_id=order_id)
                    logger.info(f"Cancelled order ID: {order_id}")

                except Exception as e:
                    logger.error(f"❌ Failed to cancel order ID {order_id}: {e}", exc_info=True)
                    remaining_orders.append(order)

            self.state.orders = remaining_orders

            if not hasattr(self.state, "confirmed_orders"):
                self.state.confirmed_orders = []
            if confirmed_orders:
                self.state.confirmed_orders.extend(confirmed_orders)

            if confirmed_found:
                self.state.current_trade_confirmed = True
                logger.info("✔️ Trade marked as confirmed due to confirmed orders.")
            else:
                self.state.reset_trade_attributes(current_position=None)

            logger.info("🧹 Pending order cancellation process complete.")

        except Exception as e:
            logger.error(f"🔥 Error in cancel_pending_trade: {e}", exc_info=True)

    @staticmethod
    def symbol_full(symbol: Optional[str]) -> Optional[str]:
        return f"NSE:{symbol}" if symbol and not symbol.startswith("NSE:") else symbol

    def refresh_settings_live(self) -> None:
        self.trade_config.load()
        self.profit_loss_config.load()
        self.apply_settings_to_state()

    def apply_settings_to_state(self) -> None:
        self.state.capital_reserve = getattr(self.trade_config, "capital_reserve", 0)
        self.state.account_balance = self.broker.get_balance(getattr(self.state, "capital_reserve", 0))
        self.state.derivative = getattr(self.trade_config, "derivative", "")
        self.state.expiry = getattr(self.trade_config, "week", "")
        self.state.lot_size = getattr(self.trade_config, "lot_size", 0)
        self.state.call_lookback = getattr(self.trade_config, "call_lookback", 0)
        self.state.put_lookback = getattr(self.trade_config, "put_lookback", 0)
        self.state.interval = getattr(self.trade_config, "history_interval", "")
        self.state.max_num_of_option = getattr(self.trade_config, "max_num_of_option", 0)
        self.state.lower_percentage = getattr(self.trade_config, "lower_percentage", 0)
        self.state.cancel_after = getattr(self.trade_config, "cancel_after", 0)
        self.state.sideway_zone_trade = getattr(self.trade_config, "sideway_zone_trade", False)

        plc = self.profit_loss_config
        self.state.tp_percentage = self.state.original_profit_per = getattr(plc, "tp_percentage", 0)
        self.state.stoploss_percentage = self.state.original_stoploss_per = getattr(plc, "stoploss_percentage", 0)
        self.state.trailing_first_profit = getattr(plc, "trailing_first_profit", 0)
        self.state.max_profit = getattr(plc, "max_profit", 0)
        self.state.profit_step = getattr(plc, "profit_step", 0)
        self.state.loss_step = getattr(plc, "loss_step", 0)
        self.state.take_profit_type = getattr(plc, "profit_type", "absolute")

        logger.info(f"[Settings] Applied trade and P/L configs: capital_reserve={self.state.capital_reserve}, "
                    f"lot_size={self.state.lot_size}, max_num_of_option={self.state.max_num_of_option}, "
                    f"tp_percentage={self.state.tp_percentage}, stoploss_percentage={self.state.stoploss_percentage}")
