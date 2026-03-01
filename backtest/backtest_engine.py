"""
backtest/backtest_engine.py
============================
Pure-Python backtest engine that replays historical spot candles through
the same signal logic used by the live trading app.

Uses TradeState singleton via state_manager for consistent state access.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd

from backtest.backtest_option_pricer import OptionPricer, PriceSource, atm_strike
from backtest.backtest_candle_debugger import CandleDebugger
from models.trade_state_manager import state_manager
from Utils.Utils import Utils
from Utils.common import (MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
                          MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)

logger = logging.getLogger(__name__)

# ── Market session ─────────────────────────────────────────────────────────────
MARKET_OPEN = time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)
MARKET_CLOSE = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
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
    index_sl: Optional[float] = None  # absolute spot points stop loss (e.g. 100 pts)
    trailing_sl_pct: Optional[float] = None  # trailing SL as % of entry; updates high-water mark
    max_hold_bars: Optional[int] = None  # force-exit after N bars regardless of signal

    # Execution
    slippage_pct: float = 0.0025  # 0.25% slippage on fill
    brokerage_per_lot: float = 40.0  # ₹40/lot round-trip

    # Interval (must match what broker returns)
    interval_minutes: int = 5  # candle interval in minutes

    # Capital
    capital: float = 100_000.0

    # Misc
    sideway_zone_skip: bool = True  # skip sideways zone as in live
    sideway_start: time = field(default_factory=lambda: time(12, 0))
    sideway_end: time = field(default_factory=lambda: time(14, 0))
    use_vix: bool = True  # False → rolling HV from spot candles (offline/faster)

    # Analysis timeframes
    analysis_timeframes: List[str] = field(default_factory=list)

    # Debug
    debug_candles: bool = False
    debug_output_path: str = ""


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

    # Aggregate metrics
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
    debug_log_path: Optional[str] = None

    # Strategy analysis: {timeframe_str → List[BarAnalysis]}
    analysis_data: Dict = field(default_factory=dict)

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

        # Simplified Sharpe
        if len(pnls) > 1:
            mean_r = sum(pnls) / len(pnls)
            std_r = math.sqrt(sum((p - mean_r) ** 2 for p in pnls) / (len(pnls) - 1))
            self.sharpe = Utils.round_off(mean_r / std_r * math.sqrt(252) if std_r else 0.0)

        self.completed = True


# ── Per-candle assessment debug helper ────────────────────────────────────────

def _bt_log_candle_assessment(
        bar_time,
        o: float,
        h: float,
        l: float,
        c: float,
        sig_result: dict,
        current_position,
        history_len: int,
) -> None:
    """
    Emit a comprehensive per-candle DEBUG log showing:
      - OHLC values for this bar
      - Every signal group with its logic, confidence score, and fired status
      - Every rule inside each group
      - Resolved final signal and action taken
      - Current position context
    """
    try:
        ts = f"{bar_time:%d-%b %H:%M}"

        fired = sig_result.get("fired", {})
        rule_results = sig_result.get("rule_results", {})
        confidence = sig_result.get("confidence", {})
        threshold = sig_result.get("threshold", 0.6)
        raw_signal = sig_result.get("signal_value", "WAIT")
        available = sig_result.get("available", False)
        ind_values = sig_result.get("indicator_values", {})

        SEP = "─" * 72
        SEP2 = "· " * 36

        lines = [
            "",
            SEP,
            f"  CANDLE  {ts}  |  O={o:.1f}  H={h:.1f}  L={l:.1f}  C={c:.1f}  "
            f"|  bars={history_len}  |  pos={current_position or 'FLAT'}",
            SEP2,
        ]

        if not available:
            lines.append("  [ENGINE] available=False — not enough data or no rules configured")
            lines.append(SEP)
            logger.debug("\n".join(lines))
            return

        # ── Indicator snapshot ─────────────────────────────────────────
        if ind_values:
            ind_parts = []
            for key, vals in ind_values.items():
                last = vals.get("last")
                prev = vals.get("prev")
                lstr = f"{last:.4f}" if isinstance(last, float) else str(last)
                pstr = f"{prev:.4f}" if isinstance(prev, float) else str(prev)
                ind_parts.append(f"{key}={lstr} (prev={pstr})")
            lines.append("  [INDICATORS]  " + "   ".join(ind_parts))
            lines.append(SEP2)

        # ── Per-group rule breakdown ─────────────────────────────────────────
        GROUP_ORDER = ["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]
        for grp in GROUP_ORDER:
            grp_fired = fired.get(grp, False)
            grp_conf = confidence.get(grp, 0.0)
            grp_rules = rule_results.get(grp, [])

            if not grp_rules:
                continue

            # Status tag
            if grp_fired:
                status = "FIRED ✓"
            elif grp_conf >= threshold:
                status = f"SUPPRESSED (conf {grp_conf:.0%} >= thresh {threshold:.0%})"
            else:
                status = f"blocked (conf {grp_conf:.0%} < thresh {threshold:.0%})"

            lines.append(
                f"  [{grp:10s}]  conf={grp_conf:.0%}  threshold={threshold:.0%}  "
                f"rules={len(grp_rules)}  →  {status}"
            )

            for idx, rr in enumerate(grp_rules):
                rule_str = rr.get("rule", "?")
                passed = rr.get("result", False)
                lhs_val = rr.get("lhs_value")
                rhs_val = rr.get("rhs_value")
                weight = rr.get("weight", 1.0)
                detail = rr.get("detail", "")
                error = rr.get("error", "")

                tick = "✓" if passed else "✗"

                def _fv(v):
                    if v is None:
                        return "N/A"
                    if isinstance(v, float):
                        return f"{v:.4f}"
                    return str(v)

                if error:
                    lines.append(
                        f"    rule[{idx}]  {tick}  {rule_str}  "
                        f"w={weight:.1f}  ERROR: {error}"
                    )
                elif lhs_val is None and rhs_val is None:
                    lines.append(
                        f"    rule[{idx}]  {tick}  {rule_str}  "
                        f"w={weight:.1f}  LHS=N/A  RHS=N/A  (indicator not computed)"
                    )
                else:
                    lines.append(
                        f"    rule[{idx}]  {tick}  {rule_str}  "
                        f"w={weight:.1f}  LHS={_fv(lhs_val)}  RHS={_fv(rhs_val)}  [{detail}]"
                    )

        # ── Resolution ──────────────────────────────────────────────────────
        lines.append(SEP2)
        override = sig_result.get("_bt_override", "")
        override_str = f"  ⚡ OVERRIDE: {override}" if override else ""
        lines.append(
            f"  [RESOLVED]  signal={raw_signal}{override_str}  |  "
            f"explanation={sig_result.get('explanation', '')}"
        )
        lines.append(SEP)

        logger.debug("\n".join(lines))

    except Exception as e:
        logger.debug(f"[_bt_log_candle_assessment] Error building debug log: {e}", exc_info=True)


# ── Backtest Engine ────────────────────────────────────────────────────────────

class BacktestEngine:
    """
    Runs the full backtest using the TradeState singleton for consistent state.

    The engine uses state_manager to access and update the trade state,
    ensuring that all backtest operations are reflected in the same state
    object used by the live trading system.
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

        # Get the trade state singleton
        self.state = state_manager.get_state()

        # Save initial state for restoration after backtest
        self._saved_state = state_manager.save_state()

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
                use_vix=self.config.use_vix,
            )
            if self.config.use_vix:
                pricer.load_vix(
                    self.config.start_date.date(),
                    self.config.end_date.date(),
                    broker=self.broker,
                )
            else:
                logger.info("[BacktestEngine] use_vix=False — skipping VIX fetch; rolling HV will be used")

            self._emit(10, "Loading strategy signals…")
            signal_engine, detector = self._load_signal_engine()

            self._emit(12, "Starting bar-by-bar replay…")

            # Reset state for clean backtest
            state_manager.reset_for_backtest()

            # Run the replay
            result = self._replay(spot_df, pricer, signal_engine, detector)

        except Exception as e:
            logger.error(f"[BacktestEngine.run] {e}", exc_info=True)
            result.error_msg = str(e)
        finally:
            # Restore original state after backtest
            state_manager.restore_state(self._saved_state)

        return result

    # ── Private methods ───────────────────────────────────────────────────

    def _fetch_spot(self) -> Optional[pd.DataFrame]:
        """
        Fetch 1-minute spot data from the broker, then resample to the
        configured interval_minutes.
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
                # Legacy fallback
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

            # Strip tz before .dt.time comparison
            _time_naive = df["time"].dt.tz_localize(None) if df["time"].dt.tz is not None else df["time"]
            df = df[_time_naive.dt.time.between(MARKET_OPEN, MARKET_CLOSE)].copy()
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
            _time_naive = df["time"].dt.tz_localize(None) if df["time"].dt.tz is not None else df["time"]
            df = df[_time_naive.dt.time.between(MARKET_OPEN, MARKET_CLOSE)].copy()
            df = df.sort_values("time").reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"[BacktestEngine._fetch_spot_legacy] {e}", exc_info=True)
            return None

    def _try_fetch_option_history(self, option_symbol: str) -> Optional[pd.DataFrame]:
        """
        Fetch real option OHLCV at 1-min resolution, then resample to the
        target interval_minutes.
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
        """Bar-by-bar replay loop with full per-candle debug logging."""
        import BaseEnums

        cfg = self.config
        result = BacktestResult(config=cfg)

        # Use the singleton state (already set in __init__)
        state = self.state

        # Set initial state from config
        state.derivative = cfg.derivative
        state.lot_size = cfg.lot_size
        state.expiry = 0

        equity = cfg.capital
        trade_no = 0
        _option_cache: Dict[str, Optional[pd.DataFrame]] = {}
        total_bars = len(spot_df)
        history_rows = []

        # ── Per-candle debugger ───────────────────────────────────────────────
        _debugger = CandleDebugger(debug_mode=cfg.debug_candles)

        # ── Per-trade tracking ──────────────────────────────────
        _trailing_sl_high: Optional[float] = None
        _bars_in_trade: int = 0

        # ── Debug counters ────────────────────────────────────────────────────
        _skip_sideway = 0
        _skip_market = 0
        _skip_no_signal = 0
        _skip_in_trade = 0
        _skip_min_bars = 0
        _entry_attempts = 0
        _signals_seen: Dict[str, int] = {}

        logger.info(
            f"[Backtest] Starting replay: {total_bars} bars | "
            f"interval={cfg.interval_minutes}m | "
            f"sideway_skip={cfg.sideway_zone_skip} | "
            f"tp={cfg.tp_pct} | sl={cfg.sl_pct}"
        )

        for i, row in spot_df.iterrows():
            if self._stop_requested:
                result.error_msg = "Backtest cancelled by user."
                break

            ts = row["time"]
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]
            bar_time = ts if isinstance(ts, datetime) else pd.Timestamp(ts).to_pydatetime()
            if hasattr(bar_time, "tzinfo") and bar_time.tzinfo is not None:
                bar_time = bar_time.replace(tzinfo=None)

            # Progress update every 50 bars
            if i % 50 == 0:
                pct = 12 + (i / total_bars) * 85
                self._emit(
                    pct,
                    f"Bar {i}/{total_bars}  |  {bar_time.strftime('%d-%b %H:%M')}"
                    f"  |  Equity ₹{equity:,.0f}  |  Trades: {trade_no}"
                )

            # ── Skip sideway zone ─────────────────────────────────────────────
            if cfg.sideway_zone_skip:
                t = bar_time.time()
                if cfg.sideway_start <= t <= cfg.sideway_end:
                    _skip_sideway += 1
                    _debugger.record(
                        bar_time=bar_time, o=o, h=h, l=l, c=c,
                        sig_result=None, action="SKIP",
                        state=state, bars_in_trade=_bars_in_trade,
                        trailing_sl_high=_trailing_sl_high,
                        skip_reason="SIDEWAY",
                    )
                    continue

            # ── Skip non-market hours ─────────────────────────────────────────
            t = bar_time.time()
            if not (MARKET_OPEN <= t <= MARKET_CLOSE):
                _skip_market += 1
                _debugger.record(
                    bar_time=bar_time, o=o, h=h, l=l, c=c,
                    sig_result=None, action="SKIP",
                    state=state, bars_in_trade=_bars_in_trade,
                    trailing_sl_high=_trailing_sl_high,
                    skip_reason="MARKET_CLOSED",
                )
                continue

            # ── Auto-exit before close ────────────────────────────────────────
            auto_exit_time = datetime.combine(
                bar_time.date(),
                time(15, 30 - AUTO_EXIT_BEFORE_CLOSE_MINUTES)
            )
            if state.current_position and bar_time >= auto_exit_time:
                logger.debug(f"[BT {bar_time:%H:%M}] AUTO-EXIT at market close. pos={state.current_position}")
                result, equity, trade_no = self._close_trade(
                    result, state, bar_time, c, pricer, equity, trade_no, "MARKET_CLOSE"
                )
                state.reset_trade_attributes(current_position=None)
                continue

            # ── Accumulate history buffer ─────────────────────────────────────
            history_rows.append({
                "time": bar_time, "open": o, "high": h, "low": l, "close": c, "volume": 0
            })
            if len(history_rows) > 500:
                history_rows = history_rows[-500:]

            # Need at least 2 bars for crossover detection, 15 for RSI to warm up
            MIN_BARS = 15
            if len(history_rows) < MIN_BARS:
                _skip_min_bars += 1
                _debugger.record(
                    bar_time=bar_time, o=o, h=h, l=l, c=c,
                    sig_result=None, action="SKIP",
                    state=state, bars_in_trade=_bars_in_trade,
                    trailing_sl_high=_trailing_sl_high,
                    skip_reason=f"WARMUP({len(history_rows)}/{MIN_BARS})",
                )
                continue

            hist_df = pd.DataFrame(history_rows)

            # ── Run signal engine ─────────────────────────────────────────────
            sig_result = None
            raw_signal = "WAIT"

            if signal_engine:
                try:
                    # Pass the current position context from state
                    _pos_context = state.current_position

                    sig_result = signal_engine.evaluate(hist_df, current_position=_pos_context)

                    if sig_result and sig_result.get("available", False):
                        fired = sig_result.get("fired", {})

                        # ── Position-aware signal resolution ──────────────────
                        raw_signal = sig_result.get("signal_value", "WAIT")
                        _override_reason = ""

                        current_pos = state.current_position
                        if current_pos is None:
                            # Flat — exit signals are meaningless; pick best entry
                            if raw_signal in ("EXIT_CALL", "EXIT_PUT", "HOLD"):
                                bc_conf = sig_result.get("confidence", {}).get("BUY_CALL", 0.0)
                                bp_conf = sig_result.get("confidence", {}).get("BUY_PUT", 0.0)
                                threshold = sig_result.get("threshold", 0.6)

                                if bc_conf >= threshold and bp_conf >= threshold:
                                    if bc_conf > bp_conf:
                                        raw_signal = "BUY_CALL"
                                        _override_reason = f"flat+conflict→BUY_CALL(conf={bc_conf:.0%})"
                                    elif bp_conf > bc_conf:
                                        raw_signal = "BUY_PUT"
                                        _override_reason = f"flat+conflict→BUY_PUT(conf={bp_conf:.0%})"
                                    else:
                                        raw_signal = "WAIT"
                                        _override_reason = "flat+conflict+tie→WAIT"
                                elif bc_conf >= threshold:
                                    raw_signal = "BUY_CALL"
                                    _override_reason = f"flat:exit→BUY_CALL(conf={bc_conf:.0%})"
                                elif bp_conf >= threshold:
                                    raw_signal = "BUY_PUT"
                                    _override_reason = f"flat:exit→BUY_PUT(conf={bp_conf:.0%})"
                                else:
                                    raw_signal = "WAIT"
                                    _override_reason = f"flat:exit_suppressed(bc={bc_conf:.0%},bp={bp_conf:.0%})"

                        # Patch the signal into the result dict
                        if _override_reason:
                            sig_result = sig_result.copy()
                            sig_result["signal_value"] = raw_signal
                            sig_result["signal"] = raw_signal
                            sig_result["_bt_override"] = _override_reason

                        # Update state with signal result
                        state.option_signal_result = sig_result
                        _signals_seen[raw_signal] = _signals_seen.get(raw_signal, 0) + 1

                        if _override_reason:
                            logger.debug(
                                f"[BT {bar_time:%d-%b %H:%M}] SIGNAL OVERRIDE: "
                                f"engine={sig_result.get('_bt_override', '?')} "
                                f"original={sig_result.get('signal_value', '?')} "
                                f"→ effective={raw_signal}"
                            )
                    else:
                        raw_signal = "WAIT"
                        state.option_signal_result = None

                    # ── Per-candle assessment debug ───────────────────────────
                    if logger.isEnabledFor(logging.DEBUG) and sig_result:
                        _bt_log_candle_assessment(
                            bar_time, o, h, l, c,
                            sig_result, state.current_position, len(history_rows)
                        )

                except Exception as e:
                    logger.warning(f"[BT {bar_time:%H:%M}] SignalEngine error: {e}", exc_info=True)
                    state.option_signal_result = None
                    raw_signal = "WAIT"

            # ── Determine action from signal ──────────────────────────────────
            action = self._signal_to_action(raw_signal, state)

            # ── Build TP/SL debug context ────────────────────────────────
            _tp_sl_debug: Optional[Dict] = None
            if cfg.debug_candles and state.current_position:
                _tp_sl_debug = {"current_option_price": None, "tp_price": None,
                                "sl_price": None, "trailing_sl_price": None,
                                "index_sl_level": None, "tp_hit": False,
                                "sl_hit": False, "trailing_sl_hit": False, "index_sl_hit": False}
                try:
                    _d_strike = getattr(state, "_bt_strike", atm_strike(c, cfg.derivative))
                    _d_opt_type = "CE" if state.current_position == BaseEnums.CALL else "PE"
                    _d_opt_sym = f"{cfg.derivative}{_d_strike}{_d_opt_type}"
                    _d_real_row = self._lookup_real_bar(_option_cache, _d_opt_sym, bar_time)
                    _d_bar = pricer.resolve_bar(bar_time, o, h, l, c, _d_opt_type, _d_real_row, cfg.interval_minutes)
                    _d_cur_price = _d_bar["close"]
                    _tp_sl_debug["current_option_price"] = _d_cur_price
                    _tp_sl_debug["price_source"] = str(_d_bar.get("source", ""))
                    if cfg.tp_pct and state.current_buy_price:
                        tp_p = state.current_buy_price * (1 + cfg.tp_pct)
                        _tp_sl_debug["tp_price"] = tp_p
                        _tp_sl_debug["tp_hit"] = _d_cur_price >= tp_p
                    if cfg.sl_pct and state.current_buy_price:
                        sl_p = state.current_buy_price * (1 - cfg.sl_pct)
                        _tp_sl_debug["sl_price"] = sl_p
                        _tp_sl_debug["sl_hit"] = _d_cur_price <= sl_p
                    if cfg.trailing_sl_pct and _trailing_sl_high:
                        tsl_p = _trailing_sl_high * (1 - cfg.trailing_sl_pct)
                        _tp_sl_debug["trailing_sl_price"] = tsl_p
                        _tp_sl_debug["trailing_sl_hit"] = _d_cur_price <= tsl_p
                    if cfg.index_sl is not None:
                        _e_spot = getattr(state, "_bt_spot_entry", None)
                        if _e_spot:
                            if state.current_position == BaseEnums.CALL:
                                idx_sl_level = _e_spot - cfg.index_sl
                            else:
                                idx_sl_level = _e_spot + cfg.index_sl
                            _tp_sl_debug["index_sl_level"] = idx_sl_level
                            if state.current_position == BaseEnums.CALL:
                                _tp_sl_debug["index_sl_hit"] = c <= idx_sl_level
                            else:
                                _tp_sl_debug["index_sl_hit"] = c >= idx_sl_level
                    # option bar for debug
                    _opt_bar_debug = {
                        "symbol": _d_opt_sym,
                        "open": _d_bar.get("open"), "high": _d_bar.get("high"),
                        "low": _d_bar.get("low"), "close": _d_bar.get("close"),
                        "source": str(_d_bar.get("source", "")),
                    }
                except Exception as _dbe:
                    logger.debug(f"[CandleDebugger] TP/SL context build failed: {_dbe}")
                    _opt_bar_debug = None
            else:
                _opt_bar_debug = None

            # ── Record candle debug snapshot ──────────────────────────────────
            if cfg.debug_candles:
                _debugger.record(
                    bar_time=bar_time, o=o, h=h, l=l, c=c,
                    sig_result=sig_result,
                    action=action,
                    state=state,
                    bars_in_trade=_bars_in_trade,
                    trailing_sl_high=_trailing_sl_high,
                    skip_reason=None,
                    option_bar=_opt_bar_debug,
                    tp_sl_info=_tp_sl_debug,
                )

            # ── Monitor open position ─────────────────────────────────────────
            if state.current_position:
                # Use the ENTRY strike, not the current ATM
                strike = getattr(state, "_bt_strike", atm_strike(c, cfg.derivative))
                opt_type = "CE" if state.current_position == BaseEnums.CALL else "PE"
                opt_sym = f"{cfg.derivative}{strike}{opt_type}"

                real_row = self._lookup_real_bar(_option_cache, opt_sym, bar_time)
                bar = pricer.resolve_bar(bar_time, o, h, l, c, opt_type, real_row, cfg.interval_minutes)
                current_price = bar["close"]

                # ── Check TP ────────────────────────────────────────────────
                if cfg.tp_pct and state.current_buy_price:
                    tp_price = state.current_buy_price * (1 + cfg.tp_pct)
                    if current_price >= tp_price:
                        logger.debug(
                            f"[BT {bar_time:%H:%M}] TP HIT: opt={current_price:.2f} >= tp={tp_price:.2f}"
                        )
                        result, equity, trade_no = self._close_trade(
                            result, state, bar_time, c, pricer, equity, trade_no, "TP",
                            forced_option_price=current_price, forced_source=bar["source"]
                        )
                        state.reset_trade_attributes(current_position=None)
                        result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})
                        continue

                # ── Check SL ────────────────────────────────────────────────
                if cfg.sl_pct and state.current_buy_price:
                    sl_price = state.current_buy_price * (1 - cfg.sl_pct)
                    if current_price <= sl_price:
                        logger.debug(
                            f"[BT {bar_time:%H:%M}] SL HIT: opt={current_price:.2f} <= sl={sl_price:.2f}"
                        )
                        result, equity, trade_no = self._close_trade(
                            result, state, bar_time, c, pricer, equity, trade_no, "SL",
                            forced_option_price=current_price, forced_source=bar["source"]
                        )
                        state.reset_trade_attributes(current_position=None)
                        _trailing_sl_high = None
                        _bars_in_trade = 0
                        result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})
                        continue

                # ── Check trailing SL ───────────────────────────────────────
                if cfg.trailing_sl_pct and state.current_buy_price:
                    _trailing_sl_high = max(_trailing_sl_high or current_price, current_price)
                    trailing_sl_price = _trailing_sl_high * (1 - cfg.trailing_sl_pct)
                    if current_price <= trailing_sl_price:
                        logger.debug(
                            f"[BT {bar_time:%H:%M}] TRAILING SL HIT: "
                            f"opt={current_price:.2f} <= trail={trailing_sl_price:.2f} "
                            f"(peak={_trailing_sl_high:.2f})"
                        )
                        result, equity, trade_no = self._close_trade(
                            result, state, bar_time, c, pricer, equity, trade_no, "TRAILING_SL",
                            forced_option_price=current_price, forced_source=bar["source"]
                        )
                        state.reset_trade_attributes(current_position=None)
                        _trailing_sl_high = None
                        _bars_in_trade = 0
                        result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})
                        continue

                # ── Check index SL ───────────────────────────────────────────
                if cfg.index_sl is not None:
                    entry_spot = getattr(state, "_bt_spot_entry", None)
                    if entry_spot is not None:
                        if state.current_position == BaseEnums.CALL and c <= entry_spot - cfg.index_sl:
                            logger.debug(
                                f"[BT {bar_time:%H:%M}] INDEX SL HIT (CALL): "
                                f"spot={c:.0f} <= entry_spot({entry_spot:.0f}) - index_sl({cfg.index_sl})"
                            )
                            result, equity, trade_no = self._close_trade(
                                result, state, bar_time, c, pricer, equity, trade_no, "INDEX_SL",
                                forced_option_price=current_price, forced_source=bar["source"]
                            )
                            state.reset_trade_attributes(current_position=None)
                            _trailing_sl_high = None
                            _bars_in_trade = 0
                            result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})
                            continue
                        elif state.current_position == BaseEnums.PUT and c >= entry_spot + cfg.index_sl:
                            logger.debug(
                                f"[BT {bar_time:%H:%M}] INDEX SL HIT (PUT): "
                                f"spot={c:.0f} >= entry_spot({entry_spot:.0f}) + index_sl({cfg.index_sl})"
                            )
                            result, equity, trade_no = self._close_trade(
                                result, state, bar_time, c, pricer, equity, trade_no, "INDEX_SL",
                                forced_option_price=current_price, forced_source=bar["source"]
                            )
                            state.reset_trade_attributes(current_position=None)
                            _trailing_sl_high = None
                            _bars_in_trade = 0
                            result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})
                            continue

                # ── Check max hold bars ───────────────────────────────────────
                _bars_in_trade += 1
                if cfg.max_hold_bars and _bars_in_trade >= cfg.max_hold_bars:
                    logger.debug(
                        f"[BT {bar_time:%H:%M}] MAX HOLD BARS HIT: "
                        f"{_bars_in_trade} bars >= {cfg.max_hold_bars}"
                    )
                    result, equity, trade_no = self._close_trade(
                        result, state, bar_time, c, pricer, equity, trade_no, "MAX_HOLD",
                        forced_option_price=current_price, forced_source=bar["source"]
                    )
                    state.reset_trade_attributes(current_position=None)
                    _trailing_sl_high = None
                    _bars_in_trade = 0
                    result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})
                    continue

                # ── Check signal exit ─────────────────────────────────────────
                should_exit = (
                        (state.current_position == BaseEnums.CALL and action in ("EXIT_CALL", "BUY_PUT")) or
                        (state.current_position == BaseEnums.PUT and action in ("EXIT_PUT", "BUY_CALL"))
                )
                if should_exit:
                    logger.debug(
                        f"[BT {bar_time:%H:%M}] SIGNAL EXIT: pos={state.current_position} action={action}"
                    )
                    result, equity, trade_no = self._close_trade(
                        result, state, bar_time, c, pricer, equity, trade_no, "SIGNAL",
                        forced_option_price=current_price, forced_source=bar["source"]
                    )
                    state.reset_trade_attributes(current_position=None)
                    _trailing_sl_high = None
                    _bars_in_trade = 0
                    result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})
                    continue

            # ── Entry logic ───────────────────────────────────────────────────
            if state.current_position is None:
                if action == "BUY_CALL":
                    opt_type = "CE"
                elif action == "BUY_PUT":
                    opt_type = "PE"
                else:
                    _skip_no_signal += 1
                    result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})
                    continue

                _entry_attempts += 1
                strike = atm_strike(c, cfg.derivative)
                opt_sym = f"{cfg.derivative}{strike}{opt_type}"

                real_row = self._lookup_real_bar(_option_cache, opt_sym, bar_time)
                bar = pricer.resolve_bar(bar_time, o, h, l, c, opt_type, real_row, cfg.interval_minutes)
                entry_price = round(bar["close"] * (1 + cfg.slippage_pct), 2)

                # Update state with entry information
                state.current_position = BaseEnums.CALL if opt_type == "CE" else BaseEnums.PUT
                state.current_buy_price = entry_price
                state.put_option = opt_sym if opt_type == "PE" else getattr(state, "put_option", None)
                state.call_option = opt_sym if opt_type == "CE" else getattr(state, "call_option", None)

                # Store backtest-specific attributes (these are not part of the main state)
                # We'll use private attributes that won't interfere with live trading
                object.__setattr__(state, "_bt_entry_time", bar_time)
                object.__setattr__(state, "_bt_spot_entry", c)
                object.__setattr__(state, "_bt_entry_source", bar["source"])
                object.__setattr__(state, "_bt_entry_price", entry_price)
                object.__setattr__(state, "_bt_signal_name", str(raw_signal))
                object.__setattr__(state, "_bt_strike", int(strike))

                # Reset per-trade tracking
                _trailing_sl_high = entry_price
                _bars_in_trade = 0

                logger.info(
                    f"[BT {bar_time:%d-%b %H:%M}] ENTRY #{trade_no + 1}: "
                    f"{opt_type} strike={strike} @ ₹{entry_price:.2f} | "
                    f"spot={c:.0f} | signal={raw_signal} | src={bar['source']}"
                )
            else:
                _skip_in_trade += 1

            result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})

        # ── Final close if still open ─────────────────────────────────────────
        if state.current_position and not spot_df.empty:
            last = spot_df.iloc[-1]
            last_ts = (last["time"] if isinstance(last["time"], datetime)
                       else pd.Timestamp(last["time"]).to_pydatetime())
            if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is not None:
                last_ts = last_ts.replace(tzinfo=None)
            result, equity, trade_no = self._close_trade(
                result, state, last_ts, last["close"], pricer, equity, trade_no, "MARKET_CLOSE"
            )

        # ── Summary diagnostics ───────────────────────────────────────
        _summary = (
            f"[Backtest] REPLAY COMPLETE - {total_bars} total bars processed | "
            f"sideway_skip={_skip_sideway} | market_skip={_skip_market} | "
            f"warmup_skip={_skip_min_bars} | no_signal={_skip_no_signal} | "
            f"in_trade={_skip_in_trade} | entries={_entry_attempts} | "
            f"trades={trade_no} | signals={_signals_seen}"
        )
        logger.info(_summary)

        if _entry_attempts == 0:
            logger.warning(
                "[Backtest] ZERO entry attempts - signal engine never fired BUY_CALL/BUY_PUT. "
                "Check: (1) strategy rules loaded correctly, (2) min_confidence not too high, "
                "(3) enough warmup bars (need >=15 for RSI), "
                "(4) sideway_zone_skip not eating all signal bars."
            )

        self._emit(98, "Finalising statistics…")
        result.finalize()

        # ── Build strategy analysis data for the Analysis tab ─────────────────
        if self.config.analysis_timeframes and not result.error_msg:
            try:
                self._emit(98, "Building strategy analysis…")
                result.analysis_data = self._build_analysis_data(spot_df, signal_engine)
            except Exception as _ae:
                logger.warning(f"[BacktestEngine] Analysis data build failed: {_ae}", exc_info=True)

        # ── Save candle debug log ─────────────────────────────────────────────
        if cfg.debug_candles and len(_debugger) > 0:
            import tempfile
            _dbg_path = cfg.debug_output_path
            if not _dbg_path:
                _ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                _dbg_path = os.path.join(
                    tempfile.gettempdir(),
                    f"backtest_debug_{_ts}.json"
                )
            if _debugger.save(_dbg_path):
                result.debug_log_path = _dbg_path
                self._emit(99, f"Debug log saved → {_dbg_path}")

        self._emit(100, f"Complete — {result.total_trades} trades | Net P&L ₹{result.total_net_pnl:,.0f}")
        return result

    def _build_analysis_data(self, spot_df: pd.DataFrame, signal_engine) -> Dict:
        """
        Re-runs the signal engine on each requested analysis timeframe and
        collects BarAnalysis objects.
        """
        from backtest.backtest_window import BarAnalysis
        from data.candle_store import resample_df

        result: Dict = {}
        if spot_df is None or spot_df.empty or not signal_engine:
            return result

        tfs_to_run = list(dict.fromkeys(self.config.analysis_timeframes))

        for tf_str in tfs_to_run:
            try:
                tf_minutes = self._parse_tf_minutes(tf_str)

                # Resample spot data to this timeframe
                if tf_minutes == self.config.interval_minutes:
                    tf_df = spot_df.copy()
                elif tf_minutes == 1:
                    tf_df = spot_df.copy()
                else:
                    if self.config.interval_minutes == 1:
                        tf_df = resample_df(spot_df, tf_minutes)
                    else:
                        if tf_minutes < self.config.interval_minutes:
                            logger.debug(
                                f"[Analysis] Skipping {tf_str}: cannot upsample from "
                                f"{self.config.interval_minutes}m execution interval"
                            )
                            continue
                        tf_df = resample_df(spot_df, tf_minutes)

                if tf_df is None or tf_df.empty:
                    continue

                # Ensure datetime column
                if not pd.api.types.is_datetime64_any_dtype(tf_df["time"]):
                    tf_df["time"] = pd.to_datetime(tf_df["time"])

                bars: list = []
                history_rows: list = []
                MIN_BARS = 15

                for _, row in tf_df.iterrows():
                    ts = row["time"]
                    bar_time = ts if isinstance(ts, datetime) else pd.Timestamp(ts).to_pydatetime()
                    if hasattr(bar_time, "tzinfo") and bar_time.tzinfo is not None:
                        bar_time = bar_time.replace(tzinfo=None)

                    c = row["close"]
                    history_rows.append({
                        "time": bar_time,
                        "open": row["open"], "high": row["high"],
                        "low": row["low"], "close": c, "volume": 0
                    })
                    if len(history_rows) > 500:
                        history_rows = history_rows[-500:]
                    if len(history_rows) < MIN_BARS:
                        continue

                    hist_df = pd.DataFrame(history_rows)
                    try:
                        sig_result = signal_engine.evaluate(hist_df, current_position=None)
                    except Exception as _se:
                        logger.debug(f"[Analysis {tf_str}] signal eval error: {_se}")
                        continue

                    if not sig_result or not sig_result.get("available", False):
                        continue

                    bars.append(BarAnalysis(
                        timestamp=bar_time,
                        spot_price=c,
                        signal=sig_result.get("signal_value", "WAIT"),
                        confidence=dict(sig_result.get("confidence", {})),
                        rule_results=dict(sig_result.get("rule_results", {})),
                        indicator_values=dict(sig_result.get("indicator_values", {})),
                        timeframe=tf_str,
                    ))

                result[tf_str] = bars
                logger.info(f"[Analysis] {tf_str}: {len(bars)} bars evaluated")

            except Exception as e:
                logger.warning(f"[BacktestEngine._build_analysis_data] {tf_str}: {e}", exc_info=True)

        return result

    @staticmethod
    def _parse_tf_minutes(tf_str: str) -> int:
        """Convert timeframe string like '5m', '60m', '1h' to integer minutes."""
        tf_str = tf_str.strip().lower()
        if tf_str.endswith("h"):
            return int(tf_str[:-1]) * 60
        if tf_str.endswith("m"):
            return int(tf_str[:-1])
        try:
            return int(tf_str)
        except ValueError:
            return 5

    def _signal_to_action(self, signal_value: str, state) -> str:
        """
        Convert a raw signal string directly to an action string.
        """
        import BaseEnums
        try:
            current = getattr(state, "current_position", None)

            # Entry signals — only when flat
            if signal_value == "BUY_CALL" and current is None:
                return "BUY_CALL"
            if signal_value == "BUY_PUT" and current is None:
                return "BUY_PUT"

            # Exit signals — only when in matching position
            if signal_value in ("EXIT_CALL", "BUY_PUT") and current == BaseEnums.CALL:
                return "EXIT_CALL"
            if signal_value in ("EXIT_PUT", "BUY_CALL") and current == BaseEnums.PUT:
                return "EXIT_PUT"

            return "WAIT"
        except Exception as e:
            logger.debug(f"[_signal_to_action] {e}")
            return "WAIT"

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
            slippage_cost = 0.0
            brokerage = self.config.brokerage_per_lot * lots * 2
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
