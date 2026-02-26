"""
Utils/BrokerLoginHelper.py
==========================
Generic multi-broker login helper.

Replaces FyersManualLoginHelper with a polymorphic design.

Usage:
    helper = BrokerLoginHelper.for_broker(
        broker_type="fyers",          # or "zerodha", "upstox", etc.
        client_id=...,
        secret_key=...,
        redirect_uri=...,
    )

    # For OAuth brokers (fyers, zerodha, upstox, flattrade):
    url  = helper.generate_login_url()
    tok  = helper.exchange_code_for_token(auth_code)

    # For TOTP brokers (angelone, shoonya):
    tok  = helper.exchange_code_for_token(totp_code, password="MPIN")

    # For static-token brokers (dhan):
    tok  = helper.exchange_code_for_token(access_token)

    # For session-token brokers (icici):
    url  = helper.generate_login_url()
    tok  = helper.exchange_code_for_token(session_token)

    # For password brokers (aliceblue):
    tok  = helper.exchange_code_for_token("")   # credentials already in helper

Auth methods (mirrors BrokerType.AUTH_METHOD):
    oauth    — Fyers, Zerodha, Upstox, FlatTrade
    totp     — Angel One, Shoonya, Kotak Neo
    static   — Dhan
    session  — ICICI Breeze
    password — Alice Blue
"""

import hashlib
import logging
import urllib.parse
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from db.connector import get_db
from db.crud import tokens

logger = logging.getLogger(__name__)


# ── Abstract base ─────────────────────────────────────────────────────────────

