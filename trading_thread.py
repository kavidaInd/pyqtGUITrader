# PYQT: QThread wrapper for TradingApp to keep GUI responsive
from PyQt5.QtCore import QThread, pyqtSignal
import logging

logger = logging.getLogger(__name__)


class TradingThread(QThread):
    """
    # PYQT: Wraps TradingApp.run() in a QThread so it never blocks the GUI.
    # Signals are the only safe way to communicate results back to the main thread.
    """
    # PYQT: Signals emitted to main thread — never call Qt widgets directly from here
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, trading_app, parent=None):
        super().__init__(parent)
        self.trading_app = trading_app

    def run(self):
        # PYQT: This method runs on the background thread
        try:
            self.trading_app.run()
        except Exception as e:
            logger.error(f"TradingThread crashed: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
        finally:
            self.finished.emit()

    def stop(self):
        """Gracefully stop — called from main thread, executes blocking work here."""
        try:
            state = self.trading_app.state
            if getattr(state, "current_position", None):
                self.trading_app.executor.exit_position(state, reason="Stop app Exit")
            if hasattr(self.trading_app, "ws") and self.trading_app.ws:
                self.trading_app.ws.unsubscribe()
        except Exception as e:
            logger.error(f"TradingThread stop error: {e}", exc_info=True)