"""
backtest/backtest_engine.py
============================
Pure-Python backtest engine replaying historical spot candles through
the live signal logic.

Changes from original:
- _PositionTracker dataclass holds all per-trade mutable state (entry_time,
  spot_entry, strike, opt_type, entry_price, entry_source, signal_name,
  trailing_sl_high, bars_in_trade).  A single tracker.reset() replaces the
  seven scattered object.__setattr__ calls and makes it impossible to leave
  any field stale.
- Auto-exit time: pre-computed once per trading day instead of
  datetime.combine(...) on every single bar.
- _close_trade: returns a NamedTuple CloseResult so callers don't unpack a
  (result, equity, trade_no) tuple by positional index.
- _fetch_spot / _fetch_spot_legacy: date-range and market-hours filtering
  extracted into a single _filter_spot_df() helper called by both paths —
  was duplicated verbatim.
- Removed MARKET_OPEN_TIME = time(9, 15) re-definition; MARKET_OPEN is
  already set at module level from Utils.common constants.
- _bt_log_candle_assessment: guarded by logger.isEnabledFor(logging.DEBUG)
  check before building the expensive multi-line string (was done, confirmed
  present; kept and documented).
- BacktestResult.finalize: profit_factor handles zero gross_loss with
  float('inf') already — confirmed clean.
- Duplicate `broker_type = broker_type` no-op assignment removed from
  _get_historical_option_symbol.
- history_rows buffer trimmed with slice instead of re-assignment to avoid
  creating a new list object every 500 bars.
- _skip_cooldown counter incremented but replay continues (don't skip) so
  the signal engine gets day-1 warm-up data.
- Progress emission interval raised from 50 to 100 bars for lower overhead.
- All f-string logger calls replaced with % formatting.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from Utils.time_utils import IST, ist_now, fmt_display, fmt_stamp
from typing import Callable, Dict, List, NamedTuple, Optional

import pandas as pd

from Utils.OptionUtils import OptionUtils
from Utils.safe_getattr import safe_getattr, safe_hasattr
from Utils.Utils import Utils
from Utils.common import (MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
                          MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
from backtest.backtest_candle_debugger import CandleDebugger
from backtest.backtest_option_pricer import OptionPricer, PriceSource, atm_strike
from data.candle_store import resample_df
from data.candle_store_manager import candle_store_manager
from data.trade_state_manager import state_manager

logger = logging.getLogger(__name__)

MARKET_OPEN  = time(MARKET_OPEN_HOUR,  MARKET_OPEN_MINUTE)
MARKET_CLOSE = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
AUTO_EXIT_BEFORE_CLOSE_MINUTES = 5
COOLDOWN_MINUTES = 15
HISTORY_BUFFER_MAX = 500
MIN_WARMUP_BARS = 15
PROGRESS_INTERVAL = 100   # emit progress every N bars


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class BacktestConfig:
    start_date: datetime
    end_date:   datetime
    derivative: str = "NIFTY"
    expiry_type: str = "weekly"
    lot_size: int = 50
    num_lots: int = 1
    strategy_slug: Optional[str] = None
    signal_engine_cfg: Optional[Dict] = None
    tp_pct:            Optional[float] = None
    sl_pct:            Optional[float] = None
    index_sl:          Optional[float] = None
    trailing_sl_pct:   Optional[float] = None
    max_hold_bars:     Optional[int]   = None
    slippage_pct:      float = 0.0025
    brokerage_per_lot: float = 40.0
    execution_interval_minutes: int = 5
    capital: float = 100_000.0
    sideway_zone_skip: bool = True
    sideway_start: time = field(default_factory=lambda: time(12, 0))
    sideway_end:   time = field(default_factory=lambda: time(14, 0))
    use_vix: bool = True
    analysis_timeframes: List[str] = field(default_factory=list)
    debug_candles: bool = False
    debug_output_path: str = ""


@dataclass
class BacktestTrade:
    trade_no:     int
    direction:    str
    entry_time:   datetime
    exit_time:    datetime
    spot_entry:   float
    spot_exit:    float
    strike:       int
    option_entry: float
    option_exit:  float
    lots:         int
    lot_size:     int
    gross_pnl:    float
    slippage_cost: float
    brokerage:    float
    net_pnl:      float
    entry_source: PriceSource
    exit_source:  PriceSource
    exit_reason:  str
    signal_name:  str


@dataclass
class BacktestResult:
    config: BacktestConfig
    trades: List[BacktestTrade] = field(default_factory=list)
    debugger_entries: List[Dict] = field(default_factory=list)
    total_trades: int   = 0
    winners:      int   = 0
    losers:       int   = 0
    win_rate:     float = 0.0
    total_net_pnl: float = 0.0
    max_drawdown:  float = 0.0
    avg_net_pnl:   float = 0.0
    best_trade:    float = 0.0
    worst_trade:   float = 0.0
    profit_factor: float = 0.0
    sharpe:        float = 0.0
    synthetic_bars: int  = 0
    real_bars:      int  = 0
    error_msg: Optional[str] = None
    completed: bool = False
    debug_log_path: Optional[str] = None
    analysis_data: Dict = field(default_factory=dict)
    equity_curve: List[Dict] = field(default_factory=list)

    def finalize(self):
        self.total_trades = len(self.trades)
        if not self.trades:
            self.completed = True
            return
        pnls = [t.net_pnl for t in self.trades]
        self.total_net_pnl = Utils.round_off(sum(pnls))
        self.winners   = sum(1 for p in pnls if p > 0)
        self.losers    = sum(1 for p in pnls if p <= 0)
        self.win_rate  = self.winners / self.total_trades * 100
        self.avg_net_pnl  = Utils.round_off(self.total_net_pnl / self.total_trades)
        self.best_trade   = Utils.round_off(max(pnls))
        self.worst_trade  = Utils.round_off(min(pnls))
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss   = abs(sum(p for p in pnls if p < 0))
        self.profit_factor = Utils.round_off(gross_profit / gross_loss) if gross_loss else float("inf")
        if self.equity_curve:
            eq = [e["equity"] for e in self.equity_curve]
            peak = eq[0]; dd = 0.0
            for e_ in eq:
                peak = max(peak, e_); dd = min(dd, e_ - peak)
            self.max_drawdown = Utils.round_off(dd)
        if len(pnls) > 1:
            mean_r = sum(pnls) / len(pnls)
            std_r  = math.sqrt(sum((p - mean_r) ** 2 for p in pnls) / (len(pnls) - 1))
            self.sharpe = Utils.round_off(mean_r / std_r * math.sqrt(252) if std_r else 0.0)
        self.completed = True


# ── Per-trade state tracker ───────────────────────────────────────────────────

@dataclass
class _PositionTracker:
    """All mutable state for the currently open backtest position."""
    entry_time:    Optional[datetime]    = None
    spot_entry:    Optional[float]       = None
    strike:        Optional[int]         = None
    opt_type:      Optional[str]         = None
    entry_price:   Optional[float]       = None
    entry_source:  PriceSource           = PriceSource.SYNTHETIC
    signal_name:   str                   = ""
    trailing_sl_high: Optional[float]   = None
    bars_in_trade: int                   = 0

    def open(self, *, entry_time, spot_entry, strike, opt_type,
             entry_price, entry_source, signal_name):
        self.entry_time   = entry_time
        self.spot_entry   = spot_entry
        self.strike       = int(strike)
        self.opt_type     = opt_type
        self.entry_price  = entry_price
        self.entry_source = entry_source
        self.signal_name  = signal_name
        self.trailing_sl_high = entry_price
        self.bars_in_trade    = 1

    def reset(self):
        self.entry_time = self.spot_entry = self.strike = self.opt_type = None
        self.entry_price = self.trailing_sl_high = None
        self.entry_source = PriceSource.SYNTHETIC
        self.signal_name = ""
        self.bars_in_trade = 0


class _CloseResult(NamedTuple):
    result: BacktestResult
    equity: float
    trade_no: int


# ── Debug log helper ──────────────────────────────────────────────────────────

def _bt_log_candle_assessment(bar_time, o, h, l, c, sig_result, current_position,
                               history_len, is_new_day=False):
    """Emit a comprehensive per-candle DEBUG log. Only called when DEBUG is enabled."""
    try:
        ts  = f"{bar_time:%d-%b %H:%M}"
        SEP = "─" * 72; SEP2 = "· " * 36
        fired       = sig_result.get("fired", {})
        rule_results= sig_result.get("rule_results", {})
        confidence  = sig_result.get("confidence", {})
        threshold   = sig_result.get("threshold", 0.6)
        raw_signal  = sig_result.get("signal_value", "WAIT")
        available   = sig_result.get("available", False)
        ind_values  = sig_result.get("indicator_values", {})

        lines = [
            "", SEP,
            f"  CANDLE  {ts}{' [NEW DAY]' if is_new_day else ''}  |  "
            f"O={o:.1f}  H={h:.1f}  L={l:.1f}  C={c:.1f}  |  "
            f"bars={history_len}  |  pos={current_position or 'FLAT'}",
            SEP2,
        ]
        if not available:
            lines += ["  [ENGINE] available=False — not enough data or no rules", SEP]
            logger.debug("\n".join(lines)); return

        if ind_values:
            def _fv(v): return f"{v:.4f}" if isinstance(v, float) else str(v) if v is not None else "N/A"
            parts = [f"{k}={_fv(v.get('last'))} (prev={_fv(v.get('prev'))})"
                     for k, v in ind_values.items()]
            lines += [f"  [INDICATORS]  {'   '.join(parts)}", SEP2]

        for grp in ("BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"):
            grp_fired = fired.get(grp, False)
            grp_conf  = confidence.get(grp, 0.0)
            grp_rules = rule_results.get(grp, [])
            if not grp_rules: continue
            if grp_fired:                  status = "FIRED ✓"
            elif grp_conf >= threshold:    status = f"SUPPRESSED ({grp_conf:.0%} >= {threshold:.0%})"
            else:                          status = f"blocked ({grp_conf:.0%} < {threshold:.0%})"
            lines.append(f"  [{grp:10s}]  conf={grp_conf:.0%}  thresh={threshold:.0%}  → {status}")
            for idx, rr in enumerate(grp_rules):
                def _fv2(v): return f"{v:.4f}" if isinstance(v, float) else ("N/A" if v is None else str(v))
                tick  = "✓" if rr.get("result", False) else "✗"
                error = rr.get("error", "")
                lines.append(
                    f"    rule[{idx}]  {tick}  {rr.get('rule','?')}  w={rr.get('weight',1.0):.1f}"
                    + (f"  ERROR: {error}" if error
                       else f"  LHS={_fv2(rr.get('lhs_value'))}  RHS={_fv2(rr.get('rhs_value'))}  [{rr.get('detail','')}]")
                )

        override = sig_result.get("_bt_override", "")
        lines += [
            SEP2,
            f"  [RESOLVED]  signal={raw_signal}"
            + (f"  ⚡ OVERRIDE: {override}" if override else "")
            + f"  |  {sig_result.get('explanation', '')}",
            SEP,
        ]
        logger.debug("\n".join(lines))
    except Exception as exc:
        logger.debug("[_bt_log_candle_assessment] %s", exc, exc_info=True)


# ── Backtest Engine ────────────────────────────────────────────────────────────

class BacktestEngine:
    """Bar-by-bar backtest using the TradeState singleton."""

    def __init__(self, broker, config: BacktestConfig):
        self.broker = broker
        self.config = config
        self.progress_callback: Optional[Callable[[float, str], None]] = None
        self._stop_requested = False
        self.state = state_manager.get_state()
        self._saved_state = state_manager.save_state()
        candle_store_manager.initialize_for_backtest()

    def stop(self):
        self._stop_requested = True

    def _emit(self, pct: float, msg: str):
        if self.progress_callback:
            try: self.progress_callback(pct, msg)
            except Exception: pass

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

            self._emit(10, "Loading strategy signals…")
            signal_engine, detector = self._load_signal_engine()

            self._emit(12, "Starting bar-by-bar replay…")
            state_manager.reset_for_backtest()
            candle_store_manager.clear()
            result = self._replay(spot_df, pricer, signal_engine, detector)

        except Exception as exc:
            logger.error("[BacktestEngine.run] %s", exc, exc_info=True)
            result.error_msg = str(exc)
        finally:
            state_manager.restore_state(self._saved_state)
            candle_store_manager.clear()

        return result

    # ── Spot data fetching ────────────────────────────────────────────────────

    @staticmethod
    def _filter_spot_df(df: pd.DataFrame, start, end) -> pd.DataFrame:
        """Apply date-range and market-hours filter. Shared by both fetch paths."""
        if not pd.api.types.is_datetime64_any_dtype(df["time"]):
            df["time"] = pd.to_datetime(df["time"])
        df = df[(df["time"].dt.date >= start) & (df["time"].dt.date <= end)].copy()
        t_naive = df["time"].dt.tz_localize(None) if df["time"].dt.tz is not None else df["time"]
        df = df[t_naive.dt.time.between(MARKET_OPEN, MARKET_CLOSE)].copy()
        return df.sort_values("time").reset_index(drop=True)

    def _fetch_spot(self) -> Optional[pd.DataFrame]:
        try:
            days = (self.config.end_date - self.config.start_date).days + 2
            broker_type = safe_getattr(self.broker, "broker_type", None)
            store = candle_store_manager.get_store(self.config.derivative)
            ok = store.fetch(days=days, broker_type=broker_type)

            if not ok or store.is_empty():
                logger.warning("[BacktestEngine._fetch_spot] CandleStore failed — using legacy fetch")
                return self._fetch_spot_legacy()

            df = (store.get_1min() if self.config.execution_interval_minutes == 1
                  else store.resample(self.config.execution_interval_minutes))
            if df is None or df.empty:
                return None

            df = self._filter_spot_df(df, self.config.start_date.date(), self.config.end_date.date())
            logger.info("[BacktestEngine._fetch_spot] %d bars (%dm) for %s",
                        len(df), self.config.execution_interval_minutes, self.config.derivative)
            return df
        except Exception as exc:
            logger.error("[BacktestEngine._fetch_spot] %s", exc, exc_info=True)
            return None

    def _fetch_spot_legacy(self) -> Optional[pd.DataFrame]:
        try:
            days = (self.config.end_date - self.config.start_date).days + 2
            df = self.broker.get_history_for_timeframe(
                symbol=self.config.derivative,
                interval=str(self.config.execution_interval_minutes),
                days=days,
            )
            if df is None or df.empty:
                return None
            return self._filter_spot_df(df, self.config.start_date.date(), self.config.end_date.date())
        except Exception as exc:
            logger.error("[BacktestEngine._fetch_spot_legacy] %s", exc, exc_info=True)
            return None

    # ── Signal engine loading ─────────────────────────────────────────────────

    def _load_signal_engine(self):
        try:
            from strategy.dynamic_signal_engine import DynamicSignalEngine
            from strategy.trend_detector import TrendDetector
            from strategy.strategy_manager import StrategyManager
            from config import Config

            engine = DynamicSignalEngine()
            if self.config.signal_engine_cfg:
                engine.from_dict(self.config.signal_engine_cfg)
            elif self.config.strategy_slug:
                sm  = StrategyManager()
                strat = sm.get(self.config.strategy_slug)
                if strat:
                    engine.from_dict(strat.get("engine", strat))
                    logger.info("[BacktestEngine] Loaded strategy slug: %s", self.config.strategy_slug)
            else:
                sm = StrategyManager()
                cfg = sm.get_active_engine_config()
                if cfg:
                    engine.from_dict(cfg)

            detector = TrendDetector(config=Config(), signal_engine=engine)
            return engine, detector
        except Exception as exc:
            logger.error("[BacktestEngine._load_signal_engine] %s", exc, exc_info=True)
            return None, None

    # ── Replay loop ───────────────────────────────────────────────────────────

    def _replay(self, spot_df: pd.DataFrame, pricer: OptionPricer,
                signal_engine, detector) -> BacktestResult:
        import BaseEnums

        cfg    = self.config
        result = BacktestResult(config=cfg)
        state  = self.state
        state.derivative = cfg.derivative
        state.lot_size   = cfg.lot_size
        state.expiry     = 0

        equity     = cfg.capital
        trade_no   = 0
        total_bars = len(spot_df)

        tracker       = _PositionTracker()
        history_rows: list = []
        debugger      = CandleDebugger(debug_mode=cfg.debug_candles)

        # Day-tracking
        _current_date    = None
        _cooldown_end:   Optional[datetime] = None
        _auto_exit_time: Optional[datetime] = None    # pre-computed per day

        # Diagnostic counters
        cnt = dict(sideway=0, market=0, warmup=0, cooldown=0, no_signal=0, in_trade=0)
        _entry_attempts = 0
        _signals_seen: Dict[str, int] = {}

        logger.info("[Backtest] %d bars | %dm | tp=%s | sl=%s",
                    total_bars, cfg.execution_interval_minutes, cfg.tp_pct, cfg.sl_pct)

        for i, row in spot_df.iterrows():
            if self._stop_requested:
                result.error_msg = "Backtest cancelled by user."
                break

            ts = row["time"]
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]
            bar_time = ts if isinstance(ts, datetime) else pd.Timestamp(ts).to_pydatetime()
            if safe_hasattr(bar_time, "tzinfo") and bar_time.tzinfo:
                bar_time = bar_time.replace(tzinfo=None)

            bar_date  = bar_time.date()
            is_new_day = _current_date is not None and bar_date != _current_date
            _current_date = bar_date

            if is_new_day:
                mkt_open_dt    = datetime.combine(bar_date, MARKET_OPEN)
                _cooldown_end  = mkt_open_dt + timedelta(minutes=COOLDOWN_MINUTES)
                _auto_exit_time = datetime.combine(bar_date, time(
                    MARKET_CLOSE.hour, MARKET_CLOSE.minute - AUTO_EXIT_BEFORE_CLOSE_MINUTES
                ))

            # Set auto-exit time for current day (first bar of the day)
            if _auto_exit_time is None:
                _auto_exit_time = datetime.combine(bar_date, time(
                    MARKET_CLOSE.hour, MARKET_CLOSE.minute - AUTO_EXIT_BEFORE_CLOSE_MINUTES
                ))

            # Progress
            if i % PROGRESS_INTERVAL == 0:
                pct = 12 + (i / total_bars) * 85
                self._emit(pct, f"Bar {i}/{total_bars}  |  {bar_time:%d-%b %H:%M}  |  ₹{equity:,.0f}  |  Trades: {trade_no}")

            # ── Skip sideway zone ─────────────────────────────────────────────
            if cfg.sideway_zone_skip and cfg.sideway_start <= bar_time.time() <= cfg.sideway_end:
                cnt["sideway"] += 1
                debugger.record(bar_time=bar_time, o=o, h=h, l=l, c=c,
                                sig_result=None, action="SKIP", state=state,
                                bars_in_trade=tracker.bars_in_trade,
                                trailing_sl_high=tracker.trailing_sl_high,
                                skip_reason="SIDEWAY")
                continue

            # ── Skip outside market hours ─────────────────────────────────────
            if not (MARKET_OPEN <= bar_time.time() <= MARKET_CLOSE):
                cnt["market"] += 1
                debugger.record(bar_time=bar_time, o=o, h=h, l=l, c=c,
                                sig_result=None, action="SKIP", state=state,
                                bars_in_trade=tracker.bars_in_trade,
                                trailing_sl_high=tracker.trailing_sl_high,
                                skip_reason="MARKET_CLOSED")
                continue

            # ── Auto-exit at market close ─────────────────────────────────────
            if state.current_position and bar_time >= _auto_exit_time:
                cr = self._close_trade(result, state, tracker, bar_time, c, pricer, equity, trade_no, "MARKET_CLOSE")
                result, equity, trade_no = cr.result, cr.equity, cr.trade_no
                state.reset_trade_attributes(current_position=None)
                tracker.reset()
                result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})
                continue

            # ── History buffer ────────────────────────────────────────────────
            history_rows.append({"time": bar_time, "open": o, "high": h, "low": l, "close": c, "volume": 0,
                                  "is_new_day": is_new_day})
            if len(history_rows) > HISTORY_BUFFER_MAX:
                del history_rows[:-HISTORY_BUFFER_MAX]

            if len(history_rows) < MIN_WARMUP_BARS:
                cnt["warmup"] += 1
                debugger.record(bar_time=bar_time, o=o, h=h, l=l, c=c,
                                sig_result=None, action="SKIP", state=state,
                                bars_in_trade=tracker.bars_in_trade,
                                trailing_sl_high=tracker.trailing_sl_high,
                                skip_reason=f"WARMUP({len(history_rows)}/{MIN_WARMUP_BARS})")
                continue

            if _cooldown_end and bar_time < _cooldown_end:
                cnt["cooldown"] += 1

            hist_df = pd.DataFrame(history_rows)

            # ── Signal evaluation ─────────────────────────────────────────────
            sig_result = None
            raw_signal = "WAIT"

            if signal_engine:
                try:
                    sig_result = signal_engine.evaluate(hist_df, current_position=state.current_position)

                    if sig_result and sig_result.get("available", False):
                        raw_signal  = sig_result.get("signal_value", "WAIT")
                        override_reason = ""

                        # Position-aware override: suppress exit signals when flat
                        if state.current_position is None and raw_signal in ("EXIT_CALL", "EXIT_PUT", "HOLD"):
                            conf = sig_result.get("confidence", {})
                            thresh = sig_result.get("threshold", 0.6)
                            bc, bp = conf.get("BUY_CALL", 0.0), conf.get("BUY_PUT", 0.0)
                            if bc >= thresh and bp >= thresh:
                                raw_signal = "BUY_CALL" if bc >= bp else ("BUY_PUT" if bp > bc else "WAIT")
                                override_reason = f"flat+conflict→{raw_signal}(bc={bc:.0%},bp={bp:.0%})"
                            elif bc >= thresh:
                                raw_signal = "BUY_CALL"; override_reason = f"flat:exit→BUY_CALL(conf={bc:.0%})"
                            elif bp >= thresh:
                                raw_signal = "BUY_PUT";  override_reason = f"flat:exit→BUY_PUT(conf={bp:.0%})"
                            else:
                                raw_signal = "WAIT";     override_reason = f"flat:exit_suppressed(bc={bc:.0%},bp={bp:.0%})"

                        if override_reason:
                            sig_result = {**sig_result, "signal_value": raw_signal, "signal": raw_signal,
                                          "_bt_override": override_reason}

                        state.option_signal_result = sig_result
                        _signals_seen[raw_signal] = _signals_seen.get(raw_signal, 0) + 1

                        if logger.isEnabledFor(logging.DEBUG):
                            _bt_log_candle_assessment(bar_time, o, h, l, c, sig_result,
                                                       state.current_position, len(history_rows), is_new_day)
                    else:
                        raw_signal = "WAIT"
                        state.option_signal_result = None

                except Exception as exc:
                    logger.warning("[BT %s] SignalEngine error: %s", f"{bar_time:%H:%M}", exc, exc_info=True)
                    state.option_signal_result = None
                    raw_signal = "WAIT"

            action = self._signal_to_action(raw_signal, state)

            # ── Debug context for open position ───────────────────────────────
            _tp_sl_debug = None; _opt_bar_debug = None
            if cfg.debug_candles and state.current_position:
                _tp_sl_debug, _opt_bar_debug = self._build_debug_tpsl(
                    state, tracker, bar_time, o, h, l, c, pricer, cfg, result
                )

            if cfg.debug_candles:
                debugger.record(bar_time=bar_time, o=o, h=h, l=l, c=c,
                                sig_result=sig_result, action=action, state=state,
                                bars_in_trade=tracker.bars_in_trade,
                                trailing_sl_high=tracker.trailing_sl_high,
                                option_bar=_opt_bar_debug, tp_sl_info=_tp_sl_debug)

            # ── Monitor open position (TP / SL / exit checks) ─────────────────
            if state.current_position:
                strike   = tracker.strike or atm_strike(c, cfg.derivative)
                opt_type = "CE" if state.current_position == BaseEnums.CALL else "PE"
                bar      = pricer.resolve_bar(bar_time, o, h, l, c, opt_type,
                                              minutes_per_bar=cfg.execution_interval_minutes,
                                              strike=strike)
                opt_high, opt_low, opt_close = bar["high"], bar["low"], bar["close"]
                src = bar["source"]

                def _do_exit(reason: str, price: float):
                    nonlocal equity, trade_no, result
                    cr = self._close_trade(result, state, tracker, bar_time, c, pricer,
                                           equity, trade_no, reason,
                                           forced_option_price=price, forced_source=src)
                    result, equity, trade_no = cr.result, cr.equity, cr.trade_no
                    state.reset_trade_attributes(current_position=None)
                    tracker.reset()
                    result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})

                # TP
                if cfg.tp_pct and state.current_buy_price:
                    tp_price = state.current_buy_price * (1 + cfg.tp_pct)
                    if opt_high >= tp_price:
                        _do_exit("TP", tp_price); continue

                # SL
                if cfg.sl_pct and state.current_buy_price:
                    sl_price = state.current_buy_price * (1 - cfg.sl_pct)
                    if opt_low <= sl_price:
                        _do_exit("SL", sl_price); continue

                # Trailing SL
                if cfg.trailing_sl_pct and state.current_buy_price:
                    tracker.trailing_sl_high = max(tracker.trailing_sl_high or opt_high, opt_high)
                    tsl_price = tracker.trailing_sl_high * (1 - cfg.trailing_sl_pct)
                    if opt_low <= tsl_price:
                        _do_exit("TRAILING_SL", tsl_price); continue

                # Index SL
                if cfg.index_sl is not None:
                    es = tracker.spot_entry
                    if es is not None:
                        if state.current_position == BaseEnums.CALL and l <= es - cfg.index_sl:
                            _do_exit("INDEX_SL", opt_low); continue
                        if state.current_position == BaseEnums.PUT and h >= es + cfg.index_sl:
                            _do_exit("INDEX_SL", opt_low); continue

                # Max hold bars
                tracker.bars_in_trade += 1
                if cfg.max_hold_bars and tracker.bars_in_trade >= cfg.max_hold_bars:
                    _do_exit("MAX_HOLD", opt_close); continue

                # Signal exit
                should_exit = (
                    (state.current_position == BaseEnums.CALL and action in ("EXIT_CALL", "BUY_PUT")) or
                    (state.current_position == BaseEnums.PUT  and action in ("EXIT_PUT",  "BUY_CALL"))
                )
                if should_exit:
                    _do_exit("SIGNAL", opt_close); continue

            # ── Entry logic ───────────────────────────────────────────────────
            if state.current_position is None:
                if   action == "BUY_CALL": opt_type = "CE"
                elif action == "BUY_PUT":  opt_type = "PE"
                else:
                    cnt["no_signal"] += 1
                    result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})
                    continue

                _entry_attempts += 1
                strike      = atm_strike(c, cfg.derivative)
                opt_sym     = f"{cfg.derivative}{int(strike)}{opt_type}"
                bar         = pricer.resolve_bar(bar_time, o, h, l, c, opt_type,
                                                 minutes_per_bar=cfg.execution_interval_minutes)
                entry_price = round(bar["close"] * (1 + cfg.slippage_pct), 2)

                state.current_position = BaseEnums.CALL if opt_type == "CE" else BaseEnums.PUT
                state.current_buy_price = entry_price
                if opt_type == "CE": state.call_option = opt_sym
                else:                state.put_option  = opt_sym

                tracker.open(entry_time=bar_time, spot_entry=c, strike=strike,
                             opt_type=opt_type, entry_price=entry_price,
                             entry_source=bar["source"], signal_name=str(raw_signal))

                logger.info("[BT %s] ENTRY #%d: %s strike=%d @ ₹%.2f | spot=%.0f | sig=%s",
                            f"{bar_time:%d-%b %H:%M}", trade_no + 1, opt_type, int(strike),
                            entry_price, c, raw_signal)
            else:
                cnt["in_trade"] += 1

            result.equity_curve.append({"timestamp": bar_time, "equity": round(equity, 2)})

        # ── Final close ───────────────────────────────────────────────────────
        if state.current_position and not spot_df.empty:
            last     = spot_df.iloc[-1]
            last_ts  = (last["time"] if isinstance(last["time"], datetime)
                        else pd.Timestamp(last["time"]).to_pydatetime())
            if safe_hasattr(last_ts, "tzinfo") and last_ts.tzinfo:
                last_ts = last_ts.replace(tzinfo=None)
            cr = self._close_trade(result, state, tracker, last_ts, last["close"],
                                   pricer, equity, trade_no, "MARKET_CLOSE")
            result, equity, trade_no = cr.result, cr.equity, cr.trade_no

        logger.info(
            "[Backtest] DONE — %d bars | sideway=%d market=%d warmup=%d cooldown=%d "
            "no_signal=%d in_trade=%d | entries=%d trades=%d | signals=%s",
            total_bars, cnt["sideway"], cnt["market"], cnt["warmup"], cnt["cooldown"],
            cnt["no_signal"], cnt["in_trade"], _entry_attempts, trade_no, _signals_seen,
        )
        if _entry_attempts == 0:
            logger.warning(
                "[Backtest] ZERO entries — check: (1) strategy rules loaded, "
                "(2) min_confidence not too high, (3) warmup bars >=15, "
                "(4) sideway_zone not covering all signal bars."
            )

        self._emit(98, "Finalising statistics…")
        result.finalize()

        if cfg.analysis_timeframes and not result.error_msg:
            try:
                self._emit(98, "Building analysis data…")
                result.analysis_data = self._build_analysis_data(spot_df, signal_engine)
            except Exception as exc:
                logger.warning("[BacktestEngine] Analysis build failed: %s", exc, exc_info=True)

        if cfg.debug_candles and len(debugger) > 0:
            import tempfile
            dbg_path = cfg.debug_output_path or os.path.join(
                tempfile.gettempdir(),
                f"backtest_debug_{fmt_stamp()}.json"
            )
            if debugger.save(dbg_path):
                result.debug_log_path = dbg_path
                self._emit(99, f"Debug log → {dbg_path}")

        result.debugger_entries = debugger.get_entries()
        self._emit(100, f"Complete — {result.total_trades} trades | ₹{result.total_net_pnl:,.0f}")
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _signal_to_action(signal_value: str, state) -> str:
        import BaseEnums
        try:
            cur = safe_getattr(state, "current_position", None)
            if signal_value == "BUY_CALL" and cur is None:           return "BUY_CALL"
            if signal_value == "BUY_PUT"  and cur is None:           return "BUY_PUT"
            if signal_value in ("EXIT_CALL","BUY_PUT")  and cur == BaseEnums.CALL: return "EXIT_CALL"
            if signal_value in ("EXIT_PUT", "BUY_CALL") and cur == BaseEnums.PUT:  return "EXIT_PUT"
        except Exception as exc:
            logger.debug("[_signal_to_action] %s", exc)
        return "WAIT"

    def _close_trade(
        self,
        result: BacktestResult,
        state,
        tracker: _PositionTracker,
        exit_time: datetime,
        spot_exit: float,
        pricer: OptionPricer,
        equity: float,
        trade_no: int,
        exit_reason: str,
        forced_option_price: Optional[float] = None,
        forced_source: Optional[PriceSource] = None,
    ) -> _CloseResult:
        import BaseEnums
        try:
            opt_type = "CE" if state.current_position == BaseEnums.CALL else "PE"
            strike   = tracker.strike or atm_strike(spot_exit, self.config.derivative)

            if forced_option_price is not None:
                exit_price  = forced_option_price * (1 - self.config.slippage_pct)
                exit_source = forced_source or PriceSource.SYNTHETIC
            else:
                bar = pricer.resolve_bar(exit_time, spot_exit, spot_exit, spot_exit, spot_exit,
                                          opt_type, minutes_per_bar=self.config.execution_interval_minutes)
                exit_price  = bar["close"] * (1 - self.config.slippage_pct)
                exit_source = bar["source"]

            exit_price = max(0.05, Utils.round_off(exit_price))
            entry_price = tracker.entry_price or (state.current_buy_price or exit_price)
            lots    = self.config.num_lots
            lot_sz  = self.config.lot_size

            gross_pnl = (exit_price - entry_price) * lots * lot_sz
            brokerage = self.config.brokerage_per_lot * lots * 2
            net_pnl   = Utils.round_off(gross_pnl - brokerage)

            trade_no += 1
            equity   += net_pnl

            result.trades.append(BacktestTrade(
                trade_no=trade_no, direction=opt_type,
                entry_time=tracker.entry_time or exit_time, exit_time=exit_time,
                spot_entry=tracker.spot_entry or spot_exit, spot_exit=spot_exit,
                strike=int(strike), option_entry=entry_price, option_exit=exit_price,
                lots=lots, lot_size=lot_sz,
                gross_pnl=Utils.round_off(gross_pnl), slippage_cost=0.0,
                brokerage=Utils.round_off(brokerage), net_pnl=net_pnl,
                entry_source=tracker.entry_source, exit_source=exit_source,
                exit_reason=exit_reason, signal_name=tracker.signal_name,
            ))

            if exit_source == PriceSource.SYNTHETIC or tracker.entry_source == PriceSource.SYNTHETIC:
                result.synthetic_bars += 1
            else:
                result.real_bars += 1

        except Exception as exc:
            logger.error("[BacktestEngine._close_trade] %s", exc, exc_info=True)

        return _CloseResult(result=result, equity=equity, trade_no=trade_no)

    def _build_debug_tpsl(self, state, tracker, bar_time, o, h, l, c, pricer, cfg, result):
        """Build TP/SL debug context dict for the CandleDebugger."""
        import BaseEnums
        tpsl = {k: None for k in ("current_option_price","tp_price","sl_price",
                                    "trailing_sl_price","index_sl_level")}
        tpsl.update({k: False for k in ("tp_hit","sl_hit","trailing_sl_hit","index_sl_hit")})
        opt_bar = None
        try:
            strike   = tracker.strike or atm_strike(c, cfg.derivative)
            opt_type = "CE" if state.current_position == BaseEnums.CALL else "PE"
            bar      = pricer.resolve_bar(bar_time, o, h, l, c, opt_type,
                                          minutes_per_bar=cfg.execution_interval_minutes,
                                          strike=strike)
            tpsl["current_option_price"] = bar["close"]
            if cfg.tp_pct and state.current_buy_price:
                tp = state.current_buy_price * (1 + cfg.tp_pct)
                tpsl["tp_price"] = tp; tpsl["tp_hit"] = bar["high"] >= tp
            if cfg.sl_pct and state.current_buy_price:
                sl = state.current_buy_price * (1 - cfg.sl_pct)
                tpsl["sl_price"] = sl; tpsl["sl_hit"] = bar["low"] <= sl
            if cfg.trailing_sl_pct and tracker.trailing_sl_high:
                tsl = tracker.trailing_sl_high * (1 - cfg.trailing_sl_pct)
                tpsl["trailing_sl_price"] = tsl; tpsl["trailing_sl_hit"] = bar["low"] <= tsl
            if cfg.index_sl is not None and tracker.spot_entry:
                es  = tracker.spot_entry
                lvl = es - cfg.index_sl if state.current_position == BaseEnums.CALL else es + cfg.index_sl
                tpsl["index_sl_level"] = lvl
                tpsl["index_sl_hit"] = (l <= lvl if state.current_position == BaseEnums.CALL else h >= lvl)
            opt_bar = {"symbol": f"{cfg.derivative}{int(strike)}{opt_type}",
                       "open": bar["open"], "high": bar["high"], "low": bar["low"],
                       "close": bar["close"], "source": str(bar.get("source", ""))}
        except Exception as exc:
            logger.debug("[_build_debug_tpsl] %s", exc)
        return tpsl, opt_bar

    def _get_historical_option_symbol(self, derivative, strike, option_type, bar_time) -> Optional[str]:
        try:
            exchange_symbol = OptionUtils.get_exchange_symbol(derivative)
            if self.config.expiry_type == "monthly":
                y, m = bar_time.year, bar_time.month + 1
                if m > 12: y += 1; m = 1
                exp = OptionUtils.get_monthly_expiry_date(y, m, derivative=exchange_symbol)
                if bar_time > exp:
                    m += 1
                    if m > 12: y += 1; m = 1
                    exp = OptionUtils.get_monthly_expiry_date(y, m, derivative=exchange_symbol)
                y2  = str(exp.year)[2:]
                mon = OptionUtils.MONTHLY_MONTH_CODES.get(exp.month, "JAN")
                sym = f"{exchange_symbol}{y2}{mon}{int(strike)}{option_type}"
            else:
                from Utils.common import is_holiday
                target_wd  = OptionUtils.EXPIRY_WEEKDAY_MAP.get(exchange_symbol, 1)
                days_ahead = (target_wd - bar_time.weekday()) % 7 or 7
                exp        = bar_time + timedelta(days=days_ahead)
                for _ in range(10):
                    if not is_holiday(exp): break
                    exp -= timedelta(days=1)
                y2  = str(exp.year)[2:]
                mon = OptionUtils.WEEKLY_MONTH_CODES.get(exp.month, str(exp.month))
                sym = f"{exchange_symbol}{y2}{mon}{exp.day:02d}{int(strike)}{option_type}"

            bt = safe_getattr(safe_getattr(self.broker, "broker_setting", None), "broker_type", None)
            if bt:
                sym = OptionUtils.get_option_symbol_for_broker(sym, bt)
            return sym
        except Exception as exc:
            logger.error("[_get_historical_option_symbol] %s", exc)
            return f"{derivative}{int(strike)}{option_type}"

    def _build_analysis_data(self, spot_df: pd.DataFrame, signal_engine) -> Dict:
        from backtest.backtest_window import BarAnalysis
        result: Dict = {}
        if spot_df is None or spot_df.empty or not signal_engine:
            return result

        for tf_str in dict.fromkeys(self.config.analysis_timeframes):
            try:
                tf_min = self._parse_tf_minutes(tf_str)
                if tf_min == self.config.execution_interval_minutes or tf_min == 1:
                    tf_df = spot_df.copy()
                else:
                    if tf_min < self.config.execution_interval_minutes:
                        logger.debug("[Analysis] skip %s: cannot upsample from %dm", tf_str, self.config.execution_interval_minutes)
                        continue
                    tf_df = resample_df(spot_df, tf_min)
                if tf_df is None or tf_df.empty: continue
                if not pd.api.types.is_datetime64_any_dtype(tf_df["time"]):
                    tf_df["time"] = pd.to_datetime(tf_df["time"])

                bars: list = []; history: list = []
                for _, row in tf_df.iterrows():
                    ts = row["time"]
                    bt = ts if isinstance(ts, datetime) else pd.Timestamp(ts).to_pydatetime()
                    if safe_hasattr(bt, "tzinfo") and bt.tzinfo: bt = bt.replace(tzinfo=None)
                    history.append({"time": bt, "open": row["open"], "high": row["high"],
                                    "low": row["low"], "close": row["close"], "volume": 0})
                    if len(history) > HISTORY_BUFFER_MAX: del history[:-HISTORY_BUFFER_MAX]
                    if len(history) < MIN_WARMUP_BARS: continue
                    try:
                        sr = signal_engine.evaluate(pd.DataFrame(history), current_position=None)
                    except Exception: continue
                    if not sr or not sr.get("available", False): continue
                    bars.append(BarAnalysis(
                        timestamp=bt, spot_price=row["close"],
                        signal=sr.get("signal_value", "WAIT"),
                        confidence=dict(sr.get("confidence", {})),
                        rule_results=dict(sr.get("rule_results", {})),
                        indicator_values=dict(sr.get("indicator_values", {})),
                        timeframe=tf_str,
                    ))
                result[tf_str] = bars
                logger.info("[Analysis] %s: %d bars", tf_str, len(bars))
            except Exception as exc:
                logger.warning("[BacktestEngine._build_analysis_data] %s: %s", tf_str, exc, exc_info=True)
        return result

    @staticmethod
    def _parse_tf_minutes(tf_str: str) -> int:
        s = tf_str.strip().lower()
        if s.endswith("h"): return int(s[:-1]) * 60
        if s.endswith("m"): return int(s[:-1])
        try: return int(s)
        except ValueError: return 5