class BrokerLoginHelper(ABC):
    """
    Abstract base for broker login helpers.
    Subclasses implement the auth flow for each broker.
    """

    def __init__(self, client_id: str, secret_key: str, redirect_uri: str = ""):
        self.client_id = client_id or ""
        self.secret_key = secret_key or ""
        self.redirect_uri = redirect_uri or ""
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_issued_at: Optional[str] = None
        self.token_expires_at: Optional[str] = None
        self._load_token()

    # ── Factory method ────────────────────────────────────────────────────────

    @staticmethod
    def for_broker(broker_type: str, client_id: str, secret_key: str,
                   redirect_uri: str = "", **extra) -> "BrokerLoginHelper":
        """
        Create the correct helper subclass for the given broker_type.
        extra kwargs are passed to the subclass constructor (e.g. totp_secret).
        """
        bt = (broker_type or "fyers").strip().lower()
        mapping = {
            "fyers": FyersLoginHelper,
            "zerodha": ZerodhaLoginHelper,
            "dhan": DhanLoginHelper,
            "angelone": AngelOneLoginHelper,
            "upstox": UpstoxLoginHelper,
            "shoonya": ShoonyaLoginHelper,
            "kotak": KotakLoginHelper,
            "icici": IciciLoginHelper,
            "aliceblue": AliceBlueLoginHelper,
            "flattrade": FlattradeLoginHelper,
        }
        cls = mapping.get(bt, FyersLoginHelper)
        return cls(client_id=client_id, secret_key=secret_key,
                   redirect_uri=redirect_uri, **extra)

    # ── Required interface ────────────────────────────────────────────────────

    @property
    def auth_method(self) -> str:
        """Returns: 'oauth', 'totp', 'static', 'session', or 'password'"""
        return "oauth"

    @property
    def broker_display_name(self) -> str:
        return "Broker"

    def generate_login_url(self) -> str:
        """Return the URL the user should open in a browser (OAuth/session brokers)."""
        return ""

    @abstractmethod
    def exchange_code_for_token(self, code_or_token: str, **kwargs) -> Optional[str]:
        """
        Perform the final authentication step.

        For OAuth brokers: code_or_token = auth_code from browser redirect.
        For TOTP brokers:  code_or_token = 6-digit TOTP, password=MPIN in kwargs.
        For static/session: code_or_token = the token itself.
        For password:      code_or_token = "" (credentials stored internally).

        Returns:
            access_token string, or None on failure.
        """

    # ── Step-by-step instructions (displayed in the popup) ───────────────────

    @property
    def step1_title(self) -> str:
        return "Step 1 — Open the login URL and authorise"

    @property
    def step1_hint(self) -> str:
        return "Click the button below to open the login page in your browser."

    @property
    def step2_title(self) -> str:
        return "Step 2 — Paste the redirected URL or auth code"

    @property
    def step2_hint(self) -> str:
        return ("After authorising, paste the full redirected URL or just the "
                "token/code here.")

    @property
    def code_entry_placeholder(self) -> str:
        return "Paste full redirected URL or auth code here…"

    @property
    def has_login_url(self) -> bool:
        """True if this broker needs the user to visit a URL."""
        return self.auth_method in ("oauth", "session")

    @property
    def needs_password_field(self) -> bool:
        """True if the popup should show a secondary password/MPIN field."""
        return self.auth_method == "totp"

    @property
    def password_field_label(self) -> str:
        return "MPIN / Password"

    @property
    def password_field_placeholder(self) -> str:
        return "Enter your broker MPIN or password"

    # ── Common token helpers ──────────────────────────────────────────────────

    def _load_token(self) -> None:
        try:
            db = get_db()
            data = tokens.get(db)
            if data and data.get("access_token"):
                self.access_token = data["access_token"]
                self.refresh_token = data.get("refresh_token", "")
                self.token_issued_at = data.get("issued_at")
                self.token_expires_at = data.get("expires_at")
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}._load_token] {e}", exc_info=True)

    def _save_token(self, access_token: str, refresh_token: str = "",
                    hours_valid: int = 8) -> bool:
        try:
            issued = datetime.now().isoformat()
            expires = (datetime.now() + timedelta(hours=hours_valid)).isoformat()
            self.access_token = access_token
            self.refresh_token = refresh_token
            self.token_issued_at = issued
            self.token_expires_at = expires
            db = get_db()
            return bool(tokens.save_token(
                access_token=access_token,
                refresh_token=refresh_token,
                issued_at=issued,
                expires_at=expires,
                db=db,
            ))
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}._save_token] {e}", exc_info=True)
            return False

    def is_authenticated(self) -> bool:
        if not self.access_token or len(self.access_token) < 10:
            return False
        status = self.get_token_expiry_status()
        return status.get("is_valid", False)

    def get_token_expiry_status(self) -> Dict[str, Any]:
        try:
            if not self.access_token:
                return {"is_valid": False, "expires_at": None,
                        "expires_in_seconds": 0, "expires_in_hours": 0, "status": "no_token"}

            if not self.token_expires_at:
                return {"is_valid": True, "expires_at": None,
                        "expires_in_seconds": -1, "expires_in_hours": -1, "status": "unknown"}

            exp = self.token_expires_at
            try:
                if isinstance(exp, (int, float)):
                    expiry_time = datetime.fromtimestamp(int(exp))
                else:
                    try:
                        expiry_time = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
                    except Exception:
                        expiry_time = datetime.fromtimestamp(int(float(exp)))
            except Exception:
                return {"is_valid": True, "expires_at": str(exp),
                        "expires_in_seconds": -1, "expires_in_hours": -1, "status": "unknown"}

            secs = (expiry_time - datetime.now()).total_seconds()
            hrs = secs / 3600
            if secs <= 0:
                status, valid = "expired", False
            elif secs < 3600:
                status, valid = "expiring_soon", True
            else:
                status, valid = "valid", True

            return {"is_valid": valid, "expires_at": expiry_time.isoformat(),
                    "expires_in_seconds": int(secs),
                    "expires_in_hours": round(hrs, 2), "status": status}

        except Exception as e:
            logger.error(f"[get_token_expiry_status] {e}", exc_info=True)
            return {"is_valid": bool(self.access_token), "expires_at": None,
                    "expires_in_seconds": -1, "expires_in_hours": -1, "status": "error"}

    def get_token_info(self) -> Dict[str, Any]:
        expiry = self.get_token_expiry_status()
        return {
            "has_token": bool(self.access_token),
            "token_length": len(self.access_token) if self.access_token else 0,
            "has_refresh_token": bool(self.refresh_token),
            "issued_at": self.token_issued_at,
            **expiry,
        }

    def is_token_expired(self) -> bool:
        s = self.get_token_expiry_status()
        return s["status"] == "expired" or not s["is_valid"]

    def is_token_expiring_soon(self, threshold_hours: int = 1) -> bool:
        s = self.get_token_expiry_status()
        return s["status"] == "expiring_soon" and 0 < s.get("expires_in_hours", 0) < threshold_hours

    def clear_token(self) -> None:
        self.access_token = self.refresh_token = None
        self.token_issued_at = self.token_expires_at = None

    def revoke_token(self) -> bool:
        try:
            db = get_db()
            ok = tokens.clear(db)
            if ok:
                self.clear_token()
            return bool(ok)
        except Exception as e:
            logger.error(f"[revoke_token] {e}", exc_info=True)
            return False

    def cleanup(self) -> None:
        self.clear_token()


