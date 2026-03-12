"""
Utils/time_utils.py
===================
Central timezone and display-format utilities for the entire application.

Rules enforced here:
  • All "current time" calls → ist_now()          (datetime.now(IST))
  • Attaching IST to a naive datetime → ist_localize(dt)  (pytz .localize, NOT .replace)
  • All user-facing time strings → fmt_display(dt) → "HH:MM:SS DD/MM/YY"
  • Internal ISO / DB strings    → fmt_iso(dt)     → "%Y-%m-%dT%H:%M:%S"
  • File-suffix timestamps       → fmt_stamp(dt)   → "%Y%m%d_%H%M%S"

Never import datetime.timezone for IST work — always use pytz.
.replace(tzinfo=IST) is WRONG for pytz timezones because pytz stores historical
LMT offsets; always use IST.localize(naive_dt) instead.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Union

import pytz

logger = logging.getLogger(__name__)

# ── Canonical IST timezone object ────────────────────────────────────────────
IST: pytz.BaseTzInfo = pytz.timezone("Asia/Kolkata")

# ── User-facing display format ────────────────────────────────────────────────
_FMT_DISPLAY = "%H:%M:%S %d/%m/%y"  # "14:35:07 11/03/26"
_FMT_DISPLAY_D = "%d/%m/%y"  # date-only variant
_FMT_DISPLAY_T = "%H:%M:%S"  # time-only variant
_FMT_ISO = "%Y-%m-%dT%H:%M:%S"  # internal / DB
_FMT_STAMP = "%Y%m%d_%H%M%S"  # file suffixes


# ── Core helpers ──────────────────────────────────────────────────────────────

def ist_now() -> datetime:
    """Return current time as a timezone-aware IST datetime."""
    return datetime.now(IST)


def ist_localize(dt: datetime) -> datetime:
    """
    Attach IST timezone to a *naive* datetime using pytz.localize().
    If dt is already tz-aware, convert it to IST.

    NEVER use dt.replace(tzinfo=IST) — pytz stores historical LMT offsets
    which would produce +05:53:20 instead of +05:30 for pre-1945 data.
    """
    if dt is None:
        return ist_now()
    if dt.tzinfo is None:
        return IST.localize(dt)
    return dt.astimezone(IST)


def to_ist(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert any tz-aware datetime (or naive, assumed IST) to IST. Safe."""
    if dt is None:
        return None
    try:
        return ist_localize(dt)
    except Exception:
        return dt


# ── Formatting helpers ────────────────────────────────────────────────────────

def fmt_display(dt: Optional[datetime], *, date_only: bool = False,
                time_only: bool = False) -> str:
    """
    Format datetime for user-facing display.
      Default  → "HH:MM:SS DD/MM/YY"   e.g. "14:35:07 11/03/26"
      date_only→ "DD/MM/YY"
      time_only→ "HH:MM:SS"

    If dt is naive it is treated as IST.
    Falls back to empty string on error.
    """
    if dt is None:
        return ""
    try:
        dt_ist = ist_localize(dt) if dt.tzinfo is None else dt.astimezone(IST)
        if date_only:
            return dt_ist.strftime(_FMT_DISPLAY_D)
        if time_only:
            return dt_ist.strftime(_FMT_DISPLAY_T)
        return dt_ist.strftime(_FMT_DISPLAY)
    except Exception as exc:
        logger.debug(f"[fmt_display] {exc}")
        return ""


def fmt_iso(dt: Optional[datetime]) -> str:
    """
    Format for internal storage / DB: "YYYY-MM-DDTHH:MM:SS" (no TZ suffix).
    Uses IST if naive.
    """
    if dt is None:
        return ""
    try:
        dt_ist = ist_localize(dt) if dt.tzinfo is None else dt.astimezone(IST)
        return dt_ist.strftime(_FMT_ISO)
    except Exception:
        return ""


def fmt_stamp(dt: Optional[datetime] = None) -> str:
    """Return a compact timestamp string suitable for file names: YYYYMMDD_HHMMSS."""
    dt = dt or ist_now()
    try:
        dt_ist = ist_localize(dt) if dt.tzinfo is None else dt.astimezone(IST)
        return dt_ist.strftime(_FMT_STAMP)
    except Exception:
        return datetime.now().strftime(_FMT_STAMP)


def parse_display(s: str) -> Optional[datetime]:
    """
    Parse a user-facing display string back to an IST-aware datetime.
    Accepts both "HH:MM:SS DD/MM/YY" and "DD/MM/YY".
    """
    for fmt in (_FMT_DISPLAY, _FMT_DISPLAY_D, _FMT_ISO, "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M", "%d-%b %H:%M"):
        try:
            return IST.localize(datetime.strptime(s.strip(), fmt))
        except ValueError:
            continue
    return None
