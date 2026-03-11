"""
license/license_manager.py  — Hardened Edition
================================================
Drop-in replacement for the original license_manager.py.

Security Hardening vs. original
─────────────────────────────────
1. HMAC-SHA256 request signing          — every outbound request carries an
   X-ATP-Signature header.  The WordPress plugin validates this so it will
   reject any forged/replayed API call.

2. Nonce / replay protection            — each request embeds a fresh UUID4
   nonce + UTC timestamp.  The server checks the nonce is unused and that the
   timestamp is within ±5 minutes.

3. Encrypted local storage              — license data is AES-GCM encrypted
   before being written to the KV store.  A 32-byte key is derived from
   hardware fingerprint + app secret via PBKDF2, so the ciphertext is useless
   without the original machine.

4. Response signature verification      — the server signs every response body
   with HMAC-SHA256.  The client checks X-ATP-Response-Sig before trusting
   any server-returned value.

5. DEVELOPMENT_MODE removed             — the backdoor flag is gone.  Use
   the WordPress plugin's "Test Mode" toggle instead.

6. Anti-tamper heartbeat hash           — a hash of (license_key + machine_id
   + plan + expires_at) is stored locally and re-verified before every live-
   trading gate check.  Tampering with the KV store breaks the hash and the
   gate denies access.

7. Minimum TLS 1.2 enforced            — requests.Session configured to refuse
   connections below TLS 1.2.

API Endpoints (WordPress plugin)
──────────────────────────────────
  POST /wp-json/atp-license/v1/trial
  POST /wp-json/atp-license/v1/activate
  POST /wp-json/atp-license/v1/verify
  GET  /wp-json/atp-license/v1/version
  POST /wp-json/atp-license/v1/heartbeat   (silent background ping every 4 h)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import platform
import secrets
import ssl
import uuid
from base64 import b64decode, b64encode
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

# ── App constants ──────────────────────────────────────────────────────────────
ACTIVATION_SERVER_URL: str = "http://localhost/wordpress"  # ← set this
APP_VERSION: str = "1.0.0"
REQUEST_TIMEOUT: int = 15
OFFLINE_GRACE_DAYS: int = 3  # paid plans only
TRIAL_DURATION_DAYS: int = 7
HEARTBEAT_INTERVAL_H: int = 4  # background re-verify interval

# Shared secret — must match `ATP_SHARED_SECRET` in the WordPress plugin.
# Store this in an environment variable or embed via build-time obfuscation.
# _APP_SECRET: str = os.environ.get("ATP_APP_SECRET", "CHANGE_ME_BEFORE_RELEASE_32BYTES!")
_APP_SECRET= "1b7e0b8f37c53f3e6c43d4a38e6bad5cb5e4ba8dd10a697cd14092609c92e9f0"
# Plan constants
PLAN_TRIAL = "trial"
PLAN_STANDARD = "standard"
PLAN_PRO = "pro"
PLAN_PAID = "paid"
_PAID_PLANS = {PLAN_STANDARD, PLAN_PRO, PLAN_PAID}

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
_KV_INTEGRITY_HASH = "license:integrity_hash"  # anti-tamper
_KV_ENC_KEY_SALT = "license:enc_salt"  # PBKDF2 salt for storage key


# ── TLS enforcement ────────────────────────────────────────────────────────────

class _TLSAdapter(HTTPAdapter):
    """Force TLS 1.2+ on all outbound connections."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


def _build_session() -> requests.Session:
    s = requests.Session()
    adapter = _TLSAdapter()
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


# ── Encrypted KV helpers ───────────────────────────────────────────────────────