# ── Fyers ─────────────────────────────────────────────────────────────────────

class FyersLoginHelper(BrokerLoginHelper):
    auth_method = "oauth"
    broker_display_name = "Fyers"

    step1_title = "Step 1 — Open the Fyers login URL and authorise"
    step1_hint = "Click the button below to open the Fyers login page in your browser."
    step2_title = "Step 2 — Paste the redirected URL or auth code"
    step2_hint = ("After authorising, your browser will redirect to your Redirect URI.\n"
                  "Paste the entire redirected URL, or just the auth_code value.")
    code_entry_placeholder = "Paste full redirected URL or auth code here…"

    def generate_login_url(self, state: str = "STATE123") -> str:
        try:
            if not self.client_id or not self.redirect_uri:
                return ""
            params = {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "state": state,
            }
            return f"https://api-t1.fyers.in/api/v3/generate-authcode?{urllib.parse.urlencode(params)}"
        except Exception as e:
            logger.error(f"[FyersLoginHelper.generate_login_url] {e}", exc_info=True)
            return ""

    def exchange_code_for_token(self, code_or_token: str, **kwargs) -> Optional[str]:
        try:
            from fyers_apiv3 import fyersModel
            if not code_or_token:
                return None
            session = fyersModel.SessionModel(
                client_id=self.client_id,
                secret_key=self.secret_key,
                redirect_uri=self.redirect_uri,
                response_type="code",
                grant_type="authorization_code",
            )
            session.set_token(code_or_token)
            resp = session.generate_token()
            if isinstance(resp, dict) and resp.get("access_token"):
                tok = resp["access_token"]
                self.token_issued_at = resp.get("issued_at")
                self.token_expires_at = resp.get("expires_at")
                self._save_token(tok, resp.get("refresh_token", ""), hours_valid=24)
                return tok
            logger.error(f"Fyers token exchange failed: {resp}")
            return None
        except Exception as e:
            logger.error(f"[FyersLoginHelper.exchange_code_for_token] {e}", exc_info=True)
            return None


# ── Zerodha ───────────────────────────────────────────────────────────────────

class ZerodhaLoginHelper(BrokerLoginHelper):
    auth_method = "oauth"
    broker_display_name = "Zerodha (Kite)"

    step1_title = "Step 1 — Open the Kite Connect login URL"
    step1_hint = "Click below to open the Kite Connect login page in your browser."
    step2_title = "Step 2 — Paste the redirected URL or request_token"
    step2_hint = ("After login, Kite redirects to your redirect URL with a request_token.\n"
                  "Paste the full URL or just the request_token value.")
    code_entry_placeholder = "Paste full redirected URL or request_token here…"

    def generate_login_url(self) -> str:
        if not self.client_id:
            return ""
        return f"https://kite.zerodha.com/connect/login?v=3&api_key={self.client_id}"

    def exchange_code_for_token(self, code_or_token: str, **kwargs) -> Optional[str]:
        try:
            from kiteconnect import KiteConnect
            if not code_or_token:
                return None
            kite = KiteConnect(api_key=self.client_id)
            data = kite.generate_session(code_or_token, api_secret=self.secret_key)
            access_token = data.get("access_token")
            if access_token:
                self._save_token(access_token, hours_valid=8)
                return access_token
            logger.error(f"Zerodha token exchange failed: {data}")
            return None
        except Exception as e:
            logger.error(f"[ZerodhaLoginHelper.exchange_code_for_token] {e}", exc_info=True)
            return None


# ── Dhan ──────────────────────────────────────────────────────────────────────

