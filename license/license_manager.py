"""
license/license_manager.py
==========================
Client-side license engine for the Algo Trading SaaS.

Plans
─────
  trial    — 7-day free trial, one per machine ever (server-enforced)
  standard — paid, 1-year, 1 machine
  pro      — paid, 1-year, up to 3 machines

Flows
─────
  Trial (first run):
    1. User enters email only → POST /api/v1/trial
    2. Server checks machine_id has never had a trial
    3. Returns { status:"trial_activated", license_key, expires_at, days_remaining }
    4. Stored locally with plan="trial"

  Paid activation:
    1. User enters order_id + email → POST /api/v1/activate
    2. Returns { status:"activated", license_key, expires_at, plan, customer_name }
    3. Replaces any existing trial record on the same machine

  Every startup:
    POST /api/v1/verify { license_key, machine_id, app_version }
    Trial : NO offline grace — must verify online (prevents clock manipulation)
    Paid  : OFFLINE_GRACE_DAYS tolerance when server is unreachable

Server contract
───────────────
  POST /api/v1/trial
      body : { email, machine_id, app_version }
      200  : { status:"trial_activated", license_key, expires_at, days_remaining }
      400  : { status:"error", reason:"trial_already_used"|"invalid_email"|... }

  POST /api/v1/activate
      body : { order_id, email, machine_id, app_version }
      200  : { status:"activated", license_key, expires_at, plan,
               customer_name, days_remaining }
      400  : { status:"error", reason:"..." }

  POST /api/v1/verify
      body : { license_key, machine_id, app_version }
      200  : { valid:true,  plan, expires_at, days_remaining, customer_name }
      200  : { valid:false, reason:"trial_expired"|"expired"|"revoked"|... }

  GET  /api/v1/version
      200  : { latest_version, download_url, release_notes, is_mandatory }
"""

from __future__ import annotations

import hashlib
import logging
import platform
import uuid
from datetime import datetime, timedelta
from typing import Dict

import requests

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
ACTIVATION_SERVER_URL: str = "https://your-activation-server.com"  # ← change this
REQUEST_TIMEOUT: int = 15
OFFLINE_GRACE_DAYS: int = 3  # paid plans only — trials must verify online
TRIAL_DURATION_DAYS: int = 7
APP_VERSION: str = "1.0.0"

# DEVELOPMENT MODE - Set to True to bypass server checks during development
DEVELOPMENT_MODE: bool = True  # ← Set to False for production

# Plan name constants
PLAN_TRIAL = "trial"
PLAN_STANDARD = "standard"
PLAN_PRO = "pro"

# KV store keys
_KV_LICENSE_KEY = "license:license_key"
_KV_ORDER_ID = "license:order_id"
_KV_EMAIL = "license:email"
_KV_MACHINE_ID = "license:machine_id"
_KV_EXPIRES_AT = "license:expires_at"
_KV_PLAN = "license:plan"
_KV_CUSTOMER_NAME = "license:customer_name"
_KV_LAST_VERIFY_AT = "license:last_verify_at"
_KV_LAST_VERIFY_OK = "license:last_verify_ok"
_KV_DAYS_REMAINING = "license:days_remaining"


# ── Machine fingerprint ────────────────────────────────────────────────────────

def _get_machine_id() -> str:
    """
    Stable anonymous machine fingerprint, persisted in the KV store.

    Because the fingerprint is written to SQLite before being sent to the server,
    reinstalling the app recreates the same ID from the same hardware — making it
    impossible to obtain a second trial by reinstalling.
    """
    try:
        from db.crud import kv
        stored = kv.get(_KV_MACHINE_ID)
        if stored:
            return stored
        parts = [
            platform.node(),
            platform.processor(),
            platform.machine(),
            str(uuid.getnode()),  # MAC-address-derived integer
        ]
        fingerprint = hashlib.sha256("|".join(filter(None, parts)).encode()).hexdigest()[:32]
        kv.set(_KV_MACHINE_ID, fingerprint)
        return fingerprint
    except Exception as e:
        logger.warning(f"Could not generate machine_id: {e}")
        return hashlib.sha256(platform.node().encode()).hexdigest()[:32]


