"""
SettingsManager.py
==================
Single source of truth for all application settings.

Responsibilities
----------------
1. Own the three settings objects (BrokerageSetting, DailyTradeSetting,
   ProfitStoplossSetting) and load them once at startup.
2. Expose ``apply_to_state(state)`` — pushes every relevant value from
   all three objects into a live TradeState in one atomic call.
3. Emit ``settings_changed`` (PyQt5 signal) whenever any section is saved
   so every connected widget / component can react without polling.
4. Provide ``save_all()`` / ``save_section(name)`` helpers that persist,
   re-apply to a live state if one is registered, and emit the signal.

Threading
---------
All public methods are safe to call from any thread.
The Qt signal is emitted on whichever thread calls ``save_*`` — connect
slots with ``Qt.QueuedConnection`` in GUI components so they are always
invoked on the main thread.

Usage
-----
    # Application startup (main thread)
    from SettingsManager import SettingsManager

    mgr = SettingsManager()          # loads all JSON files
    mgr.apply_to_state(trade_state)  # push settings into engine on boot

    # Register live state so saves auto-apply
    mgr.register_state(trade_state)

    # GUI — react to any change
    mgr.settings_changed.connect(my_slot, Qt.QueuedConnection)

    # Save one section (e.g. from UnifiedSettingsGUI)
    ok, err = mgr.save_section("daily")

    # Save all sections at once
    results = mgr.save_all()
"""

import logging
import threading
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal

from gui.BrokerageSetting import BrokerageSetting
from gui.DailyTradeSetting import DailyTradeSetting
from gui.ProfitStoplossSetting import ProfitStoplossSetting

logger = logging.getLogger(__name__)


