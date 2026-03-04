"""
brokers/KotakNeoBroker.py
=========================
Kotak Neo (neo_api_client) implementation of BaseBroker.

Prerequisites:
    pip install "git+https://github.com/Kotak-Neo/kotak-neo-api.git#egg=neo_api_client"

Authentication (TOTP + MPIN, no browser OAuth):
    BrokerageSetting fields:
        client_id    → Consumer Key (from Kotak Neo app → Invest → Trade API)
        secret_key   → Consumer Secret
        redirect_uri → TOTP secret (base32) from Kotak Securities TOTP registration

    Credential notes:
        - mobile_number and UCC are needed for TOTP login.
          Store "mobile|UCC" as username in an extended approach, OR
          store them in separate config fields (see below).
        - For simplest setup, the broker asks for MPIN during login.

    Call flow:
        broker.login_totp(mobile="+919999999999", ucc="CLIENT_UCC", mpin="XXXX")
        # This calls totp_login() then totp_validate() and saves the token.

    Note: Kotak Neo does NOT provide historical data via its official API
    (confirmed in GitHub discussions). History calls fall back to None.

API docs: https://github.com/Kotak-Neo/kotak-neo-api
SDK:      pip install "git+https://github.com/Kotak-Neo/kotak-neo-api.git#egg=neo_api_client"

FIXED: Added proper WebSocket cleanup with timeout and state tracking.
"""

import logging
import time
import random
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable

import pandas as pd
from requests.exceptions import Timeout, ConnectionError

from broker.BaseBroker import BaseBroker, TokenExpiredError
from db.connector import get_db
from db.crud import tokens

try:
    from neo_api_client import NeoAPI
    KOTAK_NEO_AVAILABLE = True
except ImportError:
    KOTAK_NEO_AVAILABLE = False

try:
    import pyotp as _pyotp_kotak
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Kotak Neo exchange / product / order constants ────────────────────────────
NEO_EXCHANGE_NSE_EQ = "nse_cm"
NEO_EXCHANGE_NSE_FO = "nse_fo"
NEO_EXCHANGE_BSE_EQ = "bse_cm"

NEO_PRODUCT_MIS  = "MIS"
NEO_PRODUCT_NRML = "NRML"
NEO_PRODUCT_CNC  = "CNC"

NEO_ORDER_MARKET = "MKT"
NEO_ORDER_LIMIT  = "L"
NEO_ORDER_SL     = "SL"
NEO_ORDER_SLM    = "SL-M"

NEO_BUY  = "B"
NEO_SELL = "S"


