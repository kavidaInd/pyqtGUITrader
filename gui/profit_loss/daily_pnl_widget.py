"""
daily_pnl_widget.py
===================
Daily P&L Widget — redesigned with a professional card-based layout.

Layout (horizontal, fills the full-width strip between chart and status bar):

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  📈 REALIZED          📊 UNREALIZED       ⚡ TOTAL        [====▓▓   ]  │
  │  ₹12,450.00           ₹-320.00            ₹12,130.00      24/50 target │
  │  ─────────────────────────────────────────────────────────────────────  │
  │  Trades: 14 │ W: 10  L: 4  │ Win%: 71%  │ MaxDD: ₹-1,200  │ Peak: ₹14K│
  └─────────────────────────────────────────────────────────────────────────┘

Features:
  • Three primary metric cards (Realized / Unrealized / Total) with color coding
  • Horizontal progress bar that shows position relative to target & max loss
  • Compact stats strip with win-rate badge and drawdown
  • All tokens from theme_manager — zero hardcoded colors
  • Responds to theme_changed and density_changed signals
"""

import logging
from datetime import datetime, date

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame, QSizePolicy
)

from Utils.safe_getattr import safe_hasattr
from data.trade_state_manager import state_manager
from db.crud import kv, orders
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Small building-block: single metric card
# ─────────────────────────────────────────────────────────────────────────────

class _MetricCard(QFrame):
    """
    Single P&L metric card.

    Layout (vertical):
        LABEL (dim, uppercase, tiny)
        VALUE (large, bold, colored)
    """

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label_text = label
        self._value_text = "₹0.00"
        self._positive = True

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)

        self._lbl = QLabel(label.upper())
        self._lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._val = QLabel("₹0.00")
        self._val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._val.setMinimumWidth(110)

        lay.addWidget(self._lbl)
        lay.addWidget(self._val)

        theme_manager.theme_changed.connect(self._apply_theme)
        theme_manager.density_changed.connect(self._apply_theme)
        self._apply_theme()

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def _apply_theme(self, _=None):
        try:
            c, ty, sp = self._c, self._ty, self._sp
            lay = self.layout()
            if lay:
                lay.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM)
                lay.setSpacing(sp.GAP_XS)

            self.setStyleSheet(f"""
                QFrame {{
                    background: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                }}
                QFrame:hover {{
                    border-color: {c.BORDER_STRONG};
                }}
            """)

            self._lbl.setStyleSheet(
                f"color: {c.TEXT_DISABLED}; font-size: {ty.SIZE_XS}pt; "
                f"font-weight: {ty.WEIGHT_BOLD}; letter-spacing: 0.6px; "
                f"background: transparent; border: none;"
            )

            value_color = c.GREEN_BRIGHT if self._positive else c.RED_BRIGHT
            self._val.setStyleSheet(
                f"color: {value_color}; font-size: {ty.SIZE_2XL}pt; "
                f"font-weight: {ty.WEIGHT_HEAVY}; "
                f"font-family: {ty.FONT_NUMERIC}; "
                f"background: transparent; border: none;"
            )
        except Exception as e:
            logger.debug(f"[_MetricCard._apply_theme] {e}")

    def set_value(self, text: str, positive: bool = True):
        self._value_text = text
        self._positive = positive
        self._val.setText(text)
        try:
            c, ty = self._c, self._ty
            value_color = c.GREEN_BRIGHT if positive else c.RED_BRIGHT
            self._val.setStyleSheet(
                f"color: {value_color}; font-size: {ty.SIZE_2XL}pt; "
                f"font-weight: {ty.WEIGHT_HEAVY}; "
                f"font-family: {ty.FONT_NUMERIC}; "
                f"background: transparent; border: none;"
            )
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# _PnLProgressBar — custom dual-color progress bar
# ─────────────────────────────────────────────────────────────────────────────

