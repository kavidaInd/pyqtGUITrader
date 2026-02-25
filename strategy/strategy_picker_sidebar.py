"""
strategy_picker_sidebar_db.py
==============================
A compact, non-modal sidebar popup for quickly switching the active strategy
at runtime without opening the full editor. Uses database-backed strategy manager.

Shows:
  - List of all strategies with the active one highlighted
  - One-click activation
  - Active strategy stats (name, rules count, last updated)
  - "Open Editor" button to launch StrategyEditorWindow
  - Live indicator: current signal from active strategy

Embed in TradingGUI as a pinned sidebar OR show as a floating popup.

Usage (as floating popup from TradingGUI):
    # __init__:
    self.strategy_picker = None

    # Method:
    def _show_strategy_picker(self):
        if not self.strategy_picker:
            self.strategy_picker = StrategyPickerSidebar(
                trading_app=self.trading_app,
                parent=self
            )
            self.strategy_picker.strategy_activated.connect(self._on_strategy_changed)
            self.strategy_picker.open_editor_requested.connect(self._open_strategy_editor)
        self.strategy_picker.show()
        self.strategy_picker.raise_()
        self.strategy_picker.activateWindow()
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from strategy.strategy_manager import strategy_manager

# Import SIGNAL_GROUPS as strings from the right place
# These are the string values used in the engine config
SIGNAL_GROUPS = ["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

# ── Palette ──────────────────────────────────────────────────────────────────
BG = "#0d1117"
BG_PANEL = "#161b22"
BG_ITEM = "#1c2128"
BG_SEL = "#1f3d5c"
BORDER = "#30363d"
TEXT = "#e6edf3"
DIM = "#8b949e"
GREEN = "#3fb950"
RED = "#f85149"
BLUE = "#58a6ff"
YELLOW = "#d29922"
ORANGE = "#ffa657"

SIGNAL_COLORS = {
    "BUY_CALL": GREEN,
    "BUY_PUT": BLUE,
    "EXIT_CALL": RED,
    "EXIT_PUT": ORANGE,
    "HOLD": YELLOW,
    "WAIT": "#484f58",
}
SIGNAL_LABELS = {
    "BUY_CALL": "📈 Buy Call",
    "BUY_PUT": "📉 Buy Put",
    "EXIT_CALL": "🔴 Exit Call",
    "EXIT_PUT": "🟠 Exit Put",
    "HOLD": "⏸ Hold",
    "WAIT": "⏳ Wait",
}


def _ss() -> str:
    return f"""
        QDialog, QWidget {{
            background: {BG}; color: {TEXT}; font-size: 10pt;
        }}
        QLabel {{ color: {TEXT}; }}
        QPushButton {{
            background: #21262d; color: {TEXT};
            border: 1px solid {BORDER}; border-radius: 5px;
            padding: 7px 14px; font-size: 10pt; font-weight: bold;
        }}
        QPushButton:hover {{ background: #2d333b; }}
        QPushButton:disabled {{ background: #161b22; color: #484f58; }}
        QListWidget {{
            background: {BG_PANEL}; color: {TEXT};
            border: 1px solid {BORDER}; border-radius: 4px;
            font-size: 10pt; outline: none;
        }}
        QListWidget::item {{
            padding: 10px 14px;
            border-bottom: 1px solid {BORDER};
        }}
        QListWidget::item:selected {{
            background: {BG_SEL}; color: {BLUE};
            border-left: 3px solid {BLUE};
        }}
        QListWidget::item:hover {{ background: #1f2937; }}
        QScrollArea {{ border: none; background: transparent; }}
        QFrame {{ background: transparent; }}
    """


class _StrategyCard(QFrame):
    """Expanded card showing active strategy details."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setStyleSheet(f"""
                QFrame {{
                    background: {BG_PANEL};
                    border: 1px solid {BORDER};
                    border-radius: 6px;
                }}
            """)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(5)

            header = QHBoxLayout()
            badge = QLabel("⚡ ACTIVE")
            badge.setStyleSheet(f"color:{BLUE}; font-size:8pt; font-weight:bold;")
            header.addWidget(badge)
            header.addStretch()
            self._signal_lbl = QLabel()
            self._signal_lbl.setStyleSheet(f"color:#484f58; font-size:9pt; font-weight:bold;")
            header.addWidget(self._signal_lbl)
            layout.addLayout(header)

            self._name_lbl = QLabel("—")
            self._name_lbl.setStyleSheet(f"color:{TEXT}; font-size:12pt; font-weight:bold;")
            layout.addWidget(self._name_lbl)

            self._desc_lbl = QLabel()
            self._desc_lbl.setStyleSheet(f"color:{DIM}; font-size:9pt;")
            self._desc_lbl.setWordWrap(True)
            layout.addWidget(self._desc_lbl)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"QFrame{{background:{BORDER};max-height:1px;border:none;}}")
            layout.addWidget(sep)

            # Stats row
            stats = QHBoxLayout()
            self._rules_lbl = self._stat_lbl("0 rules")
            self._updated_lbl = self._stat_lbl("—")
            stats.addWidget(self._rules_lbl)
            stats.addStretch()
            stats.addWidget(self._updated_lbl)
            layout.addLayout(stats)

        except Exception as e:
            logger.error(f"[_StrategyCard.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._signal_lbl = None
        self._name_lbl = None
        self._desc_lbl = None
        self._rules_lbl = None
        self._updated_lbl = None

    def _stat_lbl(self, text: str) -> QLabel:
        try:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color:{DIM}; font-size:8pt;")
            return lbl
        except Exception as e:
            logger.error(f"[_StrategyCard._stat_lbl] Failed: {e}", exc_info=True)
            return QLabel(text)

    def update(self, strategy: Dict, current_signal: str = "WAIT"):
        """Update card with strategy data and current signal"""
        try:
            if strategy is None:
                logger.warning("update called with None strategy")
                return

            if self._name_lbl:
                self._name_lbl.setText(str(strategy.get("name", "—")))

            desc = strategy.get("description", "")
            if self._desc_lbl:
                self._desc_lbl.setText(desc[:100] + ("…" if len(desc) > 100 else ""))
                self._desc_lbl.setVisible(bool(desc))

            # Rules count - use string keys directly, not .value
            engine = strategy.get("engine", {})
            total = 0
            for sig in SIGNAL_GROUPS:  # sig is already a string like "BUY_CALL"
                group = engine.get(sig, {}) if engine else {}
                rules = group.get("rules", []) if isinstance(group, dict) else []
                total += len(rules)

            if self._rules_lbl:
                self._rules_lbl.setText(f"{total} rule{'s' if total != 1 else ''}")

            # Updated
            upd = strategy.get("updated_at", "—")
            if upd and "T" in upd:
                upd = upd.replace("T", " ")[:16]
            if self._updated_lbl:
                self._updated_lbl.setText(f"saved {upd}")

            # Signal
            color = SIGNAL_COLORS.get(current_signal, "#484f58")
            label = SIGNAL_LABELS.get(current_signal, current_signal)
            if self._signal_lbl:
                self._signal_lbl.setText(label)
                self._signal_lbl.setStyleSheet(
                    f"color:{color}; font-size:9pt; font-weight:bold;"
                    f" background:{color}22; border:1px solid {color}55;"
                    f" border-radius:4px; padding:2px 7px;"
                )
        except Exception as e:
            logger.error(f"[_StrategyCard.update] Failed: {e}", exc_info=True)


class StrategyPickerSidebar(QDialog):
    """
    Compact floating sidebar for switching active strategy.
    Non-modal — can stay open while trading. Uses database-backed strategy manager.
    """
    strategy_activated = pyqtSignal(str)  # emitted with slug
    open_editor_requested = pyqtSignal()  # user wants full editor

    def __init__(self, trading_app=None, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent, Qt.Window | Qt.Tool)
            self.trading_app = trading_app
            self._current_signal = "WAIT"

            self.setWindowTitle("⚡ Strategy Picker")
            self.setFixedWidth(360)
            self.setMinimumHeight(480)
            self.setMaximumHeight(800)
            self.setStyleSheet(_ss())

            self._build_ui()
            self.refresh()

            # Auto-refresh signal display every 2s
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._refresh_signal)
            self._timer.start(2000)

            logger.info("StrategyPickerSidebar (database) initialized")

        except Exception as e:
            logger.critical(f"[StrategyPickerSidebar.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent, Qt.Window | Qt.Tool)
            self.setWindowTitle("Strategy Picker - ERROR")
            self.setMinimumWidth(300)

            layout = QVBoxLayout(self)
            error_label = QLabel(f"Failed to initialize strategy picker:\n{e}")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #f85149; padding: 20px;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.trading_app = None
        self._current_signal = "WAIT"
        self._timer = None
        self._card = None
        self._list = None
        self._activate_btn = None
        self._status_lbl = None

    def _build_ui(self):
        """Build the UI components"""
        try:
            root = QVBoxLayout(self)
            root.setContentsMargins(10, 10, 10, 10)
            root.setSpacing(8)

            # Active strategy card
            self._card = _StrategyCard()
            root.addWidget(self._card)

            # ── Separator ─────────────────────────────────────────────────────────
            sep = QLabel("  ALL STRATEGIES")
            sep.setStyleSheet(f"color:{DIM}; font-size:8pt; font-weight:bold; padding:4px 0 2px 0;")
            root.addWidget(sep)

            # Strategy list
            self._list = QListWidget()
            self._list.setSelectionMode(QAbstractItemView.SingleSelection)
            self._list.itemDoubleClicked.connect(self._on_double_click)
            root.addWidget(self._list, 1)

            # ── Activate button ───────────────────────────────────────────────────
            self._activate_btn = QPushButton("⚡ Activate Selected")
            self._activate_btn.setStyleSheet(
                f"QPushButton{{background:#1f6feb;color:#fff;border:1px solid #388bfd;"
                f"border-radius:5px;padding:9px;font-weight:bold;font-size:11pt;}}"
                f"QPushButton:hover{{background:#388bfd;}}"
            )
            self._activate_btn.clicked.connect(self._on_activate)
            root.addWidget(self._activate_btn)

            # ── Footer ────────────────────────────────────────────────────────────
            foot = QHBoxLayout()
            foot.setSpacing(8)

            open_editor_btn = QPushButton("📋 Open Editor")
            open_editor_btn.clicked.connect(self._on_open_editor)
            foot.addWidget(open_editor_btn)

            foot.addStretch()

            close_btn = QPushButton("✕ Close")
            close_btn.clicked.connect(self.close)
            foot.addWidget(close_btn)

            root.addLayout(foot)

            self._status_lbl = QLabel()
            self._status_lbl.setAlignment(Qt.AlignCenter)
            self._status_lbl.setStyleSheet(f"color:{GREEN}; font-size:9pt;")
            root.addWidget(self._status_lbl)

        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._build_ui] Failed: {e}", exc_info=True)
            raise

    def refresh(self):
        """Reload the strategy list from database."""
        try:
            # Use explicit `is None` — never use truthiness on QWidget or
            # custom objects, as an empty QListWidget is falsy (len == 0).
            if self._list is None:
                return

            self._list.blockSignals(True)
            self._list.clear()

            strategies = strategy_manager.list_strategies()
            active_slug = strategy_manager.get_active_slug()

            for s in strategies:
                try:
                    item = QListWidgetItem()
                    slug = s.get("slug", "")
                    is_active = (slug == active_slug)

                    # Get full strategy data for rules count
                    strategy_data = strategy_manager.get(slug) or {}
                    engine = strategy_data.get("engine", {}) if strategy_data else {}

                    total_rules = 0
                    for sig in SIGNAL_GROUPS:  # sig is a string like "BUY_CALL"
                        group = engine.get(sig, {}) if engine else {}
                        rules = group.get("rules", []) if isinstance(group, dict) else []
                        total_rules += len(rules)

                    # Build item text
                    prefix = "⚡" if is_active else "  "
                    name = s.get("name", "Unknown")
                    item.setText(f"{prefix}  {name}")
                    item.setData(Qt.UserRole, slug)

                    tooltip = s.get("description", "")
                    updated = s.get("updated_at", "—")
                    if updated and "T" in updated:
                        updated = updated.replace("T", " ")[:16]
                    tooltip += f"\n{total_rules} rules | updated {updated}"
                    item.setToolTip(tooltip)

                    if is_active:
                        item.setForeground(QColor(BLUE))
                        font = QFont()
                        font.setBold(True)
                        item.setFont(font)

                    self._list.addItem(item)

                except Exception as e:
                    logger.warning(f"Failed to add strategy item: {e}")
                    continue

            self._list.blockSignals(False)

            # Update active card
            if self._card is not None:
                active_data = strategy_manager.get_active()
                if active_data is not None:
                    self._card.update(active_data, self._current_signal)

        except Exception as e:
            logger.error(f"[StrategyPickerSidebar.refresh] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _refresh_signal(self):
        """Pull current signal from trading_app and update card."""
        try:
            if not self.isVisible() or self._card is None:
                return

            if self.trading_app is None:
                return

            state = getattr(self.trading_app, "state", None)
            if state is None:
                return

            trend = getattr(state, "derivative_trend", None) or {}
            sig_data = trend.get("option_signal", {})
            self._current_signal = sig_data.get("signal_value", "WAIT") if sig_data else "WAIT"

            active = strategy_manager.get_active()
            if active is not None and self._card is not None:
                self._card.update(active, self._current_signal)

        except Exception as e:
            logger.debug(f"[_refresh_signal] Failed: {e}")

    def _on_double_click(self, item):
        """Handle double-click on strategy item"""
        try:
            if item:
                slug = item.data(Qt.UserRole)
                self._activate(slug)
        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._on_double_click] Failed: {e}", exc_info=True)

    def _on_activate(self):
        """Handle activate button click"""
        try:
            if self._list is None:
                return

            item = self._list.currentItem()
            if item:
                slug = item.data(Qt.UserRole)
                self._activate(slug)
        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._on_activate] Failed: {e}", exc_info=True)

    def _activate(self, slug: str):
        """Activate a strategy by slug"""
        try:
            if not slug:
                logger.warning("Cannot activate: empty slug")
                return

            ok = strategy_manager.activate(slug)
            if ok:
                self.refresh()
                self.strategy_activated.emit(slug)

                strategy_data = strategy_manager.get(slug) or {}
                name = strategy_data.get("name", slug)

                if self._status_lbl:
                    self._status_lbl.setText(f"✓ Activated: {name}")
                    QTimer.singleShot(3000, lambda: self._status_lbl.clear() if self._status_lbl else None)

        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._activate] Failed for {slug}: {e}", exc_info=True)

    def _on_open_editor(self):
        """Emit signal to open editor"""
        try:
            self.open_editor_requested.emit()
        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._on_open_editor] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources — call only when permanently destroying the widget."""
        try:
            logger.info("[StrategyPickerSidebar] Starting cleanup")

            # Stop timer
            if self._timer:
                try:
                    if self._timer.isActive():
                        self._timer.stop()
                    self._timer = None
                except Exception as e:
                    logger.warning(f"Error stopping timer: {e}")

            # Clear references
            self.trading_app = None
            self._card = None
            self._list = None
            self._activate_btn = None
            self._status_lbl = None

            logger.info("[StrategyPickerSidebar] Cleanup completed")

        except Exception as e:
            logger.error(f"[StrategyPickerSidebar.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """
        Hide the sidebar instead of destroying it so it can be re-shown later.
        Call cleanup() explicitly only when the parent window is closing.
        """
        try:
            # Pause the timer while hidden to avoid wasted work
            if self._timer and self._timer.isActive():
                self._timer.stop()
            self.hide()
            event.ignore()   # Do NOT close/destroy — just hide
        except Exception as e:
            logger.error(f"[StrategyPickerSidebar.closeEvent] Failed: {e}", exc_info=True)
            event.ignore()

    def showEvent(self, event):
        """Resume the refresh timer whenever the sidebar becomes visible."""
        try:
            super().showEvent(event)
            if self._timer and not self._timer.isActive():
                self._timer.start(2000)
        except Exception as e:
            logger.error(f"[StrategyPickerSidebar.showEvent] Failed: {e}", exc_info=True)