class DhanLoginHelper(BrokerLoginHelper):
    auth_method = "static"
    broker_display_name = "Dhan"

    step1_title = "Static Access Token"
    step1_hint = "Dhan uses a static access token obtained from the dhanhq.co portal. No browser login required."
    step2_title = "Paste your Dhan access token"
    step2_hint = ("Log in to https://dhanhq.co → Account → Generate API Token.\n"
                  "Paste the token below and click 'Complete Login'.")
    code_entry_placeholder = "Paste Dhan access token here…"
    has_login_url = False

    def generate_login_url(self) -> str:
        return "https://dhanhq.co/docs/v2"

    def exchange_code_for_token(self, code_or_token: str, **kwargs) -> Optional[str]:
        try:
            token = (code_or_token or self.secret_key or "").strip()
            if not token:
                logger.error("Dhan: no access token provided")
                return None
            self._save_token(token, hours_valid=24 * 365)  # static tokens are long-lived
            return token
        except Exception as e:
            logger.error(f"[DhanLoginHelper.exchange_code_for_token] {e}", exc_info=True)
            return None


# ── Angel One ─────────────────────────────────────────────────────────────────

class AngelOneLoginHelper(BrokerLoginHelper):
    """
    Requires:
        client_id    = Angel One Client Code
        secret_key   = API Key
        redirect_uri = TOTP base32 secret (stored in BrokerageSetting.redirect_uri)
    """
    auth_method = "totp"
    broker_display_name = "Angel One (SmartAPI)"
    needs_password_field = True
    password_field_label = "MPIN (4-digit)"
    password_field_placeholder = "Enter your Angel One MPIN"

    step1_title = "TOTP-based login — no browser required"
    step1_hint = ("Angel One uses TOTP + MPIN. No browser login is needed.\n"
                  "Your TOTP secret is stored in settings and used automatically.")
    step2_title = "Enter your MPIN to complete login"
    step2_hint = ("Enter your 4-digit Angel One MPIN in the password field below.\n"
                  "The TOTP code will be auto-generated from your stored secret.")
    code_entry_placeholder = "TOTP code (leave blank to auto-generate)"

    def __init__(self, client_id: str, secret_key: str, redirect_uri: str = "", **kwargs):
        # redirect_uri holds the TOTP base32 secret
        self.totp_secret = redirect_uri or kwargs.get("totp_secret", "")
        super().__init__(client_id=client_id, secret_key=secret_key, redirect_uri=redirect_uri)

    def generate_login_url(self) -> str:
        return "https://smartapi.angelbroking.com"

    def exchange_code_for_token(self, code_or_token: str, **kwargs) -> Optional[str]:
        """
        code_or_token: TOTP code (optional — auto-generated if blank and totp_secret is set)
        kwargs['password']: MPIN (required)
        """
        try:
            from SmartApi import SmartConnect
            import pyotp
            password = kwargs.get("password", "")
            if not password:
                logger.error("AngelOne: MPIN (password) is required")
                return None
            totp = code_or_token.strip() or (
                pyotp.TOTP(self.totp_secret).now() if self.totp_secret else ""
            )
            if not totp:
                logger.error("AngelOne: TOTP code required and could not be auto-generated")
                return None

            smart = SmartConnect(api_key=self.secret_key)
            data = smart.generateSession(self.client_id, password, totp)
            if data and data.get("status") is not False:
                jwt = data["data"]["jwtToken"]
                refresh = data["data"].get("refreshToken", "")
                self._save_token(jwt, refresh, hours_valid=8)
                return jwt
            logger.error(f"AngelOne login failed: {data}")
            return None
        except Exception as e:
            logger.error(f"[AngelOneLoginHelper.exchange_code_for_token] {e}", exc_info=True)
            return None


# ── Upstox ────────────────────────────────────────────────────────────────────

