# Utils/safe_getattr.py
import inspect
import logging
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


def safe_getattr(obj: Any, attr_name: str, default: T = None, log_level: int = logging.WARNING) -> T:
    """
    Safe getattr with logging when attribute is missing.

    Args:
        obj: Object to get attribute from
        attr_name: Name of the attribute
        default: Default value if attribute doesn't exist
        log_level: Logging level for missing attributes

    Returns:
        Attribute value or default
    """
    try:
        # First check if attribute exists using hasattr (fast)
        if hasattr(obj, attr_name):
            return getattr(obj, attr_name)
        else:
            # Get caller info for better debugging
            frame = inspect.currentframe()
            caller_frame = frame.f_back
            caller_name = caller_frame.f_code.co_name if caller_frame else 'unknown'
            caller_file = caller_frame.f_code.co_filename if caller_frame else 'unknown'
            line_no = caller_frame.f_lineno if caller_frame else 0

            # Log the missing attribute
            logger.log(log_level,
                       f"Attribute '{attr_name}' not found in {type(obj).__name__} "
                       f"(called from {caller_name} at {caller_file}:{line_no}). "
                       f"Using default: {default}")

            return default
    except Exception as e:
        # Handle any unexpected errors
        logger.error(f"Error accessing attribute '{attr_name}': {e}", exc_info=True)
        return default


def safe_hasattr(obj: Any, attr_name: str) -> bool:
    """
    Safe hasattr with error handling.
    """
    try:
        return hasattr(obj, attr_name)
    except Exception as e:
        logger.error(f"Error checking attribute '{attr_name}': {e}", exc_info=True)
        return False


def safe_setattr(obj: Any, attr_name: str, value: Any) -> bool:
    """
    Safe setattr with error handling.
    Returns True if successful, False otherwise.
    """
    try:
        setattr(obj, attr_name, value)
        return True
    except Exception as e:
        logger.error(f"Error setting attribute '{attr_name}': {e}", exc_info=True)
        return False