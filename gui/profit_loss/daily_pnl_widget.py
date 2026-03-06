"""
daily_pnl_widget.py
===================
Daily P&L Widget for the Algo Trading Dashboard.

FEATURE 5: Real-time P&L tracking with progress bar and statistics.
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

import logging
from datetime import datetime, date
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame
)
from PyQt5.QtGui import QColor

from Utils.safe_getattr import safe_hasattr
# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class ThemedMixin:
    """Mixin class to provide theme token shortcuts."""

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing


class DailyPnLWidget(QWidget, ThemedMixin):
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
        # Rule 2: Safe defaults
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

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

            # Apply theme initially
            self.apply_theme()

            # Check for daily reset every minute
            self._reset_timer = QTimer(self)
            self._reset_timer.timeout.connect(self._check_daily_reset)
            self._reset_timer.start(60000)  # 1 minute

            logger.info("[DailyPnLWidget.__init__] Initialized successfully")

        except Exception as e:
            logger.critical(f"[DailyPnLWidget.__init__] Failed: {e}", exc_info=True)
            # Ensure we still call super().__init__ even if construction fails
            if not safe_hasattr(self, '_is_initialized'):
                super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        try:
            self._is_initialized = False
            self.config = None
            self._realized = 0.0
            self._unrealized = 0.0
            self._trades = 0
            self._winners = 0
            self._max_dd = 0.0
            self._peak = 0.0
            self._last_reset_date = None
            self._reset_timer = None
            self._realized_lbl = None
            self._unrealized_lbl = None
            self._pbar = None
            self._stats_lbl = None
            self._dd_lbl = None
            self._target_lbl = None
            self._max_loss_lbl = None
            self._main_layout = None
            self._row1_layout = None
            self._row5_layout = None
            self._closing = False
        except Exception as e:
            logger.error(f"[DailyPnLWidget._safe_defaults_init] Failed: {e}", exc_info=True)

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the widget.
        Called on theme change, density change, and initial render.
        """
        try:
            # Skip if closing
            if self._closing:
                return

            c = self._c
            ty = self._ty
            sp = self._sp

            # Update main container stylesheet using theme_manager helpers
            self.setStyleSheet(f"""
                DailyPnLWidget {{
                    background: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                }}
            """)

            # Update layout margins and spacing
            if self._main_layout:
                self._main_layout.setContentsMargins(
                    sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM
                )
                self._main_layout.setSpacing(sp.GAP_XS)

            # Update row layouts
            if self._row1_layout:
                self._row1_layout.setSpacing(sp.GAP_MD)

            if self._row5_layout:
                self._row5_layout.setSpacing(sp.GAP_MD)

            # Progress bar height
            if self._pbar:
                self._pbar.setFixedHeight(sp.PROGRESS_MD)

            # Refresh UI with current values and new theme
            self._refresh_ui()

            logger.debug("[DailyPnLWidget.apply_theme] Applied theme")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[DailyPnLWidget.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[DailyPnLWidget.apply_theme] Failed: {e}", exc_info=True)

    def _build_ui(self):
        """Build the widget UI."""
        try:
            self._main_layout = QVBoxLayout(self)
            # Margins and spacing will be set in apply_theme

            # Row 1: Realized and Unrealized P&L
            self._row1_layout = QHBoxLayout()
            self._row1_layout.setContentsMargins(0, 0, 0, 0)
            # Spacing will be set in apply_theme

            self._realized_lbl = QLabel('Realized: ₹0.00')
            self._realized_lbl.setToolTip("Realized profit/loss from closed trades")

            self._unrealized_lbl = QLabel('Unrealized: ₹0.00')
            self._unrealized_lbl.setToolTip("Current unrealized profit/loss on open position")

            self._row1_layout.addWidget(self._realized_lbl)
            self._row1_layout.addStretch()
            self._row1_layout.addWidget(self._unrealized_lbl)
            self._main_layout.addLayout(self._row1_layout)

            # Row 2: Progress bar
            self._pbar = QProgressBar()
            self._pbar.setToolTip("Daily P&L progress toward target / max loss")

            # Get range from config with validation
            max_loss = self._get_max_loss()
            daily_target = self._get_daily_target()

            self._pbar.setRange(int(-max_loss), int(daily_target))
            self._pbar.setValue(0)
            self._pbar.setTextVisible(False)
            # Height will be set in apply_theme
            self._main_layout.addWidget(self._pbar)

            # Row 3: Trade stats
            self._stats_lbl = QLabel('Trades: 0 | W: 0 | L: 0 | Win%: 0%')
            self._stats_lbl.setToolTip("Trade statistics: Total, Winners, Losers, Win Percentage")
            self._main_layout.addWidget(self._stats_lbl)

            # Row 4: Max drawdown
            self._dd_lbl = QLabel('Max Drawdown: ₹0.00')
            self._dd_lbl.setToolTip("Maximum drawdown from peak for the day")
            self._main_layout.addWidget(self._dd_lbl)

            # Row 5: Daily target/max loss labels
            self._row5_layout = QHBoxLayout()
            # Spacing will be set in apply_theme

            self._target_lbl = QLabel(f'Target: ₹{daily_target}')
            self._target_lbl.setToolTip("Daily profit target")

            self._max_loss_lbl = QLabel(f'Max Loss: ₹{-max_loss}')
            self._max_loss_lbl.setToolTip("Maximum allowed daily loss")

            self._row5_layout.addWidget(self._target_lbl)
            self._row5_layout.addStretch()
            self._row5_layout.addWidget(self._max_loss_lbl)
            self._main_layout.addLayout(self._row5_layout)

        except Exception as e:
            logger.error(f"[DailyPnLWidget._build_ui] Failed: {e}", exc_info=True)

    def _get_max_loss(self) -> float:
        """Safely get max loss from config."""
        try:
            if self.config is None:
                return 5000.0
            # Rule 6: Input validation
            value = self.config.get('max_daily_loss', 5000.0)
            return abs(float(value)) if value is not None else 5000.0
        except (TypeError, ValueError) as e:
            logger.warning(f"[DailyPnLWidget._get_max_loss] Invalid config value: {e}")
            return 5000.0
        except Exception as e:
            logger.error(f"[DailyPnLWidget._get_max_loss] Failed: {e}", exc_info=True)
            return 5000.0

    def _get_daily_target(self) -> float:
        """Safely get daily target from config."""
        try:
            if self.config is None:
                return 5000.0
            # Rule 6: Input validation
            value = self.config.get('daily_target', 5000.0)
            return abs(float(value)) if value is not None else 5000.0
        except (TypeError, ValueError) as e:
            logger.warning(f"[DailyPnLWidget._get_daily_target] Invalid config value: {e}")
            return 5000.0
        except Exception as e:
            logger.error(f"[DailyPnLWidget._get_daily_target] Failed: {e}", exc_info=True)
            return 5000.0

    @pyqtSlot(float, bool)
    def on_trade_closed(self, pnl: float, is_winner: bool):
        """
        Handle trade closed signal.

        Args:
            pnl: Profit/Loss amount
            is_winner: True if profitable trade
        """
        try:
            # Rule 6: Input validation
            pnl = float(pnl) if pnl is not None else 0.0
            is_winner = bool(is_winner) if is_winner is not None else False

            # Clamp pnl to reasonable range
            pnl = max(-1000000.0, min(1000000.0, pnl))

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
            logger.debug(f"[DailyPnLWidget.on_trade_closed] Trade closed - P&L: ₹{pnl:.2f}, Winner: {is_winner}")

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
            # Rule 6: Input validation
            pnl = float(pnl) if pnl is not None else 0.0

            # Clamp pnl to reasonable range
            pnl = max(-1000000.0, min(1000000.0, pnl))

            self._unrealized = pnl
            self._refresh_ui()
        except Exception as e:
            logger.error(f"[DailyPnLWidget.on_unrealized_update] Failed: {e}", exc_info=True)

    def _refresh_ui(self):
        """Refresh all UI elements with current state."""
        try:
            # Skip if closing or widgets not initialized
            if self._closing:
                return

            c = self._c
            ty = self._ty
            sp = self._sp

            # Realized label
            if self._realized_lbl:
                color = c.GREEN if self._realized >= 0 else c.RED
                self._realized_lbl.setText(f'Realized: ₹{self._realized:,.2f}')
                self._realized_lbl.setStyleSheet(
                    f'color: {color}; font-size: {ty.SIZE_LG}pt; font-weight: {ty.WEIGHT_BOLD}; background: transparent;'
                )

            # Unrealized label
            if self._unrealized_lbl:
                ucolor = c.GREEN if self._unrealized >= 0 else c.RED
                self._unrealized_lbl.setText(f'Unrealized: ₹{self._unrealized:,.2f}')
                self._unrealized_lbl.setStyleSheet(
                    f'color: {ucolor}; font-size: {ty.SIZE_LG}pt; background: transparent;'
                )

            # Total P&L for progress bar (realized only)
            total_pnl = self._realized

            # Progress bar
            if self._pbar:
                self._pbar.setValue(int(total_pnl))

                # Set progress bar color based on P&L
                bar_color = c.GREEN if total_pnl >= 0 else c.RED

                self._pbar.setStyleSheet(f"""
                    QProgressBar {{
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_SM}px;
                        background: {c.BG_MAIN};
                    }}
                    QProgressBar::chunk {{
                        background: {bar_color};
                        border-radius: {sp.RADIUS_SM}px;
                    }}
                """)

            # Stats
            if self._stats_lbl:
                losses = self._trades - self._winners
                win_pct = (self._winners / self._trades * 100) if self._trades > 0 else 0
                self._stats_lbl.setText(
                    f'Trades: {self._trades} | W: {self._winners} | L: {losses} | Win%: {win_pct:.0f}%'
                )
                self._stats_lbl.setStyleSheet(
                    f'color: {c.TEXT_DIM}; font-size: {ty.SIZE_BODY}pt; background: transparent;'
                )

            # Drawdown
            if self._dd_lbl:
                self._dd_lbl.setText(f'Max Drawdown: ₹{self._max_dd:,.2f}')
                self._dd_lbl.setStyleSheet(
                    f'color: {c.RED}; font-size: {ty.SIZE_BODY}pt; background: transparent;'
                )

            # Target and max loss labels
            if self._target_lbl and self._max_loss_lbl:
                max_loss = self._get_max_loss()
                daily_target = self._get_daily_target()

                self._target_lbl.setText(f'Target: ₹{daily_target}')
                self._target_lbl.setStyleSheet(
                    f'color: {c.GREEN}; font-size: {ty.SIZE_XS}pt; background: transparent;'
                )

                self._max_loss_lbl.setText(f'Max Loss: ₹{-max_loss}')
                self._max_loss_lbl.setStyleSheet(
                    f'color: {c.RED}; font-size: {ty.SIZE_XS}pt; background: transparent;'
                )

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[DailyPnLWidget._refresh_ui] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[DailyPnLWidget._refresh_ui] Failed: {e}", exc_info=True)

    def _check_daily_reset(self):
        """Check if we need to reset for a new day."""
        try:
            # Skip if closing
            if self._closing:
                return

            today = datetime.now().date()
            now_time = datetime.now().time()

            # Reset at 09:15 each day (market open)
            if today != self._last_reset_date and now_time.hour == 9 and now_time.minute >= 15:
                logger.info("[DailyPnLWidget._check_daily_reset] Daily reset triggered")
                self.reset()
                self._last_reset_date = today

        except Exception as e:
            logger.error(f"[DailyPnLWidget._check_daily_reset] Failed: {e}", exc_info=True)

    def reset(self):
        """Reset all statistics (called at daily reset)."""
        try:
            # Skip if closing
            if self._closing:
                return

            self._realized = 0.0
            self._unrealized = 0.0
            self._trades = 0
            self._winners = 0
            self._max_dd = 0.0
            self._peak = 0.0
            self._refresh_ui()
            logger.info("[DailyPnLWidget.reset] Reset completed")

        except Exception as e:
            logger.error(f"[DailyPnLWidget.reset] Failed: {e}", exc_info=True)

    def update_config(self):
        """Update config values (called when settings change)."""
        try:
            # Skip if closing
            if self._closing:
                return

            max_loss = self._get_max_loss()
            daily_target = self._get_daily_target()

            if self._pbar:
                self._pbar.setRange(int(-max_loss), int(daily_target))
            self._refresh_ui()
            logger.debug("[DailyPnLWidget.update_config] Config updated")

        except Exception as e:
            logger.error(f"[DailyPnLWidget.update_config] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources."""
        try:
            # Prevent multiple cleanups
            if self._closing:
                return

            logger.info("[DailyPnLWidget.cleanup] Starting cleanup")
            self._closing = True

            # Stop timer
            if self._reset_timer is not None:
                try:
                    self._reset_timer.stop()
                    self._reset_timer.timeout.disconnect(self._check_daily_reset)
                except Exception as e:
                    logger.warning(f"[DailyPnLWidget.cleanup] Timer stop error: {e}")
                self._reset_timer = None

            # Nullify widget references
            self._realized_lbl = None
            self._unrealized_lbl = None
            self._pbar = None
            self._stats_lbl = None
            self._dd_lbl = None
            self._target_lbl = None
            self._max_loss_lbl = None
            self._main_layout = None
            self._row1_layout = None
            self._row5_layout = None

            # Disconnect signals
            try:
                theme_manager.theme_changed.disconnect(self.apply_theme)
                theme_manager.density_changed.disconnect(self.apply_theme)
            except (TypeError, RuntimeError):
                pass  # Already disconnected or not connected

            logger.info("[DailyPnLWidget.cleanup] Cleanup completed")

        except Exception as e:
            logger.error(f"[DailyPnLWidget.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event with cleanup."""
        try:
            self.cleanup()
            super().closeEvent(event)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[DailyPnLWidget.closeEvent] RuntimeError: {e}", exc_info=True)
            # Ensure event is accepted even on error
            event.accept()
        except Exception as e:
            logger.error(f"[DailyPnLWidget.closeEvent] Failed: {e}", exc_info=True)
            event.accept()