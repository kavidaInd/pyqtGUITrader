# utils/session_utils.py
"""
Session utilities for generating and managing session IDs.
"""

import uuid
import socket
import datetime
import logging

logger = logging.getLogger(__name__)


def generate_session_id() -> str:
    """
    Generate a unique session ID.

    Format: YYYYMMDD_HHMMSS_<hostname>_<uuid-short>

    Returns:
        str: Unique session identifier
    """
    try:
        # Get current timestamp
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")

        # Get hostname (shortened if too long)
        hostname = socket.gethostname()
        if len(hostname) > 20:
            hostname = hostname[:20]

        # Generate short UUID (first 8 chars)
        short_uuid = str(uuid.uuid4())[:8]

        # Combine into session ID
        session_id = f"{timestamp}_{hostname}_{short_uuid}"

        logger.debug(f"Generated session ID: {session_id}")
        return session_id

    except Exception as e:
        logger.error(f"Failed to generate session ID: {e}", exc_info=True)
        # Fallback to simple UUID if anything fails
        return f"session_{uuid.uuid4().hex[:12]}"


def parse_session_id(session_id: str) -> dict:
    """
    Parse a session ID into its components.

    Args:
        session_id: Session ID string

    Returns:
        dict: Parsed components (timestamp, hostname, uuid)
    """
    try:
        parts = session_id.split('_')
        if len(parts) >= 3:
            return {
                'timestamp': parts[0] + '_' + parts[1] if len(parts) > 1 else None,
                'hostname': parts[2] if len(parts) > 2 else None,
                'uuid': '_'.join(parts[3:]) if len(parts) > 3 else None
            }
        return {}
    except Exception as e:
        logger.error(f"Failed to parse session ID: {e}", exc_info=True)
        return {}