"""
DailyTradeSetting_db.py
=======================
Database-backed daily trade settings using the SQLite database.

Enhanced with support for:
- FEATURE 6: Multi-Timeframe Filter settings
- Risk management defaults
- Improved validation
"""

import logging
import logging.handlers
from typing import Any, Dict, Optional

from db.connector import get_db
from db.crud import daily_trade

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class DailyTradeSetting:
    """
    Database-backed daily trade settings using the daily_trade_setting table.

    Enhanced with additional fields for new features.
    This is a drop-in replacement for the JSON-based DailyTradeSetting class,
    maintaining the same interface while using the database.
    """

    DEFAULTS = {
        # Original fields
        "exchange": "NSE",
        "week": 0,
        "derivative": "NIFTY50",
        "lot_size": 65,
        "call_lookback": 0,
        "put_lookback": 0,
        "history_interval": "2m",
        "max_num_of_option": 1800,
        "lower_percentage": 0,
        "cancel_after": 5,
        "capital_reserve": 0,
        "sideway_zone_trade": False,

        # FEATURE 6: Multi-Timeframe Filter settings
        "use_mtf_filter": False,
        "mtf_timeframes": "1,5,15",
        "mtf_ema_fast": 9,
        "mtf_ema_slow": 21,
        "mtf_agreement_required": 2,

        # FEATURE 1: Risk limits (moved from config)
        "max_daily_loss": -5000,
        "max_trades_per_day": 10,
        "daily_target": 5000,

        # FEATURE 3: Signal confidence
        "min_confidence": 0.6,

        # Market hours (BUG #4 fix)
        "market_open_time": "09:15",
        "market_close_time": "15:30",
    }

    # Type mapping for validation
    FIELD_TYPES = {
        # Original fields
        "exchange": str,
        "week": int,
        "derivative": str,
        "lot_size": int,
        "call_lookback": int,
        "put_lookback": int,
        "history_interval": str,
        "max_num_of_option": int,
        "lower_percentage": float,
        "cancel_after": int,
        "capital_reserve": int,
        "sideway_zone_trade": bool,

        # FEATURE 6: Multi-Timeframe Filter
        "use_mtf_filter": bool,
        "mtf_timeframes": str,
        "mtf_ema_fast": int,
        "mtf_ema_slow": int,
        "mtf_agreement_required": int,

        # FEATURE 1: Risk limits
        "max_daily_loss": float,
        "max_trades_per_day": int,
        "daily_target": float,

        # FEATURE 3: Signal confidence
        "min_confidence": float,

        # Market hours
        "market_open_time": str,
        "market_close_time": str,
    }

    def __init__(self):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Load from database
            self.load()
            logger.info("DailyTradeSetting (database) initialized")

        except Exception as e:
            logger.critical(f"[DailyTradeSetting.__init__] Failed: {e}", exc_info=True)
            # Still set basic attributes to prevent crashes
            self.data = dict(self.DEFAULTS)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.data: Dict[str, Any] = dict(self.DEFAULTS)
        self._loaded = False

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
                if expected_type == bool:
                    # Handle various boolean representations
                    if isinstance(value, str):
                        return value.lower() in ('true', '1', 'yes', 'on')
                    return bool(value)

                elif expected_type == int:
                    # Handle both int and float strings
                    if isinstance(value, (int, float)):
                        return int(value)
                    elif isinstance(value, str):
                        # Try to convert string to int, handle floats in strings
                        try:
                            return int(float(value.strip()))
                        except (ValueError, TypeError):
                            return self.DEFAULTS[key]
                    else:
                        return self.DEFAULTS[key]

                elif expected_type == float:
                    if isinstance(value, (int, float)):
                        return float(value)
                    elif isinstance(value, str):
                        try:
                            return float(value.strip())
                        except (ValueError, TypeError):
                            return self.DEFAULTS[key]
                    else:
                        return self.DEFAULTS[key]

                else:  # str
                    return str(value) if value is not None else self.DEFAULTS[key]

            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(f"Failed to convert {key}={value!r} to {expected_type}: {e}")
                return self.DEFAULTS[key]

        except Exception as e:
            logger.error(f"[DailyTradeSetting._validate_and_convert] Failed for key={key}: {e}", exc_info=True)
            return self.DEFAULTS.get(key, None) if key in self.DEFAULTS else None

    def load(self) -> bool:
        """
        Load settings from database.

        Returns:
            bool: True if load successful, False otherwise
        """
        try:
            db = get_db()
            data = daily_trade.get(db)

            # Always start with defaults
            self.data = dict(self.DEFAULTS)

            if data:
                # Update with loaded values
                for k, v in data.items():
                    if k in self.DEFAULTS:
                        self.data[k] = self._validate_and_convert(k, v)
                    else:
                        # Unknown key - ignore but log
                        logger.debug(f"Ignoring unknown key in database: {k}")

            self._loaded = True
            logger.debug("Daily trade settings loaded from database")
            return True

        except Exception as e:
            logger.error(f"[DailyTradeSetting.load] Failed: {e}", exc_info=True)
            self.data = dict(self.DEFAULTS)
            return False

    def save(self) -> bool:
        """
        Save settings to database.

        Returns:
            bool: True if save successful, False otherwise
        """
        try:
            db = get_db()

            # Filter to only keys that exist in database table
            # (daily_trade table may not have all our new fields)
            save_data = {}
            for k in daily_trade.DEFAULTS.keys():
                if k in self.data:
                    save_data[k] = self.data[k]

            success = daily_trade.save(save_data, db)

            if success:
                logger.debug("Daily trade settings saved to database")
            else:
                logger.error("Failed to save daily trade settings to database")

            return success

        except Exception as e:
            logger.error(f"[DailyTradeSetting.save] Failed: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Original property accessors (preserved)
    # ------------------------------------------------------------------

    @property
    def exchange(self) -> str:
        """Get exchange setting."""
        try:
            return str(self.data.get("exchange", self.DEFAULTS["exchange"]))
        except Exception as e:
            logger.error(f"[DailyTradeSetting.exchange getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["exchange"]

    @exchange.setter
    def exchange(self, value):
        try:
            self.data["exchange"] = str(value) if value is not None else self.DEFAULTS["exchange"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.exchange setter] Failed: {e}", exc_info=True)

    @property
    def week(self) -> int:
        """Get week setting."""
        try:
            val = self.data.get("week", self.DEFAULTS["week"])
            return int(val) if val is not None else self.DEFAULTS["week"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.week getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["week"]

    @week.setter
    def week(self, value):
        try:
            if value is None:
                self.data["week"] = self.DEFAULTS["week"]
            else:
                self.data["week"] = int(float(str(value)))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid week value {value!r}: {e}")
            self.data["week"] = self.DEFAULTS["week"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.week setter] Failed: {e}", exc_info=True)

    @property
    def derivative(self) -> str:
        """Get derivative setting."""
        try:
            return str(self.data.get("derivative", self.DEFAULTS["derivative"]))
        except Exception as e:
            logger.error(f"[DailyTradeSetting.derivative getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["derivative"]

    @derivative.setter
    def derivative(self, value):
        try:
            self.data["derivative"] = str(value) if value is not None else self.DEFAULTS["derivative"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.derivative setter] Failed: {e}", exc_info=True)

    @property
    def lot_size(self) -> int:
        """Get lot size setting."""
        try:
            val = self.data.get("lot_size", self.DEFAULTS["lot_size"])
            return int(val) if val is not None else self.DEFAULTS["lot_size"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.lot_size getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["lot_size"]

    @lot_size.setter
    def lot_size(self, value):
        try:
            if value is None:
                self.data["lot_size"] = self.DEFAULTS["lot_size"]
            else:
                val = int(float(str(value)))
                self.data["lot_size"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid lot_size value {value!r}: {e}")
            self.data["lot_size"] = self.DEFAULTS["lot_size"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.lot_size setter] Failed: {e}", exc_info=True)

    @property
    def call_lookback(self) -> int:
        """Get call lookback setting."""
        try:
            val = self.data.get("call_lookback", self.DEFAULTS["call_lookback"])
            return int(val) if val is not None else self.DEFAULTS["call_lookback"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.call_lookback getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["call_lookback"]

    @call_lookback.setter
    def call_lookback(self, value):
        try:
            if value is None:
                self.data["call_lookback"] = self.DEFAULTS["call_lookback"]
            else:
                self.data["call_lookback"] = int(float(str(value)))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid call_lookback value {value!r}: {e}")
            self.data["call_lookback"] = self.DEFAULTS["call_lookback"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.call_lookback setter] Failed: {e}", exc_info=True)

    @property
    def put_lookback(self) -> int:
        """Get put lookback setting."""
        try:
            val = self.data.get("put_lookback", self.DEFAULTS["put_lookback"])
            return int(val) if val is not None else self.DEFAULTS["put_lookback"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.put_lookback getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["put_lookback"]

    @put_lookback.setter
    def put_lookback(self, value):
        try:
            if value is None:
                self.data["put_lookback"] = self.DEFAULTS["put_lookback"]
            else:
                self.data["put_lookback"] = int(float(str(value)))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid put_lookback value {value!r}: {e}")
            self.data["put_lookback"] = self.DEFAULTS["put_lookback"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.put_lookback setter] Failed: {e}", exc_info=True)

    @property
    def history_interval(self) -> str:
        """Get history interval setting."""
        try:
            return str(self.data.get("history_interval", self.DEFAULTS["history_interval"]))
        except Exception as e:
            logger.error(f"[DailyTradeSetting.history_interval getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["history_interval"]

    @history_interval.setter
    def history_interval(self, value):
        try:
            self.data["history_interval"] = str(value) if value is not None else self.DEFAULTS["history_interval"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.history_interval setter] Failed: {e}", exc_info=True)

    @property
    def max_num_of_option(self) -> int:
        """Get max number of option setting."""
        try:
            val = self.data.get("max_num_of_option", self.DEFAULTS["max_num_of_option"])
            return int(val) if val is not None else self.DEFAULTS["max_num_of_option"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.max_num_of_option getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["max_num_of_option"]

    @max_num_of_option.setter
    def max_num_of_option(self, value):
        try:
            if value is None:
                self.data["max_num_of_option"] = self.DEFAULTS["max_num_of_option"]
            else:
                val = int(float(str(value)))
                self.data["max_num_of_option"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid max_num_of_option value {value!r}: {e}")
            self.data["max_num_of_option"] = self.DEFAULTS["max_num_of_option"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.max_num_of_option setter] Failed: {e}", exc_info=True)

    @property
    def lower_percentage(self) -> float:
        """Get lower percentage setting."""
        try:
            val = self.data.get("lower_percentage", self.DEFAULTS["lower_percentage"])
            return float(val) if val is not None else self.DEFAULTS["lower_percentage"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.lower_percentage getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["lower_percentage"]

    @lower_percentage.setter
    def lower_percentage(self, value):
        try:
            if value is None:
                self.data["lower_percentage"] = self.DEFAULTS["lower_percentage"]
            else:
                val = float(value)
                self.data["lower_percentage"] = max(0, min(100, val))  # Clamp between 0-100
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid lower_percentage value {value!r}: {e}")
            self.data["lower_percentage"] = self.DEFAULTS["lower_percentage"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.lower_percentage setter] Failed: {e}", exc_info=True)

    @property
    def cancel_after(self) -> int:
        """Get cancel after setting."""
        try:
            val = self.data.get("cancel_after", self.DEFAULTS["cancel_after"])
            return int(val) if val is not None else self.DEFAULTS["cancel_after"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.cancel_after getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["cancel_after"]

    @cancel_after.setter
    def cancel_after(self, value):
        try:
            if value is None:
                self.data["cancel_after"] = self.DEFAULTS["cancel_after"]
            else:
                val = int(float(str(value)))
                self.data["cancel_after"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid cancel_after value {value!r}: {e}")
            self.data["cancel_after"] = self.DEFAULTS["cancel_after"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.cancel_after setter] Failed: {e}", exc_info=True)

    @property
    def capital_reserve(self) -> int:
        """Get capital reserve setting."""
        try:
            val = self.data.get("capital_reserve", self.DEFAULTS["capital_reserve"])
            return int(val) if val is not None else self.DEFAULTS["capital_reserve"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.capital_reserve getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["capital_reserve"]

    @capital_reserve.setter
    def capital_reserve(self, value):
        try:
            if value is None:
                self.data["capital_reserve"] = self.DEFAULTS["capital_reserve"]
            else:
                val = int(float(str(value)))
                self.data["capital_reserve"] = max(0, val)  # Ensure non-negative
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid capital_reserve value {value!r}: {e}")
            self.data["capital_reserve"] = self.DEFAULTS["capital_reserve"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.capital_reserve setter] Failed: {e}", exc_info=True)

    @property
    def sideway_zone_trade(self) -> bool:
        """Get sideway zone trade setting."""
        try:
            val = self.data.get("sideway_zone_trade", self.DEFAULTS["sideway_zone_trade"])
            return bool(val) if val is not None else self.DEFAULTS["sideway_zone_trade"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.sideway_zone_trade getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["sideway_zone_trade"]

    @sideway_zone_trade.setter
    def sideway_zone_trade(self, value):
        try:
            self.data["sideway_zone_trade"] = bool(value)
        except Exception as e:
            logger.error(f"[DailyTradeSetting.sideway_zone_trade setter] Failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # FEATURE 6: Multi-Timeframe Filter properties
    # ------------------------------------------------------------------

    @property
    def use_mtf_filter(self) -> bool:
        """Get whether MTF filter is enabled."""
        try:
            val = self.data.get("use_mtf_filter", self.DEFAULTS["use_mtf_filter"])
            return bool(val) if val is not None else self.DEFAULTS["use_mtf_filter"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.use_mtf_filter getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["use_mtf_filter"]

    @use_mtf_filter.setter
    def use_mtf_filter(self, value: bool):
        try:
            self.data["use_mtf_filter"] = bool(value)
        except Exception as e:
            logger.error(f"[DailyTradeSetting.use_mtf_filter setter] Failed: {e}", exc_info=True)

    @property
    def mtf_timeframes(self) -> str:
        """Get MTF timeframes as comma-separated string."""
        try:
            return str(self.data.get("mtf_timeframes", self.DEFAULTS["mtf_timeframes"]))
        except Exception as e:
            logger.error(f"[DailyTradeSetting.mtf_timeframes getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["mtf_timeframes"]

    @mtf_timeframes.setter
    def mtf_timeframes(self, value: str):
        try:
            # Validate format (comma-separated numbers)
            if value:
                parts = [p.strip() for p in value.split(',')]
                # Check if all parts are valid numbers
                for p in parts:
                    if p and not p.isdigit():
                        logger.warning(f"Invalid timeframe format: {p}")
                        return
                self.data["mtf_timeframes"] = value
            else:
                self.data["mtf_timeframes"] = self.DEFAULTS["mtf_timeframes"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.mtf_timeframes setter] Failed: {e}", exc_info=True)

    def get_mtf_timeframes_list(self) -> list:
        """Get MTF timeframes as list of strings."""
        try:
            tf_str = self.mtf_timeframes
            if tf_str:
                return [t.strip() for t in tf_str.split(',') if t.strip()]
            return ['1', '5', '15']
        except Exception as e:
            logger.error(f"[DailyTradeSetting.get_mtf_timeframes_list] Failed: {e}", exc_info=True)
            return ['1', '5', '15']

    @property
    def mtf_ema_fast(self) -> int:
        """Get MTF fast EMA period."""
        try:
            val = self.data.get("mtf_ema_fast", self.DEFAULTS["mtf_ema_fast"])
            return int(val) if val is not None else self.DEFAULTS["mtf_ema_fast"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.mtf_ema_fast getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["mtf_ema_fast"]

    @mtf_ema_fast.setter
    def mtf_ema_fast(self, value: int):
        try:
            if value is None:
                self.data["mtf_ema_fast"] = self.DEFAULTS["mtf_ema_fast"]
            else:
                val = int(float(str(value)))
                self.data["mtf_ema_fast"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid mtf_ema_fast value {value!r}: {e}")
            self.data["mtf_ema_fast"] = self.DEFAULTS["mtf_ema_fast"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.mtf_ema_fast setter] Failed: {e}", exc_info=True)

    @property
    def mtf_ema_slow(self) -> int:
        """Get MTF slow EMA period."""
        try:
            val = self.data.get("mtf_ema_slow", self.DEFAULTS["mtf_ema_slow"])
            return int(val) if val is not None else self.DEFAULTS["mtf_ema_slow"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.mtf_ema_slow getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["mtf_ema_slow"]

    @mtf_ema_slow.setter
    def mtf_ema_slow(self, value: int):
        try:
            if value is None:
                self.data["mtf_ema_slow"] = self.DEFAULTS["mtf_ema_slow"]
            else:
                val = int(float(str(value)))
                self.data["mtf_ema_slow"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid mtf_ema_slow value {value!r}: {e}")
            self.data["mtf_ema_slow"] = self.DEFAULTS["mtf_ema_slow"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.mtf_ema_slow setter] Failed: {e}", exc_info=True)

    @property
    def mtf_agreement_required(self) -> int:
        """Get number of timeframes required to agree."""
        try:
            val = self.data.get("mtf_agreement_required", self.DEFAULTS["mtf_agreement_required"])
            return int(val) if val is not None else self.DEFAULTS["mtf_agreement_required"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.mtf_agreement_required getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["mtf_agreement_required"]

    @mtf_agreement_required.setter
    def mtf_agreement_required(self, value: int):
        try:
            if value is None:
                self.data["mtf_agreement_required"] = self.DEFAULTS["mtf_agreement_required"]
            else:
                val = int(float(str(value)))
                # Clamp between 1 and 3 (max timeframes)
                self.data["mtf_agreement_required"] = max(1, min(3, val))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid mtf_agreement_required value {value!r}: {e}")
            self.data["mtf_agreement_required"] = self.DEFAULTS["mtf_agreement_required"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.mtf_agreement_required setter] Failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # FEATURE 1: Risk limit properties
    # ------------------------------------------------------------------

    @property
    def max_daily_loss(self) -> float:
        """Get maximum daily loss limit."""
        try:
            val = self.data.get("max_daily_loss", self.DEFAULTS["max_daily_loss"])
            return float(val) if val is not None else self.DEFAULTS["max_daily_loss"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.max_daily_loss getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["max_daily_loss"]

    @max_daily_loss.setter
    def max_daily_loss(self, value: float):
        try:
            if value is None:
                self.data["max_daily_loss"] = self.DEFAULTS["max_daily_loss"]
            else:
                val = float(value)
                # Ensure it's negative (loss limit)
                if val > 0:
                    val = -val
                self.data["max_daily_loss"] = val
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid max_daily_loss value {value!r}: {e}")
            self.data["max_daily_loss"] = self.DEFAULTS["max_daily_loss"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.max_daily_loss setter] Failed: {e}", exc_info=True)

    @property
    def max_trades_per_day(self) -> int:
        """Get maximum trades per day."""
        try:
            val = self.data.get("max_trades_per_day", self.DEFAULTS["max_trades_per_day"])
            return int(val) if val is not None else self.DEFAULTS["max_trades_per_day"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.max_trades_per_day getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["max_trades_per_day"]

    @max_trades_per_day.setter
    def max_trades_per_day(self, value: int):
        try:
            if value is None:
                self.data["max_trades_per_day"] = self.DEFAULTS["max_trades_per_day"]
            else:
                val = int(float(str(value)))
                self.data["max_trades_per_day"] = max(1, val)  # Ensure positive
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid max_trades_per_day value {value!r}: {e}")
            self.data["max_trades_per_day"] = self.DEFAULTS["max_trades_per_day"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.max_trades_per_day setter] Failed: {e}", exc_info=True)

    @property
    def daily_target(self) -> float:
        """Get daily profit target."""
        try:
            val = self.data.get("daily_target", self.DEFAULTS["daily_target"])
            return float(val) if val is not None else self.DEFAULTS["daily_target"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.daily_target getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["daily_target"]

    @daily_target.setter
    def daily_target(self, value: float):
        try:
            if value is None:
                self.data["daily_target"] = self.DEFAULTS["daily_target"]
            else:
                val = float(value)
                self.data["daily_target"] = max(0, val)  # Ensure non-negative
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid daily_target value {value!r}: {e}")
            self.data["daily_target"] = self.DEFAULTS["daily_target"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.daily_target setter] Failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # FEATURE 3: Signal confidence property
    # ------------------------------------------------------------------

    @property
    def min_confidence(self) -> float:
        """Get minimum confidence threshold."""
        try:
            val = self.data.get("min_confidence", self.DEFAULTS["min_confidence"])
            return float(val) if val is not None else self.DEFAULTS["min_confidence"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.min_confidence getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["min_confidence"]

    @min_confidence.setter
    def min_confidence(self, value: float):
        try:
            if value is None:
                self.data["min_confidence"] = self.DEFAULTS["min_confidence"]
            else:
                val = float(value)
                # Clamp between 0 and 1
                self.data["min_confidence"] = max(0, min(1, val))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid min_confidence value {value!r}: {e}")
            self.data["min_confidence"] = self.DEFAULTS["min_confidence"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.min_confidence setter] Failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Market hours (BUG #4 fix)
    # ------------------------------------------------------------------

    @property
    def market_open_time(self) -> str:
        """Get market open time (HH:MM format)."""
        try:
            return str(self.data.get("market_open_time", self.DEFAULTS["market_open_time"]))
        except Exception as e:
            logger.error(f"[DailyTradeSetting.market_open_time getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["market_open_time"]

    @market_open_time.setter
    def market_open_time(self, value: str):
        try:
            # Validate time format
            if value and ':' in value:
                parts = value.split(':')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    self.data["market_open_time"] = value
                else:
                    logger.warning(f"Invalid time format: {value}")
            else:
                self.data["market_open_time"] = self.DEFAULTS["market_open_time"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.market_open_time setter] Failed: {e}", exc_info=True)

    @property
    def market_close_time(self) -> str:
        """Get market close time (HH:MM format)."""
        try:
            return str(self.data.get("market_close_time", self.DEFAULTS["market_close_time"]))
        except Exception as e:
            logger.error(f"[DailyTradeSetting.market_close_time getter] Failed: {e}", exc_info=True)
            return self.DEFAULTS["market_close_time"]

    @market_close_time.setter
    def market_close_time(self, value: str):
        try:
            # Validate time format
            if value and ':' in value:
                parts = value.split(':')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    self.data["market_close_time"] = value
                else:
                    logger.warning(f"Invalid time format: {value}")
            else:
                self.data["market_close_time"] = self.DEFAULTS["market_close_time"]
        except Exception as e:
            logger.error(f"[DailyTradeSetting.market_close_time setter] Failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        try:
            return dict(self.data)
        except Exception as e:
            logger.error(f"[DailyTradeSetting.to_dict] Failed: {e}", exc_info=True)
            return dict(self.DEFAULTS)

    def from_dict(self, d: Optional[Dict[str, Any]]) -> None:
        """Load settings from dictionary."""
        try:
            # Rule 6: Input validation
            if d is None:
                logger.warning("from_dict called with None, using defaults")
                self.data = dict(self.DEFAULTS)
                return

            if not isinstance(d, dict):
                logger.error(f"from_dict expected dict, got {type(d)}. Using defaults.")
                self.data = dict(self.DEFAULTS)
                return

            for k in self.DEFAULTS:
                if k in d:
                    self.data[k] = self._validate_and_convert(k, d[k])

        except Exception as e:
            logger.error(f"[DailyTradeSetting.from_dict] Failed: {e}", exc_info=True)
            self.data = dict(self.DEFAULTS)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get setting value by key with safe default.

        Args:
            key: Setting key
            default: Default value if key not found

        Returns:
            Setting value or default
        """
        try:
            # Rule 6: Input validation
            if not isinstance(key, str):
                logger.warning(f"get() called with non-string key: {key}")
                return default

            if key in self.FIELD_TYPES:
                return self.data.get(key, default)
            else:
                logger.warning(f"get() called with unknown key: {key}")
                return default

        except Exception as e:
            logger.error(f"[DailyTradeSetting.get] Failed for key '{key}': {e}", exc_info=True)
            return default

    def __repr__(self) -> str:
        """String representation of DailyTradeSetting."""
        try:
            return f"<DailyTradeSetting {self.data}>"
        except Exception as e:
            logger.error(f"[DailyTradeSetting.__repr__] Failed: {e}", exc_info=True)
            return "<DailyTradeSetting Error>"

    # Rule 8: Cleanup method
    def cleanup(self) -> None:
        """Clean up resources before shutdown."""
        try:
            logger.info("[DailyTradeSetting] Starting cleanup")
            # Clear data
            self.data.clear()
            logger.info("[DailyTradeSetting] Cleanup completed")
        except Exception as e:
            logger.error(f"[DailyTradeSetting.cleanup] Error: {e}", exc_info=True)


# Optional: Context manager for temporary settings changes
class DailyTradeSettingContext:
    """
    Context manager for temporarily modifying daily trade settings.

    Example:
        with DailyTradeSettingContext(settings) as dts:
            dts.lot_size = 100
            # ... do something with temp settings
        # Settings automatically revert
    """

    def __init__(self, settings: DailyTradeSetting):
        # Rule 2: Safe defaults
        self.settings = None
        self._backup = None

        try:
            # Rule 6: Input validation
            if not isinstance(settings, DailyTradeSetting):
                raise ValueError(f"Expected DailyTradeSetting instance, got {type(settings)}")

            self.settings = settings
            self._backup = settings.to_dict()
            logger.debug("DailyTradeSettingContext initialized")

        except Exception as e:
            logger.error(f"[DailyTradeSettingContext.__init__] Failed: {e}", exc_info=True)
            raise

    def __enter__(self) -> DailyTradeSetting:
        return self.settings

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            # Restore backup
            if self.settings and self._backup is not None:
                self.settings.from_dict(self._backup)
                # Save to database to persist the restoration
                self.settings.save()
                logger.debug("DailyTradeSettingContext restored backup")

        except Exception as e:
            logger.error(f"[DailyTradeSettingContext.__exit__] Failed: {e}", exc_info=True)
            # Log but don't re-raise to avoid masking original exception
            if exc_type:
                logger.error(f"Original exception: {exc_type.__name__}: {exc_val}")