class UpstoxLoginHelper(BrokerLoginHelper):
    auth_method = "oauth"
    broker_display_name = "Upstox"

    UPSTOX_TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"

    step1_title = "Step 1 — Open the Upstox login URL"
    step1_hint = "Click below to open the Upstox OAuth login page."
    step2_title = "Step 2 — Paste the redirected URL or auth code"
    step2_hint = ("After login, Upstox redirects to your redirect URI with a code.\n"
                  "Paste the full URL or just the code value.")
    code_entry_placeholder = "Paste full redirected URL or auth code here…"

    def generate_login_url(self) -> str:
        if not self.client_id or not self.redirect_uri:
            return ""
        return (f"https://api.upstox.com/v2/login/authorization/dialog"
                f"?response_type=code&client_id={self.client_id}"
                f"&redirect_uri={urllib.parse.quote(self.redirect_uri)}")

    def exchange_code_for_token(self, code_or_token: str, **kwargs) -> Optional[str]:
        try:
            import requests
            if not code_or_token:
                return None
            resp = requests.post(
                self.UPSTOX_TOKEN_URL,
                data={
                    "code": code_or_token,
                    "client_id": self.client_id,
                    "client_secret": self.secret_key,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"accept": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            access_token = data.get("access_token")
            if access_token:
                self._save_token(access_token, hours_valid=8)
                return access_token
            logger.error(f"Upstox token exchange failed: {data}")
            return None
        except Exception as e:
            logger.error(f"[UpstoxLoginHelper.exchange_code_for_token] {e}", exc_info=True)
            return None


# ── Shoonya ───────────────────────────────────────────────────────────────────

class ShoonyaLoginHelper(BrokerLoginHelper):
    """
    client_id    = "user_id|vendor_code"
    secret_key   = password (plain text, will be SHA256-hashed)
    redirect_uri = TOTP base32 secret
    """
    auth_method = "totp"
    broker_display_name = "Shoonya / Finvasia"
    needs_password_field = False  # Password is stored in secret_key; only TOTP needed

    step1_title = "TOTP-based login — no browser required"
    step1_hint = ("Shoonya uses TOTP. No browser login is needed.\n"
                  "Your credentials and TOTP secret are stored in settings.")
    step2_title = "Enter TOTP code (or leave blank to auto-generate)"
    step2_hint = ("If you stored your TOTP secret in settings, leave the field blank.\n"
                  "Otherwise, enter the 6-digit code from your authenticator app.")
    code_entry_placeholder = "6-digit TOTP code (blank = auto-generate)"

    SHOONYA_HOST = "https://api.shoonya.com/NorenWClientTP/"
    SHOONYA_WS = "wss://api.shoonya.com/NorenWSTP/"

    def __init__(self, client_id: str, secret_key: str, redirect_uri: str = "", **kwargs):
        self.totp_secret = redirect_uri or kwargs.get("totp_secret", "")
        raw = client_id or ""
        if "|" in raw:
            self.user_id, self.vendor_code = raw.split("|", 1)
        else:
            self.user_id = raw
            self.vendor_code = raw
        super().__init__(client_id=client_id, secret_key=secret_key, redirect_uri=redirect_uri)

    def generate_login_url(self) -> str:
        return "https://www.shoonya.com/api-documentation"

    def exchange_code_for_token(self, code_or_token: str, **kwargs) -> Optional[str]:
        try:
            from NorenRestApiPy.NorenApi import NorenApi
            import pyotp
            totp = code_or_token.strip() or (
                pyotp.TOTP(self.totp_secret).now() if self.totp_secret else ""
            )
            if not totp:
                logger.error("Shoonya: TOTP required")
                return None
            pwd_hash = hashlib.sha256(self.secret_key.encode()).hexdigest()
            api = NorenApi(host=self.SHOONYA_HOST, websocket=self.SHOONYA_WS)
            ret = api.login(
                userid=self.user_id, password=pwd_hash,
                twoFA=totp, vendor_code=self.vendor_code,
                api_secret=self.vendor_code, imei="algo-trader",
            )
            if ret and ret.get("stat") == "Ok":
                susertoken = ret["susertoken"]
                self._save_token(susertoken, hours_valid=8)
                return susertoken
            logger.error(f"Shoonya login failed: {ret}")
            return None
        except Exception as e:
            logger.error(f"[ShoonyaLoginHelper.exchange_code_for_token] {e}", exc_info=True)
            return None


# ── Kotak Neo ─────────────────────────────────────────────────────────────────

class KotakLoginHelper(BrokerLoginHelper):
    """
    client_id    = Consumer Key
    secret_key   = Consumer Secret
    redirect_uri = TOTP base32 secret

    TOTP login requires mobile + UCC + MPIN passed as kwargs.
    """
    auth_method = "totp"
    broker_display_name = "Kotak Neo"
    needs_password_field = True
    password_field_label = "MPIN (4-digit)"
    password_field_placeholder = "Enter your Kotak Neo MPIN"

    step1_title = "TOTP-based login — no browser required"
    step1_hint = ("Kotak Neo uses TOTP + MPIN. No browser login is needed.")
    step2_title = "Enter TOTP and additional details"
    step2_hint = ("Enter your TOTP code (or leave blank to auto-generate).\n"
                  "Provide your MPIN in the password field below.\n"
                  "Mobile number and UCC must be set in the extra fields.")
    code_entry_placeholder = "6-digit TOTP code (blank = auto-generate)"

    def __init__(self, client_id: str, secret_key: str, redirect_uri: str = "", **kwargs):
        self.totp_secret = redirect_uri or kwargs.get("totp_secret", "")
        self.mobile = kwargs.get("mobile", "")
        self.ucc = kwargs.get("ucc", "")
        super().__init__(client_id=client_id, secret_key=secret_key, redirect_uri=redirect_uri)

    def generate_login_url(self) -> str:
        return "https://github.com/Kotak-Neo/kotak-neo-api"

    def exchange_code_for_token(self, code_or_token: str, **kwargs) -> Optional[str]:
        try:
            from neo_api_client import NeoAPI
            import pyotp
            password = kwargs.get("password", "")
            mobile = kwargs.get("mobile", self.mobile or "")
            ucc = kwargs.get("ucc", self.ucc or "")

            if not mobile or not ucc:
                logger.error("KotakNeo: mobile and UCC are required")
                return None
            if not password:
                logger.error("KotakNeo: MPIN is required")
                return None

            totp = code_or_token.strip() or (
                pyotp.TOTP(self.totp_secret).now() if self.totp_secret else ""
            )
            if not totp:
                logger.error("KotakNeo: TOTP required")
                return None

            client = NeoAPI(
                consumer_key=self.client_id,
                consumer_secret=self.secret_key,
                environment="prod",
                neo_fin_key="neotradeapi",
            )
            client.totp_login(mobile_number=mobile, ucc=ucc, totp=totp)
            ret = client.totp_validate(mpin=password)
            if ret:
                access_token = str(ret.get("data", {}).get("token") or ret)
                self._save_token(access_token, hours_valid=8)
                return access_token
            logger.error(f"KotakNeo login failed: {ret}")
            return None
        except Exception as e:
            logger.error(f"[KotakLoginHelper.exchange_code_for_token] {e}", exc_info=True)
            return None


# ── ICICI Breeze ──────────────────────────────────────────────────────────────

class IciciLoginHelper(BrokerLoginHelper):
    auth_method = "session"
    broker_display_name = "ICICI Breeze"

    step1_title = "Step 1 — Open the ICICI Breeze login URL"
    step1_hint = ("Click below to open the ICICI Direct login page.\n"
                  "⚠️  ICICI Breeze now requires a Static IP for API usage (SEBI mandate).")
    step2_title = "Step 2 — Paste the session token"
    step2_hint = ("After login, the page redirects to your app with a session token.\n"
                  "Copy the token value and paste it here.")
    code_entry_placeholder = "Paste ICICI Breeze session token here…"

    def generate_login_url(self) -> str:
        if not self.client_id:
            return ""
        import urllib.parse
        return f"https://api.icicidirect.com/apiuser/login?api_key={urllib.parse.quote_plus(self.client_id)}"

    def exchange_code_for_token(self, code_or_token: str, **kwargs) -> Optional[str]:
        try:
            from breeze_connect import BreezeConnect
            if not code_or_token:
                return None
            breeze = BreezeConnect(api_key=self.client_id)
            breeze.generate_session(api_secret=self.secret_key, session_token=code_or_token)
            self._save_token(code_or_token, hours_valid=10)
            return code_or_token
        except Exception as e:
            logger.error(f"[IciciLoginHelper.exchange_code_for_token] {e}", exc_info=True)
            return None


# ── Alice Blue ────────────────────────────────────────────────────────────────

class AliceBlueLoginHelper(BrokerLoginHelper):
    """
    client_id    = App ID
    secret_key   = API Secret
    redirect_uri = "username|password|YOB"
    """
    auth_method = "password"
    broker_display_name = "Alice Blue"

    step1_title = "Automated login — no browser required"
    step1_hint = ("Alice Blue uses username + password + Year of Birth.\n"
                  "Credentials are stored in settings (redirect_uri field).\n"
                  "Click 'Complete Login' to authenticate automatically.")
    step2_title = "Click 'Complete Login' to authenticate"
    step2_hint = ("Leave the field below blank — credentials will be read from settings.\n"
                  "Format in redirect_uri: username|password|YOB")
    code_entry_placeholder = "Leave blank — login uses stored credentials"

    def __init__(self, client_id: str, secret_key: str, redirect_uri: str = "", **kwargs):
        creds = (redirect_uri or "").split("|")
        self.username = creds[0] if len(creds) > 0 else ""
        self.password = creds[1] if len(creds) > 1 else ""
        self.yob = creds[2] if len(creds) > 2 else ""
        super().__init__(client_id=client_id, secret_key=secret_key, redirect_uri=redirect_uri)

    def generate_login_url(self) -> str:
        return "https://ant.aliceblueonline.com/developers"

    def exchange_code_for_token(self, code_or_token: str = "", **kwargs) -> Optional[str]:
        try:
            from pya3 import Aliceblue
            if not self.username or not self.password or not self.yob:
                logger.error("AliceBlue: username, password, and YOB required in redirect_uri")
                return None
            session_id = Aliceblue.login_and_get_access_token(
                username=self.username,
                password=self.password,
                twoFA=self.yob,
                api_secret=self.secret_key,
                app_id=self.client_id,
            )
            if not session_id:
                logger.error("AliceBlue: login_and_get_access_token returned None")
                return None
            self._save_token(session_id, hours_valid=10)
            return session_id
        except Exception as e:
            logger.error(f"[AliceBlueLoginHelper.exchange_code_for_token] {e}", exc_info=True)
            return None


# ── FlatTrade ─────────────────────────────────────────────────────────────────

class FlattradeLoginHelper(BrokerLoginHelper):
    """
    client_id    = "user_id|api_key"
    secret_key   = API Secret
    redirect_uri = registered redirect URI
    """
    auth_method = "oauth"
    broker_display_name = "FlatTrade (Pi)"

    FLATTRADE_HOST = "https://piconnect.flattrade.in/PiConnectTP/"
    FLATTRADE_WS = "wss://piconnect.flattrade.in/PiConnectWSTp/"

    step1_title = "Step 1 — Open the FlatTrade login URL"
    step1_hint = ("Click below to open the FlatTrade OAuth login page.\n"
                  "FlatTrade Pi offers zero brokerage algo trading!")
    step2_title = "Step 2 — Paste the token from the redirect URL"
    step2_hint = ("After login, the URL will contain a code (token).\n"
                  "Paste the full URL or just the code/token here.")
    code_entry_placeholder = "Paste full redirected URL or token code here…"

    def __init__(self, client_id: str, secret_key: str, redirect_uri: str = "", **kwargs):
        raw = client_id or ""
        if "|" in raw:
            self.user_id, self.api_key = raw.split("|", 1)
        else:
            self.user_id = raw
            self.api_key = raw
        super().__init__(client_id=client_id, secret_key=secret_key, redirect_uri=redirect_uri)

    def generate_login_url(self) -> str:
        return f"https://auth.flattrade.in/?api_key={self.api_key}"

    def exchange_code_for_token(self, code_or_token: str, **kwargs) -> Optional[str]:
        try:
            from NorenRestApiPy.NorenApi import NorenApi
            if not code_or_token:
                return None
            # Try SHA256(user_id + api_key + code) first
            sha_token = hashlib.sha256(
                f"{self.user_id}{self.api_key}{code_or_token}".encode()
            ).hexdigest()

            api = NorenApi(host=self.FLATTRADE_HOST, websocket=self.FLATTRADE_WS)

            for attempt_token in (sha_token, code_or_token):
                ret = api.set_session(userid=self.user_id, password="", usertoken=attempt_token)
                if ret and ret.get("stat") == "Ok":
                    self._save_token(attempt_token, hours_valid=8)
                    return attempt_token

            logger.error(f"FlatTrade set_session failed for both hash and raw token")
            return None
        except Exception as e:
            logger.error(f"[FlattradeLoginHelper.exchange_code_for_token] {e}", exc_info=True)
            return None
