"""
strategy_picker_sidebar.py
==========================
A compact, non-modal sidebar popup for quickly switching the active strategy
at runtime without opening the full editor.

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
                manager=self.strategy_manager,
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
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from strategy.strategy_manager import StrategyManager, SIGNAL_GROUPS

logger = logging.getLogger(__name__)

# ── Palette ──────────────────────────────────────────────────────────────────
BG       = "#0d1117"
BG_PANEL = "#161b22"
BG_ITEM  = "#1c2128"
BG_SEL   = "#1f3d5c"
BORDER   = "#30363d"
TEXT     = "#e6edf3"
DIM      = "#8b949e"
GREEN    = "#3fb950"
RED      = "#f85149"
BLUE     = "#58a6ff"
YELLOW   = "#d29922"
ORANGE   = "#ffa657"

SIGNAL_COLORS = {
    "BUY_CALL":  GREEN,
    "BUY_PUT":   BLUE,
    "SELL_CALL": RED,
    "SELL_PUT":  ORANGE,
    "HOLD":      YELLOW,
    "WAIT":      "#484f58",
}
SIGNAL_LABELS = {
    "BUY_CALL":  "📈 Buy Call",
    "BUY_PUT":   "📉 Buy Put",
    "SELL_CALL": "🔴 Sell Call",
    "SELL_PUT":  "🟠 Sell Put",
    "HOLD":      "⏸ Hold",
    "WAIT":      "⏳ Wait",
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

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"QFrame{{background:{BORDER};max-height:1px;border:none;}}")
        layout.addWidget(sep)

        # Stats row
        stats = QHBoxLayout()
        self._rules_lbl  = self._stat_lbl("0 rules")
        self._updated_lbl = self._stat_lbl("—")
        stats.addWidget(self._rules_lbl)
        stats.addStretch()
        stats.addWidget(self._updated_lbl)
        layout.addLayout(stats)

    def _stat_lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{DIM}; font-size:8pt;")
        return lbl

    def update(self, strategy: Dict, current_signal: str = "WAIT"):
        meta = strategy.get("meta", {})
        self._name_lbl.setText(meta.get("name", "—"))
        desc = meta.get("description", "")
        self._desc_lbl.setText(desc[:100] + ("…" if len(desc) > 100 else ""))
        self._desc_lbl.setVisible(bool(desc))

        # Rules count
        engine = strategy.get("engine", {})
        total = sum(len(engine.get(sig, {}).get("rules", [])) for sig in SIGNAL_GROUPS)
        self._rules_lbl.setText(f"{total} rule{'s' if total != 1 else ''}")

        # Updated
        upd = meta.get("updated_at", "—")
        if "T" in upd:
            upd = upd.replace("T", " ")[:16]
        self._updated_lbl.setText(f"saved {upd}")

        # Signal
        color = SIGNAL_COLORS.get(current_signal, "#484f58")
        label = SIGNAL_LABELS.get(current_signal, current_signal)
        self._signal_lbl.setText(label)
        self._signal_lbl.setStyleSheet(
            f"color:{color}; font-size:9pt; font-weight:bold;"
            f" background:{color}22; border:1px solid {color}55;"
            f" border-radius:4px; padding:2px 7px;"
        )


class StrategyPickerSidebar(QDialog):
    """
    Compact floating sidebar for switching active strategy.
    Non-modal — can stay open while trading.
    """
    strategy_activated  = pyqtSignal(str)   # emitted with slug
    open_editor_requested = pyqtSignal()    # user wants full editor

    def __init__(self, manager: StrategyManager, trading_app=None, parent=None):
        super().__init__(parent, Qt.Window | Qt.Tool)
        self.manager = manager
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

    def _build_ui(self):
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

    def refresh(self):
        """Reload the strategy list from manager."""
        self._list.blockSignals(True)
        self._list.clear()
        strategies = self.manager.list_strategies()
        active_slug = self.manager.get_active_slug()

        for s in strategies:
            item = QListWidgetItem()
            is_active = s["is_active"]
            engine = (self.manager.get(s["slug"]) or {}).get("engine", {})
            total_rules = sum(len(engine.get(sig, {}).get("rules", [])) for sig in SIGNAL_GROUPS)

            # Build item text
            prefix = "⚡" if is_active else "  "
            item.setText(f"{prefix}  {s['name']}")
            item.setData(Qt.UserRole, s["slug"])
            item.setToolTip(
                f"{s['description']}\n{total_rules} rules | updated {s['updated_at'][:16] if s['updated_at'] else '—'}"
            )
            if is_active:
                item.setForeground(QColor(BLUE))
                item.setFont(QFont("", -1, QFont.Bold))
            self._list.addItem(item)

        self._list.blockSignals(False)

        # Update active card
        active_data = self.manager.get_active()
        if active_data:
            self._card.update(active_data, self._current_signal)

    @pyqtSlot()
    def _refresh_signal(self):
        """Pull current signal from trading_app and update card."""
        if not self.isVisible():
            return
        try:
            state = getattr(self.trading_app, "state", None) if self.trading_app else None
            if state is None:
                return
            trend = getattr(state, "derivative_trend", None) or {}
            sig_data = trend.get("option_signal", {})
            self._current_signal = sig_data.get("signal_value", "WAIT")
            active = self.manager.get_active()
            if active:
                self._card.update(active, self._current_signal)
        except Exception:
            pass

    def _on_double_click(self, item):
        slug = item.data(Qt.UserRole)
        self._activate(slug)

    def _on_activate(self):
        item = self._list.currentItem()
        if item:
            slug = item.data(Qt.UserRole)
            self._activate(slug)

    def _activate(self, slug: str):
        ok = self.manager.activate(slug)
        if ok:
            self.refresh()
            self.strategy_activated.emit(slug)
            name = (self.manager.get(slug) or {}).get("meta", {}).get("name", slug)
            self._status_lbl.setText(f"✓ Activated: {name}")
            QTimer.singleShot(3000, self._status_lbl.clear)

    def _on_open_editor(self):
        self.open_editor_requested.emit()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)