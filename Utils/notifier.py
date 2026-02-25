"""
notifier.py
===========
Telegram Notifier for the Algo Trading Dashboard.

FEATURE 4: Sends non-blocking notifications via Telegram.
"""

import logging
import concurrent.futures
from typing import Optional, Dict, Any

import requests

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class Notifier:
    """
    FEATURE 4: Telegram Notifier with non-blocking sends.

    All sends are submitted to a single-thread executor to avoid blocking.
    """

    def __init__(self, config):
        """
        Initialize Notifier with config.

        Args:
            config: Config object with telegram_bot_token and telegram_chat_id
        """
        # Rule 2: Safe defaults
        self.config = config
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix='Notifier'
        )
        self._enabled = self._is_configured()

        if self._enabled:
            logger.info("Telegram Notifier initialized (enabled)")
        else:
            logger.info("Telegram Notifier initialized (disabled - missing credentials)")

    def _is_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        try:
            if not self.config:
                return False

            token = self.config.get('telegram_bot_token', '')
            chat_id = self.config.get('telegram_chat_id', '')

            return bool(token and chat_id)
        except Exception as e:
            logger.error(f"[Notifier._is_configured] Failed: {e}", exc_info=True)
            return False

    def _send(self, message: str) -> bool:
        """
        Actually send the message (runs in thread pool).

        Args:
            message: Message to send (can include Markdown formatting)

        Returns:
            True if sent successfully
        """
        try:
            if not self._enabled:
                logger.debug("Telegram not configured, skipping notification")
                return False

            token = self.config.get('telegram_bot_token', '')
            chat_id = self.config.get('telegram_chat_id', '')

            url = f'https://api.telegram.org/bot{token}/sendMessage'

            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }

            response = requests.post(
                url,
                json=payload,
                timeout=5
            )

            if response.status_code == 200:
                logger.debug(f"Telegram notification sent: {message[:50]}...")
                return True
            else:
                logger.warning(f"Telegram send failed: {response.status_code} - {response.text}")
                return False

        except requests.Timeout:
            logger.warning("Telegram request timed out")
            return False
        except requests.ConnectionError as e:
            logger.warning(f"Telegram connection error: {e}")
            return False
        except Exception as e:
            logger.warning(f"Telegram send failed: {e}")
            return False

    def notify_entry(self, symbol: str, direction: str, price: float, sl: float, tp: float):
        """
        Send entry notification.

        Args:
            symbol: Option symbol
            direction: 'CALL' or 'PUT'
            price: Entry price
            sl: Stop loss price
            tp: Take profit price
        """
        try:
            emoji = '📈' if direction == 'CALL' else '📉'
            msg = (f'{emoji} *ENTRY* | `{symbol}` {direction}\n'
                   f'💰 Price: ₹{price:.2f}\n'
                   f'🛑 SL: ₹{sl:.2f} | 🎯 TP: ₹{tp:.2f}')

            self._pool.submit(self._send, msg)
            logger.debug(f"Entry notification queued: {symbol} {direction}")

        except Exception as e:
            logger.error(f"[Notifier.notify_entry] Failed: {e}", exc_info=True)

    def notify_exit(self, symbol: str, direction: str, entry_price: float,
                    exit_price: float, pnl: float, reason: str):
        """
        Send exit notification.

        Args:
            symbol: Option symbol
            direction: 'CALL' or 'PUT'
            entry_price: Entry price
            exit_price: Exit price
            pnl: Profit/Loss amount
            reason: Exit reason
        """
        try:
            emoji = '✅' if pnl > 0 else '❌'
            pnl_symbol = '+' if pnl > 0 else ''
            msg = (f'{emoji} *EXIT* | `{symbol}` {direction}\n'
                   f'Entry: ₹{entry_price:.2f} → Exit: ₹{exit_price:.2f}\n'
                   f'P&L: ₹{pnl_symbol}{pnl:.2f} | Reason: {reason}')

            self._pool.submit(self._send, msg)
            logger.debug(f"Exit notification queued: {symbol} P&L={pnl:.2f}")

        except Exception as e:
            logger.error(f"[Notifier.notify_exit] Failed: {e}", exc_info=True)

    def notify_risk_breach(self, reason: str):
        """
        Send risk breach notification.

        Args:
            reason: Risk breach reason
        """
        try:
            msg = f'🚨 *RISK BREACH*\n{reason}\nBot has been stopped.'
            self._pool.submit(self._send, msg)
            logger.debug(f"Risk breach notification queued: {reason}")
        except Exception as e:
            logger.error(f"[Notifier.notify_risk_breach] Failed: {e}", exc_info=True)

    def notify_token_expired(self):
        """Send token expired notification."""
        try:
            msg = '⚠️ *TOKEN EXPIRED*\nFyers session expired. Please re-login.'
            self._pool.submit(self._send, msg)
            logger.debug("Token expired notification queued")
        except Exception as e:
            logger.error(f"[Notifier.notify_token_expired] Failed: {e}", exc_info=True)

    def notify_ws_disconnect(self):
        """Send WebSocket disconnect notification."""
        try:
            msg = '📡 *WS DISCONNECTED*\nAttempting auto-reconnect...'
            self._pool.submit(self._send, msg)
            logger.debug("WS disconnect notification queued")
        except Exception as e:
            logger.error(f"[Notifier.notify_ws_disconnect] Failed: {e}", exc_info=True)

    def notify_ws_reconnected(self):
        """Send WebSocket reconnected notification."""
        try:
            msg = '✅ *WS RECONNECTED*\nWebSocket connection restored.'
            self._pool.submit(self._send, msg)
            logger.debug("WS reconnect notification queued")
        except Exception as e:
            logger.error(f"[Notifier.notify_ws_reconnected] Failed: {e}", exc_info=True)

    def notify_stop_requested(self):
        """Send stop requested notification."""
        try:
            msg = '🛑 *STOP REQUESTED*\nBot is shutting down gracefully...'
            self._pool.submit(self._send, msg)
            logger.debug("Stop request notification queued")
        except Exception as e:
            logger.error(f"[Notifier.notify_stop_requested] Failed: {e}", exc_info=True)

    def notify_shutdown(self, pnl: float = 0.0):
        """
        Send shutdown notification with final P&L.

        Args:
            pnl: Final P&L amount
        """
        try:
            emoji = '✅' if pnl >= 0 else '❌'
            pnl_symbol = '+' if pnl > 0 else ''
            msg = f'{emoji} *BOT SHUTDOWN*\nFinal P&L: ₹{pnl_symbol}{pnl:.2f}'
            self._pool.submit(self._send, msg)
            logger.debug("Shutdown notification queued")
        except Exception as e:
            logger.error(f"[Notifier.notify_shutdown] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources - shutdown thread pool."""
        try:
            logger.info("[Notifier] Starting cleanup")
            self._pool.shutdown(wait=False)
            logger.info("[Notifier] Cleanup completed")
        except Exception as e:
            logger.error(f"[Notifier.cleanup] Error: {e}", exc_info=True)