class KotakNeoBroker(BaseBroker):
    """
    Kotak Neo broker implementation.

    BrokerageSetting fields:
        client_id    → Consumer Key (Trade API card in Neo app)
        secret_key   → Consumer Secret
        redirect_uri → TOTP secret (base32) for auto-TOTP

    Extended setup — store "mobile|UCC" in username field (if available):
        call broker.login_totp(mobile="+91XXXXXXXXXX", ucc="XXXXXXX", mpin="XXXX")

    FIXED: Added proper WebSocket cleanup with timeout and state tracking.
    """

    def __init__(self, state, broker_setting=None):
        self._safe_defaults_init()
        try:
            if not KOTAK_NEO_AVAILABLE:
                raise ImportError(
                    "neo_api_client is not installed.\n"
                    "Run: pip install \"git+https://github.com/Kotak-Neo/kotak-neo-api.git"
                    "#egg=neo_api_client\""
                )
            self.state = state

            if broker_setting is None:
                raise ValueError("BrokerageSetting must be provided for KotakNeoBroker.")

            self.consumer_key    = getattr(broker_setting, 'client_id', None)
            self.consumer_secret = getattr(broker_setting, 'secret_key', None)
            self.totp_secret     = getattr(broker_setting, 'redirect_uri', None)

            if not self.consumer_key:
                raise ValueError("Kotak Neo consumer_key (client_id) is required.")

            # Load any saved access token
            saved_token = self._load_token_from_db()

            # Initialize NeoAPI
            self.client = NeoAPI(
                consumer_key=self.consumer_key,
                consumer_secret=self.consumer_secret or "",
                environment="prod",
                access_token=saved_token,    # restore previous session if available
                neo_fin_key="neotradeapi",
            )

            if saved_token:
                self.state.token = saved_token
                logger.info("KotakNeoBroker: token loaded from DB")
            else:
                logger.warning("KotakNeoBroker: no token found — call broker.login_totp()")

            # WebSocket cleanup tracking
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()
            self._ws_client = None

            logger.info("KotakNeoBroker initialized")

        except Exception as e:
            logger.critical(f"[KotakNeoBroker.__init__] {e}", exc_info=True)
            raise

    @property
    def broker_type(self) -> str:
        return "kitak_neo"

    def _safe_defaults_init(self):
        self.state = None
        self.consumer_key = None
        self.consumer_secret = None
        self.totp_secret = None
        self.client = None
        self._last_request_time = 0
        self._request_count = 0

        # WebSocket cleanup tracking
        self._ws_closed = False
        self._ws_cleanup_event = None
        self._ws_client = None
        self._ws_on_tick = None
        self._ws_on_connect = None
        self._ws_on_close = None
        self._ws_on_error = None

    # ── Authentication ────────────────────────────────────────────────────────

    def login_totp(self, mobile: str, ucc: str, mpin: str,
                   totp: Optional[str] = None) -> bool:
        """
        Authenticate with Kotak Neo using TOTP + MPIN.

        Args:
            mobile: Registered mobile number with country code (e.g. "+919999999999")
            ucc:    Unique Client Code (from Kotak Neo app profile)
            mpin:   4-digit MPIN
            totp:   6-digit TOTP. Auto-generated from totp_secret if None.

        Returns:
            True on success
        """
        try:
            if totp is None and self.totp_secret and PYOTP_AVAILABLE:
                totp = _pyotp_kotak.TOTP(self.totp_secret).now()
            if not totp:
                raise ValueError("TOTP is required. Store TOTP secret in redirect_uri.")

            # Step 1: TOTP login (generates view_token + session_id)
            self.client.totp_login(mobile_number=mobile, ucc=ucc, totp=totp)

            # Step 2: Validate with MPIN (generates trade_token)
            ret = self.client.totp_validate(mpin=mpin)

            if ret:
                # Extract token from response
                access_token = ret.get("data", {}).get("token") or str(ret)
                self.state.token = access_token
                expires_at = (datetime.now() + timedelta(hours=8)).isoformat()
                db = get_db()
                tokens.save_token(access_token, "", expires_at=expires_at, db=db)
                logger.info("KotakNeoBroker: TOTP session generated")
                return True
            else:
                logger.error(f"KotakNeoBroker TOTP validate failed: {ret}")
                return False

        except Exception as e:
            logger.error(f"[KotakNeoBroker.login_totp] {e}", exc_info=True)
            return False

    def login_otp(self, mobile: str, password: str) -> str:
        """
        Initiate OTP-based login. Returns OTP session state.
        Then call complete_login_otp(otp) to finish.
        """
        try:
            self.client.login(mobilenumber=mobile, password=password)
            logger.info("KotakNeoBroker: OTP sent to mobile")
            return "otp_sent"
        except Exception as e:
            logger.error(f"[KotakNeoBroker.login_otp] {e}", exc_info=True)
            return "error"

    def complete_login_otp(self, otp: str) -> bool:
        """Complete OTP login after receiving the OTP."""
        try:
            ret = self.client.session_2fa(OTP=otp)
            if ret:
                access_token = ret.get("data", {}).get("token") or str(ret)
                self.state.token = access_token
                expires_at = (datetime.now() + timedelta(hours=8)).isoformat()
                db = get_db()
                tokens.save_token(access_token, "", expires_at=expires_at, db=db)
                logger.info("KotakNeoBroker: OTP session completed")
                return True
            return False
        except Exception as e:
            logger.error(f"[KotakNeoBroker.complete_login_otp] {e}", exc_info=True)
            return False

    def _load_token_from_db(self) -> Optional[str]:
        try:
            db = get_db()
            token_data = tokens.get(db)
            if token_data and token_data.get("access_token"):
                return token_data["access_token"]
            return None
        except Exception as e:
            logger.error(f"[KotakNeoBroker._load_token_from_db] {e}", exc_info=True)
            return None

    # ── Rate limiting ─────────────────────────────────────────────────────────

    def _check_rate_limit(self):
        current = time.time()
        diff = current - self._last_request_time
        if diff < 1.0:
            self._request_count += 1
            if self._request_count > self.MAX_REQUESTS_PER_SECOND:
                time.sleep(1.0 - diff + 0.1)
                self._request_count = 0
                self._last_request_time = time.time()
        else:
            self._request_count = 1
            self._last_request_time = current

    # ── Symbol helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _exchange_segment(symbol: str) -> str:
        s = symbol.upper()
        if s.startswith("NFO:") or "CE" in s or "PE" in s or "FUT" in s:
            return NEO_EXCHANGE_NSE_FO
        if s.startswith("BSE:"):
            return NEO_EXCHANGE_BSE_EQ
        return NEO_EXCHANGE_NSE_EQ

    @staticmethod
    def _clean_symbol(symbol: str) -> str:
        clean = symbol.split(":")[-1]
        # Kotak Neo typically requires "-EQ" suffix for equities
        if clean.isupper() and not any(x in clean for x in ["FUT","CE","PE"]):
            if not clean.endswith("-EQ"):
                return f"{clean}-EQ"
        return clean

    @staticmethod
    def _to_neo_side(side: int) -> str:
        return NEO_BUY if side == BaseBroker.SIDE_BUY else NEO_SELL

    @staticmethod
    def _is_ok(response: Any) -> bool:
        if isinstance(response, dict):
            stat = response.get("stat", "")
            return stat == "Ok" or response.get("status") == "success"
        return False

    def _check_token_error(self, response: Any):
        if isinstance(response, dict):
            errors = response.get("error", [])
            if isinstance(errors, list):
                for err in errors:
                    if str(err.get("code", "")) in ("10020", "10030"):
                        raise TokenExpiredError(err.get("message", "Auth failed"))
            msg = str(response.get("message", "")).lower()
            if "authentication" in msg or "token" in msg or "session" in msg:
                raise TokenExpiredError(response.get("message", "Auth error"))

    # ── BaseBroker implementation ─────────────────────────────────────────────

    def get_profile(self) -> Optional[Dict]:
        try:
            if not self.client:
                return None
            result = self._call(self.client.limits, context="get_profile")
            return result if self._is_ok(result) else None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[KotakNeoBroker.get_profile] {e!r}", exc_info=True)
            return None

    def get_balance(self, capital_reserve: float = 0.0) -> float:
        try:
            if not self.client:
                return 0.0
            result = self._call(self.client.limits, context="get_balance")
            if self._is_ok(result):
                data = result.get("data", {})
                available = float(data.get("Net", 0.0))
                if capital_reserve > 0:
                    available = available * (1 - capital_reserve / 100)
                return available
            return 0.0
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[KotakNeoBroker.get_balance] {e!r}", exc_info=True)
            return 0.0

    def get_history(self, symbol: str, interval: str = "2", length: int = 400):
        """
        Kotak Neo does not officially support historical data in its API.
        Returns None — users must use an alternative data source.
        """
        logger.warning("KotakNeoBroker: historical data is not supported by Kotak Neo API.")
        return None

    def get_history_for_timeframe(self, symbol: str, interval: str, days: int = 30):
        logger.warning("KotakNeoBroker: historical data is not supported by Kotak Neo API.")
        return None

    def get_option_current_price(self, option_name: str) -> Optional[float]:
        try:
            if not option_name or not self.client:
                return None
            exchange = self._exchange_segment(option_name)
            clean = self._clean_symbol(option_name)
            self._check_rate_limit()
            # Use quotes endpoint
            result = self._call(
                lambda: self.client.quotes(
                    instrument_tokens=[{
                        "instrument_token": clean,
                        "exchange_segment": exchange,
                    }]
                ),
                context="get_option_price"
            )
            if result:
                data = result.get("data", [{}])
                if data:
                    return float(data[0].get("last_traded_price", 0) or 0)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[KotakNeoBroker.get_option_current_price] {e!r}", exc_info=True)
            return None

    def get_option_quote(self, option_name: str) -> Optional[Dict[str, float]]:
        try:
            if not option_name or not self.client:
                return None
            exchange = self._exchange_segment(option_name)
            clean = self._clean_symbol(option_name)
            self._check_rate_limit()
            result = self._call(
                lambda: self.client.quotes(
                    instrument_tokens=[{
                        "instrument_token": clean,
                        "exchange_segment": exchange,
                    }]
                ),
                context="get_option_quote"
            )
            if result:
                data = result.get("data", [{}])
                if data:
                    q = data[0]
                    return {
                        "ltp":    float(q.get("last_traded_price", 0) or 0),
                        "bid":    float(q.get("best_bid_price", 0) or 0),
                        "ask":    float(q.get("best_ask_price", 0) or 0),
                        "high":   float(q.get("high", 0) or 0),
                        "low":    float(q.get("low", 0) or 0),
                        "open":   float(q.get("open", 0) or 0),
                        "close":  float(q.get("close", 0) or 0),
                        "volume": int(q.get("volume", 0) or 0),
                        "oi":     int(q.get("open_interest", 0) or 0),
                    }
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[KotakNeoBroker.get_option_quote] {e!r}", exc_info=True)
            return None

    def get_option_chain_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        out = {}
        for sym in symbols:
            quote = self.get_option_quote(sym)
            if quote:
                out[self._clean_symbol(sym)] = quote
        return out

    def place_order(self, **kwargs) -> Optional[str]:
        try:
            if not self.client:
                return None
            symbol = kwargs.get('symbol')
            qty = kwargs.get('qty', 75)
            side = kwargs.get('side', self.SIDE_BUY)
            order_type = kwargs.get('order_type', self.MARKET_ORDER_TYPE)
            product = kwargs.get('product_type', NEO_PRODUCT_MIS)
            limit_price = str(float(kwargs.get('limitPrice', 0) or 0))
            stop_price  = str(float(kwargs.get('stopPrice', 0) or 0))

            if not symbol or qty <= 0:
                return None

            exchange_seg = self._exchange_segment(symbol)
            clean = self._clean_symbol(symbol)

            neo_order_type = {
                self.MARKET_ORDER_TYPE:          NEO_ORDER_MARKET,
                self.LIMIT_ORDER_TYPE:           NEO_ORDER_LIMIT,
                self.STOPLOSS_MARKET_ORDER_TYPE: NEO_ORDER_SLM,
            }.get(order_type, NEO_ORDER_MARKET)

            self._check_rate_limit()
            result = self._call(
                lambda: self.client.place_order(
                    exchange_segment=exchange_seg,
                    product=product,
                    price=limit_price,
                    order_type=neo_order_type,
                    quantity=str(qty),
                    validity="DAY",
                    trading_symbol=clean,
                    transaction_type=self._to_neo_side(side),
                    amo="NO",
                    disclosed_quantity="0",
                    market_protection="0",
                    pf="N",
                    trigger_price=stop_price,
                    tag=None,
                ),
                context="place_order"
            )
            if result:
                self._check_token_error(result)
                norder_id = result.get("nOrdNo")
                if norder_id:
                    logger.info(f"KotakNeoBroker: order placed {norder_id}")
                    return str(norder_id)
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[KotakNeoBroker.place_order] {e!r}", exc_info=True)
            return None

    def modify_order(self, **kwargs) -> bool:
        try:
            order_id = kwargs.get('order_id')
            limit_price = str(float(kwargs.get('limit_price', 0) or 0))
            qty = str(int(kwargs.get('qty', 0)))
            symbol = kwargs.get('symbol', '')
            if not order_id or not self.client:
                return False
            self._check_rate_limit()
            result = self._call(
                lambda: self.client.modify_order(
                    order_id=order_id,
                    price=limit_price,
                    quantity=qty,
                    exchange_segment=self._exchange_segment(symbol),
                    product=NEO_PRODUCT_MIS,
                    validity="DAY",
                    trading_symbol=self._clean_symbol(symbol),
                    order_type=NEO_ORDER_LIMIT,
                    trigger_price="0",
                    disclosed_quantity="0",
                ),
                context="modify_order"
            )
            return result is not None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[KotakNeoBroker.modify_order] {e!r}", exc_info=True)
            return False

    def cancel_order(self, **kwargs) -> bool:
        try:
            order_id = kwargs.get('order_id')
            if not order_id or not self.client:
                return False
            self._check_rate_limit()
            result = self._call(
                lambda: self.client.cancel_order(order_id=order_id),
                context="cancel_order"
            )
            return result is not None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[KotakNeoBroker.cancel_order] {e!r}", exc_info=True)
            return False

    def exit_position(self, **kwargs) -> bool:
        symbol = kwargs.get('symbol')
        qty = kwargs.get('qty', 0)
        current_side = kwargs.get('side', self.SIDE_BUY)
        exit_side = self.SIDE_SELL if current_side == self.SIDE_BUY else self.SIDE_BUY
        if not symbol or qty <= 0:
            return False
        return self.place_order(symbol=symbol, qty=qty, side=exit_side,
                                order_type=self.MARKET_ORDER_TYPE) is not None

    def add_stoploss(self, **kwargs) -> bool:
        kwargs['order_type'] = self.STOPLOSS_MARKET_ORDER_TYPE
        kwargs.setdefault('side', self.SIDE_SELL)
        return self.place_order(**kwargs) is not None

    def remove_stoploss(self, **kwargs) -> bool:
        return self.cancel_order(**kwargs)

    def sell_at_current(self, **kwargs) -> bool:
        return self.place_order(order_type=self.MARKET_ORDER_TYPE,
                                side=self.SIDE_SELL, **kwargs) is not None

    def get_positions(self) -> List[Dict[str, Any]]:
        try:
            if not self.client:
                return []
            result = self._call(self.client.positions, context="get_positions")
            if result:
                return result.get("data", []) or []
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[KotakNeoBroker.get_positions] {e!r}", exc_info=True)
            return []

    def get_orderbook(self) -> List[Dict[str, Any]]:
        try:
            if not self.client:
                return []
            result = self._call(self.client.order_report, context="get_orderbook")
            if result:
                return result.get("data", []) or []
            return []
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[KotakNeoBroker.get_orderbook] {e!r}", exc_info=True)
            return []

    def get_current_order_status(self, order_id: str) -> Optional[int]:
        """
        Return order status as integer:
        2 = filled, 1 = pending/open, -1 = rejected/cancelled, None = not found
        """
        try:
            orders = self.get_orderbook()
            for order in orders:
                if str(order.get("nOrdNo") or order.get("orderId")) == str(order_id):
                    status_str = str(order.get("orderStatus") or "").upper()
                    if status_str in ("COMPLETE", "FILLED", "EXECUTED"):
                        return 2
                    if status_str in ("REJECTED", "CANCELLED", "CANCELED"):
                        return -1
                    # OPEN, PENDING, TRIGGER_PENDING, etc.
                    return 1
            return None
        except TokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"[KotakNeoBroker.get_current_order_status] {e!r}", exc_info=True)
            return None

    def get_fill_price(self, broker_order_id: str) -> Optional[float]:
        """
        Return the actual average fill price for a completed order.
        Kotak Neo orderbook includes 'avgPrice' for filled orders.
        """
        try:
            if not broker_order_id or not self.client:
                return None
            orders = self.get_orderbook()
            for order in orders:
                if str(order.get("nOrdNo") or order.get("orderId")) == str(broker_order_id):
                    avg = order.get("avgPrice") or order.get("averagePrice")
                    if avg:
                        return float(avg)
            return None
        except Exception as e:
            logger.error(f"[KotakNeoBroker.get_fill_price] {e!r}", exc_info=True)
            return None
    # ── Broker-specific option symbol construction ────────────────────────────

    def build_option_symbol(
        self,
        underlying: str,
        spot_price: float,
        option_type: str,
        weeks_offset: int = 0,
        lookback_strikes: int = 0,
    ) -> Optional[str]:
        """
        KotakNeo option symbol: bare compact core ``NIFTY2531825000CE``.

        Kotak Neo passes the exchange_segment separately in the API request
        payload; the symbol itself is just the NSE compact core without
        any exchange prefix.
        """
        try:
            from Utils.OptionSymbolBuilder import OptionSymbolBuilder
            params = OptionSymbolBuilder.get_option_params(
                underlying=underlying, spot_price=spot_price,
                option_type=option_type, weeks_offset=weeks_offset,
                lookback_strikes=lookback_strikes,
            )
            return self._params_to_symbol(params)
        except Exception as e:
            logger.error(f"[KotakNeoBroker.build_option_symbol] {e}", exc_info=True)
            return None

    def _params_to_symbol(self, params) -> Optional[str]:
        """KotakNeoBroker symbol from OptionParams."""
        if not params:
            return None
        # KotakNeo: bare compact core; exchange_segment added at order time
        return params.compact_core

    def build_option_chain(
        self,
        underlying: str,
        spot_price: float,
        option_type: str,
        weeks_offset: int = 0,
        itm: int = 5,
        otm: int = 5,
    ) -> List[str]:
        """KotakNeo option chain as bare compact core strings."""
        try:
            from Utils.OptionSymbolBuilder import OptionSymbolBuilder
            all_params = OptionSymbolBuilder.get_all_option_params(
                underlying=underlying, spot_price=spot_price,
                option_type=option_type, weeks_offset=weeks_offset,
                itm=itm, otm=otm,
            )
            return [s for s in (self._params_to_symbol(p) for p in all_params) if s]
        except Exception as e:
            logger.error(f"[KotakNeoBroker.build_option_chain] {e}", exc_info=True)
            return []

    def is_connected(self) -> bool:
        try:
            return self.get_profile() is not None
        except TokenExpiredError:
            return False
        except Exception:

            return False

    def cleanup(self) -> None:
        """Clean up resources including WebSocket connection."""
        logger.info("[KotakNeoBroker] Starting cleanup")

        # Mark WebSocket as closed to prevent callbacks
        self._ws_closed = True

        # Clean up WebSocket if it exists
        if self._ws_client is not None:
            try:
                # Try to unsubscribe all with timeout
                self._ws_cleanup_event.clear()

                def _do_cleanup():
                    try:
                        if hasattr(self._ws_client, "un_subscribe_all"):
                            self._ws_client.un_subscribe_all()
                            logger.debug("[KotakNeoBroker] un_subscribe_all called")
                    except Exception as e:
                        logger.warning(f"[KotakNeoBroker] Error unsubscribing: {e}")
                    finally:
                        self._ws_cleanup_event.set()

                # Run cleanup in separate thread with timeout
                cleanup_thread = threading.Thread(target=_do_cleanup, daemon=True)
                cleanup_thread.start()

                # Wait for cleanup with timeout
                if not self._ws_cleanup_event.wait(timeout=2.0):
                    logger.warning("[KotakNeoBroker] WebSocket cleanup timed out")

            except Exception as e:
                logger.error(f"[KotakNeoBroker] Error during WebSocket cleanup: {e}", exc_info=True)
            finally:
                self._ws_client = None

        # Clear callbacks
        self._ws_on_tick = None
        self._ws_on_connect = None
        self._ws_on_close = None
        self._ws_on_error = None

        logger.info("[KotakNeoBroker] Cleanup completed")

    # ── Internal call wrapper ─────────────────────────────────────────────────

    def _call(self, func: Callable, context: str = "",
              max_retries: int = 3, base_delay: int = 1):
        for attempt in range(max_retries):
            try:
                self._check_rate_limit()
                response = func()
                if isinstance(response, dict):
                    self._check_token_error(response)
                return response
            except TokenExpiredError:
                raise
            except (Timeout, ConnectionError) as e:
                delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning(f"[KotakNeo.{context}] Network error, retry {attempt+1}: {e}")
                time.sleep(delay)
            except Exception as e:
                error_str = str(e).lower()
                if "auth" in error_str or "token" in error_str or "session" in error_str:
                    raise TokenExpiredError(str(e))
                logger.error(f"[KotakNeo.{context}] {e!r}", exc_info=True)
                return None
        logger.critical(f"[KotakNeo.{context}] Max retries reached.")
        return None

    # ── WebSocket interface ────────────────────────────────────────────────────

    def create_websocket(self, on_tick, on_connect, on_close, on_error) -> Any:
        """
        Create Kotak Neo WebSocket via neo_api_client.

        NeoAPI has built-in WebSocket support through client.on_message,
        client.subscribe() and client.un_subscribe() methods.

        FIXED: Added state tracking and stored callbacks.
        """
        try:
            if not hasattr(self, 'client') or self.client is None:
                logger.error("KotakNeoBroker.create_websocket: client not initialized — login first")
                return None

            # Reset WebSocket state
            self._ws_closed = False
            self._ws_cleanup_event = threading.Event()

            self._ws_on_tick    = on_tick
            self._ws_on_connect = on_connect
            self._ws_on_close   = on_close
            self._ws_on_error   = on_error
            self._ws_client = self.client

            logger.info("KotakNeoBroker: WebSocket callbacks stored")
            return {"__neo_client__": self.client, "__ws_active__": True}
        except Exception as e:
            logger.error(f"[KotakNeoBroker.create_websocket] {e}", exc_info=True)
            return None

    def ws_connect(self, ws_obj) -> None:
        """
        Start Kotak Neo WebSocket.

        NeoAPI WebSocket is started by calling client.subscribe() which
        internally opens the WebSocket connection. Here we set up the
        message callback and call subscribe() in ws_subscribe().

        FIXED: Added safety checks.
        """
        try:
            if ws_obj is None or self._ws_closed:
                return
            client = ws_obj.get("__neo_client__") if isinstance(ws_obj, dict) else self.client
            if client is None:
                logger.error("KotakNeoBroker.ws_connect: no client")
                return

            # Attach message handler with safety check
            def safe_on_message(msg):
                if not self._ws_closed:
                    self._ws_on_tick(msg)

            client.on_message = safe_on_message
            logger.info("KotakNeoBroker: on_message callback attached")

            if not self._ws_closed and self._ws_on_connect:
                self._ws_on_connect()
        except Exception as e:
            logger.error(f"[KotakNeoBroker.ws_connect] {e}", exc_info=True)

    def ws_subscribe(self, ws_obj, symbols: List[str]) -> None:
        """
        Subscribe to Kotak Neo live feed.

        NeoAPI subscribe() takes instrument_tokens as a list.
        Translates generic symbols to Kotak Neo instrument_token format.
        """
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return
            client = ws_obj.get("__neo_client__") if isinstance(ws_obj, dict) else self.client
            if client is None:
                return

            tokens = []
            for sym in symbols:
                token = self._resolve_neo_token(sym)
                if token:
                    tokens.append(token)

            if not tokens:
                logger.warning("KotakNeoBroker.ws_subscribe: no valid tokens")
                return

            client.subscribe(
                instrument_tokens=tokens,
                isIndex=False,
                isDepth=False,
            )
            logger.info(f"KotakNeoBroker: subscribed {len(tokens)} tokens")
        except Exception as e:
            logger.error(f"[KotakNeoBroker.ws_subscribe] {e}", exc_info=True)

    def ws_unsubscribe(self, ws_obj, symbols: List[str]) -> None:
        """Unsubscribe from Kotak Neo live feed."""
        try:
            if ws_obj is None or not symbols or self._ws_closed:
                return
            client = ws_obj.get("__neo_client__") if isinstance(ws_obj, dict) else self.client
            if client is None:
                return
            tokens = [self._resolve_neo_token(s) for s in symbols]
            tokens = [t for t in tokens if t]
            if tokens:
                client.un_subscribe(instrument_tokens=tokens)
        except Exception as e:
            logger.error(f"[KotakNeoBroker.ws_unsubscribe] {e}", exc_info=True)

    def ws_disconnect(self, ws_obj) -> None:
        """
        Close Kotak Neo WebSocket with timeout protection.

        FIXED: Added timeout and better error handling.
        """
        try:
            if ws_obj is None:
                return

            logger.info("[KotakNeoBroker] Starting WebSocket disconnect")
            self._ws_closed = True

            client = ws_obj.get("__neo_client__") if isinstance(ws_obj, dict) else self.client

            if client and hasattr(client, "un_subscribe_all"):
                # Run unsubscribe in separate thread with timeout
                disconnect_complete = threading.Event()

                def _do_disconnect():
                    try:
                        client.un_subscribe_all()
                        logger.debug("[KotakNeoBroker] un_subscribe_all completed")
                    except Exception as e:
                        logger.warning(f"[KotakNeoBroker] un_subscribe_all error: {e}")
                    finally:
                        disconnect_complete.set()

                disconnect_thread = threading.Thread(target=_do_disconnect, daemon=True)
                disconnect_thread.start()

                # Wait for disconnect with timeout
                if not disconnect_complete.wait(timeout=2.0):
                    logger.warning("[KotakNeoBroker] un_subscribe_all timed out")

            # Clear reference
            if self._ws_client == client:
                self._ws_client = None

            # Call on_close callback
            if self._ws_on_close:
                try:
                    self._ws_on_close("disconnected by user")
                except Exception as e:
                    logger.warning(f"[KotakNeoBroker] Error in close callback: {e}")

            logger.info("[KotakNeoBroker] WebSocket disconnect completed")

        except Exception as e:
            logger.error(f"[KotakNeoBroker.ws_disconnect] {e}", exc_info=True)

    def normalize_tick(self, raw_tick) -> Optional[Dict[str, Any]]:
        """
        Normalize a Kotak Neo live feed tick.

        NeoAPI tick dict fields: token, ltp, ltq, ltt, tbq, tsq,
        open, high, low, close, oi, bq1/bp1/sq1/sp1 (depth).
        """
        try:
            if self._ws_closed:
                return None

            if isinstance(raw_tick, str):
                import json
                raw_tick = json.loads(raw_tick)
            if not isinstance(raw_tick, dict):
                return None

            ltp = raw_tick.get("ltp") or raw_tick.get("LTP")
            if ltp is None:
                return None

            token  = raw_tick.get("tk") or raw_tick.get("token", "")
            symbol = f"NSE:{token}"

            return {
                "symbol":    symbol,
                "ltp":       float(ltp),
                "timestamp": str(raw_tick.get("ltt", "")),
                "bid":       raw_tick.get("bp1"),
                "ask":       raw_tick.get("sp1"),
                "volume":    raw_tick.get("v") or raw_tick.get("tbq"),
                "oi":        raw_tick.get("oi"),
                "open":      raw_tick.get("o") or raw_tick.get("open"),
                "high":      raw_tick.get("h") or raw_tick.get("high"),
                "low":       raw_tick.get("lo") or raw_tick.get("low"),
                "close":     raw_tick.get("c") or raw_tick.get("close"),
            }
        except Exception as e:
            if not self._ws_closed:  # Only log if not during shutdown
                logger.error(f"[KotakNeoBroker.normalize_tick] {e}", exc_info=True)
            return None

    def _load_neo_instruments(self):
        """Load Kotak Neo instrument master from their CDN."""
        try:
            url = "https://kite.kotakneo.com/static/instruments.json"
            self._instruments_df = pd.read_json(url)
            logger.info("KotakNeoBroker: instrument master loaded")
        except Exception as e:
            logger.error(f"KotakNeoBroker: instrument load failed: {e}")

    def _resolve_neo_token(self, symbol: str) -> Optional[str]:
        """Map generic NSE:SYMBOL → Kotak Neo instrument_token."""
        try:
            cache = getattr(self, "_neo_token_cache", {})
            if symbol in cache:
                return cache[symbol]

            # Try to look up from instrument master
            if hasattr(self, '_instruments_df') and self._instruments_df is not None:
                clean = symbol.split(":")[-1].replace("-EQ", "")
                match = self._instruments_df[
                    (self._instruments_df['tradingsymbol'].str.contains(clean)) &
                    (self._instruments_df['exchange'] == 'NSE')
                    ]
                if not match.empty:
                    token = str(match.iloc[0]['instrument_token'])
                    cache[symbol] = token
                    self._neo_token_cache = cache
                    return token

            # Fallback to bare symbol
            bare = symbol.split(":")[-1]
            cache[symbol] = bare
            self._neo_token_cache = cache
            return bare
        except Exception:
            return None