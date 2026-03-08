# utils/timing.py
"""
Timing decorator for performance logging.
"""

import time
import functools
import logging

logger = logging.getLogger(__name__)


def timed(log_level=logging.DEBUG, warn_threshold=1.0):
    """
    Decorator to log execution time of functions.

    Args:
        log_level: Logging level for normal execution
        warn_threshold: Seconds after which to log warning
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                if duration > warn_threshold:
                    logger.warning(f"Slow operation: {func.__name__} took {duration:.3f}s")
                else:
                    logger.log(log_level, f"{func.__name__} took {duration:.3f}s")

        return wrapper

    return decorator