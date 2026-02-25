"""
FyersManualLoginHelper_db.py
=============================
Database-backed Fyers manual login helper using the SQLite database for token storage.
"""

import logging
import urllib.parse
from typing import Optional

from fyers_apiv3 import fyersModel

from db.connector import get_db
from db.crud import tokens

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class FyersManualLoginHelper:
    """
    Fyers manual login helper using database for token storage.
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

            # Load token from database
            self._load_token()

            logger.debug("FyersManualLoginHelper (database) initialized")

        except Exception as e:
            logger.critical(f"[FyersManualLoginHelper.__init__] Failed: {e}", exc_info=True)
            self.client_id = client_id or ""
            self.secret_key = secret_key or ""
            self.redirect_uri = redirect_uri or ""
            self.access_token = None

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.client_id = ""
        self.secret_key = ""
        self.redirect_uri = ""
        self.access_token = None

    def _load_token(self) -> None:
        """
        Load token from database.
        """
        try:
            db = get_db()
            token_data = tokens.get(db)

            if token_data and token_data.get("access_token"):
                self.access_token = token_data["access_token"]
                logger.debug(f"Token loaded from database (length: {len(self.access_token)})")
            else:
                logger.debug("No token found in database")

        except Exception as e:
            logger.error(f"Error loading token from database: {e}", exc_info=True)
            self.access_token = None

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

                    # Save token to database
                    try:
                        db = get_db()
                        issued_at = response.get("issued_at")
                        expires_at = response.get("expires_at")

                        success = tokens.save_token(
                            access_token=self.access_token,
                            refresh_token=response.get("refresh_token", ""),
                            issued_at=issued_at,
                            expires_at=expires_at,
                            db=db
                        )

                        if success:
                            logger.info("Token received and saved to database successfully")
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
            return bool(self.access_token and len(self.access_token) > 50)
        except Exception as e:
            logger.error(f"[is_authenticated] Failed: {e}", exc_info=True)
            return False

    def clear_token(self) -> None:
        """Clear the current token from memory and optionally from database."""
        try:
            self.access_token = None
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