class _PnLProgressBar(QWidget):
    """
    Visual progress bar showing current P&L between max loss (left) and target (right).

    Segments:
      [  red zone  |  neutral  |  green zone  ]
                   ^           ^
               max_loss        target

    The fill position shows current P&L relative to [−max_loss … +target] range.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = 0.0
        self._target = 5000.0
        self._max_loss = 5000.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setMinimumHeight(8)
        self._bar.setMaximumHeight(12)

        self._labels_row = QWidget()
        lr = QHBoxLayout(self._labels_row)
        lr.setContentsMargins(0, 0, 0, 0)
        lr.setSpacing(0)

        self._loss_lbl = QLabel()
        self._target_lbl = QLabel()
        self._pct_lbl = QLabel()

        lr.addWidget(self._loss_lbl)
        lr.addStretch()
        lr.addWidget(self._pct_lbl)
        lr.addStretch()
        lr.addWidget(self._target_lbl)

        lay.addWidget(self._bar)
        lay.addWidget(self._labels_row)

        theme_manager.theme_changed.connect(self._apply_theme)
        theme_manager.density_changed.connect(self._apply_theme)
        self._apply_theme()

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def _apply_theme(self, _=None):
        try:
            c, ty, sp = self._c, self._ty, self._sp
            self._bar.setMinimumHeight(sp.PROGRESS_MD)
            self._bar.setMaximumHeight(sp.PROGRESS_LG)
            self._update_bar_style()

            dim_style = (
                f"color: {c.TEXT_DISABLED}; font-size: {ty.SIZE_XS}pt; "
                f"background: transparent; border: none;"
            )
            self._loss_lbl.setStyleSheet(dim_style)
            self._target_lbl.setStyleSheet(dim_style)
            self._pct_lbl.setStyleSheet(
                f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; "
                f"font-weight: {ty.WEIGHT_BOLD}; background: transparent; border: none;"
            )
        except Exception as e:
            logger.debug(f"[_PnLProgressBar._apply_theme] {e}")

    def _update_bar_style(self):
        try:
            c, sp = self._c, self._sp
            positive = self._current >= 0
            chunk_color = c.GREEN if positive else c.RED
            bg_color = c.GREEN + "22" if positive else c.RED + "22"
            self._bar.setStyleSheet(f"""
                QProgressBar {{
                    border: none;
                    border-radius: {sp.RADIUS_SM}px;
                    background: {c.BG_MAIN};
                }}
                QProgressBar::chunk {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {chunk_color}88,
                        stop:1 {chunk_color}
                    );
                    border-radius: {sp.RADIUS_SM}px;
                }}
            """)
        except Exception:
            pass

    def set_values(self, current: float, target: float, max_loss: float):
        self._current = current
        self._target = max(1.0, target)
        self._max_loss = max(1.0, max_loss)

        # Map current into a 0–100 range
        total_range = self._target + self._max_loss
        offset = self._current + self._max_loss  # shift so 0 = at max_loss
        pct = max(0, min(100, int(offset / total_range * 100)))

        self._bar.setRange(0, 100)
        self._bar.setValue(pct)
        self._update_bar_style()

        self._loss_lbl.setText(f"−₹{max_loss:,.0f}")
        self._target_lbl.setText(f"+₹{target:,.0f}")

        if current >= 0:
            self._pct_lbl.setText(f"{int(current / target * 100)}% of target" if target else "")
        else:
            self._pct_lbl.setText(f"{int(abs(current) / max_loss * 100)}% of max loss" if max_loss else "")


# ─────────────────────────────────────────────────────────────────────────────
# DailyPnLWidget — main widget
# ─────────────────────────────────────────────────────────────────────────────

class DailyPnLWidget(QWidget):
    """
    Professional Daily P&L strip widget.

    Placed below the chart, above the app status bar.
    Uses a fully token-driven design that re-skins on theme changes.
    """

    def __init__(self, config, daily_setting=None, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.config = config
            self.daily_setting = daily_setting
            self._state = state_manager.get_state()

            self._realized = 0.0
            self._unrealized = 0.0
            self._trades = 0
            self._winners = 0
            self._max_dd = 0.0
            self._peak = 0.0
            self._last_reset_date = self._get_last_reset_date()

            self._load_daily_data()
            self._build_ui()
            self.apply_theme()

            self._reset_timer = QTimer(self)
            self._reset_timer.timeout.connect(self._check_daily_reset)
            self._reset_timer.start(60000)

            # Fallback-only timer: TradingGUI.timer_fast (1 s) already drives
            # unrealized updates via the on_unrealized_update() slot.  This timer
            # runs at 5 s purely as a safety-net (e.g. when the widget is used
            # without a connected TradingGUI) and must NOT run at 1 s or it will
            # race with on_trade_closed() which resets _unrealized to 0.
            self._update_timer = QTimer(self)
            self._update_timer.timeout.connect(self._update_unrealized)
            self._update_timer.start(5000)

            logger.info("[DailyPnLWidget] Initialized")

        except Exception as e:
            logger.critical(f"[DailyPnLWidget.__init__] Failed: {e}", exc_info=True)
            if not safe_hasattr(self, '_is_initialized'):
                super().__init__(parent)

    # ── Safe defaults ─────────────────────────────────────────────────────────

    def _safe_defaults_init(self):
        try:
            self._is_initialized = False
            self.config = None
            self.daily_setting = None
            self._state = None
            self._realized = 0.0
            self._unrealized = 0.0
            self._trades = 0
            self._winners = 0
            self._max_dd = 0.0
            self._peak = 0.0
            self._last_reset_date = None
            self._reset_timer = None
            self._update_timer = None
            self._closing = False
            # UI refs
            self._card_realized = None
            self._card_unrealized = None
            self._card_total = None
            self._pnl_bar = None
            self._stats_row = None
            self._trades_lbl = None
            self._win_lbl = None
            self._loss_lbl = None
            self._winpct_lbl = None
            self._dd_lbl = None
            self._peak_lbl = None
            self._main_layout = None
        except Exception as e:
            logger.error(f"[DailyPnLWidget._safe_defaults_init] {e}")

    # ── Theme shortcuts ───────────────────────────────────────────────────────

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        try:
            sp = self._sp

            self._main_layout = QVBoxLayout(self)
            self._main_layout.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_XS)
            self._main_layout.setSpacing(sp.GAP_SM)

            # ── Row 1: three metric cards + progress bar ────────────────────
            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.setSpacing(sp.GAP_MD)

            self._card_realized = _MetricCard("Realized")
            self._card_unrealized = _MetricCard("Unrealized")
            self._card_total = _MetricCard("Total P&L")

            for card in (self._card_realized, self._card_unrealized, self._card_total):
                card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

            self._pnl_bar = _PnLProgressBar()
            self._pnl_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self._pnl_bar.setMinimumWidth(140)

            top_row.addWidget(self._card_realized, 3)
            top_row.addWidget(self._card_unrealized, 3)
            top_row.addWidget(self._card_total, 3)

            # Thin vertical separator
            sep = QFrame()
            sep.setFrameShape(QFrame.VLine)
            sep.setFixedWidth(1)
            top_row.addWidget(sep)

            top_row.addWidget(self._pnl_bar, 4)

            self._main_layout.addLayout(top_row)

            # ── Row 2: compact stats strip ──────────────────────────────────
            self._stats_row = QHBoxLayout()
            self._stats_row.setContentsMargins(0, 0, 0, 0)
            self._stats_row.setSpacing(sp.GAP_MD)

            self._trades_lbl = QLabel("Trades: 0")
            self._win_lbl = QLabel("W: 0")
            self._loss_lbl = QLabel("L: 0")
            self._winpct_lbl = QLabel("Win%: 0%")
            self._dd_lbl = QLabel("MaxDD: ₹0")
            self._peak_lbl = QLabel("Peak: ₹0")

            for lbl in (self._trades_lbl, self._win_lbl, self._loss_lbl,
                        self._winpct_lbl, self._dd_lbl, self._peak_lbl):
                lbl.setToolTip(lbl.text())
                self._stats_row.addWidget(lbl)

            self._stats_row.addStretch()
            self._main_layout.addLayout(self._stats_row)

        except Exception as e:
            logger.error(f"[DailyPnLWidget._build_ui] Failed: {e}", exc_info=True)

    # ── Theme application ─────────────────────────────────────────────────────

    def apply_theme(self, _=None):
        try:
            if self._closing:
                return

            c, ty, sp = self._c, self._ty, self._sp

            self.setStyleSheet(f"""
                DailyPnLWidget {{
                    background: {c.BG_PANEL};
                    border-top: {sp.SEPARATOR}px solid {c.BORDER};
                    border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
                }}
            """)

            if self._main_layout:
                self._main_layout.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_XS)
                self._main_layout.setSpacing(sp.GAP_SM)

            # Style stats labels
            stat_chip_style = (
                f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt; "
                f"background: transparent; border: none;"
            )
            for lbl in (self._trades_lbl, self._win_lbl, self._loss_lbl, self._winpct_lbl):
                if lbl:
                    lbl.setStyleSheet(stat_chip_style)

            if self._dd_lbl:
                self._dd_lbl.setStyleSheet(
                    f"color: {c.RED}; font-size: {ty.SIZE_SM}pt; "
                    f"background: transparent; border: none;"
                )
            if self._peak_lbl:
                self._peak_lbl.setStyleSheet(
                    f"color: {c.GREEN}; font-size: {ty.SIZE_SM}pt; "
                    f"background: transparent; border: none;"
                )

            self._refresh_ui()

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[DailyPnLWidget.apply_theme] Failed: {e}", exc_info=True)

    # ── UI refresh ────────────────────────────────────────────────────────────

    def _refresh_ui(self):
        try:
            if self._closing:
                return

            realized = self._realized
            unrealized = self._unrealized
            total = realized + unrealized

            # Metric cards
            if self._card_realized:
                self._card_realized.set_value(
                    f"₹{realized:+,.2f}" if realized != 0 else "₹0.00",
                    positive=(realized >= 0)
                )
            if self._card_unrealized:
                self._card_unrealized.set_value(
                    f"₹{unrealized:+,.2f}" if unrealized != 0 else "₹0.00",
                    positive=(unrealized >= 0)
                )
            if self._card_total:
                self._card_total.set_value(
                    f"₹{total:+,.2f}" if total != 0 else "₹0.00",
                    positive=(total >= 0)
                )

            # Progress bar
            if self._pnl_bar:
                self._pnl_bar.set_values(
                    total,
                    self._get_daily_target(),
                    self._get_max_loss()
                )

            # Stats strip
            losses = self._trades - self._winners
            win_pct = (self._winners / self._trades * 100) if self._trades > 0 else 0.0

            if self._trades_lbl:  self._trades_lbl.setText(f"Trades: {self._trades}")
            if self._win_lbl:     self._win_lbl.setText(f"W: {self._winners}")
            if self._loss_lbl:    self._loss_lbl.setText(f"L: {losses}")
            if self._winpct_lbl:  self._winpct_lbl.setText(f"Win%: {win_pct:.0f}%")
            if self._dd_lbl:      self._dd_lbl.setText(f"MaxDD: ₹{self._max_dd:,.0f}")
            if self._peak_lbl:    self._peak_lbl.setText(f"Peak: ₹{self._peak:,.0f}")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[DailyPnLWidget._refresh_ui] Failed: {e}", exc_info=True)

    # ── Data loading / persistence ────────────────────────────────────────────

    def _get_last_reset_date(self) -> date:
        try:
            last_reset = kv.get("daily_pnl_last_reset")
            if last_reset:
                return datetime.strptime(last_reset, "%Y-%m-%d").date()
        except Exception as e:
            logger.error(f"[DailyPnLWidget._get_last_reset_date] {e}")
        return datetime.now().date()

    def _save_last_reset_date(self):
        try:
            kv.set("daily_pnl_last_reset", self._last_reset_date.isoformat())
        except Exception as e:
            logger.error(f"[DailyPnLWidget._save_last_reset_date] {e}")

    def _load_daily_data(self):
        try:
            today_str = datetime.now().date().isoformat()
            from db.connector import get_db
            db = get_db()
            row = db.fetchone(
                "SELECT realized_pnl, unrealized_pnl, trades_count, winners_count, "
                "max_drawdown, peak FROM daily_pnl WHERE date = ?",
                (today_str,)
            )
            if row:
                self._realized = float(row['realized_pnl'])
                self._unrealized = float(row['unrealized_pnl'])
                self._trades = int(row['trades_count'])
                self._winners = int(row['winners_count'])
                self._max_dd = float(row['max_drawdown'])
                self._peak = float(row['peak'])
            else:
                self._calculate_from_orders()
        except Exception as e:
            logger.error(f"[DailyPnLWidget._load_daily_data] {e}", exc_info=True)

    def _calculate_from_orders(self):
        try:
            today_orders = orders.get_by_period('today')
            realized = 0.0
            trades = 0
            winners = 0
            max_dd = 0.0
            peak = 0.0
            running = 0.0
            for order in today_orders:
                pnl = order.get('pnl', 0.0)
                if pnl is not None:
                    realized += pnl
                    trades += 1
                    if pnl > 0:
                        winners += 1
                    running += pnl
                    if running > peak:
                        peak = running
                    if running < max_dd:
                        max_dd = running
            self._realized = realized
            self._trades = trades
            self._winners = winners
            self._max_dd = max_dd
            self._peak = peak
            self._save_daily_data()
        except Exception as e:
            logger.error(f"[DailyPnLWidget._calculate_from_orders] {e}", exc_info=True)

    def _save_daily_data(self):
        try:
            today_str = datetime.now().date().isoformat()
            from db.connector import get_db
            db = get_db()
            db.execute("""
                INSERT INTO daily_pnl
                (date, realized_pnl, unrealized_pnl, trades_count,
                 winners_count, max_drawdown, peak, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    realized_pnl = excluded.realized_pnl,
                    unrealized_pnl = excluded.unrealized_pnl,
                    trades_count = excluded.trades_count,
                    winners_count = excluded.winners_count,
                    max_drawdown = excluded.max_drawdown,
                    peak = excluded.peak,
                    updated_at = excluded.updated_at
            """, (
                today_str, self._realized, self._unrealized, self._trades,
                self._winners, self._max_dd, self._peak, datetime.now().isoformat()
            ))
        except Exception as e:
            logger.error(f"[DailyPnLWidget._save_daily_data] {e}", exc_info=True)

    def _update_from_state(self):
        try:
            snapshot = state_manager.get_position_snapshot()
            current_pnl = snapshot.get('current_pnl')
            if current_pnl is not None:
                self._unrealized = max(-1_000_000.0, min(1_000_000.0, float(current_pnl)))
            else:
                self._unrealized = 0.0
        except Exception as e:
            logger.error(f"[DailyPnLWidget._update_from_state] {e}", exc_info=True)

    # ── Config helpers ────────────────────────────────────────────────────────

    def _get_max_loss(self) -> float:
        """Return max daily loss as a positive float (e.g. 5000 for -₹5000 limit).
        Priority: daily_setting > trade_state > config > hardcoded default."""
        try:
            # 1. Use the live daily_setting object (most up-to-date)
            if self.daily_setting is not None and hasattr(self.daily_setting, 'max_daily_loss'):
                value = self.daily_setting.max_daily_loss
                if value is not None:
                    result = abs(float(value))
                    if result > 0:
                        return result
            # 2. Fallback: read from live trade state (set when DailyTradeSetting.save() is called)
            try:
                snapshot = state_manager.get_snapshot()
                value = snapshot.get('max_daily_loss')
                if value is not None:
                    result = abs(float(value))
                    if result > 0:
                        return result
            except Exception:
                pass
            # 3. Fallback: config dict
            if self.config is not None:
                value = self.config.get('max_daily_loss', 5000.0)
                if value is not None:
                    result = abs(float(value))
                    if result > 0:
                        return result
            return 5000.0
        except Exception:
            return 5000.0

    def _get_daily_target(self) -> float:
        """Return daily profit target as a positive float.
        Priority: daily_setting > trade_state > config > hardcoded default."""
        try:
            # 1. Use the live daily_setting object (most up-to-date)
            if self.daily_setting is not None and hasattr(self.daily_setting, 'daily_target'):
                value = self.daily_setting.daily_target
                if value is not None:
                    result = abs(float(value))
                    if result > 0:
                        return result
            # 2. Fallback: read from live trade state (set when DailyTradeSetting.save() is called)
            try:
                snapshot = state_manager.get_snapshot()
                value = snapshot.get('daily_target')
                if value is not None:
                    result = abs(float(value))
                    if result > 0:
                        return result
            except Exception:
                pass
            # 3. Fallback: config dict
            if self.config is not None:
                value = self.config.get('daily_target', 5000.0)
                if value is not None:
                    result = abs(float(value))
                    if result > 0:
                        return result
            return 5000.0
        except Exception:
            return 5000.0

    def refresh_settings(self, daily_setting=None) -> None:
        """
        Call this after any settings dialog is accepted to immediately reflect
        new daily_target / max_daily_loss values in the progress bar.

        If daily_setting is provided it replaces the stored reference (useful
        when TradingGUI passes the updated object).  Either way the display is
        redrawn so the new limits appear instantly without waiting for the next
        P&L tick.
        """
        try:
            if daily_setting is not None:
                self.daily_setting = daily_setting
            self._refresh_ui()
            logger.info(
                f"[DailyPnLWidget.refresh_settings] target=₹{self._get_daily_target():,.0f} "
                f"max_loss=₹{self._get_max_loss():,.0f}"
            )
        except Exception as e:
            logger.error(f"[DailyPnLWidget.refresh_settings] {e}", exc_info=True)

    # ── Public slots ──────────────────────────────────────────────────────────

    @pyqtSlot(float, bool)
    def on_trade_closed(self, pnl: float, is_winner: bool):
        try:
            pnl = max(-1_000_000.0, min(1_000_000.0, float(pnl or 0)))
            is_winner = bool(is_winner)
            self._realized += pnl
            self._unrealized = 0.0
            self._trades += 1
            if is_winner:
                self._winners += 1
            if self._realized < self._max_dd:
                self._max_dd = self._realized
            if self._realized > self._peak:
                self._peak = self._realized
            self._save_daily_data()
            self._refresh_ui()
        except Exception as e:
            logger.error(f"[DailyPnLWidget.on_trade_closed] {e}", exc_info=True)

    @pyqtSlot(float)
    def on_unrealized_update(self, pnl: float):
        try:
            self._unrealized = max(-1_000_000.0, min(1_000_000.0, float(pnl or 0)))
            self._refresh_ui()
        except Exception as e:
            logger.error(f"[DailyPnLWidget.on_unrealized_update] {e}", exc_info=True)

    @pyqtSlot()
    def _update_unrealized(self):
        try:
            self._update_from_state()
            self._refresh_ui()
        except Exception as e:
            logger.error(f"[DailyPnLWidget._update_unrealized] {e}", exc_info=True)

    # ── Daily reset ───────────────────────────────────────────────────────────

    def _check_daily_reset(self):
        try:
            if self._closing:
                return
            today = datetime.now().date()
            now_time = datetime.now().time()
            if today != self._last_reset_date and now_time.hour == 9 and now_time.minute >= 15:
                self.reset()
                self._last_reset_date = today
                self._save_last_reset_date()
        except Exception as e:
            logger.error(f"[DailyPnLWidget._check_daily_reset] {e}", exc_info=True)

    def reset(self):
        try:
            if self._closing:
                return
            self._save_daily_data()
            self._realized = self._unrealized = 0.0
            self._trades = self._winners = 0
            self._max_dd = self._peak = 0.0
            self._save_daily_data()
            self._refresh_ui()
        except Exception as e:
            logger.error(f"[DailyPnLWidget.reset] {e}", exc_info=True)

    def update_config(self):
        try:
            if self._closing:
                return
            self._refresh_ui()
        except Exception as e:
            logger.error(f"[DailyPnLWidget.update_config] {e}", exc_info=True)

    def manual_refresh(self):
        try:
            self._load_daily_data()
            self._update_from_state()
            self._refresh_ui()
        except Exception as e:
            logger.error(f"[DailyPnLWidget.manual_refresh] {e}", exc_info=True)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        try:
            if self._closing:
                return
            self._closing = True
            self._save_daily_data()
            for timer in (self._reset_timer, self._update_timer):
                if timer is not None:
                    try:
                        timer.stop()
                    except Exception:
                        pass
            self._reset_timer = self._update_timer = None
            try:
                theme_manager.theme_changed.disconnect(self.apply_theme)
                theme_manager.density_changed.disconnect(self.apply_theme)
            except (TypeError, RuntimeError):
                pass
            logger.info("[DailyPnLWidget.cleanup] Done")
        except Exception as e:
            logger.error(f"[DailyPnLWidget.cleanup] {e}", exc_info=True)

    def closeEvent(self, event):
        try:
            self.cleanup()
            super().closeEvent(event)
        except Exception:
            event.accept()