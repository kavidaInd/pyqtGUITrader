"""
gui/app_status_bar.py
---------------------
Professional status bar for the trading dashboard.

Design goals
────────────
• Three-zone layout (left / center / right) with clear visual hierarchy.
• Every piece of information has a label so the user never has to guess.
• Semantic colour coding: green = good, amber = active/warning, red = error.
• Animated dot for live activity — subtle, not distracting.
• No emoji-only labels in compact items; short text abbreviations are used
  alongside the icons so the bar is readable at a glance.
• All colours, sizes, and spacing come from theme_manager tokens — no
  hardcoded values.

Layout (left → right)
─────────────────────
  [ ● STATUS TEXT  HH:MM:SS ]  |  [ MODE ]  [ ↓DATA ]  [ ⚙PROC ]  [ ⬤ORDER ]  [ ⬤POS ]  [ ⬤CONN ]  [ MKT ]  [▓▓  progress ]  |  CPU 0%  MEM 0%  |  PNL ₹0  QUEUE 0  MSG 0/s
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
# TZ-FIX: snapshot cache timestamp comparisons must use ist_now() so the
# 0.1-second throttle is consistent with IST-stored DB timestamps.
from Utils.time_utils import ist_now
from Utils.time_utils import IST, ist_now, fmt_display, fmt_stamp
from typing import Any, Dict, Optional

import psutil

from PyQt5.QtCore  import (
    QEasingCurve, QPropertyAnimation, QTimer, Qt, pyqtProperty,
)
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QSizePolicy, QWidget,
)

from Utils.safe_getattr import safe_hasattr
from data.trade_state_manager import state_manager
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Small building-block widgets
# ─────────────────────────────────────────────────────────────────────────────

class _PulseDot(QLabel):
    """A single coloured circle that blinks when active."""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__("●", parent)
        self._color: str = ""
        self._anim: Optional[QPropertyAnimation] = None
        self._opacity: float = 1.0
        self._active: bool   = False
        self._build_anim()

    # Qt property for animation
    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, v: float) -> None:
        self._opacity = max(0.0, min(1.0, v))
        self._refresh_style()

    opacity = pyqtProperty(float, _get_opacity, _set_opacity)

    def _build_anim(self) -> None:
        self._anim = QPropertyAnimation(self, b"opacity")
        self._anim.setDuration(900)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.15)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)

    def activate(self, color: str) -> None:
        if self._active and self._color == color:
            return
        self._color = color
        self._active = True
        if self._anim and not self._anim.state():
            self._anim.start()
        self._refresh_style()

    def deactivate(self, dim_color: str) -> None:
        if not self._active:
            return
        self._active = False
        self._color  = dim_color
        if self._anim:
            self._anim.stop()
        self._opacity = 1.0
        self._refresh_style()

    def _refresh_style(self) -> None:
        try:
            r, g, b = (
                int(self._color[1:3], 16),
                int(self._color[3:5], 16),
                int(self._color[5:7], 16),
            )
            ty = theme_manager.typography
            self.setStyleSheet(
                f"color: rgba({r},{g},{b},{self._opacity:.2f}); "
                f"font-size: {ty.SIZE_MD}pt; "
                f"background: transparent; border: none;"
            )
        except Exception:
            pass


class _Separator(QFrame):
    """Thin vertical divider between status-bar zones."""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.VLine)
        self.setFixedWidth(1)
        self._refresh()

    def _refresh(self) -> None:
        c = theme_manager.palette
        self.setStyleSheet(f"color: {c.BORDER}; background: {c.BORDER};")


class _MetricChip(QWidget):
    """
    A two-part chip:  LABEL [ value ].
    Used for CPU, MEM, PNL, QUEUE, MSG.
    """

    def __init__(self, label: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._label_text = label
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        self._lbl = QLabel(label)
        self._val = QLabel("—")
        lay.addWidget(self._lbl)
        lay.addWidget(self._val)
        self._apply_base_style()

    def _apply_base_style(self) -> None:
        c  = theme_manager.palette
        ty = theme_manager.typography
        sp = theme_manager.spacing
        self._lbl.setStyleSheet(
            f"color: {c.TEXT_DISABLED}; font-size: {ty.SIZE_XS}pt; "
            f"background: transparent; border: none; "
            f"letter-spacing: 0.4px;"
        )
        self._val.setStyleSheet(
            f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_SM}pt; "
            f"font-weight: {ty.WEIGHT_BOLD}; "
            f"background: {c.BG_HOVER}; border: none; "
            f"border-radius: {sp.RADIUS_SM}px; "
            f"padding: 1px {sp.PAD_XS + 1}px;"
        )

    def set_value(self, text: str, color: Optional[str] = None) -> None:
        self._val.setText(text)
        c  = theme_manager.palette
        ty = theme_manager.typography
        sp = theme_manager.spacing
        col = color or c.TEXT_MAIN
        self._val.setStyleSheet(
            f"color: {col}; font-size: {ty.SIZE_SM}pt; "
            f"font-weight: {ty.WEIGHT_BOLD}; "
            f"background: {c.BG_HOVER}; border: none; "
            f"border-radius: {sp.RADIUS_SM}px; "
            f"padding: 1px {sp.PAD_XS + 1}px;"
        )

    def apply_theme(self) -> None:
        self._apply_base_style()


class _OpIndicator(QWidget):
    """
    A labelled indicator for one operation type (DATA, PROC, ORDER, POS).
    Shows a coloured dot + short abbreviation.
    """

    def __init__(self, abbr: str, tooltip: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self._dot  = _PulseDot()
        self._abbr = QLabel(abbr)
        lay.addWidget(self._dot)
        lay.addWidget(self._abbr)
        self.setToolTip(tooltip)
        self._apply_inactive()

    def _apply_inactive(self) -> None:
        c  = theme_manager.palette
        ty = theme_manager.typography
        dim = c.TEXT_DISABLED
        self._dot.deactivate(dim)
        self._abbr.setStyleSheet(
            f"color: {dim}; font-size: {ty.SIZE_XS}pt; "
            f"background: transparent; border: none;"
        )

    def set_active(self, active: bool, color: str) -> None:
        c  = theme_manager.palette
        ty = theme_manager.typography
        if active:
            self._dot.activate(color)
            self._abbr.setStyleSheet(
                f"color: {color}; font-size: {ty.SIZE_XS}pt; "
                f"font-weight: {ty.WEIGHT_BOLD}; "
                f"background: transparent; border: none;"
            )
        else:
            self._apply_inactive()

    def apply_theme(self) -> None:
        self._apply_inactive()


class _ModeBadge(QLabel):
    """Pill badge for ALGO / MANUAL mode."""

    def set_mode(self, mode_text: str, is_algo: bool) -> None:
        self.setText(mode_text)
        c  = theme_manager.palette
        ty = theme_manager.typography
        sp = theme_manager.spacing
        bg = c.BLUE_DARK if is_algo else c.YELLOW
        fg = c.TEXT_INVERSE
        self.setStyleSheet(
            f"color: {fg}; background: {bg}; "
            f"border-radius: {sp.RADIUS_PILL}px; "
            f"padding: 1px {sp.PAD_SM}px; "
            f"font-size: {ty.SIZE_XS}pt; "
            f"font-weight: {ty.WEIGHT_BOLD}; "
            f"letter-spacing: 0.6px;"
        )


class _ConnBadge(QLabel):
    """CONN indicator: green = connected, red = disconnected."""

    def set_connected(self, connected: bool) -> None:
        c  = theme_manager.palette
        ty = theme_manager.typography
        sp = theme_manager.spacing
        if connected:
            color = c.GREEN
            bg    = c.GREEN + "22"
            text  = "CONN ●"
        else:
            color = c.RED
            bg    = c.RED + "22"
            text  = "CONN ○"
        self.setText(text)
        self.setStyleSheet(
            f"color: {color}; background: {bg}; "
            f"border: 1px solid {color}44; "
            f"border-radius: {sp.RADIUS_PILL}px; "
            f"padding: 1px {sp.PAD_SM}px; "
            f"font-size: {ty.SIZE_XS}pt; "
            f"font-weight: {ty.WEIGHT_BOLD};"
        )


class _MktBadge(QLabel):
    """MKT indicator: green = open, muted = closed / unknown."""

    def set_status(self, status: str) -> None:
        c  = theme_manager.palette
        ty = theme_manager.typography
        sp = theme_manager.spacing
        if status == "OPEN":
            color, bg, text = c.GREEN, c.GREEN + "22", "MKT OPEN"
        elif status == "CLOSED":
            color, bg, text = c.TEXT_DISABLED, c.BG_HOVER, "MKT CLOSED"
        else:
            color, bg, text = c.TEXT_DISABLED, c.BG_HOVER, "MKT —"
        self.setText(text)
        self.setStyleSheet(
            f"color: {color}; background: {bg}; "
            f"border-radius: {sp.RADIUS_PILL}px; "
            f"padding: 1px {sp.PAD_SM}px; "
            f"font-size: {ty.SIZE_XS}pt; "
            f"font-weight: {ty.WEIGHT_BOLD};"
        )


# ─────────────────────────────────────────────────────────────────────────────
# AppStatusBar
# ─────────────────────────────────────────────────────────────────────────────

class AppStatusBar(QFrame):
    """
    Three-zone professional status bar.

    Zone A (left)   — app status indicator + timestamp
    Zone B (centre) — mode badge + operation indicators + connection + market + progress
    Zone C (right)  — system metrics + trading metrics
    """

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._init_state()
        self._build_ui()
        self.apply_theme()

        # Connect theme signals
        theme_manager.theme_changed.connect(self.apply_theme)
        theme_manager.density_changed.connect(self.apply_theme)

        # 1-second refresh timer
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

        # Safety reset after 5-min stuck ops
        self._safety = QTimer()
        self._safety.setSingleShot(True)
        self._safety.timeout.connect(self._safety_reset)

        logger.info("[AppStatusBar] Initialized")

    # ── internal state ────────────────────────────────────────────────────────

    def _init_state(self) -> None:
        self._app_running:   bool = False
        self._mode:          str  = "algo"
        self._market_status: str  = "UNKNOWN"
        self._connected:     bool = False
        self._op_times:      dict = {}
        self._snapshot_ts:   Optional[datetime] = None
        self._snapshot:      dict = {}
        self._pos_snapshot:  dict = {}
        self._last_msg_cnt:  int  = 0
        self._peak_rate:     int  = 0
        self.trading_app           = None  # wired by TradingGUI

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        c  = theme_manager.palette
        sp = theme_manager.spacing

        root = QHBoxLayout(self)
        root.setContentsMargins(sp.PAD_MD, 0, sp.PAD_MD, 0)
        root.setSpacing(0)

        # ── Zone A: status ────────────────────────────────────────────────────
        self._zone_a = QWidget()
        za = QHBoxLayout(self._zone_a)
        za.setContentsMargins(0, 0, 0, 0)
        za.setSpacing(sp.GAP_SM)

        self._status_dot   = _PulseDot()
        self._status_label = QLabel("Ready")
        self._time_label   = QLabel()
        self._time_label.setMinimumWidth(52)

        za.addWidget(self._status_dot)
        za.addWidget(self._status_label)
        za.addSpacing(sp.GAP_SM)
        za.addWidget(self._time_label)

        # ── Zone B: operations ────────────────────────────────────────────────
        self._zone_b = QWidget()
        zb = QHBoxLayout(self._zone_b)
        zb.setContentsMargins(0, 0, 0, 0)
        zb.setSpacing(sp.GAP_MD)

        self._mode_badge = _ModeBadge()
        self._mode_badge.set_mode("ALGO", True)

        self._op_data  = _OpIndicator("DATA",  "Fetching market data")
        self._op_proc  = _OpIndicator("PROC",  "Processing signals")
        self._op_order = _OpIndicator("ORDER", "Order in flight")
        self._op_pos   = _OpIndicator("POS",   "Position open")

        self._conn_badge = _ConnBadge()
        self._conn_badge.set_connected(False)
        self._mkt_badge  = _MktBadge()
        self._mkt_badge.set_status("UNKNOWN")

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedWidth(80)
        self._progress.setFixedHeight(6)
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)

        for w in (
            self._mode_badge, self._op_data, self._op_proc,
            self._op_order, self._op_pos, self._conn_badge,
            self._mkt_badge, self._progress,
        ):
            zb.addWidget(w)

        # ── Zone C: metrics ───────────────────────────────────────────────────
        self._zone_c = QWidget()
        zc = QHBoxLayout(self._zone_c)
        zc.setContentsMargins(0, 0, 0, 0)
        zc.setSpacing(sp.GAP_MD)

        self._cpu  = _MetricChip("CPU")
        self._mem  = _MetricChip("MEM")
        self._pnl  = _MetricChip("PNL")
        self._que  = _MetricChip("QUE")
        self._msg  = _MetricChip("MSG")

        for w in (self._cpu, self._mem, self._pnl, self._que, self._msg):
            zc.addWidget(w)

        # ── Assemble ──────────────────────────────────────────────────────────
        root.addWidget(self._zone_a)
        root.addWidget(_Separator())
        root.addSpacing(sp.GAP_MD)
        root.addWidget(self._zone_b, 1)
        root.addWidget(_Separator())
        root.addSpacing(sp.GAP_MD)
        root.addWidget(self._zone_c)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def apply_theme(self, _: str = None) -> None:
        c  = theme_manager.palette
        sp = theme_manager.spacing
        ty = theme_manager.typography

        self.setStyleSheet(f"""
            AppStatusBar {{
                background:  {c.BAR_BG};
                border-top:  {sp.SEPARATOR}px solid {c.BAR_BORDER};
            }}
        """)

        # Status label
        self._status_label.setStyleSheet(
            f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_SM}pt; "
            f"font-weight: {ty.WEIGHT_BOLD}; background: transparent; border: none;"
        )
        self._time_label.setStyleSheet(
            f"color: {c.TEXT_DISABLED}; font-size: {ty.SIZE_XS}pt; "
            f"background: transparent; border: none;"
        )

        # Progress bar
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background: {c.BG_HOVER};
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {c.BLUE};
                border-radius: 3px;
            }}
        """)

        # Metric chips
        for chip in (self._cpu, self._mem, self._pnl, self._que, self._msg):
            chip.apply_theme()

        # Op indicators
        for op in (self._op_data, self._op_proc, self._op_order, self._op_pos):
            op.apply_theme()

    # ── Public API ────────────────────────────────────────────────────────────

    def update_status(
        self,
        status_info: Dict[str, Any],
        mode:        str,
        app_running: bool,
    ) -> None:
        """Called by TradingGUI on every state change."""
        try:
            self._mode        = mode
            self._app_running = app_running
            snap              = self._cached_snapshot()

            self._update_status_zone(status_info, snap)
            self._update_mode_badge(mode)
            self._update_ops(status_info, snap)
            self._update_conn(status_info)
            self._update_progress(status_info)

            if "market_status" in status_info:
                self.update_market_status(status_info["market_status"])

            # Arm safety reset
            if not self._safety.isActive():
                self._safety.start(300_000)   # 5 min

        except Exception as exc:
            logger.error(f"[AppStatusBar.update_status] {exc}", exc_info=True)

    def update_market_status(self, status: str) -> None:
        self._market_status = status
        self._mkt_badge.set_status(status)

    def update_live_price(self, ltp: float) -> None:
        """
        Fast-path called by TradingGUI._on_price_tick on every WS tick.
        app_status_bar does not currently display the index price inline,
        so this is a no-op stub to prevent AttributeError from safe_hasattr checks.
        """
        pass

    def show_progress(self, value: int = -1, *, text: str = "") -> None:
        """value=-1 → indeterminate; 0-100 → determinate."""
        self._progress.setVisible(True)
        if value < 0:
            self._progress.setRange(0, 0)
        else:
            self._progress.setRange(0, 100)
            self._progress.setValue(max(0, min(100, value)))
        if text:
            self._status_label.setText(text)

    def hide_progress(self) -> None:
        self._progress.setVisible(False)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)

    def reset(self) -> None:
        self._op_times.clear()
        self._app_running = False
        self._connected   = False
        self.update_status({}, self._mode, False)
        self.update_market_status("UNKNOWN")
        self.hide_progress()

    def cleanup(self) -> None:
        try:
            if self._timer.isActive():
                self._timer.stop()
            if self._safety.isActive():
                self._safety.stop()
        except Exception as exc:
            logger.warning(f"[AppStatusBar.cleanup] {exc}")

    # ── Internal update helpers ───────────────────────────────────────────────

    def _cached_snapshot(self) -> dict:
        now = ist_now()
        if (
            self._snapshot_ts is None
            or (now - self._snapshot_ts).total_seconds() > 0.1
        ):
            self._snapshot      = state_manager.get_snapshot()
            self._pos_snapshot  = state_manager.get_position_snapshot()
            self._snapshot_ts   = now
        return self._snapshot

    def _update_status_zone(
        self, info: dict, snap: dict
    ) -> None:
        c  = theme_manager.palette
        ty = theme_manager.typography

        # Text
        text = info.get("status", "Ready") if info else "Ready"
        self._status_label.setText(str(text))

        # Dot colour
        if not self._app_running:
            dot_color = c.RED
        elif info.get("order_pending"):
            dot_color = c.YELLOW
        elif info.get("fetching_history"):
            dot_color = c.ORANGE
        elif info.get("processing"):
            dot_color = c.BLUE
        elif snap.get("current_position") is not None:
            dot_color = c.GREEN_BRIGHT
        else:
            dot_color = c.GREEN

        if self._app_running:
            self._status_dot.activate(dot_color)
        else:
            self._status_dot.deactivate(c.RED)

    def _update_mode_badge(self, mode: str) -> None:
        is_algo = (mode == "algo")
        label   = "ALGO" if is_algo else "MANUAL"
        self._mode_badge.set_mode(label, is_algo)

    def _update_ops(self, info: dict, snap: dict) -> None:
        c = theme_manager.palette
        pairs = [
            (self._op_data,  info.get("fetching_history", False), c.ORANGE),
            (self._op_proc,  info.get("processing",       False), c.BLUE),
            (self._op_order, info.get("order_pending",    False), c.YELLOW),
            (self._op_pos,
             bool(info.get("has_position")) or snap.get("current_position") is not None,
             c.GREEN),
        ]
        for indicator, active, color in pairs:
            indicator.set_active(active, color)

    def _update_conn(self, info: dict) -> None:
        connected = info.get("connection_status") == "Connected"
        self._connected = connected
        self._conn_badge.set_connected(connected)

    def _update_progress(self, info: dict) -> None:
        if info.get("fetching_history"):
            prog = info.get("progress", -1)
            self.show_progress(prog)
        else:
            self.hide_progress()

    # ── 1-second tick (metrics) ───────────────────────────────────────────────

    def _tick(self) -> None:
        """Update clock and dynamic system/trading metrics once per second."""
        try:
            self._time_label.setText(fmt_display(ist_now(), time_only=True))

            if not self._app_running:
                return

            c = theme_manager.palette

            # CPU
            try:
                cpu = psutil.cpu_percent(interval=None)
                col = c.RED if cpu > 90 else (c.YELLOW if cpu > 70 else c.GREEN)
                self._cpu.set_value(f"{cpu:.0f}%", col)
            except Exception:
                pass

            # MEM
            try:
                mem = psutil.virtual_memory().percent
                col = c.RED if mem > 90 else (c.YELLOW if mem > 80 else c.GREEN)
                self._mem.set_value(f"{mem:.0f}%", col)
            except Exception:
                pass

            # PNL
            try:
                snap = self._cached_snapshot()
                pos  = self._pos_snapshot
                pnl  = pos.get("current_pnl", 0) or 0
                col  = c.GREEN if pnl > 0 else (c.RED if pnl < 0 else c.TEXT_DIM)
                self._pnl.set_value(
                    f"₹{pnl:,.0f}" if pnl != 0 else "₹0", col
                )
            except Exception:
                pass

            # Queue
            try:
                if (
                    safe_hasattr(self, "trading_app")
                    and self.trading_app
                    and safe_hasattr(self.trading_app, "_tick_queue")
                ):
                    qsz = self.trading_app._tick_queue.qsize()
                    col = c.RED if qsz > 100 else (c.YELLOW if qsz > 50 else c.TEXT_DIM)
                    self._que.set_value(str(qsz), col)
            except Exception:
                pass

            # Msg rate
            try:
                if (
                    safe_hasattr(self, "trading_app")
                    and self.trading_app
                    and safe_hasattr(self.trading_app, "ws")
                    and self.trading_app.ws
                    and safe_hasattr(self.trading_app.ws, "get_statistics")
                ):
                    stats = self.trading_app.ws.get_statistics()
                    cnt   = stats.get("message_count", 0)
                    rate  = cnt - self._last_msg_cnt
                    self._last_msg_cnt = cnt
                    col   = c.RED if rate > 100 else (c.YELLOW if rate > 50 else c.GREEN)
                    self._msg.set_value(f"{rate}/s", col)
            except Exception:
                pass

        except Exception as exc:
            logger.debug(f"[AppStatusBar._tick] {exc}")

    # ── Safety reset ──────────────────────────────────────────────────────────

    def _safety_reset(self) -> None:
        """After 5 minutes, clear any stuck operation indicators."""
        try:
            logger.info("[AppStatusBar] safety reset triggered")
            for op in (self._op_data, self._op_proc, self._op_order, self._op_pos):
                op.apply_theme()
        except Exception:
            pass