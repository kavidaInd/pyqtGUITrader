# PYQT: Qt-compatible log handler replaces Tkinter TextHandler
import logging
from PyQt5.QtCore import QObject, pyqtSignal


class QtLogSignaller(QObject):
    # PYQT: Signal must live on a QObject so it can cross thread boundaries safely
    log_message = pyqtSignal(str)


class QtLogHandler(logging.Handler):
    """
    # PYQT: Replaces the Tkinter TextHandler.
    # Emits log records as Qt signals so the main thread can append them to the log widget.
    """
    def __init__(self):
        super().__init__()
        self.signaller = QtLogSignaller()

    def emit(self, record):
        try:
            msg = self.format(record)
            # PYQT: Emit signal — safe to call from any thread
            self.signaller.log_message.emit(msg)
        except Exception:
            self.handleError(record)