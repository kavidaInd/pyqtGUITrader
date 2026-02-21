from __future__ import annotations
import logging
import pandas as pd
import numpy as np
from Utils.Quants import Quants

try:
    from dynamic_signal_engine import DynamicSignalEngine, OptionSignal
    _ENGINE_AVAILABLE = True
except ImportError:
    _ENGINE_AVAILABLE = False

logger = logging.getLogger(__name__)


def to_native(value):
    if isinstance(value, (np.generic, float)):
        return round(value.item(), 2)
    elif isinstance(value, (int,)):
        return int(value)
    return value


def round_series(series):
    if isinstance(series, (float, int, np.float64, np.int64)):
        return round(series, 2)
    return [round(x, 2) if x is not None else None for x in series]


class TrendDetector:
    def __init__(self, config: object):
        self.config = config
        if _ENGINE_AVAILABLE:
            self.signal_engine = DynamicSignalEngine()
            logger.info("DynamicSignalEngine (option signals) initialised.")
        else:
            self.signal_engine = None
            logger.warning("DynamicSignalEngine not available — dynamic option signals disabled.")

    def reload_signal_engine(self) -> bool:
        if self.signal_engine is None:
            return False
        ok = self.signal_engine.load()
        logger.info("DynamicSignalEngine config reloaded." if ok else "DynamicSignalEngine reload failed.")
        return ok

    def detect(self, df: pd.DataFrame, state: object, symbol: str) -> dict | None:
        try:
            if df is None or df.empty:
                logger.warning(f"Empty/None DataFrame for {symbol}")
                return None
            required_cols = {'open', 'high', 'low', 'close'}
            missing = required_cols - set(df.columns)
            if missing:
                logger.error(f"DataFrame for {symbol} missing: {missing}")
                return None

            results = {'name': symbol}
            results['close'] = round_series(df['close'])

            # SuperTrend Short
            try:
                st_short = Quants.supertrend(df=df,
                    period=getattr(self.config,'short_st_length',10),
                    multiplier=getattr(self.config,'short_st_multi',3), full_output=True)
                results['super_trend_short'] = {
                    'trend': round_series(st_short['trend']),
                    'direction': list(map(str, st_short['direction']))}
            except Exception as e:
                logger.error(f"SuperTrend Short error for {symbol}: {e}", exc_info=True)
                results['super_trend_short'] = None

            # SuperTrend Long
            try:
                st_long = Quants.supertrend(df=df,
                    period=getattr(self.config,'long_st_length',21),
                    multiplier=getattr(self.config,'long_st_multi',5), full_output=True)
                results['super_trend_long'] = {
                    'trend': round_series(st_long['trend']),
                    'direction': list(map(str, st_long['direction']))}
            except Exception as e:
                logger.error(f"SuperTrend Long error for {symbol}: {e}", exc_info=True)
                results['super_trend_long'] = None

            # MACD
            try:
                macd_result = Quants.macd(df=df,
                    fast=getattr(self.config,'macd_fast',12),
                    slow=getattr(self.config,'macd_slow',26),
                    signal=getattr(self.config,'macd_signal',9))
                results['macd'] = {
                    'macd': round_series(macd_result['macd']),
                    'signal': round_series(macd_result['signal']),
                    'histogram': round_series(macd_result['histogram'])}
                results['macd_bottoming'] = bool(Quants.is_bottoming(macd_result['macd']))
                results['macd_topping']   = bool(Quants.is_topping(macd_result['macd']))
                results['macd_cross_up']  = bool(Quants.has_crossed_above(macd_result['macd'], macd_result['signal']))
                results['macd_cross_down']= bool(Quants.has_crossed_below(macd_result['macd'], macd_result['signal']))
            except Exception as e:
                logger.error(f"MACD error for {symbol}: {e}", exc_info=True)
                results['macd'] = None
                results['macd_bottoming'] = results['macd_topping'] = results['macd_cross_up'] = results['macd_cross_down'] = False

            # Bollinger Bands
            try:
                bb_result = Quants.bollinger_bands(data=df,
                    period=getattr(self.config,'bb_length',20),
                    factor=getattr(self.config,'bb_std',2), full_output=True)
                results['bb'] = {
                    'middle': round_series(bb_result['middle']),
                    'upper':  round_series(bb_result['upper']),
                    'lower':  round_series(bb_result['lower'])}
            except Exception as e:
                logger.error(f"BB error for {symbol}: {e}", exc_info=True)
                results['bb'] = None

            # RSI
            try:
                if 'close' not in df or len(df['close'].dropna()) < 15:
                    raise ValueError("Not enough data for RSI.")
                rsi_series = Quants.rsi(data=df, period=getattr(self.config,'rsi_length',14), full_output=True)
                results['rsi']          = round(float(rsi_series.iloc[-1]), 2)
                results['rsi_series']   = round_series(rsi_series)
                results['rsi_bottoming']= bool(Quants.is_bottoming(rsi_series))
                results['rsi_topping']  = bool(Quants.is_topping(rsi_series))
            except Exception as e:
                logger.error(f"RSI error for {symbol}: {e}", exc_info=True)
                results['rsi'] = results['rsi_series'] = None
                results['rsi_bottoming'] = results['rsi_topping'] = False

            # ── Dynamic option signals ──────────────────────────────────
            results['option_signal'] = self._evaluate_option_signal(df, symbol)

            return results

        except Exception as e:
            logger.error(f"Trend detection error for {symbol}: {e}", exc_info=True)
            return None

    def _evaluate_option_signal(self, df: pd.DataFrame, symbol: str) -> dict:
        """
        Run the DynamicSignalEngine and return the option signal dict.
        Schema:
          {
            "signal":       OptionSignal  (BUY_CALL / BUY_PUT / SELL_CALL / SELL_PUT / HOLD / WAIT)
            "signal_value": str
            "fired":        {group: bool, ...}
            "rule_results": {group: [{rule, result}, ...], ...}
            "conflict":     bool
            "available":    bool
          }
        """
        neutral = {
            "signal":       OptionSignal.WAIT if _ENGINE_AVAILABLE else "WAIT",
            "signal_value": "WAIT",
            "fired":        {},
            "rule_results": {},
            "conflict":     False,
            "available":    False,
        }

        if self.signal_engine is None:
            return neutral

        has_rules = any(
            len(self.signal_engine.get_rules(sig)) > 0
            for sig in ["BUY_CALL","BUY_PUT","SELL_CALL","SELL_PUT","HOLD"]
        )
        if not has_rules:
            neutral["available"] = True
            return neutral

        try:
            result = self.signal_engine.evaluate(df)
            result["available"] = True
            logger.debug(f"[{symbol}] Option signal → {result['signal_value']}  conflict={result['conflict']}")
            return result
        except Exception as e:
            logger.error(f"DynamicSignalEngine eval error for {symbol}: {e}", exc_info=True)
            return neutral