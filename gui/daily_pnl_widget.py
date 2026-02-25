"""
daily_pnl_widget.py
===================
Daily P&L Widget for the Algo Trading Dashboard.

FEATURE 5: Real-time P&L tracking with progress bar and statistics.
"""

import logging
from datetime import datetime, date

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame
)
from PyQt5.QtGui import QColor

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class DailyPnLWidget(QWidget):
    """
    FEATURE 5: Daily P&L Widget with progress bar and statistics.

    Receives data via pyqtSlot - no direct state polling.
    """

    def __init__(self, config, parent=None):
        """
        Initialize DailyPnLWidget.

        Args:
            config: Config object with daily_target and max_daily_loss
            parent: Parent widget
        """
        super().__init__(parent)

        # Rule 2: Safe defaults
        self.config = config

        # Internal state
        self._realized = 0.0
        self._unrealized = 0.0
        self._trades = 0
        self._winners = 0
        self._max_dd = 0.0
        self._peak = 0.0
        self._last_reset_date = datetime.now().date()

        # Build UI
        self._build_ui()

        # Check for daily reset every minute
        self._reset_timer = QTimer(self)
        self._reset_timer.timeout.connect(self._check_daily_reset)
        self._reset_timer.start(60000)  # 1 minute

        logger.info("DailyPnLWidget initialized")

    def _build_ui(self):
        """Build the widget UI."""
        try:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(6)

            # Main container with border
            self.setStyleSheet("""
                DailyPnLWidget {
                    background: #161b22;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                }
            """)

            # Row 1: Realized and Unrealized P&L
            row1 = QHBoxLayout()
            row1.setContentsMargins(0, 0, 0, 0)

            self._realized_lbl = QLabel('Realized: ₹0.00')
            self._unrealized_lbl = QLabel('Unrealized: ₹0.00')

            for lbl in [self._realized_lbl, self._unrealized_lbl]:
                lbl.setStyleSheet('color: #8b949e; font-size: 11pt; font-weight: bold;')

            row1.addWidget(self._realized_lbl)
            row1.addStretch()
            row1.addWidget(self._unrealized_lbl)
            layout.addLayout(row1)

            # Row 2: Progress bar
            self._pbar = QProgressBar()

            # Get range from config
            max_loss = abs(self.config.get('max_daily_loss', -5000))
            daily_target = self.config.get('daily_target', 5000)

            self._pbar.setRange(int(-max_loss), int(daily_target))
            self._pbar.setValue(0)
            self._pbar.setTextVisible(False)
            self._pbar.setFixedHeight(10)
            self._pbar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #30363d;
                    border-radius: 4px;
                    background: #0d1117;
                }
                QProgressBar::chunk {
                    background: #3fb950;
                    border-radius: 4px;
                }
            """)
            layout.addWidget(self._pbar)

            # Row 3: Trade stats
            self._stats_lbl = QLabel('Trades: 0 | W: 0 | L: 0 | Win%: 0%')
            self._stats_lbl.setStyleSheet('color: #8b949e; font-size: 10pt;')
            layout.addWidget(self._stats_lbl)

            # Row 4: Max drawdown
            self._dd_lbl = QLabel('Max Drawdown: ₹0.00')
            self._dd_lbl.setStyleSheet('color: #f85149; font-size: 10pt;')
            layout.addWidget(self._dd_lbl)

            # Row 5: Daily target/max loss labels
            row5 = QHBoxLayout()

            self._target_lbl = QLabel(f'Target: ₹{daily_target}')
            self._target_lbl.setStyleSheet('color: #3fb950; font-size: 9pt;')

            self._max_loss_lbl = QLabel(f'Max Loss: ₹{-max_loss}')
            self._max_loss_lbl.setStyleSheet('color: #f85149; font-size: 9pt;')

            row5.addWidget(self._target_lbl)
            row5.addStretch()
            row5.addWidget(self._max_loss_lbl)
            layout.addLayout(row5)

        except Exception as e:
            logger.error(f"[DailyPnLWidget._build_ui] Failed: {e}", exc_info=True)

    @pyqtSlot(float, bool)
    def on_trade_closed(self, pnl: float, is_winner: bool):
        """
        Handle trade closed signal.

        Args:
            pnl: Profit/Loss amount
            is_winner: True if profitable trade
        """
        try:
            self._realized += pnl
            self._unrealized = 0.0  # Reset unrealized after trade closed
            self._trades += 1

            if is_winner:
                self._winners += 1

            # Track max drawdown
            if self._realized < self._max_dd:
                self._max_dd = self._realized

            # Track peak
            if self._realized > self._peak:
                self._peak = self._realized

            self._refresh_ui()
            logger.debug(f"Trade closed - P&L: ₹{pnl:.2f}, Winner: {is_winner}")

        except Exception as e:
            logger.error(f"[DailyPnLWidget.on_trade_closed] Failed: {e}", exc_info=True)

    @pyqtSlot(float)
    def on_unrealized_update(self, pnl: float):
        """
        Handle unrealized P&L update.

        Args:
            pnl: Unrealized P&L amount
        """
        try:
            self._unrealized = pnl
            self._refresh_ui()
        except Exception as e:
            logger.error(f"[DailyPnLWidget.on_unrealized_update] Failed: {e}", exc_info=True)

    def _refresh_ui(self):
        """Refresh all UI elements with current state."""
        try:
            # Realized label
            color = '#3fb950' if self._realized >= 0 else '#f85149'
            self._realized_lbl.setText(f'Realized: ₹{self._realized:,.2f}')
            self._realized_lbl.setStyleSheet(
                f'color: {color}; font-size: 11pt; font-weight: bold;'
            )

            # Unrealized label
            ucolor = '#3fb950' if self._unrealized >= 0 else '#f85149'
            self._unrealized_lbl.setText(f'Unrealized: ₹{self._unrealized:,.2f}')
            self._unrealized_lbl.setStyleSheet(
                f'color: {ucolor}; font-size: 11pt;'
            )

            # Total P&L for progress bar (realized only)
            total_pnl = self._realized

            # Progress bar
            self._pbar.setValue(int(total_pnl))

            # Set progress bar color based on P&L
            if total_pnl >= 0:
                bar_color = '#3fb950'  # Green
            else:
                bar_color = '#f85149'  # Red

            self._pbar.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid #30363d;
                    border-radius: 4px;
                    background: #0d1117;
                }}
                QProgressBar::chunk {{
                    background: {bar_color};
                    border-radius: 4px;
                }}
            """)

            # Stats
            losses = self._trades - self._winners
            win_pct = (self._winners / self._trades * 100) if self._trades > 0 else 0
            self._stats_lbl.setText(
                f'Trades: {self._trades} | W: {self._winners} | L: {losses} | Win%: {win_pct:.0f}%'
            )

            # Drawdown
            self._dd_lbl.setText(f'Max Drawdown: ₹{self._max_dd:,.2f}')

        except Exception as e:
            logger.error(f"[DailyPnLWidget._refresh_ui] Failed: {e}", exc_info=True)

    def _check_daily_reset(self):
        """Check if we need to reset for a new day."""
        try:
            today = datetime.now().date()
            now_time = datetime.now().time()

            # Reset at 09:15 each day (market open)
            if today != self._last_reset_date and now_time.hour == 9 and now_time.minute >= 15:
                logger.info("Daily reset triggered for P&L widget")
                self.reset()
                self._last_reset_date = today

        except Exception as e:
            logger.error(f"[DailyPnLWidget._check_daily_reset] Failed: {e}", exc_info=True)

    def reset(self):
        """Reset all statistics (called at daily reset)."""
        try:
            self._realized = 0.0
            self._unrealized = 0.0
            self._trades = 0
            self._winners = 0
            self._max_dd = 0.0
            self._peak = 0.0
            self._refresh_ui()
            logger.info("DailyPnLWidget reset")

        except Exception as e:
            logger.error(f"[DailyPnLWidget.reset] Failed: {e}", exc_info=True)

    def update_config(self):
        """Update config values (called when settings change)."""
        try:
            max_loss = abs(self.config.get('max_daily_loss', -5000))
            daily_target = self.config.get('daily_target', 5000)

            self._pbar.setRange(int(-max_loss), int(daily_target))
            self._target_lbl.setText(f'Target: ₹{daily_target}')
            self._max_loss_lbl.setText(f'Max Loss: ₹{-max_loss}')

            self._refresh_ui()
            logger.debug("DailyPnLWidget config updated")

        except Exception as e:
            logger.error(f"[DailyPnLWidget.update_config] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources."""
        try:
            logger.info("[DailyPnLWidget] Starting cleanup")
            self._reset_timer.stop()
            logger.info("[DailyPnLWidget] Cleanup completed")
        except Exception as e:
            logger.error(f"[DailyPnLWidget.cleanup] Error: {e}", exc_info=True)