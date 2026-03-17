# utils/structured_logger.py
"""
Structured logging with context and JSON output.
"""

import logging
import json
import threading
from datetime import datetime
from typing import Dict, Any, Optional
# TZ-FIX: log record timestamps must reflect IST wall clock time.
from Utils.time_utils import ist_now


class StructuredLogger:
    """
    Structured logger with context and JSON output option.

    Usage:
        log = StructuredLogger('trading_app')
        log.set_context(symbol='NIFTY', strategy='momentum')
        log.info('Trade executed', entry_price=18500, quantity=75)
    """

    _local = threading.local()

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._context: Dict[str, Any] = {}

    def set_context(self, **kwargs):
        """Set context for all subsequent logs."""
        self._context.update(kwargs)

    def clear_context(self):
        """Clear context."""
        self._context.clear()

    def _format(self, level: str, msg: str, **kwargs) -> str:
        """Format log message with context."""
        record = {
            'timestamp': ist_now().isoformat(),
            'level': level,
            'logger': self.logger.name,
            'thread': threading.current_thread().name,
            'message': msg,
            **self._context,
            **kwargs
        }
        return json.dumps(record)

    def debug(self, msg: str, **kwargs):
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(self._format('DEBUG', msg, **kwargs))

    def info(self, msg: str, **kwargs):
        self.logger.info(self._format('INFO', msg, **kwargs))

    def warning(self, msg: str, **kwargs):
        self.logger.warning(self._format('WARNING', msg, **kwargs))

    def error(self, msg: str, exc_info: bool = False, **kwargs):
        self.logger.error(self._format('ERROR', msg, **kwargs), exc_info=exc_info)

    def critical(self, msg: str, exc_info: bool = False, **kwargs):
        self.logger.critical(self._format('CRITICAL', msg, **kwargs), exc_info=exc_info)