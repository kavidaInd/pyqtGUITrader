"""
backtest/backtest_thread.py
============================
QThread wrapper for BacktestEngine so the GUI stays responsive.

Signals
-------
progress(float, str)   — 0–100 percent + status message
finished(object)       — BacktestResult on completion
error(str)             — error message string
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt5.QtCore import QThread, pyqtSignal

if TYPE_CHECKING:
    from backtest.backtest_engine import BacktestConfig, BacktestResult

logger = logging.getLogger(__name__)


class BacktestThread(QThread):
    progress = pyqtSignal(float, str)   # pct, message
    finished = pyqtSignal(object)       # BacktestResult
    error    = pyqtSignal(str)

    def __init__(self, broker, config: "BacktestConfig", parent=None):
        super().__init__(parent)
        self._broker = broker
        self._config = config
        self._engine = None

    def run(self):
        try:
            from backtest.backtest_engine import BacktestEngine
            self._engine = BacktestEngine(self._broker, self._config)
            self._engine.progress_callback = lambda pct, msg: self.progress.emit(pct, msg)
            result = self._engine.run()
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"[BacktestThread] {e}", exc_info=True)
            self.error.emit(str(e))

    def stop(self):
        if self._engine:
            self._engine.stop()
        self.quit()