class SettingsManager(QObject):
    """
    Central settings manager — own, load, save, and broadcast all settings.

    Signals
    -------
    settings_changed(section: str)
        Emitted after any successful save.
        ``section`` is one of ``"brokerage"``, ``"daily"``, ``"profit"``,
        or ``"all"``.
    """

    settings_changed = pyqtSignal(str)  # section name

    # ------------------------------------------------------------------
    # Construction / loading
    # ------------------------------------------------------------------

    def __init__(self,
                 brokerage_json: str = "config/brokerage_setting.json",
                 daily_json: str = "config/daily_trade_setting.json",
                 profit_json: str = "config/profit_stoploss_setting.json",
                 parent: Optional[QObject] = None):
        super().__init__(parent)

        self._lock = threading.RLock()
        self._state = None  # optional registered TradeState

        # Owned setting objects — each loads its own JSON in __init__
        self.brokerage = BrokerageSetting(brokerage_json)
        self.daily = DailyTradeSetting(daily_json)
        self.profit = ProfitStoplossSetting(profit_json)

        logger.info(
            "SettingsManager loaded — "
            f"exchange={self.daily.exchange!r}  "
            f"derivative={self.daily.derivative!r}  "
            f"profit_type={self.profit.profit_type!r}"
        )

    # ------------------------------------------------------------------
    # State registration
    # ------------------------------------------------------------------

    def register_state(self, state) -> None:
        """
        Register a live TradeState so that every successful save
        automatically calls ``apply_to_state`` without extra wiring.
        """
        with self._lock:
            self._state = state
        logger.info("SettingsManager: TradeState registered for live updates")

    def unregister_state(self) -> None:
        with self._lock:
            self._state = None

    # ------------------------------------------------------------------
    # Apply to TradeState
    # ------------------------------------------------------------------

    def apply_to_state(self, state=None) -> None:
        """
        Push all current settings into *state* (or the registered state).

        Safe to call at startup (before the engine thread starts) and
        during runtime — the TradeState uses its own RLock internally.
        """
        with self._lock:
            target = state or self._state

        if target is None:
            logger.debug("apply_to_state: no TradeState registered — skipping")
            return

        d = self.daily
        p = self.profit

        # ── Daily trade settings ─────────────────────────────────────
        try:
            target.lot_size = d.lot_size
            target.max_num_of_option = d.max_num_of_option
            target.lower_percentage = d.lower_percentage
            target.cancel_after = d.cancel_after
            target.capital_reserve = d.capital_reserve
            target.sideway_zone_trade = d.sideway_zone_trade
            target.call_lookback = d.call_lookback
            target.put_lookback = d.put_lookback
            # Preserve originals so reset_trade_attributes can restore them
            target.original_call_lookback = d.call_lookback
            target.original_put_lookback = d.put_lookback
        except AttributeError as exc:
            logger.warning(f"apply_to_state [daily]: {exc}")

        # ── Profit / stoploss settings ───────────────────────────────
        try:
            target.take_profit_type = p.profit_type
            target.tp_percentage = p.tp_percentage
            target.stoploss_percentage = p.stoploss_percentage
            target.original_profit_per = p.tp_percentage
            target.original_stoploss_per = p.stoploss_percentage
            target.trailing_first_profit = p.trailing_first_profit
            target.max_profit = p.max_profit
            target.profit_step = p.profit_step
            target.loss_step = p.loss_step
        except AttributeError as exc:
            logger.warning(f"apply_to_state [profit]: {exc}")

        logger.info(
            "SettingsManager: settings applied to TradeState — "
            f"lot_size={d.lot_size}  tp={p.tp_percentage}%  sl={p.stoploss_percentage}%"
        )

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------

    def save_section(self, section: str) -> tuple[bool, str]:
        """
        Persist one section and, if successful, apply and broadcast.

        Parameters
        ----------
        section : ``"brokerage"`` | ``"daily"`` | ``"profit"``

        Returns
        -------
        (ok: bool, error_message: str)
        """
        section = section.lower()
        mapping = {
            "brokerage": self.brokerage,
            "daily": self.daily,
            "profit": self.profit,
        }
        obj = mapping.get(section)
        if obj is None:
            return False, f"Unknown section '{section}'"

        try:
            ok = obj.save()
            if ok:
                if section != "brokerage":
                    self.apply_to_state()
                self.settings_changed.emit(section)
                logger.info(f"SettingsManager: section '{section}' saved & applied")
                return True, ""
            else:
                return False, "File write failed"
        except Exception as exc:
            logger.error(f"SettingsManager: save_section({section}) failed: {exc}", exc_info=True)
            return False, str(exc)

    def save_all(self) -> dict[str, tuple[bool, str]]:
        """
        Persist all three sections.

        Returns
        -------
        Dict mapping section name → (ok, error_message)
        """
        results = {}
        any_ok = False
        for name in ("brokerage", "daily", "profit"):
            obj = getattr(self, name if name != "profit" else "profit")
            mapping = {"brokerage": self.brokerage, "daily": self.daily, "profit": self.profit}
            try:
                ok = mapping[name].save()
                results[name] = (ok, "" if ok else "File write failed")
                if ok:
                    any_ok = True
            except Exception as exc:
                results[name] = (False, str(exc))

        if any_ok:
            self.apply_to_state()
            self.settings_changed.emit("all")

        return results

    # ------------------------------------------------------------------
    # Convenience read-only snapshots
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """
        Return a plain-dict copy of every setting value.
        Safe to call from any thread.
        """
        d = self.daily
        p = self.profit
        b = self.brokerage
        return {
            # Brokerage
            "client_id": b.client_id,
            "redirect_uri": b.redirect_uri,
            # secret_key deliberately omitted
            # Daily trade
            "exchange": d.exchange,
            "week": d.week,
            "derivative": d.derivative,
            "lot_size": d.lot_size,
            "call_lookback": d.call_lookback,
            "put_lookback": d.put_lookback,
            "history_interval": d.history_interval,
            "max_num_of_option": d.max_num_of_option,
            "lower_percentage": d.lower_percentage,
            "cancel_after": d.cancel_after,
            "capital_reserve": d.capital_reserve,
            "sideway_zone_trade": d.sideway_zone_trade,
            # Profit / stoploss
            "profit_type": p.profit_type,
            "tp_percentage": p.tp_percentage,
            "stoploss_percentage": p.stoploss_percentage,
            "trailing_first_profit": p.trailing_first_profit,
            "max_profit": p.max_profit,
            "profit_step": p.profit_step,
            "loss_step": p.loss_step,
        }

    def __repr__(self) -> str:
        snap = self.snapshot()
        return (
            f"<SettingsManager "
            f"exchange={snap['exchange']!r} "
            f"derivative={snap['derivative']!r} "
            f"profit_type={snap['profit_type']!r}>"
        )