def _derive_storage_key(machine_id: str, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256 → 32-byte AES key bound to this machine."""
    material = (machine_id + _APP_SECRET).encode()
    return hashlib.pbkdf2_hmac("sha256", material, salt, iterations=200_000, dklen=32)


def _encrypt(plaintext: str, key: bytes) -> str:
    """AES-256-GCM encrypt → base64 string (nonce+tag+ciphertext)."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
        return b64encode(nonce + ct).decode()
    except ImportError:
        # Fallback: XOR obfuscation (not true encryption — warn loudly)
        logger.warning("[license] cryptography package missing — using weak XOR obfuscation!")
        data = plaintext.encode()
        xored = bytes(b ^ key[i % 32] for i, b in enumerate(data))
        return b64encode(xored).decode()


def _decrypt(blob: str, key: bytes) -> str:
    """Inverse of _encrypt."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = b64decode(blob)
        nonce = raw[:12]
        ct = raw[12:]
        return AESGCM(key).decrypt(nonce, ct, None).decode()
    except ImportError:
        data = b64decode(blob)
        xored = bytes(b ^ key[i % 32] for i, b in enumerate(data))
        return xored.decode()
    except Exception as e:
        raise ValueError(f"Decryption failed: {e}") from e


def _get_enc_key() -> bytes:
    """Return (or lazily create) the per-machine storage encryption key."""
    from db.crud import kv
    salt_b64 = kv.get(_KV_ENC_KEY_SALT)
    if salt_b64:
        salt = b64decode(salt_b64)
    else:
        salt = os.urandom(32)
        kv.set(_KV_ENC_KEY_SALT, b64encode(salt).decode())
    machine_id = _get_machine_id()
    return _derive_storage_key(machine_id, salt)


def _kv_set_enc(key: str, value: str) -> None:
    from db.crud import kv
    enc_key = _get_enc_key()
    kv.set(key, _encrypt(value, enc_key))


def _kv_get_enc(key: str, default: str = "") -> str:
    from db.crud import kv
    blob = kv.get(key, "")
    if not blob:
        return default
    try:
        enc_key = _get_enc_key()
        return _decrypt(blob, enc_key)
    except Exception:
        logger.warning(f"[license] Could not decrypt KV key '{key}' — clearing it.")
        kv.delete(key)
        return default


# ── Machine fingerprint ────────────────────────────────────────────────────────

def _get_machine_id() -> str:
    """
    Stable hardware fingerprint.  Written to KV before the first server call
    so reinstalling the app returns the same ID.
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
            str(uuid.getnode()),
        ]
        fp = hashlib.sha256("|".join(filter(None, parts)).encode()).hexdigest()[:32]
        kv.set(_KV_MACHINE_ID, fp)
        return fp
    except Exception as e:
        logger.warning(f"[license] Could not generate machine_id: {e}")
        return hashlib.sha256(platform.node().encode()).hexdigest()[:32]


# ── HMAC request signing ───────────────────────────────────────────────────────

def _sign_request(payload: dict) -> tuple[dict, dict]:
    """
    Return (augmented_payload, headers) where:
      - payload gains  'nonce' and 'timestamp'
      - headers gains  'X-ATP-Signature' (HMAC-SHA256 hex of canonical body)
    """
    nonce = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = {**payload, "nonce": nonce, "timestamp": timestamp}
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(_APP_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-ATP-Signature": sig,
        "X-ATP-Version": APP_VERSION,
    }
    return payload, headers


def _verify_response_sig(body_bytes: bytes, sig_header: str) -> bool:
    """Return True when the server's HMAC-SHA256 signature matches."""
    print(body_bytes)
    print(sig_header)
    if not sig_header:
        logger.warning("[license] Response has no X-ATP-Response-Sig header — rejecting.")
        return False
    expected = hmac.new(_APP_SECRET.encode(), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header)


# ── Anti-tamper integrity hash ─────────────────────────────────────────────────

def _compute_integrity_hash(license_key: str, machine_id: str,
                            plan: str, expires_at: str) -> str:
    material = f"{license_key}|{machine_id}|{plan}|{expires_at}|{_APP_SECRET}"
    return hashlib.sha256(material.encode()).hexdigest()


