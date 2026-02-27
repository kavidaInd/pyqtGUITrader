"""
BrokerageSetting.py  (multi-broker edition)
============================================
Adds `broker_type` field to the existing database-backed settings class.

New field stored in brokerage_setting table:
    broker_type  → "fyers" | "zerodha" | "dhan"  (default: "fyers")

All existing code that uses BrokerageSetting continues to work unchanged.
"""

import logging
import logging.handlers
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from db.connector import get_db
from db.crud import brokerage, tokens
from db.config_crud import config_crud

logger = logging.getLogger(__name__)


class BrokerageSetting:
    """
    Database-backed brokerage settings.

    Enhanced with:
    - broker_type selection (fyers / zerodha / dhan)
    - Telegram notification settings
    - Token management and expiry tracking
    """

    REQUIRED_FIELDS = ["client_id", "secret_key", "redirect_uri"]
    BROKER_FIELDS = ["broker_type"]
    TELEGRAM_FIELDS = ["telegram_bot_token", "telegram_chat_id"]

    DEFAULT_BROKER_TYPE = "fyers"

    def __init__(self):
        self._safe_defaults_init()
        try:
            self.load()
            self._load_telegram_settings()
            self._load_token_info()
            logger.info("BrokerageSetting initialized")
        except Exception as e:
            logger.critical(f"[BrokerageSetting.__init__] Failed: {e}", exc_info=True)
            self._data = {k: "" for k in self.REQUIRED_FIELDS}
            self._broker_data = {"broker_type": self.DEFAULT_BROKER_TYPE}
            self._telegram_data = {k: "" for k in self.TELEGRAM_FIELDS}
            self._token_data = {}

    def _safe_defaults_init(self):
        self._data: Dict[str, str] = {k: "" for k in self.REQUIRED_FIELDS}
        self._broker_data: Dict[str, str] = {"broker_type": self.DEFAULT_BROKER_TYPE}
        self._telegram_data: Dict[str, str] = {k: "" for k in self.TELEGRAM_FIELDS}
        self._token_data: Dict[str, Any] = {
            "access_token": "", "refresh_token": "",
            "issued_at": None, "expires_at": None, "is_valid": False
        }
        self._loaded = False
        self._token_loaded = False
        self._telegram_loaded = False

    # ── Load ──────────────────────────────────────────────────────────────────

    def load(self) -> bool:
        try:
            db = get_db()
            data = brokerage.get(db)
            if data:
                for k in self.REQUIRED_FIELDS:
                    self._data[k] = str(data.get(k, ""))
                # Load broker_type (may not exist in old DB rows — default gracefully)
                self._broker_data["broker_type"] = str(
                    data.get("broker_type", self.DEFAULT_BROKER_TYPE)
                ) or self.DEFAULT_BROKER_TYPE
            self._loaded = True
            return True
        except Exception as e:
            logger.error(f"[BrokerageSetting.load] {e}", exc_info=True)
            return False

    def _load_telegram_settings(self):
        try:
            db = get_db()
            self._telegram_data["telegram_bot_token"] = config_crud.get("telegram_bot_token", "", db)
            self._telegram_data["telegram_chat_id"] = config_crud.get("telegram_chat_id", "", db)
            self._telegram_loaded = True
        except Exception as e:
            logger.error(f"[BrokerageSetting._load_telegram_settings] {e}", exc_info=True)

    def _load_token_info(self):
        try:
            db = get_db()
            token_data = tokens.get(db)
            if token_data:
                self._token_data.update({
                    "access_token": token_data.get("access_token", ""),
                    "refresh_token": token_data.get("refresh_token", ""),
                    "issued_at": token_data.get("issued_at"),
                    "expires_at": token_data.get("expires_at"),
                    "is_valid": self._check_token_valid(),
                })
            self._token_loaded = True
        except Exception as e:
            logger.error(f"[BrokerageSetting._load_token_info] {e}", exc_info=True)

    def _check_token_valid(self) -> bool:
        try:
            if not self._token_data.get("access_token"):
                return False
            expires_at = self._token_data.get("expires_at")
            if expires_at:
                try:
                    expiry_time = (
                        datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                        if isinstance(expires_at, str) else expires_at
                    )
                    if datetime.now() > (expiry_time - timedelta(minutes=5)):
                        return False
                except Exception:
                    pass
            return True
        except Exception:
            return False

    # ── Save ──────────────────────────────────────────────────────────────────

    def save(self) -> bool:
        try:
            db = get_db()
            # Merge broker_type into the data dict for storage
            save_data = dict(self._data)
            save_data["broker_type"] = self._broker_data.get("broker_type", self.DEFAULT_BROKER_TYPE)
            success = brokerage.save(save_data, db)
            if success:
                self._save_telegram_settings()
            return success
        except Exception as e:
            logger.error(f"[BrokerageSetting.save] {e}", exc_info=True)
            return False

    def _save_telegram_settings(self):
        try:
            db = get_db()
            config_crud.set("telegram_bot_token", self._telegram_data.get("telegram_bot_token", ""), db)
            config_crud.set("telegram_chat_id", self._telegram_data.get("telegram_chat_id", ""), db)
        except Exception as e:
            logger.error(f"[BrokerageSetting._save_telegram_settings] {e}", exc_info=True)

    def save_token(self, access_token: str, refresh_token: str = "",
                   issued_at: str = None, expires_at: str = None) -> bool:
        try:
            db = get_db()
            success = tokens.save_token(access_token, refresh_token, issued_at, expires_at, db)
            if success:
                self._token_data.update({
                    "access_token": access_token, "refresh_token": refresh_token,
                    "issued_at": issued_at, "expires_at": expires_at, "is_valid": True,
                })
            return success
        except Exception as e:
            logger.error(f"[BrokerageSetting.save_token] {e}", exc_info=True)
            return False

    def clear_token(self) -> bool:
        try:
            db = get_db()
            success = tokens.save_token("", "", db=db)
            if success:
                self._token_data = {
                    "access_token": "", "refresh_token": "",
                    "issued_at": None, "expires_at": None, "is_valid": False
                }
            return success
        except Exception as e:
            logger.error(f"[BrokerageSetting.clear_token] {e}", exc_info=True)
            return False

    # ── Dict interface ────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, str]:
        result = dict(self._data)
        result.update(self._broker_data)
        result.update(self._telegram_data)
        result["has_token"] = str(self._token_data.get("is_valid", False))
        result["token_expiry"] = str(self._token_data.get("expires_at", ""))
        return result

    def from_dict(self, d: Optional[Dict[str, Any]]) -> None:
        if not isinstance(d, dict):
            return
        for k in self.REQUIRED_FIELDS:
            value = d.get(k, "")
            self._data[k] = str(value) if value is not None else ""
        # broker_type
        bt = d.get("broker_type", self.DEFAULT_BROKER_TYPE)
        self._broker_data["broker_type"] = str(bt) if bt else self.DEFAULT_BROKER_TYPE
        for k in self.TELEGRAM_FIELDS:
            value = d.get(k, "")
            self._telegram_data[k] = str(value) if value is not None else ""

    def get(self, key: str, default: str = "") -> str:
        try:
            if key in self._data:
                return str(self._data.get(key, default) or default)
            if key in self._broker_data:
                return str(self._broker_data.get(key, default) or default)
            if key in self._telegram_data:
                return str(self._telegram_data.get(key, default) or default)
            if key == "has_token":
                return str(self._token_data.get("is_valid", False))
            if key == "token_expiry":
                expiry = self._token_data.get("expires_at", "")
                return str(expiry) if expiry else ""
            return default
        except Exception as e:
            logger.error(f"[BrokerageSetting.get] key='{key}': {e}", exc_info=True)
            return default

    def set(self, key: str, value: str) -> bool:
        try:
            if key in self.REQUIRED_FIELDS:
                self._data[key] = str(value) if value is not None else ""
                return True
            if key == "broker_type":
                self._broker_data["broker_type"] = str(value) if value else self.DEFAULT_BROKER_TYPE
                return True
            if key in self.TELEGRAM_FIELDS:
                self._telegram_data[key] = str(value) if value is not None else ""
                return True
            logger.warning(f"BrokerageSetting.set: unknown key '{key}'")
            return False
        except Exception as e:
            logger.error(f"[BrokerageSetting.set] key='{key}': {e}", exc_info=True)
            return False

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self) -> Dict[str, bool]:
        results = {f: bool(self._data.get(f, "").strip()) for f in self.REQUIRED_FIELDS}
        results["broker_type"] = bool(self._broker_data.get("broker_type", "").strip())
        return results

    def is_valid(self) -> bool:
        v = self.validate()
        # broker_type is always set to default; only check required fields
        return all(v[f] for f in self.REQUIRED_FIELDS)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def client_id(self) -> str:
        return str(self._data.get("client_id", ""))

    @client_id.setter
    def client_id(self, value: str):
        self._data["client_id"] = str(value) if value is not None else ""

    @property
    def secret_key(self) -> str:
        return str(self._data.get("secret_key", ""))

    @secret_key.setter
    def secret_key(self, value: str):
        self._data["secret_key"] = str(value) if value is not None else ""

    @property
    def redirect_uri(self) -> str:
        return str(self._data.get("redirect_uri", ""))

    @redirect_uri.setter
    def redirect_uri(self, value: str):
        self._data["redirect_uri"] = str(value) if value is not None else ""

    @property
    def broker_type(self) -> str:
        """Active broker: 'fyers' | 'zerodha' | 'dhan'"""
        return str(self._broker_data.get("broker_type", self.DEFAULT_BROKER_TYPE))

    @broker_type.setter
    def broker_type(self, value: str):
        self._broker_data["broker_type"] = str(value).lower() if value else self.DEFAULT_BROKER_TYPE

    @property
    def telegram_bot_token(self) -> str:
        return str(self._telegram_data.get("telegram_bot_token", ""))

    @telegram_bot_token.setter
    def telegram_bot_token(self, value: str):
        self._telegram_data["telegram_bot_token"] = str(value) if value is not None else ""

    @property
    def telegram_chat_id(self) -> str:
        return str(self._telegram_data.get("telegram_chat_id", ""))

    @telegram_chat_id.setter
    def telegram_chat_id(self, value: str):
        self._telegram_data["telegram_chat_id"] = str(value) if value is not None else ""

    @property
    def has_valid_token(self) -> bool:
        return self._token_data.get("is_valid", False)

    @property
    def token_expiry(self) -> Optional[str]:
        expiry = self._token_data.get("expires_at")
        return str(expiry) if expiry else None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def is_telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def get_telegram_config(self) -> Dict[str, str]:
        return {"bot_token": self.telegram_bot_token, "chat_id": self.telegram_chat_id}

    def get_token_info(self) -> Dict[str, Any]:
        return dict(self._token_data)

    def reload_token(self) -> bool:
        try:
            self._load_token_info()
            return self._token_loaded
        except Exception as e:
            logger.error(f"[BrokerageSetting.reload_token] {e}", exc_info=True)
            return False

    def cleanup(self) -> None:
        self._data.clear()
        self._broker_data.clear()
        self._telegram_data.clear()
        self._token_data.clear()

    def __repr__(self) -> str:
        safe = {k: (v if k != "secret_key" else "***") for k, v in self._data.items()}
        safe["broker_type"] = self.broker_type
        safe["telegram"] = "configured" if self.is_telegram_configured() else "not configured"
        safe["token_valid"] = self._token_data.get("is_valid", False)
        return f"<BrokerageSetting {safe}>"