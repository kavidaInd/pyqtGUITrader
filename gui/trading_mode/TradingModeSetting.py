"""
TradingModeSetting_db.py
========================
Database-backed trading mode settings using the SQLite database.

Enhanced with support for:
- FEATURE 6: Multi-Timeframe Filter
- FEATURE 1: Risk Management
"""

import logging
from enum import Enum
from typing import Any, Dict, Optional

from db.connector import get_db
from db.crud import trading_mode

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class TradingMode(Enum):
    LIVE = "Live"
    SIM = "Simulation"
    BACKTEST = "Backtest"

    @classmethod
    def _missing_(cls, value):
        """Handle missing enum values gracefully."""
        try:
            logger.warning(f"Unknown trading mode value: {value}, defaulting to SIM")
            return cls.SIM
        except Exception as e:
            logger.error(f"[TradingMode._missing_] Failed: {e}", exc_info=True)
            return cls.SIM


class TradingModeSetting:
    """
    Database-backed trading mode settings using the trading_mode_setting table.

    Enhanced with additional fields for new features.
    This is a drop-in replacement for the JSON-based TradingModeSetting class,
    maintaining the same interface while using the database.
    """

    # Rule 2: Class-level defaults with new features
    DEFAULTS = {
        # Original fields
        "mode": TradingMode.SIM,
        "paper_balance": 100000.0,
        "allow_live_trading": False,
        "confirm_live_trades": True,
        "simulate_slippage": True,
        "slippage_percent": 0.05,
        "simulate_delay": True,
        "delay_ms": 500,

        # FEATURE 6: Multi-Timeframe Filter
        "use_mtf_filter": False,
        "mtf_timeframes": "1,5,15",
        "mtf_ema_fast": 9,
        "mtf_ema_slow": 21,
        "mtf_agreement_required": 2,

        # FEATURE 1: Risk Management
        "max_daily_loss": -5000.0,
        "max_trades_per_day": 10,
        "daily_target": 5000.0,

        # FEATURE 3: Signal Confidence
        "min_confidence": 0.6,
    }

    # Type mapping for validation
    FIELD_TYPES = {
        # Original fields
        "mode": str,
        "paper_balance": float,
        "allow_live_trading": bool,
        "confirm_live_trades": bool,
        "simulate_slippage": bool,
        "slippage_percent": float,
        "simulate_delay": bool,
        "delay_ms": int,

        # FEATURE 6: Multi-Timeframe Filter
        "use_mtf_filter": bool,
        "mtf_timeframes": str,
        "mtf_ema_fast": int,
        "mtf_ema_slow": int,
        "mtf_agreement_required": int,

        # FEATURE 1: Risk Management
        "max_daily_loss": float,
        "max_trades_per_day": int,
        "daily_target": float,

        # FEATURE 3: Signal Confidence
        "min_confidence": float,
    }

    # Validation ranges
    VALIDATION_RANGES = {
        # Original fields
        "paper_balance": (0, 10_000_000),  # 0 to 10 million
        "slippage_percent": (0, 100),      # 0% to 100%
        "delay_ms": (0, 60000),             # 0 to 60 seconds

        # FEATURE 6: Multi-Timeframe Filter
        "mtf_ema_fast": (1, 50),
        "mtf_ema_slow": (5, 200),
        "mtf_agreement_required": (1, 3),

        # FEATURE 1: Risk Management
        "max_daily_loss": (-1_000_000, 0),  # Negative values only
        "max_trades_per_day": (1, 100),
        "daily_target": (0, 10_000_000),

        # FEATURE 3: Signal Confidence
        "min_confidence": (0.0, 1.0),
    }

    def __init__(self):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Load from database
            self.load()
            logger.info("TradingModeSetting (database) initialized")

        except Exception as e:
            logger.critical(f"[TradingModeSetting.__init__] Failed: {e}", exc_info=True)
            # Still set basic attributes to prevent crashes
            self._set_defaults()

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.mode = TradingMode.SIM
        self.paper_balance = 100000.0
        self.allow_live_trading = False
        self.confirm_live_trades = True
        self.simulate_slippage = True
        self.slippage_percent = 0.05
        self.simulate_delay = True
        self.delay_ms = 500

        # FEATURE 6: Multi-Timeframe Filter
        self.use_mtf_filter = False
        self.mtf_timeframes = "1,5,15"
        self.mtf_ema_fast = 9
        self.mtf_ema_slow = 21
        self.mtf_agreement_required = 2

        # FEATURE 1: Risk Management
        self.max_daily_loss = -5000.0
        self.max_trades_per_day = 10
        self.daily_target = 5000.0

        # FEATURE 3: Signal Confidence
        self.min_confidence = 0.6

        self._loaded = False

    def _set_defaults(self):
        """Set all attributes to default values"""
        try:
            self.mode = TradingMode.SIM
            self.paper_balance = 100000.0
            self.allow_live_trading = False
            self.confirm_live_trades = True
            self.simulate_slippage = True
            self.slippage_percent = 0.05
            self.simulate_delay = True
            self.delay_ms = 500

            # FEATURE 6
            self.use_mtf_filter = False
            self.mtf_timeframes = "1,5,15"
            self.mtf_ema_fast = 9
            self.mtf_ema_slow = 21
            self.mtf_agreement_required = 2

            # FEATURE 1
            self.max_daily_loss = -5000.0
            self.max_trades_per_day = 10
            self.daily_target = 5000.0

            # FEATURE 3
            self.min_confidence = 0.6

        except Exception as e:
            logger.error(f"[TradingModeSetting._set_defaults] Failed: {e}", exc_info=True)

    def _validate_and_convert(self, key: str, value: Any) -> Any:
        """Validate and convert value to the correct type"""
        try:
            # Rule 6: Input validation
            if not isinstance(key, str):
                logger.warning(f"_validate_and_convert called with non-string key: {key}")
                return self.DEFAULTS.get(key, None) if key in self.DEFAULTS else None

            expected_type = self.FIELD_TYPES.get(key, str)

            if value is None:
                logger.debug(f"Value for {key} is None, using default")
                return self.DEFAULTS[key]

            try:
                if key == "mode":
                    # Special handling for mode enum
                    if isinstance(value, TradingMode):
                        return value
                    return TradingMode(str(value))

                elif expected_type == bool:
                    # Handle various boolean representations
                    if isinstance(value, bool):
                        return value
                    elif isinstance(value, str):
                        return value.lower() in ('true', '1', 'yes', 'on', 'y')
                    elif isinstance(value, (int, float)):
                        return value != 0
                    else:
                        return bool(value)

                elif expected_type == int:
                    val = int(float(str(value)))  # Handle both int and float strings
                    # Apply range validation
                    if key in self.VALIDATION_RANGES:
                        min_val, max_val = self.VALIDATION_RANGES[key]
                        val = max(min_val, min(max_val, val))
                    return val

                elif expected_type == float:
                    val = float(value)
                    # Apply range validation
                    if key in self.VALIDATION_RANGES:
                        min_val, max_val = self.VALIDATION_RANGES[key]
                        val = max(min_val, min(max_val, val))
                    return val

                else:  # str
                    return str(value)

            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(f"Failed to convert {key}={value!r} to {expected_type}: {e}")
                return self.DEFAULTS[key]

        except Exception as e:
            logger.error(f"[TradingModeSetting._validate_and_convert] Failed for key={key}: {e}", exc_info=True)
            return self.DEFAULTS.get(key, None) if key in self.DEFAULTS else None

    def _to_bool(self, value: Any) -> bool:
        """Convert various values to boolean."""
        try:
            if value is None:
                return False
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return value != 0
            if isinstance(value, str):
                return value.lower() in ('true', '1', 'yes', 'on', 'y')
            return bool(value)
        except Exception as e:
            logger.warning(f"Boolean conversion failed for {value!r}: {e}")
            return False

    def load(self) -> bool:
        """
        Load settings from database.

        Returns:
            bool: True if load successful, False otherwise
        """
        try:
            db = get_db()
            data = trading_mode.get(db)

            if data:
                # Mode with special handling
                mode_str = data.get("mode", "SIM")
                try:
                    self.mode = TradingMode(mode_str)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid mode value {mode_str!r}: {e}. Using SIM.")
                    self.mode = TradingMode.SIM

                # Paper balance
                try:
                    val = float(data.get("paper_balance", 100000.0))
                    min_val, max_val = self.VALIDATION_RANGES["paper_balance"]
                    self.paper_balance = max(min_val, min(max_val, val))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid paper_balance value: {e}")
                    self.paper_balance = 100000.0

                # Boolean flags
                self.allow_live_trading = self._to_bool(data.get("allow_live_trading", False))
                self.confirm_live_trades = self._to_bool(data.get("confirm_live_trades", True))
                self.simulate_slippage = self._to_bool(data.get("simulate_slippage", True))
                self.simulate_delay = self._to_bool(data.get("simulate_delay", True))

                # Slippage percent
                try:
                    val = float(data.get("slippage_percent", 0.05))
                    min_val, max_val = self.VALIDATION_RANGES["slippage_percent"]
                    self.slippage_percent = max(min_val, min(max_val, val))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid slippage_percent value: {e}")
                    self.slippage_percent = 0.05

                # Delay MS
                try:
                    val = int(float(str(data.get("delay_ms", 500))))
                    min_val, max_val = self.VALIDATION_RANGES["delay_ms"]
                    self.delay_ms = max(min_val, min(max_val, val))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid delay_ms value: {e}")
                    self.delay_ms = 500

                # ==================================================================
                # FEATURE 6: Multi-Timeframe Filter
                # ==================================================================
                try:
                    self.use_mtf_filter = self._to_bool(data.get("use_mtf_filter", False))
                except Exception as e:
                    logger.warning(f"Invalid use_mtf_filter value: {e}")
                    self.use_mtf_filter = False

                try:
                    val = str(data.get("mtf_timeframes", "1,5,15"))
                    self.mtf_timeframes = val
                except Exception as e:
                    logger.warning(f"Invalid mtf_timeframes value: {e}")
                    self.mtf_timeframes = "1,5,15"

                try:
                    val = int(float(str(data.get("mtf_ema_fast", 9))))
                    min_val, max_val = self.VALIDATION_RANGES["mtf_ema_fast"]
                    self.mtf_ema_fast = max(min_val, min(max_val, val))
                except Exception as e:
                    logger.warning(f"Invalid mtf_ema_fast value: {e}")
                    self.mtf_ema_fast = 9

                try:
                    val = int(float(str(data.get("mtf_ema_slow", 21))))
                    min_val, max_val = self.VALIDATION_RANGES["mtf_ema_slow"]
                    self.mtf_ema_slow = max(min_val, min(max_val, val))
                except Exception as e:
                    logger.warning(f"Invalid mtf_ema_slow value: {e}")
                    self.mtf_ema_slow = 21

                try:
                    val = int(float(str(data.get("mtf_agreement_required", 2))))
                    min_val, max_val = self.VALIDATION_RANGES["mtf_agreement_required"]
                    self.mtf_agreement_required = max(min_val, min(max_val, val))
                except Exception as e:
                    logger.warning(f"Invalid mtf_agreement_required value: {e}")
                    self.mtf_agreement_required = 2

                # ==================================================================
                # FEATURE 1: Risk Management
                # ==================================================================
                try:
                    val = float(data.get("max_daily_loss", -5000.0))
                    min_val, max_val = self.VALIDATION_RANGES["max_daily_loss"]
                    self.max_daily_loss = max(min_val, min(max_val, val))
                except Exception as e:
                    logger.warning(f"Invalid max_daily_loss value: {e}")
                    self.max_daily_loss = -5000.0

                try:
                    val = int(float(str(data.get("max_trades_per_day", 10))))
                    min_val, max_val = self.VALIDATION_RANGES["max_trades_per_day"]
                    self.max_trades_per_day = max(min_val, min(max_val, val))
                except Exception as e:
                    logger.warning(f"Invalid max_trades_per_day value: {e}")
                    self.max_trades_per_day = 10

                try:
                    val = float(data.get("daily_target", 5000.0))
                    min_val, max_val = self.VALIDATION_RANGES["daily_target"]
                    self.daily_target = max(min_val, min(max_val, val))
                except Exception as e:
                    logger.warning(f"Invalid daily_target value: {e}")
                    self.daily_target = 5000.0

                # ==================================================================
                # FEATURE 3: Signal Confidence
                # ==================================================================
                try:
                    val = float(data.get("min_confidence", 0.6))
                    min_val, max_val = self.VALIDATION_RANGES["min_confidence"]
                    self.min_confidence = max(min_val, min(max_val, val))
                except Exception as e:
                    logger.warning(f"Invalid min_confidence value: {e}")
                    self.min_confidence = 0.6

                self._loaded = True
                logger.debug("Trading mode settings loaded from database")
                return True
            else:
                # No data found, use defaults
                self._set_defaults()
                return False

        except Exception as e:
            logger.error(f"[TradingModeSetting.load] Failed: {e}", exc_info=True)
            self._set_defaults()
            return False

    def save(self) -> bool:
        """
        Save settings to database.

        Returns:
            bool: True if save successful, False otherwise
        """
        try:
            db = get_db()
            data = self.to_dict()
            success = trading_mode.save(data, db)

            if success:
                logger.debug("Trading mode settings saved to database")
            else:
                logger.error("Failed to save trading mode settings to database")

            return success

        except Exception as e:
            logger.error(f"[TradingModeSetting.save] Failed: {e}", exc_info=True)
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        try:
            return {
                # Original fields
                "mode": self.mode.value if self.mode else TradingMode.SIM.value,
                "paper_balance": float(self.paper_balance) if self.paper_balance is not None else 100000.0,
                "allow_live_trading": bool(self.allow_live_trading),
                "confirm_live_trades": bool(self.confirm_live_trades),
                "simulate_slippage": bool(self.simulate_slippage),
                "slippage_percent": float(self.slippage_percent) if self.slippage_percent is not None else 0.05,
                "simulate_delay": bool(self.simulate_delay),
                "delay_ms": int(self.delay_ms) if self.delay_ms is not None else 500,

                # FEATURE 6
                "use_mtf_filter": bool(self.use_mtf_filter),
                "mtf_timeframes": str(self.mtf_timeframes) if self.mtf_timeframes else "1,5,15",
                "mtf_ema_fast": int(self.mtf_ema_fast) if self.mtf_ema_fast is not None else 9,
                "mtf_ema_slow": int(self.mtf_ema_slow) if self.mtf_ema_slow is not None else 21,
                "mtf_agreement_required": int(self.mtf_agreement_required) if self.mtf_agreement_required is not None else 2,

                # FEATURE 1
                "max_daily_loss": float(self.max_daily_loss) if self.max_daily_loss is not None else -5000.0,
                "max_trades_per_day": int(self.max_trades_per_day) if self.max_trades_per_day is not None else 10,
                "daily_target": float(self.daily_target) if self.daily_target is not None else 5000.0,

                # FEATURE 3
                "min_confidence": float(self.min_confidence) if self.min_confidence is not None else 0.6,
            }
        except Exception as e:
            logger.error(f"[TradingModeSetting.to_dict] Failed: {e}", exc_info=True)
            return {
                "mode": TradingMode.SIM.value,
                "paper_balance": 100000.0,
                "allow_live_trading": False,
                "confirm_live_trades": True,
                "simulate_slippage": True,
                "slippage_percent": 0.05,
                "simulate_delay": True,
                "delay_ms": 500,
                "use_mtf_filter": False,
                "mtf_timeframes": "1,5,15",
                "mtf_ema_fast": 9,
                "mtf_ema_slow": 21,
                "mtf_agreement_required": 2,
                "max_daily_loss": -5000.0,
                "max_trades_per_day": 10,
                "daily_target": 5000.0,
                "min_confidence": 0.6,
            }

    def from_dict(self, data: Optional[Dict[str, Any]]) -> None:
        """Load settings from dictionary."""
        try:
            # Rule 6: Input validation
            if data is None:
                logger.warning("from_dict called with None, using defaults")
                self._set_defaults()
                return

            if not isinstance(data, dict):
                logger.error(f"from_dict expected dict, got {type(data)}. Using defaults.")
                self._set_defaults()
                return

            # Mode with special handling
            mode_str = data.get("mode", "Simulation")
            try:
                self.mode = TradingMode(mode_str)
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid mode value {mode_str!r}: {e}. Using SIM.")
                self.mode = TradingMode.SIM

            # Paper balance
            try:
                val = float(data.get("paper_balance", 100000.0))
                min_val, max_val = self.VALIDATION_RANGES["paper_balance"]
                self.paper_balance = max(min_val, min(max_val, val))
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid paper_balance value: {e}")
                self.paper_balance = 100000.0

            # Boolean flags
            self.allow_live_trading = self._to_bool(data.get("allow_live_trading", False))
            self.confirm_live_trades = self._to_bool(data.get("confirm_live_trades", True))
            self.simulate_slippage = self._to_bool(data.get("simulate_slippage", True))
            self.simulate_delay = self._to_bool(data.get("simulate_delay", True))

            # Slippage percent
            try:
                val = float(data.get("slippage_percent", 0.05))
                min_val, max_val = self.VALIDATION_RANGES["slippage_percent"]
                self.slippage_percent = max(min_val, min(max_val, val))
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid slippage_percent value: {e}")
                self.slippage_percent = 0.05

            # Delay MS
            try:
                val = int(float(str(data.get("delay_ms", 500))))
                min_val, max_val = self.VALIDATION_RANGES["delay_ms"]
                self.delay_ms = max(min_val, min(max_val, val))
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid delay_ms value: {e}")
                self.delay_ms = 500

            # ==================================================================
            # FEATURE 6: Multi-Timeframe Filter
            # ==================================================================
            self.use_mtf_filter = self._to_bool(data.get("use_mtf_filter", False))

            try:
                self.mtf_timeframes = str(data.get("mtf_timeframes", "1,5,15"))
            except Exception as e:
                logger.warning(f"Invalid mtf_timeframes value: {e}")
                self.mtf_timeframes = "1,5,15"

            try:
                val = int(float(str(data.get("mtf_ema_fast", 9))))
                min_val, max_val = self.VALIDATION_RANGES["mtf_ema_fast"]
                self.mtf_ema_fast = max(min_val, min(max_val, val))
            except Exception as e:
                logger.warning(f"Invalid mtf_ema_fast value: {e}")
                self.mtf_ema_fast = 9

            try:
                val = int(float(str(data.get("mtf_ema_slow", 21))))
                min_val, max_val = self.VALIDATION_RANGES["mtf_ema_slow"]
                self.mtf_ema_slow = max(min_val, min(max_val, val))
            except Exception as e:
                logger.warning(f"Invalid mtf_ema_slow value: {e}")
                self.mtf_ema_slow = 21

            try:
                val = int(float(str(data.get("mtf_agreement_required", 2))))
                min_val, max_val = self.VALIDATION_RANGES["mtf_agreement_required"]
                self.mtf_agreement_required = max(min_val, min(max_val, val))
            except Exception as e:
                logger.warning(f"Invalid mtf_agreement_required value: {e}")
                self.mtf_agreement_required = 2

            # ==================================================================
            # FEATURE 1: Risk Management
            # ==================================================================
            try:
                val = float(data.get("max_daily_loss", -5000.0))
                min_val, max_val = self.VALIDATION_RANGES["max_daily_loss"]
                self.max_daily_loss = max(min_val, min(max_val, val))
            except Exception as e:
                logger.warning(f"Invalid max_daily_loss value: {e}")
                self.max_daily_loss = -5000.0

            try:
                val = int(float(str(data.get("max_trades_per_day", 10))))
                min_val, max_val = self.VALIDATION_RANGES["max_trades_per_day"]
                self.max_trades_per_day = max(min_val, min(max_val, val))
            except Exception as e:
                logger.warning(f"Invalid max_trades_per_day value: {e}")
                self.max_trades_per_day = 10

            try:
                val = float(data.get("daily_target", 5000.0))
                min_val, max_val = self.VALIDATION_RANGES["daily_target"]
                self.daily_target = max(min_val, min(max_val, val))
            except Exception as e:
                logger.warning(f"Invalid daily_target value: {e}")
                self.daily_target = 5000.0

            # ==================================================================
            # FEATURE 3: Signal Confidence
            # ==================================================================
            try:
                val = float(data.get("min_confidence", 0.6))
                min_val, max_val = self.VALIDATION_RANGES["min_confidence"]
                self.min_confidence = max(min_val, min(max_val, val))
            except Exception as e:
                logger.warning(f"Invalid min_confidence value: {e}")
                self.min_confidence = 0.6

            self._loaded = True
            logger.debug("Trading mode settings loaded from dict")

        except Exception as e:
            logger.error(f"[TradingModeSetting.from_dict] Failed: {e}", exc_info=True)
            self._set_defaults()

    # ==================================================================
    # Helper methods for mode checking
    # ==================================================================

    def is_live(self) -> bool:
        """Check if live trading mode is active."""
        try:
            return self.mode == TradingMode.LIVE and self.allow_live_trading
        except Exception as e:
            logger.error(f"[TradingModeSetting.is_live] Failed: {e}", exc_info=True)
            return False

    def is_sim(self) -> bool:
        """Check if simulation mode is active."""
        try:
            return self.mode == TradingMode.SIM
        except Exception as e:
            logger.error(f"[TradingModeSetting.is_sim] Failed: {e}", exc_info=True)
            return True  # Default to SIM for safety

    def is_backtest(self) -> bool:
        """Check if backtest mode is active."""
        try:
            return self.mode == TradingMode.BACKTEST
        except Exception as e:
            logger.error(f"[TradingModeSetting.is_backtest] Failed: {e}", exc_info=True)
            return False

    def get_mode_name(self) -> str:
        """Get current mode name as string."""
        try:
            return self.mode.value if self.mode else TradingMode.SIM.value
        except Exception as e:
            logger.error(f"[TradingModeSetting.get_mode_name] Failed: {e}", exc_info=True)
            return TradingMode.SIM.value

    # ==================================================================
    # FEATURE 6: Multi-Timeframe Filter helpers
    # ==================================================================

    def get_mtf_timeframes_list(self) -> list:
        """Get MTF timeframes as list of strings."""
        try:
            if self.mtf_timeframes:
                return [t.strip() for t in self.mtf_timeframes.split(',') if t.strip()]
            return ['1', '5', '15']
        except Exception as e:
            logger.error(f"[TradingModeSetting.get_mtf_timeframes_list] Failed: {e}", exc_info=True)
            return ['1', '5', '15']

    # ==================================================================
    # FEATURE 1: Risk Management helpers
    # ==================================================================

    def get_risk_summary(self) -> Dict[str, Any]:
        """Get risk management summary."""
        try:
            return {
                'max_daily_loss': self.max_daily_loss,
                'max_trades_per_day': self.max_trades_per_day,
                'daily_target': self.daily_target,
                'min_confidence': self.min_confidence,
            }
        except Exception as e:
            logger.error(f"[TradingModeSetting.get_risk_summary] Failed: {e}", exc_info=True)
            return {
                'max_daily_loss': -5000.0,
                'max_trades_per_day': 10,
                'daily_target': 5000.0,
                'min_confidence': 0.6,
            }

    def __repr__(self) -> str:
        """String representation of TradingModeSetting."""
        try:
            return f"<TradingModeSetting mode={self.mode.value if self.mode else 'Unknown'}>"
        except Exception as e:
            logger.error(f"[TradingModeSetting.__repr__] Failed: {e}", exc_info=True)
            return "<TradingModeSetting Error>"

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        try:
            logger.info("[TradingModeSetting] Starting cleanup")
            # No special cleanup needed, but method exists for consistency
            logger.info("[TradingModeSetting] Cleanup completed")
        except Exception as e:
            logger.error(f"[TradingModeSetting.cleanup] Error: {e}", exc_info=True)


