"""
indicator_columns.py
====================
Dynamic column name generator for all pandas_ta indicators.
Centralizes the column naming logic for multi-column indicators.

This module provides functions to generate column names dynamically based on
indicator parameters, ensuring that the signal engine can always find the
correct column regardless of parameter changes.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class IndicatorColumnGenerator:
    """
    Dynamic column name generator for pandas_ta indicators.

    This class handles the naming conventions for all multi-column indicators
    in pandas_ta, generating column names based on the parameters used.
    """

    # Indicator categories for better organization
    MOMENTUM_INDICATORS = [
        'macd', 'macd_ext', 'rsi', 'stoch', 'stochrsi', 'cci', 'tsi', 'uo', 'ao',
        'kama', 'roc', 'rvi', 'trix', 'willr', 'dm', 'psl', 'mom', 'slope'
    ]

    TREND_INDICATORS = [
        'ema', 'sma', 'wma', 'hma', 'dema', 'tema', 'trima', 'vidya',
        'adx', 'aroon', 'amat', 'chop', 'cksp', 'psar', 'qstick', 'supertrend',
        'trendflex', 'ichimoku', 'vwap', 'linreg', 'hwma', 'mcgd'
    ]

    VOLATILITY_INDICATORS = [
        'bbands', 'kc', 'donchian', 'atr', 'natr', 'hwc', 'true_range', 'massi'
    ]

    VOLUME_INDICATORS = [
        'ad', 'adosc', 'obv', 'cmf', 'efi', 'eom', 'kvo', 'mfi',
        'nvi', 'pvi', 'pvr', 'pvt', 'vp'
    ]

    STATISTIC_INDICATORS = [
        'entropy', 'kurtosis', 'mad', 'median', 'quantile', 'skew', 'stdev',
        'tos_stdevall', 'variance', 'zscore'
    ]

    @classmethod
    def get_column_name(cls, indicator: str, params: Dict[str, Any],
                        column_type: Optional[str] = None) -> str:
        """
        Generate column name for an indicator based on parameters.

        Args:
            indicator: Indicator name (lowercase)
            params: Indicator parameters
            column_type: Type of column (for multi-column indicators)
                        e.g., 'UPPER', 'LOWER', 'MIDDLE' for bands
                        'K', 'D' for stochastic
                        'MACD', 'SIGNAL', 'HIST' for MACD

        Returns:
            str: Generated column name
        """
        indicator_lower = indicator.lower()

        # Try specific handlers first
        handler_name = f"_handle_{indicator_lower}"
        handler = getattr(cls, handler_name, None)
        if handler:
            try:
                return handler(params, column_type)
            except Exception as e:
                logger.warning(f"Error in handler for {indicator}: {e}")

        # Fall back to generic handlers by category
        if indicator_lower in cls.MOMENTUM_INDICATORS:
            return cls._handle_momentum_default(indicator_lower, params, column_type)
        elif indicator_lower in cls.TREND_INDICATORS:
            return cls._handle_trend_default(indicator_lower, params, column_type)
        elif indicator_lower in cls.VOLATILITY_INDICATORS:
            return cls._handle_volatility_default(indicator_lower, params, column_type)
        elif indicator_lower in cls.VOLUME_INDICATORS:
            return cls._handle_volume_default(indicator_lower, params, column_type)
        elif indicator_lower in cls.STATISTIC_INDICATORS:
            return cls._handle_statistic_default(indicator_lower, params, column_type)

        # Ultimate fallback: uppercase indicator name
        return indicator.upper()

    @classmethod
    def get_all_column_names(cls, indicator: str, params: Dict[str, Any]) -> Dict[str, str]:
        """
        Get all possible column names for a multi-column indicator.

        Args:
            indicator: Indicator name
            params: Indicator parameters

        Returns:
            Dict mapping column types to column names
        """
        indicator_lower = indicator.lower()

        # Multi-column indicators
        multi_column_handlers = {
            # Momentum
            'macd': lambda p: {
                'MACD': cls._handle_macd(p, 'MACD'),
                'SIGNAL': cls._handle_macd(p, 'SIGNAL'),
                'HIST': cls._handle_macd(p, 'HIST')
            },
            'stoch': lambda p: {
                'K': cls._handle_stoch(p, 'K'),
                'D': cls._handle_stoch(p, 'D')
            },
            'stochrsi': lambda p: {
                'K': cls._handle_stochrsi(p, 'K'),
                'D': cls._handle_stochrsi(p, 'D')
            },
            'aroon': lambda p: {
                'AROON_UP': cls._handle_aroon(p, 'UP'),
                'AROON_DOWN': cls._handle_aroon(p, 'DOWN')
            },
            'dm': lambda p: {
                'PLUS_DM': cls._handle_dm(p, 'PLUS'),
                'MINUS_DM': cls._handle_dm(p, 'MINUS')
            },

            # Trend
            'adx': lambda p: {
                'ADX': cls._handle_adx(p, 'ADX'),
                'PLUS_DI': cls._handle_adx(p, 'PLUS_DI'),
                'MINUS_DI': cls._handle_adx(p, 'MINUS_DI')
            },
            'supertrend': lambda p: {
                'TREND': cls._handle_supertrend(p, 'TREND'),
                'DIRECTION': cls._handle_supertrend(p, 'DIRECTION'),
                'LONG': cls._handle_supertrend(p, 'LONG'),
                'SHORT': cls._handle_supertrend(p, 'SHORT')
            },
            'ichimoku': lambda p: {
                'ISA': cls._handle_ichimoku(p, 'ISA'),
                'ISB': cls._handle_ichimoku(p, 'ISB'),
                'ITS': cls._handle_ichimoku(p, 'ITS'),
                'IKS': cls._handle_ichimoku(p, 'IKS'),
                'ICS': cls._handle_ichimoku(p, 'ICS')
            },

            # Volatility
            'bbands': lambda p: {
                'LOWER': cls._handle_bbands(p, 'LOWER'),
                'MIDDLE': cls._handle_bbands(p, 'MIDDLE'),
                'UPPER': cls._handle_bbands(p, 'UPPER'),
                'BANDWIDTH': cls._handle_bbands(p, 'BANDWIDTH'),
                'PERCENT': cls._handle_bbands(p, 'PERCENT')
            },
            'kc': lambda p: {
                'LOWER': cls._handle_kc(p, 'LOWER'),
                'MIDDLE': cls._handle_kc(p, 'MIDDLE'),
                'UPPER': cls._handle_kc(p, 'UPPER')
            },
            'donchian': lambda p: {
                'LOWER': cls._handle_donchian(p, 'LOWER'),
                'MIDDLE': cls._handle_donchian(p, 'MIDDLE'),
                'UPPER': cls._handle_donchian(p, 'UPPER')
            },

            # Volume
            'adosc': lambda p: {
                'ADOSC': cls._handle_adosc(p, 'ADOSC'),
                'AD': cls._handle_adosc(p, 'AD')
            },
            'kvo': lambda p: {
                'KVO': cls._handle_kvo(p, 'KVO'),
                'SIGNAL': cls._handle_kvo(p, 'SIGNAL')
            },
        }

        handler = multi_column_handlers.get(indicator_lower)
        if handler:
            return handler(params)

        # Single column indicators return just the main column
        return {'MAIN': cls.get_column_name(indicator, params)}

    # =========================================================================
    # Specific Handlers for Each Indicator
    # =========================================================================

    @classmethod
    def _handle_macd(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle MACD column names"""
        fast = params.get('fast', 12)
        slow = params.get('slow', 26)
        signal = params.get('signal', 9)

        if column_type == 'SIGNAL':
            return f"MACDs_{fast}_{slow}_{signal}"
        elif column_type == 'HIST' or column_type == 'HISTOGRAM':
            return f"MACDh_{fast}_{slow}_{signal}"
        else:  # MACD line
            return f"MACD_{fast}_{slow}_{signal}"

    @classmethod
    def _handle_macd_ext(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle MACD_EXT column names"""
        fast = params.get('fast', 12)
        slow = params.get('slow', 26)
        signal = params.get('signal', 9)

        if column_type == 'SIGNAL':
            return f"MACDs_{fast}_{slow}_{signal}"
        elif column_type == 'HIST':
            return f"MACDh_{fast}_{slow}_{signal}"
        else:
            return f"MACD_{fast}_{slow}_{signal}"

    @classmethod
    def _handle_rsi(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle RSI column names"""
        length = params.get('length', 14)
        return f"RSI_{length}"

    @classmethod
    def _handle_stoch(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Stochastic column names"""
        k = params.get('k', 14)
        d = params.get('d', 3)
        smooth_k = params.get('smooth_k', 3)

        if column_type == 'D':
            return f"STOCHd_{k}_{d}_{smooth_k}"
        else:  # K line
            return f"STOCHk_{k}_{d}_{smooth_k}"

    @classmethod
    def _handle_stochrsi(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Stochastic RSI column names"""
        length = params.get('length', 14)
        rsi_length = params.get('rsi_length', 14)
        k = params.get('k', 3)
        d = params.get('d', 3)

        if column_type == 'D':
            return f"STOCHRSId_{length}_{rsi_length}_{k}_{d}"
        else:  # K line
            return f"STOCHRSIk_{length}_{rsi_length}_{k}_{d}"

    @classmethod
    def _handle_cci(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle CCI column names"""
        length = params.get('length', 20)
        return f"CCI_{length}"

    @classmethod
    def _handle_tsi(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle TSI column names"""
        fast = params.get('fast', 13)
        slow = params.get('slow', 25)
        return f"TSI_{fast}_{slow}"

    @classmethod
    def _handle_uo(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Ultimate Oscillator column names"""
        fast = params.get('fast', 7)
        medium = params.get('medium', 14)
        slow = params.get('slow', 28)
        return f"UO_{fast}_{medium}_{slow}"

    @classmethod
    def _handle_ao(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Awesome Oscillator column names"""
        fast = params.get('fast', 5)
        slow = params.get('slow', 34)
        return f"AO_{fast}_{slow}"

    @classmethod
    def _handle_kama(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle KAMA column names"""
        length = params.get('length', 10)
        fast = params.get('fast', 2)
        slow = params.get('slow', 30)
        return f"KAMA_{length}_{fast}_{slow}"

    @classmethod
    def _handle_roc(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle ROC column names"""
        length = params.get('length', 10)
        return f"ROC_{length}"

    @classmethod
    def _handle_rvi(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle RVI column names"""
        length = params.get('length', 14)
        return f"RVI_{length}"

    @classmethod
    def _handle_trix(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle TRIX column names"""
        length = params.get('length', 15)
        return f"TRIX_{length}"

    @classmethod
    def _handle_willr(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Williams %R column names"""
        length = params.get('length', 14)
        return f"WILLR_{length}"

    @classmethod
    def _handle_dm(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Directional Movement column names"""
        length = params.get('length', 14)

        if column_type == 'PLUS' or column_type == 'PLUS_DM':
            return f"DMP_{length}"
        elif column_type == 'MINUS' or column_type == 'MINUS_DM':
            return f"DMN_{length}"
        else:
            return f"DMP_{length}"  # Default to plus

    @classmethod
    def _handle_psl(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle PSL column names"""
        length = params.get('length', 12)
        return f"PSL_{length}"

    @classmethod
    def _handle_mom(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Momentum column names"""
        length = params.get('length', 10)
        return f"MOM_{length}"

    # -------------------------------------------------------------------------
    # Moving Averages
    # -------------------------------------------------------------------------

    @classmethod
    def _handle_ema(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle EMA column names"""
        length = params.get('length', 10)
        return f"EMA_{length}"

    @classmethod
    def _handle_sma(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle SMA column names"""
        length = params.get('length', 10)
        return f"SMA_{length}"

    @classmethod
    def _handle_wma(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle WMA column names"""
        length = params.get('length', 10)
        return f"WMA_{length}"

    @classmethod
    def _handle_hma(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle HMA column names"""
        length = params.get('length', 10)
        return f"HMA_{length}"

    @classmethod
    def _handle_dema(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle DEMA column names"""
        length = params.get('length', 10)
        return f"DEMA_{length}"

    @classmethod
    def _handle_tema(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle TEMA column names"""
        length = params.get('length', 10)
        return f"TEMA_{length}"

    @classmethod
    def _handle_trima(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle TRIMA column names"""
        length = params.get('length', 10)
        return f"TRIMA_{length}"

    @classmethod
    def _handle_vidya(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle VIDYA column names"""
        length = params.get('length', 14)
        return f"VIDYA_{length}"

    @classmethod
    def _handle_hwma(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle HWMA column names"""
        na = params.get('na', 0)
        nb = params.get('nb', 0)
        nc = params.get('nc', 0)
        return f"HWMA_{na}_{nb}_{nc}"

    @classmethod
    def _handle_mcgd(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle MCGD column names"""
        length = params.get('length', 10)
        return f"MCGD_{length}"

    # -------------------------------------------------------------------------
    # Trend Indicators
    # -------------------------------------------------------------------------

    @classmethod
    def _handle_adx(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle ADX column names"""
        length = params.get('length', 14)

        if column_type == 'PLUS_DI':
            return f"DMP_{length}"
        elif column_type == 'MINUS_DI':
            return f"DMN_{length}"
        else:  # ADX line
            return f"ADX_{length}"

    @classmethod
    def _handle_aroon(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Aroon column names"""
        length = params.get('length', 14)

        if column_type == 'DOWN':
            return f"AROOND_{length}"
        else:  # UP line
            return f"AROONU_{length}"

    @classmethod
    def _handle_amat(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle AMAT column names"""
        fast = params.get('fast', 8)
        slow = params.get('slow', 21)
        lookback = params.get('lookback', 2)
        return f"AMAT_{fast}_{slow}_{lookback}"

    @classmethod
    def _handle_chop(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle CHOP column names"""
        length = params.get('length', 14)
        return f"CHOP_{length}"

    @classmethod
    def _handle_cksp(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle CKSP column names"""
        length = params.get('length', 10)
        return f"CKSP_{length}"

    @classmethod
    def _handle_psar(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle PSAR column names"""
        af0 = params.get('af0', 0.02)
        af = params.get('af', 0.02)
        max_af = params.get('max_af', 0.2)

        if column_type == 'LONG':
            return f"PSARl_{af0}_{af}_{max_af}"
        elif column_type == 'SHORT':
            return f"PSARs_{af0}_{af}_{max_af}"
        else:
            return f"PSARl_{af0}_{af}_{max_af}"  # Default to long

    @classmethod
    def _handle_qstick(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle QSTICK column names"""
        length = params.get('length', 10)
        return f"QSTICK_{length}"

    @classmethod
    def _handle_supertrend(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Supertrend column names"""
        length = params.get('length', 7)
        multiplier = params.get('multiplier', 3.0)

        if column_type == 'DIRECTION':
            return f"SUPERTd_{length}_{multiplier}"
        elif column_type == 'LONG':
            return f"SUPERTl_{length}_{multiplier}"
        elif column_type == 'SHORT':
            return f"SUPERTs_{length}_{multiplier}"
        else:  # Trend line
            return f"SUPERT_{length}_{multiplier}"

    @classmethod
    def _handle_trendflex(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle TRENDFLEX column names"""
        length = params.get('length', 20)
        return f"TRENDFLEX_{length}"

    @classmethod
    def _handle_ichimoku(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Ichimoku column names"""
        tenkan = params.get('tenkan', 9)
        kijun = params.get('kijun', 26)
        senkou = params.get('senkou', 52)

        if column_type == 'ISA':  # Tenkan-sen (Conversion Line)
            return f"ISA_{tenkan}"
        elif column_type == 'ISB':  # Kijun-sen (Base Line)
            return f"ISB_{kijun}"
        elif column_type == 'ITS':  # Senkou Span A
            return f"ITS_{tenkan}_{kijun}"
        elif column_type == 'IKS':  # Senkou Span B
            return f"IKS_{senkou}"
        elif column_type == 'ICS':  # Chikou Span
            return f"ICS_{tenkan}"
        else:
            return f"ISA_{tenkan}"

    @classmethod
    def _handle_vwap(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle VWAP column names"""
        anchor = params.get('anchor', 'D')
        return f"VWAP_{anchor}"

    @classmethod
    def _handle_linreg(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Linear Regression column names"""
        length = params.get('length', 14)
        return f"LINREG_{length}"

    # -------------------------------------------------------------------------
    # Volatility Indicators
    # -------------------------------------------------------------------------

    @classmethod
    def _handle_bbands(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Bollinger Bands column names"""
        length = params.get('length', 20)
        std = params.get('std', 2.0)

        if column_type == 'LOWER':
            return f"BBL_{length}_{std}"
        elif column_type == 'MIDDLE':
            return f"BBM_{length}_{std}"
        elif column_type == 'UPPER':
            return f"BBU_{length}_{std}"
        elif column_type == 'BANDWIDTH':
            return f"BBB_{length}_{std}"
        elif column_type == 'PERCENT':
            return f"BBP_{length}_{std}"
        else:
            return f"BBM_{length}_{std}"  # Default to middle band

    @classmethod
    def _handle_kc(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Keltner Channels column names"""
        length = params.get('length', 20)
        scalar = params.get('scalar', 1.5)

        if column_type == 'LOWER':
            return f"KCLe_{length}_{scalar}"
        elif column_type == 'MIDDLE':
            return f"KCBe_{length}_{scalar}"
        elif column_type == 'UPPER':
            return f"KCUe_{length}_{scalar}"
        else:
            return f"KCBe_{length}_{scalar}"  # Default to middle band

    @classmethod
    def _handle_donchian(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Donchian Channels column names"""
        lower_length = params.get('lower_length', 20)
        upper_length = params.get('upper_length', 20)

        if column_type == 'LOWER':
            return f"DCL_{lower_length}_{upper_length}"
        elif column_type == 'MIDDLE':
            return f"DCM_{lower_length}_{upper_length}"
        elif column_type == 'UPPER':
            return f"DCU_{lower_length}_{upper_length}"
        else:
            return f"DCM_{lower_length}_{upper_length}"  # Default to middle band

    @classmethod
    def _handle_atr(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle ATR column names"""
        length = params.get('length', 14)
        return f"ATR_{length}"

    @classmethod
    def _handle_natr(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle NATR column names"""
        length = params.get('length', 14)
        return f"NATR_{length}"

    @classmethod
    def _handle_true_range(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle True Range column names"""
        return "TRUE_RANGE"

    @classmethod
    def _handle_massi(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Mass Index column names"""
        fast = params.get('fast', 9)
        slow = params.get('slow', 25)
        return f"MASSI_{fast}_{slow}"

    # -------------------------------------------------------------------------
    # Volume Indicators
    # -------------------------------------------------------------------------

    @classmethod
    def _handle_ad(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle AD (Accumulation/Distribution) column names"""
        return "AD"

    @classmethod
    def _handle_adosc(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle ADOSC column names"""
        fast = params.get('fast', 3)
        slow = params.get('slow', 10)

        if column_type == 'AD':
            return "AD"
        else:
            return f"ADOSC_{fast}_{slow}"

    @classmethod
    def _handle_obv(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle OBV column names"""
        return "OBV"

    @classmethod
    def _handle_cmf(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle CMF column names"""
        length = params.get('length', 20)
        return f"CMF_{length}"

    @classmethod
    def _handle_efi(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle EFI column names"""
        length = params.get('length', 13)
        return f"EFI_{length}"

    @classmethod
    def _handle_eom(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle EOM column names"""
        length = params.get('length', 14)
        divisor = params.get('divisor', 100000000)
        return f"EOM_{length}_{divisor}"

    @classmethod
    def _handle_kvo(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle KVO column names"""
        fast = params.get('fast', 34)
        slow = params.get('slow', 55)
        signal = params.get('signal', 13)

        if column_type == 'SIGNAL':
            return f"KVOs_{fast}_{slow}_{signal}"
        else:
            return f"KVO_{fast}_{slow}_{signal}"

    @classmethod
    def _handle_mfi(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle MFI column names"""
        length = params.get('length', 14)
        return f"MFI_{length}"

    @classmethod
    def _handle_nvi(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle NVI column names"""
        length = params.get('length', 1)
        return f"NVI_{length}"

    @classmethod
    def _handle_pvi(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle PVI column names"""
        length = params.get('length', 1)
        return f"PVI_{length}"

    @classmethod
    def _handle_pvt(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle PVT column names"""
        return "PVT"

    # -------------------------------------------------------------------------
    # Statistical Indicators
    # -------------------------------------------------------------------------

    @classmethod
    def _handle_entropy(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Entropy column names"""
        length = params.get('length', 10)
        return f"ENTROPY_{length}"

    @classmethod
    def _handle_kurtosis(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Kurtosis column names"""
        length = params.get('length', 30)
        return f"KURT_{length}"

    @classmethod
    def _handle_mad(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle MAD column names"""
        length = params.get('length', 30)
        return f"MAD_{length}"

    @classmethod
    def _handle_median(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Median column names"""
        length = params.get('length', 30)
        return f"MEDIAN_{length}"

    @classmethod
    def _handle_quantile(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Quantile column names"""
        length = params.get('length', 30)
        q = params.get('q', 0.5)
        return f"Q_{length}_{q}"

    @classmethod
    def _handle_skew(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Skew column names"""
        length = params.get('length', 30)
        return f"SKEW_{length}"

    @classmethod
    def _handle_stdev(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Standard Deviation column names"""
        length = params.get('length', 30)
        return f"STDEV_{length}"

    @classmethod
    def _handle_variance(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Variance column names"""
        length = params.get('length', 30)
        return f"VAR_{length}"

    @classmethod
    def _handle_zscore(cls, params: Dict[str, Any], column_type: Optional[str] = None) -> str:
        """Handle Z-Score column names"""
        length = params.get('length', 30)
        return f"Z_{length}"

    # -------------------------------------------------------------------------
    # Generic Default Handlers
    # -------------------------------------------------------------------------

    @classmethod
    def _handle_momentum_default(cls, indicator: str, params: Dict[str, Any],
                                 column_type: Optional[str] = None) -> str:
        """Default handler for momentum indicators"""
        # Try to extract common parameters
        length = params.get('length')
        if length:
            return f"{indicator.upper()}_{length}"

        fast = params.get('fast')
        slow = params.get('slow')
        if fast and slow:
            return f"{indicator.upper()}_{fast}_{slow}"

        return indicator.upper()

    @classmethod
    def _handle_trend_default(cls, indicator: str, params: Dict[str, Any],
                              column_type: Optional[str] = None) -> str:
        """Default handler for trend indicators"""
        length = params.get('length')
        if length:
            return f"{indicator.upper()}_{length}"
        return indicator.upper()

    @classmethod
    def _handle_volatility_default(cls, indicator: str, params: Dict[str, Any],
                                   column_type: Optional[str] = None) -> str:
        """Default handler for volatility indicators"""
        length = params.get('length')
        if length:
            return f"{indicator.upper()}_{length}"
        return indicator.upper()

    @classmethod
    def _handle_volume_default(cls, indicator: str, params: Dict[str, Any],
                               column_type: Optional[str] = None) -> str:
        """Default handler for volume indicators"""
        return indicator.upper()

    @classmethod
    def _handle_statistic_default(cls, indicator: str, params: Dict[str, Any],
                                  column_type: Optional[str] = None) -> str:
        """Default handler for statistical indicators"""
        length = params.get('length')
        if length:
            return f"{indicator.upper()}_{length}"
        return indicator.upper()


# Convenience function for easy import
def get_indicator_column(indicator: str, params: Dict[str, Any],
                         column_type: Optional[str] = None) -> str:
    """
    Get the column name for an indicator based on parameters.

    Args:
        indicator: Indicator name
        params: Indicator parameters
        column_type: Type of column (for multi-column indicators)

    Returns:
        str: Column name
    """
    return IndicatorColumnGenerator.get_column_name(indicator, params, column_type)


def get_all_indicator_columns(indicator: str, params: Dict[str, Any]) -> Dict[str, str]:
    """
    Get all possible column names for a multi-column indicator.

    Args:
        indicator: Indicator name
        params: Indicator parameters

    Returns:
        Dict mapping column types to column names
    """
    return IndicatorColumnGenerator.get_all_column_names(indicator, params)