def _verify_integrity() -> bool:
    """Return False if any stored license field was tampered with."""
    try:
        from db.crud import kv
        stored_hash = kv.get(_KV_INTEGRITY_HASH, "")
        if not stored_hash:
            return False
        lic_key = _kv_get_enc(_KV_LICENSE_KEY)
        machine = kv.get(_KV_MACHINE_ID, "")
        plan = _kv_get_enc(_KV_PLAN)
        expires = _kv_get_enc(_KV_EXPIRES_AT)
        expected = _compute_integrity_hash(lic_key, machine, plan, expires)
        ok = hmac.compare_digest(expected, stored_hash)
        if not ok:
            logger.error("[license] INTEGRITY CHECK FAILED — local data may have been tampered with!")
        return ok
    except Exception as e:
        logger.error(f"[license] Integrity check error: {e}")
        return False


def _write_integrity_hash(license_key: str, machine_id: str,
                          plan: str, expires_at: str) -> None:
    from db.crud import kv
    h = _compute_integrity_hash(license_key, machine_id, plan, expires_at)
    kv.set(_KV_INTEGRITY_HASH, h)


# ── Result type ────────────────────────────────────────────────────────────────

class LicenseResult:
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
        return self.plan in _PAID_PLANS

    def __repr__(self):
        return (
            f"LicenseResult(ok={self.ok}, plan={self.plan!r}, "
            f"days_remaining={self.days_remaining}, offline={self.offline})"
        )


# ── Main class ─────────────────────────────────────────────────────────────────