# ── Result type ────────────────────────────────────────────────────────────────

class LicenseResult:
    """Returned by start_trial(), activate(), and verify_on_startup()."""

    def __init__(
            self,
            ok: bool,
            reason: str = "",
            license_key: str = "",
            expires_at: str = "",
            plan: str = "",
            customer_name: str = "",
            days_remaining: int = 0,
            offline: bool = False,
    ):
        self.ok = ok
        self.reason = reason
        self.license_key = license_key
        self.expires_at = expires_at
        self.plan = plan
        self.customer_name = customer_name
        self.days_remaining = days_remaining
        self.offline = offline

    @property
    def is_trial(self) -> bool:
        return self.plan == PLAN_TRIAL

    @property
    def is_paid(self) -> bool:
        return self.plan in (PLAN_STANDARD, PLAN_PRO)

    def __repr__(self):
        return (
            f"LicenseResult(ok={self.ok}, plan={self.plan!r}, "
            f"days_remaining={self.days_remaining}, offline={self.offline})"
        )


# ── Main class ─────────────────────────────────────────────────────────────────

class LicenseManager:
    """
    Singleton license manager.
    Use the module-level `license_manager` instance.
    """

    def __init__(self, server_url: str = ACTIVATION_SERVER_URL):
        self.server_url = server_url.rstrip("/")
        self.machine_id = _get_machine_id()

    # ── Query helpers ──────────────────────────────────────────────────────────

    def is_locally_activated(self) -> bool:
        """Quick check — does any local license record exist?"""
        try:
            from db.crud import kv
            return bool(kv.get(_KV_LICENSE_KEY))
        except Exception:
            return False

    def get_local_plan(self) -> str:
        """Return the cached plan string ('trial', 'standard', 'pro', or '')."""
        try:
            from db.crud import kv
            return kv.get(_KV_PLAN, "") or ""
        except Exception:
            return ""

    def get_cached_email(self) -> str:
        """Return stored email — used to pre-fill the upgrade form after trial expiry."""
        try:
            from db.crud import kv
            return kv.get(_KV_EMAIL, "") or ""
        except Exception:
            return ""

    def get_local_info(self) -> Dict:
        """Full cached record — used by About / License status dialogs."""
        try:
            from db.crud import kv
            return {
                "order_id": kv.get(_KV_ORDER_ID, ""),
                "email": kv.get(_KV_EMAIL, ""),
                "plan": kv.get(_KV_PLAN, ""),
                "expires_at": kv.get(_KV_EXPIRES_AT, ""),
                "customer_name": kv.get(_KV_CUSTOMER_NAME, ""),
                "machine_id": self.machine_id,
                "last_verify": kv.get(_KV_LAST_VERIFY_AT, ""),
                "days_remaining": kv.get(_KV_DAYS_REMAINING, 0),
            }
        except Exception:
            return {}

    # ── Trial activation ───────────────────────────────────────────────────────

    def start_trial(self, email: str) -> LicenseResult:
        """
        Register a free 7-day trial for this machine.

        The server enforces ONE trial per machine_id for all time.  Reinstalling
        the app will not grant a second trial because the machine_id is derived
        from hardware and already stored in the DB before the first request.
        """
        email = email.strip().lower()
        if not email or "@" not in email:
            return LicenseResult(ok=False, reason="Please enter a valid email address.")

        # DEVELOPMENT MODE: Always succeed
        if DEVELOPMENT_MODE:
            logger.info(f"DEVELOPMENT MODE: Trial activated for {email}")
            expires_at = (datetime.now() + timedelta(days=TRIAL_DURATION_DAYS)).isoformat()
            result = LicenseResult(
                ok=True,
                license_key=f"DEV_TRIAL_{hashlib.md5(email.encode()).hexdigest()[:8]}",
                expires_at=expires_at,
                plan=PLAN_TRIAL,
                customer_name=email.split('@')[0],
                days_remaining=TRIAL_DURATION_DAYS,
            )
            self._persist("DEV_TRIAL", email, result)
            return result

        try:
            resp = requests.post(
                f"{self.server_url}/api/v1/trial",
                json={
                    "email": email,
                    "machine_id": self.machine_id,
                    "app_version": APP_VERSION,
                },
                timeout=REQUEST_TIMEOUT,
            )
            data = resp.json()

            if resp.status_code == 200 and data.get("status") == "trial_activated":
                result = LicenseResult(
                    ok=True,
                    license_key=data["license_key"],
                    expires_at=data["expires_at"],
                    plan=PLAN_TRIAL,
                    customer_name=email,
                    days_remaining=int(data.get("days_remaining", TRIAL_DURATION_DAYS)),
                )
                self._persist("TRIAL", email, result)
                logger.info(
                    f"Trial activated: expires={result.expires_at}, "
                    f"days_remaining={result.days_remaining}"
                )
                return result

            reason = data.get("reason", "")
            friendly = {
                "trial_already_used": (
                    "A free trial has already been used on this machine.\n\n"
                    "Purchase a license to continue using Algo Trading Pro."
                ),
                "invalid_email": "Please enter a valid email address.",
            }.get(reason, data.get("message") or "Trial activation failed. Please try again.")
            return LicenseResult(ok=False, reason=friendly)

        except requests.exceptions.ConnectionError:
            return LicenseResult(
                ok=False,
                reason=(
                    "Cannot reach the activation server.\n\n"
                    "An internet connection is required to start your free trial."
                ),
            )
        except requests.exceptions.Timeout:
            return LicenseResult(ok=False, reason="Server timed out. Please try again.")
        except Exception as e:
            logger.error(f"[LicenseManager.start_trial] {e}", exc_info=True)
            return LicenseResult(ok=False, reason=f"Unexpected error: {e}")

    # ── Paid activation ────────────────────────────────────────────────────────

    def activate(self, order_id: str, email: str) -> LicenseResult:
        """
        Activate a paid license for this machine.
        Seamlessly upgrades a machine that previously had a trial.
        """
        order_id = order_id.strip()
        email = email.strip().lower()

        if not order_id or not email:
            return LicenseResult(ok=False, reason="Order ID and email are required.")

        # DEVELOPMENT MODE: Always succeed
        if DEVELOPMENT_MODE:
            logger.info(f"DEVELOPMENT MODE: License activated for {email} with order {order_id}")
            expires_at = (datetime.now() + timedelta(days=365)).isoformat()
            result = LicenseResult(
                ok=True,
                license_key=f"DEV_PAID_{hashlib.md5(f'{email}{order_id}'.encode()).hexdigest()[:8]}",
                expires_at=expires_at,
                plan=PLAN_PRO,
                customer_name=email.split('@')[0],
                days_remaining=365,
            )
            self._persist(order_id, email, result)
            return result

        try:
            resp = requests.post(
                f"{self.server_url}/api/v1/activate",
                json={
                    "order_id": order_id,
                    "email": email,
                    "machine_id": self.machine_id,
                    "app_version": APP_VERSION,
                },
                timeout=REQUEST_TIMEOUT,
            )
            data = resp.json()

            if resp.status_code == 200 and data.get("status") == "activated":
                result = LicenseResult(
                    ok=True,
                    license_key=data["license_key"],
                    expires_at=data["expires_at"],
                    plan=data.get("plan", PLAN_STANDARD),
                    customer_name=data.get("customer_name", ""),
                    days_remaining=int(data.get("days_remaining", 365)),
                )
                self._persist(order_id, email, result)
                logger.info(f"License activated: plan={result.plan}, expires={result.expires_at}")
                return result

            reason = data.get("reason") or data.get("message") or "Activation failed."
            return LicenseResult(ok=False, reason=reason)

        except requests.exceptions.ConnectionError:
            return LicenseResult(
                ok=False, reason="Cannot reach activation server. Check your internet connection."
            )
        except requests.exceptions.Timeout:
            return LicenseResult(ok=False, reason="Server timed out. Please try again.")
        except Exception as e:
            logger.error(f"[LicenseManager.activate] {e}", exc_info=True)
            return LicenseResult(ok=False, reason=f"Unexpected error: {e}")

    # ── Startup verification ───────────────────────────────────────────────────

    def verify_on_startup(self) -> LicenseResult:
        """
        Verify the license against the server on every app start.

        Trial  : Must be online — no offline grace period at all.
        Paid   : Falls back to OFFLINE_GRACE_DAYS cached grace when unreachable.
        """
        from db.crud import kv

        license_key = kv.get(_KV_LICENSE_KEY, "")
        current_plan = kv.get(_KV_PLAN, "")

        # DEVELOPMENT MODE: Always succeed if there's a local license
        if DEVELOPMENT_MODE:
            if license_key:
                logger.info("DEVELOPMENT MODE: License verified successfully")
                days_remaining = int(kv.get(_KV_DAYS_REMAINING, 7))
                return LicenseResult(
                    ok=True,
                    license_key=license_key,
                    expires_at=kv.get(_KV_EXPIRES_AT, ""),
                    plan=current_plan,
                    customer_name=kv.get(_KV_CUSTOMER_NAME, ""),
                    days_remaining=days_remaining,
                )
            return LicenseResult(ok=False, reason="not_activated")

        if not license_key:
            return LicenseResult(ok=False, reason="not_activated")

        try:

            resp = requests.post(
                f"{self.server_url}/api/v1/verify",
                json={
                    "license_key": license_key,
                    "machine_id": self.machine_id,
                    "app_version": APP_VERSION,
                },
                timeout=REQUEST_TIMEOUT,
            )
            data = resp.json()

            if data.get("valid"):
                plan = data.get("plan", current_plan)
                days_remaining = int(data.get("days_remaining", 0))
                result = LicenseResult(
                    ok=True,
                    license_key=license_key,
                    expires_at=data.get("expires_at", ""),
                    plan=plan,
                    customer_name=data.get("customer_name", ""),
                    days_remaining=days_remaining,
                )
                kv.update_many({
                    _KV_LAST_VERIFY_AT: datetime.now().isoformat(),
                    _KV_LAST_VERIFY_OK: True,
                    _KV_PLAN: plan,
                    _KV_DAYS_REMAINING: days_remaining,
                })
                if data.get("expires_at"):
                    kv.set(_KV_EXPIRES_AT, data["expires_at"])
                logger.info(
                    f"License verified online: plan={plan}, days_remaining={days_remaining}"
                )
                return result

            # Server returned valid:false
            reason = data.get("reason", "License is no longer valid.")
            if reason in ("revoked", "invalid_machine"):
                self._clear_local()
            elif reason in ("expired", "trial_expired"):
                # Keep email so dialog can pre-fill the upgrade form
                self._soft_clear()
            logger.warning(f"Verification failed: {reason}")
            return LicenseResult(ok=False, reason=reason)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            # Trials never get offline grace
            if current_plan == PLAN_TRIAL:
                return LicenseResult(
                    ok=False,
                    reason=(
                        "Could not verify your trial license.\n\n"
                        "An internet connection is required to use the free trial."
                    ),
                )
            return self._offline_fallback()

        except Exception as e:
            logger.error(f"[LicenseManager.verify_on_startup] {e}", exc_info=True)
            if current_plan == PLAN_TRIAL:
                return LicenseResult(ok=False, reason=f"License check error: {e}")
            return self._offline_fallback()

    # ── Deactivation ──────────────────────────────────────────────────────────

    def deactivate(self):
        """Remove the local activation record (support / reinstall use)."""
        self._clear_local()
        logger.info("Local license record cleared.")

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _persist(self, order_id: str, email: str, result: LicenseResult):
        try:
            from db.crud import kv
            kv.update_many({
                _KV_LICENSE_KEY: result.license_key,
                _KV_ORDER_ID: order_id,
                _KV_EMAIL: email,
                _KV_EXPIRES_AT: result.expires_at,
                _KV_PLAN: result.plan,
                _KV_CUSTOMER_NAME: result.customer_name,
                _KV_LAST_VERIFY_AT: datetime.now().isoformat(),
                _KV_LAST_VERIFY_OK: True,
                _KV_DAYS_REMAINING: result.days_remaining,
            })
        except Exception as e:
            logger.error(f"[LicenseManager._persist] {e}", exc_info=True)

    def _clear_local(self):
        """Wipe all license KV entries."""
        try:
            from db.crud import kv
            for key in (
                    _KV_LICENSE_KEY, _KV_ORDER_ID, _KV_EMAIL, _KV_EXPIRES_AT,
                    _KV_PLAN, _KV_CUSTOMER_NAME, _KV_LAST_VERIFY_AT,
                    _KV_LAST_VERIFY_OK, _KV_DAYS_REMAINING,
            ):
                kv.delete(key)
        except Exception as e:
            logger.error(f"[LicenseManager._clear_local] {e}", exc_info=True)

    def _soft_clear(self):
        """
        Clear license key + status but preserve email.
        Used after trial/paid expiry so the upgrade dialog can pre-fill the email field.
        """
        try:
            from db.crud import kv
            for key in (
                    _KV_LICENSE_KEY, _KV_EXPIRES_AT, _KV_PLAN,
                    _KV_LAST_VERIFY_AT, _KV_LAST_VERIFY_OK, _KV_DAYS_REMAINING,
            ):
                kv.delete(key)
        except Exception as e:
            logger.error(f"[LicenseManager._soft_clear] {e}", exc_info=True)

    def _offline_fallback(self) -> LicenseResult:
        """
        Allow paid-plan startup for up to OFFLINE_GRACE_DAYS when
        the activation server is unreachable.
        """
        try:
            from db.crud import kv
            last_ok_raw = kv.get(_KV_LAST_VERIFY_AT)
            last_ok = kv.get(_KV_LAST_VERIFY_OK, False)
            expires_raw = kv.get(_KV_EXPIRES_AT, "")

            if not last_ok or not last_ok_raw:
                return LicenseResult(
                    ok=False,
                    reason=(
                        "License could not be verified and no previous "
                        "successful verification exists."
                    ),
                )

            if expires_raw:
                try:
                    if datetime.now() > datetime.fromisoformat(expires_raw):
                        return LicenseResult(ok=False, reason="expired")
                except ValueError:
                    pass

            try:
                last_dt = datetime.fromisoformat(last_ok_raw)
                grace_end = last_dt + timedelta(days=OFFLINE_GRACE_DAYS)
                days_left = max(0, (grace_end - datetime.now()).days)

                if datetime.now() > grace_end:
                    return LicenseResult(
                        ok=False,
                        reason=(
                            f"Offline grace period of {OFFLINE_GRACE_DAYS} days has expired.\n"
                            "Please connect to the internet to verify your license."
                        ),
                    )

                logger.warning(f"Offline grace active: {days_left} day(s) remaining")
                return LicenseResult(
                    ok=True,
                    license_key=kv.get(_KV_LICENSE_KEY, ""),
                    expires_at=expires_raw,
                    plan=kv.get(_KV_PLAN, ""),
                    customer_name=kv.get(_KV_CUSTOMER_NAME, ""),
                    days_remaining=kv.get(_KV_DAYS_REMAINING, 0),
                    offline=True,
                    reason=f"Offline mode — {days_left} day(s) of grace remaining.",
                )
            except ValueError:
                return LicenseResult(ok=False, reason="Invalid cached verification timestamp.")

        except Exception as e:
            logger.error(f"[LicenseManager._offline_fallback] {e}", exc_info=True)
            return LicenseResult(ok=False, reason=f"License check error: {e}")


# ── Module-level singleton ─────────────────────────────────────────────────────
license_manager = LicenseManager()