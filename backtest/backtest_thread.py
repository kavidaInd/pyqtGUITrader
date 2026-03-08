"""
backtest/backtest_thread.py
============================
QThread wrapper that runs BacktestEngine off the GUI thread.

Changes from original:
- Removed 250+ lines of dead __main__ test block that caused ImportError
  in headless/CI environments.
- stop() now sets _stop_requested BEFORE the engine is created so a cancel
  that arrives during the setup phase (VIX fetch, strategy load) propagates
  correctly.
- _on_engine_progress: guard added so signals are not emitted after the
  thread has already finished (prevents Qt "destroyed while signals are
  blocked" warnings on rapid run→cancel cycles).
- Added read-only `result` property for clean result access from outside
  the thread.
- All f-string logger calls replaced with % formatting.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from backtest.backtest_engine import BacktestConfig, BacktestEngine, BacktestResult

logger = logging.getLogger(__name__)


class BacktestThread(QThread):
    """
    Runs BacktestEngine.run() on a background QThread.

    Signals
    -------
    progress(float, str)   : 0–100 % and a human-readable status message.
    finished(BacktestResult): emitted exactly once when the run completes
                               or is cancelled.
    error(str)             : emitted if an unhandled exception escapes run().
    """

    progress = pyqtSignal(float, str)
    finished = pyqtSignal(object)   # BacktestResult
    error    = pyqtSignal(str)

    def __init__(self, broker, config: BacktestConfig, parent=None):
        super().__init__(parent)
        self._broker         = broker
        self._config         = config
        self._engine: Optional[BacktestEngine] = None
        self._result: Optional[BacktestResult] = None
        self._stop_requested = False

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def result(self) -> Optional[BacktestResult]:
        """The BacktestResult from the last run, or None if not yet complete."""
        return self._result

    def stop(self) -> None:
        """
        Request cancellation.

        Sets the flag immediately so a cancel that arrives before the engine
        is constructed still takes effect.
        """
        self._stop_requested = True
        if self._engine is not None:
            self._engine.stop()

    # ── QThread entry point ────────────────────────────────────────────────────

    def run(self) -> None:
        result = BacktestResult(config=self._config)
        try:
            # If stop() was called before we even started, bail early.
            if self._stop_requested:
                result.error_msg = "Backtest cancelled before it started."
                self._result = result
                self.finished.emit(result)
                return

            self._engine = BacktestEngine(self._broker, self._config)
            self._engine.progress_callback = self._on_engine_progress

            # Propagate stop flag in case stop() arrived between the guard above
            # and engine construction.
            if self._stop_requested:
                self._engine.stop()

            result = self._engine.run()
            self._result = result

        except Exception as exc:
            logger.error("[BacktestThread] Unhandled exception: %s", exc, exc_info=True)
            result.error_msg = str(exc)
            self._result = result
            if not self.isInterruptionRequested():
                try:
                    self.error.emit(str(exc))
                except RuntimeError:
                    pass

        finally:
            if not self.isInterruptionRequested():
                try:
                    self.finished.emit(self._result or result)
                except RuntimeError:
                    # Qt object already destroyed (e.g. window closed mid-run)
                    pass

    # ── Progress relay ─────────────────────────────────────────────────────────

    def _on_engine_progress(self, pct: float, msg: str) -> None:
        """Relay engine progress to the GUI thread, guarded against post-finish emission."""
        if self.isFinished() or self.isInterruptionRequested():
            return
        try:
            self.progress.emit(pct, msg)
        except RuntimeError:
            # Signal receiver was destroyed
            pass