# Optional: Context manager for temporary mode changes
class TradingModeContext:
    """
    Context manager for temporarily modifying trading mode.

    Example:
        with TradingModeContext(settings) as tms:
            tms.mode = TradingMode.LIVE
            # ... do something in live mode
        # Settings automatically revert
    """

    def __init__(self, settings: TradingModeSetting):
        # Rule 2: Safe defaults
        self.settings = None
        self._backup = None

        try:
            # Rule 6: Input validation
            if not isinstance(settings, TradingModeSetting):
                raise ValueError(f"Expected TradingModeSetting instance, got {type(settings)}")

            self.settings = settings
            self._backup = settings.to_dict()
            logger.debug("TradingModeContext initialized")

        except Exception as e:
            logger.error(f"[TradingModeContext.__init__] Failed: {e}", exc_info=True)
            raise

    def __enter__(self) -> TradingModeSetting:
        return self.settings

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            # Restore backup
            if self.settings and self._backup is not None:
                self.settings.from_dict(self._backup)
                # Save to database to persist the restoration
                self.settings.save()
                logger.debug("TradingModeContext restored backup")

        except Exception as e:
            logger.error(f"[TradingModeContext.__exit__] Failed: {e}", exc_info=True)
            # Log but don't re-raise to avoid masking original exception
            if exc_type:
                logger.error(f"Original exception: {exc_type.__name__}: {exc_val}")