import numpy as np
import pandas as pd
from BaseEnums import BULLISH, BEARISH


class Quants:

    @staticmethod
    def bollinger_bands(data: pd.DataFrame, period=20, factor=2, full_output=False):
        if 'close' not in data.columns:
            raise ValueError("DataFrame must contain a 'close' column.")
        if len(data) < period:
            raise ValueError(f"DataFrame length must be at least {period} to compute Bollinger Bands.")

        close = data['close']
        ma = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper_band = ma + factor * std
        lower_band = ma - factor * std

        if full_output:
            return {
                'middle': ma,
                'upper': upper_band,
                'lower': lower_band
            }
        else:
            ma_val = round(ma.iloc[-1], 2) if pd.notnull(ma.iloc[-1]) else None
            upper_val = round(upper_band.iloc[-1], 2) if pd.notnull(upper_band.iloc[-1]) else None
            lower_val = round(lower_band.iloc[-1], 2) if pd.notnull(lower_band.iloc[-1]) else None
            return {'middle': ma_val, 'upper': upper_val, 'lower': lower_val}

    @staticmethod
    def supertrend(df: pd.DataFrame, period=7, multiplier=3, full_output=False):
        required_cols = ['high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"DataFrame must contain columns: {required_cols}")
        if len(df) < period:
            raise ValueError(f"DataFrame length must be at least {period} to compute Supertrend.")

        # Always call _custom_supertrend with full_series=full_output
        result = Quants._custom_supertrend(df, period, multiplier, full_series=full_output)
        if full_output:
            # result: trend, direction, long_band, short_band, trend_series, dir_series, long_series, short_series
            trend, direction, long_band, short_band, trend_series, dir_series, long_series, short_series = result
            dir_flag = pd.Series(BULLISH if d == 1 else BEARISH for d in dir_series)
            return {
                'trend': trend_series,
                'direction': dir_series,
                'long': long_series,
                'short': short_series
            }
        else:
            # result: trend, direction, long_band, short_band
            trend, direction, long_band, short_band = result
            dir_flag = BULLISH if direction == 1 else BEARISH
            return {
                'trend': round(trend, 2) if pd.notnull(trend) else None,
                'direction': dir_flag
            }

    @staticmethod
    def get_med_price(high, low):
        return (high + low) / 2

    @staticmethod
    def _get_atr(high, low, close, period):
        tr0 = abs(high - low)
        tr1 = abs(high - close.shift())
        tr2 = abs(low - close.shift())
        tr = pd.concat([tr0, tr1, tr2], axis=1).max(axis=1)
        return tr.ewm(alpha=1 / period, adjust=False).mean()

    @staticmethod
    def _get_basic_bands(med_price, atr, multiplier):
        return med_price + multiplier * atr, med_price - multiplier * atr

    @staticmethod
    def _get_final_bands(close, upper, lower, full_series=False):
        upper = upper.copy()
        lower = lower.copy()
        trend = pd.Series(np.nan, index=close.index)
        direction = pd.Series(1, index=close.index)
        long = pd.Series(np.nan, index=close.index)
        short = pd.Series(np.nan, index=close.index)

        for i in range(1, len(close)):
            if close.iloc[i] > upper.iloc[i - 1]:
                direction.iloc[i] = 1
            elif close.iloc[i] < lower.iloc[i - 1]:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = direction.iloc[i - 1]
                if direction.iloc[i] > 0 and lower.iloc[i] < lower.iloc[i - 1]:
                    lower.iloc[i] = lower.iloc[i - 1]
                if direction.iloc[i] < 0 and upper.iloc[i] > upper.iloc[i - 1]:
                    upper.iloc[i] = upper.iloc[i - 1]

            if direction.iloc[i] > 0:
                trend.iloc[i] = long.iloc[i] = lower.iloc[i]
            else:
                trend.iloc[i] = short.iloc[i] = upper.iloc[i]

        if full_series:
            trend_ff = trend.ffill()
            long_ff = long.ffill()
            short_ff = short.ffill()
            return (
                trend_ff.iloc[-1],
                direction.iloc[-1],
                long_ff.iloc[-1],
                short_ff.iloc[-1],
                trend_ff,
                direction,
                long_ff,
                short_ff
            )
        else:
            trend_ff = trend.ffill()
            long_ff = long.ffill()
            short_ff = short.ffill()
            return (
                trend_ff.iloc[-1],
                direction.iloc[-1],
                long_ff.iloc[-1],
                short_ff.iloc[-1]
            )

    @staticmethod
    def _custom_supertrend(df, period=7, multiplier=3, full_series=False):
        med_price = Quants.get_med_price(df['high'], df['low'])
        atr = Quants._get_atr(df['high'], df['low'], df['close'], period)
        upper, lower = Quants._get_basic_bands(med_price, atr, multiplier)
        return Quants._get_final_bands(df['close'], upper, lower, full_series=full_series)

    @staticmethod
    def ema(series: pd.Series, span: int):
        return series.ewm(span=span, adjust=False).mean()

    @staticmethod
    def ma(data: pd.DataFrame, period: int):
        if 'close' not in data.columns:
            raise ValueError("DataFrame must contain a 'close' column.")
        if len(data) < period:
            raise ValueError(f"DataFrame length must be at least {period} to compute moving average.")

        val = data['close'].rolling(window=period).mean().iloc[-1]
        return round(val, 2) if pd.notnull(val) else None

    @staticmethod
    def atr(data: pd.DataFrame, period: int):
        required_cols = ['high', 'low', 'close']
        if not all(col in data.columns for col in required_cols):
            raise ValueError(f"DataFrame must contain columns: {required_cols}")
        if len(data) < period:
            raise ValueError(f"DataFrame length must be at least {period} to compute ATR.")

        high = data['high']
        low = data['low']
        close = data['close']
        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)
        val = tr.rolling(window=period).mean().iloc[-1]
        return round(val, 2) if pd.notnull(val) else None

    @staticmethod
    def ppsr(data: pd.DataFrame):
        required_cols = ['high', 'low', 'close']
        if not all(col in data.columns for col in required_cols):
            raise ValueError(f"DataFrame must contain columns: {required_cols}")
        if len(data) < 1:
            raise ValueError("DataFrame must contain at least one row.")

        PP = (data['high'] + data['low'] + data['close']) / 3
        R1 = 2 * PP - data['low']
        S1 = 2 * PP - data['high']
        R2 = PP + (data['high'] - data['low'])
        S2 = PP - (data['high'] - data['low'])
        R3 = data['high'] + 2 * (PP - data['low'])
        S3 = data['low'] - 2 * (data['high'] - PP)
        last_idx = data.index[-1]

        return pd.DataFrame({
            'PP': round(PP.iloc[-1], 2), 'R1': round(R1.iloc[-1], 2), 'S1': round(S1.iloc[-1], 2),
            'R2': round(R2.iloc[-1], 2), 'S2': round(S2.iloc[-1], 2), 'R3': round(R3.iloc[-1], 2),
            'S3': round(S3.iloc[-1], 2)
        }, index=[last_idx])

    @staticmethod
    def rsi(data: pd.DataFrame, period=14, full_output=False):
        if 'close' not in data.columns or len(data) < period:
            raise ValueError("Invalid input for RSI.")

        delta = data['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / avg_loss
        rsi_series = 100 - (100 / (1 + rs))
        if full_output:
            return rsi_series
        else:
            return round(rsi_series.iloc[-1], 2) if pd.notnull(rsi_series.iloc[-1]) else None

    @staticmethod
    def macd(df: pd.DataFrame, fast=12, slow=26, signal=9, full_output=True):
        if 'close' not in df.columns:
            raise ValueError("MACD requires 'close' column.")

        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        if full_output:
            return {
                'macd': macd_line,
                'signal': signal_line,
                'histogram': histogram
            }
        else:
            return round(macd_line.iloc[-1], 2), round(signal_line.iloc[-1], 2), round(histogram.iloc[-1], 2)

    @staticmethod
    def is_increasing(series: pd.Series, lookback=3) -> bool:
        return all(x < y for x, y in zip(series[-lookback:], series[-lookback + 1:]))

    @staticmethod
    def is_decreasing(series: pd.Series, lookback=3) -> bool:
        return all(x > y for x, y in zip(series[-lookback:], series[-lookback + 1:]))

    @staticmethod
    def is_bottoming(series: pd.Series, threshold=30, lookback=3) -> bool:
        return series.iloc[-1] > series.iloc[-2] and min(series[-lookback:]) < threshold

    @staticmethod
    def is_topping(series: pd.Series, threshold=70, lookback=3) -> bool:
        return series.iloc[-1] < series.iloc[-2] and max(series[-lookback:]) > threshold

    @staticmethod
    def has_crossed_above(series1: pd.Series, series2: pd.Series) -> bool:
        return series1.iloc[-2] < series2.iloc[-2] and series1.iloc[-1] > series2.iloc[-1]

    @staticmethod
    def has_crossed_below(series1: pd.Series, series2: pd.Series) -> bool:
        return series1.iloc[-2] > series2.iloc[-2] and series1.iloc[-1] < series2.iloc[-1]

    @staticmethod
    def is_crossing_up(series1, series2):
        """
        Detect if series1 has just crossed above series2
        """
        if len(series1) < 2 or len(series2) < 2:
            return False
        return series1.iloc[-2] < series2.iloc[-2] and series1.iloc[-1] > series2.iloc[-1]

    @staticmethod
    def is_crossing_down(series1, series2):
        """
        Detect if series1 has just crossed below series2
        """
        if len(series1) < 2 or len(series2) < 2:
            return False
        return series1.iloc[-2] > series2.iloc[-2] and series1.iloc[-1] < series2.iloc[-1]