class LicenseManager:
    """
    Hardened singleton license manager.
    Use the module-level `license_manager` instance.
    """

    def __init__(self, server_url: str = ACTIVATION_SERVER_URL):
        self.server_url = server_url.rstrip("/")
        self.machine_id = _get_machine_id()
        self._session = _build_session()

    # ── Query helpers ──────────────────────────────────────────────────────────

    def is_locally_activated(self) -> bool:
        try:
            return bool(_kv_get_enc(_KV_LICENSE_KEY))
        except Exception:
            return False

    def get_local_plan(self) -> str:
        try:
            return _kv_get_enc(_KV_PLAN) or ""
        except Exception:
            return ""

    def is_trial_active(self) -> bool:
        try:
            plan = _kv_get_enc(_KV_PLAN) or ""
            key = _kv_get_enc(_KV_LICENSE_KEY) or ""
            return bool(key) and plan == PLAN_TRIAL
        except Exception:
            return False

    def is_live_trading_allowed(self) -> bool:
        """
        Hard gate for live trading.
        1. Check integrity hash — if tampered, deny.
        2. Check plan is trial or paid and key exists.
        Fail-safe: returns False on ANY error.
        """
        try:
            if not _verify_integrity():
                logger.error("[license] Live trading blocked — integrity check failed.")
                return False
            plan = _kv_get_enc(_KV_PLAN) or ""
            key = _kv_get_enc(_KV_LICENSE_KEY) or ""
            if not key:
                return False
            return plan in (PLAN_TRIAL, PLAN_PAID, PLAN_STANDARD, PLAN_PRO)
        except Exception as e:
            logger.warning(f"[license] is_live_trading_allowed error: {e}")
            return False

    def get_cached_email(self) -> str:
        try:
            return _kv_get_enc(_KV_EMAIL) or ""
        except Exception:
            return ""

    def get_local_info(self) -> Dict:
        try:
            from db.crud import kv
            return {
                "order_id": _kv_get_enc(_KV_ORDER_ID),
                "email": _kv_get_enc(_KV_EMAIL),
                "plan": _kv_get_enc(_KV_PLAN),
                "expires_at": _kv_get_enc(_KV_EXPIRES_AT),
                "customer_name": _kv_get_enc(_KV_CUSTOMER_NAME),
                "machine_id": self.machine_id,
                "last_verify": kv.get(_KV_LAST_VERIFY_AT, ""),
                "days_remaining": kv.get(_KV_DAYS_REMAINING, 0),
                "integrity_ok": _verify_integrity(),
            }
        except Exception:
            return {}

    # ── Trial activation ───────────────────────────────────────────────────────

    def start_trial(self, email: str) -> LicenseResult:
        email = email.strip().lower()
        if not email or "@" not in email:
            return LicenseResult(ok=False, reason="Please enter a valid email address.")

        payload, headers = _sign_request({
            "email": email,
            "machine_id": self.machine_id,
            "app_version": APP_VERSION,
        })

        try:
            resp = self._session.post(
                f"{self.server_url}/wp-json/atp-license/v1/trial",
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            raw = resp.content
            sig = resp.headers.get("X-ATP-Response-Sig", "")
            if not _verify_response_sig(raw, sig):
                return LicenseResult(ok=False, reason="Server response signature invalid. Please try again.")

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
                logger.info(f"[license] Trial activated — expires {result.expires_at}")
                return result

            reason = data.get("reason", "")
            return LicenseResult(ok=False, reason=self._friendly_error(reason, data))

        except requests.exceptions.SSLError:
            return LicenseResult(ok=False, reason="SSL/TLS error. Check your system clock and CA certificates.")
        except requests.exceptions.ConnectionError:
            return LicenseResult(ok=False,
                                 reason="Cannot reach the activation server.\nAn internet connection is required to start your free trial.")
        except requests.exceptions.Timeout:
            return LicenseResult(ok=False, reason="Server timed out. Please try again.")
        except Exception as e:
            logger.error(f"[license] start_trial: {e}", exc_info=True)
            return LicenseResult(ok=False, reason=f"Unexpected error: {e}")

    # ── Paid activation ────────────────────────────────────────────────────────

    def activate(self, order_id: str, email: str) -> LicenseResult:
        order_id = order_id.strip()
        email = email.strip().lower()
        if not order_id or not email:
            return LicenseResult(ok=False, reason="Order ID and email are required.")

        payload, headers = _sign_request({
            "order_id": order_id,
            "email": email,
            "machine_id": self.machine_id,
            "app_version": APP_VERSION,
        })

        try:
            resp = self._session.post(
                f"{self.server_url}/wp-json/atp-license/v1/activate",
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            raw = resp.content
            sig = resp.headers.get("X-ATP-Response-Sig", "")
            if not _verify_response_sig(raw, sig):
                return LicenseResult(ok=False, reason="Server response signature invalid. Please try again.")

            data = resp.json()

            if resp.status_code == 200 and data.get("status") == "activated":
                result = LicenseResult(
                    ok=True,
                    license_key=data["license_key"],
                    expires_at=data["expires_at"],
                    plan=data.get("plan", PLAN_PAID),
                    customer_name=data.get("customer_name", ""),
                    days_remaining=int(data.get("days_remaining", 365)),
                )
                self._persist(order_id, email, result)
                logger.info(f"[license] Activated — plan={result.plan}, expires={result.expires_at}")
                return result

            reason = data.get("reason") or data.get("message") or "Activation failed."
            return LicenseResult(ok=False, reason=reason)

        except requests.exceptions.SSLError:
            return LicenseResult(ok=False, reason="SSL/TLS error. Check your system clock and CA certificates.")
        except requests.exceptions.ConnectionError:
            return LicenseResult(ok=False, reason="Cannot reach activation server. Check your internet connection.")
        except requests.exceptions.Timeout:
            return LicenseResult(ok=False, reason="Server timed out. Please try again.")
        except Exception as e:
            logger.error(f"[license] activate: {e}", exc_info=True)
            return LicenseResult(ok=False, reason=f"Unexpected error: {e}")

    # ── Startup verification ───────────────────────────────────────────────────

    def verify_on_startup(self) -> LicenseResult:
        """
        Full verification flow:
        1. Integrity check on local data
        2. Online verify if possible
        3. Offline fallback (paid only, within grace window)
        """
        from db.crud import kv

        license_key = _kv_get_enc(_KV_LICENSE_KEY)
        current_plan = _kv_get_enc(_KV_PLAN)

        if not license_key:
            return LicenseResult(ok=False, reason="not_activated")

        # Local integrity gate
        if not _verify_integrity():
            self._clear_local()
            return LicenseResult(ok=False, reason="License data corrupted or tampered. Please re-activate.")

        payload, headers = _sign_request({
            "license_key": license_key,
            "machine_id": self.machine_id,
            "app_version": APP_VERSION,
        })

        try:
            resp = self._session.post(
                f"{self.server_url}/wp-json/atp-license/v1/verify",
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            raw = resp.content
            sig = resp.headers.get("X-ATP-Response-Sig", "")
            if not _verify_response_sig(raw, sig):
                # Treat as network/server error — apply offline grace for paid
                if current_plan == PLAN_TRIAL:
                    return LicenseResult(ok=False, reason="Could not securely verify your trial license.")
                return self._offline_fallback()

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
                    _KV_LAST_VERIFY_AT: datetime.now(timezone.utc).isoformat(),
                    _KV_LAST_VERIFY_OK: True,
                    _KV_DAYS_REMAINING: days_remaining,
                })
                _kv_set_enc(_KV_PLAN, plan)
                if data.get("expires_at"):
                    _kv_set_enc(_KV_EXPIRES_AT, data["expires_at"])
                # Refresh integrity hash after any server-side update
                _write_integrity_hash(license_key, self.machine_id, plan,
                                      data.get("expires_at", _kv_get_enc(_KV_EXPIRES_AT)))
                logger.info(f"[license] Verified online: plan={plan}, days_remaining={days_remaining}")
                return result

            reason = data.get("reason", "License is no longer valid.")
            if reason in ("revoked", "invalid_machine"):
                self._clear_local()
            elif reason in ("expired", "trial_expired"):
                self._soft_clear()
            logger.warning(f"[license] Verification failed: {reason}")
            return LicenseResult(ok=False, reason=reason)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                requests.exceptions.SSLError):
            if current_plan == PLAN_TRIAL:
                return LicenseResult(ok=False,
                                     reason="Could not verify your trial license.\nAn internet connection is required to use the free trial.")
            return self._offline_fallback()
        except Exception as e:
            logger.error(f"[license] verify_on_startup: {e}", exc_info=True)
            if current_plan == PLAN_TRIAL:
                return LicenseResult(ok=False, reason=f"License check error: {e}")
            return self._offline_fallback()

    # ── Silent background heartbeat ────────────────────────────────────────────

    def send_heartbeat(self) -> bool:
        """
        Silent ping every HEARTBEAT_INTERVAL_H hours.
        Returns True if server ack'd, False otherwise (no user-facing action).
        """
        license_key = _kv_get_enc(_KV_LICENSE_KEY)
        if not license_key:
            return False
        payload, headers = _sign_request({
            "license_key": license_key,
            "machine_id": self.machine_id,
            "app_version": APP_VERSION,
        })
        try:
            resp = self._session.post(
                f"{self.server_url}/wp-json/atp-license/v1/heartbeat",
                json=payload,
                headers=headers,
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ── Deactivation ──────────────────────────────────────────────────────────

    def deactivate(self):
        self._clear_local()
        logger.info("[license] Local license record cleared.")

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _persist(self, order_id: str, email: str, result: LicenseResult):
        try:
            from db.crud import kv
            _kv_set_enc(_KV_LICENSE_KEY, result.license_key)
            _kv_set_enc(_KV_ORDER_ID, order_id)
            _kv_set_enc(_KV_EMAIL, email)
            _kv_set_enc(_KV_EXPIRES_AT, result.expires_at)
            _kv_set_enc(_KV_PLAN, result.plan)
            _kv_set_enc(_KV_CUSTOMER_NAME, result.customer_name)
            kv.update_many({
                _KV_LAST_VERIFY_AT: datetime.now(timezone.utc).isoformat(),
                _KV_LAST_VERIFY_OK: True,
                _KV_DAYS_REMAINING: result.days_remaining,
            })
            _write_integrity_hash(result.license_key, self.machine_id,
                                  result.plan, result.expires_at)
        except Exception as e:
            logger.error(f"[license] _persist: {e}", exc_info=True)

    def _clear_local(self):
        try:
            from db.crud import kv
            for key in (
                    _KV_LICENSE_KEY, _KV_ORDER_ID, _KV_EMAIL, _KV_EXPIRES_AT,
                    _KV_PLAN, _KV_CUSTOMER_NAME, _KV_LAST_VERIFY_AT,
                    _KV_LAST_VERIFY_OK, _KV_DAYS_REMAINING, _KV_INTEGRITY_HASH,
            ):
                kv.delete(key)
        except Exception as e:
            logger.error(f"[license] _clear_local: {e}", exc_info=True)

    def _soft_clear(self):
        """Clear key/status but keep email for upgrade dialog pre-fill."""
        try:
            from db.crud import kv
            for key in (
                    _KV_LICENSE_KEY, _KV_EXPIRES_AT, _KV_PLAN,
                    _KV_LAST_VERIFY_AT, _KV_LAST_VERIFY_OK,
                    _KV_DAYS_REMAINING, _KV_INTEGRITY_HASH,
            ):
                kv.delete(key)
        except Exception as e:
            logger.error(f"[license] _soft_clear: {e}", exc_info=True)

    def _offline_fallback(self) -> LicenseResult:
        try:
            from db.crud import kv
            last_ok_raw = kv.get(_KV_LAST_VERIFY_AT)
            last_ok = kv.get(_KV_LAST_VERIFY_OK, False)
            expires_raw = _kv_get_enc(_KV_EXPIRES_AT)

            if not last_ok or not last_ok_raw:
                return LicenseResult(ok=False,
                                     reason="License could not be verified and no previous successful verification exists.")

            if expires_raw:
                try:
                    if datetime.now(timezone.utc) > datetime.fromisoformat(expires_raw):
                        return LicenseResult(ok=False, reason="expired")
                except ValueError:
                    pass

            last_dt = datetime.fromisoformat(last_ok_raw)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            grace_end = last_dt + timedelta(days=OFFLINE_GRACE_DAYS)
            days_left = max(0, (grace_end - datetime.now(timezone.utc)).days)

            if datetime.now(timezone.utc) > grace_end:
                return LicenseResult(ok=False,
                                     reason=f"Offline grace period of {OFFLINE_GRACE_DAYS} days has expired.\nPlease connect to the internet to verify your license.")

            logger.warning(f"[license] Offline grace active: {days_left} day(s) remaining")
            return LicenseResult(
                ok=True,
                license_key=_kv_get_enc(_KV_LICENSE_KEY),
                expires_at=expires_raw,
                plan=_kv_get_enc(_KV_PLAN),
                customer_name=_kv_get_enc(_KV_CUSTOMER_NAME),
                days_remaining=kv.get(_KV_DAYS_REMAINING, 0),
                offline=True,
                reason=f"Offline mode — {days_left} day(s) of grace remaining.",
            )
        except Exception as e:
            logger.error(f"[license] _offline_fallback: {e}", exc_info=True)
            return LicenseResult(ok=False, reason=f"License check error: {e}")

    @staticmethod
    def _friendly_error(reason: str, data: dict) -> str:
        return {
            "trial_already_used": (
                "A free trial has already been used on this machine.\n\n"
                "Purchase a license to continue using Algo Trading Pro."
            ),
            "invalid_email": "Please enter a valid email address.",
            "replay_detected": "Request replay detected. Please check your system clock.",
            "invalid_signature": "Request signature invalid. Please reinstall the application.",
        }.get(reason, data.get("message") or "Operation failed. Please try again.")


# ── Module-level singleton ─────────────────────────────────────────────────────
license_manager = LicenseManager()
