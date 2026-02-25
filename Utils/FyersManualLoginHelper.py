"""
FyersManualLoginHelper_db.py
=============================
Database-backed Fyers manual login helper using the SQLite database for token storage.

FEATURE 4: Added token expiry tracking for Telegram notifications.
"""

import logging
import urllib.parse
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from fyers_apiv3 import fyersModel

from db.connector import get_db
from db.crud import tokens

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class FyersManualLoginHelper:
    """
    Fyers manual login helper using database for token storage.

    FEATURE 4: Tracks token expiry for notifications.
    """

    def __init__(
            self,
            client_id: str,
            secret_key: str,
            redirect_uri: str
    ):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 6: Input validation
            if not client_id:
                logger.error("client_id is required")
                client_id = ""

            if not secret_key:
                logger.error("secret_key is required")
                secret_key = ""

            if not redirect_uri:
                logger.error("redirect_uri is required")
                redirect_uri = ""

            self.client_id = client_id
            self.secret_key = secret_key
            self.redirect_uri = redirect_uri
            self.access_token: Optional[str] = None
            self.token_issued_at: Optional[str] = None
            self.token_expires_at: Optional[str] = None
            self.refresh_token: Optional[str] = None

            # Load token from database
            self._load_token()

            logger.debug("FyersManualLoginHelper (database) initialized")

        except Exception as e:
            logger.critical(f"[FyersManualLoginHelper.__init__] Failed: {e}", exc_info=True)
            self.client_id = client_id or ""
            self.secret_key = secret_key or ""
            self.redirect_uri = redirect_uri or ""
            self.access_token = None
            self.token_issued_at = None
            self.token_expires_at = None
            self.refresh_token = None

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.client_id = ""
        self.secret_key = ""
        self.redirect_uri = ""
        self.access_token = None
        self.token_issued_at = None
        self.token_expires_at = None
        self.refresh_token = None

    def _load_token(self) -> None:
        """
        Load token from database.
        """
        try:
            db = get_db()
            token_data = tokens.get(db)

            if token_data and token_data.get("access_token"):
                self.access_token = token_data["access_token"]
                self.token_issued_at = token_data.get("issued_at")
                self.token_expires_at = token_data.get("expires_at")
                self.refresh_token = token_data.get("refresh_token", "")

                # Calculate expiry status
                expiry_status = self.get_token_expiry_status()
                logger.debug(f"Token loaded from database (length: {len(self.access_token)}, expires: {self.token_expires_at}, status: {expiry_status['status']})")
            else:
                logger.debug("No token found in database")

        except Exception as e:
            logger.error(f"Error loading token from database: {e}", exc_info=True)
            self.access_token = None
            self.token_issued_at = None
            self.token_expires_at = None
            self.refresh_token = None

    def generate_login_url(self, state: str = "STATE123") -> str:
        """
        Generate Fyers login URL.

        Args:
            state: State parameter for OAuth

        Returns:
            Login URL string
        """
        try:
            # Rule 6: Input validation
            if not self.client_id:
                logger.error("Cannot generate login URL: client_id is missing")
                return ""

            if not self.redirect_uri:
                logger.error("Cannot generate login URL: redirect_uri is missing")
                return ""

            params = {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "state": state or "STATE123"
            }

            url = f"https://api-t1.fyers.in/api/v3/generate-authcode?{urllib.parse.urlencode(params)}"
            logger.debug(f"Generated login URL: {url}")
            return url

        except Exception as e:
            logger.error(f"Failed to generate login URL: {e}", exc_info=True)
            return ""

    def exchange_code_for_token(self, auth_code: str) -> Optional[str]:
        """
        Exchange authorization code for access token.

        Args:
            auth_code: Authorization code from Fyers

        Returns:
            Access token or None if failed
        """
        try:
            # Rule 6: Input validation
            if not auth_code:
                logger.error("exchange_code_for_token called with empty auth_code")
                return None

            if not self.client_id:
                logger.error("Cannot exchange token: client_id is missing")
                return None

            if not self.secret_key:
                logger.error("Cannot exchange token: secret_key is missing")
                return None

            if not self.redirect_uri:
                logger.error("Cannot exchange token: redirect_uri is missing")
                return None

            # Create session
            try:
                session = fyersModel.SessionModel(
                    client_id=self.client_id,
                    secret_key=self.secret_key,
                    redirect_uri=self.redirect_uri,
                    response_type="code",
                    grant_type="authorization_code"
                )
            except Exception as e:
                logger.error(f"Failed to create SessionModel: {e}", exc_info=True)
                return None

            # Set token and generate
            try:
                session.set_token(auth_code)
                response = session.generate_token()
            except Exception as e:
                logger.error(f"Token exchange API call failed: {e}", exc_info=True)
                return None

            # Process response
            if isinstance(response, dict):
                if "access_token" in response and response["access_token"]:
                    self.access_token = response["access_token"]
                    self.refresh_token = response.get("refresh_token", "")

                    # FEATURE 4: Store expiry times
                    self.token_issued_at = response.get("issued_at")
                    self.token_expires_at = response.get("expires_at")

                    # Save token to database
                    try:
                        db = get_db()
                        success = tokens.save_token(
                            access_token=self.access_token,
                            refresh_token=self.refresh_token,
                            issued_at=self.token_issued_at,
                            expires_at=self.token_expires_at,
                            db=db
                        )

                        if success:
                            logger.info("Token received and saved to database successfully")

                            # Log expiry info
                            if self.token_expires_at:
                                try:
                                    # Parse expiry (Fyers typically returns timestamp in seconds)
                                    if isinstance(self.token_expires_at, (int, float)):
                                        expiry_dt = datetime.fromtimestamp(int(self.token_expires_at))
                                        logger.info(f"Token expires at: {expiry_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                                except Exception as e:
                                    logger.warning(f"Could not parse expiry timestamp: {e}")
                        else:
                            logger.error("Failed to save token to database")

                    except Exception as e:
                        logger.error(f"Failed to save token to database: {e}", exc_info=True)

                    return self.access_token
                else:
                    error_msg = f"Token exchange failed. Response missing access_token: {response}"
                    logger.error(error_msg)
                    return None
            else:
                error_msg = f"Unexpected response type from generate_token: {type(response)}"
                logger.error(error_msg)
                return None

        except Exception as e:
            logger.error(f"Exception during token exchange: {e}", exc_info=True)
            return None

    def get_access_token(self) -> Optional[str]:
        """Get the current access token."""
        try:
            return self.access_token
        except Exception as e:
            logger.error(f"[get_access_token] Failed: {e}", exc_info=True)
            return None

    def is_authenticated(self) -> bool:
        """Check if helper has a valid access token."""
        try:
            # Check if token exists and has reasonable length
            if not self.access_token or len(self.access_token) < 50:
                return False

            # FEATURE 4: Check if token is expired
            expiry_info = self.get_token_expiry_status()
            return expiry_info["is_valid"]

        except Exception as e:
            logger.error(f"[is_authenticated] Failed: {e}", exc_info=True)
            return False

    # ==================================================================
    # FEATURE 4: Token expiry tracking
    # ==================================================================

    def get_token_expiry_status(self) -> Dict[str, Any]:
        """
        Get detailed token expiry status.

        Returns:
            Dict with expiry information:
            - is_valid: bool
            - expires_at: str (ISO format)
            - expires_in_seconds: int
            - expires_in_hours: float
            - status: str ('valid', 'expired', 'expiring_soon', 'unknown')
        """
        try:
            if not self.access_token:
                return {
                    "is_valid": False,
                    "expires_at": None,
                    "expires_in_seconds": 0,
                    "expires_in_hours": 0,
                    "status": "no_token"
                }

            if not self.token_expires_at:
                # If no expiry info, assume token is valid but unknown expiry
                return {
                    "is_valid": True,
                    "expires_at": None,
                    "expires_in_seconds": -1,
                    "expires_in_hours": -1,
                    "status": "unknown"
                }

            # Parse expiry timestamp
            try:
                # Fyers typically returns timestamp in seconds
                if isinstance(self.token_expires_at, (int, float)):
                    expiry_time = datetime.fromtimestamp(int(self.token_expires_at))
                elif isinstance(self.token_expires_at, str):
                    # Try to parse ISO format
                    try:
                        expiry_time = datetime.fromisoformat(self.token_expires_at.replace('Z', '+00:00'))
                    except:
                        # Try as timestamp string
                        expiry_time = datetime.fromtimestamp(int(float(self.token_expires_at)))
                else:
                    expiry_time = None
            except Exception as e:
                logger.warning(f"Could not parse expiry time: {e}")
                return {
                    "is_valid": True,
                    "expires_at": str(self.token_expires_at),
                    "expires_in_seconds": -1,
                    "expires_in_hours": -1,
                    "status": "unknown"
                }

            if expiry_time is None:
                return {
                    "is_valid": True,
                    "expires_at": str(self.token_expires_at),
                    "expires_in_seconds": -1,
                    "expires_in_hours": -1,
                    "status": "unknown"
                }

            now = datetime.now()
            seconds_remaining = (expiry_time - now).total_seconds()
            hours_remaining = seconds_remaining / 3600

            # Determine status
            if seconds_remaining <= 0:
                status = "expired"
                is_valid = False
            elif seconds_remaining < 3600:  # Less than 1 hour
                status = "expiring_soon"
                is_valid = True
            else:
                status = "valid"
                is_valid = True

            return {
                "is_valid": is_valid,
                "expires_at": expiry_time.isoformat(),
                "expires_in_seconds": int(seconds_remaining),
                "expires_in_hours": round(hours_remaining, 2),
                "status": status
            }

        except Exception as e:
            logger.error(f"[get_token_expiry_status] Failed: {e}", exc_info=True)
            return {
                "is_valid": bool(self.access_token),
                "expires_at": str(self.token_expires_at) if self.token_expires_at else None,
                "expires_in_seconds": -1,
                "expires_in_hours": -1,
                "status": "error"
            }

    def is_token_expired(self) -> bool:
        """
        Check if token is expired.

        Returns:
            True if token is expired or missing
        """
        try:
            status = self.get_token_expiry_status()
            return status["status"] == "expired" or not status["is_valid"]
        except Exception as e:
            logger.error(f"[is_token_expired] Failed: {e}", exc_info=True)
            return False

    def is_token_expiring_soon(self, threshold_hours: int = 1) -> bool:
        """
        Check if token will expire soon.

        Args:
            threshold_hours: Hours threshold for "soon"

        Returns:
            True if token expires within threshold_hours
        """
        try:
            status = self.get_token_expiry_status()
            return status["status"] == "expiring_soon" and 0 < status["expires_in_hours"] < threshold_hours
        except Exception as e:
            logger.error(f"[is_token_expiring_soon] Failed: {e}", exc_info=True)
            return False

    def get_token_info(self) -> Dict[str, Any]:
        """
        Get comprehensive token information.

        Returns:
            Dict with token details
        """
        try:
            expiry_status = self.get_token_expiry_status()

            return {
                "has_token": bool(self.access_token),
                "token_length": len(self.access_token) if self.access_token else 0,
                "has_refresh_token": bool(self.refresh_token),
                "issued_at": self.token_issued_at,
                **expiry_status
            }
        except Exception as e:
            logger.error(f"[get_token_info] Failed: {e}", exc_info=True)
            return {
                "has_token": False,
                "token_length": 0,
                "has_refresh_token": False,
                "issued_at": None,
                "is_valid": False,
                "expires_at": None,
                "expires_in_seconds": 0,
                "expires_in_hours": 0,
                "status": "error"
            }

    def clear_token(self) -> None:
        """Clear the current token from memory and optionally from database."""
        try:
            self.access_token = None
            self.token_issued_at = None
            self.token_expires_at = None
            self.refresh_token = None
            logger.info("Token cleared from memory")
        except Exception as e:
            logger.error(f"[clear_token] Failed: {e}", exc_info=True)

    def revoke_token(self) -> bool:
        """
        Revoke the current token (clear from database).

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            db = get_db()
            success = tokens.clear(db)
            if success:
                self.access_token = None
                self.token_issued_at = None
                self.token_expires_at = None
                self.refresh_token = None
                logger.info("Token revoked and cleared from database")
            else:
                logger.error("Failed to revoke token from database")
            return success
        except Exception as e:
            logger.error(f"[revoke_token] Failed: {e}", exc_info=True)
            return False

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before shutdown."""
        try:
            logger.info("[FyersManualLoginHelper] Starting cleanup")
            self.clear_token()
            logger.info("[FyersManualLoginHelper] Cleanup completed")
        except Exception as e:
            logger.error(f"[FyersManualLoginHelper.cleanup] Error: {e}", exc_info=True)