"""
backtest/backtest_engine.py
============================
Pure-Python backtest engine that replays historical spot candles through
the same signal logic used by the live trading app.

Architecture
------------
  BacktestEngine.run(config) → BacktestResult

  For each candle in the spot history:
    1.  Feed candle into TrendDetector / DynamicSignalEngine  (re-used live code)
    2.  Determine trade signal (ENTER_CALL / ENTER_PUT / EXIT_* / RESET)
    3.  Resolve option price via OptionPricer (real or BS synthetic)
    4.  Simulate entry / exit / P&L with configurable slippage
    5.  Enforce TP / SL / market-close auto-exit rules
    6.  Emit progress updates via callback

No orders are placed.  No broker connection is required.
Produces a list of BacktestTrade and a BacktestResult summary.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd

from backtest.backtest_option_pricer import OptionPricer, PriceSource, atm_strike
from Utils.Utils import Utils
from Utils.common import (MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
                          MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)

logger = logging.getLogger(__name__)

# ── Market session ─────────────────────────────────────────────────────────────
MARKET_OPEN = time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)  # from Utils.common
MARKET_CLOSE = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)  # from Utils.common
AUTO_EXIT_BEFORE_CLOSE_MINUTES = 5  # exit at 15:25


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class BacktestConfig:
    """All inputs needed to run one backtest."""
    # Date range
    start_date: datetime
    end_date: datetime

    # Instrument
    derivative: str = "NIFTY"
    expiry_type: str = "weekly"  # "weekly" | "monthly"
    lot_size: int = 50
    num_lots: int = 1

    # Strategy (mirrors live settings)
    strategy_slug: Optional[str] = None  # loaded from DB if set
    signal_engine_cfg: Optional[Dict] = None  # raw dict override

    # TP / SL  (% of entry price)
    tp_pct: Optional[float] = None  # e.g. 0.30  → exit at +30%
    sl_pct: Optional[float] = None  # e.g. 0.25  → exit at -25%
    index_sl: Optional[float] = None  # absolute spot stop loss

    # Execution
    slippage_pct: float = 0.0025  # 0.25% slippage on fill
    brokerage_per_lot: float = 40.0  # ₹40/lot round-trip

    # Interval (must match what broker returns)
    interval_minutes: int = 5  # candle interval in minutes

    # Capital
    capital: float = 100_000.0

    # Misc
    sideway_zone_skip: bool = True  # skip 12:00-14:00 as in live


@dataclass
class BacktestTrade:
    """A single completed trade in the backtest."""
    trade_no: int
    direction: str  # "CALL" or "PUT"
    entry_time: datetime
    exit_time: datetime
    spot_entry: float
    spot_exit: float
    strike: int
    option_entry: float  # option price at entry
    option_exit: float  # option price at exit
    lots: int
    lot_size: int
    gross_pnl: float  # (exit - entry) × lots × lot_size
    slippage_cost: float
    brokerage: float
    net_pnl: float  # gross - slippage - brokerage
    entry_source: PriceSource  # REAL or SYNTHETIC
    exit_source: PriceSource
    exit_reason: str  # "TP" | "SL" | "SIGNAL" | "MARKET_CLOSE"
    signal_name: str  # the signal that triggered entry


@dataclass
class BacktestResult:
    """Summary of a completed backtest run."""
    config: BacktestConfig
    trades: List[BacktestTrade] = field(default_factory=list)

    # Aggregate metrics (computed by finalize())
    total_trades: int = 0
    winners: int = 0
    losers: int = 0
    win_rate: float = 0.0
    total_net_pnl: float = 0.0
    max_drawdown: float = 0.0
    avg_net_pnl: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    profit_factor: float = 0.0
    sharpe: float = 0.0

    # Metadata
    synthetic_bars: int = 0  # bars where BS pricing was used
    real_bars: int = 0
    error_msg: Optional[str] = None
    completed: bool = False

    # Equity curve: list of {timestamp, equity} dicts
    equity_curve: List[Dict] = field(default_factory=list)

    def finalize(self):
        """Compute aggregate statistics after all trades are recorded."""
        self.total_trades = len(self.trades)
        if not self.trades:
            self.completed = True
            return

        pnls = [t.net_pnl for t in self.trades]
        self.total_net_pnl = Utils.round_off(sum(pnls))
        self.winners = sum(1 for p in pnls if p > 0)
        self.losers = sum(1 for p in pnls if p <= 0)
        self.win_rate = self.winners / self.total_trades * 100
        self.avg_net_pnl = Utils.round_off(self.total_net_pnl / self.total_trades)
        self.best_trade = Utils.round_off(max(pnls))
        self.worst_trade = Utils.round_off(min(pnls))

        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        self.profit_factor = Utils.round_off(gross_profit / gross_loss) if gross_loss else float("inf")

        # Max drawdown from equity curve
        if self.equity_curve:
            equities = [e["equity"] for e in self.equity_curve]
            peak = equities[0]
            dd = 0.0
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd = min(dd, eq - peak)
            self.max_drawdown = Utils.round_off(dd)

        # Simplified Sharpe (daily returns, risk-free = 0 for brevity)
        if len(pnls) > 1:
            mean_r = sum(pnls) / len(pnls)
            std_r = math.sqrt(sum((p - mean_r) ** 2 for p in pnls) / (len(pnls) - 1))
            self.sharpe = Utils.round_off(mean_r / std_r * math.sqrt(252) if std_r else 0.0)

        self.completed = True


# ── Backtest Engine ────────────────────────────────────────────────────────────

class BacktestEngine:
    """
    Runs the full backtest.

    Designed to run in a QThread:
      engine = BacktestEngine(broker, config)
      engine.progress_callback = lambda pct, msg: ...
      result = engine.run()
    """

    def __init__(self, broker, config: BacktestConfig):
        """
        Parameters
        ----------
        broker  : BaseBroker instance (used to fetch historical spot data)
        config  : BacktestConfig
        """
        self.broker = broker
        self.config = config
        self.progress_callback: Optional[Callable[[float, str], None]] = None
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def _emit(self, pct: float, msg: str):
        if self.progress_callback:
            try:
                self.progress_callback(pct, msg)
            except Exception:
                pass

    def run(self) -> BacktestResult:
        result = BacktestResult(config=self.config)
        try:
            self._emit(0, "Fetching spot history…")
            spot_df = self._fetch_spot()
            if spot_df is None or spot_df.empty:
                result.error_msg = "Could not fetch spot history from broker."
                return result

            self._emit(5, f"Loaded {len(spot_df)} spot candles. Fetching VIX…")
            pricer = OptionPricer(
                derivative=self.config.derivative,
                expiry_type=self.config.expiry_type,
                broker=self.broker,
            )
            pricer.load_vix(
                self.config.start_date.date(),
                self.config.end_date.date(),
                broker=self.broker,
            )

            self._emit(10, "Loading strategy signals…")
            signal_engine, detector = self._load_signal_engine()

            self._emit(12, "Starting bar-by-bar replay…")
            result = self._replay(spot_df, pricer, signal_engine, detector)

        except Exception as e:
            logger.error(f"[BacktestEngine.run] {e}", exc_info=True)
            result.error_msg = str(e)

        return result

    # ── Private ────────────────────────────────────────────────────────────────

    def _fetch_spot(self) -> Optional[pd.DataFrame]:
        """
        Fetch 1-minute spot data from the broker, then resample to the
        configured interval_minutes.

        Always fetching at 1-min resolution means:
        - One broker call regardless of the target timeframe
        - Switching interval_minutes requires no extra API call
        - Brokers that don't support the target interval (e.g. Dhan
          has no 3-min candle) are handled transparently
        - Option history can be resampled from the same 1-min store
        """
        try:
            from data.candle_store import CandleStore, resample_df

            days = (self.config.end_date - self.config.start_date).days + 2

            # Detect broker type for correct symbol/interval translation
            broker_type = getattr(
                getattr(self.broker, "broker_setting", None), "broker_type", None
            )

            store = CandleStore(symbol=self.config.derivative, broker=self.broker)
            ok = store.fetch(days=days, broker_type=broker_type)

            if not ok or store.is_empty():
                # Legacy fallback: fetch at the target interval directly
                logger.warning(
                    "[BacktestEngine._fetch_spot] CandleStore fetch failed — "
                    "falling back to direct broker fetch at target interval."
                )
                return self._fetch_spot_legacy()

            # Resample 1-min → target interval
            if self.config.interval_minutes == 1:
                df = store.get_1min()
            else:
                df = resample_df(store.get_1min(), self.config.interval_minutes)

            if df is None or df.empty:
                return None

            # Ensure datetime type
            if not pd.api.types.is_datetime64_any_dtype(df["time"]):
                df["time"] = pd.to_datetime(df["time"])

            # Filter to requested date range
            df = df[
                (df["time"].dt.date >= self.config.start_date.date()) &
                (df["time"].dt.date <= self.config.end_date.date())
                ].copy()

            df = df[df["time"].dt.time.between(MARKET_OPEN, MARKET_CLOSE)].copy()
            df = df.sort_values("time").reset_index(drop=True)

            logger.info(
                f"[BacktestEngine._fetch_spot] {len(df)} bars "
                f"({self.config.interval_minutes}-min) for {self.config.derivative} "
                f"resampled from 1-min store"
            )
            return df

        except Exception as e:
            logger.error(f"[BacktestEngine._fetch_spot] {e}", exc_info=True)
            return None

    def _fetch_spot_legacy(self) -> Optional[pd.DataFrame]:
        """Direct broker fetch at the target interval (fallback only)."""
        try:
            days = (self.config.end_date - self.config.start_date).days + 2
            df = self.broker.get_history_for_timeframe(
                symbol=self.config.derivative,
                interval=str(self.config.interval_minutes),
                days=days,
            )
            if df is None or df.empty:
                return None
            if not pd.api.types.is_datetime64_any_dtype(df["time"]):
                df["time"] = pd.to_datetime(df["time"])
            df = df[
                (df["time"].dt.date >= self.config.start_date.date()) &
                (df["time"].dt.date <= self.config.end_date.date())
                ].copy()
            df = df[df["time"].dt.time.between(MARKET_OPEN, MARKET_CLOSE)].copy()
            df = df.sort_values("time").reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"[BacktestEngine._fetch_spot_legacy] {e}", exc_info=True)
            return None

    def _try_fetch_option_history(self, option_symbol: str) -> Optional[pd.DataFrame]:
        """
        Fetch real option OHLCV at 1-min resolution, then resample to the
        target interval_minutes.  Returns None when the broker has no data
        for this (typically expired) contract.
        """
        try:
            from data.candle_store import CandleStore, resample_df

            days = (self.config.end_date - self.config.start_date).days + 5
            broker_type = getattr(
                getattr(self.broker, "broker_setting", None), "broker_type", None
            )

            store = CandleStore(symbol=option_symbol, broker=self.broker)
            ok = store.fetch(days=days, broker_type=broker_type)

            if not ok or store.is_empty():
                return None

            # Resample to target interval
            if self.config.interval_minutes == 1:
                df = store.get_1min()
            else:
                df = resample_df(store.get_1min(), self.config.interval_minutes)

            if df is None or df.empty:
                return None

            # Filter to backtest date range
            if not pd.api.types.is_datetime64_any_dtype(df["time"]):
                df["time"] = pd.to_datetime(df["time"])
            df = df[
                (df["time"].dt.date >= self.config.start_date.date()) &
                (df["time"].dt.date <= self.config.end_date.date())
                ]
            df = df.set_index("time")
            return df

        except Exception as e:
            logger.debug(f"[BacktestEngine] Option history unavailable for {option_symbol}: {e}")
        return None

    def _load_signal_engine(self):
        """Load the DynamicSignalEngine and TrendDetector from the active strategy."""
        try:
            from strategy.dynamic_signal_engine import DynamicSignalEngine
            from strategy.trend_detector import TrendDetector
            from strategy.strategy_manager import StrategyManager
            from config import Config

            engine = DynamicSignalEngine()
            if self.config.signal_engine_cfg:
                engine.from_dict(self.config.signal_engine_cfg)
            elif self.config.strategy_slug:
                sm = StrategyManager()
                strategy = sm.get(self.config.strategy_slug)
                if strategy:
                    # sm.get() returns the full strategy dict — unwrap the "engine" key
                    cfg = strategy.get("engine", strategy)
                    engine.from_dict(cfg)
                    logger.info(f"[BacktestEngine] Loaded strategy from slug: {self.config.strategy_slug}")
            else:
                # Load active strategy from DB
                sm = StrategyManager()
                cfg = sm.get_active_engine_config()
                if cfg:
                    engine.from_dict(cfg)

            config_obj = Config()
            detector = TrendDetector(config=config_obj, signal_engine=engine)
            return engine, detector

        except Exception as e:
            logger.error(f"[BacktestEngine._load_signal_engine] {e}", exc_info=True)
            return None, None

    def _replay(
            self,
            spot_df: pd.DataFrame,
            pricer: OptionPricer,
            signal_engine,
            detector,
    ) -> BacktestResult:
        """Bar-by-bar replay loop."""
        from models.trade_state import TradeState
        import BaseEnums

        cfg = self.config
        result = BacktestResult(config=cfg)
        state = TradeState()

        # Apply basic settings to state
        state.derivative = cfg.derivative
        state.lot_size = cfg.lot_size
        state.expiry = 0  # 0 = nearest weekly

        equity = cfg.capital
        trade_no = 0

        # ── Optional: try to load real option data upfront ────────────────────
        # We'll load it lazily per-trade to avoid fetching for every possible strike
        _option_cache: Dict[str, Optional[pd.DataFrame]] = {}

        total_bars = len(spot_df)

        # Running history buffer fed to the detector
        history_rows = []

        for i, row in spot_df.iterrows():
            if self._stop_requested:
                result.error_msg = "Backtest cancelled by user."
                break

            ts = row["time"]
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]
            bar_time = ts if isinstance(ts, datetime) else pd.Timestamp(ts).to_pydatetime()
            # Strip timezone — expiry datetimes are always tz-naive (NSE/IST)
            if hasattr(bar_time, "tzinfo") and bar_time.tzinfo is not None:
                bar_time = bar_time.replace(tzinfo=None)

            # Progress update every 50 bars
            if i % 50 == 0:
                pct = 12 + (i / total_bars) * 85
                self._emit(pct, f"Bar {i}/{total_bars}  |  {bar_time.strftime('%d-%b %H:%M')}"
                                f"  |  Equity ₹{equity:,.0f}"
                                f"  |  Trades: {trade_no}")

            # ── Skip sideway zone ─────────────────────────────────────────────
            if cfg.sideway_zone_skip:
                t = bar_time.time()
                if time(12, 0) <= t <= time(14, 0):
                    continue

            # ── Skip non-market hours ─────────────────────────────────────────
            t = bar_time.time()
            if not (MARKET_OPEN <= t <= MARKET_CLOSE):
                continue

            # ── Auto-exit before close ────────────────────────────────────────
            auto_exit_time = datetime.combine(
                bar_time.date(),
                time(15, 30 - AUTO_EXIT_BEFORE_CLOSE_MINUTES)
            )
            if state.current_position and bar_time >= auto_exit_time:
                result, equity, trade_no = self._close_trade(
                    result, state, bar_time, c, pricer, equity, trade_no, "MARKET_CLOSE"
                )
                state.reset_trade_attributes(current_position=None)
                continue

            # ── Accumulate history and run signal detection ───────────────────
            history_rows.append({"time": bar_time, "open": o, "high": h, "low": l, "close": c, "volume": 0})
            # Keep last 500 bars for indicators
            if len(history_rows) > 500:
                history_rows = history_rows[-500:]

            hist_df = pd.DataFrame(history_rows)

            if detector:
                try:
                    state.derivative_history_df = hist_df
                    trends = detector.detect(hist_df, state, cfg.derivative)
                    state.derivative_trend = trends
                except Exception as e:
                    logger.debug(f"[Backtest] Detector error at {bar_time}: {e}")

            # Run signal engine to populate state flags
            if signal_engine and hasattr(state, 'derivative_trend'):
                try:
                    if hasattr(signal_engine, 'evaluate'):
                        sig_result = signal_engine.evaluate(hist_df)
                        if sig_result:
                            state.option_signal_result = sig_result
                            state.option_signal = sig_result.get('signal')
                            state.dynamic_signals_active = True
                except Exception as e:
                    logger.debug(f"[Backtest] SignalEngine error at {bar_time}: {e}")

            # ── Determine trend ───────────────────────────────────────────────
            trend = self._determine_trend(state)

            # ── Monitor open position ─────────────────────────────────────────
            if state.current_position:
                # Update current option price for this bar
                strike = atm_strike(c, cfg.derivative)
                opt_type = "CE" if state.current_position == BaseEnums.CALL else "PE"
                opt_sym = f"{cfg.derivative}{strike}{opt_type}"

                real_row = self._lookup_real_bar(_option_cache, opt_sym, bar_time)
                bar = pricer.resolve_bar(bar_time, o, h, l, c, opt_type, real_row, cfg.interval_minutes)
                current_price = bar["close"]

                if i not in result.__dict__:
                    pass  # tracking state inline

                # Check TP
                if cfg.tp_pct and state.current_buy_price:
                    tp_price = state.current_buy_price * (1 + cfg.tp_pct)
                    if current_price >= tp_price:
                        result, equity, trade_no = self._close_trade(
                            result, state, bar_time, c, pricer, equity, trade_no, "TP",
                            forced_option_price=current_price, forced_source=bar["source"]
                        )
                        state.reset_trade_attributes(current_position=None)
                        continue

                # Check SL
                if cfg.sl_pct and state.current_buy_price:
                    sl_price = state.current_buy_price * (1 - cfg.sl_pct)
                    if current_price <= sl_price:
                        result, equity, trade_no = self._close_trade(
                            result, state, bar_time, c, pricer, equity, trade_no, "SL",
                            forced_option_price=current_price, forced_source=bar["source"]
                        )
                        state.reset_trade_attributes(current_position=None)
                        continue

                # Check signal exit
                if (state.current_position == BaseEnums.CALL and
                        getattr(state, "should_sell_call", False) or
                        getattr(state, "should_buy_put", False)):
                    result, equity, trade_no = self._close_trade(
                        result, state, bar_time, c, pricer, equity, trade_no, "SIGNAL",
                        forced_option_price=current_price, forced_source=bar["source"]
                    )
                    state.reset_trade_attributes(current_position=None)
                    continue

                if (state.current_position == BaseEnums.PUT and
                        getattr(state, "should_sell_put", False) or
                        getattr(state, "should_buy_call", False)):
                    result, equity, trade_no = self._close_trade(
                        result, state, bar_time, c, pricer, equity, trade_no, "SIGNAL",
                        forced_option_price=current_price, forced_source=bar["source"]
                    )
                    state.reset_trade_attributes(current_position=None)
                    continue

            # ── Entry logic ───────────────────────────────────────────────────
            if state.current_position is None and trend:
                if trend == "ENTER_CALL" and getattr(state, "should_buy_call", False):
                    opt_type = "CE"
                elif trend == "ENTER_PUT" and getattr(state, "should_buy_put", False):
                    opt_type = "PE"
                else:
                    continue

                strike = atm_strike(c, cfg.derivative)
                opt_sym = f"{cfg.derivative}{strike}{opt_type}"
                real_row = self._lookup_real_bar(_option_cache, opt_sym, bar_time)
                bar = pricer.resolve_bar(bar_time, o, h, l, c, opt_type, real_row, cfg.interval_minutes)

                entry_price = bar["close"] * (1 + cfg.slippage_pct)
                entry_price = Utils.round_off(entry_price)

                state.current_position = BaseEnums.CALL if opt_type == "CE" else BaseEnums.PUT
                state.current_buy_price = entry_price
                state.put_option = opt_sym if opt_type == "PE" else state.put_option
                state.call_option = opt_sym if opt_type == "CE" else state.call_option

                # Store entry metadata
                state._bt_entry_time = bar_time
                state._bt_spot_entry = c
                state._bt_entry_source = bar["source"]
                state._bt_entry_price = entry_price
                state._bt_signal_name = str(getattr(state, "option_signal", ""))
                state._bt_strike = int(strike)

            # Equity curve point
            result.equity_curve.append({"timestamp": bar_time, "equity": Utils.round_off(equity)})

        # Final close if still open at end
        if state.current_position and spot_df is not None and not spot_df.empty:
            last = spot_df.iloc[-1]
            last_ts = last["time"] if isinstance(last["time"], datetime) else pd.Timestamp(last["time"]).to_pydatetime()
            result, equity, trade_no = self._close_trade(
                result, state, last_ts, last["close"], pricer, equity, trade_no, "MARKET_CLOSE"
            )

        self._emit(98, "Finalising statistics…")
        result.finalize()
        self._emit(100, f"Complete — {result.total_trades} trades | Net P&L ₹{result.total_net_pnl:,.0f}")
        return result

    def _determine_trend(self, state) -> Optional[str]:
        """Mirror of TradingApp.determine_trend_from_signals for backtest."""
        import BaseEnums
        try:
            if not getattr(state, "dynamic_signals_active", False):
                return None
            signal = getattr(state, "option_signal", None)
            current = getattr(state, "current_position", None)
            previous = getattr(state, "previous_position", None)

            if current is None and previous is None:
                if getattr(state, "should_buy_call", False):
                    return "ENTER_CALL"
                if getattr(state, "should_buy_put", False):
                    return "ENTER_PUT"
            elif current == BaseEnums.CALL:
                if signal in ["EXIT_CALL", "BUY_PUT"]:
                    return "EXIT_CALL"
            elif current == BaseEnums.PUT:
                if signal in ["EXIT_PUT", "BUY_CALL"]:
                    return "EXIT_PUT"
            elif current is None and previous is not None:
                return "RESET"
        except Exception:
            pass
        return None

    def _close_trade(
            self,
            result: BacktestResult,
            state,
            exit_time: datetime,
            spot_exit: float,
            pricer: OptionPricer,
            equity: float,
            trade_no: int,
            exit_reason: str,
            forced_option_price: Optional[float] = None,
            forced_source: Optional[PriceSource] = None,
    ):
        import BaseEnums
        try:
            opt_type = "CE" if state.current_position == BaseEnums.CALL else "PE"
            strike = getattr(state, "_bt_strike", atm_strike(spot_exit, self.config.derivative))
            opt_sym = f"{self.config.derivative}{strike}{opt_type}"

            if forced_option_price is not None:
                exit_price = forced_option_price * (1 - self.config.slippage_pct)
                exit_source = forced_source or PriceSource.SYNTHETIC
            else:
                real_row = {}
                bar = pricer.resolve_bar(exit_time, spot_exit, spot_exit, spot_exit, spot_exit,
                                         opt_type, None, self.config.interval_minutes)
                exit_price = bar["close"] * (1 - self.config.slippage_pct)
                exit_source = bar["source"]

            exit_price = max(0.05, Utils.round_off(exit_price))

            entry_price = getattr(state, "_bt_entry_price", state.current_buy_price or exit_price)
            entry_source = getattr(state, "_bt_entry_source", PriceSource.SYNTHETIC)
            lots = self.config.num_lots
            lot_size = self.config.lot_size

            gross_pnl = (exit_price - entry_price) * lots * lot_size
            slippage_cost = (entry_price + exit_price) * self.config.slippage_pct * lots * lot_size
            brokerage = self.config.brokerage_per_lot * lots * 2  # entry + exit
            net_pnl = Utils.round_off(gross_pnl - slippage_cost - brokerage)

            trade_no += 1
            equity += net_pnl

            trade = BacktestTrade(
                trade_no=trade_no,
                direction=opt_type,
                entry_time=getattr(state, "_bt_entry_time", exit_time),
                exit_time=exit_time,
                spot_entry=getattr(state, "_bt_spot_entry", spot_exit),
                spot_exit=spot_exit,
                strike=strike,
                option_entry=entry_price,
                option_exit=exit_price,
                lots=lots,
                lot_size=lot_size,
                gross_pnl=Utils.round_off(gross_pnl),
                slippage_cost=Utils.round_off(slippage_cost),
                brokerage=Utils.round_off(brokerage),
                net_pnl=net_pnl,
                entry_source=entry_source,
                exit_source=exit_source,
                exit_reason=exit_reason,
                signal_name=getattr(state, "_bt_signal_name", ""),
            )
            result.trades.append(trade)

            if exit_source == PriceSource.SYNTHETIC or entry_source == PriceSource.SYNTHETIC:
                result.synthetic_bars += 1
            else:
                result.real_bars += 1

        except Exception as e:
            logger.error(f"[BacktestEngine._close_trade] {e}", exc_info=True)

        return result, equity, trade_no

    def _lookup_real_bar(
            self,
            cache: Dict,
            opt_sym: str,
            bar_time: datetime,
    ) -> Optional[Dict]:
        """Look up a real option bar from the broker cache (lazy-loaded)."""
        if opt_sym not in cache:
            cache[opt_sym] = self._try_fetch_option_history(opt_sym)

        df = cache[opt_sym]
        if df is None or df.empty:
            return None

        try:
            if bar_time in df.index:
                row = df.loc[bar_time]
                return {"open": row.get("open"), "high": row.get("high"),
                        "low": row.get("low"), "close": row.get("close")}
            # Nearest match within 1 bar interval
            diffs = abs(df.index - bar_time)
            nearest_idx = diffs.argmin()
            if diffs[nearest_idx].seconds <= self.config.interval_minutes * 60 * 2:
                row = df.iloc[nearest_idx]
                return {"open": row.get("open"), "high": row.get("high"),
                        "low": row.get("low"), "close": row.get("close")}
        except Exception:
            pass
        return None

    def _try_fetch_option_history(self, option_symbol: str) -> Optional[pd.DataFrame]:
        try:
            days = (self.config.end_date - self.config.start_date).days + 5
            df = self.broker.get_history_for_timeframe(
                symbol=option_symbol,
                interval=str(self.config.interval_minutes),
                days=days,
            )
            if df is not None and not df.empty:
                if not pd.api.types.is_datetime64_any_dtype(df["time"]):
                    df["time"] = pd.to_datetime(df["time"])
                df = df.set_index("time")
                return df
        except Exception as e:
            logger.debug(f"[Backtest] Option history unavailable: {option_symbol}: {e}")
        return None